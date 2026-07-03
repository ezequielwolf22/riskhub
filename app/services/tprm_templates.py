"""Biblioteca de plantillas de cuestionario TPRM del sistema.

Plantillas preestablecidas (is_system_template=true): NO se editan, se clonan.
Cada pregunta lleva:
 - id, text, type
 - weight: peso relativo dentro de la plantilla
 - scoring_rules: mapeo respuesta -> score 0-100
 - control_refs: referencias a controles de marcos (ISO 27001, NIS2, DORA, GDPR, ENS, EU AI Act)
 - domain: dominio funcional para el spider chart
 - requires_evidence: si exige evidencia documental
 - criticity: Major | Minor | None  (no-conformidad si respuesta = valor no-conformidad)
 - ir_level: medium | high | critical  (nivel inherente minimo para mostrar la pregunta)
 - nonconformity_value: valor de respuesta que cuenta como NC (por defecto "no")
 - scenarios: lista de escenarios TPRM que activan esta pregunta

i18n: las plantillas se sirven en vivo desde codigo, por lo que llevan campos
bilingues (*_en: text_en, help_text_en, name_en, description_en) y un accessor
que selecciona por idioma (patron _localize_framework de compliance_service).
Cuando una plantilla se CLONA a BD (cuestionario o plantilla personalizada),
la copia queda fijada en el idioma activo del usuario que clona; eso es lo
esperado: el original del sistema permanece bilingue.

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
       scoring_rules=None, requires_evidence=False, options=None, help_text="",
       criticity=None, ir_level="medium", scenarios=None,
       text_en=None, help_text_en=None):
    q = {
        "id": qid,
        "text": text,
        "text_en": text_en or text,
        "type": qtype,
        "domain": domain,
        "control_refs": control_refs,
        "weight": weight,
        "scoring_rules": scoring_rules if scoring_rules is not None else YNP,
        "requires_evidence": requires_evidence,
        "help_text": help_text,
        "help_text_en": help_text_en or help_text,
        "criticity": criticity,
        "ir_level": ir_level,
        "nonconformity_value": "no",
        "scenarios": scenarios or ["SCN_ALWAYS"],
    }
    if options:
        q["options"] = options
    return q


# Helper para preguntas yes_no del assessment (sin parcial)
def _qa(qid, text, domain, control_refs, criticity, scenarios,
        ir_level="medium", weight=1.0, requires_evidence=False, help_text="",
        text_en=None, help_text_en=None):
    return _q(qid, text, domain, control_refs, weight=weight, qtype="yes_no",
              scoring_rules=YN, requires_evidence=requires_evidence, help_text=help_text,
              criticity=criticity, ir_level=ir_level, scenarios=scenarios,
              text_en=text_en, help_text_en=help_text_en)


# ---------- RH_TPRM_LITE_v1 ----------
_LITE = [
    _q("gov1", "La organizacion dispone de un SGSI certificado o equivalente (ISO 27001, SOC 2, ENS).",
       "governance", ["ISO27001:A.5.1", "ISO27001:A.5.19"], 1.5, requires_evidence=True,
       text_en="The organization has a certified ISMS or equivalent (ISO 27001, SOC 2, ENS)."),
    _q("acc1", "Se exige autenticacion multifactor (MFA) para el acceso a sistemas que tratan datos del cliente.",
       "access_control", ["ISO27001:A.8.5"], 1.5, qtype="single_choice", scoring_rules=MFA,
       options=["always_mfa_all_users", "mfa_privileged_only", "mfa_optional", "no_mfa"],
       text_en="Multi-factor authentication (MFA) is required to access systems that process customer data."),
    _q("cry1", "Los datos sensibles se cifran en transito y en reposo.",
       "cryptography", ["ISO27001:A.8.24"], 1.0,
       text_en="Sensitive data is encrypted in transit and at rest."),
    _q("inc1", "Existen procedimientos documentados de respuesta a incidentes con notificacion al cliente.",
       "incident_management", ["ISO27001:A.5.24", "NIS2:art.23"], 1.0,
       text_en="Documented incident response procedures exist, including customer notification."),
    _q("priv1", "Si trata datos personales, existe un acuerdo de encargado de tratamiento (DPA, GDPR art. 28).",
       "privacy", ["GDPR:art.28"], 1.0, requires_evidence=True,
       text_en="If personal data is processed, a data processing agreement is in place (DPA, GDPR art. 28)."),
    _q("sup1", "Existe una politica de seguridad de la cadena de suministro para sus propios proveedores.",
       "supplier_chain", ["ISO27001:A.5.21", "NIS2:art.21.2.d"], 1.0,
       text_en="A supply chain security policy exists for the supplier's own vendors."),
]

# ---------- RH_TPRM_ISO27001_FULL_v1 ----------
_ISO27001 = [
    _q("org1", "Existe una politica de seguridad de la informacion aprobada por direccion y revisada periodicamente.",
       "governance", ["ISO27001:A.5.1"], 1.0, requires_evidence=True,
       text_en="An information security policy exists, approved by management and periodically reviewed."),
    _q("org2", "Hay roles y responsabilidades de seguridad definidos y segregacion de funciones.",
       "governance", ["ISO27001:A.5.2", "ISO27001:A.5.3"], 1.0,
       text_en="Security roles and responsibilities are defined, with segregation of duties."),
    _q("hr1", "El personal recibe formacion y concienciacion en seguridad de forma periodica.",
       "governance", ["ISO27001:A.6.3"], 1.0,
       text_en="Staff receive periodic security training and awareness."),
    _q("hr2", "Se realizan verificaciones de antecedentes antes de la contratacion cuando procede.",
       "governance", ["ISO27001:A.6.1"], 0.5,
       text_en="Background checks are performed before hiring where applicable."),
    _q("am1", "Existe un inventario de activos de informacion clasificado por sensibilidad.",
       "asset_management", ["ISO27001:A.5.9", "ISO27001:A.5.12"], 1.0,
       text_en="An information asset inventory classified by sensitivity is maintained."),
    _q("ac1", "Se aplica el principio de minimo privilegio con revision periodica de accesos.",
       "access_control", ["ISO27001:A.5.15", "ISO27001:A.5.18"], 1.0,
       text_en="The least privilege principle is applied, with periodic access reviews."),
    _q("ac2", "Se exige MFA para accesos privilegiados y remotos.",
       "access_control", ["ISO27001:A.8.5"], 1.5, qtype="single_choice", scoring_rules=MFA,
       options=["always_mfa_all_users", "mfa_privileged_only", "mfa_optional", "no_mfa"],
       text_en="MFA is required for privileged and remote access."),
    _q("ac3", "Se gestiona el ciclo de vida de cuentas (alta, cambios, baja) de forma controlada.",
       "access_control", ["ISO27001:A.5.16", "ISO27001:A.5.18"], 1.0,
       text_en="The account lifecycle (provisioning, changes, deprovisioning) is managed in a controlled way."),
    _q("cr1", "Existe una politica criptografica y gestion segura de claves (KMS/HSM).",
       "cryptography", ["ISO27001:A.8.24"], 1.0,
       text_en="A cryptographic policy and secure key management (KMS/HSM) are in place."),
    _q("ph1", "Existen controles de seguridad fisica en las instalaciones que alojan datos del cliente.",
       "physical_security", ["ISO27001:A.7.1", "ISO27001:A.7.2"], 0.5,
       text_en="Physical security controls exist at facilities hosting customer data."),
    _q("ops1", "Se aplica gestion de parches y hardening de sistemas de forma documentada.",
       "operations_security", ["ISO27001:A.8.8", "ISO27001:A.8.9"], 1.0,
       text_en="Patch management and system hardening are applied in a documented manner."),
    _q("ops2", "Se realizan copias de seguridad probadas periodicamente.",
       "operations_security", ["ISO27001:A.8.13"], 1.0, requires_evidence=True,
       text_en="Backups are performed and tested periodically."),
    _q("ops3", "Existe registro y monitorizacion de eventos de seguridad (logging).",
       "operations_security", ["ISO27001:A.8.15", "ISO27001:A.8.16"], 1.0,
       text_en="Security event logging and monitoring are in place."),
    _q("net1", "La red esta segmentada y protegida (firewalls, IDS/IPS).",
       "network_security", ["ISO27001:A.8.20", "ISO27001:A.8.22"], 1.0,
       text_en="The network is segmented and protected (firewalls, IDS/IPS)."),
    _q("dev1", "El desarrollo sigue un ciclo seguro (SDLC) con SAST/DAST/SCA y revision de codigo.",
       "secure_development", ["ISO27001:A.8.25", "ISO27001:A.8.28"], 1.0,
       text_en="Development follows a secure lifecycle (SDLC) with SAST/DAST/SCA and code review."),
    _q("sup1", "Se evalua y supervisa la seguridad de los propios proveedores.",
       "supplier_chain", ["ISO27001:A.5.19", "ISO27001:A.5.21", "ISO27001:A.5.22"], 1.0,
       text_en="The security of the supplier's own vendors is assessed and monitored."),
    _q("inc1", "Existe gestion de incidentes con metricas (MTTD/MTTR) y notificacion.",
       "incident_management", ["ISO27001:A.5.24", "ISO27001:A.5.26"], 1.0,
       text_en="Incident management exists with metrics (MTTD/MTTR) and notification."),
    _q("bc1", "Existe un plan de continuidad/recuperacion (RTO/RPO) probado anualmente.",
       "business_continuity", ["ISO27001:A.5.29", "ISO27001:A.5.30"], 1.0, requires_evidence=True,
       text_en="A continuity/recovery plan (RTO/RPO) exists and is tested annually."),
    _q("cmp1", "Se realizan auditorias internas y se concede derecho de auditoria al cliente.",
       "compliance_legal", ["ISO27001:A.5.35", "ISO27001:A.5.36"], 1.0,
       text_en="Internal audits are performed and the customer is granted audit rights."),
    # --- Cobertura ampliada del Annex A ---
    _q("ac4", "Se usa gestion de accesos privilegiados (PAM) y bovedas de credenciales.",
       "access_control", ["ISO27001:A.8.2", "ISO27001:A.8.5"], 1.0,
       text_en="Privileged access management (PAM) and credential vaults are used."),
    _q("ac5", "El acceso remoto se realiza por canales seguros (VPN/ZTNA) con MFA.",
       "network_security", ["ISO27001:A.6.7", "ISO27001:A.8.20"], 1.0,
       text_en="Remote access is performed over secure channels (VPN/ZTNA) with MFA."),
    _q("cr2", "Las claves criptograficas se gestionan en un ciclo de vida formal (generacion, rotacion, custodia, revocacion).",
       "cryptography", ["ISO27001:A.8.24"], 1.0, requires_evidence=True,
       text_en="Cryptographic keys are managed through a formal lifecycle (generation, rotation, custody, revocation)."),
    _q("ops4", "Se realiza gestion de vulnerabilidades tecnicas con plazos por criticidad.",
       "operations_security", ["ISO27001:A.8.8"], 1.0,
       text_en="Technical vulnerability management is performed with remediation deadlines by criticality."),
    _q("ops5", "Existen entornos separados de desarrollo, pruebas y produccion.",
       "operations_security", ["ISO27001:A.8.31"], 0.5,
       text_en="Separate development, testing and production environments exist."),
    _q("dev2", "Se gestionan secretos y credenciales fuera del codigo fuente (vault, no hardcode).",
       "secure_development", ["ISO27001:A.8.25", "ISO27001:A.8.28"], 1.0,
       text_en="Secrets and credentials are managed outside the source code (vault, no hardcoding)."),
    _q("dev3", "Se mantiene un inventario de dependencias (SBOM) y se analizan sus vulnerabilidades.",
       "supplier_chain", ["ISO27001:A.8.28"], 1.0,
       text_en="A dependency inventory (SBOM) is maintained and its vulnerabilities are analyzed."),
    _q("sup2", "Los contratos con subcontratistas incluyen clausulas minimas de seguridad y notificacion.",
       "supplier_chain", ["ISO27001:A.5.20", "ISO27001:A.5.21"], 1.0,
       text_en="Contracts with subcontractors include minimum security and notification clauses."),
    _q("inc2", "Se notifican los incidentes que afecten al cliente dentro de un SLA acordado (p. ej. 24-72h).",
       "incident_management", ["ISO27001:A.5.24", "ISO27001:A.5.26"], 1.0,
       text_en="Incidents affecting the customer are notified within an agreed SLA (e.g. 24-72h)."),
    _q("bc2", "Las copias de seguridad y los planes de recuperacion se prueban de forma documentada.",
       "business_continuity", ["ISO27001:A.8.13", "ISO27001:A.5.30"], 1.0, requires_evidence=True,
       text_en="Backups and recovery plans are tested in a documented manner."),
    _q("priv2", "Se aplica minimizacion y retencion controlada de los datos del cliente.",
       "privacy", ["ISO27001:A.5.34", "GDPR:art.5"], 0.5,
       text_en="Minimization and controlled retention of customer data are applied."),
    _q("cmp2", "Se realizan pruebas de penetracion por terceros de forma periodica (anual).",
       "compliance_legal", ["ISO27001:A.8.8", "ISO27001:A.5.36"], 1.0, requires_evidence=True,
       text_en="Third-party penetration tests are performed periodically (annually)."),
]

# ---------- RH_TPRM_GDPR_PROCESSOR_v1 ----------
_GDPR = [
    _q("g1", "Actua como encargado del tratamiento y existe un DPA firmado (art. 28).",
       "privacy", ["GDPR:art.28"], 1.5, requires_evidence=True,
       text_en="The supplier acts as data processor and a signed DPA exists (art. 28)."),
    _q("g2", "Mantiene un registro de actividades de tratamiento (art. 30).",
       "privacy", ["GDPR:art.30"], 1.0,
       text_en="A record of processing activities is maintained (art. 30)."),
    _q("g3", "Aplica medidas de seguridad apropiadas (art. 32): cifrado, seudonimizacion, resiliencia.",
       "privacy", ["GDPR:art.32"], 1.5,
       text_en="Appropriate security measures are applied (art. 32): encryption, pseudonymization, resilience."),
    _q("g4", "Notifica al responsable las brechas de datos sin dilacion indebida (art. 33).",
       "privacy", ["GDPR:art.33"], 1.0,
       text_en="Data breaches are notified to the controller without undue delay (art. 33)."),
    _q("g5", "Solo subcontrata con autorizacion y notifica cambios de subencargados (art. 28.2).",
       "supplier_chain", ["GDPR:art.28"], 1.0,
       text_en="Subprocessing only occurs with authorization and changes of subprocessors are notified (art. 28.2)."),
    _q("g6", "Las transferencias internacionales cuentan con garantias adecuadas (art. 44-49).",
       "privacy", ["GDPR:art.44"], 1.0, qtype="single_choice",
       scoring_rules={"no_transfers": 100, "scc_bcr": 90, "adequacy": 100, "no_safeguards": 0},
       options=["no_transfers", "adequacy", "scc_bcr", "no_safeguards"],
       text_en="International transfers have adequate safeguards (art. 44-49)."),
    _q("g7", "Asiste al responsable en el ejercicio de derechos de los interesados (art. 12-22).",
       "privacy", ["GDPR:art.28"], 0.5,
       text_en="The controller is assisted with data subject rights requests (art. 12-22)."),
]

# ---------- RH_TPRM_NIS2_v1 ----------
_NIS2 = [
    _q("n1", "Politicas de analisis de riesgos y seguridad de la informacion (art. 21.2.a).",
       "risk_management", ["NIS2:art.21.2.a"], 1.0,
       text_en="Risk analysis and information security policies (art. 21.2.a)."),
    _q("n2", "Gestion de incidentes (art. 21.2.b).",
       "incident_management", ["NIS2:art.21.2.b"], 1.0,
       text_en="Incident handling (art. 21.2.b)."),
    _q("n3", "Continuidad de negocio y gestion de crisis (art. 21.2.c).",
       "business_continuity", ["NIS2:art.21.2.c"], 1.0, requires_evidence=True,
       text_en="Business continuity and crisis management (art. 21.2.c)."),
    _q("n4", "Seguridad de la cadena de suministro (art. 21.2.d).",
       "supplier_chain", ["NIS2:art.21.2.d"], 1.5,
       text_en="Supply chain security (art. 21.2.d)."),
    _q("n5", "Seguridad en adquisicion, desarrollo y mantenimiento (art. 21.2.e).",
       "secure_development", ["NIS2:art.21.2.e"], 1.0,
       text_en="Security in acquisition, development and maintenance (art. 21.2.e)."),
    _q("n6", "Politicas para evaluar la eficacia de las medidas (art. 21.2.f).",
       "governance", ["NIS2:art.21.2.f"], 1.0,
       text_en="Policies to assess the effectiveness of measures (art. 21.2.f)."),
    _q("n7", "Higiene basica de ciberseguridad y formacion (art. 21.2.g).",
       "governance", ["NIS2:art.21.2.g"], 1.0,
       text_en="Basic cyber hygiene and training (art. 21.2.g)."),
    _q("n8", "Uso de criptografia y cifrado (art. 21.2.h).",
       "cryptography", ["NIS2:art.21.2.h"], 1.0,
       text_en="Use of cryptography and encryption (art. 21.2.h)."),
    _q("n9", "Seguridad de RRHH, control de accesos y gestion de activos (art. 21.2.i).",
       "access_control", ["NIS2:art.21.2.i"], 1.0,
       text_en="HR security, access control and asset management (art. 21.2.i)."),
    _q("n10", "Autenticacion multifactor y comunicaciones seguras (art. 21.2.j).",
       "access_control", ["NIS2:art.21.2.j"], 1.5, qtype="single_choice", scoring_rules=MFA,
       options=["always_mfa_all_users", "mfa_privileged_only", "mfa_optional", "no_mfa"],
       text_en="Multi-factor authentication and secure communications (art. 21.2.j)."),
]

# ---------- RH_TPRM_DORA_ICT_v1 ----------
_DORA = [
    _q("d1", "El contrato ICT cumple los requisitos del art. 30 (descripcion servicio, ubicaciones de datos, niveles de servicio).",
       "compliance_legal", ["DORA:art.30"], 1.5, requires_evidence=True,
       text_en="The ICT contract meets the requirements of art. 30 (service description, data locations, service levels)."),
    _q("d2", "Garantiza derechos de acceso, inspeccion y auditoria a la entidad financiera (art. 30.3).",
       "compliance_legal", ["DORA:art.30"], 1.0,
       text_en="Access, inspection and audit rights are guaranteed to the financial entity (art. 30.3)."),
    _q("d3", "Notifica incidentes graves relacionados con las TIC en plazo (art. 28).",
       "incident_management", ["DORA:art.28"], 1.0,
       text_en="Major ICT-related incidents are notified within the required timeframe (art. 28)."),
    _q("d4", "Dispone de estrategias de salida y planes de transicion (art. 28.8).",
       "business_continuity", ["DORA:art.28"], 1.0,
       text_en="Exit strategies and transition plans are in place (art. 28.8)."),
    _q("d5", "Participa en pruebas de resiliencia operativa digital cuando aplica (TLPT/TIBER-EU).",
       "resilience_testing", ["DORA:art.26", "DORA:art.27"], 1.0,
       text_en="Participates in digital operational resilience testing where applicable (TLPT/TIBER-EU)."),
    _q("d6", "Gestiona el riesgo de subcontratacion de servicios ICT criticos (RTS subcontratacion).",
       "supplier_chain", ["DORA:art.30"], 1.0,
       text_en="Subcontracting risk of critical ICT services is managed (subcontracting RTS)."),
    _q("d7", "Mantiene medidas de continuidad y recuperacion con RTO/RPO acordados.",
       "business_continuity", ["DORA:art.11", "DORA:art.12"], 1.0, requires_evidence=True,
       text_en="Continuity and recovery measures with agreed RTO/RPO are maintained."),
]

# ---------- RH_TPRM_AI_USAGE_DECLARATION_v1 ----------
_AI = [
    _q("ai1", "Declara si utiliza sistemas de IA para prestar el servicio contratado.",
       "ai_governance", ["ISO42001:A.2"], 1.0, qtype="yes_no", scoring_rules=YN,
       text_en="Declares whether AI systems are used to deliver the contracted service."),
    _q("ai2", "Dispone de gobernanza de IA (politicas, supervision humana, roles) — ISO 42001 AIMS.",
       "ai_governance", ["ISO42001:A.3", "ISO42001:A.4"], 1.0,
       text_en="AI governance is in place (policies, human oversight, roles) — ISO 42001 AIMS."),
    _q("ai3", "Evalua el impacto de los sistemas de IA (sesgo, equidad, derechos).",
       "ai_governance", ["ISO42001:A.5"], 1.0,
       text_en="The impact of AI systems is assessed (bias, fairness, rights)."),
    _q("ai4", "Garantiza transparencia e informacion sobre decisiones automatizadas.",
       "ai_governance", ["ISO42001:A.8"], 1.0,
       text_en="Transparency and information about automated decisions are guaranteed."),
    _q("ai5", "Controla el uso de datos del cliente para entrenamiento de modelos.",
       "ai_governance", ["ISO42001:A.7"], 1.0, qtype="yes_no", scoring_rules=YN,
       text_en="The use of customer data for model training is controlled."),
]

# ---------- RH_TPRM_OFFBOARDING_v1 ----------
_OFFBOARD = [
    _q("o1", "Se han revocado todos los accesos (SSO, VPN, API keys, cuentas dedicadas).",
       "access_control", ["ISO27001:A.5.18"], 1.5, requires_evidence=True,
       text_en="All access has been revoked (SSO, VPN, API keys, dedicated accounts)."),
    _q("o2", "Se ha devuelto o destruido de forma certificada la informacion del cliente.",
       "privacy", ["ISO27001:A.5.10", "GDPR:art.28"], 1.5, requires_evidence=True,
       text_en="Customer information has been returned or destroyed with certification."),
    _q("o3", "Se han cerrado las cuentas de subencargados implicados.",
       "supplier_chain", ["ISO27001:A.5.22"], 1.0,
       text_en="Accounts of involved subprocessors have been closed."),
    _q("o4", "Se ha realizado la auditoria/cuestionario final de salida.",
       "compliance_legal", ["ISO27001:A.5.22"], 1.0,
       text_en="The final exit audit/questionnaire has been completed."),
    _q("o5", "Se han archivado las evidencias para retencion legal.",
       "compliance_legal", ["ISO27001:A.5.33"], 0.5,
       text_en="Evidence has been archived for legal retention."),
]


# ============================================================
# CATALOGO COMPLETO (§4 del spec RISKHUB_TPRM_QUESTIONNAIRES)
# Plantillas por nivel: Profiling + Assessment MEDIUM/HIGH/CRITICAL
# ============================================================

# ---------- FASE A: RISK PROFILING (RP01-RP12) ----------
# Respondido por el usuario INTERNO. No se envia al proveedor directamente.
_RP_QUESTIONS = [
    _q("RP01", "El servicio se considera critico en terminos de disponibilidad (RTO < 3 dias)?",
       "business_continuity", ["ISO22301", "NIS2:art.21.2.c", "DORA:art.11"],
       weight=1.0, qtype="yes_no", scoring_rules=YN,
       scenarios=["SCN_CRITICAL_AVAILABILITY"],
       help_text="Si el servicio se interrumpe, la recuperacion debe ser inferior a 3 dias.",
       text_en="Is the service considered critical in terms of availability (RTO < 3 days)?",
       help_text_en="If the service is interrupted, recovery must take less than 3 days."),
    _q("RP02", "El servicio implica acceso o tratamiento de datos personales de clientes o empleados?",
       "privacy", ["GDPR:art.28", "GDPR:art.32", "ISO27701"],
       weight=1.0, qtype="yes_no", scoring_rules=YN,
       scenarios=["SCN_PERSONAL_DATA"],
       help_text="Datos que permiten identificar a personas fisicas.",
       text_en="Does the service involve access to or processing of personal data of customers or employees?",
       help_text_en="Data that allows natural persons to be identified."),
    _q("RP03", "El servicio implica acceso o tratamiento de informacion interna (documentos, procedimientos, politicas)?",
       "governance", ["ISO27001:A.5.12", "ENS:mp.info.1"],
       weight=1.0, qtype="yes_no", scoring_rules=YN,
       scenarios=["SCN_INTERNAL_INFO"],
       text_en="Does the service involve access to or processing of internal information (documents, procedures, policies)?"),
    _q("RP04", "El servicio implica acceso o tratamiento de informacion estrategica de negocio (M&A, financiera)?",
       "governance", ["ISO27001:A.5.12"],
       weight=1.0, qtype="yes_no", scoring_rules=YN,
       scenarios=["SCN_STRATEGIC_INFO"],
       text_en="Does the service involve access to or processing of strategic business information (M&A, financial)?"),
    _q("RP05", "El servicio implica acceso o tratamiento de informacion critica de seguridad (infraestructuras, vulnerabilidades, incidentes)?",
       "governance", ["ISO27001:A.5.12", "ISO27001:A.5.24", "NIS2:art.21.2.h"],
       weight=1.0, qtype="yes_no", scoring_rules=YN,
       scenarios=["SCN_SECURITY_INFO"],
       text_en="Does the service involve access to or processing of critical security information (infrastructure, vulnerabilities, incidents)?"),
    _q("RP06", "El servicio implica acceso o tratamiento de datos de tarjeta de credito/debito (PAN, CVV)?",
       "compliance_legal", ["PCI-DSS:Req.3"],
       weight=1.0, qtype="yes_no", scoring_rules=YN,
       scenarios=["SCN_PAYMENT_CARDS"],
       text_en="Does the service involve access to or processing of credit/debit card data (PAN, CVV)?"),
    _q("RP07", "El proveedor utiliza o prevee utilizar herramientas de Inteligencia Artificial en la prestacion del servicio?",
       "ai_governance", ["EU-AI-Act:art.13", "ISO42001:A.6"],
       weight=1.0, qtype="yes_no", scoring_rules=YN,
       scenarios=["SCN_AI_USAGE"],
       text_en="Does the supplier use or plan to use Artificial Intelligence tools in delivering the service?"),
    _q("RP08", "El proveedor utilizara su endpoint corporativo para prestar el servicio?",
       "operations_security", ["ISO27001:A.8.1", "ENS:mp.eq"],
       weight=1.0, qtype="yes_no", scoring_rules=YN,
       scenarios=["SCN_VENDOR_ENDPOINT"],
       text_en="Will the supplier use its own corporate endpoint to deliver the service?"),
    _q("RP09", "La informacion se alojara en los sistemas del proveedor o de otros terceros?",
       "operations_security", ["ISO27001:A.5.23", "ENS:op.ext"],
       weight=1.0, qtype="yes_no", scoring_rules=YN,
       scenarios=["SCN_VENDOR_HOSTING", "SCN_EXPOSED_SYSTEM", "SCN_DESTRUCTION_REQUIRED"],
       text_en="Will the information be hosted on the supplier's systems or those of other third parties?"),
    _q("RP10", "El servicio implica integracion con los sistemas internos de la organizacion?",
       "network_security", ["ISO27001:A.8.21", "NIS2:art.21.2.d"],
       weight=1.0, qtype="yes_no", scoring_rules=YN,
       scenarios=["SCN_SYSTEM_INTEGRATION"],
       text_en="Does the service involve integration with the organization's internal systems?"),
    _q("RP11", "El servicio implica el uso o despliegue de un producto o solucion de software?",
       "secure_development", ["ISO27001:A.8.25"],
       weight=1.0, qtype="yes_no", scoring_rules=YN,
       scenarios=["SCN_PRODUCT_DEPLOYMENT"],
       text_en="Does the service involve the use or deployment of a software product or solution?"),
    _q("RP12", "El producto o solucion se desplegara en sistemas del proveedor o de terceros (expuesto)?",
       "secure_development", ["ISO27001:A.5.23"],
       weight=1.0, qtype="yes_no", scoring_rules=YN,
       scenarios=["SCN_PRODUCT_EXTERNAL_DEPLOY", "SCN_EXPOSED_SYSTEM"],
       text_en="Will the product or solution be deployed on supplier or third-party systems (exposed)?"),
]

# ---------- FASE B: ASSESSMENT — CATALOGO COMPLETO (§4) ----------
# Niveles: medium=aparece en MEDIUM/HIGH/CRITICAL, high=HIGH/CRITICAL, critical=CRITICAL only

# IAM — Identity and Access Management
_CAT_IAM = [
    _qa("IAM01", "Los usuarios que acceden a la informacion seran nominativos (cuentas personales, no compartidas)?",
        "access_control", ["ISO27001:A.5.16", "ENS:op.acc.1"], "Major", ["SCN_ALWAYS"],
        text_en="Will the users accessing the information be nominative (personal accounts, not shared)?"),
    _qa("IAM02", "El proveedor dispone de una politica de uso seguro de la informacion que prohibe la descarga de datos del cliente?",
        "access_control", ["ISO27001:A.5.10", "ISO27001:A.5.13"], "Major", ["SCN_ALWAYS"], ir_level="high",
        text_en="Does the supplier have a secure information use policy that prohibits downloading customer data?"),
    _qa("IAM03", "La baja de un usuario se procesara en menos de 24 horas tras la solicitud?",
        "access_control", ["ISO27001:A.5.16", "ISO27001:A.5.18", "ENS:op.acc.4"], "Minor", ["SCN_ALWAYS"], ir_level="high",
        text_en="Will user deprovisioning be processed within 24 hours of the request?"),
    _qa("IAM04", "Existe un procedimiento documentado para el registro, baja y modificacion de usuarios con acceso?",
        "access_control", ["ISO27001:A.5.16", "ENS:op.acc.2"], "Minor", ["SCN_VENDOR_HOSTING"],
        text_en="Is there a documented procedure for registering, removing and modifying users with access?"),
    _qa("IAM05", "La gestion de identidades esta integrada con una fuente autoritativa (AD, IdP corporativo)?",
        "access_control", ["ISO27001:A.5.16", "ISO27001:A.5.17"], "Minor", ["SCN_VENDOR_HOSTING"],
        text_en="Is identity management integrated with an authoritative source (AD, corporate IdP)?"),
    _qa("IAM06", "Existe inventario actualizado de equipos y medios usados para almacenar o respaldar la informacion?",
        "access_control", ["ISO27001:A.5.9", "ENS:op.exp.1"], "Minor", ["SCN_VENDOR_HOSTING"], ir_level="critical",
        text_en="Is there an up-to-date inventory of equipment and media used to store or back up the information?"),
    _qa("IAM07", "Se utiliza autenticacion de doble factor (2FA/MFA) para acceder a los sistemas donde se almacena la informacion?",
        "access_control", ["ISO27001:A.8.5", "NIS2:art.21.2.j", "ENS:op.acc.5"], "Major", ["SCN_VENDOR_HOSTING"],
        requires_evidence=True,
        text_en="Is two-factor authentication (2FA/MFA) used to access the systems where the information is stored?"),
    _qa("IAM08", "Solo los usuarios necesarios tienen acceso a la informacion (modelo RBAC, minimo privilegio)?",
        "access_control", ["ISO27001:A.5.15", "ISO27001:A.5.18", "ENS:op.acc.4"], "Minor", ["SCN_VENDOR_HOSTING"],
        text_en="Do only the necessary users have access to the information (RBAC model, least privilege)?"),
    _qa("IAM09", "Los logs de acciones sobre la informacion estan disponibles y se conservan minimo 2 anos?",
        "access_control", ["ISO27001:A.8.15", "ENS:op.exp.8", "NIS2:art.21.2.b"], "Minor", ["SCN_VENDOR_HOSTING"], ir_level="high",
        text_en="Are logs of actions on the information available and retained for at least 2 years?"),
    _qa("IAM10", "Se realiza un servicio proactivo de log mining (minimo mensual)?",
        "access_control", ["ISO27001:A.8.16", "NIS2:art.21.2.b"], "Minor", ["SCN_VENDOR_HOSTING"], ir_level="critical",
        text_en="Is a proactive log mining service performed (at least monthly)?"),
    _qa("IAM11", "Se realiza una revision trimestral de usuarios y permisos con acceso a la informacion?",
        "access_control", ["ISO27001:A.5.18", "ENS:op.acc.4"], "Minor", ["SCN_VENDOR_HOSTING"],
        text_en="Is a quarterly review of users and permissions with access to the information performed?"),
]

# TRN — Cybersecurity Training
_CAT_TRN = [
    _qa("TRN01", "El proveedor imparte sesiones anuales de formacion sobre riesgos y buenas practicas con informacion confidencial?",
        "governance", ["ISO27001:A.6.3", "NIS2:art.21.2.g", "ENS:mp.per.3"], "Minor", ["SCN_ALWAYS"], ir_level="high",
        text_en="Does the supplier deliver annual training sessions on risks and good practices when handling confidential information?"),
]

# PRI — Processing / Access to Personal Data
_CAT_PRI = [
    _qa("PRI01", "El proveedor dispone de un Delegado de Proteccion de Datos (DPO)?",
        "privacy", ["GDPR:art.37-39", "ISO27701"], "Minor", ["SCN_PERSONAL_DATA"],
        text_en="Does the supplier have a Data Protection Officer (DPO)?"),
    _qa("PRI02", "Se mantiene actualizado el registro de actividades de tratamiento (RoPA, GDPR art.30)?",
        "privacy", ["GDPR:art.30", "ISO27701"], "Minor", ["SCN_PERSONAL_DATA"],
        text_en="Is the record of processing activities kept up to date (RoPA, GDPR art. 30)?"),
    _qa("PRI03", "Existe un acuerdo de encargado de tratamiento (DPA) firmado conforme al art. 28 GDPR?",
        "privacy", ["GDPR:art.28"], "Major", ["SCN_PERSONAL_DATA"], requires_evidence=True,
        text_en="Is there a signed data processing agreement (DPA) compliant with GDPR art. 28?"),
    _qa("PRI04", "Se realiza una DPIA (Evaluacion de Impacto en Proteccion de Datos) cuando aplica?",
        "privacy", ["GDPR:art.35"], "Minor", ["SCN_PERSONAL_DATA"], ir_level="high",
        text_en="Is a DPIA (Data Protection Impact Assessment) carried out where applicable?"),
    _qa("PRI05", "Las transferencias internacionales de datos tienen garantias adecuadas (SCC, BCR, decision de adecuacion)?",
        "privacy", ["GDPR:art.44-49"], "Major", ["SCN_PERSONAL_DATA"], ir_level="high",
        text_en="Do international data transfers have adequate safeguards (SCC, BCR, adequacy decision)?"),
    _qa("PRI06", "Las brechas de datos personales se notifican al cliente sin dilacion indebida y siempre en menos de 72h?",
        "privacy", ["GDPR:art.33", "ISO27701"], "Major", ["SCN_PERSONAL_DATA"], ir_level="high",
        text_en="Are personal data breaches notified to the customer without undue delay and always within 72 hours?"),
]

# EPP — Vendor Endpoint Protection
_CAT_EPP = [
    _qa("EPP01", "La contrasena de acceso al endpoint es robusta (minimo 12 caracteres, complejidad, no reutilizada)?",
        "operations_security", ["ISO27001:A.5.17", "ENS:op.acc.5"], "Minor", ["SCN_VENDOR_ENDPOINT"],
        text_en="Is the endpoint access password robust (minimum 12 characters, complexity, not reused)?"),
    _qa("EPP02", "Los permisos de administrador en los endpoints estan restringidos (least privilege)?",
        "operations_security", ["ISO27001:A.8.2"], "Major", ["SCN_VENDOR_ENDPOINT"],
        text_en="Are administrator permissions on endpoints restricted (least privilege)?"),
    _qa("EPP03", "Los endpoints estan cifrados (BitLocker o equivalente)?",
        "operations_security", ["ISO27001:A.8.24", "ENS:mp.eq.3"], "Major", ["SCN_VENDOR_ENDPOINT"],
        requires_evidence=True,
        text_en="Are endpoints encrypted (BitLocker or equivalent)?"),
    _qa("EPP04", "Los endpoints estan actualizados con los ultimos parches de seguridad?",
        "operations_security", ["ISO27001:A.8.8", "NIS2:art.21.2.e"], "Major", ["SCN_VENDOR_ENDPOINT"],
        text_en="Are endpoints up to date with the latest security patches?"),
    _qa("EPP05", "Los endpoints estan protegidos por una solucion EPP y/o EDR?",
        "operations_security", ["ISO27001:A.8.7", "NIS2:art.21.2.e"], "Major", ["SCN_VENDOR_ENDPOINT"],
        text_en="Are endpoints protected by an EPP and/or EDR solution?"),
    _qa("EPP06", "El acceso de escritura en puertos USB del endpoint esta deshabilitado?",
        "operations_security", ["ISO27001:A.8.13", "ENS:mp.eq.6"], "Minor", ["SCN_VENDOR_ENDPOINT"],
        text_en="Is write access to the endpoint's USB ports disabled?"),
    _qa("EPP07", "El endpoint incluye una solucion DLP para correo y navegacion con informes periodicos de alertas?",
        "operations_security", ["ISO27001:A.8.12"], "Major", ["SCN_VENDOR_ENDPOINT"], ir_level="high",
        text_en="Does the endpoint include a DLP solution for email and browsing with periodic alert reports?"),
    _qa("EPP08", "Existe solucion de navegacion web segura (proxy/SWG) tanto en red interna como externa?",
        "operations_security", ["ISO27001:A.8.23"], "Major", ["SCN_VENDOR_ENDPOINT"], ir_level="high",
        text_en="Is there a secure web browsing solution (proxy/SWG) on both internal and external networks?"),
    _qa("EPP09", "La navegacion a servicios cloud SaaS (file sharing, almacenamiento) esta restringida y controlada?",
        "operations_security", ["ISO27001:A.8.23"], "Major", ["SCN_VENDOR_ENDPOINT"], ir_level="high",
        text_en="Is browsing to SaaS cloud services (file sharing, storage) restricted and controlled?"),
    _qa("EPP10", "La informacion esta etiquetada para ser rastreada y monitorizada mediante DLP?",
        "operations_security", ["ISO27001:A.5.12", "ISO27001:A.8.12"], "Minor", ["SCN_VENDOR_ENDPOINT"], ir_level="critical",
        text_en="Is the information labeled so it can be tracked and monitored via DLP?"),
    _qa("EPP11", "Existe politica y control sobre la impresion de informacion confidencial?",
        "operations_security", ["ISO27001:A.5.10", "ENS:mp.info.4"], "Minor", ["SCN_VENDOR_ENDPOINT"], ir_level="high",
        text_en="Is there a policy and control over printing confidential information?"),
    _qa("EPP12", "Se ha realizado una revision de seguridad de los endpoints en el ultimo ano?",
        "operations_security", ["ISO27001:A.8.8"], "Minor", ["SCN_VENDOR_ENDPOINT"], ir_level="critical",
        text_en="Has a security review of the endpoints been performed in the last year?"),
    _qa("EPP13", "Si se permite BYOD, el acceso se gestiona mediante MDM (si no se permite, responder N/A)?",
        "operations_security", ["ISO27001:A.8.1", "ISO27001:A.6.7"], "Major", ["SCN_VENDOR_ENDPOINT"], ir_level="high",
        text_en="If BYOD is allowed, is access managed via MDM (if not allowed, answer N/A)?"),
]

# INC — Incidents Notification
_CAT_INC = [
    _qa("INC01", "El proveedor tiene un proceso para notificar incidentes dentro del perimetro del servicio (dispositivos perdidos, compromiso de credenciales, ransomware)?",
        "incident_management", ["ISO27001:A.5.24", "ISO27001:A.5.25", "NIS2:art.23", "GDPR:art.33"], "Minor", ["SCN_ALWAYS"], ir_level="high",
        text_en="Does the supplier have a process to notify incidents within the service perimeter (lost devices, credential compromise, ransomware)?"),
    _qa("INC02", "El proveedor se compromete a notificar incidentes de seguridad relevantes en maximo 24h desde la deteccion?",
        "incident_management", ["NIS2:art.23", "DORA:art.19", "GDPR:art.33"], "Major", ["SCN_ALWAYS"], ir_level="high",
        text_en="Does the supplier commit to notifying relevant security incidents within a maximum of 24 hours of detection?"),
    _qa("INC03", "Existe un canal tecnico definido (correo, SIEM, ticketing) y un contacto 24x7 para notificacion de incidentes?",
        "incident_management", ["ISO27001:A.5.25"], "Minor", ["SCN_ALWAYS"], ir_level="high",
        text_en="Is there a defined technical channel (email, SIEM, ticketing) and a 24x7 contact for incident notification?"),
]

# INF — Infrastructure
_CAT_INF = [
    _qa("INF01", "El equipo que gestiona la infraestructura incorpora solo recursos internos del proveedor?",
        "operations_security", ["ISO27001:A.5.19"], "Minor", ["SCN_VENDOR_HOSTING"],
        text_en="Is the team managing the infrastructure composed only of the supplier's internal staff?"),
    _qa("INF02", "Existen herramientas de deteccion o prevencion de intrusiones (IDS/IPS)?",
        "network_security", ["ISO27001:A.8.16", "NIS2:art.21.2.e"], "Minor", ["SCN_VENDOR_HOSTING"],
        text_en="Are intrusion detection or prevention tools in place (IDS/IPS)?"),
    _qa("INF03", "Los servidores se actualizan regularmente con parches de seguridad?",
        "operations_security", ["ISO27001:A.8.8"], "Minor", ["SCN_VENDOR_HOSTING"],
        text_en="Are servers regularly updated with security patches?"),
    _qa("INF04", "El acceso a la base de datos esta restringido desde la red interna?",
        "network_security", ["ISO27001:A.8.20", "ISO27001:A.8.22"], "Minor", ["SCN_VENDOR_HOSTING"], ir_level="high",
        text_en="Is database access restricted from the internal network?"),
    _qa("INF05", "Si se permite acceso remoto, esta autenticado con doble factor?",
        "access_control", ["ISO27001:A.8.5"], "Minor", ["SCN_VENDOR_HOSTING"],
        text_en="If remote access is allowed, is it authenticated with two-factor authentication?"),
    _qa("INF06", "La seguridad del entorno se monitoriza 24x7 (SIEM, CSPM o equivalente)?",
        "operations_security", ["ISO27001:A.8.15", "ISO27001:A.8.16", "NIS2:art.21.2.b"], "Minor", ["SCN_VENDOR_HOSTING"], ir_level="high",
        text_en="Is the environment's security monitored 24x7 (SIEM, CSPM or equivalent)?"),
    _qa("INF07", "La red esta segmentada en zonas de confianza (DMZ, interna, restringida) con controles entre ellas?",
        "network_security", ["ISO27001:A.8.22"], "Minor", ["SCN_VENDOR_HOSTING"], ir_level="high",
        text_en="Is the network segmented into trust zones (DMZ, internal, restricted) with controls between them?"),
]

# DAT — Data
_CAT_DAT = [
    _qa("DAT01", "Las comunicaciones y los datos en reposo estan cifrados con algoritmos robustos en todos los entornos?",
        "cryptography", ["ISO27001:A.8.24", "NIS2:art.21.2.h", "ENS:mp.info.3"], "Major", ["SCN_VENDOR_HOSTING"],
        requires_evidence=True,
        text_en="Are communications and data at rest encrypted with robust algorithms in all environments?"),
    _qa("DAT02", "Los logs a nivel de base de datos estan disponibles y se conservan minimo 2 anos?",
        "operations_security", ["ISO27001:A.8.15"], "Minor", ["SCN_VENDOR_HOSTING"], ir_level="high",
        text_en="Are database-level logs available and retained for at least 2 years?"),
    _qa("DAT03", "Se utiliza un sistema de gestion de claves (KMS/HSM) para proteger las claves criptograficas?",
        "cryptography", ["ISO27001:A.8.24"], "Minor", ["SCN_VENDOR_HOSTING"], ir_level="high",
        text_en="Is a key management system (KMS/HSM) used to protect cryptographic keys?"),
]

# BKP — Backups
_CAT_BKP = [
    _qa("BKP01", "Se realizan copias de seguridad diarias (datos criticos), semanales (datos moderados) y mensuales (datos estaticos)?",
        "business_continuity", ["ISO27001:A.8.13", "ISO22301", "ENS:op.cont"], "Major", ["SCN_CRITICAL_AVAILABILITY"],
        requires_evidence=True,
        text_en="Are backups performed daily (critical data), weekly (moderate data) and monthly (static data)?"),
    _qa("BKP02", "Se realizan pruebas de restauracion de backups al menos anualmente?",
        "business_continuity", ["ISO27001:A.8.13", "ISO22301"], "Major", ["SCN_CRITICAL_AVAILABILITY"],
        requires_evidence=True,
        text_en="Are backup restoration tests performed at least annually?"),
    _qa("BKP03", "El proveedor garantiza la inmutabilidad de los backups (proteccion anti-ransomware)?",
        "business_continuity", ["ISO27001:A.8.13", "NIS2:art.21.2.c"], "Minor", ["SCN_CRITICAL_AVAILABILITY"], ir_level="high",
        text_en="Does the supplier guarantee backup immutability (anti-ransomware protection)?"),
    _qa("BKP04", "Las copias de seguridad estan en una ubicacion fisica o logica distinta de la principal?",
        "business_continuity", ["ISO22301", "ENS:op.cont.3"], "Minor", ["SCN_CRITICAL_AVAILABILITY"], ir_level="high",
        text_en="Are backups stored in a physical or logical location separate from the primary one?"),
]

# PAM — Privileged Access Management
_CAT_PAM = [
    _qa("PAM01", "La gestion de cuentas privilegiadas se realiza mediante una solucion PAM?",
        "access_control", ["ISO27001:A.8.2", "ISO27001:A.5.15"], "Minor", ["SCN_VENDOR_HOSTING"], ir_level="high",
        text_en="Are privileged accounts managed through a PAM solution?"),
    _qa("PAM02", "Se realiza revision trimestral de usuarios privilegiados y se controlan permisos de terceros con acceso privilegiado?",
        "access_control", ["ISO27001:A.5.18"], "Minor", ["SCN_VENDOR_HOSTING"], ir_level="high",
        text_en="Is a quarterly review of privileged users performed and are third-party privileged access permissions controlled?"),
    _qa("PAM03", "Las sesiones administrativas con acceso a la informacion del cliente se graban (session recording)?",
        "access_control", ["ISO27001:A.8.15"], "Minor", ["SCN_VENDOR_HOSTING"], ir_level="critical",
        text_en="Are administrative sessions with access to customer information recorded (session recording)?"),
]

# EXP — System Exposed to the Outside
_CAT_EXP = [
    _qa("EXP01", "El sistema expuesto dispone de proteccion WAF y firewall perimetral?",
        "network_security", ["ISO27001:A.8.20", "ISO27001:A.8.23"], "Minor", ["SCN_EXPOSED_SYSTEM"],
        text_en="Does the exposed system have WAF protection and a perimeter firewall?"),
    _qa("EXP02", "La base de datos del sistema esta protegida frente a exposicion directa externa?",
        "network_security", ["ISO27001:A.8.20", "ISO27001:A.8.22"], "Major", ["SCN_EXPOSED_SYSTEM"],
        text_en="Is the system's database protected against direct external exposure?"),
    _qa("EXP03", "Se realizan escaneos de vulnerabilidades trimestrales y tests de penetracion anuales, y el sistema esta actualmente parcheado sin vulnerabilidades criticas o altas?",
        "resilience_testing", ["ISO27001:A.8.8", "ISO27001:A.8.29", "NIS2:art.21.2.f"], "Major", ["SCN_EXPOSED_SYSTEM"],
        requires_evidence=True,
        text_en="Are quarterly vulnerability scans and annual penetration tests performed, and is the system currently patched with no critical or high vulnerabilities?"),
    _qa("EXP04", "Los sistemas expuestos se han desarrollado considerando el principio Security by Design?",
        "secure_development", ["ISO27001:A.8.25", "NIS2:art.21.2.i"], "Minor", ["SCN_EXPOSED_SYSTEM"], ir_level="high",
        text_en="Have the exposed systems been developed following the Security by Design principle?"),
    _qa("EXP05", "Si se usan datos reales en pruebas de desarrollo, se aplica enmascaramiento de datos?",
        "secure_development", ["ISO27001:A.8.33", "GDPR:art.32"], "Minor", ["SCN_EXPOSED_SYSTEM"], ir_level="high",
        text_en="If real data is used in development testing, is data masking applied?"),
    _qa("EXP06", "El servicio se expone a traves de API gateways con autenticacion, rate limiting y validacion de inputs?",
        "network_security", ["ISO27001:A.8.21"], "Minor", ["SCN_SYSTEM_INTEGRATION"], ir_level="high",
        text_en="Is the service exposed through API gateways with authentication, rate limiting and input validation?"),
]

# CYI — Cyberintelligence
_CAT_CYI = [
    _qa("CYI01", "El proveedor dispone de un servicio de ciber-inteligencia para detectar fugas de informacion y filtracion de credenciales?",
        "incident_management", ["ISO27001:A.5.7", "NIS2:art.21.2.e"], "Minor", ["SCN_SECURITY_INFO"], ir_level="critical",
        text_en="Does the supplier have a cyber intelligence service to detect information leaks and credential exposure?"),
]

# IRP — Incident Response
_CAT_IRP = [
    _qa("IRP01", "Existe un playbook especifico de respuesta a incidentes para fugas o robo de informacion?",
        "incident_management", ["ISO27001:A.5.24", "ISO27001:A.5.26"], "Minor", ["SCN_SECURITY_INFO"], ir_level="critical",
        text_en="Is there a specific incident response playbook for information leaks or theft?"),
    _qa("IRP02", "Se realizan analisis post-incidente y se documentan las lecciones aprendidas?",
        "incident_management", ["ISO27001:A.5.27"], "Minor", ["SCN_SECURITY_INFO"], ir_level="high",
        text_en="Are post-incident analyses performed and lessons learned documented?"),
]

# CYX — Cyber Exercises
_CAT_CYX = [
    _qa("CYX01", "Se realizan ejercicios anuales de Red Team cuyo alcance incluye los sistemas que prestan servicio al cliente?",
        "resilience_testing", ["ISO27001:A.8.29", "DORA:art.24-27"], "Minor", ["SCN_SECURITY_INFO"], ir_level="critical",
        text_en="Are annual Red Team exercises performed with a scope covering the systems serving the customer?"),
    _qa("CYX02", "Se realizan ejercicios de simulacion de incidentes (table-top) al menos anualmente?",
        "resilience_testing", ["ISO27001:A.5.30", "ISO22301"], "Minor", ["SCN_SECURITY_INFO"], ir_level="high",
        text_en="Are incident simulation exercises (table-top) performed at least annually?"),
]

# DST — Destruction of Information
_CAT_DST = [
    _qa("DST01", "Existen procesos que garantizan la destruccion de la informacion tras la finalizacion del servicio?",
        "compliance_legal", ["ISO27001:A.8.10", "GDPR:art.5.1.e", "GDPR:art.28.3.g"], "Minor",
        ["SCN_DESTRUCTION_REQUIRED"], ir_level="critical",
        text_en="Are there processes guaranteeing the destruction of information after the service ends?"),
    _qa("DST02", "Se entrega certificado de destruccion de la informacion al finalizar el contrato?",
        "compliance_legal", ["ISO27001:A.8.10", "GDPR:art.28"], "Minor",
        ["SCN_DESTRUCTION_REQUIRED"], ir_level="critical", requires_evidence=True,
        text_en="Is a certificate of information destruction delivered at contract termination?"),
]

# BCM — Business Continuity
_CAT_BCM = [
    _qa("BCM01", "El proveedor dispone de un Plan de Continuidad de Negocio (BCP) documentado y probado al menos anualmente?",
        "business_continuity", ["ISO22301", "NIS2:art.21.2.c", "DORA:art.11"], "Major",
        ["SCN_CRITICAL_AVAILABILITY"], ir_level="high", requires_evidence=True,
        text_en="Does the supplier have a Business Continuity Plan (BCP) documented and tested at least annually?"),
    _qa("BCM02", "Existe un Plan de Recuperacion ante Desastres (DRP) con RTO y RPO documentados y validados?",
        "business_continuity", ["ISO22301", "DORA:art.12"], "Major",
        ["SCN_CRITICAL_AVAILABILITY"], ir_level="high", requires_evidence=True,
        text_en="Is there a Disaster Recovery Plan (DRP) with documented and validated RTO and RPO?"),
    _qa("BCM03", "Se identifican y gestionan las dependencias criticas de cuartos (subcontratistas) en el plan de continuidad?",
        "business_continuity", ["ISO22301", "NIS2:supply-chain", "DORA:art.28"], "Minor",
        ["SCN_CRITICAL_AVAILABILITY"], ir_level="high",
        text_en="Are critical fourth-party dependencies (subcontractors) identified and managed in the continuity plan?"),
]

# PCI — PCI DSS
_CAT_PCI = [
    _qa("PCI01", "El proveedor esta certificado o atestado PCI DSS vigente para el alcance del servicio?",
        "compliance_legal", ["PCI-DSS:Req.12"], "Major", ["SCN_PAYMENT_CARDS"], ir_level="critical",
        requires_evidence=True,
        text_en="Does the supplier hold a current PCI DSS certification or attestation for the service scope?"),
    _qa("PCI02", "El PAN (numero de tarjeta) se almacena cifrado y nunca el CVV ni datos sensibles de autenticacion (SAD)?",
        "cryptography", ["PCI-DSS:Req.3"], "Major", ["SCN_PAYMENT_CARDS"], ir_level="critical",
        text_en="Is the PAN (card number) stored encrypted and never the CVV or sensitive authentication data (SAD)?"),
    _qa("PCI03", "El Cardholder Data Environment (CDE) esta segmentado del resto de la red?",
        "network_security", ["PCI-DSS:Req.1"], "Major", ["SCN_PAYMENT_CARDS"], ir_level="critical",
        text_en="Is the Cardholder Data Environment (CDE) segmented from the rest of the network?"),
]

# AIG — AI Governance (EU AI Act + ISO 42001)
_CAT_AIG = [
    _qa("AIG01", "Estan identificadas todas las herramientas de IA, modelos y sub-procesadores usados en la prestacion del servicio?",
        "ai_governance", ["EU-AI-Act:art.13", "EU-AI-Act:art.50", "ISO42001:A.6"], "Major",
        ["SCN_AI_USAGE"], requires_evidence=True,
        text_en="Are all AI tools, models and sub-processors used in delivering the service identified?"),
    _qa("AIG02", "Cualquier dato del cliente procesado por IA se trata solo para el fin autorizado, no se usa para entrenamiento sin consentimiento y se protege de accesos no autorizados?",
        "ai_governance", ["EU-AI-Act:art.10", "ISO42001:A.7", "GDPR:art.5"], "Major", ["SCN_AI_USAGE"],
        text_en="Is any customer data processed by AI used only for the authorized purpose, never used for training without consent, and protected from unauthorized access?"),
    _qa("AIG03", "Existen controles de seguridad y gobernanza para los componentes de IA (control de acceso, logging, supervision humana)?",
        "ai_governance", ["EU-AI-Act:art.14", "ISO42001:A.8"], "Minor", ["SCN_AI_USAGE"], ir_level="high",
        text_en="Are there security and governance controls for the AI components (access control, logging, human oversight)?"),
    _qa("AIG04", "Se realizan evaluaciones de riesgos de seguridad especificas para IA (testing, modelado de amenazas)?",
        "ai_governance", ["EU-AI-Act:art.9", "ISO42001:A.5"], "Minor", ["SCN_AI_USAGE"], ir_level="critical",
        text_en="Are AI-specific security risk assessments performed (testing, threat modeling)?"),
    _qa("AIG05", "El proveedor cumple todos los requisitos regulatorios aplicables relacionados con IA y proteccion de datos (GDPR, EU AI Act)?",
        "ai_governance", ["EU-AI-Act", "GDPR", "ISO42001"], "Major", ["SCN_AI_USAGE"], ir_level="high",
        text_en="Does the supplier comply with all applicable regulatory requirements related to AI and data protection (GDPR, EU AI Act)?"),
    _qa("AIG06", "El sistema de IA esta clasificado segun las categorias de riesgo del EU AI Act y se documenta dicha clasificacion?",
        "ai_governance", ["EU-AI-Act:art.6", "EU-AI-Act:Annex-III"], "Major", ["SCN_AI_USAGE"], ir_level="high",
        requires_evidence=True,
        text_en="Is the AI system classified according to the EU AI Act risk categories and is that classification documented?"),
    _qa("AIG07", "Si el sistema de IA es de alto riesgo (Anexo III), se cumplen las obligaciones especificas de gobernanza, documentacion tecnica y supervision humana?",
        "ai_governance", ["EU-AI-Act:art.9-15"], "Major", ["SCN_AI_USAGE"], ir_level="critical",
        text_en="If the AI system is high-risk (Annex III), are the specific governance, technical documentation and human oversight obligations met?"),
    _qa("AIG08", "Se informa transparentemente a los usuarios cuando interactuan con un sistema de IA?",
        "ai_governance", ["EU-AI-Act:art.50"], "Minor", ["SCN_AI_USAGE"], ir_level="high",
        text_en="Are users transparently informed when interacting with an AI system?"),
    _qa("AIG09", "Se evaluan y mitigan los sesgos en los datos de entrenamiento y en las salidas del modelo?",
        "ai_governance", ["EU-AI-Act:art.10", "ISO42001:A.7"], "Minor", ["SCN_AI_USAGE"], ir_level="high",
        text_en="Are biases in training data and model outputs assessed and mitigated?"),
    _qa("AIG10", "Existe mecanismo de supervision humana significativa (human-in-the-loop) para decisiones automatizadas que afecten al cliente?",
        "ai_governance", ["EU-AI-Act:art.14", "GDPR:art.22"], "Major", ["SCN_AI_USAGE"], ir_level="high",
        text_en="Is there a meaningful human oversight mechanism (human-in-the-loop) for automated decisions affecting the customer?"),
    _qa("AIG11", "Se mantiene un registro de incidentes relacionados con la IA (model drift, fallos, decisiones erroneas)?",
        "ai_governance", ["EU-AI-Act:art.62", "ISO42001:A.9"], "Minor", ["SCN_AI_USAGE"], ir_level="high",
        text_en="Is a log of AI-related incidents maintained (model drift, failures, wrong decisions)?"),
    _qa("AIG12", "Se ha implementado un Sistema de Gestion de IA (AIMS) conforme a ISO/IEC 42001:2023?",
        "ai_governance", ["ISO42001"], "Minor", ["SCN_AI_USAGE"], ir_level="high", requires_evidence=True,
        text_en="Has an AI Management System (AIMS) compliant with ISO/IEC 42001:2023 been implemented?"),
]

# SDL — Secure Development
_CAT_SDL = [
    _qa("SDL01", "El desarrollo sigue un ciclo de vida seguro (SDLC) con revision de codigo y testing de seguridad?",
        "secure_development", ["ISO27001:A.8.25", "NIS2:art.21.2.e"], "Minor", ["SCN_PRODUCT_DEPLOYMENT"], ir_level="high",
        text_en="Does development follow a secure lifecycle (SDLC) with code review and security testing?"),
    _qa("SDL02", "Se ejecutan analisis SAST/DAST/SCA en cada release?",
        "secure_development", ["ISO27001:A.8.28", "ISO27001:A.8.29"], "Minor", ["SCN_PRODUCT_DEPLOYMENT"], ir_level="high",
        text_en="Are SAST/DAST/SCA analyses run on every release?"),
    _qa("SDL03", "Se mantiene un SBOM (Software Bill of Materials) actualizado y se comparte con el cliente bajo demanda?",
        "secure_development", ["NIST-SSDF", "EU-CRA"], "Minor", ["SCN_PRODUCT_DEPLOYMENT"], ir_level="high",
        text_en="Is an up-to-date SBOM (Software Bill of Materials) maintained and shared with the customer on demand?"),
    _qa("SDL04", "Existe una politica de divulgacion de vulnerabilidades (VDP) publica?",
        "secure_development", ["ISO29147", "ENISA-guidelines"], "Minor", ["SCN_PRODUCT_DEPLOYMENT"], ir_level="high",
        text_en="Is there a public vulnerability disclosure policy (VDP)?"),
]


def _filter_by_level(questions, max_level):
    """Filtra preguntas por nivel inherente: medium=todas, high=high+critical, critical=solo critical."""
    levels = {"medium": 0, "high": 1, "critical": 2}
    max_val = levels.get(max_level, 0)
    return [q for q in questions if levels.get(q.get("ir_level", "medium"), 0) <= max_val]


# Assessment MEDIUM: questions with ir_level=medium
_ALL_ASSESSMENT = (
    _CAT_IAM + _CAT_TRN + _CAT_PRI + _CAT_EPP + _CAT_INC +
    _CAT_INF + _CAT_DAT + _CAT_BKP + _CAT_PAM + _CAT_EXP +
    _CAT_CYI + _CAT_IRP + _CAT_CYX + _CAT_DST + _CAT_BCM +
    _CAT_PCI + _CAT_AIG + _CAT_SDL
)

_ASSESSMENT_MEDIUM = _filter_by_level(_ALL_ASSESSMENT, "medium")
_ASSESSMENT_HIGH = _filter_by_level(_ALL_ASSESSMENT, "high")
_ASSESSMENT_CRITICAL = _ALL_ASSESSMENT  # all levels

SYSTEM_TEMPLATES = [
    {
        "code": "RH_TPRM_LITE_v1",
        "name": "Cuestionario rapido (Tier Low)",
        "name_en": "Quick questionnaire (Tier Low)",
        "description": "ISO 27001 baseline + GDPR minimos. Proveedores no criticos.",
        "description_en": "ISO 27001 baseline + GDPR minimums. Non-critical suppliers.",
        "framework_codes": ["ISO_27001", "GDPR"],
        "target_tier": ["low", "medium"],
        "estimated_minutes": 15,
        "questions": _LITE,
    },
    {
        "code": "RH_TPRM_ISO27001_FULL_v1",
        "name": "ISO/IEC 27001:2022 + 27002 completo",
        "name_en": "ISO/IEC 27001:2022 + 27002 full",
        "description": "Cobertura de los dominios del Annex A. Proveedores critical/high.",
        "description_en": "Coverage of the Annex A domains. Critical/high suppliers.",
        "framework_codes": ["ISO_27001", "ISO_27002"],
        "target_tier": ["critical", "high"],
        "estimated_minutes": 60,
        "questions": _ISO27001,
    },
    {
        "code": "RH_TPRM_GDPR_PROCESSOR_v1",
        "name": "GDPR art. 28/32 — Encargado del tratamiento",
        "name_en": "GDPR art. 28/32 — Data processor",
        "description": "Procesamiento de datos personales, seguridad y transferencias.",
        "description_en": "Personal data processing, security and transfers.",
        "framework_codes": ["GDPR"],
        "target_tier": ["critical", "high", "medium"],
        "estimated_minutes": 25,
        "questions": _GDPR,
    },
    {
        "code": "RH_TPRM_NIS2_v1",
        "name": "NIS2 Directiva art. 21 medidas",
        "name_en": "NIS2 Directive art. 21 measures",
        "description": "Las 10 areas obligatorias del art. 21.2 (a-j) + cadena de suministro.",
        "description_en": "The 10 mandatory areas of art. 21.2 (a-j) + supply chain.",
        "framework_codes": ["NIS2"],
        "target_tier": ["critical", "high"],
        "estimated_minutes": 35,
        "questions": _NIS2,
    },
    {
        "code": "RH_TPRM_DORA_ICT_v1",
        "name": "DORA arts. 28-30 para proveedores ICT",
        "name_en": "DORA arts. 28-30 for ICT providers",
        "description": "Identificacion, contratos, notificacion y salida para terceros ICT.",
        "description_en": "Identification, contracts, notification and exit for ICT third parties.",
        "framework_codes": ["DORA"],
        "target_tier": ["critical", "high"],
        "estimated_minutes": 40,
        "questions": _DORA,
    },
    {
        "code": "RH_TPRM_AI_USAGE_DECLARATION_v1",
        "name": "Declaracion de uso de IA (ISO 42001 / EU AI Act)",
        "name_en": "AI usage declaration (ISO 42001 / EU AI Act)",
        "description": "Gobernanza, impacto, transparencia y datos de entrenamiento.",
        "description_en": "Governance, impact, transparency and training data.",
        "framework_codes": ["ISO_42001", "EU_AI_ACT"],
        "target_tier": ["critical", "high", "medium", "low"],
        "estimated_minutes": 15,
        "questions": _AI,
    },
    {
        "code": "RH_TPRM_OFFBOARDING_v1",
        "name": "Checklist de offboarding",
        "name_en": "Offboarding checklist",
        "description": "Devolucion/destruccion de datos, revocacion de accesos, auditoria final.",
        "description_en": "Data return/destruction, access revocation, final audit.",
        "framework_codes": ["ISO_27001", "GDPR"],
        "target_tier": ["critical", "high", "medium", "low"],
        "estimated_minutes": 15,
        "questions": _OFFBOARD,
    },
    # --- Nuevas plantillas del catalogo completo (§4 del spec) ---
    {
        "code": "RH_TPRM_PROFILING_v1",
        "name": "Risk Profiling — 12 preguntas (completar internamente)",
        "name_en": "Risk Profiling — 12 questions (complete internally)",
        "description": "Fase A: Calcula el nivel de riesgo inherente del servicio contratado. Lo completa el usuario interno, no el proveedor.",
        "description_en": "Phase A: Computes the inherent risk level of the contracted service. Completed by the internal user, not the supplier.",
        "framework_codes": ["ISO_27001", "NIS2", "GDPR", "DORA", "EU_AI_ACT"],
        "target_tier": ["critical", "high", "medium", "low"],
        "estimated_minutes": 10,
        "questions": _RP_QUESTIONS,
    },
    {
        "code": "RH_TPRM_ASSESSMENT_MEDIUM_v1",
        "name": "Assessment nivel MEDIO (~" + str(len(_ASSESSMENT_MEDIUM)) + " preguntas)",
        "name_en": "MEDIUM level assessment (~" + str(len(_ASSESSMENT_MEDIUM)) + " questions)",
        "description": "Fase B para proveedores con riesgo inherente MEDIO. Bloques: IAM, formacion, datos personales, endpoints, incidentes, infraestructura, datos, backups, continuidad.",
        "description_en": "Phase B for suppliers with MEDIUM inherent risk. Blocks: IAM, training, personal data, endpoints, incidents, infrastructure, data, backups, continuity.",
        "framework_codes": ["ISO_27001", "NIS2", "GDPR", "ENS"],
        "target_tier": ["medium"],
        "estimated_minutes": 30,
        "questions": _ASSESSMENT_MEDIUM,
    },
    {
        "code": "RH_TPRM_ASSESSMENT_HIGH_v1",
        "name": "Assessment nivel ALTO (~" + str(len(_ASSESSMENT_HIGH)) + " preguntas)",
        "name_en": "HIGH level assessment (~" + str(len(_ASSESSMENT_HIGH)) + " questions)",
        "description": "Fase B para proveedores con riesgo inherente ALTO. Incluye todas las preguntas MEDIO mas controles avanzados de PAM, DLP, inteligencia de amenazas y continuidad.",
        "description_en": "Phase B for suppliers with HIGH inherent risk. Includes all MEDIUM questions plus advanced PAM, DLP, threat intelligence and continuity controls.",
        "framework_codes": ["ISO_27001", "NIS2", "GDPR", "ENS", "DORA"],
        "target_tier": ["high"],
        "estimated_minutes": 50,
        "questions": _ASSESSMENT_HIGH,
    },
    {
        "code": "RH_TPRM_ASSESSMENT_CRITICAL_v1",
        "name": "Assessment nivel CRITICO (~" + str(len(_ASSESSMENT_CRITICAL)) + " preguntas)",
        "name_en": "CRITICAL level assessment (~" + str(len(_ASSESSMENT_CRITICAL)) + " questions)",
        "description": "Fase B para proveedores con riesgo inherente CRITICO. Catalogo completo: IAM, endpoints, incidentes, infraestructura, backups, PAM, sistemas expuestos, ciberinteligencia, respuesta a incidentes, ejercicios, destruccion, continuidad, PCI DSS, IA, desarrollo seguro.",
        "description_en": "Phase B for suppliers with CRITICAL inherent risk. Full catalogue: IAM, endpoints, incidents, infrastructure, backups, PAM, exposed systems, cyber intelligence, incident response, exercises, destruction, continuity, PCI DSS, AI, secure development.",
        "framework_codes": ["ISO_27001", "NIS2", "GDPR", "ENS", "DORA", "PCI_DSS", "EU_AI_ACT", "ISO_42001"],
        "target_tier": ["critical"],
        "estimated_minutes": 90,
        "questions": _ASSESSMENT_CRITICAL,
    },
]

_BY_CODE = {t["code"]: t for t in SYSTEM_TEMPLATES}

# Campos bilingues internos que no deben salir en las respuestas de la API
_I18N_QUESTION_FIELDS = ("text_en", "help_text_en")
_I18N_TEMPLATE_FIELDS = ("name_en", "description_en")


def _localize_question(q: dict, lang: str) -> dict:
    """Copia de la pregunta con text/help_text en el idioma pedido (sin campos *_en)."""
    q2 = {k: v for k, v in q.items() if k not in _I18N_QUESTION_FIELDS}
    if lang == "en":
        q2["text"] = q.get("text_en") or q.get("text", "")
        q2["help_text"] = q.get("help_text_en") or q.get("help_text", "")
    return q2


def localize_template(tpl: dict | None, lang: str = "es") -> dict | None:
    """Copia de la plantilla con name/description/preguntas en el idioma pedido.

    Patron identico a _localize_framework de compliance_service: los datos
    crudos llevan campos *_en y la traduccion se aplica al leer.
    """
    if not tpl:
        return tpl
    t2 = {k: v for k, v in tpl.items() if k not in _I18N_TEMPLATE_FIELDS}
    if lang == "en":
        t2["name"] = tpl.get("name_en") or tpl.get("name", "")
        t2["description"] = tpl.get("description_en") or tpl.get("description", "")
    t2["questions"] = [_localize_question(q, lang) for q in tpl.get("questions", [])]
    return t2


def list_templates(lang: str = "es") -> list:
    """Devuelve metadatos de las plantillas (sin el detalle de preguntas)."""
    key_name = "name_en" if lang == "en" else "name"
    key_desc = "description_en" if lang == "en" else "description"
    return [
        {
            "code": t["code"],
            "name": t.get(key_name) or t["name"],
            "description": t.get(key_desc) or t["description"],
            "framework_codes": t["framework_codes"],
            "target_tier": t["target_tier"],
            "estimated_minutes": t["estimated_minutes"],
            "question_count": len(t["questions"]),
            "is_system_template": True,
        }
        for t in SYSTEM_TEMPLATES
    ]


def get_template(code: str, lang: str = "es") -> dict | None:
    """Devuelve la plantilla completa por codigo, localizada al idioma pedido.

    Devuelve una copia (plantilla y preguntas): los clones a BD quedan en el
    idioma activo del usuario que clona, y el original permanece bilingue.
    """
    return localize_template(_BY_CODE.get(code), lang)
