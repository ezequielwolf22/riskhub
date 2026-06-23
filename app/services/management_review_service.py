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
    """Recoge KPIs del SGSI para incluir en la MR (ISO 9.3.2.e)."""
    from app.models import Risk, RiskStatus, ControlImplementation, ControlStatus, Incident, Policy, PolicyStatus
    now = datetime.now(timezone.utc)

    risks = db.query(Risk).filter_by(organization_id=org_id).all()
    controls = db.query(ControlImplementation).filter_by(organization_id=org_id).all()
    incidents = db.query(Incident).filter_by(organization_id=org_id).all()

    maturity_values = [c.maturity for c in controls if c.maturity is not None]
    avg_maturity = round(sum(maturity_values) / len(maturity_values), 1) if maturity_values else 0

    closed_incidents_month = sum(
        1 for i in incidents
        if i.status.value == "closed" and i.updated_at
        and i.updated_at.year == now.year and i.updated_at.month == now.month
    )

    overdue_policies = db.query(Policy).filter(
        Policy.organization_id == org_id,
        Policy.review_date < now,
        Policy.status.in_([PolicyStatus.APPROVED, PolicyStatus.PUBLISHED]),
    ).count()

    return {
        "total_risks": len(risks),
        "critical_risks": sum(1 for r in risks if (r.residual_level or 0) >= 7),
        "high_risks": sum(1 for r in risks if 5 <= (r.residual_level or 0) < 7),
        "accepted_risks": sum(1 for r in risks if r.status == RiskStatus.ACCEPTED),
        "controls_implemented": sum(1 for c in controls if c.status == ControlStatus.IMPLEMENTED),
        "controls_total": len(controls),
        "avg_control_maturity": avg_maturity,
        "open_incidents": sum(1 for i in incidents if i.status.value != "closed"),
        "closed_incidents_month": closed_incidents_month,
        "policies_overdue_review": overdue_policies,
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
    """Crea un borrador de Management Review con inputs auto-poblados (ISO 9.3.2).

    Evita duplicados en el mismo mes. Retorna la MR existente o la nueva.
    """
    from app.models import ManagementReview, NonConformity, NCStatus, AuditProgram, AuditStatus, ChangeRequest

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

    # ISO 9.3.2.a — seguimiento de acciones de revisiones anteriores
    previous_mr = (
        db.query(ManagementReview)
        .filter(
            ManagementReview.organization_id == org_id,
            ManagementReview.status == "approved",
        )
        .order_by(ManagementReview.approved_at.desc())
        .first()
    )
    previous_actions = []
    if previous_mr and previous_mr.output_decisions:
        previous_actions = [
            {
                "decision": d if isinstance(d, str) else d.get("decision", ""),
                "mr_code": previous_mr.code,
                "followup": "pendiente",
            }
            for d in (previous_mr.output_decisions or [])
            if d
        ]

    # ISO 9.3.2.b — cambios en factores externos e internos
    recent_changes = (
        db.query(ChangeRequest)
        .filter(
            ChangeRequest.organization_id == org_id,
            ChangeRequest.created_at >= datetime(now.year, now.month, 1, tzinfo=timezone.utc),
        )
        .order_by(ChangeRequest.created_at.desc())
        .limit(5)
        .all()
    )
    changes_text = None
    if recent_changes:
        lines = [f"[{c.code}] {c.title} — {c.status}" for c in recent_changes]
        changes_text = "\n".join(lines)

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
        input_previous_actions=previous_actions or None,
        input_changes_context=changes_text,
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
        small = ParagraphStyle("small", parent=normal, fontSize=9, leading=12)

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
        ]

        # Asistentes
        attendees = mr.attendees or []
        if attendees:
            names = ", ".join(
                a.get("name", a) if isinstance(a, dict) else str(a)
                for a in attendees
            )
            story.append(Paragraph(f"<b>Asistentes:</b> {names}", normal))
        story.append(Spacer(1, 0.5*cm))

        # Entradas ISO 9.3.2
        story.append(Paragraph("ENTRADAS (ISO 9.3.2)", h2_style))

        # 9.3.2.a — Acciones previas
        if mr.input_previous_actions:
            story.append(Paragraph("<b>a) Seguimiento acciones anteriores:</b>", small))
            for item in mr.input_previous_actions:
                dec = item.get("decision", "") if isinstance(item, dict) else str(item)
                ref = item.get("mr_code", "") if isinstance(item, dict) else ""
                story.append(Paragraph(f"  - [{ref}] {dec}", small))
            story.append(Spacer(1, 0.2*cm))

        # 9.3.2.b — Cambios en el contexto
        if mr.input_changes_context:
            story.append(Paragraph("<b>b) Cambios en contexto del SGSI:</b>", small))
            for line in mr.input_changes_context.split("\n"):
                if line.strip():
                    story.append(Paragraph(f"  {line}", small))
            story.append(Spacer(1, 0.2*cm))

        # 9.3.2.e — Desempeno del SGSI (KPIs)
        if mr.input_performance_data:
            story.append(Paragraph("<b>e) Desempeno e indicadores del SGSI:</b>", small))
            kpis = mr.input_performance_data

            KPI_LABELS = {
                "total_risks": "Riesgos totales",
                "critical_risks": "Riesgos criticos (>= 7)",
                "high_risks": "Riesgos altos (5-6)",
                "accepted_risks": "Riesgos aceptados",
                "controls_implemented": "Controles implementados",
                "controls_total": "Controles totales",
                "avg_control_maturity": "Madurez media controles",
                "open_incidents": "Incidentes abiertos",
                "closed_incidents_month": "Incidentes cerrados este mes",
                "policies_overdue_review": "Politicas con revision vencida",
            }
            data = [["Indicador", "Valor"]]
            for k, v in kpis.items():
                if k != "generated_at":
                    label = KPI_LABELS.get(k, k.replace("_", " ").title())
                    data.append([label, str(v)])
            t = Table(data, colWidths=[11*cm, 6*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]))
            story += [t, Spacer(1, 0.3*cm)]

        # Top riesgos residuales
        if mr.input_risk_register:
            story.append(Paragraph("<b>Registro de riesgos — Top residuales:</b>", small))
            risk_data = [["Codigo", "Activo", "Amenaza", "Nivel", "Estado"]]
            for r in (mr.input_risk_register or []):
                risk_data.append([
                    r.get("code", "-"),
                    (r.get("asset", "") or "")[:25],
                    (r.get("threat", "") or "")[:25],
                    str(r.get("level", "-")),
                    r.get("status", "-"),
                ])
            rt = Table(risk_data, colWidths=[2.5*cm, 4.5*cm, 4.5*cm, 2*cm, 3.5*cm])
            rt.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("PADDING", (0, 0), (-1, -1), 3),
            ]))
            story += [rt, Spacer(1, 0.3*cm)]

        # No conformidades
        if mr.input_nc_corrections:
            nc = mr.input_nc_corrections
            story.append(Paragraph(
                f"<b>No conformidades:</b> Abiertas: {nc.get('open', 0)} | "
                f"Cerradas este mes: {nc.get('closed_this_month', 0)}", small
            ))
            story.append(Spacer(1, 0.2*cm))

        # Resultados de auditorias
        if mr.input_audit_results:
            story.append(Paragraph("<b>Resultados de auditorias:</b>", small))
            for a in mr.input_audit_results:
                story.append(Paragraph(
                    f"  - [{a.get('code', '')}] {a.get('title', '')} — {a.get('finding_count', 0)} hallazgos", small
                ))
            story.append(Spacer(1, 0.3*cm))

        # Salidas ISO 9.3.3
        story.append(Paragraph("SALIDAS (ISO 9.3.3)", h2_style))
        if mr.output_decisions:
            story.append(Paragraph("<b>Decisiones y acciones formales adoptadas:</b>", small))
            for d in (mr.output_decisions or []):
                text = d.get("decision", "") if isinstance(d, dict) else str(d)
                story.append(Paragraph(f"  - {text}", small))
        else:
            story.append(Paragraph("(Pendiente de completar por la Direccion)", small))

        if mr.output_resources:
            story.append(Spacer(1, 0.2*cm))
            story.append(Paragraph(f"<b>Recursos aprobados:</b> {mr.output_resources}", small))

        if mr.output_objectives:
            story.append(Spacer(1, 0.2*cm))
            story.append(Paragraph("<b>Objetivos de mejora:</b>", small))
            for obj in (mr.output_objectives or []):
                story.append(Paragraph(f"  - {obj}", small))

        story.append(Spacer(1, 1*cm))
        story.append(Paragraph("Firma del Responsable: ____________________________", normal))

        doc.build(story)
        return buf.getvalue()
    except Exception as exc:
        logger.exception("Error generando PDF Management Review: %s", exc)
        return b""
