"""Servicio NIS2 — notificaciones a autoridades competentes (Art. 23).

Tres fases obligatorias:
  early_warning  : <= 24h desde deteccion
  initial_report : <= 72h
  final_report   : <= 30 dias
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.i18n import t as _t

logger = logging.getLogger("riskhub.nis2")

NIS2_DEADLINES = {
    "early_warning": timedelta(hours=24),
    "initial_report": timedelta(hours=72),
    "final_report": timedelta(days=30),
}

NIS2_STAGE_LABELS = {
    "early_warning": "Alerta temprana (Art. 23.1a)",
    "initial_report": "Notificacion inicial (Art. 23.1b)",
    "final_report": "Informe final (Art. 23.1c)",
}


def nis2_stage_label(stage: str, lang: str = "es") -> str:
    """Etiqueta traducida de la fase NIS2; cae al literal si la clave no existe."""
    label = _t(f"nis2.stage_{stage}", lang)
    if label == f"nis2.stage_{stage}":
        return NIS2_STAGE_LABELS.get(stage, stage)
    return label


def create_nis2_notification_chain(db: Session, incident_id: int, org_id: int) -> list:
    """Crea los 3 registros de notificacion NIS2 con sus deadlines.

    Evita duplicados. Retorna lista de notificaciones creadas.
    """
    from app.models import NIS2Notification, Incident

    incident = db.get(Incident, incident_id)
    if not incident:
        logger.warning("NIS2: incidente %d no encontrado", incident_id)
        return []

    detected = incident.detected_at or incident.created_at
    if detected and not detected.tzinfo:
        detected = detected.replace(tzinfo=timezone.utc)

    created = []
    for stage, delta in NIS2_DEADLINES.items():
        existing = (
            db.query(NIS2Notification)
            .filter_by(incident_id=incident_id, stage=stage)
            .first()
        )
        if existing:
            continue
        notif = NIS2Notification(
            organization_id=org_id,
            incident_id=incident_id,
            stage=stage,
            deadline_at=detected + delta,
            status="pending",
            recipient_authority="INCIBE-CERT",
        )
        db.add(notif)
        created.append(notif)

    if created:
        db.commit()
        logger.info(
            "NIS2: %d notificaciones creadas para incidente %d", len(created), incident_id
        )
    return created


def recalculate_nis2_deadlines(db: Session, incident_id: int) -> None:
    """Recalcula deadlines de notificaciones NIS2 pendientes cuando cambia detected_at.

    Solo actualiza notificaciones en estado 'pending' (las enviadas no se tocan).
    """
    from app.models import NIS2Notification, Incident

    inc = db.get(Incident, incident_id)
    if not inc:
        return

    notifs = db.query(NIS2Notification).filter_by(
        incident_id=incident_id, status="pending"
    ).all()
    if not notifs:
        return

    detected = inc.detected_at or inc.created_at
    if detected and not detected.tzinfo:
        detected = detected.replace(tzinfo=timezone.utc)

    for notif in notifs:
        delta = NIS2_DEADLINES.get(notif.stage)
        if delta:
            notif.deadline_at = detected + delta

    db.commit()
    logger.info(
        "NIS2: recalculados %d deadlines para incidente %d", len(notifs), incident_id
    )


def check_nis2_deadlines(db: Session) -> None:
    """Job periodico: detecta notificaciones proximas a vencer y marca overdue."""
    from app.models import NIS2Notification, EmailSettings, User, UserRole

    now = datetime.now(timezone.utc)
    warning_threshold = now + timedelta(hours=6)

    urgent = (
        db.query(NIS2Notification)
        .filter(
            NIS2Notification.status == "pending",
            NIS2Notification.deadline_at <= warning_threshold,
        )
        .all()
    )

    for notif in urgent:
        hours_left = (notif.deadline_at - now).total_seconds() / 3600

        # Notificar al admin de la org
        try:
            from app.models import EmailSettings
            from app.services import email_service
            cfg = db.query(EmailSettings).filter_by(
                organization_id=notif.organization_id
            ).first()
            if cfg and cfg.smtp_host:
                admin = (
                    db.query(User)
                    .filter_by(
                        organization_id=notif.organization_id,
                        role=UserRole.ADMIN,
                        is_active=True,
                    )
                    .first()
                )
                if admin and admin.email:
                    _send_nis2_deadline_alert(email_service, cfg, admin.email, notif, hours_left)
        except Exception as exc:
            logger.debug("NIS2 email error: %s", exc)

        # Si ya vencio → marcar overdue
        if notif.deadline_at < now:
            notif.status = "overdue"
            logger.warning(
                "NIS2: notificacion %d (%s) OVERDUE para incidente %d",
                notif.id, notif.stage, notif.incident_id,
            )

    if urgent:
        try:
            db.commit()
        except Exception:
            db.rollback()


def _send_nis2_deadline_alert(email_service, cfg, recipient: str, notif, hours_left: float) -> None:
    """Envia email de alerta de deadline NIS2."""
    stage_label = NIS2_STAGE_LABELS.get(notif.stage, notif.stage)
    urgency = "URGENTE" if hours_left < 2 else "AVISO"
    subject = f"[RiskHub] {urgency}: {stage_label} NIS2 vence en {hours_left:.0f}h"
    body = (
        f"<p><strong>AVISO NIS2 — Directiva (UE) 2022/2555 Art. 23</strong></p>"
        f"<p>La notificacion <strong>{stage_label}</strong> correspondiente al incidente "
        f"<strong>#{notif.incident_id}</strong> vence en <strong>{hours_left:.0f} horas</strong>.</p>"
        f"<p>Autoridad receptora: <strong>{notif.recipient_authority}</strong></p>"
        f"<p>Accede a RiskHub &rarr; NIS2 Dashboard para completar y enviar la notificacion.</p>"
        f"<p style='color:#a83232;font-weight:700;'>El incumplimiento del plazo puede "
        f"derivar en sanciones por parte del organismo supervisor.</p>"
    )
    try:
        email_service.send_email(cfg, recipient, subject, body)
    except Exception as exc:
        logger.debug("Error enviando alerta NIS2: %s", exc)


def generate_nis2_pdf(notif) -> bytes:
    """Genera PDF de la notificacion NIS2 en formato compatible ENISA."""
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

        stage_label = NIS2_STAGE_LABELS.get(notif.stage, notif.stage)
        deadline_str = notif.deadline_at.strftime("%d/%m/%Y %H:%M") if notif.deadline_at else "-"
        submitted_str = notif.submitted_at.strftime("%d/%m/%Y %H:%M") if notif.submitted_at else "Pendiente"

        h1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=PURPLE, fontSize=14)
        h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=ORANGE, fontSize=11)

        story = [
            Paragraph("NOTIFICACION DE INCIDENTE DE SEGURIDAD", h1),
            Paragraph(f"NIS2 Art. 23 — {stage_label}", h2),
            Spacer(1, 0.4*cm),
        ]

        meta = [
            ["Referencia notificacion", notif.notification_ref or "Pendiente asignacion"],
            ["Autoridad receptora", notif.recipient_authority or "INCIBE-CERT"],
            ["Fase", stage_label],
            ["Plazo limite", deadline_str],
            ["Fecha de envio", submitted_str],
            ["Estado", notif.status.upper()],
        ]
        t = Table(meta, colWidths=[7*cm, 9*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F5F5")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story += [t, Spacer(1, 0.5*cm)]

        content = notif.content_json or {}
        if content:
            story.append(Paragraph("CONTENIDO DE LA NOTIFICACION", h2))
            for key, val in content.items():
                if val:
                    story.append(Paragraph(f"<b>{key.replace('_', ' ').title()}:</b> {val}", normal))
                    story.append(Spacer(1, 0.2*cm))

        story += [
            Spacer(1, 1*cm),
            Paragraph("Responsable de la notificacion: ____________________________", normal),
            Spacer(1, 0.3*cm),
            Paragraph("Firma y fecha: ____________________________", normal),
        ]

        doc.build(story)
        return buf.getvalue()
    except Exception as exc:
        logger.exception("Error generando PDF NIS2: %s", exc)
        return b""
