"""Servicio de construccion de evaluaciones consolidadas de proveedores (TPRM §2.1)."""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Supplier, SupplierQuestionnaire
from app.services import tprm_scoring_service
from app.services.tprm_scoring_service import compute_residual_risk, risk_level_label

logger = logging.getLogger("riskhub.vendor_assessment_service")


def build_assessment(
    db: Session,
    supplier: Supplier,
    questionnaire_ids: Optional[list[int]],
) -> dict:
    """Calcula scores consolidados para una evaluacion de proveedor.

    Devuelve dict con inherent_risk_score, inherent_risk_level,
    control_effectiveness_score, residual_risk_score, residual_risk_level,
    score_by_domain.
    """
    # 1. Riesgo inherente
    inherent = supplier.inherent_risk_score
    if inherent is None:
        inherent = tprm_scoring_service.compute_inherent_risk(supplier)

    # 2. Cuestionarios a incluir en la evaluacion
    q_query = (
        db.query(SupplierQuestionnaire)
        .filter(
            SupplierQuestionnaire.supplier_id == supplier.id,
            SupplierQuestionnaire.submitted_at.isnot(None),
        )
    )
    if questionnaire_ids:
        q_query = q_query.filter(SupplierQuestionnaire.id.in_(questionnaire_ids))
    questionnaires = q_query.all()

    # 3. Eficacia de controles: media de scores de cuestionarios enviados
    if questionnaires and any(q.score is not None for q in questionnaires):
        scores = [q.score for q in questionnaires if q.score is not None]
        control_effectiveness = int(round(sum(scores) / len(scores)))
    else:
        # Fallback a la postura conocida del proveedor
        control_effectiveness = supplier.control_effectiveness
        if control_effectiveness is None:
            control_effectiveness = supplier.score if supplier.score is not None else 0
    control_effectiveness = max(0, min(100, int(control_effectiveness)))

    # 4. Riesgo residual
    residual = compute_residual_risk(inherent, control_effectiveness)

    # 5. Score por dominio: agrupar by_question por el campo "domain" de cada pregunta
    score_by_domain: dict[str, list[float]] = {}
    for q in questionnaires:
        questions = q.questions or []
        answers = q.answers or {}
        if not questions:
            continue
        try:
            result = tprm_scoring_service.score_questionnaire(questions, answers)
            by_question = result.get("by_question", {})
        except Exception as exc:
            logger.warning("score_questionnaire fallo para cuestionario %d: %s", q.id, exc)
            continue
        for question in questions:
            qid = question.get("id")
            domain = question.get("domain") or "general"
            sc = by_question.get(qid)
            if sc is not None:
                score_by_domain.setdefault(domain, []).append(float(sc))

    # Promediar scores por dominio -> entero 0-100
    domain_averages: dict[str, int] = {}
    for domain, values in score_by_domain.items():
        if values:
            domain_averages[domain] = int(round(sum(values) / len(values)))

    return {
        "inherent_risk_score": inherent,
        "inherent_risk_level": risk_level_label(inherent),
        "control_effectiveness_score": control_effectiveness,
        "residual_risk_score": residual,
        "residual_risk_level": risk_level_label(residual),
        "score_by_domain": domain_averages,
    }
