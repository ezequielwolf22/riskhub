"""Gestion de politicas de seguridad — ISO 27001 cl. 5.2."""
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AiConfig, Policy, PolicyStatus, User
from app.routers.documents import MAX_SIZE_BYTES, _infer_mime, _validate_magic
from app.schemas import PolicyIn, PolicyOut, PolicyUpdate
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action
from app.services.document_service import extract_text
from app.routers.ai_config import resolve_api_key

router = APIRouter(prefix="/api/policies", tags=["policies"])

_EXTRACT_SYSTEM = """Eres un asistente especializado en seguridad de la informacion e ISO/IEC 27001.
Tu tarea es extraer informacion estructurada de documentos de politica de seguridad.

Devuelve UNICAMENTE un objeto JSON valido con estos campos (sin texto extra antes ni despues):
{
  "title": "titulo de la politica (string)",
  "category": "categoria o tipo (Acceso, Criptografia, Backup, Continuidad, RRHH, etc.)",
  "version": "numero de version detectado, ej: 1.0 o 2.3 (string)",
  "scope": "alcance de la politica (string, max 300 chars)",
  "content": "resumen ejecutivo del contenido (string, max 800 chars)",
  "review_date": "fecha de proxima revision en formato YYYY-MM-DD o null si no se detecta",
  "iso_clauses": ["lista de clausulas ISO 27001/27002 referenciadas, ej: ['5.1','6.1.3','8.2']"],
  "confidence_notes": "notas sobre campos con baja confianza en la extraccion (string)"
}

Si no puedes determinar un campo con certeza, usa null o string vacio segun el tipo.
Para iso_clauses, busca referencias explicitas a articulos, clausulas o controles ISO.
"""


def _next_code(db: Session) -> str:
    n = db.query(Policy).count() + 1
    return f"POL-{n:04d}"


@router.get("/", response_model=list[PolicyOut])
def list_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: Optional[PolicyStatus] = None,
    category: Optional[str] = None,
    q: Optional[str] = None,
):
    query = filter_by_org(db.query(Policy), Policy, current_user)
    if status:
        query = query.filter(Policy.status == status)
    if category:
        query = query.filter(Policy.category.ilike(f"%{category}%"))
    if q:
        query = query.filter(Policy.title.ilike(f"%{q}%"))
    return query.order_by(Policy.updated_at.desc()).all()


@router.get("/stats/summary")
def policies_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    policies = filter_by_org(db.query(Policy), Policy, current_user).all()
    now = datetime.now(timezone.utc)
    overdue_review = sum(
        1 for p in policies
        if p.review_date and p.status not in (PolicyStatus.OBSOLETE,)
        and p.review_date.replace(tzinfo=timezone.utc) < now
    )
    by_status = {s.value: sum(1 for p in policies if p.status == s) for s in PolicyStatus}
    return {
        "total": len(policies),
        "overdue_review": overdue_review,
        "by_status": by_status,
    }


@router.get("/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: int, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    p = db.query(Policy).filter(Policy.id == policy_id).first()
    if not p or not check_org_access(p.organization_id, current_user):
        raise HTTPException(404, "Politica no encontrada")
    return p


@router.post("/", response_model=PolicyOut)
def create_policy(body: PolicyIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_analyst)):
    p = Policy(
        code=_next_code(db),
        organization_id=current_user.organization_id,
        title=body.title,
        version=body.version,
        category=body.category,
        status=body.status,
        scope=body.scope,
        content=body.content,
        iso_clauses=body.iso_clauses,
        review_date=body.review_date,
        owner_id=body.owner_id or current_user.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    log_action(db, current_user.id, "create", "policy", str(p.id), {"code": p.code})
    return p


@router.patch("/{policy_id}", response_model=PolicyOut)
def update_policy(policy_id: int, body: PolicyUpdate,
                  db: Session = Depends(get_db),
                  current_user: User = Depends(require_analyst)):
    p = db.query(Policy).filter(Policy.id == policy_id).first()
    if not p or not check_org_access(p.organization_id, current_user):
        raise HTTPException(404, "Politica no encontrada")
    update_data = body.model_dump(exclude_none=True)
    # Auto-stamp approved_at when approving
    if update_data.get("status") == PolicyStatus.APPROVED and not p.approved_at:
        update_data.setdefault("approved_at", datetime.now(timezone.utc))
        update_data.setdefault("approved_by_id", current_user.id)
    for field, value in update_data.items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)
    log_action(db, current_user.id, "update", "policy", str(p.id))
    return p


@router.delete("/{policy_id}", status_code=204)
def delete_policy(policy_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(require_analyst)):
    p = db.query(Policy).filter(Policy.id == policy_id).first()
    if not p or not check_org_access(p.organization_id, current_user):
        raise HTTPException(404, "Politica no encontrada")
    log_action(db, current_user.id, "delete", "policy", str(policy_id), {"title": p.title})
    db.delete(p)
    db.commit()


# ============================================================
# Extraccion IA de campos desde documento de politica
# ============================================================

@router.post("/ai-extract")
def ai_extract_policy(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Sube un documento de politica y extrae sus campos principales con IA.

    Devuelve un objeto con los campos extraidos para pre-rellenar el formulario.
    El documento NO se guarda — solo se procesa en memoria.
    """
    # Validaciones de archivo (reutilizar logica de documents.py)
    data = file.file.read()
    if len(data) > MAX_SIZE_BYTES:
        raise HTTPException(400, "Archivo demasiado grande (maximo 20 MB)")

    mime = _infer_mime(file.filename or "", file.content_type or "")
    allowed_types = ("pdf", "docx", "plain", "csv")
    if not any(k in mime for k in allowed_types):
        raise HTTPException(400, "Tipo de archivo no soportado. Usa PDF, DOCX o TXT.")
    if not _validate_magic(mime, data):
        raise HTTPException(400, "El contenido del archivo no coincide con la extension declarada.")

    # Extraer texto
    try:
        text = extract_text(data, mime)
    except Exception as e:
        raise HTTPException(422, f"No se pudo extraer texto del documento: {e}")

    if not text or len(text.strip()) < 50:
        raise HTTPException(422, "El documento no contiene suficiente texto para analizar.")

    # Truncar a ~12 000 chars para no exceder el contexto del modelo
    text_truncated = text[:12000]

    # Resolver API key del tenant actual
    cfg = filter_by_org(db.query(AiConfig), AiConfig, current_user).first()
    api_key = resolve_api_key(cfg)
    if not api_key:
        raise HTTPException(
            400,
            "API key no configurada. Ve a Configuracion > Agente IA para añadir una clave."
        )
    model = (cfg.model if cfg else None) or "claude-haiku-4-5"

    # Llamar a Claude
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_EXTRACT_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"Extrae los campos de esta politica de seguridad:\n\n{text_truncated}",
            }],
        )
        raw = response.content[0].text if response.content else "{}"
    except Exception as e:
        raise HTTPException(500, f"Error llamando al agente IA: {e}")

    # Parsear JSON de la respuesta
    try:
        # Extraer el bloque JSON aunque venga con texto decorativo
        m = re.search(r"\{[\s\S]*\}", raw)
        extracted = json.loads(m.group(0)) if m else {}
    except Exception:
        extracted = {"confidence_notes": "La IA no devolvio JSON valido. Rellena los campos manualmente."}

    log_action(db, current_user.id, "ai_extract", "policy", None,
               {"filename": file.filename, "model": model})
    db.commit()

    return {
        "title": extracted.get("title") or "",
        "category": extracted.get("category") or "",
        "version": extracted.get("version") or "1.0",
        "scope": extracted.get("scope") or "",
        "content": extracted.get("content") or "",
        "review_date": extracted.get("review_date") or None,
        "iso_clauses": extracted.get("iso_clauses") or [],
        "confidence_notes": extracted.get("confidence_notes") or "",
    }
