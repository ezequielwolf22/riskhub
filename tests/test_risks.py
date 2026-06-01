"""Tests de endpoints REST de riesgos."""


def test_list_risks_requires_auth(client):
    resp = client.get("/api/risks")
    assert resp.status_code == 401


def test_list_risks_with_auth(client, auth_headers):
    resp = client.get("/api/risks", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_create_risk_requires_asset(client, auth_headers):
    """Un riesgo sin asset_id debe fallar con 422 o 404."""
    payload = {
        "title": "Riesgo de prueba",
        "inherent_likelihood": 2,
        "inherent_consequence": 3,
    }
    resp = client.post("/api/risks", json=payload, headers=auth_headers)
    assert resp.status_code in (422, 400, 404)


def test_risk_levels_within_bounds(client, auth_headers):
    """Todos los riesgos listados deben tener niveles entre 0 y 8."""
    risks = client.get("/api/risks", headers=auth_headers).json()
    for risk in risks:
        if risk.get("inherent_level") is not None:
            assert 0 <= risk["inherent_level"] <= 8
        if risk.get("residual_level") is not None:
            assert 0 <= risk["residual_level"] <= 8
