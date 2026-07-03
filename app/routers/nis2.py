"""Router NIS2 — Notification Wizard (Art. 23 Directiva NIS2)."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import NIS2Notification, Incident, User
from app.security import get_current_user, require_admin, require_analyst
from app.services.audit_service import log_action
from app.services.nis2_service import (
    create_nis2_notification_chain, nis2_stage_label, generate_nis2_pdf
)

logger = logging.getLogger("riskhub.nis2_router")

router = APIRouter(prefix="/api/nis2", tags=["nis2"])


def _notif_to_dict(n: NIS2Notification, lang: str = "es") -> dict:
    now = datetime.now(timezone.utc)
    deadline = n.deadline_at
    if deadline and not deadline.tzinfo:
        deadline = deadline.replace(tzinfo=timezone.utc)
    hours_left = (deadline - now).total_seconds() / 3600 if deadline else None

    return {
        "id": n.id,
        "organization_id": n.organization_id,
        "incident_id": n.incident_id,
        "stage": n.stage,
        "stage_label": nis2_stage_label(n.stage, lang),
        "deadline_at": n.deadline_at.isoformat() if n.deadline_at else None,
        "hours_left": round(hours_left, 1) if hours_left is not None else None,
        "submitted_at": n.submitted_at.isoformat() if n.submitted_at else None,
        "recipient_authority": n.recipient_authority,
        "notification_ref": n.notification_ref,
        "content_json": n.content_json,
        "status": n.status,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("/dashboard")
def nis2_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Estado global NIS2: incidentes activos con notificaciones requeridas."""
    lang = get_lang(request)
    org_id = current_user.organization_id

    incidents_nis2 = db.query(Incident).filter(
        Incident.organization_id == org_id,
        Incident.nis2_notification_required.is_(True),
    ).all()

    result = []
    for inc in incidents_nis2:
        notifs = db.query(NIS2Notification).filter_by(
            incident_id=inc.id, organization_id=org_id
        ).all()
        result.append({
            "incident_id": inc.id,
            "incident_code": inc.code,
            "incident_title": inc.title,
            "incident_status": inc.status.value if inc.status else "open",
            "detected_at": inc.detected_at.isoformat() if inc.detected_at else None,
            "notifications": [_notif_to_dict(n, lang) for n in notifs],
        })

    pending_count = db.query(NIS2Notification).filter(
        NIS2Notification.organization_id == org_id,
        NIS2Notification.status == "pending",
    ).count()
    overdue_count = db.query(NIS2Notification).filter(
        NIS2Notification.organization_id == org_id,
        NIS2Notification.status == "overdue",
    ).count()

    return {
        "incidents_requiring_notification": len(incidents_nis2),
        "pending_notifications": pending_count,
        "overdue_notifications": overdue_count,
        "incidents": result,
    }


@router.get("/notifications")
def list_notifications(
    request: Request,
    status: Optional[str] = None,
    overdue: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Lista notificaciones NIS2 de la organizacion con filtros opcionales."""
    lang = get_lang(request)
    q = (
        db.query(NIS2Notification)
        .filter(NIS2Notification.organization_id == current_user.organization_id)
    )
    if status and overdue is True:
        from sqlalchemy import or_
        q = q.filter(or_(NIS2Notification.status == status, NIS2Notification.status == "overdue"))
    elif status:
        q = q.filter(NIS2Notification.status == status)
    elif overdue is True:
        q = q.filter(NIS2Notification.status == "overdue")
    notifs = q.order_by(NIS2Notification.deadline_at.asc()).all()
    return [_notif_to_dict(n, lang) for n in notifs]


@router.get("/notifications/{notif_id}")
def get_notification(
    notif_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    n = db.get(NIS2Notification, notif_id)
    if not n or n.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("nis2.notification_not_found", lang))
    return _notif_to_dict(n, lang)


class NotifUpdate(BaseModel):
    recipient_authority: Optional[str] = None
    notification_ref: Optional[str] = None
    content_json: Optional[dict] = None


@router.patch("/notifications/{notif_id}")
def update_notification(
    notif_id: int,
    body: NotifUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Actualiza el contenido del formulario de notificacion."""
    lang = get_lang(request)
    n = db.get(NIS2Notification, notif_id)
    if not n or n.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("nis2.notification_not_found", lang))
    if n.status == "submitted":
        raise HTTPException(400, _t("nis2.cannot_modify_submitted", lang))

    if body.recipient_authority is not None:
        n.recipient_authority = body.recipient_authority
    if body.notification_ref is not None:
        n.notification_ref = body.notification_ref
    if body.content_json is not None:
        n.content_json = body.content_json

    db.commit()
    return _notif_to_dict(n, lang)


@router.post("/notifications/{notif_id}/submit")
def submit_notification(
    notif_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Marca la notificacion como enviada con timestamp inmutable."""
    lang = get_lang(request)
    n = db.get(NIS2Notification, notif_id)
    if not n or n.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("nis2.notification_not_found", lang))
    if n.status == "submitted":
        raise HTTPException(409, _t("nis2.already_submitted", lang))

    n.status = "submitted"
    n.submitted_at = datetime.now(timezone.utc)   # timestamp inmutable
    n.submitted_by_id = current_user.id
    db.commit()
    log_action(db, current_user.id, "submit", "nis2_notification", str(notif_id),
               {"stage": n.stage, "incident_id": n.incident_id})
    return _notif_to_dict(n, lang)


@router.get("/notifications/{notif_id}/pdf")
def download_pdf(
    notif_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Genera PDF de la notificacion en formato compatible ENISA."""
    lang = get_lang(request)
    n = db.get(NIS2Notification, notif_id)
    if not n or n.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("nis2.notification_not_found", lang))

    pdf_bytes = generate_nis2_pdf(n, lang)
    if not pdf_bytes:
        raise HTTPException(500, _t("nis2.pdf_error", lang))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="NIS2_{n.stage}_{notif_id}.pdf"'},
    )


@router.post("/incidents/{incident_id}/create-chain")
def create_chain_for_incident(
    incident_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Crea manualmente la cadena de notificaciones NIS2 para un incidente."""
    lang = get_lang(request)
    inc = db.get(Incident, incident_id)
    if not inc or inc.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("nis2.incident_not_found", lang))

    notifs = create_nis2_notification_chain(db, incident_id, current_user.organization_id)
    return {
        "created": len(notifs),
        "notifications": [_notif_to_dict(n, lang) for n in notifs],
    }
