"""Router de Management Review — ISO 27001 cl. 9.3."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import ManagementReview, User
from app.security import get_current_user, require_admin, require_analyst
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.management_review")

router = APIRouter(prefix="/api/management-review", tags=["management-review"])


class MRCreate(BaseModel):
    review_date: Optional[str] = None
    attendees: Optional[list] = None
    input_changes_context: Optional[str] = None


class MRUpdate(BaseModel):
    review_date: Optional[str] = None
    attendees: Optional[list] = None
    input_changes_context: Optional[str] = None
    output_decisions: Optional[list] = None
    output_resources: Optional[str] = None
    output_objectives: Optional[list] = None
    status: Optional[str] = None


def _mr_to_dict(mr: ManagementReview) -> dict:
    return {
        "id": mr.id,
        "organization_id": mr.organization_id,
        "code": mr.code,
        "review_date": mr.review_date.isoformat() if mr.review_date else None,
        "status": mr.status,
        "attendees": mr.attendees,
        "input_previous_actions": mr.input_previous_actions,
        "input_changes_context": mr.input_changes_context,
        "input_performance_data": mr.input_performance_data,
        "input_nc_corrections": mr.input_nc_corrections,
        "input_risk_register": mr.input_risk_register,
        "input_audit_results": mr.input_audit_results,
        "output_decisions": mr.output_decisions,
        "output_resources": mr.output_resources,
        "output_objectives": mr.output_objectives,
        "approved_by_id": mr.approved_by_id,
        "approved_at": mr.approved_at.isoformat() if mr.approved_at else None,
        "created_at": mr.created_at.isoformat() if mr.created_at else None,
    }


@router.get("")
def list_reviews(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Lista revisiones por la direccion de la organizacion."""
    org_id = current_user.organization_id
    reviews = (
        db.query(ManagementReview)
        .filter_by(organization_id=org_id)
        .order_by(ManagementReview.created_at.desc())
        .all()
    )
    return [_mr_to_dict(r) for r in reviews]


@router.post("", status_code=201)
def create_review(
    body: MRCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Crea una nueva revision por la direccion (o usa el borrador auto-preparado del mes)."""
    from app.services.management_review_service import prepare_monthly_review
    org_id = current_user.organization_id

    # Si ya hay borrador del mes, devolverlo
    mr = prepare_monthly_review(db, org_id)

    if body.review_date:
        try:
            mr.review_date = datetime.fromisoformat(body.review_date)
        except ValueError:
            pass
    if body.attendees is not None:
        mr.attendees = body.attendees
    if body.input_changes_context:
        mr.input_changes_context = body.input_changes_context

    db.commit()
    log_action(db, current_user.id, "create", "management_review", str(mr.id), {"code": mr.code})
    return _mr_to_dict(mr)


@router.get("/{mr_id}")
def get_review(
    mr_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    mr = db.get(ManagementReview, mr_id)
    if not mr or mr.organization_id != current_user.organization_id:
        raise HTTPException(404, "Revision no encontrada")
    return _mr_to_dict(mr)


@router.patch("/{mr_id}")
def update_review(
    mr_id: int,
    body: MRUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    mr = db.get(ManagementReview, mr_id)
    if not mr or mr.organization_id != current_user.organization_id:
        raise HTTPException(404, "Revision no encontrada")

    if mr.status == "approved":
        raise HTTPException(400, "No se puede modificar una revision ya aprobada")

    if body.review_date is not None:
        try:
            mr.review_date = datetime.fromisoformat(body.review_date)
        except ValueError:
            pass
    if body.attendees is not None:
        mr.attendees = body.attendees
    if body.input_changes_context is not None:
        mr.input_changes_context = body.input_changes_context
    if body.output_decisions is not None:
        mr.output_decisions = body.output_decisions
    if body.output_resources is not None:
        mr.output_resources = body.output_resources
    if body.output_objectives is not None:
        mr.output_objectives = body.output_objectives
    if body.status in ("draft", "conducted"):
        mr.status = body.status

    db.commit()
    log_action(db, current_user.id, "update", "management_review", str(mr_id), {})
    return _mr_to_dict(mr)


@router.post("/{mr_id}/conduct")
def conduct_review(
    mr_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Marca la revision como celebrada."""
    mr = db.get(ManagementReview, mr_id)
    if not mr or mr.organization_id != current_user.organization_id:
        raise HTTPException(404, "Revision no encontrada")
    if mr.status not in ("draft",):
        raise HTTPException(400, f"Estado actual '{mr.status}' no permite esta transicion")

    mr.status = "conducted"
    db.commit()
    log_action(db, current_user.id, "conduct", "management_review", str(mr_id), {})
    return _mr_to_dict(mr)


@router.post("/{mr_id}/approve")
def approve_review(
    mr_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin aprueba la revision y congela el acta."""
    mr = db.get(ManagementReview, mr_id)
    if not mr or mr.organization_id != current_user.organization_id:
        raise HTTPException(404, "Revision no encontrada")
    if mr.status not in ("conducted", "draft"):
        raise HTTPException(400, "Solo se pueden aprobar revisiones en estado 'conducted' o 'draft'")

    # Validar campos obligatorios ISO 9.3.3
    if not mr.review_date:
        raise HTTPException(422, "La fecha de revisión es obligatoria (ISO 9.3.3)")
    if not mr.output_decisions:
        raise HTTPException(422, "Las decisiones de salida son obligatorias (ISO 9.3.3)")
    if not mr.attendees:
        raise HTTPException(422, "Los asistentes son obligatorios para la validez del acta (ISO 9.3.3)")

    mr.status = "approved"
    mr.approved_by_id = current_user.id
    mr.approved_at = datetime.now(timezone.utc)
    db.commit()
    log_action(db, current_user.id, "approve", "management_review", str(mr_id), {})
    return _mr_to_dict(mr)


@router.get("/{mr_id}/pdf")
def download_pdf(
    mr_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Genera y descarga el acta PDF de la revision."""
    mr = db.get(ManagementReview, mr_id)
    if not mr or mr.organization_id != current_user.organization_id:
        raise HTTPException(404, "Revision no encontrada")

    from app.services.management_review_service import generate_minutes_pdf
    pdf_bytes = generate_minutes_pdf(mr)
    if not pdf_bytes:
        raise HTTPException(500, "Error generando PDF")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="acta_{mr.code or mr_id}.pdf"'},
    )
