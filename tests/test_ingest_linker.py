"""Tests del enlazado de dependencias — lo que da aristas al mapa.

El agente extrae la dependencia como texto ("Ringcentral Phone System"); este
paso la ata al proveedor real ("RingCentral"), que es lo que el grafo necesita
para dibujar la relacion.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import BCPDependency, BusinessProcess, Supplier
from app.services.ingest.linker import link_dependencies

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)
ORG = 445001


@pytest.fixture()
def db():
    s = _Session()
    yield s
    for m in (BCPDependency, BusinessProcess, Supplier):
        s.query(m).filter_by(organization_id=ORG).delete(synchronize_session=False)
    s.commit()
    s.close()


def test_una_dependencia_se_ata_al_proveedor_por_nombre(db):
    db.add_all([
        Supplier(organization_id=ORG, code="SUP-1", name="RingCentral"),
        Supplier(organization_id=ORG, code="SUP-2", name="Microsoft"),
    ])
    p = BusinessProcess(organization_id=ORG, name="Telefonia")
    db.add(p)
    db.flush()
    db.add_all([
        BCPDependency(organization_id=ORG, process_id=p.id,
                      name="Ringcentral Phone System", dependency_type="communication"),
        BCPDependency(organization_id=ORG, process_id=p.id,
                      name="Office 365 / Azure", dependency_type="IT_system"),
    ])
    db.commit()

    out = link_dependencies(db, ORG)
    # Solo "Ringcentral Phone System" contiene el nombre de un proveedor;
    # "Office 365 / Azure" no contiene "microsoft" y NO se ata a la fuerza.
    assert out["suppliers_linked"] == 1

    deps = db.query(BCPDependency).filter_by(organization_id=ORG).all()
    by_name = {d.name: d.supplier_id for d in deps}
    ring = db.query(Supplier).filter_by(name="RingCentral").one()
    ms = db.query(Supplier).filter_by(name="Microsoft").one()
    assert by_name["Ringcentral Phone System"] == ring.id
    # "Office 365 / Azure" no contiene "microsoft"; enlaza por token solo si hay 2+
    # comunes, aqui no -> puede quedar sin enlazar, y eso es correcto (mejor de
    # menos que atarlo al proveedor equivocado)
    # El proceso recibe los proveedores para que el grafo dibuje la arista
    db.refresh(p)
    assert ring.id in (p.supplier_ids or [])


def test_no_ata_al_proveedor_equivocado(db):
    db.add(Supplier(organization_id=ORG, code="SUP-9", name="Telefonica"))
    p = BusinessProcess(organization_id=ORG, name="P")
    db.add(p)
    db.flush()
    db.add(BCPDependency(organization_id=ORG, process_id=p.id,
                         name="Servidor de base de datos", dependency_type="IT_system"))
    db.commit()
    link_dependencies(db, ORG)
    dep = db.query(BCPDependency).filter_by(organization_id=ORG).one()
    assert dep.supplier_id is None


def test_no_pisa_un_enlace_ya_puesto(db):
    real = Supplier(organization_id=ORG, code="SUP-1", name="AWS")
    otro = Supplier(organization_id=ORG, code="SUP-2", name="AWS Europe")
    db.add_all([real, otro])
    p = BusinessProcess(organization_id=ORG, name="P")
    db.add(p)
    db.flush()
    d = BCPDependency(organization_id=ORG, process_id=p.id, name="AWS",
                      dependency_type="IT_system", supplier_id=otro.id)
    db.add(d)
    db.commit()
    link_dependencies(db, ORG)
    db.refresh(d)
    assert d.supplier_id == otro.id      # respeta el enlace existente
