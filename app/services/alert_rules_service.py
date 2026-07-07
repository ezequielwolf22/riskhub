"""Motor de reglas de alerta (AlertRule).

Consolida la evaluacion de reglas para que el scheduler periodico
(services/scheduler.py, cada hora) y el endpoint manual
"Evaluar reglas" (routers/alerts.py POST /check-rules) compartan
exactamente la misma logica — evita que las dos rutas de ejecucion diverjan.

Catalogo de event_type soportados, por categoria:

Riesgos:       risk_critical, risk_high, treatment_overdue, risk_no_treatment,
               treatment_due_soon, daily_digest, compound (entity_type=risk, legacy)
Controles:     control_review_overdue
Incidentes:    incident_p1p2, nis2_pending
Politicas/tareas: policy_review_overdue, task_overdue
Proveedores/TPRM: supplier_created, supplier_critical_risk, vendor_issue_created,
               vendor_issue_sla_breach, questionnaire_overdue
BCP:           bcp_review_overdue, bcp_under_review
Vigilancia normativa (regwatch): regwatch_new_change, regwatch_high_impact
Personalizada: compound (entity_type=supplier|supplier_questionnaire)
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("riskhub.alert_rules")

COOLDOWN_HOURS = 20

# Campos permitidos en reglas compuestas (event_type="compound"), por entidad.
# Lista blanca — previene acceso arbitrario a atributos del modelo.
ENTITY_FIELDS = {
    "risk": {
        "inherent_score", "residual_score", "residual_level",
        "inherent_likelihood", "inherent_impact",
        "residual_likelihood", "residual_impact",
        "treatment_progress", "days_since_review", "owner_id",
    },
    "supplier": {
        "score", "inherent_risk_score", "residual_risk_score", "control_effectiveness",
        "business_criticality", "geographic_risk", "data_sensitivity", "data_volume",
        "annual_spend", "nth_party_depth",
    },
    "supplier_questionnaire": {"score", "major_nc", "minor_nc"},
}


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _cooldown_ok(rule, now: datetime) -> bool:
    """True si ya paso el periodo de enfriamiento desde el ultimo envio (o nunca se envio)."""
    if not rule.last_triggered_at:
        return True
    last = rule.last_triggered_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    hours = (now - last).total_seconds() / 3600
    return hours >= COOLDOWN_HOURS


def _cutoff(rule) -> datetime:
    """Marca de tiempo desde la que se consideran 'nuevos' los registros (reglas delta).

    Usa el ultimo envio si existe; si la regla nunca se disparo, usa su fecha de
    creacion (evita volcar todo el historico la primera vez que se activa).
    """
    ts = rule.last_triggered_at or rule.created_at
    if ts and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts or datetime.now(timezone.utc)


def _digest_html(title: str, org: str, intro: str, header_bg: str,
                  cols: list, rows: list) -> str:
    """Plantilla HTML generica para digests tabulares (proveedores, BCP, vigilancia, etc.)."""
    thead = "".join(f"<th style='padding:7px 12px;text-align:left;'>{_esc(c)}</th>" for c in cols)
    tbody = "".join(
        "<tr>" + "".join(f"<td style='padding:7px 12px;'>{cell}</td>" for cell in row) + "</tr>"
        for row in rows[:15]
    )
    return f"""<!DOCTYPE html>
<html lang='es'><body style='margin:0;padding:24px;background:#F5F5F5;font-family:Arial,sans-serif;'>
  <div style='max-width:640px;margin:0 auto;background:#fff;border-radius:10px;border:1px solid #E9E9E9;overflow:hidden;'>
    <div style='background:linear-gradient(90deg,#59008D,#D65200);padding:20px 28px;'>
      <h1 style='color:#fff;margin:0;font-size:18px;'>RiskHub &mdash; {_esc(title)}</h1>
      <p style='color:rgba(255,255,255,.75);margin:4px 0 0;font-size:13px;'>{_esc(org)}</p>
    </div>
    <div style='padding:24px;'>
      <p style='font-size:13px;color:#262626;'>{intro}</p>
      <table style='width:100%;border-collapse:collapse;font-size:12px;'>
        <thead><tr style='background:{header_bg};'>{thead}</tr></thead>
        <tbody>{tbody}</tbody>
      </table>
      <p style='color:#9D9D9D;font-size:11px;margin-top:16px;'>Generado automaticamente por RiskHub.</p>
    </div>
  </div>
</body></html>"""


def _eval_condition(attr, op: str, val) -> bool:
    if attr is None or val is None:
        return False
    try:
        attr_f = float(attr)
        val_f = float(val)
        if op == "gte":
            return attr_f >= val_f
        if op == "lte":
            return attr_f <= val_f
        if op == "gt":
            return attr_f > val_f
        if op == "lt":
            return attr_f < val_f
        if op == "eq":
            return attr_f == val_f
        return str(attr) == str(val)
    except (TypeError, ValueError):
        return str(attr) == str(val)


def _matches_conditions(obj, conditions: list, logic: str, allowed_fields: set) -> bool:
    results = []
    for cond in conditions or []:
        field = cond.get("field", "")
        op = cond.get("op", "gte")
        val = cond.get("value")
        if field not in allowed_fields:
            logger.warning("Regla compuesta: campo no permitido '%s' — ignorado", field)
            results.append(False)
            continue
        results.append(_eval_condition(getattr(obj, field, None), op, val))
    if not results:
        return False
    return any(results) if (logic or "AND").upper() == "OR" else all(results)


def evaluate_rule(db: Session, rule, cfg, org: str, now: datetime) -> tuple:
    """Evalua una regla individual y despacha las alertas correspondientes.

    Devuelve (alertas_enviadas: int, errores: list[str]). Puede modificar
    rule.last_triggered_at in-place; el caller es responsable del commit.
    """
    from app.services import email_service, notification_channels

    sent = 0
    errors: list = []

    def dispatch(subject, body_txt, html_body, event, fields=None):
        nonlocal sent
        result = notification_channels.dispatch_alert(
            db, cfg, org, rule.recipient_email, subject, body_txt,
            html_body=html_body, event=event, fields=fields or {},
        )
        if any(v for v in result.values()):
            sent += 1
        else:
            errors.append(f"{rule.event_type}: fallo al enviar alerta (ningun canal disponible)")
        return result

    et = rule.event_type

    if et in ("risk_critical", "risk_high", "treatment_overdue", "risk_no_treatment", "treatment_due_soon"):
        _eval_risk_simple(db, rule, org, now, dispatch)
    elif et == "compound":
        _eval_compound(db, rule, org, now, dispatch)
    elif et == "daily_digest":
        _eval_daily_digest(db, rule, org, now, dispatch)
    elif et == "control_review_overdue":
        _eval_control_review_overdue(db, rule, org, now, dispatch)
    elif et == "incident_p1p2":
        _eval_incident_p1p2(db, rule, org, now, dispatch)
    elif et == "nis2_pending":
        _eval_nis2_pending(db, rule, org, now, dispatch)
    elif et == "policy_review_overdue":
        _eval_policy_review_overdue(db, rule, org, now, dispatch)
    elif et == "task_overdue":
        _eval_task_overdue(db, rule, org, now, dispatch)
    elif et == "supplier_created":
        _eval_supplier_created(db, rule, org, now, dispatch)
    elif et == "supplier_critical_risk":
        _eval_supplier_critical_risk(db, rule, org, now, dispatch)
    elif et == "vendor_issue_created":
        _eval_vendor_issue_created(db, rule, org, now, dispatch)
    elif et == "vendor_issue_sla_breach":
        _eval_vendor_issue_sla_breach(db, rule, org, now, dispatch)
    elif et == "questionnaire_overdue":
        _eval_questionnaire_overdue(db, rule, org, now, dispatch)
    elif et == "bcp_review_overdue":
        _eval_bcp_review_overdue(db, rule, org, now, dispatch)
    elif et == "bcp_under_review":
        _eval_bcp_under_review(db, rule, org, now, dispatch)
    elif et == "regwatch_new_change":
        _eval_regwatch_new_change(db, rule, org, now, dispatch)
    elif et == "regwatch_high_impact":
        _eval_regwatch_high_impact(db, rule, org, now, dispatch)

    return sent, errors


# ---------- Riesgos ----------

def _eval_risk_simple(db, rule, org, now, dispatch):
    from app.models import Risk, RiskStatus
    from app.services import email_service

    risks = db.query(Risk).filter(Risk.organization_id == rule.organization_id).all()
    matching = []
    if rule.event_type in ("risk_critical", "risk_high"):
        matching = [r for r in risks if r.residual_level >= rule.threshold_level
                    and r.status not in (RiskStatus.ACCEPTED, RiskStatus.CLOSED)]
    elif rule.event_type == "treatment_overdue":
        matching = [r for r in risks
                    if r.treatment_due_date and r.treatment_due_date.replace(tzinfo=timezone.utc) < now
                    and r.status not in (RiskStatus.TREATED, RiskStatus.ACCEPTED, RiskStatus.CLOSED)]
    elif rule.event_type == "risk_no_treatment":
        matching = [r for r in risks
                    if r.residual_level >= rule.threshold_level and not r.treatment_option
                    and r.status not in (RiskStatus.ACCEPTED, RiskStatus.CLOSED)]
    elif rule.event_type == "treatment_due_soon":
        in_n = timedelta(days=rule.threshold_level if rule.threshold_level > 0 else 7)
        matching = [r for r in risks
                    if r.treatment_due_date
                    and timedelta(0) <= r.treatment_due_date.replace(tzinfo=timezone.utc) - now <= in_n
                    and r.status not in (RiskStatus.TREATED, RiskStatus.ACCEPTED, RiskStatus.CLOSED)]

    reason_map = {
        "risk_critical": "supera el umbral critico",
        "risk_high": "supera el umbral alto configurado",
        "treatment_overdue": "tiene el plan de tratamiento vencido",
        "risk_no_treatment": "no tiene plan de tratamiento definido",
        "treatment_due_soon": "tiene el plan de tratamiento proximo a vencer",
    }
    for risk in matching:
        reason = reason_map.get(rule.event_type, "")
        body_txt = f"El riesgo {risk.code} {reason}."
        dispatch(
            f"RiskHub — Alerta: {risk.code} ({org})", body_txt,
            email_service.risk_alert_html(risk, org, body_txt),
            f"risk.{rule.event_type}",
            {"risk_code": risk.code, "residual_level": risk.residual_level},
        )
    if matching:
        rule.last_triggered_at = now


def _eval_compound(db, rule, org, now, dispatch):
    """Reglas compuestas (conditions + logic). entity_type=None/'risk' preserva el
    comportamiento legacy (un email por riesgo, cada evaluacion). Otras entidades
    usan formato digest con enfriamiento de 20h."""
    entity = (rule.entity_type or "risk").lower()
    allowed = ENTITY_FIELDS.get(entity)
    if not allowed or not rule.conditions:
        return

    if entity == "risk":
        from app.models import Risk, RiskStatus
        from app.services import email_service
        risks = db.query(Risk).filter(Risk.organization_id == rule.organization_id).all()
        matching = [
            r for r in risks
            if r.status not in (RiskStatus.ACCEPTED, RiskStatus.CLOSED)
            and _matches_conditions(r, rule.conditions, rule.logic, allowed)
        ]
        for risk in matching:
            body_txt = f"El riesgo {risk.code} cumple las condiciones configuradas."
            dispatch(
                f"RiskHub — Alerta: {risk.code} ({org})", body_txt,
                email_service.risk_alert_html(risk, org, body_txt),
                "risk.compound", {"risk_code": risk.code, "residual_level": risk.residual_level},
            )
        if matching:
            rule.last_triggered_at = now
        return

    if not _cooldown_ok(rule, now):
        return

    if entity == "supplier":
        from app.models import Supplier
        items = db.query(Supplier).filter(Supplier.organization_id == rule.organization_id).all()
        matching = [s for s in items if _matches_conditions(s, rule.conditions, rule.logic, allowed)]
        if matching:
            rows = [[_esc(s.code), _esc(s.name), str(s.residual_risk_score or "-")] for s in matching]
            html = _digest_html(
                "Proveedores — condicion personalizada cumplida", org,
                f"<strong>{len(matching)}</strong> proveedor(es) cumplen la condicion configurada en la regla \"{_esc(rule.name)}\".",
                "#EDD1FF", ["Codigo", "Nombre", "Score residual"], rows,
            )
            dispatch(
                f"RiskHub — {len(matching)} proveedor(es) cumplen condicion personalizada ({org})",
                f"{len(matching)} proveedor(es) cumplen la condicion configurada.",
                html, "supplier.compound", {"count": len(matching)},
            )
            rule.last_triggered_at = now

    elif entity == "supplier_questionnaire":
        from app.models import SupplierQuestionnaire
        items = db.query(SupplierQuestionnaire).filter(
            SupplierQuestionnaire.organization_id == rule.organization_id
        ).all()
        matching = [q for q in items if _matches_conditions(q, rule.conditions, rule.logic, allowed)]
        if matching:
            rows = [[_esc(q.code), _esc(q.supplier_name), str(q.score or "-")] for q in matching]
            html = _digest_html(
                "Cuestionarios — condicion personalizada cumplida", org,
                f"<strong>{len(matching)}</strong> cuestionario(s) cumplen la condicion configurada en la regla \"{_esc(rule.name)}\".",
                "#EDD1FF", ["Codigo", "Proveedor", "Score"], rows,
            )
            dispatch(
                f"RiskHub — {len(matching)} cuestionario(s) cumplen condicion personalizada ({org})",
                f"{len(matching)} cuestionario(s) cumplen la condicion configurada.",
                html, "supplier_questionnaire.compound", {"count": len(matching)},
            )
            rule.last_triggered_at = now


def _eval_daily_digest(db, rule, org, now, dispatch):
    from app.models import Risk, RiskStatus
    if not _cooldown_ok(rule, now):
        return
    risks = db.query(Risk).filter(Risk.organization_id == rule.organization_id).all()
    active_risks = [r for r in risks if r.status not in (RiskStatus.CLOSED,)]
    overdue_list = [
        {"code": r.code, "asset": r.asset.name if r.asset else "-",
         "due": r.treatment_due_date.strftime("%d/%m/%Y") if r.treatment_due_date else "-"}
        for r in active_risks
        if r.treatment_due_date and r.treatment_due_date.replace(tzinfo=timezone.utc) < now
        and r.status not in (RiskStatus.TREATED, RiskStatus.ACCEPTED, RiskStatus.CLOSED)
    ]
    in7 = now + timedelta(days=7)
    upcoming_list = [
        {"code": r.code, "asset": r.asset.name if r.asset else "-",
         "due": r.treatment_due_date.strftime("%d/%m/%Y") if r.treatment_due_date else "-",
         "days": (r.treatment_due_date.replace(tzinfo=timezone.utc) - now).days}
        for r in active_risks
        if r.treatment_due_date and now <= r.treatment_due_date.replace(tzinfo=timezone.utc) <= in7
        and r.status not in (RiskStatus.TREATED, RiskStatus.ACCEPTED, RiskStatus.CLOSED)
    ]
    stats = {
        "total": len(active_risks),
        "high": sum(1 for r in active_risks if r.residual_level >= 5),
        "medium": sum(1 for r in active_risks if 3 <= r.residual_level < 5),
        "low": sum(1 for r in active_risks if r.residual_level < 3),
    }
    from app.services.scheduler import _daily_digest_html
    html = _daily_digest_html(org, stats, overdue_list, upcoming_list)
    summary = (f"{stats['total']} riesgo(s) activos — {stats['high']} alto(s), "
               f"{len(overdue_list)} vencido(s), {len(upcoming_list)} proximo(s) a vencer.")
    result = dispatch(f"RiskHub — Resumen diario de riesgos ({org})", summary, html,
                       "risk.daily_digest", stats)
    if any(result.values()):
        rule.last_triggered_at = now


def _eval_control_review_overdue(db, rule, org, now, dispatch):
    from app.models import ControlImplementation
    if not _cooldown_ok(rule, now):
        return
    impls = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == rule.organization_id
    ).all()
    overdue = [i for i in impls if i.next_review and i.next_review.replace(tzinfo=timezone.utc) < now]
    if not overdue:
        return
    rows = [[_esc(i.name), i.next_review.strftime("%d/%m/%Y")] for i in overdue]
    html = _digest_html(
        "Revisiones de controles vencidas", org,
        f"<strong>{len(overdue)}</strong> control(es) tienen la fecha de revision vencida.",
        "#EDD1FF", ["Control", "Fecha programada"], rows,
    )
    result = dispatch(f"RiskHub — {len(overdue)} revisiones de controles vencidas ({org})",
                       f"{len(overdue)} control(es) tienen la fecha de revision vencida.",
                       html, "control.review_overdue", {"count": len(overdue)})
    if any(result.values()):
        rule.last_triggered_at = now


def _eval_incident_p1p2(db, rule, org, now, dispatch):
    from app.models import Incident, IncidentStatus, IncidentSeverity
    if not _cooldown_ok(rule, now):
        return
    open_p1p2 = db.query(Incident).filter(
        Incident.organization_id == rule.organization_id,
        Incident.status != IncidentStatus.CLOSED,
        Incident.severity.in_([IncidentSeverity.P1, IncidentSeverity.P2]),
    ).all()
    if not open_p1p2:
        return
    rows = [[_esc(i.code), _esc(i.title[:60]),
             f"<strong style='color:#a83232;'>{_esc(i.severity.value.upper())}</strong>"] for i in open_p1p2]
    html = _digest_html(
        "Incidentes P1/P2 abiertos", org,
        f"<strong>{len(open_p1p2)}</strong> incidente(s) P1/P2 permanecen abiertos.",
        "#FEE2E2", ["Codigo", "Titulo", "Severidad"], rows,
    )
    result = dispatch(f"RiskHub — {len(open_p1p2)} incidente(s) P1/P2 abierto(s) ({org})",
                       f"{len(open_p1p2)} incidente(s) P1/P2 permanecen abiertos.",
                       html, "incident.p1p2_open", {"count": len(open_p1p2)})
    if any(result.values()):
        rule.last_triggered_at = now


def _eval_nis2_pending(db, rule, org, now, dispatch):
    from app.models import Incident, IncidentStatus
    if not _cooldown_ok(rule, now):
        return
    pending = db.query(Incident).filter(
        Incident.organization_id == rule.organization_id,
        Incident.status != IncidentStatus.CLOSED,
        Incident.nis2_notification_required.is_(True),
        Incident.nis2_notification_sent_at.is_(None),
    ).all()
    if not pending:
        return
    rows = [[_esc(i.code), _esc(i.title[:60])] for i in pending]
    html = _digest_html(
        "Notificaciones NIS2 pendientes", org,
        f"<strong style='color:#a83232;'>ATENCION:</strong> {len(pending)} incidente(s) requieren "
        f"notificacion NIS2 al supervisor nacional (Art. 23, plazo 24h).",
        "#FEE2E2", ["Codigo", "Incidente"], rows,
    )
    result = dispatch(f"RiskHub [URGENTE] — {len(pending)} notificacion(es) NIS2 pendiente(s) ({org})",
                       f"ATENCION: {len(pending)} incidente(s) requieren notificacion NIS2 (24h).",
                       html, "incident.nis2_pending", {"count": len(pending)})
    if any(result.values()):
        rule.last_triggered_at = now


def _eval_policy_review_overdue(db, rule, org, now, dispatch):
    from app.models import Policy, PolicyStatus
    if not _cooldown_ok(rule, now):
        return
    overdue = [
        p for p in db.query(Policy).filter(Policy.organization_id == rule.organization_id).all()
        if p.review_date and p.status != PolicyStatus.OBSOLETE
        and p.review_date.replace(tzinfo=timezone.utc) < now
    ]
    if not overdue:
        return
    rows = [[_esc(p.code), _esc(p.title[:60]), p.review_date.strftime("%d/%m/%Y")] for p in overdue]
    html = _digest_html(
        "Politicas con revision vencida", org,
        f"<strong>{len(overdue)}</strong> politica(s) tienen la fecha de revision vencida.",
        "#FEF9C3", ["Codigo", "Titulo", "Fecha revision"], rows,
    )
    result = dispatch(f"RiskHub — {len(overdue)} politica(s) con revision vencida ({org})",
                       f"{len(overdue)} politica(s) tienen la fecha de revision vencida.",
                       html, "policy.review_overdue", {"count": len(overdue)})
    if any(result.values()):
        rule.last_triggered_at = now


def _eval_task_overdue(db, rule, org, now, dispatch):
    from app.models import TreatmentTask, TaskStatus
    if not _cooldown_ok(rule, now):
        return
    overdue = [
        t for t in db.query(TreatmentTask).filter(TreatmentTask.organization_id == rule.organization_id).all()
        if t.due_date and t.status != TaskStatus.DONE and t.due_date.replace(tzinfo=timezone.utc) < now
    ]
    if not overdue:
        return
    rows = [[_esc(t.code), _esc(t.title[:60]), t.due_date.strftime("%d/%m/%Y")] for t in overdue]
    html = _digest_html(
        "Tareas de tratamiento vencidas", org,
        f"<strong>{len(overdue)}</strong> tarea(s) de tratamiento tienen la fecha limite vencida.",
        "#FFF7ED", ["Codigo", "Titulo", "Fecha limite"], rows,
    )
    result = dispatch(f"RiskHub — {len(overdue)} tarea(s) vencida(s) ({org})",
                       f"{len(overdue)} tarea(s) de tratamiento tienen la fecha limite vencida.",
                       html, "task.overdue", {"count": len(overdue)})
    if any(result.values()):
        rule.last_triggered_at = now


# ---------- Proveedores / TPRM ----------

def _eval_supplier_created(db, rule, org, now, dispatch):
    from app.models import Supplier
    cutoff = _cutoff(rule)
    new_suppliers = db.query(Supplier).filter(
        Supplier.organization_id == rule.organization_id,
        Supplier.created_at > cutoff,
    ).all()
    if not new_suppliers:
        return
    rows = [[_esc(s.code), _esc(s.name), _esc(s.tier.value if s.tier else "-")] for s in new_suppliers]
    html = _digest_html(
        "Nuevos proveedores dados de alta", org,
        f"<strong>{len(new_suppliers)}</strong> proveedor(es) nuevo(s) desde la ultima revision.",
        "#D1FAE5", ["Codigo", "Nombre", "Tier"], rows,
    )
    result = dispatch(f"RiskHub — {len(new_suppliers)} proveedor(es) nuevo(s) ({org})",
                       f"{len(new_suppliers)} proveedor(es) nuevo(s) dado(s) de alta.",
                       html, "supplier.created", {"count": len(new_suppliers)})
    if any(result.values()):
        rule.last_triggered_at = now


def _eval_supplier_critical_risk(db, rule, org, now, dispatch):
    from app.models import Supplier
    if not _cooldown_ok(rule, now):
        return
    threshold = rule.threshold_level or 70
    critical = db.query(Supplier).filter(
        Supplier.organization_id == rule.organization_id,
        Supplier.residual_risk_score.isnot(None),
        Supplier.residual_risk_score >= threshold,
    ).all()
    if not critical:
        return
    rows = [[_esc(s.code), _esc(s.name), str(s.residual_risk_score)] for s in critical]
    html = _digest_html(
        "Proveedores con riesgo residual critico", org,
        f"<strong>{len(critical)}</strong> proveedor(es) con score de riesgo residual >= {threshold}.",
        "#FEE2E2", ["Codigo", "Nombre", "Score residual"], rows,
    )
    result = dispatch(f"RiskHub — {len(critical)} proveedor(es) con riesgo critico ({org})",
                       f"{len(critical)} proveedor(es) superan el umbral de riesgo residual ({threshold}).",
                       html, "supplier.critical_risk", {"count": len(critical)})
    if any(result.values()):
        rule.last_triggered_at = now


def _eval_vendor_issue_created(db, rule, org, now, dispatch):
    from app.models import VendorIssue
    cutoff = _cutoff(rule)
    new_issues = db.query(VendorIssue).filter(
        VendorIssue.organization_id == rule.organization_id,
        VendorIssue.created_at > cutoff,
    ).all()
    if not new_issues:
        return
    rows = [[_esc(i.code), _esc(i.supplier_name), _esc(i.title[:50]),
             _esc(i.severity.value.upper())] for i in new_issues]
    html = _digest_html(
        "Nuevos hallazgos de proveedor", org,
        f"<strong>{len(new_issues)}</strong> hallazgo(s) nuevo(s) de proveedor desde la ultima revision.",
        "#FEF0E3", ["Codigo", "Proveedor", "Titulo", "Severidad"], rows,
    )
    result = dispatch(f"RiskHub — {len(new_issues)} hallazgo(s) de proveedor nuevo(s) ({org})",
                       f"{len(new_issues)} hallazgo(s) nuevo(s) registrado(s) sobre proveedores.",
                       html, "vendor_issue.created", {"count": len(new_issues)})
    if any(result.values()):
        rule.last_triggered_at = now


def _eval_vendor_issue_sla_breach(db, rule, org, now, dispatch):
    from app.models import VendorIssue, VendorIssueStatus
    if not _cooldown_ok(rule, now):
        return
    open_statuses = (VendorIssueStatus.OPEN, VendorIssueStatus.ACKNOWLEDGED, VendorIssueStatus.IN_REMEDIATION)
    breached = db.query(VendorIssue).filter(
        VendorIssue.organization_id == rule.organization_id,
        VendorIssue.status.in_(open_statuses),
        VendorIssue.due_date.isnot(None),
        VendorIssue.due_date < now,
    ).all()
    if not breached:
        return
    rows = [[_esc(i.code), _esc(i.supplier_name), _esc(i.title[:50]),
             i.due_date.strftime("%d/%m/%Y")] for i in breached]
    html = _digest_html(
        "Hallazgos de proveedor con SLA vencido", org,
        f"<strong>{len(breached)}</strong> hallazgo(s) de proveedor superan el plazo de resolucion (SLA).",
        "#FEE2E2", ["Codigo", "Proveedor", "Titulo", "Vencio el"], rows,
    )
    result = dispatch(f"RiskHub — {len(breached)} hallazgo(s) con SLA vencido ({org})",
                       f"{len(breached)} hallazgo(s) de proveedor superan el plazo de resolucion.",
                       html, "vendor_issue.sla_breach", {"count": len(breached)})
    if any(result.values()):
        rule.last_triggered_at = now


def _eval_questionnaire_overdue(db, rule, org, now, dispatch):
    from app.models import SupplierQuestionnaire
    if not _cooldown_ok(rule, now):
        return
    overdue = db.query(SupplierQuestionnaire).filter(
        SupplierQuestionnaire.organization_id == rule.organization_id,
        SupplierQuestionnaire.submitted_at.is_(None),
        SupplierQuestionnaire.expires_at.isnot(None),
        SupplierQuestionnaire.expires_at < now,
    ).all()
    if not overdue:
        return
    rows = [[_esc(q.code), _esc(q.supplier_name), _esc(q.title[:50]),
             q.expires_at.strftime("%d/%m/%Y")] for q in overdue]
    html = _digest_html(
        "Cuestionarios de proveedor vencidos", org,
        f"<strong>{len(overdue)}</strong> cuestionario(s) de proveedor sin responder, con plazo vencido.",
        "#FEF9C3", ["Codigo", "Proveedor", "Titulo", "Vencio el"], rows,
    )
    result = dispatch(f"RiskHub — {len(overdue)} cuestionario(s) vencido(s) ({org})",
                       f"{len(overdue)} cuestionario(s) de proveedor sin responder, con plazo vencido.",
                       html, "supplier_questionnaire.overdue", {"count": len(overdue)})
    if any(result.values()):
        rule.last_triggered_at = now


# ---------- BCP / ISO 22301 ----------

def _eval_bcp_review_overdue(db, rule, org, now, dispatch):
    from app.models import BCPPlan
    if not _cooldown_ok(rule, now):
        return
    overdue = db.query(BCPPlan).filter(
        BCPPlan.organization_id == rule.organization_id,
        BCPPlan.status != "deprecated",
        BCPPlan.review_date.isnot(None),
        BCPPlan.review_date < now,
    ).all()
    if not overdue:
        return
    rows = [[_esc(p.code or "-"), _esc(p.name), p.review_date.strftime("%d/%m/%Y")] for p in overdue]
    html = _digest_html(
        "Planes BCP/DRP con revision vencida", org,
        f"<strong>{len(overdue)}</strong> plan(es) de continuidad tienen la fecha de revision vencida.",
        "#FEF9C3", ["Codigo", "Nombre", "Fecha revision"], rows,
    )
    result = dispatch(f"RiskHub — {len(overdue)} plan(es) BCP con revision vencida ({org})",
                       f"{len(overdue)} plan(es) de continuidad tienen la fecha de revision vencida.",
                       html, "bcp.review_overdue", {"count": len(overdue)})
    if any(result.values()):
        rule.last_triggered_at = now


def _eval_bcp_under_review(db, rule, org, now, dispatch):
    from app.models import BCPPlan
    if not _cooldown_ok(rule, now):
        return
    plans = db.query(BCPPlan).filter(
        BCPPlan.organization_id == rule.organization_id,
        BCPPlan.status == "under_review",
    ).all()
    if not plans:
        return
    rows = [[_esc(p.code or "-"), _esc(p.name), _esc(p.plan_type or "-")] for p in plans]
    html = _digest_html(
        "Planes BCP/DRP en revision", org,
        f"<strong>{len(plans)}</strong> plan(es) de continuidad estan actualmente en revision "
        f"(posiblemente por un cambio normativo detectado).",
        "#FEF0E3", ["Codigo", "Nombre", "Tipo"], rows,
    )
    result = dispatch(f"RiskHub — {len(plans)} plan(es) BCP en revision ({org})",
                       f"{len(plans)} plan(es) de continuidad estan en revision.",
                       html, "bcp.under_review", {"count": len(plans)})
    if any(result.values()):
        rule.last_triggered_at = now


# ---------- Vigilancia normativa (Regwatch) ----------

def _eval_regwatch_new_change(db, rule, org, now, dispatch):
    from app.models import TenantChangeInboxItem, InboxItemStatus
    cutoff = _cutoff(rule)
    new_items = db.query(TenantChangeInboxItem).filter(
        TenantChangeInboxItem.organization_id == rule.organization_id,
        TenantChangeInboxItem.created_at > cutoff,
    ).all()
    if not new_items:
        return
    rows = []
    for item in new_items:
        pack = item.change_pack
        rows.append([
            _esc(pack.framework_code if pack else "-"),
            _esc((pack.title_es or "-")[:60] if pack else "-"),
            _esc(pack.severity.value if pack and pack.severity else "-"),
        ])
    html = _digest_html(
        "Nuevos cambios normativos detectados", org,
        f"<strong>{len(new_items)}</strong> cambio(s) normativo(s) nuevo(s) requieren revision en el inbox de vigilancia normativa.",
        "#D1FAE5", ["Norma", "Cambio", "Severidad"], rows,
    )
    result = dispatch(f"RiskHub — {len(new_items)} cambio(s) normativo(s) nuevo(s) ({org})",
                       f"{len(new_items)} cambio(s) normativo(s) nuevo(s) detectado(s), pendientes de revision.",
                       html, "regwatch.new_change", {"count": len(new_items)})
    if any(result.values()):
        rule.last_triggered_at = now


def _eval_regwatch_high_impact(db, rule, org, now, dispatch):
    from app.models import TenantChangeInboxItem, InboxItemStatus, ChangeSeverity
    if not _cooldown_ok(rule, now):
        return
    pending = db.query(TenantChangeInboxItem).filter(
        TenantChangeInboxItem.organization_id == rule.organization_id,
        TenantChangeInboxItem.status == InboxItemStatus.PENDING,
    ).all()
    high_impact = [
        item for item in pending
        if item.change_pack and item.change_pack.severity in (ChangeSeverity.SUBSTANTIVE, ChangeSeverity.BREAKING)
    ]
    if not high_impact:
        return
    rows = [[
        _esc(item.change_pack.framework_code),
        _esc((item.change_pack.title_es or "-")[:60]),
        _esc(item.change_pack.severity.value),
    ] for item in high_impact]
    html = _digest_html(
        "Cambios normativos de alto impacto pendientes", org,
        f"<strong>{len(high_impact)}</strong> cambio(s) normativo(s) de impacto sustancial o mayor siguen pendientes de revision.",
        "#FEE2E2", ["Norma", "Cambio", "Severidad"], rows,
    )
    result = dispatch(f"RiskHub — {len(high_impact)} cambio(s) normativo(s) de alto impacto pendiente(s) ({org})",
                       f"{len(high_impact)} cambio(s) normativo(s) de alto impacto siguen sin revisar.",
                       html, "regwatch.high_impact_pending", {"count": len(high_impact)})
    if any(result.values()):
        rule.last_triggered_at = now


# ---------- Runners ----------

def evaluate_rules_for_org(db: Session, org_id: int) -> dict:
    """Evalua todas las reglas activas de una organizacion. Usado por el
    endpoint manual POST /api/alerts/check-rules. Hace commit al final."""
    from app.models import AlertRule, EmailSettings, RiskContext
    from app.services import notification_channels

    cfg = db.query(EmailSettings).filter_by(organization_id=org_id).first()
    ctx = db.query(RiskContext).filter_by(organization_id=org_id).first()
    org = ctx.organization_name if ctx else "Organizacion"

    rules = db.query(AlertRule).filter(
        AlertRule.organization_id == org_id, AlertRule.is_active.is_(True)
    ).all()
    now = datetime.now(timezone.utc)
    sent = 0
    errors: list = []
    if notification_channels.has_any_channel(cfg):
        for rule in rules:
            rule_sent, rule_errors = evaluate_rule(db, rule, cfg, org, now)
            sent += rule_sent
            errors.extend(rule_errors)
    db.commit()
    return {"sent": sent, "rules_evaluated": len(rules), "errors": errors}


def run_all_orgs() -> None:
    """Evaluacion periodica de reglas de alerta activas, para todas las organizaciones.
    Usado por el scheduler (cada hora)."""
    from app.database import SessionLocal
    from app.models import AlertRule, EmailSettings, RiskContext
    from app.services import notification_channels

    db = SessionLocal()
    try:
        rules = db.query(AlertRule).filter(AlertRule.is_active.is_(True)).all()
        if not rules:
            return

        rule_org_ids = list({r.organization_id for r in rules if r.organization_id})
        cfg_by_org: dict = {}
        ctx_by_org: dict = {}
        for org_id in rule_org_ids:
            cfg_by_org[org_id] = db.query(EmailSettings).filter_by(organization_id=org_id).first()
            ctx_obj = db.query(RiskContext).filter_by(organization_id=org_id).first()
            ctx_by_org[org_id] = ctx_obj.organization_name if ctx_obj else "Organizacion"

        now = datetime.now(timezone.utc)
        total_sent = 0
        for rule in rules:
            cfg = cfg_by_org.get(rule.organization_id)
            org = ctx_by_org.get(rule.organization_id, "Organizacion")
            if not notification_channels.has_any_channel(cfg):
                continue
            rule_sent, rule_errors = evaluate_rule(db, rule, cfg, org, now)
            total_sent += rule_sent
            for err in rule_errors:
                logger.warning("Regla '%s' (org %s): %s", rule.name, rule.organization_id, err)

        db.commit()
        if total_sent:
            logger.info("Evaluacion periodica: %d alertas enviadas (%d reglas).", total_sent, len(rules))
    except Exception as exc:
        logger.exception("Error en evaluacion periodica de reglas: %s", exc)
    finally:
        db.close()
