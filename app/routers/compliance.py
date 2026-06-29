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
    result = get_framework_compliance_status(db, org_id, framework_code)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


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
    db.flush()

    # Inicializar requisitos para cada framework (commit unico al final)
    totals = {}
    for code in body.frameworks:
        created = initialize_org_framework(db, org_id, code)
        totals[code] = created

    db.commit()
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
            status=ComplianceRequirementStatus(body.status),
        )
        db.add(req)
        db.flush()
    else:
        req.status = ComplianceRequirementStatus(body.status)
    if body.completion_pct is not None:
        req.completion_pct = max(0, min(100, body.completion_pct))
    if body.notes is not None:
        req.notes = body.notes
    if body.responsible_id is not None:
        resp_user = db.get(User, body.responsible_id)
        if not resp_user or resp_user.organization_id != org_id:
            raise HTTPException(400, "responsible_id no pertenece a esta organizacion")
        req.responsible_id = body.responsible_id

    req.last_reviewed_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Requisito actualizado", "id": req.id}


@router.post("/sync-controls")
def sync_controls(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Actualiza estado de compliance basado en controles implementados y evidencias."""
    org_id = _filter_org(current_user)
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    updated = auto_update_compliance_from_controls(db, org_id)
    return {"message": "Compliance sincronizado", "updated": updated}


@router.get("/evidence-gaps")
def get_evidence_gaps(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Requisitos con controles implementados pero sin evidencia — bloqueantes para auditoria."""
    org_id = _filter_org(current_user)
    if not org_id:
        return {"frameworks": [], "total_gaps": 0}

    from app.services.compliance_service import get_framework_compliance_status, get_multi_framework_dashboard
    from app.models import RiskContext
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    active = (ctx.active_frameworks or []) if ctx else []

    result = []
    for fw_code in active:
        fw_status = get_framework_compliance_status(db, org_id, fw_code)
        if "error" in fw_status:
            continue
        result.append({
            "framework_code": fw_code,
            "framework_name": fw_status.get("framework_name", fw_code),
            "overall_pct": fw_status.get("overall_pct", 0),
            "total_requirements": fw_status.get("total_requirements", 0),
            "reqs_with_evidence": fw_status.get("reqs_with_evidence", 0),
            "total_evidence_count": fw_status.get("total_evidence_count", 0),
            "evidence_gaps": fw_status.get("evidence_gaps", []),
            "evidence_gap_count": len(fw_status.get("evidence_gaps", [])),
        })

    total_gaps = sum(f["evidence_gap_count"] for f in result)
    return {
        "frameworks": result,
        "total_gaps": total_gaps,
        "message": (
            f"{total_gaps} requisito(s) con controles implementados sin evidencia. "
            "Sube evidencias en /api/evidence para desbloquear el cumplimiento al 100%."
            if total_gaps else "Sin brechas de evidencia detectadas."
        ),
    }
