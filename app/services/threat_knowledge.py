"""Capa de conocimiento amenaza -> controles / vulnerabilidades.

El catalogo base vive en app/data/threat_control_map.json (generado offline
y revisable en git); cada organizacion puede ajustarlo via la tabla
threat_control_overrides. El efecto P/D/C de cada control se deriva de
classify_control() para mantener una sola fuente de verdad.

Consumidores: generacion de riesgos por activo (candidatos concretos por
amenaza + fallback determinista de vinculo control-riesgo), suggest-controls
y push-to-risk de TPRM.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Control, ControlImplementation, ControlStatus, Vulnerability
from app.services.risk_analysis_helpers import classify_control

logger = logging.getLogger(__name__)

_MAP_PATH = Path(__file__).resolve().parent.parent / "data" / "threat_control_map.json"


@lru_cache(maxsize=1)
def _load_map() -> dict:
    try:
        with open(_MAP_PATH, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        data.pop("_meta", None)
        return data
    except Exception:
        logger.exception("threat_knowledge: no se pudo cargar %s", _MAP_PATH)
        return {}


def controls_for_threat(db: Session, org_id: int | None, threat_code: str) -> list[dict]:
    """Controles que mitigan la amenaza: [{code, relevance, effect}].

    Combina el catalogo base con los overrides de la org (un override
    active=False elimina el control; active=True anade o reemplaza).
    """
    base = {c["code"]: float(c.get("relevance", 0.5))
            for c in _load_map().get(threat_code, [])}

    try:
        from app.models import ThreatControlOverride
        rows = db.query(ThreatControlOverride).filter_by(
            organization_id=org_id, threat_code=threat_code
        ).all()
        for ov in rows:
            if ov.active:
                base[ov.control_code] = float(ov.relevance or 0.5)
            else:
                base.pop(ov.control_code, None)
    except Exception:
        logger.debug("threat_knowledge: overrides no disponibles", exc_info=True)

    result = []
    for code, relevance in sorted(base.items(), key=lambda kv: -kv[1]):
        result.append({
            "code": code,
            "relevance": relevance,
            "effect": classify_control(code),
        })
    return result


def vulns_for_threat(db: Session, threat_code: str) -> list[Vulnerability]:
    """Vulnerabilidades del catalogo cuyo related_threats incluye la amenaza."""
    result = []
    for v in db.query(Vulnerability).all():
        rt = v.related_threats or []
        if isinstance(rt, str):
            try:
                rt = json.loads(rt)
            except Exception:
                rt = [rt]
        if threat_code in rt:
            result.append(v)
    return result


def candidate_impls_for_threat(
    db: Session, org_id: int | None, threat_code: str,
    impls: list[ControlImplementation] | None = None,
) -> list[dict]:
    """Cruza el mapeo con las implementaciones reales de la org.

    Devuelve [{impl, code, name, relevance, effect, maturity}] ordenado por
    relevancia. Sirve para construir el bloque de controles candidatos del
    prompt y como fallback determinista si el LLM no devuelve contribuciones.
    """
    mapping = controls_for_threat(db, org_id, threat_code)
    if not mapping:
        return []
    by_code = {m["code"]: m for m in mapping}

    if impls is None:
        impls = db.query(ControlImplementation).filter(
            ControlImplementation.organization_id == org_id,
            ControlImplementation.status != ControlStatus.NOT_IMPLEMENTED,
        ).all()

    result = []
    for ci in impls:
        ctrl: Control | None = ci.control
        if not ctrl or not ctrl.code:
            continue
        code_norm = ctrl.code.strip().lstrip("A.").strip()
        entry = by_code.get(code_norm) or by_code.get(ctrl.code.strip())
        if not entry:
            continue
        result.append({
            "impl": ci,
            "impl_id": ci.id,
            "code": ctrl.code,
            "name": ctrl.name,
            "relevance": entry["relevance"],
            "effect": entry["effect"],
            "maturity": ci.maturity or 0,
        })
    result.sort(key=lambda r: -r["relevance"])
    return result


def fallback_contributions(candidates: list[dict], min_relevance: float = 0.6) -> list[dict]:
    """Vinculo determinista control->riesgo cuando el LLM no lo proporciona.

    Usa los controles implementados con relevancia >= umbral, con
    contribution = relevance del catalogo.
    """
    return [
        {"impl_id": c["impl_id"], "contribution": c["relevance"]}
        for c in candidates if c["relevance"] >= min_relevance
    ]
