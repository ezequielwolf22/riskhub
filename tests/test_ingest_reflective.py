"""La ingesta REFLEJA, no modifica.

Tres garantias que pidio el cliente y que valen para cualquier organizacion:

1. Un codigo roto de Excel ("#¡REF!") no es identidad: cuatro escenarios
   distintos con el codigo roto NO se funden en uno.
2. Escenarios con nombres distintos son registros distintos; el mismo nombre
   enlaza (identidad por nombre cuando el codigo falta).
3. Una importacion NUNCA pisa un valor que ya existe: rellena huecos y, si algo
   difiere, lo deja como propuesta (conflicto) — no lo sobrescribe.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (BCMScenario, BusinessProcess, IngestBatch,
                        IngestConflict, IngestRecordTrace)
from app.services.ingest import batch as batch_mod
from app.services.ingest.materializer import materialize

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)
ORG = 662000


@pytest.fixture()
def db():
    s = _Session()
    yield s
    for m in (IngestConflict, IngestRecordTrace, IngestBatch, BCMScenario,
              BusinessProcess):
        s.query(m).filter_by(organization_id=ORG).delete(synchronize_session=False)
    s.commit()
    s.close()


@pytest.fixture()
def bat(db):
    return batch_mod.create_batch(db, ORG, module="bcm")


def test_codigo_roto_de_excel_no_funde_escenarios_distintos(db, bat):
    # El BIA trae el codigo como "#¡REF!" en los cuatro: son escenarios DISTINTOS
    materialize(db, ORG, bat, "bcm_scenario", [
        {"code": "#¡REF!", "name": "Caida de las comunicaciones", "family": "systems_comms"},
        {"code": "#¡REF!", "name": "Caida de los sistemas de producto", "family": "systems_comms"},
        {"code": "#¡REF!", "name": "Caida de la infraestructura AWS", "family": "systems_comms"},
        {"code": "#N/A", "name": "Ataques de ciberseguridad", "family": "systems_comms"},
    ])
    db.commit()
    scenarios = db.query(BCMScenario).filter_by(organization_id=ORG).all()
    assert len(scenarios) == 4                      # cuatro, no uno
    codes = {s.code for s in scenarios}
    assert "#¡REF!" not in codes and "#N/A" not in codes   # el error no es codigo
    assert len(codes) == 4                          # cada uno con su codigo propio


def test_el_mismo_nombre_de_escenario_enlaza_no_duplica(db, bat):
    materialize(db, ORG, bat, "bcm_scenario",
                [{"name": "Huelga de personal", "family": "personnel"}])
    db.commit()
    # Reimportar el mismo escenario (otra vez, sin codigo) no lo duplica
    materialize(db, ORG, bat, "bcm_scenario",
                [{"name": "Huelga de personal ", "family": "personnel"}])
    db.commit()
    assert db.query(BCMScenario).filter_by(organization_id=ORG).count() == 1


def test_una_importacion_no_pisa_un_valor_que_ya_existe(db, bat):
    # Ya existe un proceso con descripcion. Un documento trae otra distinta.
    db.add(BusinessProcess(organization_id=ORG, name="Facturacion",
                           description="Proceso de facturacion a clientes",
                           criticality="high"))
    db.commit()
    materialize(db, ORG, bat, "business_process",
                [{"name": "Facturacion",
                  "description": "OTRA descripcion completamente distinta",
                  "criticality": "low"}],
                source_filename="DRP.docx")
    db.commit()

    p = db.query(BusinessProcess).filter_by(organization_id=ORG).one()
    # NADA se sobrescribio: los valores originales siguen intactos
    assert p.description == "Proceso de facturacion a clientes"
    assert p.criticality == "high"
    # Las diferencias quedaron como propuestas, para que el usuario decida
    assert p.needs_review is True
    campos = {c.field_name for c in db.query(IngestConflict).filter_by(
        organization_id=ORG).all()}
    assert "description" in campos and "criticality" in campos


def test_una_importacion_rellena_huecos(db, bat):
    # Existe el proceso pero sin criticidad ni RTO. El documento los aporta.
    db.add(BusinessProcess(organization_id=ORG, name="Nominas"))
    db.commit()
    materialize(db, ORG, bat, "business_process",
                [{"name": "Nominas", "criticality": "critical", "rto_hours": 8}])
    db.commit()
    p = db.query(BusinessProcess).filter_by(organization_id=ORG).one()
    assert p.criticality == "critical"      # hueco rellenado
    assert p.rto_hours == 8
    # Rellenar un hueco no es un conflicto
    assert db.query(IngestConflict).filter_by(organization_id=ORG).count() == 0
