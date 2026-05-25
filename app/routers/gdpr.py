"""GDPR — Registro de actividades de tratamiento (Art. 30) y DPIA (Art. 35)."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DPIA, DPIAStatus, ProcessingActivity, User
from app.schemas import (
    DPIAIn, DPIAOut, DPIAUpdate,
    ProcessingActivityIn, ProcessingActivityOut, ProcessingActivityUpdate,
)
from app.security import get_current_user, require_analyst
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/gdpr", tags=["gdpr"])


def _next_pa_code(db: Session) -> str:
    n = db.query(ProcessingActivity).count() + 1
    return f"PAR-{n:04d}"


def _next_dpia_code(db: Session) -> str:
    n = db.query(DPIA).count() + 1
    return f"DPI-{n:04d}"


# ---------- Processing Activities ----------

@router.get("/activities/", response_model=list[ProcessingActivityOut])
def list_activities(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    requires_dpia: Optional[bool] = None,
    q: Optional[str] = None,
):
    query = db.query(ProcessingActivity)
    if requires_dpia is not None:
        query = query.filter(ProcessingActivity.requires_dpia == requires_dpia)
    if q:
        query = query.filter(ProcessingActivity.title.ilike(f"%{q}%"))
    return query.order_by(ProcessingActivity.updated_at.desc()).all()


@router.get("/stats/summary")
def gdpr_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    activities = db.query(ProcessingActivity).all()
    dpias = db.query(DPIA).all()
    return {
        "total_activities": len(activities),
        "requires_dpia": sum(1 for a in activities if a.requires_dpia),
        "transfers_outside_eu": sum(1 for a in activities if a.transfers_outside_eu),
        "total_dpias": len(dpias),
        "dpias_pending": sum(1 for d in dpias if d.status == DPIAStatus.PENDING),
    }


@router.get("/activities/{activity_id}", response_model=ProcessingActivityOut)
def get_activity(activity_id: int, db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    a = db.query(ProcessingActivity).filter(ProcessingActivity.id == activity_id).first()
    if not a:
        raise HTTPException(404, "Actividad de tratamiento no encontrada")
    return a


@router.post("/activities/", response_model=ProcessingActivityOut)
def create_activity(body: ProcessingActivityIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    a = ProcessingActivity(
        code=_next_pa_code(db),
        title=body.title,
        purposes=body.purposes,
        legal_basis=body.legal_basis,
        data_categories=body.data_categories,
        data_subjects=body.data_subjects,
        recipients=body.recipients,
        transfers_outside_eu=body.transfers_outside_eu,
        transfer_safeguards=body.transfer_safeguards,
        retention_period=body.retention_period,
        security_measures=body.security_measures,
        controller_name=body.controller_name,
        dpo_contact=body.dpo_contact,
        requires_dpia=body.requires_dpia,
        owner_id=body.owner_id or current_user.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    log_action(db, current_user.id, "create", "processing_activity", str(a.id), {"code": a.code})
    return a


@router.patch("/activities/{activity_id}", response_model=ProcessingActivityOut)
def update_activity(activity_id: int, body: ProcessingActivityUpdate,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    a = db.query(ProcessingActivity).filter(ProcessingActivity.id == activity_id).first()
    if not a:
        raise HTTPException(404, "Actividad de tratamiento no encontrada")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(a, field, value)
    db.commit()
    db.refresh(a)
    log_action(db, current_user.id, "update", "processing_activity", str(a.id))
    return a


@router.delete("/activities/{activity_id}", status_code=204)
def delete_activity(activity_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    a = db.query(ProcessingActivity).filter(ProcessingActivity.id == activity_id).first()
    if not a:
        raise HTTPException(404, "Actividad de tratamiento no encontrada")
    db.delete(a)
    db.commit()


# ---------- DPIAs ----------

@router.get("/dpias/", response_model=list[DPIAOut])
def list_dpias(db: Session = Depends(get_db), _: User = Depends(get_current_user),
               activity_id: Optional[int] = None):
    q = db.query(DPIA)
    if activity_id:
        q = q.filter(DPIA.activity_id == activity_id)
    return q.order_by(DPIA.created_at.desc()).all()


@router.get("/dpias/{dpia_id}", response_model=DPIAOut)
def get_dpia(dpia_id: int, db: Session = Depends(get_db),
             _: User = Depends(get_current_user)):
    d = db.query(DPIA).filter(DPIA.id == dpia_id).first()
    if not d:
        raise HTTPException(404, "DPIA no encontrado")
    return d


@router.post("/dpias/", response_model=DPIAOut)
def create_dpia(body: DPIAIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    d = DPIA(
        code=_next_dpia_code(db),
        activity_id=body.activity_id,
        title=body.title,
        necessity_assessment=body.necessity_assessment,
        risks_identified=body.risks_identified,
        risk_measures=body.risk_measures,
        residual_risk_level=body.residual_risk_level,
        dpo_opinion=body.dpo_opinion,
        owner_id=body.owner_id or current_user.id,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    log_action(db, current_user.id, "create", "dpia", str(d.id), {"code": d.code})
    return d


@router.patch("/dpias/{dpia_id}", response_model=DPIAOut)
def update_dpia(dpia_id: int, body: DPIAUpdate,
                db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    d = db.query(DPIA).filter(DPIA.id == dpia_id).first()
    if not d:
        raise HTTPException(404, "DPIA no encontrado")
    update_data = body.model_dump(exclude_none=True)
    if update_data.get("status") == DPIAStatus.APPROVED and not d.reviewed_at:
        update_data.setdefault("reviewed_at", datetime.now(timezone.utc))
        update_data.setdefault("approved_by_id", current_user.id)
    for field, value in update_data.items():
        setattr(d, field, value)
    db.commit()
    db.refresh(d)
    log_action(db, current_user.id, "update", "dpia", str(d.id))
    return d


@router.delete("/dpias/{dpia_id}", status_code=204)
def delete_dpia(dpia_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    d = db.query(DPIA).filter(DPIA.id == dpia_id).first()
    if not d:
        raise HTTPException(404, "DPIA no encontrado")
    db.delete(d)
    db.commit()
