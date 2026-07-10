"""Tests unitarios del motor de scoring TPRM (Third-Party Risk Management).

Tests puramente en memoria: se construyen objetos Supplier() sin sesion de BD
porque las funciones compute_* solo leen atributos del modelo.
"""
import pytest

from app.models import Supplier, SupplierTier
from app.services.tprm_scoring_service import (
    INHERENT_WEIGHTS,
    REASSESSMENT_MONTHS,
    SYSTEM_ACCESS_SCORE,
    TIER_THRESHOLDS,
    compute_inherent_risk,
    compute_residual_risk,
    derive_tier,
    risk_level_label,
    score_questionnaire,
)


# ---------------------------------------------------------------------------
# Helpers para construir proveedores en memoria
# ---------------------------------------------------------------------------

def _low_risk_supplier() -> Supplier:
    """Proveedor de riesgo minimo: todos los parametros en sus valores mas bajos."""
    s = Supplier()
    s.data_sensitivity = 1
    s.data_volume = 1
    s.system_access_type = "none"
    s.business_criticality = 1
    s.geographic_risk = 1
    s.is_dora = False
    s.is_nis2 = False
    s.is_ens = False
    s.is_data_processor = False
    s.processes_personal_data = False
    return s


def _high_risk_supplier() -> Supplier:
    """Proveedor de riesgo maximo: todos los parametros en sus valores mas altos."""
    s = Supplier()
    s.data_sensitivity = 5
    s.data_volume = 5
    s.system_access_type = "admin_to_our_systems"
    s.business_criticality = 5
    s.geographic_risk = 5
    s.is_dora = True
    s.is_nis2 = True
    s.is_ens = False
    s.is_data_processor = False
    s.processes_personal_data = True
    return s


# ---------------------------------------------------------------------------
# compute_inherent_risk
# ---------------------------------------------------------------------------

class TestComputeInherentRisk:
    def test_low_risk_yields_low_score(self):
        score = compute_inherent_risk(_low_risk_supplier())
        # Riesgo bajo: los factores minimos deben producir un score reducido
        assert score < 30

    def test_high_risk_yields_high_score(self):
        score = compute_inherent_risk(_high_risk_supplier())
        # Riesgo maximo: todos los factores al maximo deben producir un score elevado
        assert score >= 70

    def test_high_greater_than_low(self):
        low_score = compute_inherent_risk(_low_risk_supplier())
        high_score = compute_inherent_risk(_high_risk_supplier())
        assert high_score > low_score

    def test_score_within_0_100(self):
        low_score = compute_inherent_risk(_low_risk_supplier())
        high_score = compute_inherent_risk(_high_risk_supplier())
        assert 0 <= low_score <= 100
        assert 0 <= high_score <= 100

    def test_result_is_integer(self):
        score = compute_inherent_risk(_low_risk_supplier())
        assert isinstance(score, int)

    def test_none_attributes_handled_gracefully(self):
        """Atributos None en Supplier no deben lanzar excepcion."""
        s = Supplier()
        s.data_sensitivity = None
        s.data_volume = None
        s.system_access_type = None
        s.business_criticality = None
        s.geographic_risk = None
        s.is_dora = False
        s.is_nis2 = False
        s.is_ens = False
        s.is_data_processor = False
        s.processes_personal_data = False
        score = compute_inherent_risk(s)
        assert 0 <= score <= 100

    def test_system_access_type_admin_raises_score(self):
        """Acceso admin debe producir score mas alto que sin acceso."""
        s_none = _low_risk_supplier()
        s_admin = _low_risk_supplier()
        s_admin.system_access_type = "admin_to_our_systems"
        assert compute_inherent_risk(s_admin) > compute_inherent_risk(s_none)

    def test_monotonicity_data_sensitivity(self):
        """Incrementar data_sensitivity no debe reducir el inherent score."""
        scores = []
        for level in range(1, 6):
            s = _low_risk_supplier()
            s.data_sensitivity = level
            scores.append(compute_inherent_risk(s))
        for i in range(len(scores) - 1):
            assert scores[i + 1] >= scores[i], (
                f"Score no monotono en data_sensitivity {i+1}→{i+2}: "
                f"{scores[i]}→{scores[i+1]}"
            )

    def test_regulatory_flags_raise_score(self):
        """NIS2 + DORA + processes_personal_data deben elevar el score."""
        base = _low_risk_supplier()
        regulated = _low_risk_supplier()
        regulated.is_nis2 = True
        regulated.is_dora = True
        regulated.processes_personal_data = True
        assert compute_inherent_risk(regulated) > compute_inherent_risk(base)


# ---------------------------------------------------------------------------
# derive_tier — umbrales §4.3
# ---------------------------------------------------------------------------

class TestDeriveTier:
    def test_score_80_is_critical(self):
        assert derive_tier(80) == SupplierTier.CRITICAL

    def test_score_100_is_critical(self):
        assert derive_tier(100) == SupplierTier.CRITICAL

    def test_score_79_is_high(self):
        assert derive_tier(79) == SupplierTier.HIGH

    def test_score_60_is_high(self):
        assert derive_tier(60) == SupplierTier.HIGH

    def test_score_59_is_medium(self):
        assert derive_tier(59) == SupplierTier.MEDIUM

    def test_score_30_is_medium(self):
        assert derive_tier(30) == SupplierTier.MEDIUM

    def test_score_29_is_low(self):
        assert derive_tier(29) == SupplierTier.LOW

    def test_score_0_is_low(self):
        assert derive_tier(0) == SupplierTier.LOW

    def test_all_tiers_reachable(self):
        """Todos los valores de SupplierTier deben ser alcanzables."""
        reached = {
            derive_tier(0),
            derive_tier(30),
            derive_tier(60),
            derive_tier(80),
        }
        assert SupplierTier.LOW in reached
        assert SupplierTier.MEDIUM in reached
        assert SupplierTier.HIGH in reached
        assert SupplierTier.CRITICAL in reached


# ---------------------------------------------------------------------------
# compute_residual_risk — §5.2
# ---------------------------------------------------------------------------

class TestComputeResidualRisk:
    def test_50_percent_effectiveness_halves_inherent(self):
        # residual = round(80 * (1 - 50/100)) = 40
        assert compute_residual_risk(80, 50) == 40

    def test_zero_effectiveness_equals_inherent(self):
        assert compute_residual_risk(80, 0) == 80

    def test_full_effectiveness_yields_zero(self):
        assert compute_residual_risk(80, 100) == 0

    def test_none_effectiveness_treated_as_zero(self):
        assert compute_residual_risk(80, None) == 80

    def test_result_is_integer(self):
        result = compute_residual_risk(70, 30)
        assert isinstance(result, int)

    def test_effectiveness_clamped_above_100(self):
        """Efectividad > 100 se acota a 100 -> residual = 0."""
        assert compute_residual_risk(60, 150) == 0

    def test_effectiveness_clamped_below_0(self):
        """Efectividad < 0 se acota a 0 -> residual = inherent."""
        assert compute_residual_risk(60, -20) == 60

    def test_residual_never_exceeds_inherent(self):
        for ce in range(0, 101, 10):
            assert compute_residual_risk(75, ce) <= 75

    def test_zero_inherent_yields_zero_residual(self):
        assert compute_residual_risk(0, 0) == 0
        assert compute_residual_risk(0, 100) == 0


# ---------------------------------------------------------------------------
# risk_level_label — mapeo score -> nivel §5.1
# ---------------------------------------------------------------------------

class TestRiskLevelLabel:
    # posture = 100 - score
    # posture < 25  -> critical  => score > 75
    # posture < 50  -> high      => score 51..75
    # posture < 75  -> medium    => score 26..50
    # posture < 90  -> low       => score 11..25
    # else          -> very_low  => score <= 10

    def test_score_90_is_critical(self):
        # posture = 10 < 25
        assert risk_level_label(90) == "critical"

    def test_score_76_is_critical(self):
        # posture = 24 < 25
        assert risk_level_label(76) == "critical"

    def test_score_75_is_high(self):
        # posture = 25, NOT < 25; posture < 50 -> high
        assert risk_level_label(75) == "high"

    def test_score_60_is_high(self):
        # posture = 40 < 50
        assert risk_level_label(60) == "high"

    def test_score_51_is_high(self):
        # posture = 49 < 50
        assert risk_level_label(51) == "high"

    def test_score_50_is_medium(self):
        # posture = 50, NOT < 50; posture < 75 -> medium
        assert risk_level_label(50) == "medium"

    def test_score_30_is_medium(self):
        # posture = 70 < 75
        assert risk_level_label(30) == "medium"

    def test_score_26_is_medium(self):
        # posture = 74 < 75
        assert risk_level_label(26) == "medium"

    def test_score_25_is_low(self):
        # posture = 75, NOT < 75; posture < 90 -> low
        assert risk_level_label(25) == "low"

    def test_score_15_is_low(self):
        # posture = 85 < 90
        assert risk_level_label(15) == "low"

    def test_score_11_is_low(self):
        # posture = 89 < 90
        assert risk_level_label(11) == "low"

    def test_score_10_is_very_low(self):
        # posture = 90, NOT < 90 -> very_low
        assert risk_level_label(10) == "very_low"

    def test_score_5_is_very_low(self):
        assert risk_level_label(5) == "very_low"

    def test_score_0_is_very_low(self):
        # posture = 100 -> very_low
        assert risk_level_label(0) == "very_low"

    def test_none_returns_unknown(self):
        assert risk_level_label(None) == "unknown"

    def test_score_100_is_critical(self):
        # posture = 0 < 25
        assert risk_level_label(100) == "critical"


# ---------------------------------------------------------------------------
# score_questionnaire — §4.7.1
# ---------------------------------------------------------------------------

def _make_ynp_question(qid: str, weight: float = 1.0,
                        requires_evidence: bool = False) -> dict:
    """Construye una pregunta yes/no/partial con scoring_rules YNP."""
    return {
        "id": qid,
        "text": f"Pregunta {qid}",
        "type": "yes_no_partial",
        "domain": "governance",
        "control_refs": [],
        "weight": weight,
        "scoring_rules": {"yes": 100, "partial": 50, "no": 0, "na": None},
        "requires_evidence": requires_evidence,
    }


class TestScoreQuestionnaire:
    def test_all_yes_returns_100(self):
        questions = [
            _make_ynp_question("q1"),
            _make_ynp_question("q2"),
            _make_ynp_question("q3"),
        ]
        answers = {"q1": "yes", "q2": "yes", "q3": "yes"}
        result = score_questionnaire(questions, answers)
        assert result["score"] == 100
        assert result["answered"] == 3
        assert result["total"] == 3

    def test_all_no_returns_0(self):
        questions = [_make_ynp_question("q1"), _make_ynp_question("q2")]
        answers = {"q1": "no", "q2": "no"}
        result = score_questionnaire(questions, answers)
        assert result["score"] == 0
        assert result["answered"] == 2

    def test_mixed_answers_weighted_average(self):
        """q1(weight=2, yes=100) + q2(weight=1, no=0) -> weighted = (200+0)/3 = 66.67 -> 67."""
        questions = [
            _make_ynp_question("q1", weight=2.0),
            _make_ynp_question("q2", weight=1.0),
        ]
        answers = {"q1": "yes", "q2": "no"}
        result = score_questionnaire(questions, answers)
        expected = int(round((100 * 2.0 + 0 * 1.0) / (2.0 + 1.0)))
        assert result["score"] == expected
        assert result["answered"] == 2

    def test_partial_scores_50(self):
        questions = [_make_ynp_question("q1")]
        result = score_questionnaire(questions, {"q1": "partial"})
        assert result["score"] == 50

    def test_unanswered_question_excluded(self):
        """Una pregunta sin respuesta no penaliza el score ni cuenta como answered."""
        questions = [
            _make_ynp_question("q1"),
            _make_ynp_question("q2"),
        ]
        answers = {"q1": "yes"}  # q2 no respondida
        result = score_questionnaire(questions, answers)
        assert result["answered"] == 1
        assert result["total"] == 2
        assert result["score"] == 100  # solo q1 contribuye

    def test_none_answer_excluded(self):
        """Respuesta None no cuenta."""
        questions = [_make_ynp_question("q1"), _make_ynp_question("q2")]
        answers = {"q1": "yes", "q2": None}
        result = score_questionnaire(questions, answers)
        assert result["answered"] == 1
        assert result["score"] == 100

    def test_empty_answers_returns_zero(self):
        questions = [_make_ynp_question("q1")]
        result = score_questionnaire(questions, {})
        assert result["score"] == 0
        assert result["answered"] == 0
        assert result["total"] == 1

    def test_empty_questions_returns_zero(self):
        result = score_questionnaire([], {"q1": "yes"})
        assert result["score"] == 0
        assert result["answered"] == 0
        assert result["total"] == 0

    def test_by_question_contains_all_ids(self):
        questions = [_make_ynp_question("q1"), _make_ynp_question("q2")]
        answers = {"q1": "yes"}
        result = score_questionnaire(questions, answers)
        assert "q1" in result["by_question"]
        assert "q2" in result["by_question"]
        assert result["by_question"]["q1"] == 100.0
        assert result["by_question"]["q2"] is None  # no respondida

    def test_evidence_penalty_halves_contribution(self):
        """Pregunta con requires_evidence=True y sin clave __evidence -> score * 0.5."""
        q = _make_ynp_question("q1", requires_evidence=True)
        result = score_questionnaire([q], {"q1": "yes"})
        # 100 * 0.5 = 50
        assert result["score"] == 50
        assert result["by_question"]["q1"] == pytest.approx(50.0)

    def test_evidence_uploaded_but_unverified_gets_partial_credit(self):
        """Evidencia aportada pero sin revision IA del contenido -> x0.7 (v6)."""
        q = _make_ynp_question("q1", requires_evidence=True)
        answers = {"q1": "yes", "q1__evidence": "certificado_ISO27001.pdf"}
        result = score_questionnaire([q], answers)
        assert result["score"] == 70

    def test_evidence_verified_consistent_full_credit(self):
        """Evidencia revisada por IA y consistente con la respuesta -> x1.0."""
        q = _make_ynp_question("q1", requires_evidence=True)
        answers = {"q1": "yes"}
        evidence = {"q1": {"filename": "cert.pdf",
                           "ai_review": {"consistency": "consistent"}}}
        result = score_questionnaire([q], answers, evidence=evidence)
        assert result["score"] == 100

    def test_evidence_contradictory_heavier_penalty(self):
        """Evidencia que CONTRADICE la respuesta declarada -> x0.4."""
        q = _make_ynp_question("q1", requires_evidence=True)
        answers = {"q1": "yes"}
        evidence = {"q1": {"filename": "cert.pdf",
                           "ai_review": {"consistency": "contradictory"}}}
        result = score_questionnaire([q], answers, evidence=evidence)
        assert result["score"] == 40

    def test_evidence_penalty_does_not_affect_non_evidence_question(self):
        """Preguntas sin requires_evidence no se penalizan aunque falte evidencia."""
        q = _make_ynp_question("q1", requires_evidence=False)
        result = score_questionnaire([q], {"q1": "yes"})
        assert result["score"] == 100

    def test_evidence_penalty_on_partial_answer(self):
        """Penalizacion del 0.5 tambien aplica sobre respuesta 'partial' (50)."""
        q = _make_ynp_question("q1", requires_evidence=True)
        result = score_questionnaire([q], {"q1": "partial"})
        assert result["by_question"]["q1"] == pytest.approx(25.0)  # 50 * 0.5

    def test_na_answer_excluded_from_score(self):
        """La opcion 'na' mapea a None en las scoring_rules -> se excluye."""
        questions = [
            _make_ynp_question("q1"),
            _make_ynp_question("q2"),
        ]
        answers = {"q1": "yes", "q2": "na"}
        result = score_questionnaire(questions, answers)
        # q2 con 'na' -> None -> excluida del calculo
        assert result["answered"] == 1
        assert result["score"] == 100
