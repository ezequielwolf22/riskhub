"""Router NIS2 — Notification Wizard (Art. 23 Directiva NIS2)."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import NIS2Notification, Incident, User
from app.security import get_current_user, require_admin, require_analyst
from app.services.audit_service import log_action
from app.services.nis2_service import (
    create_nis2_notification_chain, NIS2_STAGE_LABELS, generate_nis2_pdf
)

logger = logging.getLogger("riskhub.nis2_router")

router = APIRouter(prefix="/api/nis2", tags=["nis2"])


def _notif_to_dict(n: NIS2Notification) -> dict:
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
        "stage_label": NIS2_STAGE_LABELS.get(n.stage, n.stage),
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Estado global NIS2: incidentes activos con notificaciones requeridas."""
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
            "notifications": [_notif_to_dict(n) for n in notifs],
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Lista todas las notificaciones NIS2 de la organizacion."""
    notifs = (
        db.query(NIS2Notification)
        .filter_by(organization_id=current_user.organization_id)
        .order_by(NIS2Notification.deadline_at.asc())
        .all()
    )
    return [_notif_to_dict(n) for n in notifs]


@router.get("/notifications/{notif_id}")
def get_notification(
    notif_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    n = db.get(NIS2Notification, notif_id)
    if not n or n.organization_id != current_user.organization_id:
        raise HTTPException(404, "Notificacion no encontrada")
    return _notif_to_dict(n)


class NotifUpdate(BaseModel):
    recipient_authority: Optional[str] = None
    notification_ref: Optional[str] = None
    content_json: Optional[dict] = None


@router.patch("/notifications/{notif_id}")
def update_notification(
    notif_id: int,
    body: NotifUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Actualiza el contenido del formulario de notificacion."""
    n = db.get(NIS2Notification, notif_id)
    if not n or n.organization_id != current_user.organization_id:
        raise HTTPException(404, "Notificacion no encontrada")
    if n.status == "submitted":
        raise HTTPException(400, "No se puede modificar una notificacion ya enviada")

    if body.recipient_authority is not None:
        n.recipient_authority = body.recipient_authority
    if body.notification_ref is not None:
        n.notification_ref = body.notification_ref
    if body.content_json is not None:
        n.content_json = body.content_json

    db.commit()
    return _notif_to_dict(n)


@router.post("/notifications/{notif_id}/submit")
def submit_notification(
    notif_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Marca la notificacion como enviada con timestamp inmutable."""
    n = db.get(NIS2Notification, notif_id)
    if not n or n.organization_id != current_user.organization_id:
        raise HTTPException(404, "Notificacion no encontrada")
    if n.status == "submitted":
        raise HTTPException(409, "La notificacion ya fue enviada")

    n.status = "submitted"
    n.submitted_at = datetime.now(timezone.utc)   # timestamp inmutable
    n.submitted_by_id = current_user.id
    db.commit()
    log_action(db, current_user.id, "submit", "nis2_notification", str(notif_id),
               {"stage": n.stage, "incident_id": n.incident_id})
    return _notif_to_dict(n)


@router.get("/notifications/{notif_id}/pdf")
def download_pdf(
    notif_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Genera PDF de la notificacion en formato compatible ENISA."""
    n = db.get(NIS2Notification, notif_id)
    if not n or n.organization_id != current_user.organization_id:
        raise HTTPException(404, "Notificacion no encontrada")

    pdf_bytes = generate_nis2_pdf(n)
    if not pdf_bytes:
        raise HTTPException(500, "Error generando PDF")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="NIS2_{n.stage}_{notif_id}.pdf"'},
    )


@router.post("/incidents/{incident_id}/create-chain")
def create_chain_for_incident(
    incident_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Crea manualmente la cadena de notificaciones NIS2 para un incidente."""
    inc = db.get(Incident, incident_id)
    if not inc or inc.organization_id != current_user.organization_id:
        raise HTTPException(404, "Incidente no encontrado")

    notifs = create_nis2_notification_chain(db, incident_id, current_user.organization_id)
    return {
        "created": len(notifs),
        "notifications": [_notif_to_dict(n) for n in notifs],
    }
