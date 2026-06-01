"""Router de integraciones ITSM (Jira, ServiceNow, Slack, Teams)."""
import hashlib, base64, re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import User, IntegrationConfig
from app.security import get_current_user, require_role
from app.services.itsm_service import (
    create_jira_issue, create_servicenow_incident,
    send_slack_notification, send_teams_notification,
    _get_config, _save_config,
)

router = APIRouter(prefix="/api/itsm", tags=["itsm"])


class JiraConfigIn(BaseModel):
    base_url: str
    project_key: str
    email: str
    api_token: str
    auto_create_issues: bool = True


class ServiceNowConfigIn(BaseModel):
    instance: str
    username: str
    password: str
    auto_create_incidents: bool = True


class SlackConfigIn(BaseModel):
    webhook_url: str


class TeamsConfigIn(BaseModel):
    webhook_url: str


class ManualTicketIn(BaseModel):
    summary: str
    description: str
    risk_id: Optional[int] = None
    priority: str = "High"


# ─── Jira ──────────────────────────────────────────────────────────────────────

@router.get("/jira/config")
def get_jira_config(db: Session = Depends(get_db),
                    current_user: User = Depends(require_role("admin"))):
    cfg = _get_config(db, current_user.organization_id, "jira")
    if not cfg:
        return {"configured": False}
    return {"configured": True, "base_url": cfg.get("base_url"), "project_key": cfg.get("project_key"),
            "email": cfg.get("email"), "auto_create_issues": cfg.get("auto_create_issues", True)}


@router.put("/jira/config")
def save_jira_config(body: JiraConfigIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_role("admin"))):
    if not body.base_url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL inválida")
    _save_config(db, current_user.organization_id, "jira", body.model_dump())
    return {"message": "Configuración Jira guardada"}


@router.post("/jira/test")
def test_jira(db: Session = Depends(get_db), current_user: User = Depends(require_role("admin"))):
    cfg = _get_config(db, current_user.organization_id, "jira")
    if not cfg:
        raise HTTPException(404, "Jira no configurado")
    result = create_jira_issue(cfg, "[RiskHub] Test de conexión",
                               "Este es un ticket de prueba de RiskHub.", issue_type="Task", priority="Low")
    if result:
        return {"success": True, "issue_key": result.get("key")}
    raise HTTPException(502, "No se pudo conectar con Jira")


@router.post("/jira/ticket")
def create_jira_ticket(body: ManualTicketIn, db: Session = Depends(get_db),
                       current_user: User = Depends(require_role("analyst"))):
    cfg = _get_config(db, current_user.organization_id, "jira")
    if not cfg:
        raise HTTPException(404, "Jira no configurado")
    result = create_jira_issue(cfg, body.summary, body.description, priority=body.priority)
    if result:
        return {"success": True, "issue_key": result.get("key"), "url": f"{cfg['base_url']}/browse/{result.get('key')}"}
    raise HTTPException(502, "Error creando ticket en Jira")


# ─── ServiceNow ───────────────────────────────────────────────────────────────

@router.get("/servicenow/config")
def get_snow_config(db: Session = Depends(get_db),
                    current_user: User = Depends(require_role("admin"))):
    cfg = _get_config(db, current_user.organization_id, "servicenow")
    if not cfg:
        return {"configured": False}
    return {"configured": True, "instance": cfg.get("instance"),
            "username": cfg.get("username"), "auto_create_incidents": cfg.get("auto_create_incidents", True)}


@router.put("/servicenow/config")
def save_snow_config(body: ServiceNowConfigIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_role("admin"))):
    _save_config(db, current_user.organization_id, "servicenow", body.model_dump())
    return {"message": "Configuración ServiceNow guardada"}


@router.post("/servicenow/test")
def test_snow(db: Session = Depends(get_db), current_user: User = Depends(require_role("admin"))):
    cfg = _get_config(db, current_user.organization_id, "servicenow")
    if not cfg:
        raise HTTPException(404, "ServiceNow no configurado")
    result = create_servicenow_incident(cfg, "[RiskHub] Test de conexión",
                                        "Incident de prueba de RiskHub.", urgency=3, impact=3)
    if result:
        return {"success": True, "sys_id": result.get("sys_id")}
    raise HTTPException(502, "No se pudo conectar con ServiceNow")


# ─── Slack ─────────────────────────────────────────────────────────────────────

@router.get("/slack/config")
def get_slack_config(db: Session = Depends(get_db),
                     current_user: User = Depends(require_role("admin"))):
    cfg = _get_config(db, current_user.organization_id, "slack")
    return {"configured": bool(cfg and cfg.get("webhook_url"))}


@router.put("/slack/config")
def save_slack_config(body: SlackConfigIn, db: Session = Depends(get_db),
                      current_user: User = Depends(require_role("admin"))):
    if not body.webhook_url.startswith("https://hooks.slack.com/"):
        raise HTTPException(400, "URL de Slack inválida (debe ser hooks.slack.com)")
    _save_config(db, current_user.organization_id, "slack", body.model_dump())
    return {"message": "Configuración Slack guardada"}


@router.post("/slack/test")
def test_slack(db: Session = Depends(get_db), current_user: User = Depends(require_role("admin"))):
    cfg = _get_config(db, current_user.organization_id, "slack")
    if not cfg or not cfg.get("webhook_url"):
        raise HTTPException(404, "Slack no configurado")
    ok = send_slack_notification(cfg["webhook_url"], ":white_check_mark: RiskHub conectado a Slack correctamente")
    if ok:
        return {"success": True}
    raise HTTPException(502, "No se pudo conectar con Slack")


# ─── Teams ─────────────────────────────────────────────────────────────────────

@router.get("/teams/config")
def get_teams_config(db: Session = Depends(get_db),
                     current_user: User = Depends(require_role("admin"))):
    cfg = _get_config(db, current_user.organization_id, "teams")
    return {"configured": bool(cfg and cfg.get("webhook_url"))}


@router.put("/teams/config")
def save_teams_config(body: TeamsConfigIn, db: Session = Depends(get_db),
                      current_user: User = Depends(require_role("admin"))):
    # A4: validar dominio explicitamente para prevenir SSRF via metadata endpoints
    if not re.match(r"https://[^/]*\.webhook\.office\.com/", body.webhook_url):
        raise HTTPException(400, "URL de Teams invalida: debe ser de *.webhook.office.com")
    _save_config(db, current_user.organization_id, "teams", body.model_dump())
    return {"message": "Configuracion Teams guardada"}


@router.post("/teams/test")
def test_teams(db: Session = Depends(get_db), current_user: User = Depends(require_role("admin"))):
    cfg = _get_config(db, current_user.organization_id, "teams")
    if not cfg or not cfg.get("webhook_url"):
        raise HTTPException(404, "Teams no configurado")
    ok = send_teams_notification(cfg["webhook_url"], "RiskHub conectado",
                                  "Conexión con Microsoft Teams funcionando correctamente.", "00CC00")
    if ok:
        return {"success": True}
    raise HTTPException(502, "No se pudo conectar con Teams")


# ─── Status global ─────────────────────────────────────────────────────────────

@router.get("/status")
def itsm_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    org_id = current_user.organization_id
    return {
        "jira": bool(_get_config(db, org_id, "jira")),
        "servicenow": bool(_get_config(db, org_id, "servicenow")),
        "slack": bool(_get_config(db, org_id, "slack")),
        "teams": bool(_get_config(db, org_id, "teams")),
    }
