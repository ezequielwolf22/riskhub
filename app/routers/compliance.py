"""Router de cumplimiento normativo multi-framework."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.i18n import get_lang, t as _t
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
def list_frameworks(request: Request, current_user: User = Depends(get_current_user)):
    """Lista todos los frameworks disponibles con metadata."""
    return list_available_frameworks(get_lang(request))


@router.get("/frameworks/{code}")
def get_framework_detail(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Detalle completo de un framework."""
    lang = get_lang(request)
    fw = load_framework(code, lang)
    if not fw:
        raise HTTPException(404, _t("compliance.not_found", lang))
    return fw


@router.get("/status")
def get_compliance_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dashboard de cumplimiento multi-framework para la org del usuario."""
    lang = get_lang(request)
    org_id = _filter_org(current_user)
    if not org_id:
        return {"frameworks": [], "overall_pct": 0, "message": _t("compliance.select_org_message", lang)}
    return get_multi_framework_dashboard(db, org_id, lang)


@router.get("/status/{framework_code}")
def get_framework_status(
    framework_code: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Estado de cumplimiento de un framework específico."""
    lang = get_lang(request)
    org_id = _filter_org(current_user)
    if not org_id:
        raise HTTPException(403, _t("compliance.org_required", lang))
    fw = load_framework(framework_code, lang)
    if not fw:
        raise HTTPException(404, _t("compliance.not_found", lang))
    result = get_framework_compliance_status(db, org_id, framework_code, lang)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


class FrameworkSubscribeIn(BaseModel):
    frameworks: list[str]


@router.post("/subscribe")
def subscribe_frameworks(
    body: FrameworkSubscribeIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Org selecciona qué frameworks debe cumplir. Inicializa requisitos."""
    lang = get_lang(request)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, _t("compliance.org_required", lang))

    # Validar que todos los frameworks existen
    for code in body.frameworks:
        if not load_framework(code):
            raise HTTPException(404, _t("compliance.framework_code_not_found", lang, code=code))

    # Actualizar RiskContext
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    if not ctx:
        raise HTTPException(404, _t("compliance.risk_context_not_configured", lang))

    ctx.active_frameworks = body.frameworks
    db.flush()

    # Inicializar requisitos para cada framework (commit unico al final)
    totals = {}
    for code in body.frameworks:
        created = initialize_org_framework(db, org_id, code)
        totals[code] = created

    db.commit()
    return {"message": _t("compliance.frameworks_configured", lang), "initialized": totals}


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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Actualiza el estado de un requisito de compliance."""
    lang = get_lang(request)
    org_id = _filter_org(current_user)
    if not org_id:
        raise HTTPException(400, _t("compliance.org_required", lang))

    # Validar status
    valid_statuses = [s.value for s in ComplianceRequirementStatus]
    if body.status not in valid_statuses:
        raise HTTPException(400, _t("compliance.invalid_status", lang, valid=valid_statuses))

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
            raise HTTPException(400, _t("compliance.responsible_not_in_org", lang))
        req.responsible_id = body.responsible_id

    req.last_reviewed_at = datetime.now(timezone.utc)
    # F4 — procedencia: decision humana. Tiene la maxima precedencia (junto con
    # auditor); los recalculos automaticos ya no la pisan.
    req.source = "human_manual"
    req.source_ref = f"user:{current_user.id}"
    req.rationale = (body.notes or "").strip()[:500] or "Marcado manualmente por un analista."
    req.computed_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": _t("compliance.requirement_updated", lang), "id": req.id}


@router.get("/requirements/{framework_code}/{requirement_id}/provenance")
def get_requirement_provenance(
    framework_code: str,
    requirement_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Procedencia del estado de un requisito: por que esta como esta (F4).

    Responde "por que esta en verde" con la fuente (auditor/humano/contenido IA/
    controles/heuristica), la referencia (documento, control, usuario), la
    explicacion y cuando se calculo. Ademas lista las evidencias que lo sostienen.
    """
    lang = get_lang(request)
    org_id = _filter_org(current_user)
    if not org_id:
        raise HTTPException(400, _t("compliance.org_required", lang))

    req = db.query(ComplianceFrameworkStatus).filter(
        ComplianceFrameworkStatus.organization_id == org_id,
        ComplianceFrameworkStatus.framework_code == framework_code,
        ComplianceFrameworkStatus.requirement_id == requirement_id,
    ).first()
    if not req:
        raise HTTPException(404, _t("compliance.not_found", lang))

    from app.models import Evidence
    ev_rows = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.compliance_framework == framework_code,
        Evidence.compliance_requirement == requirement_id,
        Evidence.is_current == True,  # noqa: E712
    ).all()
    evidences = [{
        "id": e.id,
        "code": e.code,
        "title": e.title,
        "auto_generated": bool(getattr(e, "auto_generated", False)),
        "verified": bool(isinstance(e.ai_review, dict) and e.ai_review.get("relevant") is True),
        "source_document_id": getattr(e, "source_document_id", None),
    } for e in ev_rows]

    return {
        "framework_code": framework_code,
        "requirement_id": requirement_id,
        "status": req.status.value if req.status else None,
        "completion_pct": req.completion_pct,
        "source": getattr(req, "source", None),
        "source_ref": getattr(req, "source_ref", None),
        "rationale": getattr(req, "rationale", None),
        "computed_at": req.computed_at.isoformat() if getattr(req, "computed_at", None) else None,
        "last_reviewed_at": req.last_reviewed_at.isoformat() if req.last_reviewed_at else None,
        "evidence_count": req.evidence_count,
        "evidences": evidences,
    }


@router.post("/sync-controls")
def sync_controls(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Actualiza estado de compliance basado en controles implementados y evidencias."""
    lang = get_lang(request)
    org_id = _filter_org(current_user)
    if not org_id:
        raise HTTPException(400, _t("compliance.org_required", lang))
    updated = auto_update_compliance_from_controls(db, org_id)
    return {"message": _t("compliance.synced", lang), "updated": updated}


@router.get("/evidence-gaps")
def get_evidence_gaps(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Requisitos con controles implementados pero sin evidencia — bloqueantes para auditoria."""
    lang = get_lang(request)
    org_id = _filter_org(current_user)
    if not org_id:
        return {"frameworks": [], "total_gaps": 0}

    from app.services.compliance_service import get_framework_compliance_status, get_multi_framework_dashboard
    from app.models import RiskContext
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    active = (ctx.active_frameworks or []) if ctx else []

    result = []
    for fw_code in active:
        fw_status = get_framework_compliance_status(db, org_id, fw_code, lang)
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
            _t("compliance.evidence_gaps_msg", lang, n=total_gaps)
            if total_gaps else _t("compliance.no_evidence_gaps", lang)
        ),
    }
