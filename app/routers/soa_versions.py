"""Router de versiones de SoA — ISO 27001 cl. 6.1.3.

Flujo: Analyst crea draft → Admin aprueba → snapshot inmutable → PDF.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Crea nueva version draft de la SoA con snapshot actual."""
    org_id = current_user.organization_id

    # Comprobar que no hay otro draft activo
    existing_draft = db.query(SoAVersion).filter_by(
        organization_id=org_id, status="draft"
    ).first()
    if existing_draft:
        raise HTTPException(409, "Ya existe un borrador de SoA activo")

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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    soa = db.get(SoAVersion, version_id)
    if not soa or soa.organization_id != current_user.organization_id:
        raise HTTPException(404, "Version no encontrada")
    result = _soa_to_dict(soa)
    result["snapshot_json"] = soa.snapshot_json   # incluir snapshot completo en detalle
    return result


@router.post("/{version_id}/submit")
def submit_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Analyst envia la version para revision del Admin."""
    soa = db.get(SoAVersion, version_id)
    if not soa or soa.organization_id != current_user.organization_id:
        raise HTTPException(404, "Version no encontrada")
    if soa.status != "draft":
        raise HTTPException(400, "Solo se pueden enviar versiones en borrador")

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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin aprueba la SoA. El snapshot queda inmutable. Las versiones anteriores pasan a 'superseded'."""
    soa = db.get(SoAVersion, version_id)
    if not soa or soa.organization_id != current_user.organization_id:
        raise HTTPException(404, "Version no encontrada")
    if soa.status not in ("under_review", "draft"):
        raise HTTPException(400, "Solo se pueden aprobar versiones en revision o borrador")

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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Genera PDF de la SoA aprobada."""
    soa = db.get(SoAVersion, version_id)
    if not soa or soa.organization_id != current_user.organization_id:
        raise HTTPException(404, "Version no encontrada")

    pdf_bytes = _generate_soa_pdf(soa)
    if not pdf_bytes:
        raise HTTPException(500, "Error generando PDF")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="SoA_{soa.version}.pdf"'},
    )


def _generate_soa_pdf(soa: SoAVersion) -> bytes:
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
            Paragraph("DECLARACION DE APLICABILIDAD (SoA)", h1),
            Paragraph("ISO/IEC 27001:2022 — Clausula 6.1.3", h2),
            Spacer(1, 0.4*cm),
            Paragraph(f"<b>Version:</b> {soa.version}", normal),
            Paragraph(f"<b>Estado:</b> {soa.status.upper()}", normal),
            Paragraph(f"<b>Aprobada el:</b> {approved_str}", normal),
        ]
        if soa.approval_notes:
            story.append(Paragraph(f"<b>Notas de aprobacion:</b> {soa.approval_notes}", normal))
        story.append(Spacer(1, 0.5*cm))

        controls = soa.snapshot_json or []
        if controls:
            story.append(Paragraph(f"CONTROLES ({len(controls)} entradas)", h2))

            STATUS_ES = {
                "implemented": "Implementado",
                "partial": "Parcial",
                "planned": "Planificado",
                "not_implemented": "No implementado",
            }

            # colWidths suma exacta: 1.8+5.2+2.5+1.5+6.0 = 17.0cm
            COL_W = [1.8*cm, 5.2*cm, 2.5*cm, 1.5*cm, 6.0*cm]
            data = [[
                Paragraph("Codigo", cell_hdr),
                Paragraph("Control", cell_hdr),
                Paragraph("Estado", cell_hdr),
                Paragraph("Mad.", cell_hdr),
                Paragraph("Razon inclusion / Justif. exclusion", cell_hdr),
            ]]
            for c in controls:
                status_raw = c.get("status", "") or ""
                reason = (c.get("inclusion_reason") or c.get("exclusion_justification") or "—").strip()
                data.append([
                    Paragraph(c.get("control_code") or "—", cell),
                    Paragraph(c.get("control_name") or "—", cell),
                    Paragraph(STATUS_ES.get(status_raw, status_raw), cell),
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
            Paragraph("Aprobado por: ____________________________", normal),
            Spacer(1, 0.3*cm),
            Paragraph("Firma y fecha: ____________________________", normal),
        ]

        doc.build(story)
        return buf.getvalue()
    except Exception as exc:
        logger.exception("Error generando PDF SoA: %s", exc)
        return b""
