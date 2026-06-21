"""Router de encuestas distribuidas — gestión interna y respuesta pública."""
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SurveyTemplate, SurveyCampaign, SurveyResponse
from app.security import get_current_user, require_analyst, require_admin
from app.services.audit_service import log_action
from app.services import survey_service

logger = logging.getLogger("riskhub.surveys")

router = APIRouter(prefix="/api/surveys", tags=["surveys"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    survey_type: str = "risk_assessment"
    questions: list


class CampaignCreate(BaseModel):
    title: str
    campaign_type: str = "risk_assessment"
    template_id: Optional[int] = None
    questions: Optional[list] = None
    scope_risk_ids: Optional[List[int]] = None
    scope_asset_ids: Optional[List[int]] = None
    deadline_days: int = 14
    intro_text: Optional[str] = None
    show_risk_context: bool = True
    allow_comments: bool = True
    reminder_days: int = 3


class AddRespondentIn(BaseModel):
    name: str
    email: EmailStr
    role: Optional[str] = None
    dept: Optional[str] = None


class AddRespondentsBulk(BaseModel):
    respondents: List[AddRespondentIn]


class AnswerSubmit(BaseModel):
    answers: list
    general_comment: Optional[str] = None


def _org(u): return u.organization_id


# ── Plantillas ────────────────────────────────────────────────────────────────

@router.get("/templates")
def list_templates(db=Depends(get_db), u=Depends(require_analyst)):
    templates = db.query(SurveyTemplate).filter_by(
        organization_id=_org(u)
    ).order_by(SurveyTemplate.is_default.desc(), SurveyTemplate.name).all()
    return [_tmpl_d(t) for t in templates]


@router.post("/templates", status_code=201)
def create_template(body: TemplateCreate, db=Depends(get_db), u=Depends(require_analyst)):
    t = SurveyTemplate(organization_id=_org(u), created_by_id=u.id,
                        **body.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return _tmpl_d(t)


@router.delete("/templates/{tid}", status_code=204)
def delete_template(tid: int, db=Depends(get_db), u=Depends(require_admin)):
    t = db.get(SurveyTemplate, tid)
    if not t or t.organization_id != _org(u):
        raise HTTPException(404)
    if t.is_default:
        raise HTTPException(422, "No se pueden eliminar plantillas predeterminadas")
    db.delete(t)
    db.commit()


# ── Campañas ──────────────────────────────────────────────────────────────────

@router.get("/campaigns")
def list_campaigns(status: Optional[str] = None, db=Depends(get_db),
                   u=Depends(require_analyst)):
    q = db.query(SurveyCampaign).filter_by(organization_id=_org(u))
    if status:
        q = q.filter_by(status=status)
    return [_campaign_d(c, db) for c in q.order_by(SurveyCampaign.created_at.desc()).all()]


@router.post("/campaigns", status_code=201)
def create_campaign(body: CampaignCreate, db=Depends(get_db), u=Depends(require_analyst)):
    questions = body.questions or []
    if body.template_id and not questions:
        tmpl = db.get(SurveyTemplate, body.template_id)
        if not tmpl or tmpl.organization_id != _org(u):
            raise HTTPException(422, "Plantilla no encontrada")
        questions = tmpl.questions
    if not questions:
        raise HTTPException(422, "La campaña debe tener preguntas")
    if body.scope_risk_ids:
        from app.models import Risk
        for rid in body.scope_risk_ids:
            r = db.get(Risk, rid)
            if not r or r.organization_id != _org(u):
                raise HTTPException(422, f"Riesgo {rid} no encontrado en esta organización")
    c = survey_service.create_campaign(
        db=db, org_id=_org(u), user_id=u.id,
        title=body.title, campaign_type=body.campaign_type,
        questions=questions, deadline_days=body.deadline_days,
        scope_risk_ids=body.scope_risk_ids,
        scope_asset_ids=body.scope_asset_ids,
        intro_text=body.intro_text,
        template_id=body.template_id,
        show_risk_context=body.show_risk_context,
        allow_comments=body.allow_comments,
    )
    log_action(db, u.id, "create", "survey_campaign", str(c.id), {"code": c.code})
    return _campaign_d(c, db)


@router.get("/campaigns/{cid}")
def get_campaign(cid: int, db=Depends(get_db), u=Depends(require_analyst)):
    c = _chk_campaign(db, cid, _org(u))
    return _campaign_d(c, db)


@router.delete("/campaigns/{cid}", status_code=204)
def delete_campaign(cid: int, db=Depends(get_db), u=Depends(require_admin)):
    c = _chk_campaign(db, cid, _org(u))
    if c.status == "active":
        raise HTTPException(422, "No se puede eliminar una campaña activa. Ciérrala primero.")
    db.delete(c)
    db.commit()


# ── Destinatarios ─────────────────────────────────────────────────────────────

@router.get("/campaigns/{cid}/respondents")
def list_respondents(cid: int, db=Depends(get_db), u=Depends(require_analyst)):
    _chk_campaign(db, cid, _org(u))
    resps = db.query(SurveyResponse).filter_by(campaign_id=cid).all()
    return [_resp_summary(r) for r in resps]


@router.post("/campaigns/{cid}/respondents", status_code=201)
def add_respondents(cid: int, body: AddRespondentsBulk,
                    db=Depends(get_db), u=Depends(require_analyst)):
    c = _chk_campaign(db, cid, _org(u))
    if c.status == "closed":
        raise HTTPException(422, "No se pueden añadir destinatarios a una campaña cerrada")
    added = []
    for r in body.respondents:
        resp = survey_service.add_respondent(db, c, r.name, r.email, r.role, r.dept)
        added.append(_resp_summary(resp))
    return {"added": len(added), "respondents": added}


@router.delete("/campaigns/{cid}/respondents/{rid}", status_code=204)
def remove_respondent(cid: int, rid: int,
                      db=Depends(get_db), u=Depends(require_analyst)):
    _chk_campaign(db, cid, _org(u))
    resp = db.get(SurveyResponse, rid)
    if not resp or resp.campaign_id != cid:
        raise HTTPException(404)
    if resp.status == "completed":
        raise HTTPException(422, "No se puede eliminar una respuesta ya completada")
    db.delete(resp)
    db.commit()


# ── Envío y acciones ──────────────────────────────────────────────────────────

@router.post("/campaigns/{cid}/send")
def send_invitations(cid: int, request: Request,
                     db=Depends(get_db), u=Depends(require_analyst)):
    c = _chk_campaign(db, cid, _org(u))
    if c.status == "closed":
        raise HTTPException(422, "Campaña cerrada")
    count = db.query(SurveyResponse).filter_by(campaign_id=cid).count()
    if count == 0:
        raise HTTPException(422, "Añade destinatarios antes de enviar")
    base_url = str(request.base_url).rstrip("/")
    result = survey_service.send_campaign_invitations(db, cid, base_url)
    log_action(db, u.id, "send", "survey_campaign", str(cid),
               {"sent": result.get("sent")})
    return result


@router.post("/campaigns/{cid}/close")
def close_campaign(cid: int, db=Depends(get_db), u=Depends(require_admin)):
    c = _chk_campaign(db, cid, _org(u))
    c.status = "closed"
    c.closed_at = datetime.now(timezone.utc)
    db.commit()
    log_action(db, u.id, "close", "survey_campaign", str(cid), {})

    # Auto-aplicar resultados a riesgos si hay riesgos en scope y respuestas completadas
    auto_result = {"applied": 0}
    if c.scope_risk_ids:
        try:
            auto_result = survey_service.apply_responses_to_risks(db, cid, u.id)
            if auto_result.get("applied", 0) > 0:
                log_action(db, u.id, "auto_apply_survey_results", "survey_campaign", str(cid),
                           {"auto": True, "changes": auto_result.get("changes", [])})
        except Exception:
            pass

    return {"status": "closed", "auto_applied": auto_result.get("applied", 0)}


@router.post("/campaigns/{cid}/apply-to-risks")
def apply_to_risks(cid: int, db=Depends(get_db), u=Depends(require_admin)):
    """Aplica los promedios de las respuestas al modelo de riesgos (acción deliberada del admin)."""
    _chk_campaign(db, cid, _org(u))
    result = survey_service.apply_responses_to_risks(db, cid, u.id)
    if result.get("applied", 0) > 0:
        log_action(db, u.id, "apply_survey_results", "survey_campaign", str(cid),
                   {"changes": result.get("changes", [])})
    return result


@router.get("/campaigns/{cid}/results")
def get_results(cid: int, db=Depends(get_db), u=Depends(require_analyst)):
    c = _chk_campaign(db, cid, _org(u))
    resps = db.query(SurveyResponse).filter_by(campaign_id=cid).all()
    completed = [r for r in resps if r.status == "completed"]
    question_stats = {}
    for resp in completed:
        for ans in (resp.answers or []):
            qid = ans.get("question_id") or ans.get("id")
            if qid not in question_stats:
                question_stats[qid] = {"values": [], "comments": []}
            v = ans.get("value")
            if v is not None:
                question_stats[qid]["values"].append(v)
            c_text = ans.get("comment")
            if c_text:
                question_stats[qid]["comments"].append(c_text)
    aggregated = []
    for q in (c.questions or []):
        qid = q.get("id")
        stats = question_stats.get(qid, {"values": [], "comments": []})
        values = stats["values"]
        agg = {
            "question_id": qid,
            "question_text": q.get("text"),
            "question_type": q.get("type"),
            "response_count": len(values),
        }
        if values and q.get("type") in ("likelihood_scale", "impact_scale",
                                         "rating_stars", "nps"):
            try:
                nums = [int(v) for v in values if v is not None]
                if nums:
                    agg["average"] = round(sum(nums) / len(nums), 1)
                    agg["min"] = min(nums)
                    agg["max"] = max(nums)
                    agg["distribution"] = {str(v): nums.count(v) for v in set(nums)}
            except (ValueError, TypeError):
                pass
        elif values:
            freq = {}
            for v in values:
                freq[str(v)] = freq.get(str(v), 0) + 1
            agg["distribution"] = freq
        agg["comments"] = stats["comments"][:10]
        aggregated.append(agg)
    return {
        "campaign_id": cid,
        "campaign_code": c.code,
        "title": c.title,
        "status": c.status,
        "total_respondents": len(resps),
        "completed": len(completed),
        "pending": sum(1 for r in resps if r.status == "pending"),
        "response_rate": round(len(completed) / len(resps) * 100) if resps else 0,
        "questions": aggregated,
        "general_comments": [r.general_comment for r in completed if r.general_comment],
    }


# ─────────────────────────── ENDPOINT PÚBLICO (sin auth) ─────────────────────

# NOTA: estos endpoints son accesibles sin autenticación JWT.
# La seguridad es por token único de un solo uso (SurveyResponse.token).

public_router = APIRouter(prefix="/survey", tags=["survey-public"])

_SURVEY_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self' 'unsafe-inline'; img-src data:;",
}


@public_router.get("/{token}", response_class=HTMLResponse)
async def survey_page(token: str, db: Session = Depends(get_db)):
    resp = survey_service.get_response_by_token(db, token)
    if not resp:
        return HTMLResponse(
            _error_page("El enlace ha expirado o no es válido."),
            status_code=410,
            headers=_SURVEY_SECURITY_HEADERS,
        )
    campaign = db.get(SurveyCampaign, resp.campaign_id)
    if not campaign or campaign.status not in ("active", "draft"):
        return HTMLResponse(
            _error_page("Esta encuesta ya no está disponible."),
            status_code=410,
            headers=_SURVEY_SECURITY_HEADERS,
        )
    if resp.status == "completed":
        return HTMLResponse(
            _thank_you_page(campaign, resp),
            status_code=200,
            headers=_SURVEY_SECURITY_HEADERS,
        )
    if not resp.opened_at:
        resp.opened_at = datetime.now(timezone.utc)
        resp.status = "in_progress"
        db.commit()
    risks_context = []
    if campaign.show_risk_context and campaign.scope_risk_ids:
        from app.models import Risk
        for rid in campaign.scope_risk_ids[:5]:
            r = db.get(Risk, rid)
            if r:
                risks_context.append({
                    "code": r.code, "name": r.name,
                    "description": (r.description or "")[:300],
                })
    return HTMLResponse(
        _build_survey_page(resp, campaign, risks_context),
        status_code=200,
        headers=_SURVEY_SECURITY_HEADERS,
    )


@public_router.post("/{token}/submit")
async def submit_survey(token: str, body: AnswerSubmit,
                        request: Request, db: Session = Depends(get_db)):
    content_length = request.headers.get("content-length", "0")
    try:
        if int(content_length) > 51200:
            raise HTTPException(413, "Respuesta demasiado grande")
    except ValueError:
        pass

    resp = survey_service.get_response_by_token(db, token)
    if not resp:
        raise HTTPException(410, "Token expirado o inválido")
    if resp.status == "completed":
        raise HTTPException(409, "Esta encuesta ya fue respondida")

    # Sanitizar respuestas de texto libre
    sanitized = []
    for ans in body.answers:
        ans_copy = dict(ans)
        if isinstance(ans_copy.get("value"), str):
            ans_copy["value"] = ans_copy["value"][:2000]
        if isinstance(ans_copy.get("comment"), str):
            ans_copy["comment"] = ans_copy["comment"][:500]
        sanitized.append(ans_copy)

    general = (body.general_comment or "")[:2000] or None

    survey_service.save_answers(
        db, resp, sanitized, general,
        ip=request.client.host if request.client else None,
        ua=request.headers.get("user-agent"),
    )
    return {"success": True, "message": "Respuesta registrada correctamente"}


# ─────────────────────────── HELPERS ─────────────────────────────────────────

def _chk_campaign(db, cid, org_id):
    c = db.get(SurveyCampaign, cid)
    if not c or c.organization_id != org_id:
        raise HTTPException(404, "Campaña no encontrada")
    return c


def _tmpl_d(t):
    return {
        "id": t.id, "name": t.name, "description": t.description,
        "survey_type": t.survey_type, "is_default": t.is_default,
        "questions_count": len(t.questions or []),
        "questions": t.questions,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _campaign_d(c, db):
    total = db.query(SurveyResponse).filter_by(campaign_id=c.id).count()
    completed = db.query(SurveyResponse).filter_by(campaign_id=c.id, status="completed").count()
    return {
        "id": c.id, "code": c.code, "title": c.title,
        "campaign_type": c.campaign_type, "status": c.status,
        "template_id": c.template_id,
        "scope_risk_ids": c.scope_risk_ids,
        "scope_asset_ids": c.scope_asset_ids,
        "questions_count": len(c.questions or []),
        "questions": c.questions,
        "deadline_at": c.deadline_at.isoformat() if c.deadline_at else None,
        "total_respondents": total,
        "completed_responses": completed,
        "response_rate": round(completed / total * 100) if total else 0,
        "show_risk_context": c.show_risk_context,
        "allow_comments": c.allow_comments,
        "intro_text": c.intro_text,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "closed_at": c.closed_at.isoformat() if c.closed_at else None,
    }


def _resp_summary(r):
    return {
        "id": r.id, "name": r.respondent_name, "email": r.respondent_email,
        "role": r.respondent_role, "dept": r.respondent_dept,
        "status": r.status,
        "opened_at": r.opened_at.isoformat() if r.opened_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "applied_to_risks": r.applied_to_risks,
    }


def _build_survey_page(resp, campaign, risks_context: list) -> str:
    questions_html = _build_questions_html(campaign.questions or [])
    questions_json = json.dumps(campaign.questions or [], ensure_ascii=False)
    thank_you_inline = json.dumps(_thank_you_page_inline(campaign), ensure_ascii=False)

    risks_html = ""
    if risks_context:
        risks_html = "<div class='risk-context'><h3>Riesgo(s) a evaluar</h3>"
        for r in risks_context:
            desc_html = f"<p>{r['description']}</p>" if r['description'] else ""
            risks_html += (
                f"<div class='risk-card'>"
                f"<span class='risk-code'>{r['code']}</span>"
                f"<strong>{r['name']}</strong>"
                f"{desc_html}"
                f"</div>"
            )
        risks_html += "</div>"

    intro_html = (
        f"<div class='card'><p style='font-size:14px;color:#3d3d5c'>{campaign.intro_text}</p></div>"
        if campaign.intro_text else ""
    )
    general_comment_html = (
        """<div class="question-block general-comment">
          <div class="question-label">¿Quieres añadir algún comentario general?</div>
          <textarea name="general_comment" rows="3" placeholder="Comentarios adicionales (opcional)..."></textarea>
        </div>"""
        if campaign.allow_comments else ""
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{campaign.title} — RiskHub</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background: #f5f5fa; color: #1a1a2e; min-height: 100vh; }}
    .header {{ background: linear-gradient(135deg, #5B00AD, #E05500);
               padding: 20px 24px; color: white; }}
    .header h1 {{ font-size: 18px; font-weight: 700; margin: 0; }}
    .header p {{ font-size: 13px; opacity: 0.85; margin-top: 4px; }}
    .container {{ max-width: 680px; margin: 0 auto; padding: 24px 16px 48px; }}
    .card {{ background: white; border-radius: 12px; padding: 24px;
             box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin-bottom: 16px; }}
    .risk-context {{ margin-bottom: 16px; }}
    .risk-context h3 {{ font-size: 12px; font-weight: 700; text-transform: uppercase;
                        letter-spacing: 0.06em; color: #8585a0; margin-bottom: 10px; }}
    .risk-card {{ background: white; border: 1px solid #e2e2ed; border-radius: 10px;
                  padding: 14px 16px; margin-bottom: 8px; }}
    .risk-card .risk-code {{ font-family: monospace; font-size: 11px; font-weight: 700;
                              background: #eee0ff; color: #5B00AD; padding: 2px 8px;
                              border-radius: 4px; display: inline-block; margin-bottom: 6px; }}
    .risk-card strong {{ font-size: 15px; display: block; }}
    .risk-card p {{ font-size: 13px; color: #5a5c78; margin-top: 6px; }}
    .question-block {{ margin-bottom: 24px; padding-bottom: 24px;
                        border-bottom: 1px solid #eeeef5; }}
    .question-block:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
    .question-label {{ font-size: 15px; font-weight: 600; margin-bottom: 6px; line-height: 1.4; }}
    .question-label .req {{ color: #dc2626; margin-left: 3px; }}
    .question-help {{ font-size: 12px; color: #8585a0; margin-bottom: 10px; }}
    .options {{ display: flex; flex-direction: column; gap: 8px; }}
    .option-btn {{ display: flex; align-items: center; gap: 10px; padding: 10px 14px;
                   border: 1.5px solid #e2e2ed; border-radius: 8px; cursor: pointer;
                   background: white; font-size: 14px; text-align: left;
                   transition: all 0.15s; }}
    .option-btn:hover {{ border-color: #9B4EFF; background: #f8f2ff; }}
    .option-btn.selected {{ border-color: #5B00AD; background: #f0e8ff; font-weight: 600; }}
    .option-btn input {{ accent-color: #5B00AD; flex-shrink: 0; }}
    .scale-row {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .scale-btn {{ flex: 1; min-width: 48px; padding: 10px 4px; border: 1.5px solid #e2e2ed;
                  border-radius: 8px; cursor: pointer; background: white; font-size: 13px;
                  font-weight: 600; text-align: center; transition: all 0.15s; }}
    .scale-btn:hover {{ border-color: #9B4EFF; background: #f8f2ff; }}
    .scale-btn.selected {{ border-color: #5B00AD; background: #5B00AD; color: white; }}
    textarea, input[type=text], input[type=date] {{
      width: 100%; padding: 10px 12px; border: 1.5px solid #e2e2ed;
      border-radius: 8px; font-size: 14px; font-family: inherit;
      resize: vertical; transition: border 0.15s; }}
    textarea:focus, input:focus {{ outline: none; border-color: #5B00AD;
                                    box-shadow: 0 0 0 3px rgba(91,0,173,0.1); }}
    .submit-section {{ margin-top: 24px; }}
    .btn-submit {{ width: 100%; padding: 14px; background: linear-gradient(135deg,#5B00AD,#E05500);
                   color: white; border: none; border-radius: 10px; font-size: 16px;
                   font-weight: 700; cursor: pointer; transition: opacity 0.15s; }}
    .btn-submit:hover {{ opacity: 0.9; }}
    .btn-submit:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    .progress-bar {{ height: 4px; background: #eeeef5; border-radius: 2px; margin-bottom: 20px; }}
    .progress-fill {{ height: 100%; background: linear-gradient(90deg,#5B00AD,#E05500);
                       border-radius: 2px; transition: width 0.3s; }}
    @media (max-width: 480px) {{
      .scale-row {{ gap: 4px; }}
      .scale-btn {{ min-width: 36px; font-size: 12px; }}
    }}
  </style>
</head>
<body>
  <div class="header">
    <h1>RiskHub — {campaign.title}</h1>
    <p>Hola {resp.respondent_name} — Tu valoración es confidencial y se usará para mejorar la gestión de riesgos.</p>
  </div>
  <div class="container">
    {intro_html}
    {risks_html}
    <div class="progress-bar"><div class="progress-fill" id="progress" style="width:0%"></div></div>
    <form id="survey-form" class="card">
      {questions_html}
      {general_comment_html}
      <div class="submit-section">
        <button type="submit" class="btn-submit" id="btn-submit">Enviar respuesta</button>
      </div>
    </form>
  </div>
  <script>
    const QUESTIONS = {questions_json};
    const TOKEN = "{resp.token}";
    const answers = {{}};
    function updateProgress() {{
      const required = QUESTIONS.filter(function(q) {{ return q.required; }});
      const answered = required.filter(function(q) {{ return answers[q.id] !== undefined && answers[q.id] !== ''; }});
      const pct = required.length ? (answered.length / required.length * 100) : 100;
      document.getElementById('progress').style.width = pct + '%';
    }}
    document.querySelectorAll('.option-btn[data-group]').forEach(function(btn) {{
      btn.addEventListener('click', function() {{
        const group = btn.dataset.group;
        document.querySelectorAll('[data-group="' + group + '"].option-btn').forEach(function(b) {{ b.classList.remove('selected'); }});
        btn.classList.add('selected');
        answers[group] = btn.dataset.value;
        updateProgress();
      }});
    }});
    document.querySelectorAll('.scale-btn').forEach(function(btn) {{
      btn.addEventListener('click', function() {{
        const group = btn.dataset.group;
        document.querySelectorAll('[data-group="' + group + '"].scale-btn').forEach(function(b) {{ b.classList.remove('selected'); }});
        btn.classList.add('selected');
        answers[group] = btn.dataset.value;
        updateProgress();
      }});
    }});
    document.querySelectorAll('textarea[data-qid], input[data-qid]').forEach(function(el) {{
      el.addEventListener('input', function() {{
        answers[el.dataset.qid] = el.value;
        updateProgress();
      }});
    }});
    document.getElementById('survey-form').addEventListener('submit', async function(e) {{
      e.preventDefault();
      const btn = document.getElementById('btn-submit');
      const required = QUESTIONS.filter(function(q) {{ return q.required; }});
      const missing = required.filter(function(q) {{
        const v = answers[q.id];
        return v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
      }});
      if (missing.length > 0) {{
        alert('Por favor responde todas las preguntas obligatorias (marcadas con *)');
        return;
      }}
      btn.disabled = true; btn.textContent = 'Enviando...';
      const payload = {{
        answers: Object.keys(answers).map(function(id) {{ return {{ question_id: id, value: answers[id] }}; }}),
        general_comment: (document.querySelector('[name=general_comment]') || {{}}).value || null
      }};
      try {{
        const r = await fetch('/survey/' + TOKEN + '/submit', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});
        if (r.ok) {{
          document.body.innerHTML = {thank_you_inline};
        }} else {{
          btn.disabled = false; btn.textContent = 'Enviar respuesta';
          alert('Error al enviar. Por favor, inténtalo de nuevo.');
        }}
      }} catch(err) {{
        btn.disabled = false; btn.textContent = 'Enviar respuesta';
        alert('Error de conexión. Comprueba tu conexión a internet.');
      }}
    }});
    updateProgress();
  </script>
</body>
</html>"""


def _build_questions_html(questions: list) -> str:
    html = ""
    for q in questions:
        qid = q.get("id", "")
        qtype = q.get("type", "text_short")
        text = q.get("text", "")
        required = q.get("required", False)
        help_text = q.get("help_text", "")
        options = q.get("options", [])
        req_mark = '<span class="req">*</span>' if required else ''
        help_html = f'<div class="question-help">{help_text}</div>' if help_text else ''

        if qtype in ("likelihood_scale", "impact_scale", "rating_stars"):
            scale_html = '<div class="scale-row">'
            for i, opt in enumerate(options, 1):
                scale_html += (
                    f'<button type="button" class="scale-btn" '
                    f'data-group="{qid}" data-value="{i}" title="{opt}">{i}</button>'
                )
            scale_html += '</div>'
            if options:
                scale_html += (
                    f'<div style="display:flex;justify-content:space-between;font-size:11px;'
                    f'color:#8585a0;margin-top:4px">'
                    f'<span>{options[0]}</span><span>{options[-1]}</span></div>'
                )
            input_html = scale_html

        elif qtype in ("yes_no_na", "multiple_choice", "control_effectiveness"):
            opts = options or (["Sí", "No", "No aplica"] if qtype == "yes_no_na" else [])
            input_html = '<div class="options">'
            for opt in opts:
                input_html += (
                    f'<button type="button" class="option-btn" '
                    f'data-group="{qid}" data-value="{opt}"><span>{opt}</span></button>'
                )
            input_html += '</div>'

        elif qtype == "multi_select":
            opts = options or []
            input_html = '<div class="options">'
            for opt in opts:
                safe_opt = opt.replace('"', '&quot;')
                input_html += (
                    f'<label class="option-btn" style="cursor:pointer">'
                    f'<input type="checkbox" data-qid="{qid}" value="{safe_opt}"'
                    f' onchange="'
                    f'var vals=[].slice.call(document.querySelectorAll(\'[data-qid={qid}]:checked\')).map(function(c){{return c.value;}});'
                    f'answers[\'{qid}\']=vals;'
                    f'this.closest(\'.option-btn\').classList.toggle(\'selected\',this.checked);'
                    f'updateProgress();"'
                    f'> {opt}</label>'
                )
            input_html += '</div>'

        elif qtype == "text_long":
            input_html = f'<textarea data-qid="{qid}" rows="3" placeholder="Escribe tu respuesta..."></textarea>'

        elif qtype == "date":
            input_html = f'<input type="date" data-qid="{qid}">'

        elif qtype == "file_upload":
            input_html = '<p style="font-size:13px;color:#8585a0;font-style:italic">Subida de archivos disponible en la versión completa de la plataforma.</p>'

        else:
            input_html = f'<input type="text" data-qid="{qid}" placeholder="Tu respuesta...">'

        html += (
            f'<div class="question-block" id="qblock-{qid}">'
            f'<div class="question-label">{text}{req_mark}</div>'
            f'{help_html}'
            f'{input_html}'
            f'</div>'
        )
    return html


def _thank_you_page(campaign, resp) -> str:
    msg = campaign.thank_you_text or "Tu respuesta ha sido registrada. Gracias por contribuir a la mejora continua de la seguridad."
    name = resp.respondent_name or "participante"
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Encuesta completada — RiskHub</title>
<style>body{{font-family:system-ui,sans-serif;background:#f5f5fa;display:flex;
align-items:center;justify-content:center;min-height:100vh;margin:0}}.card{{background:white;
border-radius:16px;padding:40px;text-align:center;max-width:440px;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
h2{{color:#1a1a2e;margin:0 0 12px}}p{{color:#5a5c78;font-size:15px;line-height:1.6}}</style></head>
<body><div class="card">
<div style="font-size:48px;margin-bottom:16px">&#10003;</div>
<h2>Gracias, {name}!</h2><p>{msg}</p>
<p style="font-size:12px;color:#8585a0;margin-top:16px">Puedes cerrar esta ventana.</p>
</div></body></html>"""


def _thank_you_page_inline(campaign) -> str:
    msg = campaign.thank_you_text or "Tu respuesta ha sido registrada correctamente."
    return (
        '<div style="font-family:system-ui,sans-serif;background:#f5f5fa;display:flex;'
        'align-items:center;justify-content:center;min-height:100vh">'
        '<div style="background:white;border-radius:16px;padding:40px;text-align:center;max-width:440px;'
        'box-shadow:0 4px 24px rgba(0,0,0,.08)">'
        '<div style="font-size:48px;margin-bottom:16px">&#10003;</div>'
        '<h2 style="color:#1a1a2e;margin:0 0 12px">Gracias!</h2>'
        f'<p style="color:#5a5c78;font-size:15px;line-height:1.6">{msg}</p>'
        '<p style="font-size:12px;color:#8585a0;margin-top:16px">Puedes cerrar esta ventana.</p>'
        '</div></div>'
    )


def _error_page(msg: str) -> str:
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<title>Enlace no válido — RiskHub</title>
<style>body{{font-family:system-ui,sans-serif;background:#f5f5fa;display:flex;
align-items:center;justify-content:center;min-height:100vh;margin:0}}.card{{background:white;
border-radius:16px;padding:40px;text-align:center;max-width:440px;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
</style></head><body><div class="card">
<div style="font-size:48px;margin-bottom:16px">&#9888;</div>
<h2 style="color:#1a1a2e">Enlace no válido</h2>
<p style="color:#5a5c78;font-size:15px">{msg}</p></div></body></html>"""
