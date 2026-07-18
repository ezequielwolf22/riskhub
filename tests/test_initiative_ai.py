"""IA del Plan Director: import de plan, borrador de iniciativa, plan de tratamiento.

Toda llamada a Claude se mockea (structured_message) — nunca se llama a la API real.
"""
import io
import uuid
from unittest.mock import patch

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _default_org(db):
    from app.models import Organization
    return db.query(Organization).first()


def _ensure_api_key(org_id):
    """El servicio requiere una API key configurada (org o global fallback).
    En test forzamos settings.anthropic_api_key para que _resolve_api_key no falle."""
    from app.config import settings
    settings.anthropic_api_key = "sk-test-fake-key-not-real"


def _make_control(db, code, name="Control de prueba"):
    from app.models import Control
    ctrl = db.query(Control).filter(Control.code == code).first()
    if ctrl:
        return ctrl
    ctrl = Control(code=code, name=name, is_custom=True)
    db.add(ctrl)
    db.flush()
    return ctrl


def _make_impl(db, org_id, control_code, maturity=1):
    from app.models import ControlImplementation, ControlStatus
    ctrl = _make_control(db, control_code)
    impl = ControlImplementation(
        organization_id=org_id, control_id=ctrl.id, name=f"Impl {control_code}",
        status=ControlStatus.PARTIAL, maturity=maturity,
    )
    db.add(impl)
    db.flush()
    return impl


def _make_risk(db, org_id, threat_code=None):
    from app.models import Asset, AssetType, Risk, RiskStatus, Threat, ThreatOrigin
    asset = Asset(organization_id=org_id, code=f"AST-AI-{_uid()}", name="Activo IA",
                  asset_type=AssetType.SUPPORT_SOFTWARE)
    db.add(asset)
    db.flush()
    threat = Threat(code=threat_code or f"THR-AI-{_uid()}", name="Amenaza IA",
                    origin=ThreatOrigin.DELIBERATE, is_custom=True)
    db.add(threat)
    db.flush()
    risk = Risk(
        organization_id=org_id, code=f"RSK-AI-{_uid()}", asset_id=asset.id, threat_id=threat.id,
        inherent_likelihood=4, inherent_consequence=4,
        residual_likelihood=4, residual_consequence=4, residual_level=7,
        status=RiskStatus.ASSESSED,
    )
    db.add(risk)
    db.flush()
    return risk


# ---------- parse_plan_document: post-proceso determinista ----------

def test_parse_plan_document_discards_unknown_control_and_bad_dates(client):
    from app.services import initiative_ai_service as svc

    db = _TestSession()
    try:
        org = _default_org(db)
        _ensure_api_key(org.id)
        impl = _make_impl(db, org.id, "8.7")
        db.commit()

        fake_response = {
            "programs": [{
                "name": "Programa Test",
                "area": "GRC",
                "initiatives": [{
                    "title": "Iniciativa con control valido e invalido",
                    "priority": "high",
                    "start_date": "not-a-date",
                    "target_date": "2026-12-31",
                    "control_targets": [
                        {"control_code": "8.7", "target_maturity": 4},
                        {"control_code": "99.99-INEXISTENTE", "target_maturity": 3},
                    ],
                    "objectives": [{"definition": "OKR de prueba", "target_date": "2026-06-30"}],
                }],
            }],
        }
        with patch.object(svc, "structured_message", return_value=(fake_response, object())):
            result = svc.parse_plan_document(db, org.id, "Texto de un plan director de prueba " * 20, "es")

        assert len(result["programs"]) == 1
        ini = result["programs"][0]["initiatives"][0]
        assert ini["start_date"] is None  # fecha invalida descartada
        assert ini["target_date"] == "2026-12-31"
        assert len(ini["control_targets"]) == 1
        assert ini["control_targets"][0]["implementation_id"] == impl.id
        assert "99.99-INEXISTENTE" in result["skipped_controls"]
    finally:
        db.close()


# ---------- Endpoints /import y /import/confirm ----------

def test_import_preview_does_not_persist(client, auth_headers):
    from app.services import initiative_ai_service as svc
    db = _TestSession()
    try:
        org = _default_org(db)
        _ensure_api_key(org.id)
        _make_impl(db, org.id, "5.1")
        db.commit()
    finally:
        db.close()

    fake_response = {
        "programs": [{
            "name": "Programa Import",
            "area": None,
            "initiatives": [{
                "title": "Iniciativa importada", "control_targets": [{"control_code": "5.1", "target_maturity": 3}],
                "objectives": [],
            }],
        }],
    }
    long_text = ("Este es un plan director de prueba con suficiente contenido textual. " * 10)
    file_bytes = long_text.encode("utf-8")

    with patch.object(svc, "structured_message", return_value=(fake_response, object())):
        resp = client.post(
            "/api/initiatives/import",
            files={"file": ("plan.txt", io.BytesIO(file_bytes), "text/plain")},
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert len(preview["programs"]) == 1
    assert preview["programs"][0]["initiatives"][0]["title"] == "Iniciativa importada"

    # Nada persistido todavia
    listed = client.get("/api/initiatives/", headers=auth_headers).json()
    assert not any(i["title"] == "Iniciativa importada" for i in listed)


def test_import_rejects_empty_file(client, auth_headers):
    resp = client.post(
        "/api/initiatives/import",
        files={"file": ("empty.txt", io.BytesIO(b"short"), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_import_confirm_creates_hierarchy_and_projects(client, auth_headers):
    db = _TestSession()
    try:
        org = _default_org(db)
        impl = _make_impl(db, org.id, f"5.{_uid()[:4]}")
        db.commit()
        impl_id = impl.id
    finally:
        db.close()

    payload = {
        "programs": [{
            "name": f"Programa Confirm {_uid()}",
            "area": "GRC",
            "initiatives": [{
                "title": "Iniciativa confirmada",
                "control_targets": [{"implementation_id": impl_id, "target_maturity": 4}],
                "objectives": [{"definition": "OKR confirmado"}],
            }],
        }],
    }
    resp = client.post("/api/initiatives/import/confirm", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"]["programs"] == 1
    assert body["created"]["initiatives"] == 1
    assert body["created"]["objectives"] == 1

    listed = client.get("/api/initiatives/", headers=auth_headers).json()
    created = next(i for i in listed if i["title"] == "Iniciativa confirmada")
    assert created["source"] == "import"
    assert created["ai_generated"] is True

    detail = client.get(f"/api/initiatives/{created['id']}", headers=auth_headers).json()
    assert len(detail["control_targets"]) == 1
    assert detail["control_targets"][0]["target_maturity"] == 4


def test_import_confirm_reuses_existing_program_by_name(client, auth_headers):
    prog_name = f"Programa Reuso {_uid()}"
    client.post("/api/initiatives/programs", json={"name": prog_name}, headers=auth_headers)

    payload = {"programs": [{"name": prog_name, "initiatives": [{"title": "Ini en programa existente"}]}]}
    resp = client.post("/api/initiatives/import/confirm", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["created"]["programs"] == 0  # reutilizado, no duplicado

    programs = client.get("/api/initiatives/programs", headers=auth_headers).json()
    matching = [p for p in programs if p["name"] == prog_name]
    assert len(matching) == 1


# ---------- draft-for-risk ----------

def test_draft_for_risk_filters_invalid_candidate_codes(client, auth_headers):
    from app.services import initiative_ai_service as svc
    db = _TestSession()
    try:
        org = _default_org(db)
        _ensure_api_key(org.id)
        risk = _make_risk(db, org.id)
        db.commit()
        risk_id = risk.id
    finally:
        db.close()

    fake_response = {
        "title": "Borrador propuesto", "description": "desc",
        "priority": "high", "expected_risk_reduction": "reduce el riesgo",
        "control_targets": [{"control_code": "CODIGO-NO-CANDIDATO", "target_maturity": 3, "rationale": "x"}],
        "rationale": "Justificacion del borrador",
    }
    with patch.object(svc, "structured_message", return_value=(fake_response, object())):
        resp = client.post("/api/initiatives/draft-for-risk", json={"risk_ids": [risk_id]}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    draft = resp.json()
    assert draft["title"] == "Borrador propuesto"
    # El codigo no es candidato real de la amenaza -> descartado
    assert draft["control_targets"] == []
    assert "CODIGO-NO-CANDIDATO" in draft["skipped_controls"]
    assert draft["risk_ids"] == [risk_id]


def test_draft_for_risk_requires_valid_risks(client, auth_headers):
    resp = client.post("/api/initiatives/draft-for-risk", json={"risk_ids": [999999]}, headers=auth_headers)
    assert resp.status_code == 422


def test_draft_confirm_creates_ai_draft_initiative_and_signal(client, auth_headers):
    db = _TestSession()
    try:
        org = _default_org(db)
        risk = _make_risk(db, org.id)
        impl = _make_impl(db, org.id, f"9.{_uid()[:4]}", maturity=1)
        db.commit()
        risk_id, impl_id = risk.id, impl.id
    finally:
        db.close()

    resp = client.post("/api/initiatives/draft-for-risk/confirm", json={
        "title": "Iniciativa desde borrador IA",
        "priority": "high",
        "rationale": "Justificacion del agente",
        "control_targets": [
            {"implementation_id": impl_id, "target_maturity": 4},
            {"implementation_id": impl_id, "target_maturity": 5},  # duplicado: dedupe
        ],
        "risk_ids": [risk_id],
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created["source"] == "ai_draft"
    assert created["ai_generated"] is True

    detail = client.get(f"/api/initiatives/{created['id']}", headers=auth_headers).json()
    assert len(detail["control_targets"]) == 1          # dedupe aplicado
    link = next(rl for rl in detail["risk_links"] if rl["risk_id"] == risk_id)
    assert link["origin"] == "ai_draft"
    assert link["projected_residual_level"] is not None  # proyeccion ejecutada

    db = _TestSession()
    try:
        from app.models import AiDecisionSignal
        sig = db.query(AiDecisionSignal).filter(
            AiDecisionSignal.signal_type == "initiative_draft_accepted",
            AiDecisionSignal.entity_ref == created["code"],
        ).first()
        assert sig is not None
    finally:
        db.close()


def test_draft_discard_records_rejection_signal(client, auth_headers):
    marker = f"Borrador rechazado {_uid()}"
    resp = client.post("/api/initiatives/draft-for-risk/discard", json={
        "risk_ids": [1], "title": marker,
    }, headers=auth_headers)
    assert resp.status_code == 204

    db = _TestSession()
    try:
        from app.models import AiDecisionSignal
        sig = db.query(AiDecisionSignal).filter(
            AiDecisionSignal.signal_type == "initiative_draft_rejected",
        ).order_by(AiDecisionSignal.id.desc()).first()
        assert sig is not None
        assert sig.context.get("title") == marker
    finally:
        db.close()


def test_import_rejects_non_file_field(client, auth_headers):
    """El campo 'file' enviado como texto no debe provocar un 500."""
    resp = client.post("/api/initiatives/import", data={"file": "no soy un fichero"},
                       headers=auth_headers)
    assert resp.status_code == 400


# ---------- ai-treatment-plan ----------

def test_ai_treatment_plan_returns_draft_without_persisting(client, auth_headers):
    from app.services import initiative_ai_service as svc
    db = _TestSession()
    try:
        org = _default_org(db)
        _ensure_api_key(org.id)
        risk = _make_risk(db, org.id)
        db.commit()
        risk_id = risk.id
    finally:
        db.close()

    fake_response = {
        "treatment_option": "modification",
        "plan": "Plan de tratamiento de prueba con varias lineas de accion.",
        "tasks": [{"title": "Tarea propuesta 1", "priority": "high", "weeks_offset": 2}],
        "rationale": "Justificacion IA",
    }
    with patch.object(svc, "structured_message", return_value=(fake_response, object())):
        resp = client.post(f"/api/risks/{risk_id}/ai-treatment-plan", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    draft = resp.json()
    assert draft["treatment_option"] == "modification"
    assert len(draft["tasks"]) == 1

    # No debe haber persistido nada en el riesgo
    risk_after = client.get(f"/api/risks/{risk_id}", headers=auth_headers).json()
    assert risk_after["treatment_option"] is None
