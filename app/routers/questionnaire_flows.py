"""Flujos de cuestionarios encadenados segun resultado de la fase anterior."""
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import QuestionnaireFlow, QuestionnaireSchedule, Supplier, SupplierQuestionnaire, User
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.questionnaire_flows")

router = APIRouter(prefix="/api/questionnaire-flows", tags=["questionnaire-flows"])


class FlowIn(BaseModel):
    name: str
    description: Optional[str] = None
    steps: list[dict]  # [{id, name, template_code, custom_template_id, expires_days, condition}]


class FlowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[list[dict]] = None


def _flow_out(f: QuestionnaireFlow) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "description": f.description,
        "steps": f.steps or [],
        "created_by": f.created_by.full_name if f.created_by else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


@router.get("/")
def list_flows(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    flows = filter_by_org(
        db.query(QuestionnaireFlow), QuestionnaireFlow, current_user
    ).order_by(QuestionnaireFlow.name).all()
    return [_flow_out(f) for f in flows]


@router.get("/{fid}")
def get_flow(fid: int, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    f = filter_by_org(
        db.query(QuestionnaireFlow).filter(QuestionnaireFlow.id == fid),
        QuestionnaireFlow, current_user,
    ).first()
    if not f:
        raise HTTPException(404, "Flujo no encontrado")
    return _flow_out(f)


@router.post("/")
def create_flow(body: FlowIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    if not body.steps:
        raise HTTPException(400, "El flujo debe tener al menos un paso")
    f = QuestionnaireFlow(
        organization_id=current_user.organization_id,
        name=body.name,
        description=body.description,
        steps=body.steps,
        created_by_id=current_user.id,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    log_action(db, current_user.id, "create", "questionnaire_flow", str(f.id), {"name": f.name})
    return _flow_out(f)


@router.patch("/{fid}")
def update_flow(fid: int, body: FlowUpdate,
                db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    f = filter_by_org(
        db.query(QuestionnaireFlow).filter(QuestionnaireFlow.id == fid),
        QuestionnaireFlow, current_user,
    ).first()
    if not f:
        raise HTTPException(404, "Flujo no encontrado")
    if body.name is not None:
        f.name = body.name
    if body.description is not None:
        f.description = body.description
    if body.steps is not None:
        if not body.steps:
            raise HTTPException(400, "El flujo debe tener al menos un paso")
        f.steps = body.steps
    db.commit()
    db.refresh(f)
    log_action(db, current_user.id, "update", "questionnaire_flow", str(f.id))
    return _flow_out(f)


@router.delete("/{fid}", status_code=204)
def delete_flow(fid: int, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    f = filter_by_org(
        db.query(QuestionnaireFlow).filter(QuestionnaireFlow.id == fid),
        QuestionnaireFlow, current_user,
    ).first()
    if not f:
        raise HTTPException(404, "Flujo no encontrado")
    log_action(db, current_user.id, "delete", "questionnaire_flow", str(f.id), {"name": f.name})
    db.delete(f)
    db.commit()


@router.post("/{fid}/apply/{supplier_id}")
def apply_flow(
    fid: int,
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Inicia el flujo para un proveedor: crea el primer cuestionario (paso sin condicion)."""
    f = filter_by_org(
        db.query(QuestionnaireFlow).filter(QuestionnaireFlow.id == fid),
        QuestionnaireFlow, current_user,
    ).first()
    if not f:
        raise HTTPException(404, "Flujo no encontrado")
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier or not check_org_access(supplier.organization_id, current_user):
        raise HTTPException(404, "Proveedor no encontrado")

    steps = f.steps or []
    first_steps = [s for s in steps if not s.get("condition")]
    if not first_steps:
        raise HTTPException(400, "El flujo no tiene ningun paso inicial (sin condicion)")
    step = first_steps[0]

    expires_days = step.get("expires_days", 30)
    expires = datetime.now(timezone.utc) + timedelta(days=expires_days)

    # Resolver preguntas de plantilla
    from app.services import tprm_templates as _sys_tpls
    from app.routers.supplier_questionnaires import DEFAULT_QUESTIONS

    questions = DEFAULT_QUESTIONS
    template_code = None
    tpl_val = step.get("template_code")
    custom_tpl_id = step.get("custom_template_id")
    if tpl_val:
        tpl = _sys_tpls.get_template(tpl_val)
        if tpl:
            questions = tpl["questions"]
            template_code = tpl["code"]
    elif custom_tpl_id:
        from app.models import TPRMTemplate
        tpl = db.query(TPRMTemplate).filter(TPRMTemplate.id == custom_tpl_id).first()
        if tpl and check_org_access(tpl.organization_id, current_user):
            questions = tpl.questions or []
            template_code = f"custom:{tpl.id}"

    from sqlalchemy import func as _func
    max_id = db.query(_func.max(SupplierQuestionnaire.id)).scalar() or 0
    code = f"SEQ-{max_id + 1:04d}"
    title = step.get("name") or f"Evaluacion — Flujo {f.name}"
    q = SupplierQuestionnaire(
        code=code,
        supplier_id=supplier_id,
        title=title,
        token=secrets.token_urlsafe(32),
        template_code=template_code,
        questions=questions,
        expires_at=expires,
        notes=f"Iniciado por flujo: {f.name}",
        created_by_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    log_action(db, current_user.id, "apply_flow", "questionnaire_flow", str(f.id),
               {"supplier": supplier.name, "questionnaire": q.code})
    return {
        "questionnaire_id": q.id,
        "questionnaire_code": q.code,
        "token": q.token,
        "title": q.title,
    }
