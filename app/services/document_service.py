"""Extraccion de texto, chunking y gestion de documentos IA.

Seguridad en reposo:
  Los archivos subidos se cifran con Fernet (AES-128-CBC + HMAC-SHA256) antes
  de escribirse en disco. La clave se deriva del SECRET_KEY del servidor usando
  SHA-256 -> base64url. Los archivos anteriores a esta version (no cifrados) se
  leen correctamente por compatibilidad hacia atras (InvalidToken -> raw bytes).
"""
import base64
import hashlib
import io
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings
from app.models import AiDocument, AiDocumentChunk, AiDocumentStatus

# Directorio de almacenamiento de documentos
# FIX: comprobar el punto de montaje persistente (/srv/data) en vez de la
# subcarpeta "documents" — esta ultima nunca existe en el primer arranque de
# un volumen nuevo, asi que el chequeo anterior caia SIEMPRE al fallback local
# (efimero, se pierde en cada `docker build` + recreate del contenedor).
_DOC_ROOT = Path("/srv/data/documents")
if not _DOC_ROOT.parent.exists():
    _DOC_ROOT = Path(__file__).parent.parent.parent / "data" / "documents"
_DOC_ROOT.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = 600
CHUNK_OVERLAP = 100


# ---------- Cifrado en reposo ----------

def _fernet_key() -> bytes:
    """Deriva clave Fernet de 32 bytes a partir del SECRET_KEY de la app."""
    return base64.urlsafe_b64encode(
        hashlib.sha256(settings.secret_key.encode()).digest()
    )


def encrypt_doc(data: bytes) -> bytes:
    """Cifra los bytes de un documento con Fernet antes de escribir en disco."""
    from cryptography.fernet import Fernet
    return Fernet(_fernet_key()).encrypt(data)


def decrypt_doc(data: bytes) -> bytes:
    """Descifra los bytes de un documento leido del disco.

    Si el archivo no esta cifrado (version anterior), devuelve los bytes sin
    modificar para mantener compatibilidad con documentos pre-cifrado.
    """
    from cryptography.fernet import Fernet, InvalidToken
    try:
        return Fernet(_fernet_key()).decrypt(data)
    except (InvalidToken, ValueError, Exception):
        # Archivo pre-cifrado: devolver raw para compatibilidad hacia atras
        return data


def save_document_file(data: bytes, filename: str) -> None:
    """Escribe los bytes del documento en disco cifrados con Fernet."""
    dest = _DOC_ROOT / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(encrypt_doc(data))


# ---------- helpers ----------

def doc_path(filename: str) -> Path:
    return _DOC_ROOT / filename


def _extract_text_pdf(data: bytes) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        return "\n".join(parts)
    except Exception as e:
        raise ValueError(f"Error extrayendo PDF: {e}")


def _extract_text_docx(data: bytes) -> str:
    try:
        import docx
        doc = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        raise ValueError(f"Error extrayendo DOCX: {e}")


def _extract_text_plain(data: bytes) -> str:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_text(data: bytes, mime_type: str) -> str:
    if "pdf" in mime_type:
        return _extract_text_pdf(data)
    if "wordprocessingml" in mime_type or "docx" in mime_type:
        return _extract_text_docx(data)
    return _extract_text_plain(data)


def chunk_text(full_text: str) -> list[str]:
    """Divide el texto en fragmentos de CHUNK_SIZE con solapamiento CHUNK_OVERLAP."""
    full_text = re.sub(r"\s+", " ", full_text).strip()
    chunks = []
    start = 0
    while start < len(full_text):
        end = start + CHUNK_SIZE
        chunks.append(full_text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if len(c.strip()) > 20]


def _delete_fts_for_doc(db: Session, doc_id: int) -> None:
    """Elimina del indice FTS5 todos los chunks de un documento."""
    chunk_ids = [
        r[0] for r in db.query(AiDocumentChunk.id).filter_by(document_id=doc_id).all()
    ]
    for cid in chunk_ids:
        try:
            db.execute(text("DELETE FROM ai_chunks_fts WHERE rowid = :cid"), {"cid": cid})
        except Exception:
            pass  # FTS puede no existir aun


def process_document(db: Session, doc_id: int) -> None:
    """Extrae texto, genera chunks y los indexa en FTS5."""
    doc = db.query(AiDocument).filter_by(id=doc_id).first()
    if not doc:
        return

    doc.status = AiDocumentStatus.PROCESSING
    db.commit()

    try:
        # decrypt_doc soporta tanto archivos cifrados (nuevos) como no cifrados (legacy)
        file_data = decrypt_doc(doc_path(doc.filename).read_bytes())
        raw_text = extract_text(file_data, doc.mime_type or "text/plain")
        chunks = chunk_text(raw_text)

        # Borrar chunks previos
        _delete_fts_for_doc(db, doc_id)
        db.query(AiDocumentChunk).filter_by(document_id=doc_id).delete()

        for idx, chunk_content in enumerate(chunks):
            chunk = AiDocumentChunk(
                document_id=doc_id,
                chunk_index=idx,
                content=chunk_content,
            )
            db.add(chunk)
            db.flush()  # necesario para obtener chunk.id
            try:
                db.execute(
                    text("INSERT INTO ai_chunks_fts(rowid, content) VALUES (:rowid, :content)"),
                    {"rowid": chunk.id, "content": chunk_content},
                )
            except Exception:
                pass  # FTS puede no estar disponible

        doc.chunk_count = len(chunks)
        doc.status = AiDocumentStatus.INDEXED
        doc.processed_at = datetime.now(timezone.utc)
        db.commit()

        # Generar embeddings semanticos si hay Voyage API key configurada
        _try_embed_document(db, doc_id, doc.organization_id)

    except Exception as e:
        doc.status = AiDocumentStatus.ERROR
        doc.error_message = str(e)[:500]
        db.commit()
        raise


def _try_embed_document(db: Session, doc_id: int, organization_id: int | None) -> None:
    """Genera embeddings Voyage AI para el documento si la key esta configurada.

    Falla silenciosamente — los embeddings son una mejora opcional sobre FTS5.
    """
    if not organization_id:
        return
    try:
        from app.models import AiConfig
        from app.security import decrypt_secret
        from app.services.embedding_service import embed_document_chunks
        cfg = db.query(AiConfig).filter_by(organization_id=organization_id).first()
        if not cfg or not cfg.voyage_api_key_encrypted:
            return
        voyage_key = decrypt_secret(cfg.voyage_api_key_encrypted)
        embed_document_chunks(db, doc_id, voyage_key)
    except Exception as e:
        import logging
        logging.getLogger("riskhub.doc").warning("Embedding falló para doc %d: %s", doc_id, e)


def delete_document(db: Session, doc: AiDocument) -> None:
    """Elimina documento, sus chunks de BD y FTS5, y el archivo del disco."""
    _delete_fts_for_doc(db, doc.id)
    db.query(AiDocumentChunk).filter_by(document_id=doc.id).delete()
    p = doc_path(doc.filename)
    if p.exists():
        p.unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
