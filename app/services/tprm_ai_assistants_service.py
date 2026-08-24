"""Asistentes de IA del modulo de proveedores (feedback cliente, punto 14).

Tres asistentes, todos advisory: la IA PROPONE, Seguridad aprueba. Nunca escriben
en el proveedor por su cuenta.
 - suggest_classification: importancia de negocio, riesgo de seguridad, frecuencia
   de revision y evaluaciones requeridas tras alta/import.
 - analyze_supplier: datos/acuerdos/evaluaciones faltantes, revisiones vencidas y
   acciones recomendadas (base determinista + narrativa IA).
 - review_assistant: resumen de la revision a partir de evaluaciones, hallazgos,
   eventos, incidentes e historial de riesgo, con acciones y recomendaciones.

Usa structured_message + model_registry (convencion del proyecto).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.i18n import ai_lang_directive

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base determinista: hechos que no necesitan IA (y que la IA no debe inventar)
# ---------------------------------------------------------------------------

def compute_gaps(db: Session, supplier) -> dict:
    """Huecos objetivos del proveedor (sin IA). Alimenta analyze_supplier."""
    from app.models import SupplierQuestionnaire, VendorIssue, VendorRiskAssessment

    missing_data = []
    if not supplier.business_importance_level:
        missing_data.append("Importancia de negocio sin clasificar")
    if not supplier.security_risk_level:
        missing_data.append("Riesgo de seguridad sin clasificar")
    if not supplier.owner_id:
        missing_data.append("Sin Owner asignado")
    if not supplier.operating_region:
        missing_data.append("Sin región operativa")
    if not supplier.contact_email:
        missing_data.append("Sin email de contacto")

    missing_agreements = []
    if (supplier.processes_personal_data or supplier.is_data_processor) and not supplier.dpa_signed_at:
        missing_agreements.append("DPA (Art. 28 GDPR) sin firmar")
    if not supplier.contract_document_id and not supplier.contract_ref:
        missing_agreements.append("Contrato sin registrar")

    q_count = db.query(SupplierQuestionnaire).filter(
        SupplierQuestionnaire.supplier_id == supplier.id).count()
    q_submitted = db.query(SupplierQuestionnaire).filter(
        SupplierQuestionnaire.supplier_id == supplier.id,
        SupplierQuestionnaire.submitted_at.isnot(None)).count()
    assessments = db.query(VendorRiskAssessment).filter(
        VendorRiskAssessment.supplier_id == supplier.id).count()
    missing_assessments = []
    if q_count == 0:
        missing_assessments.append("Nunca se ha enviado un cuestionario")
    elif q_submitted == 0:
        missing_assessments.append("Cuestionario enviado pero sin respuesta")
    if assessments == 0:
        missing_assessments.append("Sin evaluación de riesgo consolidada")

    overdue_reviews = []
    review_status = supplier.review_status
    if review_status == "review_overdue":
        overdue_reviews.append("Revisión vencida")
    elif review_status in ("review_due_30", "review_due_60", "review_due_90"):
        overdue_reviews.append(f"Revisión próxima ({review_status})")

    open_issues = db.query(VendorIssue).filter(
        VendorIssue.supplier_id == supplier.id,
        VendorIssue.status.in_(["open", "acknowledged", "in_remediation", "overdue"]),
    ).count()

    return {
        "missing_data": missing_data,
        "missing_agreements": missing_agreements,
        "missing_assessments": missing_assessments,
        "overdue_reviews": overdue_reviews,
        "open_issues": open_issues,
        "questionnaires": {"total": q_count, "submitted": q_submitted},
        "assessments": assessments,
    }


def _supplier_context(db: Session, supplier) -> str:
    """Perfil compacto del proveedor para el prompt."""
    from app.models import SupplierEvent, VendorIssue

    lines = [
        f"Proveedor: {supplier.name}",
        f"Categoria: {supplier.category or '—'} | Tipo: {supplier.vendor_type or '—'}",
        f"Servicios: {(supplier.services or '—')[:300]}",
        f"Importancia negocio: {supplier.business_importance_level or 'sin clasificar'}",
        f"Riesgo seguridad: {supplier.security_risk_level or 'sin clasificar'}",
        f"Tier/inherent/residual: {supplier.tier.value if supplier.tier else '—'} / "
        f"{supplier.inherent_risk_score} / {supplier.residual_risk_score}",
        f"Acceso a sistemas: {supplier.system_access_type or '—'}",
        f"Datos: sensibilidad {supplier.data_sensitivity}, volumen {supplier.data_volume}",
        f"Trata datos personales: {supplier.processes_personal_data} | Encargado GDPR: {supplier.is_data_processor}",
        f"Flags: NIS2={supplier.is_nis2} DORA={supplier.is_dora} ENS={supplier.is_ens}",
        f"Region: {supplier.operating_region or '—'} | Pais: {supplier.country_code or '—'}",
        f"Estado seguridad: {supplier.security_status or '—'} | Estado revision: {supplier.review_status}",
    ]
    issues = db.query(VendorIssue).filter(
        VendorIssue.supplier_id == supplier.id).order_by(VendorIssue.discovered_at.desc()).limit(10).all()
    if issues:
        lines.append("Hallazgos recientes:")
        for i in issues:
            sev = i.severity.value if i.severity else "—"
            st = i.status.value if i.status else "—"
            lines.append(f"  - [{sev}/{st}] {i.title}")
    events = db.query(SupplierEvent).filter(
        SupplierEvent.supplier_id == supplier.id).order_by(SupplierEvent.occurred_at.desc()).limit(10).all()
    if events:
        lines.append("Eventos recientes:")
        for e in events:
            lines.append(f"  - [{e.event_type}] {e.title}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Esquemas de salida (tool use forzado)
# ---------------------------------------------------------------------------

_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "business_importance_level": {"type": "string",
            "enum": ["not_relevant", "normal", "important", "critical"]},
        "security_risk_level": {"type": "string",
            "enum": ["very_low", "low", "medium", "high", "critical"]},
        "review_frequency": {"type": "string",
            "enum": ["monthly", "quarterly", "semiannual", "annual", "biennial"]},
        "required_assessments": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["business_importance_level", "security_risk_level",
                 "review_frequency", "rationale", "confidence"],
}

_ANALYZE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
        "priority": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["summary", "recommended_actions"],
}

_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "review_summary": {"type": "string"},
        "suggested_actions": {"type": "array", "items": {"type": "string"}},
        "reassessment_recommendations": {"type": "array", "items": {"type": "string"}},
        "overall_posture": {"type": "string",
            "enum": ["improving", "stable", "deteriorating", "unknown"]},
        "confidence": {"type": "number"},
    },
    "required": ["review_summary", "suggested_actions", "reassessment_recommendations"],
}


def _call_ai(api_key: str, model: str, system: str, prompt: str, schema: dict,
             tool_name: str, org_id: Optional[int], call_type: str) -> dict:
    from app.services.claude_client import structured_message
    result, _msg = structured_message(
        api_key, model=model, max_tokens=2048,
        system=system, messages=[{"role": "user", "content": prompt}],
        tool_name=tool_name, tool_description="Registra la salida estructurada",
        input_schema=schema, org_id=org_id, call_type=call_type,
    )
    return result


# ---------------------------------------------------------------------------
# Asistentes
# ---------------------------------------------------------------------------

def suggest_classification(db: Session, supplier, api_key: str, model: str,
                           lang: str = "es") -> dict:
    """Sugiere importancia/riesgo/frecuencia/evaluaciones. Advisory (Seguridad aprueba)."""
    ctx = _supplier_context(db, supplier)
    system = ai_lang_directive(lang) + (
        "\nEres un analista TPRM. Propon una clasificacion inicial para el proveedor "
        "a partir de su perfil. La decision final es de Seguridad; tu salida es una "
        "sugerencia. Se conservador cuando falten datos y explica el porque.")
    prompt = (
        f"Perfil del proveedor:\n{ctx}\n\n"
        "Sugiere: importancia de negocio, nivel de riesgo de seguridad, frecuencia de "
        "revision y que evaluaciones/cuestionarios deberian requerirse (por ejemplo "
        "ISO 27001, NIS2, GDPR/DPA, uso de IA). Da confianza 0-1.")
    result = _call_ai(api_key, model, system, prompt, _CLASSIFY_SCHEMA,
                      "sugerir_clasificacion", getattr(supplier, "organization_id", None),
                      "tprm_ai_classify")
    result["advisory"] = True
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    return result


def analyze_supplier(db: Session, supplier, api_key: str, model: str,
                     lang: str = "es") -> dict:
    """Analiza huecos (base determinista) + narrativa y acciones IA."""
    gaps = compute_gaps(db, supplier)
    ctx = _supplier_context(db, supplier)
    system = ai_lang_directive(lang) + (
        "\nEres un analista TPRM. A partir de los huecos detectados y el perfil, "
        "resume el estado del proveedor y propon acciones concretas priorizadas.")
    prompt = (
        f"Perfil:\n{ctx}\n\nHuecos detectados (deterministas):\n"
        f"- Datos faltantes: {gaps['missing_data']}\n"
        f"- Acuerdos faltantes: {gaps['missing_agreements']}\n"
        f"- Evaluaciones faltantes: {gaps['missing_assessments']}\n"
        f"- Revisiones: {gaps['overdue_reviews']}\n"
        f"- Hallazgos abiertos: {gaps['open_issues']}\n\n"
        "Resume y propon acciones recomendadas.")
    try:
        ai = _call_ai(api_key, model, system, prompt, _ANALYZE_SCHEMA,
                      "analizar_proveedor", getattr(supplier, "organization_id", None),
                      "tprm_ai_analyze")
    except Exception as exc:  # noqa: BLE001
        logger.warning("analyze_supplier IA fallo: %s", exc)
        ai = {"summary": "Análisis IA no disponible.", "recommended_actions": []}
    # Fusion: hechos deterministas + narrativa IA
    return {
        "missing_data": gaps["missing_data"],
        "missing_agreements": gaps["missing_agreements"],
        "missing_assessments": gaps["missing_assessments"],
        "overdue_reviews": gaps["overdue_reviews"],
        "open_issues": gaps["open_issues"],
        "summary": ai.get("summary", ""),
        "recommended_actions": ai.get("recommended_actions", []),
        "priority": ai.get("priority", "medium"),
        "advisory": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def review_assistant(db: Session, supplier, api_key: str, model: str,
                     lang: str = "es") -> dict:
    """Resume la revision a partir del historial completo del proveedor."""
    from app.models import Risk, VendorRiskAssessment

    ctx = _supplier_context(db, supplier)
    assessments = db.query(VendorRiskAssessment).filter(
        VendorRiskAssessment.supplier_id == supplier.id).order_by(
        VendorRiskAssessment.assessment_date.desc()).limit(5).all()
    hist = []
    for a in assessments:
        hist.append(f"  - {a.period_label or a.code}: residual {a.residual_risk_level or '—'}, "
                    f"recomendacion {a.recommendation.value if a.recommendation else '—'}")
    linked_risks = db.query(Risk).filter(Risk.supplier_id == supplier.id).limit(10).all() \
        if hasattr(Risk, "supplier_id") else []
    risk_lines = [f"  - {r.title} (nivel residual {getattr(r, 'residual_level', '—')})"
                  for r in linked_risks]

    system = ai_lang_directive(lang) + (
        "\nEres un analista TPRM senior preparando la revision periodica de un "
        "proveedor. Sintetiza evaluaciones, hallazgos, eventos e historial de riesgo. "
        "Da un resumen, acciones sugeridas y recomendaciones para la reevaluacion.")
    prompt = (
        f"Perfil:\n{ctx}\n\n"
        f"Historial de evaluaciones:\n{chr(10).join(hist) or '  (ninguna)'}\n\n"
        f"Riesgos vinculados:\n{chr(10).join(risk_lines) or '  (ninguno)'}\n\n"
        "Prepara el resumen de la revision.")
    result = _call_ai(api_key, model, system, prompt, _REVIEW_SCHEMA,
                      "resumen_revision", getattr(supplier, "organization_id", None),
                      "tprm_ai_review_assistant")
    result["advisory"] = True
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    return result
