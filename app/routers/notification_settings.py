"""Control total de las notificaciones automaticas por organizacion.

Expone el catalogo de alertas (notification_registry) fusionado con la
configuracion de la org (NotificationSetting), y permite editar cada una:
on/off, destinatarios, canal, cooldown y umbral. Es el backend del panel
Configuracion -> Alertas.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EmailSettings, NotificationSetting, UserRole
from app.security import filter_by_org, get_current_user
from app.services import notification_registry as reg
from app.services import notification_settings as ns
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/notification-settings", tags=["notification-settings"])

_VALID_CHANNELS = {"email", "teams", "power_automate", "all"}
_VALID_RECIPIENT_MODES = {"admins", "custom"}


# ---------- Schemas ----------

class NotificationSettingIn(BaseModel):
    enabled: Optional[bool] = None
    recipient_mode: Optional[str] = None          # admins | custom
    recipients: Optional[List[EmailStr]] = None    # cuando recipient_mode == custom
    channel: Optional[str] = None                  # email | teams | power_automate | all
    cooldown_days: Optional[int] = Field(default=None, ge=0, le=365)
    threshold: Optional[float] = None


class NotificationSettingOut(BaseModel):
    key: str
    label: str
    category: str
    description: str
    frequency_human: str
    audience: str
    supports_threshold: bool
    threshold_label: Optional[str] = None
    # valores efectivos (config de la org o default del catalogo)
    enabled: bool
    channel: str
    recipient_mode: str
    recipients: List[str]
    cooldown_days: int
    threshold: Optional[float] = None
    last_sent_at: Optional[datetime] = None
    configured: bool          # existe fila propia (no es solo el default)


class NotificationCatalogOut(BaseModel):
    settings: List[NotificationSettingOut]
    admin_emails: List[str]         # destinatarios por defecto (modo admins)
    email_channel_ready: bool       # hay SMTP configurado
    teams_channel_ready: bool
    power_automate_channel_ready: bool


def _require_admin(current_user):
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, "Solo administradores pueden configurar las alertas")


def _effective(entry: dict, s: Optional[NotificationSetting], admin_emails: List[str]) -> NotificationSettingOut:
    enabled = bool(s.enabled) if s is not None else bool(entry.get("default_enabled", True))
    channel = (s.channel if s is not None else None) or "email"
    recipient_mode = (s.recipient_mode if s is not None else None) or "admins"
    if recipient_mode == "custom" and s is not None:
        try:
            recipients = [e for e in json.loads(s.recipients or "[]") if e]
        except Exception:
            recipients = []
    else:
        recipients = admin_emails
    if s is not None and s.cooldown_days is not None:
        cooldown = int(s.cooldown_days)
    else:
        cooldown = int(entry.get("default_cooldown_days", 0))
    if s is not None and s.threshold is not None:
        threshold = float(s.threshold)
    elif entry.get("threshold_default") is not None:
        threshold = float(entry["threshold_default"])
    else:
        threshold = None
    return NotificationSettingOut(
        key=entry["key"], label=entry["label"], category=entry["category"],
        description=entry["description"], frequency_human=entry["frequency_human"],
        audience=entry.get("audience", "org"),
        supports_threshold=bool(entry.get("supports_threshold", False)),
        threshold_label=entry.get("threshold_label"),
        enabled=enabled, channel=channel, recipient_mode=recipient_mode,
        recipients=recipients, cooldown_days=cooldown, threshold=threshold,
        last_sent_at=s.last_sent_at if s is not None else None,
        configured=s is not None,
    )


@router.get("", response_model=NotificationCatalogOut)
def get_catalog(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _require_admin(current_user)
    org_id = current_user.organization_id
    rows = {r.alert_key: r for r in db.query(NotificationSetting).filter(
        NotificationSetting.organization_id == org_id).all()}
    admin_emails = ns._org_admin_emails(db, org_id)

    # El superadmin de plataforma ve tambien las alertas de audiencia 'platform'.
    audiences = {"org"}
    if current_user.role == UserRole.SUPERADMIN:
        audiences.add("platform")

    settings = [
        _effective(entry, rows.get(entry["key"]), admin_emails)
        for entry in reg.ALERT_CATALOG
        if entry.get("audience", "org") in audiences
    ]

    cfg = filter_by_org(db.query(EmailSettings), EmailSettings, current_user).first()
    return NotificationCatalogOut(
        settings=settings,
        admin_emails=admin_emails,
        email_channel_ready=bool(cfg and cfg.smtp_host),
        teams_channel_ready=bool(cfg and getattr(cfg, "teams_webhook_enabled", False)
                                 and getattr(cfg, "teams_webhook_url_encrypted", None)),
        power_automate_channel_ready=bool(cfg and getattr(cfg, "power_automate_webhook_enabled", False)
                                          and getattr(cfg, "power_automate_webhook_url_encrypted", None)),
    )


@router.put("/{alert_key}", response_model=NotificationSettingOut)
def update_setting(alert_key: str, body: NotificationSettingIn,
                   db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _require_admin(current_user)
    entry = reg.get_catalog_entry(alert_key)
    if not entry:
        raise HTTPException(404, f"alert_key desconocido: {alert_key}")
    if entry.get("audience", "org") == "platform" and current_user.role != UserRole.SUPERADMIN:
        raise HTTPException(403, "Esta alerta solo la configura el superadministrador")
    if body.channel is not None and body.channel not in _VALID_CHANNELS:
        raise HTTPException(422, f"channel debe ser uno de: {', '.join(sorted(_VALID_CHANNELS))}")
    if body.recipient_mode is not None and body.recipient_mode not in _VALID_RECIPIENT_MODES:
        raise HTTPException(422, f"recipient_mode debe ser uno de: {', '.join(sorted(_VALID_RECIPIENT_MODES))}")

    org_id = current_user.organization_id
    s = db.query(NotificationSetting).filter(
        NotificationSetting.organization_id == org_id,
        NotificationSetting.alert_key == alert_key).first()
    if s is None:
        s = NotificationSetting(organization_id=org_id, alert_key=alert_key)
        db.add(s)

    if body.enabled is not None:
        s.enabled = body.enabled
    if body.channel is not None:
        s.channel = body.channel
    if body.recipient_mode is not None:
        s.recipient_mode = body.recipient_mode
    if body.recipients is not None:
        s.recipients = json.dumps([str(e) for e in body.recipients])
    if body.cooldown_days is not None:
        s.cooldown_days = body.cooldown_days
    if body.threshold is not None:
        s.threshold = body.threshold

    # Guardarrail: modo custom sin destinatarios = nadie recibe. Lo permitimos
    # (equivale a silenciar) pero no es lo que suele quererse; el front avisa.
    log_action(db, current_user.id, "update", "notification_setting", alert_key,
               {"enabled": s.enabled, "channel": s.channel, "recipient_mode": s.recipient_mode})
    db.commit()
    db.refresh(s)
    admin_emails = ns._org_admin_emails(db, org_id)
    return _effective(entry, s, admin_emails)


@router.post("/silence-all")
def silence_all(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Boton de panico: desactiva TODAS las notificaciones de la org de golpe."""
    _require_admin(current_user)
    org_id = current_user.organization_id
    audiences = {"org"}
    if current_user.role == UserRole.SUPERADMIN:
        audiences.add("platform")
    existing = {r.alert_key: r for r in db.query(NotificationSetting).filter(
        NotificationSetting.organization_id == org_id).all()}
    count = 0
    for entry in reg.ALERT_CATALOG:
        if entry.get("audience", "org") not in audiences:
            continue
        s = existing.get(entry["key"])
        if s is None:
            s = NotificationSetting(organization_id=org_id, alert_key=entry["key"], enabled=False)
            db.add(s)
        else:
            s.enabled = False
        count += 1
    log_action(db, current_user.id, "update", "notification_setting", "*",
               {"action": "silence_all", "count": count})
    db.commit()
    return {"ok": True, "silenced": count}


@router.delete("/{alert_key}", status_code=204)
def reset_setting(alert_key: str, db: Session = Depends(get_db),
                  current_user=Depends(get_current_user)):
    """Vuelve una alerta a los valores por defecto del catalogo (borra la fila)."""
    _require_admin(current_user)
    if not reg.get_catalog_entry(alert_key):
        raise HTTPException(404, f"alert_key desconocido: {alert_key}")
    org_id = current_user.organization_id
    s = db.query(NotificationSetting).filter(
        NotificationSetting.organization_id == org_id,
        NotificationSetting.alert_key == alert_key).first()
    if s is not None:
        db.delete(s)
        log_action(db, current_user.id, "delete", "notification_setting", alert_key, {})
        db.commit()
