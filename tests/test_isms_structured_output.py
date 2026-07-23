"""Analisis ISMS con salida estructurada (tool use forzado).

Antes el servicio pedia "devuelve SOLO JSON" y hacia `json.loads` sobre texto
libre: cualquier prosa alrededor o un truncado dejaba el documento en
`isms_status='error'`. Ahora la API valida los argumentos contra un schema
formal, asi que el JSON malformado deja de existir como clase de error.

Estos tests no llaman a la API real: mockean `structured_message` y comprueban
que el pipeline determinista posterior persiste lo que debe.
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


class _FakeUsage:
    input_tokens = 1200
    output_tokens = 400


class _FakeMessage:
    usage = _FakeUsage()
    stop_reason = "tool_use"


def _make_indexed_doc(db, org_id, owner_id):
    from app.models import AiDocument, AiDocumentCategory, AiDocumentChunk, AiDocumentStatus
    doc = AiDocument(
        organization_id=org_id,
        filename=f"{_uid()}_norma.pdf",
        original_name=f"Norma de Contrasenas {_uid()}.pdf",
        category=AiDocumentCategory.POLICIES,
        status=AiDocumentStatus.INDEXED,
        file_size=2048,
        mime_type="application/pdf",
        uploaded_by_id=owner_id,
    )
    db.add(doc)
    db.flush()
    db.add(AiDocumentChunk(
        document_id=doc.id, chunk_index=0,
        content="Toda contrasena tendra un minimo de 14 caracteres y se rotara cada 365 dias.",
    ))
    db.commit()
    return doc


def _analysis_payload():
    return {
        "doc_class": "normative",
        "doc_class_confidence": 0.95,
        "document_level": 2,
        "document_level_label": "Norma",
        "document_category": "policies",
        "is_policy": True,
        "policy": {
            "title": f"Norma de Contrasenas {_uid()}",
            "category": "Acceso",
            "version": "1.0",
            "scope": "Toda la organizacion",
            "content": "Longitud minima y rotacion.",
            "review_date": None,
            "review_cycle_months": 12,
            "iso_clauses": ["A.5.17"],
        },
        "controls_covered": [{
            "code": "5.17",
            "name": "Informacion de autenticacion",
            "coverage": "full",
            "maturity_current": 3,
            "maturity_rationale": "Norma que define reglas de obligado cumplimiento.",
            "gap_to_5": "Falta procedimiento e instruccion tecnica con metricas.",
            "evidence_note": "Minimo 14 caracteres, rotacion 365 dias.",
        }],
        "threat_categories_addressed": [],
        "overall_summary": "Norma de contrasenas de la organizacion.",
    }


def _record_payload():
    """Un informe SOC 2 Type 2: doc_class=record, aunque el modelo marque is_policy."""
    p = _analysis_payload()
    p["doc_class"] = "record"
    p["doc_class_confidence"] = 0.9
    p["document_level"] = None
    p["is_policy"] = True          # el modelo se equivoca; el gating debe ignorarlo
    p["policy"]["title"] = f"SOC 2 Type 2 Report {_uid()}"
    return p


def test_schema_is_a_valid_tool_input_schema():
    """El schema debe ser un object con required — es el contrato con la API."""
    from app.services.isms_analysis_service import _ISMS_ANALYSIS_SCHEMA as S
    assert S["type"] == "object"
    props = S["properties"]
    for field in ("doc_class", "document_category", "is_policy",
                  "controls_covered", "overall_summary"):
        assert field in props, field
    # El eje primario doc_class debe estar en required y con su enum.
    assert "doc_class" in S["required"]
    assert set(props["doc_class"]["enum"]) == {
        "normative", "record", "reference", "unclassified"}
    # El enum de categorias debe coincidir con el enum real del modelo.
    from app.models import AiDocumentCategory
    assert set(props["document_category"]["enum"]) == {c.value for c in AiDocumentCategory}
    # Los limites de nivel documental son los de la jerarquia ISO (1..4).
    assert props["document_level"]["minimum"] == 1
    assert props["document_level"]["maximum"] == 4


def test_analysis_persists_policy_and_controls(client):
    from app.services import isms_analysis_service as svc
    from app.models import AiDocument, Policy

    db = _TestSession()
    try:
        user = _admin(db)
        doc = _make_indexed_doc(db, user.organization_id, user.id)
        doc_id = doc.id
    finally:
        db.close()

    db = _TestSession()
    try:
        with patch("app.services.model_registry.get_api_key", return_value="sk-test"), \
             patch("app.services.claude_client.structured_message",
                   return_value=(_analysis_payload(), _FakeMessage())) as fake:
            svc.analyze_document_for_isms(db, doc_id)
        assert fake.call_count == 1
        # Contrato de llamada: tool use forzado con el schema del modulo
        kwargs = fake.call_args.kwargs
        assert kwargs["tool_name"] == "isms_document_analysis"
        assert kwargs["input_schema"] is svc._ISMS_ANALYSIS_SCHEMA
        assert kwargs["call_type"] == "isms_analysis"
    finally:
        db.close()

    db = _TestSession()
    try:
        doc = db.get(AiDocument, doc_id)
        assert doc.isms_status == "analysed"
        assert doc.doc_class == "normative"
        assert doc.analysed_at is not None
        summary = doc.isms_summary or {}
        assert summary.get("document_level") == 2
        pol = db.get(Policy, summary.get("policy_id"))
        assert pol is not None
        assert pol.document_level == 2
        assert "5.17" in (pol.intended_controls or [])
    finally:
        db.close()


def test_record_does_not_create_policy(client):
    """F2: un documento clasificado como `record` no se materializa como Policy,
    aunque el modelo marque is_policy=True (SOC 2, certificado, pentest)."""
    from app.services import isms_analysis_service as svc
    from app.models import AiDocument, Policy

    db = _TestSession()
    try:
        user = _admin(db)
        doc_id = _make_indexed_doc(db, user.organization_id, user.id).id
    finally:
        db.close()

    db = _TestSession()
    try:
        with patch("app.services.model_registry.get_api_key", return_value="sk-test"), \
             patch("app.services.claude_client.structured_message",
                   return_value=(_record_payload(), _FakeMessage())):
            svc.analyze_document_for_isms(db, doc_id)
    finally:
        db.close()

    db = _TestSession()
    try:
        doc = db.get(AiDocument, doc_id)
        assert doc.doc_class == "record"
        summary = doc.isms_summary or {}
        assert summary.get("policy_id") is None, "Un record no debe crear Policy"
        assert db.query(Policy).filter_by(source_document_id=doc_id).count() == 0
    finally:
        db.close()


def test_missing_api_key_is_skipped_not_error(client):
    """Sin credencial el documento queda 'skipped', nunca 'error'."""
    from app.services import isms_analysis_service as svc
    from app.models import AiDocument

    db = _TestSession()
    try:
        user = _admin(db)
        doc_id = _make_indexed_doc(db, user.organization_id, user.id).id
    finally:
        db.close()

    db = _TestSession()
    try:
        with patch("app.services.model_registry.get_api_key", return_value=None):
            svc.analyze_document_for_isms(db, doc_id)
    finally:
        db.close()

    db = _TestSession()
    try:
        assert db.get(AiDocument, doc_id).isms_status == "skipped"
    finally:
        db.close()


def test_api_failure_records_readable_error(client):
    """Un fallo de la API deja el motivo visible en isms_summary."""
    from app.services import isms_analysis_service as svc
    from app.models import AiDocument

    db = _TestSession()
    try:
        user = _admin(db)
        doc_id = _make_indexed_doc(db, user.organization_id, user.id).id
    finally:
        db.close()

    db = _TestSession()
    try:
        with patch("app.services.model_registry.get_api_key", return_value="sk-test"), \
             patch("app.services.claude_client.structured_message",
                   side_effect=ValueError("el modelo no devolvio la herramienta")):
            svc.analyze_document_for_isms(db, doc_id)
    finally:
        db.close()

    db = _TestSession()
    try:
        doc = db.get(AiDocument, doc_id)
        assert doc.isms_status == "error"
        assert "herramienta" in (doc.isms_summary or {}).get("error", "")
    finally:
        db.close()


def test_legacy_helpers_still_importable(client):
    """policy_generation_service, risk_auto_generator y bcp.py importan estos
    dos helpers desde aqui. Delegan en model_registry pero deben seguir vivos."""
    from app.services.isms_analysis_service import _get_api_key, _get_model

    db = _TestSession()
    try:
        org_id = _admin(db).organization_id
        # Sin AiConfig ni key global el fallback es None, no una excepcion.
        assert _get_api_key(db, org_id) in (None, "") or isinstance(_get_api_key(db, org_id), str)
        # El tier deep respeta el override de la org y si no cae al modelo profundo.
        assert _get_model(db, org_id).startswith("claude-")
    finally:
        db.close()
