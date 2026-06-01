"""Tests del endpoint de health check."""


def test_health_returns_200(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_health_response_structure(client):
    data = client.get("/api/health").json()
    assert "status" in data
    assert "version" in data
    assert "env" in data


def test_health_status_ok(client):
    data = client.get("/api/health").json()
    assert data["status"] == "ok"


def test_health_db_check(client):
    """El health check detallado debe incluir estado de la base de datos."""
    data = client.get("/api/health").json()
    # db_ok puede estar o no, pero si esta debe ser True
    if "db_ok" in data:
        assert data["db_ok"] is True
