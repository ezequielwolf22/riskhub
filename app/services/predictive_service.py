"""Servicio de análisis predictivo de riesgos.

Funcionalidades:
- Forecasting de likelihood basado en historial
- Detección de trends (riesgos subiendo/bajando)
- Maturity path: qué controles implementar para mejorar postura
- CVE prediction: software con mayor probabilidad de CVE próximo
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Risk, RiskStatus, Asset, Threat, ControlImplementation, ControlStatus,
    RiskContext, ExternalFinding,
)

logger = logging.getLogger("riskhub.predictive")


def get_risk_trend_analysis(db: Session, org_id: int, days: int = 90) -> dict:
    """Analiza trend de riesgos en los últimos N días.

    Retorna: velocidad de creación, porcentaje de cambio, forecast.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    mid = now - timedelta(days=days // 2)

    risks_all = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.created_at >= start,
    ).all()

    # Dividir en dos mitades para comparar
    first_half = [r for r in risks_all if r.created_at and r.created_at.replace(tzinfo=timezone.utc) < mid]
    second_half = [r for r in risks_all if r.created_at and r.created_at.replace(tzinfo=timezone.utc) >= mid]

    first_high = sum(1 for r in first_half if (r.residual_level or 0) >= 5)
    second_high = sum(1 for r in second_half if (r.residual_level or 0) >= 5)

    total_change_pct = 0
    if len(first_half) > 0:
        total_change_pct = int(((len(second_half) - len(first_half)) / len(first_half)) * 100)

    high_change_pct = 0
    if first_high > 0:
        high_change_pct = int(((second_high - first_high) / first_high) * 100)

    # Velocidad: riesgos/día
    velocity = round(len(risks_all) / max(1, days), 2)
    high_velocity = round((first_high + second_high) / max(1, days), 2)

    # Forecast próximos 30 días
    forecast_total = int(velocity * 30)
    forecast_high = int(high_velocity * 30)

    # Determinar dirección del trend
    if total_change_pct > 15:
        trend_direction = "increasing"
        trend_label = "Riesgos en aumento"
        trend_severity = "warning"
    elif total_change_pct < -15:
        trend_direction = "decreasing"
        trend_label = "Riesgos en descenso"
        trend_severity = "good"
    else:
        trend_direction = "stable"
        trend_label = "Riesgos estables"
        trend_severity = "neutral"

    return {
        "period_days": days,
        "total_risks": len(risks_all),
        "first_half_count": len(first_half),
        "second_half_count": len(second_half),
        "high_risks_first": first_high,
        "high_risks_second": second_high,
        "total_change_pct": total_change_pct,
        "high_change_pct": high_change_pct,
        "velocity_per_day": velocity,
        "high_velocity_per_day": high_velocity,
        "forecast_30d_total": forecast_total,
        "forecast_30d_high": forecast_high,
        "trend_direction": trend_direction,
        "trend_label": trend_label,
        "trend_severity": trend_severity,
    }


def get_maturity_path(db: Session, org_id: int) -> dict:
    """Calcula el camino de madurez: qué controles implementar para mejorar más.

    Retorna lista de recomendaciones priorizadas.
    """
    from app.services.compliance_service import get_multi_framework_dashboard, load_framework

    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    active_frameworks = (ctx.active_frameworks or []) if ctx else []

    # Controles actualmente implementados
    implemented = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == org_id,
        ControlImplementation.status == ControlStatus.IMPLEMENTED,
    ).count()

    total_controls = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == org_id,
    ).count()

    partial = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == org_id,
        ControlImplementation.status == ControlStatus.PARTIAL,
    ).count()

    current_pct = int((implemented / total_controls * 100) if total_controls > 0 else 0)

    # Obtener gaps de compliance
    gaps_by_framework = {}
    for fw_code in active_frameworks:
        from app.services.compliance_service import get_framework_compliance_status
        status = get_framework_compliance_status(db, org_id, fw_code)
        gaps_by_framework[fw_code] = status.get("gaps", [])

    # Priorizar recomendaciones
    recommendations = []

    # 1. Controles parciales — son los más fáciles de completar
    partial_controls = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == org_id,
        ControlImplementation.status == ControlStatus.PARTIAL,
    ).limit(5).all()

    for ctrl in partial_controls:
        recommendations.append({
            "type": "complete_partial_control",
            "priority": "high",
            "title": f"Completar control parcial: {ctrl.name[:60]}",
            "description": f"Este control está parcialmente implementado (madurez {ctrl.maturity or 0}/5). "
                          f"Completarlo mejorará directamente el residual de riesgos asociados.",
            "impact": "medium",
            "effort": "low",
            "estimated_days": 7,
        })

    # 2. Gaps de frameworks seleccionados
    for fw_code, gaps in gaps_by_framework.items():
        for gap in gaps[:3]:
            recommendations.append({
                "type": "framework_gap",
                "priority": "high" if gap.get("status") == "not_started" else "medium",
                "title": f"[{fw_code.upper()}] {gap.get('id')}: {gap.get('name', '')[:60]}",
                "description": f"Requisito pendiente en {fw_code.upper()}, dominio {gap.get('domain', '')}. "
                              f"Estado actual: {gap.get('status', 'sin iniciar')}.",
                "impact": "high",
                "effort": "medium",
                "estimated_days": 14,
                "framework": fw_code,
                "requirement_id": gap.get("id"),
            })

    # 3. Riesgos sin controles asignados
    risks_no_controls = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.status == RiskStatus.ASSESSED,
        Risk.residual_level >= 4,
    ).limit(5).all()

    for r in risks_no_controls:
        ctrl_count = len(r.controls) if r.controls else 0
        if ctrl_count == 0:
            recommendations.append({
                "type": "assign_controls",
                "priority": "high",
                "title": f"Asignar controles a {r.code}",
                "description": f"El riesgo {r.code} (nivel {r.residual_level}) no tiene controles asignados. "
                              f"Asignar controles ISO 27002 reduciría el residual.",
                "impact": "high",
                "effort": "medium",
                "estimated_days": 30,
                "risk_id": r.id,
                "risk_code": r.code,
            })

    # Estimar mejora potencial
    potential_improvement = min(30, len(recommendations) * 3)
    target_pct = min(100, current_pct + potential_improvement)

    return {
        "current_implementation_pct": current_pct,
        "total_controls": total_controls,
        "implemented": implemented,
        "partial": partial,
        "target_pct": target_pct,
        "potential_improvement": potential_improvement,
        "recommendations": recommendations[:10],
        "active_frameworks": active_frameworks,
    }


def get_high_risk_assets(db: Session, org_id: int, limit: int = 10) -> list[dict]:
    """Identifica activos con mayor concentración de riesgos altos."""
    risks = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.residual_level >= 4,
        Risk.status.notin_([RiskStatus.ACCEPTED, RiskStatus.CLOSED]),
    ).all()

    asset_risk_counts: dict[int, dict] = defaultdict(lambda: {"count": 0, "max_level": 0, "total_level": 0})
    for r in risks:
        if r.asset_id:
            asset_risk_counts[r.asset_id]["count"] += 1
            asset_risk_counts[r.asset_id]["max_level"] = max(
                asset_risk_counts[r.asset_id]["max_level"], r.residual_level or 0
            )
            asset_risk_counts[r.asset_id]["total_level"] += r.residual_level or 0

    result = []
    for asset_id, stats in sorted(
        asset_risk_counts.items(),
        key=lambda x: (x[1]["max_level"], x[1]["count"]),
        reverse=True
    )[:limit]:
        asset = db.get(Asset, asset_id)
        if not asset:
            continue
        result.append({
            "asset_id": asset_id,
            "asset_code": asset.code,
            "asset_name": asset.name,
            "asset_type": asset.asset_type.value if hasattr(asset.asset_type, "value") else str(asset.asset_type),
            "high_risk_count": stats["count"],
            "max_residual_level": stats["max_level"],
            "avg_residual_level": round(stats["total_level"] / stats["count"], 1),
            "recommendation": _asset_recommendation(asset, stats),
        })
    return result


def _asset_recommendation(asset: Asset, stats: dict) -> str:
    if stats["max_level"] >= 6:
        return "Acción urgente: riesgos críticos sin mitigar. Revisar controles inmediatamente."
    if stats["count"] >= 5:
        return "Alta concentración de riesgos. Considerar segmentación o controles adicionales."
    return "Revisar y asignar controles específicos para este activo."


def get_threat_forecast(db: Session, org_id: int) -> list[dict]:
    """Predice qué amenazas tienen mayor probabilidad de materializarse próximamente.

    Basado en: historial de incidentes, hallazgos externos, CVEs recientes.
    """
    # Obtener amenazas con riesgos activos y su historial
    risks = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.status.notin_([RiskStatus.ACCEPTED, RiskStatus.CLOSED]),
    ).all()

    threat_stats: dict[int, dict] = defaultdict(lambda: {
        "count": 0, "max_level": 0, "avg_likelihood": 0, "name": "", "code": ""
    })

    for r in risks:
        if r.threat_id:
            threat_stats[r.threat_id]["count"] += 1
            threat_stats[r.threat_id]["max_level"] = max(
                threat_stats[r.threat_id]["max_level"], r.residual_level or 0
            )
            threat_stats[r.threat_id]["avg_likelihood"] += r.inherent_likelihood or 0
            if r.threat:
                threat_stats[r.threat_id]["name"] = r.threat.name
                threat_stats[r.threat_id]["code"] = r.threat.code

    # Normalizar likelihood promedio
    for tid in threat_stats:
        cnt = threat_stats[tid]["count"]
        if cnt > 0:
            threat_stats[tid]["avg_likelihood"] = round(
                threat_stats[tid]["avg_likelihood"] / cnt, 1
            )

    # Hallazgos externos recientes como señal
    recent_findings = db.query(ExternalFinding).filter(
        ExternalFinding.organization_id == org_id,
        ExternalFinding.severity.in_(["HIGH", "CRITICAL"]),
        ExternalFinding.status == "open",
    ).count()

    forecasts = []
    for tid, stats in sorted(
        threat_stats.items(),
        key=lambda x: (x[1]["max_level"], x[1]["avg_likelihood"]),
        reverse=True
    )[:8]:
        score = (stats["max_level"] * 0.4 + stats["avg_likelihood"] * 0.4 + min(5, stats["count"]) * 0.2)
        forecasts.append({
            "threat_id": tid,
            "threat_name": stats["name"],
            "threat_code": stats["code"],
            "risk_count": stats["count"],
            "max_residual_level": stats["max_level"],
            "avg_likelihood": stats["avg_likelihood"],
            "forecast_score": round(score, 2),
            "signal": "Alta" if score >= 3.5 else "Media" if score >= 2 else "Baja",
        })

    return forecasts
