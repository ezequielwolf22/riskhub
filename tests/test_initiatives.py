"""Plan Director — CRUD de programas/iniciativas/OKRs/control-targets/risk-links."""
import uuid

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _default_org(db):
    from app.models import Organization
    return db.query(Organization).first()


def _make_asset(db, org_id):
    from app.models import Asset, AssetType
    a = Asset(
        organization_id=org_id, code=f"AST-TEST-{_uid()}", name=f"Activo {_uid()}",
        asset_type=AssetType.SUPPORT_SOFTWARE,
    )
    db.add(a)
    db.flush()
    return a


def _make_threat(db):
    from app.models import Threat, ThreatOrigin
    th = Threat(
        code=f"THR-TEST-{_uid()}", name=f"Amenaza {_uid()}",
        origin=ThreatOrigin.DELIBERATE, is_custom=True,
    )
    db.add(th)
    db.flush()
    return th


def _make_risk(db, org_id, asset=None, threat=None, residual_level=6, treatment_option=None):
    from app.models import Risk, RiskStatus
    asset = asset or _make_asset(db, org_id)
    threat = threat or _make_threat(db)
    r = Risk(
        organization_id=org_id, code=f"RSK-TEST-{_uid()}",
        asset_id=asset.id, threat_id=threat.id,
        inherent_likelihood=4, inherent_consequence=4, inherent_level=8,
        residual_likelihood=4, residual_consequence=4, residual_level=residual_level,
        status=RiskStatus.ASSESSED, treatment_option=treatment_option,
    )
    db.add(r)
    db.flush()
    return r


def _make_second_org(db):
    from app.models import Organization
    org = Organization(name=f"Org secundaria {_uid()}", plan="enterprise")
    db.add(org)
    db.flush()
    return org


class _Ctx:
    """Contexto de datos creado en una sesion propia, con ids ya persistidos."""


def _setup(residual_level=6):
    db = _TestSession()
    try:
        org = _default_org(db)
        risk = _make_risk(db, org.id, residual_level=residual_level)
        db.commit()
        ctx = _Ctx()
        ctx.org_id = org.id
        ctx.risk_id = risk.id
        ctx.risk_code = risk.code
        return ctx
    finally:
        db.close()


# ---------- Programas ----------

def test_program_crud(client, auth_headers):
    resp = client.post("/api/initiatives/programs", json={
        "name": f"Programa GRC {_uid()}", "area": "GRC",
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    prog = resp.json()
    assert prog["code"].startswith("PRG-")
    assert prog["derived_status"] == "draft"
    assert prog["initiatives_count"] == 0

    resp = client.patch(f"/api/initiatives/programs/{prog['id']}", json={"area": "Arquitectura"},
                        headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["area"] == "Arquitectura"

    resp = client.get("/api/initiatives/programs", headers=auth_headers)
    assert resp.status_code == 200
    assert any(p["id"] == prog["id"] for p in resp.json())


def test_program_derived_status_reflects_initiatives(client, auth_headers):
    prog = client.post("/api/initiatives/programs", json={"name": f"Prog {_uid()}"},
                       headers=auth_headers).json()
    ini1 = client.post("/api/initiatives/", json={
        "title": f"Ini A {_uid()}", "program_id": prog["id"], "status": "in_progress",
    }, headers=auth_headers).json()
    client.post("/api/initiatives/", json={
        "title": f"Ini B {_uid()}", "program_id": prog["id"], "status": "completed",
    }, headers=auth_headers)

    resp = client.get("/api/initiatives/programs", headers=auth_headers)
    p = next(p for p in resp.json() if p["id"] == prog["id"])
    assert p["derived_status"] == "in_progress"
    assert p["initiatives_count"] == 2


def test_program_delete_blocked_with_initiatives(client, auth_headers):
    prog = client.post("/api/initiatives/programs", json={"name": f"Prog {_uid()}"},
                       headers=auth_headers).json()
    client.post("/api/initiatives/", json={"title": f"Ini {_uid()}", "program_id": prog["id"]},
               headers=auth_headers)
    resp = client.delete(f"/api/initiatives/programs/{prog['id']}", headers=auth_headers)
    assert resp.status_code == 409


# ---------- Iniciativas + OKRs ----------

def test_initiative_crud_and_system_fields_not_editable(client, auth_headers):
    resp = client.post("/api/initiatives/", json={
        "title": f"Iniciativa {_uid()}", "priority": "high",
        "health": "blocked", "progress": 99, "verification": {"x": 1},
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    ini = resp.json()
    assert ini["code"].startswith("INI-")
    assert ini["health"] == "ok"          # ignorado: no esta en InitiativeIn
    assert ini["progress"] == 0           # ignorado: no esta en InitiativeIn
    assert ini["verification"] is None    # ignorado: no esta en InitiativeIn
    assert ini["source"] == "manual"
    assert ini["ai_generated"] is False

    resp = client.patch(f"/api/initiatives/{ini['id']}", json={"priority": "critical"},
                        headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["priority"] == "critical"

    resp = client.get(f"/api/initiatives/{ini['id']}", headers=auth_headers)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["objectives"] == []
    assert detail["control_targets"] == []
    assert detail["risk_links"] == []


def test_initiative_okrs_progress_without_tasks(client, auth_headers):
    ini = client.post("/api/initiatives/", json={"title": f"Ini OKR {_uid()}"},
                      headers=auth_headers).json()
    okr1 = client.post(f"/api/initiatives/{ini['id']}/objectives", json={
        "definition": "OKR 1: primer objetivo medible", "progress": 50,
    }, headers=auth_headers)
    assert okr1.status_code == 200, okr1.text
    assert okr1.json()["code"].startswith("OKR-")

    okr2 = client.post(f"/api/initiatives/{ini['id']}/objectives", json={
        "definition": "OKR 2: segundo objetivo medible", "progress": 100,
    }, headers=auth_headers).json()

    detail = client.get(f"/api/initiatives/{ini['id']}", headers=auth_headers).json()
    assert detail["progress"] == 75   # media de 50 y 100

    client.patch(f"/api/initiatives/{ini['id']}/objectives/{okr2['id']}",
                json={"progress": 100, "status": "completed"}, headers=auth_headers)
    client.delete(f"/api/initiatives/{ini['id']}/objectives/{okr2['id']}", headers=auth_headers)
    detail = client.get(f"/api/initiatives/{ini['id']}", headers=auth_headers).json()
    assert detail["progress"] == 50  # solo queda el primer OKR


def test_initiative_progress_from_tasks_without_okrs(client, auth_headers):
    ini = client.post("/api/initiatives/", json={"title": f"Ini Tareas {_uid()}"},
                      headers=auth_headers).json()
    t1 = client.post("/api/tasks/", json={"title": "Tarea 1", "initiative_id": ini["id"]},
                     headers=auth_headers).json()
    client.post("/api/tasks/", json={"title": "Tarea 2", "initiative_id": ini["id"]},
               headers=auth_headers)

    client.patch(f"/api/tasks/{t1['id']}", json={"status": "done"}, headers=auth_headers)

    detail = client.get(f"/api/initiatives/{ini['id']}", headers=auth_headers).json()
    assert detail["progress"] == 50
    assert detail["tasks_total"] == 2
    assert detail["tasks_done"] == 1


def test_initiative_complete_triggers_verification(client, auth_headers):
    ini = client.post("/api/initiatives/", json={"title": f"Ini Verif {_uid()}"},
                      headers=auth_headers).json()
    resp = client.patch(f"/api/initiatives/{ini['id']}", json={"status": "completed"},
                        headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["progress"] == 100
    assert body["verification"] is not None
    assert body["verification"]["controls"]["total"] == 0


def test_initiative_delete_admin_detaches_tasks(client, auth_headers):
    ini = client.post("/api/initiatives/", json={"title": f"Ini Del {_uid()}"},
                      headers=auth_headers).json()
    task = client.post("/api/tasks/", json={"title": "Tarea huerfana", "initiative_id": ini["id"]},
                       headers=auth_headers).json()
    resp = client.delete(f"/api/initiatives/{ini['id']}", headers=auth_headers)
    assert resp.status_code == 204

    got = client.get(f"/api/tasks/{task['id']}", headers=auth_headers).json()
    assert got["initiative_id"] is None


# ---------- Control targets ----------

def test_control_target_seals_baseline_and_blocks_duplicate(client, auth_headers):
    db = _TestSession()
    try:
        org = _default_org(db)
        from app.models import Control, ControlImplementation, ControlStatus
        ctrl = Control(code=f"TEST-{_uid()}", name="Control de prueba", is_custom=True)
        db.add(ctrl)
        db.flush()
        impl = ControlImplementation(
            organization_id=org.id, control_id=ctrl.id, name="Impl de prueba",
            status=ControlStatus.PARTIAL, maturity=2,
        )
        db.add(impl)
        db.commit()
        impl_id = impl.id
    finally:
        db.close()

    ini = client.post("/api/initiatives/", json={"title": f"Ini CT {_uid()}"},
                      headers=auth_headers).json()
    resp = client.post(f"/api/initiatives/{ini['id']}/control-targets", json={
        "implementation_id": impl_id, "target_maturity": 4,
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    ct = resp.json()
    assert ct["baseline_maturity"] == 2
    assert ct["target_maturity"] == 4
    assert ct["current_maturity"] == 2

    dup = client.post(f"/api/initiatives/{ini['id']}/control-targets", json={
        "implementation_id": impl_id, "target_maturity": 5,
    }, headers=auth_headers)
    assert dup.status_code == 409


# ---------- Riesgos vinculados (manual) ----------

def test_manual_risk_link_flow(client, auth_headers):
    ctx = _setup(residual_level=6)
    ini = client.post("/api/initiatives/", json={"title": f"Ini Link {_uid()}"},
                      headers=auth_headers).json()

    resp = client.post(f"/api/initiatives/{ini['id']}/risks", json={
        "risk_id": ctx.risk_id, "rationale": "Vinculo manual de prueba",
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    link = resp.json()
    assert link["baseline_residual_level"] == 6
    assert link["origin"] == "manual"
    assert link["current_residual_level"] == 6

    dup = client.post(f"/api/initiatives/{ini['id']}/risks", json={"risk_id": ctx.risk_id},
                      headers=auth_headers)
    assert dup.status_code == 409

    resp = client.delete(f"/api/initiatives/{ini['id']}/risks/{ctx.risk_id}", headers=auth_headers)
    assert resp.status_code == 204


def test_manual_risk_link_rejects_risk_from_other_org(client, auth_headers):
    db = _TestSession()
    try:
        other_org = _make_second_org(db)
        risk = _make_risk(db, other_org.id, residual_level=7)
        db.commit()
        other_risk_id = risk.id
    finally:
        db.close()

    ini = client.post("/api/initiatives/", json={"title": f"Ini XOrg {_uid()}"},
                      headers=auth_headers).json()
    resp = client.post(f"/api/initiatives/{ini['id']}/risks", json={"risk_id": other_risk_id},
                       headers=auth_headers)
    assert resp.status_code == 404


def test_cannot_delete_auto_link_directly(client, auth_headers):
    """Un link origin=auto no se puede desvincular manualmente (409)."""
    ctx = _setup(residual_level=6)
    ini = client.post("/api/initiatives/", json={"title": f"Ini Auto {_uid()}"},
                      headers=auth_headers).json()
    db = _TestSession()
    try:
        from app.models import InitiativeRiskLink
        db.add(InitiativeRiskLink(
            organization_id=ctx.org_id, initiative_id=ini["id"], risk_id=ctx.risk_id,
            origin="auto", baseline_residual_level=6,
        ))
        db.commit()
    finally:
        db.close()

    resp = client.delete(f"/api/initiatives/{ini['id']}/risks/{ctx.risk_id}", headers=auth_headers)
    assert resp.status_code == 409


# ---------- Stats ----------

def test_stats_reports_coverage(client, auth_headers):
    ctx_covered = _setup(residual_level=7)
    ctx_uncovered = _setup(residual_level=6)

    ini = client.post("/api/initiatives/", json={"title": f"Ini Stats {_uid()}", "status": "in_progress"},
                      headers=auth_headers).json()
    client.post(f"/api/initiatives/{ini['id']}/risks", json={"risk_id": ctx_covered.risk_id},
               headers=auth_headers)

    resp = client.get("/api/initiatives/stats", headers=auth_headers)
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["initiatives_total"] >= 1
    uncovered_codes = {r["code"] for r in stats["high_risks_uncovered"]}
    assert ctx_uncovered.risk_code in uncovered_codes
    assert ctx_covered.risk_code not in uncovered_codes


def test_manual_link_gets_projection(client, auth_headers):
    """El vinculo manual dispara la proyeccion (spec 2.2): projected no queda en None."""
    ctx = _setup(residual_level=6)
    ini = client.post("/api/initiatives/", json={"title": f"Ini Proj {_uid()}"},
                      headers=auth_headers).json()
    link = client.post(f"/api/initiatives/{ini['id']}/risks", json={"risk_id": ctx.risk_id},
                       headers=auth_headers).json()
    assert link["projected_residual_level"] is not None


def test_create_initiative_rejects_cross_org_program(client, auth_headers):
    db = _TestSession()
    try:
        from app.models import StrategicProgram
        other_org = _make_second_org(db)
        foreign_prog = StrategicProgram(
            organization_id=other_org.id, code=f"PRG-X-{_uid()}", name="Programa ajeno",
        )
        db.add(foreign_prog)
        db.commit()
        foreign_prog_id = foreign_prog.id
    finally:
        db.close()

    resp = client.post("/api/initiatives/", json={
        "title": f"Ini XProg {_uid()}", "program_id": foreign_prog_id,
    }, headers=auth_headers)
    assert resp.status_code == 404

    # Tambien via PATCH sobre una iniciativa propia
    ini = client.post("/api/initiatives/", json={"title": f"Ini Propia {_uid()}"},
                      headers=auth_headers).json()
    resp = client.patch(f"/api/initiatives/{ini['id']}", json={"program_id": foreign_prog_id},
                        headers=auth_headers)
    assert resp.status_code == 404


def test_create_initiative_rejects_cross_org_owner(client, auth_headers):
    db = _TestSession()
    try:
        from app.models import User, UserRole
        other_org = _make_second_org(db)
        foreign_user = User(
            email=f"ajeno-{_uid()}@test.internal", full_name="Usuario Ajeno",
            hashed_password="x", role=UserRole.VIEWER, organization_id=other_org.id,
        )
        db.add(foreign_user)
        db.commit()
        foreign_user_id = foreign_user.id
    finally:
        db.close()

    resp = client.post("/api/initiatives/", json={
        "title": f"Ini XOwner {_uid()}", "owner_id": foreign_user_id,
    }, headers=auth_headers)
    assert resp.status_code == 404


def test_task_rejects_cross_org_initiative(client, auth_headers):
    db = _TestSession()
    try:
        from app.models import StrategicInitiative
        other_org = _make_second_org(db)
        foreign_ini = StrategicInitiative(
            organization_id=other_org.id, code=f"INI-X-{_uid()}", title="Iniciativa ajena",
        )
        db.add(foreign_ini)
        db.commit()
        foreign_ini_id = foreign_ini.id
    finally:
        db.close()

    resp = client.post("/api/tasks/", json={
        "title": "Tarea intrusa", "initiative_id": foreign_ini_id,
    }, headers=auth_headers)
    assert resp.status_code == 404


def test_delete_risk_cleans_initiative_links(client, auth_headers):
    ctx = _setup(residual_level=6)
    ini = client.post("/api/initiatives/", json={"title": f"Ini DelRisk {_uid()}"},
                      headers=auth_headers).json()
    client.post(f"/api/initiatives/{ini['id']}/risks", json={"risk_id": ctx.risk_id},
               headers=auth_headers)

    resp = client.delete(f"/api/risks/{ctx.risk_id}", headers=auth_headers)
    assert resp.status_code == 204

    db = _TestSession()
    try:
        from app.models import InitiativeRiskLink
        remaining = db.query(InitiativeRiskLink).filter(
            InitiativeRiskLink.risk_id == ctx.risk_id).count()
        assert remaining == 0
    finally:
        db.close()


def test_delete_impl_cleans_control_targets(client, auth_headers):
    db = _TestSession()
    try:
        org = _default_org(db)
        from app.models import Control, ControlImplementation, ControlStatus
        ctrl = Control(code=f"DELIMPL-{_uid()}", name="Control temporal", is_custom=True)
        db.add(ctrl)
        db.flush()
        impl = ControlImplementation(
            organization_id=org.id, control_id=ctrl.id, name="Impl temporal",
            status=ControlStatus.PARTIAL, maturity=2,
        )
        db.add(impl)
        db.commit()
        impl_id = impl.id
    finally:
        db.close()

    ini = client.post("/api/initiatives/", json={"title": f"Ini DelImpl {_uid()}"},
                      headers=auth_headers).json()
    client.post(f"/api/initiatives/{ini['id']}/control-targets", json={
        "implementation_id": impl_id, "target_maturity": 4,
    }, headers=auth_headers)

    resp = client.delete(f"/api/control-implementations/{impl_id}", headers=auth_headers)
    assert resp.status_code == 204

    detail = client.get(f"/api/initiatives/{ini['id']}", headers=auth_headers).json()
    assert detail["control_targets"] == []


def test_org_isolation_on_initiatives(client, auth_headers):
    db = _TestSession()
    try:
        other_org = _make_second_org(db)
        db.commit()
        other_org_id = other_org.id
    finally:
        db.close()

    # Iniciativa en la org por defecto (via API con el admin autenticado)
    ini = client.post("/api/initiatives/", json={"title": f"Ini Propia {_uid()}"},
                      headers=auth_headers).json()

    # Iniciativa creada directamente en la BD para otra organizacion
    db = _TestSession()
    try:
        from app.models import StrategicInitiative
        foreign = StrategicInitiative(
            organization_id=other_org_id, code=f"INI-FOREIGN-{_uid()}",
            title="Iniciativa de otra org",
        )
        db.add(foreign)
        db.commit()
        foreign_id = foreign.id
    finally:
        db.close()

    listed_ids = {i["id"] for i in client.get("/api/initiatives/", headers=auth_headers).json()}
    assert ini["id"] in listed_ids
    assert foreign_id not in listed_ids

    resp = client.get(f"/api/initiatives/{foreign_id}", headers=auth_headers)
    assert resp.status_code == 404
