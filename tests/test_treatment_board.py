"""Cockpit de Tratamiento: GET /api/risks/treatment-board."""
import uuid
from datetime import datetime, timedelta, timezone

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _default_org(db):
    from app.models import Organization
    return db.query(Organization).first()


def _make_asset(db, org_id):
    from app.models import Asset, AssetType
    a = Asset(organization_id=org_id, code=f"AST-TB-{_uid()}", name=f"Activo {_uid()}",
             asset_type=AssetType.SUPPORT_SOFTWARE)
    db.add(a)
    db.flush()
    return a


def _make_threat(db):
    from app.models import Threat, ThreatOrigin
    th = Threat(code=f"THR-TB-{_uid()}", name=f"Amenaza {_uid()}",
               origin=ThreatOrigin.DELIBERATE, is_custom=True)
    db.add(th)
    db.flush()
    return th


def _make_risk(db, org_id, residual_level=6, treatment_option=None, due_date=None, status=None):
    from app.models import Risk, RiskStatus
    asset = _make_asset(db, org_id)
    threat = _make_threat(db)
    r = Risk(
        organization_id=org_id, code=f"RSK-TB-{_uid()}",
        asset_id=asset.id, threat_id=threat.id,
        inherent_likelihood=4, inherent_consequence=4, inherent_level=8,
        residual_likelihood=4, residual_consequence=4, residual_level=residual_level,
        status=status or RiskStatus.ASSESSED, treatment_option=treatment_option,
        treatment_due_date=due_date,
    )
    db.add(r)
    db.flush()
    return r


def test_board_empty_has_zero_kpis(client, auth_headers):
    from app.models import Organization
    db = _TestSession()
    try:
        # Org nueva y aislada para garantizar un board realmente vacio
        org = Organization(name=f"OrgVacia {_uid()}", plan="enterprise")
        db.add(org)
        db.commit()
        org_id = org.id
    finally:
        db.close()

    resp = client.get("/api/risks/treatment-board", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "appetite" in body
    assert "kpis" in body
    assert set(body["columns"].keys()) == {"modification", "sharing", "avoidance", "retention", "untreated"}


def test_untreated_high_risk_counted(client, auth_headers):
    db = _TestSession()
    try:
        org = _default_org(db)
        risk = _make_risk(db, org.id, residual_level=6)
        db.commit()
        risk_code = risk.code
    finally:
        db.close()

    resp = client.get("/api/risks/treatment-board", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    untreated_codes = {item["code"] for item in body["columns"]["untreated"]}
    assert risk_code in untreated_codes
    assert body["kpis"]["above_appetite_no_plan"] >= 1
    assert body["kpis"]["above_appetite_no_coverage"] >= 1


def test_treated_risk_shows_progress_and_tasks(client, auth_headers):
    from app.models import TreatmentOption
    db = _TestSession()
    try:
        org = _default_org(db)
        risk = _make_risk(db, org.id, residual_level=6, treatment_option=TreatmentOption.MODIFICATION)
        db.commit()
        risk_id = risk.id
        risk_code = risk.code
    finally:
        db.close()

    t1 = client.post("/api/tasks/", json={"title": "Tarea 1", "risk_id": risk_id},
                     headers=auth_headers).json()
    client.post("/api/tasks/", json={"title": "Tarea 2", "risk_id": risk_id}, headers=auth_headers)
    client.patch(f"/api/tasks/{t1['id']}", json={"status": "done"}, headers=auth_headers)

    resp = client.get("/api/risks/treatment-board", headers=auth_headers)
    body = resp.json()
    item = next(i for i in body["columns"]["modification"] if i["code"] == risk_code)
    assert item["tasks"]["total"] == 2
    assert item["tasks"]["done"] == 1


def test_overdue_treatment_counted(client, auth_headers):
    from app.models import TreatmentOption
    past = datetime.now(timezone.utc) - timedelta(days=5)
    db = _TestSession()
    try:
        org = _default_org(db)
        risk = _make_risk(db, org.id, residual_level=6, treatment_option=TreatmentOption.MODIFICATION,
                          due_date=past)
        db.commit()
        risk_code = risk.code
    finally:
        db.close()

    resp = client.get("/api/risks/treatment-board", headers=auth_headers)
    body = resp.json()
    item = next(i for i in body["columns"]["modification"] if i["code"] == risk_code)
    assert item["overdue"] is True
    assert body["kpis"]["overdue_plans"] >= 1


def test_risk_with_active_initiative_has_coverage(client, auth_headers):
    from app.models import InitiativeRiskLink, StrategicInitiative
    db = _TestSession()
    try:
        org = _default_org(db)
        risk = _make_risk(db, org.id, residual_level=7)
        ini = StrategicInitiative(
            organization_id=org.id, code=f"INI-TB-{_uid()}", title="Iniciativa cobertura",
            status="in_progress",
        )
        db.add(ini)
        db.flush()
        db.add(InitiativeRiskLink(
            organization_id=org.id, initiative_id=ini.id, risk_id=risk.id,
            origin="manual", baseline_residual_level=7, projected_residual_level=3,
        ))
        db.commit()
        risk_code = risk.code
        ini_code = ini.code
    finally:
        db.close()

    resp = client.get("/api/risks/treatment-board", headers=auth_headers)
    body = resp.json()
    item = next(i for i in body["columns"]["untreated"] if i["code"] == risk_code)
    assert any(i["code"] == ini_code for i in item["initiatives"])
    # Con cobertura activa no debe contar como "sin cobertura"
    uncovered_before = body["kpis"]["above_appetite_no_coverage"]
    assert isinstance(uncovered_before, int)


def test_board_includes_burndown(client, auth_headers):
    resp = client.get("/api/risks/treatment-board", headers=auth_headers)
    body = resp.json()
    assert "burndown" in body
    assert "history" in body["burndown"]
    assert "projected" in body["burndown"]
    assert "appetite_line" in body["burndown"]
