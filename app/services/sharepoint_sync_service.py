"""Sincronizacion automatica de carpetas SharePoint permitidas.

Usa Microsoft Graph delta query para detectar archivos nuevos, modificados o
eliminados dentro de las carpetas que el administrador del cliente marco como
"permitidas" en Integraciones > SharePoint, y los importa/reprocesa como
documentos del agente IA con el mismo pipeline que la carga manual: indexado
FTS5/embeddings -> analisis ISMS -> inferencia de evidencias/compliance ->
extraccion de clausulas ISO. Es analisis diferencial: solo se reprocesa lo
que cambio desde la ultima sincronizacion (delta token de Graph).

Los archivos eliminados en origen no se borran automaticamente: se marcan
con source_deleted=True para no perder evidencia de auditoria sin revision.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AiDocument, AiDocumentCategory, AiDocumentStatus
from app.services import sharepoint_service as sp
from app.services.document_service import save_document_file, process_document

logger = logging.getLogger("riskhub.sharepoint_sync")

_MAX_FILE_SIZE = 20 * 1024 * 1024

_EXT_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".csv": "text/plain",
}


def _ext_mime(name: str, mime: str) -> str:
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _EXT_MIME.get(ext, mime or "text/plain")


def _run_post_import_analysis(doc_id: int) -> None:
    """Replica el pipeline que sigue a una carga manual: analisis ISMS + clausulas ISO."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        from app.services.isms_analysis_service import analyze_document_for_isms
        analyze_document_for_isms(db, doc_id)
    except Exception as exc:
        logger.warning("Sync SharePoint: analisis ISMS fallo para doc %d: %s", doc_id, exc)
    finally:
        db.close()

    try:
        from app.services.iso_clause_extractor import run_extraction_for_document
        run_extraction_for_document(doc_id)
    except Exception as exc:
        logger.warning("Sync SharePoint: extraccion de clausulas fallo para doc %d: %s", doc_id, exc)


def _process_delta_item(db: Session, organization_id: int, token: str, drive_id: str,
                         item: dict, summary: dict) -> None:
    item_id = item["id"]
    existing = db.query(AiDocument).filter_by(
        organization_id=organization_id, source_drive_id=drive_id, source_item_id=item_id,
    ).first()

    if item.get("deleted"):
        if existing and not existing.source_deleted:
            existing.source_deleted = True
            db.commit()
            summary["deleted"] += 1
        return

    name = item.get("name") or "archivo.bin"
    mime = item.get("mime", "")
    if not sp.is_importable(name, mime):
        return

    data = sp.download_file(token, drive_id, item_id)
    if len(data) > _MAX_FILE_SIZE:
        summary["errors"].append(f"{name}: supera 20 MB")
        return

    inferred_mime = _ext_mime(name, mime)

    if existing:
        save_document_file(data, existing.filename)
        existing.original_name = name
        existing.file_size = len(data)
        existing.mime_type = inferred_mime
        existing.status = AiDocumentStatus.PENDING
        existing.isms_status = None
        existing.isms_summary = None
        existing.extracted_clauses = None
        existing.source_deleted = False
        db.commit()
        doc_id = existing.id
        summary["updated"] += 1
    else:
        unique_name = f"{uuid.uuid4().hex}_{name}"
        save_document_file(data, unique_name)
        doc = AiDocument(
            filename=unique_name,
            original_name=name,
            category=AiDocumentCategory.OTHER,
            status=AiDocumentStatus.PENDING,
            file_size=len(data),
            mime_type=inferred_mime,
            organization_id=organization_id,
            source="sharepoint",
            source_drive_id=drive_id,
            source_item_id=item_id,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id
        summary["imported"] += 1

    try:
        process_document(db, doc_id)
    except Exception as exc:
        logger.warning("Sync SharePoint: process_document fallo para %s: %s", name, exc)
        return

    _run_post_import_analysis(doc_id)


def sync_organization(db: Session, organization_id: int) -> dict:
    """Sincroniza las carpetas permitidas de SharePoint para una organizacion.

    Devuelve un resumen {imported, updated, deleted, errors}.
    """
    summary = {"imported": 0, "updated": 0, "deleted": 0, "errors": []}
    cfg = sp.get_config(db, organization_id)
    if not cfg:
        return summary
    allowed_folders = cfg.get("allowed_folders") or []
    if not allowed_folders:
        return summary

    try:
        token = sp.get_token(cfg["tenant_id"], cfg["client_id"], cfg["client_secret"], org_id=organization_id)
    except ValueError as e:
        summary["errors"].append(str(e))
        sp.update_config(
            db, organization_id, None,
            last_sync_at=datetime.now(timezone.utc).isoformat(),
            last_sync_summary={"imported": 0, "updated": 0, "deleted": 0, "errors": len(summary["errors"])},
        )
        return summary

    delta_links = dict(cfg.get("delta_links") or {})

    for folder in allowed_folders:
        drive_id = folder.get("drive_id")
        item_id = folder.get("item_id")
        if not drive_id or not item_id:
            continue
        key = f"{drive_id}:{item_id}"
        try:
            items, next_delta_link = sp.delta_scan(token, drive_id, item_id, delta_links.get(key))
        except ValueError as e:
            summary["errors"].append(f"{folder.get('name', key)}: {e}")
            continue

        for item in items:
            try:
                _process_delta_item(db, organization_id, token, drive_id, item, summary)
            except Exception as exc:
                summary["errors"].append(f"{item.get('name', item.get('id'))}: {exc}")

        if next_delta_link:
            delta_links[key] = next_delta_link

    sp.update_config(
        db, organization_id, None,
        delta_links=delta_links,
        last_sync_at=datetime.now(timezone.utc).isoformat(),
        last_sync_summary={
            "imported": summary["imported"],
            "updated": summary["updated"],
            "deleted": summary["deleted"],
            "errors": len(summary["errors"]),
        },
    )
    return summary


def sync_all_organizations() -> dict:
    """Punto de entrada del scheduler: sincroniza todas las orgs con sync activo."""
    from app.database import SessionLocal
    results = {}
    db = SessionLocal()
    try:
        org_ids = sp.list_configured_organizations(db)
    finally:
        db.close()

    for org_id in org_ids:
        db = SessionLocal()
        try:
            results[org_id] = sync_organization(db, org_id)
        except Exception as exc:
            logger.error("Sync SharePoint: error inesperado para org %d: %s", org_id, exc)
        finally:
            db.close()
    return results
