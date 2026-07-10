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
from app.i18n import ai_lang_directive

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
    "7. evidence_consistency SOLO puede afirmarse sobre evidencias cuyo CONTENIDO aparece "
    "analizado en el prompt (seccion 'Evidencia adjunta analizada'). Una evidencia subida "
    "pero no analizada cuenta como no verificada, no como consistente. Si una evidencia "
    "analizada CONTRADICE la respuesta del proveedor, marcalo como red_flag y refleja la "
    "inconsistencia en evidence_consistency. "
    "8. Pondera el juicio con el perfil del proveedor y su historico: un proveedor de tier "
    "critico con issues abiertos exige mas exigencia probatoria. "
    f"Devuelve exactamente este esquema JSON:\n{_EXPECTED_SCHEMA}"
)

# Prompt corto para analizar un fichero de evidencia adjunto a una pregunta
_EVIDENCE_REVIEW_PROMPT = (
    "Eres un auditor TPRM. Analiza el fichero de evidencia que un proveedor adjunto "
    "a una pregunta de un cuestionario de seguridad. Devuelve SOLO JSON: "
    '{"summary": "<2-3 frases de lo que contiene realmente>", '
    '"consistency": "<consistent|contradictory|unrelated>", '
    '"key_facts": ["<hecho verificable>", ...]}. '
    "consistency=consistent solo si el contenido respalda la respuesta declarada; "
    "contradictory si la contradice; unrelated si no tiene relacion. Se estricto."
)


def _evidence_dir():
    from pathlib import Path
    root = Path("/srv/data/evidence")
    if not root.parent.exists():
        root = Path(__file__).parent.parent.parent / "data" / "evidence"
    return root


def analyze_questionnaire_evidence(
    db: Session, questionnaire: Any, api_key: str, model: str,
    max_files: int = 10,
) -> int:
    """Analiza con IA el contenido de las evidencias adjuntas al cuestionario.

    Guarda el resultado en q.evidence[qid]["ai_review"] (cache: no re-analiza).
    Imagenes van por Vision; documentos por extraccion de texto. Devuelve el
    numero de ficheros analizados. Best-effort: nunca lanza al caller.
    """
    import base64
    import json as _json

    evidence: dict = dict(questionnaire.evidence or {})
    if not evidence or not api_key:
        return 0

    try:
        import anthropic
        from app.services.document_service import extract_text
        client = anthropic.Anthropic(api_key=api_key)
    except Exception:
        return 0

    questions_by_id = {
        str(q.get("id")): q for q in (questionnaire.questions or [])
    }
    answers = questionnaire.answers or {}

    analyzed = 0
    for qid, entry in evidence.items():
        if analyzed >= max_files:
            break
        if not isinstance(entry, dict) or entry.get("ai_review"):
            continue
        stored = entry.get("stored_name")
        if not stored:
            continue
        fpath = _evidence_dir() / stored
        if not fpath.exists():
            continue

        question = questions_by_id.get(str(qid), {})
        answer = answers.get(str(qid), answers.get(qid, ""))
        context_txt = (
            f"Pregunta: {question.get('text', '')}\n"
            f"Respuesta declarada por el proveedor: {answer}\n"
            f"Fichero adjunto: {entry.get('filename', stored)}"
        )

        try:
            raw_bytes = fpath.read_bytes()
            ext = stored.lower().rsplit(".", 1)[-1]
            if ext in ("png", "jpg", "jpeg"):
                if len(raw_bytes) > 5 * 1024 * 1024:
                    continue
                media = "image/png" if ext == "png" else "image/jpeg"
                content = [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": media,
                                "data": base64.standard_b64encode(raw_bytes).decode()}},
                    {"type": "text", "text": context_txt},
                ]
            else:
                mime = {"pdf": "application/pdf", "docx": "wordprocessingml",
                        "xlsx": "spreadsheetml"}.get(ext, "text/plain")
                text = extract_text(raw_bytes, mime)
                if len(text.strip()) < 50:
                    continue
                content = [{"type": "text",
                            "text": f"{context_txt}\n\nContenido del fichero:\n{text[:15000]}"}]

            msg = client.messages.create(
                model=model, max_tokens=1024,
                system=_EVIDENCE_REVIEW_PROMPT,
                messages=[{"role": "user", "content": content}],
            )
            raw = msg.content[0].text.strip() if msg.content else "{}"
            review = _repair_json(raw)
            if not isinstance(review, dict) or "consistency" not in review:
                continue
            entry = dict(entry)
            entry["ai_review"] = {
                "summary": str(review.get("summary", ""))[:500],
                "consistency": str(review.get("consistency", "unrelated")),
                "key_facts": [str(f)[:200] for f in (review.get("key_facts") or [])][:5],
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            }
            evidence[qid] = entry
            analyzed += 1

            if entry["ai_review"]["consistency"] == "contradictory":
                _create_contradiction_issue(db, questionnaire, qid, question, entry)
        except Exception as exc:
            logger.warning("tprm_ai: fallo analizando evidencia %s de Q%s: %s",
                           stored, questionnaire.id, exc)

    if analyzed:
        questionnaire.evidence = evidence
        try:
            db.flush()
        except Exception:
            pass
    return analyzed


def _create_contradiction_issue(db: Session, questionnaire: Any, qid: str,
                                question: dict, entry: dict) -> None:
    """Evidencia que contradice la respuesta declarada -> VendorIssue automatico."""
    try:
        from app.models import VendorIssue, VendorIssueSeverity
        title = f"Evidencia contradictoria en {questionnaire.code} (pregunta {qid})"
        dup = (
            db.query(VendorIssue)
            .filter(
                VendorIssue.supplier_id == questionnaire.supplier_id,
                VendorIssue.title == title,
            ).first()
        )
        if dup:
            return
        count = db.query(VendorIssue).filter_by(
            organization_id=questionnaire.organization_id).count()
        issue = VendorIssue(
            organization_id=questionnaire.organization_id,
            code=f"VIS-{count + 1:04d}",
            supplier_id=questionnaire.supplier_id,
            source="questionnaire",
            title=title,
            description=(
                f"Pregunta: {question.get('text', '')[:300]}\n"
                f"El fichero adjunto '{entry.get('filename', '?')}' contradice la "
                f"respuesta declarada segun la revision IA: "
                f"{entry['ai_review'].get('summary', '')}"
            ),
            severity=VendorIssueSeverity.HIGH,
            auto_generated=True,
            auto_generated_source="ai_evidence_review",
        )
        db.add(issue)
        db.flush()
        logger.info("tprm_ai: VendorIssue %s creado por evidencia contradictoria (Q%s)",
                    issue.code, questionnaire.id)
    except Exception:
        logger.debug("tprm_ai: no se pudo crear issue de contradiccion", exc_info=True)


def _build_supplier_profile(db: Session, questionnaire: Any) -> str:
    """Perfil del proveedor + historico para ponderar el juicio del auditor IA."""
    lines: list[str] = []
    try:
        from app.models import Supplier, SupplierQuestionnaire, VendorIssue
        supplier = db.get(Supplier, questionnaire.supplier_id)
        if not supplier:
            return ""
        tier = supplier.tier.value if getattr(supplier, "tier", None) and hasattr(supplier.tier, "value") else getattr(supplier, "tier", None)
        lines.append("PERFIL DEL PROVEEDOR:")
        lines.append(
            f"  Tier: {tier or 'sin calcular'} | Riesgo inherente: "
            f"{supplier.inherent_risk_score if supplier.inherent_risk_score is not None else '?'}/100 "
            f"| Critico para el negocio: {'si' if supplier.is_critical else 'no'}"
        )
        flags = [f for f, on in [
            ("NIS2", getattr(supplier, "is_nis2", False)),
            ("DORA", getattr(supplier, "is_dora", False)),
            ("ENS", getattr(supplier, "is_ens", False)),
            ("encargado GDPR", getattr(supplier, "is_data_processor", False)),
        ] if on]
        if flags:
            lines.append(f"  Alcance regulatorio: {', '.join(flags)}")
        if getattr(supplier, "category", None):
            lines.append(f"  Categoria de servicio: {supplier.category}")

        open_issues = (
            db.query(VendorIssue)
            .filter(
                VendorIssue.supplier_id == supplier.id,
                VendorIssue.status.notin_(["closed", "mitigated"]),
            )
            .order_by(VendorIssue.id.desc())
            .limit(5)
            .all()
        )
        if open_issues:
            lines.append(f"  Issues abiertos ({len(open_issues)}):")
            for issue in open_issues:
                sev = issue.severity.value if hasattr(issue.severity, "value") else issue.severity
                lines.append(f"    - [{sev}] {issue.title[:80]}")

        prev = (
            db.query(SupplierQuestionnaire)
            .filter(
                SupplierQuestionnaire.supplier_id == supplier.id,
                SupplierQuestionnaire.id != questionnaire.id,
                SupplierQuestionnaire.score.isnot(None),
            )
            .order_by(SupplierQuestionnaire.submitted_at.desc())
            .limit(3)
            .all()
        )
        if prev:
            hist = ", ".join(
                f"{p.score}/100 ({p.submitted_at.strftime('%Y-%m') if p.submitted_at else '?'})"
                for p in prev
            )
            lines.append(f"  Cuestionarios anteriores: {hist}")
    except Exception:
        logger.debug("tprm_ai: perfil de proveedor no disponible", exc_info=True)
        return ""
    return "\n".join(lines)


def _build_evaluation_prompt(questionnaire: Any, lang: str = "es",
                             db: Session | None = None) -> str:
    """Construye el prompt de usuario con las preguntas y respuestas del cuestionario.

    Incluye ademas: perfil del proveedor (tier, riesgo inherente, alcance
    regulatorio, issues abiertos, historico de scores) y el contenido
    ANALIZADO de las evidencias adjuntas (q.evidence[qid].ai_review).
    El andamiaje del prompt permanece en espanol; solo la SALIDA del modelo
    (red_flags, follow_up_questions, rationale) debe respetar *lang*.
    """
    questions: list[dict] = questionnaire.questions or []
    answers: dict = questionnaire.answers or {}
    evidence: dict = questionnaire.evidence or {}

    lines: list[str] = [
        f"Cuestionario: {questionnaire.title or questionnaire.code}",
        "",
    ]

    if db is not None:
        profile = _build_supplier_profile(db, questionnaire)
        if profile:
            lines.append(profile)
            lines.append("")

    lines.append(
        "A continuacion se listan las preguntas del cuestionario, sus referencias de control "
        "y las respuestas proporcionadas por el proveedor:"
    )
    lines.append("")

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

        ev_entry = evidence.get(qid) or evidence.get(str(i))
        if isinstance(ev_entry, dict):
            review = ev_entry.get("ai_review")
            if review:
                lines.append(
                    f"  Evidencia adjunta analizada ({ev_entry.get('filename', '?')}): "
                    f"consistencia={review.get('consistency', '?')} — {review.get('summary', '')}"
                )
                for fact in (review.get("key_facts") or [])[:3]:
                    lines.append(f"    · {fact}")
            else:
                lines.append(
                    f"  Evidencia adjunta SIN ANALIZAR ({ev_entry.get('filename', '?')}): "
                    "cuenta como no verificada."
                )
        lines.append("")

    lines.append(
        f"Total preguntas respondidas: {answered_count} de {len(questions)}."
    )
    lines.append("")
    lines.append(
        "Evalua la madurez de seguridad del proveedor basandote exclusivamente en las respuestas "
        "y evidencias analizadas anteriores, ponderando con su perfil e historico. "
        "Devuelve el JSON de evaluacion segun el esquema indicado en las instrucciones del sistema."
    )

    return ai_lang_directive(lang) + "\n\n" + "\n".join(lines)


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
    lang: str = "es",
) -> dict:
    """Evalua un cuestionario de proveedor con IA y devuelve el resultado estructurado.

    Nunca lanza excepciones al caller. En caso de error transitorio o de parseo
    devuelve un dict con 'error' y 'needs_manual_review': True.

    Args:
        db: sesion SQLAlchemy (no se modifica — solo lectura contextual).
        questionnaire: instancia SupplierQuestionnaire con .questions y .answers.
        api_key: clave Anthropic activa para el tenant.
        model: modelo Claude a usar (por defecto claude-opus-4-5).
        lang: idioma de SALIDA del modelo (es/en). El andamiaje del prompt
            permanece en espanol; solo los campos de texto libre respetan lang.

    Returns:
        dict con los campos del schema de evaluacion.
    """
    if not api_key:
        return _safe_result("API key de Claude no disponible")

    try:
        import anthropic
    except ImportError:
        return _safe_result("Paquete 'anthropic' no instalado")

    # Analizar primero el contenido de las evidencias adjuntas (tier fast):
    # la evaluacion solo puede afirmar consistencia sobre lo analizado
    try:
        from app.services.model_registry import MODEL_TIERS
        analyze_questionnaire_evidence(
            db, questionnaire, api_key, MODEL_TIERS["fast"])
    except Exception as exc:
        logger.warning("tprm_ai: analisis de evidencias fallo para Q%s: %s",
                       questionnaire.id, exc)

    try:
        prompt = _build_evaluation_prompt(questionnaire, lang, db=db)
    except Exception as exc:
        logger.error("tprm_ai: error construyendo prompt para Q%s: %s", questionnaire.id, exc)
        return _safe_result(f"Error construyendo prompt: {exc}")

    system_prompt = ai_lang_directive(lang) + "\n\n" + _SYSTEM_PROMPT

    raw: str | None = None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        try:
            message = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            # Reintentar con limite menor si el modelo rechaza el valor maximo
            err_str = str(exc).lower()
            if "max_tokens" in err_str or "maximum" in err_str:
                message = client.messages.create(
                    model=model,
                    max_tokens=2048,
                    system=system_prompt,
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
