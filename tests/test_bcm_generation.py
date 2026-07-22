"""Tests de la generacion sin documentacion (IA mockeada).

El caso del cliente que llega sin nada. Lo que se fija aqui:

- lo generado pasa por el mismo materializador que la ingesta, asi que hereda
  deshacer, revertir y forzar;
- nace como borrador con confianza baja y marcado para revision, nunca como
  dato firme;
- el cuestionario pregunta solo lo que no se puede deducir de lo ya cargado;
- el "porque" de cada propuesta sobrevive hasta el resumen del lote, para que
  la revision no sea a ciegas.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (Asset, BCMLocation, BCMScenario, BCPPlan, BusinessProcess,
                        IngestBatch, IngestRecordTrace, Supplier)
from app.services.ingest import generation

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)

ORG = 888001


@pytest.fixture()
def db():
    session = _Session()
    yield session
    for model in (IngestRecordTrace, BCPPlan, BCMScenario, BusinessProcess,
                  Supplier, Asset, BCMLocation, IngestBatch):
        session.query(model).filter_by(organization_id=ORG).delete(
            synchronize_session=False)
    session.commit()
    session.close()


# ── Contexto ─────────────────────────────────────────────────────────────────

def test_el_contexto_recoge_lo_que_ya_hay(db):
    db.add_all([
        BCMLocation(organization_id=ORG, name="Madrid", site_type="office",
                    is_active=True),
        Asset(organization_id=ORG, code="AST-9001", name="Plataforma CAE", asset_type="support_software", value_availability=5),
        Asset(organization_id=ORG, code="AST-9002", name="Impresora", asset_type="support_software", value_availability=1),
        Supplier(organization_id=ORG, code="SUP-9001", name="AWS", is_critical=True),
    ])
    db.commit()

    ctx = generation.gather_context(db, ORG)
    assert [loc["name"] for loc in ctx["locations"]] == ["Madrid"]
    # Solo los activos criticos alimentan la propuesta
    assert [a["name"] for a in ctx["assets"]] == ["Plataforma CAE"]
    assert ctx["suppliers"][0]["name"] == "AWS"


def test_el_contexto_no_falla_con_la_organizacion_vacia(db):
    ctx = generation.gather_context(db, ORG)
    assert ctx["locations"] == [] and ctx["assets"] == []
    assert ctx["profile"] is None


# ── Cuestionario adaptativo ──────────────────────────────────────────────────

def test_sin_datos_pregunta_lo_esencial(db):
    keys = {q["key"] for q in generation.pending_questions(db, ORG)}
    assert {"locations", "scenarios", "processes", "assets"} <= keys


def test_no_pregunta_lo_que_puede_deducir(db):
    """Con sedes y activos cargados, esas preguntas desaparecen."""
    db.add_all([
        BCMLocation(organization_id=ORG, name="Madrid", site_type="office",
                    is_active=True),
        Asset(organization_id=ORG, code="AST-9101", name="ERP", asset_type="support_software", value_availability=5),
        BCMScenario(organization_id=ORG, code="ALT.01", name="Huelga",
                    family="personnel", is_active=True),
        BusinessProcess(organization_id=ORG, name="Facturacion"),
    ])
    db.commit()

    keys = {q["key"] for q in generation.pending_questions(db, ORG)}
    assert keys == set()


def test_pregunta_por_el_tipo_de_sede_solo_si_falta(db):
    db.add_all([
        BCMLocation(organization_id=ORG, name="Madrid", site_type="office",
                    is_active=True),
        BCMLocation(organization_id=ORG, name="Lisboa", is_active=True),
        Asset(organization_id=ORG, code="AST-9102", name="ERP", asset_type="support_software", value_availability=5),
        BCMScenario(organization_id=ORG, code="A", name="X", family="personnel",
                    is_active=True),
        BusinessProcess(organization_id=ORG, name="P"),
    ])
    db.commit()

    questions = {q["key"]: q for q in generation.pending_questions(db, ORG)}
    assert "site_types" in questions
    assert questions["site_types"]["items"] == ["Lisboa"]
    # La pregunta explica por que se hace y que desbloquea
    assert questions["site_types"]["why"]
    assert questions["site_types"]["unlocks"]


# ── Generacion ───────────────────────────────────────────────────────────────

_SCENARIOS = {
    "rationale": "Hay tres proveedores cloud criticos y ningun escenario de terceros.",
    "scenarios": [
        {"name": "Caida del proveedor cloud principal", "family": "third_party",
         "why": "AWS es critico y no hay alternativa declarada.", "confidence": 0.8},
        {"name": "Indisponibilidad de personal clave", "family": "personnel",
         "why": "Un solo responsable para la plataforma.", "confidence": 0.5},
    ],
}


def test_lo_generado_se_materializa_en_un_lote_reversible(db):
    with patch.object(generation, "_generate", return_value=_SCENARIOS):
        out = generation.generate(db, ORG, "scenarios", lang="es")

    assert out["status"] == "completed"
    assert out["created"]["bcm_scenario"] == 2
    scenarios = db.query(BCMScenario).filter_by(organization_id=ORG).all()
    assert {s.family for s in scenarios} == {"third_party", "personnel"}
    # Origen trazable y codigo asignado por el motor
    assert all(s.source == "imported" and s.code for s in scenarios)

    from app.services.ingest.batch import undo_batch
    bat = db.get(IngestBatch, out["batch_id"])
    assert undo_batch(db, bat)["reverted"] == 2
    assert db.query(BCMScenario).filter_by(organization_id=ORG).count() == 0


def test_lo_generado_nace_como_borrador_para_revisar(db):
    with patch.object(generation, "_generate", return_value=_SCENARIOS):
        out = generation.generate(db, ORG, "scenarios", lang="es")
    # Confianza 0.5 esta por debajo del umbral de revision
    assert out["needs_review"] >= 1
    trazas = db.query(IngestRecordTrace).filter_by(
        batch_id=out["batch_id"], needs_review=True).all()
    assert len(trazas) >= 1


def test_el_porque_de_cada_propuesta_llega_al_resumen(db):
    """Un BIA propuesto sin justificacion no vale nada en una auditoria."""
    with patch.object(generation, "_generate", return_value=_SCENARIOS):
        out = generation.generate(db, ORG, "scenarios", lang="es")
    assert out["rationale"]
    porques = {p["name"]: p["why"] for p in out["proposals"]}
    assert porques["Caida del proveedor cloud principal"].startswith("AWS es critico")


def test_el_porque_no_se_escribe_como_campo_del_modelo(db):
    with patch.object(generation, "_generate", return_value=_SCENARIOS):
        generation.generate(db, ORG, "scenarios", lang="es")
    sc = db.query(BCMScenario).filter_by(
        organization_id=ORG, family="third_party").one()
    assert not hasattr(sc, "why")
    assert sc.description is None


def test_generar_un_bia_crea_procesos_con_sus_objetivos(db):
    parsed = {
        "rationale": "Derivado de los activos criticos.",
        "processes": [
            {"name": "Coordinacion de actividades", "criticality": "critical",
             "rto_hours": 4, "rpo_hours": 1, "why": "Sostiene el producto.",
             "confidence": 0.8},
        ],
    }
    with patch.object(generation, "_generate", return_value=parsed):
        out = generation.generate(db, ORG, "bia", lang="es")
    assert out["created"]["business_process"] == 1
    p = db.query(BusinessProcess).filter_by(organization_id=ORG).one()
    assert p.criticality == "critical" and p.rto_hours == 4


def test_generar_un_plan_no_lo_deja_aprobado(db):
    """Un borrador generado no puede nacer con el sello de aprobado."""
    parsed = {
        "rationale": "No hay DRP para la infraestructura cloud.",
        "name": "DRP infraestructura cloud", "plan_type": "drp",
        "scope": "Servicios en AWS",
        "sections": [{"title": "Objeto", "content": "Recuperar la infraestructura."}],
        "confidence": 0.7,
    }
    with patch.object(generation, "_generate", return_value=parsed):
        out = generation.generate(db, ORG, "plan", lang="es")
    assert out["created"]["bcp_plan"] == 1
    plan = db.query(BCPPlan).filter_by(organization_id=ORG).one()
    assert plan.status == "draft"
    assert plan.plan_type == "drp"
    assert plan.sections


def test_objetivo_desconocido_se_rechaza(db):
    with pytest.raises(ValueError):
        generation.generate(db, ORG, "loqueSea", lang="es")


def test_si_la_ia_falla_el_lote_queda_marcado_no_a_medias(db):
    with patch.object(generation, "_generate", side_effect=RuntimeError("sin creditos")):
        out = generation.generate(db, ORG, "scenarios", lang="es")
    assert out["status"] == "failed"
    assert "sin creditos" in out["error"]
    assert db.query(BCMScenario).filter_by(organization_id=ORG).count() == 0
    bat = db.get(IngestBatch, out["batch_id"])
    assert bat.status == "failed"
