"""Endpoints del agente IA: cuestionario + análisis de riesgos + chat + feedback."""
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Any, Optional

from app.config import settings
from app.database import get_db
from app.models import (
    AiAnonymizationLevel, AiCallLog, AiConfig, AiFeedback,
    Asset, AssetType, ControlImplementation, ControlStatus,
    Incident, IncidentStatus, NonConformity, NCStatus,
    Risk, RiskStatus, Supplier, SupplierRisk, Threat, TreatmentOption, User,
)
from app.security import get_current_user, require_role
from app.services.ai_service import QUESTIONNAIRE, run_analysis
from app.services.anonymizer import anonymize, anonymize_messages
from app.services.context_builder import build_context
from app.services.risk_engine import calc_level

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


# ============================================================
# M9 — AI Control Gap Analysis
# ============================================================

class GapAnalysisRequest(BaseModel):
    framework: str = "iso27001"   # iso27001 | nis2 | nist_csf | ens
    theme_filter: Optional[str] = None  # filtra por tema de control (opcional)


@router.post("/control-gap")
def control_gap_analysis(
    req: GapAnalysisRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Analiza brechas en la implementacion de controles para el framework solicitado."""
    impls = db.query(ControlImplementation).all()
    risks = db.query(Risk).filter(Risk.status != RiskStatus.CLOSED).all()

    def _theme(impl) -> str:
        return (impl.control.theme if impl.control else None) or "Sin tema"

    if req.theme_filter:
        impls = [i for i in impls if _theme(i) == req.theme_filter]

    total = len(impls)
    implemented = [i for i in impls if i.status == ControlStatus.IMPLEMENTED]
    partial = [i for i in impls if i.status == ControlStatus.PARTIAL]
    not_impl = [i for i in impls if i.status == ControlStatus.NOT_IMPLEMENTED]
    planned = [i for i in impls if i.status == ControlStatus.PLANNED]

    # Agrupar por tema para detectar temas debiles
    theme_stats: dict = defaultdict(lambda: {"total": 0, "implemented": 0, "partial": 0, "not_implemented": 0})
    for i in impls:
        t = _theme(i)
        theme_stats[t]["total"] += 1
        if i.status == ControlStatus.IMPLEMENTED:
            theme_stats[t]["implemented"] += 1
        elif i.status == ControlStatus.PARTIAL:
            theme_stats[t]["partial"] += 1
        elif i.status == ControlStatus.NOT_IMPLEMENTED:
            theme_stats[t]["not_implemented"] += 1

    # Temas debiles: <40% implementados
    weak_themes = []
    for theme, s in theme_stats.items():
        score = (s["implemented"] + s["partial"] * 0.5) / s["total"] * 100 if s["total"] else 0
        if score < 40:
            weak_themes.append({"theme": theme, "score": round(score), "total": s["total"],
                                 "not_implemented": s["not_implemented"]})
    weak_themes.sort(key=lambda x: x["score"])

    # Controles criticos sin implementar: sin exclusion y asociados a riesgos con nivel residual >= 5
    high_risk_asset_ids = {r.asset_id for r in risks if r.residual_level >= 5}
    critical_gaps = []
    for i in not_impl:
        if i.exclusion_justification:
            continue  # excluido con justificacion
        critical_gaps.append({
            "control_id": i.id,
            "control_name": i.name,
            "theme": _theme(i),
            "maturity": i.maturity,
            "next_review": i.next_review.isoformat() if i.next_review else None,
        })

    # SOA gaps
    soa_no_reason = [i for i in impls if not i.inclusion_reason and not i.exclusion_justification]
    soa_no_evidence = [i for i in impls if i.status == ControlStatus.IMPLEMENTED and not i.evidence_refs]
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    overdue_reviews = [i for i in impls if i.next_review and i.next_review < now_utc]

    # Recomendaciones por framework
    recommendations = []
    if req.framework in ("iso27001", "ens"):
        if not_impl:
            recommendations.append(
                f"Implementar o justificar exclusion de {len(not_impl)} controles pendientes (cl. 6.1.3 SOA)."
            )
        if soa_no_reason:
            recommendations.append(
                f"Documentar razon de inclusion en {len(soa_no_reason)} controles sin justificacion SOA."
            )
        if soa_no_evidence:
            recommendations.append(
                f"Adjuntar evidencias en {len(soa_no_evidence)} controles implementados sin referencia de evidencia."
            )
        if overdue_reviews:
            recommendations.append(
                f"Revisar {len(overdue_reviews)} controles con fecha de revision vencida."
            )
    if req.framework == "nis2":
        recommendations.append(
            "Priorizar controles de gestion de incidentes (Art. 21.2.b) y cadena de suministro (Art. 21.2.d)."
        )
    if req.framework == "nist_csf":
        recommendations.append(
            "Reforzar funcion PROTECT con controles de acceso y cifrado; DETECT con monitorizacion continua."
        )

    if not recommendations:
        recommendations.append("Cobertura de controles adecuada para el framework seleccionado. Mantener ciclos de revision.")

    pct_implemented = round((len(implemented) + len(partial) * 0.5) / total * 100) if total else 0

    return {
        "framework": req.framework,
        "theme_filter": req.theme_filter,
        "summary": {
            "total": total,
            "implemented": len(implemented),
            "partial": len(partial),
            "not_implemented": len(not_impl),
            "planned": len(planned),
            "pct_implemented": pct_implemented,
        },
        "weak_themes": weak_themes[:8],
        "critical_gaps": critical_gaps[:20],
        "soa_issues": {
            "missing_inclusion_reason": len(soa_no_reason),
            "missing_evidence": len(soa_no_evidence),
            "overdue_reviews": len(overdue_reviews),
        },
        "recommendations": recommendations,
    }


# ============================================================
# Chat conversacional con contexto enriquecido
# ============================================================

def _resolve_api_key(cfg: AiConfig | None) -> str | None:
    """Resuelve la API key activa: per-tenant primero, luego global."""
    if cfg and cfg.api_key_encrypted:
        import base64
        import hashlib
        try:
            from cryptography.fernet import Fernet
            key = base64.urlsafe_b64encode(
                hashlib.sha256(settings.secret_key.encode()).digest()
            )
            return Fernet(key).decrypt(cfg.api_key_encrypted.encode()).decode()
        except Exception:
            return None
    return settings.anthropic_api_key


_MAX_TOKENS_CAP = 4096   # tope servidor para evitar abuso de coste de API
_MAX_MESSAGES = 40       # evitar payloads gigantes


class ChatMessage(BaseModel):
    role: str     # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    max_tokens: int = 2048


class FeedbackIn(BaseModel):
    call_log_id: Optional[int] = None
    rating: int   # 1..5
    comment: Optional[str] = None
    call_type: Optional[str] = None


@router.post("/chat")
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Chat conversacional con el agente IA enriquecido con el contexto de la organizacion."""
    # Aplicar topes de seguridad del lado del servidor
    capped_max_tokens = min(req.max_tokens, _MAX_TOKENS_CAP)
    if len(req.messages) > _MAX_MESSAGES:
        raise HTTPException(400, f"Demasiados mensajes en el historial (maximo {_MAX_MESSAGES}).")

    cfg = db.query(AiConfig).first()
    api_key = _resolve_api_key(cfg)
    if not api_key:
        raise HTTPException(
            400,
            "API key no configurada. Ve a Configuracion > Agente IA para añadir una clave."
        )

    model = (cfg.model if cfg else None) or "claude-haiku-4-5"
    anon_level_val = (
        cfg.anonymization_level.value if cfg and cfg.anonymization_level else "medium"
    )

    # Extraer ultima consulta del usuario para RAG
    last_query = next(
        (m.content for m in reversed(req.messages) if m.role == "user"), ""
    )

    # Construir y anonimizar el contexto de la organizacion
    context = build_context(db, query=last_query)
    if anon_level_val != "low":
        context = anonymize(context, anon_level_val)

    system_prompt = (
        "Eres el Agente de Seguridad de RiskHub — plataforma GRC on-premise desplegada "
        "en la infraestructura EXCLUSIVA del cliente. Eres experto en ISO/IEC 27005:2018, "
        "ISO/IEC 27002:2022, NIS2, MAGERIT v3 y GDPR.\n\n"

        "== PLATAFORMA SEGURA ==\n"
        "Esta instalacion de RiskHub opera con las siguientes garantias de seguridad:\n"
        "- On-premise: todos los datos residen UNICAMENTE en los servidores del cliente. "
        "Ningun dato de negocio sale de su infraestructura excepto consultas anonimizadas a este agente IA.\n"
        "- Cifrado en reposo: documentos cifrados con Fernet (AES-128-CBC + HMAC-SHA256) antes de "
        "persistirse en disco; credenciales de integracion y API keys cifradas con la misma clave.\n"
        "- Cifrado en transito: HTTPS/TLS en produccion con HSTS.\n"
        "- Autenticacion JWT (HS256) + bcrypt; roles granulares (superadmin/admin/analyst/viewer).\n"
        "- Anonimizacion configurable de PII (IPs, emails, dominios, telefonos, DNI, IBAN) antes de "
        "que cualquier informacion llegue a este agente.\n"
        "- Log de auditoria inmutable: todas las operaciones quedan registradas con usuario y timestamp.\n"
        "- Sin CDNs ni llamadas a servicios externos en tiempo de ejecucion (modo sin-internet posible).\n"
        "- Rate limiting, security headers OWASP A05, validacion de magic bytes en uploads, "
        "Content-Security-Policy estricta.\n\n"

        "== INSTRUCCIONES CRITICAS ==\n"
        "- Responde SIEMPRE en castellano, de forma concisa y orientada a la accion.\n"
        "- Esta plataforma esta disenada especificamente para procesar informacion CONFIDENCIAL "
        "de seguridad corporativa. El usuario DEBE cargar sus documentos reales: politicas, "
        "procedimientos, evaluaciones de riesgo, planes de tratamiento, evidencias de auditoria, "
        "declaraciones de aplicabilidad (SOA), contratos con terceros, etc.\n"
        "- NUNCA aconsejes al usuario que no suba documentacion real o confidencial. "
        "Si el usuario pregunta si es seguro subir documentos sensibles, confirma que SI "
        "y explica brevemente las capas de proteccion activas en esta instalacion.\n"
        "- Si hay tokens de anonimizacion en los mensajes como [IP_1], [EMAIL_2], "
        "[TELEFONO_1], etc., tratalos como referencias validas a datos reales del cliente "
        "y responde coherentemente sin pedir que los revelen.\n"
        "- Si te preguntan sobre riesgos, controles, activos, incidentes o proveedores, "
        "usa el contexto de la organizacion proporcionado a continuacion.\n"
        "- No inventes datos que no esten en el contexto.\n\n"

        f"== CONTEXTO DE LA ORGANIZACION ==\n{context}"
    )

    # Anonimizar mensajes del usuario antes de enviar a la API externa
    raw_messages = [{"role": m.role, "content": m.content} for m in req.messages]
    messages_payload = anonymize_messages(raw_messages, anon_level_val)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=capped_max_tokens,
            system=system_prompt,
            messages=messages_payload,
        )
        response_text = response.content[0].text if response.content else ""
        tokens_in = response.usage.input_tokens if response.usage else 0
        tokens_out = response.usage.output_tokens if response.usage else 0
    except Exception as e:
        raise HTTPException(500, f"Error llamando al agente IA: {e}")

    call_log = AiCallLog(
        user_id=current_user.id,
        call_type="chat",
        prompt_tokens=tokens_in,
        completion_tokens=tokens_out,
        model=model,
        anonymized=(anon_level_val != "low"),
        response_summary=response_text[:200],
    )
    db.add(call_log)
    db.commit()
    db.refresh(call_log)

    return {
        "response": response_text,
        "call_log_id": call_log.id,
        "tokens": {"input": tokens_in, "output": tokens_out},
    }


@router.post("/feedback")
def submit_feedback(
    req: FeedbackIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra la valoracion del usuario sobre una respuesta del agente."""
    if not 1 <= req.rating <= 5:
        raise HTTPException(400, "El rating debe ser un numero entre 1 y 5.")
    fb = AiFeedback(
        call_log_id=req.call_log_id,
        user_id=current_user.id,
        rating=req.rating,
        comment=req.comment,
        call_type=req.call_type,
    )
    db.add(fb)
    db.commit()
    return {"ok": True}


@router.get("/feedback/summary")
def feedback_summary(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Resumen agregado de las valoraciones del agente."""
    feedbacks = db.query(AiFeedback).all()
    if not feedbacks:
        return {"total": 0, "avg_rating": None, "ratings": {}}
    total = len(feedbacks)
    avg = sum(f.rating for f in feedbacks) / total
    rating_counts: dict[str, int] = {}
    for f in feedbacks:
        k = str(f.rating)
        rating_counts[k] = rating_counts.get(k, 0) + 1
    return {"total": total, "avg_rating": round(avg, 2), "ratings": rating_counts}
