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


def iso22301_status(db: Session, org_id: int) -> dict:
    """
    Checklist ISO 22301:2019 completo — 23 cláusulas relevantes.
    Evalúa el estado del SGCN basándose en datos reales del módulo BCP.
    """
    from app.models import (BusinessProcess, BCPTest, BCPPlan, BCPStrategy,
                             BCPExerciseProgramme, BCPDependency, Policy)
    now = datetime.now(timezone.utc)

    # ── Cargar datos base ────────────────────────────────────────────────────
    procs = db.query(BusinessProcess).filter_by(organization_id=org_id).all()
    crit_procs = [p for p in procs if p.criticality in ("critical", "high")]
    tests = db.query(BCPTest).filter_by(organization_id=org_id).all()
    plans = db.query(BCPPlan).filter_by(organization_id=org_id).all()
    strategies = db.query(BCPStrategy).filter_by(organization_id=org_id).all()
    exercise_prog = db.query(BCPExerciseProgramme).filter_by(
        organization_id=org_id
    ).order_by(BCPExerciseProgramme.year.desc()).first()

    # Política BCP
    bcp_policy = None
    try:
        bcp_policy = db.query(Policy).filter(
            Policy.organization_id == org_id
        ).filter(
            Policy.title.ilike("%continuidad%") | Policy.title.ilike("%bcp%") |
            Policy.title.ilike("%sgcn%") | Policy.title.ilike("%continuity%")
        ).first()
    except Exception:
        pass

    # ManagementReview aprobada en año actual
    mgmt_review_recent = None
    try:
        from app.models import ManagementReview
        mgmt_review_recent = db.query(ManagementReview).filter(
            ManagementReview.organization_id == org_id,
            ManagementReview.status == "approved",
            ManagementReview.approved_at >= datetime(now.year, 1, 1, tzinfo=timezone.utc),
        ).first()
    except Exception:
        pass

    # Derivaciones
    recent_tests = [
        t for t in tests if t.conducted_at and
        (now - t.conducted_at.replace(tzinfo=timezone.utc)).days <= 365
    ]
    passed_tests = [t for t in recent_tests if t.result == "passed"]
    approved_plans = [p for p in plans if p.status in ("approved", "active")]
    bcp_plans = [p for p in approved_plans if p.plan_type == "bcp"]
    drp_plans = [p for p in approved_plans if p.plan_type in ("drp", "crp")]
    # BUG13 fix: "communication" is not in VALID_PLAN_TYPES; use "crp" as closest equivalent
    # so existing CRP plans count toward ISO 22301 cl. 7.4 communication requirement
    comm_plans = [p for p in approved_plans if p.plan_type in ("crp", "communication")]

    # BIA completeness
    bia_complete_crit = [p for p in crit_procs if bia_completeness(db, p)["pct"] >= 80]
    bia_complete_all = [p for p in procs if bia_completeness(db, p)["pct"] >= 80]

    # Procesos con owner Y recovery_owner
    procs_with_owners = [p for p in crit_procs if p.owner_id and getattr(p, "recovery_owner_id", None)]
    # Procesos con MBCO
    procs_with_mbco = [p for p in crit_procs if getattr(p, "mbco", None)]
    # Procesos con procedimiento alternativo
    procs_with_workaround = [
        p for p in crit_procs if
        getattr(p, "alternative_procedure", None) or getattr(p, "workaround_procedure", None)
    ]
    # Planes con review_date futura
    plans_with_review = [
        p for p in approved_plans
        if p.review_date and p.review_date.replace(tzinfo=timezone.utc) > now
    ]

    # NCs de BCP
    nc_from_bcp_open = 0
    nc_from_bcp_closed = 0
    try:
        from app.models import NonConformity, NCStatus
        nc_from_bcp_closed = db.query(NonConformity).filter(
            NonConformity.organization_id == org_id,
            NonConformity.source == "bcp_test",
            NonConformity.status == NCStatus.CLOSED,
        ).count()
        nc_from_bcp_open = db.query(NonConformity).filter(
            NonConformity.organization_id == org_id,
            NonConformity.source == "bcp_test",
            NonConformity.status != NCStatus.CLOSED,
        ).count()
    except Exception:
        pass

    def _pct(part, total):
        return int(part / total * 100) if total > 0 else 0

    def st(ok: bool, partial_ok: bool = False) -> str:
        if ok:
            return "implemented"
        if partial_ok:
            return "partial"
        return "gap"

    # ── Construcción del checklist ────────────────────────────────────────────
    clauses = [
        {
            "id": "4.1", "name": "Comprensión de la organización y su contexto",
            "status": st(len(procs) >= 1),
            "detail": f"{len(procs)} proceso(s) de negocio registrado(s)",
            "reference": "ISO 22301 cl. 4.1",
        },
        {
            "id": "4.2", "name": "Partes interesadas y sus requisitos",
            "status": st(
                bool(comm_plans) or any(getattr(p, "escalation_contacts", None) for p in crit_procs),
                any(getattr(p, "escalation_contacts", None) for p in crit_procs),
            ),
            "detail": (
                f"Plan comunicación: {'sí' if comm_plans else 'no'}; "
                f"contactos escalada: {sum(1 for p in crit_procs if getattr(p,'escalation_contacts',None))} proceso(s)"
            ),
            "reference": "ISO 22301 cl. 4.2",
        },
        {
            "id": "4.3", "name": "Alcance del SGCN",
            "status": st(any(getattr(p, "bcp_scope", None) for p in procs), len(procs) >= 1),
            "detail": "Alcance definido en al menos un proceso crítico",
            "reference": "ISO 22301 cl. 4.3",
        },
        {
            "id": "5.1", "name": "Liderazgo y compromiso de la dirección",
            "status": st(bool(mgmt_review_recent), bool(bcp_policy)),
            "detail": (
                f"Revisión dirección: {'sí' if mgmt_review_recent else 'no'}; "
                f"Política BCP: {'sí' if bcp_policy else 'no'}"
            ),
            "reference": "ISO 22301 cl. 5.1",
        },
        {
            "id": "5.2", "name": "Política de continuidad de negocio",
            "status": st(bool(bcp_policy)),
            "detail": f"Política BCP: {'encontrada' if bcp_policy else 'no encontrada — requerida'}",
            "reference": "ISO 22301 cl. 5.2",
        },
        {
            "id": "5.3", "name": "Roles, responsabilidades y autoridades",
            "status": st(
                _pct(len(procs_with_owners), len(crit_procs)) >= 80,
                _pct(len(procs_with_owners), len(crit_procs)) >= 50,
            ),
            "detail": (
                f"{len(procs_with_owners)}/{len(crit_procs)} procesos críticos con "
                f"propietario y responsable de recuperación asignados"
            ),
            "reference": "ISO 22301 cl. 5.3",
        },
        {
            "id": "6.1", "name": "Riesgos y oportunidades del SGCN",
            "status": st(len(strategies) >= 1),
            "detail": f"{len(strategies)} estrategia(s) de continuidad definida(s)",
            "reference": "ISO 22301 cl. 6.1",
        },
        {
            "id": "6.2", "name": "Objetivos de continuidad de negocio",
            "status": st(
                _pct(len(procs_with_mbco), len(crit_procs)) >= 80,
                _pct(len(procs_with_mbco), len(crit_procs)) >= 50,
            ),
            "detail": f"{len(procs_with_mbco)}/{len(crit_procs)} procesos críticos con MBCO definido",
            "reference": "ISO 22301 cl. 6.2",
        },
        {
            "id": "7.4", "name": "Comunicación durante incidente",
            "status": st(bool(comm_plans)),
            "detail": f"{len(comm_plans)} plan(es) de comunicación aprobado(s)",
            "reference": "ISO 22301 cl. 7.4",
        },
        {
            "id": "8.2", "name": "Análisis de Impacto de Negocio (BIA)",
            "status": st(
                _pct(len(bia_complete_crit), len(crit_procs)) >= 80,
                _pct(len(bia_complete_crit), len(crit_procs)) >= 50,
            ),
            "detail": (
                f"{len(bia_complete_all)}/{len(procs)} procesos con BIA >= 80% "
                f"({len(bia_complete_crit)}/{len(crit_procs)} críticos)"
            ),
            "reference": "ISO 22301 cl. 8.2",
        },
        {
            "id": "8.3", "name": "Estrategias y soluciones de continuidad",
            "status": st(len(strategies) >= 1),
            "detail": f"{len(strategies)} estrategia(s) registrada(s)",
            "reference": "ISO 22301 cl. 8.3",
        },
        {
            "id": "8.4_bcp", "name": "Plan de Continuidad de Negocio (BCP)",
            "status": st(bool(bcp_plans)),
            "detail": f"{len(bcp_plans)} BCP aprobado(s)",
            "reference": "ISO 22301 cl. 8.4",
        },
        {
            "id": "8.4_drp", "name": "Plan de Recuperación ante Desastres (DRP)",
            "status": st(bool(drp_plans)),
            "detail": f"{len(drp_plans)} DRP/CRP aprobado(s)",
            "reference": "ISO 22301 cl. 8.4",
        },
        {
            "id": "8.4_comm", "name": "Plan de comunicación de crisis",
            "status": st(bool(comm_plans)),
            "detail": f"{len(comm_plans)} plan(es) de comunicación aprobado(s)",
            "reference": "ISO 22301 cl. 8.4 / 7.4",
        },
        {
            "id": "8.4_workaround", "name": "Procedimientos de trabajo temporal",
            "status": st(
                _pct(len(procs_with_workaround), len(crit_procs)) >= 80,
                _pct(len(procs_with_workaround), len(crit_procs)) >= 40,
            ),
            "detail": (
                f"{len(procs_with_workaround)}/{len(crit_procs)} procesos críticos "
                f"con procedimiento alternativo"
            ),
            "reference": "ISO 22301 cl. 8.4 / 4.5.1",
        },
        {
            "id": "8.5_programme", "name": "Programa de ejercicios y pruebas",
            "status": st(bool(exercise_prog)),
            "detail": (
                f"Programa: {'año ' + str(exercise_prog.year) if exercise_prog else 'no definido'}"
            ),
            "reference": "ISO 22301 cl. 8.5",
        },
        {
            "id": "8.5_test", "name": "Ejercicios realizados (últimos 12 meses)",
            "status": st(len(passed_tests) >= 1, len(recent_tests) >= 1),
            "detail": (
                f"{len(passed_tests)} ejercicio(s) superado(s) / "
                f"{len(recent_tests)} realizado(s) en últimos 12 meses"
            ),
            "reference": "ISO 22301 cl. 8.5",
        },
        {
            "id": "8.5_lessons", "name": "Lecciones aprendidas documentadas",
            "status": st(any(getattr(t, "lessons_learned", None) for t in recent_tests)),
            "detail": (
                f"{sum(1 for t in recent_tests if getattr(t,'lessons_learned',None))} "
                f"test(s) con lecciones documentadas"
            ),
            "reference": "ISO 22301 cl. 8.5",
        },
        {
            "id": "8.6", "name": "Evaluación y revisión de documentación BCM",
            "status": st(
                len(plans_with_review) >= max(1, len(approved_plans)) * 0.8,
                bool(plans_with_review),
            ),
            "detail": (
                f"{len(plans_with_review)}/{len(approved_plans)} planes aprobados "
                f"con fecha de revisión programada"
            ),
            "reference": "ISO 22301 cl. 8.6",
        },
        {
            "id": "9.1", "name": "Seguimiento, medición y evaluación",
            "status": st(len(tests) >= 1),
            "detail": f"{len(tests)} test(s) de continuidad registrado(s)",
            "reference": "ISO 22301 cl. 9.1",
        },
        {
            "id": "9.2", "name": "Auditoría interna del SGCN",
            "status": st(
                any(t.test_type == "full_test" for t in recent_tests),
                any(t.test_type in ("tabletop", "simulation") for t in recent_tests),
            ),
            "detail": (
                "Auditoría completa realizada"
                if any(t.test_type == "full_test" for t in recent_tests)
                else "Sin auditoría completa del SGCN en 12 meses"
            ),
            "reference": "ISO 22301 cl. 9.2",
        },
        {
            "id": "9.3", "name": "Revisión del SGCN por la dirección",
            "status": st(bool(mgmt_review_recent)),
            "detail": (
                f"Revisión dirección (año actual): "
                f"{'completada' if mgmt_review_recent else 'pendiente'}"
            ),
            "reference": "ISO 22301 cl. 9.3",
        },
        {
            "id": "10.1", "name": "No conformidades y acciones correctoras",
            "status": st(nc_from_bcp_open == 0, nc_from_bcp_closed > 0),
            "detail": (
                f"{nc_from_bcp_closed} NC(s) de BCP cerrada(s)"
                + (f", {nc_from_bcp_open} abierta(s)" if nc_from_bcp_open else "")
            ),
            "reference": "ISO 22301 cl. 10.1",
        },
    ]

    implemented = sum(1 for c in clauses if c["status"] == "implemented")
    partial = sum(1 for c in clauses if c["status"] == "partial")
    pct = int((implemented + partial * 0.5) / len(clauses) * 100) if clauses else 0

    return {
        "clauses": clauses,
        "implemented": implemented,
        "partial": partial,
        "total": len(clauses),
        "pct": pct,
        "is_ready": implemented >= len(clauses) * 0.85 and pct >= 85,
    }


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


def update_risk_bcp_coverage(db: Session, org_id: int) -> int:
    """
    Para todos los riesgos activos de la org, calcula si hay un plan BCP/DRP
    aprobado que cubra el activo o proceso vinculado al riesgo.
    Actualiza el campo bcp_coverage del riesgo.
    Devuelve número de riesgos actualizados.

    ISO 22301 cl. 8.4 / ISO 27001 A.5.29
    """
    from app.models import Risk, RiskStatus, BCPPlan, BusinessProcess

    try:
        risks = db.query(Risk).filter(
            Risk.organization_id == org_id,
            Risk.status.notin_([RiskStatus.ACCEPTED, RiskStatus.CLOSED]),
        ).all()

        approved_plans = db.query(BCPPlan).filter(
            BCPPlan.organization_id == org_id,
            BCPPlan.status.in_(["approved", "active"]),
        ).all()

        updated = 0
        for risk in risks:
            if not risk.asset_id:
                continue

            # Buscar procesos BCP que vinculen este activo
            covering_procs = db.query(BusinessProcess).filter(
                BusinessProcess.organization_id == org_id,
                BusinessProcess.asset_ids.contains(str(risk.asset_id)),
            ).all()

            if not covering_procs:
                continue

            # Buscar plan aprobado que cubra alguno de esos procesos
            best_plan = None
            for plan in approved_plans:
                plan_proc_ids = [str(p) for p in (plan.process_ids or [])]
                if any(str(proc.id) in plan_proc_ids for proc in covering_procs):
                    best_plan = plan
                    break

            if not best_plan:
                continue

            # RTO del proceso más relevante
            min_rto = min(
                (p.rto_hours for p in covering_procs if p.rto_hours),
                default=None,
            )

            # Último test del proceso
            last_test_date = max(
                (p.last_tested_at for p in covering_procs if p.last_tested_at),
                default=None,
            )

            # Calcular cobertura: plan aprobado=60%, test reciente=+30%, RTO definido=+10%
            coverage_pct = 60
            if last_test_date:
                days_since = (
                    datetime.now(timezone.utc)
                    - last_test_date.replace(tzinfo=timezone.utc)
                ).days
                if days_since <= 365:
                    coverage_pct += 30
            if min_rto:
                coverage_pct += 10

            risk.bcp_coverage = {
                "plan_id": best_plan.id,
                "plan_code": best_plan.code,
                "plan_type": best_plan.plan_type,
                "rto_hours": min_rto,
                "last_tested": last_test_date.isoformat() if last_test_date else None,
                "coverage_pct": coverage_pct,
            }
            updated += 1

        if updated > 0:
            db.commit()
        return updated

    except Exception as exc:
        logger.debug("update_risk_bcp_coverage error org=%d: %s", org_id, exc)
        return 0
