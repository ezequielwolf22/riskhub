"""Programador de tareas periodicas (APScheduler)."""
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
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
        rules = db.query(AlertRule).filter(AlertRule.is_active.is_(True)).all()
        if not rules:
            return

        # E1: SMTP por org (nunca global)
        rule_org_ids = list({r.organization_id for r in rules if r.organization_id})
        cfg_by_org: dict = {}
        ctx_by_org: dict = {}
        risks_by_org: dict = {}
        from app.models import RiskContext, EmailSettings
        for org_id in rule_org_ids:
            cfg_by_org[org_id] = db.query(EmailSettings).filter_by(
                organization_id=org_id
            ).first()
            ctx_obj = db.query(RiskContext).filter_by(organization_id=org_id).first()
            ctx_by_org[org_id] = ctx_obj.organization_name if ctx_obj else "Organizacion"
            risks_by_org[org_id] = db.query(Risk).filter(
                Risk.organization_id == org_id
            ).all()

        now = datetime.now(timezone.utc)
        sent = 0

        for rule in rules:
            # Seleccionar SMTP y nombre de org correctos para esta regla
            cfg = cfg_by_org.get(rule.organization_id)
            org = ctx_by_org.get(rule.organization_id, "Organizacion")
            if not cfg or not cfg.smtp_host:
                continue   # org sin SMTP configurado — saltar
            risks = risks_by_org.get(rule.organization_id, [])
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
                impls = db.query(ControlImplementation).filter(
                    ControlImplementation.organization_id == rule.organization_id
                ).all()
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

            elif rule.event_type == "incident_p1p2":
                # Alertar sobre incidentes P1/P2 abiertos (cooldown 20h)
                if rule.last_triggered_at:
                    hours = (now - rule.last_triggered_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                    if hours < 20:
                        continue
                from app.models import Incident, IncidentStatus, IncidentSeverity
                open_p1p2 = db.query(Incident).filter(
                    Incident.organization_id == rule.organization_id,
                    Incident.status != IncidentStatus.CLOSED,
                    Incident.severity.in_([IncidentSeverity.P1, IncidentSeverity.P2]),
                ).all()
                if open_p1p2:
                    rows_inc = "".join(
                        f"<tr><td style='padding:7px 12px;'>{UI.esc(i.code)}</td>"
                        f"<td style='padding:7px 12px;'>{UI.esc(i.title[:60])}</td>"
                        f"<td style='padding:7px 12px;font-weight:700;color:#a83232;'>{UI.esc(i.severity.value.upper())}</td></tr>"
                        for i in open_p1p2[:15]
                    )
                    html_inc = f"""<!DOCTYPE html>
<html lang='es'><body style='margin:0;padding:24px;background:#F5F5F5;font-family:Arial,sans-serif;'>
  <div style='max-width:640px;margin:0 auto;background:#fff;border-radius:10px;border:1px solid #E9E9E9;overflow:hidden;'>
    <div style='background:linear-gradient(90deg,#59008D,#D65200);padding:20px 28px;'>
      <h1 style='color:#fff;margin:0;font-size:18px;'>RiskHub &mdash; Incidentes P1/P2 abiertos</h1>
      <p style='color:rgba(255,255,255,.75);margin:4px 0 0;font-size:13px;'>{org}</p>
    </div>
    <div style='padding:24px;'>
      <p style='font-size:13px;color:#262626;'><strong>{len(open_p1p2)}</strong> incidente(s) P1/P2 permanecen abiertos.</p>
      <table style='width:100%;border-collapse:collapse;font-size:12px;'>
        <thead><tr style='background:#FEE2E2;'>
          <th style='padding:7px 12px;text-align:left;'>Codigo</th>
          <th style='padding:7px 12px;text-align:left;'>Titulo</th>
          <th style='padding:7px 12px;text-align:left;'>Severidad</th>
        </tr></thead>
        <tbody>{rows_inc}</tbody>
      </table>
      <p style='color:#9D9D9D;font-size:11px;margin-top:16px;'>Accede a RiskHub &rarr; Incidentes para gestionar la respuesta.</p>
    </div>
  </div>
</body></html>"""
                    try:
                        email_service.send_email(
                            cfg, rule.recipient_email,
                            f"RiskHub — {len(open_p1p2)} incidente(s) P1/P2 abierto(s) ({org})",
                            html_inc,
                        )
                        rule.last_triggered_at = now
                        sent += 1
                    except Exception as exc:
                        logger.warning("Error enviando alerta incident_p1p2: %s", exc)
                continue

            elif rule.event_type == "nis2_pending":
                # Alertar cuando hay notificaciones NIS2 pendientes (cooldown 20h)
                if rule.last_triggered_at:
                    hours = (now - rule.last_triggered_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                    if hours < 20:
                        continue
                from app.models import Incident, IncidentStatus
                nis2_pending_list = db.query(Incident).filter(
                    Incident.organization_id == rule.organization_id,
                    Incident.status != IncidentStatus.CLOSED,
                    Incident.nis2_notification_required.is_(True),
                    Incident.nis2_notification_sent_at.is_(None),
                ).all()
                if nis2_pending_list:
                    rows_nis2 = "".join(
                        f"<tr><td style='padding:7px 12px;'>{UI.esc(i.code)}</td>"
                        f"<td style='padding:7px 12px;'>{UI.esc(i.title[:60])}</td></tr>"
                        for i in nis2_pending_list[:15]
                    )
                    html_nis2 = f"""<!DOCTYPE html>
<html lang='es'><body style='margin:0;padding:24px;background:#F5F5F5;font-family:Arial,sans-serif;'>
  <div style='max-width:640px;margin:0 auto;background:#fff;border-radius:10px;border:1px solid #E9E9E9;overflow:hidden;'>
    <div style='background:linear-gradient(90deg,#59008D,#D65200);padding:20px 28px;'>
      <h1 style='color:#fff;margin:0;font-size:18px;'>RiskHub &mdash; Notificaciones NIS2 pendientes</h1>
      <p style='color:rgba(255,255,255,.75);margin:4px 0 0;font-size:13px;'>{org}</p>
    </div>
    <div style='padding:24px;'>
      <p style='font-size:13px;color:#a83232;font-weight:700;'>ATENCION: {len(nis2_pending_list)} incidente(s) requieren notificacion NIS2 al supervisor nacional.</p>
      <p style='font-size:12px;color:#262626;'>La Directiva NIS2 (Art. 23) exige notificacion en 24h para incidentes significativos.</p>
      <table style='width:100%;border-collapse:collapse;font-size:12px;'>
        <thead><tr style='background:#FEE2E2;'>
          <th style='padding:7px 12px;text-align:left;'>Codigo</th>
          <th style='padding:7px 12px;text-align:left;'>Incidente</th>
        </tr></thead>
        <tbody>{rows_nis2}</tbody>
      </table>
    </div>
  </div>
</body></html>"""
                    try:
                        email_service.send_email(
                            cfg, rule.recipient_email,
                            f"RiskHub [URGENTE] — {len(nis2_pending_list)} notificacion(es) NIS2 pendiente(s) ({org})",
                            html_nis2,
                        )
                        rule.last_triggered_at = now
                        sent += 1
                    except Exception as exc:
                        logger.warning("Error enviando alerta nis2_pending: %s", exc)
                continue

            elif rule.event_type == "policy_review_overdue":
                # Alertar sobre politicas con revision vencida (cooldown 20h)
                if rule.last_triggered_at:
                    hours = (now - rule.last_triggered_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                    if hours < 20:
                        continue
                from app.models import Policy, PolicyStatus
                overdue_policies = [
                    p for p in db.query(Policy).filter(
                        Policy.organization_id == rule.organization_id
                    ).all()
                    if p.review_date and p.status != PolicyStatus.OBSOLETE
                    and p.review_date.replace(tzinfo=timezone.utc) < now
                ]
                if overdue_policies:
                    rows_pol = "".join(
                        f"<tr><td style='padding:7px 12px;'>{UI.esc(p.code)}</td>"
                        f"<td style='padding:7px 12px;'>{UI.esc(p.title[:60])}</td>"
                        f"<td style='padding:7px 12px;'>{p.review_date.strftime('%d/%m/%Y')}</td></tr>"
                        for p in overdue_policies[:15]
                    )
                    html_pol = f"""<!DOCTYPE html>
<html lang='es'><body style='margin:0;padding:24px;background:#F5F5F5;font-family:Arial,sans-serif;'>
  <div style='max-width:640px;margin:0 auto;background:#fff;border-radius:10px;border:1px solid #E9E9E9;overflow:hidden;'>
    <div style='background:linear-gradient(90deg,#59008D,#D65200);padding:20px 28px;'>
      <h1 style='color:#fff;margin:0;font-size:18px;'>RiskHub &mdash; Politicas con revision vencida</h1>
      <p style='color:rgba(255,255,255,.75);margin:4px 0 0;font-size:13px;'>{org}</p>
    </div>
    <div style='padding:24px;'>
      <p style='font-size:13px;color:#262626;'><strong>{len(overdue_policies)}</strong> politica(s) tienen la fecha de revision vencida.</p>
      <table style='width:100%;border-collapse:collapse;font-size:12px;'>
        <thead><tr style='background:#FEF9C3;'>
          <th style='padding:7px 12px;text-align:left;'>Codigo</th>
          <th style='padding:7px 12px;text-align:left;'>Titulo</th>
          <th style='padding:7px 12px;text-align:left;'>Fecha revision</th>
        </tr></thead>
        <tbody>{rows_pol}</tbody>
      </table>
    </div>
  </div>
</body></html>"""
                    try:
                        email_service.send_email(
                            cfg, rule.recipient_email,
                            f"RiskHub — {len(overdue_policies)} politica(s) con revision vencida ({org})",
                            html_pol,
                        )
                        rule.last_triggered_at = now
                        sent += 1
                    except Exception as exc:
                        logger.warning("Error enviando alerta policy_review_overdue: %s", exc)
                continue

            elif rule.event_type == "task_overdue":
                # Alertar sobre tareas vencidas (cooldown 20h)
                if rule.last_triggered_at:
                    hours = (now - rule.last_triggered_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                    if hours < 20:
                        continue
                from app.models import TreatmentTask, TaskStatus
                overdue_tasks = [
                    t for t in db.query(TreatmentTask).filter(
                        TreatmentTask.organization_id == rule.organization_id
                    ).all()
                    if t.due_date and t.status != TaskStatus.DONE
                    and t.due_date.replace(tzinfo=timezone.utc) < now
                ]
                if overdue_tasks:
                    rows_tsk = "".join(
                        f"<tr><td style='padding:7px 12px;'>{UI.esc(t.code)}</td>"
                        f"<td style='padding:7px 12px;'>{UI.esc(t.title[:60])}</td>"
                        f"<td style='padding:7px 12px;'>{t.due_date.strftime('%d/%m/%Y')}</td></tr>"
                        for t in overdue_tasks[:15]
                    )
                    html_tsk = f"""<!DOCTYPE html>
<html lang='es'><body style='margin:0;padding:24px;background:#F5F5F5;font-family:Arial,sans-serif;'>
  <div style='max-width:640px;margin:0 auto;background:#fff;border-radius:10px;border:1px solid #E9E9E9;overflow:hidden;'>
    <div style='background:linear-gradient(90deg,#59008D,#D65200);padding:20px 28px;'>
      <h1 style='color:#fff;margin:0;font-size:18px;'>RiskHub &mdash; Tareas de tratamiento vencidas</h1>
      <p style='color:rgba(255,255,255,.75);margin:4px 0 0;font-size:13px;'>{org}</p>
    </div>
    <div style='padding:24px;'>
      <p style='font-size:13px;color:#262626;'><strong>{len(overdue_tasks)}</strong> tarea(s) de tratamiento tienen la fecha limite vencida.</p>
      <table style='width:100%;border-collapse:collapse;font-size:12px;'>
        <thead><tr style='background:#FFF7ED;'>
          <th style='padding:7px 12px;text-align:left;'>Codigo</th>
          <th style='padding:7px 12px;text-align:left;'>Titulo</th>
          <th style='padding:7px 12px;text-align:left;'>Fecha limite</th>
        </tr></thead>
        <tbody>{rows_tsk}</tbody>
      </table>
    </div>
  </div>
</body></html>"""
                    try:
                        email_service.send_email(
                            cfg, rule.recipient_email,
                            f"RiskHub — {len(overdue_tasks)} tarea(s) vencida(s) ({org})",
                            html_tsk,
                        )
                        rule.last_triggered_at = now
                        sent += 1
                    except Exception as exc:
                        logger.warning("Error enviando alerta task_overdue: %s", exc)
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


def _match_cve_to_assets(db, cve_record: dict, org_id: int) -> list:
    """Correlaciona un CVE con activos de la org usando tres capas de matching:

    1. CPE exacto: affected_products del CVE vs software_tags del activo
    2. CPE fuzzy: asset_matches_cve() de cve_service (score >= 0.15)
    3. Descripcion: patterns conocidos en desc del activo/nombre
    """
    from app.models import Asset
    from app.services.cve_service import asset_matches_cve

    # La clave correcta del record normalizado es "id", no "cve_id"
    cve_id = cve_record.get("id") or cve_record.get("cve_id", "UNKNOWN")
    cpe_products = set(cve_record.get("affected_products") or [])  # list[str] ya en minusculas
    desc = (cve_record.get("description", "") or "").lower()

    assets = db.query(Asset).filter(Asset.organization_id == org_id).all()
    matched: dict[int, float] = {}  # asset_id → score (mayor = mejor match)

    for asset in assets:
        asset_name = (asset.name or "").lower()
        asset_desc = (asset.description or "").lower()
        asset_tags = [t.lower() for t in (asset.software_tags or [])]
        score = 0.0

        # --- Capa 1: CVE ID explicito en el activo (maxima prioridad) ---
        if cve_id.lower() in asset_desc or cve_id.lower() in asset_name:
            score = 1.0

        # --- Capa 2: software_tags del activo vs CPE products del CVE ---
        elif asset_tags and cpe_products:
            common = cpe_products & set(asset_tags)
            if common:
                score = min(1.0, len(common) / max(1, len(cpe_products)) * 3)

        # --- Capa 3: asset_matches_cve (fuzzy CPE + descripcion) ---
        if score < 0.15:
            fuzzy = asset_matches_cve(asset_name, asset_desc, cve_record)
            score = max(score, fuzzy)

        # --- Capa 4: tags del activo vs descripcion del CVE ---
        if score < 0.15 and asset_tags:
            for tag in asset_tags:
                if len(tag) > 3 and tag in desc:
                    score = max(score, 0.4)
                    break

        if score >= 0.15:
            matched[asset.id] = score

    if not matched:
        return []

    # Ordenar por score desc, devolver objetos Asset
    id_to_asset = {a.id: a for a in assets}
    return [id_to_asset[aid] for aid, _ in sorted(matched.items(), key=lambda x: -x[1])]


def _run_cve_auto_scan() -> None:
    """Escaneo automatico diario de CVEs: busca + auto-genera riesgos."""
    from app.database import SessionLocal
    from app.models import IntegrationConfig, Asset
    from app.services.risk_auto_generator import auto_generate_risk_from_cve
    import json, base64, hashlib

    db = SessionLocal()
    try:
        ic = db.query(IntegrationConfig).filter_by(name="nvd_cve").first()
        if not ic or not ic.config_encrypted:
            return
        key = base64.urlsafe_b64encode(hashlib.sha256(
            __import__('app.config', fromlist=['settings']).settings.secret_key.encode()
        ).digest())
        from cryptography.fernet import Fernet
        cfg = json.loads(Fernet(key).decrypt(ic.config_encrypted.encode()).decode())
        if not cfg.get("auto_scan_enabled"):
            return

        from app.services import cve_service as cvs
        api_key = cfg.get("api_key")
        severity = cfg.get("auto_scan_severity", "CRITICAL")
        sev = None if severity == "ALL" else severity

        logger.info("CVE auto-scan: buscando CVEs %s de los ultimos 2 dias...", severity)
        try:
            cves = cvs.fetch_recent(api_key, days=2, severity=sev, max_results=50)
        except Exception as e:
            logger.warning("CVE auto-scan: error al obtener CVEs: %s", e)
            return

        if not cves:
            logger.info("CVE auto-scan: sin nuevas CVEs %s en los ultimos 2 dias.", severity)
            return

        logger.info("CVE auto-scan: %d CVEs encontradas. Correlacionando con activos...", len(cves))
        created_count = 0
        # Procesar por org
        orgs = db.query(Asset.organization_id).distinct().all()
        for org_tuple in orgs:
            org_id = org_tuple[0]
            for cve_record in cves:
                # "id" es la clave correcta del record normalizado por _normalize()
                cve_id = cve_record.get("id") or cve_record.get("cve_id", "UNKNOWN")
                # Matching por CPE products + software_tags + descripcion
                affected_assets = _match_cve_to_assets(db, cve_record, org_id)

                if not affected_assets:
                    # Fallback: algun CPE product vs nombre de activo
                    for prod in (cve_record.get("affected_products") or []):
                        if prod and len(prod) > 4:
                            hits = db.query(Asset).filter(
                                Asset.organization_id == org_id,
                                Asset.name.ilike(f"%{prod}%"),
                            ).limit(3).all()
                            if hits:
                                affected_assets = hits
                                break

                # Ajustar severidad segun CVSS
                cvss = cve_record.get("cvss_score", 7.0) or 7.0
                inh_con = 4 if cvss >= 9.0 else (3 if cvss >= 7.0 else 2)
                inh_lik = 3 if cvss >= 7.0 else 2

                for asset in affected_assets:
                    risk = auto_generate_risk_from_cve(
                        db, asset.id, cve_id,
                        affected_software=(
                            ", ".join((cve_record.get("affected_products") or [])[:3])
                            or cve_record.get("description", "Unknown")[:100]
                        ),
                        inherent_consequence=inh_con,
                        inherent_likelihood=inh_lik,
                    )
                    if risk:
                        created_count += 1
        logger.info("CVE auto-scan: %d riesgos generados automaticamente.", created_count)
    except Exception as exc:
        logger.exception("Error en CVE auto-scan: %s", exc)
    finally:
        db.close()


def _run_risk_reviews() -> None:
    """Envia recordatorios de revision periodica de riesgos a los risk owners."""
    from datetime import timedelta
    from app.database import SessionLocal
    from app.models import Risk, RiskStatus, User
    from app.services import email_service

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        thresholds = [
            (timedelta(days=30), "en 30 dias"),
            (timedelta(days=7), "en 7 dias"),
            (timedelta(days=1), "MANANA"),
        ]

        active_risks = db.query(Risk).filter(
            Risk.next_review.isnot(None),
            Risk.status.notin_([RiskStatus.CLOSED]),
            Risk.owner_id.isnot(None),
            Risk.organization_id.isnot(None),
        ).all()

        # Cache de SMTP y nombres de org por org_id (E1: per-org SMTP)
        from app.models import RiskContext, Organization, EmailSettings
        _org_name_cache: dict[int, str] = {}
        _cfg_cache: dict[int, object] = {}

        def _org_name(oid: int) -> str:
            if oid not in _org_name_cache:
                ctx2 = db.query(RiskContext).filter(RiskContext.organization_id == oid).first()
                if ctx2 and ctx2.organization_name:
                    _org_name_cache[oid] = ctx2.organization_name
                else:
                    org2 = db.get(Organization, oid)
                    _org_name_cache[oid] = org2.name if org2 else "Organizacion"
            return _org_name_cache[oid]

        def _get_cfg(oid: int):
            if oid not in _cfg_cache:
                _cfg_cache[oid] = db.query(EmailSettings).filter_by(
                    organization_id=oid
                ).first()
            return _cfg_cache[oid]

        for risk in active_risks:
            # Dedup: no reenviar si ya se notifico en las ultimas 20 horas
            if risk.last_review_notified_at:
                notified_dt = risk.last_review_notified_at
                if not notified_dt.tzinfo:
                    notified_dt = notified_dt.replace(tzinfo=timezone.utc)
                if (now - notified_dt).total_seconds() < 72000:  # 20 horas
                    continue

            cfg = _get_cfg(risk.organization_id)
            if not cfg or not cfg.smtp_host:
                continue

            org = _org_name(risk.organization_id)
            review_dt = risk.next_review.replace(tzinfo=timezone.utc)
            sent_this_risk = False
            if review_dt < now:
                # Vencida
                days_overdue = (now - review_dt).days
                if days_overdue in (0, 1, 7):
                    owner = db.query(User).filter(User.id == risk.owner_id).first()
                    if owner and owner.email:
                        subject = f"RiskHub — Revision vencida: {risk.code} ({org})"
                        body = f"La revision del riesgo <b>{risk.code}</b> estaba programada para {risk.next_review.strftime('%d/%m/%Y')} y no ha sido completada."
                        try:
                            email_service.send_email(cfg, owner.email, subject,
                                email_service._wrap_html(subject, body, org))
                            sent_this_risk = True
                        except Exception:
                            pass
                continue
            time_until = review_dt - now
            for threshold, label in thresholds:
                if timedelta(0) <= time_until <= threshold:
                    owner = db.query(User).filter(User.id == risk.owner_id).first()
                    if owner and owner.email:
                        subject = f"RiskHub — Revision de riesgo {label}: {risk.code} ({org})"
                        body = (f"El riesgo <b>{risk.code}</b> ({risk.asset.name if risk.asset else '-'}) "
                                f"tiene programada su revision para el {risk.next_review.strftime('%d/%m/%Y')} ({label}).")
                        try:
                            email_service.send_email(cfg, owner.email, subject,
                                email_service._wrap_html(subject, body, org))
                            sent_this_risk = True
                        except Exception:
                            pass
                    break
            if sent_this_risk:
                risk.last_review_notified_at = now
        # Persistir todas las actualizaciones de last_review_notified_at
        db.commit()
    except Exception as exc:
        logger.exception("Error en revision de riesgos: %s", exc)
    finally:
        db.close()


def _run_task_escalation() -> None:
    """Escala automaticamente la prioridad de tareas de tratamiento con vencimiento muy vencido."""
    from datetime import timedelta
    from app.database import SessionLocal
    from app.models import TreatmentTask, TaskStatus, TaskPriority

    _ESCALATION_MAP = {
        TaskPriority.LOW: TaskPriority.MEDIUM,
        TaskPriority.MEDIUM: TaskPriority.HIGH,
        TaskPriority.HIGH: TaskPriority.CRITICAL,
        TaskPriority.CRITICAL: TaskPriority.CRITICAL,  # tope
    }

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(days=7)
        tasks = db.query(TreatmentTask).filter(
            TreatmentTask.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
            TreatmentTask.due_date.isnot(None),
            TreatmentTask.due_date < threshold,
        ).all()
        escalated = 0
        for t in tasks:
            old_p = t.priority or TaskPriority.LOW
            new_p = _ESCALATION_MAP.get(old_p, TaskPriority.CRITICAL)
            if new_p != old_p:
                t.priority = new_p
                escalated += 1
        if escalated:
            db.commit()
            logger.info("Task escalation: %d tareas escaladas.", escalated)
    except Exception as exc:
        logger.exception("Error en task_escalation: %s", exc)
    finally:
        db.close()


def _run_policy_review_tasks() -> None:
    """Crea tareas de revision para politicas con review_date vencida."""
    from app.database import SessionLocal
    from app.models import Policy, PolicyStatus, TreatmentTask, TaskStatus, TaskPriority

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        overdue_policies = db.query(Policy).filter(
            Policy.status != PolicyStatus.OBSOLETE,
            Policy.review_date.isnot(None),
            Policy.review_date < now,
        ).all()

        created = 0
        for pol in overdue_policies:
            # Evitar duplicados: no crear si ya existe tarea para esta politica
            dup = db.query(TreatmentTask).filter(
                TreatmentTask.organization_id == pol.organization_id,
                TreatmentTask.title.like(f"%{pol.code}%"),
                TreatmentTask.status != TaskStatus.DONE,
            ).first()
            if dup:
                continue

            # Generar codigo unico TSK-XXXX
            count = db.query(TreatmentTask).filter_by(organization_id=pol.organization_id).count()
            code = f"TSK-{count + 1:04d}"
            while db.query(TreatmentTask).filter_by(code=code).first():
                count += 1
                code = f"TSK-{count + 1:04d}"

            task = TreatmentTask(
                organization_id=pol.organization_id,
                code=code,
                title=f"Revisar politica {pol.code}: {pol.title[:60]}",
                description=(
                    f"La politica {pol.code} ({pol.title}) tenia programada su revision "
                    f"para {pol.review_date.strftime('%d/%m/%Y') if pol.review_date else 'N/A'} "
                    f"y no ha sido actualizada. Revisar el contenido, actualizar la fecha de revision "
                    f"y cambiar el estado a ACTIVE si sigue vigente."
                ),
                status=TaskStatus.PENDING,
                priority=TaskPriority.MEDIUM,
                assigned_to_id=pol.owner_id,
                created_by_id=pol.owner_id,
            )
            db.add(task)
            created += 1

        if created:
            db.commit()
            logger.info("Policy review tasks: %d tareas creadas.", created)
    except Exception as exc:
        logger.exception("Error en policy_review_tasks: %s", exc)
    finally:
        db.close()


def _run_policy_review_reminders() -> None:
    """Envia recordatorio por email cuando una politica vence en 30 dias o menos."""
    from app.database import SessionLocal
    from app.models import Policy, PolicyStatus
    from app.services import email_service

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        threshold = now + timedelta(days=30)
        upcoming = db.query(Policy).filter(
            Policy.status.in_([PolicyStatus.APPROVED, PolicyStatus.PUBLISHED]),
            Policy.review_date.isnot(None),
            Policy.review_date > now,
            Policy.review_date <= threshold,
        ).all()

        orgs_done: set[int] = set()
        for pol in upcoming:
            oid = pol.organization_id
            cfg = email_service.get_settings_for_org(db, oid) if oid else None
            if not cfg or not cfg.smtp_host:
                continue
            if pol.owner_id and pol.owner and pol.owner.email:
                days_left = (pol.review_date - now).days
                subject = f"[RiskHub] Recordatorio: revision de {pol.code} en {days_left} dias"
                body = f"""
                <p>El documento <strong>{pol.code} — {pol.title}</strong> (v{pol.version or '1.0'})
                   requiere revision antes del
                   <strong>{pol.review_date.strftime('%d/%m/%Y')}</strong>
                   ({days_left} dias).</p>
                <p>Accede a la seccion <em>Cumplimiento &rarr; Documentos ISMS</em> para revisar y actualizar el documento.</p>
                """
                from app.services.approval_service import _wrap_html
                try:
                    email_service.send_email(
                        cfg, pol.owner.email, subject,
                        _wrap_html(f"Recordatorio de revision: {pol.code}", body, "RiskHub"),
                    )
                except Exception:
                    pass
    except Exception as exc:
        logger.exception("Error en policy_review_reminders: %s", exc)
    finally:
        db.close()


def _run_checkout_auto_release() -> None:
    """Libera el checkout de documentos que llevan mas de 4h bloqueados."""
    from datetime import timedelta
    from app.database import SessionLocal
    from app.models import Policy

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=4)
        stale = db.query(Policy).filter(
            Policy.checked_out_by_id.isnot(None),
            Policy.checked_out_at < cutoff,
        ).all()
        for pol in stale:
            pol.checked_out_by_id = None
            pol.checked_out_at = None
        if stale:
            db.commit()
            logger.info("Checkout auto-release: %d documentos liberados.", len(stale))
    except Exception as exc:
        logger.exception("Error en checkout_auto_release: %s", exc)
    finally:
        db.close()


def _run_control_degradation() -> None:
    """Degrada controles IMPLEMENTED sin evidencia nueva en mas de 12 meses."""
    from datetime import timedelta
    from app.database import SessionLocal
    from app.models import ControlImplementation, ControlStatus, TreatmentTask, TaskStatus, TaskPriority

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(days=365)
        stale = db.query(ControlImplementation).filter(
            ControlImplementation.status == ControlStatus.IMPLEMENTED,
            ControlImplementation.next_review.isnot(None),
            ControlImplementation.next_review < threshold,
        ).all()

        degraded = 0
        for impl in stale:
            impl.status = ControlStatus.PARTIAL
            if impl.maturity and impl.maturity > 1:
                impl.maturity = impl.maturity - 1

            # Crear tarea de revision si no existe
            dup = db.query(TreatmentTask).filter(
                TreatmentTask.organization_id == impl.organization_id,
                TreatmentTask.title.like(f"%control%{impl.name[:30]}%"),
                TreatmentTask.status != TaskStatus.DONE,
            ).first()
            if not dup:
                count = db.query(TreatmentTask).filter_by(organization_id=impl.organization_id).count()
                code = f"TSK-{count + 1:04d}"
                while db.query(TreatmentTask).filter_by(code=code).first():
                    count += 1
                    code = f"TSK-{count + 1:04d}"
                task = TreatmentTask(
                    organization_id=impl.organization_id,
                    code=code,
                    title=f"Revisar control obsoleto: {impl.name[:60]}",
                    description=(
                        f"El control '{impl.name}' lleva mas de 12 meses sin evidencia actualizada "
                        f"(next_review: {impl.next_review.strftime('%d/%m/%Y') if impl.next_review else 'N/A'}). "
                        f"Su estado ha sido degradado automaticamente a PARTIAL. "
                        f"Actualiza la evidencia y la fecha de proxima revision."
                    ),
                    status=TaskStatus.PENDING,
                    priority=TaskPriority.MEDIUM,
                    assigned_to_id=impl.owner_id,
                    created_by_id=impl.owner_id,
                )
                db.add(task)
            degraded += 1

        if degraded:
            db.commit()
            logger.info("Control degradation: %d controles degradados a PARTIAL.", degraded)
    except Exception as exc:
        logger.exception("Error en control_degradation: %s", exc)
    finally:
        db.close()


def _match_osint_to_assets(db, finding_type: str, finding_value: str, org_id: int) -> list:
    """Inteligencia para correlacionar OSINT findings con Assets.

    Estrategia:
    - email: buscar asset con esa empresa en descripción
    - domain: buscar asset que mencionan ese dominio
    - ip: buscar asset por IP en descripción
    - url: extraer dominio del URL y buscar
    """
    from app.models import Asset
    import re

    affected = []

    for asset in db.query(Asset).filter(Asset.organization_id == org_id).all():
        desc = (asset.description or "").lower()
        name = (asset.name or "").lower()

        if finding_type == "email":
            # Extraer dominio del email
            domain = finding_value.split("@")[1] if "@" in finding_value else ""
            if domain and (domain in desc or domain in name):
                affected.append(asset)

        elif finding_type == "domain":
            # Búsqueda directa del dominio
            if finding_value.lower() in desc or finding_value.lower() in name:
                affected.append(asset)

        elif finding_type == "ip":
            # Búsqueda por IP
            if finding_value in desc or finding_value in name:
                affected.append(asset)

        elif finding_type == "url":
            # Extraer dominio de URL
            match = re.search(r"https?://([^/]+)", finding_value)
            if match:
                domain = match.group(1).lower()
                if domain in desc or domain in name:
                    affected.append(asset)

        elif finding_type == "username":
            # Búsqueda por username (menos likely, pero incluir)
            if finding_value.lower() in desc or finding_value.lower() in name:
                affected.append(asset)

    return affected


def _run_osint_periodic_scan() -> None:
    """Re-escanea automaticamente objetivos OSINT que llevan mas de 7 dias sin escanear."""
    from datetime import timedelta
    from app.database import SessionLocal
    from app.models import OSINTIdentifier, OSINTScan
    from app.services.osint_engine import osint_engine

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(days=7)

        from sqlalchemy import or_
        identifiers = db.query(OSINTIdentifier).filter(
            or_(
                OSINTIdentifier.last_scanned_at.is_(None),   # nunca escaneado
                OSINTIdentifier.last_scanned_at < threshold,  # escaneado hace >7 dias
            )
        ).all()

        if not identifiers:
            return

        logger.info("OSINT periodic re-scan: %d objetivos a re-escanear.", len(identifiers))

        for ident in identifiers:
            # Crear registro de scan
            scan = OSINTScan(
                target=ident.value,
                scan_type=ident.identifier_type,
                status="pending",
                organization_id=ident.organization_id,
                user_id=ident.user_id,
            )
            db.add(scan)
            db.flush()
            scan_id = scan.id
            db.commit()

            # Lanzar escaneo en hilo separado segun tipo
            import threading
            target_val = ident.value
            user_id_val = ident.user_id
            org_id_val = ident.organization_id
            stype_val = ident.identifier_type.value if hasattr(ident.identifier_type, 'value') else str(ident.identifier_type)

            def _do_scan(sid=scan_id, stype=stype_val, tgt=target_val, uid=user_id_val, oid=org_id_val):
                try:
                    if stype == "email":
                        osint_engine.run_email_scan(sid, tgt, uid)
                    elif stype == "domain":
                        osint_engine.run_domain_scan(sid, tgt, uid)
                    elif stype == "ip":
                        osint_engine.run_ip_scan(sid, tgt, uid)
                    elif stype == "url":
                        osint_engine.run_url_scan(sid, tgt, uid)
                    elif stype == "username":
                        osint_engine.run_username_scan(sid, tgt, uid)

                    # NUEVO: Auto-generar riesgos si hallazgo es CRITICAL/HIGH
                    # Buscar scan y verificar findings
                    db2 = SessionLocal()
                    try:
                        scan_obj = db2.get(OSINTScan, sid)
                        if scan_obj and scan_obj.findings:
                            from app.services.risk_auto_generator import auto_generate_risk_from_osint
                            findings = scan_obj.findings if isinstance(scan_obj.findings, list) else [scan_obj.findings]
                            for finding in findings:
                                severity = finding.get("severity", "LOW") if isinstance(finding, dict) else "LOW"
                                if severity in ["CRITICAL", "HIGH"]:
                                    # Correlacionar con assets
                                    affected_assets = _match_osint_to_assets(db2, stype, tgt, oid)
                                    for asset in affected_assets:
                                        auto_generate_risk_from_osint(
                                            db2, asset.id,
                                            osint_finding_type=stype,
                                            osint_finding_title=finding.get("title", "OSINT hallazgo"),
                                            inherent_consequence=4,
                                            inherent_likelihood=4,
                                        )
                    except Exception as _e2:
                        logger.debug("OSINT auto-risk generation failed: %s", _e2)
                    finally:
                        db2.close()

                except Exception as _e:
                    logger.warning("OSINT periodic scan failed target=%s: %s", tgt, _e)

            t = threading.Thread(target=_do_scan, daemon=True)
            t.start()
    except Exception as exc:
        logger.exception("Error en osint_periodic_scan: %s", exc)
    finally:
        db.close()


def _run_kri_evaluation() -> None:
    """Evalua todos los KRIs activos de todas las organizaciones y genera alertas si hay breach."""
    from app.database import SessionLocal
    from app.models import KRI, Organization
    from app.routers.kris import evaluate_kri

    db = SessionLocal()
    try:
        orgs = db.query(Organization).filter(Organization.is_active.is_(True)).all()
        total = 0
        breaches = 0
        for org in orgs:
            kris = db.query(KRI).filter(
                KRI.organization_id == org.id,
                KRI.is_active == True,
            ).all()
            for kri in kris:
                from app.models import KRIStatus
                status = evaluate_kri(db, kri, org.id)
                total += 1
                if status == KRIStatus.BREACH:
                    breaches += 1
        if total:
            db.commit()
            logger.info("KRI evaluation: %d evaluados, %d en breach", total, breaches)
    except Exception as exc:
        logger.exception("Error en _run_kri_evaluation: %s", exc)
    finally:
        db.close()


def _run_risk_snapshots() -> None:
    """Crea un snapshot mensual del estado de cada riesgo activo el primer dia del mes.

    Estos snapshots alimentan el endpoint GET /api/risks/{id}/history para mostrar
    la evolucion temporal del riesgo (inherente vs residual).
    """
    from app.database import SessionLocal
    from app.models import Organization, Risk, RiskStatus, RiskSnapshot

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        if now.day != 1:
            return

        # Fecha canonica del snapshot: primer dia del mes a medianoche UTC
        snapshot_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

        orgs = db.query(Organization).filter(Organization.is_active.is_(True)).all()
        total = 0
        for org in orgs:
            risks = db.query(Risk).filter(
                Risk.organization_id == org.id,
                Risk.status.notin_([RiskStatus.CLOSED]),
            ).all()

            for r in risks:
                # Evitar duplicados: un snapshot por riesgo por mes
                dup = db.query(RiskSnapshot).filter(
                    RiskSnapshot.risk_id == r.id,
                    RiskSnapshot.snapshot_date == snapshot_date,
                ).first()
                if dup:
                    continue

                control_count = len(r.controls or [])
                snap = RiskSnapshot(
                    organization_id=org.id,
                    risk_id=r.id,
                    snapshot_date=snapshot_date,
                    inherent_likelihood=r.inherent_likelihood,
                    inherent_consequence=r.inherent_consequence,
                    inherent_level=r.inherent_level,
                    residual_likelihood=r.residual_likelihood,
                    residual_consequence=r.residual_consequence,
                    residual_level=r.residual_level,
                    control_count=control_count,
                    risk_status=r.status.value if r.status else None,
                    created_at=now,
                )
                db.add(snap)
                total += 1

        if total:
            db.commit()
            logger.info("RiskSnapshot: %d snapshots creados para %s", total, snapshot_date.strftime("%Y-%m"))

    except Exception as exc:
        logger.exception("Error en _run_risk_snapshots: %s", exc)
    finally:
        db.close()


def _run_monthly_report() -> None:
    """Genera y envia el informe mensual de seguridad a admins el primer dia de cada mes."""
    from app.database import SessionLocal
    from app.models import Risk, RiskStatus, RiskContext, TreatmentTask, TaskStatus, User, UserRole
    from app.services import email_service

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # Solo ejecutar el primer dia del mes
        if now.day != 1:
            return

        # Aplicar penalizacion Risk→Compliance antes del informe mensual
        from app.models import Organization as _Org
        from app.services.compliance_service import apply_high_risk_compliance_penalty
        for _org in db.query(_Org).filter(_Org.is_active.is_(True)).all():
            try:
                apply_high_risk_compliance_penalty(db, _org.id)
            except Exception as _exc:
                logger.warning("Compliance penalty org=%d error: %s", _org.id, _exc)

        # E2: SMTP por org — no global
        from app.models import EmailSettings
        contexts = db.query(RiskContext).all()

        for ctx in contexts:
            org_id = ctx.organization_id
            org_name = ctx.organization_name or "Organizacion"

            cfg = db.query(EmailSettings).filter_by(organization_id=org_id).first()
            if not cfg or not cfg.smtp_host:
                continue

            # KPIs
            risks = db.query(Risk).filter(
                Risk.organization_id == org_id,
                Risk.status != RiskStatus.CLOSED,
            ).all()
            tasks = db.query(TreatmentTask).filter(
                TreatmentTask.organization_id == org_id,
                TreatmentTask.status != TaskStatus.DONE,
            ).all()

            total_risks = len(risks)
            high_risks = sum(1 for r in risks if (r.residual_level or 0) >= 6)
            medium_risks = sum(1 for r in risks if 3 <= (r.residual_level or 0) < 6)
            low_risks = sum(1 for r in risks if (r.residual_level or 0) < 3)
            overdue_tasks = sum(
                1 for t in tasks
                if t.due_date and t.due_date.replace(tzinfo=timezone.utc) < now
            )
            avg_reduction = 0
            if risks:
                reductions = []
                for r in risks:
                    if r.inherent_level and r.inherent_level > 0:
                        red = (r.inherent_level - (r.residual_level or 0)) / r.inherent_level * 100
                        reductions.append(max(0, red))
                avg_reduction = round(sum(reductions) / len(reductions)) if reductions else 0

            month_str = now.strftime("%B %Y")
            html = f"""<!DOCTYPE html>
<html lang='es'>
<body style='margin:0;padding:24px;background:#F5F5F5;font-family:Inter,Arial,sans-serif;'>
  <div style='max-width:660px;margin:0 auto;background:#fff;border-radius:10px;border:1px solid #E9E9E9;overflow:hidden;'>
    <div style='background:linear-gradient(90deg,#59008D,#D65200);padding:24px 28px;'>
      <h1 style='color:#fff;margin:0;font-size:20px;'>RiskHub &mdash; Informe mensual</h1>
      <p style='color:rgba(255,255,255,.75);margin:6px 0 0;font-size:13px;'>{org_name} &mdash; {month_str}</p>
    </div>
    <div style='padding:28px;'>
      <h2 style='font-size:15px;margin:0 0 16px;color:#262626;'>Resumen ejecutivo del mes</h2>
      <table style='width:100%;border-collapse:collapse;margin-bottom:24px;'>
        <tr>
          <td style='padding:14px;text-align:center;background:#F5F5F5;border-radius:8px;'>
            <div style='font-size:32px;font-weight:700;color:#59008D;'>{total_risks}</div>
            <div style='font-size:11px;color:#9D9D9D;text-transform:uppercase;letter-spacing:.5px;'>Riesgos activos</div>
          </td>
          <td style='width:12px;'></td>
          <td style='padding:14px;text-align:center;background:#FEE2E2;border-radius:8px;'>
            <div style='font-size:32px;font-weight:700;color:#a83232;'>{high_risks}</div>
            <div style='font-size:11px;color:#9D9D9D;text-transform:uppercase;letter-spacing:.5px;'>Altos (&ge;6)</div>
          </td>
          <td style='width:12px;'></td>
          <td style='padding:14px;text-align:center;background:#FEF0E3;border-radius:8px;'>
            <div style='font-size:32px;font-weight:700;color:#c25a1f;'>{medium_risks}</div>
            <div style='font-size:11px;color:#9D9D9D;text-transform:uppercase;letter-spacing:.5px;'>Medios (3-5)</div>
          </td>
          <td style='width:12px;'></td>
          <td style='padding:14px;text-align:center;background:#E8F5E9;border-radius:8px;'>
            <div style='font-size:32px;font-weight:700;color:#2e7d32;'>{low_risks}</div>
            <div style='font-size:11px;color:#9D9D9D;text-transform:uppercase;letter-spacing:.5px;'>Bajos (&lt;3)</div>
          </td>
        </tr>
      </table>
      <table style='width:100%;border-collapse:collapse;margin-bottom:24px;'>
        <tr>
          <td style='padding:14px;text-align:center;background:#F5F5F5;border-radius:8px;'>
            <div style='font-size:28px;font-weight:700;color:#59008D;'>{avg_reduction}%</div>
            <div style='font-size:11px;color:#9D9D9D;text-transform:uppercase;'>Reduccion media</div>
          </td>
          <td style='width:12px;'></td>
          <td style='padding:14px;text-align:center;background:{'#FEE2E2' if overdue_tasks > 0 else '#E8F5E9'};border-radius:8px;'>
            <div style='font-size:28px;font-weight:700;color:{'#a83232' if overdue_tasks > 0 else '#2e7d32'};'>{overdue_tasks}</div>
            <div style='font-size:11px;color:#9D9D9D;text-transform:uppercase;'>Tareas vencidas</div>
          </td>
        </tr>
      </table>
      <p style='color:#9D9D9D;font-size:11px;margin-top:20px;border-top:1px solid #E9E9E9;padding-top:16px;'>
        Informe generado automaticamente por RiskHub el {now.strftime('%d/%m/%Y')}.
        Accede al sistema para ver el detalle completo.
      </p>
    </div>
  </div>
</body>
</html>"""

            # Enviar a todos los admins activos de la org
            admins = db.query(User).filter(
                User.organization_id == org_id,
                User.role == UserRole.ADMIN,
                User.is_active == True,  # noqa: E712
                User.email.isnot(None),
            ).all()

            for admin in admins:
                try:
                    email_service.send_email(
                        cfg, admin.email,
                        f"RiskHub &mdash; Informe mensual {month_str} ({org_name})",
                        html,
                    )
                    logger.info("Monthly report sent to %s org=%s", admin.email, org_name)
                except Exception as exc:
                    logger.warning("Monthly report email failed to %s: %s", admin.email, exc)
    except Exception as exc:
        logger.exception("Error en monthly_report: %s", exc)
    finally:
        db.close()


def _run_incident_tasks() -> None:
    """Crea tareas de resolucion para incidentes abiertos sin actividad durante mas de 7 dias."""
    from datetime import timedelta
    from app.database import SessionLocal
    from app.models import Incident, IncidentStatus, IncidentSeverity, TreatmentTask, TaskStatus, TaskPriority

    _SEVERITY_PRIORITY = {
        IncidentSeverity.P1: TaskPriority.CRITICAL,
        IncidentSeverity.P2: TaskPriority.HIGH,
        IncidentSeverity.P3: TaskPriority.MEDIUM,
        IncidentSeverity.P4: TaskPriority.LOW,
    }

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(days=7)

        open_incidents = db.query(Incident).filter(
            Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.IN_PROGRESS]),
            Incident.created_at < threshold,
        ).all()

        created = 0
        for inc in open_incidents:
            # Evitar duplicados: no crear si ya hay tarea activa para este incidente
            dup = db.query(TreatmentTask).filter(
                TreatmentTask.organization_id == inc.organization_id,
                TreatmentTask.title.like(f"%{inc.code}%"),
                TreatmentTask.status != TaskStatus.DONE,
            ).first()
            if dup:
                continue

            count = db.query(TreatmentTask).filter_by(organization_id=inc.organization_id).count()
            code = f"TSK-{count + 1:04d}"
            while db.query(TreatmentTask).filter_by(code=code).first():
                count += 1
                code = f"TSK-{count + 1:04d}"

            priority = _SEVERITY_PRIORITY.get(inc.severity, TaskPriority.MEDIUM)
            days_open = (now - inc.created_at.replace(tzinfo=timezone.utc)).days

            task = TreatmentTask(
                organization_id=inc.organization_id,
                code=code,
                title=f"Resolver incidente {inc.code}: {inc.title[:60]}",
                description=(
                    f"El incidente {inc.code} ({inc.title}) lleva {days_open} dias abierto "
                    f"sin resolucion. Severidad: {inc.severity.value}. "
                    f"Revisar el estado, tomar acciones de contencion y cierre, "
                    f"y documentar las lecciones aprendidas."
                ),
                status=TaskStatus.PENDING,
                priority=priority,
                assigned_to_id=inc.assigned_to_id,
                created_by_id=inc.assigned_to_id,
            )
            db.add(task)
            created += 1

        if created:
            db.commit()
            logger.info("Incident tasks: %d tareas de resolucion creadas.", created)
    except Exception as exc:
        logger.exception("Error en incident_tasks: %s", exc)
    finally:
        db.close()


def _run_sla_check() -> None:
    """Verifica SLAs de workflows de riesgos y escala los vencidos."""
    from app.database import SessionLocal
    from app.services.workflow_engine import run_sla_check

    db = SessionLocal()
    try:
        run_sla_check(db)
    except Exception as exc:
        logger.exception("Error en sla_check: %s", exc)
    finally:
        db.close()


def _run_evidence_expiry_check() -> None:
    """Alerta sobre evidencias proximas a vencer (30 dias) o vencidas."""
    from datetime import timedelta
    from app.database import SessionLocal
    from app.models import Evidence, User, UserRole
    from app.services import email_service

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        soon = now + timedelta(days=30)

        # Evidencias que vencen en 30 dias y no se ha enviado alerta
        expiring = db.query(Evidence).filter(
            Evidence.expires_at.isnot(None),
            Evidence.expires_at <= soon,
            Evidence.expires_at >= now,
            Evidence.expiry_alert_sent == False,
            Evidence.is_current == True,
        ).all()

        if not expiring:
            return

        alerted = 0
        for ev in expiring:
            ev.expiry_alert_sent = True
            days_left = (ev.expires_at - now).days if ev.expires_at else 0

            try:
                cfg = email_service.get_settings_for_org(db, ev.organization_id)
                if cfg and cfg.smtp_host:
                    admins = db.query(User).filter(
                        User.organization_id == ev.organization_id,
                        User.role == UserRole.ADMIN,
                        User.is_active == True,
                        User.email.isnot(None),
                    ).all()
                    for admin in admins:
                        subject = f"[RiskHub] Evidencia {ev.code} vence en {days_left} días"
                        body = (
                            f"<p>La evidencia <strong>{ev.code} — {ev.title}</strong> "
                            f"vence en <strong>{days_left} días</strong> "
                            f"({ev.expires_at.strftime('%d/%m/%Y')}).</p>"
                            f"<p>Accede a RiskHub para renovarla o subir una nueva versión.</p>"
                        )
                        email_service.send_email(cfg, admin.email, subject, body)
            except Exception as exc:
                logger.debug("Error enviando alerta evidencia: %s", exc)

            # Disparar webhook
            try:
                from app.services.webhook_service import fire_event
                from app.models import WebhookEvent
                fire_event(db, ev.organization_id, WebhookEvent.EVIDENCE_EXPIRED, {
                    "evidence_id": ev.id,
                    "code": ev.code,
                    "title": ev.title,
                    "expires_at": ev.expires_at.isoformat() if ev.expires_at else None,
                    "days_left": days_left,
                })
            except Exception:
                pass

            alerted += 1

        if alerted:
            db.commit()
            logger.info("Evidence expiry: %d evidencias alertadas", alerted)
    except Exception as exc:
        logger.exception("Error en evidence_expiry_check: %s", exc)
    finally:
        db.close()


def _run_ccm_tests() -> None:
    """Ejecuta tests CCM diariamente por organización y alerta si hay FAIL nuevos."""
    from app.database import SessionLocal
    from app.models import Organization, RiskContext
    from app.services.ccm_service import run_all_tests
    from app.services import email_service

    db = SessionLocal()
    try:
        orgs = db.query(Organization).filter(Organization.is_active == True).all()
        for org in orgs:
            try:
                results = run_all_tests(db, org.id)
                fails = [r for r in results.get("results", []) if r["status"] == "FAIL"]
                score = results.get("score", 0)
                logger.info("CCM org=%d: score=%s FAIL=%d", org.id, score, len(fails))

                # Alertar si score < 70 o hay FAILs críticos
                if fails and score < 70:
                    cfg = email_service.get_settings_for_org(db, org.id)
                    if cfg and cfg.smtp_host:
                        from app.models import User, UserRole
                        admins = db.query(User).filter(
                            User.organization_id == org.id,
                            User.role == UserRole.ADMIN,
                            User.is_active == True,
                            User.email.isnot(None),
                        ).all()
                        ctx = db.query(RiskContext).filter(
                            RiskContext.organization_id == org.id
                        ).first()
                        org_name = ctx.organization_name if ctx else org.name if hasattr(org, "name") else f"Org {org.id}"
                        fail_items = "".join(
                            f"<li><strong>{r['control_code']}</strong>: {r['name']} — {r['detail']}<br>"
                            f"<em>{r.get('recommendation','')}</em></li>"
                            for r in fails[:8]
                        )
                        html = (
                            f"<p><strong>{org_name}</strong> — CCM Score: <strong>{score}/100</strong></p>"
                            f"<p>Se han detectado {len(fails)} control(es) fallando:</p>"
                            f"<ul>{fail_items}</ul>"
                            f"<p>Accede a RiskHub → CCM para ver el detalle completo.</p>"
                        )
                        for admin in admins:
                            email_service.send_email(
                                cfg, admin.email,
                                f"[RiskHub] CCM Alert: {len(fails)} controles FAIL — Score {score}/100",
                                html
                            )
            except Exception as exc:
                logger.exception("Error en CCM tests para org %d: %s", org.id, exc)
    except Exception as exc:
        logger.exception("Error en _run_ccm_tests: %s", exc)
    finally:
        db.close()


def _supplier_score_to_likelihood(score: float) -> int:
    """Mapea residual_risk_score del proveedor (0-100, mayor=mas riesgo) a likelihood ISO 27005 (0-4)."""
    if score >= 70:
        return 3
    if score >= 50:
        return 2
    if score >= 30:
        return 1
    return 0


def _run_supplier_scoring() -> None:
    """Actualiza el score de riesgo de todos los proveedores semanalmente.

    Tras recalcular los scores, propaga cambios significativos (>=10 puntos) al
    inherent_likelihood de los riesgos TPRM vinculados (Risk.supplier_id).
    """
    from app.database import SessionLocal
    from app.models import Organization, Supplier, Risk, RiskStatus
    from app.services.supplier_scoring_service import update_all_supplier_scores

    db = SessionLocal()
    try:
        orgs = db.query(Organization).filter(Organization.is_active == True).all()
        for org in orgs:
            try:
                # Guardar scores anteriores para detectar cambios
                pre_scores = {
                    s.id: s.residual_risk_score
                    for s in db.query(Supplier).filter(
                        Supplier.organization_id == org.id,
                        Supplier.residual_risk_score.isnot(None),
                    ).all()
                }

                stats = update_all_supplier_scores(db, org.id)
                if stats["updated"] > 0:
                    logger.info(
                        "Supplier scoring org=%d: %d actualizados H=%d M=%d L=%d",
                        org.id, stats["updated"],
                        stats["high_risk"], stats["medium_risk"], stats["low_risk"]
                    )

                # Propagar cambios significativos a riesgos TPRM vinculados
                changed_suppliers = db.query(Supplier).filter(
                    Supplier.organization_id == org.id,
                    Supplier.residual_risk_score.isnot(None),
                    Supplier.id.in_(pre_scores.keys()),
                ).all()

                risk_updates = 0
                from app.routers.risks import _recalc
                for supplier in changed_suppliers:
                    prev = pre_scores.get(supplier.id) or 0
                    new_score = supplier.residual_risk_score or 0
                    if abs(new_score - prev) < 10:
                        continue  # cambio no significativo
                    new_lik = _supplier_score_to_likelihood(new_score)
                    tprm_risks = db.query(Risk).filter(
                        Risk.supplier_id == supplier.id,
                        Risk.organization_id == org.id,
                        Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
                    ).all()
                    for r in tprm_risks:
                        if r.inherent_likelihood != new_lik:
                            r.inherent_likelihood = new_lik
                            r.likelihood_adjusted_reason = (
                                f"Score TPRM actualizado: {supplier.name} "
                                f"({prev}→{new_score})"
                            )
                            _recalc(db, r)
                            risk_updates += 1
                if risk_updates:
                    db.commit()
                    logger.info(
                        "Supplier scoring→risk propagation org=%d: %d riesgos actualizados",
                        org.id, risk_updates,
                    )

            except Exception as exc:
                logger.exception("Error en supplier scoring org %d: %s", org.id, exc)
    except Exception as exc:
        logger.exception("Error en _run_supplier_scoring: %s", exc)
    finally:
        db.close()


def _run_cisa_kev_sync() -> None:
    """Descarga KEV de CISA y cruza con software_tags de activos para generar riesgos CVE."""
    import urllib.request
    import json as _json
    from app.database import SessionLocal
    from app.models import Asset, Organization
    from app.services.risk_auto_generator import auto_generate_risk_from_cve

    db = SessionLocal()
    try:
        url = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
        with urllib.request.urlopen(url, timeout=30) as r:
            kev_data = _json.loads(r.read())
        vulnerabilities = kev_data.get("vulnerabilities", [])
        if not vulnerabilities:
            return
        logger.info("CISA KEV: %d vulnerabilidades descargadas", len(vulnerabilities))

        from app.models import Risk, RiskStatus
        from app.routers.risks import _recalc

        orgs = db.query(Organization).filter(Organization.is_active.is_(True)).all()
        created_count = 0
        updated_count = 0
        for org in orgs:
            assets = db.query(Asset).filter(
                Asset.organization_id == org.id,
                Asset.software_tags.isnot(None),
            ).all()
            if not assets:
                continue
            for asset in assets:
                tags = [t.lower() for t in (asset.software_tags or [])]
                if not tags:
                    continue
                for vuln in vulnerabilities:
                    product = vuln.get("product", "").lower()
                    vendor = vuln.get("vendorProject", "").lower()
                    if any(tag in product or tag in vendor for tag in tags if len(tag) > 3):
                        cve_id = vuln.get("cveID", "UNKNOWN")
                        # Crear nuevo riesgo si no existe
                        risk = auto_generate_risk_from_cve(
                            db, asset.id, cve_id,
                            affected_software=f"{vuln.get('vendorProject','')} {vuln.get('product','')}".strip(),
                            inherent_consequence=4,
                            inherent_likelihood=4,   # KEV = explotado activamente
                        )
                        if risk:
                            created_count += 1

                        # Actualizar riesgos existentes vinculados al mismo activo
                        existing_risks = db.query(Risk).filter(
                            Risk.asset_id == asset.id,
                            Risk.organization_id == org.id,
                            Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
                        ).all()
                        for r in existing_risks:
                            new_lik = max(3, r.inherent_likelihood or 0)
                            if r.inherent_likelihood != new_lik:
                                r.inherent_likelihood = new_lik
                                r.likelihood_adjusted_reason = (
                                    f"CISA KEV: explotacion activa confirmada — {cve_id}"
                                )
                                _recalc(db, r)
                                updated_count += 1

        if created_count or updated_count:
            db.commit()
            logger.info(
                "CISA KEV: %d nuevos riesgos, %d riesgos existentes actualizados",
                created_count, updated_count,
            )
    except Exception as exc:
        logger.exception("Error en CISA KEV sync: %s", exc)
    finally:
        db.close()


def _run_compliance_review_reminders() -> None:
    """Dia 1 de cada mes: alerta sobre requisitos de compliance sin revisar en 300+ dias.

    Para cada org con SMTP configurado, notifica al admin de los requisitos implementados
    que no han sido revisados en el periodo recomendado.
    """
    from datetime import timedelta
    from app.database import SessionLocal
    from app.models import (
        ComplianceFrameworkStatus, ComplianceRequirementStatus,
        EmailSettings, Organization, User, UserRole,
    )
    from app.services import email_service

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(days=300)

        orgs = db.query(Organization).filter(Organization.is_active.is_(True)).all()
        for org in orgs:
            stale = db.query(ComplianceFrameworkStatus).filter(
                ComplianceFrameworkStatus.organization_id == org.id,
                ComplianceFrameworkStatus.status == ComplianceRequirementStatus.IMPLEMENTED,
                ComplianceFrameworkStatus.last_reviewed_at < stale_cutoff,
            ).all()
            if not stale:
                continue

            cfg = db.query(EmailSettings).filter_by(organization_id=org.id).first()
            if not cfg or not cfg.smtp_host:
                continue

            admin = db.query(User).filter_by(
                organization_id=org.id, role=UserRole.ADMIN, is_active=True
            ).first()
            if not admin or not admin.email:
                continue

            rows_html = "".join(
                f"<tr><td style='padding:6px 10px;'>{s.framework_code.upper()}</td>"
                f"<td style='padding:6px 10px;'>{s.requirement_id}</td>"
                f"<td style='padding:6px 10px;'>"
                f"{s.last_reviewed_at.strftime('%d/%m/%Y') if s.last_reviewed_at else 'Nunca'}"
                f"</td></tr>"
                for s in stale[:20]
            )
            subject = f"[RiskHub] {len(stale)} requisito(s) de compliance sin revision — {org.name}"
            body_html = (
                f"<p>Los siguientes requisitos de compliance en <strong>{org.name}</strong> "
                f"llevan mas de 300 dias sin revisarse:</p>"
                f"<table style='border-collapse:collapse;font-size:13px;'>"
                f"<thead><tr>"
                f"<th style='padding:6px 10px;background:#f0f0f0;text-align:left;'>Framework</th>"
                f"<th style='padding:6px 10px;background:#f0f0f0;text-align:left;'>Requisito</th>"
                f"<th style='padding:6px 10px;background:#f0f0f0;text-align:left;'>Ultima revision</th>"
                f"</tr></thead><tbody>{rows_html}</tbody></table>"
                f"<p style='margin-top:16px;'>Accede a RiskHub &rarr; Cumplimiento Normativo para revisar y actualizar su estado.</p>"
            )
            try:
                email_service.send_email(cfg, admin.email, subject, body_html)
                logger.info(
                    "Compliance reminders enviados a %s org=%d (%d requisitos)",
                    admin.email, org.id, len(stale),
                )
            except Exception as exc2:
                logger.debug("Error enviando compliance reminder org=%d: %s", org.id, exc2)
    except Exception as exc:
        logger.exception("compliance_review_reminders error: %s", exc)
    finally:
        db.close()


def _run_nis2_deadline_check() -> None:
    """Detecta notificaciones NIS2 proximas a vencer y marca overdue."""
    from app.database import SessionLocal
    from app.services.nis2_service import check_nis2_deadlines

    db = SessionLocal()
    try:
        check_nis2_deadlines(db)
    except Exception as exc:
        logger.exception("Error en NIS2 deadline check: %s", exc)
    finally:
        db.close()


def _run_management_review_prepare() -> None:
    """Dia 25 de cada mes: prepara borrador de Management Review para el mes siguiente."""
    from app.database import SessionLocal
    from app.models import Organization
    from app.services.management_review_service import prepare_monthly_review

    db = SessionLocal()
    try:
        orgs = db.query(Organization).filter(Organization.is_active.is_(True)).all()
        for org in orgs:
            try:
                mr = prepare_monthly_review(db, org.id)
                logger.info("Management Review preparada: org=%d code=%s", org.id, mr.code)
            except Exception as exc:
                logger.exception("Error preparando MR para org %d: %s", org.id, exc)
    except Exception as exc:
        logger.exception("Error en management_review_prepare: %s", exc)
    finally:
        db.close()


def _run_scheduled_reports() -> None:
    """Envía informes PDF programados a sus destinatarios."""
    from datetime import timedelta
    from app.database import SessionLocal
    from app.models import ReportSchedule
    from app.services import email_service, report_ai_service

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        due = db.query(ReportSchedule).filter(
            ReportSchedule.is_active.is_(True),
            ReportSchedule.next_scheduled_at <= now,
        ).all()

        for schedule in due:
            try:
                from app.models import EmailSettings
                cfg = db.query(EmailSettings).filter_by(
                    organization_id=schedule.organization_id
                ).first()
                if not cfg or not cfg.smtp_host:
                    continue

                try:
                    from app.routers.ai_config import resolve_api_key
                    api_key = resolve_api_key(db, schedule.organization_id)
                except Exception:
                    api_key = None

                data = report_ai_service.generate(
                    schedule.report_type, db,
                    org_id=schedule.organization_id,
                    api_key=api_key,
                )
                subject = f"[RiskHub] Informe programado: {schedule.report_type}"
                body_html = f"<p>Informe automatico <strong>{schedule.report_type}</strong> adjunto.</p>"
                for email_addr in (schedule.recipients or []):
                    try:
                        email_service.send_email(cfg, email_addr, subject, body_html)
                    except Exception as exc2:
                        logger.warning("Error enviando informe a %s: %s", email_addr, exc2)

                schedule.last_sent_at = now
                # Recalcular proxima ejecucion
                delta_map = {"weekly": timedelta(days=7), "monthly": timedelta(days=30),
                             "quarterly": timedelta(days=90)}
                schedule.next_scheduled_at = now + delta_map.get(schedule.frequency, timedelta(days=30))
                db.commit()
            except Exception as exc:
                logger.warning("Error en scheduled report id=%d: %s", schedule.id, exc)
    except Exception as exc:
        logger.exception("Error en _run_scheduled_reports: %s", exc)
    finally:
        db.close()


def _run_acceptance_expiry_check() -> None:
    """Riesgos ACCEPTED cuya acceptance_review_date ha pasado → vuelven a ASSESSED."""
    from app.database import SessionLocal
    from app.models import Risk, RiskStatus

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        expired = db.query(Risk).filter(
            Risk.status == RiskStatus.ACCEPTED,
            Risk.acceptance_review_date < now,
            Risk.acceptance_review_date.isnot(None),
        ).all()
        for risk in expired:
            risk.status = RiskStatus.ASSESSED
            risk.treatment_option = None   # requiere nueva decision
            logger.info("Risk %s acceptance expirado → ASSESSED", risk.code)
        if expired:
            db.commit()
            logger.info("Acceptance expiry: %d riesgos devueltos a ASSESSED", len(expired))
    except Exception as exc:
        logger.exception("Error en acceptance_expiry_check: %s", exc)
    finally:
        db.close()


def _run_soa_review_check() -> None:
    """Alerta si la SoA no ha sido aprobada en 11 meses."""
    from datetime import timedelta
    from app.database import SessionLocal
    from app.models import SoAVersion, Organization, User, UserRole, EmailSettings
    from app.services import email_service

    db = SessionLocal()
    try:
        orgs = db.query(Organization).filter(Organization.is_active.is_(True)).all()
        now = datetime.now(timezone.utc)
        for org in orgs:
            latest = (
                db.query(SoAVersion)
                .filter_by(organization_id=org.id, status="approved")
                .order_by(SoAVersion.approved_at.desc())
                .first()
            )
            needs_alert = False
            msg = ""
            if not latest:
                needs_alert = True
                msg = "No existe ninguna version aprobada de la SoA"
            elif latest.approved_at:
                approved_dt = latest.approved_at
                if not approved_dt.tzinfo:
                    approved_dt = approved_dt.replace(tzinfo=timezone.utc)
                if (now - approved_dt).days > 330:
                    needs_alert = True
                    msg = f"La ultima version aprobada ({latest.version}) tiene {(now - approved_dt).days} dias"

            if needs_alert:
                cfg = db.query(EmailSettings).filter_by(organization_id=org.id).first()
                if cfg and cfg.smtp_host:
                    admins = db.query(User).filter_by(
                        organization_id=org.id, role=UserRole.ADMIN, is_active=True
                    ).all()
                    for admin in admins:
                        if admin.email:
                            subject = f"[RiskHub] SoA pendiente de revision — {org.name}"
                            body = (
                                f"<p><strong>ISO 27001 cl. 6.1.3</strong> requiere revisar y aprobar la SoA anualmente.</p>"
                                f"<p>{msg}.</p>"
                                f"<p>Accede a RiskHub &rarr; SoA para crear una nueva version.</p>"
                            )
                            try:
                                email_service.send_email(cfg, admin.email, subject, body)
                            except Exception as exc2:
                                logger.debug("Error enviando alerta SoA: %s", exc2)
    except Exception as exc:
        logger.exception("Error en soa_review_check: %s", exc)
    finally:
        db.close()


def _run_license_expiry_check() -> None:
    """Auto-expira licencias vencidas y las marca como EXPIRED."""
    from app.database import SessionLocal
    from app.services import license_service as lic_svc

    db = SessionLocal()
    try:
        expired_count = lic_svc.auto_expire_licenses(db)
        if expired_count:
            logger.info("License expiry: %d licencias expiradas automaticamente", expired_count)
    except Exception as exc:
        logger.exception("Error en license_expiry_check: %s", exc)
    finally:
        db.close()


def _run_compliance_auto_sync() -> None:
    """Sincroniza estado de compliance con controles implementados."""
    from app.database import SessionLocal
    from app.models import Organization
    from app.services.compliance_service import auto_update_compliance_from_controls

    db = SessionLocal()
    try:
        orgs = db.query(Organization).filter(Organization.is_active == True).all()
        total_updated = 0
        for org in orgs:
            updated = auto_update_compliance_from_controls(db, org.id)
            total_updated += updated
        if total_updated:
            logger.info("Compliance auto-sync: %d requisitos actualizados", total_updated)
    except Exception as exc:
        logger.exception("Error en compliance_auto_sync: %s", exc)
    finally:
        db.close()


def _run_bcp_test_overdue() -> None:
    """Alerta sobre procesos BCP criticos sin test de continuidad en >12 meses.

    Ademas incrementa inherent_likelihood de riesgos de disponibilidad vinculados
    a los activos cubiertos por esos procesos (ISO 22301 cl. 8.5 / ISO 27005).
    """
    from app.models import BusinessProcess, Risk, RiskStatus, User, UserRole
    from app.database import SessionLocal
    from app.services import email_service
    from app.routers.risks import _recalc

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        procs = db.query(BusinessProcess).filter(
            BusinessProcess.criticality.in_(["critical", "high"])
        ).all()
        by_org: dict[int, list] = {}
        for p in procs:
            if not p.organization_id:
                continue
            stale = (
                not p.last_tested_at
                or (now - p.last_tested_at.replace(tzinfo=timezone.utc)).days > 365
            )
            if stale:
                by_org.setdefault(p.organization_id, []).append(p)

        for org_id, procs_list in by_org.items():
            # Notificacion por email al admin
            cfg = email_service.get_settings_for_org(db, org_id)
            if cfg and cfg.smtp_host:
                admin = db.query(User).filter_by(
                    organization_id=org_id, role=UserRole.ADMIN, is_active=True
                ).first()
                if admin:
                    names = ", ".join(p.name for p in procs_list[:5])
                    suffix = "..." if len(procs_list) > 5 else ""
                    subject = "[RiskHub] Procesos BCM sin test de continuidad"
                    body_html = (
                        f"<p>Los siguientes <strong>{len(procs_list)}</strong> proceso(s) critico(s) "
                        f"no tienen un test de continuidad en los ultimos 12 meses:</p>"
                        f"<p>{names}{suffix}</p>"
                        f"<p>ISO 22301 cl. 8.5 requiere ejercicios periodicos. "
                        f"<a href='#/bcp'>Ir al modulo BCP</a></p>"
                    )
                    try:
                        email_service.send_email(cfg, admin.email, subject,
                                                  email_service._wrap_html(subject, body_html, ""))
                    except Exception:
                        pass

            # Incrementar likelihood de riesgos de disponibilidad en activos cubiertos
            asset_ids: set[int] = set()
            for p in procs_list:
                for asset in getattr(p, "assets", None) or []:
                    asset_ids.add(asset.id)

            if not asset_ids:
                continue

            availability_risks = db.query(Risk).filter(
                Risk.asset_id.in_(asset_ids),
                Risk.organization_id == org_id,
                Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
                Risk.inherent_likelihood < 4,
            ).all()

            risk_updates = 0
            for r in availability_risks:
                r.inherent_likelihood = min(4, (r.inherent_likelihood or 0) + 1)
                r.likelihood_adjusted_reason = (
                    "BCP/BCM sin test >12m — mayor exposicion a interrupcion (ISO 22301)"
                )
                _recalc(db, r)
                risk_updates += 1

            if risk_updates:
                db.commit()
                logger.info(
                    "BCP overdue→risk propagation org=%d: %d riesgos de disponibilidad actualizados",
                    org_id, risk_updates,
                )

    except Exception as exc:
        logger.exception("bcp_test_overdue error: %s", exc)
    finally:
        db.close()


def _run_bcp_plan_review_due() -> None:
    """Alerta sobre planes BCP cuya fecha de revision ha vencido."""
    from app.models import BCPPlan, User, UserRole
    from app.database import SessionLocal
    from app.services import email_service
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        overdue = db.query(BCPPlan).filter(
            BCPPlan.status.in_(["approved"]),
            BCPPlan.review_date < now,
            BCPPlan.review_date.isnot(None),
        ).all()
        by_org: dict[int, list] = {}
        for p in overdue:
            if p.organization_id:
                by_org.setdefault(p.organization_id, []).append(p)
        for org_id, plans in by_org.items():
            cfg = email_service.get_settings_for_org(db, org_id)
            if not cfg or not cfg.smtp_host:
                continue
            admin = db.query(User).filter_by(
                organization_id=org_id, role=UserRole.ADMIN, is_active=True
            ).first()
            if not admin:
                continue
            names = ", ".join(f"{p.code} ({p.plan_type})" for p in plans[:5])
            suffix = "..." if len(plans) > 5 else ""
            subject = "[RiskHub] Planes de continuidad pendientes de revision"
            body_html = (
                f"<p><strong>{len(plans)}</strong> plan(es) BCP/DRP superaron su fecha de revision:</p>"
                f"<p>{names}{suffix}</p>"
                f"<p>ISO 22301 cl. 8.4 requiere revision periodica de los planes. "
                f"<a href='#/bcp'>Ir al modulo BCP</a></p>"
            )
            try:
                email_service.send_email(cfg, admin.email, subject,
                                         email_service._wrap_html(subject, body_html, ""))
            except Exception:
                pass
    except Exception as exc:
        logger.exception("bcp_plan_review_due error: %s", exc)
    finally:
        # Actualizar cobertura BCP en el registro de riesgos (ISO 22301 cl. 8.4 / ISO 27001 A.5.29)
        try:
            from app.services.bcp_service import update_risk_bcp_coverage
            orgs = db.query(Organization).filter_by(is_active=True).all()
            for org in orgs:
                update_risk_bcp_coverage(db, org.id)
        except Exception as exc_cov:
            logger.debug("bcp risk coverage update error: %s", exc_cov)
        db.close()


def _run_survey_reminders() -> None:
    """Recordatorio diario a destinatarios de encuestas activas próximas al deadline."""
    from app.services.survey_service import send_reminders
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        base_url = "https://localhost"
        try:
            from app.config import settings as _s
            base_url = getattr(_s, "base_url", base_url)
        except Exception:
            pass
        sent = send_reminders(db, base_url)
        if sent > 0:
            logger.info("Survey reminders sent: %d", sent)
    except Exception as exc:
        logger.exception("survey_reminders error: %s", exc)
    finally:
        db.close()


def _run_bcp_bia_gap_check() -> None:
    """Alerta sobre procesos criticos con BIA incompleto (<80%)."""
    from app.models import BusinessProcess, User, UserRole
    from app.database import SessionLocal
    from app.services import email_service
    from app.services.bcp_service import bia_completeness
    db = SessionLocal()
    try:
        procs = db.query(BusinessProcess).filter(
            BusinessProcess.criticality.in_(["critical", "high"])
        ).all()
        by_org: dict[int, list] = {}
        for p in procs:
            if not p.organization_id:
                continue
            bia = bia_completeness(db, p)
            if bia["pct"] < 80:
                by_org.setdefault(p.organization_id, []).append(
                    (p.name, bia["pct"], bia["missing"])
                )
        for org_id, gaps in by_org.items():
            cfg = email_service.get_settings_for_org(db, org_id)
            if not cfg or not cfg.smtp_host:
                continue
            admin = db.query(User).filter_by(
                organization_id=org_id, role=UserRole.ADMIN, is_active=True
            ).first()
            if not admin:
                continue
            rows = "".join(
                f"<tr><td>{name}</td><td>{pct}%</td>"
                f"<td>{', '.join(str(m) for m in missing[:3])}</td></tr>"
                for name, pct, missing in gaps[:10]
            )
            subject = "[RiskHub] Analisis de Impacto (BIA) incompletos"
            body_html = (
                f"<p><strong>{len(gaps)}</strong> proceso(s) critico(s) tienen el BIA incompleto:</p>"
                f"<table border='1' cellpadding='4'>"
                f"<tr><th>Proceso</th><th>Completitud</th><th>Campos faltantes</th></tr>"
                f"{rows}</table>"
                f"<p>BIA completo es requerido por ISO 22301 cl. 8.2. "
                f"<a href='#/bcp'>Completar en modulo BCP</a></p>"
            )
            try:
                email_service.send_email(cfg, admin.email, subject,
                                         email_service._wrap_html(subject, body_html, ""))
            except Exception:
                pass
    except Exception as exc:
        logger.exception("bcp_bia_gap_check error: %s", exc)
    finally:
        db.close()


def _run_bcm_test_recommendations() -> None:
    """Genera recomendaciones de tests BCM para todas las organizaciones activas."""
    from app.services.bcm_test_engine import generate_recommendations
    from app.database import SessionLocal
    from app.models import Organization
    db = SessionLocal()
    try:
        orgs = db.query(Organization).filter_by(is_active=True).all()
        total = sum(generate_recommendations(db, o.id) for o in orgs)
        if total:
            logger.info("BCM test recommendations: %d generated", total)
    except Exception as exc:
        logger.exception("bcm_test_recommendations error: %s", exc)
    finally:
        db.close()


def _cleanup_ai_jobs() -> None:
    """Elimina jobs IA expirados del store en memoria del router de IA."""
    try:
        from app.routers.ai import _JOBS, _JOBS_LOCK, _cleanup_old_jobs
        with _JOBS_LOCK:
            _cleanup_old_jobs()
        logger.debug("AI jobs cleanup completado.")
    except Exception as exc:
        logger.warning("AI jobs cleanup error: %s", exc)


def _run_regwatch_sweep() -> None:
    """Barrido periodico de fuentes de vigilancia normativa (regwatch §5.2)."""
    from app.database import SessionLocal
    from app.services import regwatch_service

    db = SessionLocal()
    try:
        regwatch_service.run_sweep(db)
    except Exception as exc:
        logger.exception("Error en regwatch_sweep: %s", exc)
    finally:
        db.close()


def schedule_first_sweep(delay_minutes: int = 5) -> None:
    """Programa un barrido unico de regwatch poco despues de activar el toggle.

    Spec §2.3: al activar, se programa el primer barrido para ~5 min despues.
    No-op silencioso si el scheduler aun no esta iniciado.
    """
    from datetime import timedelta
    if _scheduler is None:
        return
    try:
        run_at = datetime.now(timezone.utc) + timedelta(minutes=max(1, delay_minutes))
        _scheduler.add_job(
            func=_run_regwatch_sweep,
            trigger="date",
            run_date=run_at,
            id="regwatch_first_sweep",
            name="Vigilancia normativa — primer barrido tras activacion",
            replace_existing=True,
            misfire_grace_time=600,
        )
    except Exception as exc:
        logger.warning("No se pudo programar el primer barrido regwatch: %s", exc)


def _run_questionnaire_schedules() -> None:
    """Envia cuestionarios planificados a los proveedores cuando llega su fecha."""
    from app.database import SessionLocal
    from app.models import QuestionnaireSchedule, SupplierQuestionnaire, EmailSettings
    import secrets

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        due = (
            db.query(QuestionnaireSchedule)
            .filter(
                QuestionnaireSchedule.enabled.is_(True),
                QuestionnaireSchedule.next_send_at <= now,
            )
            .all()
        )
        if not due:
            return

        from app.services import tprm_templates as _sys_tpls
        from app.routers.supplier_questionnaires import DEFAULT_QUESTIONS

        for sched in due:
            try:
                supplier = sched.supplier
                if not supplier:
                    continue

                # Resolver plantilla
                questions = DEFAULT_QUESTIONS
                template_code = None
                if sched.template_code:
                    tpl = _sys_tpls.get_template(sched.template_code)
                    if tpl:
                        questions = tpl["questions"]
                        template_code = tpl["code"]
                elif sched.custom_template_id:
                    from app.models import TPRMTemplate
                    tpl = db.query(TPRMTemplate).filter(
                        TPRMTemplate.id == sched.custom_template_id
                    ).first()
                    if tpl:
                        questions = tpl.questions or []
                        template_code = f"custom:{tpl.id}"

                # Generar titulo
                title = (sched.title_template or "Evaluacion de seguridad")
                title = title.replace("{year}", str(now.year)).replace("{month}", str(now.month))

                from datetime import timedelta
                expires = now + timedelta(days=sched.expires_days or 30)

                n = db.query(SupplierQuestionnaire).count() + 1
                code = f"SEQ-{n:04d}"
                q = SupplierQuestionnaire(
                    code=code,
                    supplier_id=supplier.id,
                    title=title,
                    token=secrets.token_urlsafe(32),
                    template_code=template_code,
                    questions=questions,
                    expires_at=expires,
                    notes=f"Enviado automaticamente por planificacion (cada {sched.interval_days} dias).",
                    organization_id=sched.organization_id,
                )
                db.add(q)
                db.flush()

                # Enviar email al proveedor si tiene contacto
                recipient = (supplier.contact_email or "").strip()
                if recipient:
                    cfg = (
                        db.query(EmailSettings)
                        .filter(EmailSettings.organization_id == sched.organization_id)
                        .first()
                    )
                    if cfg and cfg.smtp_host:
                        from app.services import email_service
                        link = f"http://localhost/supplier-q?token={q.token}"
                        expires_str = expires.strftime("%d/%m/%Y")
                        body_html = f"""
                        <div style="font-family:Inter,Arial,sans-serif;color:#1f2937;">
                          <p>Estimado/a {UI.esc(supplier.contact_name or supplier.name)}:</p>
                          <p>Le solicitamos completar el siguiente cuestionario de seguridad:
                          <strong>{UI.esc(title)}</strong>.</p>
                          <p style="margin:24px 0;">
                            <a href="{link}" style="background:#59008D;color:#fff;padding:12px 24px;
                               border-radius:6px;text-decoration:none;font-weight:600;">Completar cuestionario</a>
                          </p>
                          <p style="font-size:13px;color:#6b7280;">Fecha limite: {expires_str}.</p>
                        </div>
                        """
                        try:
                            email_service.send_email(cfg, recipient, f"Cuestionario de seguridad — {title}", body_html)
                        except Exception as exc:
                            logger.warning("Error enviando cuestionario planificado a %s: %s", recipient, exc)

                # Actualizar planificacion
                from datetime import timedelta
                sched.last_sent_at = now
                sched.next_send_at = now + timedelta(days=sched.interval_days or 365)
                db.commit()
                logger.info(
                    "Cuestionario planificado %s enviado a proveedor %s (siguiente: %s)",
                    q.code, supplier.code, sched.next_send_at.date(),
                )
            except Exception as exc:
                logger.warning("Error procesando planificacion %d: %s", sched.id, exc)
                db.rollback()
    finally:
        db.close()


def _notify_questionnaire_submitted(questionnaire_id: int, org_id: int) -> None:
    """Notifica por email cuando un proveedor responde cualquier cuestionario.

    Destinatarios (sin duplicados):
    1. notify_email del propio cuestionario.
    2. notify_email de la planificacion activa del mismo proveedor.
    3. cc_email del proveedor.
    """
    from app.database import SessionLocal
    from app.models import QuestionnaireSchedule, SupplierQuestionnaire, EmailSettings

    db = SessionLocal()
    try:
        q = db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == questionnaire_id).first()
        if not q:
            return

        # Recoger todos los destinatarios relevantes
        recipients: set[str] = set()
        if getattr(q, "notify_email", None):
            recipients.add(q.notify_email.strip())

        # Planificacion activa del proveedor
        sched = (
            db.query(QuestionnaireSchedule)
            .filter(
                QuestionnaireSchedule.supplier_id == q.supplier_id,
                QuestionnaireSchedule.organization_id == org_id,
                QuestionnaireSchedule.notify_email != None,  # noqa: E711
            )
            .first()
        )
        if sched and sched.notify_email:
            recipients.add(sched.notify_email.strip())

        # CC del proveedor
        supplier = q.supplier
        if supplier and getattr(supplier, "cc_email", None):
            recipients.add(supplier.cc_email.strip())

        if not recipients:
            return

        cfg = db.query(EmailSettings).filter(EmailSettings.organization_id == org_id).first()
        if not cfg or not cfg.smtp_host:
            return

        supplier_name = supplier.name if supplier else "proveedor"
        subject = f"RiskHub — {supplier_name} ha respondido el cuestionario {q.code}"
        body_html = f"""
        <div style="font-family:Inter,Arial,sans-serif;color:#1f2937;max-width:600px;">
          <div style="background:linear-gradient(90deg,#59008D,#D65200);padding:20px 28px;">
            <h1 style="color:#fff;margin:0;font-size:18px;">RiskHub — Cuestionario respondido</h1>
          </div>
          <div style="padding:24px;">
            <p>El proveedor <strong>{supplier_name}</strong> ha respondido el cuestionario
            <strong>{q.code} — {q.title}</strong>.</p>
            <p>Puntuacion obtenida: <strong>{q.score if q.score is not None else '-'}/100</strong></p>
            <p>Accede a RiskHub para revisar las respuestas y lanzar el analisis de IA.</p>
          </div>
        </div>
        """
        from app.services import email_service
        recipients_list = list(recipients)
        primary = recipients_list[0]
        cc_list = recipients_list[1:] if len(recipients_list) > 1 else None
        try:
            email_service.send_email(cfg, primary, subject, body_html, cc=cc_list)
        except Exception as exc:
            logger.warning("Error enviando notificacion de respuesta: %s", exc)
    finally:
        db.close()


def _run_supplier_monitoring() -> None:
    """Monitorea semanalmente la disponibilidad web, SSL y DNS de todos los proveedores
    que tienen website o contact_email configurado. Crea ExternalFinding por cada problema
    detectado, enlazado al proveedor."""
    from app.database import SessionLocal
    from app.models import Supplier

    db = SessionLocal()
    try:
        suppliers = db.query(Supplier).filter(
            (Supplier.website != None) | (Supplier.contact_email != None)  # noqa: E711
        ).all()
        if not suppliers:
            return

        from app.services.supplier_monitoring_service import scan_supplier

        total_findings = 0
        for s in suppliers:
            try:
                findings = scan_supplier(db, s, s.organization_id)
                total_findings += len(findings)
            except Exception as exc:
                logger.warning("Error monitorizando proveedor %s: %s", getattr(s, "code", "?"), exc)

        if total_findings:
            db.commit()
            logger.info("Monitoreo de proveedores completado: %d hallazgos creados/actualizados.", total_findings)
        else:
            logger.debug("Monitoreo de proveedores: todos los proveedores accesibles.")
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
        misfire_grace_time=300,
    )
    _scheduler.add_job(
        func=_run_risk_reviews,
        trigger=IntervalTrigger(hours=24),
        id="check_risk_reviews",
        name="Recordatorios de revision periodica de riesgos",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_cve_auto_scan,
        trigger=IntervalTrigger(hours=24),
        id="cve_auto_scan",
        name="Escaneo automatico diario de CVEs",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_task_escalation,
        trigger=IntervalTrigger(hours=24),
        id="task_escalation",
        name="Escalada automatica de prioridad de tareas vencidas",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_policy_review_tasks,
        trigger=IntervalTrigger(hours=24),
        id="policy_review_tasks",
        name="Creacion de tareas por politicas con revision vencida",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_incident_tasks,
        trigger=IntervalTrigger(hours=24),
        id="incident_tasks",
        name="Creacion de tareas para incidentes sin resolver >7 dias",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_control_degradation,
        trigger=IntervalTrigger(hours=168),  # semanal
        id="control_degradation",
        name="Degradacion de controles IMPLEMENTED sin evidencia",
        replace_existing=True,
        misfire_grace_time=7200,
    )
    _scheduler.add_job(
        func=_run_osint_periodic_scan,
        trigger=IntervalTrigger(hours=168),  # semanal
        id="osint_periodic_scan",
        name="Re-escaneo periodico de objetivos OSINT",
        replace_existing=True,
        misfire_grace_time=7200,
    )
    _scheduler.add_job(
        func=_run_monthly_report,
        trigger=IntervalTrigger(hours=24),  # se autofiltra por day==1
        id="monthly_report",
        name="Informe mensual de seguridad por email",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_sla_check,
        trigger=IntervalTrigger(hours=24),
        id="sla_check",
        name="Verificacion SLA de workflows de riesgos",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_evidence_expiry_check,
        trigger=IntervalTrigger(hours=24),
        id="evidence_expiry",
        name="Alerta de evidencias proximas a vencer",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_compliance_auto_sync,
        trigger=IntervalTrigger(hours=168),  # semanal
        id="compliance_sync",
        name="Sincronizacion automatica de estado de compliance",
        replace_existing=True,
        misfire_grace_time=7200,
    )
    _scheduler.add_job(
        func=_run_ccm_tests,
        trigger=IntervalTrigger(hours=24),
        id="ccm_tests",
        name="Continuous Control Monitoring — tests automáticos diarios",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_supplier_scoring,
        trigger=IntervalTrigger(hours=168),  # semanal
        id="supplier_scoring",
        name="Actualizacion automatica del score de riesgo de proveedores",
        replace_existing=True,
        misfire_grace_time=7200,
    )
    # v2.3.0 — nuevos jobs
    _scheduler.add_job(
        func=_run_compliance_review_reminders,
        trigger=IntervalTrigger(hours=24),  # se autofiltra por day==1
        id="compliance_review_reminders",
        name="Recordatorios de requisitos compliance pendientes de revision",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_cisa_kev_sync,
        trigger=IntervalTrigger(hours=24),
        id="cisa_kev_sync",
        name="Sincronizacion CISA Known Exploited Vulnerabilities",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_nis2_deadline_check,
        trigger=IntervalTrigger(hours=6),
        id="nis2_deadline_check",
        name="Verificacion plazos NIS2 Art. 23",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    _scheduler.add_job(
        func=_run_management_review_prepare,
        trigger=IntervalTrigger(hours=24),   # se autofiltra por day==25
        id="management_review_prepare",
        name="Preparacion automatica Management Review mensual",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_scheduled_reports,
        trigger=IntervalTrigger(hours=24),
        id="scheduled_reports",
        name="Envio de informes programados",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_acceptance_expiry_check,
        trigger=IntervalTrigger(hours=24),
        id="acceptance_expiry_check",
        name="Expiracion de aceptaciones de riesgo",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_soa_review_check,
        trigger=IntervalTrigger(hours=168),   # semanal
        id="soa_review_check",
        name="Alerta de SoA sin revision anual",
        replace_existing=True,
        misfire_grace_time=7200,
    )
    _scheduler.add_job(
        func=_run_license_expiry_check,
        trigger=IntervalTrigger(hours=24),  # diario
        id="license_expiry_check",
        name="Auto-expiracion de licencias vencidas",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # BCP: test overdue (semanal lunes 8h)
    _scheduler.add_job(
        func=_run_bcp_test_overdue,
        trigger=CronTrigger(day_of_week="mon", hour=8),
        id="bcp_test_overdue",
        name="Procesos BCP sin test en >12 meses",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # BCP: revisión de planes vencida (mensual día 1)
    _scheduler.add_job(
        func=_run_bcp_plan_review_due,
        trigger=CronTrigger(day=1, hour=9),
        id="bcp_plan_review_due",
        name="Planes BCP con revision vencida",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # BCP: BIA gap check (mensual día 15)
    _scheduler.add_job(
        func=_run_bcp_bia_gap_check,
        trigger=CronTrigger(day=15, hour=9),
        id="bcp_bia_gap_check",
        name="Procesos criticos con BIA incompleto",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Encuestas: recordatorio diario a las 9:00
    _scheduler.add_job(
        func=_run_survey_reminders,
        trigger=CronTrigger(hour=9),
        id="survey_reminders",
        name="Recordatorios de encuestas pendientes",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_cleanup_ai_jobs,
        trigger=IntervalTrigger(hours=1),
        id="cleanup_ai_jobs",
        name="Limpieza de jobs IA expirados en memoria",
        replace_existing=True,
        misfire_grace_time=300,
    )
    # BCM: generar recomendaciones de tests (domingos 7h)
    _scheduler.add_job(
        func=_run_bcm_test_recommendations,
        trigger=CronTrigger(day_of_week="sun", hour=7),
        id="bcm_test_recommendations",
        name="Generar recomendaciones de tests BCM",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Regwatch: barrido diario de fuentes normativas (§5.2)
    _scheduler.add_job(
        func=_run_regwatch_sweep,
        trigger=IntervalTrigger(hours=24),
        id="regwatch_sweep",
        name="Vigilancia normativa — barrido de fuentes",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Cuestionarios planificados: verificacion diaria de envios pendientes
    _scheduler.add_job(
        func=_run_questionnaire_schedules,
        trigger=IntervalTrigger(hours=24),
        id="questionnaire_schedules",
        name="Envio periodico de cuestionarios planificados",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Monitoreo de proveedores: disponibilidad web, SSL, DNS (semanal)
    _scheduler.add_job(
        func=_run_supplier_monitoring,
        trigger=IntervalTrigger(hours=168),  # semanal
        id="supplier_monitoring",
        name="Monitoreo semanal de disponibilidad de proveedores",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_policy_review_reminders,
        trigger=CronTrigger(hour=9),  # diario a las 9h
        id="policy_review_reminders",
        name="Recordatorio de revision de politicas (30 dias antes)",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=_run_checkout_auto_release,
        trigger=IntervalTrigger(hours=1),
        id="checkout_auto_release",
        name="Auto-liberacion de documentos en edicion (4h)",
        replace_existing=True,
        misfire_grace_time=300,
    )
    _scheduler.add_job(
        func=_run_risk_snapshots,
        trigger=CronTrigger(day=1, hour=2),  # primer dia del mes a las 2h UTC
        id="risk_snapshots",
        name="Snapshot mensual de niveles de riesgo",
        replace_existing=True,
        misfire_grace_time=7200,
    )
    _scheduler.add_job(
        func=_run_kri_evaluation,
        trigger=IntervalTrigger(hours=6),
        id="kri_evaluation",
        name="Evaluacion periodica de KRIs (cada 6h)",
        replace_existing=True,
        misfire_grace_time=1800,
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
