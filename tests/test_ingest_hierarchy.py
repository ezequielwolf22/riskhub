"""Fase 4: la ingesta reconstruye la jerarquia real de procesos.

Un documento lista los procesos en cualquier orden y de forma plana. El motor,
sin ningun modelo de lenguaje en esta capa, debe:

- colocar cada proceso en su unidad de negocio (business_unit),
- enlazar un subproceso a su macro-proceso (parent_process_id) por NOMBRE,
  aunque el hijo aparezca ANTES que el padre en el documento,
- enlazar una dependencia proceso->proceso (depends_on_process_id) por nombre,
  que es lo que alimenta el grafo de propagacion de impacto.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (BCPDependency, BusinessProcess, IngestBatch,
                        IngestRecordTrace, IngestSourceMap)
from app.services.ingest import comprehension, pipeline

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)

ORG = 778001


@pytest.fixture()
def db():
    session = _Session()
    yield session
    for model in (IngestRecordTrace, IngestSourceMap, BCPDependency,
                  BusinessProcess, IngestBatch):
        session.query(model).filter_by(organization_id=ORG).delete(
            synchronize_session=False)
    session.commit()
    session.close()


def _xlsx() -> bytes:
    import io

    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Procesos"
    ws.append(["Proceso", "Unidad"])
    ws.append(["Ventas", "Comercial"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# El mapa lista el HIJO (Facturacion) ANTES que el PADRE (Ventas) para forzar el
# reordenamiento topologico. Facturacion ademas depende del proceso Ventas.
_MAP = {
    "doc_kind": "bia",
    "confidence": 0.9,
    "rationale": "Cadena de valor Comercial con macro-proceso y subprocesos.",
    "filename": "PROCESOS.xlsx",
    "sha256": "hier123",
    "units": [
        {"label": "Procesos", "source_ref": "sheet:Procesos",
         "decomposition_key": "una fila por proceso, numeracion 1 / 1.1 / 1.2",
         "target_entity": "business_process", "confidence": 0.9,
         "rows": [
             {"fields": {"name": "Facturacion", "business_unit": "Comercial",
                         "criticality": "high", "rto_hours": 8,
                         "_ref_parent_process_id": "Ventas"}},
             {"fields": {"name": "Captacion", "business_unit": "Comercial",
                         "criticality": "medium",
                         "_ref_parent_process_id": "Ventas"}},
             {"fields": {"name": "Ventas", "business_unit": "Comercial",
                         "criticality": "critical", "rto_hours": 4}},
         ]},
        {"label": "Dependencias entre procesos", "source_ref": "sheet:Procesos",
         "decomposition_key": "una fila por dependencia proceso->proceso",
         "target_entity": "bcp_dependency", "confidence": 0.9,
         "rows": [
             {"fields": {"_ref_process_id": "Facturacion",
                         "name": "Requiere Ventas operativo",
                         "dependency_type": "process",
                         "_ref_depends_on_process_id": "Ventas",
                         "is_critical": True}},
         ]},
    ],
}


def _run(db):
    with patch.object(comprehension, "build_profile", return_value=None), \
         patch.object(comprehension, "build_source_map", return_value=_MAP):
        return pipeline.run_pack(db, ORG, [("PROCESOS.xlsx", _xlsx())],
                                 apply_profile=False)


def test_la_ingesta_reconstruye_la_jerarquia_de_procesos(db):
    out = _run(db)
    assert out["status"] == "completed"

    procs = {p.name: p for p in db.query(BusinessProcess).filter_by(
        organization_id=ORG).all()}
    assert set(procs) == {"Ventas", "Facturacion", "Captacion"}

    # Unidad de negocio en cada proceso
    assert all(p.business_unit == "Comercial" for p in procs.values())

    # El padre no tiene padre; los hijos apuntan a Ventas AUNQUE vinieran antes
    # que el en el documento (reordenamiento topologico del materializador).
    ventas = procs["Ventas"]
    assert ventas.parent_process_id is None
    assert procs["Facturacion"].parent_process_id == ventas.id
    assert procs["Captacion"].parent_process_id == ventas.id


def test_la_ingesta_reconstruye_la_dependencia_proceso_a_proceso(db):
    _run(db)
    dep = db.query(BCPDependency).filter_by(
        organization_id=ORG, dependency_type="process").one()
    procs = {p.name: p.id for p in db.query(BusinessProcess).filter_by(
        organization_id=ORG).all()}
    assert dep.process_id == procs["Facturacion"]
    assert dep.depends_on_process_id == procs["Ventas"]
    assert dep.is_critical is True


def test_un_padre_inexistente_no_rompe_el_proceso(db):
    """Si el documento cita un padre que no esta en el lote ni en la base, el
    proceso se crea igual (sin jerarquia), no se pierde."""
    orphan_map = {
        "doc_kind": "bia", "confidence": 0.9, "rationale": "x",
        "filename": "H.xlsx", "sha256": "orph1",
        "units": [
            {"label": "P", "source_ref": "s", "decomposition_key": "k",
             "target_entity": "business_process", "confidence": 0.9,
             "rows": [
                 {"fields": {"name": "Suelto", "criticality": "low",
                             "_ref_parent_process_id": "No existe"}},
             ]},
        ],
    }
    with patch.object(comprehension, "build_profile", return_value=None), \
         patch.object(comprehension, "build_source_map", return_value=orphan_map):
        out = pipeline.run_pack(db, ORG, [("H.xlsx", _xlsx())],
                                apply_profile=False)
    assert out["status"] == "completed"
    p = db.query(BusinessProcess).filter_by(
        organization_id=ORG, name="Suelto").one()
    assert p.parent_process_id is None
