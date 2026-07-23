"""Operaciones masivas sobre documentos ISMS — POST /api/ai/documents/bulk.

Cubre las tres acciones (delete, analyze, recategorize), el modo dry_run y el
aislamiento entre organizaciones: un lote nunca debe alcanzar documentos de otra
organizacion aunque el llamante ponga sus ids a mano.
"""
import uuid
from unittest.mock import patch

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _admin(db):
    from app.models import User, UserRole
    return db.query(User).filter(User.role == UserRole.SUPERADMIN).first() or \
        db.query(User).first()


def _make_doc(db, org_id, owner_id=None, status=None, category=None):
    from app.models import AiDocument, AiDocumentCategory, AiDocumentStatus
    doc = AiDocument(
        organization_id=org_id,
        filename=f"{_uid()}_bulk.pdf",
        original_name=f"Doc bulk {_uid()}.pdf",
        category=category or AiDocumentCategory.OTHER,
        status=status or AiDocumentStatus.INDEXED,
        file_size=512,
        mime_type="application/pdf",
        uploaded_by_id=owner_id,
    )
    db.add(doc)
    db.flush()
    return doc


def _make_docs(n, **kw):
    db = _TestSession()
    try:
        user = _admin(db)
        docs = [_make_doc(db, user.organization_id, user.id, **kw) for _ in range(n)]
        db.commit()
        return [d.id for d in docs]
    finally:
        db.close()


def test_bulk_delete_removes_all(client, auth_headers):
    from app.models import AiDocument
    ids = _make_docs(3)
    resp = client.post("/api/ai/documents/bulk", headers=auth_headers,
                       json={"action": "delete", "doc_ids": ids})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["requested"] == 3 and body["affected"] == 3

    db = _TestSession()
    try:
        assert db.query(AiDocument).filter(AiDocument.id.in_(ids)).count() == 0
    finally:
        db.close()


def test_bulk_delete_dry_run_deletes_nothing(client, auth_headers):
    """El preview cuenta el impacto sin tocar la base."""
    from app.models import AiDocument, Policy, PolicyStatus
    ids = _make_docs(2)
    db = _TestSession()
    try:
        user = _admin(db)
        db.add(Policy(
            organization_id=user.organization_id, code=f"POL-B{_uid()[:5]}",
            title=f"Politica bulk {_uid()}", status=PolicyStatus.DRAFT,
            source_document_id=ids[0], document_level=1,
        ))
        db.commit()
    finally:
        db.close()

    resp = client.post("/api/ai/documents/bulk", headers=auth_headers,
                       json={"action": "delete", "doc_ids": ids, "dry_run": True})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is True
    assert body["affected"] == 2
    assert body["detached"].get("policies") == 1

    db = _TestSession()
    try:
        assert db.query(AiDocument).filter(AiDocument.id.in_(ids)).count() == 2
    finally:
        db.close()

    client.post("/api/ai/documents/bulk", headers=auth_headers,
                json={"action": "delete", "doc_ids": ids})


def test_bulk_recategorize(client, auth_headers):
    """Recategorizar es decision humana: la IA no debe pisarla despues."""
    from app.models import AiDocument, AiDocumentCategory
    ids = _make_docs(2)
    db = _TestSession()
    try:
        for doc_id in ids:
            db.get(AiDocument, doc_id).auto_categorized = True
        db.commit()
    finally:
        db.close()

    resp = client.post("/api/ai/documents/bulk", headers=auth_headers,
                       json={"action": "recategorize", "doc_ids": ids,
                             "category": "risk_assessments"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["affected"] == 2

    db = _TestSession()
    try:
        for doc_id in ids:
            doc = db.get(AiDocument, doc_id)
            assert doc.category == AiDocumentCategory.RISK_ASSESSMENTS
            assert doc.auto_categorized is False
    finally:
        db.close()


def test_bulk_recategorize_rejects_invalid_category(client, auth_headers):
    ids = _make_docs(1)
    resp = client.post("/api/ai/documents/bulk", headers=auth_headers,
                       json={"action": "recategorize", "doc_ids": ids,
                             "category": "no_existe"})
    assert resp.status_code == 400


def test_bulk_analyze_skips_non_indexed(client, auth_headers):
    """Analizar solo tiene sentido sobre documentos indexados."""
    from app.models import AiDocument, AiDocumentStatus
    indexed = _make_docs(2)
    pending = _make_docs(1, status=AiDocumentStatus.PENDING)

    with patch("app.routers.documents._run_isms_analysis_bg") as fake:
        resp = client.post("/api/ai/documents/bulk", headers=auth_headers,
                           json={"action": "analyze", "doc_ids": indexed + pending})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["affected"] == 2
    assert body["skipped"]["not_indexed"] == pending
    assert fake.call_count == 2

    db = _TestSession()
    try:
        for doc_id in indexed:
            assert db.get(AiDocument, doc_id).isms_status == "analysing"
    finally:
        db.close()


def test_bulk_reports_unknown_ids(client, auth_headers):
    ids = _make_docs(1)
    resp = client.post("/api/ai/documents/bulk", headers=auth_headers,
                       json={"action": "delete", "doc_ids": ids + [99999999]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["affected"] == 1
    assert body["skipped"]["not_found"] == [99999999]


def test_bulk_rejects_unknown_action(client, auth_headers):
    ids = _make_docs(1)
    resp = client.post("/api/ai/documents/bulk", headers=auth_headers,
                       json={"action": "incinerar", "doc_ids": ids})
    assert resp.status_code == 400


def test_bulk_rejects_empty_and_oversized(client, auth_headers):
    assert client.post("/api/ai/documents/bulk", headers=auth_headers,
                       json={"action": "delete", "doc_ids": []}).status_code == 400
    assert client.post("/api/ai/documents/bulk", headers=auth_headers,
                       json={"action": "delete",
                             "doc_ids": list(range(1, 700))}).status_code == 400


def test_bulk_cannot_reach_other_organization(client):
    """Aislamiento multi-tenant: un admin de otra org no alcanza estos documentos.

    Es el vector real: el atacante conoce o adivina ids y los mete en el lote.
    """
    from app.models import AiDocument, Organization, User, UserRole
    from app.security import hash_password

    ids = _make_docs(2)          # documentos de la organizacion por defecto

    db = _TestSession()
    try:
        other = Organization(name=f"Org intrusa {_uid()}", plan="free")
        db.add(other)
        db.flush()
        email = f"intruso-{_uid()}@test.internal"
        db.add(User(
            email=email, full_name="Admin intruso",
            hashed_password=hash_password("IntrusoTest123!"),
            role=UserRole.ADMIN, is_active=True, organization_id=other.id,
        ))
        db.commit()
    finally:
        db.close()

    login = client.post("/api/auth/login",
                        data={"username": email, "password": "IntrusoTest123!"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.post("/api/ai/documents/bulk", headers=headers,
                       json={"action": "delete", "doc_ids": ids})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["affected"] == 0
    assert sorted(body["skipped"]["not_found"]) == sorted(ids)

    db = _TestSession()
    try:
        assert db.query(AiDocument).filter(AiDocument.id.in_(ids)).count() == 2
    finally:
        db.close()
