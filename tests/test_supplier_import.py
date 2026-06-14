"""Tests de la importacion masiva de proveedores (TPRM)."""


def _csv(rows):
    header = "nombre,categoria,email,servicios,pais"
    lines = [header] + rows
    return "\n".join(lines).encode("utf-8")


def test_import_creates_suppliers(client, auth_headers):
    csv = _csv([
        "Acme Cloud SL,cloud_provider,sec@acme.example,Hosting,ES",
        "Beta Consulting,consultancy,info@beta.example,Auditoria,FR",
    ])
    resp = client.post(
        "/api/suppliers/import",
        files={"file": ("proveedores.csv", csv, "text/csv")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 2
    assert body["total"] == 2
    assert "name" in body["detected_columns"]
    assert body["detected_columns"].get("contact_email") == "email"


def test_import_dedups_existing(client, auth_headers):
    csv = _csv(["Acme Cloud SL,cloud_provider,sec@acme.example,Hosting,ES"])
    resp = client.post(
        "/api/suppliers/import",
        files={"file": ("dup.csv", csv, "text/csv")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    # Acme ya existe del test anterior -> se omite
    assert resp.json()["skipped"] >= 1
    assert resp.json()["created"] == 0


def test_import_requires_name_column(client, auth_headers):
    csv = b"foo,bar\n1,2"
    resp = client.post(
        "/api/suppliers/import",
        files={"file": ("bad.csv", csv, "text/csv")},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_import_rejects_bad_extension(client, auth_headers):
    resp = client.post(
        "/api/suppliers/import",
        files={"file": ("malware.exe", b"x", "application/octet-stream")},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_import_requires_auth(client):
    resp = client.post(
        "/api/suppliers/import",
        files={"file": ("x.csv", b"nombre\nAcme", "text/csv")},
    )
    assert resp.status_code == 401
