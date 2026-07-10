"""Motor de scoring TPRM (Third-Party Risk Management).

Implementa la logica determinista de la spec del modulo TPRM:
 - Inherent risk scoring (sin depender de respuestas del proveedor) — §4.2
 - Tiering dinamico por umbrales — §4.3
 - Residual risk = inherent x (1 - control_effectiveness/100) — §5.2
 - Mapeo a 5 niveles de riesgo — §5.1
 - Scoring de cuestionarios contra plantillas con pesos y reglas — §4.7.1

Convencion de scores:
 - inherent_risk_score / residual_risk_score: 0-100, MAYOR = MAS riesgo.
 - control_effectiveness: 0-100, MAYOR = mejor postura de control.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Supplier, SupplierTier, SupplierRisk

logger = logging.getLogger("riskhub.tprm_scoring")


# ---------- Pesos de la formula de inherent risk (§4.2) ----------
# Editable por tenant en una iteracion futura (scoring_config).
INHERENT_WEIGHTS = {
    "data_sensitivity": 0.30,
    "data_volume": 0.20,
    "system_access": 0.20,
    "business_criticality": 0.15,
    "regulatory_scope": 0.10,
    "geographic_risk": 0.05,
}

# Mapeo de tipo de acceso a sistemas -> score 0-100
SYSTEM_ACCESS_SCORE = {
    "none": 0,
    "api_only": 40,
    "saas": 50,
    "paas": 60,
    "iaas": 70,
    "on_prem": 60,
    "read_write": 75,
    "admin_to_our_systems": 100,
}

# Umbrales de tiering por inherent risk (§4.3)
TIER_THRESHOLDS = [
    (80, SupplierTier.CRITICAL),
    (60, SupplierTier.HIGH),
    (30, SupplierTier.MEDIUM),
    (0, SupplierTier.LOW),
]

# Frecuencia de reassessment por tier (meses) — §4.9
REASSESSMENT_MONTHS = {
    SupplierTier.CRITICAL: 6,
    SupplierTier.HIGH: 12,
    SupplierTier.MEDIUM: 24,
    SupplierTier.LOW: 36,
}


def _scale_1_5(value: Optional[int]) -> float:
    """Normaliza un valor discreto 1-5 a 0-100."""
    v = value if value is not None else 1
    v = max(1, min(5, v))
    return (v - 1) / 4 * 100


def _regulatory_scope_score(supplier: Supplier) -> float:
    """Score 0-100 segun el alcance regulatorio del proveedor.

    NIS2/DORA elevan mas que ENS/GDPR. Acumulativo y acotado a 100.
    """
    score = 0
    if supplier.is_dora:
        score += 40
    if supplier.is_nis2:
        score += 35
    if supplier.is_ens:
        score += 20
    if supplier.is_data_processor or supplier.processes_personal_data:
        score += 20
    return float(min(100, score))


def compute_inherent_risk(supplier: Supplier) -> int:
    """Calcula el inherent risk (0-100, mayor = mas riesgo) — §4.2."""
    data_sensitivity = _scale_1_5(supplier.data_sensitivity)
    data_volume = _scale_1_5(supplier.data_volume)
    system_access = SYSTEM_ACCESS_SCORE.get(
        (supplier.system_access_type or "none").lower(), 40
    )
    business_criticality = _scale_1_5(supplier.business_criticality)
    regulatory = _regulatory_scope_score(supplier)
    geographic = _scale_1_5(supplier.geographic_risk)

    total = (
        INHERENT_WEIGHTS["data_sensitivity"] * data_sensitivity
        + INHERENT_WEIGHTS["data_volume"] * data_volume
        + INHERENT_WEIGHTS["system_access"] * system_access
        + INHERENT_WEIGHTS["business_criticality"] * business_criticality
        + INHERENT_WEIGHTS["regulatory_scope"] * regulatory
        + INHERENT_WEIGHTS["geographic_risk"] * geographic
    )
    return int(round(max(0, min(100, total))))


def derive_tier(inherent_risk: int) -> SupplierTier:
    """Deriva el tier por umbrales (§4.3)."""
    for threshold, tier in TIER_THRESHOLDS:
        if inherent_risk >= threshold:
            return tier
    return SupplierTier.LOW


def compute_residual_risk(inherent_risk: int, control_effectiveness: Optional[int]) -> int:
    """Residual = inherent x (1 - control_effectiveness/100) — §5.2."""
    ce = control_effectiveness if control_effectiveness is not None else 0
    ce = max(0, min(100, ce))
    return int(round(inherent_risk * (1 - ce / 100)))


def risk_level_label(score: Optional[int]) -> str:
    """Mapea un score 0-100 (mayor = mas riesgo) a un nivel — §5.1.

    Nota: la spec define los rangos sobre la POSTURA (100=excelente). Aqui
    invertimos porque inherent/residual son riesgo (mayor=peor): el nivel se
    calcula sobre la postura equivalente (100 - score).
    """
    if score is None:
        return "unknown"
    posture = 100 - score
    if posture < 25:
        return "critical"
    if posture < 50:
        return "high"
    if posture < 75:
        return "medium"
    if posture < 90:
        return "low"
    return "very_low"


def _tier_to_supplier_risk(tier: SupplierTier) -> str:
    return {
        SupplierTier.CRITICAL: "critical",
        SupplierTier.HIGH: "high",
        SupplierTier.MEDIUM: "medium",
        SupplierTier.LOW: "low",
    }.get(tier, "medium")


def recompute_supplier(db: Session, supplier: Supplier, commit: bool = True) -> dict:
    """Recalcula inherent risk, tier y residual risk de un proveedor.

    El control_effectiveness se deriva de la postura existente (supplier.score)
    si no se ha fijado uno explicito. Devuelve el desglose.
    """
    inherent = compute_inherent_risk(supplier)
    tier = derive_tier(inherent)

    # control_effectiveness: si no esta fijado, usar la postura (score 0-100, mayor=mejor)
    control_eff = supplier.control_effectiveness
    if control_eff is None:
        control_eff = supplier.score if supplier.score is not None else 0

    residual = compute_residual_risk(inherent, control_eff)

    supplier.inherent_risk_score = inherent
    supplier.tier = tier
    supplier.control_effectiveness = control_eff
    supplier.residual_risk_score = residual
    # Sincronizar risk_level (residual) con el tier para coherencia en listados
    supplier.risk_level = _tier_to_supplier_risk(tier)
    supplier.is_critical = (tier == SupplierTier.CRITICAL)

    if commit:
        try:
            db.commit()
        except Exception as exc:  # pragma: no cover
            db.rollback()
            logger.exception("Error recalculando TPRM scoring: %s", exc)
            raise

    return {
        "inherent_risk_score": inherent,
        "inherent_risk_level": risk_level_label(inherent),
        "tier": tier.value,
        "control_effectiveness": control_eff,
        "residual_risk_score": residual,
        "residual_risk_level": risk_level_label(residual),
        "reassessment_months": REASSESSMENT_MONTHS[tier],
    }


# ---------- Scoring de cuestionarios contra plantilla (§4.7.1) ----------

def _score_answer(question: dict, answer) -> Optional[float]:
    """Aplica scoring_rules de una pregunta a su respuesta -> 0-100 (o None)."""
    rules = question.get("scoring_rules") or {}
    if not rules:
        # Fallback Si/No para plantillas simples
        if str(answer).lower() in ("true", "1", "yes", "si", "sí"):
            return 100.0
        if str(answer).lower() in ("false", "0", "no"):
            return 0.0
        return None
    # Respuesta multiple: media de las opciones marcadas
    if isinstance(answer, list):
        vals = [rules[a] for a in answer if a in rules and rules[a] is not None]
        return sum(vals) / len(vals) if vals else None
    key = str(answer)
    if key in rules:
        return rules[key]
    # Booleanos normalizados a yes/no
    low = key.lower()
    if low in ("true", "1", "si", "sí") and "yes" in rules:
        return rules["yes"]
    if low in ("false", "0") and "no" in rules:
        return rules["no"]
    return None


# Factores por estado de la evidencia requerida (§5.5, ampliado v6.0.0):
# el estado sale de la revision IA del fichero adjunto (tprm_ai_service)
_EVIDENCE_STATE_FACTOR = {
    "missing": 0.5,        # requerida y no aportada
    "unverified": 0.7,     # aportada pero sin revision IA del contenido
    "consistent": 1.0,     # revisada y respalda la respuesta
    "contradictory": 0.4,  # revisada y CONTRADICE la respuesta
}


def _evidence_state(qid, answers: dict, evidence: Optional[dict]) -> str:
    entry = (evidence or {}).get(str(qid)) or (evidence or {}).get(qid)
    if not entry and not (answers or {}).get(f"{qid}__evidence"):
        return "missing"
    review = (entry or {}).get("ai_review") or {}
    consistency = review.get("consistency")
    if consistency == "contradictory":
        return "contradictory"
    if consistency in ("consistent", "supports"):
        return "consistent"
    return "unverified"


def score_questionnaire(questions: list, answers: dict,
                        evidence: Optional[dict] = None) -> dict:
    """Calcula el score 0-100 de un cuestionario con pesos por pregunta.

    Devuelve {score, answered, total, by_question}. Las preguntas con
    respuesta None/N-A se excluyen del calculo (no penalizan).
    La evidencia requerida pondera en 4 estados: ausente x0.5, sin verificar
    x0.7, verificada consistente x1.0, contradictoria x0.4.
    """
    total_weight = 0.0
    weighted = 0.0
    by_question = {}
    answered = 0
    for q in questions or []:
        qid = q.get("id")
        weight = float(q.get("weight", 1) or 1)
        ans = (answers or {}).get(qid)
        sc = _score_answer(q, ans) if ans is not None else None
        if sc is not None and q.get("requires_evidence"):
            state = _evidence_state(qid, answers, evidence)
            sc = sc * _EVIDENCE_STATE_FACTOR.get(state, 0.7)
        by_question[qid] = sc
        if sc is not None:
            weighted += sc * weight
            total_weight += weight
            answered += 1
    score = int(round(weighted / total_weight)) if total_weight else 0
    return {
        "score": score,
        "answered": answered,
        "total": len(questions or []),
        "by_question": by_question,
    }
