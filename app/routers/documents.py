"""Gestion de documentos para el agente IA."""
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.i18n import get_lang, t as _t

from app.database import get_db, SessionLocal
from app.models import AiDocument, AiDocumentCategory, AiDocumentStatus, User
from app.security import check_org_access, filter_by_org, get_current_user, require_role
from app.services.document_service import (
    compute_sha256, delete_document, doc_path, document_references,
    find_duplicate_document, process_document, save_document_file,
)

router = APIRouter(prefix="/api/ai/documents", tags=["ai-documents"])

ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/csv",
    # Hojas de calculo (v6.0.0) — inventarios, registros, resultados de campanas
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # Imagenes de arquitectura (v1.7.8)
    "image/png",
    "image/jpeg",
    "image/svg+xml",
}
MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

# Firmas magicas (magic bytes) para validar contenido real del archivo (OWASP A08)
_MAGIC_BYTES: dict[str, bytes] = {
    "application/pdf": b"%PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK\x03\x04",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": b"PK\x03\x04",
    "image/png": b"\x89PNG",
    "image/jpeg": b"\xff\xd8\xff",
}


def _infer_mime(filename: str, content_type: str) -> str:
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        return "application/pdf"
    if ext == "docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if ext == "xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if ext in ("txt", "csv", "md"):
        return "text/plain"
    if ext == "png":
        return "image/png"
    if ext in ("jpg", "jpeg"):
        return "image/jpeg"
    if ext == "svg":
        return "image/svg+xml"
    return content_type or "application/octet-stream"


def _validate_magic(mime: str, data: bytes) -> bool:
    """Comprueba que los magic bytes del archivo corresponden al MIME declarado."""
    expected = _MAGIC_BYTES.get(mime)
    if expected is None:
        # TXT/CSV/SVG: no hay magic bytes; aceptar si es decodificable como UTF-8
        try:
            data[:512].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return False
        return True
    return data[:len(expected)] == expected


def _doc_out(d: AiDocument) -> dict:
    summary = d.isms_summary or {}
    return {
        "id": d.id,
        "original_name": d.original_name,
        "category": d.category.value if d.category else None,
        "status": d.status.value if d.status else None,
        "file_size": d.file_size,
        "chunk_count": d.chunk_count,
        "error_message": d.error_message,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "processed_at": d.processed_at.isoformat() if d.processed_at else None,
        "uploaded_by": d.uploaded_by.full_name if d.uploaded_by else None,
        # ISMS analysis fields (v1.7.4)
        "isms_status": d.isms_status,
        "isms_policy_id": summary.get("policy_id"),
        "isms_controls_updated": summary.get("controls_updated", 0),
        "isms_tasks_created": summary.get("tasks_created", 0),
        "isms_summary_text": summary.get("summary") or summary.get("reason") or summary.get("error"),
        "isms_summary": summary,  # full summary for frontend (document_level, etc.)
        # Auto-categorizacion IA (v1.7.8)
        "auto_categorized": bool(getattr(d, "auto_categorized", False) or summary.get("auto_categorized", False)),
        "detected_category": getattr(d, "detected_category", None) or summary.get("detected_category"),
        # Eje de clasificacion documental (F2): normative/record/reference/unclassified
        "doc_class": getattr(d, "doc_class", None),
        "doc_class_confidence": getattr(d, "doc_class_confidence", None),
        "analysed_at": d.analysed_at.isoformat() if getattr(d, "analysed_at", None) else None,
        # Clausulas ISO extraidas por IA (v2.2)
        "extracted_clauses": getattr(d, "extracted_clauses", None) or [],
    }


def _run_isms_analysis_bg(doc_id: int) -> None:
    """Wrapper de background para analisis ISMS — crea su propia sesion de BD."""
    db = SessionLocal()
    try:
        from app.services.isms_analysis_service import analyze_document_for_isms
        analyze_document_for_isms(db, doc_id)
    except Exception:
        pass
    finally:
        db.close()

    # Tras el analisis ISMS, extraer clausulas ISO automaticamente
    try:
        from app.services.iso_clause_extractor import run_extraction_for_document
        run_extraction_for_document(doc_id)
    except Exception:
        pass


@router.get("/")
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    docs = filter_by_org(db.query(AiDocument), AiDocument, current_user).order_by(
        AiDocument.created_at.desc()
    ).all()
    return [_doc_out(d) for d in docs]


@router.post("/")
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(...),
    force: bool = Form(False),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    lang = get_lang(request)
    data = file.file.read()
    if len(data) > MAX_SIZE_BYTES:
        raise HTTPException(400, _t("documents.too_large", lang, max_mb=50))

    mime = _infer_mime(file.filename or "", file.content_type or "")
    if mime not in ALLOWED_MIME:
        raise HTTPException(400, _t("documents.invalid_type", lang, formats="PDF, DOCX, XLSX, TXT, PNG, JPG"))

    # OWASP A08 — validar contenido real mediante magic bytes
    if not _validate_magic(mime, data):
        raise HTTPException(400, _t("documents.invalid_type", lang, formats="PDF, DOCX, XLSX, TXT, PNG, JPG"))

    try:
        cat = AiDocumentCategory(category)
    except ValueError:
        raise HTTPException(400, f"Categoria invalida: {category}")

    # F6 — deduplicacion: el mismo contenido subido de nuevo inflaba la madurez
    # del control. Se rechaza con 409 (el cliente puede reintentar con force=true
    # si de verdad quiere una copia), salvo que el original se haya borrado.
    sha256 = compute_sha256(data)
    if not force:
        dup = find_duplicate_document(db, current_user.organization_id, sha256)
        if dup:
            raise HTTPException(409, detail={
                "error": "duplicate",
                "message": _t("documents.duplicate", lang, name=dup.original_name),
                "existing_id": dup.id,
                "existing_name": dup.original_name,
            })

    # Sanitizar el filename para evitar path traversal
    safe_filename = re.sub(r"[^\w.\-]", "_", Path(file.filename or "file").name)[:80]
    unique_name = f"{uuid.uuid4().hex}_{safe_filename}"
    # Cifrar el archivo antes de escribir en disco (Fernet / AES-128-CBC)
    save_document_file(data, unique_name)

    doc = AiDocument(
        filename=unique_name,
        original_name=file.filename or unique_name,
        category=cat,
        status=AiDocumentStatus.PENDING,
        file_size=len(data),
        mime_type=mime,
        sha256=sha256,
        uploaded_by_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    needs_vision = False
    if mime.startswith("image/"):
        # Imagenes: INDEXED de inmediato; la transcripcion Vision corre en
        # background y genera los chunks (antes quedaban invisibles al RAG)
        doc.status = AiDocumentStatus.INDEXED
        doc.chunk_count = 0
        db.commit()
        db.refresh(doc)
        needs_vision = mime != "image/svg+xml"
    else:
        # Extraccion de texto e indexado FTS5 (sincrono — rapido)
        try:
            process_document(db, doc.id)
            db.refresh(doc)
        except Exception:
            pass  # status quedo en ERROR; el cliente puede ver el mensaje
        # PDF escaneado sin capa de texto: 0 chunks -> transcripcion Vision
        if "pdf" in mime and doc.status == AiDocumentStatus.INDEXED and not doc.chunk_count:
            needs_vision = True

    if needs_vision:
        # Vision + ISMS via cola persistida (trabajo largo, sobrevive reinicios)
        try:
            from app.services.job_queue import enqueue
            enqueue(db, doc.organization_id, "document_vision_isms",
                    {"doc_id": doc.id}, created_by_id=current_user.id,
                    dedupe_key=f"document_vision_isms:{doc.id}")
            db.commit()
        except Exception:
            pass
    elif doc.status == AiDocumentStatus.INDEXED and background_tasks is not None:
        # Analisis ISMS en background para no bloquear la respuesta HTTP
        background_tasks.add_task(_run_isms_analysis_bg, doc.id)

    return _doc_out(doc)


@router.delete("/{doc_id}")
def remove_document(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    lang = get_lang(request)
    from app.models import UserRole
    doc = db.query(AiDocument).filter_by(id=doc_id).first()
    if not doc or not check_org_access(doc.organization_id, current_user):
        raise HTTPException(404, _t("documents.not_found", lang))
    # Solo el propietario o un administrador pueden eliminar el documento
    if doc.uploaded_by_id != current_user.id and current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, _t("common.forbidden", lang))
    detached = delete_document(db, doc)
    return {"ok": True, "detached": detached}


@router.get("/{doc_id}/references")
def get_document_references(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registros que quedarian desvinculados al borrar el documento.

    Alimenta el aviso previo al borrado: el documento se va, pero la politica o
    el plan que se derivaron de el se conservan sin su archivo de origen.
    """
    lang = get_lang(request)
    doc = db.query(AiDocument).filter_by(id=doc_id).first()
    if not doc or not check_org_access(doc.organization_id, current_user):
        raise HTTPException(404, _t("documents.not_found", lang))
    return {"doc_id": doc_id, "detached": document_references(db, doc_id)}


class BulkActionIn(BaseModel):
    doc_ids: list[int]
    action: str                      # delete | analyze | recategorize
    category: str | None = None      # solo para recategorize
    dry_run: bool = False            # solo para delete: calcula impacto sin borrar


_BULK_MAX = 500


@router.post("/bulk")
def bulk_documents(
    body: BulkActionIn,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Operaciones masivas sobre documentos: borrar, reanalizar o recategorizar.

    Solo actua sobre documentos de la organizacion activa. Los que el usuario no
    puede tocar se devuelven en `skipped` en vez de abortar el lote entero.
    """
    lang = get_lang(request)
    from app.models import UserRole

    if body.action not in ("delete", "analyze", "recategorize"):
        raise HTTPException(400, _t("common.bad_request", lang))
    ids = list(dict.fromkeys(body.doc_ids))       # dedupe conservando orden
    if not ids:
        raise HTTPException(400, _t("common.bad_request", lang))
    if len(ids) > _BULK_MAX:
        raise HTTPException(400, f"Maximo {_BULK_MAX} documentos por lote")

    docs = filter_by_org(
        db.query(AiDocument).filter(AiDocument.id.in_(ids)), AiDocument, current_user
    ).all()
    found = {d.id for d in docs}
    result: dict = {
        "action": body.action,
        "requested": len(ids),
        "affected": 0,
        "skipped": {"not_found": [i for i in ids if i not in found]},
    }

    if body.action == "delete":
        is_admin = current_user.role in (UserRole.ADMIN, UserRole.SUPERADMIN)
        forbidden, detached = [], {}
        for doc in docs:
            if not is_admin and doc.uploaded_by_id != current_user.id:
                forbidden.append(doc.id)
                continue
            if body.dry_run:
                refs = document_references(db, doc.id)
            else:
                refs = delete_document(db, doc)
            for kind, n in refs.items():
                detached[kind] = detached.get(kind, 0) + n
            result["affected"] += 1
        result["skipped"]["forbidden"] = forbidden
        result["detached"] = detached
        result["dry_run"] = body.dry_run
        return result

    if body.action == "recategorize":
        try:
            cat = AiDocumentCategory(body.category or "")
        except ValueError:
            raise HTTPException(400, f"Categoria invalida: {body.category}")
        for doc in docs:
            doc.category = cat
            doc.auto_categorized = False   # decision humana: la IA no la pisa
            result["affected"] += 1
        db.commit()
        return result

    # analyze: solo tiene sentido sobre documentos ya indexados
    not_indexed = []
    for doc in docs:
        if doc.status != AiDocumentStatus.INDEXED:
            not_indexed.append(doc.id)
            continue
        doc.isms_status = "analysing"
        doc.isms_summary = None
        background_tasks.add_task(_run_isms_analysis_bg, doc.id)
        result["affected"] += 1
    db.commit()
    result["skipped"]["not_indexed"] = not_indexed
    return result


@router.post("/{doc_id}/reprocess")
def reprocess_document(
    doc_id: int,
    request: Request,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    lang = get_lang(request)
    doc = db.query(AiDocument).filter_by(id=doc_id).first()
    if not doc or not check_org_access(doc.organization_id, current_user):
        raise HTTPException(404, _t("documents.not_found", lang))
    try:
        process_document(db, doc_id)
    except Exception:
        pass
    db.refresh(doc)
    # Re-lanzar analisis ISMS si el reprocesado fue exitoso
    if doc.status == AiDocumentStatus.INDEXED and background_tasks is not None:
        background_tasks.add_task(_run_isms_analysis_bg, doc.id)
    return _doc_out(doc)


@router.post("/{doc_id}/analyze")
def analyze_document(
    doc_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Lanza (o relanza) el analisis ISMS del documento en background."""
    lang = get_lang(request)
    doc = db.query(AiDocument).filter_by(id=doc_id).first()
    if not doc or not check_org_access(doc.organization_id, current_user):
        raise HTTPException(404, _t("documents.not_found", lang))
    if doc.status != AiDocumentStatus.INDEXED:
        raise HTTPException(400, _t("common.bad_request", lang))
    # Resetear estado para forzar reanalizis
    doc.isms_status = None
    doc.isms_summary = None
    db.commit()
    background_tasks.add_task(_run_isms_analysis_bg, doc.id)
    return {"ok": True, "message": "Analisis ISMS iniciado en background"}


@router.post("/analyze-pending")
def analyze_pending_documents(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Resetea documentos atascados en 'analysing' y lanza analisis solo para pendientes (null/error).

    No toca documentos ya analizados correctamente.
    """
    from sqlalchemy import or_
    org_id = current_user.organization_id
    # Resetear stuck
    stuck = db.query(AiDocument).filter(
        AiDocument.organization_id == org_id,
        AiDocument.status == AiDocumentStatus.INDEXED,
        AiDocument.isms_status == "analysing",
    )
    stuck_count = stuck.count()
    if stuck_count:
        stuck.update({"isms_status": None, "isms_summary": None})
        db.commit()
    # Lanzar solo los pendientes (null o error)
    docs = db.query(AiDocument).filter(
        AiDocument.organization_id == org_id,
        AiDocument.status == AiDocumentStatus.INDEXED,
        or_(AiDocument.isms_status == None, AiDocument.isms_status == "error"),  # noqa: E711
    ).all()
    queued = 0
    for doc in docs:
        doc.isms_status = "analysing"
        doc.isms_summary = None
        background_tasks.add_task(_run_isms_analysis_bg, doc.id)
        queued += 1
    db.commit()
    return {
        "ok": True,
        "stuck_reset": stuck_count,
        "queued": queued,
        "message": f"{stuck_count} atascados reseteados. {queued} documentos en cola.",
    }


@router.get("/{doc_id}/controls")
def get_document_controls(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve las implementaciones de control actualizadas por este documento (via evidence_refs)."""
    lang = get_lang(request)
    from app.models import ControlImplementation
    from sqlalchemy import cast, String

    doc = db.query(AiDocument).filter_by(id=doc_id).first()
    if not doc or not check_org_access(doc.organization_id, current_user):
        raise HTTPException(404, _t("documents.not_found", lang))

    doc_url = f"/api/ai/documents/{doc_id}"
    impls = (
        db.query(ControlImplementation)
        .filter(
            ControlImplementation.organization_id == doc.organization_id,
            cast(ControlImplementation.evidence_refs, String).like(f"%{doc_url}%"),
        )
        .all()
    )

    out = []
    for i in impls:
        ctrl = i.control
        out.append({
            "id": i.id,
            "control_code": ctrl.code if ctrl else None,
            "control_name": ctrl.name if ctrl else i.name,
            "maturity": i.maturity or 0,
            "status": i.status.value if i.status else None,
            "notes": i.notes or "",
        })
    return out


@router.post("/analyze-all")
def analyze_all_documents(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Lanza el analisis ISMS de todos los documentos indexados de la organizacion.

    Solo procesa documentos INDEXED. Los que ya tienen isms_status='analysed' se
    re-analizan para actualizar el gap analysis con el prompt mejorado.
    """
    lang = get_lang(request)
    docs = (
        db.query(AiDocument)
        .filter(
            AiDocument.organization_id == current_user.organization_id,
            AiDocument.status == AiDocumentStatus.INDEXED,
        )
        .all()
    )
    if not docs:
        raise HTTPException(400, _t("common.bad_request", lang))

    queued = 0
    for doc in docs:
        doc.isms_status = "analysing"
        doc.isms_summary = None
        background_tasks.add_task(_run_isms_analysis_bg, doc.id)
        queued += 1

    db.commit()
    return {"ok": True, "queued": queued, "message": f"Analisis ISMS iniciado para {queued} documentos"}
