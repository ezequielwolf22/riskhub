"""Revision semantica IA del contenido de planes BCP/DRP — ISO 22301 cl. 8.4.

Complementa a `iso_clause_extractor.py` (que cubre ISO 27001/27002 para
politicas del ISMS): este modulo hace la misma funcion pero para el dominio
de continuidad de negocio. La diferencia clave con el resto del motor de
scoring de `bcp_service.py` es que aqui SI se lee el contenido del documento
subido y se evalua semanticamente si cubre lo que la clausula exige — no solo
si el documento existe o tiene texto extraido.
"""
import json
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)

# Elementos minimos que ISO 22301 cl. 8.4 espera segun el tipo de plan.
_PLAN_TYPE_REQUIREMENTS = {
    "bcp": [
        "procedimientos de continuidad para los procesos criticos",
        "criterios y roles de activacion del plan",
        "estrategias de recuperacion (personas, instalaciones, TI, proveedores)",
        "objetivos de tiempo de recuperacion (RTO) por proceso",
        "plan de comunicacion durante la crisis",
    ],
    "drp": [
        "procedimientos tecnicos de recuperacion de sistemas/datos",
        "sitio o infraestructura alternativa de recuperacion",
        "RTO/RPO por sistema",
        "politica y procedimiento de copias de seguridad",
        "roles y responsabilidades del equipo tecnico de recuperacion",
    ],
    "crp": [
        "canales de comunicacion interna y externa durante la crisis",
        "plantillas o mensajes tipo para partes interesadas",
        "cadena de escalado y portavoces autorizados",
    ],
    "cyber_response": [
        "procedimiento de contencion y erradicacion de incidentes ciber",
        "criterios de activacion especificos a ciberataques",
        "coordinacion con el plan de respuesta a incidentes",
    ],
    "pandemic": [
        "medidas de continuidad de personal",
        "criterios de activacion sanitarios",
        "trabajo remoto y turnos alternativos",
    ],
    "supply_chain": [
        "proveedores alternativos identificados",
        "criterios de activacion por fallo de proveedor critico",
    ],
    "ems": [
        "procedimiento de gestion de crisis y mando",
        "activacion del comite de crisis",
    ],
}

_SYSTEM_PROMPT_TMPL = """Eres un auditor experto en ISO 22301:2019 (Sistemas de Gestion de Continuidad de Negocio).

Se te entrega el texto de un documento que la organizacion declara como su
plan de tipo "{plan_type}". Tu trabajo es evaluar si el CONTENIDO REAL del
documento cubre sustantivamente los elementos que la norma exige para este
tipo de plan — no si el documento existe, tiene buen formato o menciona el
tema de pasada.

Elementos esperados para un plan de tipo "{plan_type}":
{requirements}

Devuelve SOLO un objeto JSON (sin texto adicional, sin markdown) con esta forma exacta:
{{"score": <entero 0-100>, "covered": ["elemento cubierto", ...], "missing": ["elemento ausente o insuficiente", ...], "summary": "resumen de 1-2 frases"}}

Criterios de puntuacion:
- 0-20: el documento no trata continuidad de negocio o es irrelevante
- 21-50: menciona el tema pero le falta la mayoria de elementos esperados
- 51-79: cubre varios elementos pero faltan partes importantes o son superficiales
- 80-100: cubre sustantivamente los elementos esperados con detalle operativo real

Se estricto: una mencion superficial de un tema no cuenta como "cubierto".
El texto puede contener tokens como [EMAIL_1], [IP_2], [TELEFONO_1]: son datos
anonimizados antes de llegar a ti, ignoralos a efectos de evaluar el contenido."""

# Tipos de evidencia BCM y lo que un auditor esperaria encontrar en el archivo.
_EVIDENCE_TYPE_EXPECTATIONS = {
    "test_report": "un informe de resultados de un ejercicio/test de continuidad: objetivo, participantes, resultado, hallazgos",
    "plan_approval": "evidencia formal de aprobacion de un plan (acta, firma, correo de aprobacion, fecha)",
    "bcp_activation": "un registro de una activacion real de un plan de continuidad: cronologia, decisiones, resultado",
    "audit_report": "un informe de auditoria interna o externa con hallazgos y conclusiones",
    "backup_validation": "un registro de validacion/restauracion de copias de seguridad con resultado",
    "training_record": "un registro de formacion o concienciacion en continuidad de negocio",
    "supplier_cert": "una certificacion o evidencia de continuidad de un proveedor critico",
    "screenshot": "una captura de pantalla como evidencia puntual (dificil de validar por texto)",
    "other": "evidencia relevante para la gestion de continuidad de negocio",
}

_EVIDENCE_SYSTEM_PROMPT_TMPL = """Eres un auditor experto en ISO 22301:2019 revisando evidencia documental de un
Sistema de Gestion de Continuidad de Negocio (SGCN).

La organizacion subio un archivo etiquetado como evidencia de tipo "{evidence_type}"
con el titulo "{title}". Se espera que este tipo de evidencia contenga: {expectation}.

Lee el texto extraido del archivo y evalua si su contenido REAL respalda esa
etiqueta, o si es un archivo irrelevante/generico subido solo para rellenar un campo.

Devuelve SOLO un objeto JSON (sin texto adicional, sin markdown) con esta forma exacta:
{{"relevant": <true o false>, "quality_score": <entero 0-100>, "summary": "resumen de 1-2 frases de lo que contiene realmente el archivo"}}

- relevant=false si el contenido no tiene relacion real con el tipo de evidencia declarado.
- quality_score alto solo si el contenido es especifico, fechado y verificable — no una plantilla vacia.
El texto puede contener tokens como [EMAIL_1], [IP_2], [TELEFONO_1]: son datos
anonimizados antes de llegar a ti, ignoralos a efectos de evaluar el contenido."""


def review_plan_content(db: Session, plan) -> Optional[dict]:
    """Analiza con IA el documento vinculado a un BCPPlan y evalua si su
    contenido cubre sustantivamente lo que ISO 22301 exige para ese tipo de plan.

    Devuelve None si no hay documento con texto suficiente o si falla el
    analisis (en ese caso el plan sigue evaluandose solo por completitud
    estructural en bcp_service._plan_has_substance).
    """
    from app.models import AiDocument, AiDocumentChunk

    if not plan.document_id:
        return None
    doc = db.get(AiDocument, plan.document_id)
    if not doc:
        return None

    chunks = (
        db.query(AiDocumentChunk)
        .filter(AiDocumentChunk.document_id == doc.id)
        .order_by(AiDocumentChunk.chunk_index)
        .all()
    )
    text = "\n".join(c.content for c in chunks)
    if len(text.strip()) < 200:
        return None

    text_truncated = text[:32000]
    plan_type = plan.plan_type if plan.plan_type in _PLAN_TYPE_REQUIREMENTS else "bcp"
    requirements = "\n".join(f"- {r}" for r in _PLAN_TYPE_REQUIREMENTS[plan_type])
    system_prompt = _SYSTEM_PROMPT_TMPL.format(plan_type=plan_type, requirements=requirements)

    try:
        raw = _call_claude(db, plan.organization_id, system_prompt, text_truncated)
        result = _parse_response(raw)
    except Exception as e:
        logger.warning("bcm_content_reviewer: error analizando plan %d: %s", plan.id, e)
        return None

    if result is None:
        return None

    from datetime import datetime, timezone
    result["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    result["plan_type"] = plan_type
    return result


def _resolve_ai_config(db: Session, org_id: Optional[int]) -> tuple[str, str, str]:
    """Misma logica de resolucion per-tenant que iso_clause_extractor.py.

    Devuelve (api_key, model, anonymization_level) — el nivel de anonimizacion
    se respeta siempre: el texto de documentos/evidencia se anonimiza ANTES de
    enviarse a la API de Anthropic, igual que en el chat del agente IA.
    """
    try:
        import base64, hashlib
        from cryptography.fernet import Fernet
        from app.models import AiConfig

        def _fkey() -> bytes:
            return base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())

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
                logger.warning("bcm_content_reviewer: error descifrando API key de org %s", org_id)
    except Exception as e:
        logger.debug("bcm_content_reviewer: no se pudo cargar AiConfig: %s", e)

    return settings.anthropic_api_key or "", "claude-haiku-4-5", "medium"


def _call_claude(db: Session, org_id: Optional[int], system_prompt: str, text: str) -> str:
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
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Documento a analizar:\n\n{text}"}],
    )
    return msg.content[0].text if msg.content else "{}"


def _extract_json(raw: str) -> Optional[dict]:
    raw = raw.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _parse_response(raw: str) -> Optional[dict]:
    data = _extract_json(raw)
    if data is None or "score" not in data:
        return None
    try:
        data["score"] = max(0, min(100, int(data["score"])))
    except (ValueError, TypeError):
        return None
    data["covered"] = data.get("covered") or []
    data["missing"] = data.get("missing") or []
    data["summary"] = data.get("summary") or ""
    return data


def _parse_evidence_response(raw: str) -> Optional[dict]:
    data = _extract_json(raw)
    if data is None or "quality_score" not in data:
        return None
    try:
        data["quality_score"] = max(0, min(100, int(data["quality_score"])))
    except (ValueError, TypeError):
        return None
    data["relevant"] = bool(data.get("relevant", False))
    data["summary"] = data.get("summary") or ""
    return data


def review_evidence_item(db: Session, evidence) -> Optional[dict]:
    """Analiza con IA el archivo de un BCMEvidenceItem: lo descifra, extrae su
    texto y evalua si el contenido REAL respalda el tipo de evidencia declarado
    (informe de test, auditoria, validacion de backup, etc.) — no solo que el
    archivo se haya subido con esa etiqueta.

    Devuelve None si el archivo no tiene texto extraible (ej. una captura de
    pantalla sin OCR) o si falla el analisis — la evidencia se sigue contando
    en el scoring por su vinculacion/vigencia, sin penalizar por no tener texto.
    """
    from pathlib import Path
    from app.services.document_service import decrypt_doc, extract_text

    if not evidence.file_path:
        return None
    fpath = Path(evidence.file_path)
    if not fpath.exists():
        return None

    try:
        raw_bytes = decrypt_doc(fpath.read_bytes())
        text = extract_text(raw_bytes, evidence.mime_type or "")
    except Exception as e:
        logger.debug("bcm_content_reviewer: no se pudo extraer texto de evidencia %d: %s", evidence.id, e)
        return None

    if len(text.strip()) < 100:
        return None

    text_truncated = text[:32000]
    ev_type = evidence.evidence_type if evidence.evidence_type in _EVIDENCE_TYPE_EXPECTATIONS else "other"
    expectation = _EVIDENCE_TYPE_EXPECTATIONS[ev_type]
    system_prompt = _EVIDENCE_SYSTEM_PROMPT_TMPL.format(
        evidence_type=ev_type, title=evidence.title or "", expectation=expectation,
    )

    try:
        raw = _call_claude(db, evidence.organization_id, system_prompt, text_truncated)
        result = _parse_evidence_response(raw)
    except Exception as e:
        logger.warning("bcm_content_reviewer: error analizando evidencia %d: %s", evidence.id, e)
        return None

    if result is None:
        return None

    from datetime import datetime, timezone
    result["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    return result


def run_review_for_plan(plan_id: int) -> None:
    """Punto de entrada para background task — crea su propia sesion de BD."""
    from app.database import SessionLocal
    from app.models import BCPPlan
    db = SessionLocal()
    try:
        plan = db.get(BCPPlan, plan_id)
        if not plan:
            return
        result = review_plan_content(db, plan)
        plan.ai_content_review = result
        db.commit()
        if result:
            logger.info("bcm_content_reviewer: plan %d — score %d/100", plan_id, result["score"])
    except Exception as e:
        logger.error("bcm_content_reviewer: error en plan %d: %s", plan_id, e)
    finally:
        db.close()


def run_review_for_evidence(evidence_id: int) -> None:
    """Punto de entrada para background task — crea su propia sesion de BD."""
    from app.database import SessionLocal
    from app.models import BCMEvidenceItem
    db = SessionLocal()
    try:
        evidence = db.get(BCMEvidenceItem, evidence_id)
        if not evidence:
            return
        result = review_evidence_item(db, evidence)
        evidence.ai_review = result
        db.commit()
        if result:
            logger.info("bcm_content_reviewer: evidencia %d — relevante=%s quality=%d/100",
                        evidence_id, result["relevant"], result["quality_score"])
    except Exception as e:
        logger.error("bcm_content_reviewer: error en evidencia %d: %s", evidence_id, e)
    finally:
        db.close()
