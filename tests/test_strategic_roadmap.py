"""Plan Director v6.4.0 — cronograma, dependencias y auto-tareas (fase 4)."""
import uuid
from datetime import datetime, timedelta, timezone

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _default_org(db):
    from app.models import Organization
    return db.query(Organization).first()


def _mk(db, org_id, *, code=None, start=None, target=None, blocked_by=None,
        health="ok", status="in_progress"):
    from app.models import StrategicInitiative
    ini = StrategicInitiative(
        organization_id=org_id, code=code or f"INI-{_uid()}", title=f"Ini {_uid()}",
        status=status, health=health, start_date=start, target_date=target,
        blocked_by=blocked_by,
    )
    db.add(ini)
    db.flush()
    return ini


def test_critical_path_is_the_longest_dependency_chain(client):
    from app.services.initiative_projection_service import compute_critical_path

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        a = _mk(db, org_id, start=base, target=base + timedelta(days=100))
        b = _mk(db, org_id, start=base + timedelta(days=100),
                target=base + timedelta(days=300), blocked_by=[a.id])
        # Rama corta e independiente: no debe ganar
        corta = _mk(db, org_id, start=base, target=base + timedelta(days=20))
        db.commit()

        cp = compute_critical_path([a, b, corta])
        codes = [p["code"] for p in cp["path"]]
        assert codes == [a.code, b.code]
        assert cp["total_days"] == 300
        assert cp["cycles"] == []
    finally:
        db.close()


def test_dependency_cycle_is_detected_and_does_not_hang(client):
    """Un ciclo hace el plan inejecutable: hay que verlo, no colgar el calculo."""
    from app.services.initiative_projection_service import compute_critical_path

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        a = _mk(db, org_id)
        b = _mk(db, org_id, blocked_by=[a.id])
        c = _mk(db, org_id, blocked_by=[b.id])
        a.blocked_by = [c.id]          # cierra el ciclo
        db.commit()

        cp = compute_critical_path([a, b, c])
        assert cp["cycles"], "el ciclo deberia detectarse"
        assert {a.code, b.code, c.code} <= set(cp["cycles"][0])
    finally:
        db.close()


def test_self_dependency_is_ignored(client):
    from app.services.initiative_projection_service import compute_critical_path

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        a = _mk(db, org_id)
        a.blocked_by = [a.id]
        db.commit()
        cp = compute_critical_path([a])
        assert cp["cycles"] == []
    finally:
        db.close()


def test_blocked_health_is_inherited_by_dependents(client):
    """Si A esta bloqueada, B (que depende de A) tampoco puede avanzar."""
    from app.services.initiative_projection_service import _propagate_blocked_health

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        a = _mk(db, org_id, health="blocked")
        b = _mk(db, org_id, health="ok", blocked_by=[a.id])
        c = _mk(db, org_id, health="ok", blocked_by=[b.id])
        db.commit()

        _propagate_blocked_health(db, [a, b, c])
        assert b.health == "blocked"
        assert any("dependencia" in r for r in (b.health_reasons or []))
        assert c.health == "blocked", "la herencia debe encadenarse"
    finally:
        db.close()


def test_roadmap_endpoint_reports_counters_and_horizons(client, auth_headers):
    now = datetime.now(timezone.utc)
    prog = client.post("/api/initiatives/programs",
                       json={"name": f"Prog {_uid()}", "area": "GRC", "env": "OT"},
                       headers=auth_headers).json()
    vencida = client.post("/api/initiatives/", json={
        "title": f"Vencida {_uid()}", "program_id": prog["id"], "status": "in_progress",
        "start_date": (now - timedelta(days=200)).isoformat(),
        "target_date": (now - timedelta(days=10)).isoformat(),
        "business_units": ["BU EA"],
    }, headers=auth_headers).json()
    client.post("/api/initiatives/", json={
        "title": f"Larga {_uid()}", "program_id": prog["id"], "status": "in_progress",
        "start_date": now.isoformat(),
        "target_date": (now + timedelta(days=800)).isoformat(),
    }, headers=auth_headers)

    road = client.get("/api/initiatives/roadmap", headers=auth_headers).json()
    assert road["counters"]["overdue"] >= 1
    codes = {b["code"]: b for b in road["bars"]}
    assert codes[vencida["code"]]["horizon"] == "corto"
    assert "GRC" in road["areas"]
    assert "BU EA" in road["business_units"]
    assert any(b["horizon"] == "largo" for b in road["bars"])


def test_generate_tasks_from_control_targets_is_idempotent(client, auth_headers):
    """Puente entre lo estrategico y el kanban, sin duplicar trabajo."""
    catalog = client.get("/api/initiatives/control-catalog", headers=auth_headers).json()
    pending = [c for c in catalog if not c["implemented"]][:3]
    assert len(pending) == 3

    ini = client.post("/api/initiatives/", json={"title": f"Ini {_uid()}"},
                      headers=auth_headers).json()
    for c in pending:
        client.post(f"/api/initiatives/{ini['id']}/control-targets",
                    json={"control_id": c["control_id"], "target_maturity": 4},
                    headers=auth_headers)

    first = client.post(f"/api/initiatives/{ini['id']}/generate-tasks",
                        headers=auth_headers).json()
    assert first["created"] == 3
    second = client.post(f"/api/initiatives/{ini['id']}/generate-tasks",
                         headers=auth_headers).json()
    assert second["created"] == 0, "no debe duplicar tareas ya generadas"

    detail = client.get(f"/api/initiatives/{ini['id']}", headers=auth_headers).json()
    codes = [t["code"] for t in detail["tasks"]]
    assert len(codes) == len(set(codes)), "los codigos de tarea deben ser unicos"


def test_generate_tasks_skips_controls_already_at_target(client, auth_headers):
    from app.models import Control, ControlImplementation

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        control = db.query(Control).order_by(Control.code).first()
        impl = ControlImplementation(organization_id=org_id, control_id=control.id,
                                     name=f"ya maduro {_uid()}", maturity=5)
        db.add(impl)
        db.commit()
        impl_id = impl.id
    finally:
        db.close()

    ini = client.post("/api/initiatives/", json={"title": f"Ini {_uid()}"},
                      headers=auth_headers).json()
    client.post(f"/api/initiatives/{ini['id']}/control-targets",
                json={"implementation_id": impl_id, "target_maturity": 3},
                headers=auth_headers)
    resp = client.post(f"/api/initiatives/{ini['id']}/generate-tasks",
                       headers=auth_headers).json()
    assert resp["created"] == 0, "un control ya por encima del objetivo no genera trabajo"
