"""Extraccion automatica de clausulas ISO 27001/27002 desde documentos de politicas.

Usa Claude para identificar referencias a clausulas ISO mencionadas en el texto
del documento y las mapea a controles existentes en la base de datos.
"""
import json
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AiDocument, Control

logger = logging.getLogger(__name__)

# Patron para detectar referencias ISO en el resultado del LLM
_CLAUSE_PATTERN = re.compile(
    r"([A-Z]?\d+(?:\.\d+)+)",
    re.IGNORECASE,
)

# Prompt para Claude: extrae clausulas ISO del texto del documento
_SYSTEM_PROMPT = """Eres un experto en ISO 27001:2022 e ISO 27002:2022.
Analiza el texto de un documento de politica de seguridad y extrae todas las referencias
a clausulas y controles de las normas ISO 27001 e ISO 27002 que aparezcan explicita o
implicitamente en el texto.

Para cada clausula o control identificado devuelve un objeto JSON con:
- ref: referencia normalizada (ej. "A.5.1", "6.1.2", "8.8")
- title: titulo de la clausula segun la norma
- confidence: numero entre 0.0 y 1.0 indicando la confianza de la deteccion

Devuelve SOLO un array JSON valido. Sin texto adicional, sin markdown, sin explicaciones.
Ejemplo de respuesta: [{"ref":"A.5.1","title":"Politicas de seguridad de la informacion","confidence":0.95}]
El texto puede contener tokens como [EMAIL_1], [IP_2], [TELEFONO_1]: son datos
anonimizados antes de llegar a ti, ignoralos a efectos de identificar clausulas.

Si no encuentras ninguna referencia, devuelve: []"""


def extract_iso_clauses(db: Session, doc: AiDocument) -> list[dict]:
    """Extrae clausulas ISO del texto del documento usando IA.

    Returns:
        Lista de dicts con {ref, title, control_id, confidence}.
        control_id es None si no se encuentra un control coincidente en BD.
    """
    # Obtener texto del documento desde sus chunks
    text = _get_doc_text(db, doc)
    if not text or len(text.strip()) < 100:
        return []

    # Truncar a ~8000 tokens (~32000 chars) para no exceder el contexto
    text_truncated = text[:32000]

    try:
        raw = _call_claude(db, doc.organization_id, text_truncated)
        clauses = _parse_response(raw)
    except Exception as e:
        logger.warning("iso_clause_extractor: error llamando a Claude: %s", e)
        return []

    if not clauses:
        return []

    # Enriquecer con control_id de la BD
    enriched = []
    for clause in clauses:
        ref = clause.get("ref", "").strip()
        if not ref:
            continue
        control_id = _find_control_id(db, ref, doc.organization_id)
        enriched.append({
            "ref": ref,
            "title": clause.get("title", ""),
            "control_id": control_id,
            "confidence": round(float(clause.get("confidence", 0.8)), 2),
        })

    # Ordenar por referencia y filtrar confianza < 0.5
    enriched = [c for c in enriched if c["confidence"] >= 0.5]
    enriched.sort(key=lambda x: x["ref"])
    return enriched


def _get_doc_text(db: Session, doc: AiDocument) -> str:
    """Concatena el texto de todos los chunks del documento."""
    from app.models import AiDocumentChunk
    chunks = (
        db.query(AiDocumentChunk)
        .filter(AiDocumentChunk.document_id == doc.id)
        .order_by(AiDocumentChunk.chunk_index)
        .all()
    )
    return "\n".join(c.content for c in chunks)


def _resolve_ai_config(db: Session, org_id: Optional[int]) -> tuple[str, str, str]:
    """Obtiene (api_key, model, anonymization_level) para la org. Usa per-tenant
    si disponible, global como fallback."""
    try:
        import base64, hashlib
        from cryptography.fernet import Fernet
        from app.models import AiConfig

        def _fkey() -> bytes:
            return base64.urlsafe_b64encode(
                hashlib.sha256(settings.secret_key.encode()).digest()
            )

        cfg = None
        if org_id:
            cfg = db.query(AiConfig).filter(AiConfig.organization_id == org_id).first()

        model = "claude-haiku-4-5"
        if cfg and cfg.model:
            model = cfg.model
        anon_level = cfg.anonymization_level.value if cfg and cfg.anonymization_level else "medium"

        if cfg and cfg.api_key_encrypted:
            try:
                api_key = Fernet(_fkey()).decrypt(cfg.api_key_encrypted.encode()).decode()
                return api_key, model, anon_level
            except Exception:
                logger.warning("iso_clause_extractor: error descifrando API key de org %s", org_id)

    except Exception as e:
        logger.debug("iso_clause_extractor: no se pudo cargar AiConfig: %s", e)

    # Fallback a clave global
    api_key = settings.anthropic_api_key or ""
    return api_key, "claude-haiku-4-5", "medium"


def _call_claude(db: Session, org_id: Optional[int], text: str) -> str:
    """Llama a Claude API para extraer clausulas ISO del texto."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic no instalado")

    api_key, model, anon_level = _resolve_ai_config(db, org_id)
    if not api_key:
        raise RuntimeError("API key de Anthropic no configurada")

    from app.services.anonymizer import anonymize
    text = anonymize(text, anon_level)

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=16384,
        system=_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Documento a analizar:\n\n{text}",
        }],
    )
    return msg.content[0].text if msg.content else "[]"


def _parse_response(raw: str) -> list[dict]:
    """Parsea la respuesta JSON de Claude."""
    raw = raw.strip()
    # Extraer solo el JSON array si viene con texto alrededor
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _find_control_id(db: Session, ref: str, org_id: Optional[int]) -> Optional[int]:
    """Busca en la BD el control ISO 27002 que coincide con la referencia.

    Busca por codigo exacto o por codigo normalizado.
    """
    # Normalizar: A.5.1 -> 5.1, 5.1 -> 5.1
    normalized = ref.upper().lstrip("A.").strip()

    control = (
        db.query(Control)
        .filter(Control.code.ilike(f"%{normalized}%"))
        .first()
    )
    return control.id if control else None


def run_extraction_for_document(doc_id: int) -> None:
    """Punto de entrada para background task — crea su propia sesion de BD."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        doc = db.get(AiDocument, doc_id)
        if not doc:
            return
        clauses = extract_iso_clauses(db, doc)
        doc.extracted_clauses = clauses if clauses else []
        db.commit()
        logger.info(
            "iso_clause_extractor: doc %d — %d clausulas extraidas",
            doc_id, len(clauses),
        )
    except Exception as e:
        logger.error("iso_clause_extractor: error en doc %d: %s", doc_id, e)
    finally:
        db.close()
