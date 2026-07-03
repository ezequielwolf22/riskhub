"""Router de dashboard ejecutivo y reportes board-level."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.i18n import get_lang, t as _t
from app.security import get_current_user, require_role
from app.services.executive_service import (
    get_kpis,
    get_top_risks,
    get_risk_trend,
    get_risk_heatmap,
    generate_board_report_data,
)

router = APIRouter(prefix="/api/executive", tags=["executive"])


@router.get("/kpis")
def executive_kpis(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """KPIs dinámicos para dashboard ejecutivo."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, _t("compliance.org_required", get_lang(request)))
    return get_kpis(db, org_id)


@router.get("/top-risks")
def top_risks(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Top N riesgos por nivel residual con paginacion."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, _t("compliance.org_required", get_lang(request)))
    return get_top_risks(db, org_id, limit, offset)


@router.get("/risk-trend")
def risk_trend(
    request: Request,
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trend de riesgos por día (últimos N días)."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, _t("compliance.org_required", get_lang(request)))
    return get_risk_trend(db, org_id, days)


@router.get("/heatmap")
def risk_heatmap(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Heatmap de riesgos por dominio y framework."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, _t("compliance.org_required", get_lang(request)))
    return get_risk_heatmap(db, org_id)


@router.get("/board-report")
def board_report_data(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Datos para informe de dirección (board-level)."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, _t("compliance.org_required", get_lang(request)))
    return generate_board_report_data(db, org_id, get_lang(request))


@router.get("/board-report/pdf")
def board_report_pdf(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera PDF del informe de dirección."""
    from fastapi.responses import Response
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, _t("compliance.org_required", get_lang(request)))

    lang = get_lang(request)
    data = generate_board_report_data(db, org_id, lang)
    pdf_bytes = _generate_board_pdf(data, lang)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=board_report.pdf"},
    )


def _generate_board_pdf(data: dict, lang: str = "es") -> bytes:
    """Genera PDF de informe de dirección con ReportLab."""
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )
    from reportlab.lib.units import cm

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm,
                            leftMargin=2*cm, rightMargin=2*cm)

    PURPLE = colors.HexColor("#59008D")
    ORANGE = colors.HexColor("#D65200")
    LIGHT_GRAY = colors.HexColor("#F5F5F5")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"],
                                 textColor=PURPLE, fontSize=22, spaceAfter=6)
    h2_style = ParagraphStyle("h2", parent=styles["Heading2"],
                              textColor=PURPLE, fontSize=14, spaceAfter=4)
    normal_style = ParagraphStyle("normal", parent=styles["Normal"], fontSize=10, spaceAfter=4)
    small_style = ParagraphStyle("small", parent=styles["Normal"], fontSize=8,
                                 textColor=colors.gray)

    story = []
    kpis = data.get("kpis", {})
    org_name = data.get("org_name", _t("executive.org_fallback", lang))

    # Header
    story.append(Paragraph(_t("executive.pdf_title", lang, org=org_name), title_style))
    story.append(Paragraph(_t("executive.pdf_period", lang, period=data.get('period', 'N/A')), small_style))
    story.append(HRFlowable(color=ORANGE, thickness=2))
    story.append(Spacer(1, 0.4*cm))

    # Resumen ejecutivo
    story.append(Paragraph(_t("executive.pdf_exec_summary", lang), h2_style))
    story.append(Paragraph(data.get("summary_text", ""), normal_style))
    story.append(Spacer(1, 0.4*cm))

    # KPIs
    story.append(Paragraph(_t("executive.pdf_kpis", lang), h2_style))
    kpi_data = [
        [_t("executive.col_indicator", lang), _t("executive.col_value", lang)],
        [_t("executive.kpi_total_risks", lang), str(kpis.get("total_risks", 0))],
        [_t("executive.kpi_high", lang), str(kpis.get("high_risks", 0))],
        [_t("executive.kpi_over_appetite", lang), str(kpis.get("risks_over_appetite", 0))],
        [_t("executive.kpi_mitigated", lang), f"{kpis.get('mitigated_pct', 0)}%"],
        [_t("executive.kpi_controls", lang), f"{kpis.get('controls_pct', 0)}%"],
        [_t("executive.kpi_overdue", lang), str(kpis.get("overdue_tasks", 0))],
        [_t("executive.kpi_incidents_30d", lang), str(kpis.get("incidents_30d", 0))],
        [_t("executive.kpi_mat", lang), _t("executive.kpi_mat_value", lang, n=kpis.get('mat_days', 0))],
    ]
    kpi_table = Table(kpi_data, colWidths=[10*cm, 5*cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.5*cm))

    # Top riesgos
    top = data.get("top_risks", [])
    if top:
        story.append(Paragraph(_t("executive.pdf_top_risks", lang), h2_style))
        risk_rows = [[_t("executive.col_code", lang), _t("executive.col_description", lang), _t("executive.col_asset", lang), _t("executive.col_residual", lang), _t("executive.col_status", lang)]]
        for r in top[:5]:
            risk_rows.append([
                r.get("code", ""),
                (r.get("description", "") or "")[:50],
                (r.get("asset_name", "") or "")[:30],
                str(r.get("residual_level", 0)),
                r.get("status", ""),
            ])
        risk_table = Table(risk_rows, colWidths=[2.5*cm, 6*cm, 3.5*cm, 2.5*cm, 3*cm])
        risk_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(risk_table)
        story.append(Spacer(1, 0.5*cm))

    # Compliance
    compliance = data.get("compliance", {})
    if compliance.get("frameworks"):
        story.append(Paragraph(_t("executive.pdf_compliance", lang), h2_style))
        comp_rows = [[_t("executive.col_framework", lang), _t("executive.col_requirements", lang), _t("executive.col_implemented", lang), _t("executive.col_pct", lang), _t("executive.col_audit_ready", lang)]]
        for fw in compliance["frameworks"]:
            comp_rows.append([
                fw.get("framework_name", fw.get("framework_code", ""))[:25],
                str(fw.get("total_requirements", 0)),
                str(fw.get("total_requirements", 0) - len(fw.get("gaps", []))),
                f"{fw.get('overall_pct', 0)}%",
                "✓" if fw.get("is_audit_ready") else "✗",
            ])
        comp_table = Table(comp_rows, colWidths=[5*cm, 2.5*cm, 3*cm, 4*cm, 3*cm])
        comp_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ORANGE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(comp_table)

    # Footer
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(color=LIGHT_GRAY, thickness=1))
    story.append(Paragraph(
        _t("executive.pdf_footer", lang, date=data.get('report_date', '')[:10]),
        small_style
    ))

    doc.build(story)
    return buffer.getvalue()
