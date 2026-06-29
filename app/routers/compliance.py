"""Router de cumplimiento normativo multi-framework."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import User, RiskContext, ComplianceFrameworkStatus, ComplianceRequirementStatus
from app.security import get_current_user, require_role
from app.services.compliance_service import (
    list_available_frameworks,
    load_framework,
    get_framework_compliance_status,
    get_multi_framework_dashboard,
    initialize_org_framework,
    auto_update_compliance_from_controls,
)

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


def _filter_org(user: User) -> Optional[int]:
    from app.models import UserRole
    if user.role == UserRole.SUPERADMIN:
        return None
    return user.organization_id


@router.get("/frameworks")
def list_frameworks(current_user: User = Depends(get_current_user)):
    """Lista todos los frameworks disponibles con metadata."""
    return list_available_frameworks()


@router.get("/frameworks/{code}")
def get_framework_detail(
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Detalle completo de un framework."""
    fw = load_framework(code)
    if not fw:
        raise HTTPException(404, "Framework no encontrado")
    return fw


@router.get("/status")
def get_compliance_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dashboard de cumplimiento multi-framework para la org del usuario."""
    org_id = _filter_org(current_user)
    if not org_id:
        return {"frameworks": [], "overall_pct": 0, "message": "Selecciona una organizacion para ver el cumplimiento."}
    return get_multi_framework_dashboard(db, org_id)


@router.get("/status/{framework_code}")
def get_framework_status(
    framework_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Estado de cumplimiento de un framework específico."""
    org_id = _filter_org(current_user)
    if not org_id:
        raise HTTPException(403, "Se requiere organization_id")
    fw = load_framework(framework_code)
    if not fw:
        raise HTTPException(404, "Framework no encontrado")
    return get_framework_compliance_status(db, org_id, framework_code)


class FrameworkSubscribeIn(BaseModel):
    frameworks: list[str]


@router.post("/subscribe")
def subscribe_frameworks(
    body: FrameworkSubscribeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Org selecciona qué frameworks debe cumplir. Inicializa requisitos."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")

    # Validar que todos los frameworks existen
    for code in body.frameworks:
        if not load_framework(code):
            raise HTTPException(404, f"Framework '{code}' no encontrado")

    # Actualizar RiskContext
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    if not ctx:
        raise HTTPException(404, "Contexto de riesgo no configurado")

    ctx.active_frameworks = body.frameworks
    db.commit()

    # Inicializar requisitos para cada framework
    totals = {}
    for code in body.frameworks:
        created = initialize_org_framework(db, org_id, code)
        totals[code] = created

    return {"message": "Frameworks configurados", "initialized": totals}


class RequirementUpdateIn(BaseModel):
    status: str
    completion_pct: Optional[int] = None
    notes: Optional[str] = None
    responsible_id: Optional[int] = None


@router.put("/requirements/{framework_code}/{requirement_id}")
def update_requirement(
    framework_code: str,
    requirement_id: str,
    body: RequirementUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Actualiza el estado de un requisito de compliance."""
    org_id = _filter_org(current_user)
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")

    # Validar status
    valid_statuses = [s.value for s in ComplianceRequirementStatus]
    if body.status not in valid_statuses:
        raise HTTPException(400, f"Status inválido. Válidos: {valid_statuses}")

    req = db.query(ComplianceFrameworkStatus).filter(
        ComplianceFrameworkStatus.organization_id == org_id,
        ComplianceFrameworkStatus.framework_code == framework_code,
        ComplianceFrameworkStatus.requirement_id == requirement_id,
    ).first()

    if not req:
        req = ComplianceFrameworkStatus(
            organization_id=org_id,
            framework_code=framework_code,
            requirement_id=requirement_id,
            status=body.status,
        )
        db.add(req)
    else:
        req.status = body.status
    if body.completion_pct is not None:
        req.completion_pct = max(0, min(100, body.completion_pct))
    if body.notes is not None:
        req.notes = body.notes
    if body.responsible_id is not None:
        req.responsible_id = body.responsible_id

    req.last_reviewed_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Requisito actualizado", "id": req.id}


@router.post("/sync-controls")
def sync_controls(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Actualiza estado de compliance basado en controles implementados."""
    org_id = _filter_org(current_user)
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    updated = auto_update_compliance_from_controls(db, org_id)
    return {"message": "Compliance sincronizado", "updated": updated}
