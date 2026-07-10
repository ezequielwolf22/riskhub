"""Propagacion cross-plataforma de cambios normativos (Sprint 6).

Cuando el usuario acepta un cambio normativo en el wizard, este modulo:
 1. Aplica el delta al catalogo central de controles (modify/remove).
 2. Propaga el impacto a todos los modelos del tenant:
    - ControlImplementation (SoA)
    - TreatmentTask (crea tareas de revision en riesgos afectados)
    - Policy (marca como "review" si tiene clausulas del framework)
    - BCPPlan (marca como requiriendo revision)
    - SupplierQuestionnaire (marca plantillas desactualizadas)
    - ComplianceFrameworkStatus (marca requisitos afectados)

Principio: no sobreescribir decisiones del cliente; siempre marcar y proponer.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger("riskhub.regwatch.propagation")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Punto de entrada principal ----------

def apply_and_propagate(db: Session, org_id: int, pack: Any, user: Any,
                        decision: dict) -> dict:
    """Punto de entrada unico: aplica catalogo + propaga al tenant.

    Args:
        db: sesion SQLAlchemy abierta.
        org_id: tenant que acepto el cambio.
        pack: instancia ChangePack.
        user: instancia User que tomo la decision.
        decision: dict del wizard ({"action": "apply"|"keep_my_version", ...}).

    Returns:
        Dict con contadores de elementos afectados por categoria.
    """
    results: dict = {
        "action": decision.get("action", "apply"),
        "control_implementations_flagged": 0,
        "policies_flagged": 0,
        "bcp_plans_flagged": 0,
        "supplier_questionnaires_flagged": 0,
        "compliance_requirements_flagged": 0,
        "tasks_created": 0,
        "catalog_controls_updated": 0,
    }

    if decision.get("action") == "keep_my_version":
        # El tenant decide no aplicar. Solo registramos la decision.
        return results

    # 1. Aplicar delta al catalogo central de controles
    results["catalog_controls_updated"] = apply_to_catalog(db, pack)

    # 2. Propagar a elementos del tenant
    propagation = propagate_to_tenant(db, org_id, pack, user)
    results.update(propagation)

    db.flush()
    return results


def apply_to_catalog(db: Session, pack: Any) -> int:
    """Aplica los cambios atomicos del pack al catalogo global de controles.

    - controls_modified: actualiza campos en la tabla 'controls'.
    - controls_removed_ids: marca controles como deprecated.
    - controls_added_ids: no implementado (requiere datos completos del control).
    - Marca pack.applied_to_catalog_at si aun no estaba marcado.

    Devuelve el numero de controles actualizados.
    """
    from app.models import Control

    now = _now()
    updated = 0

    # Actualizar controles modificados
    mods = pack.controls_modified or []
    for mod in mods:
        code = mod.get("control_id") or mod.get("code")
        field = mod.get("field")
        after = mod.get("after")
        if not code or not field:
            continue
        ctrl = db.query(Control).filter(Control.code == code).first()
        if ctrl is None:
            continue
        _safe_update_control_field(ctrl, field, after)
        updated += 1

    # Marcar controles eliminados como deprecados
    removed = pack.controls_removed_ids or []
    if removed:
        deprecated_rows = (
            db.query(Control)
            .filter(Control.code.in_([str(r) for r in removed]))
            .all()
        )
        for ctrl in deprecated_rows:
            if not getattr(ctrl, "deprecated_at", None):
                try:
                    ctrl.deprecated_at = now
                    updated += 1
                except AttributeError:
                    pass  # columna aun no migrada

    # Marcar el pack como aplicado al catalogo
    if not pack.applied_to_catalog_at:
        pack.applied_to_catalog_at = now

    return updated


def _safe_update_control_field(ctrl: Any, field: str, value: Any) -> None:
    """Actualiza un campo permitido del Control. Solo texto/JSON; ignora otros."""
    ALLOWED = {"name", "description", "theme", "control_type", "properties",
               "cybersec_concepts", "operational"}
    if field not in ALLOWED:
        return
    try:
        setattr(ctrl, field, value)
    except Exception:
        pass


# ---------- Propagacion al tenant ----------

def propagate_to_tenant(db: Session, org_id: int, pack: Any, user: Any) -> dict:
    """Propaga el impacto del pack a todos los modulos del tenant.

    No modifica datos de negocio del cliente — los marca para revision.
    Devuelve contadores de elementos afectados.
    """
    results = {
        "control_implementations_flagged": 0,
        "policies_flagged": 0,
        "bcp_plans_flagged": 0,
        "supplier_questionnaires_flagged": 0,
        "compliance_requirements_flagged": 0,
        "tasks_created": 0,
    }

    affected_codes = _get_affected_control_codes(pack)

    # A. ControlImplementation + TreatmentTask
    impl_ids, impl_count = _flag_control_implementations(db, org_id, pack, affected_codes)
    results["control_implementations_flagged"] = impl_count
    results["tasks_created"] = _create_review_tasks(db, org_id, pack, user, impl_ids)

    # B. Politicas
    results["policies_flagged"] = _flag_policies(db, org_id, pack)

    # C. Planes BCP/DRP
    results["bcp_plans_flagged"] = _flag_bcp_plans(db, org_id, pack)

    # D. Cuestionarios de proveedor
    results["supplier_questionnaires_flagged"] = _flag_supplier_questionnaires(db, org_id, pack)

    # E. Requisitos de cumplimiento
    results["compliance_requirements_flagged"] = _update_compliance_requirements(db, org_id, pack)

    return results


def _get_affected_control_codes(pack: Any) -> list[str]:
    """Extrae los codigos de control afectados por el pack (removidos + modificados)."""
    codes: set[str] = set()
    for mod in pack.controls_modified or []:
        code = mod.get("control_id") or mod.get("code")
        if code:
            codes.add(str(code))
    for cid in pack.controls_removed_ids or []:
        codes.add(str(cid))
    return list(codes)


def _flag_control_implementations(db: Session, org_id: int, pack: Any,
                                   affected_codes: list[str]) -> tuple[list[int], int]:
    """Marca las ControlImplementations del tenant afectadas por el pack.

    Busca por codigo de control (join con Control.code). Devuelve (lista_ids, count).
    """
    from app.models import Control, ControlImplementation

    now = _now()
    impl_ids: list[int] = []

    if not affected_codes:
        # Sin codigos concretos: marcar todos los del framework (para breaking changes)
        from app.models import ChangeSeverity
        if pack.severity == ChangeSeverity.BREAKING:
            impls = (
                db.query(ControlImplementation)
                .filter(ControlImplementation.organization_id == org_id)
                .all()
            )
            for impl in impls:
                _set_regwatch_flag(impl, now, pack.id)
                impl_ids.append(impl.id)
            return impl_ids, len(impl_ids)
        return [], 0

    # Buscar controles del catalogo que coincidan con los codigos afectados
    ctrls = db.query(Control).filter(Control.code.in_(affected_codes)).all()
    ctrl_ids = [c.id for c in ctrls]
    if not ctrl_ids:
        return [], 0

    impls = (
        db.query(ControlImplementation)
        .filter(
            ControlImplementation.organization_id == org_id,
            ControlImplementation.control_id.in_(ctrl_ids),
        )
        .all()
    )
    for impl in impls:
        _set_regwatch_flag(impl, now, pack.id)
        impl_ids.append(impl.id)

    return impl_ids, len(impl_ids)


def _set_regwatch_flag(obj: Any, at: datetime, pack_id: int) -> None:
    """Establece los campos de regwatch en un objeto de modelo."""
    try:
        obj.regwatch_review_at = at
    except AttributeError:
        pass
    try:
        obj.regwatch_pack_id = pack_id
    except AttributeError:
        pass


def _create_review_tasks(db: Session, org_id: int, pack: Any, user: Any,
                          impl_ids: list[int]) -> int:
    """Crea TreatmentTasks de revision para riesgos vinculados a las CIs afectadas.

    Reutiliza la tabla risk_controls (risk_id x control_implementation_id).
    Una tarea por riesgo (no duplica si ya hay tarea pendiente del mismo pack).
    """
    from app.models import Risk, RiskStatus, TaskPriority, TaskStatus, TreatmentTask
    import sqlalchemy as sa

    if not impl_ids:
        return 0

    # Buscar riesgos ligados a las CIs afectadas via tabla risk_controls
    try:
        risk_ids_rows = db.execute(
            sa.text(
                "SELECT DISTINCT risk_id FROM risk_controls "
                "WHERE control_implementation_id IN :ids"
            ),
            {"ids": tuple(impl_ids)},
        ).fetchall()
    except Exception:
        return 0

    risk_ids = [r[0] for r in risk_ids_rows]
    if not risk_ids:
        return 0

    # Obtener riesgos activos del tenant
    risks = (
        db.query(Risk)
        .filter(
            Risk.organization_id == org_id,
            Risk.id.in_(risk_ids),
            Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
        )
        .all()
    )

    created = 0
    severity_label = pack.severity.value if pack.severity else "substantive"
    pack_label = f"[RegWatch {pack.framework_code}]"

    for risk in risks:
        # Evitar duplicar tarea si ya existe una pendiente del mismo pack
        dup = (
            db.query(TreatmentTask)
            .filter(
                TreatmentTask.risk_id == risk.id,
                TreatmentTask.title.like(f"%{pack_label}%"),
                TreatmentTask.status == TaskStatus.PENDING,
            )
            .first()
        )
        if dup:
            continue

        # Secuencia de codigo de tarea
        total = db.query(TreatmentTask).filter(
            TreatmentTask.organization_id == org_id
        ).count()
        code = f"TSK-{total + 1:04d}"

        priority = (
            TaskPriority.HIGH if severity_label == "breaking"
            else TaskPriority.MEDIUM
        )

        task = TreatmentTask(
            organization_id=org_id,
            code=code,
            title=f"{pack_label} Revision requerida — cambio normativo {pack.framework_code}",
            description=(
                f"Cambio normativo detectado: {pack.title_es}.\n\n"
                f"{pack.description_es or ''}\n\n"
                f"Este riesgo tiene controles afectados por el cambio. "
                f"Revisa y actualiza el plan de tratamiento si es necesario."
            ),
            risk_id=risk.id,
            assigned_to_id=user.id,
            created_by_id=user.id,
            status=TaskStatus.PENDING,
            priority=priority,
        )
        db.add(task)
        created += 1

    return created


def _flag_policies(db: Session, org_id: int, pack: Any) -> int:
    """Marca politicas del tenant que usan clausulas del framework afectado.

    Para ISO 27001/27002 filtra por iso_clauses. Para el resto (NIS2, GDPR, ENS, DORA)
    marca todas las politicas ya que los marcos regulatorios afectan al SGSI completo.
    """
    from app.models import ChangeSeverity, Policy, PolicyStatus
    from app.services import regwatch_sources as srcs

    now = _now()
    framework = pack.framework_code  # canonical, ej. "ISO_27001", "NIS2"
    compliance_code = srcs.to_compliance_code(framework)  # "iso27001", "nis2", ...

    policies = (
        db.query(Policy)
        .filter(
            Policy.organization_id == org_id,
            Policy.status.notin_([PolicyStatus.OBSOLETE]),
        )
        .all()
    )

    # Para ISO 27001/27002: solo las que tengan clausulas que coincidan
    iso_frameworks = {"ISO_27001", "ISO_27002"}
    affected_codes = _get_affected_control_codes(pack)

    flagged = 0
    for pol in policies:
        should_flag = False

        if framework in iso_frameworks and affected_codes:
            clauses = pol.iso_clauses or []
            if any(str(code) in clauses or str(code).split(".")[0] in clauses
                   for code in affected_codes):
                should_flag = True
        else:
            # Marcos regulatorios (NIS2, GDPR, ENS, DORA): afectan a todas las politicas
            should_flag = True

        if should_flag:
            _set_regwatch_flag(pol, now, pack.id)
            if pol.status == PolicyStatus.PUBLISHED:
                pol.status = PolicyStatus.REVIEW
            flagged += 1

    return flagged


def _flag_bcp_plans(db: Session, org_id: int, pack: Any) -> int:
    """Marca planes BCP/DRP que deben revisarse por el cambio normativo.

    Criterio:
    - "breaking": marca todos los planes del tenant.
    - "substantive" con frameworks de continuidad (NIS2, DORA, ISO_27001): marca todos.
    - Resto: solo si el plan tiene una referencia explicita al framework.
    """
    from app.models import BCPPlan, ChangeSeverity

    now = _now()
    sev = pack.severity
    framework = pack.framework_code

    BCM_RELEVANT_FRAMEWORKS = {"NIS2", "DORA", "ISO_27001", "ENS"}
    if sev not in (ChangeSeverity.BREAKING, ChangeSeverity.SUBSTANTIVE):
        return 0
    if sev == ChangeSeverity.SUBSTANTIVE and framework not in BCM_RELEVANT_FRAMEWORKS:
        return 0

    plans = (
        db.query(BCPPlan)
        .filter(
            BCPPlan.organization_id == org_id,
            BCPPlan.status.notin_(["deprecated"]),
        )
        .all()
    )

    flagged = 0
    for plan in plans:
        _set_regwatch_flag(plan, now, pack.id)
        if plan.status == "approved":
            plan.status = "under_review"
        flagged += 1

    return flagged


def _pack_control_hints(db: Session, pack: Any) -> set[str]:
    """Codigos ISO 27002 que el analisis IA del cambio identifico como afectados.

    Se leen de los NormativeChangeEvent vinculados al pack
    (ai_analysis_json.controls_affected_hint).
    """
    hints: set[str] = set()
    try:
        from app.models import NormativeChangeEvent
        events = (
            db.query(NormativeChangeEvent)
            .filter(NormativeChangeEvent.change_pack_id == pack.id)
            .all()
        )
        for ev in events:
            analysis = ev.ai_analysis_json or {}
            for code in (analysis.get("controls_affected_hint") or []):
                code_norm = str(code).strip().lstrip("A.").strip()
                if code_norm:
                    hints.add(code_norm)
    except Exception:
        logger.debug("regwatch: hints de controles no disponibles", exc_info=True)
    return hints


def _flag_supplier_questionnaires(db: Session, org_id: int, pack: Any) -> int:
    """Marca cuestionarios de proveedor afectados por el cambio normativo.

    Dos criterios de match:
      1. Plantilla del framework afectado (sistema o clonada por el tenant).
      2. Cuestionarios cuyas preguntas referencian (control_refs) los controles
         que el analisis IA identifico como afectados (controls_affected_hint) —
         propagacion dirigida, no solo por codigo de plantilla.
    """
    from app.models import SupplierQuestionnaire, TPRMTemplate
    try:
        from app.services.tprm_templates import SYSTEM_TEMPLATES
    except ImportError:
        return 0

    now = _now()
    framework = pack.framework_code

    # Plantillas del sistema que incluyen el framework afectado
    matching_codes = [
        t["code"] for t in SYSTEM_TEMPLATES
        if framework in (t.get("framework_codes") or [])
    ]

    all_codes: list[str] = []
    if matching_codes:
        # R6: plantillas clonadas por el tenant que descienden de las anteriores
        cloned = (
            db.query(TPRMTemplate)
            .filter(
                TPRMTemplate.organization_id == org_id,
                TPRMTemplate.created_from.in_(matching_codes),
            )
            .all()
        )
        all_codes = list(matching_codes) + [f"custom:{t.id}" for t in cloned]

    questionnaires = []
    seen_ids: set[int] = set()
    if all_codes:
        for q in (
            db.query(SupplierQuestionnaire)
            .filter(
                SupplierQuestionnaire.organization_id == org_id,
                SupplierQuestionnaire.template_code.in_(all_codes),
            )
            .all()
        ):
            questionnaires.append(q)
            seen_ids.add(q.id)

    # 2. Match dirigido por controles afectados segun el analisis IA
    hints = _pack_control_hints(db, pack)
    if hints:
        candidates = (
            db.query(SupplierQuestionnaire)
            .filter(SupplierQuestionnaire.organization_id == org_id)
            .all()
        )
        for q in candidates:
            if q.id in seen_ids:
                continue
            refs: set[str] = set()
            for question in (q.questions or []):
                for ref in (question.get("control_refs") or []):
                    refs.add(str(ref).strip().lstrip("A.").strip())
            if refs & hints:
                questionnaires.append(q)
                seen_ids.add(q.id)

    if not questionnaires:
        return 0

    flagged = 0
    for q in questionnaires:
        _set_regwatch_flag(q, now, pack.id)
        flagged += 1

    # R4: crear VendorIssue automatico para que el analista TPRM reciba accion
    _create_vendor_issues_from_regwatch(db, org_id, pack, questionnaires)

    return flagged


def _create_vendor_issues_from_regwatch(db: Session, org_id: int, pack: Any,
                                         questionnaires: list) -> None:
    """Crea un VendorIssue por proveedor afectado por el cambio normativo.

    Evita duplicados: no crea issue si ya existe uno abierto del mismo pack para ese proveedor.
    """
    try:
        from app.models import (
            VendorIssue, VendorIssueSeverity, VendorIssueStatus,
        )
        from datetime import timedelta
    except ImportError:
        return

    now = _now()
    sev = VendorIssueSeverity.HIGH if getattr(pack, "severity", None) and pack.severity.value == "breaking" else VendorIssueSeverity.MEDIUM
    pack_label = f"[RegWatch {pack.framework_code}]"

    # Agrupar cuestionarios por proveedor para crear un issue por proveedor, no por cuestionario
    supplier_ids_seen: set[int] = set()
    for q in questionnaires:
        sup_id = getattr(q, "supplier_id", None)
        if not sup_id or sup_id in supplier_ids_seen:
            continue
        supplier_ids_seen.add(sup_id)

        # Dedup: no crear si ya existe issue abierto del mismo pack
        dup = db.query(VendorIssue).filter(
            VendorIssue.organization_id == org_id,
            VendorIssue.supplier_id == sup_id,
            VendorIssue.title.like(f"%{pack_label}%"),
            VendorIssue.status.notin_([VendorIssueStatus.CLOSED.value, VendorIssueStatus.MITIGATED.value]),
        ).first()
        if dup:
            continue

        n = db.query(VendorIssue).filter(VendorIssue.organization_id == org_id).count() + 1
        issue = VendorIssue(
            organization_id=org_id,
            code=f"VIS-{n:04d}",
            supplier_id=sup_id,
            source="regwatch",
            title=f"{pack_label} Revision de cuestionario TPRM — cambio en {pack.framework_code}",
            description=(
                f"Cambio normativo detectado: {pack.title_es}.\n\n"
                f"{pack.description_es or ''}\n\n"
                f"Revisa si el cuestionario TPRM del proveedor refleja los nuevos requisitos "
                f"y considera re-enviar un cuestionario actualizado."
            ),
            severity=sev,
            status=VendorIssueStatus.OPEN,
            framework_refs=[pack.framework_code],
            discovered_at=now,
            due_date=now + timedelta(days=30),
            auto_generated=True,
            auto_generated_source="regwatch",
        )
        db.add(issue)
    try:
        db.flush()
    except Exception as exc:
        logger.warning("regwatch: error creando VendorIssues: %s", exc)


def _update_compliance_requirements(db: Session, org_id: int, pack: Any) -> int:
    """Marca requisitos de compliance del tenant que se ven afectados.

    Para controles eliminados o modificados del framework, baja la fecha
    de revision (last_reviewed_at = None fuerza re-evaluacion) y establece
    regwatch_review_at.
    """
    from app.models import ComplianceFrameworkStatus
    from app.services import regwatch_sources as srcs

    now = _now()
    compliance_code = srcs.to_compliance_code(pack.framework_code)
    if not compliance_code:
        return 0
    affected_codes = _get_affected_control_codes(pack)

    q = db.query(ComplianceFrameworkStatus).filter(
        ComplianceFrameworkStatus.organization_id == org_id,
        ComplianceFrameworkStatus.framework_code == compliance_code,
    )

    # Si tenemos codigos concretos, solo los afectados; si no, todos del framework
    if affected_codes:
        q = q.filter(ComplianceFrameworkStatus.requirement_id.in_(affected_codes))

    reqs = q.all()
    flagged = 0
    for req in reqs:
        _set_regwatch_flag(req, now, pack.id)
        req.last_reviewed_at = None  # fuerza re-evaluacion tras cambio normativo
        flagged += 1

    return flagged


# ---------- Utilidad: compute_impact extendido ----------

def compute_full_impact(db: Session, org_id: int, pack: Any) -> dict:
    """Calculo de impacto completo para el wizard (paso 1 del inbox).

    Extiende compute_impact del regwatch_service con contadores mas precisos
    de control_implementations, riesgos y planes BCP.
    """
    from app.models import BCPPlan, Control, ControlImplementation, Policy, Risk, SupplierQuestionnaire
    from app.services import regwatch_sources as srcs

    compliance_code = srcs.to_compliance_code(pack.framework_code)
    from app.models import ComplianceFrameworkStatus

    affected_codes = _get_affected_control_codes(pack)
    impact: dict = {
        "policies": 0,
        "compliance_requirements": 0,
        "control_implementations": 0,
        "risks": 0,
        "bcp_plans": 0,
        "supplier_questionnaires": 0,
    }

    try:
        impact["policies"] = db.query(Policy).filter(
            Policy.organization_id == org_id
        ).count()
    except Exception:
        pass

    try:
        impact["compliance_requirements"] = db.query(ComplianceFrameworkStatus).filter(
            ComplianceFrameworkStatus.organization_id == org_id,
            ComplianceFrameworkStatus.framework_code == compliance_code,
        ).count()
    except Exception:
        pass

    if affected_codes:
        try:
            ctrls = db.query(Control).filter(Control.code.in_(affected_codes)).all()
            ctrl_ids = [c.id for c in ctrls]
            if ctrl_ids:
                impact["control_implementations"] = db.query(ControlImplementation).filter(
                    ControlImplementation.organization_id == org_id,
                    ControlImplementation.control_id.in_(ctrl_ids),
                ).count()
        except Exception:
            pass

    try:
        impact["bcp_plans"] = db.query(BCPPlan).filter(
            BCPPlan.organization_id == org_id,
            BCPPlan.status.notin_(["deprecated"]),
        ).count()
    except Exception:
        pass

    return impact
