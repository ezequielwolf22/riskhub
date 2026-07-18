"""Informe de Plan de Tratamiento y Plan Director (PDF)."""
import uuid
from datetime import datetime, timedelta, timezone


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def test_treatment_report_locale_keys_loaded():
    from app.i18n import t as _t
    assert "Tratamiento" in _t("reports.treatment.title", "es")
    assert "Treatment" in _t("reports.treatment.title", "en")
    body = _t("reports.treatment.summary_body", "es", above=3, no_plan=1, overdue=2, projected=10, achieved=4)
    assert "3" in body and "10" in body and "4" in body


def test_treatment_report_pdf_ok_without_data(client, auth_headers):
    resp = client.get("/api/reports/treatment-plan", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"
    assert len(resp.content) > 800


def test_treatment_report_pdf_ok_with_data(client, auth_headers):
    from tests.conftest import _TestSession

    db = _TestSession()
    try:
        from app.models import (
            Asset, AssetType, InitiativeRiskLink, Organization, Risk, RiskStatus,
            StrategicInitiative, StrategicProgram, Threat, ThreatOrigin, TreatmentOption,
        )
        org = db.query(Organization).first()
        asset = Asset(organization_id=org.id, code=f"AST-RPT-{_uid()}", name="Activo informe",
                      asset_type=AssetType.SUPPORT_SOFTWARE)
        db.add(asset)
        db.flush()
        threat = Threat(code=f"THR-RPT-{_uid()}", name="Amenaza informe",
                        origin=ThreatOrigin.DELIBERATE, is_custom=True)
        db.add(threat)
        db.flush()
        risk = Risk(organization_id=org.id, code=f"RSK-RPT-{_uid()}", asset_id=asset.id,
                   threat_id=threat.id, inherent_likelihood=4, inherent_consequence=4,
                   residual_likelihood=4, residual_consequence=4, residual_level=7,
                   status=RiskStatus.ASSESSED)
        db.add(risk)
        db.flush()

        prog = StrategicProgram(organization_id=org.id, code=f"PRG-RPT-{_uid()}", name="Programa informe")
        db.add(prog)
        db.flush()
        ini = StrategicInitiative(organization_id=org.id, code=f"INI-RPT-{_uid()}",
                                  title="Iniciativa informe", program_id=prog.id, status="in_progress")
        db.add(ini)
        db.flush()
        db.add(InitiativeRiskLink(organization_id=org.id, initiative_id=ini.id, risk_id=risk.id,
                                  origin="manual", baseline_residual_level=7, projected_residual_level=3))

        # Snapshots historicos para cubrir la rama de la grafica burndown del PDF
        from app.models import RiskSnapshot
        now = datetime.now(timezone.utc)
        ini.target_date = now + timedelta(days=60)
        db.add(RiskSnapshot(organization_id=org.id, risk_id=risk.id,
                            snapshot_date=now.replace(day=1) - timedelta(days=32),
                            residual_level=8))
        db.add(RiskSnapshot(organization_id=org.id, risk_id=risk.id,
                            snapshot_date=now.replace(day=1), residual_level=7))
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/reports/treatment-plan", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.content[:4] == b"%PDF"
    assert len(resp.content) > 2000  # con tablas y grafica, no un PDF vacio
