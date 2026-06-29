"""CRUD de riesgos + calculo automatico inherente/residual + tratamiento."""
import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Asset, AssetGroup, ControlImplementation, Risk, RiskContext, RiskStatus,
    Threat, TreatmentOption, User, Vulnerability, risk_control_table,
)
from app.schemas import RiskIn, RiskOut, RiskUpdate
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action
from app.services.risk_engine import (
    calc_level, calc_residual,
    calc_consequence_magerit, primary_dimension_for_threat, MAGERIT_DIM_FIELD,
)
from app.i18n import get_lang, t as _t

router = APIRouter(prefix="/api/risks", tags=["risks"])


def _next_code(db: Session, org_id: int) -> str:
    from sqlalchemy import func as _func
    max_id = db.query(_func.max(Risk.id)).scalar() or 0
    return f"RSK-{max_id + 1:04d}"


def _get_context(db: Session, org_id=None) -> RiskContext | None:
    q = db.query(RiskContext)
    if org_id:
        q = q.filter(RiskContext.organization_id == org_id)
    return q.first()


def _get_matrix(db: Session, org_id=None):
    ctx = _get_context(db, org_id)
    return ctx.risk_matrix if ctx and ctx.risk_matrix else None


def _apply_magerit_consequence(risk: Risk, db: Session) -> None:
    """Si la metodologia del contexto es magerit|combined y el riesgo tiene
    dimension + degradacion, recalcula inherent_consequence desde el activo."""
    if not risk.asset_id:
        return
    ctx = _get_context(db, risk.organization_id)
    if not ctx or ctx.methodology not in ("magerit", "combined"):
        return
    if risk.degradation_pct is None:
        return

    asset = db.get(Asset, risk.asset_id)
    if not asset:
        return

    # Determinar dimension primaria si no esta guardada
    if not risk.magerit_dimension:
        threat = db.get(Threat, risk.threat_id)
        affects = getattr(threat, "affects", None) or []
        risk.magerit_dimension = primary_dimension_for_threat(affects, asset)

    # Calcular consecuencia MAGERIT
    field = MAGERIT_DIM_FIELD.get(risk.magerit_dimension, "value_availability")
    dim_value = getattr(asset, field, 0) or 0
    consequence, magerit_impact = calc_consequence_magerit(dim_value, risk.degradation_pct)
    risk.inherent_consequence = consequence
    risk.magerit_impact = magerit_impact


def _recalc(db: Session, risk: Risk) -> None:
    from sqlalchemy import text as _text
    matrix = _get_matrix(db, risk.organization_id)

    # MAGERIT: si aplica, sobrescribir inherent_consequence antes de calcular
    _apply_magerit_consequence(risk, db)

    risk.inherent_level = calc_level(
        risk.inherent_consequence, risk.inherent_likelihood, matrix)

    # Obtener contribution real de la tabla de asociacion (no hardcoded 1.0)
    rows = db.execute(
        _text("SELECT control_implementation_id, contribution FROM risk_controls WHERE risk_id = :rid"),
        {"rid": risk.id},
    ).fetchall()
    contrib_map = {row[0]: (row[1] if row[1] is not None else 1.0) for row in rows}

    controls = [
        {
            "maturity": ci.maturity or 0,
            "contribution": contrib_map.get(ci.id, 1.0),
            "nc_penalty_factor": getattr(ci, "nc_penalty_factor", None),
            "ccm_fail": getattr(ci, "ccm_last_status", None) == "FAIL",
        }
        for ci in risk.controls
    ]
    rl, rc, rlev = calc_residual(
        risk.inherent_likelihood, risk.inherent_consequence, controls, matrix)

    # Floor por controles obligatorios con madurez insuficiente (ISO 27001 Annex A)
    # Si algun control IS_MANDATORY tiene maturity < 2, el residual no puede ser
    # menor que inherent - 1 (los controles deficientes limitan la reduccion alcanzable)
    mandatory_gap = any(
        (ci.control.is_mandatory if ci.control else False) and (ci.maturity or 0) < 2
        for ci in risk.controls
    )
    if mandatory_gap:
        min_lik = max(0, (risk.inherent_likelihood or 0) - 1)
        min_con = max(0, (risk.inherent_consequence or 0) - 1)
        rl = max(rl, min_lik)
        rc = max(rc, min_con)
        rlev = calc_level(rc, rl, matrix)

    risk.residual_likelihood = rl
    risk.residual_consequence = rc
    risk.residual_level = rlev

    # Auto-tratamiento basado en apetito de riesgo
    ctx = _get_context(db, risk.organization_id)
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3
    if rlev <= appetite and risk.status not in (RiskStatus.CLOSED, RiskStatus.PENDING_ACCEPTANCE):
        if risk.treatment_option in (None, TreatmentOption.MODIFICATION, TreatmentOption.RETENTION):
            risk.treatment_option = TreatmentOption.RETENTION
            if risk.status in (RiskStatus.IDENTIFIED, RiskStatus.ASSESSED):
                risk.status = RiskStatus.ACCEPTED
                # Riesgos aceptados deben revisarse anualmente (ISO 27001 A.6.1.2)
                from datetime import timedelta
                risk.next_review = datetime.now(timezone.utc) + timedelta(days=365)


@router.get("/group-summary")
def risks_group_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve estadisticas de riesgos por grupo para la vista 'Por grupo'."""
    org_id = current_user.organization_id

    # Grupos de la org con sus miembros
    groups = db.query(AssetGroup).filter_by(organization_id=org_id).order_by(
        AssetGroup.status, AssetGroup.name
    ).all()

    result = []
    for grp in groups:
        member_ids = [
            a.id for a in db.query(Asset.id).filter_by(
                group_id=grp.id, is_group_representative=False
            ).all()
        ]
        if not member_ids:
            continue
        risks = db.query(
            Risk.residual_level, Risk.status, Risk.treatment_option
        ).filter(
            Risk.asset_id.in_(member_ids),
            Risk.organization_id == org_id,
        ).all()

        total = len(risks)
        max_res = max((r.residual_level or 0 for r in risks), default=0)
        high = sum(1 for r in risks if (r.residual_level or 0) >= 6)
        critical = sum(1 for r in risks if (r.residual_level or 0) >= 7)

        result.append({
            "group_id": grp.id,
            "group_name": grp.name,
            "group_status": grp.status.value if grp.status else "proposed",
            "member_count": len(member_ids),
            "risk_count": total,
            "max_residual": max_res,
            "high_count": high,
            "critical_count": critical,
        })

    # Activos sin grupo
    ungrouped_ids = [
        a.id for a in db.query(Asset.id).filter(
            Asset.organization_id == org_id,
            Asset.is_group_representative.is_(False),
            Asset.group_id.is_(None),
        ).all()
    ]
    ung_risks = db.query(
        Risk.residual_level, Risk.status
    ).filter(
        Risk.asset_id.in_(ungrouped_ids),
        Risk.organization_id == org_id,
    ).all() if ungrouped_ids else []

    result.append({
        "group_id": None,
        "group_name": "Sin grupo",
        "group_status": "none",
        "member_count": len(ungrouped_ids),
        "risk_count": len(ung_risks),
        "max_residual": max((r.residual_level or 0 for r in ung_risks), default=0),
        "high_count": sum(1 for r in ung_risks if (r.residual_level or 0) >= 6),
        "critical_count": sum(1 for r in ung_risks if (r.residual_level or 0) >= 7),
    })

    return result


@router.get("/", response_model=list[RiskOut])
def list_risks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    asset_id: Optional[int] = None,
    threat_id: Optional[int] = None,
    vulnerability_id: Optional[int] = None,
    status: Optional[RiskStatus] = None,
    min_level: Optional[int] = Query(None, ge=0, le=8),
    overdue: Optional[bool] = None,
    owner_id: Optional[int] = None,
    treatment: Optional[str] = None,
    group_id: Optional[int] = Query(None, description="-1 = sin grupo, >0 = grupo especifico"),
    supplier_only: Optional[bool] = Query(None, description="True = solo riesgos originados en TPRM"),
):
    now = datetime.now(timezone.utc)
    q = filter_by_org(db.query(Risk), Risk, current_user)
    if asset_id:
        q = q.filter(Risk.asset_id == asset_id)
    if group_id is not None:
        # Filtra por grupo via JOIN con Asset
        q = q.join(Asset, Risk.asset_id == Asset.id)
        if group_id < 0:
            q = q.filter(Asset.group_id.is_(None))  # sin grupo
        else:
            q = q.filter(Asset.group_id == group_id)
    if threat_id:
        q = q.filter(Risk.threat_id == threat_id)
    if vulnerability_id:
        from app.models import risk_vulnerability_table
        vuln_risk_ids = db.query(risk_vulnerability_table.c.risk_id).filter(
            risk_vulnerability_table.c.vulnerability_id == vulnerability_id
        ).subquery()
        q = q.filter(Risk.id.in_(vuln_risk_ids))
    if status:
        q = q.filter(Risk.status == status)
    if min_level is not None:
        q = q.filter(Risk.residual_level >= min_level)
    if overdue:
        active = [RiskStatus.IDENTIFIED, RiskStatus.ASSESSED]
        q = q.filter(
            Risk.status.in_(active),
            Risk.treatment_due_date.isnot(None),
            Risk.treatment_due_date < now,
        )
    if owner_id is not None:
        q = q.filter(Risk.owner_id == owner_id)
    if treatment:
        if treatment == "__none__":
            q = q.filter(Risk.treatment_option.is_(None))
        else:
            q = q.filter(Risk.treatment_option == treatment)
    if supplier_only:
        q = q.filter(Risk.supplier_id.isnot(None))
    return q.order_by(Risk.residual_level.desc(), Risk.code).all()


@router.get("/methodology")
def get_methodology(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve la metodologia activa y sus metadatos (para el formulario de riesgos)."""
    from app.services.risk_engine import MAGERIT_DIMENSIONS, MAGERIT_FREQ_LABELS
    ctx = _get_context(db, current_user.organization_id)
    methodology = ctx.methodology if ctx and ctx.methodology else "iso27005"
    risk_appetite = (ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3)
    return {
        "methodology": methodology,
        "magerit_dimensions": MAGERIT_DIMENSIONS,
        "magerit_freq_labels": MAGERIT_FREQ_LABELS,
        "risk_appetite": risk_appetite,
    }


@router.get("/{risk_id}", response_model=RiskOut)
def get_risk(risk_id: int, request: Request, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    lang = get_lang(request)
    r = db.get(Risk, risk_id)
    if not r or not check_org_access(r.organization_id, current_user):
        raise HTTPException(404, _t("risks.not_found", lang))
    return r


@router.get("/{risk_id}/trace")
def risk_trace(
    risk_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trazabilidad completa: desglosa cada control vinculado al riesgo con
    cálculo de eficacia, madurez, fuentes de evidencia y referencias SOA.
    Crítico para justificar el nivel residual ante una auditoría ISO 27001."""
    from sqlalchemy import select
    from app.models import Evidence, risk_control_table
    from app.services.risk_engine import control_reduction, LIKELIHOOD_LABELS, CONSEQUENCE_LABELS

    lang = get_lang(request)
    r = db.get(Risk, risk_id)
    if not r or not check_org_access(r.organization_id, current_user):
        raise HTTPException(404, _t("risks.not_found", lang))

    # --- Leer controles vinculados con su contribution ---
    rows = db.execute(
        select(
            risk_control_table.c.control_implementation_id,
            risk_control_table.c.contribution,
        ).where(risk_control_table.c.risk_id == risk_id)
    ).all()

    def _maturity_label(m: int) -> str:
        return {0: "Inexistente", 1: "Inicial / ad-hoc", 2: "Básico / documentado",
                3: "Definido / aplicado", 4: "Gestionado / medido", 5: "Optimizado / continuo"}.get(m, str(m))

    def _maturity_why(m: int, status: str, name: str) -> str:
        base = {
            0: f"El control '{name}' no existe o no está configurado. Eficacia nula — no reduce el riesgo.",
            1: f"'{name}' existe de forma ad-hoc pero sin proceso formal. Reducción mínima e inconsistente.",
            2: f"'{name}' está documentado y tiene aplicación básica. Reduce el riesgo de forma parcial.",
            3: f"'{name}' está definido, documentado y aplicado sistemáticamente. Reducción sustancial.",
            4: f"'{name}' se mide y gestiona activamente. Alta eficacia y consistencia en la reducción.",
            5: f"'{name}' está completamente optimizado con mejora continua. Máxima eficacia posible.",
        }.get(m, "")
        if status == "partial":
            base += " (implementación parcial — la eficacia está limitada por la cobertura incompleta)."
        elif status == "planned":
            base += " (solo planificado — no aporta reducción real hasta su implementación)."
        elif status == "not_implemented":
            base = f"El control '{name}' no está implementado. No aporta reducción al nivel residual."
        return base

    controls_trace = []
    ctrl_dicts_for_engine = []

    for row in rows:
        impl = db.get(ControlImplementation, row.control_implementation_id)
        if not impl:
            continue
        mat = impl.maturity or 0
        contrib = float(row.contribution) if row.contribution is not None else 1.0
        efficacy = (mat / 5.0) * contrib

        # Evidencias del fichero Evidence vinculadas a este control
        evd_files = db.query(Evidence).filter(
            Evidence.control_implementation_id == impl.id,
            Evidence.is_current.is_(True),
        ).all()

        controls_trace.append({
            "id": impl.id,
            "name": impl.name,
            "code": impl.control.code if impl.control else None,
            "theme": impl.control.theme if impl.control else None,
            "status": impl.status.value if impl.status else "not_implemented",
            "maturity": mat,
            "maturity_label": _maturity_label(mat),
            "maturity_why": _maturity_why(mat, impl.status.value if impl.status else "not_implemented", impl.name),
            "contribution": round(contrib, 3),
            "efficacy": round(efficacy, 3),
            "efficacy_pct": round(efficacy * 100),
            "inclusion_reason": impl.inclusion_reason,
            "evidence_refs": impl.evidence_refs or [],
            "evidence_files": [
                {
                    "id": e.id, "code": e.code, "title": e.title,
                    "type": e.evidence_type.value if e.evidence_type else None,
                    "valid_from": e.valid_from.isoformat() if e.valid_from else None,
                    "expires_at": e.expires_at.isoformat() if e.expires_at else None,
                    "compliance_framework": e.compliance_framework,
                    "compliance_requirement": e.compliance_requirement,
                }
                for e in evd_files
            ],
            "notes": impl.notes,
            "soa_reviewed_at": impl.soa_reviewed_at.isoformat() if impl.soa_reviewed_at else None,
            "nc_penalty_factor": getattr(impl, "nc_penalty_factor", None),
            "ccm_fail": getattr(impl, "ccm_last_status", None) == "FAIL",
        })
        ctrl_dicts_for_engine.append({
            "maturity": mat,
            "contribution": contrib,
            "nc_penalty_factor": getattr(impl, "nc_penalty_factor", None),
            "ccm_fail": getattr(impl, "ccm_last_status", None) == "FAIL",
        })

    # --- Cálculo combinado ---
    from app.services.risk_engine import control_reduction
    combined_efficacy = control_reduction(ctrl_dicts_for_engine) if ctrl_dicts_for_engine else 0.0
    inh_lik = r.inherent_likelihood or 0
    inh_con = r.inherent_consequence or 0
    res_lik = max(0, min(4, round(inh_lik * (1.0 - combined_efficacy))))
    res_con = max(0, min(4, round(inh_con * (1.0 - 0.5 * combined_efficacy))))

    # --- Evidencia directamente vinculada al riesgo ---
    direct_evd = db.query(Evidence).filter(
        Evidence.risk_id == risk_id,
        Evidence.is_current.is_(True),
    ).all()

    # --- Vulnerabilidades ---
    vulns_info = [
        {"id": v.id, "code": v.code, "name": v.name,
         "description": v.description, "category": v.category}
        for v in (r.vulnerabilities or [])
    ]

    appetite = (db.query(RiskContext).filter_by(organization_id=r.organization_id).first() or RiskContext()).risk_appetite or 3

    return {
        "risk_id": r.id,
        "code": r.code,
        "inherent_likelihood": inh_lik,
        "inherent_consequence": inh_con,
        "inherent_level": r.inherent_level,
        "inherent_likelihood_label": LIKELIHOOD_LABELS[inh_lik] if 0 <= inh_lik <= 4 else str(inh_lik),
        "inherent_consequence_label": CONSEQUENCE_LABELS[inh_con] if 0 <= inh_con <= 4 else str(inh_con),
        "residual_likelihood": r.residual_likelihood,
        "residual_consequence": r.residual_consequence,
        "residual_level": r.residual_level,
        "residual_likelihood_label": LIKELIHOOD_LABELS[r.residual_likelihood or 0],
        "residual_consequence_label": CONSEQUENCE_LABELS[r.residual_consequence or 0],
        "combined_efficacy": round(combined_efficacy, 3),
        "combined_efficacy_pct": round(combined_efficacy * 100),
        "reduction_pct": round((1 - r.residual_level / r.inherent_level) * 100) if r.inherent_level else 0,
        "above_appetite": (r.residual_level or 0) > appetite,
        "appetite": appetite,
        "calculation_formula": (
            f"Eficacia combinada = 1 − ∏(1 − eficacia_i) = {round(combined_efficacy*100)}%\n"
            f"Prob. residual = round({inh_lik} × (1 − {round(combined_efficacy,2)})) = {res_lik}\n"
            f"Cons. residual = round({inh_con} × (1 − 0.5 × {round(combined_efficacy,2)})) = {res_con}\n"
            f"Nivel residual = matriz[{res_con}][{res_lik}] = {r.residual_level}"
        ),
        "controls": controls_trace,
        "vulnerabilities": vulns_info,
        "evidence_direct": [
            {"id": e.id, "code": e.code, "title": e.title,
             "type": e.evidence_type.value if e.evidence_type else None,
             "expires_at": e.expires_at.isoformat() if e.expires_at else None}
            for e in direct_evd
        ],
    }


@router.post("/{risk_id}/ai-explain")
def risk_ai_explain(
    risk_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera una explicación experta del riesgo usando el modelo IA + RAG sobre documentos.

    Utiliza toda la información disponible: activo, amenaza, vulnerabilidades,
    controles con madurez, evidencias, contexto del cuestionario y documentación
    interna indexada. Devuelve un análisis riguroso como lo haría un auditor ISO 27001.
    """
    from app.models import AiConfig, AiCallLog, Evidence, risk_control_table
    from app.security import filter_by_org
    from app.services.rag_service import search_chunks_with_source
    from app.services.risk_engine import LIKELIHOOD_LABELS, CONSEQUENCE_LABELS
    from sqlalchemy import select
    import json as _json

    lang = get_lang(request)
    r = db.get(Risk, risk_id)
    if not r or not check_org_access(r.organization_id, current_user):
        raise HTTPException(404, _t("risks.not_found", lang))

    # Resolver API key
    cfg = db.query(AiConfig).filter_by(organization_id=current_user.organization_id).first()
    def _resolve_key(cfg):
        if cfg and cfg.api_key_encrypted:
            import base64, hashlib
            from cryptography.fernet import Fernet
            from app.config import settings
            key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
            try:
                return Fernet(key).decrypt(cfg.api_key_encrypted.encode()).decode()
            except Exception:
                return None
        from app.config import settings
        return settings.anthropic_api_key
    api_key = _resolve_key(cfg)
    if not api_key:
        raise HTTPException(400, "API key no configurada. Ve a Configuración > Agente IA.")
    model = (cfg.model if cfg else None) or "claude-opus-4-6"

    from app.services.risk_analysis_helpers import (
        get_asset_profile, build_vuln_section, build_control_section,
        build_document_coverage_section, threat_actor_profile, normative_context,
        LIKELIHOOD_CRITERIA, CONSEQUENCE_CRITERIA, classify_control, evidence_quality_score,
        adjusted_maturity, CONTROL_TYPE_LABELS, build_vigilancia_context,
    )

    # Contexto organizacional
    ctx = db.query(RiskContext).filter_by(organization_id=current_user.organization_id).first()
    qa = (ctx.questionnaire_answers or {}) if ctx else {}
    frameworks = (ctx.active_frameworks or []) if ctx else []
    risk_appetite = (ctx.risk_appetite or 4) if ctx else 4

    # Perfil del tipo de activo
    asset_type_raw = r.asset.asset_type.value if r.asset and r.asset.asset_type else "unknown"
    asset_profile = get_asset_profile(asset_type_raw)

    # Controles con datos enriquecidos
    rows = db.execute(
        select(risk_control_table.c.control_implementation_id, risk_control_table.c.contribution)
        .where(risk_control_table.c.risk_id == risk_id)
    ).all()
    ctrl_rows = []
    for row in rows:
        impl = db.get(ControlImplementation, row.control_implementation_id)
        if not impl:
            continue
        mat = impl.maturity or 0
        contrib = float(row.contribution) if row.contribution is not None else 1.0
        refs = impl.evidence_refs or []
        ev_factor, ev_desc = evidence_quality_score(refs)
        adj_mat = adjusted_maturity(mat, refs)
        evd_count = db.query(Evidence).filter_by(control_implementation_id=impl.id, is_current=True).count()
        ctrl_rows.append({
            "id": impl.id,
            "code": impl.control.code if impl.control else "?",
            "name": impl.name,
            "status": impl.status.value if impl.status else "N/A",
            "maturity": mat,
            "adj_maturity": adj_mat,
            "contribution": contrib,
            "efficacy_pct": round(adj_mat / 5.0 * contrib * 100),
            "evidence_refs": refs,
            "evidence_quality": ev_desc,
            "evidence_file_count": evd_count,
            "inclusion_reason": impl.inclusion_reason or "",
        })

    # Vulnerabilidades enriquecidas
    vuln_section = build_vuln_section(r.vulnerabilities or [])

    # Seccion de controles enriquecida
    ctrl_section = build_control_section(ctrl_rows)

    # Trazabilidad documental
    doc_coverage = build_document_coverage_section(ctrl_rows, [])

    # Perfil del agente de amenaza
    threat_origin_val = r.threat.origin.value if r.threat and r.threat.origin else "desconocido"
    actor_profile = threat_actor_profile(threat_origin_val, r.threat.category if r.threat else "")

    # Criterios de nivel
    lik_criterion = LIKELIHOOD_CRITERIA.get(r.inherent_likelihood, "")
    con_criterion = CONSEQUENCE_CRITERIA.get(r.inherent_consequence, "")

    # Contexto normativo
    norm_ctx = normative_context(frameworks)

    # Evidencia real de Vigilancia (OSINT, CVE, Regwatch)
    vuln_ids = [v.id for v in (r.vulnerabilities or [])]
    impl_ids = [c["id"] for c in ctrl_rows]
    vigilancia_section = build_vigilancia_context(
        db, r.asset_id, vuln_ids, impl_ids, current_user.organization_id
    )

    # RAG: query enriquecido con tipo de activo y categoria de amenaza
    asset_name = r.asset.name if r.asset else "activo"
    threat_name = r.threat.name if r.threat else "amenaza"
    threat_cat = r.threat.category if r.threat else ""
    rag_query = (
        f"{threat_name} {threat_cat} {asset_type_raw} "
        f"{' '.join(v.name for v in (r.vulnerabilities or []))} "
        f"controles mitigacion ISO 27002 {r.description or ''}"
    )
    rag_chunks = search_chunks_with_source(db, rag_query, top_k=6, organization_id=current_user.organization_id)
    rag_section = ""
    if rag_chunks:
        rag_section = "\n\n=== DOCUMENTACION INTERNA INDEXADA (RAG) ===\n" + "\n---\n".join(
            f"[{c['doc_name']}] (relevancia: {c.get('score', '?')}):\n{c['content'][:700]}"
            for c in rag_chunks
        )

    # Calculos derivados
    reduction_pct = round((1 - r.residual_level / r.inherent_level) * 100) if r.inherent_level else 0
    above_appetite = r.residual_level > risk_appetite
    cia_c = r.asset.value_confidentiality if r.asset else "N/A"
    cia_i = r.asset.value_integrity if r.asset else "N/A"
    cia_a = r.asset.value_availability if r.asset else "N/A"

    prompt = f"""Eres un auditor senior de seguridad de la informacion con:
- Certificaciones CISSP, CISM, ISO 27001 Lead Auditor, ISO 27005 Risk Manager
- Especializacion en analisis cuantitativo y cualitativo de riesgos segun ISO/IEC 27005:2018
- Conocimiento profundo de ISO 27001/27002:2022, MAGERIT v3, NIST CSF 2.0, ENS, DORA, NIS2, GDPR

Tu analisis debe ser DEFENSIBLE ante un auditor externo y ante la direccion de la compania.
Cada afirmacion debe estar justificada con los datos exactos del riesgo analizado.
NUNCA hagas afirmaciones genericas. Si faltan datos criticos, explicalo y baja la confianza.

# ANALISIS DE RIESGO ISO 27005:2018 — {r.code}

## 1. ACTIVO A PROTEGER
- Nombre: {asset_name}
- Tipo: {asset_profile['label']}
- Dimensiones CIA: Confidencialidad={cia_c}/4, Integridad={cia_i}/4, Disponibilidad={cia_a}/4
- Dimensiones criticas para este tipo: {', '.join(asset_profile['primary_dimensions'])}
- Factores de riesgo tipicos de este tipo de activo: {asset_profile['key_risk_factors']}
- Controles ISO 27002 clave para este tipo: {', '.join(asset_profile['key_iso_controls'][:6])}

## 2. AMENAZA ANALIZADA
- [{r.threat.code if r.threat else '?'}] {threat_name}
- Origen: {threat_origin_val}
- Categoria ISO 27005: {threat_cat}
- Dimensiones afectadas: {', '.join(getattr(r.threat, 'affects', None) or [])}
- Activos tipicos objetivo: {', '.join(getattr(r.threat, 'typical_assets', None) or [])}
- Perfil del agente de amenaza: {actor_profile}

## 3. VULNERABILIDADES ASOCIADAS
{vuln_section}

## 4. ESCENARIO DE RIESGO (descripcion del analista)
- Descripcion: {r.description or 'Sin descripcion — ADVERTENCIA: scenario sin contexto especifico'}
- Consecuencia esperada: {r.consequence_description or 'Sin definir'}

## 5. METRICAS DE RIESGO (ISO 27005 Annex E.2 — matriz 5x5)
- Nivel INHERENTE: {r.inherent_level}/8
  - Probabilidad inherente: {r.inherent_likelihood}/4 — Criterio: {lik_criterion}
  - Consecuencia inherente: {r.inherent_consequence}/4 — Criterio: {con_criterion}
- Nivel RESIDUAL: {r.residual_level}/8
  - Probabilidad residual: {r.residual_likelihood}/4
  - Consecuencia residual: {r.residual_consequence}/4
- Reduccion lograda: {reduction_pct}%
- Apetito de riesgo organizacional: {risk_appetite}/8
- Estado vs. apetito: {'SUPERA EL APETITO — REQUIERE ACCION' if above_appetite else 'DENTRO DEL APETITO'}
- Tratamiento actual: {r.treatment_option.value if r.treatment_option else 'Sin definir'}
- Estado del riesgo: {r.status.value}

## 6. CONTROLES MITIGANTES VINCULADOS ({len(ctrl_rows)} controles)
{ctrl_section}

## 7. TRAZABILIDAD DOCUMENTAL (controles vs. documentacion org.)
{doc_coverage}

## 8. CONTEXTO ORGANIZACIONAL
- Sector: {qa.get('sector', 'N/A')} | Empleados: {qa.get('employees', 'N/A')}
- Sistemas en uso: {', '.join(qa.get('systems', [])) or 'N/A'}
- Tipos de datos procesados: {', '.join(qa.get('data_types', [])) or 'N/A'}
- Normativas activas: {', '.join(frameworks) or 'ISO 27001'}
- Madurez global declarada: {qa.get('maturity', 'N/A')}/5
- Acceso remoto: {qa.get('remote_access', 'N/A')}

## 9. CONTEXTO NORMATIVO ESPECIFICO
{norm_ctx}

## 10. EVIDENCIA REAL DE VIGILANCIA (OSINT / CVE / REGWATCH)
{vigilancia_section}
{rag_section}

---

# INSTRUCCIONES DE ANALISIS — SIGUE ESTOS PASOS EN ORDEN

Realiza el analisis en 6 pasos estructurados. Sé ESPECIFICO y usa los datos exactos del riesgo.
El resultado debe ser defensible ante un auditor externo.

PASO 1: Analiza el tipo de activo ({asset_profile['label']}) y su exposicion especifica a [{r.threat.code if r.threat else '?'}].
PASO 2: Evalua si la amenaza es creible. Si la seccion 10 tiene hallazgos OSINT o CVEs activos,
         la amenaza es REAL y comprobada, no teorica. Reflejalo en la credibilidad y en la probabilidad.
PASO 3: Traza la cadena causal amenaza→vulnerabilidad→impacto. Integra hallazgos de la seccion 10
         como evidencia tecnica real de la cadena de ataque (CVE especificos, brechas OSINT, etc.).
PASO 4: Analiza cada control: cobertura del ataque, madurez real ajustada por evidencia.
         Si algun control tiene cambio normativo pendiente (seccion 10 regwatch), su eficacia puede
         estar sobreestimada porque la norma que lo respalda ha cambiado.
PASO 5: Valida el nivel residual {r.residual_level}/8. CVEs activos en el activo elevan la probabilidad
         real respecto a lo declarado. Hallazgos OSINT sin remediar reducen la eficacia de controles.
PASO 6: Determina implicaciones normativas especificas ({', '.join(frameworks) or 'ISO 27001'}).

Responde con JSON valido sin texto fuera del JSON:
{{
  "executive_summary": "3-5 frases. Que es este riesgo, por que es relevante para esta organizacion concreta ({qa.get('sector','N/A')}), que lo hace critico o manejable segun el nivel {r.residual_level}/8. ESPECIFICO, nunca generico.",

  "asset_exposure_analysis": "Analisis del tipo de activo {asset_profile['label']} y su exposicion a [{r.threat.code if r.threat else '?'}]. Por que las dimensiones CIA de este activo son vulnerables a esta amenaza. Menciona las dimensiones primarias ({', '.join(asset_profile['primary_dimensions'])}) y su relacion con el impacto calculado.",

  "threat_credibility": {{
    "is_credible": true,
    "credibility_reason": "Justificacion especifica de por que esta amenaza es o no creible para este activo en el sector {qa.get('sector','N/A')}",
    "threat_actor_profile": "Descripcion del perfil del agente de amenaza para este escenario concreto",
    "frequency_assessment": "alta|media|baja",
    "frequency_justification": "Por que la probabilidad inherente es {r.inherent_likelihood}/4 para este tipo de activo y amenaza"
  }},

  "attack_chain": [
    {{
      "step": 1,
      "phase": "Reconocimiento|Acceso inicial|Ejecucion|Movimiento lateral|Exfiltracion|Impacto",
      "description": "Descripcion concreta del paso del ataque",
      "vulnerability_exploited": "Vulnerabilidad especifica que habilita este paso (si aplica)",
      "controls_covering": ["codigo-control-1", "codigo-control-2"],
      "coverage_quality": "completa|parcial|sin_cobertura",
      "gap": "Descripcion de la brecha si coverage_quality no es completa"
    }}
  ],

  "why_inherent_level": "Justificacion tecnica y especifica de Probabilidad={r.inherent_likelihood}/4 ('{lik_criterion}') x Consecuencia={r.inherent_consequence}/4 ('{con_criterion}') = Nivel Inherente {r.inherent_level}/8. Referencia al tipo de activo, sector y perfil de amenaza.",

  "control_effectiveness": [
    {{
      "control_code": "codigo ISO 27002",
      "control_name": "nombre del control",
      "control_type": "Preventivo|Detectivo|Correctivo",
      "attack_phase_covered": "fase del ataque que cubre",
      "declared_maturity": {r.inherent_level},
      "evidence_reliability": "alta|media|baja",
      "evidence_analysis": "Analisis critico: es la madurez declarada creible dado las evidencias documentales? Menciona documentos si los hay.",
      "actual_effectiveness": "estimacion real del aporte de este control a la reduccion del riesgo",
      "improvement_needed": "que falta para que este control sea mas efectivo"
    }}
  ],

  "missing_controls": [
    {{
      "iso27002_code": "X.XX",
      "name": "nombre del control faltante",
      "why_needed": "que paso del ataque quedaria cubierto y por que es necesario para este riesgo",
      "priority": "critica|alta|media|baja"
    }}
  ],

  "why_residual_level": "Explicacion tecnica de como los controles reducen el riesgo de {r.inherent_level} a {r.residual_level}. La reduccion del {reduction_pct}% esta justificada por controles con evidencia real o es solo declarativa? Sé critico si la evidencia es debil.",

  "evidence_quality_assessment": "Analisis critico de la calidad de las evidencias documentales de los controles vinculados. Cuales tienen evidencia solida (E4-E5) vs declarativa (E1-E2)? El nivel residual {r.residual_level}/8 es defendible ante un auditor externo?",

  "residual_risk_verdict": {{
    "is_within_appetite": {'true' if not above_appetite else 'false'},
    "action_required": "{'si' if above_appetite else 'no'}",
    "recommended_treatment": "retencion|reduccion|transferencia|evitacion",
    "priority": "critica|alta|media|baja",
    "justification": "Por que esta recomendacion de tratamiento es la mas adecuada para este riesgo concreto"
  }},

  "gaps_and_recommendations": [
    {{
      "gap": "descripcion especifica de la brecha identificada",
      "recommendation": "accion concreta y medible para cerrar la brecha",
      "iso27002_control": "codigo del control ISO 27002 si aplica",
      "normative_requirement": "requisito normativo especifico si aplica (ej: NIS2 Art.21, GDPR Art.32)",
      "effort": "alto|medio|bajo",
      "impact_on_residual_risk": "alto|medio|bajo"
    }}
  ],

  "soa_implications": "Controles ISO 27002:2022 que deben incluirse en el SOA por este riesgo, cuales estan justificados para inclusion y cuales podrian excluirse. Especifica si hay controles del catalogo de la organizacion que deberian vincularse pero no estan.",

  "normative_alignment": {{
    {chr(10).join(f'"{"_".join(fw.lower().split())}": "implicaciones especificas de {fw} para este riesgo",' for fw in (frameworks or ['iso27001']))}
    "key_requirements": "requisitos normativos mas urgentes que aplican a este riesgo especifico"
  }},

  "confidence": "alta|media|baja",
  "confidence_reason": "Por que la confianza en el analisis es alta/media/baja",
  "data_quality_issues": ["Lista de datos faltantes o inconsistentes que limitan la fiabilidad del analisis"]
}}"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=16384,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```", 2)
            inner = parts[1] if len(parts) > 1 else raw
            if inner.startswith("json"):
                inner = inner[4:]
            raw = inner.rsplit("```", 1)[0].strip()
        result = _json.loads(raw)
    except Exception as exc:
        raise HTTPException(500, f"Error en el análisis IA: {exc}")

    # Log tokens
    tokens_in = response.usage.input_tokens if response.usage else 0
    tokens_out = response.usage.output_tokens if response.usage else 0
    log = AiCallLog(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        call_type="risk_explain",
        prompt_tokens=tokens_in,
        completion_tokens=tokens_out,
        model=model,
        anonymized=False,
        response_summary=f"Risk explain {r.code}: conf={result.get('confidence','?')}",
    )
    db.add(log)
    db.commit()

    return result


@router.post("/", response_model=RiskOut, status_code=201)
def create_risk(data: RiskIn, request: Request, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    asset = db.get(Asset, data.asset_id)
    if not asset or not check_org_access(asset.organization_id, current_user):
        raise HTTPException(400, _t("assets.not_found", lang))
    if not db.get(Threat, data.threat_id):
        raise HTTPException(400, _t("risks.threat_not_found", lang))
    # Deteccion de duplicado: mismo asset + amenaza en la org (v1.7.7)
    if hasattr(data, 'asset_id') and hasattr(data, 'threat_id') and data.asset_id and data.threat_id:
        from app.models import Risk as _Risk
        existing_dup = db.query(_Risk).filter(
            _Risk.asset_id == data.asset_id,
            _Risk.threat_id == data.threat_id,
            _Risk.organization_id == current_user.organization_id,
        ).first()
        if existing_dup:
            raise HTTPException(
                409,
                _t("risks.duplicate_detected", lang, name=existing_dup.code, id=existing_dup.id),
            )

    org_id = current_user.organization_id
    r = Risk(
        code=_next_code(db, org_id),
        organization_id=org_id,
        asset_id=data.asset_id, threat_id=data.threat_id,
        description=data.description,
        consequence_description=data.consequence_description,
        inherent_likelihood=data.inherent_likelihood,
        inherent_consequence=data.inherent_consequence,
        owner_id=data.owner_id,
        treatment_option=data.treatment_option,
        treatment_plan=data.treatment_plan,
        treatment_due_date=data.treatment_due_date,
        status=RiskStatus.ASSESSED,
        # MAGERIT v3 (si se proporcionan)
        magerit_dimension=data.magerit_dimension,
        degradation_pct=data.degradation_pct,
    )
    if data.vulnerability_ids:
        r.vulnerabilities = db.query(Vulnerability).filter(
            Vulnerability.id.in_(data.vulnerability_ids)).all()
    db.add(r)
    db.flush()  # asigna r.id antes de recalcular controles
    if data.control_implementation_ids:
        r.controls = db.query(ControlImplementation).filter(
            ControlImplementation.id.in_(data.control_implementation_ids)).all()
        db.flush()
    _recalc(db, r)
    log_action(db, current_user.id, "create", "risk", None,
               {"asset_id": data.asset_id, "threat_id": data.threat_id})
    db.commit(); db.refresh(r)

    # Disparar alerta inmediata si el riesgo es CRITICO/ALTO y NO fue auto-aceptado
    if (r.residual_level or 0) >= 5 and r.status != RiskStatus.ACCEPTED:
        import threading
        from app.database import SessionLocal as _SL

        def _fire_alert(risk_id=r.id, org_id=r.organization_id):
            db2 = _SL()
            try:
                from app.services import email_service
                from app.models import AlertRule, Risk as _R, RiskContext as _RC
                cfg = email_service.get_settings(db2)
                if not cfg or not cfg.smtp_host:
                    return
                risk_obj = db2.get(_R, risk_id)
                if not risk_obj:
                    return
                ctx = db2.query(_RC).filter(_RC.organization_id == org_id).first()
                org_name = ctx.organization_name if ctx else "Organizacion"
                rules = db2.query(AlertRule).filter(
                    AlertRule.is_active.is_(True),
                    AlertRule.organization_id == org_id,
                    AlertRule.event_type.in_(["risk_critical", "risk_high"]),
                ).all()
                for rule in rules:
                    if risk_obj.residual_level >= rule.threshold_level:
                        body = f"Se ha creado el riesgo {risk_obj.code} con nivel residual {risk_obj.residual_level}/8."
                        email_service.send_email(
                            cfg, rule.recipient_email,
                            f"RiskHub [NUEVO] — Riesgo {risk_obj.code} requiere atencion ({org_name})",
                            email_service.risk_alert_html(risk_obj, org_name, body),
                        )
            except Exception:
                pass
            finally:
                db2.close()

        threading.Thread(target=_fire_alert, daemon=True).start()

    # Comprobar cobertura BCP del riesgo (ISO 22301 cl. 8.2)
    try:
        from app.services.bcp_service import check_bcp_coverage_for_risk
        check_bcp_coverage_for_risk(db, r, current_user.organization_id)
    except Exception as _e:
        logger.debug("BCP coverage check skipped: %s", _e)

    return r


@router.patch("/{risk_id}", response_model=RiskOut)
def update_risk(risk_id: int, data: RiskUpdate, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_analyst)):
    lang = get_lang(request)
    r = db.get(Risk, risk_id)
    if not r or not check_org_access(r.organization_id, user):
        raise HTTPException(404, _t("risks.not_found", lang))

    update_data = data.model_dump(exclude_unset=True)
    if "vulnerability_ids" in update_data:
        ids = update_data.pop("vulnerability_ids")
        r.vulnerabilities = db.query(Vulnerability).filter(
            Vulnerability.id.in_(ids or [])).all()
    if "control_implementation_ids" in update_data:
        ids = update_data.pop("control_implementation_ids") or []
        # Validar que todos los controles pertenecen a la misma org
        for cid in ids:
            ci = db.get(ControlImplementation, cid)
            if not ci or ci.organization_id != r.organization_id:
                raise HTTPException(422, f"Control {cid} no pertenece a la organizacion")
        # Preservar contribution existente al actualizar M2M
        from sqlalchemy import insert as _insert, delete as _delete, text as _text
        existing = db.execute(
            _text("SELECT control_implementation_id, contribution FROM risk_controls WHERE risk_id = :rid"),
            {"rid": r.id},
        ).fetchall()
        existing_map = {row[0]: row[1] for row in existing}
        db.execute(
            _delete(risk_control_table).where(risk_control_table.c.risk_id == r.id)
        )
        for cid in ids:
            db.execute(
                _insert(risk_control_table).values(
                    risk_id=r.id,
                    control_implementation_id=cid,
                    contribution=existing_map.get(cid, 1.0),
                )
            )
        db.flush()
        # Refrescar la relacion desde BD
        db.expire(r, ["controls"])

    # Acceptance bookkeeping
    if update_data.get("status") == RiskStatus.ACCEPTED:
        r.accepted_by_id = user.id
        r.accepted_at = datetime.now(timezone.utc)

    for k, v in update_data.items():
        setattr(r, k, v)
    old_status = r.status
    _recalc(db, r)
    log_action(db, user.id, "update", "risk", str(risk_id),
               {"code": r.code, "status": str(r.status), "residual_level": r.residual_level})
    db.commit(); db.refresh(r)

    # Sincronizar compliance cuando el riesgo cambia de estado (especialmente CLOSED/ACCEPTED)
    if old_status != r.status and r.status in (RiskStatus.CLOSED, RiskStatus.ACCEPTED):
        _trigger_compliance_sync_bg(r.organization_id)

    return r


def _trigger_compliance_sync_bg(org_id: int) -> None:
    """Sincroniza compliance en background tras cambio de estado de riesgo."""
    import threading
    from app.database import SessionLocal as _SL

    def _sync():
        db2 = _SL()
        try:
            from app.services.compliance_service import auto_update_compliance_from_controls
            auto_update_compliance_from_controls(db2, org_id)
        except Exception:
            pass
        finally:
            db2.close()

    threading.Thread(target=_sync, daemon=True).start()


@router.post("/magerit-preview")
def magerit_consequence_preview(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Calcula en tiempo real la consecuencia MAGERIT para un activo + dimension + degradacion.

    Body: {asset_id, dimension, degradation_pct}
    Respuesta: {consequence, magerit_impact, dim_value, label}
    """
    from app.services.risk_engine import calc_consequence_magerit, MAGERIT_DIM_FIELD, CONSEQUENCE_LABELS
    asset_id = body.get("asset_id")
    dimension = body.get("dimension", "D")
    degrad = int(body.get("degradation_pct", 50))

    asset = db.get(Asset, asset_id) if asset_id else None
    if not asset or not check_org_access(asset.organization_id, current_user):
        return {"consequence": 0, "magerit_impact": 0.0, "dim_value": 0, "label": "-"}

    field = MAGERIT_DIM_FIELD.get(dimension, "value_availability")
    dim_value = getattr(asset, field, 0) or 0
    consequence, impact = calc_consequence_magerit(dim_value, degrad)
    return {
        "consequence": consequence,
        "magerit_impact": impact,
        "dim_value": dim_value,
        "label": CONSEQUENCE_LABELS[consequence] if 0 <= consequence < len(CONSEQUENCE_LABELS) else "-",
        "asset_dims": {
            "D": asset.value_availability or 0,
            "I": asset.value_integrity or 0,
            "C": asset.value_confidentiality or 0,
            "A": asset.value_authenticity or 0,
            "T": asset.value_accountability or 0,
        },
    }


@router.delete("/{risk_id}", status_code=204)
def delete_risk(risk_id: int, request: Request, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    r = db.get(Risk, risk_id)
    if not r or not check_org_access(r.organization_id, current_user):
        raise HTTPException(404, _t("risks.not_found", lang))
    code = r.code
    db.delete(r)
    log_action(db, current_user.id, "delete", "risk", str(risk_id), {"code": code})
    db.commit()


@router.get("/export/csv")
def export_risks_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exporta todos los riesgos como CSV."""
    risks = filter_by_org(db.query(Risk), Risk, current_user).order_by(
        Risk.residual_level.desc(), Risk.code
    ).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Codigo", "Activo", "Amenaza", "Descripcion",
        "Nivel_Inherente", "Prob_Inherente", "Cons_Inherente",
        "Nivel_Residual", "Prob_Residual", "Cons_Residual",
        "Estado", "Tratamiento", "Plan_Tratamiento",
        "Fecha_Vencimiento", "Creado",
    ])
    for r in risks:
        writer.writerow([
            r.code,
            r.asset.name if r.asset else "",
            r.threat.name if r.threat else "",
            r.description or "",
            r.inherent_level, r.inherent_likelihood, r.inherent_consequence,
            r.residual_level, r.residual_likelihood, r.residual_consequence,
            r.status.value if r.status else "",
            r.treatment_option.value if r.treatment_option else "",
            r.treatment_plan or "",
            r.treatment_due_date.strftime("%Y-%m-%d") if r.treatment_due_date else "",
            r.created_at.strftime("%Y-%m-%d") if r.created_at else "",
        ])
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    fname = f"riesgos_{ts}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/import/template")
def risks_import_template(_: User = Depends(get_current_user)):
    """Devuelve una plantilla CSV para importacion masiva de riesgos."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Activo_Codigo", "Amenaza_Codigo", "Descripcion",
        "Prob_Inherente", "Cons_Inherente",
        "Prob_Residual", "Cons_Residual",
        "Estado", "Tratamiento", "Plan_Tratamiento",
        "Fecha_Vencimiento",
    ])
    writer.writerow([
        "AST-0001", "T-CYB-01", "Acceso no autorizado al servidor de produccion",
        "3", "3", "1", "2",
        "identified", "modification", "Implantar MFA y revisar politica de acceso",
        "2025-12-31",
    ])
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="risks_template.csv"'},
    )


@router.post("/import")
async def import_risks_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Importa riesgos desde un CSV. Busca activo por codigo y amenaza por codigo."""
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # soporta BOM de Excel
        reader = csv.DictReader(io.StringIO(text))
    except Exception as exc:
        raise HTTPException(400, f"Error al leer el CSV: {exc}") from exc

    # Cache de activos y amenazas para lookups rapidos (filtrados por org)
    org_assets = filter_by_org(db.query(Asset), Asset, current_user).all()
    assets_by_code = {a.code: a for a in org_assets}
    assets_by_name = {a.name.lower(): a for a in org_assets}
    # Threat es catalogo global (sin organization_id) — se accede sin filtro de org
    all_threats = db.query(Threat).all()
    threats_by_code = {t.code: t for t in all_threats}
    threats_by_name = {t.name.lower(): t for t in all_threats}

    def _parse_int(val: str, default: int = 0, lo: int = 0, hi: int = 4) -> int:
        try:
            return max(lo, min(hi, int(str(val).strip())))
        except (ValueError, TypeError):
            return default

    created, skipped = [], []

    for row in reader:
        asset_key = (row.get("Activo_Codigo") or "").strip()
        threat_key = (row.get("Amenaza_Codigo") or "").strip()

        asset = assets_by_code.get(asset_key) or assets_by_name.get(asset_key.lower())
        threat = threats_by_code.get(threat_key) or threats_by_name.get(threat_key.lower())

        if not asset:
            skipped.append(f"Activo no encontrado: '{asset_key}'")
            continue
        if not threat:
            skipped.append(f"Amenaza no encontrada: '{threat_key}'")
            continue

        # Detectar duplicados dentro de la misma org
        dup = db.query(Risk).filter(
            Risk.asset_id == asset.id,
            Risk.threat_id == threat.id,
            Risk.organization_id == current_user.organization_id,
        ).first()
        if dup:
            skipped.append(f"{asset.code} x {threat.code} (duplicado: {dup.code})")
            continue

        il = _parse_int(row.get("Prob_Inherente", "2"), 2)
        ic = _parse_int(row.get("Cons_Inherente", "2"), 2)
        rl = _parse_int(row.get("Prob_Residual", "1"), 1)
        rc = _parse_int(row.get("Cons_Residual", "1"), 1)

        status_val = (row.get("Estado") or "identified").strip().lower()
        try:
            status = RiskStatus(status_val)
        except ValueError:
            status = RiskStatus.IDENTIFIED

        treat_val = (row.get("Tratamiento") or "").strip().lower()
        try:
            treatment = TreatmentOption(treat_val) if treat_val else None
        except ValueError:
            treatment = None

        due_str = (row.get("Fecha_Vencimiento") or "").strip()
        due_date = None
        if due_str:
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    due_date = datetime.strptime(due_str, fmt)
                    break
                except ValueError:
                    continue

        db.flush()  # hace visible el riesgo anterior del batch para MAX(id)
        code = _next_code(db, current_user.organization_id)

        risk = Risk(
            code=code,
            asset_id=asset.id,
            threat_id=threat.id,
            description=(row.get("Descripcion") or "").strip(),
            inherent_likelihood=il,
            inherent_consequence=ic,
            inherent_level=calc_level(ic, il),
            residual_likelihood=rl,
            residual_consequence=rc,
            residual_level=calc_level(rc, rl),
            status=status,
            treatment_option=treatment,
            treatment_plan=(row.get("Plan_Tratamiento") or "").strip(),
            treatment_due_date=due_date,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
        )
        db.add(risk)
        created.append(code)

    if created:
        db.commit()
        log_action(db, current_user.id, "import", "risk", None,
                   {"count": len(created), "source": "csv"})
        db.commit()

    return {
        "created": len(created),
        "skipped": len(skipped),
        "detail_created": created,
        "detail_skipped": skipped,
    }


@router.get("/heatmap/data")
def heatmap(db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user),
            mode: str = Query("residual", regex="^(residual|inherent)$")):
    """Devuelve matriz 5x5 con conteo y referencias de riesgo."""
    matrix = [[{"count": 0, "risks": []} for _ in range(5)] for _ in range(5)]
    for r in filter_by_org(db.query(Risk), Risk, current_user).all():
        if mode == "residual":
            x, y = r.residual_likelihood, r.residual_consequence
        else:
            x, y = r.inherent_likelihood, r.inherent_consequence
        x = max(0, min(4, x)); y = max(0, min(4, y))
        matrix[4 - y][x]["count"] += 1
        matrix[4 - y][x]["risks"].append({
            "id": r.id, "code": r.code,
            "asset": r.asset.name if r.asset else "",
            "threat": r.threat.name if r.threat else "",
            "level": r.residual_level if mode == "residual" else r.inherent_level,
        })
    return {"mode": mode, "matrix": matrix}


@router.get("/stats/summary")
def summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Resumen para el dashboard."""
    now = datetime.now(timezone.utc)
    risks = filter_by_org(db.query(Risk), Risk, current_user).all()
    from app.services.risk_engine import get_risk_bands, band_for_config
    _bands = get_risk_bands(db, getattr(current_user, "organization_id", None))
    # Siempre incluir low/medium/high para compatibilidad con el dashboard
    by_band: dict = {"low": 0, "medium": 0, "high": 0}
    by_band.update({b["code"]: 0 for b in _bands})
    for r in risks:
        bc = band_for_config(r.residual_level or 0, _bands)
        by_band[bc["code"]] = by_band.get(bc["code"], 0) + 1
    by_status = {s.value: 0 for s in RiskStatus}
    for r in risks:
        by_status[r.status.value] += 1
    by_treatment = {t.value: 0 for t in TreatmentOption}
    for r in risks:
        if r.treatment_option:
            by_treatment[r.treatment_option.value] += 1

    # Metricas adicionales
    active_statuses = {RiskStatus.IDENTIFIED, RiskStatus.ASSESSED}
    active_risks = [r for r in risks if r.status in active_statuses]
    overdue = sum(
        1 for r in active_risks
        if r.treatment_due_date and r.treatment_due_date.replace(tzinfo=timezone.utc) < now
    )
    no_treatment_high = sum(
        1 for r in active_risks
        if r.residual_level >= 5 and not r.treatment_option
    )
    no_owner = sum(1 for r in risks if r.owner_id is None
                   and r.status not in {RiskStatus.ACCEPTED, RiskStatus.CLOSED})
    total_inh = sum(r.inherent_level for r in risks)
    total_res = sum(r.residual_level for r in risks)
    reduction_pct = round((1 - total_res / total_inh) * 100) if total_inh else 0

    # Control maturity stats
    from app.models import ControlStatus
    impls = filter_by_org(db.query(ControlImplementation), ControlImplementation, current_user).all()
    impl_implemented = sum(1 for c in impls if c.status == ControlStatus.IMPLEMENTED)
    avg_maturity = round(sum(c.maturity for c in impls) / len(impls), 1) if impls else 0
    controls_overdue_reviews = sum(
        1 for c in impls
        if c.next_review
        and c.next_review.replace(tzinfo=timezone.utc) < now
        and c.status != ControlStatus.NOT_IMPLEMENTED
    )

    supplier_risks_count = sum(1 for r in risks if r.supplier_id is not None)

    return {
        "total_risks": len(risks),
        "supplier_risks_count": supplier_risks_count,
        "total_assets": db.query(Asset).count(),
        "total_threats": db.query(Threat).count(),
        "total_vulnerabilities": db.query(Vulnerability).count(),
        "total_controls": len(impls),
        "controls_implemented": impl_implemented,
        "controls_avg_maturity": avg_maturity,
        "controls_overdue_reviews": controls_overdue_reviews,
        "by_band": by_band,
        "by_status": by_status,
        "by_treatment": by_treatment,
        "overdue_treatments": overdue,
        "no_treatment_high": no_treatment_high,
        "no_owner": no_owner,
        "risk_reduction_pct": reduction_pct,
        "top_risks": [
            {"code": r.code, "asset": r.asset.name if r.asset else "",
             "threat": r.threat.name if r.threat else "",
             "level": r.residual_level, "inherent_level": r.inherent_level, "id": r.id}
            for r in sorted(risks, key=lambda x: -x.residual_level)[:10]
        ],
    }


@router.get("/aggregate-exposure")
def aggregate_exposure(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    simulations: int = Query(10000, ge=1000, le=50000),
):
    """Exposicion economica agregada del portfolio teniendo en cuenta correlaciones entre riesgos.

    Usa Monte Carlo con matriz de correlaciones para calcular VaR conjunto del portfolio,
    evitando la suma ingenua que sobreestima el riesgo total.
    """
    import random
    from app.models import RiskCorrelation

    org_id = current_user.organization_id
    risks = filter_by_org(db.query(Risk), Risk, current_user).filter(
        Risk.status.notin_([RiskStatus.CLOSED])
    ).all()

    if not risks:
        return {"portfolio_var_95": 0, "portfolio_var_99": 0, "expected_total_loss": 0, "risks_with_value": 0}

    lik_to_prob = {0: 0.01, 1: 0.05, 2: 0.15, 3: 0.40, 4: 0.75}
    con_to_impact = {0: 0.02, 1: 0.10, 2: 0.30, 3: 0.60, 4: 0.95}

    risk_params = []
    for r in risks:
        val = getattr(r.asset, "estimated_value", None) if r.asset else None
        if not val or val <= 0:
            continue
        risk_params.append({
            "id": r.id,
            "code": r.code,
            "prob": lik_to_prob.get(r.residual_likelihood or 0, 0.05),
            "impact_frac": con_to_impact.get(r.residual_consequence or 0, 0.10),
            "asset_value": val,
        })

    if not risk_params:
        return {"portfolio_var_95": 0, "portfolio_var_99": 0, "expected_total_loss": 0,
                "risks_with_value": 0, "note": "Ningun activo tiene valor estimado configurado"}

    # Obtener correlaciones
    correlations = db.query(RiskCorrelation).filter(
        RiskCorrelation.organization_id == org_id
    ).all()
    corr_map: dict[tuple, float] = {}
    for c in correlations:
        corr_map[(c.risk_id_a, c.risk_id_b)] = c.correlation_factor
        corr_map[(c.risk_id_b, c.risk_id_a)] = c.correlation_factor

    # Monte Carlo con correlacion simple: si riesgo A se materializa, eleva prob de B
    portfolio_losses = []
    for _ in range(simulations):
        total = 0.0
        materialized_ids: set[int] = set()
        for rp in risk_params:
            base_prob = rp["prob"]
            # Elevar prob si algun riesgo correlado ya se materializó
            for mid in materialized_ids:
                cf = corr_map.get((mid, rp["id"]), 0.0)
                base_prob = min(0.95, base_prob + cf * 0.3)
            if random.random() < base_prob:
                materialized_ids.add(rp["id"])
                tri = random.triangular(0.10, 1.50, 1.0)
                total += rp["asset_value"] * rp["impact_frac"] * tri
        portfolio_losses.append(total)

    portfolio_losses.sort()
    n = len(portfolio_losses)

    def _p(pct: float) -> float:
        return round(portfolio_losses[int(n * pct / 100)], 2)

    return {
        "risks_analyzed": len(risk_params),
        "correlations_applied": len(correlations),
        "simulations": simulations,
        "portfolio_var_95": _p(95),
        "portfolio_var_99": _p(99),
        "expected_total_loss": round(sum(portfolio_losses) / n, 2),
        "max_scenario": round(max(portfolio_losses), 2),
        "individual_expected": [
            {
                "risk_code": rp["code"],
                "expected_loss": round(rp["asset_value"] * rp["impact_frac"] * rp["prob"], 2),
            }
            for rp in risk_params
        ],
    }


@router.get("/concentration")
def risk_concentration(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Heatmap de concentracion de riesgos por amenaza, activo, propietario y dominio ISO 27002."""
    risks = filter_by_org(db.query(Risk), Risk, current_user).filter(
        Risk.status.notin_([RiskStatus.CLOSED])
    ).all()

    by_threat: dict[str, dict] = {}
    by_asset: dict[str, dict] = {}
    by_owner: dict[str, dict] = {}
    by_domain: dict[str, dict] = {}

    for r in risks:
        level = r.residual_level or 0
        # Por amenaza
        th_key = (r.threat.name if r.threat else "Sin amenaza")
        by_threat.setdefault(th_key, {"count": 0, "max_level": 0, "total_level": 0})
        by_threat[th_key]["count"] += 1
        by_threat[th_key]["max_level"] = max(by_threat[th_key]["max_level"], level)
        by_threat[th_key]["total_level"] += level
        # Por activo
        ast_key = (r.asset.name if r.asset else "Sin activo")
        by_asset.setdefault(ast_key, {"count": 0, "max_level": 0, "total_level": 0})
        by_asset[ast_key]["count"] += 1
        by_asset[ast_key]["max_level"] = max(by_asset[ast_key]["max_level"], level)
        by_asset[ast_key]["total_level"] += level
        # Por propietario
        own_key = (r.owner.username if r.owner else "Sin propietario")
        by_owner.setdefault(own_key, {"count": 0, "max_level": 0, "total_level": 0})
        by_owner[own_key]["count"] += 1
        by_owner[own_key]["max_level"] = max(by_owner[own_key]["max_level"], level)
        by_owner[own_key]["total_level"] += level
        # Por dominio ISO 27002 (theme del control)
        if r.controls:
            for ci in r.controls:
                if ci.control and ci.control.theme:
                    dom = ci.control.theme
                    by_domain.setdefault(dom, {"count": 0, "max_level": 0, "total_level": 0})
                    by_domain[dom]["count"] += 1
                    by_domain[dom]["max_level"] = max(by_domain[dom]["max_level"], level)
                    by_domain[dom]["total_level"] += level

    def _format(d: dict, key_name: str) -> list:
        return sorted(
            [{"name": k, **v, "avg_level": round(v["total_level"] / v["count"], 2)} for k, v in d.items()],
            key=lambda x: x["max_level"],
            reverse=True,
        )[:20]

    return {
        "by_threat": _format(by_threat, "threat"),
        "by_asset": _format(by_asset, "asset"),
        "by_owner": _format(by_owner, "owner"),
        "by_iso_domain": _format(by_domain, "domain"),
        "total_active_risks": len(risks),
    }


@router.get("/portfolio-score")
def portfolio_score(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Score agregado del portfolio de riesgos: media ponderada de niveles residuales.

    Ponderacion: criticos (nivel 7-8) = peso 3, altos (5-6) = peso 2, resto = peso 1.
    Devuelve el score (0-8), distribucion por banda y tendencia respecto al mes anterior.
    """
    from app.models import RiskSnapshot
    risks = filter_by_org(db.query(Risk), Risk, current_user).filter(
        Risk.status.notin_([RiskStatus.CLOSED])
    ).all()

    if not risks:
        return {"portfolio_score": 0, "risk_count": 0, "distribution": {}, "trend": 0}

    total_weighted = 0.0
    total_weight = 0.0
    distribution: dict[str, int] = {"low": 0, "medium": 0, "high": 0, "critical": 0}

    for r in risks:
        lev = r.residual_level or 0
        if lev >= 7:
            weight = 3.0
            distribution["critical"] += 1
        elif lev >= 5:
            weight = 2.0
            distribution["high"] += 1
        elif lev >= 3:
            weight = 1.5
            distribution["medium"] += 1
        else:
            weight = 1.0
            distribution["low"] += 1
        total_weighted += lev * weight
        total_weight += weight

    score = round(total_weighted / total_weight, 2) if total_weight > 0 else 0

    # Tendencia: comparar con el snapshot del mes anterior
    org_id = current_user.organization_id
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    prev_month_start = (now.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_snapshots = (
        db.query(RiskSnapshot)
        .filter(
            RiskSnapshot.organization_id == org_id,
            RiskSnapshot.snapshot_date >= prev_month_start,
            RiskSnapshot.snapshot_date < prev_month_start.replace(month=prev_month_start.month % 12 + 1) if prev_month_start.month < 12 else prev_month_start.replace(year=prev_month_start.year + 1, month=1),
        )
        .all()
    )
    trend = 0
    if prev_snapshots:
        prev_snaps = [s.residual_level or 0 for s in prev_snapshots]
        prev_score = round(sum(prev_snaps) / len(prev_snaps), 2)
        trend = round(score - prev_score, 2)

    ctx = _get_context(db, org_id)
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3

    return {
        "portfolio_score": score,
        "risk_count": len(risks),
        "distribution": distribution,
        "trend": trend,
        "risk_appetite": appetite,
        "above_appetite": distribution["high"] + distribution["critical"],
    }


# ── Risk Acceptance Formal Workflow (ISO 27001 cl. 6.1.2e) ───────────────────

class AcceptanceRequestBody(BaseModel):
    justification: str
    review_date: Optional[str] = None   # fecha de re-evaluacion ISO 8601


class AcceptanceApproveBody(BaseModel):
    review_date: Optional[str] = None
    notes: Optional[str] = None


class AcceptanceRejectBody(BaseModel):
    reason: Optional[str] = None


@router.put("/{risk_id}/request-acceptance")
def request_acceptance(
    risk_id: int,
    body: AcceptanceRequestBody,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Analyst propone aceptacion formal del riesgo (PENDING_ACCEPTANCE)."""
    lang = get_lang(request)
    risk = db.get(Risk, risk_id)
    if not risk:
        raise HTTPException(404, _t("risks.not_found", lang))
    if not check_org_access(risk.organization_id, current_user):
        raise HTTPException(403, _t("common.unauthorized", lang))

    if risk.status not in (RiskStatus.IDENTIFIED, RiskStatus.ASSESSED, RiskStatus.TREATED):
        raise HTTPException(400, f"El riesgo en estado '{risk.status.value}' no puede solicitar aceptacion")

    risk.status = RiskStatus.PENDING_ACCEPTANCE
    risk.acceptance_justification = body.justification
    risk.acceptance_requested_by_id = current_user.id
    risk.acceptance_requested_at = datetime.now(timezone.utc)

    if body.review_date:
        try:
            risk.acceptance_review_date = datetime.fromisoformat(body.review_date)
        except ValueError:
            pass

    db.commit()
    log_action(db, current_user.id, "request_acceptance", "risk", str(risk_id),
               {"code": risk.code, "residual_level": risk.residual_level})

    # Notificar al admin por email
    try:
        from app.services.email_service import get_settings, send_email
        from app.models import UserRole
        cfg = get_settings(db, risk.organization_id)
        if cfg and cfg.smtp_host:
            admin = db.query(User).filter_by(
                organization_id=risk.organization_id,
                role=UserRole.ADMIN,
                is_active=True,
            ).first()
            if admin and admin.email:
                subject = f"[RiskHub] Solicitud de aceptacion de riesgo: {risk.code}"
                body_html = (
                    f"<p>El analista <strong>{current_user.full_name}</strong> ha solicitado "
                    f"la aceptacion formal del riesgo <strong>{risk.code}</strong>.</p>"
                    f"<p><strong>Nivel residual:</strong> {risk.residual_level}/8</p>"
                    f"<p><strong>Justificacion:</strong> {body.justification}</p>"
                    f"<p>Accede a RiskHub para aprobar o rechazar.</p>"
                )
                send_email(cfg, admin.email, subject, body_html)
    except Exception:
        pass

    return {"status": "pending_acceptance", "risk_code": risk.code}


@router.put("/{risk_id}/accept")
def accept_risk(
    risk_id: int,
    body: AcceptanceApproveBody,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin / risk owner aprueba la aceptacion formal del riesgo."""
    lang = get_lang(request)
    from app.security import require_admin
    from app.models import UserRole
    risk = db.get(Risk, risk_id)
    if not risk:
        raise HTTPException(404, _t("risks.not_found", lang))
    if not check_org_access(risk.organization_id, current_user):
        raise HTTPException(403, _t("common.unauthorized", lang))

    # Solo admin o el owner del riesgo pueden aceptar
    is_admin = current_user.role in (UserRole.ADMIN, UserRole.SUPERADMIN)
    is_owner = risk.owner_id == current_user.id
    if not (is_admin or is_owner):
        raise HTTPException(403, _t("common.forbidden", lang))

    if risk.status != RiskStatus.PENDING_ACCEPTANCE:
        raise HTTPException(400, "El riesgo no esta en estado PENDING_ACCEPTANCE")

    risk.status = RiskStatus.ACCEPTED
    risk.accepted_by_id = current_user.id
    risk.accepted_at = datetime.now(timezone.utc)
    risk.acceptance_approved_by_id = current_user.id
    risk.treatment_option = TreatmentOption.RETENTION

    if body.review_date:
        try:
            risk.acceptance_review_date = datetime.fromisoformat(body.review_date)
        except ValueError:
            pass

    db.commit()
    log_action(db, current_user.id, "accept", "risk", str(risk_id),
               {"code": risk.code, "residual_level": risk.residual_level})
    return {"status": "accepted", "risk_code": risk.code}


@router.put("/{risk_id}/reject-acceptance")
def reject_acceptance(
    risk_id: int,
    body: AcceptanceRejectBody,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin / risk owner rechaza la solicitud de aceptacion → vuelve a ASSESSED."""
    lang = get_lang(request)
    from app.models import UserRole
    risk = db.get(Risk, risk_id)
    if not risk:
        raise HTTPException(404, _t("risks.not_found", lang))
    if not check_org_access(risk.organization_id, current_user):
        raise HTTPException(403, _t("common.unauthorized", lang))

    is_admin = current_user.role in (UserRole.ADMIN, UserRole.SUPERADMIN)
    is_owner = risk.owner_id == current_user.id
    if not (is_admin or is_owner):
        raise HTTPException(403, _t("common.forbidden", lang))

    if risk.status != RiskStatus.PENDING_ACCEPTANCE:
        raise HTTPException(400, "El riesgo no esta en estado PENDING_ACCEPTANCE")

    risk.status = RiskStatus.ASSESSED
    if body.reason:
        risk.acceptance_justification = (risk.acceptance_justification or "") + f"\nRechazado: {body.reason}"

    db.commit()
    log_action(db, current_user.id, "reject_acceptance", "risk", str(risk_id),
               {"code": risk.code, "reason": body.reason})
    return {"status": "assessed", "risk_code": risk.code}


@router.post("/{risk_id}/suggest-controls")
def suggest_controls_for_risk(
    risk_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Usa IA + RAG para sugerir que controles implementados mitigan mejor este riesgo.

    Lee el contexto del riesgo (activo, amenaza, vulnerabilidades), los controles
    disponibles con su madurez y evidencias, y los documentos indexados del tenant.
    Devuelve los IDs de los controles sugeridos y una justificacion breve.
    """
    from app.models import AiConfig, Control
    from app.services.rag_service import search_chunks_with_source

    lang = get_lang(request)
    r = db.get(Risk, risk_id)
    if not r:
        raise HTTPException(404, _t("risks.not_found", lang))
    if not check_org_access(r.organization_id, current_user):
        raise HTTPException(403, _t("common.forbidden", lang))

    # Configuracion IA del tenant — mismo patron de descifrado que ai-explain
    ai_cfg = db.query(AiConfig).filter_by(organization_id=r.organization_id).first()

    def _resolve_key(cfg):
        if cfg and cfg.api_key_encrypted:
            import base64, hashlib
            from cryptography.fernet import Fernet as _Fernet
            from app.config import settings as _s
            key = base64.urlsafe_b64encode(hashlib.sha256(_s.secret_key.encode()).digest())
            try:
                return _Fernet(key).decrypt(cfg.api_key_encrypted.encode()).decode()
            except Exception:
                return None
        from app.config import settings as _s
        return _s.anthropic_api_key

    api_key = _resolve_key(ai_cfg)
    if not api_key:
        raise HTTPException(400, "API key no configurada. Ve a Configuracion > Agente IA.")
    model = (ai_cfg.model if ai_cfg else None) or "claude-haiku-4-5"

    # Contexto del riesgo
    asset_name = r.asset.name if r.asset else "N/A"
    asset_type = r.asset.asset_type.value if r.asset and r.asset.asset_type else "N/A"
    threat_name = r.threat.name if r.threat else "N/A"
    threat_code = r.threat.code if r.threat else "N/A"
    threat_cat  = r.threat.category if r.threat else "N/A"
    vuln_lines  = [f"  - [{v.code}] {v.name}: {(v.description or '')[:100]}" for v in (r.vulnerabilities or [])]

    # Controles disponibles en el tenant
    impls = db.query(ControlImplementation).filter_by(organization_id=r.organization_id).all()
    impl_lines = []
    for c in impls:
        ctrl = db.get(Control, c.control_id) if c.control_id else None
        code = ctrl.code if ctrl else "?"
        theme = ctrl.theme if ctrl else "?"
        impl_lines.append(f"  - ID:{c.id} [{code}][{theme}] {c.name} (madurez:{c.maturity}/5, estado:{c.status.value})")

    # RAG: buscar fragmentos de documentos relevantes
    rag_query = f"{threat_name} {' '.join(v.name for v in (r.vulnerabilities or []))} controles mitigacion"
    rag_chunks = []
    try:
        chunks = search_chunks_with_source(db, rag_query, top_k=6, organization_id=r.organization_id)
        rag_chunks = [f"  [{c.get('doc_name','')}] {c.get('content','')[:200]}" for c in chunks]
    except Exception:
        pass

    from app.services.risk_analysis_helpers import (
        get_asset_profile, build_vuln_section, threat_actor_profile,
        classify_control, evidence_quality_score, adjusted_maturity,
        build_vigilancia_context,
    )

    asset_profile = get_asset_profile(asset_type)
    actor_profile = threat_actor_profile(
        r.threat.origin.value if r.threat and r.threat.origin else "",
        threat_cat,
    )
    vuln_section_text = build_vuln_section(r.vulnerabilities or [])

    # Controles con clasificacion de tipo y calidad de evidencia
    impl_lines_rich = []
    for c in impls:
        ctrl = db.get(Control, c.control_id) if c.control_id else None
        code = ctrl.code if ctrl else "?"
        theme = ctrl.theme if ctrl else "?"
        ctrl_type = classify_control(code, c.name)
        type_label = {"P": "PREVENTIVO", "D": "DETECTIVO", "C": "CORRECTIVO"}.get(ctrl_type, "?")
        refs = c.evidence_refs or []
        _, ev_desc = evidence_quality_score(refs)
        adj_mat = adjusted_maturity(c.maturity or 0, refs)
        regwatch_flag = " [REVISION NORMATIVA PENDIENTE]" if c.regwatch_pack_id else ""
        impl_lines_rich.append(
            f"  ID:{c.id} [{code}][{theme}] {c.name} | "
            f"Tipo:{type_label} | Madurez:{c.maturity}/5 | AjustadaEvidencia:{adj_mat}/5 | "
            f"Estado:{c.status.value} | Evidencia:{ev_desc}{regwatch_flag}"
        )

    # Evidencia real de Vigilancia (OSINT, CVE, Regwatch)
    vuln_ids_suggest = [v.id for v in (r.vulnerabilities or [])]
    impl_ids_suggest = [c.id for c in impls]
    vigilancia_suggest = build_vigilancia_context(
        db, r.asset_id, vuln_ids_suggest, impl_ids_suggest, r.organization_id
    )

    prompt = f"""Eres un auditor ISO 27001 y ISO 27005 experto en gestion de riesgos de seguridad.

Tu tarea es seleccionar los controles que REALMENTE mitigan este riesgo especifico,
NO los que tienen un nombre relacionado. Piensa en terminos de cadena de ataque.

# RIESGO A ANALIZAR
- Activo: {asset_name} (tipo: {asset_profile['label']})
- Amenaza: [{threat_code}] {threat_name} (categoria: {threat_cat})
- Origen amenaza: {r.threat.origin.value if r.threat and r.threat.origin else 'N/A'}
- Perfil del agente: {actor_profile}
- Descripcion del escenario: {r.description or 'Sin descripcion'}
- Consecuencia esperada: {r.consequence_description or 'Sin definir'}
- Dimensiones primarias afectadas: {', '.join(asset_profile['primary_dimensions'])}

# VULNERABILIDADES QUE HABILITAN ESTA AMENAZA
{vuln_section_text}

# EVIDENCIA REAL DE VIGILANCIA (OSINT / CVE / REGWATCH)
{vigilancia_suggest}

# CONTROLES DISPONIBLES EN LA ORGANIZACION ({len(impls)} total)
(Tipo P=Preventivo, D=Detectivo, C=Correctivo — Madurez real ajustada por calidad de evidencia)
(REVISION NORMATIVA PENDIENTE = el control puede estar desactualizado por cambio normativo)
{chr(10).join(impl_lines_rich)}

# DOCUMENTACION INTERNA RELEVANTE
{chr(10).join(rag_chunks) if rag_chunks else '  (sin documentos indexados)'}

# INSTRUCCIONES

Paso 1 — Construye la cadena de ataque para [{threat_code}] sobre {asset_name}.
  Si hay hallazgos OSINT o CVEs activos en la seccion de Vigilancia, la amenaza es REAL.
  Incorporalos en la descripcion de la cadena de ataque con el vector real detectado.

Paso 2 — Para cada paso del ataque, identifica que controles (de la lista disponible)
  lo bloquean (P), lo detectan (D) o limitan su impacto (C).
  Si un hallazgo OSINT/CVE corresponde a una vulnerabilidad sin control preventivo, ese paso
  es una BRECHA CRITICA y debe priorizarse en missing_controls.

Paso 3 — Selecciona los controles con IDs de la lista que cubren los pasos criticos.
  EXCLUYE controles que no tienen relacion directa con ningun paso del ataque.
  PRIORIZA controles preventivos sobre detectivos si la madurez ajustada es >= 2/5.
  INCLUYE controles detectivos cuando no hay preventivos para un paso critico.
  ADVIERTE si algun control seleccionado tiene [REVISION NORMATIVA PENDIENTE] ya que su eficacia
  real puede ser menor de lo declarado.

Paso 4 — Identifica hasta 3 controles que FALTAN (no estan en la lista pero deberian estar).
  Da maxima prioridad a controles que cubririan vulnerabilidades con CVEs o hallazgos OSINT activos.

Responde SOLO con JSON valido:
{{
  "attack_chain_summary": "Descripcion en 2-3 frases de la cadena de ataque para este riesgo especifico",
  "suggested_ids": [lista de IDs enteros de controles que mitigan pasos del ataque],
  "control_to_step_mapping": [
    {{"control_id": 123, "attack_step": "nombre del paso que cubre", "control_type": "P|D|C", "why": "por que este control es relevante para este paso especifico"}}
  ],
  "missing_controls": [
    {{"iso27002_code": "X.XX", "name": "nombre", "attack_step": "paso que cubriria", "priority": "alta|media|baja"}}
  ],
  "rationale": "Justificacion global de la seleccion en 2-3 frases. Por que estos controles son los mas adecuados para reducir el riesgo residual."
}}"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        import json as _json
        raw = msg.content[0].text.strip()
        # Limpiar posible markdown
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = _json.loads(raw.strip())
        suggested_ids = [int(i) for i in data.get("suggested_ids", []) if i]
        # Validar que los IDs existen en el tenant
        valid_ids = {c.id for c in impls}
        suggested_ids = [i for i in suggested_ids if i in valid_ids]
        # Filtrar control_to_step_mapping a IDs validos
        mapping = [
            m for m in data.get("control_to_step_mapping", [])
            if int(m.get("control_id", 0)) in valid_ids
        ]
        return {
            "suggested_ids": suggested_ids,
            "rationale": data.get("rationale", ""),
            "attack_chain_summary": data.get("attack_chain_summary", ""),
            "control_to_step_mapping": mapping,
            "missing_controls": data.get("missing_controls", []),
        }
    except Exception as exc:
        raise HTTPException(500, f"Error en sugerencia IA: {exc}") from exc


@router.get("/{risk_id}/history")
def get_risk_history(
    risk_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(24, ge=1, le=120, description="Numero maximo de snapshots a devolver"),
):
    """Devuelve el historico de snapshots mensuales del riesgo (niveles inherente/residual en el tiempo)."""
    from app.models import RiskSnapshot

    risk = db.get(Risk, risk_id)
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    if not check_org_access(risk.organization_id, current_user):
        raise HTTPException(403)

    snapshots = (
        db.query(RiskSnapshot)
        .filter(RiskSnapshot.risk_id == risk_id)
        .order_by(RiskSnapshot.snapshot_date.asc())
        .limit(limit)
        .all()
    )

    return {
        "risk_id": risk_id,
        "risk_code": risk.code,
        "history": [
            {
                "snapshot_date": s.snapshot_date.isoformat() if s.snapshot_date else None,
                "inherent_likelihood": s.inherent_likelihood,
                "inherent_consequence": s.inherent_consequence,
                "inherent_level": s.inherent_level,
                "residual_likelihood": s.residual_likelihood,
                "residual_consequence": s.residual_consequence,
                "residual_level": s.residual_level,
                "control_count": s.control_count,
                "risk_status": s.risk_status,
            }
            for s in snapshots
        ],
        "total": len(snapshots),
    }


@router.get("/{risk_id}/simulate")
def simulate_what_if(
    risk_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ci_id: Optional[int] = Query(None, description="ID del ControlImplementation a modificar"),
    new_maturity: Optional[int] = Query(None, ge=0, le=5, description="Nueva madurez simulada (0-5)"),
    new_contribution: Optional[float] = Query(None, ge=0.0, le=1.0, description="Nueva contribucion simulada (0-1)"),
    add_ci_id: Optional[int] = Query(None, description="ID de un control adicional a vincular (simulado)"),
    add_contribution: Optional[float] = Query(0.5, ge=0.0, le=1.0),
    add_maturity: Optional[int] = Query(3, ge=0, le=5),
):
    """Simulacion what-if: calcula el impacto de cambiar/anadir controles sin persistir.

    Retorna: niveles actuales + niveles simulados + delta para apoyar decisiones de tratamiento.
    """
    from sqlalchemy import text as _text
    from app.services.risk_engine import control_reduction

    risk = db.get(Risk, risk_id)
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    if not check_org_access(risk.organization_id, current_user):
        raise HTTPException(403)

    matrix = _get_matrix(db, risk.organization_id)

    # Controles actuales con sus contribuciones reales
    rows = db.execute(
        _text("SELECT control_implementation_id, contribution FROM risk_controls WHERE risk_id = :rid"),
        {"rid": risk_id},
    ).fetchall()
    contrib_map = {row[0]: (row[1] if row[1] is not None else 1.0) for row in rows}

    controls_current = []
    for ci in (risk.controls or []):
        controls_current.append({
            "id": ci.id,
            "maturity": ci.maturity or 0,
            "contribution": contrib_map.get(ci.id, 1.0),
            "nc_penalty_factor": getattr(ci, "nc_penalty_factor", None),
            "ccm_fail": getattr(ci, "ccm_last_status", None) == "FAIL",
        })

    # Construir lista simulada
    controls_simulated = []
    for c in controls_current:
        sim = dict(c)
        if ci_id and c["id"] == ci_id:
            if new_maturity is not None:
                sim["maturity"] = new_maturity
            if new_contribution is not None:
                sim["contribution"] = new_contribution
        controls_simulated.append(sim)

    # Anadir control adicional si se solicita
    if add_ci_id is not None:
        ci_add = db.get(ControlImplementation, add_ci_id)
        if ci_add and check_org_access(ci_add.organization_id, current_user):
            controls_simulated.append({
                "id": ci_add.id,
                "maturity": add_maturity,
                "contribution": add_contribution,
                "nc_penalty_factor": getattr(ci_add, "nc_penalty_factor", None),
                "ccm_fail": getattr(ci_add, "ccm_last_status", None) == "FAIL",
            })

    # Calcular niveles actuales
    rl_cur, rc_cur, rlev_cur = calc_residual(
        risk.inherent_likelihood, risk.inherent_consequence, controls_current, matrix
    )

    # Calcular niveles simulados
    rl_sim, rc_sim, rlev_sim = calc_residual(
        risk.inherent_likelihood, risk.inherent_consequence, controls_simulated, matrix
    )

    ctx = _get_context(db, risk.organization_id)
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3

    return {
        "risk_id": risk_id,
        "risk_code": risk.code,
        "inherent_likelihood": risk.inherent_likelihood,
        "inherent_consequence": risk.inherent_consequence,
        "inherent_level": risk.inherent_level,
        "current": {
            "residual_likelihood": rl_cur,
            "residual_consequence": rc_cur,
            "residual_level": rlev_cur,
            "within_appetite": rlev_cur <= appetite,
        },
        "simulated": {
            "residual_likelihood": rl_sim,
            "residual_consequence": rc_sim,
            "residual_level": rlev_sim,
            "within_appetite": rlev_sim <= appetite,
        },
        "delta": {
            "likelihood": rl_sim - rl_cur,
            "consequence": rc_sim - rc_cur,
            "level": rlev_sim - rlev_cur,
        },
        "risk_appetite": appetite,
        "parameters": {
            "ci_id": ci_id,
            "new_maturity": new_maturity,
            "new_contribution": new_contribution,
            "add_ci_id": add_ci_id,
            "add_contribution": add_contribution,
            "add_maturity": add_maturity,
        },
    }


def _resolve_ai_key(db: Session, org_id: int) -> Optional[str]:
    """Resuelve la API key de Claude para la org (Fernet descifrado + fallback a settings)."""
    from app.models import AiConfig
    cfg = db.query(AiConfig).filter_by(organization_id=org_id).first()
    if cfg and cfg.api_key_encrypted:
        import base64, hashlib
        from cryptography.fernet import Fernet as _F
        from app.config import settings as _s
        key = base64.urlsafe_b64encode(hashlib.sha256(_s.secret_key.encode()).digest())
        try:
            return _F(key).decrypt(cfg.api_key_encrypted.encode()).decode()
        except Exception:
            return None
    from app.config import settings as _s
    return _s.anthropic_api_key


@router.post("/ai-discover")
def ai_discover_risks(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """IA detecta riesgos no registrados examinando activos, amenazas y brechas de cobertura.

    Analiza los activos sin riesgos asignados y las amenazas del catalogo no cubiertas,
    y sugiere una lista priorizadas de nuevos riesgos a registrar.
    """
    import anthropic
    import json as _json

    org_id = current_user.organization_id
    api_key = _resolve_ai_key(db, org_id)
    if not api_key:
        raise HTTPException(400, "API key no configurada. Ve a Configuracion > Agente IA.")

    from app.models import AiConfig, Asset, Threat
    ai_cfg = db.query(AiConfig).filter_by(organization_id=org_id).first()
    model = (ai_cfg.model if ai_cfg else None) or "claude-haiku-4-5"

    # Activos sin riesgos vinculados
    assets_all = db.query(Asset).filter(Asset.organization_id == org_id).all()
    assets_with_risks = {r.asset_id for r in filter_by_org(db.query(Risk), Risk, current_user).all() if r.asset_id}
    assets_uncovered = [a for a in assets_all if a.id not in assets_with_risks][:15]

    # Amenazas del catalogo no usadas en riesgos activos
    threats_all = db.query(Threat).filter(
        (Threat.organization_id == org_id) | (Threat.organization_id.is_(None))
    ).all()
    threats_used = {r.threat_id for r in filter_by_org(db.query(Risk), Risk, current_user).all() if r.threat_id}
    threats_unused = [t for t in threats_all if t.id not in threats_used][:20]

    asset_lines = "\n".join(
        f"  - [{a.code}] {a.name} ({getattr(a.asset_type, 'value', 'N/A')}) "
        f"valor_disponibilidad={a.value_availability} valor_confidencialidad={a.value_confidentiality}"
        for a in assets_uncovered
    ) or "  (todos los activos tienen riesgos)"

    threat_lines = "\n".join(
        f"  - [{t.code}] {t.name} ({t.category})"
        for t in threats_unused
    ) or "  (todas las amenazas cubiertas)"

    prompt = f"""Eres un auditor ISO 27005 senior. Analiza las brechas de cobertura de riesgos:

ACTIVOS SIN RIESGOS ASIGNADOS:
{asset_lines}

AMENAZAS DEL CATALOGO NO CUBIERTAS EN NINGUN RIESGO:
{threat_lines}

Identifica hasta 10 combinaciones activo+amenaza que representan riesgos no registrados y que deberian ser evaluados.
Para cada uno indica:
- asset_code: codigo del activo
- asset_name: nombre del activo
- threat_code: codigo de la amenaza
- threat_name: nombre de la amenaza
- inherent_likelihood: estimacion 0-4 (ISO 27005 Annex E)
- inherent_consequence: estimacion 0-4
- justification: 1-2 frases en castellano explicando el riesgo

Responde SOLO con JSON valido:
{{"risks": [{{"asset_code":"...","asset_name":"...","threat_code":"...","threat_name":"...","inherent_likelihood":2,"inherent_consequence":3,"justification":"..."}}]}}
"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        data = _json.loads(raw)
        return {"discovered_risks": data.get("risks", []), "model": model}
    except Exception as exc:
        raise HTTPException(500, f"Error en AI discovery: {exc}") from exc


@router.post("/{risk_id}/ai-scenario")
def ai_attack_scenario(
    risk_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera un escenario de ataque detallado para el riesgo usando analisis IA.

    Construye la cadena de kill-chain (MITRE ATT&CK), identifica vectores reales
    (OSINT/CVE si existen), y estima el impacto economico.
    """
    import anthropic
    import json as _json
    from app.models import AiConfig

    risk = db.get(Risk, risk_id)
    if not risk or not check_org_access(risk.organization_id, current_user):
        raise HTTPException(404, "Riesgo no encontrado")

    org_id = risk.organization_id
    api_key = _resolve_ai_key(db, org_id)
    if not api_key:
        raise HTTPException(400, "API key no configurada.")

    ai_cfg = db.query(AiConfig).filter_by(organization_id=org_id).first()
    model = (ai_cfg.model if ai_cfg else None) or "claude-haiku-4-5"

    asset = risk.asset
    threat = risk.threat
    vulns = risk.vulnerabilities or []
    estimated_value = (asset.estimated_value if asset and hasattr(asset, "estimated_value") else None) or 0

    prompt = f"""Eres un experto en ciberseguridad ofensiva y analisis de riesgo ISO 27005.

RIESGO: {risk.code} — {risk.description or risk.code}
ACTIVO: {asset.name if asset else 'N/A'} (valor estimado: {estimated_value} EUR)
AMENAZA: {threat.name if threat else 'N/A'} ({getattr(threat, 'category', 'N/A')})
VULNERABILIDADES: {', '.join(v.name for v in vulns) or 'No especificadas'}
NIVEL RESIDUAL ACTUAL: {risk.residual_level}/8
NIVEL INHERENTE: {risk.inherent_level}/8

Genera un escenario de ataque realista con:
1. kill_chain: lista de pasos (Reconocimiento, Acceso inicial, Escalada, Exfiltracion/Impacto)
2. mitre_ttps: lista de IDs MITRE ATT&CK relevantes
3. attack_vector: vector de entrada mas probable
4. business_impact: descripcion del impacto en el negocio
5. estimated_loss_eur: estimacion de perdida economica en EUR (rango min-max)
6. probability_12m_pct: probabilidad de materializacion en los proximos 12 meses (0-100)
7. early_warning_indicators: 3-5 indicadores tempranos de que el ataque se esta produciendo

Responde SOLO con JSON valido:
{{"kill_chain":[],"mitre_ttps":[],"attack_vector":"","business_impact":"","estimated_loss_eur":{{"min":0,"max":0}},"probability_12m_pct":0,"early_warning_indicators":[]}}
"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        data = _json.loads(raw)
        data["risk_id"] = risk_id
        data["risk_code"] = risk.code
        data["model"] = model
        return data
    except Exception as exc:
        raise HTTPException(500, f"Error en scenario analysis: {exc}") from exc


@router.get("/{risk_id}/value-at-risk")
def value_at_risk(
    risk_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    simulations: int = Query(10000, ge=1000, le=100000, description="Iteraciones Monte Carlo"),
):
    """Calcula el Value at Risk (VaR) economico mediante simulacion Monte Carlo.

    Usa el valor del activo (Asset.estimated_value) y los niveles ISO 27005 para
    estimar la distribucion de perdidas esperadas con intervalos de confianza.
    """
    import random
    import math

    risk = db.get(Risk, risk_id)
    if not risk or not check_org_access(risk.organization_id, current_user):
        raise HTTPException(404, "Riesgo no encontrado")

    asset = risk.asset
    estimated_value = getattr(asset, "estimated_value", None) if asset else None
    if not estimated_value or estimated_value <= 0:
        return {
            "risk_id": risk_id,
            "risk_code": risk.code,
            "error": "El activo no tiene valor estimado configurado (Asset.estimated_value)",
            "var_95": None,
            "var_99": None,
            "expected_loss": None,
        }

    # Parametros: probabilidad anual y factor de impacto desde niveles ISO 27005
    # Likelihood (0-4) → probabilidad anual aproximada
    lik_to_prob = {0: 0.01, 1: 0.05, 2: 0.15, 3: 0.40, 4: 0.75}
    # Consequence (0-4) → fraccion del valor del activo perdida
    con_to_impact = {0: 0.02, 1: 0.10, 2: 0.30, 3: 0.60, 4: 0.95}

    inh_prob = lik_to_prob.get(risk.inherent_likelihood or 0, 0.15)
    inh_impact_frac = con_to_impact.get(risk.inherent_consequence or 0, 0.30)
    res_prob = lik_to_prob.get(risk.residual_likelihood or 0, 0.05)
    res_impact_frac = con_to_impact.get(risk.residual_consequence or 0, 0.10)

    def _monte_carlo(prob: float, impact_frac: float, n: int) -> list[float]:
        losses = []
        for _ in range(n):
            if random.random() < prob:
                # Impacto con variacion triangular (min=10%, mode=100%, max=150%)
                tri = random.triangular(0.10, 1.50, 1.0)
                losses.append(estimated_value * impact_frac * tri)
            else:
                losses.append(0.0)
        return sorted(losses)

    inh_losses = _monte_carlo(inh_prob, inh_impact_frac, simulations)
    res_losses = _monte_carlo(res_prob, res_impact_frac, simulations)

    def _percentile(data: list[float], p: float) -> float:
        idx = int(len(data) * p / 100)
        return round(data[min(idx, len(data) - 1)], 2)

    return {
        "risk_id": risk_id,
        "risk_code": risk.code,
        "asset_value_eur": estimated_value,
        "simulations": simulations,
        "inherent": {
            "annual_probability": inh_prob,
            "impact_fraction": inh_impact_frac,
            "expected_loss": round(sum(inh_losses) / simulations, 2),
            "var_95": _percentile(inh_losses, 95),
            "var_99": _percentile(inh_losses, 99),
            "max_loss": round(max(inh_losses), 2),
        },
        "residual": {
            "annual_probability": res_prob,
            "impact_fraction": res_impact_frac,
            "expected_loss": round(sum(res_losses) / simulations, 2),
            "var_95": _percentile(res_losses, 95),
            "var_99": _percentile(res_losses, 99),
            "max_loss": round(max(res_losses), 2),
        },
        "control_value_eur": round(
            sum(inh_losses) / simulations - sum(res_losses) / simulations, 2
        ),
    }
