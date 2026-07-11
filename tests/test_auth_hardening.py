"""Tests del hardening de acceso: jti, logout real, lockout y politica de contrasenas."""
import jwt as pyjwt
import pytest

from app.services.rate_limiter import reset_all_counters

ADMIN_EMAIL = "admin@test.internal"
ADMIN_PASSWORD = "TestAdmin123!"


@pytest.fixture(autouse=True)
def _clean_rate_limits():
    # Otros tests (test_auth.TestRateLimit) dejan la IP del TestClient
    # bloqueada; estos tests hacen logins frescos y necesitan partir limpios.
    reset_all_counters()
    yield
    reset_all_counters()


def _fresh_token(client):
    resp = client.post(
        "/api/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_token_contains_jti(client):
    token = _fresh_token(client)
    payload = pyjwt.decode(token, options={"verify_signature": False})
    assert payload.get("jti"), "El token debe llevar jti para poder revocarse"
    assert len(payload["jti"]) >= 16


def test_logout_revokes_token(client, auth_headers):
    # Token nuevo, independiente del token de sesion compartido de la suite
    token = _fresh_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/auth/me", headers=headers).status_code == 200

    resp = client.post("/api/auth/logout", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True

    # El token revocado deja de valer inmediatamente
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    # El token compartido de la suite (otro jti) sigue siendo valido
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 200


def test_login_lockout_after_failed_attempts(client):
    try:
        for _ in range(10):
            resp = client.post(
                "/api/auth/login",
                data={"username": "lockme@test.internal", "password": "wrong"},
            )
            assert resp.status_code in (401, 429)
        resp = client.post(
            "/api/auth/login",
            data={"username": "lockme@test.internal", "password": "wrong"},
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
    finally:
        # No dejar bloqueada la IP del TestClient para el resto de la suite
        reset_all_counters()


def test_password_policy_rejects_weak_password(client, auth_headers):
    resp = client.patch(
        "/api/auth/me/password",
        headers=auth_headers,
        json={"current_password": ADMIN_PASSWORD, "new_password": "weak"},
    )
    assert resp.status_code == 400
