"""Tests de la biblioteca de plantillas de cuestionario TPRM del sistema (§4.4).

Sin BD ni cliente HTTP: solo valida la integridad estructural de las plantillas
en memoria.
"""
import pytest

from app.services.tprm_templates import get_template, list_templates, SYSTEM_TEMPLATES

# Codigos de plantillas del sistema que DEBEN existir (spec §4.4)
REQUIRED_CODES = [
    "RH_TPRM_ISO27001_FULL_v1",
    "RH_TPRM_NIS2_v1",
    "RH_TPRM_GDPR_PROCESSOR_v1",
    "RH_TPRM_OFFBOARDING_v1",
]

ALL_EXPECTED_CODES = [
    "RH_TPRM_LITE_v1",
    "RH_TPRM_ISO27001_FULL_v1",
    "RH_TPRM_GDPR_PROCESSOR_v1",
    "RH_TPRM_NIS2_v1",
    "RH_TPRM_DORA_ICT_v1",
    "RH_TPRM_AI_USAGE_DECLARATION_v1",
    "RH_TPRM_OFFBOARDING_v1",
]


class TestListTemplates:
    def test_returns_at_least_seven_entries(self):
        templates = list_templates()
        assert len(templates) >= 7

    def test_all_entries_have_code(self):
        for t in list_templates():
            assert "code" in t and t["code"]

    def test_all_entries_have_name(self):
        for t in list_templates():
            assert "name" in t and t["name"]

    def test_all_entries_have_positive_question_count(self):
        for t in list_templates():
            assert "question_count" in t
            assert t["question_count"] > 0, (
                f"Plantilla '{t['code']}' tiene question_count={t['question_count']}"
            )

    def test_all_entries_are_system_templates(self):
        for t in list_templates():
            assert t.get("is_system_template") is True, (
                f"Plantilla '{t['code']}' no es system template"
            )

    def test_required_codes_present(self):
        codes = {t["code"] for t in list_templates()}
        for code in REQUIRED_CODES:
            assert code in codes, f"Plantilla requerida '{code}' no encontrada"

    def test_all_known_codes_present(self):
        codes = {t["code"] for t in list_templates()}
        for code in ALL_EXPECTED_CODES:
            assert code in codes, f"Codigo conocido '{code}' ausente"

    def test_no_duplicate_codes(self):
        codes = [t["code"] for t in list_templates()]
        assert len(codes) == len(set(codes)), "Hay codigos duplicados en list_templates()"

    def test_metadata_shape(self):
        """Cada entrada del listado debe incluir los campos de metadatos."""
        required_keys = {"code", "name", "description", "framework_codes",
                         "target_tier", "estimated_minutes", "question_count",
                         "is_system_template"}
        for t in list_templates():
            missing = required_keys - set(t.keys())
            assert not missing, f"Plantilla '{t['code']}' falta: {missing}"

    def test_estimated_minutes_positive(self):
        for t in list_templates():
            assert t["estimated_minutes"] > 0

    def test_framework_codes_is_list(self):
        for t in list_templates():
            assert isinstance(t["framework_codes"], list)
            assert len(t["framework_codes"]) >= 1

    def test_target_tier_is_list(self):
        for t in list_templates():
            assert isinstance(t["target_tier"], list)
            assert len(t["target_tier"]) >= 1


class TestGetTemplate:
    def test_get_each_listed_template_returns_full_object(self):
        """Cada codigo en list_templates() debe devolver una plantilla completa."""
        for meta in list_templates():
            code = meta["code"]
            full = get_template(code)
            assert full is not None, f"get_template('{code}') devolvio None"
            assert full["code"] == code

    def test_question_count_matches_questions_list(self):
        """El question_count del listado debe coincidir con len(questions) en la plantilla."""
        for meta in list_templates():
            code = meta["code"]
            full = get_template(code)
            assert len(full["questions"]) == meta["question_count"], (
                f"Plantilla '{code}': question_count={meta['question_count']} "
                f"pero questions={len(full['questions'])}"
            )

    def test_nonexistent_template_returns_none(self):
        assert get_template("does_not_exist") is None

    def test_empty_string_returns_none(self):
        assert get_template("") is None

    def test_case_sensitive_lookup(self):
        """Los codigos son case-sensitive; version en minusculas no debe retornar nada."""
        assert get_template("rh_tprm_nis2_v1") is None

    @pytest.mark.parametrize("code", REQUIRED_CODES)
    def test_required_template_has_questions(self, code):
        full = get_template(code)
        assert full is not None
        assert len(full["questions"]) > 0


class TestTemplateStructuralIntegrity:
    """Integridad estructural de TODAS las plantillas del sistema."""

    @pytest.fixture(params=ALL_EXPECTED_CODES)
    def template(self, request):
        code = request.param
        t = get_template(code)
        assert t is not None, f"Plantilla '{code}' no existe"
        return t

    def test_template_has_code_and_name(self, template):
        assert template.get("code")
        assert template.get("name")

    def test_template_has_questions_list(self, template):
        assert isinstance(template.get("questions"), list)
        assert len(template["questions"]) > 0

    def test_every_question_has_non_empty_id(self, template):
        for q in template["questions"]:
            assert q.get("id"), (
                f"Pregunta en '{template['code']}' tiene id vacio: {q}"
            )

    def test_every_question_has_non_empty_text(self, template):
        for q in template["questions"]:
            assert q.get("text"), (
                f"Pregunta '{q.get('id')}' en '{template['code']}' tiene text vacio"
            )

    def test_every_question_has_numeric_weight(self, template):
        for q in template["questions"]:
            w = q.get("weight")
            assert isinstance(w, (int, float)), (
                f"Pregunta '{q.get('id')}' en '{template['code']}' tiene weight no numerico: {w!r}"
            )

    def test_scoring_rules_is_dict_when_present(self, template):
        for q in template["questions"]:
            sr = q.get("scoring_rules")
            if sr is not None:
                assert isinstance(sr, dict), (
                    f"Pregunta '{q.get('id')}' en '{template['code']}': "
                    f"scoring_rules no es dict: {sr!r}"
                )

    def test_control_refs_is_list(self, template):
        for q in template["questions"]:
            refs = q.get("control_refs")
            assert isinstance(refs, list), (
                f"Pregunta '{q.get('id')}' en '{template['code']}': "
                f"control_refs no es list: {refs!r}"
            )

    def test_requires_evidence_is_bool(self, template):
        for q in template["questions"]:
            re = q.get("requires_evidence")
            assert isinstance(re, bool), (
                f"Pregunta '{q.get('id')}' en '{template['code']}': "
                f"requires_evidence no es bool: {re!r}"
            )

    def test_question_ids_are_unique_within_template(self, template):
        ids = [q["id"] for q in template["questions"]]
        assert len(ids) == len(set(ids)), (
            f"Plantilla '{template['code']}' tiene ids duplicados: {ids}"
        )

    def test_question_type_present(self, template):
        for q in template["questions"]:
            assert q.get("type"), (
                f"Pregunta '{q.get('id')}' en '{template['code']}' sin type"
            )


class TestSpecificTemplates:
    """Validaciones de plantillas concretas por spec."""

    def test_iso27001_full_has_many_questions(self):
        t = get_template("RH_TPRM_ISO27001_FULL_v1")
        # 19 preguntas definidas en el modulo
        assert len(t["questions"]) >= 15

    def test_nis2_covers_ten_articles(self):
        t = get_template("RH_TPRM_NIS2_v1")
        # Art. 21.2 (a-j): al menos 10 preguntas
        assert len(t["questions"]) >= 10

    def test_gdpr_covers_art28(self):
        t = get_template("RH_TPRM_GDPR_PROCESSOR_v1")
        # Debe tener referencias a GDPR:art.28
        all_refs = [ref for q in t["questions"] for ref in q.get("control_refs", [])]
        assert any("GDPR:art.28" in r for r in all_refs)

    def test_offboarding_has_evidence_questions(self):
        t = get_template("RH_TPRM_OFFBOARDING_v1")
        evidence_qs = [q for q in t["questions"] if q.get("requires_evidence")]
        assert len(evidence_qs) >= 1, "Offboarding debe exigir evidencia en al menos 1 pregunta"

    def test_dora_references_dora_articles(self):
        t = get_template("RH_TPRM_DORA_ICT_v1")
        all_refs = [ref for q in t["questions"] for ref in q.get("control_refs", [])]
        assert any("DORA:" in r for r in all_refs)

    def test_ai_template_covers_ai_governance(self):
        t = get_template("RH_TPRM_AI_USAGE_DECLARATION_v1")
        domains = {q["domain"] for q in t["questions"]}
        assert "ai_governance" in domains
