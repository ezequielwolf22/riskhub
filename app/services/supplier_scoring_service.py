"""Scoring continuo de proveedores mediante OSINT y datos internos.

Actualiza automáticamente el score de riesgo de cada proveedor basándose en:
- Hallazgos OSINT (breaches, reputación, certificados)
- Datos del cuestionario de seguridad
- Certificaciones declaradas
- Antigüedad de la última evaluación
- Incidentes relacionados
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Supplier, SupplierRisk

logger = logging.getLogger("riskhub.supplier_scoring")


def _score_from_certifications(certifications: list) -> int:
    """Score por certificaciones declaradas (0-30 puntos)."""
    certs = [c.lower() for c in (certifications or [])]
    score = 0
    cert_values = {
        "iso27001": 10, "iso 27001": 10,
        "soc2": 8, "soc 2": 8, "soc type 2": 8,
        "iso27017": 5, "iso27018": 5,
        "pci dss": 5, "hipaa": 5,
        "ens": 7, "ccn-cert": 7,
        "csa star": 5,
        "iso9001": 2, "gdpr": 2,
    }
    for cert_key, value in cert_values.items():
        if any(cert_key in c for c in certs):
            score += value
    return min(30, score)


def _score_from_assessment_recency(last_assessment_at: Optional[datetime]) -> int:
    """Score por recencia de la evaluación (0-20 puntos)."""
    if not last_assessment_at:
        return 0
    now = datetime.now(timezone.utc)
    la = last_assessment_at.replace(tzinfo=timezone.utc) if last_assessment_at.tzinfo is None else last_assessment_at
    days_ago = (now - la).days
    if days_ago <= 180:
        return 20
    if days_ago <= 365:
        return 15
    if days_ago <= 730:
        return 8
    return 2


def _score_from_questionnaire(db: Session, supplier_id: int) -> int:
    """Score derivado del cuestionario de seguridad (0-30 puntos)."""
    from app.models import SupplierQuestionnaire
    # El modelo usa submitted_at para saber si está completado (no tiene campo status)
    q = db.query(SupplierQuestionnaire).filter(
        SupplierQuestionnaire.supplier_id == supplier_id,
        SupplierQuestionnaire.submitted_at.isnot(None),
    ).order_by(SupplierQuestionnaire.submitted_at.desc()).first()
    if not q:
        return 0
    raw_score = q.score or 0  # 0-100
    return int(raw_score * 0.30)  # hasta 30 puntos


def _score_from_osint(db: Session, supplier: Supplier) -> int:
    """Score derivado de OSINT sobre el dominio/email del proveedor (0-20 puntos).

    Penaliza hallazgos negativos encontrados en scans OSINT.
    """
    from app.models import OSINTFinding, OSINTFindingRiskLevel
    score = 20  # Empieza bien, resta por hallazgos

    # Buscar hallazgos de OSINT relacionados con el proveedor
    email = supplier.contact_email or ""
    name = supplier.name or ""
    domain = ""
    if "@" in email:
        domain = email.split("@")[1]

    if not domain and not name:
        return 15  # Score neutro si no hay datos

    findings = db.query(OSINTFinding).filter(
        OSINTFinding.organization_id == supplier.organization_id,
    ).all()

    for f in findings:
        source = (f.source_name or "").lower()
        # Verificar si el hallazgo relaciona con este proveedor
        data_str = str(f.raw_data or "").lower()
        if domain and domain.lower() not in data_str:
            if name.lower() not in data_str:
                continue
        # Penalizar según severity
        risk_lvl = f.risk_level
        if risk_lvl == OSINTFindingRiskLevel.CRITICAL:
            score -= 8
        elif risk_lvl == OSINTFindingRiskLevel.HIGH:
            score -= 5
        elif risk_lvl == OSINTFindingRiskLevel.MEDIUM:
            score -= 2

    return max(0, score)


def _score_from_incidents(db: Session, supplier: Supplier) -> int:
    """Penaliza si hay incidentes relacionados con el proveedor (0-10 puntos base)."""
    from app.models import Incident, IncidentSeverity
    score = 10
    # Buscar incidentes que mencionen al proveedor
    name_lower = (supplier.name or "").lower()
    incidents = db.query(Incident).filter(
        Incident.organization_id == supplier.organization_id,
    ).all()
    for inc in incidents:
        desc = ((inc.description or "") + " " + (inc.title or "")).lower()
        if name_lower and name_lower[:10] in desc:
            if inc.severity == IncidentSeverity.P1:
                score -= 5
            elif inc.severity == IncidentSeverity.P2:
                score -= 3
            elif inc.severity == IncidentSeverity.P3:
                score -= 1
    return max(0, score)


def calculate_supplier_score(db: Session, supplier: Supplier) -> int:
    """Calcula score de riesgo del proveedor (0-100, mayor = mejor).

    Componentes:
    - Certificaciones: 0-30 pts
    - Recencia de evaluación: 0-20 pts
    - Cuestionario: 0-30 pts
    - OSINT limpio: 0-20 pts
    Penalizaciones:
    - Incidentes relacionados: hasta -10 pts
    """
    cert_score = _score_from_certifications(supplier.certifications)
    recency_score = _score_from_assessment_recency(supplier.last_assessment_at)
    questionnaire_score = _score_from_questionnaire(db, supplier.id)
    osint_score = _score_from_osint(db, supplier)
    # _score_from_incidents devuelve puntuación 0-10 (10=sin incidentes, 0=muchos graves)
    # La penalización es lo que se RESTA: 10 - score_incidents
    # Ejemplo: sin incidentes → score=10, penalty=0 → sin penalización
    # Ejemplo: P1 incident → score=5, penalty=5 → se restan 5 puntos del total
    incident_score = _score_from_incidents(db, supplier)   # 0-10, mayor=mejor
    incident_penalty = 10 - incident_score                 # 0-10, mayor=peor

    total = cert_score + recency_score + questionnaire_score + osint_score - incident_penalty
    return max(0, min(100, total))


def _score_to_risk_level(score: int) -> SupplierRisk:
    if score >= 70:
        return SupplierRisk.LOW
    if score >= 40:
        return SupplierRisk.MEDIUM
    return SupplierRisk.HIGH


def update_all_supplier_scores(db: Session, org_id: int) -> dict:
    """Actualiza scores de todos los proveedores de una org.

    Retorna: {updated, high_risk, medium_risk, low_risk}
    """
    suppliers = db.query(Supplier).filter(Supplier.organization_id == org_id).all()
    stats = {"updated": 0, "high_risk": 0, "medium_risk": 0, "low_risk": 0}

    for s in suppliers:
        old_score = s.score or 0
        new_score = calculate_supplier_score(db, s)
        new_level = _score_to_risk_level(new_score)

        # Solo actualizar si cambia
        if abs(new_score - old_score) >= 2 or s.risk_level != new_level:
            s.score = new_score
            s.risk_level = new_level
            stats["updated"] += 1

        if new_level == SupplierRisk.HIGH:
            stats["high_risk"] += 1
        elif new_level == SupplierRisk.MEDIUM:
            stats["medium_risk"] += 1
        else:
            stats["low_risk"] += 1

    if stats["updated"] > 0:
        try:
            db.commit()
            logger.info(
                "Supplier scoring org=%d: %d actualizados (H=%d M=%d L=%d)",
                org_id, stats["updated"],
                stats["high_risk"], stats["medium_risk"], stats["low_risk"]
            )
        except Exception as exc:
            db.rollback()
            logger.exception("Error actualizando scores de proveedores: %s", exc)

    return stats
