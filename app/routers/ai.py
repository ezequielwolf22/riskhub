"""Endpoints del agente IA: cuestionario + análisis de riesgos + chat + feedback."""
import json
import threading
import uuid
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
    DPIA, DPIAStatus, ProcessingActivity,
    Incident, IncidentSeverity, IncidentStatus, NonConformity, NCStatus,
    Policy, PolicyStatus,
    Risk, RiskStatus, Supplier, SupplierRisk, Threat, TreatmentOption,
    TreatmentTask, TaskStatus, TaskPriority,
    User, UserRole,
)
from app.security import check_org_access, filter_by_org, get_current_user, require_role
from app.services.ai_service import QUESTIONNAIRE, run_analysis
from app.services.anonymizer import anonymize, anonymize_messages
from app.services.context_builder import build_context
from app.services.risk_engine import calc_level

router = APIRouter(prefix="/api/ai", tags=["ai"])

# ============================================================
# Job store en memoria — análisis asíncrono con polling
# Evita 504 en proxies con proxy_read_timeout < 60s
# ============================================================

_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_JOB_TTL_SECONDS = 1800  # los jobs expiran a los 30 min


def _cleanup_old_jobs() -> None:
    """Elimina jobs expirados. Llamar dentro de _JOBS_LOCK."""
    now = datetime.now(timezone.utc)
    expired = [
        jid for jid, j in _JOBS.items()
        if (now - j["created_at"]).total_seconds() > _JOB_TTL_SECONDS
    ]
    for jid in expired:
        _JOBS.pop(jid, None)


class AnalyzeRequest(BaseModel):
    answers: dict[str, Any]


class ImportRequest(BaseModel):
    scenarios: list[dict[str, Any]]
    risk_appetite: int | None = None        # nivel 0-8; guarda en RiskContext
    active_frameworks: list[str] | None = None  # normativas activas del cuestionario
    ens_level: str | None = None            # "basico"|"medio"|"alto" si ENS activado


@router.get("/questionnaire")
def get_questionnaire(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve la definicion del cuestionario y las respuestas guardadas del tenant."""
    from app.models import RiskContext
    ctx = filter_by_org(db.query(RiskContext), RiskContext, current_user).first()
    saved = (ctx.questionnaire_answers or {}) if ctx else {}
    return {"questions": QUESTIONNAIRE, "saved_answers": saved}


@router.post("/analyze")
def analyze(
    req: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Envía las respuestas al agente IA y devuelve el análisis de riesgos."""
    # Resolver la API key del tenant (configurada en IA -> Configuracion)
    cfg = filter_by_org(db.query(AiConfig), AiConfig, current_user).first()
    api_key = _resolve_api_key(cfg)

    # Leer metodología activa del contexto y pasarla a las respuestas del cuestionario
    # para que el prompt adapte el análisis (ISO 27005 puro vs MAGERIT con DIACAT)
    from app.models import RiskContext
    ctx_obj = filter_by_org(db.query(RiskContext), RiskContext, current_user).first()
    enriched_answers = dict(req.answers)
    if ctx_obj and ctx_obj.methodology and "methodology" not in enriched_answers:
        enriched_answers["_active_methodology"] = ctx_obj.methodology
    if ctx_obj and ctx_obj.ens_level and "ens_level" not in enriched_answers:
        enriched_answers["ens_level"] = ctx_obj.ens_level

    try:
        result = run_analysis(enriched_answers, db, api_key=api_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=(
                f"La respuesta de la IA no es JSON valido ({e}). "
                "Intenta de nuevo — puede ser un fallo transitorio del modelo."
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el análisis: {str(e)}")

    # Persistir respuestas + contexto derivado en RiskContext — disponible para chat, informes y cumplimiento
    try:
        from app.models import RiskContext
        from app.services.ai_service import _regulations_to_frameworks, _parse_appetite_level
        ctx_save = filter_by_org(db.query(RiskContext), RiskContext, current_user).first()
        if not ctx_save:
            ctx_save = RiskContext(organization_id=current_user.organization_id)
            db.add(ctx_save)
        public_answers = {k: v for k, v in req.answers.items() if not k.startswith("_")}
        ctx_save.questionnaire_answers = public_answers
        # Normativas, nivel ENS y apetito de riesgo — propagar a todas las secciones
        regulations = public_answers.get("regulations") or []
        if regulations:
            ctx_save.active_frameworks = _regulations_to_frameworks(regulations)
        if public_answers.get("ens_level"):
            ctx_save.ens_level = public_answers["ens_level"]
        appetite_raw = public_answers.get("risk_appetite_level", "")
        if appetite_raw:
            ctx_save.risk_appetite = max(0, min(8, _parse_appetite_level(appetite_raw)))
        db.commit()
    except Exception:
        pass  # No bloquear si falla el guardado

    return result


# ============================================================
# Análisis asíncrono con polling (evita 504 en proxies)
# ============================================================

@router.post("/analyze/async")
def analyze_start(
    req: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lanza el análisis en un hilo de fondo y devuelve un job_id inmediatamente.

    El cliente debe consultar GET /api/ai/analyze/status/{job_id} cada pocos
    segundos hasta que status sea 'done' o 'error'.
    """
    cfg = filter_by_org(db.query(AiConfig), AiConfig, current_user).first()
    api_key = _resolve_api_key(cfg)

    # Enriquecer respuestas con metodología activa (igual que /analyze)
    from app.models import RiskContext
    ctx_obj = filter_by_org(db.query(RiskContext), RiskContext, current_user).first()
    enriched = dict(req.answers)
    if ctx_obj and ctx_obj.methodology and "_active_methodology" not in enriched:
        enriched["_active_methodology"] = ctx_obj.methodology
    if ctx_obj and ctx_obj.ens_level and "ens_level" not in enriched:
        enriched["ens_level"] = ctx_obj.ens_level

    org_id = current_user.organization_id

    job_id = str(uuid.uuid4())
    with _JOBS_LOCK:
        _cleanup_old_jobs()
        _JOBS[job_id] = {
            "status": "running",
            "result": None,
            "error": None,
            "created_at": datetime.now(timezone.utc),
        }

    def _run() -> None:
        from app.database import SessionLocal
        from app.services.ai_service import _regulations_to_frameworks, _parse_appetite_level
        db_t = SessionLocal()
        try:
            result = run_analysis(enriched, db_t, api_key=api_key)

            # Guardar contexto organizacional en RiskContext
            try:
                from app.models import RiskContext as RC
                ctx_s = db_t.query(RC).filter(RC.organization_id == org_id).first()
                if not ctx_s:
                    ctx_s = RC(organization_id=org_id)
                    db_t.add(ctx_s)
                public_answers = {k: v for k, v in enriched.items() if not k.startswith("_")}
                ctx_s.questionnaire_answers = public_answers
                regs = public_answers.get("regulations") or []
                if regs:
                    ctx_s.active_frameworks = _regulations_to_frameworks(regs)
                if public_answers.get("ens_level"):
                    ctx_s.ens_level = public_answers["ens_level"]
                appetite_raw = public_answers.get("risk_appetite_level", "")
                if appetite_raw:
                    ctx_s.risk_appetite = max(0, min(8, _parse_appetite_level(appetite_raw)))
                db_t.commit()
            except Exception:
                pass

            with _JOBS_LOCK:
                _JOBS[job_id]["status"] = "done"
                _JOBS[job_id]["result"] = result
        except Exception as exc:
            with _JOBS_LOCK:
                _JOBS[job_id]["status"] = "error"
                _JOBS[job_id]["error"] = str(exc)
        finally:
            db_t.close()

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id}


@router.get("/analyze/status/{job_id}")
def analyze_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Devuelve el estado del análisis asíncrono.

    Respuestas posibles:
      { "status": "running" }
      { "status": "done",  "result": { ... } }
      { "status": "error", "error": "mensaje" }
    """
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado o expirado (max 30 min).")
    return {
        "status": job["status"],
        "result": job.get("result"),
        "error": job.get("error"),
    }


@router.post("/import")
def import_risks(
    req: ImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Importa los escenarios seleccionados como riesgos en la base de datos."""
    created: list[str] = []
    skipped:  list[str] = []

    # Función auxiliar para generar código de activo único
    def _next_asset_code() -> str:
        n = db.query(Asset).count() + 1
        code = f"AST-{n:04d}"
        while db.query(Asset).filter(Asset.code == code).first():
            n += 1
            code = f"AST-{n:04d}"
        return code

    # Cache de amenazas por código
    threat_by_code = {t.code: t for t in db.query(Threat).all()}
    threat_by_name = {t.name.lower(): t for t in db.query(Threat).all()}

    for sc in req.scenarios:
        # Resolver o crear activo
        asset = None
        if sc.get("asset_id"):
            asset = filter_by_org(
                db.query(Asset).filter(Asset.id == sc["asset_id"]),
                Asset, current_user,
            ).first()

        if not asset and sc.get("asset_suggestion"):
            existing = filter_by_org(
                db.query(Asset).filter(Asset.name == sc["asset_suggestion"]),
                Asset, current_user,
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
                    organization_id=current_user.organization_id,
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

        # Comprobar duplicados (dentro del mismo tenant)
        dup = filter_by_org(
            db.query(Risk).filter(Risk.asset_id == asset.id, Risk.threat_id == threat.id),
            Risk, current_user,
        ).first()
        if dup:
            skipped.append(f"{asset.name} × {threat.name} (duplicado)")
            continue

        # Calcular código único para el riesgo
        count = db.query(Risk).count() + len(created) + 1
        code = f"RSK-{count:04d}"
        while db.query(Risk).filter(Risk.code == code).first():
            count += 1
            code = f"RSK-{count:04d}"

        # Mapear treatment_option del escenario IA al enum TreatmentOption
        treatment_map = {
            "modification": TreatmentOption.MODIFICATION,
            "retention": TreatmentOption.RETENTION,
            "avoidance": TreatmentOption.AVOIDANCE,
            "sharing": TreatmentOption.SHARING,
        }
        sc_treatment = treatment_map.get(
            (sc.get("treatment_option") or "modification").lower(),
            TreatmentOption.MODIFICATION,
        )

        vuln_desc = sc.get("vulnerability_description", "")
        rat_desc  = sc.get("rationale", "")
        combined  = (vuln_desc + (" — " + rat_desc if rat_desc else ""))[:1000]
        risk = Risk(
            code=code,
            asset_id=asset.id,
            threat_id=threat.id,
            inherent_consequence=sc.get("inherent_consequence", 2),
            inherent_likelihood=sc.get("inherent_likelihood", 2),
            inherent_level=sc.get("inherent_level", 4),
            residual_consequence=sc.get("residual_consequence", 1),
            residual_likelihood=sc.get("residual_likelihood", 1),
            residual_level=sc.get("residual_level", 1),
            status=RiskStatus.IDENTIFIED,
            treatment_option=sc_treatment,
            description=combined,
            ai_rationale=rat_desc[:500],
            ai_generated=True,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
        )
        db.add(risk)
        created.append(f"{asset.name} × {threat.name}")

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error guardando riesgos: {exc}")

    # Guardar apetito, normativas y nivel ENS en RiskContext si se proporcionan
    ctx_updated = False
    try:
        if req.risk_appetite is not None or req.active_frameworks is not None or req.ens_level is not None:
            from app.models import RiskContext
            from app.routers.context import _apply_appetite_bulk
            ctx = filter_by_org(db.query(RiskContext), RiskContext, current_user).first()
            if not ctx:
                ctx = RiskContext(organization_id=current_user.organization_id)
                db.add(ctx)
                db.flush()

            old_appetite = ctx.risk_appetite
            if req.risk_appetite is not None:
                ctx.risk_appetite = max(0, min(8, req.risk_appetite))
            if req.active_frameworks is not None:
                ctx.active_frameworks = req.active_frameworks
            if req.ens_level is not None:
                ctx.ens_level = req.ens_level
            db.commit()
            ctx_updated = True

            # Recalcular tratamientos de todos los riesgos si cambia el apetito
            if req.risk_appetite is not None and old_appetite != ctx.risk_appetite:
                _apply_appetite_bulk(db, current_user.organization_id, ctx.risk_appetite)
    except HTTPException:
        raise
    except Exception as exc:
        # No bloquear la respuesta si falla el guardado del contexto;
        # los riesgos ya están creados.
        import logging
        logging.getLogger("riskhub.ai").warning("import: error guardando contexto: %s", exc)

    return {
        "created": len(created),
        "skipped": len(skipped),
        "detail_created": created,
        "detail_skipped": skipped,
        "risk_appetite_saved": req.risk_appetite is not None,
        "frameworks_saved": ctx_updated,
    }


# ============================================================
# Compliance dashboard data — multi-framework scoring
# ============================================================

@router.get("/compliance/summary")
def compliance_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Calcula puntuaciones de cumplimiento para ISO 27001, NIS2, NIST CSF y ENS."""
    impls = filter_by_org(db.query(ControlImplementation), ControlImplementation, current_user).all()
    total_controls = len(impls)
    implemented = sum(1 for i in impls if i.status == ControlStatus.IMPLEMENTED)
    partial = sum(1 for i in impls if i.status == ControlStatus.PARTIAL)
    effective_score = (implemented + partial * 0.5) / total_controls * 100 if total_controls else 0

    risks = filter_by_org(db.query(Risk), Risk, current_user).all()
    risks_with_treatment = sum(1 for r in risks if r.treatment_option)
    risks_with_owner = sum(1 for r in risks if r.owner_id)
    risks_assessed = sum(1 for r in risks if r.status in (RiskStatus.ASSESSED, RiskStatus.TREATED, RiskStatus.ACCEPTED, RiskStatus.CLOSED))
    total_risks = len(risks)

    incidents = filter_by_org(db.query(Incident), Incident, current_user).all()
    suppliers = filter_by_org(db.query(Supplier), Supplier, current_user).all()
    ncs = filter_by_org(db.query(NonConformity), NonConformity, current_user).all()
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
    identify_score = min(100, (total_risks / max(1, filter_by_org(db.query(Asset), Asset, current_user).count()) * 100))
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

    # ---- GDPR / RGPD score (Art. 5, 25, 30, 32, 35) ----
    dpias = filter_by_org(db.query(DPIA), DPIA, current_user).all()
    activities = filter_by_org(db.query(ProcessingActivity), ProcessingActivity, current_user).all()
    dpia_high_risk = [d for d in dpias if d.status != DPIAStatus.APPROVED]
    activities_without_legal_basis = sum(1 for a in activities if not a.legal_basis)
    gdpr_incidents = sum(1 for i in incidents if getattr(i, 'nis2_notification_required', False))
    privacy_controls_codes = {"5.34", "5.33", "8.11", "8.12", "5.12"}
    privacy_impl = sum(1 for ci in impls
                       if ci.control and ci.control.code in privacy_controls_codes
                       and ci.status in (ControlStatus.IMPLEMENTED, ControlStatus.PARTIAL))
    gdpr_components = [
        min(100, len(activities) * 10) if activities else 0,           # Art. 30 registro
        100 - min(100, len(dpia_high_risk) * 20),                      # Art. 35 DPIAs
        100 if activities_without_legal_basis == 0 else max(0, 100 - activities_without_legal_basis * 15),  # Art. 6
        (privacy_impl / max(1, len(privacy_controls_codes)) * 100),    # Art. 32 controles
        100 if gdpr_incidents == 0 else max(0, 100 - gdpr_incidents * 20),  # Art. 33
    ]
    gdpr_score = round(sum(gdpr_components) / len(gdpr_components))

    # ---- PCI-DSS v4.0 score (heurístico basado en controles de acceso y cifrado) ----
    pci_codes = {"8.5", "8.6", "8.4", "8.24", "8.20", "8.8", "8.7", "5.17", "6.3"}
    pci_impl = sum(1 for ci in impls
                   if ci.control and ci.control.code in pci_codes
                   and ci.status in (ControlStatus.IMPLEMENTED, ControlStatus.PARTIAL))
    pci_score = round(
        (pci_impl / max(1, len(pci_codes)) * 60) +  # controles específicos PCI
        (effective_score * 0.3) +                    # postura general de controles
        (10 if total_risks > 0 else 0)               # análisis de riesgo presente
    )
    pci_score = min(100, pci_score)

    # ---- SOC 2 Type II score (Trust Services Criteria — CC, A, PI, C, P) ----
    soc2_cc_codes = {"8.5", "5.15", "5.17", "8.3", "8.6"}  # Common Criteria access control
    soc2_impl = sum(1 for ci in impls
                    if ci.control and ci.control.code in soc2_cc_codes
                    and ci.status in (ControlStatus.IMPLEMENTED, ControlStatus.PARTIAL))
    audit_logs_ok = any(ci.control and ci.control.code == "8.15"
                        and ci.status == ControlStatus.IMPLEMENTED for ci in impls)
    soc2_components = [
        soc2_impl / max(1, len(soc2_cc_codes)) * 100,   # CC Common Criteria
        effective_score * 0.5,                           # A Availability
        100 if audit_logs_ok else 40,                    # PI Processing Integrity
        (risks_assessed / max(1, total_risks) * 100),   # C Confidentiality
    ]
    soc2_score = min(100, round(sum(soc2_components) / len(soc2_components)))

    # ---- HIPAA score (Security Rule § 164.312) ----
    hipaa_codes = {"5.17", "8.5", "8.24", "8.13", "8.15", "5.26"}
    hipaa_impl = sum(1 for ci in impls
                     if ci.control and ci.control.code in hipaa_codes
                     and ci.status in (ControlStatus.IMPLEMENTED, ControlStatus.PARTIAL))
    hipaa_score = round(
        (hipaa_impl / max(1, len(hipaa_codes)) * 70) +
        (effective_score * 0.2) +
        (10 if total_risks > 0 else 0)
    )
    hipaa_score = min(100, hipaa_score)

    # Metodología activa (para incluir en _meta y que la UI pueda mostrarlo)
    from app.models import RiskContext
    ctx_obj = filter_by_org(db.query(RiskContext), RiskContext, current_user).first()
    active_methodology = ctx_obj.methodology if ctx_obj and ctx_obj.methodology else "iso27005"
    active_frameworks_list = ctx_obj.active_frameworks if ctx_obj and ctx_obj.active_frameworks else None

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
        "gdpr": {
            "score": gdpr_score,
            "label": "GDPR / RGPD",
            "gaps": _gdpr_gaps(activities, dpias, dpia_high_risk, activities_without_legal_basis),
        },
        "pcidss": {
            "score": pci_score,
            "label": "PCI-DSS v4.0",
            "gaps": _pcidss_gaps(impls, pci_codes, pci_impl),
        },
        "soc2": {
            "score": soc2_score,
            "label": "SOC 2 Type II",
            "gaps": _soc2_gaps(impls, soc2_codes=soc2_cc_codes, soc2_impl=soc2_impl, audit_logs_ok=audit_logs_ok),
        },
        "hipaa": {
            "score": hipaa_score,
            "label": "HIPAA Security Rule",
            "gaps": _hipaa_gaps(impls, hipaa_codes, hipaa_impl),
        },
        "_meta": {
            "total_controls": total_controls,
            "implemented_controls": implemented,
            "total_risks": total_risks,
            "risks_treated": risks_with_treatment,
            "open_incidents": sum(1 for i in incidents if i.status != IncidentStatus.CLOSED),
            "open_ncs": sum(1 for n in ncs if n.status != NCStatus.CLOSED),
            "methodology": active_methodology,
            "active_frameworks": active_frameworks_list,
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


def _gdpr_gaps(activities, dpias, dpia_high_risk, activities_without_legal_basis) -> list[str]:
    gaps = []
    if not activities:
        gaps.append("Sin actividades de tratamiento registradas (Art. 30 RGPD — obligatorio)")
    if activities_without_legal_basis > 0:
        gaps.append(f"{activities_without_legal_basis} actividad(es) sin base legal documentada (Art. 6 RGPD)")
    if dpia_high_risk:
        gaps.append(f"{len(dpia_high_risk)} DPIA(s) pendiente(s) de aprobacion para tratamientos de alto riesgo (Art. 35)")
    if not dpias:
        gaps.append("Sin evaluaciones de impacto (DPIA) registradas — requeridas para tratamientos de alto riesgo")
    return gaps


def _pcidss_gaps(impls, pci_codes, pci_impl) -> list[str]:
    gaps = []
    missing = len(pci_codes) - pci_impl
    if missing > 0:
        gaps.append(f"{missing} control(es) PCI-DSS clave no implementado(s) (acceso, cifrado, parcheo)")
    no_encryption = not any(ci.control and ci.control.code == "8.24"
                             and ci.status == ControlStatus.IMPLEMENTED for ci in impls)
    if no_encryption:
        gaps.append("Cifrado de datos en reposo/transito no confirmado (Req. 3, 4 PCI-DSS v4.0)")
    no_access = not any(ci.control and ci.control.code in ("8.5", "8.6")
                         and ci.status == ControlStatus.IMPLEMENTED for ci in impls)
    if no_access:
        gaps.append("Control de acceso a datos de tarjeta no documentado (Req. 7, 8 PCI-DSS v4.0)")
    return gaps


def _soc2_gaps(impls, soc2_codes, soc2_impl, audit_logs_ok) -> list[str]:
    gaps = []
    missing = len(soc2_codes) - soc2_impl
    if missing > 0:
        gaps.append(f"{missing} criterio(s) de control comun (CC) SOC 2 sin implementar")
    if not audit_logs_ok:
        gaps.append("Logs de auditoria no implementados — requerido para CC7 (Monitoring Activities)")
    mfa_ok = any(ci.control and ci.control.code == "5.17"
                 and ci.status == ControlStatus.IMPLEMENTED for ci in impls)
    if not mfa_ok:
        gaps.append("MFA/autenticacion fuerte no confirmada (CC6 — Logical and Physical Access Controls)")
    return gaps


def _hipaa_gaps(impls, hipaa_codes, hipaa_impl) -> list[str]:
    gaps = []
    missing = len(hipaa_codes) - hipaa_impl
    if missing > 0:
        gaps.append(f"{missing} salvaguarda(s) HIPAA Security Rule sin implementar")
    no_backup = not any(ci.control and ci.control.code == "8.13"
                         and ci.status == ControlStatus.IMPLEMENTED for ci in impls)
    if no_backup:
        gaps.append("Plan de contingencia/backup no implementado (§ 164.312.a.2.ii HIPAA)")
    no_audit = not any(ci.control and ci.control.code == "8.15"
                        and ci.status == ControlStatus.IMPLEMENTED for ci in impls)
    if no_audit:
        gaps.append("Controles de audit log no implementados (§ 164.312.b HIPAA)")
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
    current_user: User = Depends(get_current_user),
):
    """Sugiere amenazas y nivel de riesgo para un activo usando el catalogo ISO 27005."""
    asset = filter_by_org(
        db.query(Asset).filter(Asset.id == req.asset_id),
        Asset, current_user,
    ).first()
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

    # Obtener riesgos existentes para este activo en el mismo tenant (para evitar duplicados)
    existing_threat_ids = {
        r.threat_id for r in filter_by_org(
            db.query(Risk).filter(Risk.asset_id == asset.id),
            Risk, current_user,
        ).all()
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
    current_user: User = Depends(get_current_user),
):
    """Analiza brechas en la implementacion de controles para el framework solicitado."""
    impls = filter_by_org(db.query(ControlImplementation), ControlImplementation, current_user).all()
    risks = filter_by_org(
        db.query(Risk).filter(Risk.status != RiskStatus.CLOSED),
        Risk, current_user,
    ).all()

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
# M9b — AI Control Gap Analysis DETALLADO (via Claude API)
# ============================================================

class DetailedGapRequest(BaseModel):
    framework: str = "iso27001"
    include_implemented: bool = False


@router.post("/control-gap-detailed")
def control_gap_detailed(
    req: DetailedGapRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Gap analysis detallado por control usando Claude API. Cachea el resultado en RiskContext."""
    from app.models import AiConfig, AiDocument, AiDocumentCategory, AiDocumentChunk, RiskContext
    import json as _json
    import hashlib

    impls = filter_by_org(db.query(ControlImplementation), ControlImplementation, current_user).all()
    if not impls:
        raise HTTPException(400, "No hay controles registrados para analizar.")

    # Resolver API key igual que en /chat
    cfg = db.query(AiConfig).filter(
        AiConfig.organization_id == current_user.organization_id
    ).first()
    api_key = _resolve_api_key(cfg)
    if not api_key:
        raise HTTPException(400, "API key no configurada. Ve a Configuracion > Agente IA.")

    model = (cfg.model if cfg else None) or "claude-haiku-4-5"

    # Obtener riesgos para correlacion
    risks = filter_by_org(
        db.query(Risk).filter(Risk.status != RiskStatus.CLOSED),
        Risk, current_user,
    ).all()
    risk_by_asset: dict = {}
    for r in risks:
        risk_by_asset.setdefault(r.asset_id, []).append(r.residual_level or 0)

    # Construir lista de controles filtrada
    target_impls = impls if req.include_implemented else [
        i for i in impls if i.status != ControlStatus.IMPLEMENTED or (i.maturity or 0) < 4
    ]
    # Limitar a 50 para no exceder tokens
    target_impls = target_impls[:50]

    controls_payload = []
    for i in target_impls:
        ctrl_code = i.control.code if i.control else ""
        ctrl_name = i.name or (i.control.name if i.control else "")
        controls_payload.append({
            "code": ctrl_code,
            "name": ctrl_name,
            "theme": i.control.theme if i.control else "",
            "status": i.status.value if i.status else "not_implemented",
            "maturity": i.maturity or 0,
            "evidence": i.evidence or "",
            "notes": (i.notes or "")[:200],
            "inclusion_reason": i.inclusion_reason or "",
            "exclusion_justification": i.exclusion_justification or "",
        })

    # Verificar cache en RiskContext
    ctx = db.query(RiskContext).filter(
        RiskContext.organization_id == current_user.organization_id
    ).first()
    cache_key = hashlib.md5(
        _json.dumps({"fw": req.framework, "controls": [c["code"] + c["status"] for c in controls_payload]}, sort_keys=True).encode()
    ).hexdigest()
    if ctx and ctx.ai_gap_cache:
        cached = ctx.ai_gap_cache if isinstance(ctx.ai_gap_cache, dict) else {}
        if cached.get("_cache_key") == cache_key:
            return cached.get("_data", {})

    prompt_controls = _json.dumps(controls_payload, ensure_ascii=False)
    system_prompt = (
        f"Eres auditor ISO 27001:2022 certificado. Realiza un gap analysis completo del SGSI "
        f"para el framework {req.framework.upper()}.\n\n"
        "Para cada control de la lista, indica:\n"
        "- Cumplimiento: CONFORME / PARCIAL / NO CONFORME / EXCLUIDO\n"
        "- Hallazgo: descripcion especifica de que esta bien y que falta\n"
        "- Evidencias requeridas: que documentacion deberia existir para este control\n"
        "- Recomendacion: accion concreta y priorizada\n"
        "- Riesgo de no cumplimiento: impacto si no se subsana\n"
        "- Prioridad: INMEDIATA / CORTO PLAZO / MEDIO PLAZO\n\n"
        "Devuelve UNICAMENTE JSON valido con esta estructura exacta:\n"
        "{\n"
        '  "framework_score": <0-100>,\n'
        '  "controls": [\n'
        '    {\n'
        '      "code": "5.1",\n'
        '      "name": "...",\n'
        '      "status": "CONFORME|PARCIAL|NO CONFORME|EXCLUIDO",\n'
        '      "finding": "...",\n'
        '      "evidence_required": ["..."],\n'
        '      "recommendation": "...",\n'
        '      "priority": "INMEDIATA|CORTO PLAZO|MEDIO PLAZO",\n'
        '      "risk_of_non_compliance": "..."\n'
        '    }\n'
        '  ],\n'
        '  "executive_summary": "...",\n'
        '  "top_3_priorities": ["...", "...", "..."]\n'
        "}\n"
        "Sin texto ni markdown antes ni despues del JSON."
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": (
                    f"Framework: {req.framework}\n"
                    f"Controles a analizar ({len(controls_payload)}):\n"
                    f"{prompt_controls}"
                ),
            }],
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            parts = raw.split("```", 2)
            inner = parts[1] if len(parts) > 1 else raw
            if inner.startswith("json"):
                inner = inner[4:]
            raw = inner.rsplit("```", 1)[0].strip()
        result = _json.loads(raw)
    except Exception as exc:
        raise HTTPException(500, f"Error en gap analysis IA: {exc}")

    # Log tokens
    tokens_in = response.usage.input_tokens if response.usage else 0
    tokens_out = response.usage.output_tokens if response.usage else 0
    call_log = AiCallLog(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        call_type="gap_analysis_detailed",
        prompt_tokens=tokens_in,
        completion_tokens=tokens_out,
        model=model,
        anonymized=False,
        response_summary=f"Gap detailed {req.framework}: score={result.get('framework_score', '?')}",
    )
    db.add(call_log)

    # Guardar en cache RiskContext
    if ctx:
        ctx.ai_gap_cache = {"_cache_key": cache_key, "_data": result}
    db.commit()

    return result


# ============================================================
# Architecture Review — analisis de documentos de arquitectura
# ============================================================

@router.post("/architecture-review")
def architecture_review(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Analiza documentos de categoria 'architecture' con Claude Vision + texto."""
    from app.models import (
        AiConfig, AiDocument, AiDocumentCategory, AiDocumentChunk,
        ExternalFinding, ExternalFindingSource,
    )
    import json as _json
    import base64

    cfg = db.query(AiConfig).filter(
        AiConfig.organization_id == current_user.organization_id
    ).first()
    api_key = _resolve_api_key(cfg)
    if not api_key:
        raise HTTPException(400, "API key no configurada. Ve a Configuracion > Agente IA.")

    model = (cfg.model if cfg else None) or "claude-opus-4-5"

    # Obtener documentos de arquitectura de la org
    from app.models import AiDocumentStatus
    arch_docs = filter_by_org(
        db.query(AiDocument).filter(
            AiDocument.category == AiDocumentCategory.ARCHITECTURE,
            AiDocument.status == AiDocumentStatus.INDEXED,
        ),
        AiDocument, current_user,
    ).all()

    if not arch_docs:
        raise HTTPException(400, "No hay documentos de arquitectura indexados. Sube documentos en la categoria 'Arquitectura y sistemas'.")

    doc_names_list = [d.original_name for d in arch_docs[:5]]
    _ARCH_REVIEW_PROMPT = (
        "Eres un arquitecto de seguridad senior con experiencia en:\n"
        "- Seguridad en redes (firewalls, segmentacion, DMZ, VLANs, Zero Trust)\n"
        "- Hardening de sistemas (CIS Benchmarks, STIG)\n"
        "- Cloud security (AWS/Azure/GCP security best practices)\n"
        "- ISO 27001 controles de red (8.20, 8.21, 8.22, 8.23)\n"
        "- NIST SP 800-41, SP 800-125, SP 800-190\n\n"
        "Se te proporcionan uno o varios documentos/diagramas de arquitectura. Los documentos "
        f"analizados son exactamente estos (usa el nombre EXACTO como aparece aqui): {doc_names_list}\n\n"
        "Analiza la arquitectura de red/sistemas descrita y proporciona un JSON con esta estructura exacta:\n"
        "{\n"
        '  "components": [\n'
        '    {"type": "firewall|server|network|endpoint|cloud|other", "name": "...", "description": "...", '
        '"source_document": "<nombre exacto del documento de origen>"}\n'
        "  ],\n"
        '  "vulnerabilities": [\n'
        '    {"description": "...", "risk": "CRITICO|ALTO|MEDIO|BAJO", "cve": "CVE-...|null", '
        '"iso_control_violated": "8.20|null", "affected_component": "...", '
        '"source_document": "<nombre exacto del documento de origen>"}\n'
        "  ],\n"
        '  "improvements": [\n'
        '    {"improvement": "...", "justification": "...", "priority": "ALTA|MEDIA|BAJA", "effort": "BAJO|MEDIO|ALTO", '
        '"source_document": "<nombre exacto del documento de origen>"}\n'
        "  ],\n"
        '  "compliance": {\n'
        '    "iso27002_covered": ["8.20", "8.21"],\n'
        '    "iso27002_missing": ["8.22"],\n'
        '    "zero_trust_recommendations": ["..."],\n'
        '    "network_segmentation": "..."\n'
        "  },\n"
        '  "executive_summary": "..."\n'
        "}\n"
        "IMPORTANTE: cuando analices varios documentos, cada componente/vulnerabilidad/mejora debe "
        "llevar el campo source_document con el nombre EXACTO del documento del que proviene (no "
        "mezcles ni dupliques resultados entre documentos distintos salvo que la vulnerabilidad sea "
        "comun a varios, en cuyo caso genera una entrada por cada documento afectado).\n"
        "Devuelve SOLO el JSON. Sin texto ni markdown antes ni despues."
    )

    # Construir contenido del mensaje
    message_content = []
    total_text = ""

    for doc in arch_docs[:5]:  # Limitar a 5 docs
        mime = doc.mime_type or ""
        is_image = mime.startswith("image/")

        if is_image:
            # Decodificar el archivo cifrado y enviar como imagen
            try:
                from app.services.document_service import doc_path, _fernet_key
                from cryptography.fernet import Fernet
                fpath = doc_path(doc.filename)
                if fpath.exists():
                    encrypted = fpath.read_bytes()
                    raw = Fernet(_fernet_key()).decrypt(encrypted)
                    b64 = base64.standard_b64encode(raw).decode()
                    media_type = mime if mime in ("image/png", "image/jpeg", "image/gif", "image/webp") else "image/png"
                    message_content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    })
                    message_content.append({
                        "type": "text",
                        "text": f"[Imagen de arquitectura: {doc.original_name}]",
                    })
            except Exception as _e:
                pass
        else:
            # Obtener chunks de texto
            chunks = sorted(doc.chunks, key=lambda c: c.chunk_index)[:15]
            doc_text = "\n".join(c.content for c in chunks)[:6000]
            if doc_text:
                total_text += f"\n\n--- Documento: {doc.original_name} ---\n{doc_text}"

    if total_text:
        message_content.append({"type": "text", "text": total_text})

    if not message_content:
        raise HTTPException(400, "Los documentos de arquitectura no tienen contenido procesable.")

    message_content.append({
        "type": "text",
        "text": "\nRealiza el analisis de seguridad de la arquitectura descrita/mostrada arriba.",
    })

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=_ARCH_REVIEW_PROMPT,
            messages=[{"role": "user", "content": message_content}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```", 2)
            inner = parts[1] if len(parts) > 1 else raw
            if inner.startswith("json"):
                inner = inner[4:]
            raw = inner.rsplit("```", 1)[0].strip()
        if response.stop_reason == "max_tokens":
            raise HTTPException(
                502,
                "La respuesta de la IA se cortó por exceder el límite de tokens. "
                "Reduce el número de documentos analizados a la vez o su tamaño."
            )
        result = _json.loads(raw)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Error en architecture review IA: {exc}")

    tokens_in = response.usage.input_tokens if response.usage else 0
    tokens_out = response.usage.output_tokens if response.usage else 0
    call_log = AiCallLog(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        call_type="architecture_review",
        prompt_tokens=tokens_in,
        completion_tokens=tokens_out,
        model=model,
        anonymized=False,
        response_summary=f"Architecture review: {len(arch_docs)} docs, {len(result.get('vulnerabilities', []))} vulns",
    )
    db.add(call_log)

    # Persistir vulnerabilidades como ExternalFinding — esto convierte el informe en un
    # plan de trabajo operativo: cada hallazgo puede resolverse, transferirse a un
    # incidente o a un riesgo desde la vista de Hallazgos Externos (generico para
    # cualquier fuente, no solo revision de arquitectura).
    import hashlib
    _SEV_MAP = {"CRITICO": "CRITICAL", "ALTO": "HIGH", "MEDIO": "MEDIUM", "BAJO": "LOW"}
    for vuln in result.get("vulnerabilities", []):
        source_document = (vuln.get("source_document") or "").strip() or None
        description = vuln.get("description") or ""
        digest = hashlib.sha1(
            f"{source_document}|{description}|{vuln.get('affected_component', '')}".encode("utf-8")
        ).hexdigest()[:32]

        existing = db.query(ExternalFinding).filter(
            ExternalFinding.organization_id == current_user.organization_id,
            ExternalFinding.source == ExternalFindingSource.ARCHITECTURE_REVIEW.value,
            ExternalFinding.external_id == digest,
        ).first()
        if existing:
            vuln["finding_id"] = existing.id
            vuln["finding_status"] = existing.status
            vuln["finding_incident_id"] = existing.incident_id
            vuln["finding_risk_id"] = existing.risk_id
            continue

        ef = ExternalFinding(
            organization_id=current_user.organization_id,
            source=ExternalFindingSource.ARCHITECTURE_REVIEW.value,
            external_id=digest,
            title=description[:512] or "Vulnerabilidad de arquitectura",
            description=description[:2000],
            severity=_SEV_MAP.get((vuln.get("risk") or "").upper(), "MEDIUM"),
            cve_id=vuln.get("cve") or None,
            iso_control=vuln.get("iso_control_violated") or None,
            affected_software=(vuln.get("affected_component") or "")[:512],
            source_document=source_document,
            status="open",
            detected_at=datetime.now(timezone.utc),
        )
        db.add(ef)
        db.flush()
        vuln["finding_id"] = ef.id
        vuln["finding_status"] = ef.status
        vuln["finding_incident_id"] = ef.incident_id
        vuln["finding_risk_id"] = ef.risk_id

    db.commit()

    result["_meta"] = {
        "docs_analyzed": len(arch_docs),
        "doc_names": doc_names_list,
    }
    return result


# ============================================================
# Agent tools — acciones que el agente puede proponer al usuario
# ============================================================

_AGENT_TOOLS = [
    {
        "name": "create_treatment_task",
        "description": (
            "Propone crear una tarea de tratamiento concreta para un riesgo. "
            "Usar cuando el usuario necesite registrar una accion de mejora, "
            "asignar responsables o hacer seguimiento de un plan de tratamiento."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titulo claro y accionable de la tarea"},
                "description": {"type": "string", "description": "Descripcion detallada de lo que hay que hacer"},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"],
                             "description": "Prioridad segun urgencia e impacto"},
                "due_days": {"type": "integer", "description": "Dias desde hoy para la fecha limite (ej: 30, 60, 90)"},
                "risk_code": {"type": "string", "description": "Codigo RSK-XXXX del riesgo asociado (si aplica)"},
            },
            "required": ["title", "description", "priority"],
        },
    },
    {
        "name": "update_risk_status",
        "description": (
            "Propone cambiar el estado de un riesgo existente. "
            "Usar cuando el usuario indique que un riesgo ha sido tratado, aceptado o cerrado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "risk_code": {"type": "string", "description": "Codigo del riesgo, ej: RSK-0001"},
                "new_status": {
                    "type": "string",
                    "enum": ["identified", "assessed", "treated", "accepted", "closed"],
                    "description": "Nuevo estado del riesgo",
                },
                "justification": {"type": "string", "description": "Justificacion del cambio de estado"},
            },
            "required": ["risk_code", "new_status"],
        },
    },
    {
        "name": "create_incident",
        "description": (
            "Propone registrar un nuevo incidente de seguridad. "
            "Usar cuando el usuario describa un evento de seguridad que deba quedar registrado "
            "en la plataforma (brecha, fallo, acceso no autorizado, etc.)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titulo conciso del incidente"},
                "description": {"type": "string", "description": "Descripcion del evento, impacto y acciones tomadas"},
                "severity": {"type": "string", "enum": ["p1", "p2", "p3", "p4"],
                             "description": "P1=critico, P2=alto, P3=medio, P4=bajo"},
                "nis2_required": {"type": "boolean",
                                  "description": "True si el incidente podria requerir notificacion NIS2 (Art. 23)"},
            },
            "required": ["title", "description", "severity"],
        },
    },
    {
        "name": "schedule_control_review",
        "description": (
            "Propone crear una tarea de revision urgente para un control ISO 27002 especifico. "
            "Usar cuando se detecte un control critico sin evidencia, vencido o con baja madurez."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "control_name": {"type": "string", "description": "Nombre o codigo del control ISO 27002"},
                "reason": {"type": "string", "description": "Motivo por el que se requiere revision urgente"},
                "due_days": {"type": "integer", "description": "Dias para la fecha limite de revision"},
            },
            "required": ["control_name", "reason"],
        },
    },
]


def _action_label(name: str, inp: dict) -> str:
    """Genera una etiqueta legible para mostrar al usuario antes de confirmar la accion."""
    if name == "create_treatment_task":
        return f"Crear tarea: \"{inp.get('title', '')}\" | Prioridad: {inp.get('priority', '').upper()}"
    if name == "update_risk_status":
        return f"Actualizar {inp.get('risk_code', '?')} → estado: {inp.get('new_status', '').upper()}"
    if name == "create_incident":
        return f"Registrar incidente [{inp.get('severity', '').upper()}]: \"{inp.get('title', '')}\""
    if name == "schedule_control_review":
        return f"Programar revision de control: \"{inp.get('control_name', '')}\""
    return name


# ============================================================
# Chat conversacional con contexto enriquecido
# ============================================================

def _resolve_api_key(cfg: AiConfig | None) -> str | None:
    """Resuelve la API key activa: per-tenant primero, luego global."""
    if cfg and cfg.api_key_encrypted:
        try:
            from app.security import decrypt_secret
            return decrypt_secret(cfg.api_key_encrypted)
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

    cfg = db.query(AiConfig).filter(
        AiConfig.organization_id == current_user.organization_id
    ).first()
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

    # Voyage AI key para busqueda semantica multilingue (opcional)
    voyage_api_key = None
    if cfg and cfg.voyage_api_key_encrypted:
        try:
            from app.security import decrypt_secret
            voyage_api_key = decrypt_secret(cfg.voyage_api_key_encrypted)
        except Exception:
            pass

    # Extraer ultima consulta del usuario para RAG
    last_query = next(
        (m.content for m in reversed(req.messages) if m.role == "user"), ""
    )

    # Construir y anonimizar el contexto — SOLO datos del tenant del usuario autenticado
    context = build_context(
        db, query=last_query,
        organization_id=current_user.organization_id,
        voyage_api_key=voyage_api_key,
    )
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
        "- Esta plataforma esta disenada para analizar documentacion de seguridad corporativa. "
        "Los documentos se almacenan cifrados en reposo. El usuario decide que informacion "
        "sube teniendo en cuenta la politica de seguridad de su organizacion.\n"
        "- Si hay tokens de anonimizacion en los mensajes como [IP_1], [EMAIL_2], "
        "[TELEFONO_1], etc., tratalos como referencias validas a datos reales del cliente "
        "y responde coherentemente sin pedir que los revelen.\n"
        "- Si te preguntan sobre riesgos, controles, activos, incidentes o proveedores, "
        "usa el contexto de la organizacion proporcionado a continuacion.\n"
        "- No inventes datos que no esten en el contexto.\n\n"

        "== ACCESO A DOCUMENTOS ==\n"
        "IMPORTANTE: SI puedes leer y analizar documentos. El sistema incluye en tu contexto:\n"
        "1. La lista de todos los documentos indexados de la organizacion (seccion 'Documentos indexados disponibles').\n"
        "2. Fragmentos del contenido de los documentos mas relevantes para la consulta del usuario "
        "(seccion 'Contenido relevante encontrado en documentos').\n"
        "Cuando el usuario pregunte sobre un documento:\n"
        "- Si encuentras fragmentos relevantes en la seccion de contenido, citalos textualmente e indica la fuente.\n"
        "- Si no hay fragmentos pero el documento esta en la lista de indexados, explica que el documento "
        "existe pero la busqueda por palabras clave no encontro esa seccion especifica, y pide al usuario "
        "que reformule la pregunta con terminos mas especificos del documento.\n"
        "- NUNCA digas que no puedes ver documentos o que no tienes acceso a ellos — SI los tienes via RAG.\n\n"

        "== PREGUNTAS SOBRE CONFIGURACION ==\n"
        "Si el usuario pregunta sobre configuracion (API key, documentos, alertas, integraciones, etc.), proporciona:\n"
        "1. Respuesta paso a paso clara en castellano.\n"
        "2. Menciona la seccion de la guia donde encontrar documentacion completa (ej. 'Configuracion del Agente', 'Gestion de documentos').\n"
        "3. Si es una pregunta compleja, sugiere acceder a las pantallas de configuracion desde el menu lateral.\n"
        "Ejemplos de preguntas de configuracion: 'Como configuro la API key?', 'Como subo documentos?', "
        "'Como activo alertas por email?', 'Como funciona el agente IA?'\n\n"

        "== FLUJOS AUTOMATICOS ==\n"
        "RiskHub tiene los siguientes procesos automaticos:\n"
        "- APScheduler: escalada de tareas vencidas, revision periodica de politicas, "
        "degradacion de controles por madurez baja, informe mensual de postura.\n"
        "- OSINT automatico: escaneo semanal de dominios/emails/IPs, auto-creacion de incidentes si CRITICAL/HIGH.\n"
        "- Riesgos automaticos: cuando una puntuacion de proveedor baja de umbral (30), se crea automaticamente "
        "un riesgo de cadena de suministro ISO 27005.\n"
        "- CVE: escaneo automatico diario de NVD, analisis IA de impacto, linkage a activos.\n"
        "- Validaciones: cuando se crea incidente/no-conformidad, se vinculan automaticamente riesgos activos "
        "del mismo activo.\n"
        "Si el usuario pregunta sobre automatizaciones, explica el flujo correspondiente y ofrece acceso a la "
        "configuracion si es parametrizable.\n\n"

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
            tools=_AGENT_TOOLS,
            tool_choice={"type": "auto"},
        )
        # Separar bloques de texto y de tool_use
        response_text = ""
        pending_actions = []
        for block in response.content:
            if block.type == "text":
                response_text += block.text
            elif block.type == "tool_use":
                pending_actions.append({
                    "action_id": block.id,
                    "action_name": block.name,
                    "action_input": block.input,
                    "label": _action_label(block.name, block.input),
                })
        tokens_in = response.usage.input_tokens if response.usage else 0
        tokens_out = response.usage.output_tokens if response.usage else 0
    except Exception as e:
        raise HTTPException(500, f"Error llamando al agente IA: {e}")

    call_log = AiCallLog(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
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
        "actions": pending_actions,
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


# ============================================================
# Ejecucion de acciones confirmadas por el usuario
# ============================================================

class ExecuteActionRequest(BaseModel):
    action_name: str
    action_input: dict


@router.post("/execute-action")
def execute_action(
    req: ExecuteActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Ejecuta una accion propuesta por el agente IA una vez confirmada por el usuario."""
    name = req.action_name
    inp = req.action_input
    org_id = current_user.organization_id

    try:
        if name == "create_treatment_task":
            return _exec_create_task(db, inp, org_id, current_user.id)
        if name == "update_risk_status":
            return _exec_update_risk_status(db, inp, org_id)
        if name == "create_incident":
            return _exec_create_incident(db, inp, org_id, current_user.id)
        if name == "schedule_control_review":
            return _exec_schedule_control_review(db, inp, org_id, current_user.id)
        raise HTTPException(400, f"Accion desconocida: {name}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Error ejecutando la accion: {exc}")


def _next_code(db: Session, model, prefix: str, org_id) -> str:
    count = db.query(model).filter(getattr(model, "organization_id") == org_id).count()
    code = f"{prefix}-{count + 1:04d}"
    while db.query(model).filter_by(code=code).first():
        count += 1
        code = f"{prefix}-{count + 1:04d}"
    return code


def _exec_create_task(db: Session, inp: dict, org_id, user_id: int) -> dict:
    from datetime import timedelta
    priority_map = {
        "low": TaskPriority.LOW, "medium": TaskPriority.MEDIUM,
        "high": TaskPriority.HIGH, "critical": TaskPriority.CRITICAL,
    }
    priority = priority_map.get(inp.get("priority", "medium"), TaskPriority.MEDIUM)
    due_days = int(inp.get("due_days") or 30)
    due_date = datetime.now(timezone.utc) + timedelta(days=due_days)

    # Resolver risk_id si se proporcionó código
    risk_id = None
    if inp.get("risk_code"):
        r = db.query(Risk).filter(
            Risk.organization_id == org_id,
            Risk.code == inp["risk_code"],
        ).first()
        if r:
            risk_id = r.id

    code = _next_code(db, TreatmentTask, "TSK", org_id)
    task = TreatmentTask(
        organization_id=org_id,
        code=code,
        title=inp["title"],
        description=inp.get("description", ""),
        status=TaskStatus.PENDING,
        priority=priority,
        due_date=due_date,
        risk_id=risk_id,
        assigned_to_id=user_id,
        created_by_id=user_id,
    )
    db.add(task)
    db.commit()
    return {"ok": True, "message": f"Tarea {code} creada correctamente.", "code": code}


def _exec_update_risk_status(db: Session, inp: dict, org_id) -> dict:
    status_map = {
        "identified": RiskStatus.IDENTIFIED,
        "assessed": RiskStatus.ASSESSED,
        "treated": RiskStatus.TREATED,
        "accepted": RiskStatus.ACCEPTED,
        "closed": RiskStatus.CLOSED,
    }
    risk = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.code == inp.get("risk_code", ""),
    ).first()
    if not risk:
        raise HTTPException(404, f"Riesgo {inp.get('risk_code')} no encontrado.")
    new_status = status_map.get(inp.get("new_status", ""), RiskStatus.ASSESSED)
    risk.status = new_status
    if inp.get("justification"):
        risk.description = (risk.description or "") + f"\n\n[Agente IA] {inp['justification']}"
    db.commit()
    return {
        "ok": True,
        "message": f"Riesgo {risk.code} actualizado a estado {new_status.value}.",
        "code": risk.code,
    }


def _exec_create_incident(db: Session, inp: dict, org_id, user_id: int) -> dict:
    severity_map = {
        "p1": IncidentSeverity.P1, "p2": IncidentSeverity.P2,
        "p3": IncidentSeverity.P3, "p4": IncidentSeverity.P4,
    }
    severity = severity_map.get(inp.get("severity", "p3"), IncidentSeverity.P3)
    code = _next_code(db, Incident, "INC", org_id)
    incident = Incident(
        organization_id=org_id,
        code=code,
        title=inp["title"],
        description=inp.get("description", ""),
        severity=severity,
        status=IncidentStatus.OPEN,
        detected_at=datetime.now(timezone.utc),
        nis2_notification_required=bool(inp.get("nis2_required", False)),
    )
    db.add(incident)
    db.commit()
    return {
        "ok": True,
        "message": f"Incidente {code} [{severity.value.upper()}] registrado correctamente.",
        "code": code,
    }


def _exec_schedule_control_review(db: Session, inp: dict, org_id, user_id: int) -> dict:
    from datetime import timedelta
    due_days = int(inp.get("due_days") or 14)
    due_date = datetime.now(timezone.utc) + timedelta(days=due_days)
    code = _next_code(db, TreatmentTask, "TSK", org_id)
    task = TreatmentTask(
        organization_id=org_id,
        code=code,
        title=f"Revision de control: {inp.get('control_name', '')}",
        description=(
            f"Revision urgente requerida.\n"
            f"Control: {inp.get('control_name', '')}\n"
            f"Motivo: {inp.get('reason', '')}"
        ),
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
        due_date=due_date,
        assigned_to_id=user_id,
        created_by_id=user_id,
    )
    db.add(task)
    db.commit()
    return {
        "ok": True,
        "message": f"Tarea de revision {code} creada para el control '{inp.get('control_name')}'.",
        "code": code,
    }


@router.get("/feedback/summary")
def feedback_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resumen agregado de las valoraciones del agente (solo del tenant autenticado)."""
    # AiFeedback no tiene organization_id; se filtra via el usuario que envio el feedback
    if current_user.role == UserRole.SUPERADMIN:
        feedbacks = db.query(AiFeedback).all()
    else:
        feedbacks = (
            db.query(AiFeedback)
            .join(User, AiFeedback.user_id == User.id, isouter=True)
            .filter(User.organization_id == current_user.organization_id)
            .all()
        )
    if not feedbacks:
        return {"total": 0, "avg_rating": None, "ratings": {}}
    total = len(feedbacks)
    avg = sum(f.rating for f in feedbacks) / total
    rating_counts: dict[str, int] = {}
    for f in feedbacks:
        k = str(f.rating)
        rating_counts[k] = rating_counts.get(k, 0) + 1
    return {"total": total, "avg_rating": round(avg, 2), "ratings": rating_counts}
