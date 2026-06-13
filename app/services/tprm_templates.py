"""Biblioteca de plantillas de cuestionario TPRM del sistema (§4.4).

Plantillas preestablecidas (is_system_template=true): NO se editan, se clonan.
Cada pregunta lleva:
 - id, text, type
 - weight: peso relativo dentro de la plantilla
 - scoring_rules: mapeo respuesta -> score 0-100 (§4.7.1)
 - control_refs: referencias a controles de marcos (ISO 27001, NIS2, DORA, GDPR, ENS)
 - domain: dominio funcional para el spider chart (§5.3)
 - requires_evidence: si exige evidencia documental

Las plantillas cubren las areas clave de la spec. Son la base clonable que el
cliente amplia/reordena en sus copias; el original del sistema permanece fijo.
"""

# Reglas de scoring reutilizables
YN = {"yes": 100, "no": 0, "na": None}
YNP = {"yes": 100, "partial": 50, "no": 0, "na": None}
MFA = {
    "always_mfa_all_users": 100,
    "mfa_privileged_only": 60,
    "mfa_optional": 20,
    "no_mfa": 0,
}


def _q(qid, text, domain, control_refs, weight=1.0, qtype="yes_no_partial",
       scoring_rules=None, requires_evidence=False, options=None, help_text=""):
    q = {
        "id": qid,
        "text": text,
        "type": qtype,
        "domain": domain,
        "control_refs": control_refs,
        "weight": weight,
        "scoring_rules": scoring_rules if scoring_rules is not None else YNP,
        "requires_evidence": requires_evidence,
        "help_text": help_text,
    }
    if options:
        q["options"] = options
    return q


# ---------- RH_TPRM_LITE_v1 ----------
_LITE = [
    _q("gov1", "La organizacion dispone de un SGSI certificado o equivalente (ISO 27001, SOC 2, ENS).",
       "governance", ["ISO27001:A.5.1", "ISO27001:A.5.19"], 1.5, requires_evidence=True),
    _q("acc1", "Se exige autenticacion multifactor (MFA) para el acceso a sistemas que tratan datos del cliente.",
       "access_control", ["ISO27001:A.8.5"], 1.5, qtype="single_choice", scoring_rules=MFA,
       options=["always_mfa_all_users", "mfa_privileged_only", "mfa_optional", "no_mfa"]),
    _q("cry1", "Los datos sensibles se cifran en transito y en reposo.",
       "cryptography", ["ISO27001:A.8.24"], 1.0),
    _q("inc1", "Existen procedimientos documentados de respuesta a incidentes con notificacion al cliente.",
       "incident_management", ["ISO27001:A.5.24", "NIS2:art.23"], 1.0),
    _q("priv1", "Si trata datos personales, existe un acuerdo de encargado de tratamiento (DPA, GDPR art. 28).",
       "privacy", ["GDPR:art.28"], 1.0, requires_evidence=True),
    _q("sup1", "Existe una politica de seguridad de la cadena de suministro para sus propios proveedores.",
       "supplier_chain", ["ISO27001:A.5.21", "NIS2:art.21.2.d"], 1.0),
]

# ---------- RH_TPRM_ISO27001_FULL_v1 ----------
_ISO27001 = [
    _q("org1", "Existe una politica de seguridad de la informacion aprobada por direccion y revisada periodicamente.",
       "governance", ["ISO27001:A.5.1"], 1.0, requires_evidence=True),
    _q("org2", "Hay roles y responsabilidades de seguridad definidos y segregacion de funciones.",
       "governance", ["ISO27001:A.5.2", "ISO27001:A.5.3"], 1.0),
    _q("hr1", "El personal recibe formacion y concienciacion en seguridad de forma periodica.",
       "governance", ["ISO27001:A.6.3"], 1.0),
    _q("hr2", "Se realizan verificaciones de antecedentes antes de la contratacion cuando procede.",
       "governance", ["ISO27001:A.6.1"], 0.5),
    _q("am1", "Existe un inventario de activos de informacion clasificado por sensibilidad.",
       "asset_management", ["ISO27001:A.5.9", "ISO27001:A.5.12"], 1.0),
    _q("ac1", "Se aplica el principio de minimo privilegio con revision periodica de accesos.",
       "access_control", ["ISO27001:A.5.15", "ISO27001:A.5.18"], 1.0),
    _q("ac2", "Se exige MFA para accesos privilegiados y remotos.",
       "access_control", ["ISO27001:A.8.5"], 1.5, qtype="single_choice", scoring_rules=MFA,
       options=["always_mfa_all_users", "mfa_privileged_only", "mfa_optional", "no_mfa"]),
    _q("ac3", "Se gestiona el ciclo de vida de cuentas (alta, cambios, baja) de forma controlada.",
       "access_control", ["ISO27001:A.5.16", "ISO27001:A.5.18"], 1.0),
    _q("cr1", "Existe una politica criptografica y gestion segura de claves (KMS/HSM).",
       "cryptography", ["ISO27001:A.8.24"], 1.0),
    _q("ph1", "Existen controles de seguridad fisica en las instalaciones que alojan datos del cliente.",
       "physical_security", ["ISO27001:A.7.1", "ISO27001:A.7.2"], 0.5),
    _q("ops1", "Se aplica gestion de parches y hardening de sistemas de forma documentada.",
       "operations_security", ["ISO27001:A.8.8", "ISO27001:A.8.9"], 1.0),
    _q("ops2", "Se realizan copias de seguridad probadas periodicamente.",
       "operations_security", ["ISO27001:A.8.13"], 1.0, requires_evidence=True),
    _q("ops3", "Existe registro y monitorizacion de eventos de seguridad (logging).",
       "operations_security", ["ISO27001:A.8.15", "ISO27001:A.8.16"], 1.0),
    _q("net1", "La red esta segmentada y protegida (firewalls, IDS/IPS).",
       "network_security", ["ISO27001:A.8.20", "ISO27001:A.8.22"], 1.0),
    _q("dev1", "El desarrollo sigue un ciclo seguro (SDLC) con SAST/DAST/SCA y revision de codigo.",
       "secure_development", ["ISO27001:A.8.25", "ISO27001:A.8.28"], 1.0),
    _q("sup1", "Se evalua y supervisa la seguridad de los propios proveedores.",
       "supplier_chain", ["ISO27001:A.5.19", "ISO27001:A.5.21", "ISO27001:A.5.22"], 1.0),
    _q("inc1", "Existe gestion de incidentes con metricas (MTTD/MTTR) y notificacion.",
       "incident_management", ["ISO27001:A.5.24", "ISO27001:A.5.26"], 1.0),
    _q("bc1", "Existe un plan de continuidad/recuperacion (RTO/RPO) probado anualmente.",
       "business_continuity", ["ISO27001:A.5.29", "ISO27001:A.5.30"], 1.0, requires_evidence=True),
    _q("cmp1", "Se realizan auditorias internas y se concede derecho de auditoria al cliente.",
       "compliance_legal", ["ISO27001:A.5.35", "ISO27001:A.5.36"], 1.0),
]

# ---------- RH_TPRM_GDPR_PROCESSOR_v1 ----------
_GDPR = [
    _q("g1", "Actua como encargado del tratamiento y existe un DPA firmado (art. 28).",
       "privacy", ["GDPR:art.28"], 1.5, requires_evidence=True),
    _q("g2", "Mantiene un registro de actividades de tratamiento (art. 30).",
       "privacy", ["GDPR:art.30"], 1.0),
    _q("g3", "Aplica medidas de seguridad apropiadas (art. 32): cifrado, seudonimizacion, resiliencia.",
       "privacy", ["GDPR:art.32"], 1.5),
    _q("g4", "Notifica al responsable las brechas de datos sin dilacion indebida (art. 33).",
       "privacy", ["GDPR:art.33"], 1.0),
    _q("g5", "Solo subcontrata con autorizacion y notifica cambios de subencargados (art. 28.2).",
       "supplier_chain", ["GDPR:art.28"], 1.0),
    _q("g6", "Las transferencias internacionales cuentan con garantias adecuadas (art. 44-49).",
       "privacy", ["GDPR:art.44"], 1.0, qtype="single_choice",
       scoring_rules={"no_transfers": 100, "scc_bcr": 90, "adequacy": 100, "no_safeguards": 0},
       options=["no_transfers", "adequacy", "scc_bcr", "no_safeguards"]),
    _q("g7", "Asiste al responsable en el ejercicio de derechos de los interesados (art. 12-22).",
       "privacy", ["GDPR:art.28"], 0.5),
]

# ---------- RH_TPRM_NIS2_v1 ----------
_NIS2 = [
    _q("n1", "Politicas de analisis de riesgos y seguridad de la informacion (art. 21.2.a).",
       "risk_management", ["NIS2:art.21.2.a"], 1.0),
    _q("n2", "Gestion de incidentes (art. 21.2.b).",
       "incident_management", ["NIS2:art.21.2.b"], 1.0),
    _q("n3", "Continuidad de negocio y gestion de crisis (art. 21.2.c).",
       "business_continuity", ["NIS2:art.21.2.c"], 1.0, requires_evidence=True),
    _q("n4", "Seguridad de la cadena de suministro (art. 21.2.d).",
       "supplier_chain", ["NIS2:art.21.2.d"], 1.5),
    _q("n5", "Seguridad en adquisicion, desarrollo y mantenimiento (art. 21.2.e).",
       "secure_development", ["NIS2:art.21.2.e"], 1.0),
    _q("n6", "Politicas para evaluar la eficacia de las medidas (art. 21.2.f).",
       "governance", ["NIS2:art.21.2.f"], 1.0),
    _q("n7", "Higiene basica de ciberseguridad y formacion (art. 21.2.g).",
       "governance", ["NIS2:art.21.2.g"], 1.0),
    _q("n8", "Uso de criptografia y cifrado (art. 21.2.h).",
       "cryptography", ["NIS2:art.21.2.h"], 1.0),
    _q("n9", "Seguridad de RRHH, control de accesos y gestion de activos (art. 21.2.i).",
       "access_control", ["NIS2:art.21.2.i"], 1.0),
    _q("n10", "Autenticacion multifactor y comunicaciones seguras (art. 21.2.j).",
       "access_control", ["NIS2:art.21.2.j"], 1.5, qtype="single_choice", scoring_rules=MFA,
       options=["always_mfa_all_users", "mfa_privileged_only", "mfa_optional", "no_mfa"]),
]

# ---------- RH_TPRM_DORA_ICT_v1 ----------
_DORA = [
    _q("d1", "El contrato ICT cumple los requisitos del art. 30 (descripcion servicio, ubicaciones de datos, niveles de servicio).",
       "compliance_legal", ["DORA:art.30"], 1.5, requires_evidence=True),
    _q("d2", "Garantiza derechos de acceso, inspeccion y auditoria a la entidad financiera (art. 30.3).",
       "compliance_legal", ["DORA:art.30"], 1.0),
    _q("d3", "Notifica incidentes graves relacionados con las TIC en plazo (art. 28).",
       "incident_management", ["DORA:art.28"], 1.0),
    _q("d4", "Dispone de estrategias de salida y planes de transicion (art. 28.8).",
       "business_continuity", ["DORA:art.28"], 1.0),
    _q("d5", "Participa en pruebas de resiliencia operativa digital cuando aplica (TLPT/TIBER-EU).",
       "resilience_testing", ["DORA:art.26", "DORA:art.27"], 1.0),
    _q("d6", "Gestiona el riesgo de subcontratacion de servicios ICT criticos (RTS subcontratacion).",
       "supplier_chain", ["DORA:art.30"], 1.0),
    _q("d7", "Mantiene medidas de continuidad y recuperacion con RTO/RPO acordados.",
       "business_continuity", ["DORA:art.11", "DORA:art.12"], 1.0, requires_evidence=True),
]

# ---------- RH_TPRM_AI_USAGE_DECLARATION_v1 ----------
_AI = [
    _q("ai1", "Declara si utiliza sistemas de IA para prestar el servicio contratado.",
       "ai_governance", ["ISO42001:A.2"], 1.0, qtype="yes_no", scoring_rules=YN),
    _q("ai2", "Dispone de gobernanza de IA (politicas, supervision humana, roles) — ISO 42001 AIMS.",
       "ai_governance", ["ISO42001:A.3", "ISO42001:A.4"], 1.0),
    _q("ai3", "Evalua el impacto de los sistemas de IA (sesgo, equidad, derechos).",
       "ai_governance", ["ISO42001:A.5"], 1.0),
    _q("ai4", "Garantiza transparencia e informacion sobre decisiones automatizadas.",
       "ai_governance", ["ISO42001:A.8"], 1.0),
    _q("ai5", "Controla el uso de datos del cliente para entrenamiento de modelos.",
       "ai_governance", ["ISO42001:A.7"], 1.0, qtype="yes_no", scoring_rules=YN),
]

# ---------- RH_TPRM_OFFBOARDING_v1 ----------
_OFFBOARD = [
    _q("o1", "Se han revocado todos los accesos (SSO, VPN, API keys, cuentas dedicadas).",
       "access_control", ["ISO27001:A.5.18"], 1.5, requires_evidence=True),
    _q("o2", "Se ha devuelto o destruido de forma certificada la informacion del cliente.",
       "privacy", ["ISO27001:A.5.10", "GDPR:art.28"], 1.5, requires_evidence=True),
    _q("o3", "Se han cerrado las cuentas de subencargados implicados.",
       "supplier_chain", ["ISO27001:A.5.22"], 1.0),
    _q("o4", "Se ha realizado la auditoria/cuestionario final de salida.",
       "compliance_legal", ["ISO27001:A.5.22"], 1.0),
    _q("o5", "Se han archivado las evidencias para retencion legal.",
       "compliance_legal", ["ISO27001:A.5.33"], 0.5),
]


SYSTEM_TEMPLATES = [
    {
        "code": "RH_TPRM_LITE_v1",
        "name": "Cuestionario rapido (Tier Low)",
        "description": "ISO 27001 baseline + GDPR minimos. Proveedores no criticos.",
        "framework_codes": ["ISO_27001", "GDPR"],
        "target_tier": ["low", "medium"],
        "estimated_minutes": 15,
        "questions": _LITE,
    },
    {
        "code": "RH_TPRM_ISO27001_FULL_v1",
        "name": "ISO/IEC 27001:2022 + 27002 completo",
        "description": "Cobertura de los dominios del Annex A. Proveedores critical/high.",
        "framework_codes": ["ISO_27001", "ISO_27002"],
        "target_tier": ["critical", "high"],
        "estimated_minutes": 60,
        "questions": _ISO27001,
    },
    {
        "code": "RH_TPRM_GDPR_PROCESSOR_v1",
        "name": "GDPR art. 28/32 — Encargado del tratamiento",
        "description": "Procesamiento de datos personales, seguridad y transferencias.",
        "framework_codes": ["GDPR"],
        "target_tier": ["critical", "high", "medium"],
        "estimated_minutes": 25,
        "questions": _GDPR,
    },
    {
        "code": "RH_TPRM_NIS2_v1",
        "name": "NIS2 Directiva art. 21 medidas",
        "description": "Las 10 areas obligatorias del art. 21.2 (a-j) + cadena de suministro.",
        "framework_codes": ["NIS2"],
        "target_tier": ["critical", "high"],
        "estimated_minutes": 35,
        "questions": _NIS2,
    },
    {
        "code": "RH_TPRM_DORA_ICT_v1",
        "name": "DORA arts. 28-30 para proveedores ICT",
        "description": "Identificacion, contratos, notificacion y salida para terceros ICT.",
        "framework_codes": ["DORA"],
        "target_tier": ["critical", "high"],
        "estimated_minutes": 40,
        "questions": _DORA,
    },
    {
        "code": "RH_TPRM_AI_USAGE_DECLARATION_v1",
        "name": "Declaracion de uso de IA (ISO 42001 / EU AI Act)",
        "description": "Gobernanza, impacto, transparencia y datos de entrenamiento.",
        "framework_codes": ["ISO_42001", "EU_AI_ACT"],
        "target_tier": ["critical", "high", "medium", "low"],
        "estimated_minutes": 15,
        "questions": _AI,
    },
    {
        "code": "RH_TPRM_OFFBOARDING_v1",
        "name": "Checklist de offboarding",
        "description": "Devolucion/destruccion de datos, revocacion de accesos, auditoria final.",
        "framework_codes": ["ISO_27001", "GDPR"],
        "target_tier": ["critical", "high", "medium", "low"],
        "estimated_minutes": 15,
        "questions": _OFFBOARD,
    },
]

_BY_CODE = {t["code"]: t for t in SYSTEM_TEMPLATES}


def list_templates() -> list:
    """Devuelve metadatos de las plantillas (sin el detalle de preguntas)."""
    return [
        {
            "code": t["code"],
            "name": t["name"],
            "description": t["description"],
            "framework_codes": t["framework_codes"],
            "target_tier": t["target_tier"],
            "estimated_minutes": t["estimated_minutes"],
            "question_count": len(t["questions"]),
            "is_system_template": True,
        }
        for t in SYSTEM_TEMPLATES
    ]


def get_template(code: str) -> dict | None:
    """Devuelve la plantilla completa por codigo."""
    return _BY_CODE.get(code)
