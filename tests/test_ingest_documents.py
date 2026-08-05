"""Registro dinamico de documentos: control total del usuario.

Anadir, excluir/incluir, quitar y reanalizar cuando se quiera. Por defecto todo
lo que se sube se analiza.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import IngestDocument
from app.services.ingest import document_store as store

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)
ORG = 663000
_TXT = b"Escenario: Caida de las comunicaciones. RTO 1 hora."


@pytest.fixture()
def db():
    s = _Session()
    yield s
    for d in s.query(IngestDocument).filter_by(organization_id=ORG).all():
        try:
            store.remove_document(s, ORG, d.id)
        except Exception:
            pass
    s.commit()
    s.close()


def test_anadir_documento_lo_registra_incluido_y_persistido(db):
    d = store.add_document(db, ORG, "BIA.txt", _TXT, user_id=1)
    db.commit()
    assert d.included is True
    assert d.status == "pending"
    assert d.sha256 and d.size_bytes == len(_TXT)
    assert store.load_bytes(d) == _TXT          # los bytes se pueden releer


def test_subir_el_mismo_fichero_dos_veces_no_lo_duplica(db):
    store.add_document(db, ORG, "BIA.txt", _TXT)
    store.add_document(db, ORG, "BIA copia.txt", _TXT)   # mismo contenido
    db.commit()
    assert db.query(IngestDocument).filter_by(organization_id=ORG).count() == 1


def test_excluir_un_documento_lo_saca_del_analisis(db):
    d = store.add_document(db, ORG, "ruido.txt", _TXT)
    db.commit()
    store.set_included(db, ORG, d.id, False)
    db.commit()
    assert d.included is False
    assert d.status == "excluded"
    assert d not in store.included_documents(db, ORG)
    # Y se puede volver a incluir cuando se quiera
    store.set_included(db, ORG, d.id, True)
    db.commit()
    assert d.included is True and d.status == "pending"


def test_quitar_un_documento_lo_borra_del_registro(db):
    d = store.add_document(db, ORG, "temporal.txt", _TXT)
    db.commit()
    did = d.id
    assert store.remove_document(db, ORG, did) is True
    db.commit()
    assert store.get_document(db, ORG, did) is None


def test_solo_los_incluidos_entran_al_analisis(db):
    a = store.add_document(db, ORG, "a.txt", b"contenido A")
    b = store.add_document(db, ORG, "b.txt", b"contenido B")
    db.commit()
    store.set_included(db, ORG, b.id, False)
    db.commit()
    incluidos = {d.id for d in store.included_documents(db, ORG)}
    assert a.id in incluidos and b.id not in incluidos


def test_no_cruza_organizaciones(db):
    d = store.add_document(db, ORG, "priv.txt", _TXT)
    db.commit()
    assert store.get_document(db, 999999, d.id) is None
    assert store.set_included(db, 999999, d.id, False) is None
    assert store.remove_document(db, 999999, d.id) is False
