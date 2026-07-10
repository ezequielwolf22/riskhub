"""Evaluaciones consolidadas de riesgo de proveedor — TPRM Sprint 4 / v3.9.0."""
import logging
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.i18n import get_lang, t as _t
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Asset, EmailSettings, Risk, RiskStatus, Supplier,
    SupplierQuestionnaire, Threat, User, VendorRiskAssessment,
)
from app.schemas import (
    VendorAssessmentCreate, VendorAssessmentDecide, VendorAssessmentOut, VendorAssessmentUpdate,
)
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action
from app.services import tprm_scoring_service
from app.services.vendor_assessment_service import build_assessment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vendor-assessments", tags=["vendor-assessments"])

# Plantillas del sistema para el flujo de dos fases
_PROFILING_CODE = "RH_TPRM_PROFILING_v1"
_ASSESSMENT_BY_LEVEL = {
    "critical": "RH_TPRM_ASSESSMENT_CRITICAL_v1",
    "high":     "RH_TPRM_ASSESSMENT_HIGH_v1",
    "medium":   "RH_TPRM_ASSESSMENT_MEDIUM_v1",
    "low":      "RH_TPRM_ASSESSMENT_MEDIUM_v1",
}

_DECISION_VALUES = frozenset({"approve", "approve_with_conditions", "reject", "request_more_info"})


def _next_code(db: Session, org_id: int) -> str:
    # Kept for backward compatibility; real code is assigned post-flush.
    return "VAS-0000"


def _next_q_code(db: Session) -> str:
    # Kept for backward compatibility; real code is assigned post-flush.
    return "SEQ-0000"


def _score_to_likelihood_consequence(residual_score: int) -> tuple[int, int]:
    if residual_score >= 75:
        return 4, 4
    if residual_score >= 50:
        return 4, 3
    if residual_score >= 25:
        return 3, 3
    return 2, 2


def _send_q_email(
    db: Session, q: SupplierQuestionnaire, supplier: Supplier,
    current_user: User, base_url: str,
    custom_subject: str = "", custom_message: str = "",
) -> dict:
    """Envia el enlace del cuestionario al contacto del proveedor. Devuelve {sent, warning}."""
    recipient = (supplier.contact_email or "").strip()
    if not recipient:
        return {"sent": False, "warning": "El proveedor no tiene email de contacto. Envia el enlace manualmente."}
    cfg = filter_by_org(db.query(EmailSettings), EmailSettings, current_user).first()
    if not cfg or not cfg.smtp_host:
        return {"sent": False, "warning": "SMTP no configurado en Alertas -> Configuracion. Envia el enlace manualmente."}

    link = f"{base_url.rstrip('/')}/supplier-q?token={q.token}"
    expires = q.expires_at.strftime("%d/%m/%Y") if q.expires_at else "-"
    org_name = current_user.organization.name if getattr(current_user, "organization", None) else "nuestra organizacion"

    phase_label = ""
    if q.phase == "profiling":
        phase_label = " — Fase 1: Perfil de Riesgo"
    elif q.phase == "assessment":
        phase_label = " — Fase 2: Evaluacion de Seguridad"

    subject = custom_subject.strip() if custom_subject and custom_subject.strip() \
        else f"Cuestionario de seguridad{phase_label} — {q.title}"

    # Cuerpo: si el usuario personalizó el texto, convertir saltos de linea a <br>.
    # Si no, usar el mensaje por defecto.
    if custom_message and custom_message.strip():
        import html as _html
        safe_msg = _html.escape(custom_message.strip()).replace("\n", "<br>")
        body_content = f"<p>{safe_msg}</p>"
    else:
        body_content = (
            f"<p>Estimado/a {supplier.contact_name or supplier.name}:</p>"
            f"<p>Como parte de nuestro proceso de evaluacion de proveedores ({org_name}), "
            f"le solicitamos completar el siguiente cuestionario de seguridad: "
            f"<strong>{q.title}</strong>{phase_label}.</p>"
        )

    body_html = f"""
    <div style="font-family:Inter,Arial,sans-serif;color:#1f2937;">
      {body_content}
      <p style="margin:24px 0;">
        <a href="{link}" style="background:#59008D;color:#fff;padding:12px 24px;
           border-radius:6px;text-decoration:none;font-weight:600;">Completar cuestionario</a>
      </p>
      <p style="font-size:13px;color:#6b7280;">O copie este enlace: <br>{link}</p>
      <p style="font-size:13px;color:#6b7280;">Fecha limite: {expires}. No necesita crear cuenta.</p>
    </div>"""

    from app.services import email_service
    try:
        email_service.send_email(cfg, recipient, subject, body_html)
        log_action(db, current_user.id, "send", "supplier_questionnaire", str(q.id), {"recipient": recipient})
        return {"sent": True, "recipient": recipient, "link": link}
    except Exception as exc:
        logger.warning("Email send failed for questionnaire %s: %s", q.id, exc)
        return {"sent": False, "warning": f"Email no enviado ({exc}). Enlace: {link}"}


def _create_questionnaire(
    db: Session, supplier: Supplier, template_code: str,
    title: str, current_user: User, assessment_id: int,
    phase: str, expires_days: int = 30,
) -> SupplierQuestionnaire:
    """Crea un SupplierQuestionnaire a partir de una plantilla del sistema."""
    from app.services import tprm_templates
    tpl = tprm_templates.get_template(template_code)
    if not tpl:
        raise HTTPException(404, f"Plantilla {template_code!r} no encontrada")
    q = SupplierQuestionnaire(
        code="SEQ-0000",
        supplier_id=supplier.id,
        title=title,
        token=secrets.token_urlsafe(32),
        template_code=template_code,
        questions=tpl["questions"],
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_days),
        created_by_id=current_user.id,
        organization_id=current_user.organization_id,
        phase=phase,
        parent_assessment_id=assessment_id,
    )
    db.add(q)
    db.flush()
    q.code = f"SEQ-{q.id:04d}"
    return q


# ---------- Endpoints ----------

@router.get("/", response_model=list[VendorAssessmentOut])
def list_assessments(
    supplier_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = filter_by_org(db.query(VendorRiskAssessment), VendorRiskAssessment, current_user)
    if supplier_id is not None:
        query = query.filter(VendorRiskAssessment.supplier_id == supplier_id)
    return query.order_by(VendorRiskAssessment.created_at.desc()).all()


@router.get("/{aid}", response_model=VendorAssessmentOut)
def get_assessment(
    aid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lang = get_lang(request)
    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, _t("tprm.assessment_not_found", lang))
    return a


@router.get("/{aid}/detail")
def get_assessment_detail(
    aid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna la evaluacion junto con los cuestionarios completos (preguntas, respuestas, evidencias, AI)."""
    lang = get_lang(request)
    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, _t("tprm.assessment_not_found", lang))

    def _q_summary(q: Optional[SupplierQuestionnaire]) -> Optional[dict]:
        if not q:
            return None
        return {
            "id": q.id,
            "code": q.code,
            "title": q.title,
            "phase": q.phase,
            "template_code": q.template_code,
            "score": q.score,
            "submitted_at": q.submitted_at.isoformat() if q.submitted_at else None,
            "expires_at": q.expires_at.isoformat() if q.expires_at else None,
            "major_nc": q.major_nc,
            "minor_nc": q.minor_nc,
            "residual_risk_level": q.residual_risk_level,
            "questions": q.questions or [],
            "answers": q.answers or {},
            "evidence": q.evidence or {},
            "ai_review": q.ai_review,
            "ai_reviewed_at": q.ai_reviewed_at.isoformat() if q.ai_reviewed_at else None,
            "token": q.token,
        }

    profiling_q = (
        db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == a.profiling_questionnaire_id).first()
        if a.profiling_questionnaire_id else None
    )
    assessment_q = (
        db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == a.assessment_questionnaire_id).first()
        if a.assessment_questionnaire_id else None
    )

    return {
        "id": a.id,
        "code": a.code,
        "supplier_id": a.supplier_id,
        "supplier_name": a.supplier_name,
        "assessment_type": a.assessment_type or "direct",
        "assessment_date": a.assessment_date.isoformat() if a.assessment_date else None,
        "period_label": a.period_label,
        "inherent_risk_score": a.inherent_risk_score,
        "inherent_risk_level": a.inherent_risk_level,
        "control_effectiveness_score": a.control_effectiveness_score,
        "residual_risk_score": a.residual_risk_score,
        "residual_risk_level": a.residual_risk_level,
        "score_by_domain": a.score_by_domain,
        "summary": a.summary,
        "recommendation": a.recommendation.value if a.recommendation else None,
        "decision_notes": a.decision_notes,
        "decision_at": a.decision_at.isoformat() if a.decision_at else None,
        "decision_by_id": a.decision_by_id,
        "profiling_questionnaire_id": a.profiling_questionnaire_id,
        "assessment_questionnaire_id": a.assessment_questionnaire_id,
        "approved_at": a.approved_at.isoformat() if a.approved_at else None,
        "linked_risk_id": a.linked_risk_id,
        "profiling_questionnaire": _q_summary(profiling_q),
        "assessment_questionnaire": _q_summary(assessment_q),
    }


@router.get("/{aid}/evidence/{question_id}")
def download_evidence(
    aid: int,
    question_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Descarga un fichero de evidencia de la evaluacion (autenticado)."""
    lang = get_lang(request)
    import re as _re
    question_id = _re.sub(r"[^a-zA-Z0-9_\-]", "", question_id)[:64]

    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, _t("tprm.assessment_not_found", lang))

    # Buscar en ambos cuestionarios
    q_ids = []
    if a.assessment_questionnaire_id:
        q_ids.append(a.assessment_questionnaire_id)
    if a.profiling_questionnaire_id:
        q_ids.append(a.profiling_questionnaire_id)
    if not q_ids:
        raise HTTPException(404, _t("tprm.questionnaire_not_found", lang))

    entry = None
    for qid in q_ids:
        q = db.query(SupplierQuestionnaire).filter(
            SupplierQuestionnaire.id == qid,
            SupplierQuestionnaire.organization_id == a.organization_id,
        ).first()
        if q and q.evidence and question_id in q.evidence:
            entry = q.evidence[question_id]
            break

    if not entry or not entry.get("stored_name"):
        raise HTTPException(404, _t("evidence.not_found", lang))

    stored = entry["stored_name"]
    # Prevenir path traversal
    if "/" in stored or "\\" in stored or ".." in stored:
        raise HTTPException(400, _t("common.bad_request", lang))

    evidence_dir = Path("/srv/data/evidence")
    if not evidence_dir.parent.exists():
        evidence_dir = Path(__file__).parent.parent.parent / "data" / "evidence"
    dest = evidence_dir / stored
    if not dest.exists():
        raise HTTPException(404, _t("evidence.not_found", lang))

    return FileResponse(
        path=str(dest),
        filename=entry.get("filename", stored),
        media_type="application/octet-stream",
    )


@router.post("/", status_code=201)
def create_assessment(
    body: VendorAssessmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    org_id = current_user.organization_id

    supplier = db.query(Supplier).filter(Supplier.id == body.supplier_id).first()
    if not supplier or not check_org_access(supplier.organization_id, current_user):
        raise HTTPException(404, _t("suppliers.not_found", lang))

    # Calcular scores base del proveedor (sin cuestionarios vinculados aun)
    scores = build_assessment(db, supplier, [])

    a = VendorRiskAssessment(
        organization_id=org_id,
        code="VAS-0000",
        supplier_id=body.supplier_id,
        period_label=body.period_label,
        valid_until=body.valid_until,
        assessor_user_id=current_user.id,
        created_by_id=current_user.id,
        assessment_type=body.assessment_type,
        inherent_risk_score=scores["inherent_risk_score"],
        inherent_risk_level=scores["inherent_risk_level"],
        control_effectiveness_score=scores["control_effectiveness_score"],
        residual_risk_score=scores["residual_risk_score"],
        residual_risk_level=scores["residual_risk_level"],
        score_by_domain=scores["score_by_domain"],
    )
    db.add(a)
    db.flush()  # obtener a.id
    a.code = f"VAS-{a.id:04d}"

    base_url = str(request.base_url)
    email_result = {"sent": False}

    if body.assessment_type == "risk_analysis":
        # Fase 1: crear cuestionario de profiling y enviarlo al proveedor
        profiling_q = _create_questionnaire(
            db, supplier, _PROFILING_CODE,
            title=f"Perfil de Riesgo — {supplier.name}",
            current_user=current_user,
            assessment_id=a.id,
            phase="profiling",
        )
        a.profiling_questionnaire_id = profiling_q.id
        db.flush()
        email_result = _send_q_email(db, profiling_q, supplier, current_user, base_url,
                                     custom_subject=body.email_subject or "",
                                     custom_message=body.email_message or "")
    else:
        # Tipo directo: enviar cuestionario de plantilla directamente
        template_code = body.template_code
        questions = None

        if body.custom_template_id:
            from app.models import TPRMTemplate
            tpl = db.query(TPRMTemplate).filter(TPRMTemplate.id == body.custom_template_id).first()
            if not tpl or not check_org_access(tpl.organization_id, current_user):
                raise HTTPException(404, _t("tprm.template_not_found", lang))
            questions = tpl.questions or []
            template_code = f"custom:{tpl.id}"
        elif template_code:
            from app.services import tprm_templates
            tpl_data = tprm_templates.get_template(template_code)
            if not tpl_data:
                raise HTTPException(404, _t("tprm.template_not_found", lang))
            questions = tpl_data["questions"]
        else:
            from app.routers.supplier_questionnaires import DEFAULT_QUESTIONS
            questions = DEFAULT_QUESTIONS
            template_code = None

        direct_q = SupplierQuestionnaire(
            code="SEQ-0000",
            supplier_id=supplier.id,
            title=f"Evaluacion de Seguridad — {supplier.name}",
            token=secrets.token_urlsafe(32),
            template_code=template_code,
            questions=questions,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            created_by_id=current_user.id,
            organization_id=org_id,
            phase="assessment",
            parent_assessment_id=a.id,
        )
        db.add(direct_q)
        db.flush()
        direct_q.code = f"SEQ-{direct_q.id:04d}"
        a.assessment_questionnaire_id = direct_q.id
        email_result = _send_q_email(db, direct_q, supplier, current_user, base_url,
                                     custom_subject=body.email_subject or "",
                                     custom_message=body.email_message or "")

    db.commit()
    db.refresh(a)

    log_action(db, current_user.id, "create", "vendor_assessment", str(a.id),
               {"code": a.code, "supplier_id": a.supplier_id, "type": body.assessment_type,
                "email_sent": email_result.get("sent", False)})

    if not email_result.get("sent") and email_result.get("warning"):
        logger.warning("Assessment %s created but email not sent: %s", a.code, email_result["warning"])

    # Devolver el assessment + resultado del email para que el frontend muestre el estado correcto
    from app.schemas import VendorAssessmentOut
    out = VendorAssessmentOut.model_validate(a).model_dump()
    out["email_sent"] = email_result.get("sent", False)
    out["email_warning"] = email_result.get("warning") or email_result.get("link") or None
    return out


@router.post("/{aid}/decide", response_model=VendorAssessmentOut)
def decide_assessment(
    aid: int,
    body: VendorAssessmentDecide,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Registra la decision del evaluador sobre el proveedor (aprobar/rechazar/etc.)."""
    lang = get_lang(request)
    if body.decision not in _DECISION_VALUES:
        raise HTTPException(400, _t("common.bad_request", lang))

    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, _t("tprm.assessment_not_found", lang))

    from app.models import AssessmentRecommendation
    a.recommendation = AssessmentRecommendation(body.decision)
    a.decision_notes = body.notes
    a.decision_at = datetime.now(timezone.utc)
    a.decision_by_id = current_user.id

    # Aprendizaje: patron de decisiones sobre proveedores por tier/score
    try:
        from app.models import Supplier
        from app.services.ai_learning_service import record_signal
        supplier = db.get(Supplier, a.supplier_id) if a.supplier_id else None
        tier = None
        if supplier is not None and getattr(supplier, "tier", None) is not None:
            tier = supplier.tier.value if hasattr(supplier.tier, "value") else str(supplier.tier)
        record_signal(
            db, a.organization_id, "vendor_assessment_decision",
            {
                "decision": body.decision,
                "tier": tier,
                "residual_risk_score": a.residual_risk_score,
                "control_effectiveness": a.control_effectiveness,
            },
            entity_ref=a.code, user_id=current_user.id,
        )
    except Exception:
        pass

    db.commit()
    db.refresh(a)
    log_action(db, current_user.id, "decide", "vendor_assessment", str(a.id),
               {"code": a.code, "decision": body.decision})
    return a


# Campos administrativos que no alteran el contenido sustantivo de la evaluacion
# y por tanto pueden editarse aunque ya este aprobada, sin forzar nueva version.
_ASSESSMENT_SAFE_FIELDS_WHEN_APPROVED = {"valid_until", "linked_risk_id"}


@router.patch("/{aid}", response_model=VendorAssessmentOut)
def update_assessment(
    aid: int,
    body: VendorAssessmentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, _t("tprm.assessment_not_found", lang))

    changes = body.model_dump(exclude_none=True)
    # Una evaluacion aprobada es la base documental para decisiones TPRM (§5.2):
    # su contenido no debe poder mutarse por PATCH directo una vez aprobada.
    if a.approved_at:
        disallowed = set(changes.keys()) - _ASSESSMENT_SAFE_FIELDS_WHEN_APPROVED
        if disallowed:
            raise HTTPException(
                422,
                _t("common.bad_request", lang),
            )
    for field, value in changes.items():
        setattr(a, field, value)

    if "control_effectiveness_score" in changes and a.inherent_risk_score is not None:
        a.residual_risk_score = tprm_scoring_service.compute_residual_risk(
            a.inherent_risk_score, a.control_effectiveness_score
        )
        a.residual_risk_level = tprm_scoring_service.risk_level_label(a.residual_risk_score)

    db.commit()
    db.refresh(a)
    log_action(db, current_user.id, "update", "vendor_assessment", str(a.id))
    return a


@router.post("/{aid}/new-version", response_model=VendorAssessmentOut)
def new_assessment_version(
    aid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Crea una nueva re-evaluacion en borrador a partir de una evaluacion aprobada,
    copiando sus puntuaciones. La evaluacion original permanece vigente hasta que
    la nueva se apruebe (ver approve_assessment)."""
    lang = get_lang(request)
    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, _t("tprm.assessment_not_found", lang))
    if not a.approved_at:
        raise HTTPException(422, _t("common.bad_request", lang))

    new_a = VendorRiskAssessment(
        organization_id=a.organization_id,
        code="VAS-0000",
        supplier_id=a.supplier_id,
        inherent_risk_score=a.inherent_risk_score,
        inherent_risk_level=a.inherent_risk_level,
        control_effectiveness_score=a.control_effectiveness_score,
        residual_risk_score=a.residual_risk_score,
        residual_risk_level=a.residual_risk_level,
        score_by_domain=a.score_by_domain,
        summary=a.summary,
        assessor_user_id=current_user.id,
        created_by_id=current_user.id,
        assessment_type=a.assessment_type,
        questionnaire_ids=a.questionnaire_ids,
        previous_version_id=a.id,
    )
    db.add(new_a)
    db.flush()
    new_a.code = f"VAS-{new_a.id:04d}"
    db.commit()
    db.refresh(new_a)
    log_action(db, current_user.id, "new_version", "vendor_assessment", str(new_a.id),
               {"previous_id": a.id, "previous_code": a.code})
    return new_a


@router.delete("/{aid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assessment(
    aid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, _t("tprm.assessment_not_found", lang))
    log_action(db, current_user.id, "delete", "vendor_assessment", str(aid), {"code": a.code})
    db.delete(a)
    db.commit()


@router.post("/{aid}/approve", response_model=VendorAssessmentOut)
def approve_assessment(
    aid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, _t("tprm.assessment_not_found", lang))
    a.approver_user_id = current_user.id
    a.approved_at = datetime.now(timezone.utc)
    a.is_current = True
    # Versionado: al aprobar una re-evaluacion, la version anterior deja de estar vigente
    if a.previous_version_id:
        prev = db.get(VendorRiskAssessment, a.previous_version_id)
        if prev and prev.is_current:
            prev.is_current = False
    db.commit()
    db.refresh(a)
    log_action(db, current_user.id, "approve", "vendor_assessment", str(a.id), {"code": a.code})
    return a


@router.post("/{aid}/push-to-risk-register")
def push_to_risk_register(
    aid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Crea un riesgo ISO 27005 en el registro a partir de la evaluacion consolidada."""
    lang = get_lang(request)
    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, _t("tprm.assessment_not_found", lang))

    if a.linked_risk_id:
        existing_risk = db.query(Risk).filter(Risk.id == a.linked_risk_id).first()
        if existing_risk:
            # Retrocompatibilidad: si el riesgo existe pero sin supplier_id, actualizarlo
            if existing_risk.supplier_id is None and a.supplier_id:
                existing_risk.supplier_id = a.supplier_id
                db.commit()
            return {"risk_id": existing_risk.id, "risk_code": existing_risk.code}

    org_id = a.organization_id

    asset = (
        db.query(Asset)
        .filter(Asset.organization_id == org_id)
        .order_by(Asset.value_confidentiality.desc(), Asset.id)
        .first()
    )
    if not asset:
        raise HTTPException(409, _t("common.conflict", lang))

    threat = (
        db.query(Threat)
        .filter(
            Threat.name.ilike("%supply%")
            | Threat.name.ilike("%suministro%")
            | Threat.name.ilike("%proveedor%")
            | Threat.name.ilike("%third party%")
            | Threat.category.ilike("%supply%")
        )
        .first()
    )
    if not threat:
        threat = db.query(Threat).filter(Threat.category.ilike("%organiz%")).first()
    if not threat:
        raise HTTPException(409, _t("common.conflict", lang))

    existing = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.asset_id == asset.id,
        Risk.threat_id == threat.id,
        Risk.supplier_id == a.supplier_id,
    ).first()
    if existing:
        a.linked_risk_id = existing.id
        db.commit()
        return {"risk_id": existing.id, "risk_code": existing.code}

    residual_score = a.residual_risk_score or 0
    likelihood, consequence = _score_to_likelihood_consequence(residual_score)
    from app.services.risk_engine import calc_level as _calc_level
    inherent_level = _calc_level(consequence, likelihood)

    from app.routers.risks import _next_code as _risk_next_code
    code = _risk_next_code(db, org_id)

    supplier_name = a.supplier_name or f"Proveedor #{a.supplier_id}"
    risk = Risk(
        organization_id=org_id,
        code=code,
        asset_id=asset.id,
        threat_id=threat.id,
        supplier_id=a.supplier_id,
        description=(
            f"Riesgo de cadena de suministro generado desde evaluacion consolidada.\n"
            f"Proveedor: {supplier_name} — Evaluacion: {a.code}.\n"
            f"Riesgo inherente: {a.inherent_risk_score}/100 ({a.inherent_risk_level}). "
            f"Riesgo residual: {a.residual_risk_score}/100 ({a.residual_risk_level})."
        ),
        inherent_likelihood=likelihood,
        inherent_consequence=consequence,
        inherent_level=inherent_level,
        residual_likelihood=likelihood,
        residual_consequence=consequence,
        residual_level=inherent_level,
        status=RiskStatus.IDENTIFIED,
        owner_id=current_user.id,
        ai_generated=False,
    )
    db.add(risk)
    db.flush()

    a.linked_risk_id = risk.id
    db.commit()
    logger.info("Push-to-register: riesgo %s creado desde evaluacion %s", code, a.code)
    return {"risk_id": risk.id, "risk_code": risk.code}
