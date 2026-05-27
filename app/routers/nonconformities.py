"""No conformidades y acciones correctivas — ISO 27001:2022 cl. 10.1."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NCStatus, NonConformity, User
from app.schemas import NonConformityIn, NonConformityOut, NonConformityUpdate
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/nonconformities", tags=["nonconformities"])


def _next_code(db: Session) -> str:
    n = db.query(NonConformity).count() + 1
    return f"NC-{n:04d}"


@router.get("/", response_model=list[NonConformityOut])
def list_ncs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: Optional[NCStatus] = None,
    severity: Optional[str] = None,
):
    q = filter_by_org(db.query(NonConformity), NonConformity, current_user)
    if status:
        q = q.filter(NonConformity.status == status)
    if severity:
        q = q.filter(NonConformity.severity == severity)
    return q.order_by(NonConformity.created_at.desc()).all()


@router.get("/stats/summary")
def nc_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ncs = filter_by_org(db.query(NonConformity), NonConformity, current_user).all()
    now = datetime.now(timezone.utc)
    open_count = sum(1 for n in ncs if n.status != NCStatus.CLOSED)
    major_open = sum(1 for n in ncs if n.severity == "major" and n.status != NCStatus.CLOSED)
    overdue = sum(
        1 for n in ncs
        if n.due_date and n.status != NCStatus.CLOSED
        and n.due_date.replace(tzinfo=timezone.utc) < now
    )
    return {
        "total": len(ncs),
        "open": open_count,
        "major_open": major_open,
        "overdue": overdue,
    }


@router.get("/{nc_id}", response_model=NonConformityOut)
def get_nc(nc_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    nc = db.query(NonConformity).filter(NonConformity.id == nc_id).first()
    if not nc or not check_org_access(nc.organization_id, current_user):
        raise HTTPException(404, "No conformidad no encontrada")
    return nc


@router.post("/", response_model=NonConformityOut)
def create_nc(body: NonConformityIn, db: Session = Depends(get_db),
              current_user: User = Depends(require_analyst)):
    nc = NonConformity(
        code=_next_code(db),
        organization_id=current_user.organization_id,
        title=body.title,
        description=body.description,
        source=body.source,
        severity=body.severity,
        iso_clause=body.iso_clause,
        root_cause=body.root_cause,
        corrective_action=body.corrective_action,
        due_date=body.due_date,
        evidence=body.evidence,
        owner_id=body.owner_id,
        related_control_id=body.related_control_id,
        related_risk_id=body.related_risk_id,
    )
    db.add(nc)
    db.commit()
    db.refresh(nc)
    log_action(db, current_user.id, "create", "nonconformity", str(nc.id),
               {"code": nc.code, "severity": nc.severity.value})
    return nc


@router.patch("/{nc_id}", response_model=NonConformityOut)
def update_nc(nc_id: int, body: NonConformityUpdate,
              db: Session = Depends(get_db),
              current_user: User = Depends(require_analyst)):
    nc = db.query(NonConformity).filter(NonConformity.id == nc_id).first()
    if not nc or not check_org_access(nc.organization_id, current_user):
        raise HTTPException(404, "No conformidad no encontrada")
    update_data = body.model_dump(exclude_none=True)
    # Si se cierra la NC, registrar fecha de cierre
    if update_data.get("status") == NCStatus.CLOSED and not nc.closed_at:
        update_data["closed_at"] = datetime.now(timezone.utc)
    for field, value in update_data.items():
        setattr(nc, field, value)
    db.commit()
    db.refresh(nc)
    log_action(db, current_user.id, "update", "nonconformity", str(nc.id))
    return nc


@router.delete("/{nc_id}", status_code=204)
def delete_nc(nc_id: int, db: Session = Depends(get_db),
              current_user: User = Depends(require_analyst)):
    nc = db.query(NonConformity).filter(NonConformity.id == nc_id).first()
    if not nc or not check_org_access(nc.organization_id, current_user):
        raise HTTPException(404, "No conformidad no encontrada")
    log_action(db, current_user.id, "delete", "nonconformity", str(nc_id), {"code": nc.code})
    db.delete(nc)
    db.commit()
