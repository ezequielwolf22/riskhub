"""Punto unico de control de las notificaciones automaticas por organizacion.

Todos los jobs del scheduler que envian correo pasan por `send_notification(...)`,
que consulta la fila de `NotificationSetting` (o el default del catalogo) para
decidir: si se envia, a quien, por que canal y respetando el cooldown anti-flood.

Reemplaza las llamadas directas a `email_service.send_email(...)` de los jobs, que
enviaban a todos los admins sin on/off ni control de repeticion.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import NotificationSetting, User, UserRole
from app.services import notification_registry as _reg

logger = logging.getLogger("riskhub.notifications")


# ---------- Lectura de configuracion ----------

def get_setting(db: Session, org_id: int, alert_key: str) -> Optional[NotificationSetting]:
    return (
        db.query(NotificationSetting)
        .filter(NotificationSetting.organization_id == org_id,
                NotificationSetting.alert_key == alert_key)
        .first()
    )


def is_enabled(db: Session, org_id: int, alert_key: str) -> bool:
    s = get_setting(db, org_id, alert_key)
    if s is not None:
        return bool(s.enabled)
    entry = _reg.get_catalog_entry(alert_key)
    return bool(entry.get("default_enabled", True)) if entry else True


def _cooldown_days(s: Optional[NotificationSetting], entry: Optional[dict]) -> int:
    if s is not None and s.cooldown_days is not None:
        return max(0, int(s.cooldown_days))
    return int(entry.get("default_cooldown_days", 0)) if entry else 0


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def should_notify(db: Session, org_id: int, alert_key: str) -> bool:
    """True si la alerta esta activa para la org y no esta en periodo de cooldown."""
    entry = _reg.get_catalog_entry(alert_key)
    s = get_setting(db, org_id, alert_key)
    enabled = bool(s.enabled) if s is not None else (bool(entry.get("default_enabled", True)) if entry else True)
    if not enabled:
        return False
    cd = _cooldown_days(s, entry)
    if cd and s is not None and s.last_sent_at is not None:
        if datetime.now(timezone.utc) - _as_utc(s.last_sent_at) < timedelta(days=cd):
            return False
    return True


def get_threshold(db: Session, org_id: int, alert_key: str, default: float) -> float:
    s = get_setting(db, org_id, alert_key)
    if s is not None and s.threshold is not None:
        return float(s.threshold)
    entry = _reg.get_catalog_entry(alert_key)
    if entry and entry.get("threshold_default") is not None:
        return float(entry["threshold_default"])
    return default


def _org_admin_emails(db: Session, org_id: int) -> list[str]:
    admins = (
        db.query(User)
        .filter(User.organization_id == org_id,
                User.role == UserRole.ADMIN,
                User.is_active == True,  # noqa: E712
                User.email.isnot(None))
        .all()
    )
    return [a.email for a in admins if a.email]


def resolve_recipients(db: Session, org_id: int, alert_key: str,
                       default_recipients: Optional[list[str]] = None) -> list[str]:
    """Destinatarios efectivos: modo 'custom' usa la lista guardada; modo 'admins'
    (default) usa los admins activos de la org, salvo que el job pase su propia lista."""
    s = get_setting(db, org_id, alert_key)
    if s is not None and s.recipient_mode == "custom":
        try:
            emails = json.loads(s.recipients or "[]")
        except Exception:
            emails = []
        return [e for e in emails if e]
    if default_recipients is not None:
        return [e for e in default_recipients if e]
    return _org_admin_emails(db, org_id)


def note_sent(db: Session, org_id: int, alert_key: str) -> None:
    """Registra el ultimo envio efectivo (para el cooldown). Crea la fila si no existe."""
    s = get_setting(db, org_id, alert_key)
    if s is None:
        s = NotificationSetting(organization_id=org_id, alert_key=alert_key)
        db.add(s)
    s.last_sent_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()


# ---------- Envio unificado ----------

def send_notification(
    db: Session,
    org_id: int,
    alert_key: str,
    cfg,                       # EmailSettings de la org
    subject: str,
    html_body: str,
    summary_text: Optional[str] = None,
    org_name: str = "",
    recipients: Optional[list[str]] = None,   # override explicito del job (p.ej. destinatario de un informe)
    event: Optional[str] = None,
    fields: Optional[dict] = None,
) -> bool:
    """Envia una notificacion por los canales configurados respetando on/off, cooldown
    y destinatarios de la org. Devuelve True si se envio por al menos un canal.

    El job NO debe volver a llamar a email_service.send_email: esta funcion es el
    unico camino de salida y actualiza el cooldown al enviar.
    """
    from app.services import email_service
    from app.services.notification_channels import dispatch_alert

    if not should_notify(db, org_id, alert_key):
        return False

    s = get_setting(db, org_id, alert_key)
    channel = (s.channel if s is not None else None) or "email"
    to = resolve_recipients(db, org_id, alert_key, default_recipients=recipients)
    summary = summary_text or subject

    want_email = channel in ("email", "all")
    want_teams = channel in ("teams", "all")
    want_pa = channel in ("power_automate", "all")

    sent_any = False

    if want_email and cfg and getattr(cfg, "smtp_host", None) and to:
        for r in to:
            try:
                email_service.send_email(cfg, r, subject, html_body)
                sent_any = True
            except Exception as exc:
                logger.warning("send_notification[%s] email a %s fallo: %s", alert_key, r, exc)

    if (want_teams or want_pa) and cfg:
        # dispatch_alert envia a Teams/PA una sola vez (recipient_email=None evita
        # duplicar el email, que ya hemos gestionado arriba por destinatario).
        try:
            res = dispatch_alert(
                db, cfg, org_name or "", None, subject, summary,
                html_body=html_body, event=event or f"alert.{alert_key}", fields=fields,
            )
            if res.get("teams") or res.get("power_automate"):
                sent_any = True
        except Exception as exc:
            logger.warning("send_notification[%s] canal webhook fallo: %s", alert_key, exc)

    if sent_any:
        note_sent(db, org_id, alert_key)
    return sent_any
