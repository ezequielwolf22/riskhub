"""Pipeline unificado de comprension de evidencia (evidence understanding).

Lee el CONTENIDO real de cada evidencia del modulo central (documentos,
imagenes, escaneados) y produce una revision estructurada que alimenta:
  - la madurez ajustada de los controles vinculados (via control_payload
    en risk_recalc_service) y por tanto el riesgo residual
  - el contexto de los analisis IA (gap de compliance, TPRM, chat)

Sigue el patron probado de bcm_content_reviewer.py; anade la rama Claude
Vision (patron de architecture-review) para capturas de pantalla y PDFs
escaneados sin capa de texto. Sin API key degrada a no-op.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_EVIDENCE_DIR = Path("/srv/data/evidence")

# Que esperaria encontrar un auditor segun el tipo declarado de la evidencia
_EVIDENCE_TYPE_EXPECTATIONS = {
    "policy": "una politica formal: objeto, alcance, roles, aprobacion por la direccion y fecha",
    "procedure": "un procedimiento operativo con pasos concretos, responsables y registros asociados",
    "record": "un registro operativo fechado (resultado de un proceso, ticket, formulario cumplimentado)",
    "certificate": "un certificado vigente (ISO, SOC 2, formacion...) con emisor, alcance y fechas de validez",
    "screenshot": "una captura de una configuracion o control tecnico en funcionamiento (consola, panel, ajuste)",
    "log": "un extracto de logs con marcas temporales que evidencia el funcionamiento real de un control",
    "report": "un informe con hallazgos y conclusiones (auditoria, pentest, escaneo, revision)",
    "meeting_minutes": "un acta de reunion o comite: asistentes, fecha, temas tratados, decisiones y acciones",
    "training_record": "un registro de formacion o concienciacion: contenido, asistentes, fecha y resultados",
    "phishing_campaign": "resultados de una simulacion de phishing: alcance, tasa de clic, tasa de reporte y fecha",
    "other": "evidencia relevante para el sistema de gestion de seguridad de la informacion",
}

_SYSTEM_PROMPT_TMPL = """Eres un auditor experto en ISO/IEC 27001:2022 revisando evidencia documental de un SGSI.

La organizacion subio un archivo etiquetado como evidencia de tipo "{evidence_type}"
con el titulo "{title}". Se espera que este tipo de evidencia contenga: {expectation}.
{link_hint}

Evalua el CONTENIDO REAL del archivo — no si existe o si el titulo suena bien.
Devuelve SOLO un objeto JSON (sin texto adicional, sin markdown) con esta forma exacta:
{{"relevant": <true|false>,
 "quality_level": "<E1|E2|E3|E4|E5>",
 "quality_score": <0-100>,
 "doc_type": "<que es realmente el archivo, ej: acta de comite, captura MFA, informe pentest>",
 "summary": "<2-3 frases de lo que contiene realmente>",
 "key_facts": ["<hecho concreto y verificable>", ...],
 "controls_supported": ["<codigo ISO 27002 que este contenido respalda, ej: 8.5>", ...],
 "maturity_signal": <0-5>,
 "valid_until": "<YYYY-MM-DD o null si el contenido no indica caducidad>",
 "red_flags": ["<inconsistencia o senal de evidencia hueca>", ...]}}

Criterios de quality_level (calidad probatoria para un auditor):
- E5: prueba tecnica verificable y fechada (pentest, auditoria externa, test automatizado, log real)
- E4: procedimiento con registro de ejecucion o prueba documentada
- E3: documento formal (politica/norma/procedimiento) aprobado, sin registro de ejecucion
- E2: contenido informal, generico o sin fechas/responsables
- E1: irrelevante para la etiqueta declarada o no verificable

- relevant=false si el contenido no respalda el tipo de evidencia declarado.
- maturity_signal: madurez del control que este contenido justificaria por si solo (0-5).
- controls_supported: solo codigos que el CONTENIDO respalda de forma directa.
- Se estricto: una plantilla vacia o una mencion de pasada no cuenta.
El texto puede contener tokens como [EMAIL_1], [IP_2], [DOMINIO_1]: son datos
anonimizados antes de llegar a ti, ignoralos a efectos de evaluar el contenido."""

# Mapeo quality_level -> factor de calidad (misma escala que evidence_quality_score)
QUALITY_LEVEL_FACTOR = {
    "E1": 0.10, "E2": 0.35, "E3": 0.60, "E4": 0.80, "E5": 1.00,
}

_IMAGE_MEDIA_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # limite practico de la API para imagenes
_MAX_TEXT_CHARS = 32000


def _read_evidence_bytes(ev) -> Optional[bytes]:
    if not ev.filename:
        return None
    # Guard path traversal: el nombre lo genera el servidor al subir, pero
    # nunca leer fuera del directorio de evidencias
    if "/" in ev.filename or "\\" in ev.filename or ".." in ev.filename:
        logger.warning("evidence_understanding: filename sospechoso ignorado: %r",
                       ev.filename[:80])
        return None
    base = _EVIDENCE_DIR.resolve()
    fpath = (base / ev.filename).resolve()
    if not str(fpath).startswith(str(base)) or not fpath.exists():
        return None
    from app.services.document_service import decrypt_doc
    return decrypt_doc(fpath.read_bytes())


def _build_link_hint(db: Session, ev) -> str:
    """Contexto del vinculo declarado (control/requisito) para que la IA
    evalue si la evidencia respalda ESO en concreto."""
    parts = []
    if ev.control_implementation_id:
        from app.models import ControlImplementation
        ci = db.get(ControlImplementation, ev.control_implementation_id)
        if ci and ci.control:
            parts.append(
                f"Esta vinculada al control ISO 27002 {ci.control.code} "
                f"({ci.control.name}) con madurez declarada {ci.maturity or 0}/5."
            )
    if ev.compliance_framework and ev.compliance_requirement:
        parts.append(
            f"Esta vinculada al requisito {ev.compliance_requirement} "
            f"del framework {ev.compliance_framework}."
        )
    return " ".join(parts)


def analyze_evidence(db: Session, evidence_id: int) -> Optional[dict]:
    """Analiza con IA el contenido de una Evidence. Devuelve el ai_review o None.

    Documentos con texto -> tier fast con el texto extraido y anonimizado.
    Imagenes o PDFs escaneados (sin capa de texto) -> Claude Vision.
    """
    from app.models import AiConfig, Evidence
    from app.services.anonymizer import anonymize
    from app.services.document_service import extract_text
    from app.services.model_registry import get_api_key, get_model

    ev = db.get(Evidence, evidence_id)
    if not ev:
        return None

    api_key = get_api_key(db, ev.organization_id)
    if not api_key:
        logger.debug("evidence_understanding: sin API key org=%s", ev.organization_id)
        return None

    raw = _read_evidence_bytes(ev)
    if raw is None:
        return None

    mime = ev.mime_type or ""
    ev_type = ev.evidence_type.value if hasattr(ev.evidence_type, "value") else str(ev.evidence_type or "other")
    if ev_type not in _EVIDENCE_TYPE_EXPECTATIONS:
        ev_type = "other"

    system_prompt = _SYSTEM_PROMPT_TMPL.format(
        evidence_type=ev_type,
        title=ev.title or "",
        expectation=_EVIDENCE_TYPE_EXPECTATIONS[ev_type],
        link_hint=_build_link_hint(db, ev),
    )

    # Extraer texto; si es imagen o escaneado sin texto -> rama Vision
    text = ""
    if not mime.startswith("image/"):
        try:
            text = extract_text(raw, mime)
        except Exception:
            text = ""

    use_vision = mime.startswith("image/") or (
        "pdf" in mime and len(text.strip()) < 100
    )

    cfg = db.query(AiConfig).filter_by(organization_id=ev.organization_id).first()
    anon_level = cfg.anonymization_level.value if cfg and cfg.anonymization_level else "medium"
    model = get_model(db, ev.organization_id, tier="fast")

    try:
        from app.services.claude_client import create_message

        if use_vision:
            content = _vision_content(raw, mime, ev)
            if content is None:
                return _minimal_review(
                    "Archivo no analizable (imagen demasiado grande o formato no soportado)")
        else:
            if len(text.strip()) < 50:
                return _minimal_review("Sin texto extraible del archivo")
            content = [{
                "type": "text",
                "text": "Contenido del archivo de evidencia:\n\n"
                        + anonymize(text[:_MAX_TEXT_CHARS], anon_level),
            }]

        msg = create_message(
            api_key,
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
        )
        raw_response = msg.content[0].text if msg.content else "{}"
    except Exception as e:
        logger.warning("evidence_understanding: error analizando evidencia %d: %s",
                       evidence_id, e)
        return None

    result = _parse_review(raw_response)
    if result is None:
        return None
    result["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    result["model"] = model
    result["via_vision"] = use_vision
    return result


def _vision_content(raw: bytes, mime: str, ev) -> Optional[list]:
    """Construye el contenido multimodal para imagenes/escaneados."""
    if mime.startswith("image/"):
        if len(raw) > _MAX_IMAGE_BYTES:
            return None
        media_type = mime if mime in _IMAGE_MEDIA_TYPES else "image/png"
        if mime == "image/svg+xml":
            return None  # SVG no soportado por Vision
        return [
            {"type": "image",
             "source": {"type": "base64", "media_type": media_type,
                        "data": base64.standard_b64encode(raw).decode()}},
            {"type": "text",
             "text": f"Imagen subida como evidencia: {ev.title or ev.filename}"},
        ]
    # PDF escaneado: la API acepta documentos PDF como bloque document
    if len(raw) > 20 * 1024 * 1024:
        return None
    return [
        {"type": "document",
         "source": {"type": "base64", "media_type": "application/pdf",
                    "data": base64.standard_b64encode(raw).decode()}},
        {"type": "text",
         "text": f"PDF (posible escaneado) subido como evidencia: {ev.title or ev.filename}"},
    ]


def _minimal_review(reason: str) -> dict:
    return {
        "relevant": False,
        "quality_level": "E1",
        "quality_score": 0,
        "doc_type": "desconocido",
        "summary": reason,
        "key_facts": [],
        "controls_supported": [],
        "maturity_signal": 0,
        "valid_until": None,
        "red_flags": [reason],
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }


def _parse_review(raw: str) -> Optional[dict]:
    raw = raw.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or "quality_level" not in data:
        return None
    lvl = str(data.get("quality_level", "E1")).upper()
    data["quality_level"] = lvl if lvl in QUALITY_LEVEL_FACTOR else "E1"
    try:
        data["quality_score"] = max(0, min(100, int(data.get("quality_score", 0))))
    except (ValueError, TypeError):
        data["quality_score"] = 0
    try:
        data["maturity_signal"] = max(0, min(5, int(data.get("maturity_signal", 0))))
    except (ValueError, TypeError):
        data["maturity_signal"] = 0
    data["relevant"] = bool(data.get("relevant", False))
    data["summary"] = str(data.get("summary") or "")[:1000]
    data["key_facts"] = [str(f)[:300] for f in (data.get("key_facts") or [])][:10]
    data["controls_supported"] = [str(c)[:16] for c in (data.get("controls_supported") or [])][:15]
    data["red_flags"] = [str(f)[:300] for f in (data.get("red_flags") or [])][:10]
    return data


def _apply_review_effects(db: Session, ev, review: dict) -> None:
    """Efectos posteriores: recalcular riesgos del control vinculado.

    La madurez ajustada del control depende ahora de la calidad real de la
    evidencia (control_payload lee ai_review), asi que el residual de los
    riesgos vinculados debe refrescarse.
    """
    if ev.control_implementation_id:
        try:
            from app.services.risk_recalc_service import recalc_risks_for_impls
            recalc_risks_for_impls(db, [ev.control_implementation_id])
        except Exception:
            logger.debug("evidence_understanding: recalc fallo", exc_info=True)


def run_analysis_for_evidence(evidence_id: int) -> None:
    """Punto de entrada para background task — crea su propia sesion de BD."""
    from app.database import SessionLocal
    from app.models import Evidence
    db = SessionLocal()
    try:
        result = analyze_evidence(db, evidence_id)
        if result is None:
            return
        ev = db.get(Evidence, evidence_id)
        if not ev:
            return
        ev.ai_review = result
        ev.ai_reviewed_at = datetime.now(timezone.utc)
        _apply_review_effects(db, ev, result)
        db.commit()
        logger.info(
            "evidence_understanding: evidencia %d — %s relevante=%s calidad=%s",
            evidence_id, result.get("doc_type", "?"),
            result.get("relevant"), result.get("quality_level"),
        )
    except Exception as e:
        logger.error("evidence_understanding: error en evidencia %d: %s", evidence_id, e)
    finally:
        db.close()


def analyze_pending_evidence(cap_per_org: int = 20) -> int:
    """Job nocturno: analiza evidencias pendientes con limite por organizacion.

    El cap controla el coste de tokens: las que no entren hoy entraran manana.
    """
    from app.database import SessionLocal
    from app.models import Evidence
    db = SessionLocal()
    analyzed = 0
    try:
        org_ids = [r[0] for r in db.query(Evidence.organization_id).distinct().all()]
        for org_id in org_ids:
            pending = (
                db.query(Evidence.id)
                .filter(
                    Evidence.organization_id == org_id,
                    Evidence.is_current == True,  # noqa: E712
                    Evidence.filename.isnot(None),
                    Evidence.ai_reviewed_at.is_(None),
                )
                .order_by(Evidence.created_at.desc())
                .limit(cap_per_org)
                .all()
            )
            for (ev_id,) in pending:
                run_analysis_for_evidence(ev_id)
                analyzed += 1
    except Exception as e:
        logger.error("evidence_understanding: job nocturno fallo: %s", e)
    finally:
        db.close()
    if analyzed:
        logger.info("evidence_understanding: job nocturno — %d evidencias analizadas", analyzed)
    return analyzed
