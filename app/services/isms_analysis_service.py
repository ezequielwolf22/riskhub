"""Analisis automatico ISMS de documentos subidos al agente IA.

Cuando un documento queda INDEXED, este servicio llama al agente IA para:
  1. Detectar si el documento es una politica y crear/actualizar la entrada en Policy.
  2. Identificar controles ISO 27002 cubiertos y actualizar ControlImplementation.
  3. Detectar categorias de amenaza abordadas y crear TreatmentTask para riesgos activos.

El analisis se ejecuta en background (BackgroundTasks de FastAPI) para no bloquear
la respuesta HTTP de subida de documento.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    AiCallLog, AiConfig, AiDocument, AiDocumentStatus,
    Asset,
    Control, ControlImplementation, ControlStatus,
    Policy, PolicyStatus,
    Risk, RiskContext, RiskStatus,
    TaskPriority, TaskStatus, TreatmentTask,
    User,
)

logger = logging.getLogger(__name__)

# A5: pool compartido para limitar threads concurrentes (sin pool habia 2 threads por documento)
_ISMS_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="isms-bg")

# ---------- Prompt del sistema ----------

_ISMS_SYSTEM_PROMPT = """Eres un experto senior en seguridad de la informacion (ISO/IEC 27001/27002/27005).

JERARQUIA DOCUMENTAL ISO — CRITICO PARA EL ANALISIS:
Los documentos del SGSI tienen niveles jerarquicos con responsabilidades y alcance distintos:

  Nivel 1 — POLITICA: Define la intencion y compromiso organizativo. Alto nivel, sin detalles tecnicos.
    Ejemplos: "Politica de Seguridad de la Informacion", "Politica de Acceso", "Politica de Criptografia"
    Madurez maxima que puede aportar un control: 2/5

  Nivel 2 — NORMA/ESTANDAR: Define las reglas de obligado cumplimiento para un area especifica.
    Ejemplos: "Norma de Contrasenas", "Estandar de Clasificacion de la Informacion"
    Madurez maxima: 3/5

  Nivel 3 — PROCEDIMIENTO: Pasos detallados para ejecutar un proceso en una solucion concreta.
    Ejemplos: "Procedimiento de Gestion de Incidentes", "Procedimiento de Copias de Seguridad"
    Madurez maxima: 4/5

  Nivel 4 — INSTRUCCION TECNICA: Configuraciones exactas para un sistema especifico.
    Ejemplos: "Guia de Hardening Windows Server", "Instruccion de Configuracion de Firewall"
    Madurez maxima: 5/5

PRINCIPIO FUNDAMENTAL — ALCANCE ESPECIFICO:
Cada documento aborda un AREA TEMATICA concreta. Solo incluye controles ISO 27002:2022
que el documento aborda directamente segun su tema principal.
  - Una politica de contrasenas cubre: 5.17, 8.5 — NO cubre 11.1 (seguridad fisica)
  - Un procedimiento de backup cubre: 8.13 — NO cubre controles de autenticacion
  - Una guia de hardening de servidores cubre: 8.8, 8.9 — NO cubre controles de RRHH
Prefiere 3-8 controles muy relevantes a 20 vagamente relacionados.

ESCALA CMM:
  1 = Inicial/ad-hoc — practica informal, sin documentacion
  2 = Basico/documentado — politica que lo respalda
  3 = Definido/aplicado — norma o proceso definido
  4 = Gestionado/medido — procedimiento especifico con evidencia de aplicacion
  5 = Optimizado/continuo — instruccion tecnica + metricas + mejora continua

Devuelve SOLO este JSON valido (sin markdown, sin texto antes ni despues):

{
  "document_level": <1|2|3|4>,
  "document_level_label": "<Politica|Norma|Procedimiento|Instruccion Tecnica>",
  "document_category": "<architecture|normative|policies|assets_inventory|risk_assessments|critical_suppliers|incidents_lessons|other>",
  "is_policy": <true|false>,
  "policy": {
    "title": "<titulo del documento>",
    "category": "<categoria, ej: Acceso, Criptografia, Backup, Incidentes, Continuidad...>",
    "version": "<version o '1.0'>",
    "scope": "<alcance, max 200 palabras>",
    "content": "<resumen del contenido, max 400 palabras>",
    "review_date": "<YYYY-MM-DD o null>",
    "review_cycle_months": <entero>,
    "iso_clauses": ["<clausula ISO 27001>", ...]
  },
  "controls_covered": [
    {
      "code": "<codigo ISO 27002:2022, ej: 5.17>",
      "name": "<nombre del control>",
      "coverage": "<full|partial>",
      "maturity_current": <entero — RESPETA EL MAXIMO: Nivel1->max2, Nivel2->max3, Nivel3->max4, Nivel4->max5>,
      "maturity_rationale": "<Por que este documento en su nivel aporta exactamente esta madurez al control. Que aspectos cubre y que le falta para subir de nivel.>",
      "gap_to_5": "<Que documentacion adicional se necesita para llegar a nivel 5: que nivel jerarquico falta (norma, procedimiento, instruccion tecnica), que contenido especifico, que evidencias o metricas.>",
      "evidence_note": "<cita o referencia especifica del documento que respalda este control>"
    }
  ],
  "threat_categories_addressed": ["<categoria ISO 27005 Annex C>", ...],
  "overall_summary": "<resumen ejecutivo del documento y su aportacion al SGSI, max 200 palabras>"
}

REGLAS CRITICAS:
- Devuelve SOLO el JSON valido. Sin texto ni markdown antes ni despues.
- document_level: clasifica el documento honestamente segun su nivel real en la jerarquia.
- document_category: clasifica en UNA categoria:
    architecture, normative, policies, assets_inventory, risk_assessments, critical_suppliers, incidents_lessons, other
- controls_covered: SOLO controles directamente relacionados con el TEMA PRINCIPAL del documento.
- maturity_current NUNCA puede superar: Nivel1->max2, Nivel2->max3, Nivel3->max4, Nivel4->max5.
- gap_to_5: explica especificamente que niveles documentales faltan para completar la cadena hasta nivel 5.
- is_policy=true SOLO si es una politica de seguridad interna de la organizacion.
- Si is_policy=false, policy puede ser null.
- review_date: extraer si aparece en el documento, null si no.
- review_cycle_months: 12 por defecto si no se especifica.
"""


# ---------- Helpers ----------

def _get_api_key(db: Session, organization_id: int | None) -> str | None:
    """Obtiene la API key del agente IA para la organizacion dada."""
    cfg = db.query(AiConfig).filter_by(organization_id=organization_id).first()
    if cfg and cfg.api_key_encrypted:
        try:
            from cryptography.fernet import Fernet
            from app.services.document_service import _fernet_key
            return Fernet(_fernet_key()).decrypt(cfg.api_key_encrypted.encode()).decode()
        except Exception:
            pass
    # Fallback: variable de entorno global
    from app.config import settings
    return settings.anthropic_api_key or None


def _get_model(db: Session, organization_id: int | None) -> str:
    cfg = db.query(AiConfig).filter_by(organization_id=organization_id).first()
    return cfg.model if cfg and cfg.model else "claude-opus-4-6"


def _org_owner(db: Session, organization_id: int | None) -> int | None:
    """Devuelve el id del primer usuario activo de la org (para asignar ownership)."""
    user = db.query(User).filter_by(
        organization_id=organization_id, is_active=True
    ).order_by(User.id).first()
    return user.id if user else None


def _strip_fence(raw: str) -> str:
    """Elimina code fences Markdown si el modelo las anade."""
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```", 2)
        inner = parts[1] if len(parts) > 1 else raw
        if inner.startswith("json"):
            inner = inner[4:]
        raw = inner.rsplit("```", 1)[0].strip()
    return raw


# ---------- Punto de entrada ----------

def analyze_document_for_isms(db: Session, doc_id: int) -> None:
    """Analiza el documento y aplica los resultados al SGSI.

    Se ejecuta en background; no lanza excepciones al llamador.
    """
    doc = db.get(AiDocument, doc_id)
    if not doc or doc.status != AiDocumentStatus.INDEXED:
        return

    doc.isms_status = "analysing"
    db.commit()

    try:
        api_key = _get_api_key(db, doc.organization_id)
        if not api_key:
            doc.isms_status = "skipped"
            doc.isms_summary = {"reason": "No hay API key configurada para el agente IA"}
            db.commit()
            return

        # Recopilar hasta 25 chunks (~14 000 chars)
        chunks = sorted(doc.chunks, key=lambda c: c.chunk_index)[:25]
        if not chunks:
            doc.isms_status = "skipped"
            doc.isms_summary = {"reason": "Documento sin contenido indexado"}
            db.commit()
            return

        text_sample = "\n\n".join(c.content for c in chunks)[:14000]

        # Inyectar frameworks activos en el prompt para mejorar inferencia
        ctx = db.query(RiskContext).filter(
            RiskContext.organization_id == doc.organization_id
        ).first()
        active_frameworks = (ctx.active_frameworks or []) if ctx else []
        fw_hint = ""
        if active_frameworks:
            fw_names = {
                "iso27001": "ISO 27001:2022", "gdpr": "GDPR", "nis2": "NIS2",
                "hipaa": "HIPAA", "nist_csf": "NIST CSF 2.0", "soc2": "SOC2",
                "ens": "ENS (Esquema Nacional de Seguridad)",
            }
            names = [fw_names.get(f, f.upper()) for f in active_frameworks]
            fw_hint = (
                f"\n\nIMPORTANTE: La organización tiene activos los frameworks: {', '.join(names)}. "
                f"Al identificar controls_covered, sé especialmente minucioso con los controles "
                f"ISO 27002 que sean relevantes para estos frameworks."
            )

        # Llamar al agente IA
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        model = _get_model(db, doc.organization_id)

        with client.messages.stream(
            model=model,
            max_tokens=64000,
            system=_ISMS_SYSTEM_PROMPT + fw_hint,
            messages=[{
                "role": "user",
                "content": f"Nombre del documento: {doc.original_name}\n\nContenido:\n{text_sample}",
            }],
        ) as stream:
            message = stream.get_final_message()
        raw_json = _strip_fence(message.content[0].text)

        analysis = json.loads(raw_json)
        owner_id = _org_owner(db, doc.organization_id)

        result = {
            "policy_id": None,
            "controls_updated": 0,
            "tasks_created": 0,
            "summary": analysis.get("overall_summary", ""),
        }

        # Nivel jerarquico del documento (1=Politica, 2=Norma, 3=Procedimiento, 4=Instruccion)
        doc_level = max(1, min(4, int(analysis.get("document_level") or 1)))
        result["document_level"] = doc_level
        result["document_level_label"] = analysis.get("document_level_label", "Politica")

        # Controles que el documento tiene intencion de cubrir
        controls = analysis.get("controls_covered") or []
        intended = [c.get("code") for c in controls if c.get("code")]

        superseded_doc_id = None
        if analysis.get("is_policy") and analysis.get("policy"):
            try:
                result["policy_id"], superseded_doc_id = _create_or_update_policy(
                    db, doc, analysis["policy"], owner_id,
                    document_level=doc_level,
                    intended_controls=intended or None,
                )
                if superseded_doc_id:
                    result["superseded_document_id"] = superseded_doc_id
            except Exception as _pe:
                logger.warning("Policy creation failed doc=%d: %s", doc_id, _pe)

        if controls:
            try:
                result["controls_updated"] = _update_controls(
                    db, doc, controls, owner_id,
                    obsolete_doc_id=superseded_doc_id,
                    doc_level=doc_level,
                )
            except Exception as _ce2:
                logger.warning("Controls update failed doc=%d: %s", doc_id, _ce2)

            # Inferencia automatica de compliance desde controles cubiertos
            try:
                from app.services.evidence_inference_service import infer_compliance_from_document
                inference = infer_compliance_from_document(db, doc, controls, doc.organization_id)
                result["compliance_requirements_updated"] = inference.get("requirements_updated", 0)
                result["compliance_evidence_created"] = inference.get("evidence_created", 0)
                result["frameworks_updated"] = inference.get("frameworks_affected", [])
                logger.info(
                    "Evidence inference doc=%d: %d reqs, %d evidencias",
                    doc_id, inference.get("requirements_updated", 0), inference.get("evidence_created", 0)
                )
            except Exception as _ei:
                logger.warning("Evidence inference failed doc=%d: %s", doc_id, _ei)
                result["compliance_requirements_updated"] = 0

        threat_cats = analysis.get("threat_categories_addressed") or []
        if threat_cats:
            try:
                result["tasks_created"] = _create_treatment_tasks(
                    db, doc, threat_cats, owner_id
                )
            except Exception as _te:
                logger.warning("Tasks creation failed doc=%d: %s", doc_id, _te)

        # Si el documento es de categoria risk_assessments, intentar extraer CVEs/vulnerabilidades
        if doc.category and doc.category.value == "risk_assessments":
            try:
                _extract_and_link_csv_vulns(db, doc, text_sample)
            except Exception as _e:
                logger.warning("CSV vuln extraction failed doc=%d: %s", doc_id, _e)

        # Vincular el documento a los activos mencionados explicitamente en su texto
        try:
            linked_asset_ids = _link_document_to_assets(db, doc, text_sample)
            result["linked_assets"] = linked_asset_ids
        except Exception as _e:
            logger.warning("Document→asset linkage failed doc=%d: %s", doc_id, _e)
            result["linked_assets"] = []

        # Auto-categorizar documento basandose en el analisis IA
        inferred_cat = _infer_category(analysis, doc.original_name)
        from app.models import AiDocumentCategory as _AiCat
        current_is_other = (doc.category is None or doc.category == _AiCat.OTHER)
        if inferred_cat is not None and (inferred_cat != doc.category or current_is_other):
            doc.category = inferred_cat
            doc.auto_categorized = True
            doc.detected_category = inferred_cat.value
            result["auto_categorized"] = True
            result["detected_category"] = inferred_cat.value
            logger.info("ISMS auto-cat doc=%d: %s -> %s", doc_id,
                        doc.category.value if doc.category else "none", inferred_cat.value)
        else:
            result["auto_categorized"] = False
            result["detected_category"] = doc.category.value if doc.category else None

        doc.isms_status = "analysed"
        doc.isms_summary = result
        db.commit()   # commit del status — separado del call_log para no mezclar fallos
        logger.info(
            "ISMS analysis OK doc=%d policy=%s controls=%d tasks=%d auto_cat=%s",
            doc_id, result["policy_id"], result["controls_updated"], result["tasks_created"],
            result.get("detected_category", "-"),
        )

        # Registrar uso de tokens (no critico — fallo aqui no debe afectar el status)
        try:
            call_log = AiCallLog(
                organization_id=doc.organization_id,
                call_type="isms_analysis",
                prompt_tokens=message.usage.input_tokens,
                completion_tokens=message.usage.output_tokens,
                model=model,
                anonymized=False,
                response_summary=f"ISMS analysis for doc {doc_id}: {doc.original_name[:60]}",
            )
            db.add(call_log)
            db.commit()
        except Exception as _cl:
            logger.warning("Call log failed doc=%d: %s", doc_id, _cl)
            try:
                db.rollback()
            except Exception:
                pass

        # Mapear categoria del documento a requisitos de compliance (v3.0)
        try:
            _update_compliance_from_doc_category(db, doc, doc.organization_id)
        except Exception as _ce:
            logger.warning("Doc-compliance mapping failed doc=%d: %s", doc_id, _ce)

        # Nota: el re-análisis automático de activos se desactivó para evitar
        # consumo masivo de tokens de IA. Usar el botón "Analizar con IA" manual.

        # ── Auto-detección de documentos BCP/DRP ─────────────────────────────
        try:
            from app.services.bcp_service import (detect_bcp_document,
                                                   suggest_plan_type_from_doc,
                                                   next_plan_code)
            from app.models import BCPPlan as _BCPPlan
            _org_id = doc.organization_id
            if detect_bcp_document(doc.original_name or "", analysis.get("summary", "")):
                already = db.query(_BCPPlan).filter_by(
                    organization_id=_org_id, document_id=doc.id).first()
                if not already:
                    pt = suggest_plan_type_from_doc(doc.original_name or "",
                                                    analysis.get("summary", ""))
                    plan = _BCPPlan(
                        organization_id=_org_id,
                        code=next_plan_code(db, _org_id, pt),
                        plan_type=pt,
                        name=f"[Auto] {doc.original_name}",
                        status="draft",
                        content_summary=(analysis.get("summary") or "")[:500],
                        document_id=doc.id,
                    )
                    # Auto-detectar localización por nombre en el documento
                    try:
                        from app.models import BCMLocation
                        locs = db.query(BCMLocation).filter_by(
                            organization_id=_org_id, is_active=True).all()
                        doc_text = (doc.original_name or "").lower()
                        for loc in locs:
                            if loc.name.lower() in doc_text or (loc.code or "").lower() in doc_text:
                                plan.location_id = loc.id
                                break
                    except Exception:
                        pass
                    db.add(plan)
                    db.commit()
                    logger.info("BCP plan auto-created from ISMS doc %d: %s",
                                doc.id, doc.original_name)
                    # Revision semantica IA del contenido — ISO 22301 cl. 8.4.
                    # Ya estamos en un background task (analyze_document_for_isms
                    # se invoca desde _run_isms_analysis_bg), asi que se ejecuta
                    # en la misma sesion sin bloquear ninguna respuesta HTTP.
                    try:
                        from app.services.bcm_content_reviewer import review_plan_content
                        plan.ai_content_review = review_plan_content(db, plan)
                        db.commit()
                    except Exception as _re:
                        logger.debug("BCM content review skipped for plan %d: %s", plan.id, _re)
        except Exception as _e:
            logger.debug("BCP auto-detect skipped: %s", _e)

    except Exception as exc:
        logger.error("ISMS analysis failed doc=%d: %s", doc_id, exc)
        err_str = str(exc)
        is_credit = (
            "credit balance" in err_str.lower()
            or "insufficient_balance" in err_str.lower()
            or "billing" in err_str.lower()
            or "402" in err_str
        )
        err_msg = (
            "Sin creditos Anthropic. Recarga en console.anthropic.com/settings/billing"
            if is_credit else err_str[:500]
        )
        try:
            doc.isms_status = "error"
            doc.isms_summary = {"error": err_msg}
            db.commit()
        except Exception:
            pass


# ---------- Mapeo categoria de documento → requisitos compliance ----------

# Usa los valores reales del enum AiDocumentCategory del modelo
_DOC_CATEGORY_COMPLIANCE_MAP: dict[str, list[tuple[str, str]]] = {
    "policies": [
        ("iso27001", "A.5.1"),
        ("iso27001", "5.2"),
    ],
    "critical_suppliers": [
        ("iso27001", "A.5.19"),
        ("iso27001", "A.5.20"),
        ("nis2", "Art.21.2c"),
    ],
    "incidents_lessons": [
        ("iso27001", "A.5.24"),
        ("nis2", "Art.21.2a"),
    ],
    "risk_assessments": [
        ("iso27001", "6.1.2"),
        ("iso27001", "8.2"),
        ("nist_csf", "ID.RA"),
    ],
}


def _update_compliance_from_doc_category(db: Session, doc, org_id: int) -> None:
    """Actualiza ComplianceFrameworkStatus cuando se analiza un documento de categoria conocida.

    Incrementa a PARTIAL (30%) los requisitos que mapean a la categoria del documento,
    siempre que el estado actual sea PLANNED.
    """
    from app.models import ComplianceFrameworkStatus, ComplianceRequirementStatus
    cat = doc.category.value if doc.category else None
    mappings = _DOC_CATEGORY_COMPLIANCE_MAP.get(cat, [])
    if not mappings:
        return

    changed = False
    for framework_code, req_id in mappings:
        existing = db.query(ComplianceFrameworkStatus).filter_by(
            organization_id=org_id,
            framework_code=framework_code,
            requirement_id=req_id,
        ).first()
        if existing and existing.status == ComplianceRequirementStatus.PLANNED:
            existing.status = ComplianceRequirementStatus.PARTIAL
            existing.completion_pct = max(existing.completion_pct or 0, 30)
            existing.last_reviewed_at = datetime.now(timezone.utc)
            changed = True

    if changed:
        db.commit()
        logger.info(
            "Doc-compliance mapping: doc=%d cat=%s → %d requisitos actualizados",
            doc.id, cat, len(mappings),
        )


# ---------- Re-analisis de activos en cadena ----------

def _trigger_assets_reanalysis(org_id: int) -> None:
    """Lanza re-analisis de todos los activos de la org en un hilo daemon separado.

    Se llama despues de actualizar controles para que el riesgo residual refleje
    los nuevos controles aplicados sin bloquear el flujo principal de ISMS.
    """
    from app.database import SessionLocal

    def _worker():
        _db = SessionLocal()
        try:
            from app.services.asset_risk_analysis_service import analyze_all_org_assets
            analyze_all_org_assets(_db, org_id)
        except Exception as _exc:
            logger.warning(
                "Asset re-analysis after ISMS failed org=%d: %s", org_id, _exc
            )
        finally:
            _db.close()

    # A5: usar pool compartido en lugar de thread por documento
    _ISMS_EXECUTOR.submit(_worker)
    logger.info("Triggered asset re-analysis for org=%d after controls update", org_id)

    # Sincronizar compliance inmediatamente al actualizar controles
    def _compliance_worker():
        _db = SessionLocal()
        try:
            from app.services.compliance_service import auto_update_compliance_from_controls
            updated = auto_update_compliance_from_controls(_db, org_id)
            if updated:
                logger.info("Compliance auto-synced for org=%d: %d reqs updated", org_id, updated)
        except Exception as _exc:
            logger.debug("Compliance sync after ISMS failed: %s", _exc)
        finally:
            _db.close()

    _ISMS_EXECUTOR.submit(_compliance_worker)


# ---------- Creacion/actualizacion de politica ----------

def _next_policy_code(db: Session, org_id: int | None) -> str:
    last = (
        db.query(Policy)
        .filter(Policy.organization_id == org_id, Policy.code.like("POL-%"))
        .order_by(Policy.id.desc())
        .first()
    )
    num = 1
    if last:
        try:
            num = int(last.code.split("-")[1]) + 1
        except (ValueError, IndexError):
            pass
    code = f"POL-{num:04d}"
    while db.query(Policy).filter_by(code=code).first():
        num += 1
        code = f"POL-{num:04d}"
    return code


def _bump_policy_version(ver: str | None) -> str:
    try:
        major = int(str(ver or "1.0").split(".")[0])
    except ValueError:
        major = 1
    return f"{major + 1}.0"


def _create_or_update_policy(
    db: Session, doc: AiDocument, pol_data: dict, owner_id: int | None,
    document_level: int = 1, intended_controls: list | None = None,
) -> tuple[int | None, int | None]:
    """Crea o actualiza la Policy vinculada a este documento.

    Devuelve (policy_id, superseded_document_id). El segundo valor solo es
    distinto de None cuando este documento reemplaza a una version anterior
    de la misma politica (mismo titulo, documento distinto) — se usa para que
    la propagacion a controles sepa que evidencia antigua debe descartarse.
    """
    existing = db.query(Policy).filter_by(source_document_id=doc.id).first()

    # Calcular fecha de revision
    review_date = None
    if pol_data.get("review_date"):
        try:
            review_date = datetime.fromisoformat(pol_data["review_date"])
        except ValueError:
            pass
    cycle_months = int(pol_data.get("review_cycle_months") or 12)
    if review_date is None:
        review_date = datetime.now(timezone.utc) + timedelta(days=cycle_months * 30)

    if existing:
        existing.title = pol_data.get("title") or existing.title
        existing.version = pol_data.get("version") or existing.version or "1.0"
        existing.category = pol_data.get("category") or existing.category
        existing.scope = pol_data.get("scope") or existing.scope
        existing.content = pol_data.get("content") or existing.content
        existing.iso_clauses = pol_data.get("iso_clauses") or existing.iso_clauses
        existing.review_date = review_date
        existing.review_cycle_months = cycle_months
        existing.document_level = document_level
        if intended_controls:
            existing.intended_controls = intended_controls
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        return existing.id, None

    title = (pol_data.get("title") or doc.original_name or "").strip()

    # Misma politica, version nueva subida como archivo distinto: se detecta
    # por titulo igual (case-insensitive) dentro de la misma organizacion,
    # excluyendo versiones ya obsoletas. Si se encuentra, se encadena con
    # previous_version_id y la version anterior pasa a obsoleta — igual que
    # el flujo manual de "Nueva version", pero automatico porque este es un
    # pipeline desatendido en background.
    superseded = None
    if title:
        superseded = (
            db.query(Policy)
            .filter(
                Policy.organization_id == doc.organization_id,
                Policy.status != PolicyStatus.OBSOLETE,
                Policy.source_document_id != doc.id,
            )
            .filter(func.lower(Policy.title) == title.lower())
            .order_by(Policy.id.desc())
            .first()
        )

    if superseded:
        new_status = (
            superseded.status
            if superseded.status in (PolicyStatus.APPROVED, PolicyStatus.PUBLISHED)
            else PolicyStatus.DRAFT
        )
        pol = Policy(
            organization_id=doc.organization_id,
            code=_next_policy_code(db, doc.organization_id),
            title=title or superseded.title,
            version=pol_data.get("version") or _bump_policy_version(superseded.version),
            category=pol_data.get("category") or superseded.category,
            status=new_status,
            scope=pol_data.get("scope") or superseded.scope,
            content=pol_data.get("content") or superseded.content,
            iso_clauses=pol_data.get("iso_clauses") or superseded.iso_clauses,
            review_date=review_date,
            review_cycle_months=cycle_months,
            owner_id=owner_id,
            source_document_id=doc.id,
            previous_version_id=superseded.id,
            document_level=document_level,
            intended_controls=intended_controls,
        )
        db.add(pol)
        superseded_doc_id = superseded.source_document_id
        superseded.status = PolicyStatus.OBSOLETE
        db.commit()
        db.refresh(pol)
        logger.info(
            "Policy auto-superseded: old=%d (%s) -> new=%d (doc=%d)",
            superseded.id, superseded.code, pol.id, doc.id,
        )
        return pol.id, superseded_doc_id

    code = _next_policy_code(db, doc.organization_id)
    pol = Policy(
        organization_id=doc.organization_id,
        code=code,
        title=title or doc.original_name,
        version=pol_data.get("version") or "1.0",
        category=pol_data.get("category") or "General",
        status=PolicyStatus.DRAFT,
        scope=pol_data.get("scope") or "",
        content=pol_data.get("content") or "",
        iso_clauses=pol_data.get("iso_clauses") or [],
        review_date=review_date,
        review_cycle_months=cycle_months,
        owner_id=owner_id,
        source_document_id=doc.id,
        document_level=document_level,
        intended_controls=intended_controls,
    )
    db.add(pol)
    db.commit()
    db.refresh(pol)
    return pol.id, None


# ---------- Actualizacion de controles ----------

_STATUS_RANK = {
    ControlStatus.NOT_IMPLEMENTED: 0,
    ControlStatus.PLANNED: 1,
    ControlStatus.PARTIAL: 2,
    ControlStatus.IMPLEMENTED: 3,
}

# Madurez maxima que puede aportar un documento segun su nivel jerarquico
_LEVEL_MAX_MATURITY: dict[int, int] = {1: 2, 2: 3, 3: 4, 4: 5}


def _recalculate_aggregate_maturity(refs: list) -> int | None:
    """Calcula la madurez agregada de un control a partir de todas sus referencias documentales.

    Cada documento contribuye con su 'level_maturity' (madurez acotada por su nivel jerarquico).
    La madurez del control = max de todas las contribuciones con datos de nivel.
    Devuelve None si ningun ref tiene datos de nivel (legacy), para no sobreescribir.
    """
    leveled = [r for r in refs if "level_maturity" in r]
    if not leveled:
        return None
    return max(r["level_maturity"] for r in leveled)


def _update_controls(
    db: Session, doc: AiDocument, controls_covered: list, owner_id: int | None,
    obsolete_doc_id: int | None = None,
    doc_level: int = 1,
) -> int:
    """Actualiza ControlImplementation para los controles cubiertos por el documento.

    doc_level: nivel jerarquico del documento (1=Politica, 2=Norma, 3=Procedimiento, 4=Instruccion).
    La madurez maxima que puede aportar un documento esta limitada por su nivel jerarquico:
    Nivel1->max2, Nivel2->max3, Nivel3->max4, Nivel4->max5.
    La madurez final del control se recalcula como el maximo de todas las contribuciones.
    """
    updated = 0
    changed_impl_ids: list[int] = []
    old_doc_url = f"/api/ai/documents/{obsolete_doc_id}" if obsolete_doc_id else None
    doc_url = f"/api/ai/documents/{doc.id}"
    max_for_level = _LEVEL_MAX_MATURITY.get(doc_level, 2)

    for ctrl_data in controls_covered:
        code = (ctrl_data.get("code") or "").strip()
        if not code:
            continue

        control = db.query(Control).filter_by(code=code).first()
        if not control:
            # Intentar sin prefijo 'A.' (ej: "A.5.1" -> "5.1")
            code_alt = code.lstrip("A.").strip()
            control = db.query(Control).filter_by(code=code_alt).first()
        if not control:
            logger.debug("Control no encontrado en catalogo: %s", code)
            continue

        coverage = ctrl_data.get("coverage", "partial")
        note = ctrl_data.get("evidence_note", "")
        # Nivel de madurez: usar el valor del modelo; acotarlo al maximo del nivel del documento
        raw_maturity = ctrl_data.get("maturity_current") or (3 if coverage == "full" else 2)
        new_maturity = max(1, min(max_for_level, int(raw_maturity)))
        new_status = ControlStatus.IMPLEMENTED if new_maturity >= 3 else ControlStatus.PARTIAL

        # Gap analysis: por que no llega al 5 y que falta
        gap_note_parts = []
        if ctrl_data.get("maturity_rationale"):
            gap_note_parts.append(f"Nivel actual ({new_maturity}/5): {ctrl_data['maturity_rationale']}")
        if ctrl_data.get("gap_to_5"):
            gap_note_parts.append(f"Para llegar a nivel 5: {ctrl_data['gap_to_5']}")
        gap_note = "\n\n".join(gap_note_parts)

        doc_ref = {
            "title": f"[Auto] {doc.original_name}",
            "url": doc_url,
            "note": note[:200] if note else "",
            "document_level": doc_level,
            "level_maturity": new_maturity,
        }

        impl = db.query(ControlImplementation).filter_by(
            organization_id=doc.organization_id,
            control_id=control.id,
        ).first()

        if impl:
            refs = list(impl.evidence_refs or [])
            # Descartar evidencia de la version anterior de este mismo documento
            if old_doc_url:
                refs = [r for r in refs if r.get("url") != old_doc_url]
            # Reemplazar o añadir la referencia de este documento (idempotente por URL)
            refs = [r for r in refs if r.get("url") != doc_url]
            refs.append(doc_ref)
            impl.evidence_refs = refs

            # Recalcular madurez agregada: max de todas las contribuciones con nivel
            aggregate = _recalculate_aggregate_maturity(refs)
            if aggregate is not None:
                impl.maturity = aggregate
                impl.status = ControlStatus.IMPLEMENTED if aggregate >= 3 else ControlStatus.PARTIAL
            elif old_doc_url:
                # Version nueva sin refs legacy: aplicar directamente
                impl.maturity = new_maturity
                impl.status = new_status
            else:
                # Refs legacy sin datos de nivel: solo mejorar, nunca degradar
                if new_maturity > (impl.maturity or 0):
                    impl.maturity = new_maturity
                if _STATUS_RANK.get(new_status, 0) > _STATUS_RANK.get(impl.status, 0):
                    impl.status = new_status

            if note and not impl.evidence:
                impl.evidence = note
            # Actualizar gap analysis con la info del documento mas reciente de mayor nivel
            if gap_note:
                existing_level = 0
                for r in refs:
                    if r.get("url") != doc_url and r.get("document_level", 0) > existing_level:
                        existing_level = r["document_level"]
                if doc_level >= existing_level:
                    impl.notes = gap_note
        else:
            impl = ControlImplementation(
                organization_id=doc.organization_id,
                control_id=control.id,
                name=ctrl_data.get("name") or control.name,
                description=f"Identificado automaticamente desde: {doc.original_name}",
                status=new_status,
                maturity=new_maturity,
                owner_id=owner_id,
                evidence=note,
                evidence_refs=[doc_ref],
                notes=gap_note or None,
            )
            db.add(impl)

        updated += 1
        db.flush()
        if impl.id:
            changed_impl_ids.append(impl.id)

    if changed_impl_ids:
        # El residual de los riesgos vinculados se recalcula de inmediato
        # (determinista, gratis); ademas se marca el analisis IA como stale
        # para que el usuario decida si re-analizar con el boton manual.
        from app.services.risk_recalc_service import (
            mark_risks_stale_for_impls, recalc_risks_for_impls,
        )
        recalced = recalc_risks_for_impls(db, changed_impl_ids)
        stale = mark_risks_stale_for_impls(
            db, changed_impl_ids,
            f"Documento '{doc.original_name[:80]}' actualizo la madurez de "
            f"{len(changed_impl_ids)} controles",
        )
        if recalced or stale:
            logger.info(
                "ISMS doc %d: %d riesgos recalculados, %d marcados stale",
                doc.id, recalced, stale,
            )

    db.commit()
    return updated


# ---------- Creacion de tareas de tratamiento ----------

def _next_task_code(db: Session, org_id: int | None) -> str:
    last = (
        db.query(TreatmentTask)
        .filter(TreatmentTask.organization_id == org_id, TreatmentTask.code.like("TSK-%"))
        .order_by(TreatmentTask.id.desc())
        .first()
    )
    num = 1
    if last:
        try:
            num = int(last.code.split("-")[1]) + 1
        except (ValueError, IndexError):
            pass
    code = f"TSK-{num:04d}"
    while db.query(TreatmentTask).filter_by(code=code).first():
        num += 1
        code = f"TSK-{num:04d}"
    return code


def _link_document_to_assets(
    db: Session, doc: AiDocument, text_sample: str
) -> list:
    """Detecta activos de la organizacion mencionados en el texto del documento y
    registra una referencia al documento en el campo extra de cada activo coincidente.

    Devuelve la lista de IDs de activos vinculados.
    """
    if not doc.organization_id:
        return []

    assets = db.query(Asset).filter(Asset.organization_id == doc.organization_id).all()
    if not assets:
        return []

    text_lower = text_sample.lower()
    linked_ids: list = []
    doc_ref = {
        "document_id": doc.id,
        "document_name": doc.original_name,
        "linked_by": "isms_analysis",
    }

    for asset in assets:
        # Coincidencia por nombre o codigo (case-insensitive, minimo 4 chars para evitar falsos)
        name_lower = asset.name.lower()
        code_lower = asset.code.lower()
        if len(name_lower) >= 4 and name_lower in text_lower:
            matched = True
        elif len(code_lower) >= 4 and code_lower in text_lower:
            matched = True
        else:
            matched = False

        if not matched:
            continue

        # Guardar referencia en el campo extra del activo (JSON libre)
        extra = dict(asset.extra or {})
        doc_refs = extra.get("document_refs", [])
        # No duplicar referencias al mismo documento
        if not any(r.get("document_id") == doc.id for r in doc_refs):
            doc_refs.append(doc_ref)
            extra["document_refs"] = doc_refs
            asset.extra = extra
        linked_ids.append(asset.id)

    if linked_ids:
        db.commit()
        logger.info(
            "ISMS doc→asset: doc=%d linked to %d asset(s): %s",
            doc.id, len(linked_ids), linked_ids,
        )

    return linked_ids


def _extract_and_link_csv_vulns(db: Session, doc: AiDocument, text_sample: str) -> None:
    """Extrae CVEs/vulnerabilidades del texto del documento y las asocia a activos."""
    import re
    # Detectar patrones CVE
    cve_pattern = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)
    cves = list(set(cve_pattern.findall(text_sample)))
    if not cves:
        return

    # Detectar lineas con severidad (Nessus/OpenVAS style)
    severity_pattern = re.compile(
        r"(critical|high|medium|low)\s+.*?(CVE-\d{4}-\d{4,7})",
        re.IGNORECASE | re.MULTILINE
    )
    findings = []
    for m in severity_pattern.finditer(text_sample):
        findings.append({
            "severity": m.group(1).lower(),
            "cve_id": m.group(2).upper(),
            "product": "",
            "description": m.group(0)[:200],
        })
    # Si no encontramos con severidad, agregar solo los CVEs con severidad media
    if not findings:
        for cve in cves[:20]:
            findings.append({"severity": "medium", "cve_id": cve, "product": "", "description": ""})

    if findings:
        from app.services.asset_risk_analysis_service import link_csv_vulnerabilities_to_assets
        link_csv_vulnerabilities_to_assets(db, doc.organization_id, findings)


def _infer_category(
    analysis: dict, original_name: str
):
    """Infiere la categoria correcta del documento basandose en el analisis IA.

    Prioridad:
    1. Campo document_category del JSON de la IA (explícito)
    2. is_policy=true → policies
    3. Reglas por codigos de control ISO 27002
    4. Palabras clave en el nombre del fichero
    5. Palabras clave en el overall_summary generado por la IA
    Devuelve None solo si ningun signal es suficiente.
    """
    from app.models import AiDocumentCategory

    _CAT_MAP = {
        "architecture":       AiDocumentCategory.ARCHITECTURE,
        "normative":          AiDocumentCategory.NORMATIVE,
        "policies":           AiDocumentCategory.POLICIES,
        "assets_inventory":   AiDocumentCategory.ASSETS_INVENTORY,
        "risk_assessments":   AiDocumentCategory.RISK_ASSESSMENTS,
        "critical_suppliers": AiDocumentCategory.CRITICAL_SUPPLIERS,
        "incidents_lessons":  AiDocumentCategory.INCIDENTS_LESSONS,
    }

    # 1. Campo document_category explícito de la IA (señal más fiable)
    ai_category = analysis.get("document_category", "").strip().lower()
    if ai_category and ai_category != "other" and ai_category in _CAT_MAP:
        return _CAT_MAP[ai_category]

    # 2. is_policy=true → policies
    if analysis.get("is_policy"):
        return AiDocumentCategory.POLICIES

    covered = {c.get("code", "") for c in (analysis.get("controls_covered") or [])}

    # 3. Reglas por codigos de control ISO 27002
    asset_controls    = {"5.9", "5.10", "5.11", "5.12", "5.13", "5.14"}
    supplier_controls = {"5.19", "5.20", "5.21", "5.22", "5.23"}
    risk_controls     = {"5.1", "5.2", "5.3", "5.4", "6.1", "6.2"}

    if covered & asset_controls:
        return AiDocumentCategory.ASSETS_INVENTORY
    if covered & supplier_controls:
        return AiDocumentCategory.CRITICAL_SUPPLIERS
    if covered & risk_controls:
        return AiDocumentCategory.RISK_ASSESSMENTS

    # 4. Palabras clave en el nombre del fichero
    name_lower = (original_name or "").lower()
    if any(w in name_lower for w in [
        "arquitectura", "red", "network", "infraestructura",
        "topology", "diagrama", "architecture", "topologia",
    ]):
        return AiDocumentCategory.ARCHITECTURE
    if any(w in name_lower for w in [
        "normativa", "norma", "compliance", "nis2", "gdpr", "rgpd",
        "iso27", "reglamento", "directiva", "ley ", "boe",
    ]):
        return AiDocumentCategory.NORMATIVE
    if any(w in name_lower for w in [
        "incidente", "incident", "leccion", "lesson",
        "postmortem", "post-mortem", "forense",
    ]):
        return AiDocumentCategory.INCIDENTS_LESSONS
    if any(w in name_lower for w in [
        "inventario", "inventory", "activos", "assets",
        "cmdb", "hardware", "software", "catalogo",
    ]):
        return AiDocumentCategory.ASSETS_INVENTORY
    if any(w in name_lower for w in [
        "proveedor", "supplier", "vendor", "tercero",
        "contrato", "sla", "dpa",
    ]):
        return AiDocumentCategory.CRITICAL_SUPPLIERS
    if any(w in name_lower for w in [
        "riesgo", "risk", "analisis", "evaluacion",
        "assessment", "amenaza", "vulnerabilidad",
    ]):
        return AiDocumentCategory.RISK_ASSESSMENTS
    if any(w in name_lower for w in [
        "politica", "policy", "procedimiento", "procedure",
        "instruccion", "manual", "guia ",
    ]):
        return AiDocumentCategory.POLICIES

    # 5. Palabras clave en el resumen generado por la IA (fallback cuando nombre no da pistas)
    summary_lower = (analysis.get("overall_summary") or "").lower()
    if summary_lower:
        if any(w in summary_lower for w in [
            "politica de seguridad", "security policy", "procedimiento de seguridad",
            "instruccion de trabajo", "politica interna", "control de acceso",
        ]):
            return AiDocumentCategory.POLICIES
        if any(w in summary_lower for w in [
            "arquitectura", "topologia de red", "diagrama de red", "infraestructura",
            "architecture", "network topology",
        ]):
            return AiDocumentCategory.ARCHITECTURE
        if any(w in summary_lower for w in [
            "normativa", "reglamento", "nis2", "gdpr", "rgpd", "iso 27",
            "cumplimiento normativo", "compliance", "directiva", "legislacion",
        ]):
            return AiDocumentCategory.NORMATIVE
        if any(w in summary_lower for w in [
            "incidente de seguridad", "gestion de incidentes", "respuesta a incidentes",
            "post-mortem", "leccion aprendida", "registro de incidentes",
        ]):
            return AiDocumentCategory.INCIDENTS_LESSONS
        if any(w in summary_lower for w in [
            "inventario de activos", "catalogo de activos", "gestion de activos",
            "cmdb", "asset inventory", "listado de sistemas",
        ]):
            return AiDocumentCategory.ASSETS_INVENTORY
        if any(w in summary_lower for w in [
            "proveedor", "tercero", "acuerdo de nivel de servicio", "sla",
            "contrato de servicio", "dpa", "supplier", "vendor",
        ]):
            return AiDocumentCategory.CRITICAL_SUPPLIERS
        if any(w in summary_lower for w in [
            "analisis de riesgo", "evaluacion de riesgo", "risk assessment",
            "dpia", "evaluacion de impacto", "amenaza", "vulnerabilidad",
            "gestion del riesgo",
        ]):
            return AiDocumentCategory.RISK_ASSESSMENTS

    return None  # Sin certeza suficiente: no cambiar la categoria actual


def _create_treatment_tasks(
    db: Session, doc: AiDocument, threat_cats: list, owner_id: int | None
) -> int:
    """Crea TreatmentTask para riesgos activos cuya amenaza cae en las categorias identificadas."""
    if not threat_cats:
        return 0

    active_risks = (
        db.query(Risk)
        .filter(
            Risk.organization_id == doc.organization_id,
            Risk.status.in_([RiskStatus.IDENTIFIED, RiskStatus.ASSESSED]),
        )
        .all()
    )

    threat_cats_lower = [c.lower() for c in threat_cats]
    created = 0

    for risk in active_risks:
        threat = risk.threat
        if not threat:
            continue
        threat_cat = (threat.category or "").lower()
        match = any(
            tc in threat_cat or threat_cat in tc
            for tc in threat_cats_lower
        )
        if not match:
            continue

        # No crear tarea duplicada para el mismo riesgo + documento
        dup = db.query(TreatmentTask).filter(
            TreatmentTask.organization_id == doc.organization_id,
            TreatmentTask.risk_id == risk.id,
            TreatmentTask.description.like(f"%{doc.original_name[:60]}%"),
        ).first()
        if dup:
            continue

        # Prioridad segun nivel de riesgo residual
        lvl = risk.residual_level or 0
        if lvl >= 6:
            priority = TaskPriority.CRITICAL
        elif lvl >= 4:
            priority = TaskPriority.HIGH
        elif lvl >= 2:
            priority = TaskPriority.MEDIUM
        else:
            priority = TaskPriority.LOW

        asset_name = risk.asset.name if risk.asset else risk.code
        code = _next_task_code(db, doc.organization_id)

        task = TreatmentTask(
            organization_id=doc.organization_id,
            code=code,
            title=f"Tratar {asset_name} — {threat.name}",
            description=(
                f"Tarea generada automaticamente al analizar el documento: {doc.original_name}.\n"
                f"El documento aborda amenazas de tipo '{threat.category}' que afectan a este riesgo.\n"
                f"Revisar e implementar los controles identificados en el documento."
            ),
            risk_id=risk.id,
            status=TaskStatus.PENDING,
            priority=priority,
            due_date=datetime.now(timezone.utc) + timedelta(days=90),
            assigned_to_id=owner_id,
            created_by_id=owner_id,
        )
        db.add(task)
        created += 1

    if created > 0:
        db.commit()
    return created
