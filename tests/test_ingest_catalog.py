"""El catalogo canonico se inyecta en la pasada 2 para consolidar, no duplicar.

No prueba la calidad del modelo (eso se valida contra la API real), sino que el
codigo le pone delante el catalogo real de la organizacion y las instrucciones
de consolidacion.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import BCMLocation, BCMScenario, BusinessProcess
from app.services.ingest import comprehension as comp

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)
ORG = 665000


@pytest.fixture()
def db():
    s = _Session()
    s.add(BCMScenario(organization_id=ORG, code="ESC-001",
                      name="Caida de la infraestructura", family="systems_comms"))
    s.add(BusinessProcess(organization_id=ORG, name="Azure Hosting Service"))
    s.add(BCMLocation(organization_id=ORG, name="Madrid"))
    s.commit()
    yield s
    for m in (BCMScenario, BusinessProcess, BCMLocation):
        s.query(m).filter_by(organization_id=ORG).delete(synchronize_session=False)
    s.commit()
    s.close()


def test_el_catalogo_canonico_sale_de_la_base(db):
    cat = comp._canonical_catalog(db, ORG)
    assert ("ESC-001", "Caida de la infraestructura") in cat["scenarios"]
    assert "Azure Hosting Service" in cat["processes"]
    assert "Madrid" in cat["locations"]


def test_el_bloque_inyecta_catalogo_y_ordena_consolidar(db):
    block = comp._catalog_block(db, ORG, profile=None)
    # Contiene las entidades reales
    assert "Caida de la infraestructura" in block
    assert "Azure Hosting Service" in block
    assert "Madrid" in block
    # Y la instruccion clave de consolidacion (no crear variantes)
    assert "NO crees variantes" in block
    assert "NOMBRE EXACTO" in block


def test_sin_org_el_catalogo_va_vacio(db):
    assert comp._canonical_catalog(db, None) == {
        "scenarios": [], "processes": [], "locations": []}
