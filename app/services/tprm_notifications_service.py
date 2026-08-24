"""Notificaciones post-review de proveedores (feedback cliente, punto 11).

Tras una decision de seguridad (aprobado / aprobado con mitigacion / riesgo
aceptado / rechazado) avisa a destinatarios configurables por region: solicitante,
equipo de Finanzas regional y equipo de Legal regional. Reutiliza los canales ya
existentes (email SMTP / Teams / Power Automate) via notification_channels.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import EmailSettings, Supplier, TprmSettings

logger = logging.getLogger(__name__)

# Estados de seguridad que representan una DECISION (disparan la notificacion)
DECISION_STATUSES = {
    "security_approved",
    "security_approved_with_mitigation",
    "risk_accepted",
    "rejected",
}

_DECISION_LABEL_ES = {
    "security_approved": "Aprobado por seguridad",
    "security_approved_with_mitigation": "Aprobado con mitigación requerida",
    "risk_accepted": "Riesgo aceptado",
    "rejected": "Rechazado",
}
_BIZ_LABEL = {
    "not_relevant": "No relevante", "normal": "Normal",
    "important": "Importante", "critical": "Crítico",
}
_SEC_LABEL = {
    "very_low": "Muy bajo", "low": "Bajo", "medium": "Medio",
    "high": "Alto", "critical": "Crítico",
}


def _recipients_for_region(settings: Optional[TprmSettings], region: Optional[str]) -> list[str]:
    """Emails de Finanzas/Legal para la region (fallback a __default__)."""
    if not settings or not settings.review_notify_recipients:
        return []
    cfg = settings.review_notify_recipients
    emails: list[str] = []
    for key in (region, "__default__"):
        if not key:
            continue
        block = cfg.get(key)
        if isinstance(block, dict):
            for role in ("finance", "legal"):
                vals = block.get(role) or []
                if isinstance(vals, str):
                    vals = [vals]
                emails.extend(v for v in vals if v)
        if region and region in cfg:
            break  # region especifica encontrada, no mezclar con default
    # dedupe preservando orden
    seen: dict[str, None] = {}
    for e in emails:
        seen.setdefault(e, None)
    return list(seen.keys())


def build_content(supplier: Supplier, decision: str, mitigations: Optional[str] = None) -> tuple[str, str]:
    """Devuelve (subject, html_body) con el contenido acordado con el cliente."""
    decision_label = _DECISION_LABEL_ES.get(decision, decision)
    subject = f"[RiskHub] Decisión de seguridad — {supplier.name}: {decision_label}"
    owner_name = ""
    try:
        if supplier.owner:
            owner_name = supplier.owner.full_name or supplier.owner.email or ""
    except Exception:
        owner_name = ""
    next_review = supplier.next_assessment_at.strftime("%Y-%m-%d") if supplier.next_assessment_at else "—"
    rows = [
        ("Proveedor", supplier.name),
        ("Importancia de negocio", _BIZ_LABEL.get(supplier.business_importance_level or "", "—")),
        ("Riesgo de seguridad", _SEC_LABEL.get(supplier.security_risk_level or "", "—")),
        ("Decisión de seguridad", decision_label),
        ("Mitigaciones", mitigations or "—"),
        ("Próxima revisión", next_review),
        ("Responsable (Owner)", owner_name or "—"),
    ]
    tr = "".join(
        f"<tr><td style='padding:4px 10px;color:#666;'>{k}</td>"
        f"<td style='padding:4px 10px;font-weight:600;'>{v}</td></tr>"
        for k, v in rows
    )
    html = (
        f"<h2 style='color:#59008D;'>Decisión de seguridad de proveedor</h2>"
        f"<table style='border-collapse:collapse;font-family:sans-serif;font-size:14px;'>{tr}</table>"
    )
    return subject, html


def notify_security_decision(db: Session, supplier: Supplier, decision: str,
                             mitigations: Optional[str] = None,
                             user_id: Optional[int] = None) -> dict:
    """Avisa a los destinatarios configurados. Best-effort, nunca lanza al llamante."""
    org_id = supplier.organization_id
    settings = db.query(TprmSettings).filter(TprmSettings.organization_id == org_id).first()
    if not settings or not settings.review_notify_enabled:
        return {"skipped": "notifications_disabled"}

    # Destinatarios: solicitante (owner o contacto) + finanzas/legal regional
    recipients: list[str] = []
    try:
        if supplier.owner and supplier.owner.email:
            recipients.append(supplier.owner.email)
    except Exception:
        pass
    if supplier.contact_email:
        recipients.append(supplier.contact_email)
    recipients.extend(_recipients_for_region(settings, supplier.operating_region))
    # dedupe
    recipients = list(dict.fromkeys([r for r in recipients if r]))
    if not recipients:
        return {"skipped": "no_recipients"}

    cfg = db.query(EmailSettings).filter_by(organization_id=org_id).first()
    subject, html = build_content(supplier, decision, mitigations)
    summary = f"{supplier.name}: {_DECISION_LABEL_ES.get(decision, decision)}"

    sent = 0
    if cfg and getattr(cfg, "smtp_host", None):
        from app.services import email_service
        for email in recipients:
            try:
                email_service.send_email(cfg, email, subject, html)
                sent += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("post-review notify: fallo email a %s: %s", email, exc)

    # Teams / Power Automate una sola vez (no por destinatario)
    channels = {}
    try:
        from app.services import notification_channels
        org_name = ""
        if supplier.organization_id and getattr(supplier, "organization", None):
            org_name = supplier.organization.name
        channels = notification_channels.dispatch_alert(
            db, cfg, org_name, None, subject, summary,
            html_body=html, event="supplier_security_decision",
            fields={"supplier": supplier.name, "decision": decision,
                    "region": supplier.operating_region or ""},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("post-review notify: fallo canal Teams/PA: %s", exc)

    # Timeline
    try:
        from app.services import supplier_events_service as events
        events.log_event_safe(
            db, supplier, "review_completed",
            f"Notificación de decisión enviada: {_DECISION_LABEL_ES.get(decision, decision)}",
            detail={"recipients": recipients, "channels": channels},
            source="auto", user_id=user_id,
        )
    except Exception:
        pass

    return {"email_sent": sent, "recipients": recipients, "channels": channels}
