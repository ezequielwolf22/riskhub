"""Servicio de evaluacion IA para cuestionarios de proveedores (TPRM Sprint 5).

Evalua las respuestas de un cuestionario de seguridad de proveedor usando Claude,
devolviendo un dict estructurado con score, confianza, banderas de riesgo y
preguntas de seguimiento. Nunca lanza excepciones al caller — devuelve error dict.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.services.ai_service import _repair_json

logger = logging.getLogger("riskhub.tprm_ai")

# Schema JSON que el modelo debe devolver (se incluye en el system prompt)
_EXPECTED_SCHEMA = """{
  "ai_score": <entero 0-100>,
  "confidence": <decimal 0.0-1.0>,
  "control_coverage_assessment": "<fully_covered|partially_covered|not_covered|unclear>",
  "evidence_consistency": "<consistent|partially_consistent|inconsistent|no_evidence>",
  "red_flags": ["<string>", ...],
  "follow_up_questions": ["<string>", ...],
  "rationale": "<string>",
  "needs_manual_review": <true|false>
}"""

_SYSTEM_PROMPT = (
    "Eres un auditor experto en ciberseguridad especializado en evaluacion de riesgos de terceros (TPRM). "
    "Tu funcion es EVALUAR las respuestas de un proveedor a un cuestionario de seguridad y emitir un juicio "
    "tecnico objetivo. No debes decidir si se contrata o no al proveedor — solo evaluas la calidad y consistencia "
    "de sus respuestas respecto a los controles de seguridad esperados. "
    "Reglas criticas: "
    "1. Devuelve EXCLUSIVAMENTE JSON valido, sin texto adicional antes ni despues. "
    "2. No inventes evidencias ni supongas controles que el proveedor no haya mencionado. "
    "3. Si no puedes evaluar una pregunta por falta de informacion, indicalo en rationale y baja la confianza. "
    "4. Los red_flags deben ser concisos (maximo 15 palabras cada uno). "
    "5. Las follow_up_questions deben ser preguntas concretas y verificables. "
    "6. El ai_score refleja la madurez de seguridad percibida (0=nula, 100=excelente). "
    f"Devuelve exactamente este esquema JSON:\n{_EXPECTED_SCHEMA}"
)


def _build_evaluation_prompt(questionnaire: Any) -> str:
    """Construye el prompt de usuario con las preguntas y respuestas del cuestionario."""
    questions: list[dict] = questionnaire.questions or []
    answers: dict = questionnaire.answers or {}

    lines: list[str] = [
        f"Cuestionario: {questionnaire.title or questionnaire.code}",
        "",
        "A continuacion se listan las preguntas del cuestionario, sus referencias de control "
        "y las respuestas proporcionadas por el proveedor:",
        "",
    ]

    answered_count = 0
    for i, q in enumerate(questions, 1):
        qid = str(q.get("id", i))
        text = q.get("text", "").strip()
        domain = q.get("domain", "")
        control_refs: list = q.get("control_refs") or []
        hint: str = q.get("ai_evaluation_hints") or q.get("ai_evaluation_hint") or ""
        answer = answers.get(qid, answers.get(str(i), ""))

        if not answer and not text:
            continue

        lines.append(f"Pregunta {i} (ID: {qid}){' [' + domain + ']' if domain else ''}:")
        if text:
            lines.append(f"  Texto: {text}")
        if control_refs:
            refs_str = ", ".join(str(r) for r in control_refs)
            lines.append(f"  Controles de referencia: {refs_str}")
        if hint:
            lines.append(f"  Criterio de evaluacion: {hint}")
        if answer:
            answer_str = str(answer).replace("\n", " ").strip()
            lines.append(f"  Respuesta del proveedor: {answer_str}")
            answered_count += 1
        else:
            lines.append("  Respuesta del proveedor: (sin respuesta)")
        lines.append("")

    lines.append(
        f"Total preguntas respondidas: {answered_count} de {len(questions)}."
    )
    lines.append("")
    lines.append(
        "Evalua la madurez de seguridad del proveedor basandote exclusivamente en las respuestas anteriores. "
        "Devuelve el JSON de evaluacion segun el esquema indicado en las instrucciones del sistema."
    )

    return "\n".join(lines)


def _safe_result(error_msg: str) -> dict:
    """Devuelve un dict de error seguro cuando la evaluacion falla."""
    return {
        "error": error_msg,
        "needs_manual_review": True,
        "confidence": 0.0,
        "ai_score": None,
        "control_coverage_assessment": "unclear",
        "evidence_consistency": "no_evidence",
        "red_flags": [],
        "follow_up_questions": [],
        "rationale": f"Evaluacion automatica no disponible: {error_msg}",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def review_questionnaire(
    db: Session,
    questionnaire: Any,
    api_key: str,
    model: str = "claude-opus-4-6",
) -> dict:
    """Evalua un cuestionario de proveedor con IA y devuelve el resultado estructurado.

    Nunca lanza excepciones al caller. En caso de error transitorio o de parseo
    devuelve un dict con 'error' y 'needs_manual_review': True.

    Args:
        db: sesion SQLAlchemy (no se modifica — solo lectura contextual).
        questionnaire: instancia SupplierQuestionnaire con .questions y .answers.
        api_key: clave Anthropic activa para el tenant.
        model: modelo Claude a usar (por defecto claude-opus-4-6).

    Returns:
        dict con los campos del schema de evaluacion.
    """
    if not api_key:
        return _safe_result("API key de Claude no disponible")

    try:
        import anthropic
    except ImportError:
        return _safe_result("Paquete 'anthropic' no instalado")

    try:
        prompt = _build_evaluation_prompt(questionnaire)
    except Exception as exc:
        logger.error("tprm_ai: error construyendo prompt para Q%s: %s", questionnaire.id, exc)
        return _safe_result(f"Error construyendo prompt: {exc}")

    raw: str | None = None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        try:
            message = client.messages.create(
                model=model,
                max_tokens=32768,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            # Reintentar con limite menor si el modelo rechaza el valor maximo
            err_str = str(exc).lower()
            if "max_tokens" in err_str or "maximum" in err_str:
                message = client.messages.create(
                    model=model,
                    max_tokens=16384,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
            else:
                raise

        raw = message.content[0].text.strip() if message.content else ""
        if not raw:
            return _safe_result("El modelo devolvio una respuesta vacia")

    except Exception as exc:
        logger.error("tprm_ai: error llamando a Claude API para Q%s: %s", questionnaire.id, exc)
        return _safe_result(f"Error de API: {exc}")

    # Parsear la respuesta JSON
    try:
        result = _repair_json(raw)
    except Exception as exc:
        logger.error(
            "tprm_ai: JSON invalido para Q%s. Error: %s. Raw[:200]: %s",
            questionnaire.id, exc, raw[:200],
        )
        return _safe_result(f"JSON invalido en respuesta del modelo: {exc}")

    # Guardrails: forzar needs_manual_review si confianza baja
    try:
        confidence = float(result.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    result["confidence"] = confidence

    if confidence < 0.6:
        result["needs_manual_review"] = True

    # Asegurar que needs_manual_review sea bool
    if "needs_manual_review" not in result:
        result["needs_manual_review"] = confidence < 0.6

    # Asegurar listas para campos de array
    for field in ("red_flags", "follow_up_questions"):
        if not isinstance(result.get(field), list):
            result[field] = []

    # Timestamp de la evaluacion
    result["evaluated_at"] = datetime.now(timezone.utc).isoformat()

    return result
