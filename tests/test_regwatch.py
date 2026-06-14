"""Tests del modulo de Vigilancia Normativa Automatica (regwatch).

Cubre la logica pura (catalogo de fuentes, normalizacion, hash idempotente de
candidatos y routing de severidad) sin necesidad de sesion de BD, y un test de
humo del API tenant via TestClient.
"""
import pytest

from app.models import ChangeSeverity
from app.services import regwatch_sources as srcs
from app.services import regwatch_connectors as conns


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
    assert "state" in body and "headline" in body
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
