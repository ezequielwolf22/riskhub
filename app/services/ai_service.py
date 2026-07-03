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
import re
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.i18n import ai_lang_directive
from app.models import Asset, Control, Threat
from app.services.risk_engine import DEFAULT_MATRIX


def _get_model(db: Session, org_id: int | None) -> str:
    """Devuelve el modelo Claude configurado para la org, o el fallback global."""
    try:
        from app.models import AiConfig
        cfg = db.query(AiConfig).filter_by(organization_id=org_id).first() if org_id else None
        if cfg and cfg.model:
            return cfg.model
    except Exception:
        pass
    return "claude-opus-4-6"


def _sanitize_prompt_value(v: Any) -> str:
    """Elimina caracteres que confunden a Claude al generar JSON (comillas, backslashes, etc.)."""
    if isinstance(v, list):
        return ", ".join(_sanitize_prompt_value(x) for x in v)
    s = str(v)
    # Reemplazar comillas dobles por simples y backslashes por slash
    s = s.replace("\\", "/").replace('"', "'").replace("\r\n", " ").replace("\n", " ").strip()
    return s


def _repair_json(raw: str) -> dict:
    """Intenta extraer y reparar JSON de la respuesta de Claude.

    Estrategias (en orden):
    1. Parseo directo del bloque { ... }
    2. Eliminar trailing commas y parsear
    3. Truncar en el ultimo escenario completo y cerrar el JSON
    """
    # Extraer bloque JSON principal
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"La IA no devolvio JSON. Respuesta: {raw[:300]}")
    chunk = raw[start:end]

    # Estrategia 1: parseo directo
    try:
        return json.loads(chunk)
    except json.JSONDecodeError:
        pass

    # Estrategia 2: eliminar trailing commas ( ,} y ,] )
    fixed = re.sub(r",\s*([}\]])", r"\1", chunk)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Estrategia 3: truncar en el ultimo }} completo (escenario cerrado)
    # Buscar la ultima ocurrencia de "}," o "}" antes de un "]"
    last_complete = chunk.rfind("}\n    ]")
    if last_complete == -1:
        last_complete = chunk.rfind("}]")
    if last_complete != -1:
        truncated = chunk[:last_complete + 2] + "\n  ]\n}"
        truncated = re.sub(r",\s*([}\]])", r"\1", truncated)
        try:
            return json.loads(truncated)
        except json.JSONDecodeError:
            pass

    # Estrategia 4: buscar escenarios completos uno a uno usando regex
    # Extraer el summary y top_risks si existen, construir respuesta parcial
    summary_m = re.search(r'"summary"\s*:\s*"([^"]*)"', chunk)
    summary   = summary_m.group(1) if summary_m else "Analisis parcial (JSON truncado)"
    scenarios_raw = re.findall(
        r'\{[^{}]*"threat_name"[^{}]*\}',
        chunk, re.DOTALL
    )
    scenarios = []
    for s in scenarios_raw:
        try:
            scenarios.append(json.loads(s))
        except Exception:
            pass

    if scenarios:
        return {"summary": summary, "top_risks": [], "scenarios": scenarios}

    raise ValueError(
        f"La IA devolvio JSON invalido (char {len(chunk)}). "
        "Intenta de nuevo o reduce el numero de normativas/criterios adicionales."
    )

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
        "allow_extra": True,
    },
    {
        "id": "risk_appetite_level",
        "category": "Apetito de riesgo",
        "question": "¿Cuál es el nivel máximo de riesgo residual que la organización acepta sin tratamiento adicional? (escala ISO 27005: 0 mínimo – 8 máximo)",
        "type": "select",
        "options": [
            "1 — Conservador: solo riesgos mínimos (nivel residual ≤ 1)",
            "2 — Muy prudente (nivel residual ≤ 2)",
            "3 — Prudente: tolerancia baja (nivel residual ≤ 3)",
            "4 — Moderado: equilibrio seguridad / operatividad (nivel residual ≤ 4)",
            "5 — Tolerante: acepta riesgos medios (nivel residual ≤ 5)",
            "6 — Permisivo: solo actúa sobre riesgos altos/críticos (nivel residual ≤ 6)",
        ],
        "required": True,
        "allow_extra": True,
    },
    {
        "id": "additional",
        "category": "Apetito de riesgo",
        "question": "Información adicional relevante sobre el contexto de riesgo",
        "type": "textarea",
        "required": False,
        "allow_extra": True,
    },
]


# ---------- Mapa: control declarado → codigos ISO 27002:2022 ----------

CONTROLS_ISO_MAP: dict[str, list[str]] = {
    "Firewall perimetral":                              ["8.20", "8.21"],
    "IDS / IPS":                                       ["8.16"],
    "EDR / Antivirus gestionado":                      ["8.7"],
    "SIEM / Monitorización centralizada":              ["8.15", "8.16"],
    "MFA en accesos críticos":                         ["5.17", "8.5"],
    "Gestión de parches automatizada":                 ["8.8"],
    "Backups con pruebas de restauración periódicas":  ["8.13", "8.14"],
    "Cifrado de datos en reposo y en tránsito":        ["8.24"],
    "DLP (prevención de fuga de datos)":               ["8.12"],
    "Formación periódica a empleados en ciberseguridad": ["6.3"],
    "Plan de respuesta a incidentes documentado y probado": ["5.26", "5.25"],
}


_REG_TO_FRAMEWORK: dict[str, str] = {
    "GDPR / RGPD":                          "gdpr",
    "NIS2":                                  "nis2",
    "ENS (Esquema Nacional de Seguridad)":   "ens",
    "PCI-DSS":                               "pcidss",
    "HIPAA":                                 "hipaa",
    "ISO 27001 certificada":                 "iso27001",
    "SOC 2":                                 "soc2",
}


def _regulations_to_frameworks(regulations: list[str]) -> list[str]:
    """Convierte las opciones del cuestionario a claves internas de framework."""
    fw = []
    for r in regulations:
        key = _REG_TO_FRAMEWORK.get(r)
        if key and key not in fw:
            fw.append(key)
    if not fw:
        fw = ["iso27001"]   # siempre al menos ISO 27001
    elif "iso27001" not in fw:
        fw.insert(0, "iso27001")   # ISO 27001 siempre presente como base
    return fw


def _parse_appetite_level(answer: str) -> int:
    """Extrae el numero de nivel de apetito de la respuesta seleccionada."""
    import re
    m = re.match(r'^(\d+)', (answer or "").strip())
    return int(m.group(1)) if m else 3   # default 3 si no se puede parsear


# ---------- Construcción del prompt ----------

# Instrucciones de metodologia por modo (fuera del f-string para evitar KeyError en format)
_METHODOLOGY_HINTS: dict[str, str] = {
    "iso27005": (
        "Usa ISO 27005 puro: consecuencia (0-4) y probabilidad (0-4) estimadas por el analista."
    ),
    "magerit": (
        "Usa MAGERIT v3: la consecuencia se deriva de las dimensiones D/I/C/A/T del activo "
        "x degradacion. Indica la dimension primaria en magerit_dimension. "
        "La frecuencia de amenaza sigue escala MAGERIT (MB/B/M/A/MA). "
        "Menciona explicitamente las dimensiones afectadas en rationale."
    ),
    "combined": (
        "Usa ISO 27005 para la estructura + MAGERIT para los valores CIA+A+T. "
        "Indica magerit_dimension en cada escenario. "
        "Menciona las dimensiones DIACAT relevantes."
    ),
}


def _build_prompt(answers: dict, assets: list, threats: list, controls: list, lang: str = "es") -> str:
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

    # Separar respuestas propias del cuestionario de criterios extra y campos internos
    # Sanitizar valores para evitar que Claude genere JSON invalido con comillas/saltos
    base_answers = {}
    extra_criteria_items = []
    for k, v in answers.items():
        if k.startswith("extra_"):
            if v and str(v).strip():
                extra_criteria_items.append(
                    f"  [{k.replace('extra_', '')}]: {_sanitize_prompt_value(v)}"
                )
        elif k.startswith("_"):
            pass   # campos internos (ej: _active_methodology) — no se muestran en el prompt
        else:
            base_answers[k] = _sanitize_prompt_value(v)

    # Metodologia activa del contexto (enriquecida desde el router)
    active_methodology = answers.get("_active_methodology", "iso27005")
    methodology_instruction = _METHODOLOGY_HINTS.get(
        active_methodology, _METHODOLOGY_HINTS["iso27005"]
    )

    answers_str = "\n".join(f"  - {k}: {v}" for k, v in base_answers.items())
    extra_str = "\n".join(extra_criteria_items) if extra_criteria_items else "  (ninguno)"

    # Mapear controles declarados (predefinidos + personalizados) a ISO 27002:2022
    declared_controls: list[str] = list(answers.get("controls_existing") or [])
    custom_controls: list[str] = list(answers.get("custom_controls") or [])
    all_controls = declared_controls + custom_controls
    mapped_controls_lines = []
    for ctrl_name in all_controls:
        iso_codes = CONTROLS_ISO_MAP.get(ctrl_name, [])
        codes_str = ", ".join(iso_codes) if iso_codes else "mapear segun descripcion"
        mapped_controls_lines.append(f"  - {ctrl_name} → ISO 27002: {codes_str}")
    mapped_controls_str = "\n".join(mapped_controls_lines) if mapped_controls_lines else "  (ninguno declarado)"

    # Normativas activas y nivel ENS
    regulations: list[str] = list(answers.get("regulations") or [])
    ens_level: str = answers.get("ens_level", "")
    regs_str = ", ".join(regulations) if regulations else "ninguna especifica"
    ens_str = f" — Nivel ENS: {ens_level.upper()}" if ens_level else ""

    # Apetito de riesgo
    appetite_raw = answers.get("risk_appetite_level", "")
    appetite_num = _parse_appetite_level(appetite_raw)

    return f"""{ai_lang_directive(lang)}

Eres un experto en gestión de riesgos de seguridad de la información certificado en ISO/IEC 27001:2022, ISO/IEC 27005:2018 y MAGERIT v3.

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

CONTROLES DE SEGURIDAD YA IMPLEMENTADOS EN LA ORGANIZACIÓN:
{mapped_controls_str}
INSTRUCCION CRITICA: Los controles listados arriba YA EXISTEN en la organización.
- Deben aparecer en el campo control_codes de los escenarios que mitigan.
- Su presencia REDUCE el nivel residual respecto al inherente (probabilidad y/o consecuencia).
- Si un control cubre parcialmente el riesgo, reduce 1 punto; si lo cubre plenamente, reduce 2 puntos.
- Incluye también estos controles como evidencia de cumplimiento normativo en el rationale.

APETITO DE RIESGO DE LA ORGANIZACIÓN:
- Nivel máximo aceptable sin tratamiento adicional: {appetite_num} (escala 0-8, ISO 27005)
- Opción seleccionada: "{appetite_raw}"
INSTRUCCION: Para cada escenario, asigna treatment_option según la regla:
  · Si residual_level > {appetite_num} → treatment_option = "modification" (DEBE mitigarse)
  · Si residual_level <= {appetite_num} → treatment_option = "retention" (se puede aceptar)

METODOLOGÍA ACTIVA CONFIGURADA POR LA ORGANIZACIÓN: {active_methodology}
INSTRUCCION METODOLOGICA: {methodology_instruction}

NORMATIVAS REGULATORIAS APLICABLES A ESTA ORGANIZACIÓN:
  {regs_str}{ens_str}
INSTRUCCION: Para cada escenario, el campo control_rationale debe mencionar explícitamente
qué controles de estas normativas cubre o requiere el escenario. Para ENS{ens_str}, ajusta
la severidad y los controles obligatorios al nivel indicado.

CRITERIOS ADICIONALES APORTADOS POR EL USUARIO:
{extra_str}
INSTRUCCION: Considera estos criterios como contexto adicional para calibrar probabilidades,
consecuencias y tratamientos. Propágalos a todos los escenarios donde apliquen.

RESPUESTAS AL CUESTIONARIO ORGANIZACIONAL:
{answers_str}

TAREA:
Genera entre 12 y 18 escenarios de riesgo realistas y prioritarios para este perfil organizacional.
Usa amenazas del catálogo cuando sea posible (usa el campo threat_code).
Para activos: usa los registrados en la BD si aplican; si no, propón uno nuevo con asset_suggestion.

IMPORTANTE FORMATO JSON:
- Devuelve EXCLUSIVAMENTE JSON valido, sin texto antes ni despues
- Usa comillas dobles para todas las cadenas
- No incluyas caracteres especiales sin escapar en los strings
- Mantén los strings cortos: rationale maximo 120 chars, control_rationale maximo 100 chars
- NO uses saltos de linea dentro de los strings

Devuelve EXCLUSIVAMENTE un JSON válido con este esquema:
{{
  "summary": "Resumen ejecutivo del perfil de riesgo en 3-4 frases.",
  "top_risks": ["riesgo crítico 1", "riesgo crítico 2", "riesgo crítico 3"],
  "risk_appetite": {appetite_num},
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
      "control_rationale": "Por qué estos controles mitigan este riesgo y cómo los controles existentes contribuyen (1-2 frases)",
      "residual_consequence": 0,
      "residual_likelihood": 0,
      "residual_level": 0,
      "treatment_option": "modification|retention|avoidance|sharing",
      "rationale": "Justificación técnica del escenario incluyendo referencia a controles existentes (1-2 frases)"
    }}
  ]
}}\n"""


# ---------- Llamada a Claude API ----------

def run_analysis(answers: dict, db: Session, api_key: str | None = None, org_id: int | None = None, lang: str = "es") -> dict[str, Any]:
    """Llama a Claude API y devuelve el analisis de riesgos estructurado.

    El parametro api_key permite usar la clave per-tenant configurada en la UI
    (IA -> Configuracion). Si no se proporciona, se usa RISKHUB_ANTHROPIC_API_KEY.
    """
    effective_key = api_key or settings.anthropic_api_key
    if not effective_key:
        raise ValueError(
            "API key de Claude no configurada. "
            "Configurala en IA -> Configuracion o añade RISKHUB_ANTHROPIC_API_KEY al entorno."
        )

    try:
        import anthropic
    except ImportError:
        raise RuntimeError("Paquete 'anthropic' no instalado. Revisa requirements.txt.")

    # Leer catálogos de la BD
    assets = [
        {"id": a.id, "name": a.name, "type": a.asset_type.value if a.asset_type else "",
         "confidentiality": a.value_confidentiality, "integrity": a.value_integrity,
         "availability": a.value_availability}
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

    prompt = _build_prompt(answers, assets, threats, controls, lang)

    model = _get_model(db, org_id)
    client = anthropic.Anthropic(api_key=effective_key)
    try:
        message = client.messages.create(
            model=model,
            max_tokens=64000,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        err_str = str(exc).lower()
        if "max_tokens" in err_str or "maximum" in err_str:
            message = client.messages.create(
                model=model,
                max_tokens=32768,
                messages=[{"role": "user", "content": prompt}],
            )
        else:
            raise

    raw = message.content[0].text.strip()

    # Advertencia si el modelo se corto por limite de tokens
    if getattr(message, "stop_reason", None) == "max_tokens":
        import logging
        logging.getLogger("riskhub.ai").warning(
            "Analysis response truncated at max_tokens. Consider reducing scenario count."
        )

    # Parseo robusto: varios intentos de reparacion antes de fallar
    result = _repair_json(raw)

    # Obtener apetito de riesgo del cuestionario para post-procesado
    appetite_num = _parse_appetite_level(answers.get("risk_appetite_level", ""))
    # Aseguramos que el apetito quede en el resultado
    if "risk_appetite" not in result:
        result["risk_appetite"] = appetite_num
    # Propagar normativas y nivel ENS para que el import pueda guardarlos
    result["active_frameworks"] = _regulations_to_frameworks(answers.get("regulations") or [])
    if answers.get("ens_level"):
        result["ens_level"] = answers["ens_level"]

    # Post-procesar escenarios: niveles coherentes con la matriz + treatment_option por apetito
    valid_treatments = {"modification", "retention", "avoidance", "sharing"}
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

        # Garantizar treatment_option coherente con el apetito
        # Si el IA no lo puso o lo puso incorrecto, lo forzamos
        ai_treatment = sc.get("treatment_option", "")
        if ai_treatment not in valid_treatments:
            ai_treatment = ""
        if not ai_treatment:
            # Asignar basado en apetito
            sc["treatment_option"] = (
                "retention" if sc["residual_level"] <= appetite_num else "modification"
            )
        else:
            # Respetar lo que dijo la IA pero correger incoherencias graves
            if sc["residual_level"] <= appetite_num and ai_treatment == "modification":
                sc["treatment_option"] = "retention"
            elif sc["residual_level"] > appetite_num and ai_treatment == "retention":
                sc["treatment_option"] = "modification"
            else:
                sc["treatment_option"] = ai_treatment

        # Bandera visual para la UI
        sc["above_appetite"] = sc["residual_level"] > appetite_num

    return result
