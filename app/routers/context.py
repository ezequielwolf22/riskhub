"""Contexto de riesgos: criterios, matriz, apetito - ISO 27005 cl. 7."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RiskContext, User
from app.schemas import ContextIn, ContextOut
from app.security import get_current_user, require_admin
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/context", tags=["context"])


@router.get("/", response_model=ContextOut)
def get_context(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    ctx = db.query(RiskContext).first()
    return ctx


@router.put("/", response_model=ContextOut)
def update_context(data: ContextIn, db: Session = Depends(get_db),
                   current_user: User = Depends(require_admin)):
    ctx = db.query(RiskContext).first()
    if not ctx:
        ctx = RiskContext()
        db.add(ctx)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(ctx, k, v)
    log_action(db, current_user.id, "update", "context", "1",
               {"organization": ctx.organization_name, "risk_appetite": ctx.risk_appetite})
    db.commit(); db.refresh(ctx)
    return ctx
