"""Modulo de Awareness — infografias de concienciacion generadas por IA.

Endpoints:
  GET  /api/awareness/branding          — configuracion de marca actual
  PUT  /api/awareness/branding          — guardar marca (admin)
  POST /api/awareness/branding/logo     — subir logo
  POST /api/awareness/generate          — generar contenido IA
  GET  /api/awareness/                  — listar infografias guardadas
  POST /api/awareness/                  — guardar infografia
  GET  /api/awareness/{id}              — obtener infografia
  PUT  /api/awareness/{id}              — actualizar infografia
  DELETE /api/awareness/{id}            — eliminar
  GET  /api/awareness/{id}/export-pdf   — exportar como PDF
"""
import base64
import io
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.i18n import get_lang, t as _t

from app.database import get_db
from app.models import (
    AiConfig, AwarenessItem, AwarenessBranding, Risk, RiskStatus, User,
)
from app.routers.ai_config import resolve_api_key
from app.security import check_org_access, filter_by_org, get_current_user, require_admin, require_analyst
from app.services.audit_service import log_action
from app.services import awareness_service as svc

logger = logging.getLogger("riskhub.awareness")

router = APIRouter(prefix="/api/awareness", tags=["awareness"])

_BRANDING_LOGO_ROOT = None  # se inicializa lazy


def _logo_root():
    global _BRANDING_LOGO_ROOT
    if _BRANDING_LOGO_ROOT is None:
        from pathlib import Path
        p = Path("/srv/data/branding")
        if not p.exists():
            p = Path(__file__).parent.parent.parent / "data" / "branding"
        p.mkdir(parents=True, exist_ok=True)
        _BRANDING_LOGO_ROOT = p
    return _BRANDING_LOGO_ROOT


# SVG excluido: puede contener <script> y event handlers → stored XSS via localStorage JWT
_ALLOWED_LOGO_MIME = {"image/png", "image/jpeg", "image/webp"}
_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB

# ============================================================
# Branding
# ============================================================

@router.get("/branding")
def get_branding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    brand = filter_by_org(db.query(AwarenessBranding), AwarenessBranding, current_user).first()
    if not brand:
        return {
            "primary_color": "#59008D",
            "secondary_color": "#D65200",
            "company_name": "",
            "has_logo": False,
        }
    return {
        "primary_color": brand.primary_color or "#59008D",
        "secondary_color": brand.secondary_color or "#D65200",
        "company_name": brand.company_name or "",
        "has_logo": bool(brand.logo_filename),
    }


class BrandingIn(BaseModel):
    primary_color: str = "#59008D"
    secondary_color: str = "#D65200"
    company_name: Optional[str] = None


@router.put("/branding")
def save_branding(
    body: BrandingIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    def _valid_hex(c: str) -> bool:
        return len(c) == 7 and c.startswith("#")

    if not _valid_hex(body.primary_color):
        raise HTTPException(400, "primary_color debe ser un color hex valido (#RRGGBB)")
    if not _valid_hex(body.secondary_color):
        raise HTTPException(400, "secondary_color debe ser un color hex valido (#RRGGBB)")

    brand = filter_by_org(db.query(AwarenessBranding), AwarenessBranding, current_user).first()
    if not brand:
        brand = AwarenessBranding(organization_id=current_user.organization_id)
        db.add(brand)
    brand.primary_color = body.primary_color
    brand.secondary_color = body.secondary_color
    brand.company_name = body.company_name
    brand.updated_at = datetime.now(timezone.utc)
    brand.updated_by_id = current_user.id
    db.commit()
    return {"ok": True}


@router.post("/branding/logo")
def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    data = file.file.read()
    if len(data) > _MAX_LOGO_BYTES:
        raise HTTPException(400, "El logo no puede superar 2 MB")
    mime = file.content_type or "image/png"
    if mime not in _ALLOWED_LOGO_MIME:
        raise HTTPException(400, "Formato no soportado. Usa PNG, JPG o WebP. SVG no esta permitido por seguridad.")
    # Validar magic bytes para evitar spoofing de Content-Type
    _MAGIC = {
        b"\x89PNG": "image/png",
        b"\xff\xd8\xff": "image/jpeg",
        b"<svg": "image/svg+xml",
        b"RIFF": "image/webp",
    }
    if mime != "image/svg+xml":
        detected = next((m for sig, m in _MAGIC.items() if data[:len(sig)] == sig), None)
        if not detected or detected != mime:
            raise HTTPException(400, "El contenido del archivo no coincide con el formato declarado.")

    import uuid
    fname = f"logo_{uuid.uuid4().hex}.{mime.split('/')[-1]}"
    (_logo_root() / fname).write_bytes(data)

    brand = filter_by_org(db.query(AwarenessBranding), AwarenessBranding, current_user).first()
    if not brand:
        brand = AwarenessBranding(organization_id=current_user.organization_id)
        db.add(brand)
    # Eliminar logo anterior
    if brand.logo_filename:
        old = _logo_root() / brand.logo_filename
        if old.exists():
            old.unlink(missing_ok=True)
    brand.logo_filename = fname
    brand.logo_mime = mime
    brand.updated_at = datetime.now(timezone.utc)
    brand.updated_by_id = current_user.id
    db.commit()
    return {"ok": True, "filename": fname}


@router.delete("/branding/logo")
def delete_logo(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    brand = filter_by_org(db.query(AwarenessBranding), AwarenessBranding, current_user).first()
    if brand and brand.logo_filename:
        p = _logo_root() / brand.logo_filename
        if p.exists():
            p.unlink(missing_ok=True)
        brand.logo_filename = None
        brand.logo_mime = None
        brand.updated_at = datetime.now(timezone.utc)
        db.commit()
    return {"ok": True}


@router.get("/branding/logo")
def get_logo(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve el logo como base64 para embeber en el frontend."""
    lang = get_lang(request)
    brand = filter_by_org(db.query(AwarenessBranding), AwarenessBranding, current_user).first()
    if not brand or not brand.logo_filename:
        raise HTTPException(404, _t("common.not_found", lang))
    p = _logo_root() / brand.logo_filename
    if not p.exists():
        raise HTTPException(404, _t("common.not_found", lang))
    data = p.read_bytes()
    encoded = base64.b64encode(data).decode()
    return {"mime": brand.logo_mime, "data": encoded}


# ============================================================
# Generacion IA
# ============================================================

class GenerateRequest(BaseModel):
    prompt: str                        # descripcion de lo que quiere el usuario
    template: Optional[str] = None     # sugerencia de plantilla


@router.post("/generate")
def generate_content(
    request: Request,
    body: GenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Genera el contenido de una infografia usando el agente IA."""
    lang = get_lang(request)
    if not body.prompt or len(body.prompt.strip()) < 5:
        raise HTTPException(400, _t("common.bad_request", lang))

    ai_cfg = filter_by_org(db.query(AiConfig), AiConfig, current_user).first()
    api_key = resolve_api_key(ai_cfg)
    if not api_key:
        raise HTTPException(400, _t("common.bad_request", lang))

    model = (ai_cfg.model if ai_cfg else None) or "claude-haiku-4-5"

    # Contexto de riesgos activos (top 10 por nivel residual, filtrado por org)
    from app.security import filter_by_org as _fbo
    risks = (
        _fbo(db.query(Risk), Risk, current_user)
        .filter(Risk.status != RiskStatus.CLOSED)
        .order_by(Risk.residual_level.desc())
        .limit(10)
        .all()
    )
    risks_summary = "\n".join(
        f"- [{r.code}] {r.asset.name if r.asset else '?'} / "
        f"{r.threat.name if r.threat else '?'}: "
        f"residual={r.residual_level}, estado={r.status.value}"
        for r in risks
    ) or "No hay riesgos activos registrados."

    # Contexto de la organizacion
    from app.services.context_builder import build_context
    org_context = build_context(db, query=body.prompt, organization_id=current_user.organization_id)
    # Anonimizar antes de enviar al exterior
    from app.services.anonymizer import anonymize
    org_context = anonymize(org_context, "medium")

    # Inyectar plantilla sugerida si el usuario no especifico
    prompt_extra = body.prompt
    if body.template:
        prompt_extra += f"\n\nUSA LA PLANTILLA: {body.template}"

    try:
        content = svc.generate_content(
            user_prompt=prompt_extra,
            org_context=org_context,
            risks_summary=risks_summary,
            api_key=api_key,
            model=model,
        )
    except Exception as e:
        logger.error("Error generando awareness content: %s", e)
        raise HTTPException(500, f"Error del agente IA: {e}")

    log_action(db, current_user.id, "generate", "awareness", None,
               {"template": content.get("template"), "title": content.get("title")})
    db.commit()

    return {"content": content}


# ============================================================
# CRUD de infografias
# ============================================================

def _item_out(item: AwarenessItem) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "template_type": item.template_type,
        "status": item.status,
        "tags": item.tags or [],
        "created_by": item.created_by.full_name if item.created_by else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "content": json.loads(item.content_json) if item.content_json else {},
    }


@router.get("/")
def list_items(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = filter_by_org(db.query(AwarenessItem), AwarenessItem, current_user)
    if status:
        q = q.filter(AwarenessItem.status == status)
    items = q.order_by(AwarenessItem.updated_at.desc()).all()
    return [_item_out(i) for i in items]


class ItemIn(BaseModel):
    title: str
    template_type: str = "best_practices"
    content: dict
    status: str = "draft"
    tags: Optional[list[str]] = None


@router.post("/")
def create_item(
    body: ItemIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    item = AwarenessItem(
        title=body.title[:255],
        template_type=body.template_type,
        content_json=json.dumps(body.content, ensure_ascii=False),
        status=body.status,
        tags=body.tags or [],
        created_by_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _item_out(item)


@router.get("/{item_id}")
def get_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lang = get_lang(request)
    item = filter_by_org(
        db.query(AwarenessItem).filter(AwarenessItem.id == item_id),
        AwarenessItem, current_user
    ).first()
    if not item:
        raise HTTPException(404, _t("awareness.campaign_not_found", lang))
    return _item_out(item)


@router.put("/{item_id}")
def update_item(
    item_id: int,
    request: Request,
    body: ItemIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    item = filter_by_org(
        db.query(AwarenessItem).filter(AwarenessItem.id == item_id),
        AwarenessItem, current_user
    ).first()
    if not item:
        raise HTTPException(404, _t("awareness.campaign_not_found", lang))
    item.title = body.title[:255]
    item.template_type = body.template_type
    item.content_json = json.dumps(body.content, ensure_ascii=False)
    item.status = body.status
    item.tags = body.tags or []
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return _item_out(item)


@router.delete("/{item_id}")
def delete_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    item = filter_by_org(
        db.query(AwarenessItem).filter(AwarenessItem.id == item_id),
        AwarenessItem, current_user
    ).first()
    if not item:
        raise HTTPException(404, _t("awareness.campaign_not_found", lang))
    log_action(db, current_user.id, "delete", "awareness", item_id, {"title": item.title})
    db.delete(item)
    db.commit()
    return {"ok": True}


# ============================================================
# Export PDF
# ============================================================

@router.get("/{item_id}/export-pdf")
def export_pdf(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lang = get_lang(request)
    item = filter_by_org(
        db.query(AwarenessItem).filter(AwarenessItem.id == item_id),
        AwarenessItem, current_user
    ).first()
    if not item:
        raise HTTPException(404, _t("awareness.campaign_not_found", lang))

    content = json.loads(item.content_json) if item.content_json else {}

    # Cargar branding de la misma org
    brand_row = filter_by_org(db.query(AwarenessBranding), AwarenessBranding, current_user).first()
    branding: dict = {}
    if brand_row:
        branding = {
            "primary_color": brand_row.primary_color or "#59008D",
            "secondary_color": brand_row.secondary_color or "#D65200",
            "company_name": brand_row.company_name or "",
        }
        if brand_row.logo_filename:
            p = _logo_root() / brand_row.logo_filename
            if p.exists():
                branding["logo_data"] = p.read_bytes()

    try:
        pdf_bytes = svc.export_pdf(content, branding)
    except Exception as e:
        logger.error("Error exportando PDF awareness: %s", e)
        raise HTTPException(500, f"Error generando PDF: {e}")

    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in item.title)[:50]
    filename = f"awareness_{safe_title}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
