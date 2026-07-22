"""Lote, rastro, deshacer y forzar.

Tres garantias que el usuario tiene sobre todo lo que escriba el agente:

1. **Deshacer el lote entero.** Una importacion mal encaminada se revierte de
   un golpe y la base queda como estaba.
2. **Revertir un registro suelto.** Casi todo salio bien y una fila no: se
   deshace esa, no las doscientas.
3. **Forzar un valor.** Se corrige a mano y esa correccion es definitiva:
   ninguna reimportacion posterior la pisa. Ademas se emite una senal a
   `ai_learning_service` para que el agente aprenda el criterio del cliente en
   vez de repetir el mismo error en el siguiente documento.

El rastro (`IngestRecordTrace`) guarda el estado ANTERIOR de cada registro
tocado. Sin eso, "deshacer" solo podria borrar lo creado y dejaria corrompido
lo que se actualizo.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("riskhub.ingest.batch")

# Columnas que nunca se restauran ni se comparan: son metadatos del ORM.
_SKIP_FIELDS = ("id", "created_at", "updated_at")


def create_batch(db, org_id: Optional[int], module: str = "bcm",
                 files: Optional[list] = None, job_id: Optional[int] = None,
                 user_id: Optional[int] = None,
                 estimated_cost_usd: Optional[float] = None):
    from app.models import IngestBatch
    batch = IngestBatch(
        organization_id=org_id, module=module, files=files or [],
        job_id=job_id, created_by_id=user_id, status="running",
        estimated_cost_usd=estimated_cost_usd,
        summary={"created": {}, "linked": {}, "updated": {},
                 "needs_review": 0, "conflicts": 0, "warnings": []},
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def snapshot(record, spec=None) -> dict:
    """Estado serializable de un registro, para poder restaurarlo."""
    if record is None:
        return {}
    if spec is not None:
        names = [f.name for f in spec.fields]
    else:
        names = [c.name for c in record.__table__.columns]
    out = {}
    for name in names:
        if name in _SKIP_FIELDS:
            continue
        value = getattr(record, name, None)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        out[name] = value
    return out


def trace(db, batch, entity: str, table_name: str, record_id: int,
          action: str, before: Optional[dict] = None,
          after: Optional[dict] = None, confidence: Optional[float] = None,
          needs_review: bool = False, source_map_id: Optional[int] = None):
    """Registra que le paso a un registro durante la ingesta."""
    from app.models import IngestRecordTrace
    row = IngestRecordTrace(
        organization_id=getattr(batch, "organization_id", None),
        batch_id=getattr(batch, "id", None),
        source_map_id=source_map_id,
        entity=entity, table_name=table_name, record_id=record_id,
        action=action, before=before, after=after,
        confidence=confidence, needs_review=needs_review,
    )
    db.add(row)
    db.flush()
    return row


# ── Campos forzados por el usuario ───────────────────────────────────────────

def overridden_fields(db, org_id: Optional[int], table_name: str,
                      record_id: int) -> set:
    """Campos de este registro que el usuario corrigio y son intocables."""
    from app.models import IngestFieldOverride
    try:
        rows = db.query(IngestFieldOverride).filter_by(
            organization_id=org_id, table_name=table_name, record_id=record_id
        ).all()
    except Exception:
        logger.debug("ingest: no se pudieron leer los overrides", exc_info=True)
        return set()
    return {r.field_name for r in rows}


def set_override(db, org_id: Optional[int], table_name: str, record_id: int,
                 field_name: str, value: Any, previous_value: Any = None,
                 reason: str = None, user_id: Optional[int] = None,
                 entity: str = None):
    """Marca un campo como corregido a mano. Definitivo frente a reimportaciones.

    Ademas emite una senal de aprendizaje: si el cliente corrige tres veces la
    misma clase de dato, `ai_learning_service` destila una leccion y el agente
    deja de equivocarse ahi.
    """
    from app.models import IngestFieldOverride

    existing = db.query(IngestFieldOverride).filter_by(
        organization_id=org_id, table_name=table_name,
        record_id=record_id, field_name=field_name,
    ).first()
    if existing:
        existing.previous_value = existing.value
        existing.value = value
        existing.reason = reason or existing.reason
        existing.user_id = user_id or existing.user_id
        row = existing
    else:
        row = IngestFieldOverride(
            organization_id=org_id, table_name=table_name, record_id=record_id,
            field_name=field_name, value=value, previous_value=previous_value,
            reason=reason, user_id=user_id,
        )
        db.add(row)
    db.flush()

    try:
        from app.services.ai_learning_service import record_signal
        record_signal(
            db, org_id, "ingest_field_override",
            {"table": table_name, "field": field_name,
             "agent_value": previous_value, "user_value": value,
             "entity": entity, "reason": reason},
            entity_ref=f"{table_name}:{record_id}", user_id=user_id,
        )
    except Exception:
        logger.debug("ingest: no se pudo registrar la senal de aprendizaje",
                     exc_info=True)
    return row


# ── Deshacer ─────────────────────────────────────────────────────────────────

def revert_record(db, trace_row, user_id: Optional[int] = None) -> bool:
    """Revierte un unico registro al estado previo a la ingesta."""
    from app.models import IngestFieldOverride

    if trace_row is None or trace_row.reverted_at:
        return False
    model = _model_for(trace_row.table_name)
    if model is None:
        return False
    record = db.get(model, trace_row.record_id)

    if trace_row.action == "created":
        if record is not None:
            db.query(IngestFieldOverride).filter_by(
                organization_id=trace_row.organization_id,
                table_name=trace_row.table_name,
                record_id=trace_row.record_id,
            ).delete(synchronize_session=False)
            db.delete(record)
    elif trace_row.action in ("updated", "linked"):
        if record is not None and trace_row.before:
            _restore(record, trace_row.before)
    trace_row.reverted_at = datetime.now(timezone.utc)
    db.flush()
    return True


def undo_batch(db, batch, user_id: Optional[int] = None) -> dict:
    """Deshace un lote completo. Devuelve el recuento de lo revertido."""
    from app.models import IngestConflict, IngestRecordTrace, IngestSourceMap

    if batch is None:
        return {"reverted": 0, "already_undone": True}
    if batch.status == "undone":
        return {"reverted": 0, "already_undone": True}

    traces = db.query(IngestRecordTrace).filter_by(batch_id=batch.id).filter(
        IngestRecordTrace.reverted_at.is_(None)
    ).order_by(IngestRecordTrace.id.desc()).all()
    # Orden inverso al de creacion: las dependencias se borran despues que
    # quienes dependen de ellas.

    reverted = 0
    failed = []
    for t in traces:
        try:
            if revert_record(db, t, user_id):
                reverted += 1
        except Exception as exc:
            failed.append({"trace_id": t.id, "table": t.table_name,
                           "record_id": t.record_id, "error": str(exc)[:200]})
            logger.warning("ingest: no se pudo revertir %s:%s",
                           t.table_name, t.record_id, exc_info=True)

    db.query(IngestConflict).filter_by(batch_id=batch.id).delete(
        synchronize_session=False)
    db.query(IngestSourceMap).filter_by(batch_id=batch.id).update(
        {"status": "rejected"}, synchronize_session=False)

    batch.status = "undone"
    batch.undone_at = datetime.now(timezone.utc)
    summary = dict(batch.summary or {})
    summary["undo"] = {"reverted": reverted, "failed": failed}
    batch.summary = summary
    db.commit()
    logger.info("ingest: lote %s deshecho (%d registros, %d fallos)",
                batch.id, reverted, len(failed))
    return {"reverted": reverted, "failed": failed, "already_undone": False}


def _restore(record, before: dict) -> None:
    for name, value in (before or {}).items():
        if name in _SKIP_FIELDS or not hasattr(record, name):
            continue
        column = record.__table__.columns.get(name)
        if column is not None and isinstance(value, str):
            value = _coerce_datetime(column, value)
        setattr(record, name, value)


def _coerce_datetime(column, value: str):
    """`snapshot` serializa las fechas a ISO; al restaurar hay que deshacerlo."""
    try:
        from sqlalchemy import Date, DateTime
        if isinstance(column.type, (DateTime, Date)):
            parsed = datetime.fromisoformat(value)
            return parsed.date() if isinstance(column.type, Date) and not isinstance(
                column.type, DateTime) else parsed
    except Exception:
        return value
    return value


_MODEL_BY_TABLE: dict = {}


def _model_for(table_name: str):
    if not _MODEL_BY_TABLE:
        from app.database import Base
        for mapper in Base.registry.mappers:
            cls = mapper.class_
            table = getattr(cls, "__tablename__", None)
            if table:
                _MODEL_BY_TABLE[table] = cls
    model = _MODEL_BY_TABLE.get(table_name)
    if model is None:
        logger.error("ingest: tabla desconocida al revertir: %r", table_name)
    return model
