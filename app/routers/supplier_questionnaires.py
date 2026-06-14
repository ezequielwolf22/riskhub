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
    n = db.query(SupplierQuestionnaire).count() + 1
    return f"SEQ-{n:04d}"


def _calculate_score(answers: dict) -> int:
    """Calcula puntuacion 0-100 basado en respuestas Si/No."""
    if not answers:
        return 0
    yes_count = sum(1 for v in answers.values() if str(v).lower() in ('true', '1', 'yes', 'si', 'sí'))
    return round(yes_count / len(DEFAULT_QUESTIONS) * 100)


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
):
    q = filter_by_org(db.query(SupplierQuestionnaire), SupplierQuestionnaire, current_user)
    if supplier_id:
        q = q.filter(SupplierQuestionnaire.supplier_id == supplier_id)
    return q.order_by(SupplierQuestionnaire.created_at.desc()).all()


@router.get("/{qid}", response_model=SupplierQuestionnaireOut)
def get_questionnaire(qid: int, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    q = filter_by_org(
        db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == qid),
        SupplierQuestionnaire, current_user
    ).first()
    if not q:
        raise HTTPException(404, "Cuestionario no encontrado")
    return q


@router.post("/", response_model=SupplierQuestionnaireOut)
def create_questionnaire(body: SupplierQuestionnaireCreate, db: Session = Depends(get_db),
                         current_user: User = Depends(require_analyst)):
    supplier = db.query(Supplier).filter(Supplier.id == body.supplier_id).first()
    if not supplier or not check_org_access(supplier.organization_id, current_user):
        raise HTTPException(404, "Proveedor no encontrado")
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
            raise HTTPException(404, "Plantilla no encontrada")
        questions = tpl.questions or []
        template_code = f"custom:{tpl.id}"
    elif body.template_code:
        from app.services import tprm_templates
        tpl = tprm_templates.get_template(body.template_code)
        if not tpl:
            raise HTTPException(404, "Plantilla no encontrada")
        questions = tpl["questions"]
        template_code = tpl["code"]
    q = SupplierQuestionnaire(
        code=_next_code(db),
        supplier_id=body.supplier_id,
        title=body.title,
        token=secrets.token_urlsafe(32),
        template_code=template_code,
        questions=questions,
        expires_at=expires,
        notes=body.notes,
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
def delete_questionnaire(qid: int, db: Session = Depends(get_db),
                         current_user: User = Depends(require_analyst)):
    q = filter_by_org(
        db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == qid),
        SupplierQuestionnaire, current_user
    ).first()
    if not q:
        raise HTTPException(404, "Cuestionario no encontrado")
    db.delete(q)
    db.commit()


@router.post("/{qid}/ai-review")
def ai_review_questionnaire(
    qid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Evalua un cuestionario respondido con IA y almacena el resultado."""
    q = filter_by_org(
        db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == qid),
        SupplierQuestionnaire, current_user,
    ).first()
    if not q:
        raise HTTPException(404, "Cuestionario no encontrado")
    if not q.submitted_at:
        raise HTTPException(409, "El cuestionario aun no ha sido respondido")

    cfg = (
        db.query(AiConfig)
        .filter(AiConfig.organization_id == current_user.organization_id)
        .first()
    )
    key = resolve_api_key(cfg)
    if not key:
        raise HTTPException(
            400,
            "API key de Claude no configurada en IA -> Configuracion",
        )
    model = (cfg.model if cfg else None) or "claude-opus-4-5"

    result = tprm_ai_service.review_questionnaire(db, q, key, model)

    q.ai_review = result
    q.ai_reviewed_at = datetime.now(timezone.utc)
    db.commit()

    log_action(db, current_user.id, "ai_review", "supplier_questionnaire", str(q.id))

    return result


@router.post("/{qid}/send")
def send_questionnaire(qid: int, request: Request, db: Session = Depends(get_db),
                       current_user: User = Depends(require_analyst)):
    """Envia el cuestionario por email al contacto del proveedor con el enlace tokenizado."""
    q = filter_by_org(
        db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == qid),
        SupplierQuestionnaire, current_user,
    ).first()
    if not q:
        raise HTTPException(404, "Cuestionario no encontrado")
    if q.submitted_at:
        raise HTTPException(409, "Este cuestionario ya fue respondido")
    supplier = q.supplier
    recipient = (supplier.contact_email or "").strip() if supplier else ""
    if not recipient:
        raise HTTPException(400, "El proveedor no tiene email de contacto configurado")

    cfg = filter_by_org(db.query(EmailSettings), EmailSettings, current_user).first()
    if not cfg or not cfg.smtp_host:
        raise HTTPException(400, "Configura el servidor de correo (SMTP) en Alertas -> Configuracion")

    base = str(request.base_url).rstrip("/")
    link = f"{base}/supplier-q?token={q.token}"
    expires = q.expires_at.strftime("%d/%m/%Y") if q.expires_at else "-"
    org_name = current_user.organization.name if getattr(current_user, "organization", None) else "nuestra organizacion"
    subject = f"Cuestionario de seguridad — {q.title}"
    body_html = f"""
    <div style="font-family:Inter,Arial,sans-serif;color:#1f2937;">
      <p>Estimado/a {supplier.contact_name or supplier.name}:</p>
      <p>Como parte de nuestro proceso de evaluacion de proveedores ({org_name}),
      le solicitamos completar el siguiente cuestionario de seguridad:
      <strong>{q.title}</strong>.</p>
      <p style="margin:24px 0;">
        <a href="{link}" style="background:#59008D;color:#fff;padding:12px 24px;
           border-radius:6px;text-decoration:none;font-weight:600;">Completar cuestionario</a>
      </p>
      <p style="font-size:13px;color:#6b7280;">O copie este enlace: <br>{link}</p>
      <p style="font-size:13px;color:#6b7280;">Fecha limite: {expires}. No necesita crear cuenta.</p>
    </div>
    """
    from app.services import email_service
    try:
        email_service.send_email(cfg, recipient, subject, body_html)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"No se pudo enviar el email: {exc}")

    log_action(db, current_user.id, "send", "supplier_questionnaire", str(q.id), {"recipient": recipient})
    return {"sent": True, "recipient": recipient, "link": link}


# ---- Flujo dos fases: profiling → assessment ----

def _create_followup_assessment(db, profiling_q, profiling_score: int):
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
    _LEVEL_LABELS = {
        "critical": "Critico",
        "high":     "Alto",
        "medium":   "Medio",
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
    level_label = _LEVEL_LABELS[level]
    title = f"Evaluacion de Seguridad — {supplier.name} (Nivel {level_label})"

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
            VendorRiskAssessment.id == profiling_q.parent_assessment_id
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
    question_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """El proveedor sube un fichero de evidencia para una pregunta (sin auth, por token)."""
    q = db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.token == token).first()
    if not q:
        raise HTTPException(404, "Enlace no valido")
    now = datetime.now(timezone.utc)
    if q.expires_at and q.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(410, "Este enlace ha expirado")
    if q.submitted_at:
        raise HTTPException(409, "Este cuestionario ya fue respondido")

    # OWASP A01 — sanitizar question_id para evitar path traversal en el nombre del fichero
    question_id = re.sub(r"[^a-zA-Z0-9_\-]", "", question_id)[:64]
    if not question_id:
        raise HTTPException(400, "question_id invalido")

    fname = (file.filename or "").lower()
    ext = "." + fname.rsplit(".", 1)[-1] if "." in fname else ""
    if ext not in _EVIDENCE_EXT:
        raise HTTPException(400, "Tipo de fichero no permitido para evidencias.")
    content = await file.read()
    if not content:
        raise HTTPException(400, "El fichero esta vacio.")
    if len(content) > _EVIDENCE_MAX_BYTES:
        raise HTTPException(413, "El fichero supera el limite de 15 MB.")

    # OWASP A08 — validar contenido real (magic bytes) reutilizando el validador de documentos
    try:
        from app.routers.documents import _infer_mime, _validate_magic
        mime = _infer_mime(file.filename or "", file.content_type or "")
        if not _validate_magic(mime, content):
            raise HTTPException(400, "El contenido del fichero no coincide con su extension.")
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
def get_public_questionnaire(token: str, db: Session = Depends(get_db)):
    """Endpoint publico: el proveedor obtiene las preguntas del cuestionario."""
    q = db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.token == token).first()
    if not q:
        raise HTTPException(404, "Enlace no valido")
    now = datetime.now(timezone.utc)
    if q.expires_at and q.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(410, "Este enlace ha expirado")
    if q.submitted_at:
        raise HTTPException(409, "Este cuestionario ya fue respondido")
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
def submit_public_questionnaire(token: str, body: dict, db: Session = Depends(get_db)):
    """Endpoint publico: el proveedor envia sus respuestas."""
    q = db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.token == token).first()
    if not q:
        raise HTTPException(404, "Enlace no valido")
    now = datetime.now(timezone.utc)
    if q.expires_at and q.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(410, "Este enlace ha expirado")
    if q.submitted_at:
        raise HTTPException(409, "Este cuestionario ya fue respondido")
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

    # --- Flujo dos fases: si es cuestionario de profiling, crear el de assessment ---
    next_token = None
    next_title = None
    if q.phase == "profiling" and q.parent_assessment_id:
        try:
            next_token, next_title = _create_followup_assessment(db, q, score)
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
                    bg_model = (bg_cfg.model if bg_cfg else None) or "claude-opus-4-5"
                    bg_q = bg_db.query(SupplierQuestionnaire).filter(
                        SupplierQuestionnaire.id == _questionnaire_id
                    ).first()
                    if not bg_q:
                        return
                    result = tprm_ai_service.review_questionnaire(bg_db, bg_q, bg_key, bg_model)
                    bg_q.ai_review = result
                    bg_q.ai_reviewed_at = datetime.now(timezone.utc)
                    bg_db.commit()
            except Exception as _exc:
                logger.exception("Auto AI review failed for questionnaire %s: %s",
                                 _questionnaire_id, _exc)

        threading.Thread(target=_bg_ai_review, daemon=True).start()
    except Exception:
        pass

    result = {"success": True, "score": score, "message": "Gracias por completar el cuestionario."}
    if next_token:
        result["next_token"] = next_token
        result["next_title"] = next_title
        result["phase_transition"] = True
    return result
