"""Plan Director v6.4.0 — priorizacion determinista (INCIBE fase 4).

La prioridad, los quick wins y la eficiencia se CALCULAN a partir de la
reduccion que proyecta el motor determinista. Nadie los teclea.
"""
import uuid

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _default_org(db):
    from app.models import Organization
    return db.query(Organization).first()


def _make_initiative(db, org_id, *, points, budget, effort_human, title=None):
    """Crea una iniciativa con una reduccion proyectada YA sellada.

    Se sella directamente en el link (baseline - projected = points) para poder
    probar la aritmetica de priorizacion sin depender del motor de riesgo, que
    ya tiene sus propios tests.
    """
    from app.models import (
        Asset, AssetType, InitiativeRiskLink, Risk, RiskStatus, StrategicInitiative, Threat,
    )
    threat = db.query(Threat).first()
    asset = Asset(organization_id=org_id, code=f"AST-{_uid()}", name=f"Activo {_uid()}",
                  asset_type=AssetType.SUPPORT_SOFTWARE)
    db.add(asset)
    db.flush()
    risk = Risk(organization_id=org_id, code=f"RSK-{_uid()}", asset_id=asset.id,
                threat_id=threat.id, inherent_likelihood=4, inherent_consequence=4,
                inherent_level=8, residual_level=8, status=RiskStatus.ASSESSED)
    db.add(risk)
    db.flush()
    ini = StrategicInitiative(
        organization_id=org_id, code=f"INI-{_uid()}", title=title or f"Ini {_uid()}",
        status="in_progress", budget=budget, effort_human=effort_human,
    )
    db.add(ini)
    db.flush()
    db.add(InitiativeRiskLink(
        organization_id=org_id, initiative_id=ini.id, risk_id=risk.id, origin="auto",
        baseline_residual_level=8, projected_residual_level=8 - points,
    ))
    db.flush()
    return ini


def test_quick_win_requires_efficiency_not_just_medians(client):
    """Regresion: una iniciativa cara y mediocre no puede ser quick win.

    Cifras tomadas del caso real que lo destapo. Esfuerzo = presupuesto +
    dias-persona x 400:

      eficiente   4 pts / 7.000    ->  1.750 por punto
      media       8 pts / 210.000  -> 26.250 por punto  (la PEOR de las tres)
      cara        6 pts / 280.000  -> 46.667 por punto

    Medianas: reduccion 6, esfuerzo 210.000. "media" supera la mediana de
    reduccion (8>=6) y no supera la de esfuerzo (210.000<=210.000), asi que el
    criterio antiguo la coronaba quick win siendo la menos eficiente.
    """
    from app.services.initiative_projection_service import compute_portfolio_priorities

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        eficiente = _make_initiative(db, org_id, points=4, budget=5000, effort_human=5)
        media = _make_initiative(db, org_id, points=8, budget=150000, effort_human=150)
        cara = _make_initiative(db, org_id, points=6, budget=200000, effort_human=200)
        db.commit()

        prios = compute_portfolio_priorities([eficiente, media, cara])

        assert prios[eficiente.id]["quick_win"] is True, \
            "la iniciativa mas eficiente deberia ser el quick win"
        assert prios[media.id]["quick_win"] is False, \
            "una iniciativa cara y mediocre no puede marcarse como quick win"
        assert prios[cara.id]["quick_win"] is False

        # La eficiencia manda: menos coste por punto = mas score
        assert prios[eficiente.id]["priority_score"] > prios[media.id]["priority_score"]
        assert prios[eficiente.id]["cost_per_point"] < prios[cara.id]["cost_per_point"]
    finally:
        db.close()


def test_no_reduction_is_never_high_priority(client):
    from app.services.initiative_projection_service import compute_portfolio_priorities

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        inutil = _make_initiative(db, org_id, points=0, budget=90000, effort_human=90)
        util = _make_initiative(db, org_id, points=6, budget=9000, effort_human=9)
        db.commit()
        prios = compute_portfolio_priorities([inutil, util])
        assert prios[inutil.id]["priority_suggested"] == "low"
        assert prios[inutil.id]["priority_score"] is None
        assert prios[util.id]["priority_suggested"] in ("high", "critical")
    finally:
        db.close()


def test_effort_unknown_is_reported_not_invented(client):
    """Sin presupuesto ni dias-persona no se puede rankear por eficiencia: se
    dice que se desconoce, no se asume cero."""
    from app.services.initiative_projection_service import compute_portfolio_priorities

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        sin_datos = _make_initiative(db, org_id, points=5, budget=None, effort_human=None)
        db.commit()
        prios = compute_portfolio_priorities([sin_datos])
        p = prios[sin_datos.id]
        assert p["priority_factors"]["effort_known"] is False
        assert p["priority_score"] is None
        assert p["cost_per_point"] is None
        assert p["quick_win"] is False
    finally:
        db.close()


def test_budget_health_follows_progress():
    """El presupuesto aprobado deberia seguir al avance: requerido x % progreso."""
    from app.models import StrategicInitiative
    from app.services.initiative_projection_service import initiative_budget_health

    ini = StrategicInitiative(code="INI-X", title="X", budget=100000.0,
                              budget_approved=20000.0, progress=60)
    health = initiative_budget_health(ini)
    assert health["expected_approved"] == 60000.0
    assert health["funding_gap"] == 80000.0
    assert health["underfunded"] is True

    ini.budget_approved = 70000.0
    assert initiative_budget_health(ini)["underfunded"] is False

    # Sin presupuesto declarado no hay nada que evaluar
    assert initiative_budget_health(StrategicInitiative(code="Y", title="Y")) is None


def test_horizon_derived_from_target_date():
    from datetime import datetime, timedelta, timezone

    from app.models import StrategicInitiative
    from app.services.initiative_projection_service import initiative_horizon

    now = datetime.now(timezone.utc)
    corto = StrategicInitiative(code="A", title="A", target_date=now + timedelta(days=60))
    medio = StrategicInitiative(code="B", title="B", target_date=now + timedelta(days=365))
    largo = StrategicInitiative(code="C", title="C", target_date=now + timedelta(days=900))
    assert initiative_horizon(corto, now) == "corto"
    assert initiative_horizon(medio, now) == "medio"
    assert initiative_horizon(largo, now) == "largo"
    assert initiative_horizon(StrategicInitiative(code="D", title="D"), now) is None


def test_portfolio_endpoint_ranks_by_efficiency(client, auth_headers):
    """El endpoint ordena por eficiencia; el quick win es etiqueta, no atajo."""
    db = _TestSession()
    try:
        org_id = _default_org(db).id
        _make_initiative(db, org_id, points=7, budget=5000, effort_human=5,
                         title=f"Eficiente {_uid()}")
        _make_initiative(db, org_id, points=7, budget=200000, effort_human=200,
                         title=f"Cara {_uid()}")
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/initiatives/portfolio", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    scored = [r for r in data["initiatives"] if r["priority_score"] is not None]
    assert len(scored) >= 2
    # Orden descendente por eficiencia
    assert scored == sorted(scored, key=lambda r: -r["priority_score"])
    for key in ("by_horizon", "by_origin", "by_action_type", "by_env", "budget"):
        assert key in data
    assert "largest_gaps" in data["budget"]


def test_initiative_taxonomy_is_persisted(client, auth_headers):
    """Regresion: origin/action_type/env llegaban en el POST y se perdian."""
    resp = client.post("/api/initiatives/", json={
        "title": f"Ini {_uid()}", "origin": "legal", "action_type": "normativa",
        "env": "OT", "effort_human": 12.5, "spent": 300.0,
        "last_achievements": "Hecho A", "next_steps": "Siguiente B", "blockers": "Bloqueo C",
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["origin"] == "legal"
    assert body["action_type"] == "normativa"
    assert body["env"] == "OT"
    assert body["effort_human"] == 12.5
    assert body["last_achievements"] == "Hecho A"
    assert body["next_steps"] == "Siguiente B"
    assert body["blockers"] == "Bloqueo C"

    detail = client.get(f"/api/initiatives/{body['id']}", headers=auth_headers).json()
    assert detail["origin"] == "legal" and detail["env"] == "OT"
