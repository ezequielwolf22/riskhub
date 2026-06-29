"""Gestion de incidentes de seguridad — NIS2 Art. 23 + ISO 27035."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import Asset, Incident, IncidentStatus, Risk, User
from app.schemas import IncidentIn, IncidentOut, IncidentUpdate
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


def _next_code(db: Session, org_id: int) -> str:
    from sqlalchemy import func
    max_id = db.query(func.max(Incident.id)).scalar() or 0
    return f"INC-{max_id + 1:04d}"


@router.get("/", response_model=list[IncidentOut])
def list_incidents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: Optional[IncidentStatus] = None,
    severity: Optional[str] = None,
    nis2: Optional[bool] = None,
):
    q = filter_by_org(db.query(Incident), Incident, current_user)
    if status:
        q = q.filter(Incident.status == status)
    if severity:
        q = q.filter(Incident.severity == severity)
    if nis2 is not None:
        q = q.filter(Incident.nis2_notification_required == nis2)
    return q.order_by(Incident.created_at.desc()).all()


@router.get("/stats/summary")
def incidents_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    incidents = filter_by_org(db.query(Incident), Incident, current_user).all()
    now = datetime.now(timezone.utc)
    open_count = sum(1 for i in incidents if i.status not in (IncidentStatus.CLOSED,))
    p1p2 = sum(1 for i in incidents if i.severity in ("p1", "p2") and i.status != IncidentStatus.CLOSED)
    nis2_pending = sum(
        1 for i in incidents
        if i.nis2_notification_required and not i.nis2_notification_sent_at
        and i.status != IncidentStatus.CLOSED
    )
    return {
        "total": len(incidents),
        "open": open_count,
        "p1_p2_open": p1p2,
        "nis2_pending_notification": nis2_pending,
    }


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: int, request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    lang = get_lang(request)
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc or not check_org_access(inc.organization_id, current_user):
        raise HTTPException(404, _t("incidents.not_found", lang))
    return inc


@router.post("/", response_model=IncidentOut)
def create_incident(body: IncidentIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    # C2: validar que los asset_ids y risk_ids pertenecen a la misma org
    org_id = current_user.organization_id
    for aid in (body.affected_asset_ids or []):
        a = db.get(Asset, aid)
        if not a or a.organization_id != org_id:
            raise HTTPException(422, f"Asset {aid} no pertenece a tu organizacion")
    for rid in (body.related_risk_ids or []):
        r = db.get(Risk, rid)
        if not r or r.organization_id != org_id:
            raise HTTPException(422, f"Riesgo {rid} no pertenece a tu organizacion")

    inc = Incident(
        code=_next_code(db, org_id),
        organization_id=org_id,
        title=body.title,
        description=body.description,
        severity=body.severity,
        status=body.status,
        detected_at=body.detected_at or datetime.now(timezone.utc),
        nis2_notification_required=body.nis2_notification_required,
        # C1: nis2_notification_sent_at NO se acepta del usuario — solo via /notify-nis2
        gdpr_notification_required=body.gdpr_notification_required,
        affected_systems=body.affected_systems,
        affected_asset_ids=body.affected_asset_ids,
        related_risk_ids=body.related_risk_ids,
        root_cause=body.root_cause,
        response_actions=body.response_actions,
        lessons_learned=body.lessons_learned,
        owner_id=body.owner_id,
        affects_continuity=body.affects_continuity,
        bcp_activation_id=body.bcp_activation_id,
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    # Auto-vincular riesgos existentes para los activos afectados (v1.7.7)
    try:
        asset_ids = inc.affected_asset_ids or []
        if asset_ids:
            from app.models import Risk, RiskStatus
            linked_risk_ids = list(inc.related_risk_ids or [])
            active_risks = db.query(Risk).filter(
                Risk.asset_id.in_(asset_ids),
                Risk.organization_id == current_user.organization_id,
                Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
            ).order_by(Risk.residual_level.desc()).limit(20).all()
            for r in active_risks:
                if r.id not in linked_risk_ids:
                    linked_risk_ids.append(r.id)
            if linked_risk_ids != list(inc.related_risk_ids or []):
                inc.related_risk_ids = linked_risk_ids
                db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Incident->risks auto-link failed")
    log_action(db, current_user.id, "create", "incident", str(inc.id),
               {"code": inc.code, "severity": inc.severity.value})
    # Comprobar si el incidente activa criterios de algún proceso BCP (ISO 22301 cl. 8.4)
    try:
        from app.services.bcp_service import check_incident_bcp_activation
        check_incident_bcp_activation(db, inc, current_user.organization_id)
    except Exception as _e:
        import logging as _logging
        _logging.getLogger(__name__).debug("BCP activation check skipped: %s", _e)
    return inc


def _propagate_incident_close_to_risks(db: Session, inc: "Incident") -> None:
    """Retroalimentacion de materializacion: incidente cerrado → likelihood++ en riesgos vinculados.

    ISO 27005 §8.3: la materializacion de una amenaza es evidencia directa para
    recalibrar la probabilidad inherente del riesgo asociado.
    Solo incrementa riesgos activos (no CLOSED/ACCEPTED) que aun no esten al maximo.
    """
    from app.models import Risk, RiskStatus
    from app.routers.risks import _recalc

    risk_ids = inc.related_risk_ids or []
    if not risk_ids:
        return

    org_id = inc.organization_id
    risks = db.query(Risk).filter(
        Risk.id.in_(risk_ids),
        Risk.organization_id == org_id,
        Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
        Risk.inherent_likelihood < 4,
    ).all()

    for r in risks:
        old_lik = r.inherent_likelihood
        r.inherent_likelihood = min(4, r.inherent_likelihood + 1)
        r.likelihood_adjusted_reason = f"Materializacion confirmada — incidente {inc.code}"
        _recalc(db, r)
        log_action(db, None, "risk_likelihood_adjusted", "risk", str(r.id), {
            "incident_code": inc.code,
            "incident_id": inc.id,
            "old_likelihood": old_lik,
            "new_likelihood": r.inherent_likelihood,
            "source": "incident_closed",
        })

    if risks:
        db.commit()


@router.patch("/{incident_id}", response_model=IncidentOut)
def update_incident(incident_id: int, body: IncidentUpdate, request: Request,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc or not check_org_access(inc.organization_id, current_user):
        raise HTTPException(404, _t("incidents.not_found", lang))

    old_status = inc.status
    update_data = body.model_dump(exclude_none=True)
    detected_at_changed = (
        "detected_at" in update_data and
        update_data["detected_at"] != inc.detected_at
    )

    for field, value in update_data.items():
        setattr(inc, field, value)
    db.commit()
    db.refresh(inc)

    # Si cambia detected_at → recalcular deadlines NIS2 pendientes
    if detected_at_changed:
        try:
            from app.services.nis2_service import recalculate_nis2_deadlines
            recalculate_nis2_deadlines(db, inc.id)
        except Exception as _e:
            pass  # no bloquear la respuesta si el recalculo falla

    # Retroalimentacion de materializacion al cerrar el incidente
    if inc.status == IncidentStatus.CLOSED and old_status != IncidentStatus.CLOSED:
        try:
            _propagate_incident_close_to_risks(db, inc)
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning("Incident close→risk propagation failed: %s", _e)

    log_action(db, current_user.id, "update", "incident", str(inc.id))
    return inc


@router.delete("/{incident_id}", status_code=204)
def delete_incident(incident_id: int, request: Request, db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc or not check_org_access(inc.organization_id, current_user):
        raise HTTPException(404, _t("incidents.not_found", lang))
    log_action(db, current_user.id, "delete", "incident", str(incident_id),
               {"code": inc.code})
    db.delete(inc)
    db.commit()
    return


@router.post("/{incident_id}/notify-nis2", response_model=IncidentOut)
def notify_nis2(incident_id: int, request: Request, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    """Marca un incidente como notificado a NIS2 (Art. 23).

    Este es el ÚNICO endpoint autorizado para escribir nis2_notification_sent_at.
    Usa timestamp del servidor para garantizar integridad del registro de auditoría.
    """
    lang = get_lang(request)
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc or not check_org_access(inc.organization_id, current_user):
        raise HTTPException(404, _t("incidents.not_found", lang))
    if not inc.nis2_notification_required:
        raise HTTPException(400, "Incidente no requiere notificación NIS2")
    if inc.nis2_notification_sent_at:
        raise HTTPException(400, "Incidente ya ha sido notificado a NIS2")

    # Timestamp servidor — no se acepta del cliente
    inc.nis2_notification_sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(inc)
    log_action(db, current_user.id, "notify_nis2", "incident", str(inc.id),
               {"code": inc.code, "sent_at": inc.nis2_notification_sent_at.isoformat()})
    return inc
