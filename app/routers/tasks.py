"""Plan de tratamiento — tareas Kanban (M3)."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import TreatmentTask, TaskStatus, User
from app.schemas import TaskIn, TaskOut, TaskUpdate
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _update_risk_treatment_progress(db: Session, task) -> None:
    """Cuando una tarea cambia de estado, actualiza treatment_progress del riesgo vinculado.

    Bucle cerrado: todas las tareas DONE → risk.treatment_progress=100 → risk.status=TREATED
    """
    if not getattr(task, "risk_id", None):
        return
    from app.models import Risk, TreatmentTask, RiskStatus
    risk = db.get(Risk, task.risk_id)
    if not risk:
        return

    # Calcular progreso: tareas DONE / total tareas del riesgo
    all_tasks = db.query(TreatmentTask).filter(
        TreatmentTask.risk_id == task.risk_id,
    ).all()
    if not all_tasks:
        return

    done_statuses = {"done", "completed", "closed"}
    # Adaptar a los valores reales del enum TaskStatus
    done_count = sum(
        1 for t in all_tasks
        if str(getattr(t.status, "value", t.status)).lower() in done_statuses
    )
    total = len(all_tasks)
    progress = round(done_count / total * 100)
    risk.treatment_progress = progress

    # Bucle cerrado: si todas las tareas completadas → cambiar riesgo a TREATED
    if progress >= 100:
        treated_statuses = {"treated", "pending_acceptance", "accepted", "closed"}
        current_status = str(getattr(risk.status, "value", risk.status)).lower()
        if current_status not in treated_statuses:
            try:
                risk.status = RiskStatus.TREATED
            except Exception:
                pass  # si el enum no tiene TREATED, no forzar

        # Bucle cerrado: reducir residual_likelihood si hay plan documentado
        if risk.treatment_plan and risk.residual_likelihood and risk.residual_likelihood > 0:
            risk.residual_likelihood = max(0, risk.residual_likelihood - 1)
            try:
                from app.routers.risks import _recalc
                _recalc(db, risk)
            except Exception:
                pass

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        import logging
        logging.getLogger(__name__).warning("treatment_progress update failed: %s", e)


def _next_code(db: Session, org_id: int) -> str:
    n = db.query(TreatmentTask).filter(TreatmentTask.organization_id == org_id).count() + 1
    return f"TSK-{n:04d}"


@router.get("/", response_model=list[TaskOut])
def list_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: Optional[TaskStatus] = None,
    risk_id: Optional[int] = None,
    assigned_to_id: Optional[int] = None,
    overdue: Optional[bool] = None,
):
    q = filter_by_org(db.query(TreatmentTask), TreatmentTask, current_user)
    if status:
        q = q.filter(TreatmentTask.status == status)
    if risk_id:
        q = q.filter(TreatmentTask.risk_id == risk_id)
    if assigned_to_id:
        q = q.filter(TreatmentTask.assigned_to_id == assigned_to_id)
    if overdue:
        now = datetime.now(timezone.utc)
        q = q.filter(
            TreatmentTask.due_date.isnot(None),
            TreatmentTask.due_date < now,
            TreatmentTask.status != TaskStatus.DONE,
        )
    return q.order_by(TreatmentTask.created_at.desc()).all()


@router.get("/stats/summary")
def tasks_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tasks = filter_by_org(db.query(TreatmentTask), TreatmentTask, current_user).all()
    now = datetime.now(timezone.utc)
    overdue = sum(
        1 for t in tasks
        if t.due_date and t.status != TaskStatus.DONE
        and t.due_date.replace(tzinfo=timezone.utc) < now
    )
    by_status = {}
    for s in TaskStatus:
        by_status[s.value] = sum(1 for t in tasks if t.status == s)
    return {
        "total": len(tasks),
        "overdue": overdue,
        "by_status": by_status,
    }


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, request: Request, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    lang = get_lang(request)
    t = db.query(TreatmentTask).filter(TreatmentTask.id == task_id).first()
    if not t or not check_org_access(t.organization_id, current_user):
        raise HTTPException(404, _t("tasks.not_found", lang))
    return t


@router.post("/", response_model=TaskOut)
def create_task(body: TaskIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    org_id = current_user.organization_id
    t = TreatmentTask(
        code=_next_code(db, org_id),
        organization_id=org_id,
        title=body.title,
        description=body.description,
        risk_id=body.risk_id,
        assigned_to_id=body.assigned_to_id,
        created_by_id=current_user.id,
        status=body.status,
        priority=body.priority,
        due_date=body.due_date,
        notes=body.notes,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    log_action(db, current_user.id, "create", "task", str(t.id), {"code": t.code})
    return t


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: int, body: TaskUpdate, request: Request,
                db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    t = db.query(TreatmentTask).filter(TreatmentTask.id == task_id).first()
    if not t or not check_org_access(t.organization_id, current_user):
        raise HTTPException(404, _t("tasks.not_found", lang))
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(t, field, value)
    db.commit()
    db.refresh(t)
    _update_risk_treatment_progress(db, t)
    log_action(db, current_user.id, "update", "task", str(t.id))
    return t


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, request: Request, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    t = db.query(TreatmentTask).filter(TreatmentTask.id == task_id).first()
    if not t or not check_org_access(t.organization_id, current_user):
        raise HTTPException(404, _t("tasks.not_found", lang))
    log_action(db, current_user.id, "delete", "task", str(task_id), {"code": t.code})
    db.delete(t)
    db.commit()
