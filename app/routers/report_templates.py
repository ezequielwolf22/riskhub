"""Templates de marca por tipo de informe — colores, logo, fuente y textos personalizados.

Endpoints:
  GET  /api/report-templates                         — listar todos los templates de la org
  GET  /api/report-templates/{report_type}           — obtener un template especifico
  PUT  /api/report-templates/{report_type}           — crear o actualizar (upsert)
  DELETE /api/report-templates/{report_type}         — restaurar valores por defecto
  POST /api/report-templates/{report_type}/logo      — subir logo
  GET  /api/report-templates/{report_type}/logo      — obtener imagen del logo
"""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import ReportBrandingConfig, User
from app.security import filter_by_org, get_current_user, require_admin
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.report_templates")

router = APIRouter(prefix="/api/report-templates", tags=["report-templates"])

VALID_REPORT_TYPES = {
    "all",
    "risk_register",
    "soa",
    "sgsi_status",
    "management_review",
    "treatment_plan",
    "executive_dashboard",
    "committee_minutes",
    "followup_report",
}

VALID_FONTS = {"Helvetica", "Times-Roman", "Courier"}

_ALLOWED_LOGO_MIME = {"image/png", "image/jpeg", "image/webp"}
_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB

_LOGO_ROOT = None
_TEMPLATE_ROOT = None

_ALLOWED_TEMPLATE_MIME = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/html",
}
_MAX_TEMPLATE_BYTES = 10 * 1024 * 1024  # 10 MB


def _logo_root():
    global _LOGO_ROOT
    if _LOGO_ROOT is None:
        from pathlib import Path
        p = Path("/srv/data/branding")
        if not p.exists():
            p = Path(__file__).parent.parent.parent / "data" / "branding"
        p.mkdir(parents=True, exist_ok=True)
        _LOGO_ROOT = p
    return _LOGO_ROOT


def _template_root():
    global _TEMPLATE_ROOT
    if _TEMPLATE_ROOT is None:
        from pathlib import Path
        p = Path("/srv/data/branding/templates")
        if not p.exists():
            p = Path(__file__).parent.parent.parent / "data" / "branding" / "templates"
        p.mkdir(parents=True, exist_ok=True)
        _TEMPLATE_ROOT = p
    return _TEMPLATE_ROOT


def _valid_hex(c: str) -> bool:
    return len(c) == 7 and c.startswith("#")


def _template_to_dict(t: ReportBrandingConfig) -> dict:
    return {
        "id": t.id,
        "report_type": t.report_type,
        "primary_color": t.primary_color or "#59008D",
        "secondary_color": t.secondary_color or "#D65200",
        "company_name": t.company_name or "",
        "header_title": t.header_title or "",
        "footer_text": t.footer_text or "",
        "cover_subtitle": t.cover_subtitle or "",
        "font_family": t.font_family or "Helvetica",
        "has_logo": bool(t.logo_filename),
        "logo_mime": t.logo_mime or "",
        "has_template_file": bool(t.template_filename),
        "template_mime": t.template_mime or "",
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


# ──────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────

class TemplateIn(BaseModel):
    primary_color: str = "#59008D"
    secondary_color: str = "#D65200"
    company_name: Optional[str] = None
    header_title: Optional[str] = None
    footer_text: Optional[str] = None
    cover_subtitle: Optional[str] = None
    font_family: str = "Helvetica"


# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────

@router.get("")
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista todos los templates de marca configurados para la organizacion."""
    rows = (
        filter_by_org(db.query(ReportBrandingConfig), ReportBrandingConfig, current_user)
        .order_by(ReportBrandingConfig.report_type)
        .all()
    )
    return [_template_to_dict(r) for r in rows]


@router.get("/{report_type}")
def get_template(
    report_type: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve el template para un tipo de informe, o los valores por defecto si no existe."""
    lang = get_lang(request)
    if report_type not in VALID_REPORT_TYPES:
        raise HTTPException(400, _t("report_templates.invalid_report_type", lang, report_type=report_type))
    row = (
        filter_by_org(db.query(ReportBrandingConfig), ReportBrandingConfig, current_user)
        .filter(ReportBrandingConfig.report_type == report_type)
        .first()
    )
    if not row:
        return {
            "report_type": report_type,
            "primary_color": "#59008D",
            "secondary_color": "#D65200",
            "company_name": "",
            "header_title": "",
            "footer_text": "",
            "cover_subtitle": "",
            "font_family": "Helvetica",
            "has_logo": False,
            "logo_mime": "",
            "has_template_file": False,
            "template_mime": "",
            "updated_at": None,
        }
    return _template_to_dict(row)


@router.put("/{report_type}")
def upsert_template(
    report_type: str,
    body: TemplateIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Crea o actualiza el template de marca para un tipo de informe."""
    lang = get_lang(request)
    if report_type not in VALID_REPORT_TYPES:
        raise HTTPException(400, _t("report_templates.invalid_report_type", lang, report_type=report_type))
    if not _valid_hex(body.primary_color):
        raise HTTPException(400, _t("report_templates.invalid_primary_color", lang))
    if not _valid_hex(body.secondary_color):
        raise HTTPException(400, _t("report_templates.invalid_secondary_color", lang))
    if body.font_family not in VALID_FONTS:
        raise HTTPException(400, _t("report_templates.unsupported_font", lang, valid_fonts=', '.join(VALID_FONTS)))

    row = (
        filter_by_org(db.query(ReportBrandingConfig), ReportBrandingConfig, current_user)
        .filter(ReportBrandingConfig.report_type == report_type)
        .first()
    )
    if not row:
        row = ReportBrandingConfig(
            organization_id=current_user.organization_id,
            report_type=report_type,
        )
        db.add(row)

    row.primary_color = body.primary_color
    row.secondary_color = body.secondary_color
    row.company_name = body.company_name
    row.header_title = body.header_title
    row.footer_text = body.footer_text
    row.cover_subtitle = body.cover_subtitle
    row.font_family = body.font_family
    db.commit()

    log_action(db, current_user, "report_template_update",
               _t("report_templates.audit_template_updated", lang, report_type=report_type), "report_template")
    return _template_to_dict(row)


@router.delete("/{report_type}")
def delete_template(
    report_type: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Elimina el template (restaura valores por defecto de RiskHub)."""
    lang = get_lang(request)
    if report_type not in VALID_REPORT_TYPES:
        raise HTTPException(400, _t("report_templates.invalid_report_type", lang, report_type=report_type))
    row = (
        filter_by_org(db.query(ReportBrandingConfig), ReportBrandingConfig, current_user)
        .filter(ReportBrandingConfig.report_type == report_type)
        .first()
    )
    if not row:
        raise HTTPException(404, _t("report_templates.template_not_found", lang))

    # Borrar logo fisico si existe
    if row.logo_filename:
        logo_path = _logo_root() / row.logo_filename
        try:
            logo_path.unlink(missing_ok=True)
        except Exception:
            pass

    db.delete(row)
    db.commit()
    log_action(db, current_user, "report_template_delete",
               _t("report_templates.audit_template_deleted", lang, report_type=report_type), "report_template")
    return {"ok": True}


@router.post("/{report_type}/logo")
def upload_logo(
    report_type: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Sube el logo para el template. Acepta PNG, JPG o WebP (max 2 MB)."""
    lang = get_lang(request)
    if report_type not in VALID_REPORT_TYPES:
        raise HTTPException(400, _t("report_templates.invalid_report_type", lang, report_type=report_type))

    data = file.file.read()
    if len(data) > _MAX_LOGO_BYTES:
        raise HTTPException(400, _t("report_templates.logo_too_large", lang))
    mime = file.content_type or "image/png"
    if mime not in _ALLOWED_LOGO_MIME:
        raise HTTPException(400, _t("report_templates.unsupported_logo_format", lang))

    # Validar magic bytes (OWASP A08 — Software and Data Integrity Failures)
    _MAGIC = {
        b"\x89PNG": "image/png",
        b"\xff\xd8\xff": "image/jpeg",
        b"RIFF": "image/webp",
    }
    detected = next((m for sig, m in _MAGIC.items() if data[:len(sig)] == sig), None)
    if not detected or detected != mime:
        raise HTTPException(400, _t("report_templates.logo_content_mismatch", lang))

    ext = mime.split("/")[-1]
    fname = f"rpt_{report_type}_{uuid.uuid4().hex}.{ext}"
    (_logo_root() / fname).write_bytes(data)

    row = (
        filter_by_org(db.query(ReportBrandingConfig), ReportBrandingConfig, current_user)
        .filter(ReportBrandingConfig.report_type == report_type)
        .first()
    )
    if not row:
        row = ReportBrandingConfig(
            organization_id=current_user.organization_id,
            report_type=report_type,
        )
        db.add(row)

    # Borrar logo anterior
    if row.logo_filename:
        old = _logo_root() / row.logo_filename
        try:
            old.unlink(missing_ok=True)
        except Exception:
            pass

    row.logo_filename = fname
    row.logo_mime = mime
    db.commit()

    log_action(db, current_user, "report_template_logo",
               _t("report_templates.audit_logo_uploaded", lang, report_type=report_type), "report_template")
    return {"ok": True, "filename": fname}


@router.delete("/{report_type}/logo")
def delete_logo(
    report_type: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Elimina el logo del template."""
    lang = get_lang(request)
    if report_type not in VALID_REPORT_TYPES:
        raise HTTPException(400, _t("report_templates.invalid_report_type", lang, report_type=report_type))
    row = (
        filter_by_org(db.query(ReportBrandingConfig), ReportBrandingConfig, current_user)
        .filter(ReportBrandingConfig.report_type == report_type)
        .first()
    )
    if not row or not row.logo_filename:
        raise HTTPException(404, _t("report_templates.no_logo_configured", lang))
    logo_path = _logo_root() / row.logo_filename
    try:
        logo_path.unlink(missing_ok=True)
    except Exception:
        pass
    row.logo_filename = None
    row.logo_mime = None
    db.commit()
    return {"ok": True}


@router.post("/{report_type}/template-file")
def upload_template_file(
    report_type: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Sube un fichero .docx o .html como plantilla base para la generacion de informes."""
    lang = get_lang(request)
    if report_type not in VALID_REPORT_TYPES:
        raise HTTPException(400, _t("report_templates.invalid_report_type", lang, report_type=report_type))

    data = file.file.read()
    if len(data) > _MAX_TEMPLATE_BYTES:
        raise HTTPException(400, _t("report_templates.template_file_too_large", lang))

    # Detectar MIME por nombre de fichero (los .docx son ZIP, .html son texto)
    filename_lower = (file.filename or "").lower()
    if filename_lower.endswith(".docx"):
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif filename_lower.endswith(".html") or filename_lower.endswith(".htm"):
        mime = "text/html"
    else:
        raise HTTPException(400, _t("report_templates.unsupported_template_file", lang))

    ext = "docx" if mime.startswith("application/") else "html"
    fname = f"tpl_{report_type}_{uuid.uuid4().hex}.{ext}"
    (_template_root() / fname).write_bytes(data)

    row = (
        filter_by_org(db.query(ReportBrandingConfig), ReportBrandingConfig, current_user)
        .filter(ReportBrandingConfig.report_type == report_type)
        .first()
    )
    if not row:
        row = ReportBrandingConfig(
            organization_id=current_user.organization_id,
            report_type=report_type,
        )
        db.add(row)

    # Borrar fichero anterior
    if row.template_filename:
        old = _template_root() / row.template_filename
        try:
            old.unlink(missing_ok=True)
        except Exception:
            pass

    row.template_filename = fname
    row.template_mime = mime
    db.commit()

    log_action(db, current_user, "report_template_file_upload",
               _t("report_templates.audit_template_file_uploaded", lang, report_type=report_type, ext=ext), "report_template")
    return {"ok": True, "filename": fname, "mime": mime}


@router.delete("/{report_type}/template-file")
def delete_template_file(
    report_type: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Elimina el fichero de plantilla base del template."""
    lang = get_lang(request)
    if report_type not in VALID_REPORT_TYPES:
        raise HTTPException(400, _t("report_templates.invalid_report_type", lang, report_type=report_type))
    row = (
        filter_by_org(db.query(ReportBrandingConfig), ReportBrandingConfig, current_user)
        .filter(ReportBrandingConfig.report_type == report_type)
        .first()
    )
    if not row or not row.template_filename:
        raise HTTPException(404, _t("report_templates.no_template_file_configured", lang))
    tpl_path = _template_root() / row.template_filename
    try:
        tpl_path.unlink(missing_ok=True)
    except Exception:
        pass
    row.template_filename = None
    row.template_mime = None
    db.commit()
    return {"ok": True}


@router.get("/{report_type}/logo")
def get_logo(
    report_type: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve la imagen del logo del template."""
    lang = get_lang(request)
    if report_type not in VALID_REPORT_TYPES:
        raise HTTPException(400, _t("report_templates.invalid_report_type", lang, report_type=report_type))
    row = (
        filter_by_org(db.query(ReportBrandingConfig), ReportBrandingConfig, current_user)
        .filter(ReportBrandingConfig.report_type == report_type)
        .first()
    )
    if not row or not row.logo_filename:
        raise HTTPException(404, _t("report_templates.no_logo_configured", lang))
    logo_path = _logo_root() / row.logo_filename
    if not logo_path.exists():
        raise HTTPException(404, _t("report_templates.logo_file_not_found", lang))
    data = logo_path.read_bytes()
    return Response(content=data, media_type=row.logo_mime or "image/png")
