"""Bandeja de revision — agrega items pendientes de decision humana.

Fuentes: riesgos auto-generados, incidentes criticos/altos abiertos,
notificaciones NIS2 con plazo corriendo, controles degradados o con
revision vencida, tareas vencidas y no conformidades abiertas sin
accion correctiva. Solo lectura salvo el descarte explicito de items.
"""
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models import (
    ControlImplementation, ControlStatus, Incident, IncidentSeverity,
    IncidentStatus, NCStatus, NIS2Notification, NonConformity, Risk,
    RiskStatus, TaskPriority, TaskStatus, TreatmentTask, User,
)
from app.security import (
    check_org_access, filter_by_org, get_current_user, require_analyst,
)
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.inbox")

router = APIRouter(prefix="/api/inbox", tags=["inbox"])

# Orden de severidad para el sort (mayor = mas urgente)
_SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "info": 0}

# Tipos validos de item y formato de clave compuesta "tipo-id"
_ITEM_KEY_RE = re.compile(r"^(risk|incident|nis2|control|task|nonconformity)-(\d+)$")

_ITEM_MODEL = {
    "risk": Risk,
    "incident": Incident,
    "nis2": NIS2Notification,
    "control": ControlImplementation,
    "task": TreatmentTask,
    "nonconformity": NonConformity,
}


class InboxDismissal(Base):
    """Item de la bandeja descartado por un usuario de la organizacion."""
    __tablename__ = "inbox_dismissals"
    __table_args__ = (
        UniqueConstraint("organization_id", "item_key", name="uq_inbox_dismiss_org_item"),
    )
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    item_key = Column(String(64), nullable=False, index=True)   # ej. "risk-12"
    dismissed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def _aware(dt):
    """Normaliza datetimes naive de SQLite a UTC aware."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(dt):
    return dt.isoformat() if dt else None


def _item(key, type_, severity, title, description, created_at, link):
    return {
        "id": key,
        "type": type_,
        "severity": severity,
        "title": title,
        "description": description or "",
        "created_at": _iso(created_at),
        "link": link,
        "actions": ["review", "dismiss"],
    }


def _risk_severity(level):
    # Escala ISO 27005 Annex E.2: 0..8
    lvl = level or 0
    if lvl >= 7:
        return "critical"
    if lvl >= 5:
        return "high"
    if lvl >= 3:
        return "medium"
    return "info"


def _collect_auto_risks(db, user):
    """Riesgos auto-generados (ai_generated=True) aun sin decision humana.

    Los hooks de CVE/OSINT/proveedores crean riesgos con ai_generated=True
    en estado IDENTIFIED/ASSESSED (verificado en routers/suppliers.py,
    routers/ai.py y services/asset_risk_analysis_service.py).
    """
    q = filter_by_org(db.query(Risk), Risk, user).filter(
        Risk.ai_generated.is_(True),
        Risk.status.in_([RiskStatus.IDENTIFIED, RiskStatus.ASSESSED]),
    )
    items = []
    for r in q.all():
        asset_name = r.asset.name if r.asset else ""
        items.append(_item(
            f"risk-{r.id}", "risk",
            _risk_severity(r.residual_level),
            f"{r.code} — Riesgo auto-generado" + (f" sobre {asset_name}" if asset_name else ""),
            r.ai_rationale or r.description,
            _aware(r.created_at),
            f"#/risks?id={r.id}",
        ))
    return items


def _collect_open_incidents(db, user):
    """Incidentes abiertos P1/P2 (incluye los auto-creados por OSINT)."""
    q = filter_by_org(db.query(Incident), Incident, user).filter(
        Incident.severity.in_([IncidentSeverity.P1, IncidentSeverity.P2]),
        Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.INVESTIGATING]),
    )
    items = []
    for inc in q.all():
        sev = "critical" if inc.severity == IncidentSeverity.P1 else "high"
        items.append(_item(
            f"incident-{inc.id}", "incident", sev,
            f"{inc.code} — {inc.title}",
            inc.description,
            _aware(inc.created_at),
            f"#/incidents?id={inc.id}",
        ))
    return items


def _collect_nis2_notifications(db, user, now):
    """Notificaciones NIS2 pendientes o vencidas (Art. 23: 24h/72h/1 mes)."""
    from app.services.nis2_service import NIS2_STAGE_LABELS

    q = filter_by_org(db.query(NIS2Notification), NIS2Notification, user).filter(
        NIS2Notification.status.in_(["pending", "overdue"]),
        NIS2Notification.submitted_at.is_(None),
    )
    items = []
    for n in q.all():
        deadline = _aware(n.deadline_at)
        hours_left = (deadline - now).total_seconds() / 3600 if deadline else None
        if n.status == "overdue" or (hours_left is not None and hours_left < 12):
            sev = "critical"
        elif hours_left is not None and hours_left < 48:
            sev = "high"
        else:
            sev = "medium"
        stage_label = NIS2_STAGE_LABELS.get(n.stage, n.stage or "")
        inc_code = n.incident.code if n.incident else f"incidente {n.incident_id}"
        if hours_left is None:
            desc = "Sin plazo definido."
        elif hours_left < 0:
            desc = f"Plazo vencido hace {abs(round(hours_left, 1))} h."
        else:
            desc = f"Quedan {round(hours_left, 1)} h de plazo."
        items.append(_item(
            f"nis2-{n.id}", "nis2", sev,
            f"Notificacion NIS2 ({stage_label}) — {inc_code}",
            desc + " Autoridad: " + (n.recipient_authority or "INCIBE-CERT"),
            _aware(n.created_at),
            f"#/incidents?id={n.incident_id}",
        ))
    return items


def _collect_degraded_controls(db, user, now):
    """Controles degradados por el scheduler (PARTIAL) o con revision vencida.

    El scheduler (_run_control_degradation) degrada a PARTIAL los controles
    IMPLEMENTED con next_review vencida; aqui se listan ambos casos.
    """
    naive_now = now.replace(tzinfo=None)
    q = filter_by_org(db.query(ControlImplementation), ControlImplementation, user).filter(
        ControlImplementation.next_review.isnot(None),
        ControlImplementation.next_review < naive_now,
        ControlImplementation.status.in_([ControlStatus.IMPLEMENTED, ControlStatus.PARTIAL]),
    )
    items = []
    for impl in q.all():
        degraded = impl.status == ControlStatus.PARTIAL
        ctrl_code = impl.control.code if impl.control else ""
        items.append(_item(
            f"control-{impl.id}", "control",
            "high" if degraded else "medium",
            f"Control {ctrl_code} — {impl.name}",
            ("Control degradado automaticamente a PARTIAL por revision vencida."
             if degraded else "Revision del control vencida."),
            _aware(impl.next_review),
            f"#/controls?id={impl.id}",
        ))
    return items


def _collect_overdue_tasks(db, user, now):
    """Tareas de tratamiento con fecha limite vencida y no completadas."""
    naive_now = now.replace(tzinfo=None)
    q = filter_by_org(db.query(TreatmentTask), TreatmentTask, user).filter(
        TreatmentTask.due_date.isnot(None),
        TreatmentTask.due_date < naive_now,
        TreatmentTask.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]),
    )
    sev_map = {
        TaskPriority.CRITICAL: "critical",
        TaskPriority.HIGH: "high",
        TaskPriority.MEDIUM: "medium",
        TaskPriority.LOW: "info",
    }
    items = []
    for t in q.all():
        due = _aware(t.due_date)
        items.append(_item(
            f"task-{t.id}", "task",
            sev_map.get(t.priority, "medium"),
            f"{t.code} — Tarea vencida: {t.title}",
            f"Vencia el {due.strftime('%d/%m/%Y')}." if due else "",
            _aware(t.created_at),
            f"#/tasks?id={t.id}",
        ))
    return items


def _collect_open_ncs(db, user):
    """No conformidades abiertas sin accion correctiva definida."""
    q = filter_by_org(db.query(NonConformity), NonConformity, user).filter(
        NonConformity.status == NCStatus.OPEN,
        (NonConformity.corrective_action.is_(None)) | (NonConformity.corrective_action == ""),
    )
    sev_map = {"major": "high", "minor": "medium", "observation": "info"}
    items = []
    for nc in q.all():
        sev_val = nc.severity.value if nc.severity else "minor"
        items.append(_item(
            f"nonconformity-{nc.id}", "nonconformity",
            sev_map.get(sev_val, "medium"),
            f"{nc.code} — {nc.title}",
            "No conformidad abierta sin accion correctiva definida.",
            _aware(nc.created_at),
            f"#/nonconformities?id={nc.id}",
        ))
    return items


@router.get("")
def get_inbox(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista unificada de items pendientes de revision humana.

    Solo lectura: no muta nada. Viewer recibe la misma lista pero el
    descarte (POST dismiss) exige rol analyst como minimo.
    """
    now = datetime.now(timezone.utc)

    items = []
    items += _collect_auto_risks(db, current_user)
    items += _collect_open_incidents(db, current_user)
    items += _collect_nis2_notifications(db, current_user, now)
    items += _collect_degraded_controls(db, current_user, now)
    items += _collect_overdue_tasks(db, current_user, now)
    items += _collect_open_ncs(db, current_user)

    # Excluir items descartados por la organizacion
    dismissed = {
        d.item_key
        for d in filter_by_org(db.query(InboxDismissal), InboxDismissal, current_user).all()
    }
    items = [i for i in items if i["id"] not in dismissed]

    # Orden: severidad desc, luego fecha desc
    items.sort(
        key=lambda i: (_SEVERITY_RANK.get(i["severity"], 0), i["created_at"] or ""),
        reverse=True,
    )

    counts = {"critical": 0, "high": 0, "medium": 0, "info": 0}
    for i in items:
        counts[i["severity"]] = counts.get(i["severity"], 0) + 1

    return {"items": items, "counts": counts, "total": len(items)}


@router.post("/{item_key}/dismiss")
def dismiss_item(
    item_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Descarta un item de la bandeja (no borra el registro subyacente).

    Valida ownership por organizacion y registra la accion en el audit log.
    """
    m = _ITEM_KEY_RE.match(item_key)
    if not m:
        raise HTTPException(400, "Identificador de item no valido")
    item_type, entity_id = m.group(1), int(m.group(2))

    record = db.get(_ITEM_MODEL[item_type], entity_id)
    if not record or not check_org_access(record.organization_id, current_user):
        raise HTTPException(404, "Item no encontrado")

    existing = db.query(InboxDismissal).filter(
        InboxDismissal.organization_id == record.organization_id,
        InboxDismissal.item_key == item_key,
    ).first()
    if existing:
        raise HTTPException(409, "El item ya fue descartado")

    db.add(InboxDismissal(
        organization_id=record.organization_id,
        item_key=item_key,
        dismissed_by_id=current_user.id,
    ))
    log_action(db, current_user.id, "dismiss", "inbox_item", item_key,
               {"item_type": item_type, "entity_id": entity_id},
               organization_id=record.organization_id)
    db.commit()
    return {"dismissed": item_key}
