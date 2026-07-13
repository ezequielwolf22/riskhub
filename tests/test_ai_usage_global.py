"""Panel de refacturacion IA del superadmin: /api/ai/usage/global."""
from datetime import datetime, timezone


def _promote_admin_to_superadmin():
    from tests.conftest import _TestSession
    from app.models import User, UserRole
    db = _TestSession()
    try:
        u = db.query(User).filter(User.email == "admin@test.internal").first()
        prev = u.role
        u.role = UserRole.SUPERADMIN
        db.commit()
        return prev
    finally:
        db.close()


def _restore_role(prev):
    from tests.conftest import _TestSession
    from app.models import User
    db = _TestSession()
    try:
        u = db.query(User).filter(User.email == "admin@test.internal").first()
        u.role = prev
        db.commit()
    finally:
        db.close()


def _seed_call_logs():
    from tests.conftest import _TestSession
    from app.models import AiCallLog, Organization
    db = _TestSession()
    try:
        org = db.query(Organization).first()
        now = datetime.now(timezone.utc)
        rows = [
            # gasto de la org con key de plataforma (refacturable)
            AiCallLog(organization_id=org.id, call_type="asset_risk_analysis",
                      model="claude-haiku-4-5", prompt_tokens=1_000_000,
                      completion_tokens=100_000, key_source="vendor", created_at=now),
            # gasto de la org con su propia key (NO refacturable)
            AiCallLog(organization_id=org.id, call_type="chat",
                      model="claude-opus-4-6", prompt_tokens=500_000,
                      completion_tokens=50_000, key_source="org", created_at=now),
            # fila historica sin origen registrado
            AiCallLog(organization_id=org.id, call_type="evidence_review",
                      model="claude-haiku-4-5", prompt_tokens=200_000,
                      completion_tokens=20_000, key_source=None, created_at=now),
            # gasto de plataforma sin organizacion (regwatch)
            AiCallLog(organization_id=None, call_type="regwatch_analysis",
                      model="claude-haiku-4-5", prompt_tokens=300_000,
                      completion_tokens=30_000, key_source="vendor", created_at=now),
        ]
        db.add_all(rows)
        db.commit()
        return org.id
    finally:
        db.close()


def test_usage_global_requires_superadmin(client, auth_headers):
    resp = client.get("/api/ai/usage/global", headers=auth_headers)
    assert resp.status_code == 403


def test_usage_global_breakdown(client, auth_headers):
    org_id = _seed_call_logs()
    prev = _promote_admin_to_superadmin()
    try:
        resp = client.get("/api/ai/usage/global", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        by_id = {o["organization_id"]: o for o in data["organizations"]}

        # La org del tenant suma las 3 filas y separa lo refacturable
        org = by_id[org_id]
        assert org["calls"] == 3
        assert org["billable_cost_usd"] > 0
        assert org["billable_cost_usd"] < org["estimated_cost_usd"]
        assert org["unknown_cost_usd"] > 0  # la fila sin key_source

        # La fila de plataforma (org NULL) aparece y es refacturable=vendor
        assert None in by_id
        platform = by_id[None]
        assert platform["plan"] is None
        assert platform["billable_cost_usd"] == platform["estimated_cost_usd"]

        totals = data["totals"]
        assert totals["calls"] == 4
        assert totals["billable_cost_usd"] <= totals["estimated_cost_usd"]

        # Detalle por tipo de llamada de la org
        resp = client.get(f"/api/ai/usage/global?org_id={org_id}", headers=auth_headers)
        assert resp.status_code == 200
        detail = resp.json()["detail"]
        types = {d["call_type"] for d in detail}
        assert {"asset_risk_analysis", "chat", "evidence_review"} <= types
        sources = {d["key_source"] for d in detail}
        assert {"vendor", "org", "unknown"} <= sources

        # Detalle de plataforma con org_id=0
        resp = client.get("/api/ai/usage/global?org_id=0", headers=auth_headers)
        assert resp.status_code == 200
        detail = resp.json()["detail"]
        assert any(d["call_type"] == "regwatch_analysis" for d in detail)

        # Mes sin datos -> vacio; mes invalido -> 400
        resp = client.get("/api/ai/usage/global?month=2020-01", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["organizations"] == []
        resp = client.get("/api/ai/usage/global?month=nope", headers=auth_headers)
        assert resp.status_code == 400
    finally:
        _restore_role(prev)


def test_key_source_helper():
    from app.config import settings
    from app.services.claude_client import key_source
    prev = settings.anthropic_api_key
    try:
        settings.anthropic_api_key = "sk-vendor-global"
        assert key_source("sk-vendor-global") == "vendor"
        assert key_source("sk-tenant-propia") == "org"
        settings.anthropic_api_key = None
        assert key_source("sk-cualquiera") == "org"
    finally:
        settings.anthropic_api_key = prev
