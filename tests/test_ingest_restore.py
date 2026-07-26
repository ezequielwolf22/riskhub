"""Rehacer un registro deshecho: 'Deshecho' nunca es terminal.

Garantiza que revert_record y restore_record son inversos exactos, tanto para
una fila ACTUALIZADA (recupera el estado posterior) como para una CREADA
(re-inserta con su MISMO id, sin romper referencias).
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import BCMLocation, BCMScenario, IngestBatch, IngestRecordTrace
from app.services.ingest import batch as batch_mod

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)
ORG = 551000


@pytest.fixture()
def db():
    s = _Session()
    yield s
    for m in (IngestRecordTrace, IngestBatch, BCMScenario, BCMLocation):
        s.query(m).filter_by(organization_id=ORG).delete(synchronize_session=False)
    s.commit()
    s.close()


def _batch(db):
    b = IngestBatch(organization_id=ORG, module="bcm", status="running", summary={})
    db.add(b)
    db.commit()
    return b


def test_rehacer_una_actualizacion_recupera_el_estado_posterior(db):
    b = _batch(db)
    sc = BCMScenario(organization_id=ORG, code="ES-05", name="AWS",
                     family="systems_comms", description="cloud AWS")
    db.add(sc)
    db.flush()
    # La ingesta lo cambia a GCP y deja rastro (before=AWS, after=GCP)
    before = batch_mod.snapshot(sc)
    sc.description = "cloud GCP"
    db.flush()
    tr = batch_mod.trace(db, b, "bcm_scenario", "bcm_scenarios", sc.id, "updated",
                         before=before, after=batch_mod.snapshot(sc))
    db.commit()

    # Deshacer: vuelve a AWS
    assert batch_mod.revert_record(db, tr) is True
    db.commit()
    assert db.get(BCMScenario, sc.id).description == "cloud AWS"
    assert tr.reverted_at is not None

    # Rehacer: vuelve a GCP y limpia la marca de deshecho
    assert batch_mod.restore_record(db, tr) is True
    db.commit()
    assert db.get(BCMScenario, sc.id).description == "cloud GCP"
    assert tr.reverted_at is None


def test_rehacer_una_creacion_reinserta_con_el_mismo_id(db):
    b = _batch(db)
    sc = BCMScenario(organization_id=ORG, code="ES-99", name="Nuevo",
                     family="facilities", description="creado por la ingesta")
    db.add(sc)
    db.flush()
    original_id = sc.id
    tr = batch_mod.trace(db, b, "bcm_scenario", "bcm_scenarios", sc.id, "created",
                         before=None, after=batch_mod.snapshot(sc))
    db.commit()

    # Deshacer: se borra el registro creado
    assert batch_mod.revert_record(db, tr) is True
    db.commit()
    assert db.get(BCMScenario, original_id) is None

    # Rehacer: se re-inserta con el MISMO id (las referencias no se rompen)
    assert batch_mod.restore_record(db, tr) is True
    db.commit()
    rec = db.get(BCMScenario, original_id)
    assert rec is not None
    assert rec.id == original_id
    assert rec.code == "ES-99"
    assert rec.name == "Nuevo"
    assert tr.reverted_at is None


def test_rehacer_lo_que_no_esta_deshecho_no_hace_nada(db):
    b = _batch(db)
    sc = BCMScenario(organization_id=ORG, code="ES-01", name="X",
                     family="personnel", description="d")
    db.add(sc)
    db.flush()
    tr = batch_mod.trace(db, b, "bcm_scenario", "bcm_scenarios", sc.id, "updated",
                         before=batch_mod.snapshot(sc), after=batch_mod.snapshot(sc))
    db.commit()
    # No esta revertido -> restore es un no-op seguro
    assert batch_mod.restore_record(db, tr) is False


def test_rehacer_ignora_las_claves_sinteticas_de_revision(db):
    b = _batch(db)
    sc = BCMScenario(organization_id=ORG, code="ES-07", name="Dup",
                     family="third_party", description="d")
    db.add(sc)
    db.flush()
    after = batch_mod.snapshot(sc)
    after["_possible_duplicate"] = [{"id": 1, "name": "otro"}]  # anotacion de revision
    tr = batch_mod.trace(db, b, "bcm_scenario", "bcm_scenarios", sc.id, "created",
                         before=None, after=after)
    db.commit()
    batch_mod.revert_record(db, tr)
    db.commit()
    # La re-insercion no debe intentar escribir _possible_duplicate como columna
    assert batch_mod.restore_record(db, tr) is True
    db.commit()
    assert db.get(BCMScenario, sc.id) is not None
