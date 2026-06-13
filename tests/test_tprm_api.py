"""Tests de API REST del modulo TPRM.

Utiliza las fixtures `client` y `auth_headers` de conftest.py.
Todos los endpoints requieren autenticacion.
"""
import pytest


# ---------------------------------------------------------------------------
# Biblioteca de plantillas (GET /api/tprm/questionnaire-templates)
# ---------------------------------------------------------------------------

class TestQuestionnaireTemplatesEndpoint:
    def test_list_templates_requires_auth(self, client):
        resp = client.get("/api/tprm/questionnaire-templates")
        assert resp.status_code == 401

    def test_list_templates_returns_200(self, client, auth_headers):
        resp = client.get("/api/tprm/questionnaire-templates", headers=auth_headers)
        assert resp.status_code == 200

    def test_list_templates_returns_non_empty_list(self, client, auth_headers):
        resp = client.get("/api/tprm/questionnaire-templates", headers=auth_headers)
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 7

    def test_list_templates_entries_have_required_fields(self, client, auth_headers):
        resp = client.get("/api/tprm/questionnaire-templates", headers=auth_headers)
        for t in resp.json():
            assert "code" in t
            assert "name" in t
            assert "question_count" in t
            assert t["question_count"] > 0

    def test_list_templates_all_are_system_templates(self, client, auth_headers):
        resp = client.get("/api/tprm/questionnaire-templates", headers=auth_headers)
        for t in resp.json():
            assert t.get("is_system_template") is True

    def test_list_templates_known_codes_present(self, client, auth_headers):
        resp = client.get("/api/tprm/questionnaire-templates", headers=auth_headers)
        codes = {t["code"] for t in resp.json()}
        for expected in (
            "RH_TPRM_ISO27001_FULL_v1",
            "RH_TPRM_NIS2_v1",
            "RH_TPRM_GDPR_PROCESSOR_v1",
            "RH_TPRM_OFFBOARDING_v1",
        ):
            assert expected in codes


class TestGetQuestionnaireTemplate:
    def test_get_nis2_template_returns_200(self, client, auth_headers):
        resp = client.get(
            "/api/tprm/questionnaire-templates/RH_TPRM_NIS2_v1",
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_get_nis2_template_has_questions(self, client, auth_headers):
        resp = client.get(
            "/api/tprm/questionnaire-templates/RH_TPRM_NIS2_v1",
            headers=auth_headers,
        )
        data = resp.json()
        assert "questions" in data
        assert len(data["questions"]) >= 10

    def test_get_nis2_template_code_matches(self, client, auth_headers):
        resp = client.get(
            "/api/tprm/questionnaire-templates/RH_TPRM_NIS2_v1",
            headers=auth_headers,
        )
        assert resp.json()["code"] == "RH_TPRM_NIS2_v1"

    def test_get_nonexistent_template_returns_404(self, client, auth_headers):
        resp = client.get(
            "/api/tprm/questionnaire-templates/nope",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_get_template_requires_auth(self, client):
        resp = client.get("/api/tprm/questionnaire-templates/RH_TPRM_NIS2_v1")
        assert resp.status_code == 401

    @pytest.mark.parametrize("code", [
        "RH_TPRM_LITE_v1",
        "RH_TPRM_ISO27001_FULL_v1",
        "RH_TPRM_GDPR_PROCESSOR_v1",
        "RH_TPRM_NIS2_v1",
        "RH_TPRM_DORA_ICT_v1",
        "RH_TPRM_AI_USAGE_DECLARATION_v1",
        "RH_TPRM_OFFBOARDING_v1",
    ])
    def test_each_known_template_is_retrievable(self, client, auth_headers, code):
        resp = client.get(
            f"/api/tprm/questionnaire-templates/{code}",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Template '{code}' returned {resp.status_code}"
        data = resp.json()
        assert data["code"] == code
        assert len(data["questions"]) > 0


# ---------------------------------------------------------------------------
# Dashboard summary (GET /api/tprm/dashboard/summary)
# ---------------------------------------------------------------------------

class TestDashboardSummary:
    def test_summary_requires_auth(self, client):
        resp = client.get("/api/tprm/dashboard/summary")
        assert resp.status_code == 401

    def test_summary_returns_200(self, client, auth_headers):
        resp = client.get("/api/tprm/dashboard/summary", headers=auth_headers)
        assert resp.status_code == 200

    def test_summary_has_required_keys(self, client, auth_headers):
        resp = client.get("/api/tprm/dashboard/summary", headers=auth_headers)
        data = resp.json()
        assert "total" in data
        assert "by_tier" in data
        assert "by_residual_level" in data
        assert "regulatory_scope" in data

    def test_summary_total_is_non_negative_int(self, client, auth_headers):
        resp = client.get("/api/tprm/dashboard/summary", headers=auth_headers)
        data = resp.json()
        assert isinstance(data["total"], int)
        assert data["total"] >= 0

    def test_summary_by_tier_has_expected_keys(self, client, auth_headers):
        resp = client.get("/api/tprm/dashboard/summary", headers=auth_headers)
        by_tier = resp.json()["by_tier"]
        for key in ("critical", "high", "medium", "low", "unrated"):
            assert key in by_tier

    def test_summary_by_residual_level_has_expected_keys(self, client, auth_headers):
        resp = client.get("/api/tprm/dashboard/summary", headers=auth_headers)
        by_res = resp.json()["by_residual_level"]
        for key in ("critical", "high", "medium", "low", "very_low", "unknown"):
            assert key in by_res

    def test_summary_regulatory_scope_has_expected_keys(self, client, auth_headers):
        resp = client.get("/api/tprm/dashboard/summary", headers=auth_headers)
        scope = resp.json()["regulatory_scope"]
        for key in ("nis2", "dora", "ens", "gdpr_processors"):
            assert key in scope

    def test_summary_top_residual_is_list(self, client, auth_headers):
        resp = client.get("/api/tprm/dashboard/summary", headers=auth_headers)
        data = resp.json()
        assert "top_residual" in data
        assert isinstance(data["top_residual"], list)


# ---------------------------------------------------------------------------
# Dashboard heatmap (GET /api/tprm/dashboard/heatmap)
# ---------------------------------------------------------------------------

class TestDashboardHeatmap:
    def test_heatmap_requires_auth(self, client):
        resp = client.get("/api/tprm/dashboard/heatmap")
        assert resp.status_code == 401

    def test_heatmap_returns_200(self, client, auth_headers):
        resp = client.get("/api/tprm/dashboard/heatmap", headers=auth_headers)
        assert resp.status_code == 200

    def test_heatmap_returns_list(self, client, auth_headers):
        resp = client.get("/api/tprm/dashboard/heatmap", headers=auth_headers)
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Supplier creation + TPRM recompute
# ---------------------------------------------------------------------------

@pytest.fixture(scope="class")
def tprm_supplier(client, auth_headers):
    """Crea un proveedor con atributos TPRM de alto riesgo para los tests del modulo."""
    payload = {
        "name": "Test TPRM Supplier",
        "data_sensitivity": 5,
        "data_volume": 5,
        "system_access_type": "admin_to_our_systems",
        "business_criticality": 5,
        "is_nis2": True,
        "is_dora": True,
        "processes_personal_data": True,
    }
    resp = client.post("/api/suppliers/", json=payload, headers=auth_headers)
    assert resp.status_code == 200, f"Error al crear proveedor TPRM: {resp.text}"
    return resp.json()


class TestSupplierTPRMFlow:
    def test_create_supplier_returns_200(self, client, auth_headers, tprm_supplier):
        # El fixture ya verifica el status 200; solo confirmamos que tenemos un id
        assert "id" in tprm_supplier
        assert tprm_supplier["id"] > 0

    def test_create_supplier_has_code(self, client, auth_headers, tprm_supplier):
        assert tprm_supplier.get("code")

    def test_create_supplier_tier_populated(self, client, auth_headers, tprm_supplier):
        """El tier debe estar calculado tras la creacion (auto-recompute)."""
        supplier_id = tprm_supplier["id"]
        resp = client.get(f"/api/suppliers/{supplier_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("tier") is not None, "tier no fue calculado tras la creacion"

    def test_create_supplier_inherent_risk_score_populated(self, client, auth_headers, tprm_supplier):
        """inherent_risk_score debe estar calculado tras la creacion."""
        supplier_id = tprm_supplier["id"]
        resp = client.get(f"/api/suppliers/{supplier_id}", headers=auth_headers)
        data = resp.json()
        assert data.get("inherent_risk_score") is not None, (
            "inherent_risk_score no fue calculado tras la creacion"
        )
        assert data["inherent_risk_score"] > 0

    def test_create_high_risk_supplier_tier_is_critical_or_high(
        self, client, auth_headers, tprm_supplier
    ):
        """Un proveedor con todos los parametros al maximo debe clasificarse como critical o high."""
        supplier_id = tprm_supplier["id"]
        resp = client.get(f"/api/suppliers/{supplier_id}", headers=auth_headers)
        data = resp.json()
        assert data["tier"] in ("critical", "high"), (
            f"Se esperaba critical/high, se obtuvo: {data['tier']}"
        )

    def test_recompute_all_returns_200(self, client, auth_headers, tprm_supplier):
        resp = client.post("/api/tprm/vendors/recompute-all", headers=auth_headers)
        assert resp.status_code == 200

    def test_recompute_all_returns_recomputed_count(self, client, auth_headers, tprm_supplier):
        resp = client.post("/api/tprm/vendors/recompute-all", headers=auth_headers)
        data = resp.json()
        assert "recomputed" in data
        assert data["recomputed"] >= 1

    def test_recompute_all_requires_auth(self, client):
        resp = client.post("/api/tprm/vendors/recompute-all")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Recompute individual (POST /api/tprm/vendors/{id}/recompute-inherent-risk)
# ---------------------------------------------------------------------------

class TestRecomputeIndividual:
    def test_recompute_individual_returns_200(self, client, auth_headers, tprm_supplier):
        supplier_id = tprm_supplier["id"]
        resp = client.post(
            f"/api/tprm/vendors/{supplier_id}/recompute-inherent-risk",
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_recompute_individual_returns_scoring_fields(self, client, auth_headers, tprm_supplier):
        supplier_id = tprm_supplier["id"]
        resp = client.post(
            f"/api/tprm/vendors/{supplier_id}/recompute-inherent-risk",
            headers=auth_headers,
        )
        data = resp.json()
        for key in (
            "inherent_risk_score",
            "inherent_risk_level",
            "tier",
            "control_effectiveness",
            "residual_risk_score",
            "residual_risk_level",
            "reassessment_months",
        ):
            assert key in data, f"Campo '{key}' ausente en respuesta de recompute"

    def test_recompute_individual_nonexistent_returns_404(self, client, auth_headers):
        resp = client.post(
            "/api/tprm/vendors/999999/recompute-inherent-risk",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_recompute_individual_requires_auth(self, client, tprm_supplier):
        supplier_id = tprm_supplier["id"]
        resp = client.post(
            f"/api/tprm/vendors/{supplier_id}/recompute-inherent-risk"
        )
        assert resp.status_code == 401
