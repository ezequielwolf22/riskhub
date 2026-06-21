"""Servicio central de ciclo de vida de proveedores y bucle cerrado de mitigacion.

Principio: cada elevacion automatica de riesgo tiene una condicion de resolucion.
Cuando el usuario toma acciones mitigadoras, este servicio detecta el cambio y
reduce el riesgo/KRI/issue automaticamente.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ------- Checklist de onboarding -------

_CHECKLIST_TEMPLATES = [
    # item siempre presente
    {"id": "questionnaire", "title": "Cuestionario de seguridad enviado y respondido", "category": "security", "required": True, "condition": "always"},
    {"id": "risk_assessment", "title": "Evaluacion de riesgo inicial completada", "category": "security", "required": True, "condition": "always"},
    # GDPR
    {"id": "dpa", "title": "Acuerdo de Tratamiento de Datos (DPA) firmado — GDPR Art.28", "category": "legal", "required": True, "condition": "is_data_processor"},
    {"id": "cross_border", "title": "Clausulas de transferencia internacional firmadas", "category": "legal", "required": True, "condition": "cross_border_transfers"},
    # NIS2 / DORA
    {"id": "nis2_clause", "title": "Clausula NIS2 incluida en contrato (Art.21)", "category": "compliance", "required": True, "condition": "is_nis2"},
    {"id": "dora_ict_category", "title": "Clasificacion DORA ICT (critical/important) asignada — Art.28", "category": "compliance", "required": True, "condition": "is_dora"},
    {"id": "dora_exit_strategy", "title": "Estrategia de salida documentada — DORA Art.28(8)", "category": "compliance", "required": True, "condition": "is_dora"},
    # Tier-1
    {"id": "tier1_assessment", "title": "Assessment formal completado (tier-1 obligatorio en 30 dias)", "category": "security", "required": True, "condition": "tier_1"},
    {"id": "nda", "title": "NDA / acuerdo de confidencialidad firmado", "category": "legal", "required": False, "condition": "always"},
    # Contrato
    {"id": "contract_uploaded", "title": "Contrato subido al sistema", "category": "legal", "required": False, "condition": "always"},
    {"id": "sla_defined", "title": "SLAs definidos y documentados", "category": "operational", "required": False, "condition": "always"},
    {"id": "contacts_verified", "title": "Contactos del proveedor verificados", "category": "operational", "required": False, "condition": "always"},
]


def generate_onboarding_checklist(supplier) -> list[dict]:
    """Genera la lista de items de onboarding aplicables a este proveedor."""
    items = []
    for tmpl in _CHECKLIST_TEMPLATES:
        cond = tmpl["condition"]
        applicable = False
        if cond == "always":
            applicable = True
        elif cond == "is_data_processor":
            applicable = bool(supplier.is_data_processor or supplier.processes_personal_data)
        elif cond == "cross_border_transfers":
            applicable = bool(supplier.cross_border_transfers)
        elif cond == "is_nis2":
            applicable = bool(supplier.is_nis2)
        elif cond == "is_dora":
            applicable = bool(supplier.is_dora)
        elif cond == "tier_1":
            applicable = (str(getattr(supplier.tier, 'value', supplier.tier) if supplier.tier else '') == 'tier_1')

        if applicable:
            items.append({
                "id": tmpl["id"],
                "title": tmpl["title"],
                "category": tmpl["category"],
                "required": tmpl["required"],
                "completed": False,
                "completed_at": None,
                "completed_by_id": None,
                "evidence_doc_id": None,
            })
    return items


def checklist_completion_pct(checklist: list[dict]) -> float:
    """Calcula el porcentaje de completitud del checklist (solo items required)."""
    if not checklist:
        return 100.0
    required = [i for i in checklist if i.get("required")]
    if not required:
        return 100.0
    done = sum(1 for i in required if i.get("completed"))
    return round(done / len(required) * 100, 1)


# ------- Recomputo central de perfil de riesgo del proveedor -------

def recompute_supplier_risk_profile(db, supplier_id: int, triggered_by: str = "manual") -> dict:
    """Recomputa el perfil de riesgo de un proveedor y cierra bucles de mitigacion.

    Llama a esto cuando:
    - VendorIssue cambia de estado
    - Checklist item marcado como completado
    - DPA/NDA firmado
    - Cuestionario enviado/respondido
    - Assessment aprobado
    - Contrato renovado
    - Concentracion de riesgo cambia
    - BCPDependency anadida/eliminada
    """
    from app.models import Supplier, VendorIssue, VendorIssueStatus, VendorIssueSeverity, Risk, RiskStatus
    from app.services.tprm_scoring_service import recompute_supplier as _recompute

    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        return {"ok": False, "error": "supplier not found"}

    result = {"supplier_id": supplier_id, "triggered_by": triggered_by, "changes": []}

    # 1. Recomputar score TPRM
    try:
        old_score = supplier.residual_risk_score or 0
        _recompute(db, supplier)
        new_score = supplier.residual_risk_score or 0
        if abs(new_score - old_score) >= 2:
            result["changes"].append(f"score: {old_score} → {new_score}")
    except Exception as e:
        logger.warning("recompute_supplier score failed sup=%d: %s", supplier_id, e)

    # 2. Actualizar lifecycle_stage si el onboarding esta completo
    checklist = supplier.onboarding_checklist or []
    if checklist and supplier.lifecycle_stage == "onboarding":
        pct = checklist_completion_pct(checklist)
        if pct >= 100.0:
            supplier.lifecycle_stage = "active"
            supplier.onboarding_completed_at = datetime.now(timezone.utc)
            result["changes"].append("lifecycle: onboarding → active")

    # 3. Resolver VendorIssues auto-generados si la condicion que los creo ya no existe
    _resolve_stale_auto_issues(db, supplier, result)

    # 4. Re-evaluar KRIs vinculados al proveedor
    _reevaluate_supplier_kris(db, supplier, result)

    # 5. Actualizar riesgos vinculados al proveedor
    _update_linked_risks(db, supplier, result)

    # 6. Revision de concentracion de riesgo
    _check_concentration_flag(db, supplier, result)

    db.commit()
    return result


def _resolve_stale_auto_issues(db, supplier, result: dict) -> None:
    """Cierra VendorIssues auto-generados cuya condicion de origen ya no aplica."""
    from app.models import VendorIssue, VendorIssueStatus
    now = datetime.now(timezone.utc)

    auto_issues = db.query(VendorIssue).filter(
        VendorIssue.supplier_id == supplier.id,
        VendorIssue.auto_generated == True,
        VendorIssue.status.notin_([VendorIssueStatus.CLOSED, VendorIssueStatus.MITIGATED, VendorIssueStatus.ACCEPTED]),
    ).all()

    for issue in auto_issues:
        src = issue.auto_generated_source or ""
        should_resolve = False
        resolution = ""

        if src == "score_decay":
            # Resuelto cuando el proveedor es reevaluado recientemente
            if supplier.last_assessment_at:
                days_since = (now - supplier.last_assessment_at.replace(tzinfo=timezone.utc)).days
                if days_since < 365:
                    should_resolve = True
                    resolution = "Proveedor reevaluado"

        elif src == "concentration":
            # Resuelto cuando concentration_risk_flag vuelve a False
            if not supplier.concentration_risk_flag:
                should_resolve = True
                resolution = "Concentracion de riesgo reducida por accion del usuario"

        elif src == "contract_expiry":
            # Resuelto cuando contract_expiry esta en el futuro (>90 dias)
            if supplier.contract_expiry:
                days_to_expiry = (supplier.contract_expiry.replace(tzinfo=timezone.utc) - now).days
                if days_to_expiry > 90:
                    should_resolve = True
                    resolution = "Contrato renovado"

        elif src == "dpa_missing":
            # Resuelto cuando se firma el DPA
            if supplier.dpa_signed_at:
                should_resolve = True
                resolution = "DPA firmado"

        if should_resolve:
            issue.status = VendorIssueStatus.CLOSED
            issue.closed_at = now
            issue.resolved_by_action = resolution
            result["changes"].append(f"auto-issue {issue.code} cerrado: {resolution}")


def _reevaluate_supplier_kris(db, supplier, result: dict) -> None:
    """Re-evalua KRIs que dependen de datos del proveedor."""
    from app.models import KRI
    from app.routers.kris import evaluate_kri
    kris = db.query(KRI).filter(
        KRI.organization_id == supplier.organization_id,
        KRI.is_active == True,
        KRI.metric_type.in_([
            "kpi_supplier_coverage", "kpi_supplier_contract_expiry",
            "kpi_supplier_critical_issues", "kpi_vendor_issue_mttr",
            "kpi_dora_suppliers_assessed",
        ]),
    ).all()
    for kri in kris:
        try:
            evaluate_kri(db, kri, supplier.organization_id)
        except Exception as e:
            logger.debug("KRI eval failed kri=%d: %s", kri.id, e)


def _update_linked_risks(db, supplier, result: dict) -> None:
    """Actualiza el inherent_likelihood de riesgos vinculados al proveedor."""
    from app.models import Risk, RiskStatus
    from app.routers.risks import _recalc

    if supplier.residual_risk_score is None:
        return

    score = supplier.residual_risk_score
    # Mapeo score TPRM (0-100, mayor=mas riesgo) a likelihood ISO 27005 (0-4)
    new_lik = 3 if score >= 70 else (2 if score >= 50 else (1 if score >= 30 else 0))

    risks = db.query(Risk).filter(
        Risk.supplier_id == supplier.id,
        Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
    ).all()

    updated = 0
    for r in risks:
        if r.inherent_likelihood != new_lik:
            r.inherent_likelihood = new_lik
            try:
                _recalc(db, r)
                updated += 1
            except Exception as e:
                logger.debug("Risk recalc failed risk=%d: %s", r.id, e)

    if updated:
        result["changes"].append(f"{updated} riesgo(s) vinculados recalculados")


def _check_concentration_flag(db, supplier, result: dict) -> None:
    """Verifica si la concentracion de riesgo del proveedor ha cambiado."""
    from app.models import BusinessProcess, BCPDependency
    critical_procs = db.query(BusinessProcess).filter(
        BusinessProcess.organization_id == supplier.organization_id,
        BusinessProcess.criticality == "critical",
    ).all()
    if not critical_procs:
        if supplier.concentration_risk_flag:
            supplier.concentration_risk_flag = False
            result["changes"].append("concentracion: flag eliminado (sin procesos criticos)")
        return

    deps_for_supplier = db.query(BCPDependency).filter(
        BCPDependency.supplier_id == supplier.id,
    ).all()
    proc_ids_with_dep = {d.process_id for d in deps_for_supplier}
    critical_proc_ids = {p.id for p in critical_procs}
    overlap = proc_ids_with_dep & critical_proc_ids
    pct = len(overlap) / len(critical_procs) * 100 if critical_procs else 0

    was_flagged = supplier.concentration_risk_flag
    supplier.concentration_risk_flag = pct > 40.0

    if not was_flagged and supplier.concentration_risk_flag:
        result["changes"].append(f"concentracion: nuevo flag ({pct:.0f}% procesos criticos)")
        _create_concentration_vendor_issue(db, supplier, pct)
    elif was_flagged and not supplier.concentration_risk_flag:
        result["changes"].append(f"concentracion: flag eliminado ({pct:.0f}% < 40%)")


def _create_concentration_vendor_issue(db, supplier, pct: float) -> None:
    """Crea un VendorIssue de concentracion de riesgo (DORA Art.28)."""
    from app.models import VendorIssue, VendorIssueSeverity, VendorIssueStatus
    existing = db.query(VendorIssue).filter(
        VendorIssue.supplier_id == supplier.id,
        VendorIssue.auto_generated_source == "concentration",
        VendorIssue.status.notin_([VendorIssueStatus.CLOSED, VendorIssueStatus.MITIGATED]),
    ).first()
    if existing:
        return
    n = db.query(VendorIssue).filter(VendorIssue.organization_id == supplier.organization_id).count() + 1
    issue = VendorIssue(
        organization_id=supplier.organization_id,
        code=f"VIS-{n:04d}",
        supplier_id=supplier.id,
        source="monitoring",
        title=f"Concentracion de riesgo: {pct:.0f}% de procesos criticos dependen de este proveedor",
        description=(
            f"El proveedor {supplier.name} concentra el {pct:.1f}% de los procesos de negocio "
            f"criticos que dependen de el (umbral DORA: 40%). Acciones posibles: "
            f"(1) distribuir dependencias entre proveedores alternativos, "
            f"(2) documentar el plan de salida en el campo 'Estrategia de salida', "
            f"(3) anadir nuevas dependencias a otros proveedores que reduzcan la concentracion, "
            f"(4) anadir notas de mitigacion en el campo 'Notas de concentracion'."
        ),
        severity=VendorIssueSeverity.HIGH,
        status=VendorIssueStatus.OPEN,
        auto_generated=True,
        auto_generated_source="concentration",
        due_date=datetime.now(timezone.utc) + timedelta(days=90),
        created_at=datetime.now(timezone.utc),
    )
    db.add(issue)


# ------- Concentracion de riesgo para el endpoint de TPRM -------

def compute_concentration_risk(db, org_id: int) -> list[dict]:
    """Calcula el riesgo de concentracion por proveedor para toda la organizacion."""
    from app.models import Supplier, BusinessProcess, BCPDependency

    critical_procs = db.query(BusinessProcess).filter(
        BusinessProcess.organization_id == org_id,
        BusinessProcess.criticality == "critical",
    ).all()
    total_critical = len(critical_procs)
    if not total_critical:
        return []

    critical_proc_ids = {p.id: p for p in critical_procs}

    suppliers = db.query(Supplier).filter(
        Supplier.organization_id == org_id,
    ).all()

    results = []
    for sup in suppliers:
        deps = db.query(BCPDependency).filter(
            BCPDependency.supplier_id == sup.id,
        ).all()
        dep_proc_ids = {d.process_id for d in deps if d.process_id in critical_proc_ids}
        pct = len(dep_proc_ids) / total_critical * 100 if total_critical else 0

        if pct > 0 or sup.concentration_risk_flag:
            # Sync the flag
            new_flag = pct > 40.0
            if sup.concentration_risk_flag != new_flag:
                sup.concentration_risk_flag = new_flag
                if new_flag:
                    _create_concentration_vendor_issue(db, sup, pct)

            results.append({
                "supplier_id": sup.id,
                "supplier_code": sup.code,
                "supplier_name": sup.name,
                "tier": sup.tier.value if sup.tier else None,
                "critical_processes_dependent": len(dep_proc_ids),
                "total_critical_processes": total_critical,
                "concentration_pct": round(pct, 1),
                "is_critical": pct > 40.0,
                "processes": [{"id": pid, "name": critical_proc_ids[pid].name} for pid in dep_proc_ids],
                "mitigation": {
                    "exit_strategy": sup.exit_strategy,
                    "notes": sup.concentration_risk_notes,
                    "mitigated_at": sup.concentration_risk_mitigated_at.isoformat() if sup.concentration_risk_mitigated_at else None,
                },
            })

    db.commit()
    return sorted(results, key=lambda x: -x["concentration_pct"])
