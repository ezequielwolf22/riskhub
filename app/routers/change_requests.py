"""Router de Change Management — ISO 27001 cl. 6.3."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from app.i18n import get_lang, t as _t

from app.database import get_db
from app.models import ChangeRequest, User
from app.security import get_current_user, require_admin, require_analyst
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.change_requests")

router = APIRouter(prefix="/api/change-requests", tags=["change-requests"])

VALID_STATUSES = ("draft", "under_review", "approved", "rejected", "implemented", "verified")
VALID_TYPES = ("policy", "control", "asset", "process", "infrastructure", "other")
VALID_IMPACTS = ("none", "low", "medium", "high")


def _next_code(db: Session, org_id: int) -> str:
    count = db.query(ChangeRequest).filter_by(organization_id=org_id).count()
    return f"CHG-{count + 1:04d}"


def _chg_to_dict(c: ChangeRequest) -> dict:
    return {
        "id": c.id,
        "organization_id": c.organization_id,
        "code": c.code,
        "title": c.title,
        "change_type": c.change_type,
        "description": c.description,
        "business_reason": c.business_reason,
        "affected_asset_ids": c.affected_asset_ids,
        "affected_control_ids": c.affected_control_ids,
        "affected_policy_ids": c.affected_policy_ids,
        "risk_impact": c.risk_impact,
        "risk_assessment": c.risk_assessment,
        "status": c.status,
        "requested_by_id": c.requested_by_id,
        "reviewed_by_id": c.reviewed_by_id,
        "approved_by_id": c.approved_by_id,
        "planned_date": c.planned_date.isoformat() if c.planned_date else None,
        "implemented_at": c.implemented_at.isoformat() if c.implemented_at else None,
        "verification_notes": c.verification_notes,
        "verified_by_id": c.verified_by_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "urgency": c.urgency,
        "rollback_plan": c.rollback_plan,
        "approval_evidence": c.approval_evidence,
        "iso_clause_ref": c.iso_clause_ref,
    }


class ChangeRequestCreate(BaseModel):
    title: str
    change_type: str
    description: Optional[str] = None
    business_reason: Optional[str] = None
    affected_asset_ids: Optional[list] = None
    affected_control_ids: Optional[list] = None
    affected_policy_ids: Optional[list] = None
    risk_impact: Optional[str] = "low"
    risk_assessment: Optional[str] = None
    planned_date: Optional[str] = None
    urgency: Optional[str] = "normal"
    rollback_plan: Optional[str] = None
    approval_evidence: Optional[str] = None
    iso_clause_ref: Optional[str] = None


class ChangeRequestUpdate(BaseModel):
    title: Optional[str] = None
    change_type: Optional[str] = None
    description: Optional[str] = None
    business_reason: Optional[str] = None
    affected_asset_ids: Optional[list] = None
    affected_control_ids: Optional[list] = None
    affected_policy_ids: Optional[list] = None
    risk_impact: Optional[str] = None
    risk_assessment: Optional[str] = None
    planned_date: Optional[str] = None
    verification_notes: Optional[str] = None
    urgency: Optional[str] = None
    rollback_plan: Optional[str] = None
    approval_evidence: Optional[str] = None
    iso_clause_ref: Optional[str] = None


class RejectBody(BaseModel):
    reason: Optional[str] = None


@router.get("")
def list_changes(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    changes = (
        db.query(ChangeRequest)
        .filter_by(organization_id=current_user.organization_id)
        .order_by(ChangeRequest.created_at.desc())
        .all()
    )
    return [_chg_to_dict(c) for c in changes]


@router.post("", status_code=201)
def create_change(
    request: Request,
    body: ChangeRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    if body.change_type not in VALID_TYPES:
        raise HTTPException(422, _t("common.bad_request", lang))
    if body.risk_impact and body.risk_impact not in VALID_IMPACTS:
        raise HTTPException(422, _t("common.bad_request", lang))

    planned = None
    if body.planned_date:
        try:
            planned = datetime.fromisoformat(body.planned_date)
        except ValueError:
            pass

    org_id = current_user.organization_id
    chg = ChangeRequest(
        organization_id=org_id,
        code=_next_code(db, org_id),
        title=body.title,
        change_type=body.change_type,
        description=body.description,
        business_reason=body.business_reason,
        affected_asset_ids=body.affected_asset_ids or [],
        affected_control_ids=body.affected_control_ids or [],
        affected_policy_ids=body.affected_policy_ids or [],
        risk_impact=body.risk_impact or "low",
        risk_assessment=body.risk_assessment,
        planned_date=planned,
        status="draft",
        requested_by_id=current_user.id,
        urgency=body.urgency or "normal",
        rollback_plan=body.rollback_plan,
        approval_evidence=body.approval_evidence,
        iso_clause_ref=body.iso_clause_ref,
    )
    db.add(chg)
    db.commit()
    db.refresh(chg)
    log_action(db, current_user.id, "create", "change_request", str(chg.id), {"code": chg.code})
    return _chg_to_dict(chg)


@router.get("/{chg_id}")
def get_change(
    chg_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    chg = db.get(ChangeRequest, chg_id)
    if not chg or chg.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("change_requests.not_found", lang))
    return _chg_to_dict(chg)


@router.patch("/{chg_id}")
def update_change(
    chg_id: int,
    request: Request,
    body: ChangeRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    chg = db.get(ChangeRequest, chg_id)
    if not chg or chg.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("change_requests.not_found", lang))
    if chg.status in ("approved", "implemented", "verified"):
        raise HTTPException(400, _t("change_requests.cannot_modify_approved", lang))

    for field in ("title", "change_type", "description", "business_reason",
                  "affected_asset_ids", "affected_control_ids", "affected_policy_ids",
                  "risk_impact", "risk_assessment", "verification_notes",
                  "urgency", "rollback_plan", "approval_evidence", "iso_clause_ref"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(chg, field, val)
    if body.planned_date is not None:
        try:
            chg.planned_date = datetime.fromisoformat(body.planned_date)
        except ValueError:
            pass

    db.commit()
    return _chg_to_dict(chg)


@router.post("/{chg_id}/submit")
def submit_change(
    chg_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Analyst envia el cambio para revision del Admin."""
    chg = db.get(ChangeRequest, chg_id)
    if not chg or chg.organization_id != current_user.organization_id:
        raise HTTPException(404, "Cambio no encontrado")
    if chg.status != "draft":
        raise HTTPException(400, "Solo se pueden enviar cambios en borrador")

    chg.status = "under_review"
    db.commit()
    log_action(db, current_user.id, "submit", "change_request", str(chg_id), {})
    return _chg_to_dict(chg)


@router.post("/{chg_id}/approve")
def approve_change(
    chg_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin aprueba el cambio."""
    chg = db.get(ChangeRequest, chg_id)
    if not chg or chg.organization_id != current_user.organization_id:
        raise HTTPException(404, "Cambio no encontrado")
    if chg.status not in ("under_review", "draft"):
        raise HTTPException(400, "Estado no permite aprobacion")

    chg.status = "approved"
    chg.approved_by_id = current_user.id
    chg.reviewed_by_id = current_user.id
    db.commit()
    log_action(db, current_user.id, "approve", "change_request", str(chg_id), {})
    return _chg_to_dict(chg)


@router.post("/{chg_id}/reject")
def reject_change(
    chg_id: int,
    body: RejectBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin rechaza el cambio."""
    chg = db.get(ChangeRequest, chg_id)
    if not chg or chg.organization_id != current_user.organization_id:
        raise HTTPException(404, "Cambio no encontrado")

    chg.status = "rejected"
    chg.reviewed_by_id = current_user.id
    if body.reason:
        chg.risk_assessment = (chg.risk_assessment or "") + f"\nRechazo: {body.reason}"
    db.commit()
    log_action(db, current_user.id, "reject", "change_request", str(chg_id), {})
    return _chg_to_dict(chg)


@router.post("/{chg_id}/implement")
def implement_change(
    chg_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Marca el cambio como implementado."""
    chg = db.get(ChangeRequest, chg_id)
    if not chg or chg.organization_id != current_user.organization_id:
        raise HTTPException(404, "Cambio no encontrado")
    if chg.status != "approved":
        raise HTTPException(400, "Solo se pueden implementar cambios aprobados")

    chg.status = "implemented"
    chg.implemented_at = datetime.now(timezone.utc)
    db.commit()
    log_action(db, current_user.id, "implement", "change_request", str(chg_id), {})
    return _chg_to_dict(chg)


@router.post("/{chg_id}/verify")
def verify_change(
    chg_id: int,
    body: RejectBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Verifica post-implementacion."""
    chg = db.get(ChangeRequest, chg_id)
    if not chg or chg.organization_id != current_user.organization_id:
        raise HTTPException(404, "Cambio no encontrado")
    if chg.status != "implemented":
        raise HTTPException(400, "Solo se pueden verificar cambios implementados")

    chg.status = "verified"
    chg.verified_by_id = current_user.id
    if body.reason:
        chg.verification_notes = body.reason
    db.commit()
    log_action(db, current_user.id, "verify", "change_request", str(chg_id), {})
    return _chg_to_dict(chg)


@router.delete("/{chg_id}", status_code=204)
def delete_change(
    chg_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    chg = db.get(ChangeRequest, chg_id)
    if not chg or chg.organization_id != current_user.organization_id:
        raise HTTPException(404, "Cambio no encontrado")
    if chg.status in ("approved", "implemented", "verified"):
        raise HTTPException(400, "No se puede eliminar un cambio aprobado o implementado")
    db.delete(chg)
    db.commit()
