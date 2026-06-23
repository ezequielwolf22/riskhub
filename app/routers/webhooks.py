"""Router de webhooks."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import User, Webhook, WebhookDelivery, WebhookEvent
from app.security import get_current_user, require_role

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _wh_out(w: Webhook) -> dict:
    return {
        "id": w.id,
        "name": w.name,
        "url": w.url,
        "events": w.events or [],
        "is_active": w.is_active,
        "retry_count": w.retry_count,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "last_triggered_at": w.last_triggered_at.isoformat() if w.last_triggered_at else None,
        "last_success_at": w.last_success_at.isoformat() if w.last_success_at else None,
    }


class WebhookIn(BaseModel):
    name: str
    url: str
    secret: Optional[str] = None
    events: list[str]
    is_active: bool = True
    headers: Optional[dict] = None
    retry_count: int = 3


@router.get("/events")
def list_events():
    """Lista todos los eventos disponibles para webhooks."""
    return [{"event": e.value, "description": e.name.replace("_", " ").title()}
            for e in WebhookEvent]


@router.get("")
def list_webhooks(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Lista webhooks de la org."""
    whs = db.query(Webhook).filter(
        Webhook.organization_id == current_user.organization_id
    ).all()
    return [_wh_out(w) for w in whs]


@router.post("")
def create_webhook(
    body: WebhookIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Crea nuevo webhook."""
    org_id = current_user.organization_id

    # Validar eventos
    valid_events = {e.value for e in WebhookEvent} | {"*"}
    for event in body.events:
        if event not in valid_events:
            raise HTTPException(400, f"Evento '{event}' inválido")

    # Validar URL (anti-SSRF)
    from app.services.webhook_service import validate_webhook_url
    try:
        validate_webhook_url(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    wh = Webhook(
        organization_id=org_id,
        name=body.name[:128],
        url=body.url[:1024],
        secret=body.secret,
        events=body.events,
        is_active=body.is_active,
        headers=body.headers,
        retry_count=min(5, max(1, body.retry_count)),
        created_by_id=current_user.id,
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return _wh_out(wh)


@router.put("/{webhook_id}")
def update_webhook(
    webhook_id: int,
    body: WebhookIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Actualiza webhook."""
    lang = get_lang(request)
    wh = db.get(Webhook, webhook_id)
    if not wh or wh.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("webhooks.not_found", lang))

    from app.services.webhook_service import validate_webhook_url
    try:
        validate_webhook_url(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    wh.name = body.name[:128]
    wh.url = body.url[:1024]
    if body.secret is not None:
        wh.secret = body.secret
    wh.events = body.events
    wh.is_active = body.is_active
    if body.headers is not None:
        wh.headers = body.headers
    wh.retry_count = min(5, max(1, body.retry_count))
    db.commit()
    return _wh_out(wh)


@router.delete("/{webhook_id}")
def delete_webhook(
    webhook_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Elimina webhook."""
    lang = get_lang(request)
    wh = db.get(Webhook, webhook_id)
    if not wh or wh.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("webhooks.not_found", lang))
    db.delete(wh)
    db.commit()
    return {"message": "Webhook eliminado"}


@router.post("/{webhook_id}/test")
def test_webhook(
    webhook_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Envía un payload de prueba al webhook."""
    lang = get_lang(request)
    wh = db.get(Webhook, webhook_id)
    if not wh or wh.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("webhooks.not_found", lang))

    from app.services.webhook_service import trigger_webhook_sync
    payload = {
        "event": "webhook.test",
        "message": "Este es un test de RiskHub webhooks",
        "organization_id": current_user.organization_id,
    }
    triggered = trigger_webhook_sync(db, current_user.organization_id, "webhook.test", payload)
    return {"message": "Test enviado", "triggered": triggered}


@router.get("/{webhook_id}/deliveries")
def get_deliveries(
    webhook_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Historial de entregas del webhook."""
    wh = db.get(Webhook, webhook_id)
    if not wh or wh.organization_id != current_user.organization_id:
        raise HTTPException(404, "Webhook no encontrado")

    deliveries = db.query(WebhookDelivery).filter(
        WebhookDelivery.webhook_id == webhook_id
    ).order_by(WebhookDelivery.created_at.desc()).limit(limit).all()

    return [{
        "id": d.id,
        "event": d.event,
        "success": d.success,
        "response_status": d.response_status,
        "duration_ms": d.duration_ms,
        "attempt": d.attempt,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    } for d in deliveries]
