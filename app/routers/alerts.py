"""Gestion de alertas por email: configuracion SMTP y reglas de alerta."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import AlertRule, EmailSettings, Risk, UserRole
from app.security import filter_by_org, get_current_user
from app.services import email_service, notification_channels
from app.services.audit_service import log_action
from app.services.webhook_service import validate_webhook_url

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ---------- Schemas ----------

class EmailSettingsIn(BaseModel):
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_use_tls: bool = True


class EmailSettingsOut(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_from: str
    smtp_use_tls: bool
    # password no se expone


class AlertChannelIn(BaseModel):
    webhook_url: Optional[str] = None   # si se envia, reemplaza la URL guardada
    enabled: bool = True


class AlertChannelStatusOut(BaseModel):
    configured: bool
    enabled: bool
    host_hint: Optional[str] = None   # solo el hostname, nunca la URL completa (contiene el secreto)


class AlertChannelsOut(BaseModel):
    teams: AlertChannelStatusOut
    power_automate: AlertChannelStatusOut


VALID_ALERT_EVENT_TYPES = {
    # Riesgos
    "risk_critical", "risk_high", "treatment_overdue", "risk_no_treatment",
    "treatment_due_soon", "daily_digest", "compound",
    # Controles
    "control_review_overdue",
    # Incidentes
    "incident_p1p2", "nis2_pending",
    # Politicas / tareas
    "policy_review_overdue", "task_overdue",
    # Proveedores / TPRM
    "supplier_created", "supplier_critical_risk", "vendor_issue_created",
    "vendor_issue_sla_breach", "questionnaire_overdue",
    # BCP / ISO 22301
    "bcp_review_overdue", "bcp_under_review",
    # Vigilancia normativa (regwatch)
    "regwatch_new_change", "regwatch_high_impact",
}

VALID_COMPOUND_ENTITY_TYPES = {"risk", "supplier", "supplier_questionnaire"}


class AlertConditionIn(BaseModel):
    field: str
    op: str = "gte"
    value: float


class AlertRuleIn(BaseModel):
    name: str
    event_type: str
    recipient_email: EmailStr
    threshold_level: int = Field(default=5, ge=0, le=100)
    is_active: bool = True
    # Solo aplica cuando event_type == "compound"
    entity_type: Optional[str] = None
    conditions: Optional[List[AlertConditionIn]] = None
    logic: str = "AND"


class AlertRuleOut(BaseModel):
    id: int
    name: str
    event_type: str
    recipient_email: str
    threshold_level: int
    is_active: bool
    created_at: datetime
    last_triggered_at: Optional[datetime] = None
    entity_type: Optional[str] = None
    conditions: Optional[List[dict]] = None
    logic: str = "AND"


class SendRiskAlertIn(BaseModel):
    recipient_email: Optional[EmailStr] = None
    reason: str = "Alerta manual de riesgo"


# ---------- Endpoints SMTP ----------

@router.get("/settings", response_model=Optional[EmailSettingsOut])
def get_settings(db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    cfg = filter_by_org(db.query(EmailSettings), EmailSettings, current_user).first()
    if not cfg:
        return None
    return EmailSettingsOut(
        smtp_host=cfg.smtp_host,
        smtp_port=cfg.smtp_port,
        smtp_user=cfg.smtp_user,
        smtp_from=cfg.smtp_from,
        smtp_use_tls=cfg.smtp_use_tls,
    )


@router.put("/settings", response_model=EmailSettingsOut)
def save_settings(body: EmailSettingsIn, db: Session = Depends(get_db),
                  current_user=Depends(get_current_user)):
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, "Solo administradores")
    cfg = filter_by_org(db.query(EmailSettings), EmailSettings, current_user).first()
    if not cfg:
        cfg = EmailSettings(organization_id=current_user.organization_id)
        db.add(cfg)
    cfg.smtp_host = body.smtp_host
    cfg.smtp_port = body.smtp_port
    cfg.smtp_user = body.smtp_user
    if body.smtp_password:  # solo actualizar si se envia valor
        from app.security import encrypt_secret
        cfg.smtp_password_encrypted = encrypt_secret(body.smtp_password)
        cfg.smtp_password = ""   # limpiar campo legacy
    cfg.smtp_from = body.smtp_from
    cfg.smtp_use_tls = body.smtp_use_tls
    log_action(db, current_user.id, "update", "email_settings", "1",
               {"smtp_host": cfg.smtp_host, "smtp_user": cfg.smtp_user})
    db.commit()
    db.refresh(cfg)
    return EmailSettingsOut(
        smtp_host=cfg.smtp_host,
        smtp_port=cfg.smtp_port,
        smtp_user=cfg.smtp_user,
        smtp_from=cfg.smtp_from,
        smtp_use_tls=cfg.smtp_use_tls,
    )


@router.post("/test")
def send_test(db: Session = Depends(get_db),
              current_user=Depends(get_current_user)):
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, "Solo administradores")
    # A1: pasar org_id para evitar usar SMTP de otro tenant
    cfg = email_service.get_settings(db, org_id=current_user.organization_id)
    if not cfg or not cfg.smtp_host:
        raise HTTPException(400, "Configura el servidor SMTP antes de enviar un test")
    try:
        email_service.send_email(
            cfg,
            cfg.smtp_from,
            "RiskHub — Email de prueba",
            email_service.test_email_html(),
        )
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "message": f"Email de prueba enviado a {cfg.smtp_from}"}


# ---------- Endpoints canales alternativos (Teams / Power Automate) ----------

def _channel_status(cfg, url_field: str, enabled_field: str) -> AlertChannelStatusOut:
    enc = getattr(cfg, url_field, None) if cfg else None
    enabled = bool(getattr(cfg, enabled_field, False)) if cfg else False
    if not enc:
        return AlertChannelStatusOut(configured=False, enabled=enabled, host_hint=None)
    try:
        from urllib.parse import urlparse

        from app.security import decrypt_secret
        host = urlparse(decrypt_secret(enc)).hostname or ""
    except Exception:
        host = ""
    return AlertChannelStatusOut(configured=True, enabled=enabled, host_hint=host)


@router.get("/channels", response_model=AlertChannelsOut)
def get_channels(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cfg = filter_by_org(db.query(EmailSettings), EmailSettings, current_user).first()
    return AlertChannelsOut(
        teams=_channel_status(cfg, "teams_webhook_url_encrypted", "teams_webhook_enabled"),
        power_automate=_channel_status(cfg, "power_automate_webhook_url_encrypted", "power_automate_webhook_enabled"),
    )


def _save_channel(db: Session, current_user, body: AlertChannelIn,
                   url_field: str, enabled_field: str, label: str) -> AlertChannelStatusOut:
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, "Solo administradores")
    cfg = filter_by_org(db.query(EmailSettings), EmailSettings, current_user).first()
    if not cfg:
        cfg = EmailSettings(organization_id=current_user.organization_id)
        db.add(cfg)
    if body.webhook_url:
        try:
            validate_webhook_url(body.webhook_url)
        except ValueError as e:
            raise HTTPException(422, str(e))
        from app.security import encrypt_secret
        setattr(cfg, url_field, encrypt_secret(body.webhook_url))
    setattr(cfg, enabled_field, body.enabled)
    log_action(db, current_user.id, "update", "alert_channel", label, {"enabled": body.enabled})
    db.commit()
    db.refresh(cfg)
    return _channel_status(cfg, url_field, enabled_field)


@router.put("/channels/teams", response_model=AlertChannelStatusOut)
def save_teams_channel(body: AlertChannelIn, db: Session = Depends(get_db),
                       current_user=Depends(get_current_user)):
    return _save_channel(db, current_user, body,
                         "teams_webhook_url_encrypted", "teams_webhook_enabled", "teams")


@router.put("/channels/power-automate", response_model=AlertChannelStatusOut)
def save_power_automate_channel(body: AlertChannelIn, db: Session = Depends(get_db),
                                current_user=Depends(get_current_user)):
    return _save_channel(db, current_user, body,
                         "power_automate_webhook_url_encrypted", "power_automate_webhook_enabled", "power_automate")


@router.delete("/channels/teams", status_code=204)
def delete_teams_channel(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, "Solo administradores")
    cfg = filter_by_org(db.query(EmailSettings), EmailSettings, current_user).first()
    if cfg:
        cfg.teams_webhook_url_encrypted = None
        cfg.teams_webhook_enabled = False
        log_action(db, current_user.id, "delete", "alert_channel", "teams", {})
        db.commit()


@router.delete("/channels/power-automate", status_code=204)
def delete_power_automate_channel(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, "Solo administradores")
    cfg = filter_by_org(db.query(EmailSettings), EmailSettings, current_user).first()
    if cfg:
        cfg.power_automate_webhook_url_encrypted = None
        cfg.power_automate_webhook_enabled = False
        log_action(db, current_user.id, "delete", "alert_channel", "power_automate", {})
        db.commit()


@router.post("/channels/teams/test")
def test_teams_channel(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, "Solo administradores")
    cfg = filter_by_org(db.query(EmailSettings), EmailSettings, current_user).first()
    if not cfg or not cfg.teams_webhook_url_encrypted:
        raise HTTPException(400, "Configura primero la URL del webhook de Teams")
    from app.security import decrypt_secret
    try:
        notification_channels.test_teams(decrypt_secret(cfg.teams_webhook_url_encrypted))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "message": "Mensaje de prueba enviado al canal de Teams"}


@router.post("/channels/power-automate/test")
def test_power_automate_channel(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, "Solo administradores")
    cfg = filter_by_org(db.query(EmailSettings), EmailSettings, current_user).first()
    if not cfg or not cfg.power_automate_webhook_url_encrypted:
        raise HTTPException(400, "Configura primero la URL de Power Automate")
    from app.security import decrypt_secret
    try:
        notification_channels.test_power_automate(decrypt_secret(cfg.power_automate_webhook_url_encrypted))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "message": "Solicitud de prueba enviada al flujo de Power Automate"}


# ---------- Endpoints Reglas ----------

def _rule_to_out(r: AlertRule) -> AlertRuleOut:
    return AlertRuleOut(
        id=r.id, name=r.name, event_type=r.event_type,
        recipient_email=r.recipient_email, threshold_level=r.threshold_level,
        is_active=r.is_active, created_at=r.created_at,
        last_triggered_at=r.last_triggered_at,
        entity_type=r.entity_type, conditions=r.conditions,
        logic=r.logic or "AND",
    )


@router.get("/rules", response_model=List[AlertRuleOut])
def list_rules(db: Session = Depends(get_db),
               current_user=Depends(get_current_user)):
    rules = filter_by_org(db.query(AlertRule), AlertRule, current_user).order_by(AlertRule.created_at).all()
    return [_rule_to_out(r) for r in rules]


@router.post("/rules", response_model=AlertRuleOut, status_code=201)
def create_rule(body: AlertRuleIn, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    # M1: restringido a ADMIN — analyst podria exfiltrar alertas a email externo
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, "Solo administradores pueden crear reglas de alerta")
    if body.event_type not in VALID_ALERT_EVENT_TYPES:
        raise HTTPException(422, f"event_type debe ser uno de: {', '.join(sorted(VALID_ALERT_EVENT_TYPES))}")
    if body.event_type == "compound" and body.entity_type and body.entity_type not in VALID_COMPOUND_ENTITY_TYPES:
        raise HTTPException(422, f"entity_type debe ser uno de: {', '.join(sorted(VALID_COMPOUND_ENTITY_TYPES))}")
    rule = AlertRule(organization_id=current_user.organization_id, **body.model_dump())
    db.add(rule)
    log_action(db, current_user.id, "create", "alert_rule", None,
               {"name": body.name, "event_type": body.event_type,
                "recipient": body.recipient_email})
    db.commit()
    db.refresh(rule)
    return _rule_to_out(rule)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, request: Request, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    lang = get_lang(request)
    # M1: solo ADMIN puede eliminar reglas
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, _t("common.forbidden", lang))
    rule = filter_by_org(db.query(AlertRule).filter(AlertRule.id == rule_id), AlertRule, current_user).first()
    if not rule:
        raise HTTPException(404, _t("alerts.rule_not_found", lang))
    log_action(db, current_user.id, "delete", "alert_rule", str(rule_id),
               {"name": rule.name, "event_type": rule.event_type})
    db.delete(rule)
    db.commit()


@router.patch("/rules/{rule_id}/toggle", response_model=AlertRuleOut)
def toggle_rule(rule_id: int, request: Request, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    lang = get_lang(request)
    # M1: solo ADMIN puede activar/desactivar reglas
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, _t("common.forbidden", lang))
    rule = filter_by_org(db.query(AlertRule).filter(AlertRule.id == rule_id), AlertRule, current_user).first()
    if not rule:
        raise HTTPException(404, _t("alerts.rule_not_found", lang))
    rule.is_active = not rule.is_active
    log_action(db, current_user.id, "update", "alert_rule", str(rule_id),
               {"name": rule.name, "is_active": rule.is_active})
    db.commit()
    db.refresh(rule)
    return _rule_to_out(rule)


# ---------- Envio manual y evaluacion de reglas ----------

@router.post("/send-risk/{risk_id}")
def send_risk_alert(risk_id: int, body: SendRiskAlertIn,
                    db: Session = Depends(get_db),
                    current_user=Depends(get_current_user)):
    """Envia una alerta manual para un riesgo especifico por todos los canales activos
    (email si se indica destinatario y hay SMTP, Teams y/o Power Automate si estan configurados)."""
    if current_user.role not in (UserRole.ADMIN, UserRole.ANALYST):
        raise HTTPException(403, "Acceso denegado")
    risk = filter_by_org(db.query(Risk).filter(Risk.id == risk_id), Risk, current_user).first()
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    # A1: org_id para evitar usar SMTP de otro tenant
    cfg = email_service.get_settings(db, org_id=current_user.organization_id)
    if not notification_channels.has_any_channel(cfg) and not body.recipient_email:
        raise HTTPException(400, "No hay ningun canal de alerta configurado (email, Teams o Power Automate)")

    from app.models import RiskContext
    ctx = filter_by_org(db.query(RiskContext), RiskContext, current_user).first()
    org = ctx.organization_name if ctx else "Organizacion"

    subject = f"RiskHub — Alerta: {risk.code} ({risk.residual_level}/8)"
    summary = f"{body.reason}\nRiesgo {risk.code} — nivel residual {risk.residual_level}/8."
    result = notification_channels.dispatch_alert(
        db, cfg, org, body.recipient_email, subject, summary,
        html_body=email_service.risk_alert_html(risk, org, body.reason),
        event="risk.manual_alert",
        fields={"risk_code": risk.code, "residual_level": risk.residual_level, "reason": body.reason},
    )
    if not any(v for v in result.values()):
        raise HTTPException(502, "No se pudo enviar la alerta por ningun canal configurado")
    sent_channels = [k for k, v in result.items() if v]
    return {"ok": True, "message": f"Alerta enviada via: {', '.join(sent_channels)}", "channels": result}


@router.post("/check-rules")
def check_rules(db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    """Evalua todas las reglas activas de la organizacion y envia alertas
    (email/Teams/Power Automate, segun lo configurado) para cualquier categoria:
    riesgos, controles, incidentes, politicas, tareas, proveedores/TPRM, BCP y
    vigilancia normativa. Misma logica que la evaluacion periodica del scheduler."""
    if current_user.role not in (UserRole.ADMIN, UserRole.ANALYST):
        raise HTTPException(403, "Acceso denegado")
    # A1: org_id para evitar usar SMTP de otro tenant
    cfg = email_service.get_settings(db, org_id=current_user.organization_id)
    if not notification_channels.has_any_channel(cfg):
        raise HTTPException(400, "No hay ningun canal de alerta configurado (email, Teams o Power Automate)")

    from app.services.alert_rules_service import evaluate_rules_for_org
    return evaluate_rules_for_org(db, current_user.organization_id)
