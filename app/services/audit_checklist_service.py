"""Servicio de checklist de auditoria interna — ISO 27001 cl. 9.2.

Genera preguntas automaticamente desde la SoA activa.
Usa Claude para generar preguntas adicionales especificas por control.
"""
import logging

from sqlalchemy.orm import Session

logger = logging.getLogger("riskhub.audit_checklist")

_BASE_QUESTIONS = [
    "Existe procedimiento documentado para este control?",
    "Se aplica de forma consistente en toda la organizacion?",
    "Existen evidencias actualizadas de la implementacion?",
]


def _get_api_key(db: Session, org_id: int) -> str | None:
    """Resuelve la API key activa para la org (igual que isms_analysis_service)."""
    try:
        from app.models import AiConfig
        from app.security import decrypt_secret
        cfg = db.query(AiConfig).filter_by(organization_id=org_id).first()
        if cfg and cfg.api_key_encrypted:
            return decrypt_secret(cfg.api_key_encrypted)
    except Exception:
        pass
    try:
        from app.config import settings
        return settings.anthropic_api_key or None
    except Exception:
        return None


def _get_model(db: Session, org_id: int) -> str:
    try:
        from app.models import AiConfig
        cfg = db.query(AiConfig).filter_by(organization_id=org_id).first()
        if cfg and cfg.model:
            return cfg.model
    except Exception:
        pass
    return "claude-haiku-4-5"


def _generate_ai_audit_question(api_key: str, model: str,
                                 control_name: str, description: str | None) -> str | None:
    """Claude genera una pregunta de auditoria especifica para el control."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    f"Control ISO 27002: '{control_name}'. "
                    f"Descripcion: {(description or '')[:200]}. "
                    f"Genera UNA sola pregunta de auditoria interna especifica y tecnica "
                    f"que un auditor haria para verificar la implementacion real. "
                    f"Devuelve solo la pregunta, sin explicaciones ni numeracion."
                ),
            }],
        )
        q = msg.content[0].text.strip()[:300]
        # Asegurarse de que termina en "?"
        if q and not q.endswith("?"):
            q += "?"
        return q
    except Exception as exc:
        logger.debug("Error generando pregunta IA: %s", exc)
        return None


def generate_checklist_from_soa(db: Session, audit_id: int, org_id: int) -> int:
    """Genera AuditChecklist items desde controles implementados en SoA.

    Returns: numero de items creados
    """
    from app.models import AuditChecklist, ControlImplementation, ControlStatus

    # Solo controles implementados o parciales
    controls = (
        db.query(ControlImplementation)
        .filter(
            ControlImplementation.organization_id == org_id,
            ControlImplementation.status.in_([ControlStatus.IMPLEMENTED, ControlStatus.PARTIAL]),
        )
        .limit(30)
        .all()
    )

    if not controls:
        logger.info("Audit %d: sin controles implementados para generar checklist", audit_id)
        return 0

    api_key = _get_api_key(db, org_id)
    model = _get_model(db, org_id)
    created = 0

    for ctrl in controls:
        control_name = ctrl.name
        iso_clause = ctrl.control.code if ctrl.control else None
        control_desc = ctrl.control.description if ctrl.control else None

        # Preguntas base (sin IA) — siempre se crean
        for q_text in _BASE_QUESTIONS:
            q_full = f"[{control_name}] {q_text}"
            item = AuditChecklist(
                organization_id=org_id,
                audit_id=audit_id,
                control_id=ctrl.control_id,
                iso_clause=iso_clause,
                question=q_full,
                expected_evidence="Documentacion, registros o capturas de pantalla",
                response="pending",
            )
            db.add(item)
            created += 1

        # Pregunta adicional con IA si hay api_key
        if api_key:
            ai_q = _generate_ai_audit_question(api_key, model, control_name, control_desc)
            if ai_q:
                db.add(AuditChecklist(
                    organization_id=org_id,
                    audit_id=audit_id,
                    control_id=ctrl.control_id,
                    iso_clause=iso_clause,
                    question=ai_q,
                    expected_evidence="Evidencia especifica segun el control",
                    response="pending",
                ))
                created += 1

    try:
        db.commit()
        logger.info("Audit %d: %d items de checklist creados", audit_id, created)
    except Exception as exc:
        logger.exception("Error creando checklist audit %d: %s", audit_id, exc)
        db.rollback()
        return 0

    return created


def generate_audit_report_pdf(audit, checklist_items: list) -> bytes:
    """Genera PDF del informe de auditoria interna."""
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
        normal = styles["Normal"]
        h1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=PURPLE, fontSize=14)
        h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=ORANGE, fontSize=11)

        counts = {"conformant": 0, "minor_nc": 0, "major_nc": 0, "na": 0, "pending": 0}
        for item in checklist_items:
            counts[item.response] = counts.get(item.response, 0) + 1

        total = len(checklist_items)
        conformant = counts.get("conformant", 0)
        nc_total = counts.get("minor_nc", 0) + counts.get("major_nc", 0)

        from datetime import datetime
        now_str = datetime.now().strftime("%d/%m/%Y")
        actual_end = (audit.actual_end.strftime("%d/%m/%Y") if audit.actual_end else "En curso")

        story = [
            Paragraph("INFORME DE AUDITORIA INTERNA", h1),
            Paragraph("ISO/IEC 27001:2022 — Clausula 9.2", h2),
            Spacer(1, 0.4*cm),
            Paragraph(f"<b>Auditoria:</b> {audit.code} — {audit.title}", normal),
            Paragraph(f"<b>Tipo:</b> {audit.audit_type.value if audit.audit_type else 'Internal'}", normal),
            Paragraph(f"<b>Auditor lider:</b> {audit.auditor_lead or '-'}", normal),
            Paragraph(f"<b>Fecha fin:</b> {actual_end}", normal),
            Paragraph(f"<b>Informe generado:</b> {now_str}", normal),
            Spacer(1, 0.5*cm),
            Paragraph("RESUMEN EJECUTIVO", h2),
        ]

        pct = round(conformant / max(1, total - counts.get("na", 0)) * 100, 1)
        story.append(Paragraph(
            f"La auditoria evaluo {total} items de checklist. "
            f"Resultado: {conformant} conformes ({pct}%), {nc_total} no conformidades "
            f"({counts.get('minor_nc',0)} menores, {counts.get('major_nc',0)} mayores).",
            normal,
        ))
        story.append(Spacer(1, 0.5*cm))

        # Tabla de resultados
        story.append(Paragraph("RESULTADO POR ITEM", h2))
        data = [["Clausula", "Pregunta", "Resultado", "Notas"]]
        for item in checklist_items[:50]:
            status_map = {
                "conformant": "CONFORME",
                "minor_nc": "NC MENOR",
                "major_nc": "NC MAYOR",
                "na": "N/A",
                "pending": "PENDIENTE",
            }
            data.append([
                item.iso_clause or "-",
                (item.question or "")[:60],
                status_map.get(item.response, item.response),
                (item.auditor_notes or "")[:40],
            ])

        col_widths = [2.5*cm, 8*cm, 2.5*cm, 4*cm]
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("WORDWRAP", (1, 0), (1, -1), True),
        ]))
        story += [t, Spacer(1, 0.5*cm)]

        if audit.conclusion:
            story.append(Paragraph("CONCLUSION", h2))
            story.append(Paragraph(audit.conclusion, normal))

        doc.build(story)
        return buf.getvalue()
    except Exception as exc:
        logger.exception("Error generando PDF auditoria: %s", exc)
        return b""
