"""Gestion de documentos para el agente IA."""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import AiDocument, AiDocumentCategory, AiDocumentStatus, User
from app.security import check_org_access, filter_by_org, get_current_user, require_role
from app.services.document_service import (
    delete_document, doc_path, process_document, save_document_file,
)

router = APIRouter(prefix="/api/ai/documents", tags=["ai-documents"])

ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/csv",
}
MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

# Firmas magicas (magic bytes) para validar contenido real del archivo (OWASP A08)
_MAGIC_BYTES: dict[str, bytes] = {
    "application/pdf": b"%PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK\x03\x04",
}


def _infer_mime(filename: str, content_type: str) -> str:
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        return "application/pdf"
    if ext == "docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if ext in ("txt", "csv", "md"):
        return "text/plain"
    return content_type or "application/octet-stream"


def _validate_magic(mime: str, data: bytes) -> bool:
    """Comprueba que los magic bytes del archivo corresponden al MIME declarado."""
    expected = _MAGIC_BYTES.get(mime)
    if expected is None:
        # TXT/CSV: no hay magic bytes; aceptar si es decodificable como UTF-8
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
    file: UploadFile = File(...),
    category: str = Form(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    data = file.file.read()
    if len(data) > MAX_SIZE_BYTES:
        raise HTTPException(400, "Archivo demasiado grande (maximo 20 MB)")

    mime = _infer_mime(file.filename or "", file.content_type or "")
    if mime not in ALLOWED_MIME and not any(k in mime for k in ("pdf", "docx", "plain", "csv")):
        raise HTTPException(400, "Tipo de archivo no soportado. Usa PDF, DOCX o TXT.")

    # OWASP A08 — validar contenido real mediante magic bytes
    if not _validate_magic(mime, data):
        raise HTTPException(400, "El contenido del archivo no coincide con la extension declarada.")

    try:
        cat = AiDocumentCategory(category)
    except ValueError:
        raise HTTPException(400, f"Categoria invalida: {category}")

    unique_name = f"{uuid.uuid4().hex}_{file.filename}"
    # Cifrar el archivo antes de escribir en disco (Fernet / AES-128-CBC)
    save_document_file(data, unique_name)

    doc = AiDocument(
        filename=unique_name,
        original_name=file.filename or unique_name,
        category=cat,
        status=AiDocumentStatus.PENDING,
        file_size=len(data),
        mime_type=mime,
        uploaded_by_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Extraccion de texto e indexado FTS5 (sincrono — rapido)
    try:
        process_document(db, doc.id)
        db.refresh(doc)
    except Exception:
        pass  # status quedo en ERROR; el cliente puede ver el mensaje

    # Analisis ISMS en background para no bloquear la respuesta HTTP
    if doc.status == AiDocumentStatus.INDEXED and background_tasks is not None:
        background_tasks.add_task(_run_isms_analysis_bg, doc.id)

    return _doc_out(doc)


@router.delete("/{doc_id}")
def remove_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    doc = db.query(AiDocument).filter_by(id=doc_id).first()
    if not doc or not check_org_access(doc.organization_id, current_user):
        raise HTTPException(404, "Documento no encontrado")
    delete_document(db, doc)
    return {"ok": True}


@router.post("/{doc_id}/reprocess")
def reprocess_document(
    doc_id: int,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    doc = db.query(AiDocument).filter_by(id=doc_id).first()
    if not doc or not check_org_access(doc.organization_id, current_user):
        raise HTTPException(404, "Documento no encontrado")
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
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Lanza (o relanza) el analisis ISMS del documento en background."""
    doc = db.query(AiDocument).filter_by(id=doc_id).first()
    if not doc or not check_org_access(doc.organization_id, current_user):
        raise HTTPException(404, "Documento no encontrado")
    if doc.status != AiDocumentStatus.INDEXED:
        raise HTTPException(400, "El documento debe estar en estado INDEXED para ser analizado")
    # Resetear estado para forzar reanalizis
    doc.isms_status = None
    doc.isms_summary = None
    db.commit()
    background_tasks.add_task(_run_isms_analysis_bg, doc.id)
    return {"ok": True, "message": "Analisis ISMS iniciado en background"}


@router.post("/analyze-all")
def analyze_all_documents(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Lanza el analisis ISMS de todos los documentos indexados de la organizacion.

    Solo procesa documentos INDEXED. Los que ya tienen isms_status='analysed' se
    re-analizan para actualizar el gap analysis con el prompt mejorado.
    """
    docs = (
        db.query(AiDocument)
        .filter(
            AiDocument.organization_id == current_user.organization_id,
            AiDocument.status == AiDocumentStatus.INDEXED,
        )
        .all()
    )
    if not docs:
        raise HTTPException(400, "No hay documentos indexados para analizar")

    queued = 0
    for doc in docs:
        doc.isms_status = "analysing"
        doc.isms_summary = None
        background_tasks.add_task(_run_isms_analysis_bg, doc.id)
        queued += 1

    db.commit()
    return {"ok": True, "queued": queued, "message": f"Analisis ISMS iniciado para {queued} documentos"}
