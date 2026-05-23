"""Generacion de informes PDF y Excel (Risk Register, SoA, informes IA)."""
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
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
    Asset, Control, ControlImplementation, Risk, RiskContext, RiskStatus, User,
)
from app.security import get_current_user
from app.services import report_ai_service

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


# ============================================================
# Excel — Risk Register completo
# ============================================================

@router.get("/risk-register-excel")
def risk_register_excel(db: Session = Depends(get_db),
                        _: User = Depends(get_current_user)):
    """Exporta el Risk Register completo a Excel (.xlsx)."""
    import openpyxl
    from openpyxl.styles import (
        Alignment, Border, Font, PatternFill, Side,
    )
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()

    # ---- Hoja 1: Riesgos ----
    ws = wb.active
    ws.title = "Risk Register"

    hdr_fill = PatternFill("solid", fgColor="59008D")
    hdr_font = Font(color="FFFFFF", bold=True, size=10)
    alt_fill = PatternFill("solid", fgColor="F3E8FF")
    thin = Side(style="thin", color="D1D5DB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = [
        "Codigo", "Activo", "Tipo activo", "Amenaza", "Categoria amenaza",
        "Lik. inh.", "Cons. inh.", "Nivel inh.",
        "Lik. res.", "Cons. res.", "Nivel res.",
        "Estado", "Tratamiento", "Fecha limite",
        "Descripcion", "Plan tratamiento",
    ]
    ws.append(headers)
    for col_idx, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

    risks = db.query(Risk).order_by(Risk.residual_level.desc()).all()
    for i, r in enumerate(risks, 2):
        row = [
            r.code,
            r.asset.name if r.asset else "-",
            r.asset.asset_type.value if r.asset and r.asset.asset_type else "-",
            r.threat.name if r.threat else "-",
            r.threat.category if r.threat else "-",
            r.inherent_likelihood,
            r.inherent_consequence,
            r.inherent_level,
            r.residual_likelihood,
            r.residual_consequence,
            r.residual_level,
            r.status.value if r.status else "-",
            r.treatment_option.value if r.treatment_option else "-",
            r.treatment_due_date.strftime("%Y-%m-%d") if r.treatment_due_date else "-",
            r.description or "",
            r.treatment_plan or "",
        ]
        ws.append(row)
        row_fill = alt_fill if i % 2 == 0 else None
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=i, column=col_idx)
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if row_fill:
                cell.fill = row_fill
            # Colorear nivel residual
            if col_idx == 11 and isinstance(cell.value, int):
                if cell.value >= 7:
                    cell.fill = PatternFill("solid", fgColor="FCA5A5")
                elif cell.value >= 5:
                    cell.fill = PatternFill("solid", fgColor="FED7AA")
                elif cell.value >= 3:
                    cell.fill = PatternFill("solid", fgColor="FEF9C3")

    col_widths = [12, 24, 18, 30, 18, 9, 9, 9, 9, 9, 9, 14, 16, 14, 40, 40]
    for idx, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(idx)].width = w
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"

    # ---- Hoja 2: Activos ----
    ws2 = wb.create_sheet("Activos")
    ws2.append(["Codigo", "Nombre", "Tipo", "Clasificacion", "Loc.", "C", "I", "A", "Valor max"])
    for col_idx in range(1, 10):
        c = ws2.cell(row=1, column=col_idx)
        c.fill = hdr_fill
        c.font = hdr_font
        c.border = border
        c.alignment = Alignment(horizontal="center")

    assets = db.query(Asset).order_by(Asset.code).all()
    for i, a in enumerate(assets, 2):
        ws2.append([
            a.code, a.name,
            a.asset_type.value if a.asset_type else "-",
            a.classification or "-",
            a.location or "-",
            a.value_confidentiality, a.value_integrity, a.value_availability,
            a.value_max,
        ])
        for col_idx in range(1, 10):
            ws2.cell(row=i, column=col_idx).border = border

    for idx, w in enumerate([12, 28, 20, 16, 16, 6, 6, 6, 10], 1):
        ws2.column_dimensions[get_column_letter(idx)].width = w

    # ---- Hoja 3: Controles ----
    ws3 = wb.create_sheet("Controles")
    ws3.append(["Control", "Nombre", "Tema", "Estado", "Madurez", "Descripcion"])
    for col_idx in range(1, 7):
        c = ws3.cell(row=1, column=col_idx)
        c.fill = hdr_fill
        c.font = hdr_font
        c.border = border
        c.alignment = Alignment(horizontal="center")

    impls = db.query(ControlImplementation).all()
    for i, imp in enumerate(impls, 2):
        ws3.append([
            imp.control.code if imp.control else "-",
            imp.name,
            imp.control.theme if imp.control else "-",
            imp.status.value if imp.status else "-",
            imp.maturity,
            imp.description or "",
        ])
        for col_idx in range(1, 7):
            ws3.cell(row=i, column=col_idx).border = border

    for idx, w in enumerate([10, 32, 18, 18, 10, 40], 1):
        ws3.column_dimensions[get_column_letter(idx)].width = w

    # ---- Hoja 4: Resumen ----
    ws4 = wb.create_sheet("Resumen")
    ctx = db.query(RiskContext).first()
    stat_fill = PatternFill("solid", fgColor="EDE9FE")
    rows_summary = [
        ("Organizacion", ctx.organization_name if ctx else "-"),
        ("Alcance", (ctx.scope or "-") if ctx else "-"),
        ("Apetito de riesgo", f"Nivel {ctx.risk_appetite if ctx else '-'} / 8"),
        ("Fecha exportacion", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("", ""),
        ("Total riesgos", len(risks)),
        ("Nivel critico (>=7)", sum(1 for r in risks if r.residual_level >= 7)),
        ("Nivel alto (5-6)", sum(1 for r in risks if 5 <= r.residual_level < 7)),
        ("Nivel medio (3-4)", sum(1 for r in risks if 3 <= r.residual_level < 5)),
        ("Nivel bajo (<3)", sum(1 for r in risks if r.residual_level < 3)),
        ("Con plan de tratamiento", sum(1 for r in risks if r.treatment_option)),
        ("Aceptados", sum(1 for r in risks if r.status == RiskStatus.ACCEPTED)),
        ("", ""),
        ("Total activos", len(assets)),
        ("Total controles implementados", len(impls)),
    ]
    for label, value in rows_summary:
        ws4.append([label, value])
    for row_idx in range(1, len(rows_summary) + 1):
        for col_idx in [1, 2]:
            cell = ws4.cell(row=row_idx, column=col_idx)
            cell.border = border
            if col_idx == 1 and ws4.cell(row=row_idx, column=1).value:
                cell.font = Font(bold=True)
            if row_idx in [1, 2, 3, 4]:
                cell.fill = stat_fill

    ws4.column_dimensions["A"].width = 32
    ws4.column_dimensions["B"].width = 30

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"riskhub_export_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ============================================================
# Informes generados por IA
# ============================================================

REPORT_LABEL = {
    "treatment_plan": "Plan de Tratamiento de Riesgos",
    "executive_dashboard": "Dashboard Ejecutivo",
    "committee_minutes": "Acta de Comite de Seguridad",
    "followup_report": "Informe de Seguimiento ISO 27005",
}


class AiReportIn(BaseModel):
    report_type: str
    format: str = "pdf"  # pdf | excel


@router.post("/ai-generate")
def ai_generate(body: AiReportIn, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    """Genera un informe ejecutivo usando Claude API y lo devuelve como PDF o Excel."""
    if body.report_type not in REPORT_LABEL:
        raise HTTPException(422, f"report_type no valido. Opciones: {list(REPORT_LABEL)}")
    if body.format not in ("pdf", "excel"):
        raise HTTPException(422, "format debe ser 'pdf' o 'excel'")

    try:
        content = report_ai_service.generate(body.report_type, db)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Error llamando a Claude API: {e}")

    if body.format == "excel":
        return _ai_report_excel(content, body.report_type)
    return _ai_report_pdf(content, body.report_type)


def _safe(text, max_chars=None):
    """Convierte a string y opcionalmente trunca para ReportLab."""
    if not text:
        return ""
    s = str(text)
    if max_chars:
        s = s[:max_chars]
    # ReportLab no soporta algunos caracteres de control
    return s.replace("\x00", "").replace("\r", "")


def _ai_report_pdf(content: dict, report_type: str):
    """Convierte el JSON de Claude a un PDF con ReportLab."""
    s = _styles()
    el = []
    label = REPORT_LABEL.get(report_type, "Informe")

    # Portada
    el.append(Spacer(1, 30 * mm))
    el.append(Paragraph(_safe(content.get("title", label)), s["TitleBrand"]))
    org = _safe(content.get("organization", ""))
    if org:
        el.append(Paragraph(org, s["SubBrand"]))
    date_str = _safe(content.get("date", datetime.now().strftime("%d/%m/%Y")))
    el.append(Paragraph(f"Fecha: {date_str}", s["BodyBrand"]))
    el.append(Spacer(1, 8))

    def add_section(title, text):
        if text:
            el.append(Paragraph(title, s["H2Brand"]))
            el.append(Paragraph(_safe(text), s["BodyBrand"]))
            el.append(Spacer(1, 6))

    def add_list(title, items):
        if items:
            el.append(Paragraph(title, s["H2Brand"]))
            for item in items:
                el.append(Paragraph(f"• {_safe(item)}", s["BodyBrand"]))
            el.append(Spacer(1, 6))

    # Secciones comunes
    add_section("Resumen ejecutivo", content.get("executive_summary"))

    # Secciones especificas por tipo
    if report_type == "treatment_plan":
        add_section("Analisis del apetito de riesgo", content.get("risk_appetite_analysis"))
        risks = content.get("risks", [])
        if risks:
            el.append(Paragraph("Planes de tratamiento por riesgo", s["H2Brand"]))
            el.append(Spacer(1, 4))
            data = [["Codigo", "Prioridad", "Esfuerzo", "Nivel objetivo", "Acciones"]]
            for r in risks:
                actions = "\n".join(f"• {a}" for a in (r.get("recommended_actions") or [])[:3])
                data.append([
                    _safe(r.get("code", "")),
                    _safe(r.get("priority", "")),
                    _safe(r.get("estimated_effort", "")),
                    str(r.get("target_residual_level", "")),
                    _safe(actions, 200),
                ])
            t = Table(data, repeatRows=1, colWidths=[22*mm, 28*mm, 20*mm, 22*mm, 73*mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_PURPLE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_GRAY5]),
                ("GRID", (0, 0), (-1, -1), 0.25, BRAND_GRAY3),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            el.append(t)
            el.append(Spacer(1, 8))
            # Narrativas detalladas
            for r in risks:
                el.append(Paragraph(f"<b>{_safe(r.get('code',''))}</b> — {_safe(r.get('treatment_narrative',''))}",
                                    s["BodyBrand"]))
                if r.get("success_metrics"):
                    el.append(Paragraph(f"<i>Metricas de exito:</i> {_safe(r['success_metrics'])}", s["BodyBrand"]))
                el.append(Spacer(1, 4))
        add_section("Hoja de ruta de implementacion", content.get("implementation_roadmap"))
        add_section("Conclusion", content.get("conclusion"))

    elif report_type == "executive_dashboard":
        add_list("Hallazgos clave", content.get("key_findings"))
        add_section("Postura de riesgo", content.get("risk_posture_explanation"))
        add_section("Riesgos criticos", content.get("top_risks_narrative"))
        add_section("Efectividad de controles", content.get("control_effectiveness"))
        add_section("Estado de cumplimiento", content.get("compliance_status"))
        add_list("Acciones criticas requeridas", content.get("critical_actions"))
        add_section("Analisis de KPIs", content.get("kpi_commentary"))
        add_section("Proxima revision recomendada", content.get("next_review_recommendation"))

        # Tabla de estadisticas
        meta = content.get("_meta", {})
        stats = meta.get("stats", {})
        if stats:
            el.append(Paragraph("Estadisticas del registro de riesgos", s["H2Brand"]))
            stat_data = [
                ["Total", str(stats.get("total", 0))],
                ["Criticos (>=7)", str(stats.get("critical", 0))],
                ["Altos (5-6)", str(stats.get("high", 0))],
                ["Medios (3-4)", str(stats.get("medium", 0))],
                ["Bajos (<3)", str(stats.get("low", 0))],
                ["Con tratamiento", str(stats.get("with_treatment", 0))],
                ["Aceptados", str(stats.get("accepted", 0))],
            ]
            t = Table(stat_data, colWidths=[60*mm, 30*mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), BRAND_GRAY5),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, BRAND_GRAY3),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ]))
            el.append(t)

    elif report_type == "committee_minutes":
        session_info = content.get("session_number", "")
        if session_info:
            add_section("Numero de sesion", session_info)
        add_section("Nota sobre asistentes", content.get("attendees_note"))
        add_list("Orden del dia", content.get("agenda"))
        add_section("Revision del registro de riesgos", content.get("risk_register_review"))
        # Riesgos aceptados
        accepted = content.get("accepted_risks", [])
        if accepted:
            el.append(Paragraph("Riesgos formalmente aceptados", s["H2Brand"]))
            for ar in accepted:
                el.append(Paragraph(
                    f"<b>{_safe(ar.get('code',''))}</b>: {_safe(ar.get('rationale',''))}",
                    s["BodyBrand"],
                ))
            el.append(Spacer(1, 6))
        add_section("Seguimiento de tratamientos", content.get("treatment_followup"))
        add_list("Decisiones adoptadas", content.get("decisions"))
        # Acciones
        actions = content.get("action_items", [])
        if actions:
            el.append(Paragraph("Acciones acordadas", s["H2Brand"]))
            data = [["Accion", "Responsable", "Plazo"]]
            for a in actions:
                data.append([_safe(a.get("action", ""), 80),
                              _safe(a.get("responsible", "")),
                              _safe(a.get("deadline", ""))])
            t = Table(data, repeatRows=1, colWidths=[90*mm, 45*mm, 30*mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_PURPLE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, BRAND_GRAY3),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            el.append(t)
        add_list("Temas para proxima sesion", content.get("next_session_topics"))
        add_section("Cierre", content.get("closing_note"))

    elif report_type == "followup_report":
        add_section("Subtitulo", content.get("subtitle"))
        cl12 = content.get("cl12_assessment", {})
        if cl12:
            el.append(Paragraph("Evaluacion ISO 27005 clausula 12", s["H2Brand"]))
            for key, label_text in [
                ("monitoring_adequacy", "Monitorizacion continua"),
                ("review_frequency", "Frecuencia de revision"),
                ("improvement_actions", "Acciones de mejora"),
                ("context_changes", "Cambios en el contexto"),
            ]:
                if cl12.get(key):
                    el.append(Paragraph(f"<b>{label_text}:</b> {_safe(cl12[key])}", s["BodyBrand"]))
                    el.append(Spacer(1, 4))
        kpi = content.get("kpi_analysis", {})
        if kpi:
            el.append(Paragraph("Analisis de KPIs", s["H2Brand"]))
            for key, label_text in [
                ("risk_reduction_trend", "Tendencia de reduccion del riesgo"),
                ("treatment_effectiveness", "Efectividad de tratamientos"),
                ("control_coverage", "Cobertura de controles"),
                ("pending_actions", "Acciones pendientes"),
            ]:
                if kpi.get(key):
                    el.append(Paragraph(f"<b>{label_text}:</b> {_safe(kpi[key])}", s["BodyBrand"]))
                    el.append(Spacer(1, 4))
        add_list("Fortalezas identificadas", content.get("strengths"))
        add_list("Debilidades identificadas", content.get("weaknesses"))
        recs = content.get("recommendations", [])
        if recs:
            el.append(Paragraph("Recomendaciones", s["H2Brand"]))
            data = [["Area", "Recomendacion", "Prioridad", "Ref. ISO"]]
            for rec in recs:
                data.append([
                    _safe(rec.get("area", ""), 30),
                    _safe(rec.get("recommendation", ""), 100),
                    _safe(rec.get("priority", "")),
                    _safe(rec.get("iso_reference", "")),
                ])
            t = Table(data, repeatRows=1, colWidths=[30*mm, 90*mm, 18*mm, 25*mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_PURPLE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, BRAND_GRAY3),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            el.append(t)
        add_section("Conclusion", content.get("conclusion"))

    fname = f"{report_type}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return _pdf_response(el, fname)


def _ai_report_excel(content: dict, report_type: str):
    """Convierte el JSON de Claude a un Excel."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = REPORT_LABEL.get(report_type, "Informe")[:31]

    hdr_fill = PatternFill("solid", fgColor="59008D")
    hdr_font = Font(color="FFFFFF", bold=True)
    thin = Side(style="thin", color="D1D5DB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def write_section(title, text):
        if not text:
            return
        ws.append([title])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="59008D", size=11)
        ws.append([str(text)])
        ws.cell(row=ws.max_row, column=1).alignment = Alignment(wrap_text=True)
        ws.append([""])

    def write_list(title, items):
        if not items:
            return
        ws.append([title])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="59008D", size=11)
        for item in items:
            ws.append(["• " + str(item)])
        ws.append([""])

    ws.append([content.get("title", REPORT_LABEL.get(report_type, "Informe"))])
    ws.cell(row=1, column=1).font = Font(bold=True, size=14, color="59008D")
    ws.append([f"Organización: {content.get('organization', '')} — Fecha: {content.get('date', '')}"])
    ws.append([""])

    write_section("Resumen ejecutivo", content.get("executive_summary"))

    if report_type == "treatment_plan":
        write_section("Análisis del apetito de riesgo", content.get("risk_appetite_analysis"))
        risks = content.get("risks", [])
        if risks:
            ws.append(["Planes de tratamiento"])
            ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="59008D", size=11)
            hdrs = ["Código", "Prioridad", "Narrativa", "Acciones", "Métricas", "Esfuerzo", "Nivel objetivo"]
            ws.append(hdrs)
            for h_idx, _ in enumerate(hdrs, 1):
                c = ws.cell(row=ws.max_row, column=h_idx)
                c.fill = hdr_fill
                c.font = hdr_font
                c.border = border
            for r in risks:
                ws.append([
                    r.get("code", ""),
                    r.get("priority", ""),
                    r.get("treatment_narrative", ""),
                    "; ".join(r.get("recommended_actions") or []),
                    r.get("success_metrics", ""),
                    r.get("estimated_effort", ""),
                    r.get("target_residual_level", ""),
                ])
                for col_i in range(1, len(hdrs) + 1):
                    ws.cell(row=ws.max_row, column=col_i).border = border
        write_section("Hoja de ruta", content.get("implementation_roadmap"))
        write_section("Conclusión", content.get("conclusion"))

    elif report_type == "executive_dashboard":
        write_list("Hallazgos clave", content.get("key_findings"))
        write_section("Postura de riesgo", content.get("risk_posture_explanation"))
        write_section("Riesgos críticos", content.get("top_risks_narrative"))
        write_section("Efectividad de controles", content.get("control_effectiveness"))
        write_list("Acciones críticas", content.get("critical_actions"))
        write_section("Análisis de KPIs", content.get("kpi_commentary"))
        # Stats
        meta = content.get("_meta", {})
        stats = meta.get("stats", {})
        if stats:
            ws.append(["Estadísticas"])
            ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="59008D", size=11)
            for k, v in stats.items():
                ws.append([k.replace("_", " ").capitalize(), v])

    elif report_type == "committee_minutes":
        write_list("Orden del día", content.get("agenda"))
        write_section("Revisión del registro", content.get("risk_register_review"))
        accepted = content.get("accepted_risks", [])
        if accepted:
            ws.append(["Riesgos aceptados"])
            ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="59008D", size=11)
            ws.append(["Código", "Justificación"])
            for ar in accepted:
                ws.append([ar.get("code", ""), ar.get("rationale", "")])
        write_list("Decisiones adoptadas", content.get("decisions"))
        actions = content.get("action_items", [])
        if actions:
            ws.append(["Acciones acordadas"])
            ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="59008D", size=11)
            ws.append(["Acción", "Responsable", "Plazo"])
            for a in actions:
                ws.append([a.get("action", ""), a.get("responsible", ""), a.get("deadline", "")])
        write_section("Cierre", content.get("closing_note"))

    elif report_type == "followup_report":
        cl12 = content.get("cl12_assessment", {})
        if cl12:
            ws.append(["Evaluación ISO 27005 cláusula 12"])
            ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="59008D", size=11)
            for k, v in cl12.items():
                ws.append([k.replace("_", " ").capitalize(), str(v)])
        write_list("Fortalezas", content.get("strengths"))
        write_list("Debilidades", content.get("weaknesses"))
        recs = content.get("recommendations", [])
        if recs:
            ws.append(["Recomendaciones"])
            ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="59008D", size=11)
            ws.append(["Área", "Recomendación", "Prioridad", "Referencia ISO"])
            for rec in recs:
                ws.append([rec.get("area", ""), rec.get("recommendation", ""),
                           rec.get("priority", ""), rec.get("iso_reference", "")])
        write_section("Conclusión", content.get("conclusion"))

    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 70
    for col in ["C", "D", "E", "F", "G"]:
        ws.column_dimensions[col].width = 20

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"{report_type}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )
