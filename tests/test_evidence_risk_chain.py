"""F3 — la cadena documento -> evidencia -> control -> madurez -> riesgo.

El bug que arreglan estos tests: `evidence_inference_service` creaba filas
`Evidence` con `control_implementation_id = None`, asi que
`risk_recalc_service._ai_evidence_factor` (que filtra por ese id) nunca las
encontraba y el factor de calidad E1-E5 no llegaba nunca al motor de riesgo.
La documentacion del SGSI no movia el residual por la via correcta.
"""
import uuid

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _fresh_org(db):
    from app.models import Organization
    org = Organization(name=f"Org cadena {_uid()}", plan="enterprise")
    db.add(org)
    db.flush()
    return org


def _control_51(db):
    from app.models import Control
    ctrl = db.query(Control).filter_by(code="5.1").first()
    assert ctrl is not None, "El control 5.1 debe estar en el catalogo sembrado"
    return ctrl


def _make_impl(db, org_id, control):
    from app.models import ControlImplementation, ControlStatus
    impl = ControlImplementation(
        organization_id=org_id, control_id=control.id,
        name=f"Impl 5.1 {_uid()}", status=ControlStatus.IMPLEMENTED, maturity=3,
    )
    db.add(impl)
    db.flush()
    return impl


def _make_doc(db, org_id):
    from app.models import AiDocument, AiDocumentCategory, AiDocumentStatus
    doc = AiDocument(
        organization_id=org_id, filename=f"{_uid()}.pdf",
        original_name=f"Politica de accesos {_uid()}.pdf",
        category=AiDocumentCategory.POLICIES, status=AiDocumentStatus.INDEXED,
        mime_type="application/pdf",
    )
    db.add(doc)
    db.flush()
    return doc


def test_inference_links_evidence_to_control_and_document(client):
    """La Evidence derivada de un documento se engancha a su ControlImplementation."""
    from app.models import RiskContext, Evidence
    from app.services.evidence_inference_service import infer_compliance_from_document

    db = _TestSession()
    try:
        org = _fresh_org(db)
        ctx = RiskContext(organization_id=org.id, active_frameworks=["iso27001"])
        db.add(ctx)
        ctrl = _control_51(db)
        impl = _make_impl(db, org.id, ctrl)
        doc = _make_doc(db, org.id)
        db.commit()
        org_id, impl_id, doc_id = org.id, impl.id, doc.id

        controls_covered = [{"code": "5.1", "coverage": "full", "maturity_current": 4}]
        res = infer_compliance_from_document(db, doc, controls_covered, org_id)
        assert res["evidence_created"] >= 1

        ev = db.query(Evidence).filter_by(
            organization_id=org_id, source_document_id=doc_id).first()
        assert ev is not None, "Debe crearse una Evidence enganchada al documento"
        assert ev.control_implementation_id == impl_id
        assert ev.auto_generated is True
    finally:
        db.close()


def test_quality_factor_reaches_risk_engine(client):
    """Con ai_review E4, el factor de calidad llega al motor via _ai_evidence_factor.

    Es la prueba de que la cadena quedo reconectada: antes _ai_evidence_factor
    devolvia None porque no encontraba ninguna evidencia para el control.
    """
    from app.models import RiskContext, Evidence, ControlImplementation
    from app.services.evidence_inference_service import infer_compliance_from_document
    from app.services.risk_recalc_service import _ai_evidence_factor
    from app.services.evidence_understanding_service import QUALITY_LEVEL_FACTOR

    db = _TestSession()
    try:
        org = _fresh_org(db)
        db.add(RiskContext(organization_id=org.id, active_frameworks=["iso27001"]))
        ctrl = _control_51(db)
        impl = _make_impl(db, org.id, ctrl)
        doc = _make_doc(db, org.id)
        db.commit()
        impl_id = impl.id

        infer_compliance_from_document(
            db, doc, [{"code": "5.1", "coverage": "full", "maturity_current": 4}], org.id)

        ev = db.query(Evidence).filter_by(control_implementation_id=impl_id).first()
        assert ev is not None
        # Antes de verificar contenido: sin ai_review no hay factor.
        impl = db.get(ControlImplementation, impl_id)
        assert _ai_evidence_factor(db, impl) is None

        # Tras la revision de contenido (evidence understanding): E4.
        ev.ai_review = {"relevant": True, "quality_level": "E4"}
        db.commit()
        factor = _ai_evidence_factor(db, impl)
        assert factor == QUALITY_LEVEL_FACTOR["E4"]
    finally:
        db.close()


def test_deleting_document_removes_auto_evidence(client):
    """Borrar el documento elimina su evidencia auto-generada (no queda huerfana)."""
    from app.models import RiskContext, Evidence, AiDocument
    from app.services.evidence_inference_service import infer_compliance_from_document
    from app.services.document_service import delete_document

    db = _TestSession()
    try:
        org = _fresh_org(db)
        db.add(RiskContext(organization_id=org.id, active_frameworks=["iso27001"]))
        ctrl = _control_51(db)
        _make_impl(db, org.id, ctrl)
        doc = _make_doc(db, org.id)
        db.commit()
        doc_id = doc.id

        infer_compliance_from_document(
            db, doc, [{"code": "5.1", "coverage": "full", "maturity_current": 4}], org.id)
        assert db.query(Evidence).filter_by(source_document_id=doc_id).count() >= 1

        detached = delete_document(db, db.get(AiDocument, doc_id))
        assert detached.get("evidence", 0) >= 1
        # La evidencia auto-generada se fue con el documento.
        assert db.query(Evidence).filter_by(source_document_id=doc_id).count() == 0
    finally:
        db.close()


def test_manual_evidence_survives_document_delete(client):
    """La evidencia que un humano vinculo a mano se conserva, solo se desvincula."""
    from app.models import RiskContext, Evidence, AiDocument, EvidenceType
    from app.services.document_service import delete_document

    db = _TestSession()
    try:
        org = _fresh_org(db)
        db.add(RiskContext(organization_id=org.id, active_frameworks=["iso27001"]))
        doc = _make_doc(db, org.id)
        db.flush()
        ev = Evidence(
            organization_id=org.id, code=f"EVD-M{_uid()[:5]}",
            title=f"Evidencia manual {_uid()}", evidence_type=EvidenceType.OTHER,
            source_document_id=doc.id, auto_generated=False, is_current=True,
        )
        db.add(ev)
        db.commit()
        doc_id, ev_id = doc.id, ev.id

        delete_document(db, db.get(AiDocument, doc_id))
        ev = db.get(Evidence, ev_id)
        assert ev is not None, "La evidencia manual no debe borrarse"
        assert ev.source_document_id is None, "Debe quedar desvinculada"
    finally:
        db.close()
