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


def test_literal_get_routes_not_shadowed_by_asset_id(client, auth_headers):
    # Regresion: GET /{asset_id} declarado antes convertia estas rutas en 422
    for path in ("/api/assets/analysis-status", "/api/assets/group-analysis-status"):
        resp = client.get(path, headers=auth_headers)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}: {resp.text[:120]}"
