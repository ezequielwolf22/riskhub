"""Servicio de dashboard ejecutivo y generación de informes board-level."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Risk, RiskStatus, Asset, TreatmentTask, TaskStatus,
    ControlImplementation, ControlStatus, Incident, IncidentSeverity,
    Supplier, SupplierRisk, RiskContext, User, UserRole,
)

logger = logging.getLogger("riskhub.executive")


def get_kpis(db: Session, org_id: int) -> dict:
    """Calcula KPIs dinámicos para dashboard ejecutivo."""
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    seven_days = now + timedelta(days=7)

    # Riesgos
    total_risks = db.query(Risk).filter(Risk.organization_id == org_id).count()
    high_risks = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.residual_level >= 5,
        Risk.status.notin_([RiskStatus.ACCEPTED, RiskStatus.CLOSED]),
    ).count()
    accepted_risks = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.status == RiskStatus.ACCEPTED,
    ).count()
    new_risks_30d = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.created_at >= thirty_days_ago,
    ).count()

    # MAT (Mean Age of Treatment)
    open_risks = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.status.in_([RiskStatus.IDENTIFIED, RiskStatus.ASSESSED]),
    ).all()
    mat_days = 0
    if open_risks:
        ages = [
            (now - (r.created_at.replace(tzinfo=timezone.utc) if r.created_at else now)).days
            for r in open_risks
        ]
        mat_days = int(sum(ages) / len(ages))

    # Mitigación
    mitigated_pct = int((accepted_risks / total_risks * 100) if total_risks > 0 else 0)

    # Controles
    total_controls = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == org_id
    ).count()
    implemented_controls = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == org_id,
        ControlImplementation.status == ControlStatus.IMPLEMENTED,
    ).count()
    controls_pct = int((implemented_controls / total_controls * 100) if total_controls > 0 else 0)

    # Tareas
    overdue_tasks = db.query(TreatmentTask).filter(
        TreatmentTask.organization_id == org_id,
        TreatmentTask.status != TaskStatus.DONE,
        TreatmentTask.due_date < now,
    ).count()
    upcoming_tasks = db.query(TreatmentTask).filter(
        TreatmentTask.organization_id == org_id,
        TreatmentTask.status != TaskStatus.DONE,
        TreatmentTask.due_date <= seven_days,
        TreatmentTask.due_date >= now,
    ).count()

    # Incidentes
    incidents_30d = db.query(Incident).filter(
        Incident.organization_id == org_id,
        Incident.created_at >= thirty_days_ago,
    ).count() if hasattr(Incident, "organization_id") else 0

    # Proveedores
    critical_suppliers = db.query(Supplier).filter(
        Supplier.organization_id == org_id,
        Supplier.risk_score <= 30,
    ).count()

    # Risk appetite status
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    appetite = ctx.risk_appetite if ctx else 3
    risks_over_appetite = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.residual_level > appetite,
        Risk.status.notin_([RiskStatus.ACCEPTED, RiskStatus.CLOSED]),
    ).count()

    # Overall risk score (0-100, menor = mejor)
    if total_risks == 0:
        risk_score = 0
    else:
        risk_score = min(100, int(
            (high_risks * 3 + risks_over_appetite * 2 + overdue_tasks) / max(1, total_risks) * 20
        ))

    return {
        "risk_score": risk_score,                        # 0-100 (menor = mejor)
        "total_risks": total_risks,
        "high_risks": high_risks,
        "risks_over_appetite": risks_over_appetite,
        "mitigated_pct": mitigated_pct,
        "new_risks_30d": new_risks_30d,
        "mat_days": mat_days,                            # Mean Age of Treatment
        "controls_pct": controls_pct,
        "implemented_controls": implemented_controls,
        "total_controls": total_controls,
        "overdue_tasks": overdue_tasks,
        "upcoming_tasks_7d": upcoming_tasks,
        "incidents_30d": incidents_30d,
        "critical_suppliers": critical_suppliers,
        "risk_appetite": appetite,
    }


def get_top_risks(db: Session, org_id: int, limit: int = 10) -> list[dict]:
    """Top N riesgos por nivel residual."""
    risks = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.status.notin_([RiskStatus.ACCEPTED, RiskStatus.CLOSED]),
    ).order_by(Risk.residual_level.desc()).limit(limit).all()

    result = []
    for r in risks:
        asset_name = ""
        if r.asset_id:
            asset = db.get(Asset, r.asset_id)
            if asset:
                asset_name = asset.name or ""
        result.append({
            "id": r.id,
            "code": r.code,
            "description": (r.description or "")[:100],
            "asset_name": asset_name,
            "residual_level": r.residual_level,
            "inherent_level": r.inherent_level,
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return result


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
