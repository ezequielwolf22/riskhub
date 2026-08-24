"""Tests del conector VisioX (Digital Risk Protection).

Se centran en las cuatro cosas que pueden salir mal de verdad y que la revision
del diseno senalo como riesgo:

  1. Reejecutar el sync duplica hallazgos, o peor: no refleja los cambios.
  2. Un fallo de la fuente borra o cierra datos buenos.
  3. La PII acaba en claro en la base de datos o en el listado.
  4. Los datos caen en la organizacion equivocada.

La API de VisioX se sustituye por un doble: estos tests no tocan la red.
"""
import json
from datetime import datetime, timezone

import pytest

from app.models import (
    Asset,
    ExternalFinding,
    ExternalFindingSource,
    Incident,
    IntegrationSyncRun,
    Organization,
)
from app.services import visiox_service, visiox_sync_service


# ---------- utilidades ----------

def _finding(ext_id, severity="MEDIUM", module="surfacex", ftype="asm_tls",
             host="ejemplo.test", sensitive=False, evidence=None):
    return {
        "external_id": ext_id,
        "module": module,
        "finding_type": ftype,
        "title": f"Hallazgo {ext_id}",
        "severity": severity,
        "affected_host": host,
        "iso_control": "A.8.24",
        "external_url": "https://visiox.app/surfacex",
        "sensitive": sensitive,
        "evidence": evidence or {"flag": "tls_expired", "brand": "Marca"},
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def db(setup_test_db):
    from tests.conftest import _TestSession
    s = _TestSession()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def org(db):
    o = Organization(name="OFA Test VisioX", plan="enterprise")
    db.add(o)
    db.commit()
    visiox_sync_service.save_config(db, o.id, {
        "api_key": "vsx_test_secret",
        "enabled": True,
        "create_assets": False,
        "auto_sync": True,
    })
    yield o
    # Limpieza: estos tests crean riesgos, incidentes y activos.
    for model in (ExternalFinding, IntegrationSyncRun, Incident, Asset):
        db.query(model).filter(model.organization_id == o.id).delete(synchronize_session=False)
    db.commit()


def _patch_fetch(monkeypatch, items, complete=True, pages=1):
    monkeypatch.setattr(
        visiox_service, "fetch_findings",
        lambda *a, **k: (items, complete, pages),
    )


# ---------- idempotencia ----------

def test_reejecutar_no_duplica_y_si_actualiza(db, org, monkeypatch):
    """El importador generico descarta duplicados sin actualizarlos. Para datos
    DRP eso deja un dominio ya tumbado abierto para siempre."""
    _patch_fetch(monkeypatch, [_finding("visiox:surfacex:a:tls_expired", "MEDIUM")])
    r1 = visiox_sync_service.sync_organization(db, org.id)
    assert r1["status"] == "ok"
    assert r1["created"] == 1

    # Segunda pasada: el mismo hallazgo, ahora agravado.
    _patch_fetch(monkeypatch, [_finding("visiox:surfacex:a:tls_expired", "CRITICAL")])
    r2 = visiox_sync_service.sync_organization(db, org.id)

    assert r2["created"] == 0, "reejecutar no debe crear filas nuevas"
    assert r2["updated"] == 1

    rows = db.query(ExternalFinding).filter(
        ExternalFinding.organization_id == org.id,
        ExternalFinding.external_id == "visiox:surfacex:a:tls_expired",
    ).all()
    assert len(rows) == 1, "no puede haber dos filas con el mismo external_id"
    assert rows[0].severity == "CRITICAL", "el cambio de severidad debe reflejarse"


def test_lo_que_desaparece_se_cierra_pero_no_se_borra(db, org, monkeypatch):
    _patch_fetch(monkeypatch, [_finding("visiox:a:1"), _finding("visiox:a:2")])
    visiox_sync_service.sync_organization(db, org.id)

    # El segundo desaparece del origen.
    _patch_fetch(monkeypatch, [_finding("visiox:a:1")])
    r = visiox_sync_service.sync_organization(db, org.id)

    assert r["closed"] == 1
    gone = db.query(ExternalFinding).filter_by(
        organization_id=org.id, external_id="visiox:a:2").first()
    assert gone is not None, "cerrar no es borrar: la historia se conserva"
    assert gone.status == "resolved"
    assert gone.resolved_at is not None


def test_lo_que_reaparece_se_reabre(db, org, monkeypatch):
    _patch_fetch(monkeypatch, [_finding("visiox:a:1")])
    visiox_sync_service.sync_organization(db, org.id)
    _patch_fetch(monkeypatch, [])
    visiox_sync_service.sync_organization(db, org.id)

    f = db.query(ExternalFinding).filter_by(
        organization_id=org.id, external_id="visiox:a:1").first()
    assert f.status == "resolved"

    _patch_fetch(monkeypatch, [_finding("visiox:a:1")])
    visiox_sync_service.sync_organization(db, org.id)
    db.refresh(f)
    assert f.status == "open", "si la fuente lo vuelve a ver, no estaba resuelto"
    assert f.resolved_at is None


# ---------- degradacion ----------

def test_snapshot_incompleto_no_cierra_nada(db, org, monkeypatch):
    """La ausencia de un hallazgo en una respuesta truncada NO prueba que se
    haya resuelto. Cerrarlos seria borrar trabajo real por un fallo de red."""
    _patch_fetch(monkeypatch, [_finding("visiox:a:1"), _finding("visiox:a:2")])
    visiox_sync_service.sync_organization(db, org.id)

    _patch_fetch(monkeypatch, [_finding("visiox:a:1")], complete=False)
    r = visiox_sync_service.sync_organization(db, org.id)

    assert r["closed"] == 0
    assert r["complete"] is False
    survivor = db.query(ExternalFinding).filter_by(
        organization_id=org.id, external_id="visiox:a:2").first()
    assert survivor.status == "open", "no se cierra con un snapshot truncado"


def test_fuente_caida_no_toca_lo_ya_guardado(db, org, monkeypatch):
    _patch_fetch(monkeypatch, [_finding("visiox:a:1", "CRITICAL")])
    visiox_sync_service.sync_organization(db, org.id)
    before = db.query(ExternalFinding).filter_by(organization_id=org.id).count()

    def _boom(*a, **k):
        raise visiox_service.VisioXError("connection refused")
    monkeypatch.setattr(visiox_service, "fetch_findings", _boom)

    r = visiox_sync_service.sync_organization(db, org.id)
    assert r["status"] == "error"
    assert "connection refused" in (r["error"] or "")
    assert db.query(ExternalFinding).filter_by(organization_id=org.id).count() == before
    f = db.query(ExternalFinding).filter_by(
        organization_id=org.id, external_id="visiox:a:1").first()
    assert f.status == "open", "un fallo de la fuente no puede cerrar nada"


def test_error_queda_registrado_en_el_run(db, org, monkeypatch):
    def _boom(*a, **k):
        raise visiox_service.VisioXError("HTTP 500")
    monkeypatch.setattr(visiox_service, "fetch_findings", _boom)
    visiox_sync_service.sync_organization(db, org.id)

    run = db.query(IntegrationSyncRun).filter_by(
        organization_id=org.id).order_by(IntegrationSyncRun.id.desc()).first()
    assert run.status == "error"
    assert "HTTP 500" in run.error_message
    assert run.finished_at is not None and run.duration_ms is not None


# ---------- privacidad ----------

def test_la_pii_se_guarda_cifrada_y_nunca_en_claro(db, org, monkeypatch):
    secreto = "Contrasena-Real-123"
    item = _finding(
        "visiox:leakx:cred:abc", "HIGH", module="leakx", ftype="leaked_credential",
        host="portal.ofa.test", sensitive=True,
        evidence={
            "username_plain": "jperez@ofa.test",
            "password_plain": secreto,
            "asset_class": "employees",
            "password_strength": 2,
        },
    )
    _patch_fetch(monkeypatch, [item])
    visiox_sync_service.sync_organization(db, org.id)

    f = db.query(ExternalFinding).filter_by(
        organization_id=org.id, external_id="visiox:leakx:cred:abc").first()

    assert f.is_sensitive is True
    assert f.evidence_encrypted, "la evidencia sensible tiene que persistirse cifrada"
    assert secreto not in f.evidence_encrypted

    # Ni la contrasena ni el usuario pueden aparecer en NINGUN campo en claro.
    for campo in (f.evidence_json or "", f.raw_data or "", f.description or "", f.title or ""):
        assert secreto not in campo
        assert "jperez@ofa.test" not in campo

    # La parte publica conserva lo que explica el hallazgo sin identificar a nadie.
    publica = json.loads(f.evidence_json)
    assert publica.get("asset_class") == "employees"
    assert "password_plain" not in publica
    assert "username_plain" not in publica

    # Y descifrando se recupera intacta.
    recuperada = json.loads(visiox_sync_service.decrypt(f.evidence_encrypted))
    assert recuperada["password_plain"] == secreto


def test_el_listado_no_sirve_la_evidencia_protegida(db, org, monkeypatch):
    from app.routers.external_findings import _finding_out
    _patch_fetch(monkeypatch, [_finding(
        "visiox:leakx:cred:xyz", "HIGH", module="leakx", ftype="leaked_credential",
        sensitive=True, evidence={"password_plain": "NoDebeSalir-999", "asset_class": "vip"},
    )])
    visiox_sync_service.sync_organization(db, org.id)
    f = db.query(ExternalFinding).filter_by(
        organization_id=org.id, external_id="visiox:leakx:cred:xyz").first()

    out = _finding_out(f)
    assert "NoDebeSalir-999" not in json.dumps(out, default=str)
    assert out["has_protected_evidence"] is True, "la UI debe saber que existe, sin verla"
    assert out["is_sensitive"] is True
    assert "evidence_encrypted" not in out


def test_lo_no_sensible_viaja_en_claro(db, org, monkeypatch):
    """Cifrar lo que no hace falta esconderia informacion util sin ganar nada."""
    _patch_fetch(monkeypatch, [_finding("visiox:surfacex:b:no_caa")])
    visiox_sync_service.sync_organization(db, org.id)
    f = db.query(ExternalFinding).filter_by(
        organization_id=org.id, external_id="visiox:surfacex:b:no_caa").first()
    assert f.is_sensitive is False
    assert f.evidence_encrypted is None
    assert json.loads(f.evidence_json)["flag"] == "tls_expired"


# ---------- multi-tenancy ----------

def test_los_hallazgos_caen_en_la_organizacion_correcta(db, org, monkeypatch):
    otra = Organization(name="Otra Org VisioX", plan="enterprise")
    db.add(otra)
    db.commit()
    try:
        _patch_fetch(monkeypatch, [_finding("visiox:aislamiento:1")])
        visiox_sync_service.sync_organization(db, org.id)

        assert db.query(ExternalFinding).filter_by(organization_id=otra.id).count() == 0
        assert db.query(ExternalFinding).filter_by(organization_id=org.id).count() == 1
    finally:
        db.query(ExternalFinding).filter_by(organization_id=otra.id).delete()
        db.query(IntegrationSyncRun).filter_by(organization_id=otra.id).delete()
        db.delete(otra)
        db.commit()


def test_sin_configuracion_falla_limpio(db, monkeypatch):
    huerfana = Organization(name="Sin VisioX", plan="enterprise")
    db.add(huerfana)
    db.commit()
    try:
        r = visiox_sync_service.sync_organization(db, huerfana.id)
        assert r["status"] == "error"
        assert "no esta configurada" in (r["error"] or "")
    finally:
        db.query(IntegrationSyncRun).filter_by(organization_id=huerfana.id).delete()
        db.delete(huerfana)
        db.commit()


def test_orgs_with_visiox_solo_lista_las_configuradas(db, org):
    assert org.id in visiox_sync_service.orgs_with_visiox(db)


# ---------- reglas de negocio ----------

def test_un_solo_incidente_por_lote_no_uno_por_hallazgo(db, org, monkeypatch):
    criticos = [_finding(f"visiox:crit:{i}", "CRITICAL") for i in range(5)]
    _patch_fetch(monkeypatch, criticos)
    r = visiox_sync_service.sync_organization(db, org.id)

    assert r["incidents_created"] == 1, "cinco hallazgos criticos son UN incidente"
    inc = db.query(Incident).filter_by(organization_id=org.id).first()
    assert inc is not None

    # La relacion es por clave ajena, no por un marcador dentro del texto.
    enlazados = db.query(ExternalFinding).filter_by(
        organization_id=org.id, incident_id=inc.id).count()
    assert enlazados == 5


def test_el_incidente_no_se_reabre_en_cada_sync(db, org, monkeypatch):
    criticos = [_finding("visiox:crit:solo", "CRITICAL")]
    _patch_fetch(monkeypatch, criticos)
    visiox_sync_service.sync_organization(db, org.id)
    visiox_sync_service.sync_organization(db, org.id)
    visiox_sync_service.sync_organization(db, org.id)

    assert db.query(Incident).filter_by(organization_id=org.id).count() == 1, \
        "las reglas solo actuan sobre hallazgos NUEVOS"


def test_sin_criticos_no_hay_incidente(db, org, monkeypatch):
    _patch_fetch(monkeypatch, [_finding("visiox:m:1", "MEDIUM"), _finding("visiox:m:2", "LOW")])
    r = visiox_sync_service.sync_organization(db, org.id)
    assert r["incidents_created"] == 0
    assert db.query(Incident).filter_by(organization_id=org.id).count() == 0


def test_tope_de_riesgos_por_sync(db, org, monkeypatch):
    """Un mal dia en la fuente no puede inundar el registro de riesgos."""
    asset = Asset(organization_id=org.id, code="AST-VX01", name="ejemplo.test",
                  asset_type="support_network")
    db.add(asset)
    db.commit()
    try:
        muchos = [_finding(f"visiox:many:{i}", "HIGH") for i in range(60)]
        _patch_fetch(monkeypatch, muchos)
        r = visiox_sync_service.sync_organization(db, org.id)
        assert r["risks_created"] <= visiox_sync_service.MAX_RISKS_PER_SYNC
        # Los que no generan riesgo NO se pierden: siguen siendo hallazgos.
        assert db.query(ExternalFinding).filter_by(organization_id=org.id).count() == 60
    finally:
        db.query(Asset).filter_by(organization_id=org.id).delete()
        db.commit()


def test_sin_activo_casado_no_se_genera_riesgo(db, org, monkeypatch):
    """Un riesgo ISO 27005 es (activo, amenaza, vulnerabilidad). Sin activo no
    hay riesgo que valorar: queda como hallazgo, visible y sin perder."""
    _patch_fetch(monkeypatch, [_finding("visiox:sinactivo:1", "CRITICAL", host="desconocido.test")])
    r = visiox_sync_service.sync_organization(db, org.id)
    assert r["risks_created"] == 0
    f = db.query(ExternalFinding).filter_by(
        organization_id=org.id, external_id="visiox:sinactivo:1").first()
    assert f is not None and f.asset_id is None


def test_amenazas_por_familia_no_por_hallazgo(db, org):
    """Con un threat_code por hallazgo, 8000 hallazgos meterian 8000 entradas
    basura en el catalogo y la dedupe por (activo, amenaza) dejaria de servir."""
    codes = set(visiox_sync_service.THREAT_CODES.values())
    assert len(codes) <= 8
    assert visiox_sync_service.THREAT_CODES["asm_tls"] == "DRP-ASM-TLS"
    assert visiox_sync_service.THREAT_CODES["leaked_credential"] == "DRP-LEAKX-CREDS"


# ---------- cliente HTTP ----------

def test_cursor_repetido_corta_y_marca_incompleto(monkeypatch):
    """Un servidor que no avanza el cursor colgaria el sync. Y sobre todo: el
    resultado parcial no puede darse por completo."""
    llamadas = {"n": 0}

    def _fake_request(base, key, path, params=None):
        llamadas["n"] += 1
        return {"data": [{"external_id": f"x{llamadas['n']}"}],
                "next_cursor": "SIEMPRE-EL-MISMO", "complete": False}

    monkeypatch.setattr(visiox_service, "_request", _fake_request)
    items, complete, pages = visiox_service.fetch_findings("https://x", "k")
    assert complete is False
    assert pages < visiox_service.MAX_PAGES, "tiene que cortar por cursor repetido"


def test_tope_de_paginas_marca_incompleto(monkeypatch):
    contador = {"n": 0}

    def _fake_request(base, key, path, params=None):
        contador["n"] += 1
        return {"data": [{"external_id": f"x{contador['n']}"}],
                "next_cursor": f"c{contador['n']}", "complete": False}

    monkeypatch.setattr(visiox_service, "_request", _fake_request)
    monkeypatch.setattr(visiox_service.time, "sleep", lambda *_: None)
    items, complete, pages = visiox_service.fetch_findings("https://x", "k")
    assert pages == visiox_service.MAX_PAGES
    assert complete is False, "un recorrido truncado nunca es completo"


def test_la_key_va_en_cabecera_nunca_en_la_url(monkeypatch):
    """El logger de VisioX escribe la query completa al journal de systemd."""
    capturado = {}

    class _Resp:
        def read(self):
            return b'{"client":{"slug":"onceforall"}}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        capturado["url"] = req.full_url
        capturado["headers"] = dict(req.headers)
        return _Resp()

    monkeypatch.setattr(visiox_service.urllib.request, "urlopen", _fake_urlopen)
    visiox_service.whoami("https://visiox.app", "vsx_secreto_abc")

    assert "vsx_secreto_abc" not in capturado["url"]
    valores = " ".join(str(v) for v in capturado["headers"].values())
    assert "vsx_secreto_abc" in valores


def test_401_da_mensaje_accionable(monkeypatch):
    import urllib.error

    def _fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(visiox_service.urllib.request, "urlopen", _fake_urlopen)
    with pytest.raises(visiox_service.VisioXError) as exc:
        visiox_service.whoami("https://visiox.app", "mala")
    assert exc.value.status == 401
    assert "revocada" in str(exc.value) or "no es valida" in str(exc.value)
