"""F7 — router de entrada unico (opcion A).

Todo documento entra por la puerta ISMS. Tras el analisis, un fan-out decide que
modulos adicionales alimenta: continuidad estructurada (un BIA, una lista de
sedes) se encamina al motor de ingesta compartido; continuidad en prosa crea un
BCPPlan. El gate es conservador para no disparar el pipeline pesado en cada doc.
"""
import uuid
from unittest.mock import patch

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _make_doc(db, org_id, name, mime, owner_id=None):
    from app.models import AiDocument, AiDocumentCategory, AiDocumentStatus
    doc = AiDocument(
        organization_id=org_id, filename=f"{_uid()}_{name}",
        original_name=name, category=AiDocumentCategory.OTHER,
        status=AiDocumentStatus.INDEXED, mime_type=mime, uploaded_by_id=owner_id,
    )
    db.add(doc)
    db.flush()
    return doc


# ---- Gate puro ----

def test_gate_spreadsheet_with_continuity_hint_routes():
    from app.services.isms_analysis_service import _should_route_to_ingest

    class _D:
        mime_type = _XLSX
        original_name = "BIA por sede 2026.xlsx"
    assert _should_route_to_ingest(_D(), {}) is True


def test_gate_pdf_never_routes():
    from app.services.isms_analysis_service import _should_route_to_ingest

    class _D:
        mime_type = "application/pdf"
        original_name = "BIA por sede.pdf"   # aunque el nombre sugiera BIA
    assert _should_route_to_ingest(_D(), {}) is False


def test_gate_spreadsheet_without_continuity_does_not_route():
    from app.services.isms_analysis_service import _should_route_to_ingest

    class _D:
        mime_type = _XLSX
        original_name = "presupuesto marketing.xlsx"
    with patch("app.services.bcp_service.detect_bcp_document", return_value=False):
        assert _should_route_to_ingest(_D(), {}) is False


# ---- Encolado ----

def test_structured_continuity_doc_enqueues_ingest_job(client):
    from app.models import Organization, BackgroundJob
    from app.services.isms_analysis_service import route_document_downstream

    db = _TestSession()
    try:
        org = Organization(name=f"Org routing {_uid()}", plan="enterprise")
        db.add(org)
        db.flush()
        doc = _make_doc(db, org.id, "Inventario de sedes.xlsx", _XLSX)
        db.commit()
        doc_id, org_id = doc.id, org.id

        # No queremos que el camino prosa->BCPPlan dispare LLM en el test.
        with patch("app.services.bcp_service.detect_bcp_document", return_value=False):
            route_document_downstream(db, doc, {"overall_summary": "Listado de sedes."})

        job = db.query(BackgroundJob).filter_by(
            organization_id=org_id, job_type="bcp_ingest_document").first()
        assert job is not None, "Debe encolarse un job de ingesta BCM"
        assert job.payload.get("doc_id") == doc_id
    finally:
        db.close()


def test_prose_pdf_does_not_enqueue_ingest(client):
    from app.models import Organization, BackgroundJob
    from app.services.isms_analysis_service import route_document_downstream

    db = _TestSession()
    try:
        org = Organization(name=f"Org routing {_uid()}", plan="enterprise")
        db.add(org)
        db.flush()
        doc = _make_doc(db, org.id, "Plan de continuidad.pdf", "application/pdf")
        db.commit()
        org_id = org.id

        with patch("app.services.bcp_service.detect_bcp_document", return_value=False):
            route_document_downstream(db, doc, {"overall_summary": "Prosa."})

        assert db.query(BackgroundJob).filter_by(
            organization_id=org_id, job_type="bcp_ingest_document").count() == 0
    finally:
        db.close()


# ---- Handler ----

def test_handler_calls_run_pack_without_profile(client):
    """El handler descompone el documento con apply_profile=False (un solo doc
    no debe re-deducir el perfil global de la organizacion)."""
    from app.models import Organization
    from app.services import job_queue

    db = _TestSession()
    try:
        org = Organization(name=f"Org handler {_uid()}", plan="enterprise")
        db.add(org)
        db.flush()
        doc = _make_doc(db, org.id, "BIA.xlsx", _XLSX)
        db.commit()
        doc_id = doc.id
    finally:
        db.close()

    captured = {}

    def _fake_run_pack(db, org_id, files, **kwargs):
        captured["files"] = files
        captured["apply_profile"] = kwargs.get("apply_profile")
        return {"batch_id": 1, "status": "completed"}

    with patch("app.services.document_service.read_document_bytes", return_value=b"PK\x03\x04data"), \
         patch("app.services.ingest.pipeline.run_pack", side_effect=_fake_run_pack):
        res = job_queue._handle_bcp_ingest_document({"doc_id": doc_id})

    assert res["status"] == "completed"
    assert captured["apply_profile"] is False
    assert len(captured["files"]) == 1


def test_handler_missing_file_is_skipped(client):
    from app.models import Organization
    from app.services import job_queue

    db = _TestSession()
    try:
        org = Organization(name=f"Org handler {_uid()}", plan="enterprise")
        db.add(org)
        db.flush()
        doc = _make_doc(db, org.id, "BIA.xlsx", _XLSX)
        db.commit()
        doc_id = doc.id
    finally:
        db.close()

    with patch("app.services.document_service.read_document_bytes", return_value=None):
        res = job_queue._handle_bcp_ingest_document({"doc_id": doc_id})
    assert "skipped" in res


def test_bcp_ingest_document_handler_registered():
    from app.services.job_queue import _HANDLERS
    assert "bcp_ingest_document" in _HANDLERS
