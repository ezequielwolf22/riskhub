"""Regresiones del Plan Director / Cockpit de Tratamiento.

Cada test fija un fallo concreto que se detecto en uso real:

  1. Superadmin con X-Active-Org: lo creado se guardaba en la org del
     superadmin y desaparecia de la lista (parecia que no se guardaba nada).
  2. El wizard solo ofrecia implementaciones existentes: una org sin
     implementaciones veia el paso 2/2 vacio y no podia declarar controles.
  3. La proyeccion solo contaba controles ya vinculados al riesgo, asi que los
     riesgos derivados por catalogo proyectaban siempre reduccion 0.
  4. El cockpit no devolvia los datos completos del tratamiento (opcion, plan
     integro, controles, evidencia), y el formulario de edicion se abria vacio.
"""
import uuid

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _default_org(db):
    from app.models import Organization
    return db.query(Organization).first()


# ---------- 1. Aislamiento por organizacion en escritura ----------

def _superadmin_headers(client):
    """Crea un superadmin cuya organizacion propia NO es la org activa."""
    from app.models import Organization, User, UserRole
    from app.security import hash_password

    db = _TestSession()
    try:
        own_org = _default_org(db)
        target_org = Organization(name=f"Cliente {_uid()}", plan="enterprise")
        db.add(target_org)
        db.flush()
        email = f"super-{_uid()}@test.internal"
        db.add(User(
            email=email, full_name="Super", role=UserRole.SUPERADMIN,
            hashed_password=hash_password("SuperAdmin123!"),
            organization_id=own_org.id, is_active=True,
        ))
        db.commit()
        target_org_id = target_org.id
    finally:
        db.close()

    token = client.post("/api/auth/login", data={
        "username": email, "password": "SuperAdmin123!",
    }).json()["access_token"]
    return {"Authorization": f"Bearer {token}",
            "X-Active-Org": str(target_org_id)}, target_org_id


def test_superadmin_program_lands_in_active_org(client):
    """Un programa creado con X-Active-Org debe aparecer al listar esa org."""
    headers, org_id = _superadmin_headers(client)
    name = f"Programa cliente {_uid()}"

    created = client.post("/api/initiatives/programs", json={"name": name}, headers=headers)
    assert created.status_code == 200, created.text

    listed = client.get("/api/initiatives/programs", headers=headers)
    assert listed.status_code == 200
    assert any(p["id"] == created.json()["id"] for p in listed.json()), \
        "el programa se guardo en otra organizacion y no aparece en la lista"

    db = _TestSession()
    try:
        from app.models import StrategicProgram
        stored = db.get(StrategicProgram, created.json()["id"])
        assert stored.organization_id == org_id
    finally:
        db.close()


def test_superadmin_initiative_lands_in_active_org(client):
    headers, org_id = _superadmin_headers(client)

    created = client.post("/api/initiatives/", json={
        "title": f"Iniciativa cliente {_uid()}", "priority": "high",
    }, headers=headers)
    assert created.status_code == 200, created.text

    listed = client.get("/api/initiatives/", headers=headers)
    assert any(i["id"] == created.json()["id"] for i in listed.json()), \
        "la iniciativa se guardo en otra organizacion y no aparece en la lista"

    stats = client.get("/api/initiatives/stats", headers=headers).json()
    assert stats["initiatives_total"] >= 1


# ---------- 2. Catalogo de controles para el wizard ----------

def test_control_catalog_returns_full_iso_catalogue(client, auth_headers):
    """El wizard debe poder ofrecer controles aunque la org no tenga ninguna
    implementacion dada de alta."""
    resp = client.get("/api/initiatives/control-catalog", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    catalog = resp.json()
    assert len(catalog) >= 90, "el catalogo ISO 27002 deberia traer los 93 controles"
    entry = catalog[0]
    for field in ("control_id", "code", "name", "implementation_id", "maturity", "implemented"):
        assert field in entry


def test_control_target_from_catalogue_creates_implementation(client, auth_headers):
    """Declarar un control del catalogo crea su implementacion automaticamente."""
    catalog = client.get("/api/initiatives/control-catalog", headers=auth_headers).json()
    pending = next((c for c in catalog if not c["implemented"]), None)
    assert pending is not None, "se esperaba algun control sin implementacion"

    ini = client.post("/api/initiatives/", json={"title": f"Ini {_uid()}"},
                      headers=auth_headers).json()
    resp = client.post(f"/api/initiatives/{ini['id']}/control-targets", json={
        "control_id": pending["control_id"], "target_maturity": 4,
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    target = resp.json()
    assert target["implementation_id"] is not None
    assert target["control_code"] == pending["code"]
    assert target["target_maturity"] == 4

    # Repetirlo no duplica ni la implementacion ni el control objetivo
    again = client.post(f"/api/initiatives/{ini['id']}/control-targets", json={
        "control_id": pending["control_id"], "target_maturity": 5,
    }, headers=auth_headers)
    assert again.status_code == 409

    db = _TestSession()
    try:
        from app.models import ControlImplementation
        org_id = _default_org(db).id
        impls = db.query(ControlImplementation).filter(
            ControlImplementation.organization_id == org_id,
            ControlImplementation.control_id == pending["control_id"],
        ).all()
        assert len(impls) == 1, "la implementacion se duplico"
    finally:
        db.close()


def test_control_target_requires_an_identifier(client, auth_headers):
    ini = client.post("/api/initiatives/", json={"title": f"Ini {_uid()}"},
                      headers=auth_headers).json()
    resp = client.post(f"/api/initiatives/{ini['id']}/control-targets",
                       json={"target_maturity": 3}, headers=auth_headers)
    assert resp.status_code == 422


# ---------- 3. Proyeccion sobre riesgos derivados por catalogo ----------

def test_projection_reduces_risk_derived_from_threat_catalogue(client, auth_headers):
    """Un riesgo derivado por catalogo (sin el control aun vinculado) debe
    proyectar reduccion real: antes salia proyectado == baseline."""
    from app.models import Asset, AssetType, Risk, RiskStatus, Threat
    from app.services.threat_knowledge import controls_for_threat

    db = _TestSession()
    try:
        org = _default_org(db)
        org_id = org.id
        # Amenaza del catalogo con controles candidatos conocidos
        chosen, candidates = None, []
        for th in db.query(Threat).all():
            if not th.code:
                continue
            cands = controls_for_threat(db, org_id, th.code)
            if len(cands) >= 2:
                chosen, candidates = th, cands
                break
        assert chosen is not None, "no hay amenaza con controles candidatos en el catalogo"

        asset = Asset(organization_id=org_id, code=f"AST-{_uid()}", name=f"Activo {_uid()}",
                      asset_type=AssetType.SUPPORT_SOFTWARE)
        db.add(asset)
        db.flush()
        risk = Risk(
            organization_id=org_id, code=f"RSK-{_uid()}", asset_id=asset.id, threat_id=chosen.id,
            inherent_likelihood=4, inherent_consequence=4, inherent_level=8,
            residual_likelihood=4, residual_consequence=4, residual_level=8,
            status=RiskStatus.ASSESSED,
        )
        db.add(risk)
        db.commit()
        risk_id = risk.id
        candidate_codes = [c["code"] for c in candidates[:3]]
    finally:
        db.close()

    catalog = client.get("/api/initiatives/control-catalog", headers=auth_headers).json()
    by_code = {c["code"]: c for c in catalog}
    targets = [by_code[code] for code in candidate_codes if code in by_code]
    assert targets, "los controles candidatos deberian estar en el catalogo ISO 27002"

    ini = client.post("/api/initiatives/", json={
        "title": f"Ini {_uid()}", "status": "in_progress",
    }, headers=auth_headers).json()
    for target in targets:
        client.post(f"/api/initiatives/{ini['id']}/control-targets", json={
            "control_id": target["control_id"], "target_maturity": 5,
        }, headers=auth_headers)

    detail = client.get(f"/api/initiatives/{ini['id']}", headers=auth_headers).json()
    link = next((rl for rl in detail["risk_links"] if rl["risk_id"] == risk_id), None)
    assert link is not None, "el riesgo no se derivo automaticamente de los controles objetivo"
    assert link["origin"] == "auto"
    assert link["projected_residual_level"] is not None
    assert link["projected_residual_level"] < link["baseline_residual_level"], (
        "la iniciativa sube 3 controles mitigadores a madurez 5 y aun asi "
        "proyecta reduccion cero"
    )


def test_projection_ignores_controls_unrelated_to_the_threat(client, auth_headers):
    """Un control que el catalogo no reconoce como mitigador de la amenaza no
    debe inventar reduccion. Se compara la proyeccion del MISMO riesgo antes y
    despues de anadir un control objetivo irrelevante."""
    from app.models import (
        Asset, AssetType, InitiativeRiskLink, Risk, RiskStatus, Threat, ThreatOrigin,
    )

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        # Amenaza propia: no esta en el catalogo amenaza->control, asi que
        # ningun control puede reclamarse mitigador suyo.
        threat = Threat(code=f"THR-ISO-{_uid()}", name=f"Amenaza {_uid()}",
                        origin=ThreatOrigin.DELIBERATE, is_custom=True)
        db.add(threat)
        asset = Asset(organization_id=org_id, code=f"AST-{_uid()}", name=f"Activo {_uid()}",
                      asset_type=AssetType.SUPPORT_SOFTWARE)
        db.add(asset)
        db.flush()
        risk = Risk(
            organization_id=org_id, code=f"RSK-{_uid()}", asset_id=asset.id, threat_id=threat.id,
            inherent_likelihood=4, inherent_consequence=4, inherent_level=8,
            residual_likelihood=4, residual_consequence=4, residual_level=8,
            status=RiskStatus.ASSESSED,
        )
        db.add(risk)
        db.commit()
        risk_id = risk.id
    finally:
        db.close()

    ini = client.post("/api/initiatives/", json={
        "title": f"Ini {_uid()}", "status": "in_progress",
    }, headers=auth_headers).json()
    client.post(f"/api/initiatives/{ini['id']}/risks", json={"risk_id": risk_id},
                headers=auth_headers)

    def _projected():
        db = _TestSession()
        try:
            link = db.query(InitiativeRiskLink).filter(
                InitiativeRiskLink.initiative_id == ini["id"],
                InitiativeRiskLink.risk_id == risk_id,
            ).first()
            assert link is not None
            return link.projected_residual_level
        finally:
            db.close()

    before = _projected()

    catalog = client.get("/api/initiatives/control-catalog", headers=auth_headers).json()
    client.post(f"/api/initiatives/{ini['id']}/control-targets", json={
        "control_id": catalog[0]["control_id"], "target_maturity": 5,
    }, headers=auth_headers)
    client.post(f"/api/initiatives/{ini['id']}/reproject", headers=auth_headers)

    assert _projected() == before, (
        "un control ajeno a la amenaza no debe reducir el residual proyectado"
    )


# ---------- 4. Datos completos en el cockpit de tratamiento ----------

def test_treatment_board_returns_full_treatment_data(client, auth_headers):
    """El cockpit debe devolver el plan integro y la opcion elegida: con solo
    un extracto, el formulario de edicion guardaba el plan truncado o vacio."""
    from app.models import Asset, AssetType, Risk, RiskStatus, Threat, TreatmentOption

    plan = "Plan detallado de tratamiento. " * 30  # > 160 caracteres
    db = _TestSession()
    try:
        org_id = _default_org(db).id
        threat = db.query(Threat).first()
        asset = Asset(organization_id=org_id, code=f"AST-{_uid()}", name=f"Activo {_uid()}",
                      asset_type=AssetType.SUPPORT_SOFTWARE)
        db.add(asset)
        db.flush()
        risk = Risk(
            organization_id=org_id, code=f"RSK-{_uid()}", asset_id=asset.id, threat_id=threat.id,
            inherent_likelihood=4, inherent_consequence=4, inherent_level=8,
            residual_likelihood=4, residual_consequence=4, residual_level=8,
            status=RiskStatus.ASSESSED, treatment_option=TreatmentOption.MODIFICATION,
            treatment_plan=plan, treatment_progress=40,
            acceptance_justification="Aprobado por el comite.",
        )
        db.add(risk)
        db.commit()
        risk_id = risk.id
    finally:
        db.close()

    board = client.get("/api/risks/treatment-board", headers=auth_headers).json()
    items = [it for col in board["columns"].values() for it in col]
    item = next((it for it in items if it["id"] == risk_id), None)
    assert item is not None, "el riesgo tratado no aparece en el cockpit"

    assert item["treatment_option"] == "modification"
    assert item["treatment_plan"] == plan, "el plan llega truncado o vacio"
    assert len(item["treatment_plan"]) > 160
    assert item["acceptance"]["justification"] == "Aprobado por el comite."
    for field in ("controls", "evidence", "evidence_count", "owner_id", "stale_reason"):
        assert field in item, f"falta {field} en el item del cockpit"
    assert "treated_without_evidence" in board["kpis"]


def test_treatment_board_exposes_evidence_backing_the_plan(client, auth_headers):
    """La evidencia subida al riesgo y la de sus controles mitigadores deben
    verse en el cockpit (sin duplicarse)."""
    from app.models import (
        Asset, AssetType, Control, ControlImplementation, Evidence, EvidenceType,
        Risk, RiskStatus, Threat, TreatmentOption,
    )

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        threat = db.query(Threat).first()
        control = db.query(Control).first()
        asset = Asset(organization_id=org_id, code=f"AST-{_uid()}", name=f"Activo {_uid()}",
                      asset_type=AssetType.SUPPORT_SOFTWARE)
        db.add(asset)
        db.flush()
        impl = ControlImplementation(organization_id=org_id, control_id=control.id,
                                     name=f"Impl {_uid()}", maturity=3)
        db.add(impl)
        db.flush()
        risk = Risk(
            organization_id=org_id, code=f"RSK-{_uid()}", asset_id=asset.id, threat_id=threat.id,
            inherent_likelihood=4, inherent_consequence=4, inherent_level=8,
            residual_likelihood=3, residual_consequence=3, residual_level=6,
            status=RiskStatus.ASSESSED, treatment_option=TreatmentOption.MODIFICATION,
        )
        risk.controls.append(impl)
        db.add(risk)
        db.flush()
        db.add(Evidence(organization_id=org_id, code=f"EVD-{_uid()}", title="Acta de comite",
                        evidence_type=EvidenceType.RECORD, risk_id=risk.id, is_current=True))
        db.add(Evidence(organization_id=org_id, code=f"EVD-{_uid()}", title="Certificado",
                        evidence_type=EvidenceType.CERTIFICATE,
                        control_implementation_id=impl.id, is_current=True))
        db.commit()
        risk_id = risk.id
    finally:
        db.close()

    board = client.get("/api/risks/treatment-board", headers=auth_headers).json()
    items = [it for col in board["columns"].values() for it in col]
    item = next((it for it in items if it["id"] == risk_id), None)
    assert item is not None

    assert item["evidence_count"] == 2, "deberia ver la evidencia del riesgo y la del control"
    codes = [e["code"] for e in item["evidence"]]
    assert len(codes) == len(set(codes)), "evidencia duplicada"
    assert any(c["evidence_count"] == 1 for c in item["controls"])


def test_initiative_detail_exposes_control_evidence(client, auth_headers):
    """Cada control objetivo debe mostrar la evidencia que respalda su madurez."""
    from app.models import Control, ControlImplementation, Evidence, EvidenceType

    db = _TestSession()
    try:
        org_id = _default_org(db).id
        control = db.query(Control).first()
        impl = ControlImplementation(organization_id=org_id, control_id=control.id,
                                     name=f"Impl {_uid()}", maturity=2)
        db.add(impl)
        db.flush()
        db.add(Evidence(organization_id=org_id, code=f"EVD-{_uid()}", title="Politica firmada",
                        evidence_type=EvidenceType.POLICY,
                        control_implementation_id=impl.id, is_current=True))
        db.commit()
        impl_id = impl.id
    finally:
        db.close()

    ini = client.post("/api/initiatives/", json={"title": f"Ini {_uid()}"},
                      headers=auth_headers).json()
    client.post(f"/api/initiatives/{ini['id']}/control-targets", json={
        "implementation_id": impl_id, "target_maturity": 4,
    }, headers=auth_headers)

    detail = client.get(f"/api/initiatives/{ini['id']}", headers=auth_headers).json()
    target = next(ct for ct in detail["control_targets"] if ct["implementation_id"] == impl_id)
    assert target["evidence_count"] == 1
    assert target["evidence"][0]["title"] == "Politica firmada"
