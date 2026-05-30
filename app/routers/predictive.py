"""Router de análisis predictivo."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import get_current_user
from app.services.predictive_service import (
    get_risk_trend_analysis,
    get_maturity_path,
    get_high_risk_assets,
    get_threat_forecast,
)

router = APIRouter(prefix="/api/predictive", tags=["predictive"])


@router.get("/trend")
def risk_trend(
    days: int = Query(90, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    return get_risk_trend_analysis(db, org_id, days)


@router.get("/maturity-path")
def maturity_path(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    return get_maturity_path(db, org_id)


@router.get("/high-risk-assets")
def high_risk_assets(
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    return get_high_risk_assets(db, org_id, limit)


@router.get("/threat-forecast")
def threat_forecast(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    return get_threat_forecast(db, org_id)
