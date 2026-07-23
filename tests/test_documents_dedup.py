"""F6 — deduplicacion de documentos por SHA-256.

El mismo contenido subido varias veces inflaba la madurez del control tantas
veces como se subiera. Ahora el segundo intento se rechaza con 409 (salvo
force=true), y una re-subida tras borrar el original es legitima.
"""
import io
import uuid

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _pdf_bytes(marker: str) -> bytes:
    # Cabecera PDF valida (magic bytes) + contenido unico por marcador.
    return b"%PDF-1.4\n" + f"contenido {marker}".encode() + b"\n%%EOF"


def _upload(client, headers, data, category="policies", force=None):
    files = {"file": (f"doc_{_uid()}.pdf", io.BytesIO(data), "application/pdf")}
    form = {"category": category}
    if force is not None:
        form["force"] = str(force).lower()
    return client.post("/api/ai/documents/", files=files, data=form, headers=headers)


def test_compute_sha256_stable():
    from app.services.document_service import compute_sha256
    data = _pdf_bytes("x")
    assert compute_sha256(data) == compute_sha256(data)
    assert compute_sha256(data) != compute_sha256(_pdf_bytes("y"))
    assert len(compute_sha256(data)) == 64


def test_duplicate_upload_is_rejected(client, auth_headers):
    data = _pdf_bytes(_uid())
    r1 = _upload(client, auth_headers, data)
    assert r1.status_code in (200, 201), r1.text
    doc_id = r1.json()["id"]

    r2 = _upload(client, auth_headers, data)
    assert r2.status_code == 409, r2.text
    detail = r2.json()["detail"]
    assert detail["error"] == "duplicate"
    assert detail["existing_id"] == doc_id

    # Limpieza
    client.delete(f"/api/ai/documents/{doc_id}", headers=auth_headers)


def test_force_allows_duplicate(client, auth_headers):
    data = _pdf_bytes(_uid())
    r1 = _upload(client, auth_headers, data)
    assert r1.status_code in (200, 201)
    id1 = r1.json()["id"]

    r2 = _upload(client, auth_headers, data, force=True)
    assert r2.status_code in (200, 201), r2.text
    id2 = r2.json()["id"]
    assert id2 != id1

    client.delete(f"/api/ai/documents/{id1}", headers=auth_headers)
    client.delete(f"/api/ai/documents/{id2}", headers=auth_headers)


def test_reupload_after_delete_is_allowed(client, auth_headers):
    """Borrar el original y volver a subir el mismo contenido es legitimo."""
    data = _pdf_bytes(_uid())
    r1 = _upload(client, auth_headers, data)
    assert r1.status_code in (200, 201)
    id1 = r1.json()["id"]

    assert client.delete(f"/api/ai/documents/{id1}", headers=auth_headers).status_code == 200

    r2 = _upload(client, auth_headers, data)
    assert r2.status_code in (200, 201), r2.text
    client.delete(f"/api/ai/documents/{r2.json()['id']}", headers=auth_headers)


def test_sha256_persisted_on_upload(client, auth_headers):
    from app.models import AiDocument
    from app.services.document_service import compute_sha256
    data = _pdf_bytes(_uid())
    r = _upload(client, auth_headers, data)
    assert r.status_code in (200, 201)
    doc_id = r.json()["id"]
    db = _TestSession()
    try:
        doc = db.get(AiDocument, doc_id)
        assert doc.sha256 == compute_sha256(data)
    finally:
        db.close()
    client.delete(f"/api/ai/documents/{doc_id}", headers=auth_headers)


def test_different_org_can_upload_same_content(client, auth_headers):
    """La dedup es por organizacion: dos orgs pueden tener el mismo documento."""
    from app.models import AiDocument, Organization, User, UserRole
    from app.security import hash_password

    data = _pdf_bytes(_uid())
    r1 = _upload(client, auth_headers, data)
    assert r1.status_code in (200, 201)
    id1 = r1.json()["id"]

    db = _TestSession()
    try:
        other = Organization(name=f"Org dedup {_uid()}", plan="free")
        db.add(other)
        db.flush()
        email = f"dedup-{_uid()}@test.internal"
        db.add(User(
            email=email, full_name="Otro admin",
            hashed_password=hash_password("DedupTest123!"),
            role=UserRole.ADMIN, is_active=True, organization_id=other.id,
        ))
        db.commit()
    finally:
        db.close()

    login = client.post("/api/auth/login",
                        data={"username": email, "password": "DedupTest123!"})
    headers2 = {"Authorization": f"Bearer {login.json()['access_token']}"}

    r2 = _upload(client, headers2, data)
    assert r2.status_code in (200, 201), r2.text   # otra org: no es duplicado

    client.delete(f"/api/ai/documents/{id1}", headers=auth_headers)
    client.delete(f"/api/ai/documents/{r2.json()['id']}", headers=headers2)
