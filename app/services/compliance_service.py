"""Servicio de cumplimiento normativo multi-framework."""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    ComplianceFrameworkStatus, ComplianceRequirementStatus,
    RiskContext, Evidence, User, ControlImplementation, ControlStatus,
)

logger = logging.getLogger("riskhub.compliance")

_FRAMEWORKS_DIR = Path(__file__).parent.parent / "data" / "frameworks"

# A9: cache con TTL para detectar cambios en archivos JSON sin reiniciar la app
_CACHE: dict = {}
_CACHE_TS: dict = {}
_CACHE_TTL = 300  # 5 minutos


def load_framework(code: str) -> Optional[dict]:
    """Carga definicion de framework desde JSON con TTL de cache."""
    now = time.time()
    if code in _CACHE and (now - _CACHE_TS.get(code, 0)) < _CACHE_TTL:
        return _CACHE[code]
    path = _FRAMEWORKS_DIR / f"{code}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    _CACHE[code] = data
    _CACHE_TS[code] = now
    return data


def list_available_frameworks() -> list[dict]:
    """Lista todos los frameworks disponibles con metadata."""
    result = []
    for path in _FRAMEWORKS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            result.append({
                "code": data["code"],
                "name": data["name"],
                "version": data.get("version", ""),
                "description": data.get("description", ""),
                "requirements_count": len(data.get("requirements", [])),
                "audit_frequency_months": data.get("audit_frequency_months", 12),
            })
        except Exception:
            pass
    return sorted(result, key=lambda x: x["code"])


def initialize_org_framework(db: Session, org_id: int, framework_code: str) -> int:
    """Inicializa los requisitos de un framework para una org.

    Crea registros ComplianceFrameworkStatus para cada requisito si no existen.
    Retorna número de registros creados.
    """
    framework = load_framework(framework_code)
    if not framework:
        logger.warning("Framework %s no encontrado", framework_code)
        return 0

    created = 0
    for req in framework.get("requirements", []):
        existing = db.query(ComplianceFrameworkStatus).filter(
            ComplianceFrameworkStatus.organization_id == org_id,
            ComplianceFrameworkStatus.framework_code == framework_code,
            ComplianceFrameworkStatus.requirement_id == req["id"],
        ).first()
        if not existing:
            obj = ComplianceFrameworkStatus(
                organization_id=org_id,
                framework_code=framework_code,
                requirement_id=req["id"],
                status=ComplianceRequirementStatus.PLANNED,
                completion_pct=0,
            )
            db.add(obj)
            created += 1

    try:
        db.commit()
        logger.info("Inicializado framework %s para org %d: %d requisitos", framework_code, org_id, created)
    except Exception as exc:
        db.rollback()
        logger.exception("Error inicializando framework %s: %s", framework_code, exc)
        return 0

    return created


def get_framework_compliance_status(db: Session, org_id: int, framework_code: str) -> dict:
    """Calcula el estado de cumplimiento de un framework para una org.

    Retorna: {framework, completion_pct, status_breakdown, domains, requirements, gaps}
    """
    framework = load_framework(framework_code)
    if not framework:
        return {"error": "Framework no encontrado"}

    # A8: evitar side-effect en GET — solo inicializar si aun no hay registros
    existing_count = db.query(ComplianceFrameworkStatus).filter(
        ComplianceFrameworkStatus.organization_id == org_id,
        ComplianceFrameworkStatus.framework_code == framework_code,
    ).count()
    if existing_count == 0:
        initialize_org_framework(db, org_id, framework_code)

    statuses = db.query(ComplianceFrameworkStatus).filter(
        ComplianceFrameworkStatus.organization_id == org_id,
        ComplianceFrameworkStatus.framework_code == framework_code,
    ).all()

    status_map = {s.requirement_id: s for s in statuses}

    # Calcular completeness
    requirements = framework.get("requirements", [])
    mandatory_reqs = [r for r in requirements if r.get("mandatory", True)]

    total = len(requirements)
    mandatory_total = len(mandatory_reqs)
    implemented = sum(
        1 for r in requirements
        if status_map.get(r["id"]) and
        status_map[r["id"]].status in [
            ComplianceRequirementStatus.IMPLEMENTED,
            ComplianceRequirementStatus.AUDITED
        ]
    )
    mandatory_implemented = sum(
        1 for r in mandatory_reqs
        if status_map.get(r["id"]) and
        status_map[r["id"]].status in [
            ComplianceRequirementStatus.IMPLEMENTED,
            ComplianceRequirementStatus.AUDITED
        ]
    )

    overall_pct = int((implemented / total * 100) if total > 0 else 0)
    mandatory_pct = int((mandatory_implemented / mandatory_total * 100) if mandatory_total > 0 else 0)

    # Breakdown por status
    status_breakdown: dict[str, int] = {}
    for s in statuses:
        key = s.status.value if hasattr(s.status, "value") else str(s.status)
        status_breakdown[key] = status_breakdown.get(key, 0) + 1

    # Gaps: requisitos mandatorios no implementados
    gaps = []
    for r in mandatory_reqs:
        s = status_map.get(r["id"])
        if not s or s.status not in [
            ComplianceRequirementStatus.IMPLEMENTED,
            ComplianceRequirementStatus.AUDITED
        ]:
            gaps.append({
                "id": r["id"],
                "name": r["name"],
                "domain": r.get("domain", ""),
                "status": s.status.value if s else "not_started",
                "completion_pct": s.completion_pct if s else 0,
            })

    # Agrupar por dominio
    domain_stats: dict[str, dict] = {}
    for r in requirements:
        domain = r.get("domain", "General")
        if domain not in domain_stats:
            domain_stats[domain] = {"total": 0, "implemented": 0}
        domain_stats[domain]["total"] += 1
        s = status_map.get(r["id"])
        if s and s.status in [
            ComplianceRequirementStatus.IMPLEMENTED,
            ComplianceRequirementStatus.AUDITED
        ]:
            domain_stats[domain]["implemented"] += 1

    domains = [
        {
            "domain": d,
            "total": v["total"],
            "implemented": v["implemented"],
            "pct": int(v["implemented"] / v["total"] * 100) if v["total"] > 0 else 0,
        }
        for d, v in domain_stats.items()
    ]

    return {
        "framework_code": framework_code,
        "framework_name": framework["name"],
        "total_requirements": total,
        "mandatory_requirements": mandatory_total,
        "overall_pct": overall_pct,
        "mandatory_pct": mandatory_pct,
        "status_breakdown": status_breakdown,
        "domains": sorted(domains, key=lambda x: x["pct"]),
        "gaps": gaps[:20],  # Top 20 gaps
        "is_audit_ready": mandatory_pct >= 85,
    }


def get_multi_framework_dashboard(db: Session, org_id: int) -> dict:
    """Dashboard de cumplimiento multi-framework para una org."""
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    active = (ctx.active_frameworks or []) if ctx else []

    if not active:
        return {"frameworks": [], "overall_pct": 0, "message": "No hay frameworks configurados"}

    frameworks = []
    total_pct = 0
    for code in active:
        status = get_framework_compliance_status(db, org_id, code)
        frameworks.append(status)
        total_pct += status.get("overall_pct", 0)

    overall = int(total_pct / len(frameworks)) if frameworks else 0

    return {
        "org_id": org_id,
        "frameworks": frameworks,
        "overall_pct": overall,
        "total_gaps": sum(len(f.get("gaps", [])) for f in frameworks),
        "audit_ready_count": sum(1 for f in frameworks if f.get("is_audit_ready", False)),
    }


def auto_update_compliance_from_controls(db: Session, org_id: int) -> int:
    """Actualiza estado de compliance basado en controles implementados.

    Para cada requisito, cuenta evidencias y controles que lo satisfacen.
    Retorna cantidad de requisitos actualizados.
    """
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    active = (ctx.active_frameworks or []) if ctx else []
    updated = 0

    for framework_code in active:
        framework = load_framework(framework_code)
        if not framework:
            continue

        implemented_controls = db.query(ControlImplementation).filter(
            ControlImplementation.organization_id == org_id,
            ControlImplementation.status == ControlStatus.IMPLEMENTED,
        ).all()

        implemented_control_names = {
            (c.name or "").lower() for c in implemented_controls
        }

        for req in framework.get("requirements", []):
            req_controls = [c.lower() for c in req.get("controls", [])]
            # Si los controles requeridos están implementados → actualizar a PARTIAL/IMPLEMENTED
            if req_controls and all(
                any(rc in name for name in implemented_control_names)
                for rc in req_controls
            ):
                existing = db.query(ComplianceFrameworkStatus).filter(
                    ComplianceFrameworkStatus.organization_id == org_id,
                    ComplianceFrameworkStatus.framework_code == framework_code,
                    ComplianceFrameworkStatus.requirement_id == req["id"],
                ).first()
                if existing and existing.status == ComplianceRequirementStatus.PLANNED:
                    existing.status = ComplianceRequirementStatus.PARTIAL
                    existing.completion_pct = 50
                    existing.last_reviewed_at = datetime.now(timezone.utc)
                    updated += 1

    if updated:
        try:
            db.commit()
        except Exception:
            db.rollback()

    return updated
