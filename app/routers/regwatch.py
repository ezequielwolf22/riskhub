"""Modulo de Vigilancia Normativa Automatica (regwatch).

Endpoints del cliente (`/api/regwatch/...`) — minimalistas, "set it and forget it":
 - GET/PUT settings (el toggle + opciones avanzadas)
 - POST enable / disable (activacion de una frase, §5.1)
 - GET inbox + acciones (review / snooze / dismiss)
 - GET history, GET watched-frameworks, GET status, GET history.pdf (evidencia)

Endpoints internos (`/api/regwatch/admin/...`) — solo equipo RiskHub (superadmin):
 gestion de fuentes, cola de validacion, publicacion de change_packs, health.

Spec: RISKHUB_REGULATORY_WATCH_MODULE_SPEC.md
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NormativeSource, User
from app.security import get_current_user, require_admin, require_superadmin
from app.services import regwatch_service as svc
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.regwatch")

router = APIRouter(prefix="/api/regwatch", tags=["regwatch"])


def _org_id(user: User) -> int:
    if not user.organization_id:
        raise HTTPException(400, "Usuario sin organizacion asignada")
    return user.organization_id


# ---------- Settings + toggle ----------

@router.get("/settings")
def get_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return svc.settings_dict(db, _org_id(current_user))


class SettingsUpdate(BaseModel):
    notification_email: Optional[str] = None
    digest_frequency: Optional[str] = None
    auto_apply_to_clones: Optional[bool] = None
    muted_frameworks: Optional[list[str]] = None


@router.put("/settings")
def put_settings(body: SettingsUpdate, db: Session = Depends(get_db),
                 current_user: User = Depends(require_admin)):
    org_id = _org_id(current_user)
    result = svc.update_settings(db, org_id, body.model_dump(exclude_none=True))
    log_action(db, current_user.id, "update", "regwatch_settings", str(org_id),
               body.model_dump(exclude_none=True), organization_id=org_id)
    db.commit()
    return result


@router.post("/enable")
def enable(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Activa la vigilancia con un solo clic (§5.1, criterio 1)."""
    org_id = _org_id(current_user)
    result = svc.enable(db, org_id, current_user)
    log_action(db, current_user.id, "enable", "regwatch", str(org_id), result,
               organization_id=org_id)
    db.commit()
    # Spec §2.3: programa el primer barrido ~5 min despues de activar
    try:
        from app.services import scheduler as sched
        sched.schedule_first_sweep(5)
    except Exception:  # noqa: BLE001 — no bloquear la activacion
        pass
    return result


@router.post("/disable")
def disable(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    org_id = _org_id(current_user)
    result = svc.disable(db, org_id)
    log_action(db, current_user.id, "disable", "regwatch", str(org_id), result,
               organization_id=org_id)
    db.commit()
    return result


@router.get("/status")
def status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Estado para la tarjeta de Setup, sin recargar (§1.1, criterio 2)."""
    return svc.build_status(db, _org_id(current_user))


@router.get("/watched-frameworks")
def watched_frameworks(db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    """Lista derivada (solo lectura) de frameworks vigilados (§1.2, §6.1)."""
    return svc.watched_frameworks_detail(db, _org_id(current_user))


# ---------- Inbox ----------

@router.get("/inbox")
def inbox(include_resolved: bool = False, db: Session = Depends(get_db),
          current_user: User = Depends(get_current_user)):
    org_id = _org_id(current_user)
    items = svc.list_inbox(db, org_id, include_resolved=include_resolved)
    return {"items": items, "pending": svc.count_pending_inbox(db, org_id)}


@router.get("/inbox/{item_id}")
def inbox_item(item_id: int, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    d = svc.get_inbox_item(db, _org_id(current_user), item_id)
    if not d:
        raise HTTPException(404, "Item no encontrado")
    return d


class ReviewBody(BaseModel):
    decision: dict = {}


@router.post("/inbox/{item_id}/review")
def review(item_id: int, body: ReviewBody, db: Session = Depends(get_db),
           current_user: User = Depends(require_admin)):
    org_id = _org_id(current_user)
    result = svc.review_inbox_item(db, org_id, item_id, current_user, body.decision)
    log_action(db, current_user.id, "review", "regwatch_inbox", str(item_id),
               body.decision, organization_id=org_id)
    db.commit()
    return result


class SnoozeBody(BaseModel):
    days: int = 7


@router.post("/inbox/{item_id}/snooze")
def snooze(item_id: int, body: SnoozeBody = SnoozeBody(), db: Session = Depends(get_db),
           current_user: User = Depends(require_admin)):
    org_id = _org_id(current_user)
    result = svc.snooze_inbox_item(db, org_id, item_id, body.days)
    log_action(db, current_user.id, "snooze", "regwatch_inbox", str(item_id),
               {"days": body.days}, organization_id=org_id)
    db.commit()
    return result


class DismissBody(BaseModel):
    reason: str = ""


@router.post("/inbox/{item_id}/dismiss")
def dismiss(item_id: int, body: DismissBody = DismissBody(), db: Session = Depends(get_db),
            current_user: User = Depends(require_admin)):
    org_id = _org_id(current_user)
    result = svc.dismiss_inbox_item(db, org_id, item_id, body.reason)
    log_action(db, current_user.id, "dismiss", "regwatch_inbox", str(item_id),
               {"reason": body.reason}, organization_id=org_id)
    db.commit()
    return result


# ---------- Historial + evidencia PDF ----------

@router.get("/history")
def history(framework: Optional[str] = None, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)):
    return svc.list_history(db, _org_id(current_user), framework=framework)


@router.get("/history.pdf")
def history_pdf(framework: Optional[str] = None, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    """Informe firmado de actualizaciones aplicadas (§10, evidencia ante auditor)."""
    org_id = _org_id(current_user)
    rows = svc.list_history(db, org_id, framework=framework)
    pdf_bytes = _render_history_pdf(rows, framework)
    log_action(db, current_user.id, "export_pdf", "regwatch_history", str(org_id),
               {"framework": framework, "rows": len(rows)}, organization_id=org_id)
    db.commit()
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=regwatch_history.pdf"})


def _render_history_pdf(rows: list[dict], framework: Optional[str]) -> bytes:
    """Genera el PDF de historial reutilizando ReportLab (paleta del producto)."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    purple = colors.HexColor("#59008D")
    title_style = ParagraphStyle("t", parent=styles["Title"], textColor=purple, fontSize=18)
    story = [
        Paragraph("RiskHub — Vigilancia Normativa", title_style),
        Paragraph("Historial de actualizaciones aplicadas al catalogo", styles["Heading2"]),
        Paragraph(
            f"Generado: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}"
            + (f" · Framework: {framework}" if framework else ""),
            styles["Normal"],
        ),
        Spacer(1, 8 * mm),
    ]
    data = [["Fecha", "Marco", "Severidad", "Cambio"]]
    for r in rows:
        data.append([
            (r.get("applied_at") or r.get("published_at") or "")[:10],
            r.get("framework", ""),
            r.get("severity", ""),
            Paragraph(r.get("title", ""), styles["Normal"]),
        ])
    if len(data) == 1:
        data.append(["—", "—", "—", "Sin actualizaciones en el periodo."])
    table = Table(data, colWidths=[24 * mm, 38 * mm, 26 * mm, 82 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), purple),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F2FB")]),
    ]))
    story.append(table)
    doc.build(story)
    return buf.getvalue()


# ---------- FAQ usuario final (§16) ----------

@router.get("/faq")
def faq(current_user: User = Depends(get_current_user)):
    """FAQ breve para el usuario final (§16)."""
    return [
        {"q": "¿Que hace la Vigilancia Normativa?",
         "a": "RiskHub vigila los marcos normativos que ya usas y mantiene tu catalogo "
              "al dia automaticamente. Solo te avisa si necesita tu confirmacion."},
        {"q": "¿Que tengo que configurar?",
         "a": "Nada mas alla de activar el interruptor. Los frameworks vigilados se "
              "derivan solos de lo que usas en RiskHub."},
        {"q": "¿Interpreta legalmente las normas?",
         "a": "No. Detecta y propone cambios; no certifica ni sustituye a tu consultor "
              "o auditor."},
        {"q": "¿Que pasa si lo desactivo?",
         "a": "Dejas de recibir notificaciones y tus copias no se tocan. Puedes "
              "reactivarlo cuando quieras sin perder configuracion."},
        {"q": "¿Procesa datos personales de mi organizacion?",
         "a": "No. Solo analiza documentos normativos publicos mediante IA."},
    ]


# ===================================================================
#  Endpoints internos — solo equipo RiskHub (superadmin)
# ===================================================================

@router.get("/admin/sources")
def admin_list_sources(db: Session = Depends(get_db),
                       current_user: User = Depends(require_superadmin)):
    sources = db.query(NormativeSource).order_by(NormativeSource.code).all()
    return [
        {
            "id": s.id, "code": s.code, "name": s.name,
            "framework_codes": s.framework_codes, "method": s.method,
            "polling_frequency": s.polling_frequency, "is_active": s.is_active,
            "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
            "last_run_status": s.last_run_status, "last_run_error": s.last_run_error,
        }
        for s in sources
    ]


@router.get("/admin/health")
def admin_health(db: Session = Depends(get_db),
                 current_user: User = Depends(require_superadmin)):
    """Estado de cada conector, ultimo exito y errores recientes (§6.2)."""
    sources = db.query(NormativeSource).all()
    ok = sum(1 for s in sources if s.last_run_status == "ok")
    err = sum(1 for s in sources if s.last_run_status == "error")
    return {
        "total_sources": len(sources),
        "ok": ok, "error": err, "never": len(sources) - ok - err,
        "sources": [
            {"code": s.code, "status": s.last_run_status,
             "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
             "error": s.last_run_error}
            for s in sources
        ],
    }


@router.post("/admin/sources/{source_id}/run-now")
def admin_run_source(source_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(require_superadmin)):
    from app.services import regwatch_connectors as conns
    src = db.query(NormativeSource).filter(NormativeSource.id == source_id).first()
    if not src:
        raise HTTPException(404, "Fuente no encontrada")
    summary = conns.run_source(db, src)
    db.commit()
    return summary


@router.post("/admin/sweep")
def admin_sweep(db: Session = Depends(get_db),
                current_user: User = Depends(require_superadmin)):
    """Dispara un barrido completo de todas las fuentes activas."""
    return svc.run_sweep(db)


@router.get("/admin/events")
def admin_events(status: Optional[str] = None, db: Session = Depends(get_db),
                 current_user: User = Depends(require_superadmin)):
    return svc.list_events_for_review(db, status=status)


class PublishPackBody(BaseModel):
    framework_code: str
    severity: str = "substantive"
    title_es: str
    description_es: str = ""
    version_to: Optional[str] = None
    controls_added_ids: list = []
    controls_modified: list = []
    controls_removed_ids: list = []
    source_url: Optional[str] = None


@router.post("/admin/change-packs")
def admin_create_pack(body: PublishPackBody, db: Session = Depends(get_db),
                      current_user: User = Depends(require_superadmin)):
    """Crea y publica un change_pack validado a los tenants afectados (§3.3, §7)."""
    pack = svc.create_and_publish_pack(
        db,
        framework_code=body.framework_code,
        severity=body.severity,
        title_es=body.title_es,
        description_es=body.description_es,
        version_to=body.version_to,
        controls_added_ids=body.controls_added_ids,
        controls_modified=body.controls_modified,
        controls_removed_ids=body.controls_removed_ids,
        source_url=body.source_url,
    )
    log_action(db, current_user.id, "publish", "regwatch_change_pack", str(pack.id),
               {"framework": body.framework_code, "severity": body.severity})
    db.commit()
    return {"id": pack.id, "framework_code": pack.framework_code,
            "severity": pack.severity.value, "published_at": pack.published_at.isoformat()}


class ValidateEventBody(BaseModel):
    severity: Optional[str] = None


@router.post("/admin/events/{event_id}/validate")
def admin_validate_event(event_id: int, body: ValidateEventBody = ValidateEventBody(),
                         db: Session = Depends(get_db),
                         current_user: User = Depends(require_superadmin)):
    result = svc.validate_and_publish_event(db, event_id, current_user, body.severity)
    log_action(db, current_user.id, "validate", "regwatch_event", str(event_id), result)
    db.commit()
    return result
