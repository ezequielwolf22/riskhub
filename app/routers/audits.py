"""Auditoria interna — ISO 27001 cl. 9.2."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditFinding, AuditProgram, AuditStatus, User
from app.schemas import (
    AuditFindingIn, AuditFindingOut,
    AuditProgramIn, AuditProgramOut, AuditProgramUpdate,
)
from app.security import get_current_user, require_analyst
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/audits", tags=["audits"])


def _next_code(db: Session) -> str:
    n = db.query(AuditProgram).count() + 1
    return f"AUD-{n:04d}"


@router.get("/", response_model=list[AuditProgramOut])
def list_audits(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    status: Optional[AuditStatus] = None,
):
    q = db.query(AuditProgram)
    if status:
        q = q.filter(AuditProgram.status == status)
    return q.order_by(AuditProgram.planned_start.desc()).all()


@router.get("/stats/summary")
def audits_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    audits = db.query(AuditProgram).all()
    findings = db.query(AuditFinding).all()
    from app.models import AuditFindingType
    open_major = sum(
        1 for f in findings
        if f.finding_type == AuditFindingType.MAJOR_NC and not f.nonconformity_id
    )
    return {
        "total_programs": len(audits),
        "total_findings": len(findings),
        "open_major_ncs": open_major,
        "by_status": {s.value: sum(1 for a in audits if a.status == s) for s in AuditStatus},
    }


@router.get("/{audit_id}", response_model=AuditProgramOut)
def get_audit(audit_id: int, db: Session = Depends(get_db),
              _: User = Depends(get_current_user)):
    a = db.query(AuditProgram).filter(AuditProgram.id == audit_id).first()
    if not a:
        raise HTTPException(404, "Auditoria no encontrada")
    return a


@router.post("/", response_model=AuditProgramOut)
def create_audit(body: AuditProgramIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_analyst)):
    a = AuditProgram(
        code=_next_code(db),
        title=body.title,
        audit_type=body.audit_type,
        scope=body.scope,
        objectives=body.objectives,
        criteria=body.criteria,
        auditor_lead=body.auditor_lead,
        auditor_team=body.auditor_team,
        planned_start=body.planned_start,
        planned_end=body.planned_end,
        owner_id=body.owner_id or current_user.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    log_action(db, current_user.id, "create", "audit", str(a.id), {"code": a.code})
    return a


@router.patch("/{audit_id}", response_model=AuditProgramOut)
def update_audit(audit_id: int, body: AuditProgramUpdate,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(require_analyst)):
    a = db.query(AuditProgram).filter(AuditProgram.id == audit_id).first()
    if not a:
        raise HTTPException(404, "Auditoria no encontrada")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(a, field, value)
    db.commit()
    db.refresh(a)
    log_action(db, current_user.id, "update", "audit", str(a.id))
    return a


@router.delete("/{audit_id}", status_code=204)
def delete_audit(audit_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(require_analyst)):
    a = db.query(AuditProgram).filter(AuditProgram.id == audit_id).first()
    if not a:
        raise HTTPException(404, "Auditoria no encontrada")
    log_action(db, current_user.id, "delete", "audit", str(audit_id))
    db.delete(a)
    db.commit()


# -- Findings sub-resource --

@router.get("/{audit_id}/findings", response_model=list[AuditFindingOut])
def list_findings(audit_id: int, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    return db.query(AuditFinding).filter(AuditFinding.audit_id == audit_id).all()


@router.post("/{audit_id}/findings", response_model=AuditFindingOut)
def create_finding(audit_id: int, body: AuditFindingIn,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(require_analyst)):
    a = db.query(AuditProgram).filter(AuditProgram.id == audit_id).first()
    if not a:
        raise HTTPException(404, "Auditoria no encontrada")
    f = AuditFinding(
        audit_id=audit_id,
        finding_type=body.finding_type,
        title=body.title,
        description=body.description,
        evidence=body.evidence,
        iso_clause=body.iso_clause,
        recommendation=body.recommendation,
        nonconformity_id=body.nonconformity_id,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    log_action(db, current_user.id, "create", "audit_finding", str(f.id))
    return f


@router.patch("/{audit_id}/findings/{finding_id}", response_model=AuditFindingOut)
def update_finding(audit_id: int, finding_id: int, body: AuditFindingIn,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(require_analyst)):
    f = db.query(AuditFinding).filter(
        AuditFinding.id == finding_id, AuditFinding.audit_id == audit_id
    ).first()
    if not f:
        raise HTTPException(404, "Hallazgo no encontrado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(f, field, value)
    db.commit()
    db.refresh(f)
    return f


@router.delete("/{audit_id}/findings/{finding_id}", status_code=204)
def delete_finding(audit_id: int, finding_id: int,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(require_analyst)):
    f = db.query(AuditFinding).filter(
        AuditFinding.id == finding_id, AuditFinding.audit_id == audit_id
    ).first()
    if not f:
        raise HTTPException(404, "Hallazgo no encontrado")
    db.delete(f)
    db.commit()
