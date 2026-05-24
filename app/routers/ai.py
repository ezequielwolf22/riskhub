"""Endpoints del agente IA: cuestionario + análisis de riesgos + sugerencias."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Any, Optional

from app.database import get_db
from app.models import (
    Asset, AssetType, ControlImplementation, ControlStatus,
    Incident, IncidentStatus, NonConformity, NCStatus,
    Risk, RiskStatus, Supplier, SupplierRisk, Threat, TreatmentOption, User,
)
from app.security import get_current_user, require_role
from app.services.ai_service import QUESTIONNAIRE, run_analysis

router = APIRouter(prefix="/api/ai", tags=["ai"])


class AnalyzeRequest(BaseModel):
    answers: dict[str, Any]


class ImportRequest(BaseModel):
    scenarios: list[dict[str, Any]]


@router.get("/questionnaire")
def get_questionnaire(_: User = Depends(get_current_user)):
    """Devuelve la definición del cuestionario de contexto organizacional."""
    return {"questions": QUESTIONNAIRE}


@router.post("/analyze")
def analyze(
    req: AnalyzeRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Envía las respuestas al agente IA y devuelve el análisis de riesgos."""
    try:
        result = run_analysis(req.answers, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el análisis: {str(e)}")


@router.post("/import")
def import_risks(
    req: ImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Importa los escenarios seleccionados como riesgos en la base de datos."""
    created = []
    skipped = []

    # Función auxiliar para generar código de activo
    def _next_asset_code() -> str:
        n = db.query(Asset).count() + 1
        return f"AST-{n:04d}"

    # Cache de amenazas por código
    threat_by_code = {t.code: t for t in db.query(Threat).all()}
    threat_by_name = {t.name.lower(): t for t in db.query(Threat).all()}

    for sc in req.scenarios:
        # Resolver o crear activo
        asset = None
        if sc.get("asset_id"):
            asset = db.query(Asset).filter(Asset.id == sc["asset_id"]).first()

        if not asset and sc.get("asset_suggestion"):
            existing = db.query(Asset).filter(
                Asset.name == sc["asset_suggestion"]
            ).first()
            if existing:
                asset = existing
            else:
                try:
                    atype = AssetType(sc.get("asset_type", "support_hardware"))
                except ValueError:
                    atype = AssetType.SUPPORT_HARDWARE
                asset = Asset(
                    code=_next_asset_code(),
                    name=sc["asset_suggestion"],
                    asset_type=atype,
                    description="Activo generado por analisis IA",
                )
                db.add(asset)
                db.flush()

        if not asset:
            skipped.append(sc.get("asset_suggestion", "desconocido"))
            continue

        # Resolver amenaza
        threat = None
        if sc.get("threat_code"):
            threat = threat_by_code.get(sc["threat_code"])
        if not threat and sc.get("threat_name"):
            threat = threat_by_name.get(sc["threat_name"].lower())
        if not threat:
            skipped.append(f"{sc.get('asset_suggestion')} / {sc.get('threat_name')}")
            continue

        # Comprobar duplicados
        dup = db.query(Risk).filter(
            Risk.asset_id == asset.id,
            Risk.threat_id == threat.id,
        ).first()
        if dup:
            skipped.append(f"{asset.name} × {threat.name} (duplicado)")
            continue

        # Calcular código
        count = db.query(Risk).count() + len(created) + 1
        code = f"RSK-{count:04d}"

        risk = Risk(
            code=code,
            asset_id=asset.id,
            threat_id=threat.id,
            vulnerability_description=sc.get("vulnerability_description", ""),
            inherent_consequence=sc.get("inherent_consequence", 2),
            inherent_likelihood=sc.get("inherent_likelihood", 2),
            inherent_level=sc.get("inherent_level", 4),
            residual_consequence=sc.get("residual_consequence", 1),
            residual_likelihood=sc.get("residual_likelihood", 1),
            residual_level=sc.get("residual_level", 1),
            status=RiskStatus.IDENTIFIED,
            treatment_option=TreatmentOption.MODIFICATION,
            description=sc.get("rationale", ""),
            owner_id=current_user.id,
        )
        db.add(risk)
        created.append(f"{asset.name} × {threat.name}")

    db.commit()
    return {
        "created": len(created),
        "skipped": len(skipped),
        "detail_created": created,
        "detail_skipped": skipped,
    }


# ============================================================
# Compliance dashboard data — multi-framework scoring
# ============================================================

@router.get("/compliance/summary")
def compliance_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Calcula puntuaciones de cumplimiento para ISO 27001, NIS2, NIST CSF y ENS."""
    impls = db.query(ControlImplementation).all()
    total_controls = len(impls)
    implemented = sum(1 for i in impls if i.status == ControlStatus.IMPLEMENTED)
    partial = sum(1 for i in impls if i.status == ControlStatus.PARTIAL)
    effective_score = (implemented + partial * 0.5) / total_controls * 100 if total_controls else 0

    risks = db.query(Risk).all()
    risks_with_treatment = sum(1 for r in risks if r.treatment_option)
    risks_with_owner = sum(1 for r in risks if r.owner_id)
    risks_assessed = sum(1 for r in risks if r.status in (RiskStatus.ASSESSED, RiskStatus.TREATED, RiskStatus.ACCEPTED, RiskStatus.CLOSED))
    total_risks = len(risks)

    incidents = db.query(Incident).all()
    suppliers = db.query(Supplier).all()
    ncs = db.query(NonConformity).all()
    open_major_ncs = sum(1 for n in ncs if n.severity == "major" and n.status != NCStatus.CLOSED)

    # ---- ISO 27001:2022 score ----
    iso_components = [
        effective_score,                                          # 6.1.3 controles
        (risks_with_treatment / total_risks * 100) if total_risks else 0,  # 6.1.2 tratamiento
        (risks_with_owner / total_risks * 100) if total_risks else 0,      # 6.1.2 propietario
        (risks_assessed / total_risks * 100) if total_risks else 0,        # 8.3 estado
        100 if len(ncs) == 0 or open_major_ncs == 0 else max(0, 100 - open_major_ncs * 20),  # 10.1 NC
    ]
    iso_score = round(sum(iso_components) / len(iso_components))

    # ---- NIS2 score ----
    has_incident_mgmt = len(incidents) >= 0  # modulo activo
    nis2_pending = sum(1 for i in incidents if i.nis2_notification_required and not i.nis2_notification_sent_at)
    supplier_assessed = sum(1 for s in suppliers if s.last_assessment_at) if suppliers else 0
    supplier_total = len(suppliers) if suppliers else 1
    nis2_components = [
        effective_score * 0.4,             # medidas tecnicas (controles)
        100 if nis2_pending == 0 else max(0, 100 - nis2_pending * 25),  # notificacion
        supplier_assessed / supplier_total * 100,  # supply chain
        (risks_with_treatment / total_risks * 100) if total_risks else 0,  # gestion riesgos
    ]
    nis2_score = round(sum(nis2_components) / len(nis2_components))

    # ---- NIST CSF 2.0 score ----
    identify_score = min(100, (total_risks / max(1, len(db.query(Asset).all())) * 100))
    protect_score = effective_score
    detect_score = min(100, len(incidents) * 10)  # evidencia de deteccion activa
    respond_score = min(100, sum(1 for i in incidents if i.status in (IncidentStatus.CONTAINED, IncidentStatus.RESOLVED, IncidentStatus.CLOSED)) / max(1, len(incidents)) * 100)
    recover_score = min(100, sum(1 for i in incidents if i.lessons_learned) / max(1, len(incidents)) * 100)
    govern_score = min(100, (
        (50 if risks_with_owner > 0 else 0) +
        (50 if total_controls > 0 else 0)
    ))
    nist_score = round((govern_score + identify_score + protect_score + detect_score + respond_score + recover_score) / 6)

    # ---- ENS score (RD 311/2022) ----
    # ENS usa las mismas 5 dimensiones CIA+A+T y controles similares a ISO
    ens_components = [
        effective_score,                   # Anexo II medidas
        (risks_with_owner / total_risks * 100) if total_risks else 0,  # responsables
        100 if open_major_ncs == 0 else max(0, 100 - open_major_ncs * 20),  # mejora continua
    ]
    ens_score = round(sum(ens_components) / len(ens_components))

    return {
        "iso27001": {
            "score": iso_score,
            "label": "ISO/IEC 27001:2022",
            "gaps": _iso_gaps(impls, risks, ncs),
        },
        "nis2": {
            "score": nis2_score,
            "label": "NIS2 Directiva EU 2022/2555",
            "gaps": _nis2_gaps(incidents, suppliers, nis2_pending),
        },
        "nist_csf": {
            "score": nist_score,
            "label": "NIST CSF 2.0",
            "functions": {
                "GOVERN": round(govern_score),
                "IDENTIFY": round(identify_score),
                "PROTECT": round(protect_score),
                "DETECT": round(detect_score),
                "RESPOND": round(respond_score),
                "RECOVER": round(recover_score),
            },
        },
        "ens": {
            "score": ens_score,
            "label": "ENS RD 311/2022",
            "gaps": _ens_gaps(impls, risks),
        },
        "_meta": {
            "total_controls": total_controls,
            "implemented_controls": implemented,
            "total_risks": total_risks,
            "risks_treated": risks_with_treatment,
            "open_incidents": sum(1 for i in incidents if i.status != IncidentStatus.CLOSED),
            "open_ncs": sum(1 for n in ncs if n.status != NCStatus.CLOSED),
        },
    }


def _iso_gaps(impls, risks, ncs) -> list[str]:
    gaps = []
    if not impls:
        gaps.append("Sin controles ISO 27002 implementados (cl. 6.1.3)")
    soa_missing_reason = sum(1 for i in impls if not i.inclusion_reason)
    if soa_missing_reason > 0:
        gaps.append(f"SOA: {soa_missing_reason} controles sin justificacion de inclusion (cl. 6.1.3)")
    soa_missing_evidence = sum(1 for i in impls if not i.evidence_refs)
    if soa_missing_evidence > 0:
        gaps.append(f"SOA: {soa_missing_evidence} controles sin referencia de evidencia (cl. 6.1.3)")
    no_owner = sum(1 for r in risks if not r.owner_id and r.status not in (RiskStatus.CLOSED,))
    if no_owner > 0:
        gaps.append(f"{no_owner} riesgos activos sin propietario asignado (cl. 6.1.2)")
    major_open = sum(1 for n in ncs if n.severity == "major" and n.status != NCStatus.CLOSED)
    if major_open > 0:
        gaps.append(f"{major_open} no conformidades mayores abiertas (cl. 10.1)")
    return gaps


def _nis2_gaps(incidents, suppliers, nis2_pending) -> list[str]:
    gaps = []
    if nis2_pending > 0:
        gaps.append(f"{nis2_pending} incidentes con notificacion NIS2 pendiente (Art. 23 — plazo 72h)")
    if not suppliers:
        gaps.append("Sin proveedores evaluados — riesgo de cadena de suministro no gestionado (Art. 21.2.d)")
    no_assessment = sum(1 for s in suppliers if not s.last_assessment_at) if suppliers else 0
    if no_assessment > 0:
        gaps.append(f"{no_assessment} proveedores sin evaluacion completada (Art. 21.2.d)")
    return gaps


def _ens_gaps(impls, risks) -> list[str]:
    gaps = []
    not_implemented = sum(1 for i in impls if i.status == ControlStatus.NOT_IMPLEMENTED)
    if not_implemented > 0:
        gaps.append(f"{not_implemented} controles no implementados (Anexo II ENS)")
    no_review = sum(1 for i in impls if not i.next_review)
    if no_review > 0:
        gaps.append(f"{no_review} controles sin fecha de revision programada")
    return gaps


# ============================================================
# AI Risk Suggestion — sugiere riesgos para un activo
# ============================================================

class RiskSuggestRequest(BaseModel):
    asset_id: int
    context_hint: Optional[str] = None   # texto libre adicional


@router.post("/risk-suggest")
def risk_suggest(
    req: RiskSuggestRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Sugiere amenazas y nivel de riesgo para un activo usando el catalogo ISO 27005."""
    asset = db.query(Asset).filter(Asset.id == req.asset_id).first()
    if not asset:
        raise HTTPException(404, "Activo no encontrado")

    # Obtener amenazas del catalogo que tipicamente aplican a este tipo de activo
    all_threats = db.query(Threat).all()
    asset_type_val = asset.asset_type.value if asset.asset_type else ""

    relevant_threats = [
        t for t in all_threats
        if not t.typical_assets or asset_type_val in (t.typical_assets or [])
    ]
    if not relevant_threats:
        relevant_threats = all_threats[:15]

    # Obtener riesgos existentes para este activo (para evitar duplicados)
    existing_threat_ids = {
        r.threat_id for r in db.query(Risk).filter(Risk.asset_id == asset.id).all()
    }

    # Estimar likelihood basado en origen de amenaza y valoracion del activo
    asset_value = asset.value_max or 2
    suggestions = []
    for threat in relevant_threats[:20]:
        if threat.id in existing_threat_ids:
            continue
        # Likelihood base por origen: D=probable, A=posible, E=improbable
        origin_lik = {"D": 3, "A": 2, "E": 1}.get(threat.origin.value if threat.origin else "A", 2)
        # Ajuste por valor del activo (mas valioso = mas atractivo para atacante)
        lik = min(4, origin_lik + (1 if asset_value >= 3 else 0))
        # Consecuencia basada en que dimensiones afecta y valor del activo
        affected_dims = len(threat.affects or [])
        cons = min(4, max(1, asset_value - 1 + (1 if affected_dims >= 3 else 0)))
        from app.services.risk_engine import calc_level
        level = calc_level(cons, lik)
        suggestions.append({
            "threat_id": threat.id,
            "threat_code": threat.code,
            "threat_name": threat.name,
            "threat_origin": threat.origin.value if threat.origin else None,
            "threat_category": threat.category,
            "suggested_likelihood": lik,
            "suggested_consequence": cons,
            "suggested_level": level,
            "rationale": (
                f"Amenaza de origen {'deliberado' if threat.origin and threat.origin.value=='D' else 'accidental/ambiental'} "
                f"aplicable a activos tipo {asset_type_val}. "
                f"Valor del activo: {asset_value}/4. "
                f"Afecta dimensiones: {', '.join(threat.affects or []) or 'N/A'}."
            ),
        })

    # Ordenar por nivel sugerido desc
    suggestions.sort(key=lambda x: x["suggested_level"], reverse=True)

    return {
        "asset_id": asset.id,
        "asset_name": asset.name,
        "asset_type": asset_type_val,
        "suggestions": suggestions[:10],
        "note": "Sugerencias basadas en catalogo ISO 27005 Annex C. Revisar y ajustar segun contexto especifico.",
    }
