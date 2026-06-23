"""GDPR — Registro de actividades de tratamiento (Art. 30) y DPIA (Art. 35)."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import DPIA, DPIAStatus, ProcessingActivity, User
from app.schemas import (
    DPIAIn, DPIAOut, DPIAUpdate,
    ProcessingActivityIn, ProcessingActivityOut, ProcessingActivityUpdate,
)
from app.security import check_org_access, filter_by_org, get_current_user, require_admin, require_analyst
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/gdpr", tags=["gdpr"])


def _next_pa_code(db: Session, org_id: int | None = None) -> str:
    q = db.query(ProcessingActivity)
    if org_id is not None:
        q = q.filter(ProcessingActivity.organization_id == org_id)
    n = q.count() + 1
    return f"PAR-{n:04d}"


def _next_dpia_code(db: Session, org_id: int | None = None) -> str:
    q = db.query(DPIA)
    if org_id is not None:
        q = q.filter(
            DPIA.activity_id.in_(
                db.query(ProcessingActivity.id).filter(ProcessingActivity.organization_id == org_id)
            )
        )
    n = q.count() + 1
    return f"DPI-{n:04d}"


# ---------- Processing Activities ----------

@router.get("/activities/", response_model=list[ProcessingActivityOut])
def list_activities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    requires_dpia: Optional[bool] = None,
    q: Optional[str] = None,
):
    query = filter_by_org(db.query(ProcessingActivity), ProcessingActivity, current_user)
    if requires_dpia is not None:
        query = query.filter(ProcessingActivity.requires_dpia == requires_dpia)
    if q:
        query = query.filter(ProcessingActivity.title.ilike(f"%{q}%"))
    return query.order_by(ProcessingActivity.updated_at.desc()).all()


@router.get("/stats/summary")
def gdpr_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    activities = filter_by_org(db.query(ProcessingActivity), ProcessingActivity, current_user).all()
    activity_ids = [a.id for a in activities]
    dpias = db.query(DPIA).filter(DPIA.activity_id.in_(activity_ids)).all() if activity_ids else []
    return {
        "total_activities": len(activities),
        "requires_dpia": sum(1 for a in activities if a.requires_dpia),
        "transfers_outside_eu": sum(1 for a in activities if a.transfers_outside_eu),
        "total_dpias": len(dpias),
        "dpias_pending": sum(1 for d in dpias if d.status == DPIAStatus.PENDING),
    }


@router.get("/activities/{activity_id}", response_model=ProcessingActivityOut)
def get_activity(activity_id: int, request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    lang = get_lang(request)
    a = db.query(ProcessingActivity).filter(ProcessingActivity.id == activity_id).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, _t("gdpr.activity_not_found", lang))
    return a


@router.post("/activities/", response_model=ProcessingActivityOut)
def create_activity(body: ProcessingActivityIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    a = ProcessingActivity(
        code=_next_pa_code(db, current_user.organization_id),
        organization_id=current_user.organization_id,
        title=body.title,
        purposes=body.purposes,
        legal_basis=body.legal_basis,
        data_categories=body.data_categories,
        data_subjects=body.data_subjects,
        recipients=body.recipients,
        transfers_outside_eu=body.transfers_outside_eu,
        transfer_safeguards=body.transfer_safeguards,
        retention_period=body.retention_period,
        security_measures=body.security_measures,
        controller_name=body.controller_name,
        dpo_contact=body.dpo_contact,
        requires_dpia=body.requires_dpia,
        owner_id=body.owner_id or current_user.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    log_action(db, current_user.id, "create", "processing_activity", str(a.id), {"code": a.code})

    # GDPR Art.35: si la actividad requiere DPIA, crear riesgo de privacidad automaticamente
    if a.requires_dpia:
        try:
            _auto_create_dpia_risk(db, a, current_user.organization_id)
        except Exception as _exc:
            import logging
            logging.getLogger(__name__).warning("GDPR→risk auto-create failed: %s", _exc)

    return a


def _auto_create_dpia_risk(db: Session, activity: ProcessingActivity, org_id: int) -> None:
    """Crea un riesgo de privacidad en el registro de riesgos cuando una actividad requiere DPIA (GDPR Art.35)."""
    from app.models import Risk, RiskStatus, TreatmentOption
    from app.routers.risks import _recalc

    # Evitar duplicados: buscar riesgo existente vinculado a la misma actividad
    existing = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.gdpr_activity_id == activity.id,
        Risk.status.notin_([RiskStatus.CLOSED]),
    ).first()
    if existing:
        return

    n = db.query(Risk).filter(Risk.organization_id == org_id).count() + 1
    risk = Risk(
        organization_id=org_id,
        code=f"RSK-{n:04d}",
        name=f"[DPIA] {activity.title[:100]}",
        description=(
            f"Riesgo de privacidad generado automaticamente por actividad de tratamiento "
            f"{activity.code} que requiere DPIA segun GDPR Art.35. "
            f"Revisa el impacto sobre los derechos y libertades de los interesados."
        ),
        category="privacy",
        inherent_likelihood=2,
        inherent_consequence=3,
        treatment_option=TreatmentOption.MODIFICATION,
        status=RiskStatus.IDENTIFIED,
        gdpr_activity_id=activity.id,
    )
    db.add(risk)
    db.flush()
    _recalc(db, risk)
    db.commit()


@router.patch("/activities/{activity_id}", response_model=ProcessingActivityOut)
def update_activity(activity_id: int, body: ProcessingActivityUpdate,
                    request: Request,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    a = db.query(ProcessingActivity).filter(ProcessingActivity.id == activity_id).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, _t("gdpr.activity_not_found", lang))
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(a, field, value)
    db.commit()
    db.refresh(a)
    log_action(db, current_user.id, "update", "processing_activity", str(a.id))
    return a


@router.delete("/activities/{activity_id}", status_code=204)
def delete_activity(activity_id: int, request: Request, db: Session = Depends(get_db),
                    current_user: User = Depends(require_admin)):
    # A2: solo admin — GDPR Art.30 exige conservar el registro; analyst no puede borrar
    lang = get_lang(request)
    a = db.query(ProcessingActivity).filter(ProcessingActivity.id == activity_id).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, _t("gdpr.activity_not_found", lang))
    db.delete(a)
    db.commit()


# ---------- DPIAs ----------

@router.get("/dpias/", response_model=list[DPIAOut])
def list_dpias(db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
               activity_id: Optional[int] = None):
    # DPIAs son sub-recursos de ProcessingActivity — filtrar via JOIN de org
    activities = filter_by_org(db.query(ProcessingActivity), ProcessingActivity, current_user).all()
    act_ids = [a.id for a in activities]
    q = db.query(DPIA).filter(DPIA.activity_id.in_(act_ids)) if act_ids else db.query(DPIA).filter(DPIA.id == -1)
    if activity_id:
        q = q.filter(DPIA.activity_id == activity_id)
    return q.order_by(DPIA.created_at.desc()).all()


@router.get("/dpias/{dpia_id}", response_model=DPIAOut)
def get_dpia(dpia_id: int, request: Request, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    lang = get_lang(request)
    d = db.query(DPIA).filter(DPIA.id == dpia_id).first()
    if not d:
        raise HTTPException(404, _t("gdpr.dpia_not_found", lang))
    # Verificar acceso via actividad padre
    activity = db.query(ProcessingActivity).filter(ProcessingActivity.id == d.activity_id).first()
    if not activity or not check_org_access(activity.organization_id, current_user):
        raise HTTPException(404, _t("gdpr.dpia_not_found", lang))
    return d


@router.post("/dpias/", response_model=DPIAOut)
def create_dpia(body: DPIAIn, request: Request, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    # Verificar que la actividad de tratamiento pertenece a la org del usuario
    activity = db.query(ProcessingActivity).filter(ProcessingActivity.id == body.activity_id).first()
    if not activity or not check_org_access(activity.organization_id, current_user):
        raise HTTPException(404, _t("gdpr.activity_not_found", lang))
    d = DPIA(
        code=_next_dpia_code(db, current_user.organization_id),
        activity_id=body.activity_id,
        title=body.title,
        necessity_assessment=body.necessity_assessment,
        risks_identified=body.risks_identified,
        risk_measures=body.risk_measures,
        residual_risk_level=body.residual_risk_level,
        dpo_opinion=body.dpo_opinion,
        owner_id=body.owner_id or current_user.id,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    log_action(db, current_user.id, "create", "dpia", str(d.id), {"code": d.code})
    return d


@router.patch("/dpias/{dpia_id}", response_model=DPIAOut)
def update_dpia(dpia_id: int, body: DPIAUpdate,
                request: Request,
                db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    d = db.query(DPIA).filter(DPIA.id == dpia_id).first()
    if not d:
        raise HTTPException(404, _t("gdpr.dpia_not_found", lang))
    activity = db.query(ProcessingActivity).filter(ProcessingActivity.id == d.activity_id).first()
    if not activity or not check_org_access(activity.organization_id, current_user):
        raise HTTPException(404, _t("gdpr.dpia_not_found", lang))
    update_data = body.model_dump(exclude_none=True)
    approving = update_data.get("status") == DPIAStatus.APPROVED and not d.reviewed_at
    if approving:
        update_data.setdefault("reviewed_at", datetime.now(timezone.utc))
        update_data.setdefault("approved_by_id", current_user.id)
    for field, value in update_data.items():
        setattr(d, field, value)
    db.commit()
    db.refresh(d)

    # DPIA aprobado → marcar Art.35 GDPR como PARTIAL en compliance
    if approving:
        try:
            from app.models import ComplianceFrameworkStatus, ComplianceRequirementStatus
            org_id = current_user.organization_id
            req = db.query(ComplianceFrameworkStatus).filter_by(
                organization_id=org_id,
                framework_code="gdpr",
                requirement_id="Art.35",
            ).first()
            if req and req.status not in (
                ComplianceRequirementStatus.IMPLEMENTED,
                ComplianceRequirementStatus.AUDITED,
            ):
                req.status = ComplianceRequirementStatus.PARTIAL
                req.completion_pct = 60
                db.commit()
        except Exception:
            pass

    log_action(db, current_user.id, "update", "dpia", str(d.id))
    return d


@router.delete("/dpias/{dpia_id}", status_code=204)
def delete_dpia(dpia_id: int, request: Request, db: Session = Depends(get_db),
                current_user: User = Depends(require_admin)):
    # A2: solo admin puede borrar DPIAs — evidencia de cumplimiento GDPR
    lang = get_lang(request)
    d = db.query(DPIA).filter(DPIA.id == dpia_id).first()
    if not d:
        raise HTTPException(404, _t("gdpr.dpia_not_found", lang))
    activity = db.query(ProcessingActivity).filter(ProcessingActivity.id == d.activity_id).first()
    if not activity or not check_org_access(activity.organization_id, current_user):
        raise HTTPException(404, _t("gdpr.dpia_not_found", lang))
    db.delete(d)
    db.commit()
