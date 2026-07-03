"""Cuestionarios de evaluacion de seguridad de proveedores — NIS2 Art. 21.2.d."""
import logging
import re
import secrets
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("riskhub.questionnaires")

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.i18n import get_lang, t as _t
from app.models import AiConfig, EmailSettings, Supplier, SupplierQuestionnaire, User
from app.routers.ai_config import resolve_api_key
from app.schemas import SupplierQuestionnaireCreate, SupplierQuestionnaireOut
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action
from app.services import tprm_ai_service

router = APIRouter(prefix="/api/supplier-questionnaires", tags=["supplier-questionnaires"])

# Preguntas estandar de evaluacion de seguridad (NIS2 Art. 21 + ISO 27001)
DEFAULT_QUESTIONS = [
    {"id": "q1",  "text": "La organizacion tiene un SGSI certificado o equivalente (ISO 27001, SOC 2, etc.)?"},
    {"id": "q2",  "text": "Existen procedimientos documentados de respuesta a incidentes de seguridad?"},
    {"id": "q3",  "text": "Se realizan formaciones periodicas de concienciacion en seguridad para los empleados?"},
    {"id": "q4",  "text": "Los datos sensibles se cifran tanto en transito como en reposo?"},
    {"id": "q5",  "text": "Se utiliza autenticacion multifactor (MFA) para el acceso a sistemas criticos?"},
    {"id": "q6",  "text": "Existe un plan de continuidad de negocio (BCP) documentado y probado?"},
    {"id": "q7",  "text": "Se realizan evaluaciones de vulnerabilidades o pruebas de penetracion regularmente?"},
    {"id": "q8",  "text": "Existen politicas documentadas de control de acceso (principio de minimo privilegio)?"},
    {"id": "q9",  "text": "La organizacion tiene procedimientos de notificacion de brechas de datos (GDPR/NIS2)?"},
    {"id": "q10", "text": "Existe una politica de seguridad de la cadena de suministro para los propios proveedores?"},
]


def _next_code(db: Session) -> str:
    from sqlalchemy import func as _func
    max_id = db.query(_func.max(SupplierQuestionnaire.id)).scalar() or 0
    return f"SEQ-{max_id + 1:04d}"


def _calculate_score(answers: dict) -> int:
    """Calcula puntuacion 0-100 basado en respuestas Si/No."""
    if not answers:
        return 0
    yes_count = sum(1 for v in answers.values() if str(v).lower() in ('true', '1', 'yes', 'si', 'sí'))
    total = len(answers)
    return round(yes_count / total * 100) if total else 0


def _compute_residual_risk(inherent_level: str, major_nc: int, minor_nc: int) -> str:
    """Matriz de riesgo residual segun §7.2 del spec RISKHUB_TPRM_QUESTIONNAIRES."""
    lvl = (inherent_level or "medium").lower()
    if lvl == "critical":
        if major_nc >= 3 or minor_nc >= 6:
            return "critical"
        if major_nc >= 1 or minor_nc >= 2:
            return "high"
        if minor_nc >= 1:
            return "medium"
        return "low"
    if lvl == "high":
        if major_nc >= 1 or minor_nc >= 3:
            return "high"
        if minor_nc >= 1:
            return "medium"
        return "low"
    # medium or lower
    if major_nc >= 1 or minor_nc >= 3:
        return "medium"
    return "low"


@router.get("/", response_model=list[SupplierQuestionnaireOut])
def list_questionnaires(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    supplier_id: Optional[int] = None,
    regwatch_pending: bool = False,
):
    q = filter_by_org(db.query(SupplierQuestionnaire), SupplierQuestionnaire, current_user)
    if supplier_id:
        q = q.filter(SupplierQuestionnaire.supplier_id == supplier_id)
    if regwatch_pending:
        q = q.filter(SupplierQuestionnaire.regwatch_review_at.isnot(None))
    return q.order_by(SupplierQuestionnaire.created_at.desc()).all()


@router.get("/my-tasks", response_model=list[SupplierQuestionnaireOut])
def my_assigned_tasks_early(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista los cuestionarios asignados al usuario autenticado que estan pendientes."""
    return (
        db.query(SupplierQuestionnaire)
        .filter(
            SupplierQuestionnaire.assigned_user_id == current_user.id,
            SupplierQuestionnaire.assignment_type == "internal",
            SupplierQuestionnaire.submitted_at.is_(None),
        )
        .order_by(SupplierQuestionnaire.assigned_at.desc())
        .all()
    )


@router.get("/{qid}", response_model=SupplierQuestionnaireOut)
def get_questionnaire(qid: int, request: Request, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    lang = get_lang(request)
    q = filter_by_org(
        db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == qid),
        SupplierQuestionnaire, current_user
    ).first()
    if not q:
        raise HTTPException(404, _t("supplier_questionnaires.not_found", lang))
    return q


@router.post("/", response_model=SupplierQuestionnaireOut)
def create_questionnaire(body: SupplierQuestionnaireCreate, request: Request,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    supplier = db.query(Supplier).filter(Supplier.id == body.supplier_id).first()
    if not supplier or not check_org_access(supplier.organization_id, current_user):
        raise HTTPException(404, _t("supplier_questionnaires.supplier_not_found", lang))
    expires = body.expires_at or (datetime.now(timezone.utc) + timedelta(days=30))
    # TPRM: prioridad de origen de las preguntas:
    #  1) preguntas ad-hoc (override editado)  2) plantilla personalizada
    #  3) plantilla del sistema  4) set estandar NIS2/ISO 27001.
    questions = DEFAULT_QUESTIONS
    template_code = None
    if body.questions:
        questions = body.questions
        template_code = body.template_code
    elif body.custom_template_id:
        from app.models import TPRMTemplate
        tpl = db.query(TPRMTemplate).filter(TPRMTemplate.id == body.custom_template_id).first()
        if not tpl or not check_org_access(tpl.organization_id, current_user):
            raise HTTPException(404, _t("supplier_questionnaires.template_not_found", lang))
        questions = tpl.questions or []
        template_code = f"custom:{tpl.id}"
    elif body.template_code:
        from app.services import tprm_templates
        tpl = tprm_templates.get_template(body.template_code)
        if not tpl:
            raise HTTPException(404, _t("supplier_questionnaires.template_not_found", lang))
        questions = tpl["questions"]
        template_code = tpl["code"]
    now = datetime.now(timezone.utc)
    assignment_type = body.assignment_type or "external"
    q = SupplierQuestionnaire(
        code=_next_code(db),
        supplier_id=body.supplier_id,
        title=body.title,
        token=secrets.token_urlsafe(32),
        template_code=template_code,
        questions=questions,
        expires_at=expires,
        notes=body.notes,
        notify_email=body.notify_email or None,
        assigned_user_id=body.assigned_user_id or None,
        assignment_type=assignment_type,
        assigned_at=now if body.assigned_user_id else None,
        created_by_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    log_action(db, current_user.id, "create", "supplier_questionnaire", str(q.id),
               {"supplier": supplier.name})
    return q


@router.delete("/{qid}", status_code=204)
def delete_questionnaire(qid: int, request: Request, db: Session = Depends(get_db),
                         current_user: User = Depends(require_analyst)):
    q = filter_by_org(
        db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == qid),
        SupplierQuestionnaire, current_user
    ).first()
    if not q:
        raise HTTPException(404, _t("supplier_questionnaires.not_found", get_lang(request)))
    db.delete(q)
    db.commit()


@router.post("/{qid}/ai-review")
def ai_review_questionnaire(
    qid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Evalua un cuestionario respondido con IA y almacena el resultado."""
    lang = get_lang(request)
    q = filter_by_org(
        db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == qid),
        SupplierQuestionnaire, current_user,
    ).first()
    if not q:
        raise HTTPException(404, _t("supplier_questionnaires.not_found", lang))
    if not q.submitted_at:
        raise HTTPException(400, _t("supplier_questionnaires.not_answered_yet", lang))

    cfg = (
        db.query(AiConfig)
        .filter(AiConfig.organization_id == current_user.organization_id)
        .first()
    )
    key = resolve_api_key(cfg)
    if not key:
        raise HTTPException(
            400,
            _t("supplier_questionnaires.api_key_missing", lang),
        )
    model = (cfg.model if cfg else None) or "claude-opus-4-6"

    result = tprm_ai_service.review_questionnaire(db, q, key, model, lang=lang)

    q.ai_review = result
    q.ai_reviewed_at = datetime.now(timezone.utc)
    db.commit()

    log_action(db, current_user.id, "ai_review", "supplier_questionnaire", str(q.id))

    return result


@router.post("/{qid}/send")
def send_questionnaire(qid: int, request: Request, db: Session = Depends(get_db),
                       current_user: User = Depends(require_analyst)):
    """Envia el cuestionario por email al contacto del proveedor con el enlace tokenizado."""
    lang = get_lang(request)
    q = filter_by_org(
        db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == qid),
        SupplierQuestionnaire, current_user,
    ).first()
    if not q:
        raise HTTPException(404, _t("supplier_questionnaires.not_found", lang))
    if q.submitted_at:
        raise HTTPException(409, _t("supplier_questionnaires.already_answered", lang))
    supplier = q.supplier
    recipient = (supplier.contact_email or "").strip() if supplier else ""
    if not recipient:
        raise HTTPException(400, _t("supplier_questionnaires.no_contact_email", lang))

    cfg = filter_by_org(db.query(EmailSettings), EmailSettings, current_user).first()
    if not cfg or not cfg.smtp_host:
        raise HTTPException(400, _t("supplier_questionnaires.smtp_missing", lang))

    base = str(request.base_url).rstrip("/")
    link = f"{base}/supplier-q?token={q.token}"
    expires = q.expires_at.strftime("%d/%m/%Y") if q.expires_at else "-"
    org_name = current_user.organization.name if getattr(current_user, "organization", None) else _t("supplier_questionnaires.our_org_fallback", lang)
    subject = _t("supplier_questionnaires.email_subject", lang, title=q.title)
    body_html = f"""
    <div style="font-family:Inter,Arial,sans-serif;color:#1f2937;">
      <p>{_t("supplier_questionnaires.email_greeting", lang, name=supplier.contact_name or supplier.name)}</p>
      <p>{_t("supplier_questionnaires.email_intro", lang, org=org_name, title=q.title)}</p>
      <p style="margin:24px 0;">
        <a href="{link}" style="background:#59008D;color:#fff;padding:12px 24px;
           border-radius:6px;text-decoration:none;font-weight:600;">{_t("supplier_questionnaires.email_button", lang)}</a>
      </p>
      <p style="font-size:13px;color:#6b7280;">{_t("supplier_questionnaires.email_copy_link", lang)} <br>{link}</p>
      <p style="font-size:13px;color:#6b7280;">{_t("supplier_questionnaires.email_deadline", lang, expires=expires)}</p>
    </div>
    """
    # CC: cc_email del proveedor y notify_email del cuestionario
    cc_addresses = []
    if getattr(supplier, "cc_email", None):
        cc_addresses.append(supplier.cc_email.strip())
    if getattr(q, "notify_email", None) and q.notify_email.strip() not in cc_addresses + [recipient]:
        cc_addresses.append(q.notify_email.strip())
    from app.services import email_service
    try:
        email_service.send_email(cfg, recipient, subject, body_html, cc=cc_addresses or None)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, _t("supplier_questionnaires.email_send_failed", lang, error=exc))

    log_action(db, current_user.id, "send", "supplier_questionnaire", str(q.id),
               {"recipient": recipient, "cc": cc_addresses})
    return {"sent": True, "recipient": recipient, "cc": cc_addresses, "link": link}


# ---- Flujo dos fases: profiling → assessment ----

def _create_followup_assessment(db, profiling_q, profiling_score: int, lang: str = "es"):
    """Crea el cuestionario de evaluacion de seguridad correspondiente al nivel de riesgo del proveedor.

    Selecciona la plantilla segun el score del profiling:
      - score < 40  → CRITICAL  (riesgo inherente alto, evaluacion exhaustiva)
      - score 40-65 → HIGH
      - score >= 66 → MEDIUM

    Devuelve (next_token, next_title) o lanza excepcion si falla.
    """
    from app.services import tprm_templates
    from app.models import VendorRiskAssessment

    _ASSESSMENT_BY_SCORE = {
        "critical": "RH_TPRM_ASSESSMENT_CRITICAL_v1",
        "high":     "RH_TPRM_ASSESSMENT_HIGH_v1",
        "medium":   "RH_TPRM_ASSESSMENT_MEDIUM_v1",
    }
    if profiling_score < 40:
        level = "critical"
    elif profiling_score < 66:
        level = "high"
    else:
        level = "medium"

    template_code = _ASSESSMENT_BY_SCORE[level]
    tpl = tprm_templates.get_template(template_code)
    if not tpl:
        raise ValueError(f"Plantilla {template_code!r} no disponible")

    supplier = profiling_q.supplier
    level_label = _t(f"supplier_questionnaires.level_{level}", lang)
    title = _t("supplier_questionnaires.followup_title", lang, name=supplier.name, level=level_label)

    assessment_q = SupplierQuestionnaire(
        code=_next_code(db),
        supplier_id=profiling_q.supplier_id,
        title=title,
        token=secrets.token_urlsafe(32),
        template_code=template_code,
        questions=tpl["questions"],
        expires_at=profiling_q.expires_at,  # misma fecha limite
        created_by_id=profiling_q.created_by_id,
        organization_id=profiling_q.organization_id,
        phase="assessment",
        parent_assessment_id=profiling_q.parent_assessment_id,
    )
    db.add(assessment_q)
    db.flush()

    # Vincular en el cuestionario de profiling
    profiling_q.next_questionnaire_id = assessment_q.id

    # Actualizar VendorRiskAssessment con el id del cuestionario de evaluacion
    if profiling_q.parent_assessment_id:
        vas = db.query(VendorRiskAssessment).filter(
            VendorRiskAssessment.id == profiling_q.parent_assessment_id,
            VendorRiskAssessment.organization_id == profiling_q.organization_id,
        ).first()
        if vas:
            vas.assessment_questionnaire_id = assessment_q.id
            # Actualizar nivel inherente con lo que revela el profiling
            vas.inherent_risk_level = level

    db.commit()
    logger.info("Follow-up assessment Q%s created (level=%s) for profiling Q%s",
                assessment_q.id, level, profiling_q.id)
    return assessment_q.token, title


# ---- Recoleccion de evidencia (portal del proveedor) ----

_EVIDENCE_EXT = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".txt", ".csv")
_EVIDENCE_MAX_BYTES = 15 * 1024 * 1024  # 15 MB


def _evidence_dir() -> Path:
    root = Path("/srv/data/evidence")
    if not root.parent.exists():
        root = Path(__file__).parent.parent.parent / "data" / "evidence"
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.post("/public/{token}/upload")
async def upload_public_evidence(
    token: str,
    request: Request,
    question_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """El proveedor sube un fichero de evidencia para una pregunta (sin auth, por token)."""
    lang = get_lang(request)
    q = db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.token == token).first()
    if not q:
        raise HTTPException(404, _t("supplier_questionnaires.link_invalid", lang))
    now = datetime.now(timezone.utc)
    if q.expires_at and q.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(410, _t("supplier_questionnaires.link_expired", lang))
    if q.submitted_at:
        raise HTTPException(409, _t("supplier_questionnaires.already_answered", lang))

    # OWASP A01 — sanitizar question_id para evitar path traversal en el nombre del fichero
    question_id = re.sub(r"[^a-zA-Z0-9_\-]", "", question_id)[:64]
    if not question_id:
        raise HTTPException(400, _t("supplier_questionnaires.invalid_question_id", lang))

    fname = (file.filename or "").lower()
    ext = "." + fname.rsplit(".", 1)[-1] if "." in fname else ""
    if ext not in _EVIDENCE_EXT:
        raise HTTPException(400, _t("supplier_questionnaires.evidence_type_not_allowed", lang))
    content = await file.read()
    if not content:
        raise HTTPException(400, _t("supplier_questionnaires.file_empty", lang))
    if len(content) > _EVIDENCE_MAX_BYTES:
        raise HTTPException(413, _t("supplier_questionnaires.file_too_large", lang))

    # OWASP A08 — validar contenido real (magic bytes) reutilizando el validador de documentos
    try:
        from app.routers.documents import _infer_mime, _validate_magic
        mime = _infer_mime(file.filename or "", file.content_type or "")
        if not _validate_magic(mime, content):
            raise HTTPException(400, _t("supplier_questionnaires.file_content_mismatch", lang))
    except HTTPException:
        raise
    except Exception as _magic_exc:
        logger.warning("Magic bytes validation unavailable for evidence upload: %s", _magic_exc)

    import hashlib
    # No incluir el token en el nombre del fichero (evita info leakage en logs/directorios)
    stored_name = f"ev_{q.id}_{question_id}_{secrets.token_hex(8)}{ext}"
    dest = _evidence_dir() / stored_name
    dest.write_bytes(content)

    evidence = dict(q.evidence or {})
    evidence[question_id] = {
        "filename": file.filename,
        "stored_name": stored_name,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "uploaded_at": now.isoformat(),
    }
    q.evidence = evidence
    db.commit()
    return {"ok": True, "question_id": question_id, "filename": file.filename}


# ---- Endpoints publicos (sin autenticacion) ----

@router.get("/public/{token}")
def get_public_questionnaire(token: str, request: Request, db: Session = Depends(get_db)):
    """Endpoint publico: el proveedor obtiene las preguntas del cuestionario."""
    lang = get_lang(request)
    q = db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.token == token).first()
    if not q:
        raise HTTPException(404, _t("supplier_questionnaires.link_invalid", lang))
    now = datetime.now(timezone.utc)
    if q.expires_at and q.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(410, _t("supplier_questionnaires.link_expired", lang))
    if q.submitted_at:
        raise HTTPException(409, _t("supplier_questionnaires.already_answered", lang))
    supplier = q.supplier
    # Sanitizar: nunca exponer al proveedor las reglas de scoring, criticity ni
    # mapeo a controles internos. Si/no/partial es todo lo que ve.
    _public_fields = ("id", "text", "type", "options", "help_text", "requires_evidence", "domain")
    public_questions = [
        {k: qq.get(k) for k in _public_fields if k in qq}
        for qq in (q.questions or [])
    ]
    return {
        "code": q.code,
        "title": q.title,
        "supplier_name": supplier.name if supplier else "",
        "questions": public_questions,
        "expires_at": q.expires_at.isoformat() if q.expires_at else None,
        "phase": q.phase,
    }


@router.post("/public/{token}/submit")
def submit_public_questionnaire(token: str, body: dict, request: Request,
                                db: Session = Depends(get_db)):
    """Endpoint publico: el proveedor envia sus respuestas."""
    lang = get_lang(request)
    q = db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.token == token).first()
    if not q:
        raise HTTPException(404, _t("supplier_questionnaires.link_invalid", lang))
    now = datetime.now(timezone.utc)
    if q.expires_at and q.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(410, _t("supplier_questionnaires.link_expired", lang))
    if q.submitted_at:
        raise HTTPException(409, _t("supplier_questionnaires.already_answered", lang))
    answers = body.get("answers", {})
    # TPRM: incorporar al scoring la evidencia ya subida al portal (evita la
    # penalizacion por falta de evidencia en preguntas que la requieren).
    scoring_answers = dict(answers)
    for qid in (q.evidence or {}):
        scoring_answers[f"{qid}__evidence"] = True
    # Las plantillas (sistema/personalizadas) traen pesos y reglas de scoring; si la
    # pregunta los incluye, usar el scoring ponderado. Si no, scoring Si/No.
    if q.template_code or any((qq.get("scoring_rules") or qq.get("weight")) for qq in (q.questions or [])):
        from app.services.tprm_scoring_service import score_questionnaire
        result = score_questionnaire(q.questions or [], scoring_answers)
        score = result["score"]
    else:
        score = _calculate_score(answers)

    # Conteo de no-conformidades (Major/Minor) segun criticity de cada pregunta (spec §7.1)
    # Solo se cuentan las preguntas efectivamente respondidas; las omitidas no penalizan aqui
    # (el score ponderado ya refleja el gap). Respuestas "na" no cuentan como NC.
    major_nc = 0
    minor_nc = 0
    nc_val_set = {"false", "0", "no"}
    for qq in (q.questions or []):
        criticity = qq.get("criticity")
        if not criticity:
            continue
        qid = qq.get("id", "")
        answer = answers.get(qid)
        if answer is None:
            continue  # pregunta sin responder: no penalizar como NC
        answer_str = str(answer).lower()
        if answer_str == "na":
            continue  # N/A explicitamente excluido
        custom_nc_val = str(qq.get("nonconformity_value", "no")).lower()
        if answer_str in nc_val_set or answer_str == custom_nc_val:
            if criticity == "Major":
                major_nc += 1
            elif criticity == "Minor":
                minor_nc += 1

    # Residual risk via matriz del spec §7.2
    # Usamos el nivel inherente del proveedor (no el residual) como base de la matriz.
    try:
        from app.services.tprm_scoring_service import risk_level_label
        _inherent_score = getattr(q.supplier, "inherent_risk_score", None)
        _inherent_level = risk_level_label(_inherent_score) if _inherent_score is not None else "medium"
        if _inherent_level == "very_low":
            _inherent_level = "low"
    except Exception:
        _inherent_level = "medium"
    residual_risk_level = _compute_residual_risk(_inherent_level, major_nc, minor_nc)

    q.answers = answers
    q.score = score
    q.submitted_at = now
    q.major_nc = major_nc
    q.minor_nc = minor_nc
    q.residual_risk_level = residual_risk_level
    # Actualizar postura del proveedor y recalcular TPRM
    if q.supplier:
        q.supplier.score = score
        q.supplier.control_effectiveness = score
        q.supplier.last_assessment_at = now
        try:
            from app.services import tprm_scoring_service
            tprm_scoring_service.recompute_supplier(db, q.supplier, commit=False)
        except Exception:
            pass
    db.commit()

    # Bucle cerrado: cuestionario respondido → cerrar VendorIssues de expiry pendientes
    try:
        from app.models import VendorIssue, VendorIssueStatus
        open_issues = db.query(VendorIssue).filter(
            VendorIssue.supplier_id == q.supplier_id,
            VendorIssue.auto_generated_source == "questionnaire_expiry",
            VendorIssue.description.like(f"%{q.id}%"),
            VendorIssue.status.notin_([VendorIssueStatus.CLOSED, VendorIssueStatus.MITIGATED]),
        ).all()
        for issue in open_issues:
            issue.status = VendorIssueStatus.CLOSED
            issue.closed_at = now
            issue.resolved_by_action = _t("supplier_questionnaires.resolved_by_provider", lang)
        if open_issues:
            db.commit()
    except Exception as _e:
        logger.warning("questionnaire→VendorIssue close failed: %s", _e)

    # --- Flujo dos fases: si es cuestionario de profiling, crear el de assessment ---
    next_token = None
    next_title = None
    if q.phase == "profiling" and q.parent_assessment_id:
        try:
            next_token, next_title = _create_followup_assessment(db, q, score, lang)
        except Exception as _fe:
            logger.warning("No se pudo crear el cuestionario de seguimiento para Q%s: %s", q.id, _fe)

    # Best-effort auto-trigger: lanzar evaluacion IA en background si hay API key configurada.
    # No bloquea la respuesta ni propaga excepciones al proveedor.
    try:
        _questionnaire_id = q.id
        _org_id = q.organization_id

        def _bg_ai_review():
            try:
                with SessionLocal() as bg_db:
                    bg_cfg = (
                        bg_db.query(AiConfig)
                        .filter(AiConfig.organization_id == _org_id)
                        .first()
                    )
                    bg_key = resolve_api_key(bg_cfg)
                    if not bg_key:
                        return
                    bg_model = (bg_cfg.model if bg_cfg else None) or "claude-opus-4-6"
                    bg_q = bg_db.query(SupplierQuestionnaire).filter(
                        SupplierQuestionnaire.id == _questionnaire_id
                    ).first()
                    if not bg_q:
                        return
                    result = tprm_ai_service.review_questionnaire(bg_db, bg_q, bg_key, bg_model, lang="es")
                    bg_q.ai_review = result
                    bg_q.ai_reviewed_at = datetime.now(timezone.utc)
                    bg_db.commit()
            except Exception as _exc:
                logger.exception("Auto AI review failed for questionnaire %s: %s",
                                 _questionnaire_id, _exc)

        threading.Thread(target=_bg_ai_review, daemon=True).start()
    except Exception:
        pass

    # Notificar al responsable si hay una planificacion con notify_email configurado
    try:
        _qid = q.id
        _org = q.organization_id
        def _bg_notify():
            from app.services.scheduler import _notify_questionnaire_submitted
            _notify_questionnaire_submitted(_qid, _org)
        threading.Thread(target=_bg_notify, daemon=True).start()
    except Exception:
        pass

    # Notificacion saliente Monday.com si esta configurado
    try:
        from app.routers.integrations_forms import notify_monday_if_configured
        notify_monday_if_configured(db, q.organization_id, q.id)
    except Exception:
        pass

    result = {"success": True, "score": score,
              "message": _t("supplier_questionnaires.thanks", lang)}
    if next_token:
        result["next_token"] = next_token
        result["next_title"] = next_title
        result["phase_transition"] = True
    return result



# ── Opcion A: asignacion interna ─────────────────────────────────────────────

@router.post("/{qid}/assign-internal")
def assign_internal(
    qid: int,
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Asigna el cuestionario a un usuario interno de la plataforma."""
    lang = get_lang(request)
    q = filter_by_org(
        db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == qid),
        SupplierQuestionnaire, current_user,
    ).first()
    if not q:
        raise HTTPException(404, _t("supplier_questionnaires.not_found", lang))
    if q.submitted_at:
        raise HTTPException(400, _t("supplier_questionnaires.already_submitted", lang))

    target_user_id = body.get("user_id")
    if not target_user_id:
        raise HTTPException(400, _t("supplier_questionnaires.user_id_required", lang))
    target_user = db.query(User).filter(
        User.id == target_user_id,
        User.organization_id == current_user.organization_id,
    ).first()
    if not target_user:
        raise HTTPException(404, _t("supplier_questionnaires.user_not_found_org", lang))

    now = datetime.now(timezone.utc)
    q.assigned_user_id = target_user.id
    q.assignment_type = "internal"
    q.assigned_at = now
    db.commit()

    log_action(db, current_user.id, "assign_internal", "supplier_questionnaire", str(q.id),
               {"assigned_to": target_user.email, "questionnaire": q.code})

    # Notificar al usuario asignado por email si hay SMTP configurado
    try:
        cfg = db.query(EmailSettings).filter(
            EmailSettings.organization_id == current_user.organization_id,
            EmailSettings.enabled == True,
        ).first()
        if cfg and target_user.email:
            from app.services import email_service
            body_html = (
                f"<p>{_t('supplier_questionnaires.assign_email_greeting', lang, name=target_user.full_name or target_user.email)}</p>"
                f"<p>{_t('supplier_questionnaires.assign_email_body', lang, code=q.code, title=q.title)}</p>"
                f"<p>{_t('supplier_questionnaires.assign_email_supplier', lang, supplier=q.supplier_name)}</p>"
                f"<p>{_t('supplier_questionnaires.assign_email_howto', lang)}</p>"
            )
            email_service.send_email(cfg, target_user.email,
                                     _t("supplier_questionnaires.assign_email_subject", lang, code=q.code),
                                     body_html)
    except Exception:
        pass

    return {"assigned_to": target_user.email, "questionnaire_code": q.code}


@router.post("/{qid}/internal-submit")
def internal_submit(
    qid: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """El usuario interno asignado responde el cuestionario directamente en la plataforma."""
    q = db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == qid).first()
    if not q:
        raise HTTPException(404, "Cuestionario no encontrado")
    if q.organization_id != current_user.organization_id:
        raise HTTPException(403, "Sin acceso")
    if q.assignment_type != "internal":
        raise HTTPException(400, "Este cuestionario no es de tipo interno")
    if q.assigned_user_id != current_user.id:
        # Admins pueden rellenar cualquier cuestionario interno de su org
        from app.models import UserRole
        if current_user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
            raise HTTPException(403, "Solo el usuario asignado puede responder este cuestionario")
    if q.submitted_at:
        raise HTTPException(400, "El cuestionario ya ha sido respondido")

    answers = body.get("answers", {})
    now = datetime.now(timezone.utc)

    from app.services.tprm_scoring_service import score_questionnaire_answers
    try:
        score_result = score_questionnaire_answers(q.questions or [], answers)
        score = score_result.get("score", _calculate_score(answers))
        major_nc = score_result.get("major_nc", 0)
        minor_nc = score_result.get("minor_nc", 0)
    except Exception:
        score = _calculate_score(answers)
        major_nc = 0
        minor_nc = 0

    q.answers = answers
    q.score = score
    q.submitted_at = now
    q.major_nc = major_nc
    q.minor_nc = minor_nc

    supplier = q.supplier
    if supplier:
        inherent = getattr(supplier, "inherent_risk_level", None) or "medium"
        q.residual_risk_level = _compute_residual_risk(inherent, major_nc, minor_nc)

    db.commit()

    # Bucle cerrado: cuestionario respondido (interno) → cerrar VendorIssues de expiry pendientes
    try:
        from app.models import VendorIssue, VendorIssueStatus
        open_issues_int = db.query(VendorIssue).filter(
            VendorIssue.supplier_id == q.supplier_id,
            VendorIssue.auto_generated_source == "questionnaire_expiry",
            VendorIssue.description.like(f"%{q.id}%"),
            VendorIssue.status.notin_([VendorIssueStatus.CLOSED, VendorIssueStatus.MITIGATED]),
        ).all()
        for issue in open_issues_int:
            issue.status = VendorIssueStatus.CLOSED
            issue.closed_at = now
            issue.resolved_by_action = "Cuestionario respondido internamente"
        if open_issues_int:
            db.commit()
    except Exception as _e:
        logger.warning("questionnaire_internal→VendorIssue close failed: %s", _e)

    log_action(db, current_user.id, "internal_submit", "supplier_questionnaire", str(q.id),
               {"score": score, "supplier": q.supplier_name})

    # Notificaciones y IA review en background (igual que el flujo externo)
    try:
        _qid = q.id
        _org = q.organization_id
        def _bg_notify():
            from app.services.scheduler import _notify_questionnaire_submitted
            _notify_questionnaire_submitted(_qid, _org)
        threading.Thread(target=_bg_notify, daemon=True).start()
    except Exception:
        pass

    return {"success": True, "score": score, "questionnaire_code": q.code}
