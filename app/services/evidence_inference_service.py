"""Inferencia automática de cumplimiento desde documentos analizados.

Cuando el ISMS analiza un documento y extrae controls_covered (ISO 27002),
este servicio:
1. Carga el cross-map control → requisitos de frameworks
2. Marca automáticamente los requisitos de compliance como PARTIAL/IMPLEMENTED
3. Crea Evidence records vinculadas a cada requisito cubierto
4. Detecta qué frameworks se benefician de un mismo control (cross-mapping)
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    ComplianceFrameworkStatus, ComplianceRequirementStatus,
    Evidence, EvidenceType, RiskContext, AiDocument,
)

logger = logging.getLogger("riskhub.evidence_inference")

_CROSSMAP_PATH = Path(__file__).parent.parent / "data" / "frameworks" / "control_crossmap.json"
_CROSSMAP: Optional[dict] = None


def _load_crossmap() -> dict:
    global _CROSSMAP
    if _CROSSMAP is None:
        try:
            _CROSSMAP = json.loads(_CROSSMAP_PATH.read_text(encoding="utf-8"))
        except Exception:
            _CROSSMAP = {}
    return _CROSSMAP


def _next_evidence_code(db: Session, org_id: int) -> str:
    from app.models import Evidence
    count = db.query(Evidence).filter(Evidence.organization_id == org_id).count()
    code = f"EVD-{count + 1:04d}"
    while db.query(Evidence).filter_by(code=code).first():
        count += 1
        code = f"EVD-{count + 1:04d}"
    return code


def infer_compliance_from_document(
    db: Session,
    doc: AiDocument,
    controls_covered: list[dict],
    org_id: int,
) -> dict:
    """Infiere cumplimiento de frameworks desde controles cubiertos por un documento.

    Args:
        db: Session
        doc: Documento analizado
        controls_covered: Lista de {code, coverage, maturity_current} de la IA
        org_id: Organización

    Returns:
        {requirements_updated, evidence_created, frameworks_affected}
    """
    crossmap = _load_crossmap()
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    active_frameworks = (ctx.active_frameworks or []) if ctx else []

    if not active_frameworks:
        logger.debug("No hay frameworks activos para org %d, saltando inferencia", org_id)
        return {"requirements_updated": 0, "evidence_created": 0, "frameworks_affected": []}

    requirements_updated = 0
    evidence_created = 0
    frameworks_affected = set()

    for control in controls_covered:
        control_code = control.get("code", "").strip()
        coverage = control.get("coverage", "partial")
        maturity = control.get("maturity_current", 2)

        # Determinar status según coverage y maturity
        if coverage == "full" and maturity >= 4:
            new_status = ComplianceRequirementStatus.IMPLEMENTED
            completion = 90
        elif coverage == "full" or maturity >= 3:
            new_status = ComplianceRequirementStatus.PARTIAL
            completion = 60
        else:
            new_status = ComplianceRequirementStatus.PARTIAL
            completion = 40

        # Buscar en cross-map qué requisitos cubre este control
        mapped = crossmap.get(control_code, [])
        for mapping in mapped:
            fw_code = mapping.get("f", "")
            req_id = mapping.get("r", "")

            if fw_code not in active_frameworks:
                continue

            frameworks_affected.add(fw_code)

            # Buscar o crear el registro de compliance
            req_status = db.query(ComplianceFrameworkStatus).filter(
                ComplianceFrameworkStatus.organization_id == org_id,
                ComplianceFrameworkStatus.framework_code == fw_code,
                ComplianceFrameworkStatus.requirement_id == req_id,
            ).first()

            if not req_status:
                req_status = ComplianceFrameworkStatus(
                    organization_id=org_id,
                    framework_code=fw_code,
                    requirement_id=req_id,
                    status=new_status,
                    completion_pct=completion,
                )
                db.add(req_status)
            else:
                # Solo actualizar si mejora el estado actual
                current_order = [
                    ComplianceRequirementStatus.NOT_APPLICABLE,
                    ComplianceRequirementStatus.PLANNED,
                    ComplianceRequirementStatus.PARTIAL,
                    ComplianceRequirementStatus.IMPLEMENTED,
                    ComplianceRequirementStatus.AUDITED,
                ]
                try:
                    current_idx = current_order.index(req_status.status)
                    new_idx = current_order.index(new_status)
                    if new_idx > current_idx:
                        req_status.status = new_status
                        req_status.completion_pct = max(req_status.completion_pct or 0, completion)
                    elif new_idx == current_idx:
                        req_status.completion_pct = max(req_status.completion_pct or 0, completion)
                except ValueError:
                    req_status.status = new_status
                    req_status.completion_pct = completion

            req_status.last_reviewed_at = datetime.now(timezone.utc)
            req_status.evidence_count = (req_status.evidence_count or 0) + 1
            requirements_updated += 1

            # Crear Evidence record vinculada a este requisito (si no existe ya para este doc)
            existing_ev = db.query(Evidence).filter(
                Evidence.organization_id == org_id,
                Evidence.compliance_framework == fw_code,
                Evidence.compliance_requirement == req_id,
                Evidence.title.contains(doc.original_name[:40] if doc.original_name else ""),
                Evidence.is_current == True,
            ).first()

            if not existing_ev:
                ev = Evidence(
                    organization_id=org_id,
                    code=_next_evidence_code(db, org_id),
                    title=f"{doc.original_name or 'Documento'} → {fw_code.upper()} {req_id}",
                    description=(
                        f"Evidencia inferida automáticamente. "
                        f"El documento '{doc.original_name}' cubre el control ISO 27002 {control_code} "
                        f"({coverage}) con madurez {maturity}/5, "
                        f"que satisface el requisito {req_id} del framework {fw_code.upper()}."
                    ),
                    evidence_type=EvidenceType.POLICY if doc.category == "policy" else EvidenceType.PROCEDURE,
                    compliance_framework=fw_code,
                    compliance_requirement=req_id,
                    created_by_id=None,
                    version=1,
                    is_current=True,
                )
                db.add(ev)
                db.flush()
                evidence_created += 1

    try:
        db.commit()
        logger.info(
            "Evidence inference org=%d doc=%d: %d reqs, %d evidencias, frameworks=%s",
            org_id, doc.id, requirements_updated, evidence_created,
            list(frameworks_affected)
        )
    except Exception as exc:
        logger.exception("Error en evidence inference: %s", exc)
        db.rollback()
        return {"requirements_updated": 0, "evidence_created": 0, "frameworks_affected": []}

    return {
        "requirements_updated": requirements_updated,
        "evidence_created": evidence_created,
        "frameworks_affected": sorted(frameworks_affected),
    }


def reconcile_document_compliance(
    db: Session,
    doc_id: int,
    old_controls: list[str],
    new_controls: list[str],
    org_id: int,
) -> dict:
    """Detecta cambios de cobertura al actualizar un documento.

    Compara controles anteriores vs nuevos y alerta si alguno se perdió.
    Returns: {added, removed, unchanged}
    """
    crossmap = _load_crossmap()

    def _get_reqs(controls: list[str]) -> set[str]:
        reqs = set()
        for c in controls:
            for m in crossmap.get(c, []):
                reqs.add(f"{m['f']}/{m['r']}")
        return reqs

    old_reqs = _get_reqs(old_controls)
    new_reqs = _get_reqs(new_controls)

    added = sorted(new_reqs - old_reqs)
    removed = sorted(old_reqs - new_reqs)
    unchanged = sorted(old_reqs & new_reqs)

    if removed:
        logger.warning(
            "Documento %d perdió cobertura de %d requisitos: %s",
            doc_id, len(removed), removed[:5]
        )

    return {
        "added": added,
        "removed": removed,
        "unchanged": unchanged,
        "coverage_change": len(added) - len(removed),
    }
