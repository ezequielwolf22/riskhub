"""Servicio BCP/ISO 22301 — lógica de negocio para continuidad."""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("riskhub.bcp_service")

# Campos requeridos para considerar el BIA completo
BIA_REQUIRED_FIELDS = [
    "rto_hours", "rpo_hours", "mtpd_hours", "mbco",
    "financial_impact", "reputational_impact", "legal_impact", "operational_impact",
    "activation_criteria", "vital_records",
]

# Cláusulas ISO 22301 con su check correspondiente
_ISO22301_CLAUSES = [
    {"clause": "4.1", "name": "Comprensión del contexto organizacional", "check": "context"},
    {"clause": "4.2", "name": "Partes interesadas y requisitos", "check": "context"},
    {"clause": "6.1", "name": "Valoración de riesgos y oportunidades", "check": "risks"},
    {"clause": "8.2", "name": "Análisis de Impacto en el Negocio (BIA)", "check": "bia"},
    {"clause": "8.3", "name": "Estrategias de continuidad de negocio", "check": "strategies"},
    {"clause": "8.4", "name": "Planes y procedimientos de continuidad", "check": "plans"},
    {"clause": "8.5", "name": "Programa de ejercicios y pruebas", "check": "tests"},
    {"clause": "9.1", "name": "Seguimiento, medición y análisis", "check": "dashboard"},
    {"clause": "10.1", "name": "No conformidades y acciones correctivas", "check": "nc"},
]

VALID_PLAN_TYPES = ("bcp", "drp", "crp", "ems", "pandemic", "cyber_response", "supply_chain")

_BCP_KEYWORDS = [
    "bcp", "drp", "continuidad", "continuity", "disaster recovery",
    "business continuity", "recuperación", "recovery plan", "contingencia",
    "rto", "rpo", "mtpd", "iso 22301", "iso22301", "plan de continuidad",
]


def bia_completeness(db, process) -> dict:
    """Calcula el porcentaje de completitud del BIA para un proceso."""
    missing = [f for f in BIA_REQUIRED_FIELDS if not getattr(process, f, None)]
    total = len(BIA_REQUIRED_FIELDS)
    pct = int((total - len(missing)) / total * 100)
    return {"pct": pct, "missing": missing, "total": total}


def iso22301_status(db: Session, org_id: int) -> list:
    """Devuelve el estado de cumplimiento por cláusula ISO 22301."""
    from app.models import BusinessProcess, BCPPlan, BCPStrategy, BCPTest

    procs = db.query(BusinessProcess).filter_by(organization_id=org_id).all()
    plans = db.query(BCPPlan).filter_by(organization_id=org_id).all()
    strategies = db.query(BCPStrategy).filter_by(organization_id=org_id).all()
    tests = db.query(BCPTest).filter_by(organization_id=org_id).all()

    results = []
    for clause in _ISO22301_CLAUSES:
        check = clause["check"]
        try:
            if check == "context":
                status = "ok"
            elif check == "risks":
                from app.models import Risk
                count = db.query(Risk).filter_by(organization_id=org_id).count()
                status = "ok" if count > 0 else "gap"
            elif check == "bia":
                critical = [p for p in procs if p.criticality in ("critical", "high")]
                if not critical:
                    status = "gap"
                else:
                    completed = sum(1 for p in critical if bia_completeness(db, p)["pct"] >= 80)
                    ratio = completed / len(critical)
                    status = "ok" if ratio >= 0.8 else ("partial" if ratio > 0 else "gap")
            elif check == "strategies":
                status = "ok" if strategies else "gap"
            elif check == "plans":
                approved = [p for p in plans if p.status == "approved"]
                status = "ok" if approved else ("partial" if plans else "gap")
            elif check == "tests":
                done = [t for t in tests if t.conducted_at]
                status = "ok" if done else ("partial" if tests else "gap")
            elif check == "dashboard":
                status = "ok" if procs else "gap"
            elif check == "nc":
                status = "ok"  # 0 NCs es válido
            else:
                status = "gap"
        except Exception:
            status = "gap"

        results.append({
            "clause": clause["clause"],
            "name": clause["name"],
            "status": status,
        })
    return results


def detect_bcp_document(filename: str, summary: str) -> bool:
    """Detecta si un documento es BCP/DRP relacionado por nombre o resumen."""
    text = (filename + " " + summary).lower()
    return any(kw in text for kw in _BCP_KEYWORDS)


def suggest_plan_type_from_doc(filename: str, summary: str) -> str:
    """Sugiere el tipo de plan BCP a partir del nombre y resumen del documento."""
    text = (filename + " " + summary).lower()
    if "disaster recovery" in text or " drp" in text or "recuperación de desastres" in text:
        return "drp"
    if "cyber" in text:
        return "cyber_response"
    if "pandemic" in text or "pandemia" in text:
        return "pandemic"
    if "supply chain" in text or "cadena de suministro" in text:
        return "supply_chain"
    return "bcp"


def next_plan_code(db: Session, org_id: int, plan_type: str) -> str:
    """Genera el siguiente código secuencial para un plan BCP."""
    from app.models import BCPPlan
    count = db.query(BCPPlan).filter_by(organization_id=org_id).count()
    prefix = plan_type.upper()[:3]
    return f"{prefix}-{count + 1:04d}"


# ── Integraciones automáticas ──────────────────────────────────────────────────

def suggest_bcp_for_asset(db: Session, asset_id: int) -> None:
    """Si un activo crítico no está vinculado a ningún proceso BCP, crea uno draft.

    ISO 22301 cl. 8.2 — identificación de actividades críticas.
    """
    from app.models import Asset, BusinessProcess
    asset = db.get(Asset, asset_id)
    if not asset:
        return
    value = max(
        getattr(asset, "value_confidentiality", 0) or 0,
        getattr(asset, "value_availability", 0) or 0,
    )
    if value < 3:
        return
    org_id = asset.organization_id
    existing = db.query(BusinessProcess).filter(
        BusinessProcess.organization_id == org_id,
        BusinessProcess.asset_ids.contains(str(asset_id)),
    ).first()
    if existing:
        return
    p = BusinessProcess(
        organization_id=org_id,
        name=f"[Auto] Proceso dependiente de: {asset.name}",
        description=(
            f"Proceso auto-sugerido. El activo '{asset.name}' tiene valor alto "
            f"y no está vinculado a ningún plan de continuidad. Revisar y completar BIA."
        ),
        criticality="high",
        asset_ids=[asset_id],
    )
    db.add(p)
    logger.info("BCP process auto-suggested for critical asset %d (%s)", asset_id, asset.name)


def check_bcp_coverage_for_risk(db: Session, risk, org_id: int) -> None:
    """Si un riesgo crítico no tiene proceso BCP cubriendo su activo, sugiere uno.

    ISO 22301 cl. 8.2 — impacto de riesgos en continuidad.
    """
    from app.models import BusinessProcess
    if getattr(risk, "residual_level", 0) < 6:
        return
    if not risk.asset_id:
        return
    covering = db.query(BusinessProcess).filter(
        BusinessProcess.organization_id == org_id,
        BusinessProcess.asset_ids.contains(str(risk.asset_id)),
    ).first()
    if covering:
        return
    suggest_bcp_for_asset(db, risk.asset_id)


def check_incident_bcp_activation(db: Session, incident, org_id: int) -> None:
    """Si un incidente P1/P2 afecta activos de un proceso BCP crítico, anota alerta.

    ISO 22301 cl. 8.4 — activación de planes de continuidad.
    GDPR: solo escribe metadatos de eventos, sin PII externa de empleados.
    """
    from app.models import BusinessProcess
    try:
        from app.models import IncidentSeverity
        severity = getattr(incident, "severity", None)
        if severity not in (IncidentSeverity.P1, IncidentSeverity.P2):
            return
    except (ImportError, AttributeError):
        return

    critical_procs = db.query(BusinessProcess).filter(
        BusinessProcess.organization_id == org_id,
        BusinessProcess.criticality.in_(["critical", "high"]),
    ).all()
    now = datetime.now(timezone.utc)
    changed = False
    for proc in critical_procs:
        affected = incident.affected_asset_ids or []
        proc_assets = proc.asset_ids or []
        overlap = set(str(a) for a in affected) & set(str(a) for a in proc_assets)
        if not overlap:
            continue
        contacts = list(proc.escalation_contacts or [])
        contacts.append({
            "type": "bcp_activation_alert",
            "incident_id": incident.id,
            "incident_code": getattr(incident, "code", str(incident.id)),
            "severity": str(getattr(severity, "value", severity)),
            "detected_at": now.isoformat(),
            "note": (
                f"Incidente {getattr(incident, 'code', incident.id)} podría requerir "
                f"activación del plan de continuidad. Revisar criterios de activación."
            ),
        })
        proc.escalation_contacts = contacts
        changed = True
        logger.warning(
            "BCP activation candidate: process '%s' may be triggered by incident %s",
            proc.name, incident.id,
        )
    if changed:
        db.commit()


def flag_bcp_process_for_cve(db: Session, asset_id: int, cve_id: str, org_id: int) -> None:
    """Cuando un CVE afecta un activo de un proceso BCP crítico, anota revisión necesaria.

    ISO 22301 cl. 8.3 — revisión de estrategias ante nuevas amenazas.
    """
    from app.models import BusinessProcess
    affected_procs = db.query(BusinessProcess).filter(
        BusinessProcess.organization_id == org_id,
        BusinessProcess.criticality.in_(["critical", "high"]),
        BusinessProcess.asset_ids.contains(str(asset_id)),
    ).all()
    for proc in affected_procs:
        vital = list(proc.vital_records or [])
        vital.append({
            "type": "cve_alert",
            "cve_id": cve_id,
            "asset_id": asset_id,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "note": f"CVE {cve_id} afecta activo dependiente. Revisar BIA y estrategias.",
        })
        proc.vital_records = vital
    if affected_procs:
        db.commit()
        logger.info("BCP: %d proceso(s) flaggeado(s) por CVE %s", len(affected_procs), cve_id)
