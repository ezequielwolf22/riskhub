"""CRUD de riesgos + calculo automatico inherente/residual + tratamiento."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Asset, ControlImplementation, Risk, RiskContext, RiskStatus,
    Threat, TreatmentOption, User, Vulnerability, risk_control_table,
)
from app.schemas import RiskIn, RiskOut, RiskUpdate
from app.security import get_current_user, require_analyst
from app.services.audit_service import log_action
from app.services.risk_engine import calc_level, calc_residual

router = APIRouter(prefix="/api/risks", tags=["risks"])


def _next_code(db: Session) -> str:
    n = db.query(Risk).count() + 1
    return f"RSK-{n:04d}"


def _get_matrix(db: Session):
    ctx = db.query(RiskContext).first()
    return ctx.risk_matrix if ctx and ctx.risk_matrix else None


def _recalc(db: Session, risk: Risk) -> None:
    matrix = _get_matrix(db)
    risk.inherent_level = calc_level(
        risk.inherent_consequence, risk.inherent_likelihood, matrix)
    controls = [{"maturity": ci.maturity, "contribution": 1.0} for ci in risk.controls]
    rl, rc, rlev = calc_residual(
        risk.inherent_likelihood, risk.inherent_consequence, controls, matrix)
    risk.residual_likelihood = rl
    risk.residual_consequence = rc
    risk.residual_level = rlev


@router.get("/", response_model=list[RiskOut])
def list_risks(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    asset_id: Optional[int] = None,
    status: Optional[RiskStatus] = None,
    min_level: Optional[int] = Query(None, ge=0, le=8),
):
    q = db.query(Risk)
    if asset_id:
        q = q.filter(Risk.asset_id == asset_id)
    if status:
        q = q.filter(Risk.status == status)
    if min_level is not None:
        q = q.filter(Risk.residual_level >= min_level)
    return q.order_by(Risk.residual_level.desc(), Risk.code).all()


@router.get("/{risk_id}", response_model=RiskOut)
def get_risk(risk_id: int, db: Session = Depends(get_db),
             _: User = Depends(get_current_user)):
    r = db.get(Risk, risk_id)
    if not r:
        raise HTTPException(404, "Riesgo no encontrado")
    return r


@router.post("/", response_model=RiskOut, status_code=201)
def create_risk(data: RiskIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    if not db.get(Asset, data.asset_id):
        raise HTTPException(400, "asset_id no existe")
    if not db.get(Threat, data.threat_id):
        raise HTTPException(400, "threat_id no existe")
    existing = db.query(Risk).filter(
        Risk.asset_id == data.asset_id, Risk.threat_id == data.threat_id).first()
    if existing:
        raise HTTPException(400, f"Ya existe un riesgo para ese activo y amenaza ({existing.code})")

    r = Risk(
        code=_next_code(db),
        asset_id=data.asset_id, threat_id=data.threat_id,
        description=data.description,
        consequence_description=data.consequence_description,
        inherent_likelihood=data.inherent_likelihood,
        inherent_consequence=data.inherent_consequence,
        owner_id=data.owner_id,
        treatment_option=data.treatment_option,
        treatment_plan=data.treatment_plan,
        treatment_due_date=data.treatment_due_date,
        status=RiskStatus.ASSESSED,
    )
    if data.vulnerability_ids:
        r.vulnerabilities = db.query(Vulnerability).filter(
            Vulnerability.id.in_(data.vulnerability_ids)).all()
    if data.control_implementation_ids:
        r.controls = db.query(ControlImplementation).filter(
            ControlImplementation.id.in_(data.control_implementation_ids)).all()
    _recalc(db, r)
    db.add(r)
    log_action(db, current_user.id, "create", "risk", None,
               {"asset_id": data.asset_id, "threat_id": data.threat_id})
    db.commit(); db.refresh(r)
    return r


@router.patch("/{risk_id}", response_model=RiskOut)
def update_risk(risk_id: int, data: RiskUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_analyst)):
    r = db.get(Risk, risk_id)
    if not r:
        raise HTTPException(404, "Riesgo no encontrado")

    update_data = data.model_dump(exclude_unset=True)
    if "vulnerability_ids" in update_data:
        ids = update_data.pop("vulnerability_ids")
        r.vulnerabilities = db.query(Vulnerability).filter(
            Vulnerability.id.in_(ids or [])).all()
    if "control_implementation_ids" in update_data:
        ids = update_data.pop("control_implementation_ids")
        r.controls = db.query(ControlImplementation).filter(
            ControlImplementation.id.in_(ids or [])).all()

    # Acceptance bookkeeping
    if update_data.get("status") == RiskStatus.ACCEPTED:
        r.accepted_by_id = user.id
        r.accepted_at = datetime.now(timezone.utc)

    for k, v in update_data.items():
        setattr(r, k, v)
    _recalc(db, r)
    log_action(db, user.id, "update", "risk", str(risk_id),
               {"code": r.code, "status": str(r.status), "residual_level": r.residual_level})
    db.commit(); db.refresh(r)
    return r


@router.delete("/{risk_id}", status_code=204)
def delete_risk(risk_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    r = db.get(Risk, risk_id)
    if not r:
        raise HTTPException(404, "Riesgo no encontrado")
    code = r.code
    db.delete(r)
    log_action(db, current_user.id, "delete", "risk", str(risk_id), {"code": code})
    db.commit()


@router.get("/heatmap/data")
def heatmap(db: Session = Depends(get_db),
            _: User = Depends(get_current_user),
            mode: str = Query("residual", regex="^(residual|inherent)$")):
    """Devuelve matriz 5x5 con conteo y referencias de riesgo."""
    matrix = [[{"count": 0, "risks": []} for _ in range(5)] for _ in range(5)]
    for r in db.query(Risk).all():
        if mode == "residual":
            x, y = r.residual_likelihood, r.residual_consequence
        else:
            x, y = r.inherent_likelihood, r.inherent_consequence
        x = max(0, min(4, x)); y = max(0, min(4, y))
        matrix[4 - y][x]["count"] += 1
        matrix[4 - y][x]["risks"].append({
            "id": r.id, "code": r.code,
            "asset": r.asset.name if r.asset else "",
            "threat": r.threat.name if r.threat else "",
            "level": r.residual_level if mode == "residual" else r.inherent_level,
        })
    return {"mode": mode, "matrix": matrix}


@router.get("/stats/summary")
def summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Resumen para el dashboard."""
    now = datetime.now(timezone.utc)
    risks = db.query(Risk).all()
    by_band = {"low": 0, "medium": 0, "high": 0}
    for r in risks:
        if r.residual_level <= 2: by_band["low"] += 1
        elif r.residual_level <= 5: by_band["medium"] += 1
        else: by_band["high"] += 1
    by_status = {s.value: 0 for s in RiskStatus}
    for r in risks:
        by_status[r.status.value] += 1
    by_treatment = {t.value: 0 for t in TreatmentOption}
    for r in risks:
        if r.treatment_option:
            by_treatment[r.treatment_option.value] += 1

    # Metricas adicionales
    active_statuses = {RiskStatus.IDENTIFIED, RiskStatus.ANALYZED, RiskStatus.EVALUATED}
    active_risks = [r for r in risks if r.status in active_statuses]
    overdue = sum(
        1 for r in active_risks
        if r.treatment_due_date and r.treatment_due_date.replace(tzinfo=timezone.utc) < now
    )
    no_treatment_high = sum(
        1 for r in active_risks
        if r.residual_level >= 5 and not r.treatment_option
    )
    total_inh = sum(r.inherent_level for r in risks)
    total_res = sum(r.residual_level for r in risks)
    reduction_pct = round((1 - total_res / total_inh) * 100) if total_inh else 0

    return {
        "total_risks": len(risks),
        "total_assets": db.query(Asset).count(),
        "total_threats": db.query(Threat).count(),
        "total_vulnerabilities": db.query(Vulnerability).count(),
        "total_controls": db.query(ControlImplementation).count(),
        "by_band": by_band,
        "by_status": by_status,
        "by_treatment": by_treatment,
        "overdue_treatments": overdue,
        "no_treatment_high": no_treatment_high,
        "risk_reduction_pct": reduction_pct,
        "top_risks": [
            {"code": r.code, "asset": r.asset.name if r.asset else "",
             "threat": r.threat.name if r.threat else "",
             "level": r.residual_level, "id": r.id}
            for r in sorted(risks, key=lambda x: -x.residual_level)[:10]
        ],
    }
