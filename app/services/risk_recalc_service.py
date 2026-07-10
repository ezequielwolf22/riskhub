"""Autoridad unica de recalculo de riesgos (motor v2).

Principio: la IA propone entradas (inherentes calibrados, contribuciones de
controles); este servicio calcula el residual de forma determinista y
trazable. Nunca al reves.

Factores que intervienen en el residual:
  - contribution real de la tabla risk_controls
  - tipo de control P/D/C (classify_control) -> reduccion separada
    de probabilidad e impacto
  - madurez ajustada por calidad de evidencia (adjusted_maturity):
    un control 5/5 sin evidencia no reduce igual que uno con pentest
  - penalizaciones por NC major abierta y fallo CCM
  - floor por controles obligatorios con madurez < 2
  - auto-aceptacion segun apetito de riesgo de la organizacion
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

from app.models import (
    Asset, Risk, RiskContext, RiskStatus, Threat, TreatmentOption,
    risk_control_table,
)
from app.services.risk_analysis_helpers import adjusted_maturity, classify_control
from app.services.risk_engine import (
    MAGERIT_DIM_FIELD, calc_consequence_magerit, calc_level, calc_residual,
    primary_dimension_for_threat,
)

logger = logging.getLogger(__name__)


def get_context(db: Session, org_id=None) -> RiskContext | None:
    q = db.query(RiskContext)
    if org_id:
        q = q.filter(RiskContext.organization_id == org_id)
    return q.first()


def get_matrix(db: Session, org_id=None):
    ctx = get_context(db, org_id)
    return ctx.risk_matrix if ctx and ctx.risk_matrix else None


def apply_magerit_consequence(risk: Risk, db: Session) -> None:
    """Si la metodologia del contexto es magerit|combined y el riesgo tiene
    dimension + degradacion, recalcula inherent_consequence desde el activo."""
    if not risk.asset_id:
        return
    ctx = get_context(db, risk.organization_id)
    if not ctx or ctx.methodology not in ("magerit", "combined"):
        return
    if risk.degradation_pct is None:
        return

    asset = db.get(Asset, risk.asset_id)
    if not asset:
        return

    # Determinar dimension primaria si no esta guardada
    if not risk.magerit_dimension:
        threat = db.get(Threat, risk.threat_id)
        affects = getattr(threat, "affects", None) or []
        risk.magerit_dimension = primary_dimension_for_threat(affects, asset)

    field = MAGERIT_DIM_FIELD.get(risk.magerit_dimension, "value_availability")
    dim_value = getattr(asset, field, 0) or 0
    consequence, magerit_impact = calc_consequence_magerit(dim_value, risk.degradation_pct)
    risk.inherent_consequence = consequence
    risk.magerit_impact = magerit_impact


def _ai_evidence_factor(db: Session | None, ci) -> float | None:
    """Factor de calidad E1-E5 desde evidencias del modulo central analizadas
    por IA (evidence understanding). None si no hay ninguna analizada."""
    if db is None:
        return None
    try:
        from app.models import Evidence
        from app.services.evidence_understanding_service import QUALITY_LEVEL_FACTOR
        rows = (
            db.query(Evidence.ai_review)
            .filter(
                Evidence.control_implementation_id == ci.id,
                Evidence.is_current == True,  # noqa: E712
                Evidence.ai_review.isnot(None),
            ).all()
        )
        best = None
        for (review,) in rows:
            review = review or {}
            factor = QUALITY_LEVEL_FACTOR.get(str(review.get("quality_level", "")).upper())
            if factor is None:
                continue
            if review.get("relevant") is False:
                factor = QUALITY_LEVEL_FACTOR["E1"]
            best = factor if best is None else max(best, factor)
        return best
    except Exception:
        logger.debug("_ai_evidence_factor fallo", exc_info=True)
        return None


def control_payload(ci, contribution: float = 1.0, db: Session | None = None) -> dict:
    """Convierte una ControlImplementation al dict que consume el motor.

    La madurez que entra al calculo es la ajustada por calidad de evidencia
    (heuristica sobre evidence_refs y, si existe, la revision IA del contenido
    real de las evidencias vinculadas — gana la mejor de las dos), y el tipo
    P/D/C determina que eje (probabilidad/impacto) reduce.
    """
    ctrl = ci.control
    maturity_adj = adjusted_maturity(ci.maturity or 0, ci.evidence_refs or [])
    ai_factor = _ai_evidence_factor(db, ci)
    if ai_factor is not None:
        maturity_adj = max(maturity_adj, round((ci.maturity or 0) * ai_factor, 1))
    return {
        "maturity": maturity_adj,
        "contribution": contribution,
        "nc_penalty_factor": getattr(ci, "nc_penalty_factor", None),
        "ccm_fail": getattr(ci, "ccm_last_status", None) == "FAIL",
        "ctype": classify_control(
            ctrl.code if ctrl else "", ctrl.name if ctrl else ""),
    }


def recalc_risk(db: Session, risk: Risk) -> None:
    """Recalcula inherente/residual/tratamiento de un riesgo (in-place, sin commit)."""
    matrix = get_matrix(db, risk.organization_id)

    # MAGERIT: si aplica, sobrescribir inherent_consequence antes de calcular
    apply_magerit_consequence(risk, db)

    risk.inherent_level = calc_level(
        risk.inherent_consequence, risk.inherent_likelihood, matrix)

    # Obtener contribution real de la tabla de asociacion (no hardcoded 1.0)
    rows = db.execute(
        _text("SELECT control_implementation_id, contribution FROM risk_controls WHERE risk_id = :rid"),
        {"rid": risk.id},
    ).fetchall()
    contrib_map = {row[0]: (row[1] if row[1] is not None else 1.0) for row in rows}

    controls = [
        control_payload(ci, contrib_map.get(ci.id, 1.0), db=db)
        for ci in risk.controls
    ]
    rl, rc, rlev = calc_residual(
        risk.inherent_likelihood, risk.inherent_consequence, controls, matrix)

    # Floor por controles obligatorios con madurez insuficiente (ISO 27001 Annex A)
    # Si algun control IS_MANDATORY tiene maturity < 2, el residual no puede ser
    # menor que inherent - 1 (los controles deficientes limitan la reduccion alcanzable)
    mandatory_gap = any(
        (ci.control.is_mandatory if ci.control else False) and (ci.maturity or 0) < 2
        for ci in risk.controls
    )
    if mandatory_gap:
        min_lik = max(0, (risk.inherent_likelihood or 0) - 1)
        min_con = max(0, (risk.inherent_consequence or 0) - 1)
        rl = max(rl, min_lik)
        rc = max(rc, min_con)
        rlev = calc_level(rc, rl, matrix)

    risk.residual_likelihood = rl
    risk.residual_consequence = rc
    risk.residual_level = rlev

    # Auto-tratamiento basado en apetito de riesgo
    ctx = get_context(db, risk.organization_id)
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3
    if rlev <= appetite and risk.status not in (RiskStatus.CLOSED, RiskStatus.PENDING_ACCEPTANCE):
        if risk.treatment_option in (None, TreatmentOption.MODIFICATION, TreatmentOption.RETENTION):
            risk.treatment_option = TreatmentOption.RETENTION
            if risk.status in (RiskStatus.IDENTIFIED, RiskStatus.ASSESSED):
                risk.status = RiskStatus.ACCEPTED
                # Riesgos aceptados deben revisarse anualmente (ISO 27001 A.6.1.2)
                risk.next_review = datetime.now(timezone.utc) + timedelta(days=365)
                risk.accepted_at = datetime.now(timezone.utc)


def mark_risks_stale_for_impls(db: Session, impl_ids: list[int], reason: str) -> int:
    """Marca como desactualizado el analisis IA de los riesgos vinculados
    a estos controles. El recalculo determinista es gratis y se hace aparte;
    esta marca indica que conviene re-analizar con IA (accion manual)."""
    if not impl_ids:
        return 0
    risk_ids = [
        rid for (rid,) in db.query(risk_control_table.c.risk_id)
        .filter(risk_control_table.c.control_implementation_id.in_(impl_ids))
        .distinct().all()
    ]
    if not risk_ids:
        return 0
    return (
        db.query(Risk)
        .filter(Risk.id.in_(risk_ids), Risk.ai_generated == True)  # noqa: E712
        .update({"analysis_stale": True, "stale_reason": reason[:255]},
                synchronize_session=False)
    )


def mark_risks_stale_for_asset(db: Session, asset_id: int, reason: str) -> int:
    """Marca como desactualizado el analisis IA de los riesgos de un activo
    (nueva vigilancia CVE/OSINT, cambios de contexto...)."""
    return (
        db.query(Risk)
        .filter(Risk.asset_id == asset_id, Risk.ai_generated == True)  # noqa: E712
        .update({"analysis_stale": True, "stale_reason": reason[:255]},
                synchronize_session=False)
    )


def recalc_risks_for_impls(db: Session, impl_ids: list[int]) -> int:
    """Recalcula en lote los riesgos vinculados a un conjunto de controles.

    Se invoca cuando cambia el estado de controles (degradacion programada,
    analisis ISMS que sube madurez, NC, CCM...) para que el residual nunca
    quede obsoleto. Devuelve el numero de riesgos recalculados.
    """
    if not impl_ids:
        return 0
    risk_ids = [
        rid for (rid,) in db.query(risk_control_table.c.risk_id)
        .filter(risk_control_table.c.control_implementation_id.in_(impl_ids))
        .distinct().all()
    ]
    if not risk_ids:
        return 0
    risks = db.query(Risk).filter(Risk.id.in_(risk_ids)).all()
    for r in risks:
        try:
            recalc_risk(db, r)
        except Exception:
            logger.exception("recalc_risks_for_impls: fallo en risk id=%s", r.id)
    logger.info("recalc_risks_for_impls: %d riesgos recalculados (%d controles)",
                len(risks), len(impl_ids))
    return len(risks)
