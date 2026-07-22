"""Aprobacion formal del Plan Director — ISO/IEC 27001 cl. 6.1.3f.

La norma exige que los propietarios del riesgo APRUEBEN el plan de tratamiento
y ACEPTEN formalmente el riesgo residual. La no conformidad mayor tipica en
auditoria es la "aceptacion no autorizada": un riesgo alto dado por aceptado sin
que conste la firma del responsable. Antes de esto, el estado del plan pasaba a
'approved' sin dejar rastro de quien, cuando ni sobre que version.

Dos modos, configurables por organizacion en RiskContext.plan_approval_mode:

  - internal_seal: sello interno (usuario, fecha, version, hash del contenido).
    Suficiente para muchos auditores y sin dependencias externas.
  - signature: firma por token/email con IP y caducidad, para no repudio.

Se reutiliza el PATRON de approval_service (tokens, rondas paralelas o
secuenciales) pero con tabla propia `plan_approvals`: el flujo de politicas esta
en produccion y no debe tocarse para esto.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import PlanApproval, RiskContext, StrategicPlan

logger = logging.getLogger(__name__)

_TOKEN_TTL_DAYS = 30
VALID_MODES = ("internal_seal", "signature")


def get_approval_mode(db: Session, org_id: int | None) -> str:
    """Modo configurado por la organizacion (por defecto, sello interno)."""
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    mode = getattr(ctx, "plan_approval_mode", None) if ctx else None
    return mode if mode in VALID_MODES else "internal_seal"


def compute_content_hash(db: Session, plan: StrategicPlan) -> str:
    """Huella de lo que se aprueba: alcance, periodo, objetivos e iniciativas.

    Si algo de esto cambia despues, el hash deja de cuadrar y queda constancia
    de que lo aprobado ya no es lo que hay.
    """
    from app.models import StrategicInitiative, StrategicProgram

    programs = db.query(StrategicProgram).filter(
        StrategicProgram.plan_id == plan.id).order_by(StrategicProgram.code).all()
    initiatives = []
    if programs:
        initiatives = db.query(StrategicInitiative).filter(
            StrategicInitiative.program_id.in_([p.id for p in programs])
        ).order_by(StrategicInitiative.code).all()

    payload = {
        "code": plan.code,
        "version": plan.version,
        "scope": plan.scope_statement or "",
        "period": [
            plan.period_start.isoformat() if plan.period_start else None,
            plan.period_end.isoformat() if plan.period_end else None,
        ],
        "framework": plan.framework_code,
        "targets": sorted(
            f"{t.control_id or ''}|{t.framework_code or ''}|{t.requirement_id or ''}|{t.target_maturity}"
            for t in plan.targets
        ),
        "programs": [p.code for p in programs],
        "initiatives": sorted(f"{i.code}|{i.title}|{i.budget or 0}" for i in initiatives),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def request_approval(db: Session, plan: StrategicPlan, *, mode: str | None,
                     approvers: list[dict], requested_by_id: int | None,
                     notes: str | None = None) -> list[PlanApproval]:
    """Abre la ronda de aprobacion y deja el plan en 'pending_approval'.

    En modo firma hace falta al menos un aprobador con email. En modo sello, la
    aprobacion la ejerce despues un usuario con permiso desde la propia app.
    """
    org_id = plan.organization_id
    mode = mode if mode in VALID_MODES else get_approval_mode(db, org_id)
    content_hash = compute_content_hash(db, plan)
    now = datetime.now(timezone.utc)

    # Una ronda nueva invalida cualquier ronda pendiente anterior
    db.query(PlanApproval).filter(
        PlanApproval.plan_id == plan.id, PlanApproval.status == "pending",
    ).update({"status": "cancelled"}, synchronize_session=False)

    created: list[PlanApproval] = []
    if mode == "signature":
        if not approvers:
            raise ValueError("El modo de firma exige al menos un aprobador.")
        expires_at = now + timedelta(days=_TOKEN_TTL_DAYS)
        for item in approvers:
            email = (item.get("email") or "").strip()
            if not email:
                continue
            created.append(PlanApproval(
                organization_id=org_id, plan_id=plan.id, plan_version=plan.version,
                mode=mode, status="pending", requested_by_id=requested_by_id,
                requested_at=now, approver_email=email,
                approver_name=item.get("name") or None,
                token=secrets.token_urlsafe(32), expires_at=expires_at,
                order_index=int(item.get("order_index") or 1),
                content_hash=content_hash, response_notes=notes,
            ))
        if not created:
            raise ValueError("El modo de firma exige al menos un aprobador con email.")
    else:
        created.append(PlanApproval(
            organization_id=org_id, plan_id=plan.id, plan_version=plan.version,
            mode=mode, status="pending", requested_by_id=requested_by_id,
            requested_at=now, content_hash=content_hash, response_notes=notes,
        ))

    for approval in created:
        db.add(approval)
    plan.status = "pending_approval"
    db.flush()
    return created


def _finalise_plan(db: Session, plan: StrategicPlan, approvals: list[PlanApproval]) -> bool:
    """Aprueba el plan si toda la ronda dijo que si. Sella la linea base."""
    from app.services.strategic_profile_service import seal_baseline

    if not approvals or any(a.status != "approved" for a in approvals):
        return False
    latest = max(approvals, key=lambda a: a.responded_at or a.requested_at)
    plan.status = "approved"
    plan.approved_at = latest.responded_at or datetime.now(timezone.utc)
    plan.approved_by_id = latest.approved_by_id
    # La linea base se congela en el momento de aprobar: a partir de ahi el
    # avance se mide contra algo fijo (INCIBE fase 1 sellada).
    if not plan.baseline_sealed_at:
        seal_baseline(db, plan)
    db.flush()
    return True


def record_decision(db: Session, approval: PlanApproval, *, decision: str,
                    user_id: int | None = None, notes: str | None = None,
                    ip_address: str | None = None) -> dict:
    """Registra la decision de un aprobador y cierra la ronda si procede."""
    if approval.status != "pending":
        raise ValueError("Esta aprobacion ya fue resuelta.")
    if approval.expires_at and approval.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        approval.status = "cancelled"
        db.flush()
        raise ValueError("La solicitud de aprobacion ha caducado.")

    approval.status = "approved" if decision == "approved" else "rejected"
    approval.responded_at = datetime.now(timezone.utc)
    approval.approved_by_id = user_id
    approval.ip_address = ip_address
    if notes:
        approval.response_notes = notes
    db.flush()

    plan = db.get(StrategicPlan, approval.plan_id)
    round_approvals = db.query(PlanApproval).filter(
        PlanApproval.plan_id == approval.plan_id,
        PlanApproval.plan_version == approval.plan_version,
        PlanApproval.status.in_(["pending", "approved", "rejected"]),
    ).all()

    if approval.status == "rejected":
        plan.status = "draft"
        db.flush()
        return {"plan_status": plan.status, "approved": False, "rejected": True}

    approved = _finalise_plan(db, plan, round_approvals)
    return {
        "plan_status": plan.status,
        "approved": approved,
        "rejected": False,
        "pending": sum(1 for a in round_approvals if a.status == "pending"),
    }


def approval_integrity(db: Session, plan: StrategicPlan) -> dict:
    """Comprueba si lo aprobado sigue siendo lo que hay.

    No bloquea nada: informa. Que el plan haya cambiado despues de aprobarse es
    justo lo que un auditor quiere ver, no algo que deba ocultarse.
    """
    approvals = db.query(PlanApproval).filter(
        PlanApproval.plan_id == plan.id, PlanApproval.status == "approved",
    ).order_by(PlanApproval.responded_at.desc()).all()
    if not approvals:
        return {"approved": False, "drifted": False, "approved_version": None}
    approved_hash = approvals[0].content_hash
    return {
        "approved": True,
        "approved_version": approvals[0].plan_version,
        "approved_at": approvals[0].responded_at.isoformat() if approvals[0].responded_at else None,
        "mode": approvals[0].mode,
        "drifted": bool(approved_hash and approved_hash != compute_content_hash(db, plan)),
        "approvers": [
            {"name": a.approver_name, "email": a.approver_email,
             "responded_at": a.responded_at.isoformat() if a.responded_at else None,
             "mode": a.mode}
            for a in approvals
        ],
    }
