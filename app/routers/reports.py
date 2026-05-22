"""Generacion de informes PDF (Statement of Applicability, Risk Register, etc.)."""
import io
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Asset, ControlImplementation, Risk, RiskContext, RiskStatus, User,
)
from app.security import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])

# Colores brand
BRAND_PURPLE = colors.HexColor("#59008D")
BRAND_ORANGE = colors.HexColor("#D65200")
BRAND_GRAY1 = colors.HexColor("#262626")
BRAND_GRAY3 = colors.HexColor("#9D9D9D")
BRAND_GRAY5 = colors.HexColor("#E9E9E9")


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("TitleBrand", parent=s["Title"], textColor=BRAND_PURPLE,
                         fontName="Helvetica-Bold", fontSize=22, spaceAfter=6))
    s.add(ParagraphStyle("SubBrand", parent=s["Normal"], textColor=BRAND_ORANGE,
                         fontName="Helvetica-Bold", fontSize=12, spaceAfter=12))
    s.add(ParagraphStyle("H2Brand", parent=s["Heading2"], textColor=BRAND_PURPLE,
                         fontName="Helvetica-Bold", fontSize=14, spaceBefore=12, spaceAfter=6))
    s.add(ParagraphStyle("BodyBrand", parent=s["Normal"], textColor=BRAND_GRAY1,
                         fontSize=10, leading=13))
    return s


def _header_footer(canvas, doc):
    canvas.saveState()
    # Brand bar superior (gradiente simulado con rectangulos)
    w, h = A4
    bar_y = h - 8 * mm
    steps = 60
    for i in range(steps):
        t = i / (steps - 1)
        r = (1 - t) * 0x59 / 255 + t * 0xD6 / 255
        g = (1 - t) * 0x00 / 255 + t * 0x52 / 255
        b = (1 - t) * 0x8D / 255 + t * 0x00 / 255
        canvas.setFillColorRGB(r, g, b)
        canvas.rect(i * w / steps, bar_y, w / steps + 0.5, 4 * mm, stroke=0, fill=1)
    # Texto pie
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(BRAND_GRAY3)
    canvas.drawString(20 * mm, 10 * mm,
                      f"RiskHub - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    canvas.drawRightString(w - 20 * mm, 10 * mm, f"Pagina {doc.page}")
    canvas.restoreState()


def _pdf_response(elements, filename: str):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    doc.build(elements, onFirstPage=_header_footer, onLaterPages=_header_footer)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/risk-register")
def risk_register(db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    """Risk Register (ISO 27005)."""
    s = _styles()
    el = []
    el.append(Paragraph("Risk Register", s["TitleBrand"]))
    el.append(Paragraph("ISO/IEC 27005:2018", s["SubBrand"]))
    el.append(Spacer(1, 6))

    ctx = db.query(RiskContext).first()
    if ctx:
        el.append(Paragraph(f"<b>Organizacion:</b> {ctx.organization_name or '-'}", s["BodyBrand"]))
        el.append(Paragraph(f"<b>Alcance:</b> {ctx.scope or '-'}", s["BodyBrand"]))
        el.append(Paragraph(f"<b>Apetito de riesgo:</b> Nivel {ctx.risk_appetite}",
                            s["BodyBrand"]))
        el.append(Spacer(1, 12))

    risks = db.query(Risk).order_by(Risk.residual_level.desc()).all()
    data = [["Codigo", "Activo", "Amenaza", "Inh.", "Res.", "Estado", "Tratamiento"]]
    for r in risks:
        data.append([
            r.code,
            r.asset.name if r.asset else "-",
            r.threat.name if r.threat else "-",
            str(r.inherent_level),
            str(r.residual_level),
            r.status.value if r.status else "-",
            r.treatment_option.value if r.treatment_option else "-",
        ])
    if len(data) > 1:
        t = Table(data, repeatRows=1, colWidths=[20*mm, 40*mm, 50*mm, 12*mm, 12*mm, 20*mm, 22*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), BRAND_PURPLE),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, BRAND_GRAY5]),
            ("GRID", (0,0), (-1,-1), 0.25, BRAND_GRAY3),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ]))
        el.append(t)
    else:
        el.append(Paragraph("No hay riesgos registrados.", s["BodyBrand"]))

    return _pdf_response(el, "risk_register.pdf")


@router.get("/soa")
def statement_of_applicability(db: Session = Depends(get_db),
                               _: User = Depends(get_current_user)):
    """Statement of Applicability ISO 27001/27002."""
    s = _styles()
    el = []
    el.append(Paragraph("Statement of Applicability", s["TitleBrand"]))
    el.append(Paragraph("ISO/IEC 27001 - ISO/IEC 27002:2022", s["SubBrand"]))
    el.append(Spacer(1, 12))

    impls = db.query(ControlImplementation).all()
    by_control = {}
    for imp in impls:
        by_control.setdefault(imp.control_id, []).append(imp)

    from app.models import Control
    controls = db.query(Control).order_by(Control.code).all()
    data = [["Control", "Nombre", "Aplicable", "Estado", "Madurez"]]
    for c in controls:
        ims = by_control.get(c.id, [])
        if ims:
            for imp in ims:
                data.append([c.code, c.name[:60], "Si", imp.status.value, f"{imp.maturity}/5"])
        else:
            data.append([c.code, c.name[:60], "No", "-", "-"])

    t = Table(data, repeatRows=1, colWidths=[18*mm, 80*mm, 18*mm, 30*mm, 20*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), BRAND_PURPLE),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7.5),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, BRAND_GRAY5]),
        ("GRID", (0,0), (-1,-1), 0.25, BRAND_GRAY3),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    el.append(t)
    return _pdf_response(el, "soa.pdf")
