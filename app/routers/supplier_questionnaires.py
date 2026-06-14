"""Cuestionarios de evaluacion de seguridad de proveedores — NIS2 Art. 21.2.d."""
import secrets
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
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
    # TPRM: si se indica una plantilla del sistema, usar sus preguntas (con pesos
    # y reglas de scoring). Si no, usar el set estandar NIS2/ISO 27001.
    questions = DEFAULT_QUESTIONS
    template_code = None
    if body.template_code:
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
    # Sanitizar: nunca exponer al proveedor las reglas de scoring ni las pistas
    # de evaluacion / mapeo a controles internos.
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
    # TPRM: las plantillas del sistema traen pesos y reglas de scoring; si la
    # pregunta los incluye, usar el scoring ponderado. Si no, scoring Si/No.
    if q.template_code or any((qq.get("scoring_rules") or qq.get("weight")) for qq in (q.questions or [])):
        from app.services.tprm_scoring_service import score_questionnaire
        result = score_questionnaire(q.questions or [], answers)
        score = result["score"]
    else:
        score = _calculate_score(answers)
    q.answers = answers
    q.score = score
    q.submitted_at = now
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
            except Exception:
                pass

        threading.Thread(target=_bg_ai_review, daemon=True).start()
    except Exception:
        pass

    return {"success": True, "score": score, "message": "Gracias por completar el cuestionario."}
