"""Motor determinista de escenarios de indisponibilidad (ISO 22301 cl. 8.2).

Principio rector del modulo BCM, igual que en `risk_recalc_service` para el
riesgo residual: la IA propone entradas (escenarios detectados, valoraciones de
impacto leidas de un documento, reglas de aplicabilidad sugeridas), pero el
impacto ponderado, la banda y la aplicabilidad los calcula SIEMPRE este codigo.
Ninguna de estas cifras sale de un LLM.

Dos ideas sostienen el diseno:

1. **El metodo es del cliente.** Las dimensiones de impacto, los horizontes
   temporales, la escala de RTO y las bandas se declaran en `BIACriteria` por
   organizacion. El motor calcula con lo que el cliente declare; el baremo de
   `DEFAULT_CRITERIA` es solo un punto de partida razonable.

2. **La aplicabilidad no es un atributo del escenario.** Vive en
   `BCMApplicabilityRule` y por defecto NO hay reglas: todos los escenarios
   aplican a todas las sedes. Una regla solo puede QUITAR escenarios, nunca
   anadirlos, y si la sede no tiene informado el atributo del que depende la
   regla, la regla no dispara. Nunca se oculta un escenario por omision ni por
   falta de datos.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("riskhub.bcm_scenario")

# Familias de escenarios de indisponibilidad.
FAMILIES = ("personnel", "systems_comms", "third_party", "facilities")

# Baremo por defecto. Escala de impacto 1-5 mapeada a valor 0-4 (nivel 1 = "sin
# impacto" = 0), horizontes de las primeras horas y factor de RTO que prima los
# procesos que no pueden esperar. Todo esto es sustituible por organizacion.
DEFAULT_CRITERIA: dict = {
    "dimensions": [
        {"key": "operational",   "label": "Operativo"},
        {"key": "financial",     "label": "Financiero"},
        {"key": "people",        "label": "Personas"},
        {"key": "regulatory",    "label": "Regulatorio"},
        {"key": "reputational",  "label": "Reputacional"},
    ],
    "horizons": ["0h", ">1h", ">4h", ">6h"],
    "levels": [
        {"value": 1, "score": 0, "label": "Sin impacto"},
        {"value": 2, "score": 1, "label": "Trivial"},
        {"value": 3, "score": 2, "label": "Relevante"},
        {"value": 4, "score": 3, "label": "Severo"},
        {"value": 5, "score": 4, "label": "Critico"},
    ],
    "rto_scale": [
        {"label": "No puede interrumpirse nunca", "hours": 0,   "factor": 1.5},
        {"label": "1 hora",                       "hours": 1,   "factor": 0.5},
        {"label": "4 horas",                      "hours": 4,   "factor": 0.6},
        {"label": "6 horas",                      "hours": 6,   "factor": 0.7},
        {"label": "12 horas",                     "hours": 12,  "factor": 0.8},
        {"label": "24 horas",                     "hours": 24,  "factor": 0.9},
        {"label": "3 dias",                       "hours": 72,  "factor": 1.0},
        {"label": "1 semana",                     "hours": 168, "factor": 1.1},
        {"label": "Mas de 1 semana",              "hours": 336, "factor": 1.2},
    ],
    # Bandas del impacto ponderado. Se evaluan por "min" descendente: un valor
    # por encima del maximo de la banda superior sigue cayendo en ella.
    "bands": [
        {"key": "none",      "label": "Sin impacto", "min": 0.0, "max": 0.2},
        {"key": "trivial",   "label": "Trivial",     "min": 0.3, "max": 0.8},
        {"key": "relevant",  "label": "Relevante",   "min": 0.8, "max": 1.2},
        {"key": "severe",    "label": "Severo",      "min": 1.2, "max": 2.8},
        {"key": "critical",  "label": "Critico",     "min": 2.8, "max": 4.0},
    ],
    # Agregacion entre dimensiones dentro de un mismo horizonte.
    "aggregation": "max",
    # Agregacion entre horizontes: el peor horizonte manda.
    "horizon_aggregation": "max",
    # Como se combina el impacto con el RTO. "product" pondera el impacto por
    # el factor del RTO; "sum" los suma, que es lo que hacen los metodos que
    # tratan el RTO como un sumando mas ("RTO + Criterio de impacto = Impacto
    # total"). La eleccion cambia la cifra por completo, asi que se declara.
    "combination": "product",
}


# ── Criterios ────────────────────────────────────────────────────────────────

def get_criteria(db: Session, org_id: Optional[int]) -> dict:
    """Baremo de la organizacion, completado con los valores por defecto.

    Nunca falla: si la organizacion no ha declarado su metodo, se calcula con
    DEFAULT_CRITERIA para que el BIA sea utilizable desde el minuto cero.
    """
    criteria = dict(DEFAULT_CRITERIA)
    if not org_id:
        return criteria
    try:
        from app.models import BIACriteria
        row = db.query(BIACriteria).filter_by(organization_id=org_id).first()
    except Exception:
        logger.debug("bcm_scenario: no se pudo leer BIACriteria", exc_info=True)
        return criteria
    if not row:
        return criteria
    for field in ("dimensions", "horizons", "levels", "rto_scale", "bands"):
        value = getattr(row, field, None)
        if value:
            criteria[field] = value
    for field in ("aggregation", "combination"):
        value = getattr(row, field, None)
        if value:
            criteria[field] = value
    return criteria


def _level_score(value, criteria: dict) -> float:
    """Traduce un nivel de impacto declarado a su puntuacion numerica."""
    if value is None:
        return 0.0
    levels = criteria.get("levels") or DEFAULT_CRITERIA["levels"]
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        # Puede venir la etiqueta ("Severo") en vez del nivel numerico
        label = str(value).strip().lower()
        for lvl in levels:
            if str(lvl.get("label", "")).strip().lower() == label:
                return float(lvl.get("score", 0))
        return 0.0
    for lvl in levels:
        if float(lvl.get("value", -1)) == numeric:
            return float(lvl.get("score", 0))
    # Nivel fuera de la escala declarada: se usa tal cual, acotado a >= 0.
    return max(0.0, numeric)


def rto_factor(criteria: dict, label: Optional[str] = None,
               hours: Optional[float] = None) -> float:
    """Factor multiplicador del impacto segun el RTO.

    Prioriza la etiqueta declarada por el cliente ("No puede interrumpirse
    nunca") y cae a las horas si no hay etiqueta reconocible. Sin ninguna de las
    dos, factor neutro 1.0 — nunca se inventa urgencia ni se relaja.
    """
    scale = criteria.get("rto_scale") or DEFAULT_CRITERIA["rto_scale"]
    if label:
        needle = str(label).strip().lower()
        for entry in scale:
            if str(entry.get("label", "")).strip().lower() == needle:
                return float(entry.get("factor", 1.0))
    if hours is not None:
        try:
            target = float(hours)
        except (TypeError, ValueError):
            return 1.0
        # Se toma el tramo declarado mas cercano por debajo o igual; si el RTO
        # es menor que todos los tramos, manda el mas exigente.
        with_hours = [e for e in scale if e.get("hours") is not None]
        if with_hours:
            ordered = sorted(with_hours, key=lambda e: float(e["hours"]))
            chosen = ordered[0]
            for entry in ordered:
                if float(entry["hours"]) <= target:
                    chosen = entry
                else:
                    break
            return float(chosen.get("factor", 1.0))
    return 1.0


def band_for(value: Optional[float], criteria: dict) -> Optional[str]:
    """Banda del impacto ponderado. Por encima del techo, sigue la banda alta."""
    if value is None:
        return None
    bands = criteria.get("bands") or DEFAULT_CRITERIA["bands"]
    ordered = sorted(bands, key=lambda b: float(b.get("min", 0)), reverse=True)
    for band in ordered:
        if float(value) >= float(band.get("min", 0)):
            return band.get("key")
    return ordered[-1].get("key") if ordered else None


def weighted_impact(impacts: Optional[dict], criteria: dict,
                    rto_label: Optional[str] = None,
                    rto_hours: Optional[float] = None) -> dict:
    """Calcula el impacto ponderado de una valoracion.

    `impacts` tiene la forma {dimension: {horizonte: nivel}}. Se agrega primero
    entre dimensiones dentro de cada horizonte, luego entre horizontes, y el
    resultado se pondera por el factor del RTO.

    Devuelve {weighted_impact, band, base_impact, rto_factor, combination,
    per_horizon}.
    """
    horizons = criteria.get("horizons") or DEFAULT_CRITERIA["horizons"]
    agg = (criteria.get("aggregation") or "max").lower()
    horizon_agg = (criteria.get("horizon_aggregation") or "max").lower()
    combination = (criteria.get("combination") or "product").lower()
    factor = rto_factor(criteria, rto_label, rto_hours)

    per_horizon: dict[str, float] = {}
    if impacts:
        for horizon in horizons:
            scores = []
            for dim_key, by_horizon in impacts.items():
                if not isinstance(by_horizon, dict):
                    continue
                if horizon not in by_horizon:
                    continue
                scores.append(_level_score(by_horizon.get(horizon), criteria))
            if scores:
                per_horizon[horizon] = (
                    max(scores) if agg == "max" else sum(scores) / len(scores)
                )

    if per_horizon:
        values = list(per_horizon.values())
        base = max(values) if horizon_agg == "max" else sum(values) / len(values)
    else:
        base = 0.0

    # Sin impacto declarado no se inventa una cifra a partir del RTO: sumar el
    # factor a un impacto cero daria por severo un escenario sin valorar.
    if combination == "sum" and per_horizon:
        weighted = round(base + factor, 3)
    elif combination == "sum":
        weighted = 0.0
    else:
        weighted = round(base * factor, 3)

    return {
        "weighted_impact": weighted,
        "band": band_for(weighted, criteria),
        "base_impact": round(base, 3),
        "rto_factor": factor,
        "combination": combination,
        "per_horizon": {k: round(v, 3) for k, v in per_horizon.items()},
    }


# ── Aplicabilidad ────────────────────────────────────────────────────────────

def _rule_matches(rule_when: Optional[dict], location) -> bool:
    """True si la sede cumple TODAS las condiciones de la regla.

    Si la sede no tiene informado un atributo que la regla exige, la regla NO
    dispara: ante datos incompletos se prefiere mostrar el escenario de mas.
    """
    if not rule_when:
        return False   # una regla sin condiciones no se aplica a ciegas
    for attr, expected in rule_when.items():
        actual = getattr(location, attr, None) if location is not None else None
        if actual is None or actual == "":
            return False
        if isinstance(expected, (list, tuple, set)):
            candidates = {str(e).strip().lower() for e in expected}
            if str(actual).strip().lower() not in candidates:
                return False
        else:
            if str(actual).strip().lower() != str(expected).strip().lower():
                return False
    return True


def applicable_scenarios(scenarios: Iterable, rules: Iterable, location) -> list:
    """Escenarios que aplican a una sede tras evaluar las reglas.

    Sin reglas activas devuelve el catalogo entero: es el comportamiento por
    defecto y el correcto. Las reglas solo restan.
    """
    result = [s for s in scenarios if getattr(s, "is_active", True)]
    active_rules = [r for r in rules if getattr(r, "is_active", True)]
    if not active_rules:
        return result

    for rule in sorted(active_rules, key=lambda r: (getattr(r, "priority", 100) or 100)):
        if not _rule_matches(getattr(rule, "when", None), location):
            continue
        effect = getattr(rule, "then", None) or {}

        include_only = effect.get("include_only_families")
        if include_only:
            keep = {str(f).strip().lower() for f in include_only}
            result = [s for s in result if str(s.family).strip().lower() in keep]

        excluded_families = effect.get("exclude_families")
        if excluded_families:
            drop = {str(f).strip().lower() for f in excluded_families}
            result = [s for s in result if str(s.family).strip().lower() not in drop]

        excluded_codes = effect.get("exclude_scenarios")
        if excluded_codes:
            drop_codes = {str(c).strip().lower() for c in excluded_codes}
            result = [
                s for s in result
                if str(getattr(s, "code", "") or "").strip().lower() not in drop_codes
            ]

    return result


# ── Matriz y recalculo ───────────────────────────────────────────────────────

def scenario_matrix(db: Session, org_id: int,
                    location_id: Optional[int] = None) -> dict:
    """Matriz escenario x sede: que aplica, que esta valorado y que falta.

    Los huecos se declaran, nunca se ocultan: un escenario aplicable sin
    valoracion aparece como `missing`, no desaparece de la matriz.
    """
    from app.models import (BCMApplicabilityRule, BCMLocation, BCMScenario,
                            BCMScenarioAssessment)

    scenarios = db.query(BCMScenario).filter_by(
        organization_id=org_id, is_active=True
    ).order_by(BCMScenario.family, BCMScenario.code).all()
    rules = db.query(BCMApplicabilityRule).filter_by(
        organization_id=org_id, is_active=True
    ).all()

    loc_q = db.query(BCMLocation).filter_by(organization_id=org_id, is_active=True)
    if location_id:
        loc_q = loc_q.filter(BCMLocation.id == location_id)
    locations = loc_q.order_by(BCMLocation.name).all()

    assessments = db.query(BCMScenarioAssessment).filter_by(
        organization_id=org_id
    ).all()
    by_key = {(a.scenario_id, a.location_id): a for a in assessments}

    criteria = get_criteria(db, org_id)
    cells = []
    applicable_total = 0
    assessed_total = 0
    for loc in locations:
        applicable = applicable_scenarios(scenarios, rules, loc)
        applicable_ids = {s.id for s in applicable}
        for sc in scenarios:
            is_applicable = sc.id in applicable_ids
            assessment = by_key.get((sc.id, loc.id))
            if is_applicable:
                applicable_total += 1
                if assessment:
                    assessed_total += 1
            cells.append({
                "scenario_id": sc.id,
                "scenario_code": sc.code,
                "scenario_name": sc.name,
                "family": sc.family,
                "location_id": loc.id,
                "location_name": loc.name,
                "applicable": is_applicable,
                "status": ("assessed" if assessment else "missing")
                          if is_applicable else "not_applicable",
                "assessment_id": assessment.id if assessment else None,
                "impact_band": assessment.impact_band if assessment else None,
                "weighted_impact": assessment.weighted_impact if assessment else None,
                "needs_review": bool(getattr(assessment, "needs_review", False))
                                if assessment else False,
            })

    coverage = int(assessed_total / applicable_total * 100) if applicable_total else 0
    return {
        "scenarios": [
            {"id": s.id, "code": s.code, "name": s.name, "family": s.family}
            for s in scenarios
        ],
        "locations": [
            {"id": loc.id, "name": loc.name, "code": loc.code,
             "site_type": getattr(loc, "site_type", None),
             "country": loc.country, "city": getattr(loc, "city", None),
             "business_unit": getattr(loc, "business_unit", None)}
            for loc in locations
        ],
        "cells": cells,
        "rules_active": len(rules),
        "applicable_total": applicable_total,
        "assessed_total": assessed_total,
        "coverage_pct": coverage,
        "criteria": criteria,
    }


def recompute_assessment(assessment, criteria: dict) -> bool:
    """Recalcula impacto ponderado y banda de una valoracion. True si cambio."""
    result = weighted_impact(
        assessment.impacts, criteria,
        rto_label=assessment.rto_label, rto_hours=assessment.rto_hours,
    )
    changed = (assessment.weighted_impact != result["weighted_impact"]
               or assessment.impact_band != result["band"])
    assessment.weighted_impact = result["weighted_impact"]
    assessment.impact_band = result["band"]
    return changed


def recompute_org(db: Session, org_id: int) -> int:
    """Recalcula todas las valoraciones de la organizacion.

    Se llama tras cambiar el baremo: el metodo del cliente cambia y el BIA
    entero debe reflejarlo sin que nadie toque fila a fila.
    """
    from app.models import BCMScenarioAssessment

    criteria = get_criteria(db, org_id)
    rows = db.query(BCMScenarioAssessment).filter_by(organization_id=org_id).all()
    changed = 0
    for row in rows:
        if recompute_assessment(row, criteria):
            changed += 1
    if changed:
        db.commit()
        logger.info("bcm_scenario: recalculadas %d valoraciones (org=%s)", changed, org_id)
    return changed


def coverage_gaps(db: Session, org_id: int) -> list[dict]:
    """Huecos accionables del SGCN por escenario y sede.

    Un escenario aplicable puede fallar por cuatro motivos distintos, y cada uno
    exige una accion diferente: valorarlo, definir estrategia, escribir plan o
    ejercitarlo. Se devuelven separados para poder generar recomendaciones.
    """
    from app.models import BCPPlan, BCPStrategy, BCPTest

    matrix = scenario_matrix(db, org_id)
    strategies = db.query(BCPStrategy).filter_by(organization_id=org_id).all()
    with_strategy = {s.scenario_id for s in strategies if s.scenario_id}

    plans = db.query(BCPPlan).filter_by(organization_id=org_id).all()
    with_plan: set[int] = set()
    for plan in plans:
        for sid in (plan.scenario_ids or []):
            with_plan.add(sid)

    now = datetime.now(timezone.utc)
    tested_recently: set[int] = set()
    for test in db.query(BCPTest).filter_by(organization_id=org_id).all():
        if not test.conducted_at:
            continue
        conducted = test.conducted_at
        if conducted.tzinfo is None:
            conducted = conducted.replace(tzinfo=timezone.utc)
        if (now - conducted).days > 365:
            continue
        for sid in (test.scenario_ids or []):
            tested_recently.add(sid)

    gaps = []
    for cell in matrix["cells"]:
        if not cell["applicable"]:
            continue
        reasons = []
        if cell["status"] == "missing":
            reasons.append("no_assessment")
        if cell["scenario_id"] not in with_strategy:
            reasons.append("no_strategy")
        if cell["scenario_id"] not in with_plan:
            reasons.append("no_plan")
        if cell["scenario_id"] not in tested_recently:
            reasons.append("not_tested_12m")
        if reasons:
            gaps.append({
                "scenario_id": cell["scenario_id"],
                "scenario_code": cell["scenario_code"],
                "scenario_name": cell["scenario_name"],
                "family": cell["family"],
                "location_id": cell["location_id"],
                "location_name": cell["location_name"],
                "reasons": reasons,
            })
    return gaps
