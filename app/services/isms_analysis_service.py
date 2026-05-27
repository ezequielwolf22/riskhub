"""Analisis automatico ISMS de documentos subidos al agente IA.

Cuando un documento queda INDEXED, este servicio llama al agente IA para:
  1. Detectar si el documento es una politica y crear/actualizar la entrada en Policy.
  2. Identificar controles ISO 27002 cubiertos y actualizar ControlImplementation.
  3. Detectar categorias de amenaza abordadas y crear TreatmentTask para riesgos activos.

El analisis se ejecuta en background (BackgroundTasks de FastAPI) para no bloquear
la respuesta HTTP de subida de documento.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.models import (
    AiCallLog, AiConfig, AiDocument, AiDocumentStatus,
    Control, ControlImplementation, ControlStatus,
    Policy, PolicyStatus,
    Risk, RiskStatus,
    TaskPriority, TaskStatus, TreatmentTask,
    User,
)

logger = logging.getLogger(__name__)

# ---------- Prompt del sistema ----------

_ISMS_SYSTEM_PROMPT = """Eres un experto en seguridad de la informacion (ISO/IEC 27001/27002/27005).
Analiza el siguiente fragmento de documento y devuelve UNICAMENTE un objeto JSON valido con esta estructura:

{
  "is_policy": <true | false>,
  "policy": {
    "title": "<titulo del documento>",
    "category": "<categoria, ej: Seguridad fisica, Uso aceptable, Gestion de incidentes...>",
    "version": "<version, ej: '1.0'>",
    "scope": "<alcance resumido, max 200 palabras>",
    "content": "<resumen del contenido, max 400 palabras>",
    "review_date": "<fecha ISO YYYY-MM-DD o null>",
    "review_cycle_months": <entero, ej: 12>,
    "iso_clauses": ["<clausula ISO 27001>", ...]
  },
  "controls_covered": [
    {
      "code": "<codigo ISO 27002:2022, ej: 5.1>",
      "name": "<nombre del control>",
      "coverage": "<full | partial>",
      "evidence_note": "<nota breve de evidencia>"
    }
  ],
  "threat_categories_addressed": ["<categoria de amenaza>", ...],
  "overall_summary": "<resumen ejecutivo, max 200 palabras>"
}

REGLAS:
- Devuelve SOLO el JSON. Sin texto ni markdown antes ni despues.
- Si el documento NO es una politica de seguridad, pon is_policy=false y policy=null.
- controls_covered: solo controles ISO 27002:2022 identificados con confianza alta.
  Usa los codigos reales del estandar (5.1, 5.2, ... 8.34).
- threat_categories_addressed: categorias de amenazas ISO 27005 Annex C que el documento
  ayuda a mitigar (Physical damage, Natural events, Loss of services, Technical failures,
  Unauthorised actions, Compromise of functions, etc.).
- Si encuentras fechas de revision o vigencia en el documento, extrae review_date.
  Si no hay fecha explicita, pon null.
- review_cycle_months: ciclo de revision tipico para el tipo de documento (12 si no se indica).
"""


# ---------- Helpers ----------

def _get_api_key(db: Session, organization_id: int | None) -> str | None:
    """Obtiene la API key del agente IA para la organizacion dada."""
    cfg = db.query(AiConfig).filter_by(organization_id=organization_id).first()
    if cfg and cfg.api_key_encrypted:
        try:
            from cryptography.fernet import Fernet
            from app.services.document_service import _fernet_key
            return Fernet(_fernet_key()).decrypt(cfg.api_key_encrypted.encode()).decode()
        except Exception:
            pass
    # Fallback: variable de entorno global
    from app.config import settings
    return settings.anthropic_api_key or None


def _get_model(db: Session, organization_id: int | None) -> str:
    cfg = db.query(AiConfig).filter_by(organization_id=organization_id).first()
    return cfg.model if cfg and cfg.model else "claude-opus-4-5"


def _org_owner(db: Session, organization_id: int | None) -> int | None:
    """Devuelve el id del primer usuario activo de la org (para asignar ownership)."""
    user = db.query(User).filter_by(
        organization_id=organization_id, is_active=True
    ).order_by(User.id).first()
    return user.id if user else None


def _strip_fence(raw: str) -> str:
    """Elimina code fences Markdown si el modelo las anade."""
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```", 2)
        inner = parts[1] if len(parts) > 1 else raw
        if inner.startswith("json"):
            inner = inner[4:]
        raw = inner.rsplit("```", 1)[0].strip()
    return raw


# ---------- Punto de entrada ----------

def analyze_document_for_isms(db: Session, doc_id: int) -> None:
    """Analiza el documento y aplica los resultados al SGSI.

    Se ejecuta en background; no lanza excepciones al llamador.
    """
    doc = db.get(AiDocument, doc_id)
    if not doc or doc.status != AiDocumentStatus.INDEXED:
        return

    doc.isms_status = "analysing"
    db.commit()

    try:
        api_key = _get_api_key(db, doc.organization_id)
        if not api_key:
            doc.isms_status = "skipped"
            doc.isms_summary = {"reason": "No hay API key configurada para el agente IA"}
            db.commit()
            return

        # Recopilar hasta 25 chunks (~14 000 chars)
        chunks = sorted(doc.chunks, key=lambda c: c.chunk_index)[:25]
        if not chunks:
            doc.isms_status = "skipped"
            doc.isms_summary = {"reason": "Documento sin contenido indexado"}
            db.commit()
            return

        text_sample = "\n\n".join(c.content for c in chunks)[:14000]

        # Llamar al agente IA
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        model = _get_model(db, doc.organization_id)

        message = client.messages.create(
            model=model,
            max_tokens=2048,
            system=_ISMS_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Nombre del documento: {doc.original_name}\n\nContenido:\n{text_sample}",
            }],
        )
        raw_json = _strip_fence(message.content[0].text)

        # Registrar uso de tokens
        call_log = AiCallLog(
            organization_id=doc.organization_id,
            call_type="isms_analysis",
            prompt_tokens=message.usage.input_tokens,
            completion_tokens=message.usage.output_tokens,
            model=model,
            anonymized=False,
            response_summary=f"ISMS analysis for doc {doc_id}: {doc.original_name[:60]}",
        )
        db.add(call_log)

        analysis = json.loads(raw_json)
        owner_id = _org_owner(db, doc.organization_id)

        result = {
            "policy_id": None,
            "controls_updated": 0,
            "tasks_created": 0,
            "summary": analysis.get("overall_summary", ""),
        }

        if analysis.get("is_policy") and analysis.get("policy"):
            result["policy_id"] = _create_or_update_policy(
                db, doc, analysis["policy"], owner_id
            )

        controls = analysis.get("controls_covered") or []
        if controls:
            result["controls_updated"] = _update_controls(db, doc, controls, owner_id)

        threat_cats = analysis.get("threat_categories_addressed") or []
        if threat_cats:
            result["tasks_created"] = _create_treatment_tasks(
                db, doc, threat_cats, owner_id
            )

        doc.isms_status = "analysed"
        doc.isms_summary = result
        db.commit()
        logger.info(
            "ISMS analysis OK doc=%d policy=%s controls=%d tasks=%d",
            doc_id, result["policy_id"], result["controls_updated"], result["tasks_created"],
        )

    except Exception as exc:
        logger.error("ISMS analysis failed doc=%d: %s", doc_id, exc)
        try:
            doc.isms_status = "error"
            doc.isms_summary = {"error": str(exc)[:500]}
            db.commit()
        except Exception:
            pass


# ---------- Creacion/actualizacion de politica ----------

def _next_policy_code(db: Session, org_id: int | None) -> str:
    last = (
        db.query(Policy)
        .filter(Policy.organization_id == org_id, Policy.code.like("POL-%"))
        .order_by(Policy.id.desc())
        .first()
    )
    num = 1
    if last:
        try:
            num = int(last.code.split("-")[1]) + 1
        except (ValueError, IndexError):
            pass
    code = f"POL-{num:04d}"
    while db.query(Policy).filter_by(code=code).first():
        num += 1
        code = f"POL-{num:04d}"
    return code


def _create_or_update_policy(
    db: Session, doc: AiDocument, pol_data: dict, owner_id: int | None
) -> int | None:
    """Crea o actualiza la Policy vinculada a este documento."""
    existing = db.query(Policy).filter_by(source_document_id=doc.id).first()

    # Calcular fecha de revision
    review_date = None
    if pol_data.get("review_date"):
        try:
            review_date = datetime.fromisoformat(pol_data["review_date"])
        except ValueError:
            pass
    cycle_months = int(pol_data.get("review_cycle_months") or 12)
    if review_date is None:
        review_date = datetime.now(timezone.utc) + timedelta(days=cycle_months * 30)

    if existing:
        existing.title = pol_data.get("title") or existing.title
        existing.version = pol_data.get("version") or existing.version or "1.0"
        existing.category = pol_data.get("category") or existing.category
        existing.scope = pol_data.get("scope") or existing.scope
        existing.content = pol_data.get("content") or existing.content
        existing.iso_clauses = pol_data.get("iso_clauses") or existing.iso_clauses
        existing.review_date = review_date
        existing.review_cycle_months = cycle_months
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        return existing.id

    code = _next_policy_code(db, doc.organization_id)
    pol = Policy(
        organization_id=doc.organization_id,
        code=code,
        title=pol_data.get("title") or doc.original_name,
        version=pol_data.get("version") or "1.0",
        category=pol_data.get("category") or "General",
        status=PolicyStatus.DRAFT,
        scope=pol_data.get("scope") or "",
        content=pol_data.get("content") or "",
        iso_clauses=pol_data.get("iso_clauses") or [],
        review_date=review_date,
        review_cycle_months=cycle_months,
        owner_id=owner_id,
        source_document_id=doc.id,
    )
    db.add(pol)
    db.commit()
    db.refresh(pol)
    return pol.id


# ---------- Actualizacion de controles ----------

_STATUS_RANK = {
    ControlStatus.NOT_IMPLEMENTED: 0,
    ControlStatus.PLANNED: 1,
    ControlStatus.PARTIAL: 2,
    ControlStatus.IMPLEMENTED: 3,
}


def _update_controls(
    db: Session, doc: AiDocument, controls_covered: list, owner_id: int | None
) -> int:
    """Actualiza ControlImplementation para los controles cubiertos por el documento."""
    updated = 0
    for ctrl_data in controls_covered:
        code = (ctrl_data.get("code") or "").strip()
        if not code:
            continue

        control = db.query(Control).filter_by(code=code).first()
        if not control:
            # Intentar sin prefijo 'A.' (ej: "A.5.1" -> "5.1")
            code_alt = code.lstrip("A.").strip()
            control = db.query(Control).filter_by(code=code_alt).first()
        if not control:
            logger.debug("Control no encontrado en catalogo: %s", code)
            continue

        coverage = ctrl_data.get("coverage", "partial")
        note = ctrl_data.get("evidence_note", "")
        new_status = ControlStatus.IMPLEMENTED if coverage == "full" else ControlStatus.PARTIAL
        new_maturity = 3 if coverage == "full" else 2

        doc_ref = {
            "title": f"[Auto] {doc.original_name}",
            "url": f"/api/ai/documents/{doc.id}",
            "note": note[:200] if note else "",
        }

        impl = db.query(ControlImplementation).filter_by(
            organization_id=doc.organization_id,
            control_id=control.id,
        ).first()

        if impl:
            # Solo mejorar el estado, nunca degradar
            if _STATUS_RANK.get(new_status, 0) > _STATUS_RANK.get(impl.status, 0):
                impl.status = new_status
            if new_maturity > (impl.maturity or 0):
                impl.maturity = new_maturity
            refs = list(impl.evidence_refs or [])
            if not any(r.get("title") == doc_ref["title"] for r in refs):
                refs.append(doc_ref)
                impl.evidence_refs = refs
            if note and not impl.evidence:
                impl.evidence = note
        else:
            impl = ControlImplementation(
                organization_id=doc.organization_id,
                control_id=control.id,
                name=ctrl_data.get("name") or control.name,
                description=f"Identificado automaticamente desde: {doc.original_name}",
                status=new_status,
                maturity=new_maturity,
                owner_id=owner_id,
                evidence=note,
                evidence_refs=[doc_ref],
            )
            db.add(impl)

        updated += 1

    db.commit()
    return updated


# ---------- Creacion de tareas de tratamiento ----------

def _next_task_code(db: Session, org_id: int | None) -> str:
    last = (
        db.query(TreatmentTask)
        .filter(TreatmentTask.organization_id == org_id, TreatmentTask.code.like("TSK-%"))
        .order_by(TreatmentTask.id.desc())
        .first()
    )
    num = 1
    if last:
        try:
            num = int(last.code.split("-")[1]) + 1
        except (ValueError, IndexError):
            pass
    code = f"TSK-{num:04d}"
    while db.query(TreatmentTask).filter_by(code=code).first():
        num += 1
        code = f"TSK-{num:04d}"
    return code


def _create_treatment_tasks(
    db: Session, doc: AiDocument, threat_cats: list, owner_id: int | None
) -> int:
    """Crea TreatmentTask para riesgos activos cuya amenaza cae en las categorias identificadas."""
    if not threat_cats:
        return 0

    active_risks = (
        db.query(Risk)
        .filter(
            Risk.organization_id == doc.organization_id,
            Risk.status.in_([RiskStatus.IDENTIFIED, RiskStatus.ASSESSED]),
        )
        .all()
    )

    threat_cats_lower = [c.lower() for c in threat_cats]
    created = 0

    for risk in active_risks:
        threat = risk.threat
        if not threat:
            continue
        threat_cat = (threat.category or "").lower()
        match = any(
            tc in threat_cat or threat_cat in tc
            for tc in threat_cats_lower
        )
        if not match:
            continue

        # No crear tarea duplicada para el mismo riesgo + documento
        dup = db.query(TreatmentTask).filter(
            TreatmentTask.organization_id == doc.organization_id,
            TreatmentTask.risk_id == risk.id,
            TreatmentTask.description.like(f"%{doc.original_name[:60]}%"),
        ).first()
        if dup:
            continue

        # Prioridad segun nivel de riesgo residual
        lvl = risk.residual_level or 0
        if lvl >= 6:
            priority = TaskPriority.CRITICAL
        elif lvl >= 4:
            priority = TaskPriority.HIGH
        elif lvl >= 2:
            priority = TaskPriority.MEDIUM
        else:
            priority = TaskPriority.LOW

        asset_name = risk.asset.name if risk.asset else risk.code
        code = _next_task_code(db, doc.organization_id)

        task = TreatmentTask(
            organization_id=doc.organization_id,
            code=code,
            title=f"Tratar {asset_name} — {threat.name}",
            description=(
                f"Tarea generada automaticamente al analizar el documento: {doc.original_name}.\n"
                f"El documento aborda amenazas de tipo '{threat.category}' que afectan a este riesgo.\n"
                f"Revisar e implementar los controles identificados en el documento."
            ),
            risk_id=risk.id,
            status=TaskStatus.PENDING,
            priority=priority,
            due_date=datetime.now(timezone.utc) + timedelta(days=90),
            assigned_to_id=owner_id,
            created_by_id=owner_id,
        )
        db.add(task)
        created += 1

    if created > 0:
        db.commit()
    return created
