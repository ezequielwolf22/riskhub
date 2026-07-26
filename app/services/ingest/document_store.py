"""Registro persistente de documentos del cliente, bajo control del usuario.

La documentacion de la ingesta es dinamica: se anaden documentos cuando haga
falta, se quitan, se excluyen los que no se quieren analizar y se relanza el
analisis en cualquier momento. Por defecto todo lo que se sube se analiza.

Los bytes se guardan en disco (no en la base) indexados por huella SHA-256, asi
que subir dos veces el mismo fichero no lo duplica y reanalizar no obliga a
volver a subirlo. Este modulo es el unico que toca ese almacen: crear, listar,
excluir/incluir y borrar.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.services.ingest import reader

logger = logging.getLogger("riskhub.ingest.document_store")


def documents_root(org_id: int) -> Path:
    """Carpeta persistente de documentos de una organizacion."""
    from app.routers.bcp import _bcm_data_root
    root = _bcm_data_root("ingest_documents") / str(org_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def add_document(db, org_id: int, filename: str, data: bytes,
                 user_id: Optional[int] = None):
    """Registra (o actualiza) un documento y persiste sus bytes.

    Si ya existe un documento con la misma huella, se reutiliza: subir lo mismo
    dos veces no crea un duplicado. Devuelve la fila de IngestDocument.
    """
    from app.models import IngestDocument
    sha = hashlib.sha256(data).hexdigest()

    existing = db.query(IngestDocument).filter_by(
        organization_id=org_id, sha256=sha).first()
    if existing is not None:
        # Mismo contenido: se conserva, se reactiva si estaba fuera.
        if not existing.included and existing.status == "excluded":
            existing.included = True
            existing.status = "pending"
        return existing

    safe = Path(filename).name or "documento"
    stored = documents_root(org_id) / f"{sha[:16]}_{safe}"
    if not stored.exists():
        stored.write_bytes(data)

    fmt = None
    try:
        fmt = reader.read_document(data, safe).get("format")
    except Exception:
        fmt = Path(safe).suffix.lstrip(".") or None

    row = IngestDocument(
        organization_id=org_id, filename=safe, sha256=sha,
        size_bytes=len(data), doc_format=fmt, stored_path=str(stored),
        included=True, status="pending" if reader.is_supported(safe) else "unsupported",
        uploaded_by_id=user_id,
    )
    db.add(row)
    db.flush()
    return row


def list_documents(db, org_id: int) -> list:
    from app.models import IngestDocument
    return db.query(IngestDocument).filter_by(organization_id=org_id).order_by(
        IngestDocument.id.desc()).all()


def get_document(db, org_id: int, doc_id: int):
    from app.models import IngestDocument
    row = db.get(IngestDocument, doc_id)
    if row is None or row.organization_id != org_id:
        return None
    return row


def set_included(db, org_id: int, doc_id: int, included: bool):
    """Incluye o excluye un documento del analisis. La ultima palabra del usuario."""
    row = get_document(db, org_id, doc_id)
    if row is None:
        return None
    row.included = bool(included)
    # Un documento excluido no se pierde: se puede volver a incluir cuando se
    # quiera. El estado refleja que ahora mismo se obvia.
    if not included:
        row.status = "excluded"
    elif row.status == "excluded":
        row.status = "pending"
    db.flush()
    return row


def remove_document(db, org_id: int, doc_id: int) -> bool:
    """Quita un documento del registro y borra sus bytes.

    No revierte los datos que ese documento ya volco: eso se hace con deshacer
    (por lote o por registro). Quitar el documento solo evita que se vuelva a
    analizar y libera su copia en disco si no la comparte otro.
    """
    from app.models import IngestDocument
    row = get_document(db, org_id, doc_id)
    if row is None:
        return False
    shared = db.query(IngestDocument).filter(
        IngestDocument.organization_id == org_id,
        IngestDocument.sha256 == row.sha256,
        IngestDocument.id != row.id,
    ).count()
    if not shared and row.stored_path:
        try:
            Path(row.stored_path).unlink(missing_ok=True)
        except Exception:
            logger.debug("document_store: no se pudo borrar %s", row.stored_path,
                         exc_info=True)
    db.delete(row)
    db.flush()
    return True


def load_bytes(row) -> Optional[bytes]:
    """Lee los bytes persistidos de un documento, o None si ya no estan."""
    if not row or not row.stored_path:
        return None
    try:
        return Path(row.stored_path).read_bytes()
    except Exception:
        logger.warning("document_store: no se pudieron leer los bytes de %s",
                       row.filename, exc_info=True)
        return None


def included_documents(db, org_id: int) -> list:
    """Documentos que ahora mismo entran al analisis (incluidos y legibles)."""
    return [r for r in list_documents(db, org_id)
            if r.included and r.status != "unsupported" and load_bytes(r) is not None]


def mark_analyzed(db, row, batch_id: Optional[int], report: dict) -> None:
    """Sella el resultado del analisis sobre el documento."""
    if row is None:
        return
    status = report.get("status")
    row.status = "analyzed" if status == "ok" else "failed"
    row.doc_kind = report.get("doc_kind") or row.doc_kind
    row.confidence = report.get("confidence")
    row.last_batch_id = batch_id
    row.error = report.get("error")
    row.analyzed_at = datetime.now(timezone.utc)
    db.flush()


def cleanup_org(org_id: int) -> None:
    """Borra el almacen de documentos de una organizacion (best-effort)."""
    try:
        shutil.rmtree(documents_root(org_id), ignore_errors=True)
    except Exception:
        logger.debug("document_store: no se pudo limpiar la org %s", org_id,
                     exc_info=True)
