"""Router de Informes Programados — envio automatico via scheduler."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import ReportSchedule, User
from app.security import get_current_user, require_admin, require_analyst
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.report_schedules")

router = APIRouter(prefix="/api/report-schedules", tags=["report-schedules"])

VALID_REPORT_TYPES = ("risk_register", "soa", "executive_dashboard", "committee_minutes", "followup_report")
VALID_FREQUENCIES = ("weekly", "monthly", "quarterly")


def _calc_next_run(schedule_or_freq) -> datetime:
    """Calcula la proxima ejecucion basandose en la frecuencia."""
    now = datetime.now(timezone.utc)
    freq = schedule_or_freq if isinstance(schedule_or_freq, str) else schedule_or_freq.frequency
    if freq == "weekly":
        return now + timedelta(days=7)
    elif freq == "monthly":
        return now + timedelta(days=30)
    elif freq == "quarterly":
        return now + timedelta(days=90)
    return now + timedelta(days=30)


def _sched_to_dict(s: ReportSchedule) -> dict:
    return {
        "id": s.id,
        "organization_id": s.organization_id,
        "report_type": s.report_type,
        "frequency": s.frequency,
        "day_of_month": s.day_of_month,
        "recipients": s.recipients,
        "include_ai_analysis": s.include_ai_analysis,
        "is_active": s.is_active,
        "last_sent_at": s.last_sent_at.isoformat() if s.last_sent_at else None,
        "next_scheduled_at": s.next_scheduled_at.isoformat() if s.next_scheduled_at else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


class ScheduleCreate(BaseModel):
    report_type: str
    frequency: str
    day_of_month: Optional[int] = None
    recipients: List[str]
    include_ai_analysis: bool = False


class ScheduleUpdate(BaseModel):
    frequency: Optional[str] = None
    day_of_month: Optional[int] = None
    recipients: Optional[List[str]] = None
    include_ai_analysis: Optional[bool] = None
    is_active: Optional[bool] = None


@router.get("")
def list_schedules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista programaciones de informes para la organización del usuario.

    Superadmin puede ver todas las orgs; otros usuarios solo ven las de su org.
    """
    from app.models import UserRole

    # Superadmin ve todas; otros ven solo la de su org
    if current_user.role == UserRole.SUPERADMIN:
        scheds = db.query(ReportSchedule).order_by(ReportSchedule.created_at.desc()).all()
    else:
        if not current_user.organization_id:
            return []
        scheds = (
            db.query(ReportSchedule)
            .filter_by(organization_id=current_user.organization_id)
            .order_by(ReportSchedule.created_at.desc())
            .all()
        )
    return [_sched_to_dict(s) for s in scheds]


@router.post("", status_code=201)
def create_schedule(
    body: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if body.report_type not in VALID_REPORT_TYPES:
        raise HTTPException(422, f"report_type invalido. Validos: {VALID_REPORT_TYPES}")
    if body.frequency not in VALID_FREQUENCIES:
        raise HTTPException(422, f"frequency invalida. Validas: {VALID_FREQUENCIES}")
    if not body.recipients:
        raise HTTPException(422, "Se requiere al menos un destinatario")

    import re as _re
    _EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    for email in body.recipients:
        if not _EMAIL_RE.match(email):
            raise HTTPException(422, f"Email invalido: {email}")

    sched = ReportSchedule(
        organization_id=current_user.organization_id,
        report_type=body.report_type,
        frequency=body.frequency,
        day_of_month=body.day_of_month,
        recipients=body.recipients,
        include_ai_analysis=body.include_ai_analysis,
        is_active=True,
        next_scheduled_at=_calc_next_run(body.frequency),
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)
    log_action(db, current_user.id, "create", "report_schedule", str(sched.id),
               {"report_type": sched.report_type})
    return _sched_to_dict(sched)


@router.patch("/{sched_id}")
def update_schedule(
    sched_id: int,
    body: ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    sched = db.get(ReportSchedule, sched_id)
    if not sched or sched.organization_id != current_user.organization_id:
        raise HTTPException(404, "Programacion no encontrada")

    if body.frequency is not None:
        if body.frequency not in VALID_FREQUENCIES:
            raise HTTPException(422, f"frequency invalida")
        sched.frequency = body.frequency
        sched.next_scheduled_at = _calc_next_run(sched)
    if body.day_of_month is not None:
        sched.day_of_month = body.day_of_month
    if body.recipients is not None:
        sched.recipients = body.recipients
    if body.include_ai_analysis is not None:
        sched.include_ai_analysis = body.include_ai_analysis
    if body.is_active is not None:
        sched.is_active = body.is_active

    db.commit()
    return _sched_to_dict(sched)


@router.delete("/{sched_id}", status_code=204)
def delete_schedule(
    sched_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    sched = db.get(ReportSchedule, sched_id)
    if not sched or sched.organization_id != current_user.organization_id:
        raise HTTPException(404, "Programacion no encontrada")
    db.delete(sched)
    db.commit()


@router.post("/{sched_id}/run-now")
def run_now(
    sched_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Ejecuta el informe ahora (preview / envio inmediato)."""
    sched = db.get(ReportSchedule, sched_id)
    if not sched or sched.organization_id != current_user.organization_id:
        raise HTTPException(404, "Programacion no encontrada")

    try:
        from app.services import report_ai_service
        from app.services.email_service import get_settings, send_email

        cfg = get_settings(db, current_user.organization_id)
        if not cfg or not cfg.smtp_host:
            raise HTTPException(400, "SMTP no configurado")

        # Resolver api_key per-tenant
        try:
            from app.routers.ai_config import resolve_api_key
            api_key = resolve_api_key(db, current_user.organization_id)
        except Exception:
            api_key = None

        data = report_ai_service.generate(
            sched.report_type, db,
            org_id=current_user.organization_id,
            api_key=api_key,
            lang="es",
        )

        subject = f"[RiskHub] Informe: {sched.report_type}"
        body_html = "<p>Adjunto el informe generado por RiskHub.</p>"
        for email in (sched.recipients or []):
            try:
                send_email(cfg, email, subject, body_html)
            except Exception as exc:
                logger.warning("Error enviando informe a %s: %s", email, exc)

        sched.last_sent_at = datetime.now(timezone.utc)
        sched.next_scheduled_at = _calc_next_run(sched)
        db.commit()

        return {"status": "sent", "recipients": sched.recipients}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error en run_now: %s", exc)
        raise HTTPException(500, f"Error generando informe: {exc}")
