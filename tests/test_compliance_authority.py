"""F4 — cumplimiento con evidencia verificada, no fichas vacias.

Dos garantias:
  1. `_evidence_qualifies`: una ficha auto-generada sin contenido verificado NO
     cuenta como evidencia; la manual y la verificada si.
  2. `auto_update_compliance_from_controls`: un requisito con sus controles
     implementados pero sin evidencia real se queda en PARTIAL (75%), no salta a
     IMPLEMENTED (100%). Con evidencia verificada, si llega a IMPLEMENTED.
  3. La heuristica por categoria del desplegable (_update_compliance_from_doc_category)
     ya no existe.
"""
import uuid

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _fresh_org(db):
    from app.models import Organization
    org = Organization(name=f"Org compliance {_uid()}", plan="enterprise")
    db.add(org)
    db.flush()
    return org


def test_evidence_qualifies_unit():
    from app.services.compliance_service import _evidence_qualifies
    # Manual o legacy: siempre cuenta.
    assert _evidence_qualifies(False, None) is True
    assert _evidence_qualifies(None, None) is True
    # Auto-generada sin revision de contenido: no cuenta.
    assert _evidence_qualifies(True, None) is False
    assert _evidence_qualifies(True, {}) is False
    # Auto-generada verificada como relevante: cuenta.
    assert _evidence_qualifies(True, {"relevant": True, "quality_level": "E4"}) is True
    # Auto-generada verificada como NO relevante: no cuenta.
    assert _evidence_qualifies(True, {"relevant": False}) is False


def test_category_heuristic_is_gone():
    """La funcion que pintaba verde por el desplegable de subida se elimino."""
    import app.services.isms_analysis_service as svc
    assert not hasattr(svc, "_update_compliance_from_doc_category")
    assert not hasattr(svc, "_DOC_CATEGORY_COMPLIANCE_MAP")


def _setup_org_with_implemented_control(db):
    from app.models import (RiskContext, Control, ControlImplementation, ControlStatus)
    from app.services.compliance_service import initialize_org_framework
    org = _fresh_org(db)
    db.add(RiskContext(organization_id=org.id, active_frameworks=["iso27001"]))
    db.flush()
    initialize_org_framework(db, org.id, "iso27001")
    ctrl = db.query(Control).filter_by(code="5.1").first()
    impl = ControlImplementation(
        organization_id=org.id, control_id=ctrl.id, name=f"Impl {_uid()}",
        status=ControlStatus.IMPLEMENTED, maturity=4,
    )
    db.add(impl)
    db.commit()
    return org.id, impl.id


def _req_52_status(db, org_id):
    from app.models import ComplianceFrameworkStatus
    return db.query(ComplianceFrameworkStatus).filter_by(
        organization_id=org_id, framework_code="iso27001", requirement_id="5.2").first()


def test_empty_auto_evidence_does_not_reach_implemented(client):
    """Control implementado + ficha auto vacia => PARTIAL, no IMPLEMENTED."""
    from app.models import Evidence, ComplianceRequirementStatus
    from app.services.compliance_service import auto_update_compliance_from_controls

    db = _TestSession()
    try:
        org_id, impl_id = _setup_org_with_implemented_control(db)
        # Ficha auto-generada SIN ai_review (contenido no verificado)
        db.add(Evidence(
            organization_id=org_id, code=f"EVD-A{_uid()[:5]}",
            title=f"Ficha auto {_uid()}", control_implementation_id=impl_id,
            auto_generated=True, is_current=True,
        ))
        db.commit()

        auto_update_compliance_from_controls(db, org_id)
        st = _req_52_status(db, org_id)
        assert st is not None
        # El requisito 5.2 (controls=[5.1]) esta cubierto pero sin evidencia real.
        assert st.status == ComplianceRequirementStatus.PARTIAL
        assert st.completion_pct == 75
    finally:
        db.close()


def test_verified_auto_evidence_reaches_implemented(client):
    """Misma ficha, pero con contenido verificado (E4) => IMPLEMENTED 100."""
    from app.models import Evidence, ComplianceRequirementStatus
    from app.services.compliance_service import auto_update_compliance_from_controls

    db = _TestSession()
    try:
        org_id, impl_id = _setup_org_with_implemented_control(db)
        db.add(Evidence(
            organization_id=org_id, code=f"EVD-V{_uid()[:5]}",
            title=f"Ficha verificada {_uid()}", control_implementation_id=impl_id,
            auto_generated=True, is_current=True,
            ai_review={"relevant": True, "quality_level": "E4"},
        ))
        db.commit()

        auto_update_compliance_from_controls(db, org_id)
        st = _req_52_status(db, org_id)
        assert st.status == ComplianceRequirementStatus.IMPLEMENTED
        assert st.completion_pct == 100
    finally:
        db.close()


def test_auto_update_writes_provenance(client):
    """El recalculo por controles deja procedencia: source, rationale, computed_at."""
    from app.models import Evidence, EvidenceType
    from app.services.compliance_service import auto_update_compliance_from_controls

    db = _TestSession()
    try:
        org_id, impl_id = _setup_org_with_implemented_control(db)
        db.add(Evidence(
            organization_id=org_id, code=f"EVD-P{_uid()[:5]}",
            title=f"Ev {_uid()}", control_implementation_id=impl_id,
            evidence_type=EvidenceType.OTHER, auto_generated=False, is_current=True,
        ))
        db.commit()
        auto_update_compliance_from_controls(db, org_id)
        st = _req_52_status(db, org_id)
        assert st.source == "controls_derived"
        assert st.rationale and "5.1" in st.rationale
        assert st.computed_at is not None
        assert st.source_ref and "5.1" in st.source_ref
    finally:
        db.close()


def test_human_decision_not_overwritten_by_auto(client):
    """Una decision humana (source=human_manual) sobrevive al recalculo automatico."""
    from app.models import ComplianceRequirementStatus
    from app.services.compliance_service import auto_update_compliance_from_controls

    db = _TestSession()
    try:
        org_id, impl_id = _setup_org_with_implemented_control(db)
        st = _req_52_status(db, org_id)
        # Un humano lo marca NOT_APPLICABLE con procedencia humana.
        st.status = ComplianceRequirementStatus.NOT_APPLICABLE
        st.completion_pct = 0
        st.source = "human_manual"
        st.rationale = "Excluido con justificacion por el CISO."
        db.commit()

        auto_update_compliance_from_controls(db, org_id)
        st = _req_52_status(db, org_id)
        # El recalculo NO lo pisa: sigue siendo la decision humana.
        assert st.status == ComplianceRequirementStatus.NOT_APPLICABLE
        assert st.source == "human_manual"
    finally:
        db.close()


def test_manual_update_sets_human_provenance(client, auth_headers):
    """El PUT del router marca la procedencia como humana.

    Usa un requirement_id propio (no del catalogo estandar) para no contaminar
    la org por defecto compartida entre tests con requisitos que otros esperan
    crear ellos mismos (p.ej. la propagacion regwatch sobre A.5.1)."""
    fw, req_id = "iso27001", "PROV.TEST.1"
    # El PUT crea el requisito si no existe, sin necesidad de inicializar el marco.
    resp = client.put(f"/api/compliance/requirements/{fw}/{req_id}", headers=auth_headers,
                      json={"status": "implemented", "completion_pct": 100,
                            "notes": "Verificado a mano"})
    assert resp.status_code == 200, resp.text

    prov = client.get(f"/api/compliance/requirements/{fw}/{req_id}/provenance", headers=auth_headers)
    assert prov.status_code == 200, prov.text
    body = prov.json()
    assert body["source"] == "human_manual"
    assert body["rationale"] == "Verificado a mano"
    assert body["computed_at"] is not None


def test_manual_evidence_reaches_implemented(client):
    """Evidencia manual (humana) siempre cuenta => IMPLEMENTED 100."""
    from app.models import Evidence, EvidenceType, ComplianceRequirementStatus
    from app.services.compliance_service import auto_update_compliance_from_controls

    db = _TestSession()
    try:
        org_id, impl_id = _setup_org_with_implemented_control(db)
        db.add(Evidence(
            organization_id=org_id, code=f"EVD-H{_uid()[:5]}",
            title=f"Evidencia humana {_uid()}", control_implementation_id=impl_id,
            evidence_type=EvidenceType.OTHER, auto_generated=False, is_current=True,
        ))
        db.commit()

        auto_update_compliance_from_controls(db, org_id)
        st = _req_52_status(db, org_id)
        assert st.status == ComplianceRequirementStatus.IMPLEMENTED
        assert st.completion_pct == 100
    finally:
        db.close()
