"""Tests de la extraccion del metodo y de la conformidad con la politica propia.

Las dos garantias que hacen esto util:

- **Nada de lo que el agente lea en tu politica se pierde.** Si la plataforma no
  sabe aplicarlo, queda registrado con su cita y sale como hallazgo. Eso permite
  al cliente saber que hay algo suyo que la herramienta todavia no respeta, en
  vez de descubrirlo en una auditoria.
- **Tu metodo calcula tus cifras; la norma dice si cumples.** Cuando su
  procedimiento es mas laxo que la norma se sigue calculando con el suyo y se
  levanta el hallazgo. Son dos preguntas distintas.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (BCMScenarioAssessment, MethodBinding, MethodFinding,
                        MethodStatement)
from app.services.method import conformance
from app.services.method.bindings import resolve, set_binding
from app.services.method.extraction import _sanitize, has_dependent_data, persist

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)

ORG = 690001


@pytest.fixture()
def db():
    session = _Session()
    yield session
    for model in (MethodFinding, MethodBinding, MethodStatement,
                  BCMScenarioAssessment):
        session.query(model).filter_by(organization_id=ORG).delete(
            synchronize_session=False)
    session.commit()
    session.close()


_COMBINACION = {
    "parameter_key": "bcm.impact.combination",
    "proposed_value": "sum",
    "quote": "RTO + Criterio de Impacto = Impacto total",
    "source_document": "ISP_11.docx", "source_section": "6.3",
    "interpretation": "El RTO se suma al impacto en vez de multiplicarlo.",
    "confidence": 0.95,
}
_NO_MODELABLE = {
    "parameter_key": None,
    "quote": ("El comite de crisis se activa cuando dos sedes de paises "
              "distintos se ven afectadas simultaneamente."),
    "source_document": "ISP_11.docx", "source_section": "7.3",
    "interpretation": "Regla de activacion combinada entre sedes.",
    "confidence": 0.8,
}


# ── Saneado de lo que devuelve el agente ─────────────────────────────────────

def test_una_declaracion_sin_cita_se_descarta():
    """Sin poder senalar el parrafo, un parametro cambiado no es defendible."""
    out = _sanitize([{"parameter_key": "bcm.impact.combination",
                      "proposed_value": "sum", "quote": "  ",
                      "interpretation": "algo"}])
    assert out == []


def test_una_clave_inventada_no_se_descarta_pero_no_se_vincula():
    out = _sanitize([{**_COMBINACION, "parameter_key": "bcm.inventado"}])
    assert len(out) == 1
    assert out[0]["parameter_key"] is None
    # Y queda constancia de lo que el agente habia propuesto
    assert "bcm.inventado" in out[0]["interpretation"]


# ── Persistencia ─────────────────────────────────────────────────────────────

def test_una_declaracion_reconocida_se_aplica_sola(db):
    out = persist(db, ORG, [_COMBINACION])
    assert out["created"] == 1 and out["applied"] == 1

    r = resolve(db, ORG, "bcm.impact.combination")
    assert r.value == "sum"
    assert r.source == "policy"
    assert r.citation["section"] == "6.3"


def test_una_regla_no_modelable_se_guarda_con_su_cita(db):
    """El modo de fallo honesto: no se sabe aplicar, pero se dice."""
    out = persist(db, ORG, [_NO_MODELABLE])
    assert out["unmodelled"] == 1 and out["applied"] == 0

    st = db.query(MethodStatement).filter_by(organization_id=ORG).one()
    assert st.status == "unmodelled"
    assert "comite de crisis" in st.quote
    assert st.source_document == "ISP_11.docx"


def test_no_se_auto_aplica_lo_que_recalcularia_datos_existentes(db):
    """Recalcular en silencio el BIA de un cliente seria una mala sorpresa."""
    db.add(BCMScenarioAssessment(organization_id=ORG, scenario_id=1))
    db.commit()
    assert has_dependent_data(db, ORG, "bcm.impact.combination") is True

    out = persist(db, ORG, [_COMBINACION])
    assert out["applied"] == 0 and out["proposed"] == 1
    # El motor sigue con el defecto hasta que una persona lo aplique
    assert resolve(db, ORG, "bcm.impact.combination").source == "default"
    assert db.query(MethodStatement).filter_by(
        organization_id=ORG).one().status == "proposed"


def test_sin_datos_dependientes_si_se_auto_aplica(db):
    assert has_dependent_data(db, ORG, "bcm.impact.combination") is False
    assert persist(db, ORG, [_COMBINACION])["applied"] == 1


# ── Hallazgos de conformidad ─────────────────────────────────────────────────

def test_hallazgo_cuando_hay_politica_pero_manda_el_defecto(db):
    db.add(BCMScenarioAssessment(organization_id=ORG, scenario_id=1))
    db.commit()
    persist(db, ORG, [_COMBINACION])       # queda propuesta, sin aplicar

    kinds = [f["kind"] for f in conformance.check(db, ORG)]
    assert "default_used_despite_policy" in kinds


def test_hallazgo_cuando_alguien_lo_cambio_a_mano(db):
    persist(db, ORG, [_COMBINACION])
    set_binding(db, ORG, "bcm.impact.combination", "product", source="manual")

    finding = next(f for f in conformance.check(db, ORG)
                   if f["kind"] == "manual_override_diverges_from_policy")
    assert finding["effective_value"] == "product"
    assert finding["policy_value"] == "sum"


def test_hallazgo_por_regla_no_modelable(db):
    persist(db, ORG, [_NO_MODELABLE])
    finding = next(f for f in conformance.check(db, ORG)
                   if f["kind"] == "unmodelled_rule")
    assert "comite de crisis" in finding["summary"]


def test_una_politica_mas_laxa_que_la_norma_no_cambia_el_calculo(db):
    """La linea de diseno: su metodo manda en las cifras, la norma en el veredicto."""
    set_binding(db, ORG, "bcm.test.frequency_months", 36, source="policy")

    finding = next(f for f in conformance.check(db, ORG)
                   if f["kind"] == "policy_below_norm")
    assert finding["normative_ref"].startswith("ISO 22301")
    assert finding["normative_value"] == 12
    # Y el motor sigue calculando con lo que dice el cliente
    assert resolve(db, ORG, "bcm.test.frequency_months").value == 36


def test_una_cadencia_conforme_no_genera_hallazgo(db):
    set_binding(db, ORG, "bcm.test.frequency_months", 6, source="policy")
    kinds = [f["kind"] for f in conformance.check(db, ORG)]
    assert "policy_below_norm" not in kinds


def test_el_defecto_de_la_plataforma_no_se_audita_contra_la_norma(db):
    """El defecto ya cumple; auditarlo seria ruido."""
    assert not [f for f in conformance.check(db, ORG)
                if f["kind"] == "policy_below_norm"]


# ── Persistencia de hallazgos ────────────────────────────────────────────────

def test_refresh_persiste_y_conserva_lo_ya_aceptado(db):
    persist(db, ORG, [_NO_MODELABLE])
    assert conformance.refresh(db, ORG)["findings"] >= 1

    finding = db.query(MethodFinding).filter_by(
        organization_id=ORG, kind="unmodelled_rule").first()
    finding.status = "accepted"
    db.commit()

    out = conformance.refresh(db, ORG)
    assert out["accepted_kept"] >= 1
    # No se duplica el que ya estaba dado por bueno
    assert db.query(MethodFinding).filter_by(
        organization_id=ORG, kind="unmodelled_rule").count() == 1


def test_el_resumen_cuenta_de_donde_sale_cada_parametro(db):
    persist(db, ORG, [_COMBINACION])
    set_binding(db, ORG, "bcm.test.frequency_months", 6, source="manual")

    s = conformance.summary(db, ORG)
    assert s["from_policy"] >= 1
    assert s["manual"] >= 1
    assert s["default"] >= 1
    assert s["parameters_total"] == s["from_policy"] + s["manual"] + s["default"]
    assert s["wired"] > 0
