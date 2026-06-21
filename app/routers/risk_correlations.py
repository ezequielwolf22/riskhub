"""Correlaciones entre riesgos: gestion de pares correlados para VaR agregado (v5.3.0)."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Risk, RiskCorrelation, User
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/risk-correlations", tags=["risk-correlations"])


class CorrelationCreate(BaseModel):
    risk_id_a: int
    risk_id_b: int
    correlation_factor: float = Field(default=0.5, ge=0.0, le=1.0)
    description: Optional[str] = None


class CorrelationUpdate(BaseModel):
    correlation_factor: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    description: Optional[str] = None


class CorrelationOut(BaseModel):
    id: int
    organization_id: int
    risk_id_a: int
    risk_id_b: int
    correlation_factor: float
    description: Optional[str]
    created_at: Optional[datetime]
    risk_a_code: Optional[str] = None
    risk_b_code: Optional[str] = None

    model_config = {"from_attributes": True}


def _enrich(corr: RiskCorrelation, db: Session) -> dict:
    ra = db.get(Risk, corr.risk_id_a)
    rb = db.get(Risk, corr.risk_id_b)
    return {
        "id": corr.id,
        "organization_id": corr.organization_id,
        "risk_id_a": corr.risk_id_a,
        "risk_id_b": corr.risk_id_b,
        "correlation_factor": corr.correlation_factor,
        "description": corr.description,
        "created_at": corr.created_at,
        "risk_a_code": ra.code if ra else None,
        "risk_a_name": ra.name[:60] if ra else None,
        "risk_b_code": rb.code if rb else None,
        "risk_b_name": rb.name[:60] if rb else None,
    }


@router.get("/")
def list_correlations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    risk_id: Optional[int] = None,
):
    q = filter_by_org(db.query(RiskCorrelation), RiskCorrelation, current_user)
    if risk_id is not None:
        q = q.filter(
            (RiskCorrelation.risk_id_a == risk_id) | (RiskCorrelation.risk_id_b == risk_id)
        )
    return [_enrich(c, db) for c in q.all()]


@router.post("/", status_code=201)
def create_correlation(
    body: CorrelationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    org_id = current_user.organization_id
    ra = db.get(Risk, body.risk_id_a)
    rb = db.get(Risk, body.risk_id_b)
    if not ra or not check_org_access(ra.organization_id, current_user):
        raise HTTPException(404, f"Riesgo {body.risk_id_a} no encontrado")
    if not rb or not check_org_access(rb.organization_id, current_user):
        raise HTTPException(404, f"Riesgo {body.risk_id_b} no encontrado")
    if body.risk_id_a == body.risk_id_b:
        raise HTTPException(400, "Un riesgo no puede correlacionarse consigo mismo")

    # Evitar duplicados
    existing = db.query(RiskCorrelation).filter(
        RiskCorrelation.organization_id == org_id,
        (
            ((RiskCorrelation.risk_id_a == body.risk_id_a) & (RiskCorrelation.risk_id_b == body.risk_id_b))
            | ((RiskCorrelation.risk_id_a == body.risk_id_b) & (RiskCorrelation.risk_id_b == body.risk_id_a))
        ),
    ).first()
    if existing:
        raise HTTPException(409, f"Ya existe correlacion entre {ra.code} y {rb.code}")

    corr = RiskCorrelation(
        organization_id=org_id,
        risk_id_a=body.risk_id_a,
        risk_id_b=body.risk_id_b,
        correlation_factor=body.correlation_factor,
        description=body.description,
        created_at=datetime.now(timezone.utc),
    )
    db.add(corr)
    db.commit()
    db.refresh(corr)
    log_action(db, current_user.id, "create", "risk_correlation", str(corr.id),
               {"a": ra.code, "b": rb.code, "factor": body.correlation_factor})
    return _enrich(corr, db)


@router.patch("/{cid}")
def update_correlation(
    cid: int,
    body: CorrelationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    corr = db.get(RiskCorrelation, cid)
    if not corr or not check_org_access(corr.organization_id, current_user):
        raise HTTPException(404, "Correlacion no encontrada")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(corr, field, value)
    db.commit()
    log_action(db, current_user.id, "update", "risk_correlation", str(cid))
    return _enrich(corr, db)


@router.delete("/{cid}", status_code=204)
def delete_correlation(
    cid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    corr = db.get(RiskCorrelation, cid)
    if not corr or not check_org_access(corr.organization_id, current_user):
        raise HTTPException(404, "Correlacion no encontrada")
    log_action(db, current_user.id, "delete", "risk_correlation", str(cid))
    db.delete(corr)
    db.commit()
