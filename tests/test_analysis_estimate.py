"""Tests del estimador de coste del analisis masivo y del orden de rutas."""


def test_cost_estimate_endpoint(client, auth_headers):
    resp = client.get("/api/assets/analysis-cost-estimate", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in ("to_analyze", "covered_by_groups", "critical", "normal",
                "model_fast", "model_deep", "uses_batch_api", "estimated_cost_usd"):
        assert key in body, f"falta {key}"
    assert body["to_analyze"] == body["critical"] + body["normal"]
    assert "haiku" in body["model_fast"]


def test_force_deep_analysis_flag_switches_fast_tier(client, auth_headers):
    # Con el modo maxima calidad activo, el tier fast usa el modelo profundo
    resp = client.put("/api/ai/config/", headers=auth_headers,
                      json={"force_deep_analysis": True, "model": "claude-opus-4-6"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["force_deep_analysis"] is True

    est = client.get("/api/assets/analysis-cost-estimate", headers=auth_headers).json()
    assert "opus" in est["model_fast"], est

    # Al desactivarlo vuelve al modelo economico
    resp = client.put("/api/ai/config/", headers=auth_headers,
                      json={"force_deep_analysis": False})
    assert resp.status_code == 200
    est = client.get("/api/assets/analysis-cost-estimate", headers=auth_headers).json()
    assert "haiku" in est["model_fast"], est


def test_literal_get_routes_not_shadowed_by_asset_id(client, auth_headers):
    # Regresion: GET /{asset_id} declarado antes convertia estas rutas en 422
    for path in ("/api/assets/analysis-status", "/api/assets/group-analysis-status"):
        resp = client.get(path, headers=auth_headers)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}: {resp.text[:120]}"
