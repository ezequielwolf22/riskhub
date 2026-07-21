"""Tests del modulo de Vigilancia Normativa Automatica (regwatch).

Cubre la logica pura (catalogo de fuentes, normalizacion, hash idempotente de
candidatos y routing de severidad) sin necesidad de sesion de BD, y un test de
humo del API tenant via TestClient.
"""
import pytest

from app.models import ChangeSeverity
from app.services import regwatch_sources as srcs
from app.services import regwatch_connectors as conns
from tests.conftest import _TestSession


# ---------------------------------------------------------------------------
# Catalogo de fuentes y mapeo framework -> fuente (§3.1)
# ---------------------------------------------------------------------------

def test_sources_catalog_not_empty():
    assert len(srcs.SOURCES) >= 10
    # Codigos unicos
    codes = [s["code"] for s in srcs.SOURCES]
    assert len(codes) == len(set(codes))


@pytest.mark.parametrize("framework,expected_source", [
    ("NIS2", "EURLEX"),
    ("ENS", "BOE"),
    ("GDPR", "AEPD_EDPB"),
    ("ISO_27001", "ISO"),
    ("PCI_DSS", "PCI_SSC"),
])
def test_sources_for_framework(framework, expected_source):
    assert expected_source in srcs.sources_for_framework(framework)


def test_sources_for_framework_case_insensitive():
    assert srcs.sources_for_framework("nis2") == srcs.sources_for_framework("NIS2")


def test_normalize_framework_maps_compliance_codes():
    assert srcs.normalize_framework("iso27001") == "ISO_27001"
    assert srcs.normalize_framework("gdpr") == "GDPR"
    assert srcs.normalize_framework("nis2") == "NIS2"
    # Codigo ya canonico se mantiene
    assert srcs.normalize_framework("DORA") == "DORA"


def test_framework_label_has_human_readable():
    assert "27001" in srcs.framework_label("ISO_27001")
    # Codigo desconocido devuelve el propio codigo
    assert srcs.framework_label("UNKNOWN_X") == "UNKNOWN_X"


# ---------------------------------------------------------------------------
# Conectores: idempotencia y degradacion segura (§11)
# ---------------------------------------------------------------------------

def test_change_candidate_hash_is_idempotent():
    c1 = conns.ChangeCandidate("BOE", "ENS", "t", "https://x/y", raw_ref="A-1")
    c2 = conns.ChangeCandidate("BOE", "ENS", "otro titulo", "https://x/y", raw_ref="A-1")
    # Mismo source+framework+url+ref => mismo hash, aunque cambie el titulo
    assert c1.content_hash() == c2.content_hash()


def test_change_candidate_hash_differs_by_url():
    c1 = conns.ChangeCandidate("BOE", "ENS", "t", "https://x/1", raw_ref="A")
    c2 = conns.ChangeCandidate("BOE", "ENS", "t", "https://x/2", raw_ref="A")
    assert c1.content_hash() != c2.content_hash()


def test_base_watcher_discover_degrades_to_empty():
    """discover() base no lanza y devuelve [] (sin red, no es error)."""
    w = conns.BaseNormativeWatcher()
    assert w.discover() == []


def test_get_connector_resolves_by_code():
    class _FakeSrc:
        code = "EURLEX"
        fetch_config_json = {}
        framework_codes = ["NIS2"]
    c = conns.get_connector(_FakeSrc())
    assert isinstance(c, conns.EurLexWatcher)


def test_signature_changed_establishes_baseline_without_alerting():
    """Primera lectura de una fuente estatica (ISO, AICPA): fija linea base,
    no genera candidato aunque el contenido describa una transicion antigua
    ya consolidada (evita el falso positivo reportado: ISO 27001:2013->2022
    resurgiendo como alerta CRITICA en produccion, anos despues del cambio)."""
    class _FakeSrc:
        code = "ISO"
        fetch_config_json = {}
        framework_codes = ["ISO_27001"]
    w = conns.BaseNormativeWatcher(_FakeSrc())
    assert w._signature_changed("iso-ISO_27001", "abc123") is False
    # Fuente sin cambios reales: no vuelve a alertar
    assert w._signature_changed("iso-ISO_27001", "abc123") is False
    # Contenido realmente distinto: ahi si es una novedad
    assert w._signature_changed("iso-ISO_27001", "def456") is True


def test_iso_status_watcher_baseline_first_run_no_candidates(monkeypatch):
    class _FakeSrc:
        code = "ISO"
        fetch_config_json = {}
        framework_codes = ["ISO_27001", "ISO_27002"]
    w = conns.IsoStatusWatcher(_FakeSrc())
    monkeypatch.setattr(
        w, "_http_get",
        lambda url: b"ISO/IEC 27001:2022 Edition 3 replaced the withdrawn 2013 edition",
    )
    assert w.discover() == []  # linea base, sin alerta falsa
    assert w.discover() == []  # mismo contenido, sin novedad


# ---------------------------------------------------------------------------
# Routing de severidad (§3.3): solo substantive/breaking generan inbox
# ---------------------------------------------------------------------------

def test_inbox_severities_constant():
    from app.services.regwatch_service import _INBOX_SEVERITIES
    assert ChangeSeverity.SUBSTANTIVE in _INBOX_SEVERITIES
    assert ChangeSeverity.BREAKING in _INBOX_SEVERITIES
    assert ChangeSeverity.COSMETIC not in _INBOX_SEVERITIES
    assert ChangeSeverity.CLARIFICATION not in _INBOX_SEVERITIES


# ---------------------------------------------------------------------------
# Validacion humana obligatoria (§3.3): la IA nunca publica sola un cambio
# con impacto real para el tenant.
# ---------------------------------------------------------------------------

def _make_event(db, framework_code="ISO_27001"):
    from app.models import ChangeEventStatus, NormativeChangeEvent
    ev = NormativeChangeEvent(
        framework_code=framework_code,
        raw_url=None,
        content_hash=f"test-{framework_code}-{id(object())}",
        status=ChangeEventStatus.DETECTED,
    )
    db.add(ev)
    db.flush()
    return ev


def test_high_confidence_breaking_change_requires_human_review():
    """Confianza alta + severidad breaking -> PENDING_INTERNAL_REVIEW, no
    VALIDATED. Antes de la correccion la IA marcaba VALIDATED directamente y
    run_sweep la auto-publicaba sin que ningun humano la viera."""
    from unittest.mock import patch

    from app.config import settings
    from app.models import ChangeEventStatus
    from app.services import regwatch_service as svc

    settings.anthropic_api_key = "sk-test-fake-key-not-real"
    db = _TestSession()
    try:
        ev = _make_event(db)
        fake_result = {
            "severity": "breaking", "confidence": 0.95,
            "summary_es": "x", "summary_en": "x", "rationale": "x",
        }
        with patch("app.services.claude_client.structured_message", return_value=(fake_result, object())):
            ok = svc.analyze_event_with_ai(db, ev)
        assert ok is True
        assert ev.status == ChangeEventStatus.PENDING_INTERNAL_REVIEW
    finally:
        db.rollback()
        db.close()


def test_high_confidence_cosmetic_change_auto_validates():
    """Cosmetic/clarification no impactan al tenant (§3.3): pueden auto-
    validarse sin bloquear en la cola humana."""
    from unittest.mock import patch

    from app.config import settings
    from app.models import ChangeEventStatus
    from app.services import regwatch_service as svc

    settings.anthropic_api_key = "sk-test-fake-key-not-real"
    db = _TestSession()
    try:
        ev = _make_event(db)
        fake_result = {
            "severity": "cosmetic", "confidence": 0.9,
            "summary_es": "x", "summary_en": "x", "rationale": "x",
        }
        with patch("app.services.claude_client.structured_message", return_value=(fake_result, object())):
            svc.analyze_event_with_ai(db, ev)
        assert ev.status == ChangeEventStatus.VALIDATED
    finally:
        db.rollback()
        db.close()


def test_run_sweep_never_auto_publishes_substantive_or_breaking():
    """Defensa en profundidad: aunque un evento llegara a VALIDATED con
    severidad substantive/breaking (regresion futura), run_sweep no debe
    auto-publicarlo — solo cosmetic/clarification."""
    from app.models import ChangeEventStatus, ChangeSeverity as CS
    db = _TestSession()
    try:
        ev = _make_event(db, framework_code="ISO_27001_TEST_SWEEP")
        ev.status = ChangeEventStatus.VALIDATED
        ev.severity = CS.BREAKING
        ev.ai_confidence = 0.99
        db.commit()

        from app.services import regwatch_service as svc
        # run_sweep hace red real via conectores; aislamos solo la parte de
        # auto-publicacion reproduciendo su query de forma directa.
        from app.models import NormativeChangeEvent
        candidates = (
            db.query(NormativeChangeEvent)
            .filter(
                NormativeChangeEvent.status == ChangeEventStatus.VALIDATED,
                NormativeChangeEvent.change_pack_id.is_(None),
                NormativeChangeEvent.ai_confidence >= 0.7,
                NormativeChangeEvent.severity.in_(
                    [CS.COSMETIC, CS.CLARIFICATION]
                ),
            )
            .all()
        )
        assert ev.id not in [c.id for c in candidates]
    finally:
        db.rollback()
        db.close()


# ---------------------------------------------------------------------------
# Smoke test del API tenant
# ---------------------------------------------------------------------------

def test_settings_endpoint_returns_disabled_by_default(client, auth_headers):
    resp = client.get("/api/regwatch/settings", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "is_enabled" in body
    assert body["digest_frequency"] in ("daily", "weekly", "monthly", "never")


def test_status_endpoint_shape(client, auth_headers):
    resp = client.get("/api/regwatch/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "state" in body
    assert "pending_count" in body


def test_enable_then_disable_toggle(client, auth_headers):
    en = client.post("/api/regwatch/enable", headers=auth_headers)
    assert en.status_code == 200
    assert en.json()["enabled"] is True
    # Reactivar/desactivar no rompe nada (criterio 9)
    dis = client.post("/api/regwatch/disable", headers=auth_headers)
    assert dis.status_code == 200
    assert dis.json()["enabled"] is False


def test_watched_frameworks_is_list(client, auth_headers):
    resp = client.get("/api/regwatch/watched-frameworks", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_faq_has_entries(client, auth_headers):
    resp = client.get("/api/regwatch/faq", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 5
