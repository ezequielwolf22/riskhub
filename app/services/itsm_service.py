"""Integraciones ITSM: ServiceNow y Jira — crea tickets automáticamente desde riesgos/incidentes."""
import json
import logging
from typing import Optional

import urllib.request
import urllib.parse
import base64

from sqlalchemy.orm import Session
from app.models import IntegrationConfig, Risk, Incident

logger = logging.getLogger("riskhub.itsm")


def _get_config(db: Session, org_id: int, tool: str) -> Optional[dict]:
    """Obtiene config desencriptada de la herramienta ITSM."""
    import hashlib, base64 as b64
    from app.config import settings
    from cryptography.fernet import Fernet

    ic = db.query(IntegrationConfig).filter_by(
        name=f"itsm_{tool}",
        organization_id=org_id,
    ).first()
    if not ic or not ic.config_encrypted:
        return None
    key = b64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    try:
        return json.loads(Fernet(key).decrypt(ic.config_encrypted.encode()).decode())
    except Exception:
        return None


def _save_config(db: Session, org_id: int, tool: str, config: dict) -> None:
    import hashlib, base64 as b64
    from app.config import settings
    from cryptography.fernet import Fernet

    key = b64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    encrypted = Fernet(key).encrypt(json.dumps(config).encode()).decode()

    ic = db.query(IntegrationConfig).filter_by(
        name=f"itsm_{tool}",
        organization_id=org_id,
    ).first()
    if not ic:
        ic = IntegrationConfig(name=f"itsm_{tool}", organization_id=org_id)
        db.add(ic)
    ic.config_encrypted = encrypted
    db.commit()


# ─────────────────────── JIRA ─────────────────────────────────────────────────

def create_jira_issue(cfg: dict, summary: str, description: str,
                      issue_type: str = "Task", priority: str = "High") -> Optional[dict]:
    """Crea issue en Jira Cloud/Server."""
    base_url = cfg.get("base_url", "").rstrip("/")
    project_key = cfg.get("project_key", "")
    email = cfg.get("email", "")
    api_token = cfg.get("api_token", "")

    if not all([base_url, project_key, email, api_token]):
        logger.warning("Jira config incompleta")
        return None

    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary[:255],
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description[:4000]}]}],
            },
            "issuetype": {"name": issue_type},
            "priority": {"name": priority},
        }
    }

    auth = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    url = f"{base_url}/rest/api/3/issue"

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {auth}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            logger.info("Jira issue creado: %s", result.get("key"))
            return result
    except Exception as exc:
        logger.warning("Error creando Jira issue: %s", exc)
        return None


# ─────────────────────── SERVICENOW ───────────────────────────────────────────

def create_servicenow_incident(cfg: dict, short_desc: str, description: str,
                                urgency: int = 2, impact: int = 2) -> Optional[dict]:
    """Crea incident en ServiceNow."""
    instance = cfg.get("instance", "").replace("https://", "").replace(".service-now.com", "")
    username = cfg.get("username", "")
    password = cfg.get("password", "")

    if not all([instance, username, password]):
        logger.warning("ServiceNow config incompleta")
        return None

    payload = {
        "short_description": short_desc[:160],
        "description": description[:4000],
        "urgency": str(urgency),   # 1=High 2=Medium 3=Low
        "impact": str(impact),
        "category": "Security",
    }

    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    url = f"https://{instance}.service-now.com/api/now/table/incident"

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Basic {auth}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            sys_id = result.get("result", {}).get("sys_id", "")
            logger.info("ServiceNow incident creado: %s", sys_id)
            return result.get("result", {})
    except Exception as exc:
        logger.warning("Error creando ServiceNow incident: %s", exc)
        return None


# ─────────────────────── SLACK / TEAMS ────────────────────────────────────────

def send_slack_notification(webhook_url: str, text: str, blocks: Optional[list] = None) -> bool:
    """Envía notificación a Slack via Incoming Webhook."""
    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:
        logger.warning("Error enviando Slack notification: %s", exc)
        return False


def send_teams_notification(webhook_url: str, title: str, text: str,
                             color: str = "FF0000") -> bool:
    """Envía notificación a Microsoft Teams via Incoming Webhook."""
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color,
        "summary": title,
        "sections": [{"activityTitle": title, "activityText": text}],
    }

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 202)
    except Exception as exc:
        logger.warning("Error enviando Teams notification: %s", exc)
        return False


# ─────────────────────── AUTO-TRIGGER ─────────────────────────────────────────

def notify_high_risk(db: Session, risk: Risk) -> None:
    """Notifica automáticamente por todos los canales configurados cuando riesgo es HIGH."""
    org_id = risk.organization_id
    if not org_id:
        return

    risk_code = risk.code or f"RSK-{risk.id}"
    level = risk.residual_level or 0
    desc = (risk.description or "")[:200]

    summary = f"[RiskHub] Riesgo {risk_code} — Nivel {level}"
    body = f"Riesgo: {risk_code}\nNivel residual: {level}\nDescripción: {desc}"

    # Jira
    jira_cfg = _get_config(db, org_id, "jira")
    if jira_cfg and jira_cfg.get("auto_create_issues"):
        priority = "Highest" if level >= 6 else "High"
        create_jira_issue(jira_cfg, summary, body, priority=priority)

    # ServiceNow
    snow_cfg = _get_config(db, org_id, "servicenow")
    if snow_cfg and snow_cfg.get("auto_create_incidents"):
        urgency = 1 if level >= 6 else 2
        create_servicenow_incident(snow_cfg, summary, body, urgency=urgency)

    # Slack
    slack_cfg = _get_config(db, org_id, "slack")
    if slack_cfg and slack_cfg.get("webhook_url"):
        color = "danger" if level >= 6 else "warning"
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f":warning: {summary}"}},
            {"type": "section", "text": {"type": "mrkdwn",
             "text": f"*Nivel residual:* {level}\n*Descripción:* {desc}"}},
        ]
        send_slack_notification(slack_cfg["webhook_url"], summary, blocks)

    # Teams
    teams_cfg = _get_config(db, org_id, "teams")
    if teams_cfg and teams_cfg.get("webhook_url"):
        color = "FF0000" if level >= 6 else "FF8C00"
        send_teams_notification(teams_cfg["webhook_url"], summary, body, color)
