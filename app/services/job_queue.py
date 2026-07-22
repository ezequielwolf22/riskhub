"""Cola de trabajos asincrona persistida en BD.

Sin dependencias externas (compatible on-premise con SQLite): los jobs se
persisten en la tabla background_jobs y un pool pequeno de workers en hilos
los ejecuta. Frente a los hilos sueltos / BackgroundTasks:

  - sobreviven a reinicios (recovery: running -> pending al arrancar)
  - reintentos con backoff exponencial y limite de intentos
  - dedupe opcional (no encolar dos veces el mismo trabajo pendiente)
  - estado consultable via /api/jobs

Uso:
    from app.services.job_queue import enqueue
    enqueue(db, org_id, "asset_analysis_all", {"org_id": org_id})

Los handlers se registran en _HANDLERS: reciben (payload: dict) y devuelven
un dict serializable como resultado. Cada ejecucion abre su propia sesion.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_WORKERS = 2
_POLL_INTERVAL_S = 3.0
_RETRY_BASE_S = 60  # backoff: 60s, 120s, 240s...

_claim_lock = threading.Lock()
_started = False
_stop = threading.Event()


def is_cancelled(job_id: int) -> bool:
    """Consulta fresca del estado: los handlers largos la usan entre lotes
    para abortar de forma cooperativa cuando el usuario cancela el job."""
    from app.database import SessionLocal
    from app.models import BackgroundJob
    db = SessionLocal()
    try:
        status = db.query(BackgroundJob.status).filter(BackgroundJob.id == job_id).scalar()
        return status == "cancelled"
    finally:
        db.close()


# ---------- Handlers ----------

def _handle_asset_analysis_all(payload: dict) -> dict:
    from app.database import SessionLocal
    from app.services.asset_risk_analysis_service import analyze_all_org_assets
    job_id = payload.get("_job_id")
    cancel_check = (lambda: is_cancelled(job_id)) if job_id else None
    db = SessionLocal()
    try:
        result = analyze_all_org_assets(
            db, payload["org_id"],
            representatives_only=bool(payload.get("representatives_only", False)),
            cancel_check=cancel_check,
        )
        return result if isinstance(result, dict) else {"total": result}
    finally:
        db.close()


def _handle_evidence_analysis(payload: dict) -> dict:
    from app.services.evidence_understanding_service import run_analysis_for_evidence
    run_analysis_for_evidence(payload["evidence_id"])
    return {"evidence_id": payload["evidence_id"]}


def _handle_document_vision_isms(payload: dict) -> dict:
    from app.routers.documents import _run_isms_analysis_bg
    from app.services.document_service import describe_document_with_vision
    doc_id = payload["doc_id"]
    transcribed = describe_document_with_vision(doc_id)
    if transcribed:
        _run_isms_analysis_bg(doc_id)
    return {"doc_id": doc_id, "transcribed": transcribed}


def _handle_ingest_pack(payload: dict) -> dict:
    """Comprension y volcado de un pack documental.

    Los bytes no viajan en el payload: el router los dejo en un area de paso y
    aqui se leen y se borran al terminar, pase lo que pase.
    """
    from pathlib import Path

    from app.database import SessionLocal
    from app.routers.ingest import cleanup_staging
    from app.services.ingest.pipeline import run_pack

    job_id = payload.get("_job_id")
    cancel_check = (lambda: is_cancelled(job_id)) if job_id else None

    files = []
    for entry in payload.get("paths") or []:
        path = Path(entry["path"])
        if path.exists():
            files.append((entry["filename"], path.read_bytes()))

    db = SessionLocal()
    try:
        return run_pack(
            db, payload["org_id"], files,
            user_id=payload.get("user_id"), job_id=job_id,
            tier=payload.get("tier", "deep"), lang=payload.get("lang", "es"),
            apply_profile=bool(payload.get("apply_profile", True)),
            cancel_check=cancel_check,
        )
    finally:
        db.close()
        cleanup_staging(payload.get("staging_dir"))


_HANDLERS: dict[str, Callable[[dict], dict]] = {
    "asset_analysis_all": _handle_asset_analysis_all,
    "evidence_analysis": _handle_evidence_analysis,
    "document_vision_isms": _handle_document_vision_isms,
    "ingest_pack": _handle_ingest_pack,
}


# ---------- API ----------

def enqueue(db, org_id: Optional[int], job_type: str, payload: dict,
            created_by_id: int | None = None, dedupe_key: str | None = None,
            priority: int = 5, max_attempts: int = 3):
    """Encola un trabajo. Con dedupe_key, no duplica si ya hay uno en cola.

    Devuelve el BackgroundJob (existente si dedupe). No hace commit: el
    caller decide la transaccion.
    """
    from app.models import BackgroundJob
    if job_type not in _HANDLERS:
        raise ValueError(f"job_type desconocido: {job_type}")

    if dedupe_key:
        existing = (
            db.query(BackgroundJob)
            .filter(
                BackgroundJob.dedupe_key == dedupe_key,
                BackgroundJob.status.in_(["pending", "running"]),
            ).first()
        )
        if existing:
            return existing

    job = BackgroundJob(
        organization_id=org_id,
        job_type=job_type,
        payload=payload,
        status="pending",
        priority=priority,
        max_attempts=max_attempts,
        next_attempt_at=datetime.now(timezone.utc),
        dedupe_key=dedupe_key,
        created_by_id=created_by_id,
    )
    db.add(job)
    db.flush()
    return job


def job_out(job) -> dict:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "result": job.result,
        "error": (job.error or "")[:500] or None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


# ---------- Worker ----------

def _claim_next():
    """Reclama atomicamente el siguiente job pendiente (o None)."""
    from app.database import SessionLocal
    from app.models import BackgroundJob
    with _claim_lock:
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            job = (
                db.query(BackgroundJob)
                .filter(
                    BackgroundJob.status == "pending",
                    (BackgroundJob.next_attempt_at.is_(None))
                    | (BackgroundJob.next_attempt_at <= now),
                )
                .order_by(BackgroundJob.priority, BackgroundJob.id)
                .first()
            )
            if not job:
                return None
            job.status = "running"
            job.attempts = (job.attempts or 0) + 1
            job.started_at = now
            db.commit()
            return job.id
        except Exception:
            db.rollback()
            return None
        finally:
            db.close()


def _finish(job_id: int, *, result: dict | None = None, error: str | None = None) -> None:
    from app.database import SessionLocal
    from app.models import BackgroundJob
    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id)
        if not job:
            return
        now = datetime.now(timezone.utc)
        if job.status == "cancelled":
            # Cancelado por el usuario mientras corria: respetar el estado,
            # no convertirlo en done/pending/error
            job.finished_at = job.finished_at or now
            db.commit()
            return
        if error is None:
            job.status = "done"
            job.result = result or {}
            job.finished_at = now
        elif (job.attempts or 0) < (job.max_attempts or 1):
            # Reintento con backoff exponencial
            wait = _RETRY_BASE_S * (2 ** max(0, (job.attempts or 1) - 1))
            job.status = "pending"
            job.error = error[:2000]
            job.next_attempt_at = now + timedelta(seconds=wait)
            logger.warning("job %d (%s) fallo (intento %d/%d), reintento en %ds",
                           job.id, job.job_type, job.attempts, job.max_attempts, wait)
        else:
            job.status = "error"
            job.error = error[:2000]
            job.finished_at = now
            logger.error("job %d (%s) agoto reintentos: %s",
                         job.id, job.job_type, error[:200])
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("job_queue: no se pudo cerrar el job %d", job_id)
    finally:
        db.close()


def _run_job(job_id: int) -> None:
    from app.database import SessionLocal
    from app.models import BackgroundJob
    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id)
        if not job:
            return
        job_type, payload = job.job_type, dict(job.payload or {})
        # El handler conoce su job para poder consultar la cancelacion
        payload["_job_id"] = job_id
    finally:
        db.close()

    handler = _HANDLERS.get(job_type)
    if handler is None:
        _finish(job_id, error=f"handler no registrado: {job_type}")
        return
    try:
        result = handler(payload)
        _finish(job_id, result=result)
    except Exception as exc:
        _finish(job_id, error=f"{type(exc).__name__}: {exc}")


def _worker_loop(worker_idx: int) -> None:
    logger.info("job_queue: worker %d iniciado", worker_idx)
    while not _stop.is_set():
        try:
            job_id = _claim_next()
            if job_id is None:
                _stop.wait(_POLL_INTERVAL_S)
                continue
            _run_job(job_id)
        except Exception:
            logger.exception("job_queue: error en worker %d", worker_idx)
            _stop.wait(_POLL_INTERVAL_S)


def _recover_stale() -> None:
    """Jobs que quedaron 'running' tras un reinicio -> pending de nuevo."""
    from app.database import SessionLocal
    from app.models import BackgroundJob
    db = SessionLocal()
    try:
        n = (
            db.query(BackgroundJob)
            .filter(BackgroundJob.status == "running")
            .update({"status": "pending",
                     "next_attempt_at": datetime.now(timezone.utc)},
                    synchronize_session=False)
        )
        db.commit()
        if n:
            logger.info("job_queue: %d jobs 'running' recuperados a pending", n)
    except Exception:
        db.rollback()
    finally:
        db.close()


def start(workers: int = _WORKERS) -> None:
    """Arranca los workers (idempotente). Llamar una vez en startup."""
    global _started
    if _started:
        return
    _started = True
    _recover_stale()
    for i in range(workers):
        threading.Thread(target=_worker_loop, args=(i,), daemon=True,
                         name=f"job-worker-{i}").start()
    logger.info("job_queue: %d workers arrancados", workers)
