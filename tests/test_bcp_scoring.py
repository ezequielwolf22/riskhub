"""Tests del motor de scoring ISO 22301 del modulo BCP/BCM.

Contexto: una auditoria (v5.2) encontro que el dashboard BCP/BCM mostraba
scores de conformidad ISO 22301 sin ninguna base en evidencia real — por
ejemplo, la clausula "Mejora continua" partia de un piso fijo de 40 puntos
(`min(100, 40 + cl9 // 2)`) aunque la organizacion no tuviera nada configurado,
y la clausula de no conformidades marcaba "implementado" solo porque no existia
ningun registro de NC (ausencia de evidencia interpretada como conformidad).

Estos tests fijan el comportamiento correcto: ausencia total de datos siempre
da score 0 / status "gap", nunca conformidad implicita; y las clausulas que
antes se satisfacian con un simple flag de estado (plan "approved", evidencia
subida) ahora requieren contenido/vinculacion real para el credito completo.

Usa una BD SQLite propia en memoria (no la de conftest) para poder insertar
escenarios BCP conocidos sin interferir con otros tests que comparten sesion.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    BusinessProcess, BCPPlan, BCPTest, BCMEvidenceItem, NonConformity, NCStatus,
    AuditProgram, AuditStatus,
)
from app.services.bcp_service import iso22301_status, iso22301_clause_scores

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)

ORG = 999999


@pytest.fixture()
def db():
    session = _Session()
    yield session
    for model in (BusinessProcess, BCPPlan, BCPTest, BCMEvidenceItem, NonConformity, AuditProgram):
        session.query(model).filter_by(organization_id=ORG).delete()
    session.commit()
    session.close()


def _clause(result, clause_id):
    return next(c for c in result["clauses"] if c["id"] == clause_id)


def test_empty_org_scores_zero(db):
    """Organizacion sin nada configurado: el score global debe ser 0, no un
    piso arbitrario, y ninguna clausula puede marcarse 'implemented'."""
    result = iso22301_clause_scores(db, ORG)
    assert result["score_global"] == 0
    assert all(c["status"] != "implemented" for c in result["clauses"])
    mejora = _clause(result, "10.1")
    nc = _clause(result, "10.2")
    assert mejora["score"] == 0 and mejora["status"] == "gap"
    assert nc["score"] == 0 and nc["status"] == "gap"


def test_nc_clause_requires_real_audit_trail(db):
    """Bug original: 0 NCs registradas se marcaba 'implemented'. Ahora requiere
    evidencia de que el proceso de auditoria/NC realmente corre."""
    status = iso22301_status(db, ORG)
    assert _clause(status, "10.2")["status"] == "gap"

    db.add(BCPTest(
        organization_id=ORG, code="BCT-0001", test_type="tabletop",
        conducted_at=datetime.now(timezone.utc) - timedelta(days=10), result="passed",
    ))
    db.commit()
    status = iso22301_status(db, ORG)
    assert _clause(status, "10.2")["status"] == "partial"

    db.add(NonConformity(
        organization_id=ORG, code="NC-BCP-TEST-01", title="Hallazgo de prueba",
        source="bcp_test", status=NCStatus.OPEN,
    ))
    db.commit()
    status = iso22301_status(db, ORG)
    assert _clause(status, "10.2")["status"] == "partial"

    nc = db.query(NonConformity).filter_by(organization_id=ORG).first()
    nc.status = NCStatus.CLOSED
    db.commit()
    status = iso22301_status(db, ORG)
    assert _clause(status, "10.2")["status"] == "implemented"


def test_plan_status_flag_alone_is_not_full_credit(db):
    """Bug original: un BCPPlan con status='approved' vacio contaba igual que
    uno con contenido real. Ahora un plan vacio solo da 'partial'."""
    db.add(BCPPlan(
        organization_id=ORG, code="BCP-TEST-01", plan_type="bcp",
        name="Plan vacio", status="approved",
    ))
    db.commit()
    status = iso22301_status(db, ORG)
    assert _clause(status, "8.4_bcp")["status"] == "partial"

    plan = db.query(BCPPlan).filter_by(organization_id=ORG).first()
    plan.sections = [{"id": 1, "title": "Alcance", "content": "Contenido real del plan"}]
    db.commit()
    status = iso22301_status(db, ORG)
    assert _clause(status, "8.4_bcp")["status"] == "implemented"


def test_evidence_quantity_alone_does_not_inflate_score(db):
    """Bug original: cl7 = min(100, len(evidencias) * 10) daba 100% con 10
    archivos sueltos sin vincular a nada. Ahora requiere vinculacion real."""
    for i in range(10):
        db.add(BCMEvidenceItem(
            organization_id=ORG, evidence_type="other",
            title=f"Evidencia suelta {i}", is_current=True,
        ))
    db.commit()
    status = iso22301_status(db, ORG)
    assert _clause(status, "7.5")["status"] != "implemented"


def test_evidence_marked_irrelevant_by_ai_does_not_count_as_coverage(db):
    """Si bcm_content_reviewer.review_evidence_item determino que un archivo de
    evidencia NO respalda su etiqueta (ai_review.relevant=False), no debe contar
    como cobertura real aunque este vinculado a un plan aprobado."""
    db.add(BCPPlan(
        organization_id=ORG, code="BCP-TEST-03", plan_type="bcp",
        name="Plan con evidencia dudosa", status="approved",
    ))
    db.commit()
    plan = db.query(BCPPlan).filter_by(organization_id=ORG).first()

    db.add(BCMEvidenceItem(
        organization_id=ORG, evidence_type="test_report", title="Evidencia vinculada",
        is_current=True, linked_plan_id=plan.id,
        ai_review={"relevant": False, "quality_score": 5, "summary": "Archivo irrelevante"},
    ))
    db.commit()
    status = iso22301_status(db, ORG)
    assert _clause(status, "7.5")["status"] != "implemented"

    ev = db.query(BCMEvidenceItem).filter_by(organization_id=ORG).first()
    ev.ai_review = {"relevant": True, "quality_score": 80, "summary": "Acta real de test"}
    db.commit()
    status = iso22301_status(db, ORG)
    assert _clause(status, "7.5")["status"] == "implemented"


def test_ai_content_review_gates_plan_credit(db):
    """La revision semantica IA (bcm_content_reviewer.py) manda sobre el chequeo
    estructural: un plan 'approved' con documento pero score IA bajo se queda en
    'partial', y solo pasa a 'implemented' si la IA valida el contenido real."""
    db.add(BCPPlan(
        organization_id=ORG, code="BCP-TEST-02", plan_type="bcp",
        name="Plan con documento de baja calidad", status="approved",
        document_id=None,
    ))
    db.commit()
    plan = db.query(BCPPlan).filter_by(organization_id=ORG).first()

    plan.ai_content_review = {"score": 30, "covered": [], "missing": ["todo"]}
    db.commit()
    status = iso22301_status(db, ORG)
    assert _clause(status, "8.4_bcp")["status"] == "partial"

    plan.ai_content_review = {"score": 85, "covered": ["todo"], "missing": []}
    db.commit()
    status = iso22301_status(db, ORG)
    assert _clause(status, "8.4_bcp")["status"] == "implemented"
    assert "85" in _clause(status, "8.4_bcp")["detail"]


def test_formal_audit_program_counts_as_internal_audit_evidence(db):
    """Cl. 9.2 (Auditoria interna) debe reconocer una auditoria formal del
    modulo general de auditorias (AuditProgram) con alcance en continuidad/
    ISO 22301, no solo los ejercicios propios (BCPTest full_test)."""
    status = iso22301_status(db, ORG)
    assert _clause(status, "9.2")["status"] == "gap"

    db.add(AuditProgram(
        organization_id=ORG, code="AUD-BCM-01", title="Auditoria SGCN 2026",
        status=AuditStatus.COMPLETED, criteria="ISO 22301:2019",
        actual_end=datetime.now(timezone.utc) - timedelta(days=30),
    ))
    db.commit()
    status = iso22301_status(db, ORG)
    clause = _clause(status, "9.2")
    assert clause["status"] == "implemented"
    assert "Auditoria SGCN 2026" in clause["detail"] or "SGCN 2026" in clause["detail"]


def test_weights_sum_to_100_and_cover_all_clauses(db):
    """El peso de cada clausula debe sumar 100 en total (7 clausulas
    principales igual de obligatorias, repartidas entre sus sub-clausulas)."""
    result = iso22301_clause_scores(db, ORG)
    total_weight = sum(c["weight"] for c in result["clauses"])
    assert round(total_weight, 2) == 100.0
    assert len(result["clauses"]) == 25
