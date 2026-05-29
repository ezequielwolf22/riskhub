"""RAG: busqueda de fragmentos relevantes en FTS5."""
import re

from sqlalchemy.orm import Session
from sqlalchemy import text

# Caracteres especiales del motor FTS5 que podrian alterar la sintaxis de busqueda
_FTS5_SPECIAL = re.compile(r'["\*\^\(\)\{\}\[\]~\-\+:]+')


def _sanitize_fts5(query: str) -> str:
    """Elimina operadores especiales FTS5 para evitar inyeccion de sintaxis."""
    safe = _FTS5_SPECIAL.sub(" ", query)
    # Truncar a 500 caracteres para evitar queries gigantes
    return " ".join(safe.split())[:500]


def search_chunks(
    db: Session,
    query: str,
    top_k: int = 8,
    organization_id: int | None = None,
) -> list[str]:
    """Busca en FTS5 y devuelve los top_k fragmentos mas relevantes (solo texto).

    Cuando organization_id se proporciona, la busqueda queda restringida
    a los documentos de esa organizacion — nunca se cruzan datos entre tenants.
    """
    results = search_chunks_with_source(db, query, top_k=top_k, organization_id=organization_id)
    return [r["content"] for r in results]


def search_chunks_with_source(
    db: Session,
    query: str,
    top_k: int = 8,
    organization_id: int | None = None,
) -> list[dict]:
    """Busca en FTS5 y devuelve dicts con {content, doc_name, category}.

    Permite al agente IA saber exactamente de que documento proviene cada fragmento.
    """
    if not query or not query.strip():
        return []
    try:
        safe_q = _sanitize_fts5(query)
        if not safe_q:
            return []
        if organization_id is not None:
            rows = db.execute(
                text(
                    "SELECT c.content, d.original_name, d.category FROM ai_document_chunks c "
                    "JOIN ai_chunks_fts fts ON fts.rowid = c.id "
                    "JOIN ai_documents d ON d.id = c.document_id "
                    "WHERE ai_chunks_fts MATCH :q "
                    "AND d.organization_id = :org_id "
                    "ORDER BY rank "
                    "LIMIT :k"
                ),
                {"q": safe_q, "k": top_k, "org_id": organization_id},
            ).fetchall()
        else:
            rows = db.execute(
                text(
                    "SELECT c.content, d.original_name, d.category FROM ai_document_chunks c "
                    "JOIN ai_chunks_fts fts ON fts.rowid = c.id "
                    "JOIN ai_documents d ON d.id = c.document_id "
                    "WHERE ai_chunks_fts MATCH :q "
                    "ORDER BY rank "
                    "LIMIT :k"
                ),
                {"q": safe_q, "k": top_k},
            ).fetchall()
        return [{"content": r[0], "doc_name": r[1] or "Documento", "category": r[2] or ""} for r in rows]
    except Exception:
        return []
