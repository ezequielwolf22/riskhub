"""Programador de tareas periodicas (APScheduler)."""
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("riskhub.scheduler")

_scheduler: BackgroundScheduler | None = None


def _run_alert_rules() -> None:
    """Evaluacion periodica de reglas de alerta activas."""
    from app.database import SessionLocal
    from app.models import AlertRule, Risk, RiskStatus
    from app.services import email_service

    db = SessionLocal()
    try:
        cfg = email_service.get_settings(db)
        if not cfg or not cfg.smtp_host:
            return  # SMTP no configurado — no hay nada que hacer

        from app.models import RiskContext
        ctx = db.query(RiskContext).first()
        org = ctx.organization_name if ctx else "Organizacion"

        rules = db.query(AlertRule).filter(AlertRule.is_active.is_(True)).all()
        if not rules:
            return

        risks = db.query(Risk).all()
        now = datetime.now(timezone.utc)
        sent = 0

        for rule in rules:
            matching = []
            if rule.event_type in ("risk_critical", "risk_high"):
                matching = [r for r in risks
                            if r.residual_level >= rule.threshold_level
                            and r.status not in (RiskStatus.ACCEPTED, RiskStatus.CLOSED)]
            elif rule.event_type == "treatment_overdue":
                matching = [r for r in risks
                            if r.treatment_due_date
                            and r.treatment_due_date.replace(tzinfo=timezone.utc) < now
                            and r.status not in (RiskStatus.TREATED, RiskStatus.ACCEPTED, RiskStatus.CLOSED)]
            elif rule.event_type == "risk_no_treatment":
                matching = [r for r in risks
                            if r.residual_level >= rule.threshold_level
                            and not r.treatment_option
                            and r.status not in (RiskStatus.ACCEPTED, RiskStatus.CLOSED)]

            reason_map = {
                "risk_critical": "supera el umbral critico",
                "risk_high": "supera el umbral alto configurado",
                "treatment_overdue": "tiene el plan de tratamiento vencido",
                "risk_no_treatment": "no tiene plan de tratamiento definido",
            }

            for risk in matching:
                subject = f"RiskHub — Alerta: {risk.code} ({org})"
                body_txt = f"El riesgo {risk.code} {reason_map.get(rule.event_type, '')}."
                try:
                    email_service.send_email(
                        cfg,
                        rule.recipient_email,
                        subject,
                        email_service.risk_alert_html(risk, org, body_txt),
                    )
                    sent += 1
                except Exception as exc:
                    logger.warning("Error enviando alerta para %s: %s", risk.code, exc)

            if matching:
                rule.last_triggered_at = now

        db.commit()
        if sent:
            logger.info("Evaluacion periodica: %d alertas enviadas (%d reglas).", sent, len(rules))
    except Exception as exc:
        logger.exception("Error en evaluacion periodica de reglas: %s", exc)
    finally:
        db.close()


def start(interval_hours: int = 1) -> BackgroundScheduler:
    """Inicia el scheduler. Llama una sola vez en startup."""
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    _scheduler.add_job(
        func=_run_alert_rules,
        trigger=IntervalTrigger(hours=interval_hours),
        id="check_alert_rules",
        name="Evaluacion periodica de reglas de alerta",
        replace_existing=True,
        misfire_grace_time=300,  # 5 min de gracia si el job se retrasa
    )
    _scheduler.start()
    logger.info("Scheduler iniciado — intervalo: %dh.", interval_hours)
    return _scheduler


def stop() -> None:
    """Detiene el scheduler en shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido.")


def next_run() -> str | None:
    """Devuelve el timestamp ISO del proximo disparo, o None si no esta activo."""
    if not _scheduler or not _scheduler.running:
        return None
    job = _scheduler.get_job("check_alert_rules")
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None
