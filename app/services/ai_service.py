"""Servicio de análisis de riesgos con IA (Claude API).

Metodología combinada:
  - ISO/IEC 27005:2018: matriz 5x5 consecuencia × probabilidad → nivel 0-8.
  - MAGERIT v3: valoración de activos por dimensiones CIA, frecuencia ×
    degradación. Escala cualitativa mapeada a niveles 0-4.

El agente recibe el cuestionario + catálogos existentes y devuelve
escenarios de riesgo estructurados listos para importar.
"""
from __future__ import annotations
import json
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Asset, Control, Threat
from app.services.risk_engine import DEFAULT_MATRIX

# ---------- Cuestionario de contexto organizacional ----------

QUESTIONNAIRE: list[dict] = [
    {
        "id": "sector",
        "category": "Contexto organizacional",
        "question": "¿Cuál es el sector de actividad principal?",
        "type": "select",
        "options": [
            "Financiero / Banca", "Sanitario / Salud", "Industrial / Manufactura",
            "Tecnología / Software", "Administración pública", "Educación",
            "Energía / Utilities", "Retail / Comercio", "Servicios profesionales", "Otro",
        ],
        "required": True,
    },
    {
        "id": "employees",
        "category": "Contexto organizacional",
        "question": "¿Cuántos empleados tiene la organización?",
        "type": "select",
        "options": ["< 50", "50 – 250", "250 – 1.000", "1.000 – 5.000", "> 5.000"],
        "required": True,
    },
    {
        "id": "regulations",
        "category": "Contexto organizacional",
        "question": "¿Qué normativas regulatorias aplican? (selecciona todas las relevantes)",
        "type": "multiselect",
        "options": [
            "GDPR / RGPD", "NIS2", "ENS (Esquema Nacional de Seguridad)",
            "PCI-DSS", "HIPAA", "ISO 27001 certificada", "SOC 2", "Ninguna específica",
        ],
        "required": True,
    },
    {
        "id": "systems",
        "category": "Activos y datos",
        "question": "¿Qué tipos de sistemas gestiona? (selecciona todos los relevantes)",
        "type": "multiselect",
        "options": [
            "Servidores on-premise", "Infraestructura cloud (IaaS/PaaS)",
            "Aplicaciones SaaS de terceros", "Sistemas OT / industriales (SCADA/ICS)",
            "Endpoints (PCs, portátiles, móviles)", "Sistemas embebidos / IoT",
        ],
        "required": True,
    },
    {
        "id": "data_types",
        "category": "Activos y datos",
        "question": "¿Qué categorías de datos maneja?",
        "type": "multiselect",
        "options": [
            "Datos personales de clientes", "Datos personales de empleados",
            "Datos de salud", "Datos financieros / bancarios", "Datos de menores",
            "Propiedad intelectual / secretos comerciales",
            "Credenciales y datos de acceso crítico",
        ],
        "required": True,
    },
    {
        "id": "remote_access",
        "category": "Exposición",
        "question": "¿Existe acceso remoto / teletrabajo a sistemas internos?",
        "type": "select",
        "options": [
            "No", "Sí, con VPN corporativa y MFA",
            "Sí, con VPN pero sin MFA", "Sí, sin VPN ni controles adicionales",
        ],
        "required": True,
    },
    {
        "id": "third_parties",
        "category": "Exposición",
        "question": "¿Proveedores o socios externos tienen acceso a sus sistemas o datos?",
        "type": "select",
        "options": [
            "No",
            "Sí, con contrato DPA y controles auditados",
            "Sí, con contrato pero sin auditoría formal",
            "Sí, sin acuerdos formales",
        ],
        "required": True,
    },
    {
        "id": "incidents",
        "category": "Exposición",
        "question": "¿Ha sufrido incidentes de seguridad relevantes en los últimos 2 años?",
        "type": "select",
        "options": [
            "No", "Sí — ransomware / cifrado de datos", "Sí — fuga de datos",
            "Sí — phishing / compromiso de cuentas", "Sí — otro tipo", "Desconocido",
        ],
        "required": True,
    },
    {
        "id": "controls_existing",
        "category": "Controles existentes",
        "question": "¿Qué controles de seguridad tiene implementados actualmente?",
        "type": "multiselect",
        "options": [
            "Firewall perimetral", "IDS / IPS",
            "EDR / Antivirus gestionado", "SIEM / Monitorización centralizada",
            "MFA en accesos críticos", "Gestión de parches automatizada",
            "Backups con pruebas de restauración periódicas",
            "Cifrado de datos en reposo y en tránsito",
            "DLP (prevención de fuga de datos)",
            "Formación periódica a empleados en ciberseguridad",
            "Plan de respuesta a incidentes documentado y probado",
        ],
        "required": True,
    },
    {
        "id": "maturity",
        "category": "Controles existentes",
        "question": "¿Cómo valorarías el nivel de madurez global de seguridad?",
        "type": "select",
        "options": [
            "1 – Inicial (sin procesos formales)",
            "2 – Básico (controles puntuales, sin gestión sistemática)",
            "3 – Definido (políticas documentadas, aplicación irregular)",
            "4 – Gestionado (procesos medidos y mejorados)",
            "5 – Optimizado (mejora continua, automatización)",
        ],
        "required": True,
    },
    {
        "id": "rto",
        "category": "Apetito de riesgo",
        "question": "¿Cuántas horas de indisponibilidad máxima toleran los sistemas críticos? (RTO)",
        "type": "select",
        "options": ["< 1 hora", "1 – 4 horas", "4 – 24 horas", "1 – 3 días", "> 3 días"],
        "required": True,
    },
    {
        "id": "additional",
        "category": "Apetito de riesgo",
        "question": "Información adicional relevante sobre el contexto de riesgo",
        "type": "textarea",
        "required": False,
    },
]


# ---------- Construcción del prompt ----------

def _build_prompt(answers: dict, assets: list, threats: list, controls: list) -> str:
    matrix_str = "\n".join(
        f"  Consecuencia {i}: {row}" for i, row in enumerate(DEFAULT_MATRIX)
    )

    assets_str = json.dumps(
        [{"id": a["id"], "name": a["name"], "type": a["type"],
          "cia": f"C={a.get('confidentiality',0)} I={a.get('integrity',0)} A={a.get('availability',0)}"}
         for a in assets], ensure_ascii=False, indent=2
    ) if assets else "[]"

    threats_str = json.dumps(
        [{"code": t["code"], "name": t["name"], "origin": t["origin"]}
         for t in threats[:40]], ensure_ascii=False, indent=2
    )

    controls_str = json.dumps(
        [{"code": c["code"], "name": c["name"]} for c in controls[:30]],
        ensure_ascii=False, indent=2
    )

    answers_str = "\n".join(f"  - {k}: {v}" for k, v in answers.items())

    return f"""Eres un experto en gestión de riesgos de seguridad de la información certificado en ISO/IEC 27001:2022, ISO/IEC 27005:2018 y MAGERIT v3.

METODOLOGÍA:
- ISO 27005: Escala 5×5 (consecuencia 0-4 × probabilidad 0-4 → nivel 0-8)
  Matriz (filas=consecuencia 0..4, columnas=probabilidad 0..4):
{matrix_str}
- MAGERIT v3: Valoración de activos por dimensiones CIA; frecuencia de amenaza × degradación sobre el activo.
  El nivel de consecuencia inherente refleja el impacto sobre la dimensión CIA más afectada.
- Controles ISO 27002:2022 reducen consecuencia y/o probabilidad según su tipo (preventivo/detectivo/correctivo).
- Nivel residual = matriz[consecuencia_residual][probabilidad_residual].

ACTIVOS REGISTRADOS EN LA BASE DE DATOS:
{assets_str}

AMENAZAS DISPONIBLES (muestra):
{threats_str}

CONTROLES ISO 27002:2022 DISPONIBLES (muestra):
{controls_str}

RESPUESTAS AL CUESTIONARIO ORGANIZACIONAL:
{answers_str}

TAREA:
Genera entre 15 y 25 escenarios de riesgo realistas y prioritarios para este perfil organizacional.
Usa amenazas del catálogo cuando sea posible (usa el campo threat_code).
Para activos: usa los registrados en la BD si aplican; si no, propón uno nuevo con asset_suggestion.

Devuelve EXCLUSIVAMENTE un JSON válido con este esquema (sin texto adicional):
{{
  "summary": "Resumen ejecutivo del perfil de riesgo en 3-4 frases.",
  "top_risks": ["riesgo crítico 1", "riesgo crítico 2", "riesgo crítico 3"],
  "scenarios": [
    {{
      "asset_id": null,
      "asset_suggestion": "Nombre del activo (existente o propuesto)",
      "asset_type": "primary_information|primary_process|support_hardware|support_software|support_network|support_personnel|support_site",
      "threat_code": "T-N1 o null si no está en catálogo",
      "threat_name": "Nombre de la amenaza",
      "vulnerability_description": "Vulnerabilidad específica que facilita esta amenaza (1 frase)",
      "magerit_dimension": "confidentiality|integrity|availability|authenticity|traceability",
      "inherent_consequence": 0,
      "inherent_likelihood": 0,
      "inherent_level": 0,
      "control_codes": ["5.1", "8.2"],
      "control_rationale": "Por qué estos controles mitigan este riesgo (1 frase)",
      "residual_consequence": 0,
      "residual_likelihood": 0,
      "residual_level": 0,
      "rationale": "Justificación técnica del escenario (1-2 frases)"
    }}
  ]
}}"""


# ---------- Llamada a Claude API ----------

def run_analysis(answers: dict, db: Session) -> dict[str, Any]:
    """Llama a Claude API y devuelve el análisis de riesgos estructurado."""
    if not settings.anthropic_api_key:
        raise ValueError("RISKHUB_ANTHROPIC_API_KEY no configurada. Añádela al .env del servidor.")

    try:
        import anthropic
    except ImportError:
        raise RuntimeError("Paquete 'anthropic' no instalado. Revisa requirements.txt.")

    # Leer catálogos de la BD
    assets = [
        {"id": a.id, "name": a.name, "type": a.asset_type.value if a.asset_type else "",
         "confidentiality": a.confidentiality, "integrity": a.integrity,
         "availability": a.availability}
        for a in db.query(Asset).limit(50).all()
    ]
    threats = [
        {"code": t.code, "name": t.name, "origin": t.origin.value if t.origin else ""}
        for t in db.query(Threat).all()
    ]
    controls = [
        {"code": c.code, "name": c.name}
        for c in db.query(Control).order_by(Control.code).all()
    ]

    prompt = _build_prompt(answers, assets, threats, controls)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Extraer JSON aunque haya texto envolvente
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"La IA no devolvió JSON válido: {raw[:200]}")

    result = json.loads(raw[start:end])

    # Aseguramos niveles coherentes con la matriz
    for sc in result.get("scenarios", []):
        c_ = max(0, min(4, int(sc.get("inherent_consequence", 0))))
        l_ = max(0, min(4, int(sc.get("inherent_likelihood", 0))))
        sc["inherent_level"] = DEFAULT_MATRIX[c_][l_]
        sc["inherent_consequence"] = c_
        sc["inherent_likelihood"] = l_

        rc = max(0, min(4, int(sc.get("residual_consequence", 0))))
        rl = max(0, min(4, int(sc.get("residual_likelihood", 0))))
        sc["residual_level"] = DEFAULT_MATRIX[rc][rl]
        sc["residual_consequence"] = rc
        sc["residual_likelihood"] = rl

    return result
