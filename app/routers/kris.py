"""KRI/KPI — Key Risk Indicators y Key Performance Indicators (v5.4.0)."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import KRI, KRIMetricType, KRIStatus, Risk, RiskStatus, User
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/kris", tags=["kris"])


class KRICreate(BaseModel):
    risk_id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=255)
    metric_type: KRIMetricType
    warning_threshold: Optional[float] = None
    breach_threshold: Optional[float] = None
    alert_on_breach: bool = True
    recipient_email: Optional[str] = None
    indicator_type: str = "kri"
    direction: str = "lower_is_better"
    description: Optional[str] = None


class KRIUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    custom_name: Optional[str] = Field(default=None, max_length=255)
    warning_threshold: Optional[float] = None
    breach_threshold: Optional[float] = None
    is_active: Optional[bool] = None
    is_visible: Optional[bool] = None
    alert_on_breach: Optional[bool] = None
    recipient_email: Optional[str] = None
    direction: Optional[str] = None
    description: Optional[str] = None


class KRIOut(BaseModel):
    id: int
    organization_id: int
    risk_id: Optional[int]
    name: str
    custom_name: Optional[str]
    display_name: Optional[str] = None   # computed: custom_name ?? name
    metric_type: str
    description: Optional[str]
    indicator_type: str
    direction: str
    warning_threshold: Optional[float]
    breach_threshold: Optional[float]
    current_value: Optional[float]
    status: str
    is_active: bool
    is_visible: bool
    is_system: bool
    last_evaluated_at: Optional[datetime]
    created_at: Optional[datetime]
    alert_on_breach: bool
    recipient_email: Optional[str]

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):
        instance = super().model_validate(obj, **kwargs)
        instance.display_name = instance.custom_name or instance.name
        return instance


def _compute_kri_value(db: Session, kri: KRI, org_id: int) -> Optional[float]:
    """Calcula el valor actual de la metrica del KRI o KPI."""
    from sqlalchemy import text as _text
    from app.models import (
        Asset, BCPPlan, ControlImplementation, ControlStatus,
        Incident, IncidentStatus, NonConformity, NCSeverity, NcStatus,
        Policy, PolicyStatus, Supplier, SupplierQuestionnaire, SupplierTier,
        TreatmentTask, TaskStatus,
    )

    risk_id = kri.risk_id
    mt = kri.metric_type

    # --- KRI: metricas por riesgo individual ---

    if mt == KRIMetricType.RESIDUAL_LEVEL.value:
        if not risk_id:
            return None
        r = db.get(Risk, risk_id)
        return float(r.residual_level) if r and r.residual_level is not None else None

    if mt == KRIMetricType.INHERENT_LEVEL.value:
        if not risk_id:
            return None
        r = db.get(Risk, risk_id)
        return float(r.inherent_level) if r and r.inherent_level is not None else None

    if mt == KRIMetricType.OPEN_INCIDENTS.value:
        q = db.query(Incident).filter(
            Incident.organization_id == org_id,
            Incident.status.notin_([IncidentStatus.CLOSED]),
        )
        if risk_id:
            all_inc = q.all()
            count = sum(1 for i in all_inc if risk_id in (i.related_risk_ids or []))
            return float(count)
        return float(q.count())

    if mt == KRIMetricType.OPEN_NCS.value:
        q = db.query(NonConformity).filter(
            NonConformity.organization_id == org_id,
            NonConformity.severity == NCSeverity.MAJOR,
            NonConformity.status.notin_([NcStatus.CLOSED]),
        )
        return float(q.count())

    if mt == KRIMetricType.CONTROL_MATURITY.value:
        if not risk_id:
            return None
        rows = db.execute(
            _text("SELECT ci.maturity FROM risk_controls rc JOIN control_implementations ci ON ci.id = rc.control_implementation_id WHERE rc.risk_id = :rid"),
            {"rid": risk_id},
        ).fetchall()
        if not rows:
            return 0.0
        return round(sum(r[0] or 0 for r in rows) / len(rows), 2)

    if mt == KRIMetricType.OVERDUE_TASKS.value:
        now = datetime.now(timezone.utc)
        q = db.query(TreatmentTask).filter(
            TreatmentTask.organization_id == org_id,
            TreatmentTask.status.notin_([TaskStatus.DONE]),
            TreatmentTask.due_date.isnot(None),
            TreatmentTask.due_date < now,
        )
        if risk_id:
            q = q.filter(TreatmentTask.risk_id == risk_id)
        return float(q.count())

    # --- KPI: metricas de programa SGSI (nivel organizacion) ---

    if mt == KRIMetricType.KPI_TREATMENT_RATE.value:
        # % riesgos nivel alto (residual >= 4) con treatment_plan definido
        high = db.query(Risk).filter(
            Risk.organization_id == org_id,
            Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
            Risk.residual_level >= 4,
        ).all()
        if not high:
            return 100.0
        with_plan = sum(1 for r in high if r.treatment_plan and str(r.treatment_plan).strip())
        return round(with_plan / len(high) * 100, 1)

    if mt == KRIMetricType.KPI_MTTT.value:
        # Dias medios identificacion -> primer task creado
        risks = db.query(Risk).filter(
            Risk.organization_id == org_id,
            Risk.status.notin_([RiskStatus.CLOSED]),
            Risk.created_at.isnot(None),
        ).all()
        deltas = []
        for r in risks:
            first_task = db.query(TreatmentTask).filter(
                TreatmentTask.risk_id == r.id,
            ).order_by(TreatmentTask.id.asc()).first()
            if first_task and first_task.created_at and r.created_at:
                d = (first_task.created_at - r.created_at).days
                if d >= 0:
                    deltas.append(d)
        if not deltas:
            return 0.0
        return round(sum(deltas) / len(deltas), 1)

    if mt == KRIMetricType.KPI_CONTROL_COVERAGE.value:
        from app.models import Control
        total = db.query(Control).count()
        if not total:
            return 0.0
        implemented_ids = {
            ci.control_id for ci in db.query(ControlImplementation).filter(
                ControlImplementation.organization_id == org_id,
                ControlImplementation.status.in_([ControlStatus.IMPLEMENTED, ControlStatus.PARTIAL]),
            ).all()
        }
        return round(len(implemented_ids) / total * 100, 1)

    if mt == KRIMetricType.KPI_CONTROL_MATURITY_AVG.value:
        impls = db.query(ControlImplementation).filter(
            ControlImplementation.organization_id == org_id,
        ).all()
        if not impls:
            return 0.0
        return round(sum(ci.maturity or 0 for ci in impls) / len(impls), 2)

    if mt == KRIMetricType.KPI_POLICY_REVIEW.value:
        from datetime import date
        policies = db.query(Policy).filter(
            Policy.organization_id == org_id,
            Policy.status == PolicyStatus.PUBLISHED,
        ).all()
        if not policies:
            return 100.0
        today = date.today()
        in_review = sum(
            1 for p in policies
            if p.review_date is None or (hasattr(p.review_date, 'date') and p.review_date.date() >= today)
            or (isinstance(p.review_date, type(today)) and p.review_date >= today)
        )
        return round(in_review / len(policies) * 100, 1)

    if mt == KRIMetricType.KPI_NC_CLOSURE_RATE.value:
        from datetime import timedelta
        ncs = db.query(NonConformity).filter(
            NonConformity.organization_id == org_id,
            NonConformity.status == NcStatus.CLOSED,
        ).all()
        if not ncs:
            return 100.0
        closed_in_time = sum(
            1 for nc in ncs
            if nc.created_at and nc.closed_at and (nc.closed_at - nc.created_at).days <= 90
        )
        return round(closed_in_time / len(ncs) * 100, 1)

    if mt == KRIMetricType.KPI_RISK_REDUCTION_AVG.value:
        risks = db.query(Risk).filter(
            Risk.organization_id == org_id,
            Risk.inherent_level.isnot(None),
            Risk.residual_level.isnot(None),
            Risk.inherent_level > 0,
        ).all()
        if not risks:
            return 0.0
        reductions = [
            (r.inherent_level - r.residual_level) / r.inherent_level * 100
            for r in risks
        ]
        return round(sum(reductions) / len(reductions), 1)

    if mt == KRIMetricType.KPI_APPETITE_COMPLIANCE.value:
        risks = db.query(Risk).filter(
            Risk.organization_id == org_id,
            Risk.status.notin_([RiskStatus.CLOSED]),
            Risk.residual_level.isnot(None),
        ).all()
        if not risks:
            return 100.0
        within = sum(1 for r in risks if r.residual_level <= 4)
        return round(within / len(risks) * 100, 1)

    if mt == KRIMetricType.KPI_ASSET_COVERAGE.value:
        total_assets = db.query(Asset).filter(Asset.organization_id == org_id).count()
        if not total_assets:
            return 0.0
        asset_ids_with_risk = {
            r.asset_id for r in db.query(Risk).filter(
                Risk.organization_id == org_id,
                Risk.asset_id.isnot(None),
            ).all()
        }
        return round(len(asset_ids_with_risk) / total_assets * 100, 1)

    if mt == KRIMetricType.KPI_RISK_NO_OWNER.value:
        risks = db.query(Risk).filter(
            Risk.organization_id == org_id,
            Risk.status.notin_([RiskStatus.CLOSED]),
        ).all()
        if not risks:
            return 0.0
        no_owner = sum(1 for r in risks if not r.owner_id)
        return round(no_owner / len(risks) * 100, 1)

    if mt == KRIMetricType.KPI_HIGH_RISKS_NO_PLAN.value:
        high_no_plan = db.query(Risk).filter(
            Risk.organization_id == org_id,
            Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
            Risk.residual_level >= 4,
        ).all()
        count = sum(1 for r in high_no_plan if not r.treatment_plan or not str(r.treatment_plan).strip())
        return float(count)

    if mt == KRIMetricType.KPI_NIS2_NOTIFICATION.value:
        nis2_incidents = db.query(Incident).filter(
            Incident.organization_id == org_id,
            Incident.nis2_notification_required == True,
        ).all()
        if not nis2_incidents:
            return 100.0
        from datetime import timedelta
        notified_in_time = sum(
            1 for i in nis2_incidents
            if i.nis2_notification_sent_at and i.detected_at
            and (i.nis2_notification_sent_at - i.detected_at) <= timedelta(hours=72)
        )
        return round(notified_in_time / len(nis2_incidents) * 100, 1)

    if mt == KRIMetricType.KPI_BCP_COVERAGE.value:
        total_bcp = db.query(BCPPlan).filter(BCPPlan.organization_id == org_id).count()
        if not total_bcp:
            return 0.0
        approved = db.query(BCPPlan).filter(
            BCPPlan.organization_id == org_id,
            BCPPlan.status == "approved",
        ).count()
        return round(approved / total_bcp * 100, 1)

    if mt == KRIMetricType.KPI_MTTR_INCIDENTS.value:
        resolved = db.query(Incident).filter(
            Incident.organization_id == org_id,
            Incident.status.in_([IncidentStatus.RESOLVED, IncidentStatus.CLOSED]),
            Incident.detected_at.isnot(None),
            Incident.resolved_at.isnot(None),
        ).all()
        if not resolved:
            return 0.0
        days = [(i.resolved_at - i.detected_at).days for i in resolved if i.resolved_at >= i.detected_at]
        if not days:
            return 0.0
        return round(sum(days) / len(days), 1)

    if mt == KRIMetricType.KPI_SUPPLIER_COVERAGE.value:
        from datetime import timedelta
        tier1 = db.query(Supplier).filter(
            Supplier.organization_id == org_id,
            Supplier.tier == SupplierTier.TIER_1,
        ).all()
        if not tier1:
            return 100.0
        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        evaluated_ids = set()
        for sup in tier1:
            q = db.query(SupplierQuestionnaire).filter(
                SupplierQuestionnaire.supplier_id == sup.id,
                SupplierQuestionnaire.status == "completed",
                SupplierQuestionnaire.submitted_at.isnot(None),
                SupplierQuestionnaire.submitted_at >= cutoff,
            ).first()
            if q:
                evaluated_ids.add(sup.id)
        return round(len(evaluated_ids) / len(tier1) * 100, 1)

    return None


def evaluate_kri(db: Session, kri: KRI, org_id: int) -> KRIStatus:
    """Evalua el KRI/KPI, actualiza current_value y status, y envia alerta si corresponde."""
    value = _compute_kri_value(db, kri, org_id)
    now = datetime.now(timezone.utc)
    kri.current_value = value
    kri.last_evaluated_at = now

    if value is None:
        kri.status = KRIStatus.NORMAL.value
        return KRIStatus.NORMAL

    direction = getattr(kri, 'direction', None) or 'lower_is_better'
    new_status = KRIStatus.NORMAL

    if direction == 'higher_is_better':
        # Para metricas donde mayor es mejor: warning si < warning_threshold, breach si < breach_threshold
        if kri.breach_threshold is not None and value <= kri.breach_threshold:
            new_status = KRIStatus.BREACH
        elif kri.warning_threshold is not None and value <= kri.warning_threshold:
            new_status = KRIStatus.WARNING
    else:
        # Para metricas donde menor es mejor: warning si >= warning_threshold, breach si >= breach_threshold
        if kri.breach_threshold is not None and value >= kri.breach_threshold:
            new_status = KRIStatus.BREACH
        elif kri.warning_threshold is not None and value >= kri.warning_threshold:
            new_status = KRIStatus.WARNING

    prev_status = kri.status
    kri.status = new_status.value

    if kri.alert_on_breach and new_status == KRIStatus.BREACH and prev_status != KRIStatus.BREACH.value:
        try:
            _send_kri_alert(db, kri, value, org_id)
        except Exception:
            pass

    return new_status


def _send_kri_alert(db: Session, kri: KRI, value: float, org_id: int) -> None:
    from app.models import User, UserRole
    from app.services import email_service

    cfg = email_service.get_settings_for_org(db, org_id)
    if not cfg or not cfg.smtp_host:
        return

    recipients = []
    if kri.recipient_email:
        recipients.append(kri.recipient_email)
    else:
        admins = db.query(User).filter(
            User.organization_id == org_id,
            User.role == UserRole.ADMIN,
            User.is_active == True,
            User.email.isnot(None),
        ).all()
        recipients = [a.email for a in admins]

    import html as _html
    safe_name = _html.escape(str(kri.name))
    label = "KPI" if getattr(kri, 'indicator_type', 'kri') == 'kpi' else "KRI"
    subject = f"[RiskHub] {label} en BREACH: {kri.name}"
    body = (
        f"<p>El indicador <strong>{safe_name}</strong> ha superado el umbral de alerta.</p>"
        f"<p>Valor actual: <strong>{value}</strong> (umbral: {kri.breach_threshold})</p>"
        f"<p>Revisa el estado en RiskHub para tomar accion correctiva.</p>"
    )
    for email in recipients:
        try:
            email_service.send_email(cfg, email, subject,
                                     email_service._wrap_html(subject, body, ""))
        except Exception:
            pass


@router.get("/", response_model=list[KRIOut])
def list_kris(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    risk_id: Optional[int] = None,
    status: Optional[str] = None,
    active_only: bool = True,
    indicator_type: Optional[str] = None,
    show_hidden: bool = False,
):
    q = filter_by_org(db.query(KRI), KRI, current_user)
    if active_only:
        q = q.filter(KRI.is_active == True)
    if risk_id is not None:
        q = q.filter(KRI.risk_id == risk_id)
    if status:
        q = q.filter(KRI.status == status)
    if indicator_type:
        q = q.filter(KRI.indicator_type == indicator_type)
    if not show_hidden:
        q = q.filter(KRI.is_visible == True)
    return q.order_by(KRI.indicator_type.asc(), KRI.id.asc()).all()


@router.get("/{kri_id}", response_model=KRIOut)
def get_kri(
    kri_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kri = db.get(KRI, kri_id)
    if not kri or not check_org_access(kri.organization_id, current_user):
        raise HTTPException(404, "KRI no encontrado")
    return kri


@router.post("/", response_model=KRIOut, status_code=201)
def create_kri(
    body: KRICreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    org_id = current_user.organization_id
    if body.risk_id:
        r = db.get(Risk, body.risk_id)
        if not r or not check_org_access(r.organization_id, current_user):
            raise HTTPException(404, "Riesgo no encontrado")

    kri = KRI(
        organization_id=org_id,
        risk_id=body.risk_id,
        name=body.name,
        metric_type=body.metric_type.value,
        warning_threshold=body.warning_threshold,
        breach_threshold=body.breach_threshold,
        alert_on_breach=body.alert_on_breach,
        recipient_email=body.recipient_email,
        indicator_type=body.indicator_type,
        direction=body.direction,
        description=body.description,
        is_system=False,
        is_visible=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(kri)
    db.flush()
    evaluate_kri(db, kri, org_id)
    db.commit()
    db.refresh(kri)
    log_action(db, current_user.id, "create", "kri", str(kri.id), {"name": kri.name})
    return kri


@router.patch("/{kri_id}", response_model=KRIOut)
def update_kri(
    kri_id: int,
    body: KRIUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    kri = db.get(KRI, kri_id)
    if not kri or not check_org_access(kri.organization_id, current_user):
        raise HTTPException(404, "KRI no encontrado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(kri, field, value)
    db.commit()
    db.refresh(kri)
    log_action(db, current_user.id, "update", "kri", str(kri_id))
    return kri


@router.delete("/{kri_id}", status_code=204)
def delete_kri(
    kri_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    kri = db.get(KRI, kri_id)
    if not kri or not check_org_access(kri.organization_id, current_user):
        raise HTTPException(404, "KRI no encontrado")
    if kri.is_system:
        raise HTTPException(400, "Los indicadores de sistema no se pueden eliminar. Puedes ocultarlos.")
    log_action(db, current_user.id, "delete", "kri", str(kri_id), {"name": kri.name})
    db.delete(kri)
    db.commit()


@router.post("/{kri_id}/evaluate", response_model=KRIOut)
def evaluate_kri_now(
    kri_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Fuerza la evaluacion inmediata del KRI/KPI y actualiza su valor y estado."""
    kri = db.get(KRI, kri_id)
    if not kri or not check_org_access(kri.organization_id, current_user):
        raise HTTPException(404, "KRI no encontrado")
    evaluate_kri(db, kri, kri.organization_id)
    db.commit()
    db.refresh(kri)
    return kri


@router.post("/evaluate-all")
def evaluate_all_kris(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Evalua todos los KRIs/KPIs activos de la organizacion."""
    org_id = current_user.organization_id
    kris = db.query(KRI).filter(
        KRI.organization_id == org_id,
        KRI.is_active == True,
    ).all()

    results = {"evaluated": 0, "normal": 0, "warning": 0, "breach": 0}
    for kri in kris:
        status = evaluate_kri(db, kri, org_id)
        results["evaluated"] += 1
        results[status.value] += 1

    db.commit()
    return results


@router.post("/seed-kpis")
def seed_kpis(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Inicializa los KPIs de sistema por defecto para la organizacion (idempotente)."""
    from app.seed import _seed_default_kpis
    org_id = current_user.organization_id
    _seed_default_kpis(db, org_id)
    # Evaluar inmediatamente todos
    kpis = db.query(KRI).filter(
        KRI.organization_id == org_id,
        KRI.indicator_type == "kpi",
        KRI.is_active == True,
    ).all()
    for kpi in kpis:
        try:
            evaluate_kri(db, kpi, org_id)
        except Exception:
            pass
    db.commit()
    total = db.query(KRI).filter(KRI.organization_id == org_id, KRI.indicator_type == "kpi").count()
    return {"ok": True, "total_kpis": total}
