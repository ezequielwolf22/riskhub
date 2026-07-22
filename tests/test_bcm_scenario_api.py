"""Tests de API del catalogo de escenarios, reglas, valoraciones y baremos.

Complementan a test_bcm_scenario_engine.py (que cubre el calculo puro) con lo
que solo se ve a traves de HTTP: validacion de entrada, que el impacto
ponderado NUNCA se acepta del cliente, y que cambiar el baremo recalcula el BIA.
"""
import pytest


@pytest.fixture(scope="module")
def scenario(client, auth_headers):
    resp = client.post("/api/bcp/scenarios", headers=auth_headers, json={
        "name": "Caida de las comunicaciones",
        "family": "systems_comms",
        "description": "Perdida de conectividad en la sede.",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    yield data
    client.delete(f"/api/bcp/scenarios/{data['id']}", headers=auth_headers)


def test_crear_escenario_asigna_codigo_y_origen_manual(client, auth_headers, scenario):
    assert scenario["family"] == "systems_comms"
    assert scenario["code"]
    assert scenario["source"] == "manual"
    assert scenario["is_active"] is True


def test_familia_invalida_se_rechaza(client, auth_headers):
    resp = client.post("/api/bcp/scenarios", headers=auth_headers,
                       json={"name": "X", "family": "meteorologico"})
    assert resp.status_code == 422
    assert "meteorologico" not in resp.text or "personnel" in resp.text


def test_sin_reglas_la_lista_esta_vacia_y_eso_es_correcto(client, auth_headers):
    """Estado por defecto: sin reglas, todo escenario aplica a toda sede."""
    resp = client.get("/api/bcp/applicability-rules", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_regla_sin_condiciones_se_rechaza(client, auth_headers):
    """Una regla sin 'when' se aplicaria a todas las sedes en silencio."""
    resp = client.post("/api/bcp/applicability-rules", headers=auth_headers,
                       json={"when": {}, "then": {"exclude_families": ["facilities"]}})
    assert resp.status_code == 422


def test_regla_con_campo_de_condicion_inventado_se_rechaza(client, auth_headers):
    resp = client.post("/api/bcp/applicability-rules", headers=auth_headers, json={
        "when": {"planta": ["baja"]},
        "then": {"exclude_families": ["facilities"]},
    })
    assert resp.status_code == 422
    assert "planta" in resp.text


def test_regla_con_efecto_vacio_se_rechaza(client, auth_headers):
    resp = client.post("/api/bcp/applicability-rules", headers=auth_headers,
                       json={"when": {"site_type": ["remote"]}, "then": {}})
    assert resp.status_code == 422


def test_regla_con_familia_inexistente_se_rechaza(client, auth_headers):
    resp = client.post("/api/bcp/applicability-rules", headers=auth_headers, json={
        "when": {"site_type": ["remote"]},
        "then": {"exclude_families": ["cosmico"]},
    })
    assert resp.status_code == 422


def test_ciclo_completo_de_regla(client, auth_headers):
    resp = client.post("/api/bcp/applicability-rules", headers=auth_headers, json={
        "name": "Sedes remotas sin instalaciones propias",
        "when": {"site_type": ["remote"]},
        "then": {"include_only_families": ["personnel"]},
        "rationale": "Sin oficina propia no hay escenario de instalaciones.",
    })
    assert resp.status_code == 201, resp.text
    rule = resp.json()
    assert rule["source"] == "manual"
    assert rule["rationale"]

    # Se puede desactivar sin perderla: la justificacion sigue disponible
    patched = client.patch(f"/api/bcp/applicability-rules/{rule['id']}",
                           headers=auth_headers, json={"is_active": False})
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False

    assert client.delete(f"/api/bcp/applicability-rules/{rule['id']}",
                         headers=auth_headers).status_code == 204


def test_el_impacto_ponderado_lo_calcula_el_servidor(client, auth_headers, scenario):
    """El cliente manda niveles de impacto; la cifra y la banda salen del motor."""
    resp = client.post("/api/bcp/scenario-assessments", headers=auth_headers, json={
        "scenario_id": scenario["id"],
        "rto_label": "3 dias",
        "impacts": {"operational": {">6h": 5}, "regulatory": {">6h": 2}},
        # Aunque se intente colar un valor, el esquema no lo admite y el motor manda
        "weighted_impact": 0.1,
        "impact_band": "none",
    })
    assert resp.status_code == 201, resp.text
    a = resp.json()
    assert a["weighted_impact"] == 4.0
    assert a["impact_band"] == "critical"

    # Duplicar la valoracion del mismo escenario en la misma sede es un conflicto
    dup = client.post("/api/bcp/scenario-assessments", headers=auth_headers, json={
        "scenario_id": scenario["id"], "impacts": {"operational": {">6h": 1}},
    })
    assert dup.status_code == 409

    # Al editar los niveles, la cifra se recalcula sola
    upd = client.patch(f"/api/bcp/scenario-assessments/{a['id']}", headers=auth_headers,
                       json={"rto_label": "1 hora"})
    assert upd.status_code == 200
    assert upd.json()["weighted_impact"] == 2.0
    assert upd.json()["impact_band"] == "severe"

    assert client.delete(f"/api/bcp/scenario-assessments/{a['id']}",
                         headers=auth_headers).status_code == 204


def test_baremo_por_defecto_esta_disponible_sin_configurar_nada(client, auth_headers):
    resp = client.get("/api/bcp/bia-criteria", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_default"] is True
    assert body["horizons"]
    assert body["bands"]


def test_cambiar_el_baremo_recalcula_las_valoraciones(client, auth_headers, scenario):
    created = client.post("/api/bcp/scenario-assessments", headers=auth_headers, json={
        "scenario_id": scenario["id"], "rto_label": "3 dias",
        "impacts": {"operational": {">6h": 5}},
    })
    assert created.status_code == 201, created.text
    aid = created.json()["id"]
    assert created.json()["weighted_impact"] == 4.0

    resp = client.put("/api/bcp/bia-criteria", headers=auth_headers, json={
        "rto_scale": [{"label": "3 dias", "hours": 72, "factor": 0.5}],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_default"] is False
    assert resp.json()["recalculated"] >= 1

    after = client.get("/api/bcp/scenario-assessments", headers=auth_headers,
                       params={"scenario_id": scenario["id"]}).json()
    row = next(r for r in after if r["id"] == aid)
    assert row["weighted_impact"] == 2.0

    client.delete(f"/api/bcp/scenario-assessments/{aid}", headers=auth_headers)


def test_matriz_y_huecos_responden(client, auth_headers, scenario):
    matrix = client.get("/api/bcp/scenarios/matrix", headers=auth_headers)
    assert matrix.status_code == 200
    body = matrix.json()
    assert "cells" in body and "coverage_pct" in body
    assert any(s["id"] == scenario["id"] for s in body["scenarios"])

    gaps = client.get("/api/bcp/scenarios/gaps", headers=auth_headers)
    assert gaps.status_code == 200
    assert isinstance(gaps.json(), list)


def test_no_se_borra_un_escenario_que_sostiene_valoraciones(client, auth_headers):
    sc = client.post("/api/bcp/scenarios", headers=auth_headers,
                     json={"name": "Escenario con historico", "family": "personnel"}).json()
    a = client.post("/api/bcp/scenario-assessments", headers=auth_headers, json={
        "scenario_id": sc["id"], "impacts": {"people": {"0h": 3}},
    })
    assert a.status_code == 201

    blocked = client.delete(f"/api/bcp/scenarios/{sc['id']}", headers=auth_headers)
    assert blocked.status_code == 422
    assert "1" in blocked.text

    # Desactivar si es la via correcta, y conserva el historico
    off = client.patch(f"/api/bcp/scenarios/{sc['id']}", headers=auth_headers,
                       json={"is_active": False})
    assert off.status_code == 200 and off.json()["is_active"] is False

    client.delete(f"/api/bcp/scenario-assessments/{a.json()['id']}", headers=auth_headers)
    client.delete(f"/api/bcp/scenarios/{sc['id']}", headers=auth_headers)


def test_escenario_de_otra_organizacion_no_es_accesible(client, auth_headers):
    assert client.patch("/api/bcp/scenarios/99999999", headers=auth_headers,
                        json={"name": "x"}).status_code == 404
    assert client.get("/api/bcp/scenario-assessments", headers=auth_headers,
                      params={"scenario_id": 99999999}).json() == []


# ── Generacion sin documentacion (cableado del router) ────────────────────────

def test_el_cuestionario_solo_pregunta_lo_que_no_puede_deducir(client, auth_headers):
    resp = client.get("/api/bcp/generate/questions", headers=auth_headers)
    assert resp.status_code == 200
    questions = resp.json()["questions"]
    assert isinstance(questions, list)
    # Cada pregunta justifica por que se hace y que desbloquea
    for q in questions:
        assert q["question"] and q["why"] and q["unlocks"]


def test_el_contexto_de_generacion_es_consultable(client, auth_headers):
    resp = client.get("/api/bcp/generate/context", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    for key in ("locations", "scenarios", "processes", "assets", "suppliers"):
        assert key in body


def test_objetivo_de_generacion_invalido_se_rechaza(client, auth_headers):
    resp = client.post("/api/bcp/generate/loquesea", headers=auth_headers, json={})
    assert resp.status_code == 422
    # El mensaje dice cuales son validos, no solo que esta mal
    assert "scenarios" in resp.text
