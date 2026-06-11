"""Motor de recomendaciones de tests BCM — ISO 22301 cl. 8.5."""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.models import BCPPlan, BCPTest, BusinessProcess, BCMTestRecommendation
from app.services.bcp_service import bia_completeness

logger = logging.getLogger("riskhub.bcm_test_engine")

PLAN_SCHEDULE = {
    "bcp":              [("tabletop", 90), ("simulation", 180)],
    "drp":              [("walkthrough", 30), ("tabletop", 90), ("technical_recovery", 180)],
    "communication":    [("notification_drill", 60)],
    "crisis_management": [("tabletop", 60), ("simulation", 180)],
    "resumption":       [("walkthrough", 90)],
    "cyber_response":   [("tabletop", 60), ("simulation", 180)],
}

CRITICALITY_MAX_DAYS = {
    "critical": 180, "high": 270, "medium": 365, "low": 730
}


def generate_recommendations(db: Session, org_id: int, location_id: int = None) -> int:
    now = datetime.now(timezone.utc)
    created = 0

    q = db.query(BCPPlan).filter_by(organization_id=org_id, status="approved")
    if location_id:
        try:
            q = q.filter_by(location_id=location_id)
        except Exception:
            pass
    for plan in q.all():
        for test_type, interval_days in PLAN_SCHEDULE.get(plan.plan_type, [("tabletop", 180)]):
            latest = db.query(BCPTest).filter_by(
                organization_id=org_id
            ).filter(BCPTest.process_ids.contains(str(plan.id))).order_by(
                BCPTest.conducted_at.desc()
            ).first()
            days_since = 9999 if not latest or not latest.conducted_at else \
                (now - latest.conducted_at.replace(tzinfo=timezone.utc)).days
            if days_since < interval_days:
                continue
            exists = db.query(BCMTestRecommendation).filter_by(
                organization_id=org_id, plan_id=plan.id,
                recommended_test_type=test_type, status="pending"
            ).first()
            if not exists:
                db.add(BCMTestRecommendation(
                    organization_id=org_id,
                    location_id=getattr(plan, "location_id", None),
                    plan_id=plan.id,
                    recommended_test_type=test_type,
                    reason=f"Plan {plan.code} ({plan.plan_type}): sin test '{test_type}' en {days_since} días.",
                    recommended_date=now + timedelta(days=14),
                    priority="critical" if days_since > 365 else "high" if days_since > 270 else "medium",
                    trigger="overdue_12m" if days_since > 365 else "plan_approved",
                ))
                created += 1

    pq = db.query(BusinessProcess).filter_by(organization_id=org_id)
    if location_id:
        try:
            pq = pq.filter_by(location_id=location_id)
        except Exception:
            pass
    for proc in pq.all():
        max_days = CRITICALITY_MAX_DAYS.get(proc.criticality, 365)
        last = proc.last_tested_at
        days = 9999 if not last else \
            (now - last.replace(tzinfo=timezone.utc)).days
        if days < max_days:
            continue
        exists = db.query(BCMTestRecommendation).filter_by(
            organization_id=org_id, process_id=proc.id, status="pending"
        ).first()
        if not exists:
            db.add(BCMTestRecommendation(
                organization_id=org_id,
                location_id=getattr(proc, "location_id", None),
                process_id=proc.id,
                recommended_test_type="tabletop",
                reason=f"Proceso '{proc.name}' ({proc.criticality}): sin test en {days} días. ISO 22301 cl. 8.5.",
                recommended_date=now + timedelta(days=7),
                priority="critical" if proc.criticality == "critical" else "high",
                trigger="never_tested" if days == 9999 else "overdue_12m",
            ))
            created += 1

    # BIA completeness alerts — processes with < 80% BIA
    for proc in pq.all():
        bia = bia_completeness(None, proc)
        if bia["pct"] >= 80:
            continue
        exists = db.query(BCMTestRecommendation).filter_by(
            organization_id=org_id, process_id=proc.id,
            recommended_test_type="bia_incomplete", status="pending"
        ).first()
        if not exists:
            missing_str = ", ".join(bia["missing"][:4])
            db.add(BCMTestRecommendation(
                organization_id=org_id,
                location_id=getattr(proc, "location_id", None),
                process_id=proc.id,
                recommended_test_type="bia_incomplete",
                reason=(
                    f"BIA incompleto para '{proc.name}' — {bia['pct']}% completado. "
                    f"Faltan: {missing_str}. ISO 22301 cl. 8.2."
                ),
                recommended_date=now + timedelta(days=7),
                priority="critical" if proc.criticality in ("critical", "high") else "medium",
                trigger="bia_incomplete",
            ))
            created += 1

    if created:
        db.commit()
    return created


def filter_tests_ad_hoc(db: Session, org_id: int, filters: dict) -> list:
    """Genera lista de tests recomendados según filtros ad-hoc."""
    results = []
    pq = db.query(BCPPlan).filter_by(organization_id=org_id)
    if filters.get("location_ids"):
        try:
            pq = pq.filter(BCPPlan.location_id.in_(filters["location_ids"]))
        except Exception:
            pass
    if filters.get("plan_type"):
        pq = pq.filter_by(plan_type=filters["plan_type"])
    for plan in pq.all():
        if filters.get("asset_id"):
            covers = any(
                filters["asset_id"] in (db.get(BusinessProcess, pid).asset_ids or [])
                for pid in (plan.process_ids or [])
                if db.get(BusinessProcess, pid)
            )
            if not covers:
                continue
        results.append({
            "plan_id": plan.id, "plan_code": plan.code,
            "plan_name": plan.name, "plan_type": plan.plan_type,
            "location_id": getattr(plan, "location_id", None),
            "suggested_test_type": (PLAN_SCHEDULE.get(plan.plan_type, [("tabletop", 90)])[0][0]),
        })
    return results
