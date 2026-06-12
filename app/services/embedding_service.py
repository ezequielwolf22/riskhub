"""Busqueda semantica multilingue usando Voyage AI embeddings.

voyage-multilingual-2 entiende texto en cualquier idioma y devuelve vectores
comparables entre si, lo que permite buscar en documentos EN con preguntas ES
(o cualquier otra combinacion de idiomas) sin diccionarios ni traduccion previa.
"""
import json
import logging
import math

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger("riskhub.embedding")

VOYAGE_MODEL = "voyage-multilingual-2"
EMBED_BATCH_SIZE = 64  # Voyage AI acepta hasta 128 textos por llamada


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def embed_texts(texts: list[str], api_key: str, input_type: str = "document") -> list[list[float] | None]:
    """Vectoriza una lista de textos con Voyage AI (en batches con retry ante rate limit).

    input_type: "document" para chunks de documentos, "query" para preguntas.
    Devuelve lista del mismo largo que texts; None para textos que fallaron.
    """
    import time

    if not texts or not api_key:
        return [None] * len(texts)
    try:
        import voyageai
        vo = voyageai.Client(api_key=api_key)
        results: list[list[float] | None] = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i:i + EMBED_BATCH_SIZE]
            # Reintentar hasta 4 veces con backoff exponencial ante rate limit
            for attempt in range(4):
                try:
                    res = vo.embed(batch, model=VOYAGE_MODEL, input_type=input_type)
                    results.extend(res.embeddings)
                    # Pausa minima entre batches para no superar 3 RPM en cuentas sin billing
                    if i + EMBED_BATCH_SIZE < len(texts):
                        time.sleep(21)  # 60s / 3 RPM = 20s + 1s margen
                    break
                except Exception as e:
                    err = str(e).lower()
                    if "rate" in err or "429" in err or "limit" in err:
                        wait = 22 * (2 ** attempt)  # 22s, 44s, 88s, 176s
                        logger.warning("Voyage rate limit, reintentando en %ds (intento %d)", wait, attempt + 1)
                        time.sleep(wait)
                    else:
                        logger.warning("Voyage embed batch error: %s", e)
                        results.extend([None] * len(batch))
                        break
            else:
                # Todos los reintentos fallaron
                results.extend([None] * len(batch))
        return results
    except ImportError:
        logger.error("voyageai no instalado — pip install voyageai")
        return [None] * len(texts)
    except Exception as e:
        logger.error("Voyage embed error: %s", e)
        return [None] * len(texts)


def embed_query(query: str, api_key: str) -> list[float] | None:
    """Vectoriza una pregunta del usuario."""
    results = embed_texts([query], api_key, input_type="query")
    return results[0] if results else None


def search_by_embedding(
    db: Session,
    query_embedding: list[float],
    top_k: int,
    organization_id: int | None,
) -> list[dict]:
    """Busqueda por similitud coseno en todos los chunks con embedding.

    Carga los embeddings de la BD, computa similitud en Python y devuelve top_k.
    Para colecciones tipicas (<50k chunks) esto es rapido (<200ms).
    """
    if organization_id is not None:
        rows = db.execute(
            text(
                "SELECT c.content, c.embedding, d.original_name, d.category "
                "FROM ai_document_chunks c "
                "JOIN ai_documents d ON d.id = c.document_id "
                "WHERE c.embedding IS NOT NULL "
                "AND d.organization_id = :org_id "
                "AND d.status = 'indexed'"
            ),
            {"org_id": organization_id},
        ).fetchall()
    else:
        rows = db.execute(
            text(
                "SELECT c.content, c.embedding, d.original_name, d.category "
                "FROM ai_document_chunks c "
                "JOIN ai_documents d ON d.id = c.document_id "
                "WHERE c.embedding IS NOT NULL "
                "AND d.status = 'indexed'"
            )
        ).fetchall()

    if not rows:
        return []

    scored: list[tuple[float, str, str, str]] = []
    for row in rows:
        try:
            emb = json.loads(row[1])
            sim = _cosine_similarity(query_embedding, emb)
            scored.append((sim, row[0], row[2] or "Documento", row[3] or ""))
        except Exception:
            continue

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"content": s[1], "doc_name": s[2], "category": s[3], "score": round(s[0], 4)}
        for s in scored[:top_k]
        if s[0] > 0.3  # Umbral minimo de similitud — descartar ruido
    ]


def embed_document_chunks(db: Session, doc_id: int, voyage_api_key: str) -> int:
    """Genera y persiste embeddings para todos los chunks de un documento.

    Devuelve el numero de chunks vectorizados correctamente.
    """
    from app.models import AiDocumentChunk
    chunks = db.query(AiDocumentChunk).filter_by(document_id=doc_id).order_by(
        AiDocumentChunk.chunk_index
    ).all()
    if not chunks:
        return 0

    texts = [c.content for c in chunks]
    embeddings = embed_texts(texts, voyage_api_key, input_type="document")

    count = 0
    for chunk, emb in zip(chunks, embeddings):
        if emb is not None:
            chunk.embedding = json.dumps(emb)
            count += 1
    db.commit()
    logger.info("Documento %d: %d/%d chunks vectorizados", doc_id, count, len(chunks))
    return count


def embed_all_org_chunks(db: Session, organization_id: int, voyage_api_key: str) -> dict:
    """Vectoriza todos los chunks sin embedding de una organizacion.

    Usado al configurar por primera vez la Voyage API key para re-indexar docs existentes.
    Devuelve {docs_processed, chunks_embedded, chunks_failed}.
    """
    from app.models import AiDocument, AiDocumentChunk, AiDocumentStatus

    docs = (
        db.query(AiDocument)
        .filter(
            AiDocument.organization_id == organization_id,
            AiDocument.status == AiDocumentStatus.INDEXED,
        )
        .all()
    )

    total_embedded = 0
    total_failed = 0
    docs_processed = 0

    for doc in docs:
        chunks = (
            db.query(AiDocumentChunk)
            .filter(
                AiDocumentChunk.document_id == doc.id,
                AiDocumentChunk.embedding.is_(None),
            )
            .all()
        )
        if not chunks:
            continue

        texts = [c.content for c in chunks]
        embeddings = embed_texts(texts, voyage_api_key, input_type="document")

        for chunk, emb in zip(chunks, embeddings):
            if emb is not None:
                chunk.embedding = json.dumps(emb)
                total_embedded += 1
            else:
                total_failed += 1
        db.commit()
        docs_processed += 1

    return {
        "docs_processed": docs_processed,
        "chunks_embedded": total_embedded,
        "chunks_failed": total_failed,
    }
