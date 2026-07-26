"""Router de ingesta cognitiva — subir un pack y que el agente lo vuelque.

Ademas de lanzar la ingesta, expone lo que la hace fiable: el "como lo entendi"
de cada documento, los conflictos entre fuentes, y las dos formas de dar marcha
atras (deshacer un lote entero o revertir un registro suelto). Forzar un valor
a mano tambien vive aqui, porque es la garantia de que la ultima palabra la
tiene el usuario.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import (IngestBatch, IngestConflict, IngestFieldOverride,
                        IngestRecordTrace, IngestSourceMap, OrganizationProfile, User)
from app.security import get_current_user, require_admin, require_analyst
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.ingest.router")

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_PACK_FILES = 40


def _org(u: User, lang: str = "es") -> int:
    if not u.organization_id:
        raise HTTPException(400, _t("ingest.user_no_org", lang))
    return u.organization_id


def _staging_root(org_id: int) -> Path:
    from app.routers.bcp import _bcm_data_root
    return _bcm_data_root("ingest_staging") / str(org_id)


async def _collect(files: List[UploadFile], lang: str) -> list[tuple[str, bytes]]:
    if not files:
        raise HTTPException(422, _t("ingest.no_files", lang))
    if len(files) > MAX_PACK_FILES:
        raise HTTPException(422, _t("ingest.too_many_files", lang, max=MAX_PACK_FILES))
    out = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(413, _t("ingest.file_too_large", lang,
                                        name=f.filename, mb=MAX_FILE_BYTES // 1048576))
        if not data:
            continue
        out.append((f.filename or "sin_nombre", data))
    if not out:
        raise HTTPException(422, _t("ingest.no_files", lang))
    return out


# ── Estimacion previa ────────────────────────────────────────────────────────

@router.post("/estimate")
async def estimate(request: Request, files: List[UploadFile] = File(...),
                   tier: str = "deep", db: Session = Depends(get_db),
                   u: User = Depends(require_analyst)):
    """Que hay en el pack y cuanto costaria comprenderlo. No llama a la IA."""
    from app.services.ingest.pipeline import estimate_pack
    lang = get_lang(request)
    collected = await _collect(files, lang)
    return estimate_pack(collected, tier if tier in ("deep", "fast") else "deep")


# ── Lanzar la ingesta ────────────────────────────────────────────────────────

@router.post("/pack", status_code=202)
async def ingest_pack(request: Request, files: List[UploadFile] = File(...),
                      tier: str = "deep", apply_profile: bool = True,
                      db: Session = Depends(get_db),
                      u: User = Depends(require_analyst)):
    """Encola la comprension del pack. Devuelve el job para seguir el progreso."""
    from app.services.job_queue import enqueue
    lang = get_lang(request)
    org = _org(u, lang)
    collected = await _collect(files, lang)

    # Los bytes no caben en el payload del job: se dejan en un area de paso que
    # el worker lee y borra al terminar.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    staging = _staging_root(org) / stamp
    staging.mkdir(parents=True, exist_ok=True)
    paths = []
    for filename, data in collected:
        safe = Path(filename).name or "documento"
        target = staging / f"{hashlib.sha256(data).hexdigest()[:12]}_{safe}"
        target.write_bytes(data)
        paths.append({"filename": safe, "path": str(target)})

    job = enqueue(db, org, "ingest_pack", {
        "org_id": org, "user_id": u.id, "paths": paths,
        "tier": tier if tier in ("deep", "fast") else "deep",
        "lang": lang, "apply_profile": bool(apply_profile),
        "staging_dir": str(staging),
    }, created_by_id=u.id, priority=3, max_attempts=1)
    db.commit()

    log_action(db, u.id, "ingest", "ingest_pack", str(job.id),
               {"files": len(paths)})
    return {"job_id": job.id, "files": len(paths),
            "message": _t("ingest.queued", lang, n=len(paths))}


# ── Lotes ────────────────────────────────────────────────────────────────────

def _batch_d(b: IngestBatch) -> dict:
    return {
        "id": b.id, "module": b.module, "status": b.status, "job_id": b.job_id,
        "files": b.files, "summary": b.summary,
        "estimated_cost_usd": b.estimated_cost_usd,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "completed_at": b.completed_at.isoformat() if b.completed_at else None,
        "undone_at": b.undone_at.isoformat() if b.undone_at else None,
    }


@router.get("/batches")
def list_batches(limit: int = 25, db: Session = Depends(get_db),
                 u: User = Depends(get_current_user)):
    rows = db.query(IngestBatch).filter_by(organization_id=_org(u)).order_by(
        IngestBatch.id.desc()).limit(min(limit, 100)).all()
    return [_batch_d(b) for b in rows]


def _chk_batch(db, bid: int, org_id: int, lang: str) -> IngestBatch:
    b = db.get(IngestBatch, bid)
    if not b or b.organization_id != org_id:
        raise HTTPException(404, _t("ingest.batch_not_found", lang))
    return b


@router.get("/batches/{bid}")
def get_batch(bid: int, request: Request, db: Session = Depends(get_db),
              u: User = Depends(get_current_user)):
    lang = get_lang(request)
    org = _org(u, lang)
    b = _chk_batch(db, bid, org, lang)
    maps = db.query(IngestSourceMap).filter_by(batch_id=bid).all()
    conflicts = db.query(IngestConflict).filter_by(batch_id=bid).count()
    return {
        **_batch_d(b),
        "source_maps": [_map_d(m) for m in maps],
        "conflicts_total": conflicts,
        "profile_proposal": b.profile_diff,
    }


@router.get("/batches/{bid}/records")
def list_records(bid: int, request: Request, needs_review: Optional[bool] = None,
                 db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    """Registros tocados por el lote. Con needs_review, solo lo dudoso."""
    lang = get_lang(request)
    org = _org(u, lang)
    _chk_batch(db, bid, org, lang)
    q = db.query(IngestRecordTrace).filter_by(batch_id=bid)
    if needs_review is not None:
        q = q.filter(IngestRecordTrace.needs_review.is_(needs_review))
    return [{
        "id": t.id, "entity": t.entity, "table_name": t.table_name,
        "record_id": t.record_id, "action": t.action,
        "confidence": t.confidence, "needs_review": t.needs_review,
        "after": t.after, "before": t.before,
        "reverted_at": t.reverted_at.isoformat() if t.reverted_at else None,
    } for t in q.order_by(IngestRecordTrace.id).limit(500).all()]


@router.post("/batches/{bid}/undo")
def undo(bid: int, request: Request, db: Session = Depends(get_db),
         u: User = Depends(require_admin)):
    """Deshace el lote completo y deja la base como estaba."""
    from app.services.ingest.batch import undo_batch
    lang = get_lang(request)
    org = _org(u, lang)
    b = _chk_batch(db, bid, org, lang)
    result = undo_batch(db, b, user_id=u.id)
    log_action(db, u.id, "undo", "ingest_batch", str(bid), result)
    return result


@router.post("/records/{trace_id}/revert")
def revert(trace_id: int, request: Request, db: Session = Depends(get_db),
           u: User = Depends(require_analyst)):
    """Revierte un unico registro sin tocar el resto del lote."""
    from app.services.ingest.batch import revert_record
    lang = get_lang(request)
    org = _org(u, lang)
    t = db.get(IngestRecordTrace, trace_id)
    if not t or t.organization_id != org:
        raise HTTPException(404, _t("ingest.record_not_found", lang))
    if t.reverted_at:
        raise HTTPException(409, _t("ingest.record_already_reverted", lang))
    ok = revert_record(db, t, user_id=u.id)
    db.commit()
    log_action(db, u.id, "revert", t.table_name, str(t.record_id), {"trace": trace_id})
    return {"reverted": ok, "trace_id": trace_id}


@router.post("/records/{trace_id}/restore")
def restore(trace_id: int, request: Request, db: Session = Depends(get_db),
            u: User = Depends(require_analyst)):
    """Rehace un registro deshecho: deshacer nunca es la ultima palabra."""
    from app.services.ingest.batch import restore_record
    lang = get_lang(request)
    org = _org(u, lang)
    t = _chk_trace(db, trace_id, org, lang)
    if not t.reverted_at:
        raise HTTPException(409, _t("ingest.record_not_reverted", lang))
    ok = restore_record(db, t, user_id=u.id)
    db.commit()
    log_action(db, u.id, "restore", t.table_name, str(t.record_id), {"trace": trace_id})
    return {"restored": ok, "trace_id": trace_id}


class RecordEditIn(BaseModel):
    fields: dict


def _chk_trace(db, trace_id: int, org_id: int, lang: str) -> IngestRecordTrace:
    t = db.get(IngestRecordTrace, trace_id)
    if not t or t.organization_id != org_id:
        raise HTTPException(404, _t("ingest.record_not_found", lang))
    return t


@router.post("/records/{trace_id}/accept")
def accept_record(trace_id: int, request: Request, db: Session = Depends(get_db),
                  u: User = Depends(require_analyst)):
    """Da por bueno el registro: quita la marca de revision. Reversible."""
    lang = get_lang(request)
    t = _chk_trace(db, trace_id, _org(u, lang), lang)
    t.needs_review = False
    model = _model_for_table(t.table_name)
    rec = db.get(model, t.record_id) if model else None
    if rec is not None and hasattr(rec, "needs_review"):
        rec.needs_review = False
    db.commit()
    return {"trace_id": trace_id, "needs_review": False}


@router.patch("/records/{trace_id}")
def edit_record(trace_id: int, body: RecordEditIn, request: Request,
                db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    """Edita a mano los campos de un registro importado.

    Cada campo editado queda protegido (no lo pisa una reimportacion) y el
    registro se da por revisado. La ultima palabra es del usuario.
    """
    from app.services.ingest.batch import set_override
    lang = get_lang(request)
    org = _org(u, lang)
    t = _chk_trace(db, trace_id, org, lang)
    changed = {}
    for field_name, value in (body.fields or {}).items():
        previous = _apply_field(db, org, t.table_name, t.record_id,
                                field_name, value, lang)
        set_override(db, org, t.table_name, t.record_id, field_name,
                     value=value, previous_value=previous,
                     reason="Editado a mano en la revision", user_id=u.id,
                     entity=t.entity)
        changed[field_name] = value
    t.needs_review = False
    model = _model_for_table(t.table_name)
    rec = db.get(model, t.record_id) if model else None
    if rec is not None and hasattr(rec, "needs_review"):
        rec.needs_review = False
    db.commit()
    log_action(db, u.id, "edit", t.table_name, str(t.record_id), {"fields": list(changed)})
    return {"trace_id": trace_id, "changed": changed, "needs_review": False}


@router.post("/records/{trace_id}/not-duplicate")
def not_duplicate(trace_id: int, request: Request, db: Session = Depends(get_db),
                  u: User = Depends(require_analyst)):
    """Confirma que un registro marcado 'posible duplicado' NO lo es.

    Quita la marca de revision y borra la nota de parecido. No fusiona nada:
    la decision de que son distintos es del usuario y se respeta.
    """
    lang = get_lang(request)
    t = _chk_trace(db, trace_id, _org(u, lang), lang)
    after = dict(t.after or {})
    after.pop("_possible_duplicate", None)
    t.after = after
    t.needs_review = False
    model = _model_for_table(t.table_name)
    rec = db.get(model, t.record_id) if model else None
    if rec is not None and hasattr(rec, "needs_review"):
        rec.needs_review = False
    db.commit()
    return {"trace_id": trace_id, "needs_review": False}


def _model_for_table(table_name: str):
    from app.services.ingest.batch import _model_for
    return _model_for(table_name)


# ── Mapas de volcado ("como lo entendi") ─────────────────────────────────────

def _map_d(m: IngestSourceMap) -> dict:
    return {
        "id": m.id, "filename": m.filename, "sha256": m.sha256,
        "doc_kind": m.doc_kind, "units_detected": m.units_detected,
        "ambiguities": m.ambiguities, "rationale": m.rationale,
        "confidence": m.confidence, "status": m.status,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("/source-maps")
def list_source_maps(batch_id: Optional[int] = None, db: Session = Depends(get_db),
                     u: User = Depends(get_current_user)):
    q = db.query(IngestSourceMap).filter_by(organization_id=_org(u))
    if batch_id:
        q = q.filter(IngestSourceMap.batch_id == batch_id)
    return [_map_d(m) for m in q.order_by(IngestSourceMap.id.desc()).limit(200).all()]


# ── Conflictos entre documentos ──────────────────────────────────────────────

class ConflictResolve(BaseModel):
    value: object = None


@router.get("/conflicts")
def list_conflicts(status: Optional[str] = None, batch_id: Optional[int] = None,
                   db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    q = db.query(IngestConflict).filter_by(organization_id=_org(u))
    if status:
        q = q.filter(IngestConflict.status == status)
    if batch_id:
        q = q.filter(IngestConflict.batch_id == batch_id)
    return [{
        "id": c.id, "entity": c.entity, "table_name": c.table_name,
        "record_id": c.record_id, "field_name": c.field_name,
        "candidates": c.candidates, "policy": c.policy,
        "resolved_value": c.resolved_value, "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    } for c in q.order_by(IngestConflict.id.desc()).limit(300).all()]


@router.post("/conflicts/{cid}/resolve")
def resolve_conflict(cid: int, body: ConflictResolve, request: Request,
                     db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    """Elige a mano el valor ganador. Queda como campo forzado: intocable."""
    from app.services.ingest.batch import set_override
    lang = get_lang(request)
    org = _org(u, lang)
    c = db.get(IngestConflict, cid)
    if not c or c.organization_id != org:
        raise HTTPException(404, _t("ingest.conflict_not_found", lang))

    _apply_field(db, org, c.table_name, c.record_id, c.field_name, body.value, lang)
    set_override(db, org, c.table_name, c.record_id, c.field_name,
                 value=body.value, previous_value=c.resolved_value,
                 reason="Conflicto resuelto manualmente", user_id=u.id,
                 entity=c.entity)
    c.resolved_value = body.value
    c.status = "user_resolved"
    c.resolved_by_id = u.id
    c.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": c.id, "status": c.status, "resolved_value": c.resolved_value}


# ── Forzar un valor ──────────────────────────────────────────────────────────

class OverrideIn(BaseModel):
    table_name: str
    record_id: int
    field_name: str
    value: object = None
    reason: Optional[str] = None


@router.post("/overrides", status_code=201)
def create_override(body: OverrideIn, request: Request, db: Session = Depends(get_db),
                    u: User = Depends(require_analyst)):
    """Fija un valor a mano. Ninguna reimportacion posterior lo sobrescribe."""
    from app.services.ingest.batch import set_override
    lang = get_lang(request)
    org = _org(u, lang)
    previous = _apply_field(db, org, body.table_name, body.record_id,
                            body.field_name, body.value, lang)
    row = set_override(db, org, body.table_name, body.record_id, body.field_name,
                       value=body.value, previous_value=previous,
                       reason=body.reason, user_id=u.id)
    db.commit()
    log_action(db, u.id, "override", body.table_name, str(body.record_id),
               {"field": body.field_name, "value": str(body.value)[:200]})
    return {"id": row.id, "field_name": row.field_name, "value": row.value}


@router.get("/overrides")
def list_overrides(table_name: Optional[str] = None, record_id: Optional[int] = None,
                   db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    q = db.query(IngestFieldOverride).filter_by(organization_id=_org(u))
    if table_name:
        q = q.filter(IngestFieldOverride.table_name == table_name)
    if record_id:
        q = q.filter(IngestFieldOverride.record_id == record_id)
    return [{
        "id": o.id, "table_name": o.table_name, "record_id": o.record_id,
        "field_name": o.field_name, "value": o.value,
        "previous_value": o.previous_value, "reason": o.reason,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    } for o in q.order_by(IngestFieldOverride.id.desc()).limit(300).all()]


@router.delete("/overrides/{oid}", status_code=204)
def delete_override(oid: int, request: Request, db: Session = Depends(get_db),
                    u: User = Depends(require_analyst)):
    """Retira la proteccion: el campo vuelve a poder actualizarse al importar."""
    lang = get_lang(request)
    o = db.get(IngestFieldOverride, oid)
    if not o or o.organization_id != _org(u, lang):
        raise HTTPException(404, _t("ingest.override_not_found", lang))
    db.delete(o)
    db.commit()


def _apply_field(db, org_id: int, table_name: str, record_id: int,
                 field_name: str, value, lang: str):
    """Escribe el valor forzado en el registro real y devuelve el anterior.

    Tabla, columna y organizacion se validan aqui: los tres llegan del cliente
    y sin comprobarlos esto seria una via para escribir en cualquier fila de
    cualquier tenant.
    """
    from app.services.ingest.batch import _model_for
    model = _model_for(table_name)
    if model is None:
        raise HTTPException(422, _t("ingest.unknown_table", lang, table=table_name))
    if field_name not in model.__table__.columns:
        raise HTTPException(422, _t("ingest.unknown_field", lang, field=field_name))
    if field_name in ("id", "organization_id"):
        raise HTTPException(422, _t("ingest.field_not_editable", lang, field=field_name))
    record = db.get(model, record_id)
    if record is None:
        raise HTTPException(404, _t("ingest.record_not_found", lang))
    if getattr(record, "organization_id", None) != org_id:
        # Mismo 404 que si no existiera: no se confirma la existencia de un
        # registro ajeno.
        raise HTTPException(404, _t("ingest.record_not_found", lang))
    previous = getattr(record, field_name, None)
    setattr(record, field_name, value)
    db.flush()
    return previous


# ── Perfil de la organizacion ────────────────────────────────────────────────

class ProfileIn(BaseModel):
    structure: Optional[dict] = None
    method: Optional[dict] = None
    vocabulary: Optional[dict] = None
    narrative: Optional[str] = None


@router.get("/profile")
def get_profile(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    row = db.query(OrganizationProfile).filter_by(organization_id=_org(u)).first()
    if not row:
        return {"exists": False, "structure": None, "method": None,
                "vocabulary": None, "narrative": None, "derived_from": None}
    return {
        "exists": True, "structure": row.structure, "method": row.method,
        "vocabulary": row.vocabulary, "narrative": row.narrative,
        "derived_from": row.derived_from, "confidence": row.confidence,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
    }


@router.put("/profile")
def put_profile(body: ProfileIn, db: Session = Depends(get_db),
                u: User = Depends(require_analyst)):
    org = _org(u)
    row = db.query(OrganizationProfile).filter_by(organization_id=org).first()
    if not row:
        row = OrganizationProfile(organization_id=org)
        db.add(row)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(row, k, v)
    row.derived_from = "hybrid" if row.derived_from == "documents" else "questionnaire"
    row.confirmed_at = datetime.now(timezone.utc)
    row.confirmed_by_id = u.id
    db.commit()
    return {"exists": True, "structure": row.structure, "method": row.method,
            "narrative": row.narrative, "derived_from": row.derived_from}


# ── Limpieza del area de paso ────────────────────────────────────────────────

def cleanup_staging(path: Optional[str]) -> None:
    """Borra los ficheros subidos una vez volcados. Best-effort."""
    if not path:
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        logger.debug("ingest: no se pudo limpiar %s", path, exc_info=True)
