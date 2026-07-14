"""El SPA fallback no debe servir ficheros fuera del arbol estatico."""


def test_spa_fallback_blocks_path_traversal(client):
    # Rutas que intentan salir de app/static. El servidor debe devolver el
    # index de la SPA (200 con HTML), nunca el contenido del fichero objetivo.
    for evil in [
        "../../../../../../etc/passwd",
        "../app/config.py",
        "..%2f..%2f..%2fetc%2fpasswd",
        "../../requirements.txt",
    ]:
        resp = client.get("/" + evil)
        # O bien lo bloquea el router (404) o cae al index de la SPA (HTML),
        # pero jamas devuelve el fichero fuera de static.
        body = resp.text
        assert "root:" not in body, f"filtro fallo para {evil}"
        assert "SQLAlchemy" not in body
        assert "DATABASE_URL" not in body


def test_spa_fallback_serves_real_static(client):
    # Un asset real dentro de static sigue sirviendose.
    resp = client.get("/login.html")
    assert resp.status_code == 200
    assert "RiskHub" in resp.text
