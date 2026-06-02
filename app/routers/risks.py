"""CRUD de riesgos + calculo automatico inherente/residual + tratamiento."""
import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
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

router = APIRouter(prefix="/api/risks", tags=["risks"])


def _next_code(db: Session, org_id: int) -> str:
    n = db.query(Risk).filter(Risk.organization_id == org_id).count() + 1
    return f"RSK-{n:04d}"


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
    matrix = _get_matrix(db, risk.organization_id)

    # MAGERIT: si aplica, sobrescribir inherent_consequence antes de calcular
    _apply_magerit_consequence(risk, db)

    risk.inherent_level = calc_level(
        risk.inherent_consequence, risk.inherent_likelihood, matrix)
    controls = [{"maturity": ci.maturity, "contribution": 1.0} for ci in risk.controls]
    rl, rc, rlev = calc_residual(
        risk.inherent_likelihood, risk.inherent_consequence, controls, matrix)
    risk.residual_likelihood = rl
    risk.residual_consequence = rc
    risk.residual_level = rlev

    # Auto-tratamiento basado en apetito de riesgo
    ctx = _get_context(db, risk.organization_id)
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3
    if rlev <= appetite and risk.status not in (RiskStatus.CLOSED,):
        if risk.treatment_option in (None, TreatmentOption.MODIFICATION, TreatmentOption.RETENTION):
            risk.treatment_option = TreatmentOption.RETENTION
            if risk.status in (RiskStatus.IDENTIFIED, RiskStatus.ASSESSED):
                risk.status = RiskStatus.ACCEPTED
                # Riesgos aceptados deben revisarse anualmente
                if not risk.next_review:
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
    return q.order_by(Risk.residual_level.desc(), Risk.code).all()


@router.get("/{risk_id}", response_model=RiskOut)
def get_risk(risk_id: int, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    r = db.get(Risk, risk_id)
    if not r or not check_org_access(r.organization_id, current_user):
        raise HTTPException(404, "Riesgo no encontrado")
    return r


@router.get("/{risk_id}/trace")
def risk_trace(
    risk_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trazabilidad completa: desglosa cada control vinculado al riesgo con
    cálculo de eficacia, madurez, fuentes de evidencia y referencias SOA.
    Crítico para justificar el nivel residual ante una auditoría ISO 27001."""
    from sqlalchemy import select
    from app.models import Evidence, risk_control_table
    from app.services.risk_engine import control_reduction, LIKELIHOOD_LABELS, CONSEQUENCE_LABELS

    r = db.get(Risk, risk_id)
    if not r or not check_org_access(r.organization_id, current_user):
        raise HTTPException(404, "Riesgo no encontrado")

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
        })
        ctrl_dicts_for_engine.append({"maturity": mat, "contribution": contrib})

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

    r = db.get(Risk, risk_id)
    if not r or not check_org_access(r.organization_id, current_user):
        raise HTTPException(404, "Riesgo no encontrado")

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
    model = (cfg.model if cfg else None) or "claude-opus-4-7"

    # Contexto organizacional
    ctx = db.query(RiskContext).filter_by(organization_id=current_user.organization_id).first()
    qa = (ctx.questionnaire_answers or {}) if ctx else {}
    frameworks = (ctx.active_frameworks or []) if ctx else []

    # Controles con sus fuentes
    rows = db.execute(
        select(risk_control_table.c.control_implementation_id, risk_control_table.c.contribution)
        .where(risk_control_table.c.risk_id == risk_id)
    ).all()
    ctrl_lines = []
    for row in rows:
        impl = db.get(ControlImplementation, row.control_implementation_id)
        if not impl:
            continue
        mat = impl.maturity or 0
        contrib = float(row.contribution) if row.contribution is not None else 1.0
        eff = round((mat / 5.0) * contrib * 100)
        refs = "; ".join(r2.get("title", "") for r2 in (impl.evidence_refs or []))
        evd_count = db.query(Evidence).filter_by(control_implementation_id=impl.id, is_current=True).count()
        ctrl_lines.append(
            f"  - [{impl.control.code if impl.control else '?'}] {impl.name}: "
            f"estado={impl.status.value if impl.status else 'N/A'}, madurez={mat}/5, "
            f"eficacia={eff}%, contribucion={contrib:.0%}"
            + (f", refs='{refs}'" if refs else "")
            + (f", evidencias_archivo={evd_count}" if evd_count else "")
            + (f", razon_inclusion='{impl.inclusion_reason}'" if impl.inclusion_reason else "")
        )

    # Vulnerabilidades
    vuln_lines = [f"  - [{v.code}] {v.name}: {(v.description or '')[:120]}" for v in (r.vulnerabilities or [])]

    # RAG: buscar documentación relevante
    rag_query = f"{r.asset.name if r.asset else ''} {r.threat.name if r.threat else ''} {r.description or ''}"
    rag_chunks = search_chunks_with_source(db, rag_query, top_k=4, organization_id=current_user.organization_id)
    rag_section = ""
    if rag_chunks:
        rag_section = "\n\nDOCUMENTACIÓN INTERNA RELEVANTE (RAG):\n" + "\n---\n".join(
            f"[{c['doc_name']}]:\n{c['content'][:600]}" for c in rag_chunks
        )

    prompt = f"""Eres un auditor senior certificado en ISO/IEC 27001:2022 e ISO/IEC 27005:2018,
con amplia experiencia en análisis de riesgos empresariales y revisiones SOA.

Analiza el siguiente riesgo de seguridad y proporciona una evaluación experta, rigurosa y completamente
alineada con la realidad del activo y la organización. NO seas genérico. Usa los datos exactos.

=== RIESGO ===
Código: {r.code}
Activo: {r.asset.name if r.asset else 'N/A'} (tipo: {r.asset.asset_type.value if r.asset and r.asset.asset_type else 'N/A'})
{"CIA del activo: C=" + str(r.asset.value_confidentiality) + " I=" + str(r.asset.value_integrity) + " A=" + str(r.asset.value_availability) if r.asset else ""}
Amenaza: {r.threat.name if r.threat else 'N/A'} (código: {r.threat.code if r.threat else 'N/A'}, origen: {r.threat.origin.value if r.threat and r.threat.origin else 'N/A'})
Descripción del escenario: {r.description or 'Sin descripción'}
Consecuencia esperada: {r.consequence_description or 'Sin definir'}
Nivel inherente: {r.inherent_level}/8 (probabilidad={r.inherent_likelihood}, consecuencia={r.inherent_consequence})
Nivel residual: {r.residual_level}/8 (probabilidad={r.residual_likelihood}, consecuencia={r.residual_consequence})
Reducción: {round((1 - r.residual_level / r.inherent_level) * 100) if r.inherent_level else 0}%
Tratamiento: {r.treatment_option.value if r.treatment_option else 'Sin definir'}
Estado: {r.status.value}

=== VULNERABILIDADES ASOCIADAS ===
{chr(10).join(vuln_lines) if vuln_lines else '  (ninguna registrada)'}

=== CONTROLES MITIGANTES (con fuentes) ===
{chr(10).join(ctrl_lines) if ctrl_lines else '  (ningún control vinculado)'}

=== CONTEXTO ORGANIZACIONAL ===
Sector: {qa.get('sector', 'N/A')}
Empleados: {qa.get('employees', 'N/A')}
Normativas aplicables: {', '.join(qa.get('regulations', [])) or 'N/A'}
Sistemas: {', '.join(qa.get('systems', [])) or 'N/A'}
Tipos de datos: {', '.join(qa.get('data_types', [])) or 'N/A'}
Acceso remoto: {qa.get('remote_access', 'N/A')}
Madurez global: {qa.get('maturity', 'N/A')}
Frameworks activos: {', '.join(frameworks) or 'N/A'}
{rag_section}

=== INSTRUCCIONES ===
Devuelve EXCLUSIVAMENTE JSON válido con esta estructura exacta:
{{
  "executive_summary": "Párrafo de 3-5 frases explicando el riesgo, su relevancia para esta organización concreta y por qué el nivel calculado es correcto. Referencia al sector y tipo de activo.",
  "why_inherent_level": "Explicación técnica de por qué el nivel inherente es {r.inherent_level}. Justifica la probabilidad {r.inherent_likelihood} y la consecuencia {r.inherent_consequence} para este activo y amenaza concretos.",
  "why_residual_level": "Explicación detallada de cómo los controles existentes reducen el riesgo al nivel residual {r.residual_level}. Cita controles por nombre y eficacia. Si hay brechas, mencionarlas.",
  "source_analysis": "Análisis de la calidad de las fuentes de evidencia. ¿Las referencias documentales justifican adecuadamente la madurez declarada? ¿Hay controles sin evidencia que debería tenerla?",
  "gaps_and_recommendations": ["Brecha o recomendación concreta 1", "Brecha o recomendación concreta 2", "..."],
  "soa_implications": "Cómo este riesgo y sus controles deben reflejarse en la Declaración de Aplicabilidad (SOA). Qué controles ISO 27002:2022 son clave y si están correctamente justificados.",
  "normative_alignment": "Cómo se alinea este riesgo con las normativas activas ({', '.join(frameworks) or 'ISO 27001'}). Requisitos específicos que aplican.",
  "confidence": "alta|media|baja",
  "confidence_reason": "Por qué la confianza en el análisis es alta/media/baja (p.ej. falta de evidencias, controles sin madurez real, etc.)"
}}
Sin texto antes ni después del JSON."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=2048,
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
def create_risk(data: RiskIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    asset = db.get(Asset, data.asset_id)
    if not asset or not check_org_access(asset.organization_id, current_user):
        raise HTTPException(400, "asset_id no existe")
    if not db.get(Threat, data.threat_id):
        raise HTTPException(400, "threat_id no existe")
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
                f"Ya existe el riesgo {existing_dup.code} para este activo y amenaza. "
                f"Edita el riesgo existente en lugar de crear uno nuevo."
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
    if data.control_implementation_ids:
        r.controls = db.query(ControlImplementation).filter(
            ControlImplementation.id.in_(data.control_implementation_ids)).all()
    _recalc(db, r)
    db.add(r)
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

    return r


@router.patch("/{risk_id}", response_model=RiskOut)
def update_risk(risk_id: int, data: RiskUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_analyst)):
    r = db.get(Risk, risk_id)
    if not r or not check_org_access(r.organization_id, user):
        raise HTTPException(404, "Riesgo no encontrado")

    update_data = data.model_dump(exclude_unset=True)
    if "vulnerability_ids" in update_data:
        ids = update_data.pop("vulnerability_ids")
        r.vulnerabilities = db.query(Vulnerability).filter(
            Vulnerability.id.in_(ids or [])).all()
    if "control_implementation_ids" in update_data:
        ids = update_data.pop("control_implementation_ids")
        r.controls = db.query(ControlImplementation).filter(
            ControlImplementation.id.in_(ids or [])).all()

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
def delete_risk(risk_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    r = db.get(Risk, risk_id)
    if not r or not check_org_access(r.organization_id, current_user):
        raise HTTPException(404, "Riesgo no encontrado")
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

        n = db.query(Risk).count() + len(created) + 1
        code = f"RSK-{n:04d}"

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
            residual_level=calc_residual(ic, il, rc, rl),
            status=status,
            treatment_option=treatment,
            treatment_plan=(row.get("Plan_Tratamiento") or "").strip(),
            treatment_due_date=due_date,
            owner_id=current_user.id,
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
    by_band = {"low": 0, "medium": 0, "high": 0}
    for r in risks:
        if r.residual_level <= 2: by_band["low"] += 1
        elif r.residual_level <= 5: by_band["medium"] += 1
        else: by_band["high"] += 1
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

    return {
        "total_risks": len(risks),
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


# ── Risk Acceptance Formal Workflow (ISO 27001 cl. 6.1.2e) ───────────────────

class AcceptanceRequestBody(BaseModel):
    justification: str
    review_date: Optional[str] = None   # fecha de re-evaluacion ISO 8601


class AcceptanceRejectBody(BaseModel):
    reason: Optional[str] = None


@router.put("/{risk_id}/request-acceptance")
def request_acceptance(
    risk_id: int,
    body: AcceptanceRequestBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Analyst propone aceptacion formal del riesgo (PENDING_ACCEPTANCE)."""
    risk = db.get(Risk, risk_id)
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    check_org_access(risk.organization_id, current_user)

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
    body: AcceptanceRequestBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin / risk owner aprueba la aceptacion formal del riesgo."""
    from app.security import require_admin
    from app.models import UserRole
    risk = db.get(Risk, risk_id)
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    check_org_access(risk.organization_id, current_user)

    # Solo admin o el owner del riesgo pueden aceptar
    is_admin = current_user.role in (UserRole.ADMIN, UserRole.SUPERADMIN)
    is_owner = risk.owner_id == current_user.id
    if not (is_admin or is_owner):
        raise HTTPException(403, "Solo admin o el risk owner pueden aprobar la aceptacion")

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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin / risk owner rechaza la solicitud de aceptacion → vuelve a ASSESSED."""
    from app.models import UserRole
    risk = db.get(Risk, risk_id)
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    check_org_access(risk.organization_id, current_user)

    is_admin = current_user.role in (UserRole.ADMIN, UserRole.SUPERADMIN)
    is_owner = risk.owner_id == current_user.id
    if not (is_admin or is_owner):
        raise HTTPException(403, "Solo admin o el risk owner pueden rechazar la aceptacion")

    if risk.status != RiskStatus.PENDING_ACCEPTANCE:
        raise HTTPException(400, "El riesgo no esta en estado PENDING_ACCEPTANCE")

    risk.status = RiskStatus.ASSESSED
    if body.reason:
        risk.acceptance_justification = (risk.acceptance_justification or "") + f"\nRechazado: {body.reason}"

    db.commit()
    log_action(db, current_user.id, "reject_acceptance", "risk", str(risk_id),
               {"code": risk.code, "reason": body.reason})
    return {"status": "assessed", "risk_code": risk.code}
