"""Modulo TPRM (Third-Party Risk Management).

Endpoints transversales del modulo TPRM construido sobre el modelo Supplier:
 - Dashboard ejecutivo (summary, heatmap, portfolio por tier)
 - Recalculo de inherent/residual risk y tiering
 - Biblioteca de plantillas de cuestionario del sistema (§4.4)

Reutiliza la infraestructura existente de proveedores y cuestionarios; no crea
un silo paralelo (ver spec §0).
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import Supplier, SupplierTier, TPRMTemplate, TprmSettings, User
from app.schemas import TPRMTemplateCreate, TPRMTemplateOut, TPRMTemplateUpdate
from app.security import (
    check_org_access,
    filter_by_org,
    get_current_user,
    require_admin,
    require_analyst,
)
from app.services import tprm_scoring_service as scoring
from app.services import tprm_templates
from app.services.risk_engine import band_for_config, get_risk_bands
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
    _bands = get_risk_bands(db, getattr(current_user, "organization_id", None))
    by_residual = {"critical": 0, "high": 0, "medium": 0, "low": 0, "very_low": 0, "unknown": 0}
    by_residual.update({b["code"]: 0 for b in _bands})
    overdue = 0
    nis2 = dora = ens = processors = 0

    for s in suppliers:
        tier = s.tier.value if s.tier else "unrated"
        by_tier[tier] = by_tier.get(tier, 0) + 1
        # Convierte score TPRM 0-100 (mayor=peor) a nivel ISO 27005 0-8 y busca banda
        iso_lvl = round(min(100, max(0, s.residual_risk_score or 0)) * 8 / 100)
        bc = band_for_config(iso_lvl, _bands)
        by_residual[bc["code"]] = by_residual.get(bc["code"], 0) + 1
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

    from app.models import VendorRiskAssessment
    assessments = filter_by_org(db.query(VendorRiskAssessment), VendorRiskAssessment, current_user).all()
    # IDs de proveedores con al menos una evaluacion completada (decision tomada)
    assessed_supplier_ids = {a.supplier_id for a in assessments if a.recommendation is not None}
    pending_assessments   = sum(1 for a in assessments if a.recommendation is None)
    completed_assessments = sum(1 for a in assessments if a.recommendation is not None)

    # Proveedores tratados (tienen al menos una evaluacion con decision) vs sin tratar
    treated_count   = sum(1 for s in suppliers if s.id in assessed_supplier_ids)
    untreated_count = len(suppliers) - treated_count

    # Riesgo TPRM ponderado del portfolio (0-10): media ponderada por tier
    # Tier critico peso 4, alto 3, medio 2, bajo 1, sin tier 1
    tier_weights = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unrated": 1}
    scored = [s for s in suppliers if s.residual_risk_score is not None]
    if scored:
        total_w = sum(tier_weights.get(s.tier.value if s.tier else "unrated", 1) for s in scored)
        weighted_sum = sum(
            s.residual_risk_score * tier_weights.get(s.tier.value if s.tier else "unrated", 1)
            for s in scored
        )
        portfolio_score_10 = round((weighted_sum / total_w) / 10, 1)  # 0-10
    else:
        portfolio_score_10 = None

    # Proximas revisiones (proximos 90 dias)
    in_90d = now + timedelta(days=90)
    upcoming_reviews = sorted(
        [s for s in suppliers
         if s.next_assessment_at and s.next_assessment_at.replace(tzinfo=timezone.utc) > now
         and s.next_assessment_at.replace(tzinfo=timezone.utc) <= in_90d],
        key=lambda s: s.next_assessment_at,
    )[:5]

    return {
        "total": len(suppliers),
        "treated_count": treated_count,
        "untreated_count": untreated_count,
        "portfolio_score_10": portfolio_score_10,
        "by_tier": by_tier,
        "by_residual_level": by_residual,
        "overdue_assessment": overdue,
        "pending_assessments": pending_assessments,
        "completed_assessments": completed_assessments,
        "regulatory_scope": {"nis2": nis2, "dora": dora, "ens": ens, "gdpr_processors": processors},
        "upcoming_reviews": [
            {
                "id": s.id, "code": s.code, "name": s.name,
                "next_assessment_at": s.next_assessment_at.isoformat() if s.next_assessment_at else None,
                "tier": s.tier.value if s.tier else None,
                "residual_risk_score": s.residual_risk_score,
            }
            for s in upcoming_reviews
        ],
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
def recompute_inherent_risk(supplier_id: int, request: Request, db: Session = Depends(get_db),
                            current_user: User = Depends(require_analyst)):
    """Recalcula inherent risk, tier y residual risk de un proveedor (§4.2-4.3)."""
    lang = get_lang(request)
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, _t("suppliers.not_found", lang))
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
def list_questionnaire_templates(request: Request, current_user: User = Depends(get_current_user)):
    """Lista las plantillas de cuestionario del sistema (clonables)."""
    return tprm_templates.list_templates(get_lang(request))


@router.get("/questionnaire-templates/{code}")
def get_questionnaire_template(code: str, request: Request, current_user: User = Depends(get_current_user)):
    """Devuelve la estructura completa de una plantilla del sistema."""
    lang = get_lang(request)
    tpl = tprm_templates.get_template(code, lang)
    if not tpl:
        raise HTTPException(404, _t("tprm.template_not_found", lang))
    return tpl


# ---------- Plantillas personalizadas (editables por el cliente) (§4.5) ----------

@router.get("/custom-templates", response_model=list[TPRMTemplateOut])
def list_custom_templates(db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """Lista las plantillas personalizadas de la organizacion."""
    return (
        filter_by_org(db.query(TPRMTemplate), TPRMTemplate, current_user)
        .order_by(TPRMTemplate.updated_at.desc().nullslast(), TPRMTemplate.id.desc())
        .all()
    )


@router.get("/custom-templates/{tid}", response_model=TPRMTemplateOut)
def get_custom_template(tid: int, request: Request, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    lang = get_lang(request)
    t = db.query(TPRMTemplate).filter(TPRMTemplate.id == tid).first()
    if not t or not check_org_access(t.organization_id, current_user):
        raise HTTPException(404, _t("tprm.template_not_found", lang))
    return t


@router.post("/custom-templates", response_model=TPRMTemplateOut, status_code=201)
def create_custom_template(body: TPRMTemplateCreate, request: Request, db: Session = Depends(get_db),
                           current_user: User = Depends(require_analyst)):
    """Crea una plantilla editable, opcionalmente clonando una del sistema."""
    lang = get_lang(request)
    name = body.name
    description = body.description
    framework_codes = body.framework_codes
    questions = body.questions
    created_from = None
    if body.from_system_code:
        sys_tpl = tprm_templates.get_template(body.from_system_code, lang)
        if not sys_tpl:
            raise HTTPException(404, _t("tprm.template_not_found", lang))
        created_from = sys_tpl["code"]
        name = name or f"{sys_tpl['name']} (copia)"
        description = description or sys_tpl.get("description")
        framework_codes = framework_codes or sys_tpl.get("framework_codes")
        # Copia profunda de las preguntas para poder editarlas sin afectar al original
        questions = questions if questions is not None else [dict(q) for q in sys_tpl["questions"]]
    if not name:
        raise HTTPException(400, _t("common.bad_request", lang))
    if questions is None:
        questions = []
    t = TPRMTemplate(
        organization_id=current_user.organization_id,
        name=name,
        description=description,
        framework_codes=framework_codes,
        questions=questions,
        created_from=created_from,
        created_by_id=current_user.id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    log_action(db, current_user.id, "create", "tprm_template", str(t.id), {"name": t.name})
    return t


@router.patch("/custom-templates/{tid}", response_model=TPRMTemplateOut)
def update_custom_template(tid: int, body: TPRMTemplateUpdate, request: Request, db: Session = Depends(get_db),
                           current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    t = db.query(TPRMTemplate).filter(TPRMTemplate.id == tid).first()
    if not t or not check_org_access(t.organization_id, current_user):
        raise HTTPException(404, _t("tprm.template_not_found", lang))
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(t, field, value)
    db.commit()
    db.refresh(t)
    log_action(db, current_user.id, "update", "tprm_template", str(t.id))
    return t


@router.delete("/custom-templates/{tid}", status_code=204)
def delete_custom_template(tid: int, request: Request, db: Session = Depends(get_db),
                           current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    t = db.query(TPRMTemplate).filter(TPRMTemplate.id == tid).first()
    if not t or not check_org_access(t.organization_id, current_user):
        raise HTTPException(404, _t("tprm.template_not_found", lang))
    log_action(db, current_user.id, "delete", "tprm_template", str(tid), {"name": t.name})
    db.delete(t)
    db.commit()


# ---------- Concentracion de riesgo (DORA Art.28) ----------

@router.get("/concentration-risk")
async def get_concentration_risk(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """DORA Art.28: proveedores con concentracion de riesgo > 40% en procesos criticos."""
    from app.services.supplier_lifecycle_service import compute_concentration_risk
    return compute_concentration_risk(db, current_user.organization_id)


# ---------- Configuracion del modulo (feedback cliente: puntos 4/7/11) ----------

@router.get("/settings")
def get_tprm_settings(db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    """Configuracion del modulo de proveedores de la organizacion activa."""
    from app.services import tprm_settings_service as tset
    org_id = current_user.organization_id
    st = db.query(TprmSettings).filter(TprmSettings.organization_id == org_id).first()
    data = tset.as_dict(st)
    data["region_suggestions"] = tset.bcm_region_suggestions(db, org_id)
    return data


@router.put("/settings")
def update_tprm_settings(payload: dict, db: Session = Depends(get_db),
                         current_user: User = Depends(require_admin)):
    """Actualiza la configuracion del modulo (admin). Regiones editables e
    independientes de las sedes BCM (punto 4)."""
    from app.services import tprm_settings_service as tset
    st = tset.update_settings(db, current_user.organization_id, payload)
    log_action(db, current_user.id, "update", "tprm_settings", str(st.id))
    data = tset.as_dict(st)
    data["region_suggestions"] = tset.bcm_region_suggestions(db, current_user.organization_id)
    return data
