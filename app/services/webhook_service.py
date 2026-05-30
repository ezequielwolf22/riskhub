"""Servicio de webhooks: dispara notificaciones a URLs externas."""
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import urllib.request
import urllib.error
from sqlalchemy.orm import Session

from app.models import Webhook, WebhookDelivery, WebhookEvent

logger = logging.getLogger("riskhub.webhooks")

# CIDRs internos bloqueados para prevenir SSRF
_BLOCKED_CIDRS = [
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / cloud metadata
    ipaddress.ip_network("10.0.0.0/8"),        # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),     # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),    # RFC 1918
    ipaddress.ip_network("127.0.0.0/8"),       # loopback
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def validate_webhook_url(url: str) -> None:
    """Valida que la URL del webhook no apunte a recursos internos (anti-SSRF).

    Raises ValueError si la URL no es segura.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Solo se permiten esquemas http y https en webhooks")
    if not parsed.hostname:
        raise ValueError("URL de webhook sin hostname válido")

    try:
        ip_str = socket.gethostbyname(parsed.hostname)
        ip = ipaddress.ip_address(ip_str)
        for cidr in _BLOCKED_CIDRS:
            if ip in cidr:
                raise ValueError(
                    f"El host del webhook resuelve a IP interna ({ip}), no permitido"
                )
    except socket.gaierror:
        raise ValueError(f"No se puede resolver el hostname del webhook: {parsed.hostname}")


def _sign_payload(secret: str, payload: str) -> str:
    """HMAC-SHA256 signature para verificar autenticidad del payload."""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def trigger_webhook_sync(db: Session, org_id: int, event: str, payload: dict) -> int:
    """Dispara webhooks síncronos para un evento (para uso en scheduler).

    Retorna número de webhooks disparados.
    """
    import requests

    webhooks = db.query(Webhook).filter(
        Webhook.organization_id == org_id,
        Webhook.is_active == True,
    ).all()

    triggered = 0
    for wh in webhooks:
        events = wh.events or []
        if event not in events and "*" not in events:
            continue

        # Validar URL en cada disparo (el DNS puede cambiar)
        try:
            validate_webhook_url(wh.url)
        except ValueError as e:
            logger.warning("Webhook %s bloqueado por seguridad SSRF: %s", wh.name, e)
            continue

        payload_str = json.dumps(payload, default=str)
        headers_dict = {
            "Content-Type": "application/json",
            "X-RiskHub-Event": event,
            "X-RiskHub-Delivery": f"{wh.id}-{int(time.time())}",
        }
        # Solo headers seguros del config (no sobrescribir headers de seguridad)
        if wh.headers:
            safe_keys = {k for k in wh.headers if k.lower() not in (
                "host", "content-length", "transfer-encoding"
            )}
            for k in safe_keys:
                headers_dict[k] = wh.headers[k]

        if wh.secret:
            sig = _sign_payload(wh.secret, payload_str)
            headers_dict["X-RiskHub-Signature"] = f"sha256={sig}"

        start = time.time()
        success = False
        resp_status = None
        resp_body = None

        for attempt in range(1, (wh.retry_count or 1) + 1):
            try:
                req = urllib.request.Request(
                    wh.url,
                    data=payload_str.encode("utf-8"),
                    headers=headers_dict,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp_status = resp.status
                    # No guardamos response body para prevenir exfiltración
                    resp_body = None
                    success = 200 <= resp_status < 300
                if success:
                    break
            except urllib.error.HTTPError as exc:
                resp_status = exc.code
                resp_body = None  # No exponer cuerpo de error interno
                if attempt < wh.retry_count:
                    time.sleep(1)
            except Exception as exc:
                resp_body = None
                if attempt < wh.retry_count:
                    time.sleep(1)

        duration = int((time.time() - start) * 1000)

        # Log delivery
        delivery = WebhookDelivery(
            webhook_id=wh.id,
            event=event,
            payload=payload_str[:4096],
            response_status=resp_status,
            response_body=resp_body,
            duration_ms=duration,
            success=success,
            attempt=attempt,
        )
        db.add(delivery)

        # Actualizar webhook
        wh.last_triggered_at = datetime.now(timezone.utc)
        if success:
            wh.last_success_at = datetime.now(timezone.utc)

        triggered += 1
        logger.info(
            "Webhook %s (%s) → %s: status=%s success=%s",
            wh.name, event, wh.url[:60], resp_status, success
        )

    if triggered:
        try:
            db.commit()
        except Exception:
            db.rollback()

    return triggered


def fire_event(db: Session, org_id: int, event: WebhookEvent, data: dict) -> None:
    """Dispara un evento a los webhooks suscritos de una org."""
    payload = {
        "event": event.value if hasattr(event, "value") else event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "organization_id": org_id,
        "data": data,
    }
    try:
        event_str = event.value if hasattr(event, "value") else str(event)
        trigger_webhook_sync(db, org_id, event_str, payload)
    except Exception as exc:
        logger.exception("Error disparando webhook %s: %s", event, exc)


def fire_risk_created(db: Session, risk) -> None:
    from app.models import WebhookEvent as WE
    fire_event(db, risk.organization_id, WE.RISK_CREATED, {
        "risk_id": risk.id,
        "code": risk.code,
        "residual_level": risk.residual_level,
        "status": risk.status.value if hasattr(risk.status, "value") else str(risk.status),
        "asset_id": risk.asset_id,
    })


def fire_risk_high(db: Session, risk) -> None:
    from app.models import WebhookEvent as WE
    fire_event(db, risk.organization_id, WE.RISK_HIGH, {
        "risk_id": risk.id,
        "code": risk.code,
        "residual_level": risk.residual_level,
        "inherent_level": risk.inherent_level,
        "asset_id": risk.asset_id,
    })
