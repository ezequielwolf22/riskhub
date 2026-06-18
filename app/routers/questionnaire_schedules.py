"""Planificacion periodica de cuestionarios de seguridad a proveedores."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import QuestionnaireSchedule, Supplier, User
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.questionnaire_schedules")

router = APIRouter(prefix="/api/questionnaire-schedules", tags=["questionnaire-schedules"])


class ScheduleIn(BaseModel):
    supplier_id: int
    title_template: str
    template_code: Optional[str] = None
    custom_template_id: Optional[int] = None
    interval_days: int = 365
    expires_days: int = 30
    notify_email: Optional[str] = None
    notes: Optional[str] = None
    enabled: bool = True
    next_send_at: Optional[datetime] = None


class ScheduleUpdate(BaseModel):
    title_template: Optional[str] = None
    template_code: Optional[str] = None
    custom_template_id: Optional[int] = None
    interval_days: Optional[int] = None
    expires_days: Optional[int] = None
    notify_email: Optional[str] = None
    notes: Optional[str] = None
    enabled: Optional[bool] = None
    next_send_at: Optional[datetime] = None


def _schedule_out(s: QuestionnaireSchedule) -> dict:
    return {
        "id": s.id,
        "supplier_id": s.supplier_id,
        "supplier_name": s.supplier.name if s.supplier else None,
        "supplier_code": s.supplier.code if s.supplier else None,
        "title_template": s.title_template,
        "template_code": s.template_code,
        "custom_template_id": s.custom_template_id,
        "interval_days": s.interval_days,
        "expires_days": s.expires_days,
        "notify_email": s.notify_email,
        "notes": s.notes,
        "enabled": s.enabled,
        "next_send_at": s.next_send_at.isoformat() if s.next_send_at else None,
        "last_sent_at": s.last_sent_at.isoformat() if s.last_sent_at else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("/")
def list_schedules(
    supplier_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = filter_by_org(db.query(QuestionnaireSchedule), QuestionnaireSchedule, current_user)
    if supplier_id:
        q = q.filter(QuestionnaireSchedule.supplier_id == supplier_id)
    return [_schedule_out(s) for s in q.order_by(QuestionnaireSchedule.created_at.desc()).all()]


@router.get("/{sid}")
def get_schedule(sid: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    s = filter_by_org(
        db.query(QuestionnaireSchedule).filter(QuestionnaireSchedule.id == sid),
        QuestionnaireSchedule, current_user,
    ).first()
    if not s:
        raise HTTPException(404, "Planificacion no encontrada")
    return _schedule_out(s)


@router.post("/")
def create_schedule(body: ScheduleIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    supplier = db.query(Supplier).filter(Supplier.id == body.supplier_id).first()
    if not supplier or not check_org_access(supplier.organization_id, current_user):
        raise HTTPException(404, "Proveedor no encontrado")
    next_send = body.next_send_at or datetime.now(timezone.utc)
    s = QuestionnaireSchedule(
        organization_id=current_user.organization_id,
        supplier_id=body.supplier_id,
        title_template=body.title_template,
        template_code=body.template_code,
        custom_template_id=body.custom_template_id,
        interval_days=body.interval_days,
        expires_days=body.expires_days,
        notify_email=body.notify_email,
        notes=body.notes,
        enabled=body.enabled,
        next_send_at=next_send,
        created_by_id=current_user.id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    log_action(db, current_user.id, "create", "questionnaire_schedule", str(s.id),
               {"supplier": supplier.name})
    return _schedule_out(s)


@router.patch("/{sid}")
def update_schedule(sid: int, body: ScheduleUpdate,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    s = filter_by_org(
        db.query(QuestionnaireSchedule).filter(QuestionnaireSchedule.id == sid),
        QuestionnaireSchedule, current_user,
    ).first()
    if not s:
        raise HTTPException(404, "Planificacion no encontrada")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    log_action(db, current_user.id, "update", "questionnaire_schedule", str(s.id))
    return _schedule_out(s)


@router.delete("/{sid}", status_code=204)
def delete_schedule(sid: int, db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    s = filter_by_org(
        db.query(QuestionnaireSchedule).filter(QuestionnaireSchedule.id == sid),
        QuestionnaireSchedule, current_user,
    ).first()
    if not s:
        raise HTTPException(404, "Planificacion no encontrada")
    log_action(db, current_user.id, "delete", "questionnaire_schedule", str(s.id))
    db.delete(s)
    db.commit()
