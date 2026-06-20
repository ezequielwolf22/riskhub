"""KRI — Key Risk Indicators: umbrales configurables sobre metricas de riesgo (v5.3.0)."""
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


class KRIUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    warning_threshold: Optional[float] = None
    breach_threshold: Optional[float] = None
    is_active: Optional[bool] = None
    alert_on_breach: Optional[bool] = None
    recipient_email: Optional[str] = None


class KRIOut(BaseModel):
    id: int
    organization_id: int
    risk_id: Optional[int]
    name: str
    metric_type: str
    warning_threshold: Optional[float]
    breach_threshold: Optional[float]
    current_value: Optional[float]
    status: str
    is_active: bool
    last_evaluated_at: Optional[datetime]
    created_at: Optional[datetime]
    alert_on_breach: bool
    recipient_email: Optional[str]

    model_config = {"from_attributes": True}


def _compute_kri_value(db: Session, kri: KRI, org_id: int) -> Optional[float]:
    """Calcula el valor actual de la metrica del KRI."""
    from sqlalchemy import text as _text
    from app.models import Incident, IncidentStatus, NonConformity, NCSeverity, NcStatus, TreatmentTask, TaskStatus

    risk_id = kri.risk_id

    if kri.metric_type == KRIMetricType.RESIDUAL_LEVEL.value:
        if not risk_id:
            return None
        r = db.get(Risk, risk_id)
        return float(r.residual_level) if r and r.residual_level is not None else None

    if kri.metric_type == KRIMetricType.INHERENT_LEVEL.value:
        if not risk_id:
            return None
        r = db.get(Risk, risk_id)
        return float(r.inherent_level) if r and r.inherent_level is not None else None

    if kri.metric_type == KRIMetricType.OPEN_INCIDENTS.value:
        q = db.query(Incident).filter(
            Incident.organization_id == org_id,
            Incident.status.notin_([IncidentStatus.CLOSED]),
        )
        if risk_id:
            # Incidentes que referencian este riesgo en related_risk_ids
            all_inc = q.all()
            count = sum(1 for i in all_inc if risk_id in (i.related_risk_ids or []))
            return float(count)
        return float(q.count())

    if kri.metric_type == KRIMetricType.OPEN_NCS.value:
        q = db.query(NonConformity).filter(
            NonConformity.organization_id == org_id,
            NonConformity.severity == NCSeverity.MAJOR,
            NonConformity.status.notin_([NcStatus.CLOSED]),
        )
        return float(q.count())

    if kri.metric_type == KRIMetricType.CONTROL_MATURITY.value:
        if not risk_id:
            return None
        rows = db.execute(
            _text("SELECT ci.maturity FROM risk_controls rc JOIN control_implementations ci ON ci.id = rc.control_implementation_id WHERE rc.risk_id = :rid"),
            {"rid": risk_id},
        ).fetchall()
        if not rows:
            return 0.0
        return round(sum(r[0] or 0 for r in rows) / len(rows), 2)

    if kri.metric_type == KRIMetricType.OVERDUE_TASKS.value:
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

    return None


def evaluate_kri(db: Session, kri: KRI, org_id: int) -> KRIStatus:
    """Evalua el KRI, actualiza current_value y status, y envia alerta si corresponde."""
    value = _compute_kri_value(db, kri, org_id)
    now = datetime.now(timezone.utc)
    kri.current_value = value
    kri.last_evaluated_at = now

    if value is None:
        kri.status = KRIStatus.NORMAL.value
        return KRIStatus.NORMAL

    new_status = KRIStatus.NORMAL
    if kri.breach_threshold is not None and value >= kri.breach_threshold:
        new_status = KRIStatus.BREACH
    elif kri.warning_threshold is not None and value >= kri.warning_threshold:
        new_status = KRIStatus.WARNING

    prev_status = kri.status
    kri.status = new_status.value

    # Alerta solo cuando hay nueva ruptura de umbral (no en cada evaluacion)
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
    subject = f"[RiskHub] KRI en BREACH: {kri.name}"
    body = (
        f"<p>El indicador clave de riesgo <strong>{safe_name}</strong> ha superado el umbral de alerta.</p>"
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
):
    q = filter_by_org(db.query(KRI), KRI, current_user)
    if active_only:
        q = q.filter(KRI.is_active == True)
    if risk_id is not None:
        q = q.filter(KRI.risk_id == risk_id)
    if status:
        q = q.filter(KRI.status == status)
    return q.order_by(KRI.id.asc()).all()


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
        created_at=datetime.now(timezone.utc),
    )
    db.add(kri)
    db.flush()
    # Evaluacion inicial
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
    log_action(db, current_user.id, "delete", "kri", str(kri_id), {"name": kri.name})
    db.delete(kri)
    db.commit()


@router.post("/{kri_id}/evaluate", response_model=KRIOut)
def evaluate_kri_now(
    kri_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Fuerza la evaluacion inmediata del KRI y actualiza su valor y estado."""
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
    """Evalua todos los KRIs activos de la organizacion."""
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
