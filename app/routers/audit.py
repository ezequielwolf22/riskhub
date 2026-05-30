"""Consulta del log de auditoria (solo administradores)."""
import csv
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditLog, User, UserRole
from app.security import get_current_user

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditEntryOut(BaseModel):
    id: int
    timestamp: datetime
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    detail: Optional[dict] = None


class AuditPage(BaseModel):
    total: int
    items: List[AuditEntryOut]


def _require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, "Solo administradores pueden consultar el log de auditoria")
    return current_user


def _filter_audit_by_org(q, current_user: User):
    """Superadmin ve todos los logs; admin solo ve los de su organizacion."""
    if current_user.role == UserRole.SUPERADMIN:
        return q
    return q.join(User, AuditLog.user_id == User.id, isouter=True).filter(
        (User.organization_id == current_user.organization_id) |
        (AuditLog.user_id.is_(None))
    )


@router.get("/", response_model=AuditPage)
def list_audit(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    date_from: Optional[str] = Query(None, description="ISO date string YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="ISO date string YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    from datetime import timezone, timedelta
    q = _filter_audit_by_org(db.query(AuditLog), current_user).order_by(AuditLog.timestamp.desc())
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    if action:
        q = q.filter(AuditLog.action == action)
    if date_from:
        try:
            from datetime import datetime as _dt
            dt_from = _dt.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            q = q.filter(AuditLog.timestamp >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import datetime as _dt
            dt_to = _dt.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            q = q.filter(AuditLog.timestamp < dt_to)
        except ValueError:
            pass
    total = q.count()
    entries = q.offset(skip).limit(limit).all()
    return AuditPage(
        total=total,
        items=[
            AuditEntryOut(
                id=e.id,
                timestamp=e.timestamp,
                user_email=e.user.email if e.user else None,
                user_name=e.user.full_name if e.user else None,
                action=e.action,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                detail=e.detail,
            )
            for e in entries
        ],
    )


@router.get("/history/{entity_type}/{entity_id}", response_model=List[AuditEntryOut])
def entity_history(
    entity_type: str,
    entity_id: str,
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Historial de cambios de una entidad especifica. Filtrado por org del usuario."""
    from app.models import UserRole
    # Superadmin ve todo; el resto solo logs de usuarios de su misma organizacion
    q = db.query(AuditLog).filter(
        AuditLog.entity_type == entity_type,
        AuditLog.entity_id == entity_id,
    )
    if current_user.role != UserRole.SUPERADMIN:
        from app.models import User as UserModel
        allowed_user_ids = [
            u.id for u in db.query(UserModel).filter(
                UserModel.organization_id == current_user.organization_id
            ).all()
        ]
        q = q.filter(
            (AuditLog.user_id.in_(allowed_user_ids)) | (AuditLog.user_id.is_(None))
        )
    entries = q.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [
        AuditEntryOut(
            id=e.id,
            timestamp=e.timestamp,
            user_email=e.user.email if e.user else None,
            user_name=e.user.full_name if e.user else None,
            action=e.action,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            detail=e.detail,
        )
        for e in entries
    ]


@router.get("/entity-types")
def entity_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Devuelve los tipos de entidad distintos registrados en el log."""
    types = _filter_audit_by_org(
        db.query(AuditLog.entity_type).distinct(), current_user
    ).all()
    return sorted([t[0] for t in types])


@router.get("/actions")
def actions(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Devuelve las acciones distintas registradas en el log."""
    acts = _filter_audit_by_org(
        db.query(AuditLog.action).distinct(), current_user
    ).all()
    return sorted([a[0] for a in acts])


@router.get("/export/csv")
def export_csv(
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Exporta el log completo (o filtrado) a CSV."""
    from datetime import timezone, timedelta
    q = _filter_audit_by_org(db.query(AuditLog), current_user).order_by(AuditLog.timestamp.desc())
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if action:
        q = q.filter(AuditLog.action == action)
    if date_from:
        try:
            from datetime import datetime as _dt
            dt_from = _dt.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            q = q.filter(AuditLog.timestamp >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import datetime as _dt
            dt_to = _dt.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            q = q.filter(AuditLog.timestamp < dt_to)
        except ValueError:
            pass
    entries = q.all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "timestamp", "user_email", "user_name",
                     "action", "entity_type", "entity_id", "detail"])
    for e in entries:
        writer.writerow([
            e.id,
            e.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            e.user.email if e.user else "",
            e.user.full_name if e.user else "",
            e.action,
            e.entity_type,
            e.entity_id or "",
            str(e.detail or {}),
        ])

    fname = f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.get("/audit-package")
def download_audit_package(
    include_evidence_files: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Descarga paquete ZIP de auditoría con attestation de integridad (hashes SHA-256).

    Incluye: riesgos, controles, compliance, audit trail, índice de evidencias.
    """
    from fastapi.responses import Response
    from app.services.audit_export_service import generate_audit_package

    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")

    zip_bytes = generate_audit_package(db, org_id, current_user, include_evidence_files)
    fname = f"riskhub_audit_package_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.get("/framework-package/{framework_code}")
def download_framework_audit_package(
    framework_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Descarga paquete ZIP de auditoría estructurado para un framework específico.

    Estructura oficial del framework: dominios, requisitos, evidencias, gaps, attestation.
    """
    from fastapi.responses import Response
    from app.services.audit_export_service import generate_framework_audit_package

    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")

    try:
        zip_bytes = generate_framework_audit_package(db, org_id, framework_code, current_user)
    except ValueError as e:
        raise HTTPException(404, str(e))

    fname = f"riskhub_{framework_code}_audit_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )
