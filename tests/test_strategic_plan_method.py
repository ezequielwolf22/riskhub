"""Plan Director v6.4.0 — el metodo completo.

Fases 1-2 (situacion actual y objetivo), 3 (gap -> proyectos) y 5 (aprobacion
formal de la direccion, ISO/IEC 27001 cl. 6.1.3f).
"""
import uuid

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _default_org(db):
    from app.models import Organization
    return db.query(Organization).first()


def _new_plan(client, auth_headers, **kw):
    payload = {"name": f"PDS {_uid()}", "framework_code": "iso27001"}
    payload.update(kw)
    resp = client.post("/api/strategic-plans/", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------- Fase 1: situacion actual ----------

def test_current_profile_counts_unimplemented_controls_as_zero(client, auth_headers):
    """Que un control NO exista es el dato mas relevante para un plan director:
    no puede omitirse del perfil."""
    plan = _new_plan(client, auth_headers)
    prof = client.get(f"/api/strategic-plans/{plan['id']}/current-profile",
                      headers=auth_headers).json()
    assert prof["total_controls"] >= 90, "el perfil debe cubrir el catalogo ISO 27002 completo"
    sin_impl = [e for e in prof["controls"] if not e["implemented"]]
    assert sin_impl, "en una org de test deberia haber controles sin implementar"
    assert all(e["maturity"] == 0 for e in sin_impl)
    assert prof["by_theme"]


# ---------- Fase 2: perfil objetivo ----------

def test_target_by_framework_expands_via_crossmap(client, auth_headers):
    """Un objetivo sobre una categoria NIST CSF se traduce a controles ISO 27002."""
    plan = _new_plan(client, auth_headers, framework_code="nist_csf")
    resp = client.put(f"/api/strategic-plans/{plan['id']}/targets", json={
        "targets": [{"framework_code": "nist_csf", "requirement_id": "PR.AA",
                     "target_maturity": 4, "mandatory_by": "riesgo"}],
        "replace": True,
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    data = client.get(f"/api/strategic-plans/{plan['id']}/targets", headers=auth_headers).json()
    assert len(data["declared"]) == 1
    assert len(data["resolved"]) > 1, "PR.AA deberia expandirse a varios controles ISO"
    assert all(r["target_maturity"] == 4 for r in data["resolved"])


def test_unresolvable_target_is_reported_not_dropped(client, auth_headers):
    """Regresion: el crossmap cubre 16 de las 21 categorias CSF. Un objetivo sin
    control ISO equivalente se descartaba en silencio, dejando al usuario creyendo
    que el plan cubria algo que en realidad no toca."""
    plan = _new_plan(client, auth_headers, framework_code="nist_csf")
    client.put(f"/api/strategic-plans/{plan['id']}/targets", json={
        "targets": [{"framework_code": "nist_csf", "requirement_id": "GV.OC",
                     "target_maturity": 3}],
        "replace": True,
    }, headers=auth_headers)

    data = client.get(f"/api/strategic-plans/{plan['id']}/targets", headers=auth_headers).json()
    assert data["resolved"] == []
    assert len(data["unresolved"]) == 1
    assert data["unresolved"][0]["requirement_id"] == "GV.OC"
    assert data["unresolved"][0]["reason"] == "sin_control_equivalente"

    gap = client.get(f"/api/strategic-plans/{plan['id']}/gap", headers=auth_headers).json()
    assert len(gap["unresolved_targets"]) == 1


# ---------- Fase 3: gap y generacion de proyectos ----------

def test_gap_only_lists_shortfalls_and_ranks_legal_first(client, auth_headers):
    from app.models import Control, ControlImplementation

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        controls = db.query(Control).order_by(Control.code).limit(3).all()
        ids = [c.id for c in controls]
        # El primero ya supera el objetivo: no es hueco, es fortaleza
        db.add(ControlImplementation(organization_id=org_id, control_id=ids[0],
                                     name=f"maduro {_uid()}", maturity=5))
        db.commit()
    finally:
        db.close()

    plan = _new_plan(client, auth_headers)
    client.put(f"/api/strategic-plans/{plan['id']}/targets", json={
        "targets": [
            {"control_id": ids[0], "target_maturity": 3, "mandatory_by": "riesgo"},
            {"control_id": ids[1], "target_maturity": 4, "mandatory_by": "riesgo"},
            {"control_id": ids[2], "target_maturity": 2, "mandatory_by": "legal"},
        ],
        "replace": True,
    }, headers=auth_headers)

    gap = client.get(f"/api/strategic-plans/{plan['id']}/gap", headers=auth_headers).json()
    listed = [g["control_id"] for g in gap["gaps"]]
    assert ids[0] not in listed, "un control por encima del objetivo no es un hueco"
    assert gap["gaps"][0]["mandatory_by"] == "legal", "lo obligatorio por ley va primero"
    assert gap["total_gap_points"] > 0
    assert gap["total_effort_days"] > 0


def test_generate_initiatives_is_deterministic(client, auth_headers):
    """Mismo gap, misma propuesta: la generacion no puede depender del azar."""
    from app.models import Control

    db = _TestSession()
    try:
        ids = [c.id for c in db.query(Control).order_by(Control.code).limit(6).all()]
    finally:
        db.close()

    plan = _new_plan(client, auth_headers)
    client.put(f"/api/strategic-plans/{plan['id']}/targets", json={
        "targets": [{"control_id": cid, "target_maturity": 4} for cid in ids],
        "replace": True,
    }, headers=auth_headers)

    first = client.post(f"/api/strategic-plans/{plan['id']}/generate-initiatives",
                        headers=auth_headers).json()
    second = client.post(f"/api/strategic-plans/{plan['id']}/generate-initiatives",
                         headers=auth_headers).json()
    assert first["candidates"] == second["candidates"]
    assert first["candidates"], "deberia proponer al menos una iniciativa"
    assert all(c["control_targets"] for c in first["candidates"])


def test_confirming_candidates_creates_initiatives(client, auth_headers):
    from app.models import Control

    db = _TestSession()
    try:
        ids = [c.id for c in db.query(Control).order_by(Control.code).limit(3).all()]
    finally:
        db.close()

    plan = _new_plan(client, auth_headers)
    client.put(f"/api/strategic-plans/{plan['id']}/targets", json={
        "targets": [{"control_id": cid, "target_maturity": 4} for cid in ids],
        "replace": True,
    }, headers=auth_headers)
    cand = client.post(f"/api/strategic-plans/{plan['id']}/generate-initiatives",
                       headers=auth_headers).json()
    resp = client.post(f"/api/strategic-plans/{plan['id']}/generate-initiatives/confirm",
                       json={"candidates": cand["candidates"]}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] >= 1

    # Lo ya cubierto no se vuelve a proponer
    again = client.post(f"/api/strategic-plans/{plan['id']}/generate-initiatives",
                        headers=auth_headers).json()
    assert again["controls_already_covered"] >= 1


# ---------- Fase 5: aprobacion formal (ISO 27001 cl. 6.1.3f) ----------

def test_approved_is_unreachable_by_patch(client, auth_headers):
    """La No Conformidad Mayor tipica es la aprobacion sin rastro. El estado
    aprobado solo puede alcanzarse cerrando una ronda de aprobacion."""
    plan = _new_plan(client, auth_headers)
    client.patch(f"/api/strategic-plans/{plan['id']}", json={"status": "approved"},
                 headers=auth_headers)
    after = client.get(f"/api/strategic-plans/{plan['id']}", headers=auth_headers).json()
    assert after["status"] != "approved"
    assert after["approved_at"] is None
    assert after["approved_by_id"] is None


def test_internal_seal_approval_seals_baseline(client, auth_headers):
    plan = _new_plan(client, auth_headers)
    resp = client.post(f"/api/strategic-plans/{plan['id']}/request-approval",
                       json={}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["plan_status"] == "pending_approval"
    approval_id = resp.json()["approvals"][0]["id"]

    resp = client.post(f"/api/strategic-plans/approvals/{approval_id}/decide",
                       json={"decision": "approved", "notes": "Comite"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["approved"] is True

    after = client.get(f"/api/strategic-plans/{plan['id']}", headers=auth_headers).json()
    assert after["status"] == "approved"
    assert after["approved_at"] is not None
    assert after["approved_by_id"] is not None
    assert after["baseline_sealed_at"] is not None, "aprobar debe congelar la linea base"


def test_rejection_returns_plan_to_draft(client, auth_headers):
    plan = _new_plan(client, auth_headers)
    approval_id = client.post(f"/api/strategic-plans/{plan['id']}/request-approval",
                              json={}, headers=auth_headers).json()["approvals"][0]["id"]
    resp = client.post(f"/api/strategic-plans/approvals/{approval_id}/decide",
                       json={"decision": "rejected", "notes": "Falta presupuesto"},
                       headers=auth_headers)
    assert resp.json()["rejected"] is True
    after = client.get(f"/api/strategic-plans/{plan['id']}", headers=auth_headers).json()
    assert after["status"] == "draft"


def test_decision_cannot_be_replayed(client, auth_headers):
    plan = _new_plan(client, auth_headers)
    approval_id = client.post(f"/api/strategic-plans/{plan['id']}/request-approval",
                              json={}, headers=auth_headers).json()["approvals"][0]["id"]
    client.post(f"/api/strategic-plans/approvals/{approval_id}/decide",
                json={"decision": "approved"}, headers=auth_headers)
    again = client.post(f"/api/strategic-plans/approvals/{approval_id}/decide",
                        json={"decision": "approved"}, headers=auth_headers)
    assert again.status_code == 409


def test_signature_mode_requires_an_approver(client, auth_headers):
    plan = _new_plan(client, auth_headers)
    resp = client.post(f"/api/strategic-plans/{plan['id']}/request-approval",
                       json={"mode": "signature", "approvers": []}, headers=auth_headers)
    assert resp.status_code == 422

    resp = client.post(f"/api/strategic-plans/{plan['id']}/request-approval", json={
        "mode": "signature",
        "approvers": [{"email": "ciso@test.internal", "name": "CISO", "order_index": 1}],
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    approvals = client.get(f"/api/strategic-plans/{plan['id']}/approvals",
                           headers=auth_headers).json()
    assert any(a["mode"] == "signature" and a["approver_email"] == "ciso@test.internal"
               for a in approvals)


def test_scope_change_after_approval_forces_new_version(client, auth_headers):
    """Lo aprobado por la direccion no puede mutar en silencio."""
    plan = _new_plan(client, auth_headers, scope_statement="Toda la organizacion")
    approval_id = client.post(f"/api/strategic-plans/{plan['id']}/request-approval",
                              json={}, headers=auth_headers).json()["approvals"][0]["id"]
    client.post(f"/api/strategic-plans/approvals/{approval_id}/decide",
                json={"decision": "approved"}, headers=auth_headers)

    client.patch(f"/api/strategic-plans/{plan['id']}",
                 json={"scope_statement": "Solo division industrial"}, headers=auth_headers)
    after = client.get(f"/api/strategic-plans/{plan['id']}", headers=auth_headers).json()
    assert after["version"] == 2
    assert after["status"] == "draft", "un cambio de alcance exige re-aprobacion"


def test_activate_requires_prior_approval(client, auth_headers):
    plan = _new_plan(client, auth_headers)
    resp = client.post(f"/api/strategic-plans/{plan['id']}/activate", headers=auth_headers)
    assert resp.status_code == 409


def test_content_drift_is_visible_after_approval(client, auth_headers):
    """Si el plan cambia despues de aprobarse, el informe debe decirlo: es justo
    lo que un auditor quiere ver, no algo que ocultar."""
    plan = _new_plan(client, auth_headers)
    approval_id = client.post(f"/api/strategic-plans/{plan['id']}/request-approval",
                              json={}, headers=auth_headers).json()["approvals"][0]["id"]
    client.post(f"/api/strategic-plans/approvals/{approval_id}/decide",
                json={"decision": "approved"}, headers=auth_headers)

    progress = client.get(f"/api/strategic-plans/{plan['id']}/progress",
                          headers=auth_headers).json()
    assert progress["approval"]["approved"] is True
    assert progress["approval"]["drifted"] is False

    # Anadir objetivos cambia el contenido aprobado
    from app.models import Control
    db = _TestSession()
    try:
        cid = db.query(Control).order_by(Control.code).first().id
    finally:
        db.close()
    client.put(f"/api/strategic-plans/{plan['id']}/targets", json={
        "targets": [{"control_id": cid, "target_maturity": 5}], "replace": True,
    }, headers=auth_headers)

    progress = client.get(f"/api/strategic-plans/{plan['id']}/progress",
                          headers=auth_headers).json()
    assert progress["approval"]["drifted"] is True
