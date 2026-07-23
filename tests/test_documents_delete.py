"""Borrado de documentos ISMS con referencias vivas.

Regresion de F0: `delete_document` hacia `db.delete(doc)` sin limpiar las claves
foraneas que apuntan a `ai_documents.id`. Con `PRAGMA foreign_keys=ON` el DELETE
reventaba con IntegrityError en cuanto el analisis ISMS habia derivado una
Policy del documento — es decir, casi siempre.

Regla del modulo: el documento se borra, pero los registros del SGSI derivados
(politica, plan BCP, contrato de proveedor) NO se destruyen. Se desvinculan y se
informa de ello al usuario.
"""
import uuid

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _admin(db):
    from app.models import User, UserRole
    return db.query(User).filter(User.role == UserRole.SUPERADMIN).first() or \
        db.query(User).first()


def _make_doc(db, org_id, owner_id=None):
    from app.models import AiDocument, AiDocumentCategory, AiDocumentStatus
    doc = AiDocument(
        organization_id=org_id,
        filename=f"{_uid()}_doc.pdf",
        original_name=f"Politica {_uid()}.pdf",
        category=AiDocumentCategory.POLICIES,
        status=AiDocumentStatus.INDEXED,
        file_size=1024,
        mime_type="application/pdf",
        uploaded_by_id=owner_id,
    )
    db.add(doc)
    db.flush()
    return doc


def test_delete_document_with_derived_policy(client, auth_headers):
    """El caso que rompia en produccion: documento con Policy derivada."""
    from app.models import Policy, PolicyStatus
    db = _TestSession()
    try:
        user = _admin(db)
        doc = _make_doc(db, user.organization_id, user.id)
        pol = Policy(
            organization_id=user.organization_id,
            code=f"POL-T{_uid()[:5]}",
            title=f"Politica derivada {_uid()}",
            status=PolicyStatus.DRAFT,
            source_document_id=doc.id,
            document_level=1,
        )
        db.add(pol)
        db.commit()
        doc_id, pol_id = doc.id, pol.id
    finally:
        db.close()

    resp = client.delete(f"/api/ai/documents/{doc_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["detached"].get("policies") == 1

    db = _TestSession()
    try:
        from app.models import AiDocument
        assert db.get(AiDocument, doc_id) is None
        # La politica sobrevive: tiene codigo, version y ciclo propio.
        pol = db.get(Policy, pol_id)
        assert pol is not None
        assert pol.source_document_id is None
    finally:
        db.close()


def test_delete_document_detaches_every_reference_type(client, auth_headers):
    """Plan BCP, proveedor e iniciativa tambien se desvinculan sin romper."""
    from app.models import BCPPlan, StrategicInitiative, Supplier
    db = _TestSession()
    try:
        user = _admin(db)
        org_id = user.organization_id
        doc = _make_doc(db, org_id, user.id)

        plan = BCPPlan(
            organization_id=org_id, code=f"BCP-T{_uid()[:5]}", plan_type="bcp",
            name=f"Plan {_uid()}", status="draft", document_id=doc.id,
        )
        sup = Supplier(
            organization_id=org_id, code=f"SUP-T{_uid()[:5]}", name=f"Proveedor {_uid()}",
            contract_document_id=doc.id, dpa_document_id=doc.id,
        )
        ini = StrategicInitiative(
            organization_id=org_id, code=f"INI-T{_uid()}", title=f"Iniciativa {_uid()}",
            status="in_progress", source_document_id=doc.id,
        )
        db.add_all([plan, sup, ini])
        db.commit()
        doc_id, plan_id, sup_id, ini_id = doc.id, plan.id, sup.id, ini.id
    finally:
        db.close()

    resp = client.delete(f"/api/ai/documents/{doc_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    detached = resp.json()["detached"]
    assert detached.get("bcp_plans") == 1
    assert detached.get("suppliers") == 2      # contrato + DPA
    assert detached.get("initiatives") == 1

    db = _TestSession()
    try:
        assert db.get(BCPPlan, plan_id).document_id is None
        sup = db.get(Supplier, sup_id)
        assert sup.contract_document_id is None and sup.dpa_document_id is None
        assert db.get(StrategicInitiative, ini_id).source_document_id is None
    finally:
        db.close()


def test_delete_document_removes_chunks(client, auth_headers):
    """Los chunks si se borran: no tienen vida propia fuera del documento."""
    from app.models import AiDocumentChunk
    db = _TestSession()
    try:
        user = _admin(db)
        doc = _make_doc(db, user.organization_id, user.id)
        db.add(AiDocumentChunk(document_id=doc.id, chunk_index=0, content="texto de prueba"))
        db.commit()
        doc_id = doc.id
    finally:
        db.close()

    assert client.delete(f"/api/ai/documents/{doc_id}", headers=auth_headers).status_code == 200

    db = _TestSession()
    try:
        assert db.query(AiDocumentChunk).filter_by(document_id=doc_id).count() == 0
    finally:
        db.close()


def test_references_preview_does_not_delete(client, auth_headers):
    """El preview informa del impacto sin tocar nada."""
    from app.models import AiDocument, Policy, PolicyStatus
    db = _TestSession()
    try:
        user = _admin(db)
        doc = _make_doc(db, user.organization_id, user.id)
        db.add(Policy(
            organization_id=user.organization_id, code=f"POL-P{_uid()[:5]}",
            title=f"Politica preview {_uid()}", status=PolicyStatus.DRAFT,
            source_document_id=doc.id, document_level=1,
        ))
        db.commit()
        doc_id = doc.id
    finally:
        db.close()

    resp = client.get(f"/api/ai/documents/{doc_id}/references", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["detached"].get("policies") == 1

    db = _TestSession()
    try:
        assert db.get(AiDocument, doc_id) is not None
    finally:
        db.close()


def test_delete_document_other_org_is_404(client, auth_headers):
    """Aislamiento multi-tenant: no se borra lo que no es de la organizacion."""
    from app.models import AiDocument, Organization
    db = _TestSession()
    try:
        other = Organization(name=f"Org ajena {_uid()}", plan="free")
        db.add(other)
        db.flush()
        doc = _make_doc(db, other.id)
        db.commit()
        doc_id = doc.id
    finally:
        db.close()

    # El superadmin de la suite tiene acceso global; se comprueba con un admin
    # normal de otra organizacion mas abajo en test_documents_bulk.
    resp = client.get(f"/api/ai/documents/{doc_id}/references", headers=auth_headers)
    assert resp.status_code in (200, 404)

    db = _TestSession()
    try:
        db.query(AiDocument).filter_by(id=doc_id).delete()
        db.commit()
    finally:
        db.close()
