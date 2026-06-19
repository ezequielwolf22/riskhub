"""Motor de calculo de riesgos - ISO/IEC 27005:2018 Annex E.

Implementa la matriz 5x5 (Tabla E.2) que produce un nivel 0..8:
    rows = consequence (impact)
    cols = likelihood

Mapeo de bandas finales (configurable en RiskContext):
    0-2 Low / 3-5 Medium / 6-8 High
"""
from __future__ import annotations
from typing import Iterable, Optional

# Matriz por defecto (Tabla E.2 de ISO 27005:2018, p. 48)
# Filas = impacto 0..4 (very low -> very high)
# Columnas = likelihood 0..4 (very unlikely -> frequent)
DEFAULT_MATRIX = [
    [0, 1, 2, 3, 4],
    [1, 2, 3, 4, 5],
    [2, 3, 4, 5, 6],
    [3, 4, 5, 6, 7],
    [4, 5, 6, 7, 8],
]

LIKELIHOOD_LABELS = [
    "Muy improbable",
    "Improbable",
    "Posible",
    "Probable",
    "Muy probable",
]
CONSEQUENCE_LABELS = [
    "Insignificante",
    "Menor",
    "Moderado",
    "Mayor",
    "Critico",
]


def clamp(v: int, lo: int = 0, hi: int = 4) -> int:
    return max(lo, min(hi, int(v or 0)))


def calc_level(consequence: int, likelihood: int, matrix=None) -> int:
    """Devuelve nivel 0..8 dado consequence/likelihood 0..4."""
    m = matrix or DEFAULT_MATRIX
    return m[clamp(consequence)][clamp(likelihood)]


def band_for(level: int) -> str:
    """0-2 low / 3-5 medium / 6-8 high."""
    if level <= 2:
        return "low"
    if level <= 5:
        return "medium"
    return "high"


# Bandas por defecto (se devuelven cuando la org no tiene config personalizada)
_DEFAULT_BANDS = [
    {"code": "low",    "label": "Bajo",  "min_level": 0, "max_level": 2, "color": "var(--risk-low)",    "order": 1},
    {"code": "medium", "label": "Medio", "min_level": 3, "max_level": 5, "color": "var(--risk-medium)", "order": 2},
    {"code": "high",   "label": "Alto",  "min_level": 6, "max_level": 8, "color": "var(--risk-high)",   "order": 3},
]


def get_risk_bands(db, org_id: int | None) -> list[dict]:
    """Devuelve la configuracion de bandas para una org (o defaults si no hay custom)."""
    try:
        from app.models import RiskLevelConfig
        rows = (
            db.query(RiskLevelConfig)
            .filter(RiskLevelConfig.organization_id == org_id)
            .order_by(RiskLevelConfig.order)
            .all()
        )
        if rows:
            return [
                {"code": r.code, "label": r.label, "min_level": r.min_level,
                 "max_level": r.max_level, "color": r.color, "order": r.order}
                for r in rows
            ]
    except Exception:
        pass
    return [b.copy() for b in _DEFAULT_BANDS]


def band_for_config(level: int, bands: list[dict]) -> dict:
    """Devuelve la banda que corresponde al level dado segun la config."""
    for b in sorted(bands, key=lambda x: x["order"]):
        if b["min_level"] <= level <= b["max_level"]:
            return b
    return bands[-1] if bands else _DEFAULT_BANDS[-1]


def color_for(level: int) -> str:
    """Devuelve un token de color (mapeado en CSS a paleta brand)."""
    return {"low": "brand-low", "medium": "brand-medium", "high": "brand-high"}[band_for(level)]


def control_reduction(controls: Iterable[dict]) -> float:
    """Combina la eficacia de N controles (madurez 0..5 + contribucion 0..1).

    Modelo: efficacy_i = (maturity/5) * contribution
    Combinacion: 1 - PROD(1 - efficacy_i)
    """
    factor = 1.0
    for c in controls:
        mat = max(0, min(5, int(c.get("maturity", 0))))
        contrib = max(0.0, min(1.0, float(c.get("contribution", 1.0))))
        eff = (mat / 5.0) * contrib
        factor *= (1.0 - eff)
    return 1.0 - factor


def calc_residual(
    inherent_likelihood: int,
    inherent_consequence: int,
    controls: list[dict],
    matrix=None,
) -> tuple[int, int, int]:
    """Calcula likelihood/consequence/level residual aplicando controles.

    Se reduce la probabilidad y, parcialmente, la consecuencia (los controles
    correctivos/recuperacion mitigan el impacto). En este modelo simple
    aplicamos la misma reduccion a ambos pero ponderando: prob -> 100%,
    cons -> 50%, para no doble-contar.
    """
    reduction = control_reduction(controls)
    new_lik = clamp(round(inherent_likelihood * (1.0 - reduction)))
    new_cons = clamp(round(inherent_consequence * (1.0 - 0.5 * reduction)))
    return new_lik, new_cons, calc_level(new_cons, new_lik, matrix)


def default_impact_criteria() -> dict:
    """Criterios de impacto por defecto (ISO 27005 7.2.3)."""
    return {
        "financial": {
            0: "< 10.000 EUR",
            1: "10.000 - 100.000 EUR",
            2: "100.000 - 1.000.000 EUR",
            3: "1.000.000 - 10.000.000 EUR",
            4: "> 10.000.000 EUR",
        },
        "operational": {
            0: "Sin impacto operativo",
            1: "Servicio degradado < 4h",
            2: "Servicio degradado 4-24h o caida < 4h",
            3: "Caida de servicio 1-3 dias",
            4: "Caida critica > 3 dias",
        },
        "reputational": {
            0: "Sin impacto",
            1: "Quejas internas",
            2: "Cobertura sectorial",
            3: "Cobertura nacional",
            4: "Cobertura internacional sostenida",
        },
        "regulatory": {
            0: "Sin impacto",
            1: "Apercibimiento informal",
            2: "Sancion administrativa leve",
            3: "Sancion grave / GDPR <= 10M",
            4: "Sancion muy grave / GDPR > 10M / responsabilidad penal",
        },
        "safety": {
            0: "Sin riesgo para personas",
            1: "Molestias",
            2: "Lesion leve",
            3: "Lesion grave",
            4: "Fatalidad o lesiones multiples",
        },
    }


def default_likelihood_criteria() -> dict:
    return {
        0: "Muy improbable - menos de 1 vez cada 10 años",
        1: "Improbable - 1 vez cada 5-10 años",
        2: "Posible - 1 vez al año",
        3: "Probable - varias veces al año",
        4: "Muy probable - mensual o más frecuente",
    }


def default_acceptance_criteria() -> dict:
    return {
        "appetite_max_level": 3,
        "rules": [
            "Riesgos low (0-2) pueden retenerse sin aprobacion adicional.",
            "Riesgos medium (3-5) requieren aprobacion del responsable de area.",
            "Riesgos high (6-8) requieren aprobacion del Comite de Seguridad.",
            "Cualquier riesgo con impacto en seguridad de personas (safety) >= 3 "
            "requiere tratamiento obligatorio.",
        ],
    }


def default_matrix() -> list[list[int]]:
    return [row[:] for row in DEFAULT_MATRIX]


# ---------- MAGERIT v3 helpers ----------

# Escala de frecuencia MAGERIT (MA/A/M/B/MB) → probabilidad 0-4 ISO 27005
MAGERIT_FREQ_LABELS = {
    "0": "MB — Muy Baja (< 1/10 años)",
    "1": "B  — Baja (1/5-10 años)",
    "2": "M  — Media (1/año)",
    "3": "A  — Alta (varias/año)",
    "4": "MA — Muy Alta (mensual o más)",
}

# Dimensiones de seguridad MAGERIT (5D: DIACAT)
MAGERIT_DIMENSIONS = {
    "D": "Disponibilidad",
    "I": "Integridad",
    "C": "Confidencialidad",
    "A": "Autenticidad",
    "T": "Trazabilidad",
}

# Mapa dimensión → campo en Asset
MAGERIT_DIM_FIELD = {
    "D": "value_availability",
    "I": "value_integrity",
    "C": "value_confidentiality",
    "A": "value_authenticity",
    "T": "value_accountability",
}


def calc_consequence_magerit(asset_dim_value: int, degradation_pct: int) -> tuple[int, float]:
    """Calcula consecuencia e impacto MAGERIT.

    MAGERIT: Impacto = Valor_dimensión_activo × (Degradación% / 100)
    La consecuencia (0-4) se obtiene mapeando el impacto a la escala ISO 27005.

    Args:
        asset_dim_value: valor de la dimensión afectada en el activo (0-4 escala RiskHub)
        degradation_pct: porcentaje de degradación si la amenaza se materializa (0-100)

    Returns:
        (consequence 0-4, magerit_impact float)
    """
    impact = asset_dim_value * (degradation_pct / 100.0)
    consequence = clamp(round(impact))
    return consequence, round(impact, 2)


def primary_dimension_for_threat(threat_affects: list[str], asset: object) -> str:
    """Devuelve la dimensión MAGERIT más crítica para este activo y amenaza.

    Selecciona la dimensión con mayor valor en el activo entre las que afecta
    la amenaza (threat.affects = ["C","I","A"...]).
    Si no hay información, usa la dimensión con el valor más alto del activo.
    """
    dims_to_check = [d for d in (threat_affects or []) if d in MAGERIT_DIM_FIELD]
    if not dims_to_check:
        dims_to_check = list(MAGERIT_DIM_FIELD.keys())

    best_dim = "D"
    best_val = -1
    for dim in dims_to_check:
        field = MAGERIT_DIM_FIELD[dim]
        val = getattr(asset, field, 0) or 0
        if val > best_val:
            best_val = val
            best_dim = dim
    return best_dim
