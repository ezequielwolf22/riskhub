"""Router de aprobacion documental — rondas paralelas y secuenciales."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import ApprovalRequest, Policy, User
from app.security import get_current_user, require_role
from app.services import approval_service

router = APIRouter(prefix="/api/policy-approvals", tags=["policy-approvals"])
public_router = APIRouter(prefix="/api/approvals", tags=["approvals-public"])


# ---------- Schemas ----------

class ApproverIn(BaseModel):
    email: str
    name: Optional[str] = None
    order_index: int = 1


class ApprovalRequestIn(BaseModel):
    approvers: list[ApproverIn]
    mode: str = "parallel"  # parallel | sequential


class DecisionIn(BaseModel):
    decision: str   # approved | rejected
    notes: Optional[str] = None


# ---------- Endpoints autenticados ----------

def _app_base_url(request: Request) -> str:
    """Detecta la URL base de la aplicacion para incluir en emails."""
    fwd_proto = request.headers.get("x-forwarded-proto", "")
    fwd_host = request.headers.get("x-forwarded-host", "")
    if fwd_proto and fwd_host:
        return f"{fwd_proto}://{fwd_host}"
    return str(request.base_url).rstrip("/")


@router.post("/{policy_id}/requests")
def create_approval_request(
    policy_id: int,
    body: ApprovalRequestIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lang = get_lang(request)
    policy = db.query(Policy).filter_by(id=policy_id).first()
    if not policy:
        raise HTTPException(404, _t("policy_approvals.policy_not_found", lang))
    if policy.organization_id and policy.organization_id != current_user.organization_id:
        raise HTTPException(403, _t("policy_approvals.access_denied", lang))
    if not body.approvers:
        raise HTTPException(422, _t("policy_approvals.at_least_one_approver", lang))

    if body.mode not in ("parallel", "sequential"):
        raise HTTPException(422, _t("policy_approvals.invalid_mode", lang))

    approvers = [{"email": a.email, "name": a.name, "order_index": a.order_index}
                 for a in body.approvers]

    req = approval_service.create_approval_request(
        db=db,
        policy_id=policy_id,
        requested_by_id=current_user.id,
        approvers=approvers,
        mode=body.mode,
        org_id=current_user.organization_id,
        app_base_url=_app_base_url(request),
    )
    return {"id": req.id, "status": req.status, "mode": req.mode, "total": len(req.approvals)}


@router.get("/{policy_id}/requests")
def list_approval_requests(
    policy_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lang = get_lang(request)
    policy = db.query(Policy).filter_by(id=policy_id).first()
    if not policy:
        raise HTTPException(404, _t("policy_approvals.policy_not_found", lang))

    reqs = (
        db.query(ApprovalRequest)
        .filter_by(policy_id=policy_id)
        .order_by(ApprovalRequest.created_at.desc())
        .all()
    )

    result = []
    for r in reqs:
        approvals = [
            {
                "id": a.id,
                "email": a.approver_email,
                "name": a.approver_name,
                "status": a.status,
                "order_index": a.order_index,
                "sent_at": a.sent_at.isoformat() if a.sent_at else None,
                "responded_at": a.responded_at.isoformat() if a.responded_at else None,
                "response_notes": a.response_notes,
                "ip_address": a.ip_address,
                "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            }
            for a in r.approvals
        ]
        result.append({
            "id": r.id,
            "mode": r.mode,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "requested_by": r.requested_by.email if r.requested_by else None,
            "approvals": approvals,
        })
    return result


@router.delete("/{policy_id}/requests/{req_id}", status_code=204)
def cancel_approval_request(
    policy_id: int,
    req_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lang = get_lang(request)
    req = db.query(ApprovalRequest).filter_by(id=req_id, policy_id=policy_id).first()
    if not req:
        raise HTTPException(404, _t("policy_approvals.request_not_found", lang))
    if req.status != "pending":
        raise HTTPException(409, _t("policy_approvals.only_pending_cancellable", lang))
    req.status = "cancelled"
    req.completed_at = datetime.now(timezone.utc)
    # Volver a borrador si estaba en revision
    policy = db.query(Policy).filter_by(id=policy_id).first()
    if policy and str(policy.status) in ("review",):
        from app.models import PolicyStatus
        policy.status = PolicyStatus.DRAFT
    db.commit()


# ---------- Endpoints publicos (sin autenticacion) ----------

@public_router.get("/info/{token}")
def get_approval_info(token: str, request: Request, db: Session = Depends(get_db)):
    """Retorna info del documento para la pagina publica de aprobacion."""
    lang = get_lang(request)
    info = approval_service.get_approval_info(db, token)
    if "error" in info:
        raise HTTPException(404, info["error"])
    return info


@public_router.post("/decide/{token}")
def decide_approval(
    token: str,
    body: DecisionIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Procesa la decision del aprobador (approve/reject) sin requerir login."""
    lang = get_lang(request)
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(422, _t("policy_approvals.invalid_decision", lang))

    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "")
    base = _app_base_url(request)

    result = approval_service.process_decision(
        db=db,
        token=token,
        decision=body.decision,
        notes=body.notes or "",
        ip_address=ip,
        app_base_url=base,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result
