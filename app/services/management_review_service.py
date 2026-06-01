"""Servicio de Revision por la Direccion — ISO 27001 cl. 9.3.

Auto-popula los inputs del Annexo 9.3.2 desde la BD y genera el acta PDF.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

logger = logging.getLogger("riskhub.management_review")


def _next_code(db: Session, org_id: int) -> str:
    from app.models import ManagementReview
    now = datetime.now(timezone.utc)
    count = db.query(ManagementReview).filter_by(organization_id=org_id).count()
    return f"MR-{now.year}-{count + 1:02d}"


def get_kpis(db: Session, org_id: int) -> dict:
    """Recoge KPIs del dashboard ejecutivo para incluir en la MR."""
    from app.models import Risk, RiskStatus, ControlImplementation, ControlStatus, Incident
    risks = db.query(Risk).filter_by(organization_id=org_id).all()
    controls = db.query(ControlImplementation).filter_by(organization_id=org_id).all()
    incidents = db.query(Incident).filter_by(organization_id=org_id).all()
    return {
        "total_risks": len(risks),
        "critical_risks": sum(1 for r in risks if (r.residual_level or 0) >= 7),
        "high_risks": sum(1 for r in risks if 5 <= (r.residual_level or 0) < 7),
        "accepted_risks": sum(1 for r in risks if r.status == RiskStatus.ACCEPTED),
        "controls_implemented": sum(1 for c in controls if c.status == ControlStatus.IMPLEMENTED),
        "controls_total": len(controls),
        "open_incidents": sum(1 for i in incidents if i.status.value != "closed"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_top_risks(db: Session, org_id: int, limit: int = 10) -> list:
    """Devuelve los top N riesgos residuales para incluir en la MR."""
    from app.models import Risk
    risks = (
        db.query(Risk)
        .filter_by(organization_id=org_id)
        .order_by(Risk.residual_level.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "code": r.code,
            "level": r.residual_level,
            "status": r.status.value if r.status else "identified",
            "treatment": r.treatment_option.value if r.treatment_option else None,
            "asset": r.asset.name if r.asset else "-",
            "threat": r.threat.name if r.threat else "-",
        }
        for r in risks
    ]


def prepare_monthly_review(db: Session, org_id: int):
    """Crea un borrador de Management Review con inputs auto-poblados.

    Evita duplicados en el mismo mes. Retorna la MR existente o la nueva.
    """
    from app.models import ManagementReview, NonConformity, NCStatus, AuditProgram, AuditStatus

    now = datetime.now(timezone.utc)
    # Evitar duplicado en el mismo mes
    existing = (
        db.query(ManagementReview)
        .filter(
            ManagementReview.organization_id == org_id,
            ManagementReview.status == "draft",
            ManagementReview.created_at >= datetime(now.year, now.month, 1, tzinfo=timezone.utc),
        )
        .first()
    )
    if existing:
        return existing

    kpis = get_kpis(db, org_id)
    top_risks = get_top_risks(db, org_id, limit=10)

    open_ncs = (
        db.query(NonConformity)
        .filter(
            NonConformity.organization_id == org_id,
            NonConformity.status.in_([NCStatus.OPEN, NCStatus.IN_PROGRESS]),
        )
        .count()
    )
    closed_ncs_this_month = (
        db.query(NonConformity)
        .filter(
            NonConformity.organization_id == org_id,
            NonConformity.status == NCStatus.CLOSED,
            NonConformity.updated_at >= datetime(now.year, now.month, 1, tzinfo=timezone.utc),
        )
        .count()
    )
    recent_audits = (
        db.query(AuditProgram)
        .filter(
            AuditProgram.organization_id == org_id,
            AuditProgram.status == AuditStatus.COMPLETED,
        )
        .order_by(AuditProgram.actual_end.desc())
        .limit(3)
        .all()
    )
    audit_inputs = [
        {
            "code": a.code,
            "title": a.title,
            "actual_end": a.actual_end.isoformat() if a.actual_end else None,
            "finding_count": len(a.findings) if a.findings else 0,
        }
        for a in recent_audits
    ]

    # Calcular proximo mes para la fecha de revision propuesta
    if now.month == 12:
        next_year, next_month = now.year + 1, 1
    else:
        next_year, next_month = now.year, now.month + 1

    mr = ManagementReview(
        organization_id=org_id,
        code=_next_code(db, org_id),
        review_date=datetime(next_year, next_month, 1, tzinfo=timezone.utc),
        status="draft",
        input_performance_data=kpis,
        input_risk_register=top_risks,
        input_nc_corrections={
            "open": open_ncs,
            "closed_this_month": closed_ncs_this_month,
        },
        input_audit_results=audit_inputs,
    )
    db.add(mr)
    db.commit()
    db.refresh(mr)
    logger.info("Management Review auto-preparada para org %d: %s", org_id, mr.code)
    return mr


def generate_minutes_pdf(mr) -> bytes:
    """Genera el PDF del acta de la Management Review con ReportLab."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        import io

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        PURPLE = colors.HexColor("#59008D")
        ORANGE = colors.HexColor("#D65200")

        title_style = ParagraphStyle(
            "Title", parent=styles["Heading1"], textColor=PURPLE, fontSize=16, spaceAfter=6
        )
        h2_style = ParagraphStyle(
            "H2", parent=styles["Heading2"], textColor=ORANGE, fontSize=12, spaceAfter=4
        )
        normal = styles["Normal"]

        now_str = datetime.now().strftime("%d/%m/%Y")
        review_date = mr.review_date.strftime("%d/%m/%Y") if mr.review_date else "Por determinar"

        story = [
            Paragraph("ACTA DE REVISION POR LA DIRECCION", title_style),
            Paragraph("ISO/IEC 27001:2022 — Clausula 9.3", h2_style),
            Spacer(1, 0.5*cm),
            Paragraph(f"<b>Codigo:</b> {mr.code or '-'}", normal),
            Paragraph(f"<b>Fecha de revision:</b> {review_date}", normal),
            Paragraph(f"<b>Estado:</b> {(mr.status or 'draft').upper()}", normal),
            Paragraph(f"<b>Documento generado:</b> {now_str}", normal),
            Spacer(1, 0.5*cm),
        ]

        # Entradas
        story.append(Paragraph("ENTRADAS (ISO 9.3.2)", h2_style))
        if mr.input_performance_data:
            kpis = mr.input_performance_data
            data = [["KPI", "Valor"]]
            for k, v in kpis.items():
                if k != "generated_at":
                    data.append([k.replace("_", " ").title(), str(v)])
            t = Table(data, colWidths=[9*cm, 7*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]))
            story += [t, Spacer(1, 0.3*cm)]

        if mr.input_nc_corrections:
            nc = mr.input_nc_corrections
            story.append(Paragraph(
                f"No conformidades abiertas: {nc.get('open', 0)} | "
                f"Cerradas este mes: {nc.get('closed_this_month', 0)}", normal
            ))
            story.append(Spacer(1, 0.3*cm))

        # Salidas
        story.append(Paragraph("SALIDAS (ISO 9.3.3)", h2_style))
        if mr.output_decisions:
            for d in (mr.output_decisions or []):
                if isinstance(d, dict):
                    story.append(Paragraph(f"- {d.get('decision','')}", normal))
                else:
                    story.append(Paragraph(f"- {d}", normal))
        else:
            story.append(Paragraph("(Pendiente de completar por la Direccion)", normal))

        story.append(Spacer(1, 1*cm))
        story.append(Paragraph(
            "Firma del Responsable: ____________________________", normal
        ))

        doc.build(story)
        return buf.getvalue()
    except Exception as exc:
        logger.exception("Error generando PDF Management Review: %s", exc)
        return b""
