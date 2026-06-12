"""RAG: busqueda de fragmentos relevantes en FTS5."""
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger("riskhub.rag")

# Caracteres especiales del motor FTS5 que podrian alterar la sintaxis de busqueda
_FTS5_SPECIAL = re.compile(r'["\*\^\(\)\{\}\[\]~\-\+:]+')


def ask(prompt: str, org_id: Optional[int] = None) -> Optional[str]:
    """A3: llamada directa a Claude para preguntas simples (sin RAG).

    Utiliza la API key global de configuracion.
    Retorna la respuesta como string, o None si no hay API key o hay error.
    """
    try:
        from app.config import settings
        api_key = getattr(settings, "anthropic_api_key", None)
        if not api_key:
            return None
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        logger.debug("rag_service.ask fallo: %s", e)
        return None


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


_STOPWORDS_ES = {
    "que", "qué", "de", "del", "en", "el", "la", "los", "las", "un", "una",
    "y", "o", "a", "al", "es", "por", "para", "con", "se", "su", "sus",
    "me", "mi", "no", "si", "lo", "le", "hay", "como", "cómo", "cuál",
    "cual", "cuáles", "cuales", "sobre", "más", "mas", "pero", "ya", "has",
    "dime", "dame", "puedes", "puedo", "quiero", "saber", "decir", "dice",
    "dices", "tiene", "tienen", "puede", "pueden", "qué", "este", "esta",
    "estos", "estas", "son", "fue", "ser", "estar", "hace", "hacer", "hay",
    "cuanto", "cuánto", "donde", "dónde", "cuando", "cuándo", "quien",
    "quién", "alguno", "alguna", "todos", "todas", "cada", "muy",
}


def _fts5_query_variants(query: str) -> list[str]:
    """Genera variantes de query FTS5 de mayor a menor especificidad.

    1. Frase exacta entre comillas
    2. Todas las palabras significativas (AND implicito en FTS5)
    3. Prefijos con comodin (palabra*)
    """
    safe = _sanitize_fts5(query)
    words = [w for w in safe.split() if len(w) > 2 and w.lower() not in _STOPWORDS_ES]
    if not words:
        # Fallback: usar todo sin filtrar stopwords
        words = [w for w in safe.split() if len(w) > 1]
    if not words:
        return []

    variants: list[str] = []
    # Variante 1: frase exacta
    variants.append(f'"{safe}"')
    # Variante 2: AND de palabras significativas (maximo 6 para evitar 0 resultados)
    if len(words) > 1:
        variants.append(" ".join(words[:6]))
    # Variante 3: primera palabra como prefijo (mas permisivo)
    variants.append(f"{words[0]}*")
    return variants


def _run_fts5(
    db: Session,
    fts_query: str,
    top_k: int,
    organization_id: int | None,
) -> list[tuple]:
    """Ejecuta una query FTS5 y devuelve las filas crudas."""
    if organization_id is not None:
        return db.execute(
            text(
                "SELECT c.content, d.original_name, d.category FROM ai_document_chunks c "
                "JOIN ai_chunks_fts fts ON fts.rowid = c.id "
                "JOIN ai_documents d ON d.id = c.document_id "
                "WHERE ai_chunks_fts MATCH :q "
                "AND d.organization_id = :org_id "
                "ORDER BY rank LIMIT :k"
            ),
            {"q": fts_query, "k": top_k, "org_id": organization_id},
        ).fetchall()
    return db.execute(
        text(
            "SELECT c.content, d.original_name, d.category FROM ai_document_chunks c "
            "JOIN ai_chunks_fts fts ON fts.rowid = c.id "
            "JOIN ai_documents d ON d.id = c.document_id "
            "WHERE ai_chunks_fts MATCH :q "
            "ORDER BY rank LIMIT :k"
        ),
        {"q": fts_query, "k": top_k},
    ).fetchall()


def search_chunks_with_source(
    db: Session,
    query: str,
    top_k: int = 8,
    organization_id: int | None = None,
) -> list[dict]:
    """Busca en FTS5 con multiples estrategias de fallback.

    Intenta en orden: frase exacta → palabras AND → prefijo comodin.
    Permite al agente IA saber exactamente de que documento proviene cada fragmento.
    """
    if not query or not query.strip():
        return []
    try:
        for variant in _fts5_query_variants(query):
            try:
                rows = _run_fts5(db, variant, top_k, organization_id)
                if rows:
                    return [
                        {"content": r[0], "doc_name": r[1] or "Documento", "category": r[2] or ""}
                        for r in rows
                    ]
            except Exception:
                continue
        return []
    except Exception:
        return []
