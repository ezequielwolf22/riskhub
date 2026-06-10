"""Servicio de localizaciones BCM — árbol jerárquico y métricas consolidadas."""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import (BCMLocation, BusinessProcess, BCPPlan, BCPTest, Asset)

logger = logging.getLogger("riskhub.bcm_location")


def next_location_code(db: Session, org_id: int) -> str:
    n = db.query(BCMLocation).filter_by(organization_id=org_id).count()
    return f"LOC-{n + 1:03d}"


def get_location_tree(db: Session, org_id: int) -> list:
    """Árbol completo como lista de dicts anidados."""
    all_locs = db.query(BCMLocation).filter_by(
        organization_id=org_id, is_active=True
    ).order_by(BCMLocation.name).all()

    def _node(loc):
        return {
            "id": loc.id, "code": loc.code, "name": loc.name,
            "description": loc.description, "country": loc.country,
            "parent_id": loc.parent_id,
            "bcm_manager_id": loc.bcm_manager_id,
            "recovery_site_type": loc.recovery_site_type,
            "children": [_node(c) for c in all_locs if c.parent_id == loc.id],
        }

    return [_node(r) for r in all_locs if r.parent_id is None]


def get_location_metrics(db: Session, location_id: int, org_id: int) -> dict:
    """KPIs BCM para una localización."""
    from app.services.bcp_service import bia_completeness
    now = datetime.now(timezone.utc)

    procs = db.query(BusinessProcess).filter_by(
        organization_id=org_id, location_id=location_id).all()
    plans = _safe_query(db, "bcp_plans", BCPPlan, org_id, location_id)
    tests = db.query(BCPTest).filter_by(
        organization_id=org_id, location_id=location_id).all()

    bia_pcts = [bia_completeness(db, p)["pct"] for p in procs]
    avg_bia = int(sum(bia_pcts) / len(bia_pcts)) if bia_pcts else 0
    approved = [p for p in plans if p.status in ("approved", "active")]
    recent_passed = [
        t for t in tests
        if t.result == "passed" and t.conducted_at and
        (now - t.conducted_at.replace(tzinfo=timezone.utc)).days <= 365
    ]
    assets_count = db.query(Asset).filter_by(
        organization_id=org_id, bcm_location_id=location_id).count()

    maturity = "green" if avg_bia >= 80 and approved and recent_passed \
               else "yellow" if avg_bia >= 50 \
               else "red"

    return {
        "location_id": location_id,
        "processes_total": len(procs),
        "processes_critical": sum(1 for p in procs if p.criticality in ("critical", "high")),
        "avg_bia_pct": avg_bia,
        "plans_approved": len(approved),
        "tests_passed_12m": len(recent_passed),
        "assets_count": assets_count,
        "maturity_color": maturity,
    }


def get_consolidated_metrics(db: Session, org_id: int) -> dict:
    """Métricas de todas las localizaciones."""
    locs = db.query(BCMLocation).filter_by(organization_id=org_id, is_active=True).all()
    per_loc = {
        loc.id: {
            "location": {"id": loc.id, "name": loc.name, "code": loc.code,
                         "parent_id": loc.parent_id},
            "metrics": get_location_metrics(db, loc.id, org_id),
        }
        for loc in locs
    }
    unlocated = db.query(BusinessProcess).filter_by(organization_id=org_id).filter(
        BusinessProcess.location_id.is_(None)
    ).count()
    colors = [v["metrics"]["maturity_color"] for v in per_loc.values()]
    org_maturity = "green" if colors and all(c == "green" for c in colors) \
                   else "red" if any(c == "red" for c in colors) \
                   else "yellow" if colors else "red"
    return {
        "locations": per_loc, "total_locations": len(locs),
        "unlocated_processes": unlocated, "org_maturity": org_maturity,
    }


def _safe_query(db, table_name, Model, org_id, location_id):
    try:
        return db.query(Model).filter_by(
            organization_id=org_id, location_id=location_id).all()
    except Exception:
        return []
