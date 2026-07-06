"""Canales de alerta alternativos a SMTP: Microsoft Teams y Power Automate.

Pensado para clientes que por politica de seguridad no permiten configurar
un servidor SMTP dentro de la aplicacion. En ambos casos RiskHub solo hace
un POST HTTPS saliente a una URL que el propio cliente genera y controla
desde su tenant de Microsoft 365 — nunca se manejan credenciales de correo.

- Teams: URL de webhook de la app "Workflows" (plantilla nativa "Send webhook
  alerts to a channel", trigger "When a Teams webhook request is received").
  Formato POST {"text": "..."} en Markdown, sin necesidad de que el cliente
  construya un flujo personalizado.
- Power Automate: URL de un flujo propio con trigger "Cuando se recibe una
  solicitud HTTP". Se envia un JSON con campos estructurados; el cliente
  decide en su flujo que hacer con ellos (publicar en Teams, reenviar por su
  propio Outlook via conector OAuth, guardar en SharePoint, etc.). Mismo
  patron que services/msforms_service.py:_send_pa_webhook.
"""
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.services.webhook_service import validate_webhook_url

logger = logging.getLogger("riskhub.notification_channels")


def _post_json(url: str, payload: dict, timeout: int = 10) -> None:
    """POST JSON a una URL externa. Lanza RuntimeError si falla o la URL no es segura."""
    try:
        validate_webhook_url(url)
    except ValueError as exc:
        raise RuntimeError(f"URL no permitida: {exc}") from exc

    data = json.dumps(payload, default=str).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if not (200 <= resp.status < 300):
                raise RuntimeError(f"Respuesta HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Error HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Error de conexion: {exc.reason}") from exc


def send_teams_alert(webhook_url: str, title: str, summary: str) -> None:
    """Envia una alerta a un canal de Teams via webhook de Workflows.

    Usa el formato simple {"text": "..."} en Markdown, compatible con la
    plantilla nativa de Teams sin requerir un flujo custom del cliente.
    """
    text = f"**{title}**\n\n{summary}"
    _post_json(webhook_url, {"text": text})


def send_power_automate_alert(webhook_url: str, event: str, org_name: str, fields: dict) -> None:
    """POST JSON generico a un flujo de Power Automate del cliente.

    El cliente construye su propio flujo (trigger HTTP) y decide que hacer
    con estos campos: publicar en Teams, reenviar por su Outlook, etc.
    """
    payload = {
        "event": event,
        "organization": org_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    _post_json(webhook_url, payload)


def test_teams(webhook_url: str) -> None:
    send_teams_alert(
        webhook_url,
        "RiskHub — Mensaje de prueba",
        "La configuracion del canal de Teams funciona correctamente.",
    )


def test_power_automate(webhook_url: str) -> None:
    send_power_automate_alert(webhook_url, "test", "RiskHub", {
        "message": "La configuracion de Power Automate funciona correctamente.",
    })


def has_any_channel(cfg) -> bool:
    """True si la org tiene al menos un canal de alerta operativo (email, Teams o PA)."""
    if not cfg:
        return False
    if cfg.smtp_host:
        return True
    if getattr(cfg, "teams_webhook_enabled", False) and getattr(cfg, "teams_webhook_url_encrypted", None):
        return True
    if getattr(cfg, "power_automate_webhook_enabled", False) and getattr(cfg, "power_automate_webhook_url_encrypted", None):
        return True
    return False


def _decrypt_url(enc: str) -> str:
    from app.security import decrypt_secret
    return decrypt_secret(enc)


def dispatch_alert(
    db: Session,
    cfg,
    org_name: str,
    recipient_email: Optional[str],
    subject: str,
    summary_text: str,
    html_body: Optional[str] = None,
    event: str = "alert",
    fields: Optional[dict] = None,
) -> dict:
    """Envia una alerta por todos los canales configurados y activos en `cfg`
    (EmailSettings de la org): email SMTP, Teams, Power Automate.

    Devuelve {"email": bool|None, "teams": bool|None, "power_automate": bool|None}.
    None = canal no configurado/activo (no se intento), True/False = resultado del envio.
    """
    from app.services import email_service

    result: dict = {"email": None, "teams": None, "power_automate": None}
    if not cfg:
        return result

    if cfg.smtp_host and recipient_email:
        try:
            email_service.send_email(cfg, recipient_email, subject, html_body or summary_text)
            result["email"] = True
        except Exception as exc:
            logger.warning("dispatch_alert: error canal email: %s", exc)
            result["email"] = False

    if getattr(cfg, "teams_webhook_enabled", False) and getattr(cfg, "teams_webhook_url_encrypted", None):
        try:
            url = _decrypt_url(cfg.teams_webhook_url_encrypted)
            send_teams_alert(url, subject, summary_text)
            result["teams"] = True
        except Exception as exc:
            logger.warning("dispatch_alert: error canal Teams: %s", exc)
            result["teams"] = False

    if getattr(cfg, "power_automate_webhook_enabled", False) and getattr(cfg, "power_automate_webhook_url_encrypted", None):
        try:
            url = _decrypt_url(cfg.power_automate_webhook_url_encrypted)
            send_power_automate_alert(
                url, event, org_name,
                fields or {"subject": subject, "summary": summary_text},
            )
            result["power_automate"] = True
        except Exception as exc:
            logger.warning("dispatch_alert: error canal Power Automate: %s", exc)
            result["power_automate"] = False

    return result
