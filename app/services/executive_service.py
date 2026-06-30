"""Servicio de dashboard ejecutivo y generación de informes board-level."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import case, func as _func
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Risk, RiskStatus, Asset, TreatmentTask, TaskStatus,
    ControlImplementation, ControlStatus, Incident, IncidentSeverity,
    Supplier, SupplierRisk, RiskContext, User, UserRole,
)

logger = logging.getLogger("riskhub.executive")


def get_kpis(db: Session, org_id: int) -> dict:
    """Calcula KPIs dinámicos para dashboard ejecutivo — una sola pasada SQL por tabla."""
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    seven_days = now + timedelta(days=7)

    # Risk appetite (necesario para risks_over_appetite)
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    appetite = ctx.risk_appetite if ctx else 3

    closed_statuses = [RiskStatus.ACCEPTED.value, RiskStatus.CLOSED.value]
    open_statuses = [RiskStatus.IDENTIFIED.value, RiskStatus.ASSESSED.value]

    # Una sola query de riesgos con todas las agregaciones via CASE WHEN
    row = db.query(
        _func.count(Risk.id).label("total"),
        _func.sum(case(
            (Risk.residual_level >= 5, 1), else_=0
        ).filter(Risk.status.notin_(closed_statuses))).label("high"),
        _func.sum(case(
            (Risk.status == RiskStatus.ACCEPTED.value, 1), else_=0
        )).label("accepted"),
        _func.sum(case(
            (Risk.created_at >= thirty_days_ago, 1), else_=0
        )).label("new_30d"),
        _func.sum(case(
            (Risk.residual_level > appetite, 1), else_=0
        ).filter(Risk.status.notin_(closed_statuses))).label("over_appetite"),
    ).filter(Risk.organization_id == org_id).one()

    total_risks = row.total or 0
    high_risks = int(row.high or 0)
    accepted_risks = int(row.accepted or 0)
    new_risks_30d = int(row.new_30d or 0)
    risks_over_appetite = int(row.over_appetite or 0)
    mitigated_pct = int(accepted_risks / total_risks * 100) if total_risks else 0

    # MAT: calcular en Python con los riesgos abiertos (solo ids + created_at — ligero)
    open_dates = db.query(Risk.created_at).filter(
        Risk.organization_id == org_id,
        Risk.status.in_(open_statuses),
        Risk.created_at.isnot(None),
    ).all()
    if open_dates:
        ages = [(now - r.created_at.replace(tzinfo=timezone.utc)).days for r in open_dates]
        mat_days = int(sum(ages) / len(ages))
    else:
        mat_days = 0

    # Controles — dos conteos en una query
    ctrl_row = db.query(
        _func.count(ControlImplementation.id).label("total"),
        _func.sum(case(
            (ControlImplementation.status == ControlStatus.IMPLEMENTED.value, 1), else_=0
        )).label("implemented"),
    ).filter(ControlImplementation.organization_id == org_id).one()
    total_controls = ctrl_row.total or 0
    implemented_controls = int(ctrl_row.implemented or 0)
    controls_pct = int(implemented_controls / total_controls * 100) if total_controls else 0

    # Tareas — overdue + upcoming en una query
    task_row = db.query(
        _func.sum(case(
            (TreatmentTask.due_date < now, 1), else_=0
        )).label("overdue"),
        _func.sum(case(
            ((TreatmentTask.due_date >= now) & (TreatmentTask.due_date <= seven_days), 1), else_=0
        )).label("upcoming"),
    ).filter(
        TreatmentTask.organization_id == org_id,
        TreatmentTask.status != TaskStatus.DONE.value,
    ).one()
    overdue_tasks = int(task_row.overdue or 0)
    upcoming_tasks = int(task_row.upcoming or 0)

    # Incidentes + proveedores criticos en queries simples de COUNT (rapidas con indice)
    incidents_30d = db.query(_func.count(Incident.id)).filter(
        Incident.organization_id == org_id,
        Incident.created_at >= thirty_days_ago,
    ).scalar() or 0

    critical_suppliers = db.query(_func.count(Supplier.id)).filter(
        Supplier.organization_id == org_id,
        Supplier.is_critical == True,
    ).scalar() or 0

    risk_score = 0
    if total_risks:
        risk_score = min(100, int(
            (high_risks * 3 + risks_over_appetite * 2 + overdue_tasks) / max(1, total_risks) * 20
        ))

    return {
        "risk_score": risk_score,
        "total_risks": total_risks,
        "high_risks": high_risks,
        "risks_over_appetite": risks_over_appetite,
        "mitigated_pct": mitigated_pct,
        "new_risks_30d": new_risks_30d,
        "mat_days": mat_days,
        "controls_pct": controls_pct,
        "implemented_controls": implemented_controls,
        "total_controls": total_controls,
        "overdue_tasks": overdue_tasks,
        "upcoming_tasks_7d": upcoming_tasks,
        "incidents_30d": incidents_30d,
        "critical_suppliers": critical_suppliers,
        "risk_appetite": appetite,
    }


def get_top_risks(db: Session, org_id: int, limit: int = 10, offset: int = 0) -> list[dict]:
    """Top N riesgos por nivel residual — eager load de asset para evitar N+1."""
    risks = db.query(Risk).options(
        joinedload(Risk.asset),
    ).filter(
        Risk.organization_id == org_id,
        Risk.status.notin_([RiskStatus.ACCEPTED, RiskStatus.CLOSED]),
    ).order_by(Risk.residual_level.desc()).offset(offset).limit(limit).all()

    return [
        {
            "id": r.id,
            "code": r.code,
            "description": (r.description or "")[:100],
            "asset_name": r.asset.name if r.asset else "",
            "residual_level": r.residual_level,
            "inherent_level": r.inherent_level,
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in risks
    ]


def get_risk_trend(db: Session, org_id: int, days: int = 30) -> list[dict]:
    """Trend de creación/cierre de riesgos por día (últimos N días)."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    risks = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.created_at >= start,
    ).all()

    # Agrupar por día
    by_day: dict[str, dict] = {}
    for r in risks:
        if not r.created_at:
            continue
        day = r.created_at.strftime("%Y-%m-%d")
        if day not in by_day:
            by_day[day] = {"date": day, "created": 0, "closed": 0, "high": 0}
        by_day[day]["created"] += 1
        if r.status in [RiskStatus.ACCEPTED, RiskStatus.CLOSED]:
            by_day[day]["closed"] += 1
        if (r.residual_level or 0) >= 5:
            by_day[day]["high"] += 1

    return sorted(by_day.values(), key=lambda x: x["date"])


def get_risk_heatmap(db: Session, org_id: int) -> dict:
    """Heatmap de riesgos por dominio y severidad."""
    from app.services.compliance_service import load_framework, list_available_frameworks

    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    active = (ctx.active_frameworks or []) if ctx else []

    heatmap = []
    for fw_code in active:
        fw = load_framework(fw_code)
        if not fw:
            continue
        domains = list({r.get("domain", "General") for r in fw.get("requirements", [])})
        for domain in domains:
            # Contar riesgos que aplican a este dominio
            # (aproximación: por nombre de controles)
            heatmap.append({
                "framework": fw_code,
                "framework_name": fw.get("name", fw_code),
                "domain": domain,
                "risk_count": 0,  # Se puede mejorar con relación explícita
            })

    return {
        "heatmap": heatmap,
        "active_frameworks": active,
    }


def generate_board_report_data(db: Session, org_id: int) -> dict:
    """Genera datos para informe de dirección (board-level)."""
    now = datetime.now(timezone.utc)
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    org_name = ctx.organization_name if ctx else "Organización"

    kpis = get_kpis(db, org_id)
    top_risks = get_top_risks(db, org_id, 5)
    trend = get_risk_trend(db, org_id, 30)

    # Compliance summary
    from app.services.compliance_service import get_multi_framework_dashboard
    compliance = get_multi_framework_dashboard(db, org_id)

    # Incidentes del mes
    thirty_days_ago = now - timedelta(days=30)
    recent_incidents = []
    try:
        incidents = db.query(Incident).filter(
            Incident.organization_id == org_id,
            Incident.created_at >= thirty_days_ago,
        ).order_by(Incident.created_at.desc()).limit(5).all()
        for i in incidents:
            recent_incidents.append({
                "title": i.title,
                "severity": i.severity.value if hasattr(i.severity, "value") else str(i.severity),
                "date": i.created_at.isoformat() if i.created_at else None,
            })
    except Exception:
        pass

    return {
        "org_name": org_name,
        "report_date": now.isoformat(),
        "period": f"{(now - timedelta(days=30)).strftime('%d/%m/%Y')} - {now.strftime('%d/%m/%Y')}",
        "kpis": kpis,
        "top_risks": top_risks,
        "risk_trend_30d": trend,
        "compliance": compliance,
        "recent_incidents": recent_incidents,
        "summary_text": _generate_summary(kpis, top_risks, compliance),
    }


def _generate_summary(kpis: dict, top_risks: list, compliance: dict) -> str:
    """Genera texto ejecutivo del resumen."""
    lines = []
    total = kpis.get("total_risks", 0)
    high = kpis.get("high_risks", 0)
    mitigated = kpis.get("mitigated_pct", 0)
    controls = kpis.get("controls_pct", 0)
    overall_compliance = compliance.get("overall_pct", 0)
    overdue = kpis.get("overdue_tasks", 0)

    lines.append(
        f"La organización gestiona actualmente {total} riesgos, "
        f"de los cuales {high} son de nivel alto o crítico."
    )
    lines.append(
        f"El {mitigated}% de los riesgos han sido aceptados o mitigados por debajo del apetito de riesgo."
    )
    lines.append(
        f"Los controles de seguridad tienen un {controls}% de implementación."
    )
    if overall_compliance > 0:
        lines.append(f"El cumplimiento normativo global se sitúa en {overall_compliance}%.")
    if overdue > 0:
        lines.append(
            f"Hay {overdue} tarea(s) de tratamiento vencidas que requieren atención inmediata."
        )
    return " ".join(lines)
