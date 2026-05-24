"""Programador de tareas periodicas (APScheduler)."""
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("riskhub.scheduler")

_scheduler: BackgroundScheduler | None = None


def _daily_digest_html(org: str, stats: dict, overdue: list, upcoming: list) -> str:
    """Genera el HTML del resumen diario de riesgos."""
    from datetime import datetime
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    overdue_rows = "".join(
        f"<tr><td style='padding:7px 12px;'>{UI.esc(r['code'])}</td>"
        f"<td style='padding:7px 12px;'>{r['asset']}</td>"
        f"<td style='padding:7px 12px;'>{r['due']}</td></tr>"
        for r in overdue[:10]
    )
    upcoming_rows = "".join(
        f"<tr><td style='padding:7px 12px;'>{r['code']}</td>"
        f"<td style='padding:7px 12px;'>{r['asset']}</td>"
        f"<td style='padding:7px 12px;'>{r['due']} ({r['days']}d)</td></tr>"
        for r in upcoming[:10]
    )
    return f"""<!DOCTYPE html>
<html lang='es'>
<body style='margin:0;padding:24px;background:#F5F5F5;font-family:Inter,Arial,sans-serif;'>
  <div style='max-width:640px;margin:0 auto;background:#fff;border-radius:10px;
              border:1px solid #E9E9E9;overflow:hidden;'>
    <div style='background:linear-gradient(90deg,#59008D,#D65200);padding:20px 28px;'>
      <h1 style='color:#fff;margin:0;font-size:18px;'>RiskHub &mdash; Resumen diario</h1>
      <p style='color:rgba(255,255,255,.75);margin:4px 0 0;font-size:13px;'>{org} &mdash; {now_str}</p>
    </div>
    <div style='padding:24px;'>
      <table style='width:100%;border-collapse:collapse;margin-bottom:20px;'>
        <tr>
          <td style='padding:12px;text-align:center;background:#F5F5F5;border-radius:6px;'>
            <div style='font-size:28px;font-weight:700;color:#59008D;'>{stats['total']}</div>
            <div style='font-size:11px;color:#9D9D9D;text-transform:uppercase;'>Total riesgos</div>
          </td>
          <td style='width:12px;'></td>
          <td style='padding:12px;text-align:center;background:#FEE2E2;border-radius:6px;'>
            <div style='font-size:28px;font-weight:700;color:#a83232;'>{stats['high']}</div>
            <div style='font-size:11px;color:#9D9D9D;text-transform:uppercase;'>Altos (>=6)</div>
          </td>
          <td style='width:12px;'></td>
          <td style='padding:12px;text-align:center;background:#FEF0E3;border-radius:6px;'>
            <div style='font-size:28px;font-weight:700;color:#c25a1f;'>{stats['medium']}</div>
            <div style='font-size:11px;color:#9D9D9D;text-transform:uppercase;'>Medios (3-5)</div>
          </td>
          <td style='width:12px;'></td>
          <td style='padding:12px;text-align:center;background:#E8F5E9;border-radius:6px;'>
            <div style='font-size:28px;font-weight:700;color:#2e7d32;'>{stats['low']}</div>
            <div style='font-size:11px;color:#9D9D9D;text-transform:uppercase;'>Bajos (0-2)</div>
          </td>
        </tr>
      </table>
      {f'''<h3 style='font-size:14px;margin:0 0 8px;color:#a83232;'>
        Tratamientos vencidos ({len(overdue)})</h3>
      <table style='width:100%;border-collapse:collapse;font-size:12px;margin-bottom:20px;'>
        <thead><tr style='background:#FEE2E2;'>
          <th style='padding:7px 12px;text-align:left;'>Codigo</th>
          <th style='padding:7px 12px;text-align:left;'>Activo</th>
          <th style='padding:7px 12px;text-align:left;'>Fecha limite</th>
        </tr></thead>
        <tbody>{overdue_rows}</tbody>
      </table>''' if overdue else ''}
      {f'''<h3 style='font-size:14px;margin:0 0 8px;color:#c25a1f;'>
        Proximos vencimientos — 7 dias ({len(upcoming)})</h3>
      <table style='width:100%;border-collapse:collapse;font-size:12px;margin-bottom:20px;'>
        <thead><tr style='background:#FEF0E3;'>
          <th style='padding:7px 12px;text-align:left;'>Codigo</th>
          <th style='padding:7px 12px;text-align:left;'>Activo</th>
          <th style='padding:7px 12px;text-align:left;'>Vencimiento</th>
        </tr></thead>
        <tbody>{upcoming_rows}</tbody>
      </table>''' if upcoming else ''}
      <p style='color:#9D9D9D;font-size:11px;margin-top:16px;'>
        Resumen generado automaticamente por RiskHub. Accede al sistema para revisar los detalles.
      </p>
    </div>
  </div>
</body>
</html>"""


# Alias trivial para no importar UI (esta es Python, no JS)
class _UI:
    @staticmethod
    def esc(s):
        return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

UI = _UI()


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
            elif rule.event_type == "daily_digest":
                # Solo enviar una vez por dia (cooldown 20h)
                if rule.last_triggered_at:
                    hours_since = (now - rule.last_triggered_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                    if hours_since < 20:
                        continue
                active_risks = [r for r in risks if r.status not in (RiskStatus.CLOSED,)]
                overdue_list = [
                    {"code": r.code,
                     "asset": r.asset.name if r.asset else "-",
                     "due": r.treatment_due_date.strftime("%d/%m/%Y") if r.treatment_due_date else "-"}
                    for r in active_risks
                    if r.treatment_due_date
                    and r.treatment_due_date.replace(tzinfo=timezone.utc) < now
                    and r.status not in (RiskStatus.TREATED, RiskStatus.ACCEPTED, RiskStatus.CLOSED)
                ]
                from datetime import timedelta
                in7 = now + timedelta(days=7)
                upcoming_list = [
                    {"code": r.code,
                     "asset": r.asset.name if r.asset else "-",
                     "due": r.treatment_due_date.strftime("%d/%m/%Y") if r.treatment_due_date else "-",
                     "days": (r.treatment_due_date.replace(tzinfo=timezone.utc) - now).days}
                    for r in active_risks
                    if r.treatment_due_date
                    and now <= r.treatment_due_date.replace(tzinfo=timezone.utc) <= in7
                    and r.status not in (RiskStatus.TREATED, RiskStatus.ACCEPTED, RiskStatus.CLOSED)
                ]
                stats_digest = {
                    "total": len(active_risks),
                    "high": sum(1 for r in active_risks if r.residual_level >= 6),
                    "medium": sum(1 for r in active_risks if 3 <= r.residual_level < 6),
                    "low": sum(1 for r in active_risks if r.residual_level < 3),
                }
                subject_digest = f"RiskHub — Resumen diario de riesgos ({org})"
                html_digest = _daily_digest_html(org, stats_digest, overdue_list, upcoming_list)
                try:
                    email_service.send_email(cfg, rule.recipient_email, subject_digest, html_digest)
                    rule.last_triggered_at = now
                    sent += 1
                except Exception as exc:
                    logger.warning("Error enviando digest diario a %s: %s", rule.recipient_email, exc)
                continue  # ya procesado, skip el loop for risk in matching
            elif rule.event_type == "treatment_due_soon":
                from datetime import timedelta
                in_n = timedelta(days=rule.threshold_level if rule.threshold_level > 0 else 7)
                matching = [r for r in risks
                            if r.treatment_due_date
                            and timedelta(0) <= r.treatment_due_date.replace(tzinfo=timezone.utc) - now <= in_n
                            and r.status not in (RiskStatus.TREATED, RiskStatus.ACCEPTED, RiskStatus.CLOSED)]
            elif rule.event_type == "control_review_overdue":
                from app.models import ControlImplementation
                impls = db.query(ControlImplementation).all()
                # Usamos matching como lista de objetos-like para reutilizar el loop
                overdue_impls = [
                    i for i in impls
                    if i.next_review
                    and i.next_review.replace(tzinfo=timezone.utc) < now
                ]
                # Enviamos un unico email resumen por regla (cooldown 20h)
                if overdue_impls:
                    if rule.last_triggered_at:
                        hours = (now - rule.last_triggered_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                        if hours < 20:
                            continue
                    rows = "".join(
                        f"<tr><td style='padding:7px 12px;'>{UI.esc(i.name)}</td>"
                        f"<td style='padding:7px 12px;'>{i.next_review.strftime('%d/%m/%Y')}</td></tr>"
                        for i in overdue_impls[:15]
                    )
                    html_ctrl = f"""<!DOCTYPE html>
<html lang='es'>
<body style='margin:0;padding:24px;background:#F5F5F5;font-family:Inter,Arial,sans-serif;'>
  <div style='max-width:600px;margin:0 auto;background:#fff;border-radius:10px;border:1px solid #E9E9E9;overflow:hidden;'>
    <div style='background:linear-gradient(90deg,#59008D,#D65200);padding:20px 28px;'>
      <h1 style='color:#fff;margin:0;font-size:18px;'>RiskHub &mdash; Revisiones de controles vencidas</h1>
      <p style='color:rgba(255,255,255,.75);margin:4px 0 0;font-size:13px;'>{org}</p>
    </div>
    <div style='padding:24px;'>
      <p style='font-size:13px;color:#262626;'><strong>{len(overdue_impls)}</strong> control(es) tienen la fecha de revision vencida.</p>
      <table style='width:100%;border-collapse:collapse;font-size:12px;margin-top:12px;'>
        <thead><tr style='background:#EDD1FF;'>
          <th style='padding:7px 12px;text-align:left;'>Control</th>
          <th style='padding:7px 12px;text-align:left;'>Fecha programada</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
      <p style='color:#9D9D9D;font-size:11px;margin-top:16px;'>Accede a RiskHub &rarr; Controles para actualizar las fechas de revision.</p>
    </div>
  </div>
</body>
</html>"""
                    try:
                        email_service.send_email(
                            cfg, rule.recipient_email,
                            f"RiskHub — {len(overdue_impls)} revisiones de controles vencidas ({org})",
                            html_ctrl,
                        )
                        rule.last_triggered_at = now
                        sent += 1
                    except Exception as exc:
                        logger.warning("Error enviando alerta control_review_overdue: %s", exc)
                continue

            reason_map = {
                "risk_critical": "supera el umbral critico",
                "risk_high": "supera el umbral alto configurado",
                "treatment_overdue": "tiene el plan de tratamiento vencido",
                "risk_no_treatment": "no tiene plan de tratamiento definido",
                "treatment_due_soon": "tiene el plan de tratamiento proximo a vencer",
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
