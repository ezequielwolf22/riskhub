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

from app.i18n import t as _t
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

def test_all_assets_have_owner(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """8.1 — Todos los activos tienen propietario asignado."""
    total = db.query(Asset).filter(Asset.organization_id == org_id).count()
    # A1: Asset no tiene owner_id; usa la relacion M2M 'owners'
    all_assets = db.query(Asset).filter(Asset.organization_id == org_id).all()
    without_owner = sum(1 for a in all_assets if not (getattr(a, "owners", None)))
    name = _t("ccm.assets_owner.name", lang)
    if total == 0:
        return CCMResult("assets_owner", "8.1", name,
                         "SKIP", _t("ccm.assets_owner.skip", lang))
    pct = round((total - without_owner) / total * 100, 1)
    status = "PASS" if without_owner == 0 else ("WARNING" if without_owner <= 2 else "FAIL")
    return CCMResult(
        "assets_owner", "8.1", name, status,
        _t("ccm.assets_owner.detail", lang, ok=total - without_owner, total=total, pct=pct),
        value=pct,
        recommendation="" if status == "PASS" else _t("ccm.assets_owner.rec", lang, n=without_owner),
    )


def test_assets_classified(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.12/5.13 — Activos tienen clasificación de información."""
    total = db.query(Asset).filter(Asset.organization_id == org_id).count()
    classified = db.query(Asset).filter(
        Asset.organization_id == org_id,
        Asset.classification.isnot(None),
        Asset.classification != "",
    ).count()
    name = _t("ccm.assets_classified.name", lang)
    if total == 0:
        return CCMResult(
            "assets_classified", "5.12", name,
            "WARNING", _t("ccm.assets_classified.empty", lang),
            recommendation=_t("ccm.assets_classified.empty_rec", lang),
        )
    pct = round(classified / total * 100, 1)
    status = "PASS" if pct >= 90 else ("WARNING" if pct >= 70 else "FAIL")
    return CCMResult(
        "assets_classified", "5.12", name, status,
        _t("ccm.assets_classified.detail", lang, ok=classified, total=total, pct=pct), value=pct,
        recommendation="" if status == "PASS" else _t("ccm.assets_classified.rec", lang),
    )


def test_high_risks_have_treatment(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.8/6.1 — Riesgos altos/críticos tienen tratamiento asignado."""
    high_risks = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.residual_level >= 5,
        Risk.status.notin_([RiskStatus.ACCEPTED, RiskStatus.CLOSED]),
    ).all()
    name = _t("ccm.risks_treatment.name", lang)
    if not high_risks:
        return CCMResult("risks_treatment", "5.8", name,
                         "PASS", _t("ccm.risks_treatment.ok", lang))
    without = [r for r in high_risks if not r.treatment_option]
    total = len(high_risks)
    pct = round((total - len(without)) / total * 100, 1) if total > 0 else 100
    status = "PASS" if not without else ("WARNING" if len(without) <= 2 else "FAIL")
    return CCMResult(
        "risks_treatment", "5.8", name, status,
        _t("ccm.risks_treatment.detail", lang, ok=total - len(without), total=total, pct=pct), value=pct,
        recommendation="" if status == "PASS" else _t(
            "ccm.risks_treatment.rec", lang, n=len(without),
            codes=", ".join(r.code for r in without[:3]),
        ),
    )


def test_risks_over_appetite_have_tasks(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.8 — Riesgos sobre apetito tienen tareas de tratamiento activas."""
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    appetite = ctx.risk_appetite if ctx else 3
    over = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.residual_level > appetite,
        Risk.status == RiskStatus.ASSESSED,
    ).all()
    name = _t("ccm.risks_tasks.name", lang)
    if not over:
        return CCMResult("risks_tasks", "5.8", name,
                         "PASS", _t("ccm.risks_tasks.ok", lang))
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
        "risks_tasks", "5.8", name, status,
        _t("ccm.risks_tasks.detail", lang, ok=len(over) - len(without_tasks), total=len(over), pct=pct),
        value=pct,
        recommendation="" if status == "PASS" else _t("ccm.risks_tasks.rec", lang, n=len(without_tasks)),
    )


def test_controls_have_evidence(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.35/5.36 — Controles implementados tienen evidencia asociada."""
    implemented = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == org_id,
        ControlImplementation.status == ControlStatus.IMPLEMENTED,
    ).all()
    name = _t("ccm.controls_evidence.name", lang)
    if not implemented:
        return CCMResult("controls_evidence", "5.35", name,
                         "SKIP", _t("ccm.controls_evidence.skip", lang))
    with_evidence = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.control_implementation_id.isnot(None),
        Evidence.is_current == True,
    ).distinct(Evidence.control_implementation_id).count()
    total = len(implemented)
    pct = round(with_evidence / total * 100, 1)
    status = "PASS" if pct >= 80 else ("WARNING" if pct >= 50 else "FAIL")
    return CCMResult(
        "controls_evidence", "5.35", name, status,
        _t("ccm.controls_evidence.detail", lang, ok=with_evidence, total=total, pct=pct), value=pct,
        recommendation="" if status == "PASS" else _t("ccm.controls_evidence.rec", lang),
    )


def test_policies_current(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.1 — Políticas de seguridad están vigentes (no vencidas)."""
    now = datetime.now(timezone.utc)
    all_policies = db.query(Policy).filter(
        Policy.organization_id == org_id,
        Policy.status != PolicyStatus.OBSOLETE,
    ).all()
    name = _t("ccm.policies_current.name", lang)
    if not all_policies:
        return CCMResult("policies_current", "5.1", name,
                         "FAIL", _t("ccm.policies_current.none", lang),
                         recommendation=_t("ccm.policies_current.none_rec", lang))
    overdue = [p for p in all_policies
               if p.review_date and p.review_date.replace(tzinfo=timezone.utc) < now]
    pct = round((len(all_policies) - len(overdue)) / len(all_policies) * 100, 1)
    status = "PASS" if not overdue else ("WARNING" if len(overdue) <= 2 else "FAIL")
    return CCMResult(
        "policies_current", "5.1", name, status,
        _t("ccm.policies_current.detail", lang,
           ok=len(all_policies) - len(overdue), total=len(all_policies), pct=pct), value=pct,
        recommendation="" if status == "PASS" else _t("ccm.policies_current.rec", lang, n=len(overdue)),
    )


def test_incidents_resolved(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.24/5.25 — Incidentes P1/P2 resueltos en tiempo."""
    from app.models import IncidentSeverity
    now = datetime.now(timezone.utc)
    critical_open = db.query(Incident).filter(
        Incident.organization_id == org_id,
        Incident.status.notin_([IncidentStatus.CLOSED, IncidentStatus.RESOLVED]),
        Incident.severity.in_([IncidentSeverity.P1, IncidentSeverity.P2]),
        Incident.created_at < now - timedelta(days=3),
    ).count()
    name = _t("ccm.incidents_resolved.name", lang)
    if critical_open == 0:
        return CCMResult("incidents_resolved", "5.24", name,
                         "PASS", _t("ccm.incidents_resolved.ok", lang))
    return CCMResult(
        "incidents_resolved", "5.24", name, "FAIL",
        _t("ccm.incidents_resolved.detail", lang, n=critical_open),
        recommendation=_t("ccm.incidents_resolved.rec", lang),
    )


def test_suppliers_reviewed(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.19 — Proveedores críticos con evaluación reciente."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=365)
    # Obtener proveedores críticos (is_critical existe en el modelo)
    # Si no hay ninguno marcado como crítico, evaluar todos los proveedores
    suppliers = db.query(Supplier).filter(
        Supplier.organization_id == org_id,
        Supplier.is_critical == True,
    ).all()

    if not suppliers:
        # Sin proveedores marcados como críticos → evaluar todos
        suppliers = db.query(Supplier).filter(Supplier.organization_id == org_id).all()
    name = _t("ccm.suppliers_reviewed.name", lang)
    if not suppliers:
        return CCMResult("suppliers_reviewed", "5.19", name,
                         "SKIP", _t("ccm.suppliers_reviewed.skip", lang))
    stale = [s for s in suppliers
             if not s.updated_at or s.updated_at.replace(tzinfo=timezone.utc) < threshold]
    pct = round((len(suppliers) - len(stale)) / len(suppliers) * 100, 1)
    status = "PASS" if not stale else ("WARNING" if len(stale) <= 2 else "FAIL")
    return CCMResult(
        "suppliers_reviewed", "5.19", name, status,
        _t("ccm.suppliers_reviewed.detail", lang,
           ok=len(suppliers) - len(stale), total=len(suppliers), pct=pct),
        value=pct,
        recommendation="" if status == "PASS" else _t("ccm.suppliers_reviewed.rec", lang, n=len(stale)),
    )


def test_tasks_not_overdue(db: Session, org_id: int, lang: str = "es") -> CCMResult:
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
    name = _t("ccm.tasks_overdue.name", lang)
    if total == 0:
        return CCMResult("tasks_overdue", "5.36", name,
                         "PASS", _t("ccm.tasks_overdue.ok", lang))
    pct = round((total - overdue) / total * 100, 1)
    status = "PASS" if overdue == 0 else ("WARNING" if overdue <= 3 else "FAIL")
    return CCMResult(
        "tasks_overdue", "5.36", name, status,
        _t("ccm.tasks_overdue.detail", lang,
           overdue=overdue, total=total, mora=f"{100 - pct:.0f}"), value=pct,
        recommendation="" if status == "PASS" else _t("ccm.tasks_overdue.rec", lang, n=overdue),
    )


def test_evidence_freshness(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.35 — Evidencias de controles no vencidas ni antiguas (>12 meses)."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=365)
    total_ev = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.is_current == True,
    ).count()
    name = _t("ccm.evidence_fresh.name", lang)
    if total_ev == 0:
        return CCMResult("evidence_fresh", "5.35", name,
                         "WARNING", _t("ccm.evidence_fresh.none", lang),
                         recommendation=_t("ccm.evidence_fresh.none_rec", lang))
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
        "evidence_fresh", "5.35", name, status,
        _t("ccm.evidence_fresh.detail", lang, ok=total_ev - bad, total=total_ev, pct=pct), value=pct,
        recommendation="" if status == "PASS" else _t("ccm.evidence_fresh.rec", lang, n=bad),
    )


def test_admin_users_have_mfa(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """8.5 — Usuarios administradores con MFA habilitado."""
    admins = db.query(User).filter(
        User.organization_id == org_id,
        User.role.in_([UserRole.ADMIN, UserRole.SUPERADMIN]),
        User.is_active == True,
    ).all()
    name = _t("ccm.admin_mfa.name", lang)
    if not admins:
        return CCMResult("admin_mfa", "8.5", name,
                         "SKIP", _t("ccm.admin_mfa.skip", lang))
    # Verificar campo otp_secret como proxy de MFA habilitado
    with_mfa = [u for u in admins if getattr(u, "otp_secret", None)]
    pct = round(len(with_mfa) / len(admins) * 100, 1)
    status = "PASS" if pct == 100 else ("WARNING" if pct >= 50 else "FAIL")
    return CCMResult(
        "admin_mfa", "8.5", name, status,
        _t("ccm.admin_mfa.detail", lang, ok=len(with_mfa), total=len(admins), pct=pct), value=pct,
        recommendation="" if status == "PASS" else _t("ccm.admin_mfa.rec", lang),
    )


def test_vulnerabilities_addressed(db: Session, org_id: int, lang: str = "es") -> CCMResult:
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
    name = _t("ccm.vulns_addressed.name", lang)
    if critical_open == 0:
        return CCMResult("vulns_addressed", "8.8", name,
                         "PASS", _t("ccm.vulns_addressed.ok", lang))
    return CCMResult(
        "vulns_addressed", "8.8", name, "FAIL",
        _t("ccm.vulns_addressed.detail", lang, n=critical_open),
        recommendation=_t("ccm.vulns_addressed.rec", lang),
    )


def test_risk_appetite_defined(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.37/6.1 — Apetito de riesgo definido por la organización."""
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    name = _t("ccm.risk_appetite.name", lang)
    if ctx and ctx.risk_appetite is not None:
        return CCMResult("risk_appetite", "5.37", name,
                         "PASS", _t("ccm.risk_appetite.ok", lang, value=ctx.risk_appetite))
    return CCMResult(
        "risk_appetite", "5.37", name, "FAIL",
        _t("ccm.risk_appetite.detail", lang),
        recommendation=_t("ccm.risk_appetite.rec", lang),
    )


def test_compliance_frameworks_active(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.31 — Marcos normativos activos configurados."""
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    active = (ctx.active_frameworks or []) if ctx else []
    name = _t("ccm.frameworks_active.name", lang)
    if active:
        return CCMResult("frameworks_active", "5.31", name,
                         "PASS", _t("ccm.frameworks_active.ok", lang, list=", ".join(active)))
    return CCMResult(
        "frameworks_active", "5.31", name, "WARNING",
        _t("ccm.frameworks_active.detail", lang),
        recommendation=_t("ccm.frameworks_active.rec", lang),
    )


def test_data_backup_evidence(db: Session, org_id: int, lang: str = "es") -> CCMResult:
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
    name = _t("ccm.backup_evidence.name", lang)
    if ev_count > 0 or backup_controls > 0:
        return CCMResult("backup_evidence", "8.13", name,
                         "PASS", _t("ccm.backup_evidence.ok", lang))
    return CCMResult(
        "backup_evidence", "8.13", name, "WARNING",
        _t("ccm.backup_evidence.detail", lang),
        recommendation=_t("ccm.backup_evidence.rec", lang),
    )


def test_open_risks_reviewed_recently(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.36 — Riesgos altos revisados en últimos 90 días."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=90)
    high = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.residual_level >= 5,
        Risk.status.notin_([RiskStatus.ACCEPTED, RiskStatus.CLOSED]),
    ).all()
    name = _t("ccm.risks_reviewed.name", lang)
    if not high:
        return CCMResult("risks_reviewed", "5.36", name,
                         "PASS", _t("ccm.risks_reviewed.ok", lang))
    not_reviewed = [r for r in high
                    if not r.updated_at or
                    r.updated_at.replace(tzinfo=timezone.utc) < threshold]
    pct = round((len(high) - len(not_reviewed)) / len(high) * 100, 1)
    status = "PASS" if not not_reviewed else ("WARNING" if len(not_reviewed) <= 2 else "FAIL")
    return CCMResult(
        "risks_reviewed", "5.36", name, status,
        _t("ccm.risks_reviewed.detail", lang,
           ok=len(high) - len(not_reviewed), total=len(high), pct=pct), value=pct,
        recommendation="" if status == "PASS" else _t("ccm.risks_reviewed.rec", lang, n=len(not_reviewed)),
    )


# ─── Tests adicionales ──────────────────────────────────────────────────────

def test_users_with_inactive_access(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.18 — Usuarios inactivos (>90 días sin login) tienen acceso revocado."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=90)
    all_users = db.query(User).filter(
        User.organization_id == org_id,
        User.is_active == True,
    ).all()
    name = _t("ccm.user_inactive.name", lang)
    if not all_users:
        return CCMResult("user_inactive", "5.18", name,
                         "SKIP", _t("ccm.user_inactive.skip", lang))
    stale = [u for u in all_users if hasattr(u, "last_login_at") and u.last_login_at and
             u.last_login_at.replace(tzinfo=timezone.utc) < threshold]
    if not stale:
        return CCMResult("user_inactive", "5.18", name,
                         "PASS", _t("ccm.user_inactive.ok", lang, total=len(all_users)))
    status = "WARNING" if len(stale) <= 3 else "FAIL"
    return CCMResult(
        "user_inactive", "5.18", name, status,
        _t("ccm.user_inactive.detail", lang, n=len(stale)),
        recommendation=_t("ccm.user_inactive.rec", lang),
    )


def test_supplier_contracts_valid(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.19 — Contratos con proveedores críticos vigentes."""
    now = datetime.now(timezone.utc)
    suppliers = db.query(Supplier).filter(
        Supplier.organization_id == org_id,
        Supplier.is_critical == True,
    ).all()
    if not suppliers:
        suppliers = db.query(Supplier).filter(Supplier.organization_id == org_id).limit(10).all()
    name = _t("ccm.supplier_contracts.name", lang)
    if not suppliers:
        return CCMResult("supplier_contracts", "5.19", name,
                         "SKIP", _t("ccm.supplier_contracts.skip", lang))
    expired = [s for s in suppliers
               if s.contract_expiry and
               s.contract_expiry.replace(tzinfo=timezone.utc) < now]
    expiring_soon = [s for s in suppliers
                     if s.contract_expiry and
                     now < s.contract_expiry.replace(tzinfo=timezone.utc) < now + timedelta(days=30)]
    if not expired and not expiring_soon:
        return CCMResult("supplier_contracts", "5.19", name,
                         "PASS", _t("ccm.supplier_contracts.ok", lang, n=len(suppliers)))
    status = "FAIL" if expired else "WARNING"
    msgs = []
    if expired:
        msgs.append(_t("ccm.supplier_contracts.expired", lang, n=len(expired)))
    if expiring_soon:
        msgs.append(_t("ccm.supplier_contracts.expiring", lang, n=len(expiring_soon)))
    return CCMResult(
        "supplier_contracts", "5.19", name, status,
        "; ".join(msgs),
        recommendation=_t("ccm.supplier_contracts.rec", lang),
    )


def test_gdpr_activities_documented(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.34 — Registro de actividades de tratamiento de datos (GDPR Art. 30)."""
    name = _t("ccm.gdpr_activities.name", lang)
    try:
        from app.models import ProcessingActivity
        count = db.query(ProcessingActivity).filter(
            ProcessingActivity.organization_id == org_id
        ).count()
        if count >= 3:
            return CCMResult("gdpr_activities", "5.34", name,
                             "PASS", _t("ccm.gdpr_activities.ok", lang, n=count))
        if count > 0:
            return CCMResult("gdpr_activities", "5.34", name,
                             "WARNING", _t("ccm.gdpr_activities.warn", lang, n=count),
                             recommendation=_t("ccm.gdpr_activities.warn_rec", lang))
        return CCMResult(
            "gdpr_activities", "5.34", name, "FAIL",
            _t("ccm.gdpr_activities.fail", lang),
            recommendation=_t("ccm.gdpr_activities.fail_rec", lang),
        )
    except Exception:
        return CCMResult("gdpr_activities", "5.34", name,
                         "SKIP", _t("ccm.gdpr_activities.skip", lang))


def test_internal_audits_performed(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.35 — Auditoría interna realizada en el último año."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=365)
    name = _t("ccm.internal_audit.name", lang)
    try:
        from app.models import AuditProgram, AuditStatus
        recent = db.query(AuditProgram).filter(
            AuditProgram.organization_id == org_id,
            AuditProgram.status == AuditStatus.COMPLETED,
            AuditProgram.actual_end > threshold,
        ).count()
        if recent >= 1:
            return CCMResult("internal_audit", "5.35", name,
                             "PASS", _t("ccm.internal_audit.ok", lang, n=recent))
        planned = db.query(AuditProgram).filter(
            AuditProgram.organization_id == org_id,
            AuditProgram.status.in_(["planned", "in_progress"]),
        ).count()
        if planned:
            return CCMResult("internal_audit", "5.35", name,
                             "WARNING", _t("ccm.internal_audit.warn", lang),
                             recommendation=_t("ccm.internal_audit.warn_rec", lang))
        return CCMResult(
            "internal_audit", "5.35", name, "FAIL",
            _t("ccm.internal_audit.fail", lang),
            recommendation=_t("ccm.internal_audit.fail_rec", lang),
        )
    except Exception:
        return CCMResult("internal_audit", "5.35", name,
                         "SKIP", _t("ccm.internal_audit.skip", lang))


def test_nonconformities_addressed(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """10.1 — No conformidades con acciones correctivas asignadas."""
    name = _t("ccm.nc_addressed.name", lang)
    try:
        from app.models import NonConformity, NCStatus
        open_nc = db.query(NonConformity).filter(
            NonConformity.organization_id == org_id,
            NonConformity.status.notin_([NCStatus.CLOSED]),
        ).all()
        if not open_nc:
            return CCMResult("nc_addressed", "10.1", name,
                             "PASS", _t("ccm.nc_addressed.ok", lang))
        old_nc = [nc for nc in open_nc
                  if nc.created_at and
                  (datetime.now(timezone.utc) - nc.created_at.replace(tzinfo=timezone.utc)).days > 90]
        if not old_nc:
            return CCMResult("nc_addressed", "10.1", name,
                             "WARNING", _t("ccm.nc_addressed.warn", lang, n=len(open_nc)),
                             recommendation=_t("ccm.nc_addressed.warn_rec", lang))
        return CCMResult(
            "nc_addressed", "10.1", name, "FAIL",
            _t("ccm.nc_addressed.fail", lang, old=len(old_nc), open=len(open_nc)),
            recommendation=_t("ccm.nc_addressed.fail_rec", lang),
        )
    except Exception:
        return CCMResult("nc_addressed", "10.1", name,
                         "SKIP", _t("ccm.nc_addressed.skip", lang))


def test_risk_context_complete(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """4.1/4.2 — Contexto organizacional del SGSI completo."""
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    name = _t("ccm.risk_context.name", lang)
    if not ctx:
        return CCMResult("risk_context", "4.1", name,
                         "FAIL", _t("ccm.risk_context.fail", lang),
                         recommendation=_t("ccm.risk_context.fail_rec", lang))
    missing = []
    if not ctx.scope:
        missing.append(_t("ccm.risk_context.field_scope", lang))
    if not ctx.boundaries:
        missing.append(_t("ccm.risk_context.field_boundaries", lang))
    if not ctx.risk_matrix:
        missing.append(_t("ccm.risk_context.field_matrix", lang))
    if ctx.risk_appetite is None:
        missing.append(_t("ccm.risk_context.field_appetite", lang))
    if missing:
        return CCMResult(
            "risk_context", "4.1", name, "WARNING",
            _t("ccm.risk_context.warn", lang, fields=", ".join(missing)),
            recommendation=_t("ccm.risk_context.warn_rec", lang),
        )
    return CCMResult("risk_context", "4.1", name,
                     "PASS", _t("ccm.risk_context.ok", lang))


def test_treatment_tasks_assigned(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.2 — Tareas de tratamiento con responsable asignado."""
    from app.models import TreatmentTask
    total = db.query(TreatmentTask).filter(
        TreatmentTask.organization_id == org_id,
        TreatmentTask.status.notin_([TaskStatus.DONE]),
    ).count()
    name = _t("ccm.tasks_assigned.name", lang)
    if total == 0:
        return CCMResult("tasks_assigned", "5.2", name,
                         "PASS", _t("ccm.tasks_assigned.ok", lang))
    unassigned = db.query(TreatmentTask).filter(
        TreatmentTask.organization_id == org_id,
        TreatmentTask.status.notin_([TaskStatus.DONE]),
        TreatmentTask.assigned_to_id.is_(None),
    ).count()
    pct = round((total - unassigned) / total * 100, 1)
    status = "PASS" if unassigned == 0 else ("WARNING" if unassigned <= 3 else "FAIL")
    return CCMResult(
        "tasks_assigned", "5.2", name, status,
        _t("ccm.tasks_assigned.detail", lang, ok=total - unassigned, total=total, pct=pct), value=pct,
        recommendation="" if status == "PASS" else _t("ccm.tasks_assigned.rec", lang, n=unassigned),
    )


def test_awareness_training_recent(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """6.3 — Formación en concienciación reciente (último año)."""
    name = _t("ccm.awareness.name", lang)
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
            return CCMResult("awareness", "6.3", name,
                             "PASS", _t("ccm.awareness.ok", lang, n=recent))
        if recent == 1:
            return CCMResult("awareness", "6.3", name,
                             "WARNING", _t("ccm.awareness.warn", lang),
                             recommendation=_t("ccm.awareness.warn_rec", lang))
        return CCMResult(
            "awareness", "6.3", name, "FAIL",
            _t("ccm.awareness.fail", lang),
            recommendation=_t("ccm.awareness.fail_rec", lang),
        )
    except Exception:
        return CCMResult("awareness", "6.3", name,
                         "SKIP", _t("ccm.awareness.skip", lang))


def test_incident_response_plan(db: Session, org_id: int, lang: str = "es") -> CCMResult:
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
    name = _t("ccm.ir_plan.name", lang)
    if pol_count > 0:
        return CCMResult("ir_plan", "5.24", name,
                         "PASS", _t("ccm.ir_plan.ok", lang))
    return CCMResult(
        "ir_plan", "5.24", name, "WARNING",
        _t("ccm.ir_plan.detail", lang),
        recommendation=_t("ccm.ir_plan.rec", lang),
    )


def test_assets_with_risk_coverage(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.8 — Activos críticos con al menos un riesgo identificado."""
    from app.models import Asset
    total_assets = db.query(Asset).filter(Asset.organization_id == org_id).count()
    name = _t("ccm.asset_risk_coverage.name", lang)
    if total_assets == 0:
        return CCMResult("asset_risk_coverage", "5.8", name,
                         "SKIP", _t("ccm.asset_risk_coverage.skip", lang))
    assets_with_risks = db.query(Asset.id).filter(
        Asset.organization_id == org_id,
    ).join(Risk, Risk.asset_id == Asset.id, isouter=True).filter(
        Risk.id.isnot(None)
    ).distinct().count()
    pct = round(assets_with_risks / total_assets * 100, 1)
    status = "PASS" if pct >= 80 else ("WARNING" if pct >= 50 else "FAIL")
    return CCMResult(
        "asset_risk_coverage", "5.8", name, status,
        _t("ccm.asset_risk_coverage.detail", lang,
           ok=assets_with_risks, total=total_assets, pct=pct), value=pct,
        recommendation="" if status == "PASS" else _t("ccm.asset_risk_coverage.rec", lang),
    )


def test_evidence_linked_to_controls(db: Session, org_id: int, lang: str = "es") -> CCMResult:
    """5.35 — Evidencias vinculadas a requisitos de compliance."""
    total_ev = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.is_current == True,
    ).count()
    name = _t("ccm.evidence_linked.name", lang)
    if total_ev == 0:
        return CCMResult("evidence_linked", "5.35", name,
                         "WARNING", _t("ccm.evidence_linked.none", lang),
                         recommendation=_t("ccm.evidence_linked.none_rec", lang))
    linked = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.is_current == True,
        Evidence.compliance_framework.isnot(None),
    ).count()
    pct = round(linked / total_ev * 100, 1)
    status = "PASS" if pct >= 70 else ("WARNING" if pct >= 40 else "FAIL")
    return CCMResult(
        "evidence_linked", "5.35", name, status,
        _t("ccm.evidence_linked.detail", lang, ok=linked, total=total_ev, pct=pct), value=pct,
        recommendation="" if status == "PASS" else _t("ccm.evidence_linked.rec", lang),
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

# Mapeo fn.__name__ -> test_id corto (para catalogo i18n)
_TEST_KEYS: dict[str, str] = {
    "test_all_assets_have_owner": "assets_owner",
    "test_assets_classified": "assets_classified",
    "test_high_risks_have_treatment": "risks_treatment",
    "test_risks_over_appetite_have_tasks": "risks_tasks",
    "test_controls_have_evidence": "controls_evidence",
    "test_policies_current": "policies_current",
    "test_incidents_resolved": "incidents_resolved",
    "test_suppliers_reviewed": "suppliers_reviewed",
    "test_tasks_not_overdue": "tasks_overdue",
    "test_evidence_freshness": "evidence_fresh",
    "test_admin_users_have_mfa": "admin_mfa",
    "test_vulnerabilities_addressed": "vulns_addressed",
    "test_risk_appetite_defined": "risk_appetite",
    "test_compliance_frameworks_active": "frameworks_active",
    "test_data_backup_evidence": "backup_evidence",
    "test_open_risks_reviewed_recently": "risks_reviewed",
    "test_users_with_inactive_access": "user_inactive",
    "test_supplier_contracts_valid": "supplier_contracts",
    "test_gdpr_activities_documented": "gdpr_activities",
    "test_internal_audits_performed": "internal_audit",
    "test_nonconformities_addressed": "nc_addressed",
    "test_risk_context_complete": "risk_context",
    "test_treatment_tasks_assigned": "tasks_assigned",
    "test_awareness_training_recent": "awareness",
    "test_incident_response_plan": "ir_plan",
    "test_assets_with_risk_coverage": "asset_risk_coverage",
    "test_evidence_linked_to_controls": "evidence_linked",
}


def run_all_tests(db: Session, org_id: int, limit: int = 50, offset: int = 0,
                  lang: str = "es") -> dict:
    """Ejecuta todos los tests CCM para una organización con paginacion.

    Returns: {results, summary, score, timestamp, total_tests}
    """
    results = []
    counts = {"PASS": 0, "FAIL": 0, "WARNING": 0, "SKIP": 0}

    for test_fn in _ALL_TESTS:
        try:
            result = test_fn(db, org_id, lang)
            results.append(result.to_dict())
            counts[result.status] = counts.get(result.status, 0) + 1
        except Exception as exc:
            logger.exception("CCM test %s failed: %s", test_fn.__name__, exc)
            results.append({
                "test_id": test_fn.__name__,
                "control_code": "?",
                "name": test_fn.__name__,
                "status": "SKIP",
                "detail": _t("ccm.test_error", lang, error=exc),
                "recommendation": "",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            counts["SKIP"] += 1

    total_scored = counts["PASS"] + counts["FAIL"] + counts["WARNING"]
    score = round(
        (counts["PASS"] + counts["WARNING"] * 0.5) / max(1, total_scored) * 100, 1
    )

    # Aplicar paginación
    total_tests = len(results)
    paginated_results = results[offset:offset+limit]

    # Escribir ccm_last_status en las implementaciones de control para retroalimentar el motor
    try:
        _sync_ccm_status_to_controls(db, {"results": results}, org_id)
        db.commit()
    except Exception as _exc:
        logger.warning("CCM→control status sync failed: %s", _exc)

    return {
        "org_id": org_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": score,
        "counts": counts,
        "total_tests": total_tests,
        "offset": offset,
        "limit": limit,
        "returned": len(paginated_results),
        "results": paginated_results,
        "summary": _t(
            "ccm.summary", lang, score=score,
            p=counts["PASS"], w=counts["WARNING"],
            f=counts["FAIL"], s=counts["SKIP"],
        ),
    }


def _sync_ccm_status_to_controls(db: Session, ccm_results: dict, org_id: int) -> None:
    """Escribe el estado del ultimo test CCM en las implementaciones de control.

    Permite al motor de riesgos penalizar controles que fallan en CCM (factor 0.6).
    Solo actualiza CIs cuyo control_code coincide exactamente con el resultado del test.
    Dispara cascade recalc de riesgos si el estado cambia a FAIL.
    """
    from app.models import Control, ControlImplementation
    from app.routers.controls import _trigger_linked_risks_recalc

    now = datetime.now(timezone.utc)
    for result in ccm_results.get("results", []):
        control_code = (result.get("control_code") or "").strip()
        status = result.get("status")
        if not control_code or control_code in ("?", "") or status not in ("PASS", "FAIL", "WARNING"):
            continue

        control = db.query(Control).filter(Control.code == control_code).first()
        if not control:
            continue

        impls = db.query(ControlImplementation).filter(
            ControlImplementation.control_id == control.id,
            ControlImplementation.organization_id == org_id,
        ).all()

        for ci in impls:
            prev_status = ci.ccm_last_status
            ci.ccm_last_status = status
            ci.ccm_tested_at = now
            if status == "FAIL" and prev_status != "FAIL":
                # Control degradado por test FAIL → recalcular riesgos vinculados
                _trigger_linked_risks_recalc(ci.id, org_id)


def _sync_passed_tests_to_compliance(db: Session, ccm_results: dict, org_id: int) -> None:
    """Sincroniza tests CCM que pasan a PASS con ComplianceFrameworkStatus.

    Para cada test con PASS, busca el control asociado por control_code y actualiza
    los requisitos de compliance en estado PLANNED a PARTIAL.
    Sigue el mismo patron que auto_update_compliance_from_controls en compliance_service.
    """
    from app.models import (
        ComplianceFrameworkStatus, ComplianceRequirementStatus,
        Control, ControlImplementation, ControlStatus, RiskContext,
    )
    from app.services.compliance_service import load_framework

    passed_control_codes = {
        r.get("control_code", "").lower()
        for r in ccm_results.get("results", [])
        if r.get("status") == "PASS" and r.get("control_code")
    }
    if not passed_control_codes:
        return

    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    active_frameworks = (ctx.active_frameworks or []) if ctx else []

    for framework_code in active_frameworks:
        framework = load_framework(framework_code)
        if not framework:
            continue
        for req in framework.get("requirements", []):
            req_controls = [c.lower() for c in req.get("controls", [])]
            if not req_controls:
                continue
            if all(rc in passed_control_codes for rc in req_controls):
                existing = db.query(ComplianceFrameworkStatus).filter_by(
                    organization_id=org_id,
                    framework_code=framework_code,
                    requirement_id=req["id"],
                ).first()
                if existing and existing.status == ComplianceRequirementStatus.PLANNED:
                    existing.status = ComplianceRequirementStatus.PARTIAL
                    existing.completion_pct = 50
                    existing.last_reviewed_at = datetime.now(timezone.utc)


def run_single_test_for_control(control_id: int, org_id: int) -> None:
    """Re-ejecuta todos los tests CCM y sincroniza los que pasan con compliance.

    Se llama en background tras el cierre de una No Conformidad relacionada con un control.
    Usa su propia sesion de BD para no interferir con la sesion HTTP del caller.
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        results = run_all_tests(db, org_id)
        _sync_passed_tests_to_compliance(db, results, org_id)
        db.commit()
        logger.info(
            "CCM retest org=%d tras cierre NC de control %d: score=%s",
            org_id, control_id, results.get("score"),
        )
    except Exception as exc:
        logger.exception("CCM retest failed org=%d control=%d: %s", org_id, control_id, exc)
    finally:
        db.close()


def run_test_by_id(db: Session, org_id: int, test_id: str, lang: str = "es") -> Optional[dict]:
    """Ejecuta un test específico por ID."""
    for test_fn in _ALL_TESTS:
        if test_fn.__name__ == test_id or (
            hasattr(test_fn, "__doc__") and test_id in (test_fn.__doc__ or "")
        ):
            result = test_fn(db, org_id, lang)
            return result.to_dict()
    # Buscar por test_id en el resultado
    for test_fn in _ALL_TESTS:
        try:
            r = test_fn(db, org_id, lang)
            if r.test_id == test_id:
                return r.to_dict()
        except Exception:
            pass
    return None


def get_test_catalog(lang: str = "es") -> list[dict]:
    """Retorna catálogo de tests disponibles."""
    return [
        {
            "test_id": fn.__name__,
            "control_code": fn.__doc__.split("—")[0].strip().replace("def ", "") if fn.__doc__ else "",
            "description": _t(f"ccm.{_TEST_KEYS[fn.__name__]}.name", lang)
            if fn.__name__ in _TEST_KEYS else fn.__name__,
        }
        for fn in _ALL_TESTS
    ]
