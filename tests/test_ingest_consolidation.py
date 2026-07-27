"""Consolidacion de escenarios: la IA agrupa, el motor funde con marcha atras.

Se prueba lo determinista (fundir, reapuntar, deduplicar), con el agrupamiento
del modelo mockeado.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (BCMLocation, BCMScenario, BCMScenarioAssessment,
                        BCPStrategy, IngestBatch, IngestRecordTrace)
from app.services.ingest import consolidation

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)
ORG = 667000


@pytest.fixture()
def db():
    s = _Session()
    yield s
    for m in (IngestRecordTrace, IngestBatch, BCMScenarioAssessment, BCPStrategy,
              BCMScenario, BCMLocation):
        s.query(m).filter_by(organization_id=ORG).delete(synchronize_session=False)
    s.commit()
    s.close()


def _scn(db, name, fam="systems_comms"):
    s = BCMScenario(organization_id=ORG, name=name, family=fam)
    db.add(s); db.flush()
    return s


def test_funde_variantes_y_reapunta_valoraciones(db):
    loc = BCMLocation(organization_id=ORG, name="Madrid"); db.add(loc); db.flush()
    canon = _scn(db, "Caida de la infraestructura")
    v1 = _scn(db, "Caida de infraestructura GCP")
    v2 = _scn(db, "Azure Hosting failure")
    otro = _scn(db, "Huelga de personal", fam="personnel")
    # Dos escenarios mas, distintos, para superar el minimo de consolidacion
    ex1 = _scn(db, "Corte del suministro", fam="third_party")
    ex2 = _scn(db, "Desastres naturales", fam="facilities")
    # Valoraciones: una del canonico y una de una variante en la MISMA sede
    db.add(BCMScenarioAssessment(organization_id=ORG, scenario_id=canon.id, location_id=loc.id))
    db.add(BCMScenarioAssessment(organization_id=ORG, scenario_id=v1.id, location_id=loc.id))
    db.add(BCPStrategy(organization_id=ORG, scenario_id=v2.id, name="Failover cloud"))
    db.commit()

    groups = [
        {"canonical_name": "Caida de la infraestructura", "family": "systems_comms",
         "member_ids": [canon.id, v1.id, v2.id]},
        {"canonical_name": "Huelga de personal", "family": "personnel",
         "member_ids": [otro.id]},
        {"canonical_name": "Corte del suministro", "family": "third_party",
         "member_ids": [ex1.id]},
        {"canonical_name": "Desastres naturales", "family": "facilities",
         "member_ids": [ex2.id]},
    ]
    with patch.object(consolidation, "_group_with_llm", return_value=groups):
        res = consolidation.consolidate_scenarios(db, ORG)

    assert res["before"] == 6
    assert res["after"] == 4          # las dos variantes fundidas en el canonico
    assert res["merged"] == 2
    survivors = {s.name for s in db.query(BCMScenario).filter_by(organization_id=ORG).all()}
    assert survivors == {"Caida de la infraestructura", "Huelga de personal",
                         "Corte del suministro", "Desastres naturales"}
    # La estrategia de la variante ahora cuelga del superviviente
    st = db.query(BCPStrategy).filter_by(organization_id=ORG).one()
    assert st.scenario_id == canon.id
    # Las dos valoraciones en Madrid se deduplican a una
    asmts = db.query(BCMScenarioAssessment).filter_by(organization_id=ORG).all()
    assert len(asmts) == 1
    assert asmts[0].scenario_id == canon.id


def test_limpia_el_ruido_de_revision_de_las_variantes(db):
    bat = IngestBatch(organization_id=ORG, module="bcm", status="running")
    db.add(bat); db.flush()
    canon = _scn(db, "Caida de la infraestructura")
    variants = [_scn(db, f"variante {i}") for i in range(5)]
    canon_id = canon.id
    variant_ids = [v.id for v in variants]
    # trazas con needs_review; el superviviente ademas marcado posible duplicado
    for s in [canon, *variants]:
        db.add(IngestRecordTrace(
            organization_id=ORG, batch_id=bat.id, entity="bcm_scenario",
            table_name="bcm_scenarios", record_id=s.id, action="created",
            needs_review=True,
            after={"name": s.name, "_possible_duplicate": [{"id": 1, "name": "x"}]}))
    db.commit()

    groups = [{"canonical_name": "Caida de la infraestructura",
               "family": "systems_comms",
               "member_ids": [canon_id, *variant_ids]}]
    with patch.object(consolidation, "_group_with_llm", return_value=groups):
        consolidation.consolidate_scenarios(db, ORG)

    # Trazas de las variantes fundidas: borradas (apuntaban a algo inexistente)
    left = db.query(IngestRecordTrace).filter(
        IngestRecordTrace.organization_id == ORG,
        IngestRecordTrace.record_id.in_(variant_ids)).count()
    assert left == 0
    # El superviviente ya no es "por revisar" ni "posible duplicado"
    tr = db.query(IngestRecordTrace).filter_by(
        organization_id=ORG, record_id=canon_id).one()
    assert tr.needs_review is False
    assert "_possible_duplicate" not in (tr.after or {})


def test_no_toca_un_catalogo_ya_pequeno(db):
    for i in range(3):
        _scn(db, f"Escenario {i}")
    db.commit()
    res = consolidation.consolidate_scenarios(db, ORG)
    assert res["merged"] == 0
    assert res["after"] == 3


def test_grupo_de_un_miembro_solo_renombra(db):
    s = _scn(db, "infra aws")
    for i in range(6):
        _scn(db, f"otro {i}", fam="facilities")
    db.commit()
    groups = [{"canonical_name": "Caida de la infraestructura",
               "family": "systems_comms", "member_ids": [s.id]}]
    with patch.object(consolidation, "_group_with_llm", return_value=groups):
        consolidation.consolidate_scenarios(db, ORG)
    db.refresh(s)
    assert s.name == "Caida de la infraestructura"
    assert s.family == "systems_comms"
