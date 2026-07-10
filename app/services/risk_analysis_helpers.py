"""Helpers para enriquecer el contexto del analisis de riesgos ISO 27005.

Provee perfiles por tipo de activo, clasificacion de controles, calidad de evidencias
y construccion de la cadena amenaza-vulnerabilidad-control para el analisis IA.
"""
from __future__ import annotations

from typing import Optional


# ── Tipo de activo → perfil de seguridad ──────────────────────────────────────

ASSET_TYPE_PROFILES: dict[str, dict] = {
    "software": {
        "label": "Aplicacion / Software",
        "primary_dimensions": ["Confidencialidad", "Integridad"],
        "secondary_dimensions": ["Disponibilidad"],
        "typical_threat_categories": ["Ataque externo deliberado", "Explotacion de vulnerabilidades", "Acceso no autorizado", "Manipulacion de datos", "Supply chain"],
        "key_iso_controls": ["8.8", "8.28", "8.29", "8.25", "8.26", "8.27", "5.7", "8.9"],
        "key_risk_factors": "Superficie de ataque en codigo, dependencias de terceros, inyecciones (SQLi/XSS/etc), errores de autenticacion, exposicion de APIs, OWASP Top 10.",
        "evidence_guidance": "Resultados de SAST/DAST, informes de pentest, revision de codigo, CVEs gestionados, politica SDLC seguro.",
        "magerit_dimension": "integridad",
    },
    "hardware": {
        "label": "Hardware / Equipamiento fisico",
        "primary_dimensions": ["Disponibilidad", "Integridad"],
        "secondary_dimensions": ["Confidencialidad"],
        "typical_threat_categories": ["Dano fisico", "Robo", "Fallo tecnico", "Acceso fisico no autorizado", "Condiciones ambientales"],
        "key_iso_controls": ["7.1", "7.2", "7.3", "7.4", "7.5", "7.6", "7.8", "7.9", "7.10", "8.7"],
        "key_risk_factors": "Acceso fisico no controlado, mantenimiento inadecuado, obsolescencia, fallo de componentes, condiciones ambientales (temperatura, humedad, fuego).",
        "evidence_guidance": "Registros de inventario fisico, logs de acceso a salas tecnicas, contratos de mantenimiento, pruebas de backup de configuraciones.",
        "magerit_dimension": "disponibilidad",
    },
    "data": {
        "label": "Datos / Informacion",
        "primary_dimensions": ["Confidencialidad", "Integridad"],
        "secondary_dimensions": ["Disponibilidad", "Trazabilidad"],
        "typical_threat_categories": ["Filtracion de datos", "Acceso no autorizado", "Corrupcion de datos", "Perdida de datos", "Uso indebido interno"],
        "key_iso_controls": ["5.12", "5.13", "5.33", "5.34", "8.10", "8.11", "8.12", "8.24"],
        "key_risk_factors": "Clasificacion inadecuada, cifrado insuficiente, permisos excesivos, retencion indefinida, transferencia insegura, DPIA incompleto para datos personales.",
        "evidence_guidance": "Esquema de clasificacion de datos, politica de retencion, registros de cifrado en reposo/transito, control de acceso basado en roles, registros de transferencias.",
        "magerit_dimension": "confidencialidad",
    },
    "network": {
        "label": "Red / Infraestructura de comunicaciones",
        "primary_dimensions": ["Disponibilidad", "Confidencialidad"],
        "secondary_dimensions": ["Integridad"],
        "typical_threat_categories": ["Interrupcion de servicio (DDoS)", "Intercepcion de comunicaciones", "Movimiento lateral", "Configuracion insegura", "Acceso remoto no autorizado"],
        "key_iso_controls": ["8.20", "8.21", "8.22", "8.23", "8.19", "5.14", "8.15"],
        "key_risk_factors": "Segmentacion inadecuada, trafico no cifrado, reglas de firewall permisivas, servicios expuestos innecesariamente, VPN mal configurada, DNS sin proteccion.",
        "evidence_guidance": "Diagramas de red actualizados, resultados de escaneo de puertos, configuracion de firewalls auditada, monitoreo de trafico, registros de IDS/IPS.",
        "magerit_dimension": "disponibilidad",
    },
    "service": {
        "label": "Servicio / Proceso de negocio",
        "primary_dimensions": ["Disponibilidad", "Integridad"],
        "secondary_dimensions": ["Confidencialidad"],
        "typical_threat_categories": ["Interrupcion de servicio", "Fallo de proveedor", "SLA incumplido", "Dependencia critica", "Fallo en continuidad"],
        "key_iso_controls": ["5.29", "5.30", "5.31", "8.14", "5.19", "5.20", "5.21"],
        "key_risk_factors": "RTO/RPO sin validar, sin plan BCP/DRP, dependencia de proveedor unico, ausencia de redundancia, SLAs sin penalizacion, sin pruebas de recuperacion.",
        "evidence_guidance": "Plan BCP actualizado, resultados de ejercicios de DR, SLAs con penalizaciones, contratos de proveedor auditados, metricas de disponibilidad.",
        "magerit_dimension": "disponibilidad",
    },
    "cloud": {
        "label": "Servicio en la nube",
        "primary_dimensions": ["Confidencialidad", "Disponibilidad"],
        "secondary_dimensions": ["Integridad", "Trazabilidad"],
        "typical_threat_categories": ["Configuracion insegura de nube", "Acceso no autorizado (API/IAM)", "Filtracion de datos entre tenants", "Fallo del proveedor cloud", "Supply chain de software"],
        "key_iso_controls": ["5.23", "8.9", "5.17", "8.5", "5.15", "8.15", "8.25"],
        "key_risk_factors": "IAM mal configurado, buckets S3 publicos, secretos hardcodeados, logging insuficiente, datos sin cifrar en cloud, modelo de responsabilidad compartida mal entendido.",
        "evidence_guidance": "Cloud security posture assessment (CSPM), configuracion de IAM auditada, politica de uso de nube, evaluacion CAIQ/CSA, registros de actividad cloud.",
        "magerit_dimension": "confidencialidad",
    },
    "people": {
        "label": "Personas / Recurso humano",
        "primary_dimensions": ["Confidencialidad", "Integridad"],
        "secondary_dimensions": ["Disponibilidad"],
        "typical_threat_categories": ["Ingenieria social (phishing)", "Amenaza interna", "Error humano", "Falta de concienciacion", "Sabotaje"],
        "key_iso_controls": ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "6.8", "5.2", "5.9"],
        "key_risk_factors": "Falta de formacion en seguridad, ausencia de verificacion de antecedentes, permisos excesivos para funciones criticas, sin politica de escritorio limpio, sin NDA.",
        "evidence_guidance": "Registros de formacion en seguridad, verificacion de antecedentes documentada, acuerdos de confidencialidad firmados, metricas de phishing simulado.",
        "magerit_dimension": "confidencialidad",
    },
    "facility": {
        "label": "Instalaciones / Infraestructura fisica",
        "primary_dimensions": ["Disponibilidad"],
        "secondary_dimensions": ["Confidencialidad", "Integridad"],
        "typical_threat_categories": ["Acceso fisico no autorizado", "Desastre natural", "Fallo electrico", "Incendio", "Sabotaje fisico"],
        "key_iso_controls": ["7.1", "7.2", "7.3", "7.4", "7.5", "7.6", "7.7", "7.11", "7.12"],
        "key_risk_factors": "Control de acceso fisico insuficiente, sin UPS/generador, sin deteccion de incendios, ausencia de CCTV, mantenimiento preventivo inexistente.",
        "evidence_guidance": "Registros de acceso fisico, pruebas de UPS, contratos de mantenimiento, informes de auditoria fisica, planes de evacuacion.",
        "magerit_dimension": "disponibilidad",
    },
    "unknown": {
        "label": "Activo generico",
        "primary_dimensions": ["Confidencialidad", "Integridad", "Disponibilidad"],
        "secondary_dimensions": [],
        "typical_threat_categories": ["Acceso no autorizado", "Fallo tecnico", "Error humano"],
        "key_iso_controls": ["5.1", "5.2", "5.15", "8.5", "8.7"],
        "key_risk_factors": "Tipo de activo no especificado. Analizar segun dimensiones CIA declaradas.",
        "evidence_guidance": "Documentar el tipo de activo para obtener recomendaciones mas precisas.",
        "magerit_dimension": "confidencialidad",
    },
}


def get_asset_profile(asset_type: str) -> dict:
    """Retorna el perfil de riesgo para un tipo de activo dado."""
    key = (asset_type or "").lower().replace("-", "_").replace(" ", "_")
    # Normalizacion de valores del enum AssetType (incluye los valores reales
    # del catalogo ISO 27005 de RiskHub: primary_*/support_*)
    mapping = {
        "hardware": "hardware",
        "support_hardware": "hardware",
        "software": "software",
        "support_software": "software",
        "data": "data",
        "information": "data",
        "primary_information": "data",
        "datos": "data",
        "network": "network",
        "support_network": "network",
        "red": "network",
        "infrastructure": "network",
        "service": "service",
        "servicio": "service",
        "process": "service",
        "primary_process": "service",
        "support_organization": "service",
        "cloud": "cloud",
        "people": "people",
        "support_personnel": "people",
        "personas": "people",
        "human": "people",
        "facility": "facility",
        "support_site": "facility",
        "instalacion": "facility",
        "physical": "facility",
    }
    normalized = mapping.get(key, "unknown")
    return ASSET_TYPE_PROFILES.get(normalized, ASSET_TYPE_PROFILES["unknown"])


# ── Clasificacion de controles por tipo ───────────────────────────────────────

# ISO 27002:2022 control type classification
# P=Preventivo, D=Detectivo, C=Correctivo
CONTROL_TYPES: dict[str, str] = {
    # Tema 5: Controles organizacionales
    "5.1": "P", "5.2": "P", "5.3": "P", "5.4": "P", "5.5": "P",
    "5.6": "P", "5.7": "P", "5.8": "P", "5.9": "D", "5.10": "P",
    "5.11": "P", "5.12": "P", "5.13": "P", "5.14": "P", "5.15": "P",
    "5.16": "P", "5.17": "P", "5.18": "P", "5.19": "P", "5.20": "P",
    "5.21": "P", "5.22": "D", "5.23": "P", "5.24": "P", "5.25": "C",
    "5.26": "C", "5.27": "D", "5.28": "D", "5.29": "C", "5.30": "C",
    "5.31": "P", "5.32": "P", "5.33": "P", "5.34": "P",
    # Tema 6: Controles de personas
    "6.1": "P", "6.2": "P", "6.3": "P", "6.4": "P", "6.5": "P",
    "6.6": "P", "6.7": "P", "6.8": "D",
    # Tema 7: Controles fisicos
    "7.1": "P", "7.2": "P", "7.3": "P", "7.4": "D", "7.5": "P",
    "7.6": "P", "7.7": "P", "7.8": "P", "7.9": "P", "7.10": "P",
    "7.11": "C", "7.12": "C", "7.13": "P", "7.14": "P",
    # Tema 8: Controles tecnologicos
    "8.1": "P", "8.2": "P", "8.3": "P", "8.4": "P", "8.5": "P",
    "8.6": "P", "8.7": "P", "8.8": "P", "8.9": "P", "8.10": "P",
    "8.11": "C", "8.12": "D", "8.13": "C", "8.14": "C", "8.15": "D",
    "8.16": "D", "8.17": "P", "8.18": "P", "8.19": "P", "8.20": "P",
    "8.21": "P", "8.22": "P", "8.23": "P", "8.24": "P", "8.25": "P",
    "8.26": "P", "8.27": "P", "8.28": "P", "8.29": "D", "8.30": "D",
    "8.31": "P", "8.32": "P", "8.33": "P", "8.34": "P",
}

CONTROL_TYPE_LABELS = {
    "P": "Preventivo — bloquea la amenaza antes de que ocurra",
    "D": "Detectivo — identifica ataques en curso o post-incidente",
    "C": "Correctivo — limita el impacto o restaura tras el incidente",
}


def classify_control(code: str, name: str = "") -> str:
    """Retorna 'P', 'D' o 'C' para un codigo de control ISO 27002."""
    code_clean = (code or "").strip().lstrip("A.")
    # Busqueda exacta
    if code_clean in CONTROL_TYPES:
        return CONTROL_TYPES[code_clean]
    # Busqueda por prefijo (e.g. "8.28" → "8.28")
    prefix = ".".join(code_clean.split(".")[:2])
    if prefix in CONTROL_TYPES:
        return CONTROL_TYPES[prefix]
    # Heuristica por nombre
    name_lower = (name or "").lower()
    if any(k in name_lower for k in ["monitoreo", "deteccion", "alerta", "log", "audit", "siem", "monitor"]):
        return "D"
    if any(k in name_lower for k in ["recuperacion", "restauracion", "respuesta", "incidente", "backup", "continuidad"]):
        return "C"
    return "P"


# ── Calidad de evidencia ───────────────────────────────────────────────────────

def evidence_quality_score(evidence_refs: list[dict]) -> tuple[float, str]:
    """
    Calcula la calidad de la evidencia documental de un control.

    Retorna (factor 0.0-1.0, descripcion textual).

    Niveles:
      E5 Validado:   test automatizado, pentest, auditoria externa → 1.0
      E4 Probado:    procedimiento + registro de prueba            → 0.80
      E3 Documentado: politica formal + procedimiento             → 0.60
      E2 Informal:   proceso informal                             → 0.35
      E1 Declarado:  sin evidencia documental                     → 0.10
    """
    if not evidence_refs:
        return 0.10, "E1 — Sin evidencia documental. Madurez declarada sin respaldo."

    ref_count = len(evidence_refs)
    has_level4 = any(r.get("document_level", 0) >= 4 for r in evidence_refs)
    has_level3 = any(r.get("document_level", 0) >= 3 for r in evidence_refs)
    has_level2 = any(r.get("document_level", 0) >= 2 for r in evidence_refs)
    has_level1 = any(r.get("document_level", 0) >= 1 for r in evidence_refs)

    # Detectar palabras clave de alta calidad
    titles = " ".join((r.get("title", "") + " " + r.get("note", "")).lower() for r in evidence_refs)
    is_validated = any(k in titles for k in [
        "audit", "auditoria", "pentest", "test", "prueba", "resultado", "informe", "report",
        "evidencia", "evidence", "certificado", "certif", "scan", "escaneo",
    ])

    if is_validated and has_level4:
        return 1.0, f"E5 Validado — {ref_count} referencia(s) con instrucciones tecnicas y evidencia de prueba."
    if is_validated and has_level3:
        return 0.85, f"E4 Probado — {ref_count} referencia(s) con procedimientos y evidencia de prueba."
    if has_level3 and has_level2:
        return 0.65, f"E3 Documentado — {ref_count} referencia(s): norma + procedimiento sin evidencia de prueba."
    if has_level2 or (has_level1 and ref_count >= 2):
        return 0.45, f"E3 Documentado parcial — {ref_count} referencia(s) de nivel politica/norma."
    if has_level1:
        return 0.30, f"E2 Informal — {ref_count} referencia(s) de nivel politica sin procedimiento."
    return 0.15, f"E1 Declarado — {ref_count} referencia(s) sin nivel documental identificable."


def adjusted_maturity(maturity: int, evidence_refs: list[dict]) -> float:
    """
    Maturity real = maturity declarado × factor de calidad de evidencia.
    Penaliza controles con madurez alta pero evidencia pobre.
    """
    factor, _ = evidence_quality_score(evidence_refs)
    return round(maturity * factor, 1)


# ── Perfil del agente de amenaza ──────────────────────────────────────────────

def threat_actor_profile(threat_origin: str, threat_category: str) -> str:
    """Genera un perfil textual del agente de amenaza."""
    origin = (threat_origin or "").lower()
    cat = (threat_category or "").lower()

    profiles = {
        "deliberada": {
            "external": "Atacante externo motivado (cibercriminal, competidor, actor estatal). Requiere capacidades tecnicas variables segun el vector. Alta motivacion economica o de espionaje.",
            "internal": "Amenaza interna deliberada (empleado descontento, fraude). Tiene acceso privilegiado y conocimiento del entorno. Dificil de detectar con controles perimetrales.",
            "default": "Agente con intencion hostil. Puede ser externo o interno. Capacidades y motivacion variables segun el escenario especifico.",
        },
        "accidental": {
            "default": "Error no intencionado por personal interno o proveedor. Sin motivacion hostil pero con impacto potencial significativo. Alta frecuencia en entornos con formacion deficiente.",
        },
        "ambiental": {
            "default": "Evento natural o de infraestructura (fallo energetico, desastre natural, degradacion hardware). Sin agente activo. La frecuencia depende de la ubicacion geografica y la robustez de la infraestructura.",
        },
    }

    if "deliber" in origin or "intencional" in origin or "malicious" in origin:
        bucket = profiles["deliberada"]
        if any(k in cat for k in ["interno", "insider", "empleado"]):
            return bucket["internal"]
        return bucket["external"]
    elif "accidental" in origin or "error" in origin:
        return profiles["accidental"]["default"]
    elif "ambiental" in origin or "environmental" in origin or "natural" in origin:
        return profiles["ambiental"]["default"]
    return profiles["deliberada"]["default"]


# ── Constructor de seccion de vulnerabilidades ────────────────────────────────

def build_vuln_section(vulnerabilities: list) -> str:
    """Construye la seccion textual de vulnerabilidades para el prompt."""
    if not vulnerabilities:
        return "  (Sin vulnerabilidades especificas registradas — ADVERTENCIA: esto puede indicar analisis incompleto)"

    lines = []
    for v in vulnerabilities:
        cves = ", ".join(v.cves or []) if hasattr(v, "cves") and v.cves else ""
        cwes = ", ".join(str(c) for c in (v.cwes or [])) if hasattr(v, "cwes") and v.cwes else ""
        cat = getattr(v, "category", "") or ""
        line = f"  - [{v.code}] {v.name}"
        if cat:
            line += f" (categoria: {cat})"
        if cves:
            line += f" | CVEs: {cves}"
        if cwes:
            line += f" | CWEs: {cwes}"
        desc = (v.description or "")[:150]
        if desc:
            line += f"\n    Descripcion: {desc}"
        lines.append(line)

    return "\n".join(lines)


# ── Constructor de seccion de controles ──────────────────────────────────────

def build_control_section(ctrl_rows: list[dict]) -> str:
    """
    Construye la seccion textual de controles para el prompt con:
    - tipo (preventivo/detectivo/correctivo)
    - madurez ajustada por calidad de evidencia
    - referencias documentales completas
    """
    if not ctrl_rows:
        return "  (Sin controles vinculados — CRITICO: el riesgo carece de mitigacion formal)"

    lines = []
    for c in ctrl_rows:
        ctrl_type = classify_control(c.get("code", ""), c.get("name", ""))
        type_label = {"P": "PREVENTIVO", "D": "DETECTIVO", "C": "CORRECTIVO"}.get(ctrl_type, "?")
        mat = c.get("maturity", 0)
        refs = c.get("evidence_refs") or []
        ev_factor, ev_desc = evidence_quality_score(refs)
        adj_mat = adjusted_maturity(mat, refs)
        contrib = c.get("contribution", 1.0)
        eff = round(adj_mat / 5.0 * float(contrib) * 100)

        line = (
            f"  [{c.get('code','?')}] {c.get('name','?')}\n"
            f"    Tipo: {type_label} | Madurez declarada: {mat}/5 | Madurez ajustada: {adj_mat}/5\n"
            f"    Eficacia estimada: {eff}% | Calidad evidencia: {ev_desc}\n"
            f"    Estado: {c.get('status','N/A')}"
        )
        if refs:
            ref_titles = "; ".join(r.get("title", r.get("url", ""))[:80] for r in refs[:4])
            line += f"\n    Documentos de soporte: {ref_titles}"
        else:
            line += "\n    ADVERTENCIA: Sin evidencia documental registrada"

        lines.append(line)

    return "\n".join(lines)


# ── Constructor de seccion de cobertura documental ────────────────────────────

def build_document_coverage_section(ctrl_rows: list[dict], org_controls: list[dict]) -> str:
    """
    Muestra que controles del catalogo completo de la org. cubren documentalmente
    los controles vinculados al riesgo, incluyendo controles no vinculados que deberian estarlo.
    """
    if not ctrl_rows and not org_controls:
        return "  (Sin informacion de trazabilidad documental disponible)"

    lines = ["Controles vinculados al riesgo y su trazabilidad documental completa:"]
    for c in ctrl_rows:
        refs = c.get("evidence_refs") or []
        code = c.get("code", "?")
        name = c.get("name", "?")
        if refs:
            lines.append(f"  [{code}] {name}:")
            for r in refs[:5]:
                level = r.get("document_level", "?")
                level_name = {1: "Politica", 2: "Norma", 3: "Procedimiento", 4: "Instruccion Tecnica"}.get(level, f"Nivel {level}")
                lm = r.get("level_maturity", "?")
                title = r.get("title", r.get("url", "sin titulo"))[:80]
                lines.append(f"    - [{level_name}] '{title}' → aporta madurez {lm}/5")
        else:
            lines.append(f"  [{code}] {name}: SIN documentacion de respaldo")

    return "\n".join(lines)


# ── Normativa especifica para un riesgo ───────────────────────────────────────

FRAMEWORK_RISK_CONTEXT: dict[str, str] = {
    "ISO 27001": "Clausulas 6.1.2 (valoracion de riesgos) y 6.1.3 (tratamiento). El riesgo debe estar en el registro formal con propietario y estado de tratamiento.",
    "NIS2": "Art. 21 NIS2: medidas de gestion de riesgos de ciberseguridad. Para sectores esenciales e importantes, este riesgo requiere tratamiento documentado y notificacion si se materializa (Art. 23).",
    "GDPR": "Art. 32 RGPD: medidas tecnicas y organizativas adecuadas al riesgo. Si el activo contiene datos personales, evaluar impacto sobre derechos y libertades. Puede requerir DPIA (Art. 35).",
    "ENS": "RD 311/2022 ENS — Anexo II medidas de seguridad. Segun la categoria ENS del sistema, las medidas requeridas varian (basica/media/alta).",
    "DORA": "Art. 6 DORA: marco de gestion de riesgos de TIC. Requiere identificacion, clasificacion y documentacion. Art. 9: medidas de proteccion de activos TIC.",
    "PCI DSS": "PCI DSS v4.0 Req. 12.3: analisis de riesgos documentado. Req. 6: desarrollo seguro si el activo es aplicacion de pago.",
    "NIST CSF": "NIST CSF 2.0: funcion IDENTIFY (ID.RA Risk Assessment), PROTECT (PR), DETECT (DE). Asegurar que la funcion correcta cubre este riesgo.",
    "SOC 2": "Trust Services Criteria: CC9 (risk mitigation). El control debe estar en el sistema de gestion de riesgos y vinculado a criterios CC.",
    "HIPAA": "Security Rule 164.308(a)(1): analisis de riesgo obligatorio. 164.308(a)(1)(ii)(B): gestion de riesgos. Si el activo procesa ePHI, aplicar salvaguardas obligatorias.",
}


def normative_context(frameworks: list[str]) -> str:
    """Construye el contexto normativo relevante para el riesgo segun los frameworks activos."""
    if not frameworks:
        return "Sin frameworks activos especificados. Aplicar ISO 27001 como minimo."

    lines = []
    for fw in frameworks:
        ctx = FRAMEWORK_RISK_CONTEXT.get(fw)
        if ctx:
            lines.append(f"  [{fw}] {ctx}")

    return "\n".join(lines) if lines else "Frameworks activos sin contexto especifico disponible."


def build_vigilancia_context(db, asset_id: int | None, vuln_ids: list[int],
                             impl_ids: list[int], org_id: int) -> str:
    """Construye el bloque de evidencia real de Vigilancia para el analisis IA.

    Incluye:
    - OSINT findings vinculados a las vulnerabilidades del riesgo
    - External findings / CVEs vinculados al activo del riesgo
    - Regwatch change events que han flaggeado controles del riesgo para revision
    """
    from app.models import (
        OSINTFinding, osint_vulnerability_links,
        ExternalFinding, ControlImplementation, ChangePack,
    )
    lines: list[str] = []

    # 1. OSINT findings vinculados a las vulnerabilidades del riesgo
    if vuln_ids:
        osint_rows = (
            db.query(OSINTFinding)
            .join(osint_vulnerability_links,
                  OSINTFinding.id == osint_vulnerability_links.c.osint_finding_id)
            .filter(
                osint_vulnerability_links.c.vulnerability_id.in_(vuln_ids),
                OSINTFinding.is_remediated.is_(False),
            )
            .order_by(OSINTFinding.risk_score.desc())
            .limit(8)
            .all()
        )
        if osint_rows:
            lines.append("HALLAZGOS OSINT ACTIVOS (vinculados a vulnerabilidades de este riesgo):")
            for f in osint_rows:
                level = f.risk_level.upper() if f.risk_level else "?"
                lines.append(
                    f"  [{level}] {f.title} | Fuente:{f.source} | Tipo:{f.finding_type}"
                    + (f" | Score:{f.risk_score:.0f}" if f.risk_score else "")
                )
                if f.description:
                    lines.append(f"    Detalle: {f.description[:120]}")
            lines.append("")

    # 2. External findings / CVEs vinculados al activo
    if asset_id:
        ext_rows = (
            db.query(ExternalFinding)
            .filter(
                ExternalFinding.asset_id == asset_id,
                ExternalFinding.organization_id == org_id,
                ExternalFinding.status == "open",
            )
            .order_by(ExternalFinding.cvss_score.desc().nullslast())
            .limit(8)
            .all()
        )
        if ext_rows:
            lines.append("HALLAZGOS EXTERNOS / CVEs EN EL ACTIVO (escaner de seguridad / NVD):")
            for f in ext_rows:
                sev = (f.severity or "?").upper()
                cve_txt = f" | CVE: {f.cve_id}" if f.cve_id else ""
                cvss_txt = f" | CVSS: {f.cvss_score:.1f}" if f.cvss_score is not None else ""
                iso_txt = f" | Control ISO: {f.iso_control}" if f.iso_control else ""
                lines.append(f"  [{sev}] {f.title}{cve_txt}{cvss_txt}{iso_txt}")
                if f.description:
                    lines.append(f"    {f.description[:120]}")
            lines.append("")

    # 3. Regwatch: controles del riesgo que requieren revision normativa
    if impl_ids:
        impl_with_regwatch = (
            db.query(ControlImplementation)
            .filter(
                ControlImplementation.id.in_(impl_ids),
                ControlImplementation.regwatch_pack_id.isnot(None),
            )
            .all()
        )
        if impl_with_regwatch:
            pack_ids = list({c.regwatch_pack_id for c in impl_with_regwatch})
            packs = {p.id: p for p in db.query(ChangePack).filter(ChangePack.id.in_(pack_ids)).all()}
            lines.append("CAMBIOS NORMATIVOS (regwatch) QUE AFECTAN A CONTROLES DE ESTE RIESGO:")
            for impl in impl_with_regwatch:
                pack = packs.get(impl.regwatch_pack_id)
                if not pack:
                    continue
                lines.append(
                    f"  Control [{impl.name}] flaggeado por cambio [{pack.framework_code}] "
                    f"— {pack.title_es} (severidad: {pack.severity.value if pack.severity else '?'})"
                )
                if pack.description_es:
                    lines.append(f"    Impacto: {pack.description_es[:150]}")
            lines.append(
                "  IMPORTANTE: estos controles pueden estar desactualizados respecto "
                "a la normativa vigente. Considera su madurez declarada como provisional."
            )
            lines.append("")

    if not lines:
        return "Sin hallazgos activos de OSINT, CVE ni cambios normativos pendientes para este riesgo."

    return "\n".join(lines)


# ── Builder compartido de contexto por activo ────────────────────────────────
# Una sola fuente de verdad para el contexto que consumen la generacion de
# riesgos por activo (individual y batch) y suggest-controls: perfil del
# activo, criterios de calibracion, vigilancia (CVE/OSINT/Regwatch),
# contexto normativo, incidentes historicos y documentacion RAG.

def _asset_incident_history(db, asset, limit: int = 5) -> str:
    """Incidentes recientes de la org que afectaron a este activo."""
    try:
        from app.models import Incident
        rows = (
            db.query(Incident)
            .filter(Incident.organization_id == asset.organization_id)
            .order_by(Incident.id.desc())
            .limit(50)
            .all()
        )
        hits = []
        for inc in rows:
            affected = inc.affected_asset_ids or []
            if isinstance(affected, list) and asset.id in affected:
                sev = inc.severity.value if getattr(inc, "severity", None) else "?"
                when = inc.detected_at.strftime("%Y-%m-%d") if getattr(inc, "detected_at", None) else ""
                hits.append(f"  [{sev}] {inc.title} {when}".rstrip())
            if len(hits) >= limit:
                break
        if not hits:
            return ""
        return "\n".join(hits)
    except Exception:
        return ""


def build_asset_risk_context(db, asset, impls: list | None = None,
                             vuln_ids: list[int] | None = None) -> dict:
    """Ensambla las secciones de contexto para analizar los riesgos de un activo.

    Devuelve un dict de secciones de texto listas para insertar en prompts:
      profile, calibration, vigilancia, normative, incidents, rag
    Las secciones vacias vienen como cadena vacia — el llamador decide si
    imprime el encabezado.
    """
    from app.models import RiskContext

    asset_type = asset.asset_type.value if asset.asset_type else ""
    profile = get_asset_profile(asset_type)
    profile_txt = (
        f"Tipo: {profile['label']} | Dimensiones primarias: "
        f"{', '.join(profile['primary_dimensions'])}\n"
        f"Factores de riesgo tipicos: {profile['key_risk_factors']}"
    )

    calibration_txt = (
        "LIKELIHOOD (calibrar contra estos criterios):\n"
        + "\n".join(f"  {k}: {v}" for k, v in LIKELIHOOD_CRITERIA.items())
        + "\nCONSEQUENCE (coherente con el valor CIA del activo en la dimension atacada):\n"
        + "\n".join(f"  {k}: {v}" for k, v in CONSEQUENCE_CRITERIA.items())
    )

    impl_ids = [c.id for c in (impls or [])]
    vigilancia_txt = build_vigilancia_context(
        db, asset.id, vuln_ids or [], impl_ids, asset.organization_id)

    ctx = db.query(RiskContext).filter_by(organization_id=asset.organization_id).first()
    frameworks = (ctx.active_frameworks or []) if ctx else []
    normative_txt = normative_context(frameworks)

    incidents_txt = _asset_incident_history(db, asset)

    rag_txt = ""
    try:
        from app.services.rag_service import search_chunks_with_source
        query = " ".join(filter(None, [
            asset.name, asset.category, asset.business_process,
            "seguridad control procedimiento",
        ]))[:200]
        chunks = search_chunks_with_source(
            db, query, top_k=5, organization_id=asset.organization_id)
        if chunks:
            rag_txt = "\n".join(
                f"  [{c.get('doc_name', '')}] {c.get('content', '')[:200]}"
                for c in chunks
            )
    except Exception:
        pass

    # Lecciones aprendidas de las decisiones reales de la organizacion
    lessons_txt = ""
    try:
        from app.services.ai_learning_service import lessons_block
        lessons_txt = lessons_block(
            db, asset.organization_id,
            kinds=("risk_acceptance", "risk_escalation", "likelihood_calibration",
                   "consequence_calibration", "threat_rejection",
                   "residual_calibration"),
        )
    except Exception:
        pass

    return {
        "profile": profile_txt,
        "calibration": calibration_txt,
        "vigilancia": vigilancia_txt,
        "normative": normative_txt,
        "incidents": incidents_txt,
        "rag": rag_txt,
        "lessons": lessons_txt,
    }


def render_asset_risk_context(sections: dict) -> str:
    """Serializa las secciones del builder como bloque de prompt."""
    parts = [
        "# PERFIL DEL ACTIVO\n" + sections["profile"],
        "# CRITERIOS DE CALIBRACION ISO 27005\n" + sections["calibration"],
        "# EVIDENCIA REAL DE VIGILANCIA (OSINT / CVE / REGWATCH)\n" + sections["vigilancia"],
        "# CONTEXTO NORMATIVO\n" + sections["normative"],
    ]
    if sections.get("incidents"):
        parts.append("# INCIDENTES PREVIOS EN ESTE ACTIVO\n" + sections["incidents"])
    if sections.get("rag"):
        parts.append("# DOCUMENTACION INTERNA RELEVANTE (actas, evidencias, procedimientos)\n"
                     + sections["rag"])
    if sections.get("lessons"):
        parts.append("# " + sections["lessons"])
    return "\n\n".join(parts)


# ── Criterios ISO 27005 para calibrar niveles ─────────────────────────────────

LIKELIHOOD_CRITERIA = {
    0: "Muy rara — ocurre menos de 1 vez en 10 anos. Solo en circunstancias extraordinarias.",
    1: "Rara — podria ocurrir en los proximos 5 anos. Casos aislados conocidos en el sector.",
    2: "Posible — podria ocurrir en los proximos 2 anos. Casos conocidos en organizaciones similares.",
    3: "Probable — podria ocurrir en el proximo ano. Incidentes frecuentes en el sector.",
    4: "Casi cierta — es probable que ocurra en los proximos meses o ya ha ocurrido.",
}

CONSEQUENCE_CRITERIA = {
    0: "Insignificante — impacto despreciable, sin efecto apreciable en el negocio.",
    1: "Menor — impacto leve, gestionable con recursos normales. Recuperacion en horas.",
    2: "Moderado — impacto significativo. Requiere atencion especial. Recuperacion en dias.",
    3: "Mayor — impacto grave en operaciones, reputacion o datos. Recuperacion en semanas.",
    4: "Catastrofico — amenaza la supervivencia del negocio, perdida masiva de datos o responsabilidad legal grave.",
}
