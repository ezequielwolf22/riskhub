"""Generacion de informes ejecutivos mediante Claude API.

Soporta cuatro tipos de informe, cada uno con su propio prompt especializado.
Los datos se recogen de la BD y se pasan al modelo; la respuesta es JSON
estructurado que luego el router formatea como PDF o Excel.
"""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models import ControlImplementation, Risk, RiskContext, RiskStatus

REPORT_TYPES = {
    "treatment_plan": "Plan de Tratamiento de Riesgos",
    "executive_dashboard": "Dashboard Ejecutivo",
    "committee_minutes": "Acta de Comite de Seguridad de la Informacion",
    "followup_report": "Informe de Seguimiento ISO 27005 cl. 12",
}


def _collect(db: Session) -> dict:
    ctx = db.query(RiskContext).first()
    risks = db.query(Risk).order_by(Risk.residual_level.desc()).all()
    impls = db.query(ControlImplementation).all()

    risk_rows = []
    for r in risks:
        risk_rows.append({
            "code": r.code,
            "asset": r.asset.name if r.asset else "-",
            "asset_type": r.asset.asset_type.value if r.asset and r.asset.asset_type else "-",
            "threat": r.threat.name if r.threat else "-",
            "threat_category": r.threat.category if r.threat else "-",
            "inherent": r.inherent_level,
            "residual": r.residual_level,
            "status": r.status.value if r.status else "-",
            "treatment": r.treatment_option.value if r.treatment_option else None,
            "treatment_plan": (r.treatment_plan or "")[:300],
            "description": (r.description or "")[:200],
            "due_date": r.treatment_due_date.isoformat() if r.treatment_due_date else None,
            "accepted": r.status == RiskStatus.ACCEPTED,
            "acceptance_justification": r.acceptance_justification or "",
        })

    control_stats = {
        "total": len(impls),
        "implemented": sum(1 for i in impls if i.status.value == "implemented"),
        "partial": sum(1 for i in impls if i.status.value == "partial"),
        "planned": sum(1 for i in impls if i.status.value == "planned"),
        "not_implemented": sum(1 for i in impls if i.status.value == "not_implemented"),
    }

    stats = {
        "total": len(risks),
        "critical": sum(1 for r in risks if r.residual_level >= 7),
        "high": sum(1 for r in risks if 5 <= r.residual_level < 7),
        "medium": sum(1 for r in risks if 3 <= r.residual_level < 5),
        "low": sum(1 for r in risks if r.residual_level < 3),
        "with_treatment": sum(1 for r in risks if r.treatment_option),
        "accepted": sum(1 for r in risks if r.status == RiskStatus.ACCEPTED),
        "treated": sum(1 for r in risks if r.status == RiskStatus.TREATED),
    }

    return {
        "org": ctx.organization_name if ctx else "Organizacion",
        "scope": (ctx.scope or "") if ctx else "",
        "appetite": ctx.risk_appetite if ctx else 3,
        "date": datetime.now().strftime("%d/%m/%Y"),
        "risks": risk_rows,
        "stats": stats,
        "controls": control_stats,
    }


def _prompt_treatment_plan(data: dict) -> str:
    risks_json = json.dumps(data["risks"][:40], ensure_ascii=False, indent=2)
    return f"""Eres un experto en gestión del riesgo de seguridad de la información certificado en ISO/IEC 27005:2018 y CISM.

Genera un Plan de Tratamiento de Riesgos completo y profesional en ESPAÑOL para la siguiente organización.

CONTEXTO ORGANIZACIONAL:
- Organización: {data['org']}
- Alcance: {data['scope']}
- Apetito de riesgo (máximo aceptable): Nivel {data['appetite']} sobre 8
- Fecha: {data['date']}
- Estadísticas: {json.dumps(data['stats'], ensure_ascii=False)}
- Controles: {json.dumps(data['controls'], ensure_ascii=False)}

REGISTRO DE RIESGOS (top {min(40, len(data['risks']))} por nivel residual):
{risks_json}

Responde ÚNICAMENTE con un JSON válido (sin markdown) con esta estructura exacta:
{{
  "title": "Plan de Tratamiento de Riesgos",
  "organization": "{data['org']}",
  "date": "{data['date']}",
  "executive_summary": "Párrafo de resumen ejecutivo de 3-4 frases que contextualice el estado del riesgo.",
  "risk_appetite_analysis": "Análisis de 2 frases sobre el cumplimiento del apetito de riesgo.",
  "risks": [
    {{
      "code": "RSK-XXXX",
      "priority": "inmediato|corto_plazo|medio_plazo|largo_plazo",
      "treatment_narrative": "Descripción detallada del tratamiento recomendado (3-5 frases).",
      "recommended_actions": ["Acción concreta 1", "Acción concreta 2", "Acción concreta 3"],
      "success_metrics": "Cómo medir el éxito del tratamiento.",
      "estimated_effort": "Bajo|Medio|Alto",
      "target_residual_level": 2
    }}
  ],
  "implementation_roadmap": "Descripción del plan de implementación en 3 fases con plazos.",
  "conclusion": "Párrafo de conclusión y siguientes pasos."
}}"""


def _prompt_executive_dashboard(data: dict) -> str:
    top5 = json.dumps(data["risks"][:5], ensure_ascii=False, indent=2)
    return f"""Eres el CISO de {data['org']} preparando un informe ejecutivo para el Comité de Dirección.

DATOS DE GESTIÓN DEL RIESGO — {data['date']}:
Estadísticas: {json.dumps(data['stats'], ensure_ascii=False)}
Controles: {json.dumps(data['controls'], ensure_ascii=False)}
Apetito de riesgo: Nivel {data['appetite']}/8
Top 5 riesgos más críticos:
{top5}

Genera un JSON ejecutivo en ESPAÑOL (sin markdown):
{{
  "title": "Dashboard Ejecutivo de Seguridad de la Información",
  "organization": "{data['org']}",
  "date": "{data['date']}",
  "executive_summary": "Resumen de 4-5 frases orientado a dirección no técnica.",
  "key_findings": ["Hallazgo 1 (dato concreto)", "Hallazgo 2", "Hallazgo 3", "Hallazgo 4"],
  "risk_posture": "buena|aceptable|mejorable|critica",
  "risk_posture_explanation": "2-3 frases explicando la postura de riesgo actual.",
  "top_risks_narrative": "Párrafo describiendo los riesgos más críticos y su impacto potencial en el negocio.",
  "control_effectiveness": "Análisis de 2 frases sobre la efectividad de los controles implementados.",
  "compliance_status": "Estado de cumplimiento respecto a ISO/IEC 27001 en 2 frases.",
  "critical_actions": ["Acción urgente 1", "Acción urgente 2", "Acción urgente 3"],
  "kpi_commentary": "Interpretación de los KPIs clave en 3 frases.",
  "next_review_recommendation": "Recomendación sobre cuándo y cómo hacer la próxima revisión."
}}"""


def _prompt_committee_minutes(data: dict) -> str:
    accepted = [r for r in data["risks"] if r["accepted"]]
    high = [r for r in data["risks"] if r["residual"] >= 5]
    return f"""Eres el Secretario del Comité de Seguridad de la Información de {data['org']}.

Genera un Acta formal de reunión del Comité de Seguridad en ESPAÑOL.

DATOS DE LA SESIÓN:
- Organización: {data['org']}
- Fecha: {data['date']}
- Riesgos totales en registro: {data['stats']['total']}
- Riesgos críticos/altos (nivel ≥5): {len(high)}
- Riesgos aceptados formalmente: {len(accepted)}
- Riesgos aceptados: {json.dumps(accepted[:10], ensure_ascii=False)}
- Riesgos de nivel alto para revisión: {json.dumps(high[:10], ensure_ascii=False)}

Genera JSON (sin markdown):
{{
  "title": "Acta de Comité de Seguridad de la Información",
  "organization": "{data['org']}",
  "session_date": "{data['date']}",
  "session_number": "A completar por el secretario",
  "attendees_note": "Lista de asistentes a completar por el secretario del Comité.",
  "agenda": [
    "1. Revisión del estado del registro de riesgos",
    "2. Validación de riesgos aceptados",
    "3. Seguimiento de planes de tratamiento",
    "4. Revisión de incidentes del periodo",
    "5. Ruegos y preguntas"
  ],
  "risk_register_review": "Párrafo formal resumiendo el estado del registro de riesgos.",
  "accepted_risks": [
    {{
      "code": "RSK-XXXX",
      "rationale": "Justificación formal de la aceptación del riesgo."
    }}
  ],
  "treatment_followup": "Párrafo sobre el seguimiento de los planes de tratamiento en curso.",
  "decisions": ["Decisión formal 1 adoptada por el Comité", "Decisión formal 2"],
  "action_items": [
    {{
      "action": "Descripción de la acción",
      "responsible": "Responsable (cargo)",
      "deadline": "Plazo"
    }}
  ],
  "next_session_topics": ["Tema 1 para próxima sesión", "Tema 2"],
  "closing_note": "Párrafo formal de cierre del acta."
}}"""


def _prompt_followup_report(data: dict) -> str:
    risks_json = json.dumps(data["risks"][:30], ensure_ascii=False, indent=2)
    return f"""Eres auditor interno de seguridad de la información con expertise en ISO/IEC 27005:2018.

Genera un Informe de Seguimiento del proceso de gestión del riesgo según la cláusula 12 de ISO/IEC 27005:2018 (Monitoring, Review, and Improvement) en ESPAÑOL.

ORGANIZACIÓN: {data['org']}
ALCANCE: {data['scope']}
FECHA: {data['date']}
ESTADÍSTICAS: {json.dumps(data['stats'], ensure_ascii=False)}
CONTROLES: {json.dumps(data['controls'], ensure_ascii=False)}
RIESGOS (muestra): {risks_json}

Genera JSON (sin markdown):
{{
  "title": "Informe de Seguimiento de la Gestión del Riesgo",
  "subtitle": "ISO/IEC 27005:2018 — Cláusula 12: Monitoring, Review and Improvement",
  "organization": "{data['org']}",
  "date": "{data['date']}",
  "scope": "{data['scope']}",
  "executive_summary": "Resumen de 4-5 frases del estado actual del proceso de gestión del riesgo.",
  "cl12_assessment": {{
    "monitoring_adequacy": "Evaluación del nivel de monitorización continua de riesgos (2-3 frases).",
    "review_frequency": "Evaluación de la frecuencia de revisión de riesgos (2 frases).",
    "improvement_actions": "Acciones de mejora identificadas en el proceso (3-4 frases).",
    "context_changes": "Análisis de cambios en el contexto organizacional que pueden afectar al riesgo (2 frases)."
  }},
  "kpi_analysis": {{
    "risk_reduction_trend": "Análisis de la tendencia de reducción del riesgo residual.",
    "treatment_effectiveness": "Efectividad de los tratamientos implementados.",
    "control_coverage": "Cobertura de controles sobre los riesgos identificados.",
    "pending_actions": "Estado de las acciones de tratamiento pendientes."
  }},
  "strengths": ["Fortaleza identificada 1", "Fortaleza 2", "Fortaleza 3"],
  "weaknesses": ["Debilidad identificada 1", "Debilidad 2", "Debilidad 3"],
  "recommendations": [
    {{
      "area": "Area de mejora",
      "recommendation": "Recomendación concreta y accionable.",
      "priority": "alta|media|baja",
      "iso_reference": "ISO 27005 cl. X.X"
    }}
  ],
  "conclusion": "Párrafo de conclusión con valoración global del proceso."
}}"""


def _call_claude(prompt: str) -> dict:
    if not settings.anthropic_api_key:
        raise ValueError("API key de Anthropic no configurada. Configura RISKHUB_ANTHROPIC_API_KEY.")

    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    # Extraer JSON si viene envuelto en markdown
    if "```" in text:
        parts = text.split("```")
        for i, p in enumerate(parts):
            if p.startswith("json"):
                text = parts[i][4:].strip()
                break
            if i % 2 == 1:  # bloque de codigo impar
                text = p.strip()
                break
    return json.loads(text)


def generate(report_type: str, db: Session) -> dict:
    """Genera el contenido del informe llamando a Claude. Retorna dict con secciones."""
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Tipo de informe desconocido: {report_type}")

    data = _collect(db)

    prompts = {
        "treatment_plan": _prompt_treatment_plan,
        "executive_dashboard": _prompt_executive_dashboard,
        "committee_minutes": _prompt_committee_minutes,
        "followup_report": _prompt_followup_report,
    }
    prompt = prompts[report_type](data)
    content = _call_claude(prompt)
    content["_meta"] = {
        "report_type": report_type,
        "label": REPORT_TYPES[report_type],
        "stats": data["stats"],
        "controls": data["controls"],
        "org": data["org"],
        "risks_raw": data["risks"],
    }
    return content
