"""Deshacer un lote es resiliente: un fallo aislado no tumba todo el deshacer.

Antes, si revertir un registro fallaba (p.ej. otro apunta a el por clave
foranea), la sesion quedaba inservible y el deshacer entero devolvia un 500.
Ahora cada reversion va en su savepoint: la que falla se reporta y el resto
sigue.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import BusinessProcess, IngestBatch, IngestRecordTrace
from app.services.ingest import batch as batch_mod
from app.services.ingest.materializer import materialize

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)
ORG = 664000


@pytest.fixture()
def db():
    s = _Session()
    yield s
    for m in (IngestRecordTrace, IngestBatch, BusinessProcess):
        s.query(m).filter_by(organization_id=ORG).delete(synchronize_session=False)
    s.commit()
    s.close()


def test_un_fallo_al_revertir_no_tumba_el_lote(db, monkeypatch):
    bat = batch_mod.create_batch(db, ORG, module="bcm")
    materialize(db, ORG, bat, "business_process",
                [{"name": "P1"}, {"name": "P2"}, {"name": "P3"}])
    db.commit()
    assert db.query(BusinessProcess).filter_by(organization_id=ORG).count() == 3

    # Hacemos que revertir el SEGUNDO registro procesado reviente
    real = batch_mod.revert_record
    calls = {"n": 0}

    def flaky(db_, trace, user_id=None):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("FOREIGN KEY constraint failed (simulado)")
        return real(db_, trace, user_id)

    monkeypatch.setattr(batch_mod, "revert_record", flaky)

    res = batch_mod.undo_batch(db, bat)
    # No lanza excepcion; deshace lo que puede y reporta el fallo
    assert res["already_undone"] is False
    assert res["reverted"] == 2
    assert len(res["failed"]) == 1
    assert "FOREIGN KEY" in res["failed"][0]["error"]
    assert bat.status == "undone"
    # Los otros dos si se borraron
    assert db.query(BusinessProcess).filter_by(organization_id=ORG).count() == 1
