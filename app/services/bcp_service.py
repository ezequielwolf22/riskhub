"""Servicio BCP/ISO 22301 — lógica de negocio para continuidad."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("riskhub.bcp_service")

# Campos requeridos para considerar el BIA completo
BIA_REQUIRED_FIELDS = [
    "rto_hours", "rpo_hours", "mtpd_hours", "mbco",
    "financial_impact", "reputational_impact", "legal_impact", "operational_impact",
    "activation_criteria", "vital_records",
]

VALID_PLAN_TYPES = ("bcp", "drp", "crp", "ems", "pandemic", "cyber_response", "supply_chain")

# La norma ISO 22301 no pondera unas clausulas mas que otras: todos los requisitos
# "shall" de las clausulas 4 a 10 son igual de obligatorios para la certificacion.
# Por eso el peso se reparte a partes iguales entre las 7 clausulas principales y,
# dentro de cada una, a partes iguales entre sus sub-clausulas evaluadas.
_CLAUSE_GROUPS = {
    "4":  ["4.1", "4.2", "4.3"],
    "5":  ["5.1", "5.2", "5.3"],
    "6":  ["6.1", "6.2"],
    "7":  ["7.4", "7.5"],
    "8":  ["8.2", "8.3", "8.4_bcp", "8.4_drp", "8.4_comm", "8.4_workaround",
           "8.5_programme", "8.5_test", "8.5_lessons", "8.6"],
    "9":  ["9.1", "9.2", "9.3"],
    "10": ["10.1", "10.2"],
}


def _clause_weights() -> dict:
    weights = {}
    for sub_ids in _CLAUSE_GROUPS.values():
        w = 100 / len(_CLAUSE_GROUPS) / len(sub_ids)
        for cid in sub_ids:
            weights[cid] = round(w, 4)
    return weights


def _status_to_score(status: str) -> int:
    return {"implemented": 100, "partial": 50, "gap": 0}.get(status, 0)


def _plan_has_substance(plan, docs_by_id: dict) -> bool:
    """Evidencia real de contenido — no un simple flag de estado.

    Si el documento del plan ya fue revisado semánticamente por IA
    (bcm_content_reviewer.py — lee el texto y evalúa si cubre lo que la
    cláusula exige), esa revisión es la evidencia más fuerte y manda: exige
    score >= 60/100. Si no hay revisión IA todavía (sin documento, sin API
    key configurada, o pendiente de analizar), cae a comprobar que el plan
    tenga contenido estructural real (secciones, resumen largo, o documento
    efectivamente procesado con texto extraído).
    """
    review = getattr(plan, "ai_content_review", None)
    if review and isinstance(review, dict) and "score" in review:
        return review["score"] >= 60
    if plan.sections and len(plan.sections) > 0:
        return True
    if plan.content_summary and len(plan.content_summary.strip()) >= 200:
        return True
    if plan.document_id:
        doc = docs_by_id.get(plan.document_id)
        if doc and (doc.chunk_count or 0) > 0:
            return True
    return False


def _plans_ai_detail(plans_all) -> str:
    """Añade al detalle de la cláusula el resultado de la revisión IA del
    contenido, si ya se ha ejecutado sobre alguno de los planes."""
    reviewed = [
        p for p in plans_all
        if isinstance(getattr(p, "ai_content_review", None), dict) and "score" in p.ai_content_review
    ]
    if not reviewed:
        return ""
    avg = round(sum(p.ai_content_review["score"] for p in reviewed) / len(reviewed))
    return f" — revisión IA del contenido: score medio {avg}/100 ({len(reviewed)}/{len(plans_all)} analizados)"


def _policy_is_solid(policy) -> bool:
    """Una politica solo es evidencia valida si esta aprobada/publicada Y tiene
    contenido real, no solo un titulo que coincide con una busqueda."""
    if not policy:
        return False
    from app.models import PolicyStatus
    if policy.status not in (PolicyStatus.APPROVED, PolicyStatus.PUBLISHED):
        return False
    return bool(policy.content and len(policy.content.strip()) >= 200)


def _evidence_covers(evid_list, plan_id: Optional[int] = None, test_id: Optional[int] = None) -> bool:
    """Busca si existe evidencia VIGENTE (is_current) vinculada explicitamente
    al plan o test — no basta con que exista evidencia en el repositorio.

    Si el archivo ya fue leido por la IA (bcm_content_reviewer.review_evidence_item)
    y determino que el contenido NO respalda la etiqueta declarada
    (ai_review.relevant == False), esa evidencia no cuenta: es un archivo subido
    para rellenar el campo, no una evidencia real. Si no se ha analizado aun
    (o el archivo no tiene texto extraible, ej. una captura de pantalla), se
    sigue contando por vinculacion — no se penaliza la ausencia de analisis.
    """
    for e in evid_list:
        if not e.is_current:
            continue
        review = getattr(e, "ai_review", None)
        if isinstance(review, dict) and review.get("relevant") is False:
            continue
        if plan_id and e.linked_plan_id == plan_id:
            return True
        if test_id and e.linked_test_id == test_id:
            return True
    return False

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


def iso22301_status(db: Session, org_id: int, location_id: Optional[int] = None) -> dict:
    """
    Checklist ISO 22301:2019 completo — 22 cláusulas relevantes.

    Evalúa el estado real del SGCN a partir de evidencia verificable: procesos,
    planes con contenido sustantivo (no solo un flag de estado), tests realmente
    realizados, evidencia vigente vinculada a esos planes/tests, riesgos con
    cobertura BCP, no conformidades y revisiones de dirección. La ausencia total
    de datos siempre se traduce en "gap" — nunca en conformidad implícita.
    """
    from app.models import (BusinessProcess, BCPTest, BCPPlan, BCPStrategy,
                             BCPExerciseProgramme, Policy, Risk, RiskStatus,
                             AiDocument, BCMEvidenceItem, BCMContext)
    now = datetime.now(timezone.utc)

    def qf(model):
        q = db.query(model).filter_by(organization_id=org_id)
        if location_id and hasattr(model, "location_id"):
            q = q.filter(getattr(model, "location_id") == location_id)
        return q.all()

    # ── Cargar datos base ────────────────────────────────────────────────────
    procs = qf(BusinessProcess)
    crit_procs = [p for p in procs if p.criticality in ("critical", "high")]
    tests = qf(BCPTest)
    plans = qf(BCPPlan)
    strategies = qf(BCPStrategy)
    evid = qf(BCMEvidenceItem)
    ctx = db.query(BCMContext).filter_by(organization_id=org_id).first()
    exercise_prog = db.query(BCPExerciseProgramme).filter_by(
        organization_id=org_id
    ).order_by(BCPExerciseProgramme.year.desc()).first()

    doc_ids = {p.document_id for p in plans if p.document_id}
    docs_by_id = (
        {d.id: d for d in db.query(AiDocument).filter(AiDocument.id.in_(doc_ids)).all()}
        if doc_ids else {}
    )

    # Política BCP
    bcp_policy = None
    try:
        bcp_policy = db.query(Policy).filter(
            Policy.organization_id == org_id
        ).filter(
            Policy.title.ilike("%continuidad%") | Policy.title.ilike("%bcp%") |
            Policy.title.ilike("%sgcn%") | Policy.title.ilike("%continuity%")
        ).order_by(Policy.approved_at.desc()).first()
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

    # Auditoría interna formal (módulo general de auditorías, no solo los
    # ejercicios/tests propios de BCM) con alcance en continuidad/ISO 22301,
    # completada en los últimos 12 meses — ISO 22301 cl. 9.2.
    bcm_audit_recent = None
    try:
        from app.models import AuditProgram, AuditStatus
        cutoff_audit = now - timedelta(days=365)
        bcm_audit_recent = db.query(AuditProgram).filter(
            AuditProgram.organization_id == org_id,
            AuditProgram.status == AuditStatus.COMPLETED,
            AuditProgram.actual_end >= cutoff_audit,
            (
                AuditProgram.criteria.ilike("%22301%") | AuditProgram.criteria.ilike("%continuidad%") |
                AuditProgram.criteria.ilike("%continuity%") | AuditProgram.criteria.ilike("%sgcn%") |
                AuditProgram.scope.ilike("%continuidad%") | AuditProgram.scope.ilike("%bcm%")
            ),
        ).order_by(AuditProgram.actual_end.desc()).first()
    except Exception:
        pass

    # Derivaciones
    recent_tests = [
        t for t in tests if t.conducted_at and
        (now - t.conducted_at.replace(tzinfo=timezone.utc)).days <= 365
    ]
    passed_tests = [t for t in recent_tests if t.result == "passed"]
    approved_plans = [p for p in plans if p.status == "approved"]
    bcp_plans = [p for p in approved_plans if p.plan_type == "bcp"]
    drp_plans = [p for p in approved_plans if p.plan_type in ("drp", "crp")]
    comm_plans = [p for p in approved_plans if p.plan_type in ("crp", "communication")]
    bcp_plans_real = [p for p in bcp_plans if _plan_has_substance(p, docs_by_id)]
    drp_plans_real = [p for p in drp_plans if _plan_has_substance(p, docs_by_id)]

    # BIA completeness (campos reales del proceso, ISO 22301 cl. 8.2)
    bia_complete_crit = [p for p in crit_procs if bia_completeness(db, p)["pct"] >= 80]
    bia_complete_all = [p for p in procs if bia_completeness(db, p)["pct"] >= 80]

    # Procesos con owner Y recovery_owner
    procs_with_owners = [p for p in crit_procs if p.owner_id and getattr(p, "recovery_owner_id", None)]
    # Procesos con MBCO
    procs_with_mbco = [p for p in crit_procs if getattr(p, "mbco", None)]
    # Procesos con procedimiento alternativo
    procs_with_workaround = [p for p in crit_procs if getattr(p, "alternative_procedure", None)]
    # Planes con review_date futura
    plans_with_review = [
        p for p in approved_plans
        if p.review_date and p.review_date.replace(tzinfo=timezone.utc) > now
    ]

    # Estrategias implementadas/testeadas que realmente cubren procesos críticos
    strats_impl = [s for s in strategies if s.implementation_status in ("implemented", "tested")]
    crit_ids = {p.id for p in crit_procs}
    covered_crit_by_strategy = crit_ids & {s.process_id for s in strats_impl if s.process_id}

    # Cobertura de riesgos residuales altos por planes de continuidad (cl. 6.1) —
    # usa Risk.bcp_coverage, ya calculado por update_risk_bcp_coverage() y hasta
    # ahora nunca consultado por el motor de scoring.
    all_risks = []
    try:
        all_risks = db.query(Risk).filter(Risk.organization_id == org_id).all()
    except Exception:
        pass
    active_risks = [r for r in all_risks if r.status not in (RiskStatus.ACCEPTED, RiskStatus.CLOSED)]
    high_risks = [r for r in active_risks if (r.residual_level or 0) >= 6]
    high_risks_covered = [r for r in high_risks if r.bcp_coverage]

    # Evidencia vigente vinculada a planes/tests reales (cl. 7.5) — no basta con
    # contar filas de BCMEvidenceItem, hay que comprobar que estén enlazadas y activas.
    evid_sources_total = len(approved_plans) + len(recent_tests)
    evid_sources_covered = (
        sum(1 for p in approved_plans if _evidence_covers(evid, plan_id=p.id))
        + sum(1 for t in recent_tests if _evidence_covers(evid, test_id=t.id))
    )

    # NCs de BCP (cl. 10.2)
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

    # ── Cláusulas con lógica multi-rama (se resuelven antes para mantener
    #    la lista final legible) ────────────────────────────────────────────
    ctx_substantive = bool(
        ctx and (ctx.sector or ctx.geographic_scope or ctx.it_architecture or ctx.critical_infra_json)
    )
    scope_documented = bool(ctx and ctx.geographic_scope) or any(
        p.scope and len(p.scope.strip()) >= 20 for p in approved_plans
    )

    if not all_risks:
        status_61 = "gap"
        detail_61 = "Sin riesgos registrados en el módulo de riesgos — no hay evidencia de valoración de riesgos para el SGCN"
    elif high_risks:
        pct_61 = _pct(len(high_risks_covered), len(high_risks))
        status_61 = st(pct_61 >= 80, pct_61 >= 40)
        detail_61 = f"{len(high_risks_covered)}/{len(high_risks)} riesgo(s) residual(es) alto(s) con cobertura de un plan de continuidad"
    else:
        status_61 = st(False, len(active_risks) > 0)
        detail_61 = f"{len(active_risks)} riesgo(s) activo(s) registrado(s), ninguno con nivel residual alto — revisar si la valoración de riesgos está actualizada"

    if crit_procs:
        pct_83 = _pct(len(covered_crit_by_strategy), len(crit_procs))
        status_83 = st(pct_83 >= 70, len(strategies) >= 1)
        detail_83 = f"{len(covered_crit_by_strategy)}/{len(crit_procs)} procesos críticos con estrategia implementada/testeada"
    else:
        status_83 = st(False, len(strategies) >= 1)
        detail_83 = f"{len(strategies)} estrategia(s) registrada(s); sin procesos críticos identificados para validar cobertura"

    pct_75 = _pct(evid_sources_covered, evid_sources_total)
    status_75 = st(pct_75 >= 70, pct_75 >= 30 or len(evid) >= 1)
    detail_75 = (
        f"{evid_sources_covered}/{evid_sources_total} plan(es)/test(s) con evidencia vigente vinculada "
        f"({len(evid)} evidencia(s) en el repositorio)"
        if evid_sources_total else
        f"Sin planes aprobados ni tests recientes que requieran evidencia; {len(evid)} evidencia(s) en repositorio"
    )

    current_year_prog = bool(exercise_prog and exercise_prog.year == now.year)
    status_85p = st(current_year_prog, bool(exercise_prog))
    detail_85p = (
        f"Programa de ejercicios {exercise_prog.year} vigente" if current_year_prog
        else f"Programa más reciente: año {exercise_prog.year} (desactualizado)" if exercise_prog
        else "Sin programa de ejercicios definido"
    )

    lessons_full = [
        t for t in recent_tests
        if getattr(t, "lessons_learned", None) and len(t.lessons_learned.strip()) >= 20
    ]
    status_85l = st(bool(lessons_full), any(getattr(t, "lessons_learned", None) for t in recent_tests))
    detail_85l = f"{len(lessons_full)} test(s) con lecciones aprendidas documentadas en detalle"

    status_91 = st(len(recent_tests) >= 1, len(tests) >= 1)
    detail_91 = f"{len(recent_tests)} test(s) realizado(s) en los últimos 12 meses (de {len(tests)} histórico(s))"

    # 10.1 Mejora continua — evidencia de que el SGCN evoluciona con el tiempo
    # (no solo que "existe"), a partir de señales reales e independientes.
    plan_revised_recent = any(
        p.version and p.version not in ("1.0", "1", "")
        for p in approved_plans
    )
    two_year_cycle = bool(
        exercise_prog and db.query(BCPExerciseProgramme).filter(
            BCPExerciseProgramme.organization_id == org_id,
            BCPExerciseProgramme.year == exercise_prog.year - 1,
        ).first()
    )
    action_after_test = any(
        getattr(t, "lessons_learned", None) and getattr(t, "improvement_actions", None)
        for t in recent_tests
    )
    nc_closed_with_action = nc_from_bcp_closed > 0
    signals_10_1 = sum([plan_revised_recent, two_year_cycle, action_after_test, nc_closed_with_action])
    status_101 = st(signals_10_1 >= 2, signals_10_1 == 1)
    detail_101 = (
        f"{signals_10_1}/4 señales de mejora continua detectadas "
        f"(revisión de versión de planes, ciclo de ejercicios plurianual, "
        f"acciones documentadas tras pruebas, cierre de no conformidades)"
    )

    # 10.2 No conformidades y acciones correctivas — FIX: la ausencia total de
    # NCs registradas ya NO se interpreta como "implementado". Solo cuenta como
    # implementado si hubo actividad de auditoría/pruebas Y no quedan NCs abiertas.
    tests_ever = len(tests) >= 1
    nc_total = nc_from_bcp_open + nc_from_bcp_closed
    if nc_total == 0:
        status_102 = st(False, tests_ever)
        detail_102 = (
            f"{len(tests)} ejercicio(s) realizado(s) sin ninguna no conformidad registrada "
            f"— verificar si los hallazgos se documentan como NC"
            if tests_ever else
            "Sin ejercicios de continuidad realizados — no hay evidencia de gestión de no conformidades del SGCN"
        )
    else:
        # nc_total > 0 ya es evidencia de que el proceso de gestion de NCs corre;
        # solo falta ver si esta al dia (sin abiertas) o en curso (partial).
        status_102 = st(nc_from_bcp_open == 0, True)
        detail_102 = (
            f"{nc_from_bcp_closed} NC(s) de continuidad cerrada(s)"
            + (f", {nc_from_bcp_open} abierta(s)" if nc_from_bcp_open else "")
        )

    # ── Construcción del checklist ────────────────────────────────────────────
    clauses = [
        {
            "id": "4.1", "name": "Comprensión de la organización y su contexto",
            "status": st(len(procs) >= 1 and ctx_substantive, len(procs) >= 1 or ctx_substantive),
            "detail": (
                f"{len(procs)} proceso(s) de negocio registrado(s); "
                f"contexto organizacional {'documentado' if ctx_substantive else 'sin documentar'}"
            ),
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
            "id": "4.3", "name": "Determinación del alcance del SGCN",
            "status": st(scope_documented, len(procs) >= 1),
            "detail": (
                "Alcance documentado en el contexto BCM o en un plan aprobado" if scope_documented
                else f"Alcance no formalizado; {len(procs)} proceso(s) identificado(s) sin declaración de alcance"
            ),
            "reference": "ISO 22301 cl. 4.3",
        },
        {
            "id": "5.1", "name": "Liderazgo y compromiso de la dirección",
            "status": st(bool(mgmt_review_recent), _policy_is_solid(bcp_policy)),
            "detail": (
                f"Revisión dirección (año actual): {'sí' if mgmt_review_recent else 'no'}; "
                f"Política BCP: {'sólida' if _policy_is_solid(bcp_policy) else 'ausente o incompleta'}"
            ),
            "reference": "ISO 22301 cl. 5.1",
        },
        {
            "id": "5.2", "name": "Política de continuidad de negocio",
            "status": st(_policy_is_solid(bcp_policy), bool(bcp_policy)),
            "detail": (
                "Política BCP aprobada con contenido sustantivo" if _policy_is_solid(bcp_policy)
                else "Política BCP en borrador o sin contenido" if bcp_policy
                else "Sin política BCP — requerida"
            ),
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
            "id": "6.1", "name": "Acciones para abordar riesgos y oportunidades",
            "status": status_61, "detail": detail_61,
            "reference": "ISO 22301 cl. 6.1",
        },
        {
            "id": "6.2", "name": "Objetivos de continuidad de negocio (MBCO)",
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
            "id": "7.5", "name": "Información documentada y evidencia",
            "status": status_75, "detail": detail_75,
            "reference": "ISO 22301 cl. 7.5",
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
            "status": status_83, "detail": detail_83,
            "reference": "ISO 22301 cl. 8.3",
        },
        {
            "id": "8.4_bcp", "name": "Plan de Continuidad de Negocio (BCP)",
            "status": st(bool(bcp_plans_real), bool(bcp_plans)),
            "detail": (
                f"{len(bcp_plans_real)}/{len(bcp_plans)} BCP aprobado(s) con contenido verificable"
                + _plans_ai_detail(bcp_plans)
            ),
            "reference": "ISO 22301 cl. 8.4",
        },
        {
            "id": "8.4_drp", "name": "Plan de Recuperación ante Desastres (DRP)",
            "status": st(bool(drp_plans_real), bool(drp_plans)),
            "detail": (
                f"{len(drp_plans_real)}/{len(drp_plans)} DRP/CRP aprobado(s) con contenido verificable"
                + _plans_ai_detail(drp_plans)
            ),
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
            "status": status_85p, "detail": detail_85p,
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
            "status": status_85l, "detail": detail_85l,
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
            "status": status_91, "detail": detail_91,
            "reference": "ISO 22301 cl. 9.1",
        },
        {
            "id": "9.2", "name": "Auditoría interna del SGCN",
            "status": st(
                bool(bcm_audit_recent) or any(t.test_type == "full_test" for t in recent_tests),
                any(t.test_type in ("tabletop", "simulation") for t in recent_tests),
            ),
            "detail": (
                f"Auditoría formal '{bcm_audit_recent.title}' completada el "
                f"{bcm_audit_recent.actual_end.strftime('%Y-%m-%d')}"
                if bcm_audit_recent else
                "Auditoría completa (full_test) realizada en 12 meses"
                if any(t.test_type == "full_test" for t in recent_tests)
                else "Sin auditoría interna (formal o full_test) del SGCN en los últimos 12 meses"
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
            "id": "10.1", "name": "Mejora continua",
            "status": status_101, "detail": detail_101,
            "reference": "ISO 22301 cl. 10.1",
        },
        {
            "id": "10.2", "name": "No conformidades y acciones correctivas",
            "status": status_102, "detail": detail_102,
            "reference": "ISO 22301 cl. 10.2",
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


def iso22301_clause_scores(db: Session, org_id: int, location_id: Optional[int] = None) -> dict:
    """
    Convierte el checklist detallado (iso22301_status) al formato numérico 0-100
    ponderado que consume el dashboard de BCP. Es el ÚNICO cálculo de score
    ISO 22301 de la aplicación — antes existían dos motores de scoring
    incompatibles (uno con un piso arbitrario de 40 puntos en "Mejora continua"
    y campos inexistentes como bia_score); ahora ambos endpoints delegan aquí.
    """
    status = iso22301_status(db, org_id, location_id)
    weights = _clause_weights()
    out_clauses = []
    for c in status["clauses"]:
        out_clauses.append({
            "id": c["id"],
            "title": c["name"],
            "score": _status_to_score(c["status"]),
            "weight": weights.get(c["id"], 1.0),
            "status": c["status"],
            "detail": c["detail"],
            "reference": c["reference"],
        })
    total_w = sum(c["weight"] for c in out_clauses)
    score_global = round(sum(c["score"] * c["weight"] for c in out_clauses) / total_w) if total_w else 0
    return {
        "clauses": out_clauses,
        "score_global": score_global,
        "implemented": status["implemented"],
        "partial": status["partial"],
        "total": status["total"],
        "is_ready": status["is_ready"],
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
