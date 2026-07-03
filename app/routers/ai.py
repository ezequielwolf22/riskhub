"""Endpoints del agente IA: cuestionario + análisis de riesgos + chat + feedback."""
import json
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Any, Optional

from app.i18n import ai_lang_directive, get_lang, t as _t

from app.config import settings
from app.database import get_db
from app.models import (
    AiAnonymizationLevel, AiCallLog, AiConfig, AiFeedback,
    Asset, AssetType, ControlImplementation, ControlStatus,
    DPIA, DPIAStatus, ProcessingActivity,
    Evidence, EvidenceType,
    Incident, IncidentSeverity, IncidentStatus, NonConformity, NCSeverity, NCStatus,
    Policy, PolicyStatus,
    Risk, RiskStatus, Supplier, SupplierRisk, SupplierTier, Threat, TreatmentOption,
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


# Almacén temporal de archivos adjuntos al chat (30 min TTL, mismo que jobs)
_UPLOADS: dict[str, dict] = {}
_UPLOADS_LOCK = threading.Lock()


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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Envía las respuestas al agente IA y devuelve el análisis de riesgos."""
    lang = get_lang(request)
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
        result = run_analysis(enriched_answers, db, api_key=api_key, org_id=current_user.organization_id, lang=lang)
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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lanza el análisis en un hilo de fondo y devuelve un job_id inmediatamente.

    El cliente debe consultar GET /api/ai/analyze/status/{job_id} cada pocos
    segundos hasta que status sea 'done' o 'error'.
    """
    lang = get_lang(request)
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
            "org_id": org_id,
        }

    def _run() -> None:
        from app.database import SessionLocal
        from app.services.ai_service import _regulations_to_frameworks, _parse_appetite_level
        db_t = SessionLocal()
        try:
            result = run_analysis(enriched, db_t, api_key=api_key, org_id=org_id, lang=lang)

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
    if job.get("org_id") != current_user.organization_id:
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
        from sqlalchemy import func as _func
        max_id = db.query(_func.max(Asset.id)).scalar() or 0
        return f"AST-{max_id + 1:04d}"

    # Cache de amenazas por código — cargado una sola vez
    _all_threats = db.query(Threat).all()
    threat_by_code = {t.code: t for t in _all_threats}
    threat_by_name = {t.name.lower(): t for t in _all_threats}

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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Calcula puntuaciones de cumplimiento para ISO 27001, NIS2, NIST CSF y ENS."""
    lang = get_lang(request)
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
    # DPIA no tiene organization_id propio — se filtra via su ProcessingActivity
    dpias = filter_by_org(
        db.query(DPIA).join(ProcessingActivity, DPIA.activity_id == ProcessingActivity.id),
        ProcessingActivity, current_user,
    ).all()
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

    from app.models import RiskContext
    ctx_obj = filter_by_org(db.query(RiskContext), RiskContext, current_user).first()
    active_methodology = ctx_obj.methodology if ctx_obj and ctx_obj.methodology else "iso27005"
    active_frameworks_list = ctx_obj.active_frameworks if ctx_obj and ctx_obj.active_frameworks else []

    # Recuperar scores reales del motor de requisitos para frameworks activos.
    # Esto garantiza que compliance/summary y compliance/status/{fw} muestren siempre
    # el mismo numero — un unico motor de verdad, no dos estimaciones distintas.
    from app.services.compliance_service import get_framework_compliance_status as _gfcs
    _tracked: dict[str, int] = {}
    _tracked_gaps: dict[str, list] = {}
    for fw_code in (active_frameworks_list or []):
        try:
            fw_status = _gfcs(db, current_user.organization_id, fw_code, lang)
            if "error" not in fw_status:
                _tracked[fw_code] = fw_status["overall_pct"]
                _tracked_gaps[fw_code] = [
                    f"{g['id']}: {g['name']} ({g['completion_pct']}%)"
                    for g in fw_status.get("gaps", [])[:5]
                ]
        except Exception:
            pass

    def _score(fw_code: str, heuristic: int) -> tuple[int, bool]:
        """Devuelve (score, tracked). tracked=True si viene del motor de requisitos."""
        if fw_code in _tracked:
            return _tracked[fw_code], True
        return heuristic, False

    def _gaps(fw_code: str, heuristic_gaps: list) -> list:
        return _tracked_gaps.get(fw_code, heuristic_gaps)

    iso_s, iso_t = _score("iso27001", iso_score)
    nis2_s, nis2_t = _score("nis2", nis2_score)
    nist_s, nist_t = _score("nist_csf", nist_score)
    ens_s, ens_t = _score("ens", ens_score)
    gdpr_s, gdpr_t = _score("gdpr", gdpr_score)
    soc2_s, soc2_t = _score("soc2", soc2_score)
    hipaa_s, hipaa_t = _score("hipaa", hipaa_score)

    return {
        "iso27001": {
            "score": iso_s,
            "label": "ISO/IEC 27001:2022",
            "gaps": _gaps("iso27001", _iso_gaps(impls, risks, ncs, lang)),
            "tracked": iso_t,
        },
        "nis2": {
            "score": nis2_s,
            "label": _t("ai_gaps.label_nis2", lang),
            "gaps": _gaps("nis2", _nis2_gaps(incidents, suppliers, nis2_pending, lang)),
            "tracked": nis2_t,
        },
        "nist_csf": {
            "score": nist_s,
            "label": "NIST CSF 2.0",
            "functions": {
                "GOVERN": round(govern_score),
                "IDENTIFY": round(identify_score),
                "PROTECT": round(protect_score),
                "DETECT": round(detect_score),
                "RESPOND": round(respond_score),
                "RECOVER": round(recover_score),
            },
            "tracked": nist_t,
        },
        "ens": {
            "score": ens_s,
            "label": "ENS RD 311/2022",
            "gaps": _gaps("ens", _ens_gaps(impls, risks, lang)),
            "tracked": ens_t,
        },
        "gdpr": {
            "score": gdpr_s,
            "label": "GDPR / RGPD",
            "gaps": _gaps("gdpr", _gdpr_gaps(activities, dpias, dpia_high_risk, activities_without_legal_basis, lang)),
            "tracked": gdpr_t,
        },
        "pcidss": {
            "score": pci_score,
            "label": "PCI-DSS v4.0",
            "gaps": _pcidss_gaps(impls, pci_codes, pci_impl, lang),
            "tracked": False,
        },
        "soc2": {
            "score": soc2_s,
            "label": "SOC 2 Type II",
            "gaps": _gaps("soc2", _soc2_gaps(impls, soc2_codes=soc2_cc_codes, soc2_impl=soc2_impl, audit_logs_ok=audit_logs_ok, lang=lang)),
            "tracked": soc2_t,
        },
        "hipaa": {
            "score": hipaa_s,
            "label": "HIPAA Security Rule",
            "gaps": _gaps("hipaa", _hipaa_gaps(impls, hipaa_codes, hipaa_impl, lang)),
            "tracked": hipaa_t,
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


def _iso_gaps(impls, risks, ncs, lang: str = "es") -> list[str]:
    gaps = []
    if not impls:
        gaps.append(_t("ai_gaps.iso_no_controls", lang))
    soa_missing_reason = sum(1 for i in impls if not i.inclusion_reason)
    if soa_missing_reason > 0:
        gaps.append(_t("ai_gaps.iso_soa_no_reason", lang, n=soa_missing_reason))
    soa_missing_evidence = sum(1 for i in impls if not i.evidence_refs)
    if soa_missing_evidence > 0:
        gaps.append(_t("ai_gaps.iso_soa_no_evidence", lang, n=soa_missing_evidence))
    no_owner = sum(1 for r in risks if not r.owner_id and r.status not in (RiskStatus.CLOSED,))
    if no_owner > 0:
        gaps.append(_t("ai_gaps.iso_no_owner", lang, n=no_owner))
    major_open = sum(1 for n in ncs if n.severity == "major" and n.status != NCStatus.CLOSED)
    if major_open > 0:
        gaps.append(_t("ai_gaps.iso_major_nc", lang, n=major_open))
    return gaps


def _nis2_gaps(incidents, suppliers, nis2_pending, lang: str = "es") -> list[str]:
    gaps = []
    if nis2_pending > 0:
        gaps.append(_t("ai_gaps.nis2_pending", lang, n=nis2_pending))
    if not suppliers:
        gaps.append(_t("ai_gaps.nis2_no_suppliers", lang))
    no_assessment = sum(1 for s in suppliers if not s.last_assessment_at) if suppliers else 0
    if no_assessment > 0:
        gaps.append(_t("ai_gaps.nis2_no_assessment", lang, n=no_assessment))
    return gaps


def _gdpr_gaps(activities, dpias, dpia_high_risk, activities_without_legal_basis, lang: str = "es") -> list[str]:
    gaps = []
    if not activities:
        gaps.append(_t("ai_gaps.gdpr_no_activities", lang))
    if activities_without_legal_basis > 0:
        gaps.append(_t("ai_gaps.gdpr_no_legal_basis", lang, n=activities_without_legal_basis))
    if dpia_high_risk:
        gaps.append(_t("ai_gaps.gdpr_dpia_pending", lang, n=len(dpia_high_risk)))
    if not dpias:
        gaps.append(_t("ai_gaps.gdpr_no_dpias", lang))
    return gaps


def _pcidss_gaps(impls, pci_codes, pci_impl, lang: str = "es") -> list[str]:
    gaps = []
    missing = len(pci_codes) - pci_impl
    if missing > 0:
        gaps.append(_t("ai_gaps.pci_missing", lang, n=missing))
    no_encryption = not any(ci.control and ci.control.code == "8.24"
                             and ci.status == ControlStatus.IMPLEMENTED for ci in impls)
    if no_encryption:
        gaps.append(_t("ai_gaps.pci_no_encryption", lang))
    no_access = not any(ci.control and ci.control.code in ("8.5", "8.6")
                         and ci.status == ControlStatus.IMPLEMENTED for ci in impls)
    if no_access:
        gaps.append(_t("ai_gaps.pci_no_access", lang))
    return gaps


def _soc2_gaps(impls, soc2_codes, soc2_impl, audit_logs_ok, lang: str = "es") -> list[str]:
    gaps = []
    missing = len(soc2_codes) - soc2_impl
    if missing > 0:
        gaps.append(_t("ai_gaps.soc2_missing", lang, n=missing))
    if not audit_logs_ok:
        gaps.append(_t("ai_gaps.soc2_no_logs", lang))
    mfa_ok = any(ci.control and ci.control.code == "5.17"
                 and ci.status == ControlStatus.IMPLEMENTED for ci in impls)
    if not mfa_ok:
        gaps.append(_t("ai_gaps.soc2_no_mfa", lang))
    return gaps


def _hipaa_gaps(impls, hipaa_codes, hipaa_impl, lang: str = "es") -> list[str]:
    gaps = []
    missing = len(hipaa_codes) - hipaa_impl
    if missing > 0:
        gaps.append(_t("ai_gaps.hipaa_missing", lang, n=missing))
    no_backup = not any(ci.control and ci.control.code == "8.13"
                         and ci.status == ControlStatus.IMPLEMENTED for ci in impls)
    if no_backup:
        gaps.append(_t("ai_gaps.hipaa_no_backup", lang))
    no_audit = not any(ci.control and ci.control.code == "8.15"
                        and ci.status == ControlStatus.IMPLEMENTED for ci in impls)
    if no_audit:
        gaps.append(_t("ai_gaps.hipaa_no_audit", lang))
    return gaps


def _ens_gaps(impls, risks, lang: str = "es") -> list[str]:
    gaps = []
    not_implemented = sum(1 for i in impls if i.status == ControlStatus.NOT_IMPLEMENTED)
    if not_implemented > 0:
        gaps.append(_t("ai_gaps.ens_not_implemented", lang, n=not_implemented))
    no_review = sum(1 for i in impls if not i.next_review)
    if no_review > 0:
        gaps.append(_t("ai_gaps.ens_no_review", lang, n=no_review))
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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Gap analysis detallado por control usando Claude API. Cachea el resultado en RiskContext."""
    from app.models import AiConfig, AiDocument, AiDocumentCategory, AiDocumentChunk, RiskContext
    import json as _json
    import hashlib

    lang = get_lang(request)
    impls = filter_by_org(db.query(ControlImplementation), ControlImplementation, current_user).all()
    if not impls:
        raise HTTPException(400, "No hay controles registrados para analizar.")

    # Resolver API key igual que en /chat
    cfg = db.query(AiConfig).filter(
        AiConfig.organization_id == current_user.organization_id
    ).first()
    api_key = _resolve_api_key(cfg)
    if not api_key:
        raise HTTPException(400, _t("ai.not_configured", lang))

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
            max_tokens=32768,
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
        raise HTTPException(500, _t("ai.analysis_failed", lang, detail=str(exc)))

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
    request: Request,
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

    lang = get_lang(request)
    cfg = db.query(AiConfig).filter(
        AiConfig.organization_id == current_user.organization_id
    ).first()
    api_key = _resolve_api_key(cfg)
    if not api_key:
        raise HTTPException(400, _t("ai.not_configured", lang))

    model = (cfg.model if cfg else None) or "claude-opus-4-6"

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
            max_tokens=64000,
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
            raise HTTPException(502, _t("ai.token_limit_exceeded", lang))
        result = _json.loads(raw)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, _t("ai.analysis_failed", lang, detail=str(exc)))

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
    # ── Existentes ──────────────────────────────────────────────────────────
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
    # ── Activos ─────────────────────────────────────────────────────────────
    {
        "name": "create_asset",
        "description": (
            "Propone dar de alta un nuevo activo en el inventario. "
            "Usar cuando el usuario mencione un sistema, servidor, base de datos, proceso "
            "u otro activo que deba gestionarse en el SGSI."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre descriptivo del activo"},
                "asset_type": {
                    "type": "string",
                    "enum": [
                        "primary_information", "primary_process",
                        "support_hardware", "support_software", "support_network",
                        "support_services", "support_people", "support_site",
                    ],
                    "description": "Tipo de activo segun ISO 27005",
                },
                "description": {"type": "string", "description": "Descripcion del activo y su funcion"},
                "value_confidentiality": {"type": "integer", "description": "Valor de confidencialidad 0-4"},
                "value_integrity": {"type": "integer", "description": "Valor de integridad 0-4"},
                "value_availability": {"type": "integer", "description": "Valor de disponibilidad 0-4"},
            },
            "required": ["name", "asset_type"],
        },
    },
    {
        "name": "update_asset_cia",
        "description": (
            "Propone actualizar la valoracion CIA de un activo existente. "
            "Usar cuando el usuario indique que la criticidad de un activo ha cambiado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_name": {"type": "string", "description": "Nombre o codigo del activo (ej: AST-0001 o 'Servidor Web')"},
                "value_confidentiality": {"type": "integer", "description": "Nuevo valor de confidencialidad 0-4"},
                "value_integrity": {"type": "integer", "description": "Nuevo valor de integridad 0-4"},
                "value_availability": {"type": "integer", "description": "Nuevo valor de disponibilidad 0-4"},
                "justification": {"type": "string", "description": "Motivo del cambio de valoracion"},
            },
            "required": ["asset_name"],
        },
    },
    # ── Riesgos ─────────────────────────────────────────────────────────────
    {
        "name": "create_risk",
        "description": (
            "Propone registrar un nuevo riesgo en el registro ISO 27005. "
            "Usar cuando el usuario identifique una amenaza o escenario de riesgo que deba documentarse."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Descripcion clara del escenario de riesgo"},
                "asset_name": {"type": "string", "description": "Nombre del activo afectado (debe existir en el inventario)"},
                "threat_name": {"type": "string", "description": "Nombre de la amenaza (del catalogo o nueva)"},
                "vulnerability": {"type": "string", "description": "Descripcion de la vulnerabilidad explotada"},
                "consequence": {"type": "integer", "description": "Nivel de consecuencia/impacto 0-4"},
                "likelihood": {"type": "integer", "description": "Nivel de probabilidad 0-4"},
                "treatment_option": {
                    "type": "string",
                    "enum": ["modification", "retention", "avoidance", "sharing"],
                    "description": "Opcion de tratamiento propuesta",
                },
            },
            "required": ["description", "threat_name", "consequence", "likelihood"],
        },
    },
    {
        "name": "update_risk_treatment",
        "description": (
            "Propone cambiar la opcion de tratamiento de un riesgo existente. "
            "Usar cuando el usuario decida aceptar, mitigar, evitar o transferir un riesgo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "risk_code": {"type": "string", "description": "Codigo del riesgo, ej: RSK-0001"},
                "treatment_option": {
                    "type": "string",
                    "enum": ["modification", "retention", "avoidance", "sharing"],
                    "description": "Nueva opcion de tratamiento",
                },
                "justification": {"type": "string", "description": "Justificacion de la decision de tratamiento"},
            },
            "required": ["risk_code", "treatment_option", "justification"],
        },
    },
    {
        "name": "link_control_to_risk",
        "description": (
            "Propone vincular un control ISO 27002 existente a un riesgo como medida de mitigacion. "
            "Usar cuando el usuario quiera asociar un control a un riesgo especifico."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "risk_code": {"type": "string", "description": "Codigo del riesgo, ej: RSK-0001"},
                "control_code": {"type": "string", "description": "Codigo del control ISO 27002, ej: 5.1 o 8.12"},
                "rationale": {"type": "string", "description": "Explicacion de por que este control mitiga el riesgo"},
            },
            "required": ["risk_code", "control_code"],
        },
    },
    # ── Controles ────────────────────────────────────────────────────────────
    {
        "name": "update_control_maturity",
        "description": (
            "Propone actualizar el nivel de madurez de un control ISO 27002 implementado. "
            "Usar cuando el usuario informe que ha mejorado la implementacion de un control."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "control_name": {"type": "string", "description": "Nombre o codigo del control (ej: '5.1' o 'Politica de seguridad')"},
                "new_maturity": {"type": "integer", "description": "Nuevo nivel de madurez 1-5"},
                "justification": {"type": "string", "description": "Evidencia o motivo del cambio de madurez"},
            },
            "required": ["control_name", "new_maturity"],
        },
    },
    # ── No conformidades ─────────────────────────────────────────────────────
    {
        "name": "create_nonconformity",
        "description": (
            "Propone registrar una no conformidad en el SGSI. "
            "Usar cuando el usuario identifique un incumplimiento de un requisito ISO 27001 "
            "o un hallazgo de auditoria que deba gestionarse formalmente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titulo descriptivo de la no conformidad"},
                "description": {"type": "string", "description": "Descripcion del incumplimiento y su alcance"},
                "severity": {
                    "type": "string",
                    "enum": ["critical", "major", "minor", "observation"],
                    "description": "Severidad: critical=riesgo inmediato, major=incumplimiento sistematico, minor=desviacion puntual, observation=area de mejora",
                },
                "iso_clause": {"type": "string", "description": "Clausula ISO 27001 incumplida (ej: '9.1', 'A.8.1')"},
            },
            "required": ["title", "description", "severity"],
        },
    },
    # ── Tareas ───────────────────────────────────────────────────────────────
    {
        "name": "update_task_status",
        "description": (
            "Propone actualizar el estado de una tarea de tratamiento existente. "
            "Usar cuando el usuario informe del progreso o completado de una tarea."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_code": {"type": "string", "description": "Codigo de la tarea, ej: TSK-0001"},
                "new_status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "blocked", "done"],
                    "description": "Nuevo estado de la tarea",
                },
                "notes": {"type": "string", "description": "Notas sobre el progreso o motivo del cambio"},
            },
            "required": ["task_code", "new_status"],
        },
    },
    # ── Incidentes ───────────────────────────────────────────────────────────
    {
        "name": "update_incident_status",
        "description": (
            "Propone avanzar el estado de un incidente de seguridad en su ciclo de vida. "
            "Usar cuando el usuario informe de progreso en la respuesta a un incidente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_code": {"type": "string", "description": "Codigo del incidente, ej: INC-0001"},
                "new_status": {
                    "type": "string",
                    "enum": ["open", "investigating", "contained", "resolved", "closed"],
                    "description": "Nuevo estado del incidente",
                },
                "resolution_summary": {"type": "string", "description": "Resumen de las acciones tomadas o estado actual"},
            },
            "required": ["incident_code", "new_status"],
        },
    },
    # ── Politicas ────────────────────────────────────────────────────────────
    {
        "name": "create_policy_draft",
        "description": (
            "Propone crear un borrador de politica de seguridad. "
            "Usar cuando el usuario solicite crear una nueva politica (PSI, control de acceso, etc.)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titulo de la politica"},
                "category": {"type": "string", "description": "Categoria (ej: Control de acceso, Gestion de incidentes, Uso aceptable)"},
                "scope": {"type": "string", "description": "Alcance y destinatarios de la politica"},
                "iso_clauses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Clausulas ISO 27001/27002 que esta politica implementa (ej: ['5.2', '8.1'])",
                },
            },
            "required": ["title", "category"],
        },
    },
    # ── Proveedores ──────────────────────────────────────────────────────────
    {
        "name": "create_supplier",
        "description": (
            "Propone dar de alta un nuevo proveedor en el registro TPRM. "
            "Usar cuando el usuario mencione un proveedor, partner o tercero que deba gestionarse."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre del proveedor o empresa"},
                "category": {"type": "string", "description": "Categoria de servicio (ej: Cloud, Consultoria, Software, Infraestructura)"},
                "country": {"type": "string", "description": "Pais de sede del proveedor (ej: ES, US, DE)"},
                "is_critical": {"type": "boolean", "description": "True si es proveedor critico para el negocio"},
                "tier": {
                    "type": "string",
                    "enum": ["tier_1", "tier_2", "tier_3"],
                    "description": "Tier de riesgo: tier_1=critico, tier_2=importante, tier_3=estandar",
                },
            },
            "required": ["name", "category"],
        },
    },
    # ── Evidencias ───────────────────────────────────────────────────────────
    {
        "name": "register_evidence",
        "description": (
            "Propone registrar una evidencia en el repositorio centralizado del SGSI. "
            "Usar cuando el usuario mencione que dispone de una evidencia (certificado, log, "
            "informe, captura) que debe vincularse a un control, riesgo o politica."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titulo descriptivo de la evidencia"},
                "evidence_type": {
                    "type": "string",
                    "enum": ["policy", "procedure", "record", "certificate", "screenshot", "log", "report", "other"],
                    "description": "Tipo de evidencia",
                },
                "description": {"type": "string", "description": "Descripcion del contenido y que demuestra"},
                "control_code": {"type": "string", "description": "Codigo del control ISO 27002 al que se vincula (ej: 5.1)"},
                "risk_code": {"type": "string", "description": "Codigo del riesgo al que se vincula (ej: RSK-0001)"},
            },
            "required": ["title", "evidence_type", "description"],
        },
    },
    # ── Archivo adjunto ──────────────────────────────────────────────────────
    {
        "name": "store_uploaded_file",
        "description": (
            "Propone guardar el archivo que el usuario ha adjuntado al chat en la ubicacion correcta del SGSI. "
            "Usar UNICAMENTE cuando el usuario haya adjuntado un archivo en este turno de conversacion "
            "y el contexto incluya un upload_id. Clasifica el archivo segun su contenido y destino."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "upload_id": {"type": "string", "description": "ID del archivo temporal proporcionado en el contexto"},
                "destination": {
                    "type": "string",
                    "enum": ["ai_document", "evidence", "policy_document"],
                    "description": "Destino: ai_document=indexar para RAG, evidence=evidencia de control/riesgo, policy_document=documento de politica ISMS",
                },
                "title": {"type": "string", "description": "Titulo descriptivo para el archivo"},
                "evidence_type": {
                    "type": "string",
                    "enum": ["policy", "procedure", "record", "certificate", "screenshot", "log", "report", "other"],
                    "description": "Solo si destination=evidence: tipo de evidencia",
                },
                "control_code": {"type": "string", "description": "Solo si destination=evidence: codigo del control asociado"},
                "risk_code": {"type": "string", "description": "Solo si destination=evidence: codigo del riesgo asociado"},
            },
            "required": ["upload_id", "destination", "title"],
        },
    },
    # ── Automatizaciones ─────────────────────────────────────────────────────
    {
        "name": "run_ccm",
        "description": (
            "Propone ejecutar los tests de Continuous Control Monitoring (CCM) ahora mismo. "
            "Usar cuando el usuario quiera verificar el estado operativo de los controles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Motivo por el que se solicita la evaluacion CCM"},
            },
            "required": [],
        },
    },
    {
        "name": "trigger_osint_scan",
        "description": (
            "Propone lanzar un escaneo OSINT sobre un dominio, email o IP de la organizacion. "
            "Usar cuando el usuario quiera verificar la exposicion de un activo externo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Dominio, email o IP a escanear"},
                "scan_type": {
                    "type": "string",
                    "enum": ["domain", "email", "ip", "url"],
                    "description": "Tipo de objetivo",
                },
            },
            "required": ["target", "scan_type"],
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
    if name == "create_asset":
        return f"Crear activo: \"{inp.get('name', '')}\" [{inp.get('asset_type', '')}]"
    if name == "update_asset_cia":
        cia = f"C={inp.get('value_confidentiality','?')} I={inp.get('value_integrity','?')} A={inp.get('value_availability','?')}"
        return f"Actualizar CIA de activo \"{inp.get('asset_name', '?')}\": {cia}"
    if name == "create_risk":
        return f"Registrar riesgo: \"{inp.get('description', '')[:60]}\" [impacto={inp.get('consequence','?')}/4, prob={inp.get('likelihood','?')}/4]"
    if name == "update_risk_treatment":
        return f"Cambiar tratamiento {inp.get('risk_code','?')} → {inp.get('treatment_option','').upper()}"
    if name == "link_control_to_risk":
        return f"Vincular control {inp.get('control_code','?')} al riesgo {inp.get('risk_code','?')}"
    if name == "update_control_maturity":
        return f"Actualizar madurez de \"{inp.get('control_name','?')}\" → nivel {inp.get('new_maturity','?')}/5"
    if name == "create_nonconformity":
        return f"Registrar NC [{inp.get('severity','?').upper()}]: \"{inp.get('title','')}\" "
    if name == "update_task_status":
        return f"Actualizar tarea {inp.get('task_code','?')} → {inp.get('new_status','').upper()}"
    if name == "update_incident_status":
        return f"Actualizar incidente {inp.get('incident_code','?')} → {inp.get('new_status','').upper()}"
    if name == "create_policy_draft":
        return f"Crear borrador de politica: \"{inp.get('title','')}\" [{inp.get('category','')}]"
    if name == "create_supplier":
        tier = inp.get('tier', 'tier_3')
        return f"Dar de alta proveedor: \"{inp.get('name','')}\" [{inp.get('category','')} | {tier}]"
    if name == "register_evidence":
        return f"Registrar evidencia [{inp.get('evidence_type','?')}]: \"{inp.get('title','')}\" "
    if name == "store_uploaded_file":
        return f"Guardar archivo adjunto: \"{inp.get('title','')}\" → {inp.get('destination','?')}"
    if name == "run_ccm":
        return "Ejecutar evaluacion CCM de controles ahora"
    if name == "trigger_osint_scan":
        return f"Lanzar escaneo OSINT [{inp.get('scan_type','?')}]: {inp.get('target','?')}"
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


_MAX_TOKENS_CAP = 32000
_MAX_MESSAGES = 40       # evitar payloads gigantes


class ChatMessage(BaseModel):
    role: str     # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    max_tokens: int = 16384


class FeedbackIn(BaseModel):
    call_log_id: Optional[int] = None
    rating: int   # 1..5
    comment: Optional[str] = None
    call_type: Optional[str] = None


@router.post("/chat")
def chat(
    req: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Chat conversacional con el agente IA enriquecido con el contexto de la organizacion."""
    lang = get_lang(request)
    # Aplicar topes de seguridad del lado del servidor
    capped_max_tokens = min(req.max_tokens, _MAX_TOKENS_CAP)
    if len(req.messages) > _MAX_MESSAGES:
        raise HTTPException(400, f"Demasiados mensajes en el historial (maximo {_MAX_MESSAGES}).")

    cfg = db.query(AiConfig).filter(
        AiConfig.organization_id == current_user.organization_id
    ).first()
    api_key = _resolve_api_key(cfg)
    if not api_key:
        raise HTTPException(400, _t("ai.not_configured", lang))

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
        lang=lang,
    )
    if anon_level_val != "low":
        context = anonymize(context, anon_level_val)

    system_prompt = (
        ai_lang_directive(lang) + "\n\n" +
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
        "- Responde de forma concisa y orientada a la accion.\n"
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

        "== MANUAL FUNCIONAL DE LA APLICACION ==\n"
        "Eres tambien el asistente funcional de RiskHub. Puedes responder preguntas sobre:\n"
        "- Configuracion de integraciones (SSO con Entra ID/Google/Okta, SharePoint, ERP Webhooks).\n"
        "- Flujos de trabajo (gestion de proveedores TPRM, gestion de incidentes, auditorias, NC, politicas).\n"
        "- Metodologias y calculos automatizados (calculo de riesgo ISO 27005, MAGERIT v3, scoring TPRM).\n"
        "- Flujos de IA (RAG, indexacion de documentos, analisis automatico, extraccion de clausulas ISO).\n"
        "- Modulos de la plataforma (OSINT, CVE, Regwatch, BCP, GDPR, Compliance, Alertas, Informes).\n"
        "- Roles, usuarios, planes y licenciamiento.\n"
        "Cuando el contexto incluya una seccion '## Manual funcional de RiskHub', usala como fuente "
        "principal para responder la pregunta del usuario con pasos concretos y detallados.\n"
        "Si el usuario pregunta algo funcional y no hay seccion relevante en el contexto, responde "
        "con tu conocimiento general de la plataforma segun lo descrito en este prompt.\n\n"

        "== PREGUNTAS SOBRE CONFIGURACION ==\n"
        "Si el usuario pregunta sobre configuracion (API key, documentos, alertas, integraciones, etc.), proporciona:\n"
        "1. Respuesta paso a paso clara.\n"
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

        "== EVALUACION DE CUMPLIMIENTO NORMATIVO ==\n"
        "Cuando el usuario pregunte sobre cumplimiento normativo (ISO 27001, ENS, SOC 2, NIS2, GDPR, NIST CSF, HIPAA), "
        "debes actuar como auditor independiente, NO como consultor de ventas. Reglas estrictas:\n"
        "1. OBJETIVIDAD ANTE TODO: No valides afirmaciones del usuario sin respaldo en los datos del contexto. "
        "Si el usuario dice 'estamos bien en ISO 27001', verifica los datos y corrige si es necesario.\n"
        "2. CONTROLES SIN EVIDENCIA = NO IMPLEMENTADOS: Un control marcado como 'implementado' pero sin evidencias "
        "adjuntas (evidence_refs vacio) NO puede considerarse CONFORME para una auditoria. Indicalo siempre.\n"
        "3. NO CONFORMIDADES MAYORES ABIERTAS BLOQUEAN CERTIFICACION: Si hay NCs mayores abiertas, la organizacion "
        "NO esta en condiciones de obtener o mantener la certificacion. Dilo explicitamente.\n"
        "4. DISTINGUE CUMPLIMIENTO FORMAL DE CUMPLIMIENTO REAL: Un % alto de controles 'implementados' no equivale "
        "a cumplimiento real si no hay evidencias. El auditor de certificacion rechazara controles sin prueba.\n"
        "5. PRECISION NORMATIVA: Cita siempre el articulo o clausula especifica (ej. ISO 27001:2022 cl. 9.2, "
        "ENS op.acc.5, SOC 2 CC6.1, NIS2 Art.21.2.b, GDPR Art.32). Jamas generalices.\n"
        "6. ACCIONES DE MEJORA REALISTAS: Las acciones que propongas deben ser especificas, con responsable "
        "sugerido, plazo concreto y criterio de cierre verificable. No propongas acciones vagas.\n"
        "7. ENS: Indica siempre el nivel de categoria (basico/medio/alto) que aplica a cada medida. "
        "Las medidas de nivel alto son obligatorias solo para sistemas de categoria ALTA.\n"
        "8. SOC 2: Los Trust Services Criteria (CC, A, PI, C, P) tienen criterios subcriterios especificos. "
        "Cita el criterio exacto (ej. CC6.1, CC7.2) al mencionar un gap.\n"
        "9. NO EXAGERES EL % DE CUMPLIMIENTO: Si el contexto muestra controles sin evidencia o gaps estructurales, "
        "el % real es inferior al % de controles 'implementados'. Calcula y comunica la diferencia.\n"
        "10. TRATA RIESGOS RESIDUALES ALTOS COMO INCUMPLIMIENTO: Si hay riesgos con nivel residual > apetito de "
        "riesgo y afectan controles 'implementados', esos controles no son efectivos. Degrada su evaluacion.\n\n"

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
        raise HTTPException(500, _t("ai.api_error", lang, detail=str(e)))

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


@router.post("/upload-file")
async def upload_file_for_chat(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Acepta un archivo adjunto al chat y lo almacena temporalmente (30 min TTL).
    Devuelve upload_id para referenciar el archivo en la accion store_uploaded_file."""
    from fastapi import UploadFile
    form = await request.form()
    file: UploadFile | None = form.get("file")  # type: ignore[assignment]
    if not file:
        raise HTTPException(400, "Se requiere un campo 'file' en el formulario.")

    # Validacion de tipo y tamanyo
    ALLOWED_TYPES = {
        "application/pdf", "text/plain", "text/csv",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/png", "image/jpeg", "image/gif",
    }
    MAX_SIZE_MB = 20
    content_type = file.content_type or "application/octet-stream"
    data = await file.read()
    if len(data) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"El archivo supera el limite de {MAX_SIZE_MB} MB.")
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"Tipo de archivo no permitido: {content_type}")

    upload_id = str(uuid.uuid4())
    with _UPLOADS_LOCK:
        _cleanup_old_jobs()
        _UPLOADS[upload_id] = {
            "bytes": data,
            "filename": file.filename or "adjunto",
            "mime": content_type,
            "size": len(data),
            "created_at": datetime.now(timezone.utc),
            "organization_id": current_user.organization_id,
            "user_id": current_user.id,
        }

    return {
        "upload_id": upload_id,
        "filename": file.filename,
        "size": len(data),
        "content_type": content_type,
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
        if name == "create_asset":
            return _exec_create_asset(db, inp, org_id, current_user.id)
        if name == "update_asset_cia":
            return _exec_update_asset_cia(db, inp, org_id)
        if name == "create_risk":
            return _exec_create_risk(db, inp, org_id, current_user.id)
        if name == "update_risk_treatment":
            return _exec_update_risk_treatment(db, inp, org_id)
        if name == "link_control_to_risk":
            return _exec_link_control_to_risk(db, inp, org_id)
        if name == "update_control_maturity":
            return _exec_update_control_maturity(db, inp, org_id)
        if name == "create_nonconformity":
            return _exec_create_nonconformity(db, inp, org_id, current_user.id)
        if name == "update_task_status":
            return _exec_update_task_status(db, inp, org_id)
        if name == "update_incident_status":
            return _exec_update_incident_status(db, inp, org_id)
        if name == "create_policy_draft":
            return _exec_create_policy_draft(db, inp, org_id, current_user.id)
        if name == "create_supplier":
            return _exec_create_supplier(db, inp, org_id, current_user.id)
        if name == "register_evidence":
            return _exec_register_evidence(db, inp, org_id, current_user.id)
        if name == "store_uploaded_file":
            return _exec_store_uploaded_file(db, inp, org_id, current_user.id)
        if name == "run_ccm":
            return _exec_run_ccm(db, org_id)
        if name == "trigger_osint_scan":
            return _exec_trigger_osint_scan(db, inp, org_id, current_user.id)
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


def _exec_create_asset(db: Session, inp: dict, org_id, user_id: int) -> dict:
    _clamp = lambda v, lo, hi: max(lo, min(hi, int(v))) if v is not None else 2
    type_map = {t.value: t for t in AssetType}
    asset_type = type_map.get(inp.get("asset_type", "support_software"), AssetType.SUPPORT_SOFTWARE)
    code = _next_code(db, Asset, "AST", org_id)
    asset = Asset(
        organization_id=org_id,
        code=code,
        name=inp["name"],
        description=inp.get("description", ""),
        asset_type=asset_type,
        value_confidentiality=_clamp(inp.get("value_confidentiality"), 0, 4),
        value_integrity=_clamp(inp.get("value_integrity"), 0, 4),
        value_availability=_clamp(inp.get("value_availability"), 0, 4),
        owner_id=user_id,
    )
    db.add(asset)
    db.commit()
    return {"ok": True, "message": f"Activo {code} '{asset.name}' creado correctamente.", "code": code}


def _exec_update_asset_cia(db: Session, inp: dict, org_id) -> dict:
    name_or_code = inp.get("asset_name", "")
    asset = (
        db.query(Asset).filter(Asset.organization_id == org_id, Asset.code == name_or_code).first()
        or db.query(Asset).filter(Asset.organization_id == org_id, Asset.name.ilike(f"%{name_or_code}%")).first()
    )
    if not asset:
        raise HTTPException(404, f"Activo '{name_or_code}' no encontrado.")
    _clamp = lambda v, lo, hi: max(lo, min(hi, int(v))) if v is not None else None
    if inp.get("value_confidentiality") is not None:
        asset.value_confidentiality = _clamp(inp["value_confidentiality"], 0, 4)
    if inp.get("value_integrity") is not None:
        asset.value_integrity = _clamp(inp["value_integrity"], 0, 4)
    if inp.get("value_availability") is not None:
        asset.value_availability = _clamp(inp["value_availability"], 0, 4)
    db.commit()
    return {"ok": True, "message": f"Valoracion CIA de '{asset.name}' ({asset.code}) actualizada.", "code": asset.code}


def _exec_create_risk(db: Session, inp: dict, org_id, user_id: int) -> dict:
    from app.services.risk_engine import calc_level
    _clamp = lambda v: max(0, min(4, int(v))) if v is not None else 2
    consequence = _clamp(inp.get("consequence"))
    likelihood = _clamp(inp.get("likelihood"))
    inherent_level = calc_level(consequence, likelihood)
    # Resolver activo por nombre
    asset_id = None
    if inp.get("asset_name"):
        a = (
            db.query(Asset).filter(Asset.organization_id == org_id, Asset.code == inp["asset_name"]).first()
            or db.query(Asset).filter(Asset.organization_id == org_id, Asset.name.ilike(f"%{inp['asset_name']}%")).first()
        )
        if a:
            asset_id = a.id
    # Resolver amenaza por nombre
    threat_id = None
    if inp.get("threat_name"):
        t = db.query(Threat).filter(
            Threat.organization_id == org_id,
            Threat.name.ilike(f"%{inp['threat_name']}%"),
        ).first()
        if t:
            threat_id = t.id
    treatment_map = {
        "modification": TreatmentOption.MODIFICATION,
        "retention": TreatmentOption.RETENTION,
        "avoidance": TreatmentOption.AVOIDANCE,
        "sharing": TreatmentOption.SHARING,
    }
    treatment = treatment_map.get(inp.get("treatment_option", "modification"), TreatmentOption.MODIFICATION)
    code = _next_code(db, Risk, "RSK", org_id)
    risk = Risk(
        organization_id=org_id,
        code=code,
        description=inp["description"],
        asset_id=asset_id,
        threat_id=threat_id,
        vulnerability_description=inp.get("vulnerability", ""),
        inherent_consequence=consequence,
        inherent_likelihood=likelihood,
        inherent_level=inherent_level,
        residual_consequence=consequence,
        residual_likelihood=likelihood,
        residual_level=inherent_level,
        treatment_option=treatment,
        status=RiskStatus.IDENTIFIED,
        owner_id=user_id,
    )
    db.add(risk)
    db.commit()
    return {"ok": True, "message": f"Riesgo {code} registrado (nivel inherente={inherent_level}/8).", "code": code}


def _exec_update_risk_treatment(db: Session, inp: dict, org_id) -> dict:
    treatment_map = {
        "modification": TreatmentOption.MODIFICATION,
        "retention": TreatmentOption.RETENTION,
        "avoidance": TreatmentOption.AVOIDANCE,
        "sharing": TreatmentOption.SHARING,
    }
    risk = db.query(Risk).filter(Risk.organization_id == org_id, Risk.code == inp.get("risk_code", "")).first()
    if not risk:
        raise HTTPException(404, f"Riesgo {inp.get('risk_code')} no encontrado.")
    risk.treatment_option = treatment_map.get(inp["treatment_option"], TreatmentOption.MODIFICATION)
    if inp.get("justification"):
        risk.description = (risk.description or "") + f"\n\n[Agente IA — Tratamiento] {inp['justification']}"
    db.commit()
    return {"ok": True, "message": f"Tratamiento de {risk.code} actualizado a '{inp['treatment_option']}'.", "code": risk.code}


def _exec_link_control_to_risk(db: Session, inp: dict, org_id) -> dict:
    risk = db.query(Risk).filter(Risk.organization_id == org_id, Risk.code == inp.get("risk_code", "")).first()
    if not risk:
        raise HTTPException(404, f"Riesgo {inp.get('risk_code')} no encontrado.")
    ctrl = (
        db.query(ControlImplementation)
        .filter(ControlImplementation.organization_id == org_id)
        .filter(
            (ControlImplementation.iso_code == inp.get("control_code"))
            | ControlImplementation.name.ilike(f"%{inp.get('control_code', '')}%")
        )
        .first()
    )
    if not ctrl:
        raise HTTPException(404, f"Control '{inp.get('control_code')}' no encontrado en el catalogo implementado.")
    # Registrar vinculacion en el campo de notas del riesgo (relacion a nivel de nota auditada)
    note = f"\n[Control vinculado] {ctrl.iso_code} — {ctrl.name}"
    if inp.get("rationale"):
        note += f": {inp['rationale']}"
    risk.description = (risk.description or "") + note
    db.commit()
    return {"ok": True, "message": f"Control {ctrl.iso_code} vinculado al riesgo {risk.code}.", "code": risk.code}


def _exec_update_control_maturity(db: Session, inp: dict, org_id) -> dict:
    name_or_code = inp.get("control_name", "")
    ctrl = (
        db.query(ControlImplementation)
        .filter(ControlImplementation.organization_id == org_id)
        .filter(
            (ControlImplementation.iso_code == name_or_code)
            | ControlImplementation.name.ilike(f"%{name_or_code}%")
        )
        .first()
    )
    if not ctrl:
        raise HTTPException(404, f"Control '{name_or_code}' no encontrado.")
    new_mat = max(1, min(5, int(inp.get("new_maturity", 3))))
    ctrl.maturity = new_mat
    if inp.get("justification"):
        ctrl.notes = ((ctrl.notes or "") + f"\n[Agente IA] Madurez actualizada a {new_mat}: {inp['justification']}").strip()
    db.commit()
    return {"ok": True, "message": f"Madurez de '{ctrl.name}' actualizada a {new_mat}/5.", "code": ctrl.iso_code}


def _exec_create_nonconformity(db: Session, inp: dict, org_id, user_id: int) -> dict:
    sev_map = {
        "critical": NCSeverity.CRITICAL, "major": NCSeverity.MAJOR,
        "minor": NCSeverity.MINOR, "observation": NCSeverity.OBSERVATION,
    }
    severity = sev_map.get(inp.get("severity", "minor"), NCSeverity.MINOR)
    code = _next_code(db, NonConformity, "NC", org_id)
    nc = NonConformity(
        organization_id=org_id,
        code=code,
        title=inp["title"],
        description=inp.get("description", ""),
        severity=severity,
        status=NCStatus.OPEN,
        iso_clause=inp.get("iso_clause", ""),
        detected_by_id=user_id,
        detected_at=datetime.now(timezone.utc),
    )
    db.add(nc)
    db.commit()
    return {"ok": True, "message": f"No conformidad {code} [{severity.value}] registrada.", "code": code}


def _exec_update_task_status(db: Session, inp: dict, org_id) -> dict:
    status_map = {
        "pending": TaskStatus.PENDING, "in_progress": TaskStatus.IN_PROGRESS,
        "blocked": TaskStatus.BLOCKED, "done": TaskStatus.DONE,
    }
    task = db.query(TreatmentTask).filter(
        TreatmentTask.organization_id == org_id,
        TreatmentTask.code == inp.get("task_code", ""),
    ).first()
    if not task:
        raise HTTPException(404, f"Tarea {inp.get('task_code')} no encontrada.")
    task.status = status_map.get(inp.get("new_status", "in_progress"), TaskStatus.IN_PROGRESS)
    if inp.get("notes"):
        task.notes = ((task.notes or "") + f"\n[Agente IA] {inp['notes']}").strip()
    db.commit()
    return {"ok": True, "message": f"Tarea {task.code} actualizada a estado '{task.status.value}'.", "code": task.code}


def _exec_update_incident_status(db: Session, inp: dict, org_id) -> dict:
    status_map = {
        "open": IncidentStatus.OPEN, "investigating": IncidentStatus.INVESTIGATING,
        "contained": IncidentStatus.CONTAINED, "resolved": IncidentStatus.RESOLVED,
        "closed": IncidentStatus.CLOSED,
    }
    incident = db.query(Incident).filter(
        Incident.organization_id == org_id,
        Incident.code == inp.get("incident_code", ""),
    ).first()
    if not incident:
        raise HTTPException(404, f"Incidente {inp.get('incident_code')} no encontrado.")
    incident.status = status_map.get(inp.get("new_status", "investigating"), IncidentStatus.INVESTIGATING)
    if inp.get("new_status") in ("resolved", "closed"):
        incident.resolved_at = datetime.now(timezone.utc)
    if inp.get("resolution_summary"):
        incident.description = (
            (incident.description or "") + f"\n\n[Agente IA — {inp['new_status']}] {inp['resolution_summary']}"
        )
    db.commit()
    return {
        "ok": True,
        "message": f"Incidente {incident.code} actualizado a '{incident.status.value}'.",
        "code": incident.code,
    }


def _exec_create_policy_draft(db: Session, inp: dict, org_id, user_id: int) -> dict:
    code = _next_code(db, Policy, "POL", org_id)
    policy = Policy(
        organization_id=org_id,
        code=code,
        title=inp["title"],
        category=inp.get("category", ""),
        scope=inp.get("scope", ""),
        status=PolicyStatus.DRAFT,
        version="1.0",
        iso_clauses=inp.get("iso_clauses", []),
        owner_id=user_id,
    )
    db.add(policy)
    db.commit()
    return {"ok": True, "message": f"Politica {code} '{policy.title}' creada como borrador.", "code": code}


def _exec_create_supplier(db: Session, inp: dict, org_id, user_id: int) -> dict:
    tier_map = {"tier_1": SupplierTier.TIER_1, "tier_2": SupplierTier.TIER_2, "tier_3": SupplierTier.TIER_3}
    code = _next_code(db, Supplier, "SUP", org_id)
    supplier = Supplier(
        organization_id=org_id,
        code=code,
        name=inp["name"],
        category=inp.get("category", ""),
        country=inp.get("country", ""),
        is_critical=bool(inp.get("is_critical", False)),
        tier=tier_map.get(inp.get("tier", "tier_3"), SupplierTier.TIER_3),
        risk_level=SupplierRisk.MEDIUM,
    )
    db.add(supplier)
    db.commit()
    return {"ok": True, "message": f"Proveedor {code} '{supplier.name}' dado de alta correctamente.", "code": code}


def _exec_register_evidence(db: Session, inp: dict, org_id, user_id: int) -> dict:
    etype_map = {e.value: e for e in EvidenceType}
    etype = etype_map.get(inp.get("evidence_type", "other"), EvidenceType.OTHER)
    code = _next_code(db, Evidence, "EVD", org_id)
    # Resolver vinculaciones opcionales
    ctrl_id = None
    if inp.get("control_code"):
        c = db.query(ControlImplementation).filter(
            ControlImplementation.organization_id == org_id,
            ControlImplementation.iso_code == inp["control_code"],
        ).first()
        ctrl_id = c.id if c else None
    risk_id = None
    if inp.get("risk_code"):
        r = db.query(Risk).filter(Risk.organization_id == org_id, Risk.code == inp["risk_code"]).first()
        risk_id = r.id if r else None
    ev = Evidence(
        organization_id=org_id,
        code=code,
        title=inp["title"],
        description=inp.get("description", ""),
        evidence_type=etype,
        control_implementation_id=ctrl_id,
        risk_id=risk_id,
        created_by_id=user_id,
        version=1,
        is_current=True,
    )
    db.add(ev)
    db.commit()
    return {"ok": True, "message": f"Evidencia {code} '{ev.title}' registrada correctamente.", "code": code}


def _exec_store_uploaded_file(db: Session, inp: dict, org_id, user_id: int) -> dict:
    upload_id = inp.get("upload_id", "")
    with _UPLOADS_LOCK:
        upload = _UPLOADS.pop(upload_id, None)
    if not upload:
        raise HTTPException(404, "Archivo adjunto no encontrado o expirado. Vuelve a adjuntarlo.")
    destination = inp.get("destination", "ai_document")
    filename = upload["filename"]
    file_bytes = upload["bytes"]
    title = inp.get("title") or filename

    if destination == "evidence":
        import hashlib
        code = _next_code(db, Evidence, "EVD", org_id)
        etype_map = {e.value: e for e in EvidenceType}
        etype = etype_map.get(inp.get("evidence_type", "other"), EvidenceType.OTHER)
        ctrl_id = None
        if inp.get("control_code"):
            c = db.query(ControlImplementation).filter(
                ControlImplementation.organization_id == org_id,
                ControlImplementation.iso_code == inp["control_code"],
            ).first()
            ctrl_id = c.id if c else None
        risk_id = None
        if inp.get("risk_code"):
            r = db.query(Risk).filter(Risk.organization_id == org_id, Risk.code == inp["risk_code"]).first()
            risk_id = r.id if r else None
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        ev = Evidence(
            organization_id=org_id, code=code, title=title,
            description=f"Adjunto via agente IA. Archivo original: {filename}",
            evidence_type=etype, filename=filename,
            file_hash=file_hash, file_size=len(file_bytes),
            control_implementation_id=ctrl_id, risk_id=risk_id,
            created_by_id=user_id, version=1, is_current=True,
        )
        db.add(ev)
        db.commit()
        return {"ok": True, "message": f"Archivo guardado como evidencia {code} '{title}'.", "code": code}

    if destination in ("ai_document", "policy_document"):
        from app.models import AiDocument, AiDocumentStatus, AiDocumentCategory
        from app.services.document_service import process_document
        cat = AiDocumentCategory.POLICIES if destination == "policy_document" else AiDocumentCategory.OTHER
        code_doc = _next_code(db, AiDocument, "DOC", org_id)
        doc = AiDocument(
            organization_id=org_id,
            original_name=filename,
            status=AiDocumentStatus.PENDING,
            category=cat,
            uploaded_by_id=user_id,
        )
        db.add(doc)
        db.flush()
        try:
            process_document(db, doc.id, file_bytes, filename)
        except Exception:
            pass
        db.commit()
        return {"ok": True, "message": f"Archivo '{filename}' subido e indexado para el agente IA (doc #{doc.id}).", "code": str(doc.id)}

    raise HTTPException(400, f"Destino desconocido: {destination}")


def _exec_run_ccm(db: Session, org_id) -> dict:
    from app.services.ccm_service import run_all_tests
    results = run_all_tests(db, org_id, limit=100, offset=0)
    score = results.get("score", 0)
    total = results.get("total", 0)
    passed = results.get("passed", 0)
    failed = results.get("failed", 0)
    return {
        "ok": True,
        "message": (
            f"CCM ejecutado: {passed}/{total} controles OK, {failed} fallos. "
            f"Score global: {score}/100."
        ),
        "score": score,
        "passed": passed,
        "failed": failed,
        "total": total,
    }


def _exec_trigger_osint_scan(db: Session, inp: dict, org_id, user_id: int) -> dict:
    from app.models import OSINTScan, OSINTScanType
    scan_type_map = {
        "domain": OSINTScanType.DOMAIN, "email": OSINTScanType.EMAIL,
        "ip": OSINTScanType.IP, "url": OSINTScanType.URL,
    }
    scan_type = scan_type_map.get(inp.get("scan_type", "domain"), OSINTScanType.DOMAIN)
    target = inp.get("target", "")
    scan = OSINTScan(
        organization_id=org_id,
        user_id=user_id,
        scan_type=scan_type,
        target=target,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db.add(scan)
    db.commit()
    return {
        "ok": True,
        "message": f"Escaneo OSINT [{scan_type.value}] sobre '{target}' programado. El resultado estara disponible en OSINT > Historial.",
        "scan_id": scan.id,
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
