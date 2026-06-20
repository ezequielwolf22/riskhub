"""No conformidades y acciones correctivas — ISO 27001:2022 cl. 10.1."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NCStatus, NCSeverity, NonConformity, User
from app.schemas import NonConformityIn, NonConformityOut, NonConformityUpdate
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/nonconformities", tags=["nonconformities"])


def _apply_nc_control_penalty(db: Session, control_id: int, org_id: int,
                               penalty: Optional[float]) -> None:
    """Aplica o elimina penalizacion de NC major en la implementacion del control.

    penalty=0.4 cuando NC major se abre; penalty=None cuando la NC se cierra.
    Dispara cascade recalc de todos los riesgos vinculados al control.
    """
    from app.models import ControlImplementation
    from app.routers.controls import _trigger_linked_risks_recalc

    ci = db.query(ControlImplementation).filter(
        ControlImplementation.control_id == control_id,
        ControlImplementation.organization_id == org_id,
    ).first()
    if not ci:
        return
    ci.nc_penalty_factor = penalty
    db.flush()
    _trigger_linked_risks_recalc(ci.id, org_id)


def _next_code(db: Session, org_id: int) -> str:
    n = db.query(NonConformity).filter(NonConformity.organization_id == org_id).count() + 1
    return f"NC-{n:04d}"


@router.get("/", response_model=list[NonConformityOut])
def list_ncs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: Optional[NCStatus] = None,
    severity: Optional[str] = None,
):
    q = filter_by_org(db.query(NonConformity), NonConformity, current_user)
    if status:
        q = q.filter(NonConformity.status == status)
    if severity:
        q = q.filter(NonConformity.severity == severity)
    return q.order_by(NonConformity.created_at.desc()).all()


@router.get("/stats/summary")
def nc_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ncs = filter_by_org(db.query(NonConformity), NonConformity, current_user).all()
    now = datetime.now(timezone.utc)
    open_count = sum(1 for n in ncs if n.status != NCStatus.CLOSED)
    major_open = sum(1 for n in ncs if n.severity == "major" and n.status != NCStatus.CLOSED)
    overdue = sum(
        1 for n in ncs
        if n.due_date and n.status != NCStatus.CLOSED
        and n.due_date.replace(tzinfo=timezone.utc) < now
    )
    return {
        "total": len(ncs),
        "open": open_count,
        "major_open": major_open,
        "overdue": overdue,
    }


@router.get("/{nc_id}", response_model=NonConformityOut)
def get_nc(nc_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    nc = db.query(NonConformity).filter(NonConformity.id == nc_id).first()
    if not nc or not check_org_access(nc.organization_id, current_user):
        raise HTTPException(404, "No conformidad no encontrada")
    return nc


@router.post("/", response_model=NonConformityOut)
def create_nc(body: NonConformityIn, db: Session = Depends(get_db),
              current_user: User = Depends(require_analyst)):
    org_id = current_user.organization_id
    nc = NonConformity(
        code=_next_code(db, org_id),
        organization_id=org_id,
        title=body.title,
        description=body.description,
        source=body.source,
        severity=body.severity,
        iso_clause=body.iso_clause,
        root_cause=body.root_cause,
        corrective_action=body.corrective_action,
        due_date=body.due_date,
        evidence=body.evidence,
        owner_id=body.owner_id,
        related_control_id=body.related_control_id,
        related_risk_id=body.related_risk_id,
    )
    db.add(nc)
    db.commit()
    db.refresh(nc)
    # NC major con control relacionado → penalizar contribution para recalculo de residual
    if nc.severity == NCSeverity.MAJOR and nc.related_control_id:
        try:
            _apply_nc_control_penalty(db, nc.related_control_id, org_id, penalty=0.4)
            db.commit()
        except Exception as _exc:
            import logging
            logging.getLogger(__name__).warning("NC penalty apply failed: %s", _exc)
    # Auto-vincular riesgo relacionado si la NC menciona un control o clausula ISO (v1.7.7)
    try:
        if not nc.related_risk_id:
            from app.models import Risk, RiskStatus, ControlImplementation
            from sqlalchemy import text as _text
            candidate_risk = None

            # Si hay control relacionado, buscar el riesgo activo de mayor nivel que lo usa
            if nc.related_control_id:
                impl = db.query(ControlImplementation).filter(
                    ControlImplementation.control_id == nc.related_control_id,
                    ControlImplementation.organization_id == current_user.organization_id,
                ).first()
                if impl:
                    row = db.execute(
                        _text("SELECT risk_id FROM risk_controls WHERE control_implementation_id = :cid LIMIT 1"),
                        {"cid": impl.id},
                    ).first()
                    if row:
                        candidate_risk = db.get(Risk, row[0])

            # Fallback: buscar el riesgo activo de mayor nivel de la org
            if not candidate_risk:
                candidate_risk = db.query(Risk).filter(
                    Risk.organization_id == current_user.organization_id,
                    Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
                ).order_by(Risk.residual_level.desc()).first()

            if candidate_risk:
                nc.related_risk_id = candidate_risk.id
                db.commit()
    except Exception as _exc:
        import logging
        logging.getLogger(__name__).warning("NC->risk auto-link failed: %s", _exc)
    log_action(db, current_user.id, "create", "nonconformity", str(nc.id),
               {"code": nc.code, "severity": nc.severity.value})
    return nc


@router.patch("/{nc_id}", response_model=NonConformityOut)
def update_nc(nc_id: int, body: NonConformityUpdate,
              background_tasks: BackgroundTasks,
              db: Session = Depends(get_db),
              current_user: User = Depends(require_analyst)):
    nc = db.query(NonConformity).filter(NonConformity.id == nc_id).first()
    if not nc or not check_org_access(nc.organization_id, current_user):
        raise HTTPException(404, "No conformidad no encontrada")
    update_data = body.model_dump(exclude_none=True)
    # Si se cierra la NC, registrar fecha de cierre
    old_severity = nc.severity
    closing = update_data.get("status") == NCStatus.CLOSED and not nc.closed_at
    if closing:
        update_data["closed_at"] = datetime.now(timezone.utc)
    for field, value in update_data.items():
        setattr(nc, field, value)
    db.commit()
    db.refresh(nc)

    # NC cerrada → restaurar penalizacion del control (quitar factor)
    if closing and nc.related_control_id:
        try:
            _apply_nc_control_penalty(db, nc.related_control_id, nc.organization_id, penalty=None)
            db.commit()
        except Exception as _exc:
            import logging
            logging.getLogger(__name__).warning("NC penalty restore failed: %s", _exc)

    # NC cambia a major con control → aplicar penalizacion
    new_severity = update_data.get("severity")
    if (new_severity == NCSeverity.MAJOR and old_severity != NCSeverity.MAJOR
            and nc.related_control_id and not closing):
        try:
            _apply_nc_control_penalty(db, nc.related_control_id, nc.organization_id, penalty=0.4)
            db.commit()
        except Exception as _exc:
            import logging
            logging.getLogger(__name__).warning("NC severity→major penalty failed: %s", _exc)

    # NC cerrada con control asociado → re-ejecutar CCM en background
    if closing and nc.related_control_id:
        from app.services.ccm_service import run_single_test_for_control
        background_tasks.add_task(
            run_single_test_for_control, nc.related_control_id, nc.organization_id
        )

    log_action(db, current_user.id, "update", "nonconformity", str(nc.id))
    return nc


@router.delete("/{nc_id}", status_code=204)
def delete_nc(nc_id: int, db: Session = Depends(get_db),
              current_user: User = Depends(require_analyst)):
    nc = db.query(NonConformity).filter(NonConformity.id == nc_id).first()
    if not nc or not check_org_access(nc.organization_id, current_user):
        raise HTTPException(404, "No conformidad no encontrada")
    log_action(db, current_user.id, "delete", "nonconformity", str(nc_id), {"code": nc.code})
    db.delete(nc)
    db.commit()
