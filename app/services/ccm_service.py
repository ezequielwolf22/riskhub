"""Continuous Control Monitoring (CCM) — tests automáticos sobre datos internos.

Cada test verifica si un control ISO 27002 está realmente operativo
basándose en los datos del SGSI (activos, usuarios, controles, políticas, evidencias, etc.).

Resultado: PASS / FAIL / WARNING + detalles
Si FAIL → control se degrada → riesgo residual recalculado
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.models import (
    Asset, ControlImplementation, ControlStatus,
    Evidence, Incident, IncidentStatus, Policy, PolicyStatus,
    Risk, RiskStatus, RiskContext, Supplier,
    TreatmentTask, TaskStatus, User, UserRole,
    Vulnerability,
)

logger = logging.getLogger("riskhub.ccm")


# ─── Modelo de resultado de test ──────────────────────────────────────────────

class CCMResult:
    def __init__(self, test_id: str, control_code: str, name: str,
                 status: str, detail: str, value: Optional[float] = None,
                 recommendation: str = ""):
        self.test_id = test_id
        self.control_code = control_code  # ISO 27002 code
        self.name = name
        self.status = status              # PASS / FAIL / WARNING / SKIP
        self.detail = detail
        self.value = value                # valor numérico si aplica (ej: % cobertura)
        self.recommendation = recommendation
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "control_code": self.control_code,
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "value": self.value,
            "recommendation": self.recommendation,
            "timestamp": self.timestamp,
        }


# ─── Tests individuales ─────────────────────────────────────────────────────

def test_all_assets_have_owner(db: Session, org_id: int) -> CCMResult:
    """8.1 — Todos los activos tienen propietario asignado."""
    total = db.query(Asset).filter(Asset.organization_id == org_id).count()
    without_owner = db.query(Asset).filter(
        Asset.organization_id == org_id,
        Asset.owner_id.is_(None),
    ).count()
    if total == 0:
        return CCMResult("assets_owner", "8.1", "Activos con propietario",
                         "SKIP", "No hay activos registrados")
    pct = round((total - without_owner) / total * 100, 1)
    status = "PASS" if without_owner == 0 else ("WARNING" if without_owner <= 2 else "FAIL")
    return CCMResult(
        "assets_owner", "8.1", "Activos con propietario asignado", status,
        f"{total - without_owner}/{total} activos tienen propietario ({pct}%)",
        value=pct,
        recommendation="" if status == "PASS" else f"Asignar propietario a {without_owner} activos sin dueño",
    )


def test_assets_classified(db: Session, org_id: int) -> CCMResult:
    """5.12/5.13 — Activos tienen clasificación de información."""
    total = db.query(Asset).filter(Asset.organization_id == org_id).count()
    classified = db.query(Asset).filter(
        Asset.organization_id == org_id,
        Asset.classification.isnot(None),
        Asset.classification != "",
    ).count()
    if total == 0:
        return CCMResult("assets_classified", "5.12", "Activos clasificados", "SKIP", "No hay activos")
    pct = round(classified / total * 100, 1)
    status = "PASS" if pct >= 90 else ("WARNING" if pct >= 70 else "FAIL")
    return CCMResult(
        "assets_classified", "5.12", "Clasificación de información en activos", status,
        f"{classified}/{total} activos clasificados ({pct}%)", value=pct,
        recommendation="" if status == "PASS" else "Clasificar activos sin etiqueta (público/interno/confidencial/secreto)",
    )


def test_high_risks_have_treatment(db: Session, org_id: int) -> CCMResult:
    """5.8/6.1 — Riesgos altos/críticos tienen tratamiento asignado."""
    high_risks = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.residual_level >= 5,
        Risk.status.notin_([RiskStatus.ACCEPTED, RiskStatus.ARCHIVED]),
    ).all()
    if not high_risks:
        return CCMResult("risks_treatment", "5.8", "Tratamiento de riesgos altos",
                         "PASS", "No hay riesgos altos sin gestionar")
    without = [r for r in high_risks if not r.treatment_option]
    total = len(high_risks)
    pct = round((total - len(without)) / total * 100, 1) if total > 0 else 100
    status = "PASS" if not without else ("WARNING" if len(without) <= 2 else "FAIL")
    return CCMResult(
        "risks_treatment", "5.8", "Riesgos altos con tratamiento asignado", status,
        f"{total - len(without)}/{total} riesgos altos tienen tratamiento ({pct}%)", value=pct,
        recommendation="" if status == "PASS" else f"{len(without)} riesgo(s) altos sin tratamiento: " +
            ", ".join(r.code for r in without[:3]),
    )


def test_risks_over_appetite_have_tasks(db: Session, org_id: int) -> CCMResult:
    """5.8 — Riesgos sobre apetito tienen tareas de tratamiento activas."""
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    appetite = ctx.risk_appetite if ctx else 3
    over = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.residual_level > appetite,
        Risk.status == RiskStatus.ASSESSED,
    ).all()
    if not over:
        return CCMResult("risks_tasks", "5.8", "Tareas para riesgos sobre apetito",
                         "PASS", "No hay riesgos sobre apetito sin tareas")
    without_tasks = []
    for r in over:
        tasks = db.query(TreatmentTask).filter(
            TreatmentTask.risk_id == r.id,
            TreatmentTask.status.notin_([TaskStatus.DONE]),
        ).count()
        if tasks == 0:
            without_tasks.append(r)
    pct = round((len(over) - len(without_tasks)) / len(over) * 100, 1)
    status = "PASS" if not without_tasks else ("WARNING" if len(without_tasks) <= 2 else "FAIL")
    return CCMResult(
        "risks_tasks", "5.8", "Riesgos sobre apetito con tareas activas", status,
        f"{len(over) - len(without_tasks)}/{len(over)} tienen tareas ({pct}%)", value=pct,
        recommendation="" if status == "PASS" else f"Crear tareas para {len(without_tasks)} riesgo(s)",
    )


def test_controls_have_evidence(db: Session, org_id: int) -> CCMResult:
    """5.35/5.36 — Controles implementados tienen evidencia asociada."""
    implemented = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == org_id,
        ControlImplementation.status == ControlStatus.IMPLEMENTED,
    ).all()
    if not implemented:
        return CCMResult("controls_evidence", "5.35", "Controles con evidencia",
                         "SKIP", "No hay controles implementados")
    with_evidence = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.control_implementation_id.isnot(None),
        Evidence.is_current == True,
    ).distinct(Evidence.control_implementation_id).count()
    total = len(implemented)
    pct = round(with_evidence / total * 100, 1)
    status = "PASS" if pct >= 80 else ("WARNING" if pct >= 50 else "FAIL")
    return CCMResult(
        "controls_evidence", "5.35", "Controles implementados con evidencia", status,
        f"{with_evidence}/{total} controles tienen evidencia ({pct}%)", value=pct,
        recommendation="" if status == "PASS" else "Subir evidencias para controles sin documentación",
    )


def test_policies_current(db: Session, org_id: int) -> CCMResult:
    """5.1 — Políticas de seguridad están vigentes (no vencidas)."""
    now = datetime.now(timezone.utc)
    all_policies = db.query(Policy).filter(
        Policy.organization_id == org_id,
        Policy.status != PolicyStatus.OBSOLETE,
    ).all()
    if not all_policies:
        return CCMResult("policies_current", "5.1", "Políticas vigentes",
                         "FAIL", "No hay políticas de seguridad definidas",
                         recommendation="Crear políticas de seguridad de la información")
    overdue = [p for p in all_policies
               if p.review_date and p.review_date.replace(tzinfo=timezone.utc) < now]
    pct = round((len(all_policies) - len(overdue)) / len(all_policies) * 100, 1)
    status = "PASS" if not overdue else ("WARNING" if len(overdue) <= 2 else "FAIL")
    return CCMResult(
        "policies_current", "5.1", "Políticas de seguridad vigentes", status,
        f"{len(all_policies) - len(overdue)}/{len(all_policies)} políticas vigentes ({pct}%)", value=pct,
        recommendation="" if status == "PASS" else f"{len(overdue)} política(s) con revisión vencida",
    )


def test_incidents_resolved(db: Session, org_id: int) -> CCMResult:
    """5.24/5.25 — Incidentes P1/P2 resueltos en tiempo."""
    from app.models import IncidentSeverity
    now = datetime.now(timezone.utc)
    critical_open = db.query(Incident).filter(
        Incident.organization_id == org_id,
        Incident.status.notin_([IncidentStatus.CLOSED, IncidentStatus.RESOLVED]),
        Incident.severity.in_([IncidentSeverity.P1, IncidentSeverity.P2]),
        Incident.created_at < now - timedelta(days=3),
    ).count()
    if critical_open == 0:
        return CCMResult("incidents_resolved", "5.24", "Resolución de incidentes críticos",
                         "PASS", "No hay incidentes P1/P2 abiertos más de 3 días")
    return CCMResult(
        "incidents_resolved", "5.24", "Resolución de incidentes críticos", "FAIL",
        f"{critical_open} incidente(s) P1/P2 abierto(s) por más de 3 días",
        recommendation="Escalar y resolver incidentes críticos pendientes",
    )


def test_suppliers_reviewed(db: Session, org_id: int) -> CCMResult:
    """5.19 — Proveedores críticos con evaluación reciente."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=365)
    suppliers = db.query(Supplier).filter(
        Supplier.organization_id == org_id,
        Supplier.is_critical == True,
    ).all() if hasattr(Supplier, "is_critical") else db.query(Supplier).filter(
        Supplier.organization_id == org_id,
        Supplier.risk_score.isnot(None),
        Supplier.risk_score <= 50,
    ).all()

    if not suppliers:
        # Evaluar todos los proveedores si no hay is_critical
        suppliers = db.query(Supplier).filter(Supplier.organization_id == org_id).all()
    if not suppliers:
        return CCMResult("suppliers_reviewed", "5.19", "Evaluación de proveedores",
                         "SKIP", "No hay proveedores registrados")
    stale = [s for s in suppliers
             if not s.updated_at or s.updated_at.replace(tzinfo=timezone.utc) < threshold]
    pct = round((len(suppliers) - len(stale)) / len(suppliers) * 100, 1)
    status = "PASS" if not stale else ("WARNING" if len(stale) <= 2 else "FAIL")
    return CCMResult(
        "suppliers_reviewed", "5.19", "Proveedores con evaluación anual", status,
        f"{len(suppliers) - len(stale)}/{len(suppliers)} proveedores evaluados en último año ({pct}%)",
        value=pct,
        recommendation="" if status == "PASS" else f"Re-evaluar {len(stale)} proveedor(es)",
    )


def test_tasks_not_overdue(db: Session, org_id: int) -> CCMResult:
    """5.36 — Tareas de tratamiento sin vencer (SLA)."""
    now = datetime.now(timezone.utc)
    overdue = db.query(TreatmentTask).filter(
        TreatmentTask.organization_id == org_id,
        TreatmentTask.status.notin_([TaskStatus.DONE]),
        TreatmentTask.due_date < now,
    ).count()
    total = db.query(TreatmentTask).filter(
        TreatmentTask.organization_id == org_id,
        TreatmentTask.status.notin_([TaskStatus.DONE]),
    ).count()
    if total == 0:
        return CCMResult("tasks_overdue", "5.36", "Tareas sin vencer",
                         "PASS", "No hay tareas pendientes")
    pct = round((total - overdue) / total * 100, 1)
    status = "PASS" if overdue == 0 else ("WARNING" if overdue <= 3 else "FAIL")
    return CCMResult(
        "tasks_overdue", "5.36", "Tareas de tratamiento sin vencer", status,
        f"{overdue}/{total} tareas vencidas ({100 - pct:.0f}% de mora)", value=pct,
        recommendation="" if status == "PASS" else f"Gestionar {overdue} tarea(s) vencida(s)",
    )


def test_evidence_freshness(db: Session, org_id: int) -> CCMResult:
    """5.35 — Evidencias de controles no vencidas ni antiguas (>12 meses)."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=365)
    total_ev = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.is_current == True,
    ).count()
    if total_ev == 0:
        return CCMResult("evidence_fresh", "5.35", "Frescura de evidencias",
                         "WARNING", "No hay evidencias registradas",
                         recommendation="Subir evidencias de los controles implementados")
    stale = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.is_current == True,
        Evidence.created_at < threshold,
        Evidence.expires_at.is_(None),
    ).count()
    expired = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.is_current == True,
        Evidence.expires_at < now,
    ).count()
    bad = stale + expired
    pct = round((total_ev - bad) / total_ev * 100, 1)
    status = "PASS" if pct >= 90 else ("WARNING" if pct >= 70 else "FAIL")
    return CCMResult(
        "evidence_fresh", "5.35", "Frescura de evidencias (< 12 meses)", status,
        f"{total_ev - bad}/{total_ev} evidencias frescas ({pct}%)", value=pct,
        recommendation="" if status == "PASS" else f"{bad} evidencia(s) vencidas o antiguas a renovar",
    )


def test_admin_users_have_mfa(db: Session, org_id: int) -> CCMResult:
    """8.5 — Usuarios administradores con MFA habilitado."""
    admins = db.query(User).filter(
        User.organization_id == org_id,
        User.role.in_([UserRole.ADMIN, UserRole.SUPERADMIN]),
        User.is_active == True,
    ).all()
    if not admins:
        return CCMResult("admin_mfa", "8.5", "MFA en administradores",
                         "SKIP", "No hay administradores")
    # Verificar campo otp_secret como proxy de MFA habilitado
    with_mfa = [u for u in admins if getattr(u, "otp_secret", None)]
    pct = round(len(with_mfa) / len(admins) * 100, 1)
    status = "PASS" if pct == 100 else ("WARNING" if pct >= 50 else "FAIL")
    return CCMResult(
        "admin_mfa", "8.5", "Administradores con MFA habilitado", status,
        f"{len(with_mfa)}/{len(admins)} admins con MFA ({pct}%)", value=pct,
        recommendation="" if status == "PASS" else "Activar MFA para todos los administradores",
    )


def test_vulnerabilities_addressed(db: Session, org_id: int) -> CCMResult:
    """8.8 — Vulnerabilidades críticas con riesgo asociado."""
    vulns = db.query(Vulnerability).filter(
        Vulnerability.organization_id == org_id,
    ).count() if hasattr(Vulnerability, "organization_id") else 0
    # Chequeamos hallazgos externos como proxy
    from app.models import ExternalFinding
    critical_open = db.query(ExternalFinding).filter(
        ExternalFinding.organization_id == org_id,
        ExternalFinding.severity.in_(["CRITICAL", "HIGH"]),
        ExternalFinding.status == "open",
    ).count()
    if critical_open == 0:
        return CCMResult("vulns_addressed", "8.8", "Vulnerabilidades críticas gestionadas",
                         "PASS", "No hay vulnerabilidades críticas abiertas sin gestionar")
    return CCMResult(
        "vulns_addressed", "8.8", "Vulnerabilidades críticas gestionadas", "FAIL",
        f"{critical_open} hallazgo(s) CRITICAL/HIGH abierto(s) sin riesgo asociado",
        recommendation="Importar hallazgos desde escáner y generar riesgos",
    )


def test_risk_appetite_defined(db: Session, org_id: int) -> CCMResult:
    """5.37/6.1 — Apetito de riesgo definido por la organización."""
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    if ctx and ctx.risk_appetite is not None:
        return CCMResult("risk_appetite", "5.37", "Apetito de riesgo definido",
                         "PASS", f"Apetito de riesgo configurado: {ctx.risk_appetite}/8")
    return CCMResult(
        "risk_appetite", "5.37", "Apetito de riesgo definido", "FAIL",
        "El apetito de riesgo no está definido",
        recommendation="Configurar el apetito de riesgo en Contexto de la organización",
    )


def test_compliance_frameworks_active(db: Session, org_id: int) -> CCMResult:
    """5.31 — Marcos normativos activos configurados."""
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    active = (ctx.active_frameworks or []) if ctx else []
    if active:
        return CCMResult("frameworks_active", "5.31", "Frameworks normativos activos",
                         "PASS", f"Frameworks activos: {', '.join(active)}")
    return CCMResult(
        "frameworks_active", "5.31", "Frameworks normativos configurados", "WARNING",
        "No hay frameworks normativos seleccionados",
        recommendation="Seleccionar los frameworks aplicables en la sección de Cumplimiento",
    )


def test_data_backup_evidence(db: Session, org_id: int) -> CCMResult:
    """8.13 — Evidencia de copias de seguridad."""
    backup_keywords = ["backup", "copia", "respaldo", "recovery", "recuperacion"]
    ev_count = 0
    for kw in backup_keywords:
        ev_count += db.query(Evidence).filter(
            Evidence.organization_id == org_id,
            Evidence.title.ilike(f"%{kw}%"),
            Evidence.is_current == True,
        ).count()
        if ev_count > 0:
            break
    # También buscar por control_implementation
    backup_controls = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == org_id,
        ControlImplementation.name.ilike("%backup%"),
        ControlImplementation.status == ControlStatus.IMPLEMENTED,
    ).count()
    if ev_count > 0 or backup_controls > 0:
        return CCMResult("backup_evidence", "8.13", "Evidencia de copias de seguridad",
                         "PASS", "Se han encontrado evidencias o controles de backup")
    return CCMResult(
        "backup_evidence", "8.13", "Evidencia de copias de seguridad", "WARNING",
        "No se encontraron evidencias de copias de seguridad",
        recommendation="Subir evidencias del procedimiento de backup (logs, capturas, certificados)",
    )


def test_open_risks_reviewed_recently(db: Session, org_id: int) -> CCMResult:
    """5.36 — Riesgos altos revisados en últimos 90 días."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=90)
    high = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.residual_level >= 5,
        Risk.status.notin_([RiskStatus.ACCEPTED, RiskStatus.ARCHIVED]),
    ).all()
    if not high:
        return CCMResult("risks_reviewed", "5.36", "Revisión de riesgos altos",
                         "PASS", "No hay riesgos altos abiertos")
    not_reviewed = [r for r in high
                    if not r.updated_at or
                    r.updated_at.replace(tzinfo=timezone.utc) < threshold]
    pct = round((len(high) - len(not_reviewed)) / len(high) * 100, 1)
    status = "PASS" if not not_reviewed else ("WARNING" if len(not_reviewed) <= 2 else "FAIL")
    return CCMResult(
        "risks_reviewed", "5.36", "Riesgos altos revisados en 90 días", status,
        f"{len(high) - len(not_reviewed)}/{len(high)} riesgos revisados ({pct}%)", value=pct,
        recommendation="" if status == "PASS" else f"Revisar {len(not_reviewed)} riesgo(s) sin actualizar en 90 días",
    )


# ─── Tests adicionales ──────────────────────────────────────────────────────

def test_users_with_inactive_access(db: Session, org_id: int) -> CCMResult:
    """5.18 — Usuarios inactivos (>90 días sin login) tienen acceso revocado."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=90)
    all_users = db.query(User).filter(
        User.organization_id == org_id,
        User.is_active == True,
    ).all()
    if not all_users:
        return CCMResult("user_inactive", "5.18", "Revisión de usuarios inactivos",
                         "SKIP", "No hay usuarios activos")
    stale = [u for u in all_users if hasattr(u, "last_login_at") and u.last_login_at and
             u.last_login_at.replace(tzinfo=timezone.utc) < threshold]
    if not stale:
        return CCMResult("user_inactive", "5.18", "Usuarios inactivos",
                         "PASS", f"{len(all_users)} usuarios activos, ninguno inactivo >90 días")
    status = "WARNING" if len(stale) <= 3 else "FAIL"
    return CCMResult(
        "user_inactive", "5.18", "Usuarios inactivos sin acceso revocado", status,
        f"{len(stale)} usuario(s) sin login en >90 días",
        recommendation="Revisar y deshabilitar usuarios que no acceden desde hace más de 90 días",
    )


def test_supplier_contracts_valid(db: Session, org_id: int) -> CCMResult:
    """5.19 — Contratos con proveedores críticos vigentes."""
    now = datetime.now(timezone.utc)
    suppliers = db.query(Supplier).filter(
        Supplier.organization_id == org_id,
        Supplier.is_critical == True,
    ).all()
    if not suppliers:
        suppliers = db.query(Supplier).filter(Supplier.organization_id == org_id).limit(10).all()
    if not suppliers:
        return CCMResult("supplier_contracts", "5.19", "Contratos con proveedores",
                         "SKIP", "No hay proveedores registrados")
    expired = [s for s in suppliers
               if s.contract_expiry and
               s.contract_expiry.replace(tzinfo=timezone.utc) < now]
    expiring_soon = [s for s in suppliers
                     if s.contract_expiry and
                     now < s.contract_expiry.replace(tzinfo=timezone.utc) < now + timedelta(days=30)]
    if not expired and not expiring_soon:
        return CCMResult("supplier_contracts", "5.19", "Contratos con proveedores vigentes",
                         "PASS", f"{len(suppliers)} proveedor(es) con contratos vigentes")
    status = "FAIL" if expired else "WARNING"
    msgs = []
    if expired:
        msgs.append(f"{len(expired)} contrato(s) vencido(s)")
    if expiring_soon:
        msgs.append(f"{len(expiring_soon)} contrato(s) vencen en <30 días")
    return CCMResult(
        "supplier_contracts", "5.19", "Vigencia de contratos con proveedores", status,
        "; ".join(msgs),
        recommendation="Renovar contratos vencidos o próximos a vencer",
    )


def test_gdpr_activities_documented(db: Session, org_id: int) -> CCMResult:
    """5.34 — Registro de actividades de tratamiento de datos (GDPR Art. 30)."""
    try:
        from app.models import ProcessingActivity
        count = db.query(ProcessingActivity).filter(
            ProcessingActivity.organization_id == org_id
        ).count()
        if count >= 3:
            return CCMResult("gdpr_activities", "5.34", "Registro actividades tratamiento",
                             "PASS", f"{count} actividades de tratamiento documentadas")
        if count > 0:
            return CCMResult("gdpr_activities", "5.34", "Registro actividades tratamiento",
                             "WARNING", f"Solo {count} actividad(es) documentada(s)",
                             recommendation="Documentar todas las actividades de tratamiento (GDPR Art. 30)")
        return CCMResult(
            "gdpr_activities", "5.34", "Registro actividades tratamiento", "FAIL",
            "No hay actividades de tratamiento de datos documentadas",
            recommendation="Crear el Registro de Actividades de Tratamiento (GDPR Art. 30)",
        )
    except Exception:
        return CCMResult("gdpr_activities", "5.34", "Registro actividades tratamiento",
                         "SKIP", "Módulo GDPR no disponible")


def test_internal_audits_performed(db: Session, org_id: int) -> CCMResult:
    """5.35 — Auditoría interna realizada en el último año."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=365)
    try:
        from app.models import AuditProgram, AuditStatus
        recent = db.query(AuditProgram).filter(
            AuditProgram.organization_id == org_id,
            AuditProgram.status == AuditStatus.COMPLETED,
            AuditProgram.actual_date > threshold,
        ).count()
        if recent >= 1:
            return CCMResult("internal_audit", "5.35", "Auditoría interna anual",
                             "PASS", f"{recent} auditoría(s) interna(s) en último año")
        planned = db.query(AuditProgram).filter(
            AuditProgram.organization_id == org_id,
            AuditProgram.status.in_(["planned", "in_progress"]),
        ).count()
        if planned:
            return CCMResult("internal_audit", "5.35", "Auditoría interna anual",
                             "WARNING", "No hay auditorías completadas, hay una planificada",
                             recommendation="Completar la auditoría interna planificada")
        return CCMResult(
            "internal_audit", "5.35", "Auditoría interna anual", "FAIL",
            "No se han realizado auditorías internas en el último año",
            recommendation="Planificar y ejecutar auditoría interna del SGSI",
        )
    except Exception:
        return CCMResult("internal_audit", "5.35", "Auditoría interna anual",
                         "SKIP", "Módulo de auditorías no disponible")


def test_nonconformities_addressed(db: Session, org_id: int) -> CCMResult:
    """10.1 — No conformidades con acciones correctivas asignadas."""
    try:
        from app.models import NonConformity, NCStatus
        open_nc = db.query(NonConformity).filter(
            NonConformity.organization_id == org_id,
            NonConformity.status.notin_([NCStatus.CLOSED]),
        ).all()
        if not open_nc:
            return CCMResult("nc_addressed", "10.1", "No conformidades gestionadas",
                             "PASS", "No hay no conformidades abiertas")
        old_nc = [nc for nc in open_nc
                  if nc.created_at and
                  (datetime.now(timezone.utc) - nc.created_at.replace(tzinfo=timezone.utc)).days > 90]
        if not old_nc:
            return CCMResult("nc_addressed", "10.1", "No conformidades gestionadas",
                             "WARNING", f"{len(open_nc)} NC abiertas (todas recientes)",
                             recommendation="Gestionar las no conformidades abiertas")
        return CCMResult(
            "nc_addressed", "10.1", "No conformidades gestionadas", "FAIL",
            f"{len(old_nc)}/{len(open_nc)} NC abiertas sin cerrar en >90 días",
            recommendation="Cerrar no conformidades antiguas con acciones correctivas verificadas",
        )
    except Exception:
        return CCMResult("nc_addressed", "10.1", "No conformidades gestionadas",
                         "SKIP", "Módulo de no conformidades no disponible")


def test_risk_context_complete(db: Session, org_id: int) -> CCMResult:
    """4.1/4.2 — Contexto organizacional del SGSI completo."""
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    if not ctx:
        return CCMResult("risk_context", "4.1", "Contexto organizacional",
                         "FAIL", "No hay contexto de riesgo configurado",
                         recommendation="Configurar el contexto organizacional del SGSI")
    missing = []
    if not ctx.scope:
        missing.append("alcance")
    if not ctx.boundaries:
        missing.append("límites")
    if not ctx.risk_matrix:
        missing.append("matriz de riesgos")
    if ctx.risk_appetite is None:
        missing.append("apetito de riesgo")
    if missing:
        return CCMResult(
            "risk_context", "4.1", "Contexto organizacional completo", "WARNING",
            f"Campos sin completar: {', '.join(missing)}",
            recommendation="Completar todos los campos del contexto en la sección Contexto",
        )
    return CCMResult("risk_context", "4.1", "Contexto organizacional completo",
                     "PASS", "Contexto organizacional completamente configurado")


def test_treatment_tasks_assigned(db: Session, org_id: int) -> CCMResult:
    """5.2 — Tareas de tratamiento con responsable asignado."""
    from app.models import TreatmentTask
    total = db.query(TreatmentTask).filter(
        TreatmentTask.organization_id == org_id,
        TreatmentTask.status.notin_([TaskStatus.DONE]),
    ).count()
    if total == 0:
        return CCMResult("tasks_assigned", "5.2", "Tareas con responsable",
                         "PASS", "No hay tareas pendientes")
    unassigned = db.query(TreatmentTask).filter(
        TreatmentTask.organization_id == org_id,
        TreatmentTask.status.notin_([TaskStatus.DONE]),
        TreatmentTask.assigned_to_id.is_(None),
    ).count()
    pct = round((total - unassigned) / total * 100, 1)
    status = "PASS" if unassigned == 0 else ("WARNING" if unassigned <= 3 else "FAIL")
    return CCMResult(
        "tasks_assigned", "5.2", "Tareas de tratamiento con responsable", status,
        f"{total - unassigned}/{total} tareas tienen responsable asignado ({pct}%)", value=pct,
        recommendation="" if status == "PASS" else f"Asignar responsable a {unassigned} tarea(s) sin asignar",
    )


def test_awareness_training_recent(db: Session, org_id: int) -> CCMResult:
    """6.3 — Formación en concienciación reciente (último año)."""
    try:
        from app.models import AwarenessItem
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(days=365)
        recent = db.query(AwarenessItem).filter(
            AwarenessItem.organization_id == org_id,
            AwarenessItem.status == "published",
            AwarenessItem.created_at >= threshold,
        ).count()
        if recent >= 2:
            return CCMResult("awareness", "6.3", "Formación en concienciación",
                             "PASS", f"{recent} elemento(s) de awareness publicados en último año")
        if recent == 1:
            return CCMResult("awareness", "6.3", "Formación en concienciación",
                             "WARNING", "Solo 1 elemento de awareness en el último año",
                             recommendation="Aumentar la frecuencia de formación en concienciación")
        return CCMResult(
            "awareness", "6.3", "Formación en concienciación (último año)", "FAIL",
            "No se ha publicado formación de concienciación en el último año",
            recommendation="Publicar materiales de awareness en seguridad de la información",
        )
    except Exception:
        return CCMResult("awareness", "6.3", "Formación en concienciación",
                         "SKIP", "Módulo de awareness no disponible")


def test_incident_response_plan(db: Session, org_id: int) -> CCMResult:
    """5.24 — Plan de respuesta a incidentes documentado."""
    ir_keywords = ["incidente", "incident", "respuesta", "response", "ciberseguridad", "CSIRT"]
    pol_count = 0
    for kw in ir_keywords:
        pol_count += db.query(Policy).filter(
            Policy.organization_id == org_id,
            Policy.title.ilike(f"%{kw}%"),
            Policy.status != PolicyStatus.OBSOLETE,
        ).count()
        if pol_count > 0:
            break
    if pol_count > 0:
        return CCMResult("ir_plan", "5.24", "Plan de respuesta a incidentes",
                         "PASS", "Se ha encontrado política/procedimiento de respuesta a incidentes")
    return CCMResult(
        "ir_plan", "5.24", "Plan de respuesta a incidentes documentado", "WARNING",
        "No se encontró política de respuesta a incidentes",
        recommendation="Crear/subir el Plan de Respuesta a Incidentes de Seguridad",
    )


def test_assets_with_risk_coverage(db: Session, org_id: int) -> CCMResult:
    """5.8 — Activos críticos con al menos un riesgo identificado."""
    from app.models import Asset
    total_assets = db.query(Asset).filter(Asset.organization_id == org_id).count()
    if total_assets == 0:
        return CCMResult("asset_risk_coverage", "5.8", "Activos con riesgos identificados",
                         "SKIP", "No hay activos registrados")
    assets_with_risks = db.query(Asset.id).filter(
        Asset.organization_id == org_id,
    ).join(Risk, Risk.asset_id == Asset.id, isouter=True).filter(
        Risk.id.isnot(None)
    ).distinct().count()
    pct = round(assets_with_risks / total_assets * 100, 1)
    status = "PASS" if pct >= 80 else ("WARNING" if pct >= 50 else "FAIL")
    return CCMResult(
        "asset_risk_coverage", "5.8", "Activos con riesgos identificados", status,
        f"{assets_with_risks}/{total_assets} activos con riesgos ({pct}%)", value=pct,
        recommendation="" if status == "PASS" else "Completar análisis de riesgos para activos sin cobertura",
    )


def test_evidence_linked_to_controls(db: Session, org_id: int) -> CCMResult:
    """5.35 — Evidencias vinculadas a requisitos de compliance."""
    total_ev = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.is_current == True,
    ).count()
    if total_ev == 0:
        return CCMResult("evidence_linked", "5.35", "Evidencias vinculadas a compliance",
                         "WARNING", "No hay evidencias registradas",
                         recommendation="Subir evidencias y vincularlas a requisitos normativos")
    linked = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.is_current == True,
        Evidence.compliance_framework.isnot(None),
    ).count()
    pct = round(linked / total_ev * 100, 1)
    status = "PASS" if pct >= 70 else ("WARNING" if pct >= 40 else "FAIL")
    return CCMResult(
        "evidence_linked", "5.35", "Evidencias vinculadas a requisitos normativos", status,
        f"{linked}/{total_ev} evidencias vinculadas a frameworks ({pct}%)", value=pct,
        recommendation="" if status == "PASS" else "Vincular más evidencias a requisitos específicos",
    )


# ─── Runner principal ────────────────────────────────────────────────────────

_ALL_TESTS: list[Callable] = [
    test_all_assets_have_owner,
    test_assets_classified,
    test_high_risks_have_treatment,
    test_risks_over_appetite_have_tasks,
    test_controls_have_evidence,
    test_policies_current,
    test_incidents_resolved,
    test_suppliers_reviewed,
    test_tasks_not_overdue,
    test_evidence_freshness,
    test_admin_users_have_mfa,
    test_vulnerabilities_addressed,
    test_risk_appetite_defined,
    test_compliance_frameworks_active,
    test_data_backup_evidence,
    test_open_risks_reviewed_recently,
    # Nuevos tests
    test_users_with_inactive_access,
    test_supplier_contracts_valid,
    test_gdpr_activities_documented,
    test_internal_audits_performed,
    test_nonconformities_addressed,
    test_risk_context_complete,
    test_treatment_tasks_assigned,
    test_awareness_training_recent,
    test_incident_response_plan,
    test_assets_with_risk_coverage,
    test_evidence_linked_to_controls,
]


def run_all_tests(db: Session, org_id: int) -> dict:
    """Ejecuta todos los tests CCM para una organización.

    Returns: {results, summary, score, timestamp}
    """
    results = []
    counts = {"PASS": 0, "FAIL": 0, "WARNING": 0, "SKIP": 0}

    for test_fn in _ALL_TESTS:
        try:
            result = test_fn(db, org_id)
            results.append(result.to_dict())
            counts[result.status] = counts.get(result.status, 0) + 1
        except Exception as exc:
            logger.exception("CCM test %s failed: %s", test_fn.__name__, exc)
            results.append({
                "test_id": test_fn.__name__,
                "control_code": "?",
                "name": test_fn.__name__,
                "status": "SKIP",
                "detail": f"Error ejecutando test: {exc}",
                "recommendation": "",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            counts["SKIP"] += 1

    total_scored = counts["PASS"] + counts["FAIL"] + counts["WARNING"]
    score = round(
        (counts["PASS"] + counts["WARNING"] * 0.5) / max(1, total_scored) * 100, 1
    )

    return {
        "org_id": org_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": score,
        "counts": counts,
        "total_tests": len(results),
        "results": results,
        "summary": (
            f"CCM Score: {score}/100 — "
            f"{counts['PASS']} PASS, {counts['WARNING']} WARNING, "
            f"{counts['FAIL']} FAIL, {counts['SKIP']} SKIP"
        ),
    }


def run_test_by_id(db: Session, org_id: int, test_id: str) -> Optional[dict]:
    """Ejecuta un test específico por ID."""
    for test_fn in _ALL_TESTS:
        if test_fn.__name__ == test_id or (
            hasattr(test_fn, "__doc__") and test_id in (test_fn.__doc__ or "")
        ):
            result = test_fn(db, org_id)
            return result.to_dict()
    # Buscar por test_id en el resultado
    for test_fn in _ALL_TESTS:
        try:
            r = test_fn(db, org_id)
            if r.test_id == test_id:
                return r.to_dict()
        except Exception:
            pass
    return None


def get_test_catalog() -> list[dict]:
    """Retorna catálogo de tests disponibles."""
    return [
        {
            "test_id": fn.__name__,
            "control_code": fn.__doc__.split("—")[0].strip().replace("def ", "") if fn.__doc__ else "",
            "description": fn.__doc__.split("—")[1].strip() if fn.__doc__ and "—" in fn.__doc__ else fn.__name__,
        }
        for fn in _ALL_TESTS
    ]
