"""Contexto de riesgos: criterios, matriz, apetito - ISO 27005 cl. 7."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Risk, RiskContext, RiskStatus, TreatmentOption, User
from app.schemas import ContextIn, ContextOut
from app.security import filter_by_org, get_current_user, require_admin
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/context", tags=["context"])


@router.get("/", response_model=ContextOut)
def get_context(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ctx = filter_by_org(db.query(RiskContext), RiskContext, current_user).first()
    return ctx


@router.put("/", response_model=ContextOut)
def update_context(data: ContextIn, db: Session = Depends(get_db),
                   current_user: User = Depends(require_admin)):
    ctx = filter_by_org(db.query(RiskContext), RiskContext, current_user).first()
    if not ctx:
        ctx = RiskContext(organization_id=current_user.organization_id)
        db.add(ctx)

    old_appetite = ctx.risk_appetite
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(ctx, k, v)
    new_appetite = ctx.risk_appetite

    log_action(db, current_user.id, "update", "context", "1",
               {"organization": ctx.organization_name, "risk_appetite": ctx.risk_appetite})
    db.commit(); db.refresh(ctx)

    # Si cambia el apetito de riesgo, recalcular tratamientos en bulk
    if new_appetite is not None and new_appetite != old_appetite:
        _apply_appetite_bulk(db, current_user.organization_id, new_appetite)

    return ctx


def _apply_appetite_bulk(db: Session, org_id: int, appetite: int) -> None:
    """Aplica ACCEPTANCE automaticamente a todos los riesgos cuyo nivel residual
    no supera el nuevo apetito de la organizacion."""
    active_risks = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.status.notin_([RiskStatus.CLOSED]),
    ).all()
    updated = 0
    for r in active_risks:
        if r.residual_level is not None and r.residual_level <= appetite:
            if r.treatment_option in (None, TreatmentOption.MODIFICATION, TreatmentOption.RETENTION):
                r.treatment_option = TreatmentOption.ACCEPTANCE
                if r.status in (RiskStatus.IDENTIFIED, RiskStatus.ASSESSED):
                    r.status = RiskStatus.ACCEPTED
                updated += 1
    if updated:
        db.commit()
