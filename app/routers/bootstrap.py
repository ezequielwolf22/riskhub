"""Endpoint de arranque: agrega en una sola llamada los datos que necesita
el shell de la app al iniciar (badges, feature flags, risk levels).

Sustituye ~7 llamadas independientes que el frontend hacia en paralelo al
arrancar, reduciendo la latencia de primer render visible.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func as _func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Risk, RiskStatus, TreatmentTask, TaskStatus, FeatureFlag, RiskLevelConfig, NIS2Notification
from app.security import get_current_user
from app.models import User
from app.routers.feature_flags import get_flags_for_org

router = APIRouter(prefix="/api/app", tags=["bootstrap"])


@router.get("/bootstrap")
def bootstrap(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Datos de arranque del shell: feature flags + badges de sidebar + risk level config."""
    org_id = getattr(current_user, "organization_id", None)
    now = datetime.now(timezone.utc)

    # --- Feature flags ---
    try:
        flags = get_flags_for_org(db, org_id)
    except Exception:
        flags = {}

    # --- Risk level config ---
    try:
        rl_rows = db.query(RiskLevelConfig).filter(
            RiskLevelConfig.organization_id == org_id
        ).order_by(RiskLevelConfig.order).all()
        risk_levels = [
            {
                "code": r.code, "label": r.label,
                "min_level": r.min_level, "max_level": r.max_level,
                "color": r.color, "order": r.order,
            }
            for r in rl_rows
        ] if rl_rows else []
    except Exception:
        risk_levels = []

    # --- Badge: tratamientos vencidos ---
    try:
        active_statuses = [RiskStatus.IDENTIFIED.value, RiskStatus.ASSESSED.value]
        q = db.query(_func.count(Risk.id)).filter(
            Risk.status.in_(active_statuses),
            Risk.treatment_due_date.isnot(None),
            Risk.treatment_due_date < now,
        )
        if org_id:
            q = q.filter(Risk.organization_id == org_id)
        overdue_treatments = q.scalar() or 0
    except Exception:
        overdue_treatments = 0

    # --- Badge: controles con revision vencida ---
    try:
        from app.models import ControlImplementation
        q2 = db.query(_func.count(ControlImplementation.id)).filter(
            ControlImplementation.next_review_date.isnot(None),
            ControlImplementation.next_review_date < now,
        )
        if org_id:
            q2 = q2.filter(ControlImplementation.organization_id == org_id)
        controls_overdue_reviews = q2.scalar() or 0
    except Exception:
        controls_overdue_reviews = 0

    # --- Badge: tareas vencidas ---
    try:
        open_statuses = [TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]
        q3 = db.query(_func.count(TreatmentTask.id)).filter(
            TreatmentTask.status.in_(open_statuses),
            TreatmentTask.due_date.isnot(None),
            TreatmentTask.due_date < now,
        )
        if org_id:
            q3 = q3.filter(TreatmentTask.organization_id == org_id)
        tasks_overdue = q3.scalar() or 0
    except Exception:
        tasks_overdue = 0

    # --- Badge: NIS2 urgentes ---
    try:
        q4 = db.query(_func.count(NIS2Notification.id)).filter(
            NIS2Notification.status == "pending",
            NIS2Notification.deadline < now,
        )
        if org_id:
            q4 = q4.filter(NIS2Notification.organization_id == org_id)
        nis2_urgent = q4.scalar() or 0
    except Exception:
        nis2_urgent = 0

    return {
        "flags": flags,
        "risk_levels": risk_levels,
        "badges": {
            "overdue_treatments": overdue_treatments,
            "controls_overdue_reviews": controls_overdue_reviews,
            "tasks_overdue": tasks_overdue,
            "nis2_urgent": nis2_urgent,
            "notif_total": tasks_overdue + nis2_urgent,
        },
    }
