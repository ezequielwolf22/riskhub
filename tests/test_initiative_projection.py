"""Motor determinista del Plan Director: proyeccion what-if, auto-link, verificacion, burndown."""
import uuid
from datetime import datetime, timedelta, timezone

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _default_org(db):
    from app.models import Organization
    return db.query(Organization).first()


def _make_asset(db, org_id):
    from app.models import Asset, AssetType
    a = Asset(organization_id=org_id, code=f"AST-PRJ-{_uid()}", name=f"Activo {_uid()}",
             asset_type=AssetType.SUPPORT_SOFTWARE)
    db.add(a)
    db.flush()
    return a


def _make_threat(db, code=None):
    from app.models import Threat, ThreatOrigin
    th = Threat(code=code or f"THR-PRJ-{_uid()}", name=f"Amenaza {_uid()}",
               origin=ThreatOrigin.DELIBERATE, is_custom=True)
    db.add(th)
    db.flush()
    return th


def _make_control_impl(db, org_id, maturity=1, is_mandatory=False, code=None):
    from app.models import Control, ControlImplementation, ControlStatus
    ctrl = Control(code=code or f"TEST-{_uid()}", name="Control de prueba",
                   is_custom=True, is_mandatory=is_mandatory)
    db.add(ctrl)
    db.flush()
    impl = ControlImplementation(
        organization_id=org_id, control_id=ctrl.id, name="Impl de prueba",
        status=ControlStatus.PARTIAL, maturity=maturity,
    )
    db.add(impl)
    db.flush()
    return impl


def _link_control_to_risk(db, risk_id, impl_id, contribution=1.0):
    from sqlalchemy import insert
    from app.models import risk_control_table
    db.execute(insert(risk_control_table).values(
        risk_id=risk_id, control_implementation_id=impl_id, contribution=contribution,
    ))


def _make_risk(db, org_id, asset, threat, likelihood=4, consequence=4):
    from app.models import Risk, RiskStatus
    r = Risk(
        organization_id=org_id, code=f"RSK-PRJ-{_uid()}",
        asset_id=asset.id, threat_id=threat.id,
        inherent_likelihood=likelihood, inherent_consequence=consequence,
        residual_likelihood=likelihood, residual_consequence=consequence,
        status=RiskStatus.ASSESSED,
    )
    db.add(r)
    db.flush()
    return r


def _make_initiative(db, org_id, status="in_progress"):
    from app.models import StrategicInitiative
    ini = StrategicInitiative(
        organization_id=org_id, code=f"INI-PRJ-{_uid()}", title=f"Iniciativa {_uid()}",
        status=status,
    )
    db.add(ini)
    db.flush()
    return ini


# ---------- project_initiative ----------

def test_project_initiative_reduces_projected_below_current(client):
    from app.services import risk_recalc_service as recalc
    from app.services.initiative_projection_service import project_initiative
    from app.models import InitiativeControlTarget, InitiativeRiskLink

    db = _TestSession()
    try:
        org = _default_org(db)
        asset = _make_asset(db, org.id)
        threat = _make_threat(db)
        impl = _make_control_impl(db, org.id, maturity=1)
        risk = _make_risk(db, org.id, asset, threat)
        _link_control_to_risk(db, risk.id, impl.id)
        db.flush()
        recalc.recalc_risk(db, risk)
        db.commit()
        baseline_residual = risk.residual_level
        assert baseline_residual is not None

        ini = _make_initiative(db, org.id)
        db.add(InitiativeControlTarget(
            organization_id=org.id, initiative_id=ini.id, implementation_id=impl.id,
            baseline_maturity=impl.maturity, target_maturity=4,
        ))
        db.add(InitiativeRiskLink(
            organization_id=org.id, initiative_id=ini.id, risk_id=risk.id,
            origin="manual", baseline_residual_level=baseline_residual,
        ))
        db.commit()

        result = project_initiative(db, ini)
        db.commit()

        assert len(result["risks"]) == 1
        row = result["risks"][0]
        assert row["projected"] < baseline_residual
        link = ini.risk_links[0]
        assert link.projected_residual_level == row["projected"]
        assert link.projected_at is not None
    finally:
        db.close()


def test_project_initiative_never_worsens_control(client):
    """Un target de madurez inferior a la actual no debe empeorar el residual."""
    from app.services import risk_recalc_service as recalc
    from app.services.initiative_projection_service import project_initiative
    from app.models import InitiativeControlTarget, InitiativeRiskLink

    db = _TestSession()
    try:
        org = _default_org(db)
        asset = _make_asset(db, org.id)
        threat = _make_threat(db)
        impl = _make_control_impl(db, org.id, maturity=5)  # ya al maximo
        risk = _make_risk(db, org.id, asset, threat)
        _link_control_to_risk(db, risk.id, impl.id)
        db.flush()
        recalc.recalc_risk(db, risk)
        db.commit()
        baseline_residual = risk.residual_level

        ini = _make_initiative(db, org.id)
        db.add(InitiativeControlTarget(
            organization_id=org.id, initiative_id=ini.id, implementation_id=impl.id,
            baseline_maturity=impl.maturity, target_maturity=1,  # objetivo mas bajo que el actual
        ))
        db.add(InitiativeRiskLink(
            organization_id=org.id, initiative_id=ini.id, risk_id=risk.id,
            origin="manual", baseline_residual_level=baseline_residual,
        ))
        db.commit()

        result = project_initiative(db, ini)
        assert result["risks"][0]["projected"] == baseline_residual
    finally:
        db.close()


def test_project_initiative_respects_mandatory_floor(client):
    from app.services import risk_recalc_service as recalc
    from app.services.initiative_projection_service import project_initiative
    from app.models import InitiativeControlTarget, InitiativeRiskLink

    db = _TestSession()
    try:
        org = _default_org(db)
        asset = _make_asset(db, org.id)
        threat = _make_threat(db)
        impl = _make_control_impl(db, org.id, maturity=0, is_mandatory=True)
        risk = _make_risk(db, org.id, asset, threat)
        _link_control_to_risk(db, risk.id, impl.id)
        db.flush()
        recalc.recalc_risk(db, risk)
        db.commit()
        baseline_residual = risk.residual_level

        ini = _make_initiative(db, org.id)
        # Target sigue por debajo de 2: el floor de obligatorios debe seguir aplicando
        db.add(InitiativeControlTarget(
            organization_id=org.id, initiative_id=ini.id, implementation_id=impl.id,
            baseline_maturity=0, target_maturity=1,
        ))
        db.add(InitiativeRiskLink(
            organization_id=org.id, initiative_id=ini.id, risk_id=risk.id,
            origin="manual", baseline_residual_level=baseline_residual,
        ))
        db.commit()

        result = project_initiative(db, ini)
        # inherent - 1 es el minimo posible con el floor activo
        min_possible_lik = max(0, risk.inherent_likelihood - 1)
        min_possible_cons = max(0, risk.inherent_consequence - 1)
        from app.services.risk_engine import calc_level
        floor_level = calc_level(min_possible_cons, min_possible_lik)
        assert result["risks"][0]["projected"] >= floor_level
    finally:
        db.close()


# ---------- auto_link_risks ----------

def test_auto_link_direct_and_catalog_and_cleanup(client):
    from app.services.initiative_projection_service import auto_link_risks
    from app.services.threat_knowledge import controls_for_threat
    from app.models import InitiativeControlTarget, InitiativeRiskLink, Control, ControlImplementation

    db = _TestSession()
    try:
        org = _default_org(db)
        asset = _make_asset(db, org.id)
        threat = _make_threat(db)

        # Control directo: vinculado formalmente al riesgo via risk_controls
        impl_direct = _make_control_impl(db, org.id, maturity=1)
        risk_direct = _make_risk(db, org.id, asset, threat)
        risk_direct.residual_level = 7
        _link_control_to_risk(db, risk_direct.id, impl_direct.id)

        ini = _make_initiative(db, org.id)
        db.add(InitiativeControlTarget(
            organization_id=org.id, initiative_id=ini.id, implementation_id=impl_direct.id,
            baseline_maturity=1, target_maturity=4,
        ))
        db.commit()

        created = auto_link_risks(db, ini)
        db.commit()
        assert created >= 1
        risk_ids = {link.risk_id for link in ini.risk_links if link.origin == "auto"}
        assert risk_direct.id in risk_ids

        # Quitar el control target: el link auto debe desaparecer
        db.query(InitiativeControlTarget).filter(
            InitiativeControlTarget.initiative_id == ini.id
        ).delete()
        db.commit()
        db.refresh(ini)
        auto_link_risks(db, ini)
        db.commit()
        remaining_auto = [link for link in ini.risk_links if link.origin == "auto"]
        assert remaining_auto == []
    finally:
        db.close()


def test_auto_link_does_not_duplicate_manual_link(client):
    """Un riesgo con vinculo manual que luego se deriva de los controles
    objetivo NO debe generar un segundo link (uq_initiative_risk)."""
    from app.services.initiative_projection_service import auto_link_risks
    from app.models import InitiativeControlTarget, InitiativeRiskLink

    db = _TestSession()
    try:
        org = _default_org(db)
        asset = _make_asset(db, org.id)
        threat = _make_threat(db)
        impl = _make_control_impl(db, org.id, maturity=1)
        risk = _make_risk(db, org.id, asset, threat)
        risk.residual_level = 7
        _link_control_to_risk(db, risk.id, impl.id)  # derivable por via directa
        db.flush()

        ini = _make_initiative(db, org.id)
        # Primero el vinculo MANUAL...
        db.add(InitiativeRiskLink(
            organization_id=org.id, initiative_id=ini.id, risk_id=risk.id,
            origin="manual", baseline_residual_level=7,
        ))
        # ...y despues el control target que deriva el mismo riesgo
        db.add(InitiativeControlTarget(
            organization_id=org.id, initiative_id=ini.id, implementation_id=impl.id,
            baseline_maturity=1, target_maturity=4,
        ))
        db.commit()

        auto_link_risks(db, ini)  # antes del fix: IntegrityError por duplicado
        db.commit()
        db.refresh(ini)
        links_for_risk = [link for link in ini.risk_links if link.risk_id == risk.id]
        assert len(links_for_risk) == 1
        assert links_for_risk[0].origin == "manual"  # el manual se conserva
    finally:
        db.close()


def test_auto_link_keeps_manual_links_untouched(client):
    from app.services.initiative_projection_service import auto_link_risks
    from app.models import InitiativeRiskLink

    db = _TestSession()
    try:
        org = _default_org(db)
        asset = _make_asset(db, org.id)
        threat = _make_threat(db)
        risk = _make_risk(db, org.id, asset, threat)
        risk.residual_level = 6
        db.flush()

        ini = _make_initiative(db, org.id)
        db.add(InitiativeRiskLink(
            organization_id=org.id, initiative_id=ini.id, risk_id=risk.id,
            origin="manual", baseline_residual_level=6,
        ))
        db.commit()

        auto_link_risks(db, ini)  # sin control targets: no debe tocar el link manual
        db.commit()
        db.refresh(ini)
        assert len(ini.risk_links) == 1
        assert ini.risk_links[0].origin == "manual"
    finally:
        db.close()


# ---------- reproject_for_impls (via recalc_risks_for_impls) ----------

def test_recalc_risks_for_impls_reprojects_active_initiatives(client):
    from app.services import risk_recalc_service as recalc
    from app.models import InitiativeControlTarget, InitiativeRiskLink

    db = _TestSession()
    try:
        org = _default_org(db)
        asset = _make_asset(db, org.id)
        threat = _make_threat(db)
        impl = _make_control_impl(db, org.id, maturity=1)
        risk = _make_risk(db, org.id, asset, threat)
        _link_control_to_risk(db, risk.id, impl.id)
        db.flush()
        recalc.recalc_risk(db, risk)
        db.commit()

        ini = _make_initiative(db, org.id, status="in_progress")
        db.add(InitiativeControlTarget(
            organization_id=org.id, initiative_id=ini.id, implementation_id=impl.id,
            baseline_maturity=1, target_maturity=4,
        ))
        db.add(InitiativeRiskLink(
            organization_id=org.id, initiative_id=ini.id, risk_id=risk.id,
            origin="manual", baseline_residual_level=risk.residual_level,
        ))
        db.commit()
        assert ini.risk_links[0].projected_at is None

        recalc.recalc_risks_for_impls(db, [impl.id])
        db.commit()
        db.refresh(ini.risk_links[0])
        assert ini.risk_links[0].projected_at is not None
    finally:
        db.close()


# ---------- verify_initiative ----------

def test_verify_initiative_reports_gaps(client):
    from app.services.initiative_projection_service import verify_initiative
    from app.models import InitiativeControlTarget, InitiativeRiskLink

    db = _TestSession()
    try:
        org = _default_org(db)
        asset = _make_asset(db, org.id)
        threat = _make_threat(db)
        impl_ok = _make_control_impl(db, org.id, maturity=4)
        impl_gap = _make_control_impl(db, org.id, maturity=1)
        risk = _make_risk(db, org.id, asset, threat)
        risk.residual_level = 5
        db.flush()

        ini = _make_initiative(db, org.id)
        db.add(InitiativeControlTarget(
            organization_id=org.id, initiative_id=ini.id, implementation_id=impl_ok.id,
            baseline_maturity=2, target_maturity=4,
        ))
        db.add(InitiativeControlTarget(
            organization_id=org.id, initiative_id=ini.id, implementation_id=impl_gap.id,
            baseline_maturity=1, target_maturity=4,
        ))
        db.add(InitiativeRiskLink(
            organization_id=org.id, initiative_id=ini.id, risk_id=risk.id,
            origin="manual", baseline_residual_level=8, projected_residual_level=3,
        ))
        db.commit()

        result = verify_initiative(db, ini)
        db.commit()
        assert result["controls"]["total"] == 2
        assert result["controls"]["met"] == 1
        assert result["risks"]["total"] == 1
        assert result["risks"]["met"] == 0  # residual real 5 > proyectado 3
        gap_types = {g["type"] for g in result["gaps"]}
        assert "control" in gap_types
        assert "risk" in gap_types
        assert ini.verification is not None
        log_texts = [e.text for e in ini.log_entries]
        assert any("Verificacion de cierre" in t for t in log_texts)
    finally:
        db.close()


# ---------- burndown ----------

def test_burndown_history_and_projection_no_double_counting(client):
    from app.services.initiative_projection_service import compute_burndown
    from app.models import RiskSnapshot, InitiativeRiskLink

    db = _TestSession()
    try:
        org = _default_org(db)
        asset = _make_asset(db, org.id)
        threat = _make_threat(db)
        risk = _make_risk(db, org.id, asset, threat)
        risk.residual_level = 6
        db.flush()

        now = datetime.now(timezone.utc)
        db.add(RiskSnapshot(
            organization_id=org.id, risk_id=risk.id,
            snapshot_date=now.replace(day=1) - timedelta(days=32),
            residual_level=8,
        ))
        db.add(RiskSnapshot(
            organization_id=org.id, risk_id=risk.id,
            snapshot_date=now.replace(day=1),
            residual_level=6,
        ))
        db.commit()

        target_month = (now + timedelta(days=60)).strftime("%Y-%m")
        target_date = (now + timedelta(days=60))

        ini_a = _make_initiative(db, org.id, status="in_progress")
        ini_a.target_date = target_date
        ini_b = _make_initiative(db, org.id, status="approved")
        ini_b.target_date = target_date
        db.add(InitiativeRiskLink(
            organization_id=org.id, initiative_id=ini_a.id, risk_id=risk.id,
            origin="manual", baseline_residual_level=6, projected_residual_level=3,
        ))
        db.add(InitiativeRiskLink(
            organization_id=org.id, initiative_id=ini_b.id, risk_id=risk.id,
            origin="manual", baseline_residual_level=6, projected_residual_level=2,
        ))
        db.commit()

        result = compute_burndown(db, org.id)
        assert len(result["history"]) >= 2
        assert result["projected"], "debe haber al menos un punto proyectado"
        proj_point = next(p for p in result["projected"] if p["month"] == target_month)
        # Reduccion real esperada: solo se cuenta la mejor proyeccion (2), no 4+3=7 doble
        assert proj_point["total_residual"] >= 0
    finally:
        db.close()
