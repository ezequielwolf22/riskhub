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
from app.models import Supplier, SupplierTier, TPRMTemplate, User
from app.schemas import TPRMTemplateCreate, TPRMTemplateOut, TPRMTemplateUpdate
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

    from app.models import VendorRiskAssessment, AssessmentRecommendation
    org_id = current_user.organization_id
    assessments = filter_by_org(db.query(VendorRiskAssessment), VendorRiskAssessment, current_user).all()
    pending_assessments   = sum(1 for a in assessments if a.recommendation is None)
    completed_assessments = sum(1 for a in assessments if a.recommendation is not None)

    return {
        "total": len(suppliers),
        "by_tier": by_tier,
        "by_residual_level": by_residual,
        "overdue_assessment": overdue,
        "pending_assessments": pending_assessments,
        "completed_assessments": completed_assessments,
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
def get_custom_template(tid: int, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    t = db.query(TPRMTemplate).filter(TPRMTemplate.id == tid).first()
    if not t or not check_org_access(t.organization_id, current_user):
        raise HTTPException(404, "Plantilla no encontrada")
    return t


@router.post("/custom-templates", response_model=TPRMTemplateOut, status_code=201)
def create_custom_template(body: TPRMTemplateCreate, db: Session = Depends(get_db),
                           current_user: User = Depends(require_analyst)):
    """Crea una plantilla editable, opcionalmente clonando una del sistema."""
    name = body.name
    description = body.description
    framework_codes = body.framework_codes
    questions = body.questions
    created_from = None
    if body.from_system_code:
        sys_tpl = tprm_templates.get_template(body.from_system_code)
        if not sys_tpl:
            raise HTTPException(404, "Plantilla del sistema no encontrada")
        created_from = sys_tpl["code"]
        name = name or f"{sys_tpl['name']} (copia)"
        description = description or sys_tpl.get("description")
        framework_codes = framework_codes or sys_tpl.get("framework_codes")
        # Copia profunda de las preguntas para poder editarlas sin afectar al original
        questions = questions if questions is not None else [dict(q) for q in sys_tpl["questions"]]
    if not name:
        raise HTTPException(400, "El nombre es obligatorio")
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
def update_custom_template(tid: int, body: TPRMTemplateUpdate, db: Session = Depends(get_db),
                           current_user: User = Depends(require_analyst)):
    t = db.query(TPRMTemplate).filter(TPRMTemplate.id == tid).first()
    if not t or not check_org_access(t.organization_id, current_user):
        raise HTTPException(404, "Plantilla no encontrada")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(t, field, value)
    db.commit()
    db.refresh(t)
    log_action(db, current_user.id, "update", "tprm_template", str(t.id))
    return t


@router.delete("/custom-templates/{tid}", status_code=204)
def delete_custom_template(tid: int, db: Session = Depends(get_db),
                           current_user: User = Depends(require_analyst)):
    t = db.query(TPRMTemplate).filter(TPRMTemplate.id == tid).first()
    if not t or not check_org_access(t.organization_id, current_user):
        raise HTTPException(404, "Plantilla no encontrada")
    log_action(db, current_user.id, "delete", "tprm_template", str(tid), {"name": t.name})
    db.delete(t)
    db.commit()
