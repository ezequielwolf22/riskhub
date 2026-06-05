"""Servicio de encuestas distribuidas — sin autenticación de destinatario."""
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("riskhub.survey")

TOKEN_EXPIRY_DAYS = 30


def generate_response_token() -> str:
    return secrets.token_urlsafe(40)


def next_campaign_code(db: Session, org_id: int) -> str:
    from app.models import SurveyCampaign
    n = db.query(SurveyCampaign).filter_by(organization_id=org_id).count()
    return f"SRV-{n + 1:04d}"


def create_campaign(db: Session, org_id: int, user_id: int,
                    title: str, campaign_type: str,
                    questions: list, deadline_days: int = 14,
                    scope_risk_ids: list = None,
                    scope_asset_ids: list = None,
                    intro_text: str = None,
                    template_id: int = None,
                    show_risk_context: bool = True,
                    allow_comments: bool = True) -> "SurveyCampaign":
    from app.models import SurveyCampaign
    deadline = datetime.now(timezone.utc) + timedelta(days=deadline_days)
    campaign = SurveyCampaign(
        organization_id=org_id,
        code=next_campaign_code(db, org_id),
        title=title,
        template_id=template_id,
        campaign_type=campaign_type,
        scope_risk_ids=scope_risk_ids or [],
        scope_asset_ids=scope_asset_ids or [],
        questions=questions,
        deadline_at=deadline,
        status="draft",
        created_by_id=user_id,
        intro_text=intro_text,
        show_risk_context=show_risk_context,
        allow_comments=allow_comments,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def add_respondent(db: Session, campaign: "SurveyCampaign",
                   name: str, email: str,
                   role: str = None, dept: str = None,
                   user_id: int = None) -> "SurveyResponse":
    from app.models import SurveyResponse
    existing = db.query(SurveyResponse).filter_by(
        campaign_id=campaign.id,
        respondent_email=email.lower().strip()
    ).first()
    if existing:
        return existing
    token = generate_response_token()
    resp = SurveyResponse(
        campaign_id=campaign.id,
        organization_id=campaign.organization_id,
        respondent_name=name,
        respondent_email=email.lower().strip(),
        respondent_role=role,
        respondent_dept=dept,
        user_id=user_id,
        token=token,
        token_expires_at=campaign.deadline_at + timedelta(days=3),
        status="pending",
    )
    db.add(resp)
    db.commit()
    db.refresh(resp)
    return resp


def get_response_by_token(db: Session, token: str) -> Optional["SurveyResponse"]:
    from app.models import SurveyResponse
    resp = db.query(SurveyResponse).filter_by(token=token).first()
    if not resp:
        return None
    expires = resp.token_expires_at
    if not expires.tzinfo:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        resp.status = "expired"
        db.commit()
        return None
    return resp


def save_answers(db: Session, response: "SurveyResponse",
                 answers: list, general_comment: str = None,
                 ip: str = None, ua: str = None) -> None:
    from app.models import SurveyCampaign
    if response.status == "pending":
        response.opened_at = datetime.now(timezone.utc)
    response.answers = answers
    response.general_comment = general_comment
    response.status = "completed"
    response.completed_at = datetime.now(timezone.utc)
    response.ip_address = ip
    response.user_agent = (ua or "")[:255]
    db.commit()
    campaign = db.get(SurveyCampaign, response.campaign_id)
    if campaign and campaign.scope_risk_ids:
        _update_risk_survey_count(db, campaign)


def _update_risk_survey_count(db: Session, campaign: "SurveyCampaign") -> None:
    from app.models import Risk, SurveyResponse
    completed = db.query(SurveyResponse).filter_by(
        campaign_id=campaign.id, status="completed"
    ).count()
    for rid in (campaign.scope_risk_ids or []):
        risk = db.get(Risk, rid)
        if risk:
            risk.survey_response_count = completed
            risk.last_survey_date = datetime.now(timezone.utc)
    db.commit()


def apply_responses_to_risks(db: Session, campaign_id: int,
                              applied_by_id: int) -> dict:
    """Toma respuestas completadas y actualiza likelihood/impact promediando entre todas."""
    from app.models import SurveyCampaign, SurveyResponse, Risk
    campaign = db.get(SurveyCampaign, campaign_id)
    if not campaign:
        return {"error": "Campaña no encontrada"}
    completed = db.query(SurveyResponse).filter_by(
        campaign_id=campaign_id, status="completed", applied_to_risks=False
    ).all()
    if not completed:
        return {"applied": 0, "message": "No hay respuestas completadas por aplicar"}
    changes = []
    for risk_id in (campaign.scope_risk_ids or []):
        risk = db.get(Risk, risk_id)
        if not risk:
            continue
        likelihoods, impacts = [], []
        for resp in completed:
            for ans in (resp.answers or []):
                q_id = ans.get("question_id") or ans.get("id")
                q = next((q for q in campaign.questions if q.get("id") == q_id), None)
                if not q:
                    continue
                risk_field = q.get("risk_field")
                val = ans.get("value")
                if risk_field == "inherent_likelihood" and val:
                    try:
                        likelihoods.append(int(val))
                    except (ValueError, TypeError):
                        pass
                elif risk_field == "inherent_consequence" and val:
                    try:
                        impacts.append(int(val))
                    except (ValueError, TypeError):
                        pass
        old_l = risk.inherent_likelihood
        old_c = risk.inherent_consequence
        if likelihoods:
            avg_l = round(sum(likelihoods) / len(likelihoods))
            risk.inherent_likelihood = max(0, min(4, avg_l - 1))
        if impacts:
            avg_c = round(sum(impacts) / len(impacts))
            risk.inherent_consequence = max(0, min(4, avg_c - 1))
        if old_l != risk.inherent_likelihood or old_c != risk.inherent_consequence:
            changes.append({
                "risk_id": risk_id,
                "risk_code": risk.code,
                "likelihood_before": old_l, "likelihood_after": risk.inherent_likelihood,
                "impact_before": old_c, "impact_after": risk.inherent_consequence,
                "responses_count": len(completed),
            })
    now = datetime.now(timezone.utc)
    for resp in completed:
        resp.applied_to_risks = True
        resp.applied_at = now
        resp.applied_by_id = applied_by_id
    db.commit()
    return {"applied": len(changes), "changes": changes}


def send_campaign_invitations(db: Session, campaign_id: int,
                               base_url: str) -> dict:
    """Envía emails de invitación a todos los destinatarios pendientes."""
    from app.models import SurveyCampaign, SurveyResponse
    from app.services.email_service import get_settings, send_email
    campaign = db.get(SurveyCampaign, campaign_id)
    if not campaign or campaign.status not in ("draft", "active"):
        return {"sent": 0, "error": "Campaña no válida para envío"}
    campaign.status = "active"
    db.commit()
    cfg = get_settings(db, campaign.organization_id)
    if not cfg or not cfg.smtp_host:
        return {"sent": 0, "error": "SMTP no configurado"}
    pending = db.query(SurveyResponse).filter_by(
        campaign_id=campaign_id, status="pending"
    ).all()
    sent = 0
    for resp in pending:
        survey_url = f"{base_url}/survey/{resp.token}"
        deadline_str = campaign.deadline_at.strftime("%d/%m/%Y") if campaign.deadline_at else "próximamente"
        subject = f"[RiskHub] Tu opinión es importante: {campaign.title}"
        html = _build_invitation_email(resp, campaign, survey_url, deadline_str)
        try:
            send_email(cfg, resp.respondent_email, subject, html)
            sent += 1
        except Exception as e:
            logger.warning("Survey email failed for %s: %s", resp.respondent_email, e)
    return {"sent": sent, "total": len(pending)}


def _build_invitation_email(resp, campaign, url: str, deadline: str) -> str:
    name = resp.respondent_name or "Estimado/a colaborador/a"
    intro = campaign.intro_text or (
        "Como parte del proceso de gestión de riesgos, necesitamos tu valoración "
        "sobre los riesgos de seguridad que afectan a tu área de trabajo."
    )
    return f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#1a1a2e">
  <div style="background:linear-gradient(135deg,#5B00AD,#E05500);padding:24px;border-radius:8px 8px 0 0">
    <h1 style="color:#fff;margin:0;font-size:20px">RiskHub — Evaluación de riesgos</h1>
  </div>
  <div style="background:#fff;padding:28px;border:1px solid #e2e2ed;border-top:none;border-radius:0 0 8px 8px">
    <p style="margin:0 0 16px">Hola <strong>{name}</strong>,</p>
    <p style="margin:0 0 16px;color:#3d3d5c">{intro}</p>
    <p style="margin:0 0 8px;font-size:13px;color:#8585a0">
      Encuesta: <strong>{campaign.title}</strong><br>
      Plazo: {deadline}
    </p>
    <div style="margin:24px 0;text-align:center">
      <a href="{url}" style="background:linear-gradient(135deg,#5B00AD,#E05500);color:#fff;
         padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:600;
         font-size:15px;display:inline-block">
        Responder encuesta
      </a>
    </div>
    <p style="font-size:11px;color:#8585a0;margin:0">
      No necesitas cuenta ni contraseña. El enlace es personal e intransferible.<br>
      Si recibes este email por error, puedes ignorarlo sin más.
    </p>
  </div>
</div>"""


def send_reminders(db: Session, base_url: str) -> int:
    """Job del scheduler: recordatorio a destinatarios pendientes próximos al deadline."""
    from app.models import SurveyCampaign, SurveyResponse
    from app.services.email_service import get_settings, send_email
    now = datetime.now(timezone.utc)
    sent = 0
    active = db.query(SurveyCampaign).filter_by(status="active").all()
    for campaign in active:
        if not campaign.deadline_at:
            continue
        deadline_dt = campaign.deadline_at
        if not deadline_dt.tzinfo:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
        days_left = (deadline_dt - now).days
        if days_left not in (campaign.reminder_days, 1):
            continue
        cfg = get_settings(db, campaign.organization_id)
        if not cfg or not cfg.smtp_host:
            continue
        pending = db.query(SurveyResponse).filter_by(
            campaign_id=campaign.id, status="pending"
        ).all()
        for resp in pending:
            if resp.last_reminder_at:
                last = resp.last_reminder_at
                if not last.tzinfo:
                    last = last.replace(tzinfo=timezone.utc)
                if (now - last).total_seconds() < 86400:
                    continue
            survey_url = f"{base_url}/survey/{resp.token}"
            subject = f"[RiskHub] Recordatorio: {campaign.title} — {days_left} día(s) restante(s)"
            html = _build_invitation_email(resp, campaign, survey_url,
                                            deadline_dt.strftime("%d/%m/%Y"))
            try:
                send_email(cfg, resp.respondent_email, subject, html)
                resp.last_reminder_at = now
                sent += 1
            except Exception:
                pass
    if sent > 0:
        db.commit()
    return sent
