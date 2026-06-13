"""Evaluaciones consolidadas de riesgo de proveedor — TPRM Sprint 4."""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, Risk, RiskStatus, Supplier, Threat, User, VendorRiskAssessment
from app.schemas import VendorAssessmentCreate, VendorAssessmentOut, VendorAssessmentUpdate
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action
from app.services import tprm_scoring_service
from app.services.vendor_assessment_service import build_assessment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vendor-assessments", tags=["vendor-assessments"])


def _next_code(db: Session, org_id: int) -> str:
    """Genera codigo unico VAS-NNNN para la organizacion."""
    n = db.query(VendorRiskAssessment).filter(
        VendorRiskAssessment.organization_id == org_id
    ).count() + 1
    code = f"VAS-{n:04d}"
    while db.query(VendorRiskAssessment).filter_by(code=code).first():
        n += 1
        code = f"VAS-{n:04d}"
    return code


# ---------- Mapeo residual score (0-100) -> likelihood/consequence (0-4) ----------

def _score_to_likelihood_consequence(residual_score: int) -> tuple[int, int]:
    """Convierte residual_risk_score a likelihood y consequence para ISO 27005 Annex E.2."""
    if residual_score >= 75:
        return 4, 4
    if residual_score >= 50:
        return 4, 3
    if residual_score >= 25:
        return 3, 3
    return 2, 2


# ---------- Endpoints ----------

@router.get("/", response_model=list[VendorAssessmentOut])
def list_assessments(
    supplier_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = filter_by_org(db.query(VendorRiskAssessment), VendorRiskAssessment, current_user)
    if supplier_id is not None:
        query = query.filter(VendorRiskAssessment.supplier_id == supplier_id)
    return query.order_by(VendorRiskAssessment.created_at.desc()).all()


@router.get("/{aid}", response_model=VendorAssessmentOut)
def get_assessment(
    aid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Evaluacion no encontrada")
    return a


@router.post("/", response_model=VendorAssessmentOut, status_code=201)
def create_assessment(
    body: VendorAssessmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    org_id = current_user.organization_id

    # Verificar proveedor
    supplier = db.query(Supplier).filter(Supplier.id == body.supplier_id).first()
    if not supplier or not check_org_access(supplier.organization_id, current_user):
        raise HTTPException(404, "Proveedor no encontrado")

    # Calcular scores mediante el servicio
    scores = build_assessment(db, supplier, body.questionnaire_ids)

    code = _next_code(db, org_id)

    a = VendorRiskAssessment(
        organization_id=org_id,
        code=code,
        supplier_id=body.supplier_id,
        period_label=body.period_label,
        summary=body.summary,
        recommendation=body.recommendation,
        valid_until=body.valid_until,
        questionnaire_ids=body.questionnaire_ids,
        assessor_user_id=current_user.id,
        created_by_id=current_user.id,
        # Scores calculados
        inherent_risk_score=scores["inherent_risk_score"],
        inherent_risk_level=scores["inherent_risk_level"],
        control_effectiveness_score=scores["control_effectiveness_score"],
        residual_risk_score=scores["residual_risk_score"],
        residual_risk_level=scores["residual_risk_level"],
        score_by_domain=scores["score_by_domain"],
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    log_action(
        db, current_user.id, "create", "vendor_assessment", str(a.id),
        {"code": a.code, "supplier_id": a.supplier_id},
    )
    return a


@router.patch("/{aid}", response_model=VendorAssessmentOut)
def update_assessment(
    aid: int,
    body: VendorAssessmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Evaluacion no encontrada")

    changes = body.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(a, field, value)

    # Si cambia control_effectiveness, recomputar residual
    if "control_effectiveness_score" in changes and a.inherent_risk_score is not None:
        a.residual_risk_score = tprm_scoring_service.compute_residual_risk(
            a.inherent_risk_score, a.control_effectiveness_score
        )
        a.residual_risk_level = tprm_scoring_service.risk_level_label(a.residual_risk_score)

    db.commit()
    db.refresh(a)
    log_action(db, current_user.id, "update", "vendor_assessment", str(a.id))
    return a


@router.delete("/{aid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assessment(
    aid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Evaluacion no encontrada")
    log_action(db, current_user.id, "delete", "vendor_assessment", str(aid), {"code": a.code})
    db.delete(a)
    db.commit()


@router.post("/{aid}/approve", response_model=VendorAssessmentOut)
def approve_assessment(
    aid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Evaluacion no encontrada")
    a.approver_user_id = current_user.id
    a.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(a)
    log_action(db, current_user.id, "approve", "vendor_assessment", str(a.id), {"code": a.code})
    return a


@router.post("/{aid}/push-to-risk-register")
def push_to_risk_register(
    aid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Crea un riesgo ISO 27005 en el registro a partir de la evaluacion consolidada."""
    a = db.query(VendorRiskAssessment).filter(VendorRiskAssessment.id == aid).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Evaluacion no encontrada")

    # Si ya tiene riesgo vinculado, devolverlo
    if a.linked_risk_id:
        existing_risk = db.query(Risk).filter(Risk.id == a.linked_risk_id).first()
        if existing_risk:
            return {"risk_id": existing_risk.id, "risk_code": existing_risk.code}

    org_id = a.organization_id

    # Activo mas critico de la organizacion (igual que _auto_create_supplier_risk)
    asset = (
        db.query(Asset)
        .filter(Asset.organization_id == org_id)
        .order_by(Asset.value_confidentiality.desc(), Asset.id)
        .first()
    )
    if not asset:
        raise HTTPException(
            409,
            "No hay activos registrados en la organizacion. "
            "Registra al menos un activo antes de enviar al registro de riesgos.",
        )

    # Amenaza de cadena de suministro (igual que _auto_create_supplier_risk)
    threat = (
        db.query(Threat)
        .filter(
            Threat.name.ilike("%supply%")
            | Threat.name.ilike("%suministro%")
            | Threat.name.ilike("%proveedor%")
            | Threat.name.ilike("%third party%")
            | Threat.category.ilike("%supply%")
        )
        .first()
    )
    if not threat:
        threat = db.query(Threat).filter(Threat.category.ilike("%organiz%")).first()
    if not threat:
        raise HTTPException(
            409,
            "No se encontro una amenaza de cadena de suministro en el catalogo. "
            "Verifica que el catalogo ISO 27005 este cargado correctamente.",
        )

    # Deduplicar por activo + amenaza
    existing = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.asset_id == asset.id,
        Risk.threat_id == threat.id,
    ).first()
    if existing:
        # Vincular y devolver el existente
        a.linked_risk_id = existing.id
        db.commit()
        return {"risk_id": existing.id, "risk_code": existing.code}

    # Mapear residual score a escala ISO 27005 Annex E.2
    residual_score = a.residual_risk_score or 0
    likelihood, consequence = _score_to_likelihood_consequence(residual_score)
    inherent_level = likelihood + consequence

    # Generar codigo RSK-NNNN unico
    count = db.query(Risk).filter(Risk.organization_id == org_id).count()
    code = f"RSK-{count + 1:04d}"
    while db.query(Risk).filter_by(code=code).first():
        count += 1
        code = f"RSK-{count + 1:04d}"

    supplier_name = a.supplier_name or f"Proveedor #{a.supplier_id}"
    risk = Risk(
        organization_id=org_id,
        code=code,
        asset_id=asset.id,
        threat_id=threat.id,
        description=(
            f"Riesgo de cadena de suministro generado desde evaluacion consolidada.\n"
            f"Proveedor: {supplier_name} — Evaluacion: {a.code}.\n"
            f"Riesgo inherente: {a.inherent_risk_score}/100 ({a.inherent_risk_level}). "
            f"Riesgo residual: {a.residual_risk_score}/100 ({a.residual_risk_level})."
        ),
        inherent_likelihood=likelihood,
        inherent_consequence=consequence,
        inherent_level=inherent_level,
        residual_likelihood=likelihood,
        residual_consequence=consequence,
        residual_level=inherent_level,
        status=RiskStatus.IDENTIFIED,
        owner_id=current_user.id,
        ai_generated=False,
    )
    db.add(risk)
    db.flush()  # obtener risk.id sin cerrar la transaccion

    a.linked_risk_id = risk.id
    db.commit()
    logger.info(
        "Push-to-register: riesgo %s (level=%d) creado desde evaluacion %s",
        code, inherent_level, a.code,
    )
    return {"risk_id": risk.id, "risk_code": risk.code}
