"""Regwatch v6.7.0: versionado de compliance y migracion de plantillas clonadas."""
from app.services import regwatch_propagation as prop


def _mk_pack(db, framework_code="ISO_27001", version_to="2022+A1"):
    from app.models import ChangePack, ChangeSeverity
    pack = ChangePack(
        framework_code=framework_code,
        version_from="2022",
        version_to=version_to,
        severity=ChangeSeverity.SUBSTANTIVE,
        title_es="Enmienda de prueba",
        controls_modified=[{"control_id": "A.5.1", "field": "name", "after": "x"}],
    )
    db.add(pack)
    db.commit()
    return pack


def test_compliance_requirements_stamp_framework_version(client):
    from tests.conftest import _TestSession
    from app.models import ComplianceFrameworkStatus, Organization
    db = _TestSession()
    try:
        org = db.query(Organization).first()
        pack = _mk_pack(db)
        req = ComplianceFrameworkStatus(
            organization_id=org.id, framework_code="iso27001",
            requirement_id="A.5.1",
        )
        db.add(req)
        db.commit()

        flagged = prop._update_compliance_requirements(db, org.id, pack)
        db.commit()
        assert flagged >= 1
        db.refresh(req)
        assert req.framework_version == "2022+A1"
        assert req.regwatch_pack_id == pack.id
        assert req.last_reviewed_at is None
    finally:
        db.close()


def test_cloned_templates_flagged_and_migrated(client):
    from tests.conftest import _TestSession
    from app.models import Organization, TPRMTemplate, TenantRegwatchSettings
    from app.services import tprm_templates as sys_tpls
    db = _TestSession()
    try:
        org = db.query(Organization).first()
        pack = _mk_pack(db)
        system = sys_tpls.get_template("RH_TPRM_LITE_v1")
        assert system, "plantilla del sistema RH_TPRM_LITE_v1 debe existir"

        # Clon al que le falta la primera pregunta del sistema (simula version vieja)
        cloned_questions = list(system["questions"][1:])
        tpl = TPRMTemplate(
            organization_id=org.id, name="Clon de prueba",
            framework_codes=["ISO_27001"], questions=cloned_questions,
            created_from="RH_TPRM_LITE_v1",
        )
        # Clon de otro framework: no debe tocarse
        tpl_other = TPRMTemplate(
            organization_id=org.id, name="Clon PCI",
            framework_codes=["PCI_DSS"], questions=[{"id": "x1", "text": "?"}],
        )
        db.add_all([tpl, tpl_other])
        db.commit()

        # Caso 1: auto_apply OFF -> solo flag, sin tocar preguntas
        s = db.query(TenantRegwatchSettings).filter_by(organization_id=org.id).first()
        if not s:
            s = TenantRegwatchSettings(organization_id=org.id)
            db.add(s)
        s.auto_apply_to_clones = False
        db.commit()

        out = prop._migrate_cloned_templates(db, org.id, pack)
        db.commit()
        assert out["cloned_templates_flagged"] == 1
        assert out["cloned_templates_updated"] == 0
        db.refresh(tpl)
        assert tpl.regwatch_pack_id == pack.id
        assert len(tpl.questions) == len(cloned_questions)
        db.refresh(tpl_other)
        assert tpl_other.regwatch_pack_id is None

        # Caso 2: auto_apply ON -> anade la pregunta del sistema que faltaba
        s.auto_apply_to_clones = True
        db.commit()
        out = prop._migrate_cloned_templates(db, org.id, pack)
        db.commit()
        assert out["cloned_templates_updated"] == 1
        db.refresh(tpl)
        ids = {q["id"] for q in tpl.questions}
        assert system["questions"][0]["id"] in ids
        # Idempotente: segunda pasada no duplica
        out = prop._migrate_cloned_templates(db, org.id, pack)
        assert out["cloned_templates_updated"] == 0
    finally:
        # Limpieza para no contaminar otros tests. Rollback previo: la ultima
        # pasada del helper deja updates pendientes sobre las filas que vamos
        # a borrar en bulk (StaleDataError si se flushean tras el delete).
        db.rollback()
        from app.models import TPRMTemplate as _T
        db.query(_T).filter(_T.name.in_(["Clon de prueba", "Clon PCI"])).delete(
            synchronize_session=False)
        db.commit()
        db.close()
