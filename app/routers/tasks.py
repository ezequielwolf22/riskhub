"""Plan de tratamiento — tareas Kanban (M3)."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TreatmentTask, TaskStatus, User
from app.schemas import TaskIn, TaskOut, TaskUpdate
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


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
def get_task(task_id: int, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    t = db.query(TreatmentTask).filter(TreatmentTask.id == task_id).first()
    if not t or not check_org_access(t.organization_id, current_user):
        raise HTTPException(404, "Tarea no encontrada")
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
def update_task(task_id: int, body: TaskUpdate,
                db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    t = db.query(TreatmentTask).filter(TreatmentTask.id == task_id).first()
    if not t or not check_org_access(t.organization_id, current_user):
        raise HTTPException(404, "Tarea no encontrada")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(t, field, value)
    db.commit()
    db.refresh(t)
    log_action(db, current_user.id, "update", "task", str(t.id))
    return t


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    t = db.query(TreatmentTask).filter(TreatmentTask.id == task_id).first()
    if not t or not check_org_access(t.organization_id, current_user):
        raise HTTPException(404, "Tarea no encontrada")
    log_action(db, current_user.id, "delete", "task", str(task_id), {"code": t.code})
    db.delete(t)
    db.commit()
