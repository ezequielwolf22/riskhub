"""Consulta y gestion de trabajos asincronos (cola persistida en BD)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BackgroundJob, User
from app.security import get_current_user, require_analyst
from app.services.job_queue import job_out

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    status: str | None = Query(None),
    job_type: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista los trabajos de la organizacion (mas recientes primero)."""
    q = db.query(BackgroundJob).filter(
        BackgroundJob.organization_id == current_user.organization_id
    )
    if status:
        q = q.filter(BackgroundJob.status == status)
    if job_type:
        q = q.filter(BackgroundJob.job_type == job_type)
    jobs = q.order_by(BackgroundJob.id.desc()).limit(limit).all()
    return [job_out(j) for j in jobs]


@router.get("/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.get(BackgroundJob, job_id)
    if not job or job.organization_id != current_user.organization_id:
        raise HTTPException(404, "Trabajo no encontrado")
    return job_out(job)


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Cancela un trabajo pendiente o en ejecucion.

    Los handlers largos (analisis IA masivo) comprueban la cancelacion entre
    lotes y abortan: como mucho terminan las llamadas en vuelo.
    """
    job = db.get(BackgroundJob, job_id)
    if not job or job.organization_id != current_user.organization_id:
        raise HTTPException(404, "Trabajo no encontrado")
    if job.status not in ("pending", "running"):
        raise HTTPException(409, f"El trabajo ya termino (estado: {job.status})")
    job.status = "cancelled"
    job.error = "cancelado por el usuario"
    db.commit()
    return job_out(job)
