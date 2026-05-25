"""Cuestionarios de evaluacion de seguridad de proveedores — NIS2 Art. 21.2.d."""
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Supplier, SupplierQuestionnaire, User
from app.schemas import SupplierQuestionnaireCreate, SupplierQuestionnaireOut
from app.security import get_current_user, require_analyst
from app.services.audit_service import log_action

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
    _: User = Depends(get_current_user),
    supplier_id: Optional[int] = None,
):
    q = db.query(SupplierQuestionnaire)
    if supplier_id:
        q = q.filter(SupplierQuestionnaire.supplier_id == supplier_id)
    return q.order_by(SupplierQuestionnaire.created_at.desc()).all()


@router.get("/{qid}", response_model=SupplierQuestionnaireOut)
def get_questionnaire(qid: int, db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)):
    q = db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == qid).first()
    if not q:
        raise HTTPException(404, "Cuestionario no encontrado")
    return q


@router.post("/", response_model=SupplierQuestionnaireOut)
def create_questionnaire(body: SupplierQuestionnaireCreate, db: Session = Depends(get_db),
                         current_user: User = Depends(require_analyst)):
    supplier = db.query(Supplier).filter(Supplier.id == body.supplier_id).first()
    if not supplier:
        raise HTTPException(404, "Proveedor no encontrado")
    expires = body.expires_at or (datetime.now(timezone.utc) + timedelta(days=30))
    q = SupplierQuestionnaire(
        code=_next_code(db),
        supplier_id=body.supplier_id,
        title=body.title,
        token=secrets.token_urlsafe(32),
        questions=DEFAULT_QUESTIONS,
        expires_at=expires,
        notes=body.notes,
        created_by_id=current_user.id,
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
    q = db.query(SupplierQuestionnaire).filter(SupplierQuestionnaire.id == qid).first()
    if not q:
        raise HTTPException(404, "Cuestionario no encontrado")
    db.delete(q)
    db.commit()


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
    return {
        "code": q.code,
        "title": q.title,
        "supplier_name": supplier.name if supplier else "",
        "questions": q.questions,
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
    score = _calculate_score(answers)
    q.answers = answers
    q.score = score
    q.submitted_at = now
    # Actualizar score del proveedor
    if q.supplier:
        q.supplier.score = score
        q.supplier.last_assessment_at = now
    db.commit()
    return {"success": True, "score": score, "message": "Gracias por completar el cuestionario."}
