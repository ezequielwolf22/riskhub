"""Router de versiones de SoA — ISO 27001 cl. 6.1.3.

Flujo: Analyst crea draft → Admin aprueba → snapshot inmutable → PDF.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import SoAVersion, User
from app.security import get_current_user, require_admin, require_analyst
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.soa_versions")

router = APIRouter(prefix="/api/soa/versions", tags=["soa-versions"])


def _next_version(db: Session, org_id: int) -> str:
    now = datetime.now(timezone.utc)
    count = db.query(SoAVersion).filter_by(organization_id=org_id).count()
    return f"{now.year}-v{count + 1}"


def _take_snapshot(db: Session, org_id: int) -> list:
    """Genera snapshot de todos los controles implementados en la SoA actual."""
    from app.models import ControlImplementation
    impls = db.query(ControlImplementation).filter_by(organization_id=org_id).all()
    return [
        {
            "id": c.id,
            "control_code": c.control.code if c.control else None,
            "control_name": c.control.name if c.control else c.name,
            "status": c.status.value if c.status else "not_implemented",
            "maturity": c.maturity,
            "inclusion_reason": c.inclusion_reason,
            "exclusion_justification": c.exclusion_justification,
        }
        for c in impls
    ]


def _soa_to_dict(soa: SoAVersion) -> dict:
    return {
        "id": soa.id,
        "organization_id": soa.organization_id,
        "version": soa.version,
        "status": soa.status,
        "submitted_by_id": soa.submitted_by_id,
        "submitted_at": soa.submitted_at.isoformat() if soa.submitted_at else None,
        "approved_by_id": soa.approved_by_id,
        "approved_at": soa.approved_at.isoformat() if soa.approved_at else None,
        "approval_notes": soa.approval_notes,
        "controls_count": len(soa.snapshot_json or []),
        "created_at": soa.created_at.isoformat() if soa.created_at else None,
    }


@router.get("")
def list_versions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Historial de versiones de la SoA."""
    versions = (
        db.query(SoAVersion)
        .filter_by(organization_id=current_user.organization_id)
        .order_by(SoAVersion.created_at.desc())
        .all()
    )
    return [_soa_to_dict(v) for v in versions]


@router.post("", status_code=201)
def create_version(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Crea nueva version draft de la SoA con snapshot actual."""
    lang = get_lang(request)
    org_id = current_user.organization_id

    # Comprobar que no hay otro draft activo
    existing_draft = db.query(SoAVersion).filter_by(
        organization_id=org_id, status="draft"
    ).first()
    if existing_draft:
        raise HTTPException(409, _t("soa_versions.draft_already_exists", lang))

    snapshot = _take_snapshot(db, org_id)
    version = SoAVersion(
        organization_id=org_id,
        version=_next_version(db, org_id),
        status="draft",
        snapshot_json=snapshot,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    log_action(db, current_user.id, "create", "soa_version", str(version.id),
               {"version": version.version})
    return _soa_to_dict(version)


@router.get("/{version_id}")
def get_version(
    version_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    soa = db.get(SoAVersion, version_id)
    if not soa or soa.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("soa_versions.version_not_found", lang))
    result = _soa_to_dict(soa)
    result["snapshot_json"] = soa.snapshot_json   # incluir snapshot completo en detalle
    return result


@router.post("/{version_id}/submit")
def submit_version(
    version_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Analyst envia la version para revision del Admin."""
    lang = get_lang(request)
    soa = db.get(SoAVersion, version_id)
    if not soa or soa.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("soa_versions.version_not_found", lang))
    if soa.status != "draft":
        raise HTTPException(400, _t("soa_versions.submit_only_draft", lang))

    soa.status = "under_review"
    soa.submitted_by_id = current_user.id
    soa.submitted_at = datetime.now(timezone.utc)
    db.commit()
    log_action(db, current_user.id, "submit", "soa_version", str(version_id), {})
    return _soa_to_dict(soa)


class ApproveBody(BaseModel):
    approval_notes: Optional[str] = None


@router.post("/{version_id}/approve")
def approve_version(
    version_id: int,
    body: ApproveBody,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin aprueba la SoA. El snapshot queda inmutable. Las versiones anteriores pasan a 'superseded'."""
    lang = get_lang(request)
    soa = db.get(SoAVersion, version_id)
    if not soa or soa.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("soa_versions.version_not_found", lang))
    if soa.status not in ("under_review", "draft"):
        raise HTTPException(400, _t("soa_versions.approve_only_review_or_draft", lang))

    # Marcar versiones anteriores como superseded
    db.query(SoAVersion).filter(
        SoAVersion.organization_id == current_user.organization_id,
        SoAVersion.status == "approved",
        SoAVersion.id != version_id,
    ).update({"status": "superseded"})

    soa.status = "approved"
    soa.approved_by_id = current_user.id
    soa.approved_at = datetime.now(timezone.utc)
    soa.approval_notes = body.approval_notes
    # Refrescar snapshot en el momento de aprobacion (estado definitivo)
    soa.snapshot_json = _take_snapshot(db, current_user.organization_id)
    db.commit()
    log_action(db, current_user.id, "approve", "soa_version", str(version_id),
               {"version": soa.version})
    return _soa_to_dict(soa)


@router.get("/{version_id}/pdf")
def download_pdf(
    version_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Genera PDF de la SoA aprobada."""
    lang = get_lang(request)
    soa = db.get(SoAVersion, version_id)
    if not soa or soa.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("soa_versions.version_not_found", lang))

    pdf_bytes = _generate_soa_pdf(soa, lang)
    if not pdf_bytes:
        raise HTTPException(500, _t("soa_versions.pdf_generation_error", lang))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="SoA_{soa.version}.pdf"'},
    )


def _generate_soa_pdf(soa: SoAVersion, lang: str = "es") -> bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        import io

        buf = io.BytesIO()
        # A4 con margenes 2cm cada lado → ancho util = 17cm
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        PURPLE = colors.HexColor("#59008D")
        ORANGE = colors.HexColor("#D65200")
        normal = styles["Normal"]
        h1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=PURPLE, fontSize=14)
        h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=ORANGE, fontSize=11)
        # Estilos para celdas de tabla — Paragraph wrapping evita desbordamiento
        cell = ParagraphStyle("cell", parent=normal, fontSize=7, leading=9)
        cell_hdr = ParagraphStyle("cellhdr", parent=normal, fontSize=7, leading=9,
                                  textColor=colors.white, fontName="Helvetica-Bold")

        approved_str = soa.approved_at.strftime("%d/%m/%Y") if soa.approved_at else "-"
        story = [
            Paragraph(_t("soa_versions.pdf_title", lang), h1),
            Paragraph(_t("soa_versions.pdf_subtitle", lang), h2),
            Spacer(1, 0.4*cm),
            Paragraph(f"<b>{_t('soa_versions.pdf_version_label', lang)}</b> {soa.version}", normal),
            Paragraph(f"<b>{_t('soa_versions.pdf_status_label', lang)}</b> {soa.status.upper()}", normal),
            Paragraph(f"<b>{_t('soa_versions.pdf_approved_at_label', lang)}</b> {approved_str}", normal),
        ]
        if soa.approval_notes:
            story.append(Paragraph(f"<b>{_t('soa_versions.pdf_approval_notes_label', lang)}</b> {soa.approval_notes}", normal))
        story.append(Spacer(1, 0.5*cm))

        controls = soa.snapshot_json or []
        if controls:
            story.append(Paragraph(
                _t("soa_versions.pdf_controls_section_title", lang, count=len(controls)), h2
            ))

            no_data = _t("soa_versions.pdf_no_data_placeholder", lang)
            STATUS_LABELS = {
                "implemented": _t("soa_versions.pdf_status_implemented", lang),
                "partial": _t("soa_versions.pdf_status_partial", lang),
                "planned": _t("soa_versions.pdf_status_planned", lang),
                "not_implemented": _t("soa_versions.pdf_status_not_implemented", lang),
            }

            # colWidths suma exacta: 1.8+5.2+2.5+1.5+6.0 = 17.0cm
            COL_W = [1.8*cm, 5.2*cm, 2.5*cm, 1.5*cm, 6.0*cm]
            data = [[
                Paragraph(_t("soa_versions.pdf_col_code", lang), cell_hdr),
                Paragraph(_t("soa_versions.pdf_col_control", lang), cell_hdr),
                Paragraph(_t("soa_versions.pdf_col_status", lang), cell_hdr),
                Paragraph(_t("soa_versions.pdf_col_maturity", lang), cell_hdr),
                Paragraph(_t("soa_versions.pdf_col_reason", lang), cell_hdr),
            ]]
            for c in controls:
                status_raw = c.get("status", "") or ""
                reason = (c.get("inclusion_reason") or c.get("exclusion_justification") or no_data).strip()
                data.append([
                    Paragraph(c.get("control_code") or no_data, cell),
                    Paragraph(c.get("control_name") or no_data, cell),
                    Paragraph(STATUS_LABELS.get(status_raw, status_raw), cell),
                    Paragraph(str(c.get("maturity") or 0), cell),
                    Paragraph(reason, cell),
                ])
            t = Table(data, colWidths=COL_W, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(t)

        story += [
            Spacer(1, 1*cm),
            Paragraph(_t("soa_versions.pdf_approved_by_label", lang), normal),
            Spacer(1, 0.3*cm),
            Paragraph(_t("soa_versions.pdf_signature_date_label", lang), normal),
        ]

        doc.build(story)
        return buf.getvalue()
    except Exception as exc:
        logger.exception("Error generando PDF SoA: %s", exc)
        return b""
