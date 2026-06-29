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
    Risk, RiskStatus,
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

    requirements = framework.get("requirements", [])
    mandatory_reqs = [r for r in requirements if r.get("mandatory", True)]

    def _effective_pct(s) -> tuple[float, bool]:
        """Devuelve (pct efectivo 0-100, contar_en_denominador).

        NOT_APPLICABLE se excluye del denominador para no penalizar requisitos
        que la org ha declarado fuera de alcance con justificacion.
        AUDITED/IMPLEMENTED = 100%. PARTIAL = completion_pct real. PLANNED = 0.
        """
        if s is None:
            return 0.0, True
        if s.status == ComplianceRequirementStatus.NOT_APPLICABLE:
            return 0.0, False
        if s.status in (ComplianceRequirementStatus.IMPLEMENTED, ComplianceRequirementStatus.AUDITED):
            return 100.0, True
        return float(s.completion_pct or 0), True

    # overall_pct: media ponderada real de completion_pct — no binario
    total_weighted = 0.0
    total_applicable = 0
    mandatory_weighted = 0.0
    mandatory_applicable = 0
    implemented_count = 0  # para status_breakdown y compatibilidad
    mandatory_implemented_count = 0

    for r in requirements:
        s = status_map.get(r["id"])
        pct, counts = _effective_pct(s)
        if counts:
            total_weighted += pct
            total_applicable += 1
        if s and s.status in (ComplianceRequirementStatus.IMPLEMENTED, ComplianceRequirementStatus.AUDITED):
            implemented_count += 1

    for r in mandatory_reqs:
        s = status_map.get(r["id"])
        pct, counts = _effective_pct(s)
        if counts:
            mandatory_weighted += pct
            mandatory_applicable += 1
        if s and s.status in (ComplianceRequirementStatus.IMPLEMENTED, ComplianceRequirementStatus.AUDITED):
            mandatory_implemented_count += 1

    total = len(requirements)
    mandatory_total = len(mandatory_reqs)
    overall_pct = int(total_weighted / total_applicable) if total_applicable else 0
    mandatory_pct = int(mandatory_weighted / mandatory_applicable) if mandatory_applicable else 0

    # Breakdown por status
    status_breakdown: dict[str, int] = {}
    for s in statuses:
        key = s.status.value if hasattr(s.status, "value") else str(s.status)
        status_breakdown[key] = status_breakdown.get(key, 0) + 1

    # Gaps: requisitos mandatorios no totalmente completados (incluye parciales)
    gaps = []
    for r in mandatory_reqs:
        s = status_map.get(r["id"])
        if s and s.status == ComplianceRequirementStatus.NOT_APPLICABLE:
            continue  # excluido con justificacion
        eff_pct, _ = _effective_pct(s)
        if eff_pct < 100:
            gaps.append({
                "id": r["id"],
                "name": r["name"],
                "domain": r.get("domain", ""),
                "status": s.status.value if s else ComplianceRequirementStatus.PLANNED.value,
                "completion_pct": int(eff_pct),
                "evidence_count": s.evidence_count if s else 0,
                "missing_evidence": (
                    s is not None
                    and s.status == ComplianceRequirementStatus.PARTIAL
                    and (s.evidence_count or 0) == 0
                    and eff_pct >= 70  # controles presentes, solo falta evidencia
                ),
            })

    # Ordenar gaps: primero los de menor %, luego por nombre
    gaps.sort(key=lambda g: (g["completion_pct"], g["id"]))

    # Evidence gaps: requisitos donde los controles estan pero falta evidencia
    evidence_gaps = [g for g in gaps if g.get("missing_evidence")]

    # Agrupar por dominio con pct ponderado
    domain_stats: dict[str, dict] = {}
    for r in requirements:
        domain = r.get("domain", "General")
        if domain not in domain_stats:
            domain_stats[domain] = {"total": 0, "weighted": 0.0, "applicable": 0}
        domain_stats[domain]["total"] += 1
        s = status_map.get(r["id"])
        pct, counts = _effective_pct(s)
        if counts:
            domain_stats[domain]["weighted"] += pct
            domain_stats[domain]["applicable"] += 1

    domains = [
        {
            "domain": d,
            "total": v["total"],
            "implemented": sum(
                1 for r in requirements
                if r.get("domain", "General") == d
                and status_map.get(r["id"])
                and status_map[r["id"]].status in (
                    ComplianceRequirementStatus.IMPLEMENTED,
                    ComplianceRequirementStatus.AUDITED,
                )
            ),
            "pct": int(v["weighted"] / v["applicable"]) if v["applicable"] else 0,
        }
        for d, v in domain_stats.items()
    ]

    # Clausulas 4-10 (nucleares ISO 27001 — no son Annex A)
    clauses_4_10 = [r for r in requirements if not r["id"].startswith("A.")]
    clauses_w = sum(_effective_pct(status_map.get(r["id"]))[0] for r in clauses_4_10)
    clauses_n = sum(1 for r in clauses_4_10 if _effective_pct(status_map.get(r["id"]))[1])
    clauses_pct = int(clauses_w / clauses_n) if clauses_n else 0

    # Bloqueantes: clausulas 4-10 no implementadas (< 100%)
    audit_blockers = [
        r["id"] for r in clauses_4_10
        if _effective_pct(status_map.get(r["id"]))[0] < 100
    ]

    # Totales de evidencia para el framework
    total_evidence_count = sum(s.evidence_count or 0 for s in statuses)
    reqs_with_evidence = sum(1 for s in statuses if (s.evidence_count or 0) > 0)

    return {
        "framework_code": framework_code,
        "framework_name": framework["name"],
        "total_requirements": total,
        "mandatory_requirements": mandatory_total,
        "overall_pct": overall_pct,
        "mandatory_pct": mandatory_pct,
        "clauses_4_10_pct": clauses_pct,
        "status_breakdown": status_breakdown,
        "domains": sorted(domains, key=lambda x: x["pct"]),
        "gaps": gaps[:20],
        "evidence_gaps": evidence_gaps[:10],
        "total_evidence_count": total_evidence_count,
        "reqs_with_evidence": reqs_with_evidence,
        "is_audit_ready": clauses_pct == 100 and mandatory_pct >= 80,
        "audit_blockers": audit_blockers[:5],
    }


def get_multi_framework_dashboard(db: Session, org_id: int) -> dict:
    """Dashboard de cumplimiento multi-framework para una org."""
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    active = (ctx.active_frameworks or []) if ctx else []

    if not active:
        return {"frameworks": [], "overall_pct": 0, "message": "No hay frameworks configurados"}

    frameworks = []
    total_weighted = 0
    total_reqs = 0
    for code in active:
        status = get_framework_compliance_status(db, org_id, code)
        frameworks.append(status)
        reqs = status.get("total_requirements", 0)
        if reqs > 0:
            total_weighted += status.get("overall_pct", 0) * reqs
            total_reqs += reqs

    overall = int(total_weighted / total_reqs) if total_reqs else 0

    return {
        "org_id": org_id,
        "frameworks": frameworks,
        "overall_pct": overall,
        "total_gaps": sum(len(f.get("gaps", [])) for f in frameworks),
        "audit_ready_count": sum(1 for f in frameworks if f.get("is_audit_ready", False)),
    }


def auto_update_compliance_from_controls(db: Session, org_id: int) -> int:
    """Actualiza estado de compliance basado en controles implementados Y evidencias.

    Logica de graduacion:
      - Todos los controles implementados + evidencia en al menos uno → IMPLEMENTED (100%)
      - Todos los controles implementados + sin ninguna evidencia → PARTIAL (75%)
        (controles presentes pero no demostrados — un auditor los marcaria NC)
      - Controles parciales → PARTIAL proporcional (10-90%)
      - Sin controles → PLANNED (0%)

    Retorna cantidad de requisitos actualizados.
    """
    from app.models import Evidence as _Evidence

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

        # Match por codigo del control (5.1, 8.23...)
        implemented_control_codes = {
            (c.control.code or "").lower()
            for c in implemented_controls if c.control
        }

        # Mapa: control_code → lista de ControlImplementation (para contar evidencias)
        code_to_cis: dict[str, list] = {}
        for ci in implemented_controls:
            if ci.control:
                code = (ci.control.code or "").lower()
                code_to_cis.setdefault(code, []).append(ci)

        # Cache de evidencias por CI id para evitar N queries en el bucle
        ci_ids = [ci.id for ci in implemented_controls]
        if ci_ids:
            from sqlalchemy import func as _func
            evd_rows = (
                db.query(_Evidence.control_implementation_id, _func.count(_Evidence.id))
                .filter(
                    _Evidence.control_implementation_id.in_(ci_ids),
                    _Evidence.organization_id == org_id,
                    _Evidence.is_current == True,
                )
                .group_by(_Evidence.control_implementation_id)
                .all()
            )
            ci_evidence_counts: dict[int, int] = {row[0]: row[1] for row in evd_rows}
        else:
            ci_evidence_counts = {}

        for req in framework.get("requirements", []):
            req_controls = [c.lower() for c in req.get("controls", [])]
            if not req_controls:
                continue

            matched = all(
                any(rc == code for code in implemented_control_codes)
                for rc in req_controls
            )
            partial = req_controls and any(
                any(rc == code for code in implemented_control_codes)
                for rc in req_controls
            )

            existing = db.query(ComplianceFrameworkStatus).filter(
                ComplianceFrameworkStatus.organization_id == org_id,
                ComplianceFrameworkStatus.framework_code == framework_code,
                ComplianceFrameworkStatus.requirement_id == req["id"],
            ).first()
            if not existing:
                continue

            # AUDITED solo puede cambiarlo un auditor humano
            if existing.status == ComplianceRequirementStatus.AUDITED:
                continue

            matched_count = sum(
                1 for rc in req_controls
                if any(rc == code for code in implemented_control_codes)
            )

            if matched:
                # Contar evidencias: (a) vinculadas a los CIs de los controles del requisito
                ctrl_evidence = sum(
                    ci_evidence_counts.get(ci.id, 0)
                    for rc in req_controls
                    for ci in code_to_cis.get(rc, [])
                )
                # (b) vinculadas directamente al requisito por framework+requirement_id
                direct_evidence = db.query(_Evidence).filter(
                    _Evidence.organization_id == org_id,
                    _Evidence.compliance_framework == framework_code,
                    _Evidence.compliance_requirement == req["id"],
                    _Evidence.is_current == True,
                ).count()
                total_evidence = ctrl_evidence + direct_evidence
                existing.evidence_count = total_evidence

                if total_evidence > 0:
                    # Controles implementados Y evidencia — plenamente conforme
                    new_status = ComplianceRequirementStatus.IMPLEMENTED
                    new_pct = 100
                else:
                    # Controles presentes pero sin evidencia: un auditor lo marcaria NC
                    new_status = ComplianceRequirementStatus.PARTIAL
                    new_pct = 75
            elif partial:
                new_pct = int(matched_count / len(req_controls) * 100)
                new_pct = max(10, min(70, new_pct))  # cap a 70 si controles parciales
                new_status = ComplianceRequirementStatus.PARTIAL
                existing.evidence_count = 0
            else:
                if existing.status == ComplianceRequirementStatus.NOT_APPLICABLE:
                    continue
                new_status = ComplianceRequirementStatus.PLANNED
                new_pct = 0
                existing.evidence_count = 0

            if existing.status != new_status or existing.completion_pct != new_pct:
                existing.status = new_status
                existing.completion_pct = new_pct
                existing.last_reviewed_at = datetime.now(timezone.utc)
                updated += 1

    if updated:
        try:
            db.commit()
        except Exception:
            db.rollback()

    return updated


def apply_high_risk_compliance_penalty(db: Session, org_id: int) -> int:
    """Degrada requisitos de compliance cubiertos por controles con riesgos residuales altos.

    Si un requisito esta en IMPLEMENTED pero los controles que lo satisfacen tienen
    riesgos vinculados con residual_level > risk_appetite, se degrada a PARTIAL y se
    reduce el completion_pct para reflejar la brecha real.

    Retorna el numero de requisitos degradados.
    """
    from sqlalchemy import text as _text

    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    active_frameworks = (ctx.active_frameworks or []) if ctx else []
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3
    if not active_frameworks:
        return 0

    # Obtener todos los control codes con riesgos de residual alto
    high_risk_rows = db.execute(
        _text("""
            SELECT DISTINCT c.code
            FROM risks r
            JOIN risk_controls rc ON rc.risk_id = r.id
            JOIN control_implementations ci ON ci.id = rc.control_implementation_id
            JOIN controls c ON c.id = ci.control_id
            WHERE r.organization_id = :org_id
              AND ci.organization_id = :org_id
              AND r.residual_level > :appetite
              AND r.status NOT IN ('closed', 'accepted')
        """),
        {"org_id": org_id, "appetite": appetite},
    ).fetchall()

    high_risk_codes: set[str] = {row[0].lower() for row in high_risk_rows if row[0]}
    if not high_risk_codes:
        return 0

    degraded = 0
    for framework_code in active_frameworks:
        framework = load_framework(framework_code)
        if not framework:
            continue

        for req in framework.get("requirements", []):
            req_controls = [c.lower() for c in req.get("controls", [])]
            if not req_controls:
                continue
            # Interseccion: algun control del requisito tiene riesgo residual alto
            if not any(rc in high_risk_codes for rc in req_controls):
                continue

            status_rec = db.query(ComplianceFrameworkStatus).filter(
                ComplianceFrameworkStatus.organization_id == org_id,
                ComplianceFrameworkStatus.framework_code == framework_code,
                ComplianceFrameworkStatus.requirement_id == req["id"],
                ComplianceFrameworkStatus.status.in_([
                    ComplianceRequirementStatus.IMPLEMENTED,
                    ComplianceRequirementStatus.AUDITED,
                ]),
            ).first()
            if not status_rec:
                continue

            # Penalizar: degradar a PARTIAL y reducir completion_pct
            status_rec.status = ComplianceRequirementStatus.PARTIAL
            status_rec.completion_pct = max(0, (status_rec.completion_pct or 100) - 30)
            status_rec.last_reviewed_at = datetime.now(timezone.utc)
            degraded += 1

    if degraded:
        try:
            db.commit()
            logger.info(
                "apply_high_risk_compliance_penalty org=%d: %d requisitos degradados",
                org_id, degraded,
            )
        except Exception:
            db.rollback()

    return degraded
