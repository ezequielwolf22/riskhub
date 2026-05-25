"""Gestion de documentos para el agente IA."""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AiDocument, AiDocumentCategory, AiDocumentStatus, User
from app.security import get_current_user, require_role
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
    }


@router.get("/")
def list_documents(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    docs = db.query(AiDocument).order_by(AiDocument.created_at.desc()).all()
    return [_doc_out(d) for d in docs]


@router.post("/")
def upload_document(
    file: UploadFile = File(...),
    category: str = Form(...),
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
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Procesar de forma sincrona (BD pequeñas: aceptable)
    try:
        process_document(db, doc.id)
        db.refresh(doc)
    except Exception:
        pass  # status quedo en ERROR; el cliente puede ver el mensaje

    return _doc_out(doc)


@router.delete("/{doc_id}")
def remove_document(
    doc_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("analyst")),
):
    doc = db.query(AiDocument).filter_by(id=doc_id).first()
    if not doc:
        raise HTTPException(404, "Documento no encontrado")
    delete_document(db, doc)
    return {"ok": True}


@router.post("/{doc_id}/reprocess")
def reprocess_document(
    doc_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("analyst")),
):
    doc = db.query(AiDocument).filter_by(id=doc_id).first()
    if not doc:
        raise HTTPException(404, "Documento no encontrado")
    try:
        process_document(db, doc_id)
    except Exception:
        pass
    db.refresh(doc)
    return _doc_out(doc)
