"""Regresion: los codigos TSK del workflow automatico no deben colisionar.

Con autoflush=False, _next_task_code no veia las tareas pendientes de la misma
sesion: N riesgos auto-generados en lote calculaban el mismo codigo y el commit
fallaba con UNIQUE constraint (tareas perdidas silenciosamente).
"""
import uuid

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def test_batch_workflows_generate_unique_task_codes(client):
    from app.models import (
        Asset, AssetType, Organization, Risk, RiskStatus, Threat, ThreatOrigin,
        TreatmentTask,
    )
    from app.services.workflow_engine import start_risk_workflow

    db = _TestSession()
    try:
        org = db.query(Organization).first()
        asset = Asset(organization_id=org.id, code=f"AST-WF-{_uid()}", name="Activo WF",
                      asset_type=AssetType.SUPPORT_SOFTWARE)
        db.add(asset)
        db.flush()

        risks = []
        for i in range(3):
            threat = Threat(code=f"THR-WF-{_uid()}", name=f"Amenaza WF {i}",
                            origin=ThreatOrigin.DELIBERATE, is_custom=True)
            db.add(threat)
            db.flush()
            risk = Risk(
                organization_id=org.id, code=f"RSK-WF-{_uid()}",
                asset_id=asset.id, threat_id=threat.id,
                inherent_likelihood=4, inherent_consequence=4,
                residual_likelihood=4, residual_consequence=4, residual_level=6,
                status=RiskStatus.IDENTIFIED,
            )
            db.add(risk)
            db.flush()
            risks.append(risk)
        db.commit()

        # 3 workflows seguidos en la misma sesion = 9 tareas; antes del fix
        # colisionaban los codigos y algunos commits fallaban
        workflows = [start_risk_workflow(db, r) for r in risks]
        assert all(w is not None for w in workflows), "todos los workflows deben crearse"

        risk_ids = [r.id for r in risks]
        tasks = db.query(TreatmentTask).filter(TreatmentTask.risk_id.in_(risk_ids)).all()
        assert len(tasks) == 9
        codes = [t.code for t in tasks]
        assert len(codes) == len(set(codes)), f"codigos duplicados: {codes}"
    finally:
        db.close()
