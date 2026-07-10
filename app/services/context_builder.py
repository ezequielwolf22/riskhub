"""Construye el bloque de contexto para inyectar en el prompt del agente IA."""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models import (
    AiConfig, AiDocument, AiDocumentStatus, Asset, ControlImplementation, ControlStatus,
    ComplianceFrameworkStatus, ExternalFinding, Incident, KRI, KRIStatus,
    NonConformity, Policy, PolicyStatus, Risk, RiskContext, RiskStatus, Supplier,
    TaskStatus, TenantChangeInboxItem, TreatmentTask,
)
from app.services.rag_service import search_chunks_with_source
from app.services.app_knowledge_base import search_app_knowledge, format_knowledge_sections


def build_context(
    db: Session,
    query: str = "",
    max_chunks: int = 8,
    organization_id: int | None = None,
    voyage_api_key: str | None = None,
    lang: str = "es",
) -> str:
    """Genera el bloque de contexto completo para inyectar en el prompt.

    organization_id es OBLIGATORIO para uso normal — garantiza que el contexto
    contiene UNICAMENTE datos del tenant del usuario autenticado.
    Solo se omite (None) en contextos de superadmin o pruebas internas.
    """
    if organization_id is None:
        logger.warning("build_context llamado sin organization_id — contexto multi-tenant activo")
    parts: list[str] = []

    def _forg(q, model):
        """Aplica filtro de organizacion si se proporciono organization_id."""
        if organization_id is not None:
            return q.filter(model.organization_id == organization_id)
        return q

    # 1. Perfil de organizacion
    ctx = _forg(db.query(RiskContext), RiskContext).first()
    ai_cfg = _forg(db.query(AiConfig), AiConfig).first()

    if ctx:
        parts.append(f"## Organizacion: {ctx.organization_name or 'Sin nombre'}")
        if ctx.scope:
            parts.append(f"Alcance del SGSI: {ctx.scope}")
        if ctx.boundaries:
            parts.append(f"Fronteras: {ctx.boundaries}")
        if ctx.risk_appetite is not None:
            parts.append(f"Apetito de riesgo: nivel {ctx.risk_appetite}/8")
        if ctx.methodology:
            parts.append(f"Metodologia de riesgo activa: {ctx.methodology}")
        if ctx.active_frameworks:
            parts.append(f"Normativas activas: {', '.join(ctx.active_frameworks)}")
        if ctx.ens_level:
            parts.append(f"Nivel ENS: {ctx.ens_level.upper()}")
        # Respuestas del cuestionario IA — contexto organizacional completo
        qa = ctx.questionnaire_answers or {}
        if qa:
            parts.append("\n## Perfil organizacional (cuestionario IA)")
            _QA_LABELS = {
                "sector": "Sector", "employees": "Empleados",
                "regulations": "Normativas", "systems": "Sistemas gestionados",
                "data_types": "Tipos de datos", "remote_access": "Acceso remoto",
                "third_parties": "Proveedores externos", "incidents": "Incidentes previos",
                "controls_existing": "Controles implementados", "maturity": "Madurez de seguridad",
                "rto": "RTO", "risk_appetite_level": "Apetito de riesgo",
                "additional": "Contexto adicional",
            }
            for key, label in _QA_LABELS.items():
                val = qa.get(key)
                if val:
                    if isinstance(val, list):
                        val = ", ".join(str(v) for v in val)
                    parts.append(f"  {label}: {val}")

    if ai_cfg:
        if ai_cfg.org_sector:
            parts.append(f"Sector: {ai_cfg.org_sector}")
        if ai_cfg.org_size:
            parts.append(f"Tamano de la organizacion: {ai_cfg.org_size}")
        if ai_cfg.org_critical_processes:
            parts.append(f"Procesos criticos: {ai_cfg.org_critical_processes}")
        if ai_cfg.org_tech_stack:
            parts.append(f"Stack tecnologico: {ai_cfg.org_tech_stack}")

    # 2. Inventario de activos (resumen)
    assets = _forg(db.query(Asset), Asset).limit(50).all()
    if assets:
        parts.append(f"\n## Activos ({len(assets)} en inventario)")
        for a in assets[:15]:
            cia = f"C={a.value_confidentiality} I={a.value_integrity} A={a.value_availability}"
            parts.append(f"- {a.code}: {a.name} [{a.asset_type.value}] {cia}")
        if len(assets) > 15:
            parts.append(f"  ... y {len(assets) - 15} activos adicionales.")

    # 3. Riesgos activos
    risks = (
        _forg(db.query(Risk), Risk)
        .filter(Risk.status != RiskStatus.CLOSED)
        .limit(30)
        .all()
    )
    if risks:
        parts.append(f"\n## Riesgos activos ({len(risks)})")
        for r in risks[:15]:
            desc = (r.description or "Sin descripcion")[:80]
            parts.append(
                f"- {r.code}: {desc} "
                f"[residual={r.residual_level}/8, estado={r.status.value}]"
            )
        if len(risks) > 15:
            parts.append(f"  ... y {len(risks) - 15} riesgos adicionales.")

    # 4. Incidentes recientes
    incidents = (
        _forg(db.query(Incident), Incident)
        .order_by(Incident.created_at.desc())
        .limit(5)
        .all()
    )
    if incidents:
        parts.append(f"\n## Incidentes recientes ({len(incidents)})")
        for i in incidents:
            parts.append(f"- {i.code}: {i.title} [{i.severity.value}, {i.status.value}]")

    # 5. Controles con baja madurez
    weak_controls = (
        _forg(db.query(ControlImplementation), ControlImplementation)
        .filter(
            ControlImplementation.status != ControlStatus.IMPLEMENTED,
            ControlImplementation.maturity <= 2,
        )
        .limit(10)
        .all()
    )
    if weak_controls:
        parts.append(f"\n## Controles con baja madurez ({len(weak_controls)})")
        for c in weak_controls:
            parts.append(
                f"- {c.name}: madurez {c.maturity}/5, estado {c.status.value}"
            )

    # 6. Proveedores criticos
    critical_suppliers = (
        _forg(db.query(Supplier), Supplier)
        .filter(Supplier.is_critical.is_(True))
        .limit(10)
        .all()
    )
    if critical_suppliers:
        parts.append(f"\n## Proveedores criticos ({len(critical_suppliers)})")
        for s in critical_suppliers:
            # risk_level puede ser Enum o string plano segun el origen del dato
            level = s.risk_level.value if hasattr(s.risk_level, "value") else (s.risk_level or "?")
            parts.append(f"- {s.name}: riesgo {level}, score {s.score}/100")

    # 7. No conformidades abiertas
    ncs = (
        _forg(db.query(NonConformity), NonConformity)
        .filter(NonConformity.status.in_(["open", "in_progress"]))
        .limit(10)
        .all()
    )
    if ncs:
        parts.append(f"\n## No conformidades abiertas ({len(ncs)})")
        for nc in ncs:
            parts.append(f"- {nc.code}: {nc.title} [{nc.severity.value}]")

    # 8b. Tareas de tratamiento pendientes/en curso/vencidas
    now = datetime.now(timezone.utc)
    tasks = (
        _forg(db.query(TreatmentTask), TreatmentTask)
        .filter(TreatmentTask.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]))
        .order_by(TreatmentTask.due_date.asc().nulls_last())
        .limit(12)
        .all()
    )
    if tasks:
        parts.append(f"\n## Tareas de tratamiento activas ({len(tasks)})")
        for t in tasks:
            due = ""
            if t.due_date:
                due_dt = t.due_date if t.due_date.tzinfo else t.due_date.replace(tzinfo=timezone.utc)
                overdue = " [VENCIDA]" if due_dt < now else ""
                due = f", vence {due_dt.strftime('%Y-%m-%d')}{overdue}"
            assignee = (
                f", responsable: {t.assigned_to.full_name or t.assigned_to.email}"
                if t.assigned_to else ""
            )
            parts.append(f"- {t.code}: {t.title} [{t.status.value}, prioridad={t.priority.value}{due}{assignee}]")

    # 8c. Politicas vigentes y pendientes de revision
    policies = (
        _forg(db.query(Policy), Policy)
        .filter(Policy.status.in_([PolicyStatus.PUBLISHED, PolicyStatus.APPROVED, PolicyStatus.REVIEW]))
        .order_by(Policy.review_date.asc().nulls_last())
        .limit(10)
        .all()
    )
    if policies:
        parts.append(f"\n## Politicas del SGSI ({len(policies)})")
        for p in policies:
            review = ""
            if p.review_date:
                rev_dt = p.review_date if p.review_date.tzinfo else p.review_date.replace(tzinfo=timezone.utc)
                overdue = " [REVISION VENCIDA]" if rev_dt < now else ""
                review = f", revision: {rev_dt.strftime('%Y-%m-%d')}{overdue}"
            regwatch_flag = " [REGWATCH: requiere revision normativa]" if p.regwatch_review_at else ""
            parts.append(f"- {p.code}: {p.title} [v{p.version}, {p.status.value}{review}{regwatch_flag}]")

    # 8d. Scores de cumplimiento por framework
    try:
        from sqlalchemy import func as sqlfunc
        framework_rows = (
            _forg(db.query(
                ComplianceFrameworkStatus.framework_code,
                sqlfunc.avg(ComplianceFrameworkStatus.completion_pct).label("avg_pct"),
                sqlfunc.count(ComplianceFrameworkStatus.id).label("total"),
            ), ComplianceFrameworkStatus)
            .group_by(ComplianceFrameworkStatus.framework_code)
            .all()
        )
        if framework_rows:
            parts.append("\n## Estado de cumplimiento por framework")
            for row in framework_rows:
                parts.append(f"- {row.framework_code.upper()}: {round(row.avg_pct or 0)}% ({row.total} requisitos)")
    except Exception:
        pass

    # 8d-bis. SOA: controles implementados sin evidencia (bloqueantes para auditoria)
    try:
        all_impls = _forg(db.query(ControlImplementation), ControlImplementation).all()
        if all_impls:
            total_impls = len(all_impls)
            impl_count = sum(1 for c in all_impls if c.status == ControlStatus.IMPLEMENTED)
            impl_no_evidence = [
                c for c in all_impls
                if c.status == ControlStatus.IMPLEMENTED and not c.evidence_refs
            ]
            impl_no_reason = sum(
                1 for c in all_impls if not c.inclusion_reason and not c.exclusion_justification
            )
            parts.append(
                f"\n## Estado del SOA (Declaracion de Aplicabilidad)\n"
                f"- Total controles: {total_impls} | Implementados: {impl_count} "
                f"| Sin evidencia: {len(impl_no_evidence)} "
                f"| Sin justificacion inclusion/exclusion: {impl_no_reason}\n"
                f"- ATENCION: {len(impl_no_evidence)} controles 'implementados' carecen de evidencias "
                f"documentadas — NO son auditables ni conformes segun ISO 27001 cl. 6.1.3."
            )
            if impl_no_evidence:
                sample = impl_no_evidence[:8]
                parts.append("  Controles implementados SIN evidencia (muestra):")
                for c in sample:
                    code = c.control.code if c.control else "?"
                    parts.append(f"  - {code} {c.name}: sin evidence_refs")
    except Exception:
        pass

    # 8d-ter. Brechas de evidencia por framework (requisitos con controles pero sin evidencia)
    try:
        if ctx and (ctx.active_frameworks or []) and organization_id:
            from app.services.compliance_service import get_framework_compliance_status as _gfcs
            ev_gap_lines = []
            for fw_code in (ctx.active_frameworks or []):
                fw_status = _gfcs(db, organization_id, fw_code)
                ev_gaps = fw_status.get("evidence_gaps", [])
                total_evd = fw_status.get("total_evidence_count", 0)
                reqs_evd = fw_status.get("reqs_with_evidence", 0)
                total_req = fw_status.get("total_requirements", 0)
                if ev_gaps:
                    ev_gap_lines.append(
                        f"  {fw_code.upper()}: {len(ev_gaps)} requisito(s) con controles implementados "
                        f"pero SIN evidencia — auditoria bloqueada en estos puntos:"
                    )
                    for g in ev_gaps[:5]:
                        ev_gap_lines.append(f"    - {g['id']} {g['name']} [{g['completion_pct']}%]")
                if total_req:
                    ev_gap_lines.append(
                        f"  {fw_code.upper()}: {reqs_evd}/{total_req} requisitos con evidencia "
                        f"({total_evd} ficheros/registros total)"
                    )
            if ev_gap_lines:
                parts.append(
                    "\n## Brechas de evidencia por framework\n"
                    "CRITICO: los siguientes requisitos tienen controles implementados pero "
                    "carecen de evidencia documentada. Sin evidencia no hay cumplimiento demostrable."
                )
                parts.extend(ev_gap_lines)
    except Exception:
        pass

    # 8e. KRIs en estado warning o breach
    kris_alert = (
        _forg(db.query(KRI), KRI)
        .filter(KRI.is_active.is_(True), KRI.status.in_(["warning", "breach"]))
        .limit(10)
        .all()
    )
    if kris_alert:
        parts.append(f"\n## KRIs en alerta ({len(kris_alert)})")
        for k in kris_alert:
            val = f"valor actual={k.current_value}" if k.current_value is not None else ""
            breach_val = f"umbral breach={k.breach_threshold}" if k.breach_threshold is not None else ""
            parts.append(f"- {k.name} [{k.status}, {val}, {breach_val}]")

    # 8f. Inbox de Regwatch — cambios normativos pendientes
    try:
        inbox_items = (
            _forg(db.query(TenantChangeInboxItem), TenantChangeInboxItem)
            .filter(TenantChangeInboxItem.status == "pending")
            .order_by(TenantChangeInboxItem.created_at.desc())
            .limit(5)
            .all()
        )
        if inbox_items:
            parts.append(f"\n## Cambios normativos pendientes de revision (Regwatch inbox: {len(inbox_items)})")
            for item in inbox_items:
                pack = item.change_pack
                if pack:
                    impact = ""
                    if item.impact_summary_json:
                        counts = []
                        for key, val in (item.impact_summary_json or {}).items():
                            if isinstance(val, list) and val:
                                counts.append(f"{key}: {len(val)}")
                            elif isinstance(val, int) and val:
                                counts.append(f"{key}: {val}")
                        impact = f" [impacta {', '.join(counts)}]" if counts else ""
                    parts.append(f"- {pack.title or 'Cambio normativo'}{impact} (recibido {item.created_at.strftime('%Y-%m-%d')})")
    except Exception:
        pass

    # 8g. Hallazgos externos abiertos (de escaneres, OSINT, architecture review)
    open_findings = (
        _forg(db.query(ExternalFinding), ExternalFinding)
        .filter(ExternalFinding.status == "open")
        .order_by(ExternalFinding.created_at.desc())
        .limit(10)
        .all()
    )
    if open_findings:
        parts.append(f"\n## Hallazgos externos abiertos ({len(open_findings)})")
        for f in open_findings:
            source = f.source.value if hasattr(f.source, "value") else str(f.source)
            sev = f.severity or "N/D"
            host = f" [{f.affected_host}]" if f.affected_host else ""
            parts.append(f"- [{source}] {f.title[:80]} [severidad={sev}{host}]")

    # 8h. Vigilancia tecnica agregada: CVEs abiertos por severidad
    try:
        from sqlalchemy import func as _func
        sev_rows = (
            _forg(db.query(ExternalFinding.severity, _func.count()), ExternalFinding)
            .filter(ExternalFinding.status == "open", ExternalFinding.cve_id.isnot(None))
            .group_by(ExternalFinding.severity)
            .all()
        )
        if sev_rows:
            sev_txt = ", ".join(f"{n} {str(s or '?').upper()}" for s, n in sev_rows)
            parts.append(f"\n## CVEs abiertos vinculados a activos: {sev_txt}")
    except Exception:
        pass

    # 8i. OSINT: exposicion externa activa
    try:
        from app.models import OSINTFinding, OSINTScan
        scan_ids = [
            s.id for s in _forg(db.query(OSINTScan), OSINTScan).all()
        ]
        if scan_ids:
            osint_top = (
                db.query(OSINTFinding)
                .filter(
                    OSINTFinding.scan_id.in_(scan_ids),
                    OSINTFinding.is_remediated == False,  # noqa: E712
                    OSINTFinding.risk_level.in_(["critical", "high"]),
                )
                .order_by(OSINTFinding.risk_score.desc())
                .limit(5)
                .all()
            )
            if osint_top:
                parts.append(f"\n## Exposicion OSINT activa (top {len(osint_top)} criticos/altos)")
                for f in osint_top:
                    parts.append(f"- [{(f.risk_level or '?').upper()}] {f.title[:80]} [fuente: {f.source}]")
    except Exception:
        pass

    # 8j. Factor humano: formacion y campanas de phishing (evidencias analizadas)
    try:
        from app.models import Evidence
        human_evs = (
            _forg(db.query(Evidence), Evidence)
            .filter(
                Evidence.evidence_type.in_(["training_record", "phishing_campaign"]),
                Evidence.is_current == True,  # noqa: E712
            )
            .order_by(Evidence.created_at.desc())
            .limit(5)
            .all()
        )
        if human_evs:
            parts.append("\n## Factor humano: formacion y simulaciones de phishing")
            for ev in human_evs:
                etype = ev.evidence_type.value if hasattr(ev.evidence_type, "value") else ev.evidence_type
                rev = ev.ai_review or {}
                summary = rev.get("summary") or ev.description or ""
                parts.append(f"- [{etype}] {ev.title[:70]}: {summary[:150]}")
                for fact in (rev.get("key_facts") or [])[:2]:
                    parts.append(f"    · {fact[:120]}")
    except Exception:
        pass

    # 8k. Actas de comites de seguridad (gobierno)
    try:
        from app.models import Evidence
        minutes = (
            _forg(db.query(Evidence), Evidence)
            .filter(
                Evidence.evidence_type == "meeting_minutes",
                Evidence.is_current == True,  # noqa: E712
            )
            .order_by(Evidence.created_at.desc())
            .limit(3)
            .all()
        )
        if minutes:
            parts.append("\n## Actas de comites recientes")
            for ev in minutes:
                rev = ev.ai_review or {}
                summary = rev.get("summary") or ev.description or ""
                parts.append(f"- {ev.title[:70]}: {summary[:180]}")
    except Exception:
        pass

    # 8l. Auditorias en curso o recientes
    try:
        from app.models import AuditProgram
        audits = (
            _forg(db.query(AuditProgram), AuditProgram)
            .order_by(AuditProgram.id.desc())
            .limit(4)
            .all()
        )
        if audits:
            parts.append("\n## Auditorias")
            for a in audits:
                status = a.status.value if hasattr(a.status, "value") else (a.status or "?")
                parts.append(f"- {a.title or a.code} [estado: {status}, auditado: {getattr(a, 'auditee', None) or 'interno'}]")
    except Exception:
        pass

    # 8m. GDPR: RoPA y DPIAs pendientes
    try:
        from app.models import ProcessingActivity
        acts = _forg(db.query(ProcessingActivity), ProcessingActivity).all()
        if acts:
            dpia_pending = sum(
                1 for a in acts
                if getattr(a, "requires_dpia", False) and not (a.dpias or [])
            )
            parts.append(
                f"\n## GDPR: {len(acts)} actividades de tratamiento (RoPA)"
                + (f", {dpia_pending} DPIA pendientes" if dpia_pending else "")
            )
    except Exception:
        pass

    # 8n. Continuidad: estado de planes BCP
    try:
        from app.models import BCPPlan
        plans = _forg(db.query(BCPPlan), BCPPlan).limit(20).all()
        if plans:
            by_status: dict[str, int] = {}
            for p in plans:
                st = p.status.value if hasattr(p.status, "value") else str(p.status or "?")
                by_status[st] = by_status.get(st, 0) + 1
            st_txt = ", ".join(f"{n} {s}" for s, n in sorted(by_status.items()))
            parts.append(f"\n## Continuidad de negocio: {len(plans)} planes BCP ({st_txt})")
    except Exception:
        pass

    # 8o. TPRM: cuestionarios de proveedores sin responder o vencidos
    try:
        from app.models import SupplierQuestionnaire
        now_ = datetime.now(timezone.utc)
        qs = (
            _forg(db.query(SupplierQuestionnaire), SupplierQuestionnaire)
            .filter(SupplierQuestionnaire.submitted_at.is_(None))
            .limit(50)
            .all()
        )
        if qs:
            expired = sum(
                1 for q in qs
                if q.expires_at and q.expires_at.replace(tzinfo=timezone.utc) < now_
            )
            parts.append(
                f"\n## TPRM: {len(qs)} cuestionarios de proveedor sin responder"
                + (f" ({expired} vencidos)" if expired else "")
            )
    except Exception:
        pass

    # 10. Documentos indexados disponibles + fragmentos RAG relevantes
    indexed_docs = (
        _forg(db.query(AiDocument), AiDocument)
        .filter(AiDocument.status == AiDocumentStatus.INDEXED)
        .order_by(AiDocument.id.desc())
        .limit(30)
        .all()
    )
    if indexed_docs:
        parts.append(f"\n## Documentos indexados disponibles ({len(indexed_docs)})")
        for d in indexed_docs:
            cat = d.category.value if hasattr(d.category, "value") else (d.category or "sin categoria")
            parts.append(f"- {d.original_name} [categoria: {cat}, fragmentos: {d.chunk_count}]")
        parts.append(
            "(Puedes hacer preguntas sobre el contenido de cualquiera de estos documentos.)"
        )

    # Fragmentos RAG relevantes a la consulta actual
    if query:
        results = search_chunks_with_source(
            db, query, top_k=max_chunks, organization_id=organization_id,
            voyage_api_key=voyage_api_key,
        )
        if results:
            parts.append("\n## Contenido relevante encontrado en documentos")
            for r in results:
                source_label = f"[Fuente: {r['doc_name']}]"
                parts.append(f"---\n{source_label}\n{r['content'][:1200]}")
        elif indexed_docs:
            parts.append(
                "\n*No se encontraron fragmentos especificos para esta consulta. "
                "Si quieres consultar un documento concreto, menciona su nombre o "
                "usa terminos que aparezcan en el documento.*"
            )

    # Conocimiento funcional de la aplicacion (manual interno)
    if query:
        knowledge_sections = search_app_knowledge(query, max_sections=3)
        knowledge_text = format_knowledge_sections(knowledge_sections)
        if knowledge_text:
            parts.append(knowledge_text)

    return "\n".join(parts)


def _build_supplier_context(db: Session, risk, lang: str = "es") -> str:
    """Anade contexto del proveedor vinculado al riesgo para el agente IA."""
    if not getattr(risk, "supplier_id", None):
        return ""
    from app.models import Supplier, VendorIssue, VendorIssueStatus, VendorIssueSeverity

    sup = db.get(Supplier, risk.supplier_id)
    if not sup:
        return ""

    open_critical = db.query(VendorIssue).filter(
        VendorIssue.supplier_id == sup.id,
        VendorIssue.severity == VendorIssueSeverity.CRITICAL,
        VendorIssue.status.notin_([
            VendorIssueStatus.CLOSED,
            VendorIssueStatus.MITIGATED,
            VendorIssueStatus.ACCEPTED,
        ]),
    ).count()

    flags = []
    if getattr(sup, "is_data_processor", False):
        flags.append("Procesador GDPR Art.28")
    if getattr(sup, "is_nis2", False):
        flags.append("Sujeto NIS2")
    if getattr(sup, "is_dora", False):
        flags.append("ICT DORA")
    if getattr(sup, "concentration_risk_flag", False):
        flags.append("Concentracion DORA >40%")

    last_assessed = ""
    if getattr(sup, "last_assessment_at", None):
        last_assessed = sup.last_assessment_at.strftime("%Y-%m-%d")

    tier_val = sup.tier.value if getattr(sup, "tier", None) else "N/D"

    lines = [
        f"\n## Proveedor vinculado: {sup.name}",
        f"- Score residual TPRM: {sup.residual_risk_score or 'N/D'}/100",
        f"- Tier: {tier_val}",
        f"- Lifecycle: {getattr(sup, 'lifecycle_stage', None) or 'active'}",
        f"- Issues criticos abiertos: {open_critical}",
        f"- Ultima evaluacion: {last_assessed or 'Nunca'}",
        f"- Flags regulatorios: {', '.join(flags) if flags else 'Ninguno'}",
        f"- Concentracion de riesgo: "
        f"{'Si -- supera 40% de procesos criticos' if getattr(sup, 'concentration_risk_flag', False) else 'No'}",
    ]
    return "\n".join(lines)


def build_risk_context(db: Session, risk, organization_id: int | None = None, lang: str = "es") -> str:
    """Construye el bloque de contexto especifico de un riesgo para el agente IA.

    Incluye la informacion del proveedor vinculado si el riesgo tiene supplier_id.
    """
    parts: list[str] = []

    desc = (risk.description or "Sin descripcion")
    parts.append(f"## Riesgo: {risk.code}")
    parts.append(f"- Descripcion: {desc}")
    parts.append(f"- Estado: {risk.status.value}")
    if risk.residual_level is not None:
        parts.append(f"- Nivel residual: {risk.residual_level}/8")
    if risk.inherent_score is not None:
        parts.append(f"- Score inherente: {risk.inherent_score}")
    if risk.residual_score is not None:
        parts.append(f"- Score residual: {risk.residual_score}")

    supplier_ctx = _build_supplier_context(db, risk, lang)
    if supplier_ctx:
        parts.append(supplier_ctx)

    return "\n".join(parts)
