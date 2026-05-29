"""Gestion de alertas por email: configuracion SMTP y reglas de alerta."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AlertRule, EmailSettings, Risk, UserRole
from app.security import filter_by_org, get_current_user
from app.services import email_service
from app.services.audit_service import log_action

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


class AlertRuleIn(BaseModel):
    name: str
    event_type: str  # risk_high, risk_critical, treatment_overdue, risk_no_treatment
    recipient_email: EmailStr
    threshold_level: int = 5
    is_active: bool = True


class AlertRuleOut(BaseModel):
    id: int
    name: str
    event_type: str
    recipient_email: str
    threshold_level: int
    is_active: bool
    created_at: datetime
    last_triggered_at: Optional[datetime] = None


class SendRiskAlertIn(BaseModel):
    recipient_email: EmailStr
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
        cfg.smtp_password = body.smtp_password
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
    cfg = email_service.get_settings(db)
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


# ---------- Endpoints Reglas ----------

@router.get("/rules", response_model=List[AlertRuleOut])
def list_rules(db: Session = Depends(get_db),
               current_user=Depends(get_current_user)):
    rules = filter_by_org(db.query(AlertRule), AlertRule, current_user).order_by(AlertRule.created_at).all()
    return [AlertRuleOut(
        id=r.id, name=r.name, event_type=r.event_type,
        recipient_email=r.recipient_email, threshold_level=r.threshold_level,
        is_active=r.is_active, created_at=r.created_at,
        last_triggered_at=r.last_triggered_at,
    ) for r in rules]


@router.post("/rules", response_model=AlertRuleOut, status_code=201)
def create_rule(body: AlertRuleIn, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    if current_user.role not in (UserRole.ADMIN, UserRole.ANALYST):
        raise HTTPException(403, "Acceso denegado")
    valid_types = {"risk_high", "risk_critical", "treatment_overdue", "risk_no_treatment"}
    if body.event_type not in valid_types:
        raise HTTPException(422, f"event_type debe ser uno de: {', '.join(valid_types)}")
    rule = AlertRule(organization_id=current_user.organization_id, **body.model_dump())
    db.add(rule)
    log_action(db, current_user.id, "create", "alert_rule", None,
               {"name": body.name, "event_type": body.event_type,
                "recipient": body.recipient_email})
    db.commit()
    db.refresh(rule)
    return AlertRuleOut(
        id=rule.id, name=rule.name, event_type=rule.event_type,
        recipient_email=rule.recipient_email, threshold_level=rule.threshold_level,
        is_active=rule.is_active, created_at=rule.created_at,
        last_triggered_at=rule.last_triggered_at,
    )


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    if current_user.role not in (UserRole.ADMIN, UserRole.ANALYST):
        raise HTTPException(403, "Acceso denegado")
    rule = db.get(AlertRule, rule_id)
    if not rule:
        raise HTTPException(404, "Regla no encontrada")
    log_action(db, current_user.id, "delete", "alert_rule", str(rule_id),
               {"name": rule.name, "event_type": rule.event_type})
    db.delete(rule)
    db.commit()


@router.patch("/rules/{rule_id}/toggle", response_model=AlertRuleOut)
def toggle_rule(rule_id: int, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    if current_user.role not in (UserRole.ADMIN, UserRole.ANALYST):
        raise HTTPException(403, "Acceso denegado")
    rule = db.get(AlertRule, rule_id)
    if not rule:
        raise HTTPException(404, "Regla no encontrada")
    rule.is_active = not rule.is_active
    log_action(db, current_user.id, "update", "alert_rule", str(rule_id),
               {"name": rule.name, "is_active": rule.is_active})
    db.commit()
    db.refresh(rule)
    return AlertRuleOut(
        id=rule.id, name=rule.name, event_type=rule.event_type,
        recipient_email=rule.recipient_email, threshold_level=rule.threshold_level,
        is_active=rule.is_active, created_at=rule.created_at,
        last_triggered_at=rule.last_triggered_at,
    )


# ---------- Envio manual y evaluacion de reglas ----------

@router.post("/send-risk/{risk_id}")
def send_risk_alert(risk_id: int, body: SendRiskAlertIn,
                    db: Session = Depends(get_db),
                    current_user=Depends(get_current_user)):
    """Envia una alerta manual para un riesgo especifico."""
    if current_user.role not in (UserRole.ADMIN, UserRole.ANALYST):
        raise HTTPException(403, "Acceso denegado")
    risk = db.get(Risk, risk_id)
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    cfg = email_service.get_settings(db)
    if not cfg or not cfg.smtp_host:
        raise HTTPException(400, "Servidor SMTP no configurado")

    from app.models import RiskContext
    ctx = filter_by_org(db.query(RiskContext), RiskContext, current_user).first()
    org = ctx.organization_name if ctx else "Organizacion"

    try:
        email_service.send_email(
            cfg,
            body.recipient_email,
            f"RiskHub — Alerta: {risk.code} ({risk.residual_level}/8)",
            email_service.risk_alert_html(risk, org, body.reason),
        )
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "message": f"Alerta enviada a {body.recipient_email}"}


@router.post("/check-rules")
def check_rules(db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    """Evalua todas las reglas activas y envia emails para los riesgos que cumplen criterios."""
    if current_user.role not in (UserRole.ADMIN, UserRole.ANALYST):
        raise HTTPException(403, "Acceso denegado")
    cfg = email_service.get_settings(db)
    if not cfg or not cfg.smtp_host:
        raise HTTPException(400, "Servidor SMTP no configurado")

    from app.models import RiskContext, RiskStatus
    ctx = filter_by_org(db.query(RiskContext), RiskContext, current_user).first()
    org = ctx.organization_name if ctx else "Organizacion"

    rules = filter_by_org(
        db.query(AlertRule).filter(AlertRule.is_active.is_(True)), AlertRule, current_user
    ).all()
    risks = filter_by_org(db.query(Risk), Risk, current_user).all()
    sent = 0
    errors = []

    for rule in rules:
        matching = []
        now = datetime.now(timezone.utc)

        if rule.event_type == "risk_critical":
            matching = [r for r in risks if r.residual_level >= rule.threshold_level
                        and r.status not in (RiskStatus.ACCEPTED, RiskStatus.CLOSED)]
        elif rule.event_type == "risk_high":
            matching = [r for r in risks if r.residual_level >= rule.threshold_level
                        and r.status not in (RiskStatus.ACCEPTED, RiskStatus.CLOSED)]
        elif rule.event_type == "treatment_overdue":
            matching = [r for r in risks
                        if r.treatment_due_date and r.treatment_due_date < now
                        and r.status not in (RiskStatus.TREATED, RiskStatus.ACCEPTED, RiskStatus.CLOSED)]
        elif rule.event_type == "risk_no_treatment":
            matching = [r for r in risks
                        if r.residual_level >= rule.threshold_level
                        and not r.treatment_option
                        and r.status not in (RiskStatus.ACCEPTED, RiskStatus.CLOSED)]

        for risk in matching:
            reason_map = {
                "risk_critical": f"Riesgo {risk.code} supera el umbral critico (nivel {risk.residual_level})",
                "risk_high": f"Riesgo {risk.code} supera el umbral alto configurado (nivel {risk.residual_level})",
                "treatment_overdue": f"El plan de tratamiento del riesgo {risk.code} esta vencido",
                "risk_no_treatment": f"Riesgo {risk.code} (nivel {risk.residual_level}) sin plan de tratamiento definido",
            }
            try:
                email_service.send_email(
                    cfg,
                    rule.recipient_email,
                    f"RiskHub — {reason_map.get(rule.event_type, 'Alerta')}",
                    email_service.risk_alert_html(risk, org, reason_map.get(rule.event_type, "")),
                )
                sent += 1
            except RuntimeError as e:
                errors.append(str(e))

        if matching:
            rule.last_triggered_at = now
            db.commit()

    return {
        "sent": sent,
        "rules_evaluated": len(rules),
        "errors": errors,
    }
