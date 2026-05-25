"""RAG: busqueda de fragmentos relevantes en FTS5."""
from sqlalchemy.orm import Session
from sqlalchemy import text


def search_chunks(db: Session, query: str, top_k: int = 5) -> list[str]:
    """Busca en FTS5 y devuelve los top_k fragmentos mas relevantes."""
    if not query or not query.strip():
        return []
    try:
        # Sanitizar query para FTS5 (evitar caracteres especiales)
        safe_q = query.replace('"', "").replace("*", "").strip()
        if not safe_q:
            return []
        rows = db.execute(
            text(
                "SELECT c.content FROM ai_document_chunks c "
                "JOIN ai_chunks_fts fts ON fts.rowid = c.id "
                "WHERE ai_chunks_fts MATCH :q "
                "ORDER BY rank "
                "LIMIT :k"
            ),
            {"q": safe_q, "k": top_k},
        ).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []
