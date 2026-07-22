"""Plan Director v6.4.0 — informe PDS, adjuntos en OKR y revision por la direccion."""
import uuid

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _default_org(db):
    from app.models import Organization
    return db.query(Organization).first()


def _plan_with_content(client, auth_headers):
    plan = client.post("/api/strategic-plans/", json={
        "name": f"PDS {_uid()}", "period_start": "2026-01-01T00:00:00",
        "period_end": "2028-12-31T00:00:00", "scope_statement": "Toda la organizacion",
        "strategy_notes": "Reducir exposicion", "investment_capacity": 500000,
    }, headers=auth_headers).json()
    catalog = client.get("/api/initiatives/control-catalog", headers=auth_headers).json()
    client.put(f"/api/strategic-plans/{plan['id']}/targets", json={
        "targets": [{"control_id": c["control_id"], "target_maturity": 4,
                     "mandatory_by": "legal" if i == 0 else "riesgo"}
                    for i, c in enumerate(catalog[:5])],
        "replace": True,
    }, headers=auth_headers)
    cand = client.post(f"/api/strategic-plans/{plan['id']}/generate-initiatives",
                       headers=auth_headers).json()
    client.post(f"/api/strategic-plans/{plan['id']}/generate-initiatives/confirm",
                json={"candidates": cand["candidates"]}, headers=auth_headers)
    return plan


def test_strategic_plan_report_renders(client, auth_headers):
    plan = _plan_with_content(client, auth_headers)
    resp = client.get(f"/api/reports/strategic-plan/{plan['id']}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.content[:4] == b"%PDF"
    assert len(resp.content) > 3000


def test_strategic_plan_report_handles_empty_plan(client, auth_headers):
    """Un plan recien creado tambien debe producir documento, no reventar."""
    plan = client.post("/api/strategic-plans/", json={"name": f"Vacio {_uid()}"},
                       headers=auth_headers).json()
    resp = client.get(f"/api/reports/strategic-plan/{plan['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


def test_strategic_plan_report_404_for_other_org(client, auth_headers):
    resp = client.get("/api/reports/strategic-plan/999999", headers=auth_headers)
    assert resp.status_code == 404


def test_report_renders_after_approval(client, auth_headers):
    plan = _plan_with_content(client, auth_headers)
    approval_id = client.post(f"/api/strategic-plans/{plan['id']}/request-approval",
                              json={}, headers=auth_headers).json()["approvals"][0]["id"]
    client.post(f"/api/strategic-plans/approvals/{approval_id}/decide",
                json={"decision": "approved"}, headers=auth_headers)
    resp = client.get(f"/api/reports/strategic-plan/{plan['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


# ---------- Adjuntos y comentarios en el OKR ----------

def test_objective_persists_scope_units_and_comments(client, auth_headers):
    """Regresion del mismo patron que ya fallo con la iniciativa: campos nuevos
    que llegan en el POST y no se guardan."""
    ini = client.post("/api/initiatives/", json={"title": f"Ini {_uid()}"},
                      headers=auth_headers).json()
    resp = client.post(f"/api/initiatives/{ini['id']}/objectives", json={
        "definition": "OKR de prueba", "scope": "regional",
        "business_units": ["BU EA"], "comments": "Coordinar con planta",
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    detail = client.get(f"/api/initiatives/{ini['id']}", headers=auth_headers).json()
    okr = detail["objectives"][0]
    assert okr["scope"] == "regional"
    assert okr["business_units"] == ["BU EA"]
    assert okr["comments"] == "Coordinar con planta"


def test_attach_evidence_to_objective(client, auth_headers):
    from app.models import Evidence, EvidenceType

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        ev = Evidence(organization_id=org_id, code=f"EVD-{_uid()}", title="Acta de comite",
                      evidence_type=EvidenceType.RECORD, is_current=True)
        db.add(ev)
        db.commit()
        ev_id = ev.id
    finally:
        db.close()

    ini = client.post("/api/initiatives/", json={"title": f"Ini {_uid()}"},
                      headers=auth_headers).json()
    okr = client.post(f"/api/initiatives/{ini['id']}/objectives",
                      json={"definition": "OKR con prueba"}, headers=auth_headers).json()

    resp = client.post(f"/api/initiatives/{ini['id']}/objectives/{okr['id']}/attachments",
                       json={"evidence_id": ev_id}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["attachments"][0]["name"] == "Acta de comite"

    # No se duplica
    again = client.post(f"/api/initiatives/{ini['id']}/objectives/{okr['id']}/attachments",
                        json={"evidence_id": ev_id}, headers=auth_headers)
    assert again.status_code == 409

    # Se puede desadjuntar
    resp = client.delete(
        f"/api/initiatives/{ini['id']}/objectives/{okr['id']}/attachments/0",
        headers=auth_headers)
    assert resp.status_code == 204
    detail = client.get(f"/api/initiatives/{ini['id']}", headers=auth_headers).json()
    assert detail["objectives"][0]["attachments"] == []


def test_attachment_requires_a_reference(client, auth_headers):
    ini = client.post("/api/initiatives/", json={"title": f"Ini {_uid()}"},
                      headers=auth_headers).json()
    okr = client.post(f"/api/initiatives/{ini['id']}/objectives",
                      json={"definition": "OKR"}, headers=auth_headers).json()
    resp = client.post(f"/api/initiatives/{ini['id']}/objectives/{okr['id']}/attachments",
                       json={}, headers=auth_headers)
    assert resp.status_code == 422


# ---------- Revision por la direccion (ISO 27001 cl. 9.3.2) ----------

def test_management_review_includes_strategic_plan(client, auth_headers):
    """9.3.2 exige revisar el estado de las acciones decididas, y esas acciones
    viven en el Plan Director. Antes los KPIs no lo miraban."""
    from app.services.management_review_service import get_kpis

    plan = _plan_with_content(client, auth_headers)
    approval_id = client.post(f"/api/strategic-plans/{plan['id']}/request-approval",
                              json={}, headers=auth_headers).json()["approvals"][0]["id"]
    client.post(f"/api/strategic-plans/approvals/{approval_id}/decide",
                json={"decision": "approved"}, headers=auth_headers)

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        kpis = get_kpis(db, org_id)
    finally:
        db.close()

    assert "strategic_plan" in kpis
    sp = kpis["strategic_plan"]
    assert sp["has_approved_plan"] is True
    assert sp["plan_code"] == plan["code"]
    for key in ("initiatives_active", "initiatives_at_risk", "avg_progress",
                "projected_reduction_points", "achieved_reduction_points"):
        assert key in sp


def test_management_review_states_when_there_is_no_plan(client):
    """Que no exista plan aprobado es en si mismo informacion para el comite."""
    from app.models import Organization
    from app.services.management_review_service import get_strategic_plan_status

    db = _TestSession()
    try:
        org = Organization(name=f"Org sin plan {_uid()}", plan="enterprise")
        db.add(org)
        db.commit()
        status = get_strategic_plan_status(db, org.id)
    finally:
        db.close()

    assert status["has_approved_plan"] is False
    assert status["plan_code"] is None
    assert status["initiatives_active"] == 0
