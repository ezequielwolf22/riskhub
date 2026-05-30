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

            elif rule.event_type == "incident_p1p2":
                # Alertar sobre incidentes P1/P2 abiertos (cooldown 20h)
                if rule.last_triggered_at:
                    hours = (now - rule.last_triggered_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                    if hours < 20:
                        continue
                from app.models import Incident, IncidentStatus, IncidentSeverity
                open_p1p2 = db.query(Incident).filter(
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
                    p for p in db.query(Policy).all()
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
                    t for t in db.query(TreatmentTask).all()
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
    """Inteligencia para correlacionar CVE con activos.

    Estrategia: buscar por software conocidos en descripción CVE:
    - Apache, Nginx, IIS, MySQL, PostgreSQL, OpenSSL, etc.
    """
    from app.models import Asset

    cve_id = cve_record.get("cve_id", "UNKNOWN")
    desc = (cve_record.get("description", "") or "").lower()
    affected = []

    # Software patterns conocidos
    software_patterns = {
        "apache": ["apache", "httpd"],
        "nginx": ["nginx"],
        "iis": ["iis", "internet information services"],
        "mysql": ["mysql"],
        "postgresql": ["postgresql", "postgres", "pgsql"],
        "openssl": ["openssl", "ssl/tls"],
        "windows": ["windows", "winrm", "smb"],
        "linux": ["linux", "kernel"],
        "php": ["php"],
        "nodejs": ["node.js", "nodejs"],
    }

    # Detectar software en descripción CVE
    detected_software = set()
    for software, patterns in software_patterns.items():
        if any(p in desc for p in patterns):
            detected_software.add(software)

    # Buscar activos que usan ese software
    for asset in db.query(Asset).filter(Asset.organization_id == org_id).all():
        asset_desc = (asset.description or "").lower()
        asset_name = (asset.name or "").lower()

        # Match 1: CVE ID explícito en asset
        if cve_id.lower() in asset_desc or cve_id.lower() in asset_name:
            affected.append(asset)
            continue

        # Match 2: Software detectado en CVE coincide con asset
        for software in detected_software:
            if software in asset_desc or software in asset_name:
                affected.append(asset)
                break

    return affected


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
                cve_id = cve_record.get("cve_id", "UNKNOWN")
                # MEJORADO: matching inteligente por software
                affected_assets = _match_cve_to_assets(db, cve_record, org_id)

                if not affected_assets:
                    # Fallback: buscar por cualquier asset (conservative)
                    affected_assets = db.query(Asset).filter(
                        Asset.name.ilike(f"%{cve_record.get('affected_product', '')}%")
                    ).all()

                for asset in affected_assets:
                    risk = auto_generate_risk_from_cve(
                        db, asset.id, cve_id,
                        affected_software=cve_record.get("description", "Unknown"),
                        inherent_consequence=4,
                        inherent_likelihood=3,
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
        cfg = email_service.get_settings(db)
        if not cfg or not cfg.smtp_host:
            return

        from app.models import RiskContext
        ctx = db.query(RiskContext).first()
        org = ctx.organization_name if ctx else "Organizacion"

        now = datetime.now(timezone.utc)
        thresholds = [
            (timedelta(days=30), "en 30 dias"),
            (timedelta(days=7), "en 7 dias"),
            (timedelta(days=1), "MANANA"),
        ]

        active_risks = db.query(Risk).filter(
            Risk.next_review.isnot(None),
            Risk.status.not_in([RiskStatus.CLOSED]),
            Risk.owner_id.isnot(None),
        ).all()

        for risk in active_risks:
            # Dedup: no reenviar si ya se notifico en las ultimas 20 horas
            if risk.last_review_notified_at:
                notified_dt = risk.last_review_notified_at
                if not notified_dt.tzinfo:
                    notified_dt = notified_dt.replace(tzinfo=timezone.utc)
                if (now - notified_dt).total_seconds() < 72000:  # 20 horas
                    continue

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

        identifiers = db.query(OSINTIdentifier).filter(
            OSINTIdentifier.last_scanned_at.isnot(None),
            OSINTIdentifier.last_scanned_at < threshold,
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
                        scan_obj = db2.query(OSINTScan).get(sid)
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

        cfg = email_service.get_settings(db)
        if not cfg or not cfg.smtp_host:
            return

        # Obtener todas las orgs con contexto
        contexts = db.query(RiskContext).all()

        for ctx in contexts:
            org_id = ctx.organization_id
            org_name = ctx.organization_name or "Organizacion"

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

        cfg = email_service.get_settings(db)
        alerted = 0
        for ev in expiring:
            ev.expiry_alert_sent = True
            days_left = (ev.expires_at - now).days if ev.expires_at else 0

            try:
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
                        email_service.send_html(cfg, subject, body, [admin.email])
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
