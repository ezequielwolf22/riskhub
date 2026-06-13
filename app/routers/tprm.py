"""Modulo TPRM (Third-Party Risk Management).

Endpoints transversales del modulo TPRM construido sobre el modelo Supplier:
 - Dashboard ejecutivo (summary, heatmap, portfolio por tier)
 - Recalculo de inherent/residual risk y tiering
 - Biblioteca de plantillas de cuestionario del sistema (§4.4)

Reutiliza la infraestructura existente de proveedores y cuestionarios; no crea
un silo paralelo (ver spec §0).
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Supplier, SupplierTier, User
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services import tprm_scoring_service as scoring
from app.services import tprm_templates
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tprm", tags=["tprm"])


# ---------- Dashboard ----------

@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    """KPIs agregados del portfolio de proveedores (§7.1)."""
    suppliers = filter_by_org(db.query(Supplier), Supplier, current_user).all()
    now = datetime.now(timezone.utc)

    by_tier = {"critical": 0, "high": 0, "medium": 0, "low": 0, "unrated": 0}
    by_residual = {"critical": 0, "high": 0, "medium": 0, "low": 0, "very_low": 0, "unknown": 0}
    overdue = 0
    nis2 = dora = ens = processors = 0

    for s in suppliers:
        tier = s.tier.value if s.tier else "unrated"
        by_tier[tier] = by_tier.get(tier, 0) + 1
        lvl = scoring.risk_level_label(s.residual_risk_score)
        by_residual[lvl] = by_residual.get(lvl, 0) + 1
        if s.next_assessment_at and s.next_assessment_at.replace(tzinfo=timezone.utc) < now:
            overdue += 1
        if s.is_nis2:
            nis2 += 1
        if s.is_dora:
            dora += 1
        if s.is_ens:
            ens += 1
        if s.is_data_processor or s.processes_personal_data:
            processors += 1

    top_residual = sorted(
        [s for s in suppliers if s.residual_risk_score is not None],
        key=lambda s: s.residual_risk_score, reverse=True,
    )[:10]

    return {
        "total": len(suppliers),
        "by_tier": by_tier,
        "by_residual_level": by_residual,
        "overdue_assessment": overdue,
        "regulatory_scope": {"nis2": nis2, "dora": dora, "ens": ens, "gdpr_processors": processors},
        "top_residual": [
            {
                "id": s.id, "code": s.code, "name": s.name,
                "tier": s.tier.value if s.tier else None,
                "inherent_risk_score": s.inherent_risk_score,
                "residual_risk_score": s.residual_risk_score,
            }
            for s in top_residual
        ],
    }


@router.get("/dashboard/heatmap")
def dashboard_heatmap(db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    """Datos para el heatmap inherent vs residual (§7.5)."""
    suppliers = filter_by_org(db.query(Supplier), Supplier, current_user).all()
    return [
        {
            "id": s.id, "code": s.code, "name": s.name,
            "tier": s.tier.value if s.tier else None,
            "inherent_risk_score": s.inherent_risk_score or 0,
            "residual_risk_score": s.residual_risk_score or 0,
            "annual_spend": s.annual_spend,
        }
        for s in suppliers
        if s.inherent_risk_score is not None
    ]


@router.get("/dashboard/portfolio-by-tier")
def portfolio_by_tier(db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    """Listado de proveedores agrupado por tier."""
    suppliers = filter_by_org(db.query(Supplier), Supplier, current_user).all()
    groups: dict = {"critical": [], "high": [], "medium": [], "low": [], "unrated": []}
    for s in suppliers:
        tier = s.tier.value if s.tier else "unrated"
        groups.setdefault(tier, []).append({
            "id": s.id, "code": s.code, "name": s.name,
            "inherent_risk_score": s.inherent_risk_score,
            "residual_risk_score": s.residual_risk_score,
            "next_assessment_at": s.next_assessment_at.isoformat() if s.next_assessment_at else None,
        })
    return groups


# ---------- Recalculo de scoring ----------

@router.post("/vendors/{supplier_id}/recompute-inherent-risk")
def recompute_inherent_risk(supplier_id: int, db: Session = Depends(get_db),
                            current_user: User = Depends(require_analyst)):
    """Recalcula inherent risk, tier y residual risk de un proveedor (§4.2-4.3)."""
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, "Proveedor no encontrado")
    result = scoring.recompute_supplier(db, s)
    log_action(db, current_user.id, "recompute_tprm", "supplier", str(s.id), result)
    return result


@router.post("/vendors/recompute-all")
def recompute_all(db: Session = Depends(get_db),
                  current_user: User = Depends(require_analyst)):
    """Recalcula el scoring TPRM de todo el portfolio de la organizacion."""
    suppliers = filter_by_org(db.query(Supplier), Supplier, current_user).all()
    for s in suppliers:
        scoring.recompute_supplier(db, s, commit=False)
    db.commit()
    log_action(db, current_user.id, "recompute_tprm_all", "supplier", "*", {"count": len(suppliers)})
    return {"recomputed": len(suppliers)}


# ---------- Biblioteca de plantillas del sistema (§4.4) ----------

@router.get("/questionnaire-templates")
def list_questionnaire_templates(current_user: User = Depends(get_current_user)):
    """Lista las plantillas de cuestionario del sistema (clonables)."""
    return tprm_templates.list_templates()


@router.get("/questionnaire-templates/{code}")
def get_questionnaire_template(code: str, current_user: User = Depends(get_current_user)):
    """Devuelve la estructura completa de una plantilla del sistema."""
    tpl = tprm_templates.get_template(code)
    if not tpl:
        raise HTTPException(404, "Plantilla no encontrada")
    return tpl
