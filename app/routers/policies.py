"""Gestion de politicas de seguridad — ISO 27001 cl. 5.2."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Policy, PolicyStatus, User
from app.schemas import PolicyIn, PolicyOut, PolicyUpdate
from app.security import get_current_user, require_analyst
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/policies", tags=["policies"])


def _next_code(db: Session) -> str:
    n = db.query(Policy).count() + 1
    return f"POL-{n:04d}"


@router.get("/", response_model=list[PolicyOut])
def list_policies(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    status: Optional[PolicyStatus] = None,
    category: Optional[str] = None,
    q: Optional[str] = None,
):
    query = db.query(Policy)
    if status:
        query = query.filter(Policy.status == status)
    if category:
        query = query.filter(Policy.category.ilike(f"%{category}%"))
    if q:
        query = query.filter(Policy.title.ilike(f"%{q}%"))
    return query.order_by(Policy.updated_at.desc()).all()


@router.get("/stats/summary")
def policies_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    policies = db.query(Policy).all()
    now = datetime.now(timezone.utc)
    overdue_review = sum(
        1 for p in policies
        if p.review_date and p.status not in (PolicyStatus.OBSOLETE,)
        and p.review_date.replace(tzinfo=timezone.utc) < now
    )
    by_status = {s.value: sum(1 for p in policies if p.status == s) for s in PolicyStatus}
    return {
        "total": len(policies),
        "overdue_review": overdue_review,
        "by_status": by_status,
    }


@router.get("/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: int, db: Session = Depends(get_db),
               _: User = Depends(get_current_user)):
    p = db.query(Policy).filter(Policy.id == policy_id).first()
    if not p:
        raise HTTPException(404, "Politica no encontrada")
    return p


@router.post("/", response_model=PolicyOut)
def create_policy(body: PolicyIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_analyst)):
    p = Policy(
        code=_next_code(db),
        title=body.title,
        version=body.version,
        category=body.category,
        status=body.status,
        scope=body.scope,
        content=body.content,
        iso_clauses=body.iso_clauses,
        review_date=body.review_date,
        owner_id=body.owner_id or current_user.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    log_action(db, current_user.id, "create", "policy", str(p.id), {"code": p.code})
    return p


@router.patch("/{policy_id}", response_model=PolicyOut)
def update_policy(policy_id: int, body: PolicyUpdate,
                  db: Session = Depends(get_db),
                  current_user: User = Depends(require_analyst)):
    p = db.query(Policy).filter(Policy.id == policy_id).first()
    if not p:
        raise HTTPException(404, "Politica no encontrada")
    update_data = body.model_dump(exclude_none=True)
    # Auto-stamp approved_at when approving
    if update_data.get("status") == PolicyStatus.APPROVED and not p.approved_at:
        update_data.setdefault("approved_at", datetime.now(timezone.utc))
        update_data.setdefault("approved_by_id", current_user.id)
    for field, value in update_data.items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)
    log_action(db, current_user.id, "update", "policy", str(p.id))
    return p


@router.delete("/{policy_id}", status_code=204)
def delete_policy(policy_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(require_analyst)):
    p = db.query(Policy).filter(Policy.id == policy_id).first()
    if not p:
        raise HTTPException(404, "Politica no encontrada")
    log_action(db, current_user.id, "delete", "policy", str(policy_id), {"title": p.title})
    db.delete(p)
    db.commit()
