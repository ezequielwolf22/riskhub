"""Contexto de riesgos: criterios, matriz, apetito - ISO 27005 cl. 7."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RiskContext, User
from app.schemas import ContextIn, ContextOut
from app.security import get_current_user, require_admin

router = APIRouter(prefix="/api/context", tags=["context"])


@router.get("/", response_model=ContextOut)
def get_context(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    ctx = db.query(RiskContext).first()
    return ctx


@router.put("/", response_model=ContextOut, dependencies=[Depends(require_admin)])
def update_context(data: ContextIn, db: Session = Depends(get_db)):
    ctx = db.query(RiskContext).first()
    if not ctx:
        ctx = RiskContext()
        db.add(ctx)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(ctx, k, v)
    db.commit(); db.refresh(ctx)
    return ctx
