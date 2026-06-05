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

_ISMS_SYSTEM_PROMPT = """Eres un experto en seguridad de la informacion (ISO/IEC 27001/27002/27005).
Analiza el siguiente fragmento de documento y devuelve UNICAMENTE un objeto JSON valido con esta estructura:

{
  "document_category": "<una de: architecture | normative | policies | assets_inventory | risk_assessments | critical_suppliers | incidents_lessons | other>",
  "is_policy": <true | false>,
  "policy": {
    "title": "<titulo del documento>",
    "category": "<categoria, ej: Seguridad fisica, Uso aceptable, Gestion de incidentes...>",
    "version": "<version, ej: '1.0'>",
    "scope": "<alcance resumido, max 200 palabras>",
    "content": "<resumen del contenido, max 400 palabras>",
    "review_date": "<fecha ISO YYYY-MM-DD o null>",
    "review_cycle_months": <entero, ej: 12>,
    "iso_clauses": ["<clausula ISO 27001>", ...]
  },
  "controls_covered": [
    {
      "code": "<codigo ISO 27002:2022, ej: 5.1>",
      "name": "<nombre del control>",
      "coverage": "<full | partial>",
      "maturity_current": <entero 1..4, nivel de madurez actual segun CMM>,
      "maturity_rationale": "<Por que el documento solo alcanza este nivel y no el 5. Ser especifico: que aspectos cubre, que le falta.>",
      "gap_to_5": "<Lista concreta de lo que faltaria para llegar a nivel 5: procedimientos, evidencias, registros, formacion, revision periodica, metricas, etc. Max 3 acciones especificas.>",
      "evidence_note": "<nota breve de evidencia>"
    }
  ],
  "threat_categories_addressed": ["<categoria de amenaza>", ...],
  "overall_summary": "<resumen ejecutivo, max 200 palabras>"
}

REGLAS:
- Devuelve SOLO el JSON. Sin texto ni markdown antes ni despues.
- document_category: clasifica el documento en UNA de estas categorias (obligatorio, nunca null):
    * "architecture"       — diagramas de red, arquitectura de sistemas, infraestructura IT, topologia
    * "normative"          — normativas externas, reglamentos, leyes, ISO, NIS2, GDPR, ENS, compliance
    * "policies"           — politicas de seguridad internas, procedimientos, instrucciones de trabajo
    * "assets_inventory"   — inventario de activos, CMDB, listados de hardware/software/aplicaciones
    * "risk_assessments"   — analisis de riesgos, evaluaciones de amenazas, informes de vulnerabilidades, DPIA
    * "critical_suppliers" — contratos de proveedores, acuerdos SLA, evaluaciones de terceros, DPA
    * "incidents_lessons"  — informes de incidentes, post-mortems, lecciones aprendidas, registros de incidentes
    * "other"              — solo si el documento no encaja claramente en ninguna de las anteriores
- Si el documento ES una politica interna, document_category DEBE ser "policies" e is_policy=true.
- Si el documento NO es una politica de seguridad, pon is_policy=false y policy=null.
- controls_covered: SOLO controles ISO 27002:2022 que el documento cubre con confianza alta.
  Usa los codigos reales del estandar (5.1, 5.2, ... 8.34).
  NO incluyas controles que no esten claramente respaldados por el contenido del documento.
  Un documento de criptografia cubre 8.24, 8.26 etc., NO cubre controles legales ni de RRHH.
- maturity_current: escala CMM 1-5. Un documento bien redactado con procedimientos claros
  pero sin evidencias de revision ni metricas = 3. Con evidencias y KPIs = 4. Con mejora
  continua demostrada = 5. Rara vez se llega al 5 solo con un documento.
- threat_categories_addressed: categorias de amenazas ISO 27005 Annex C que el documento
  ayuda a mitigar (Physical damage, Natural events, Loss of services, Technical failures,
  Unauthorised actions, Compromise of functions, etc.).
- Si encuentras fechas de revision o vigencia en el documento, extrae review_date.
  Si no hay fecha explicita, pon null.
- review_cycle_months: ciclo de revision tipico para el tipo de documento (12 si no se indica).
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
    return cfg.model if cfg and cfg.model else "claude-opus-4-5"


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

        message = client.messages.create(
            model=model,
            max_tokens=2048,
            system=_ISMS_SYSTEM_PROMPT + fw_hint,
            messages=[{
                "role": "user",
                "content": f"Nombre del documento: {doc.original_name}\n\nContenido:\n{text_sample}",
            }],
        )
        raw_json = _strip_fence(message.content[0].text)

        # Registrar uso de tokens
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

        analysis = json.loads(raw_json)
        owner_id = _org_owner(db, doc.organization_id)

        result = {
            "policy_id": None,
            "controls_updated": 0,
            "tasks_created": 0,
            "summary": analysis.get("overall_summary", ""),
        }

        if analysis.get("is_policy") and analysis.get("policy"):
            result["policy_id"] = _create_or_update_policy(
                db, doc, analysis["policy"], owner_id
            )

        controls = analysis.get("controls_covered") or []
        if controls:
            result["controls_updated"] = _update_controls(db, doc, controls, owner_id)

            # NUEVO: Inferencia automática de compliance desde controles cubiertos
            # Un documento que cubre A.8.5 → marca automáticamente ISO27001, NIST, SOC2, ENS, HIPAA
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
            result["tasks_created"] = _create_treatment_tasks(
                db, doc, threat_cats, owner_id
            )

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

        # Auto-categorizar documento basandose en el analisis IA (v1.7.8)
        inferred_cat = _infer_category(analysis, doc.original_name)
        if inferred_cat is not None and inferred_cat != doc.category:
            doc.category = inferred_cat
            doc.auto_categorized = True
            doc.detected_category = inferred_cat.value
            result["auto_categorized"] = True
            result["detected_category"] = inferred_cat.value
            logger.info("ISMS auto-cat doc=%d: %s", doc_id, inferred_cat.value)
        else:
            result["auto_categorized"] = False
            result["detected_category"] = doc.category.value if doc.category else None

        doc.isms_status = "analysed"
        doc.isms_summary = result
        db.commit()
        logger.info(
            "ISMS analysis OK doc=%d policy=%s controls=%d tasks=%d auto_cat=%s",
            doc_id, result["policy_id"], result["controls_updated"], result["tasks_created"],
            result.get("detected_category", "-"),
        )

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
                    db.add(_BCPPlan(
                        organization_id=_org_id,
                        code=next_plan_code(db, _org_id, pt),
                        plan_type=pt,
                        name=f"[Auto] {doc.original_name}",
                        status="draft",
                        content_summary=(analysis.get("summary") or "")[:500],
                        document_id=doc.id,
                    ))
                    db.commit()
                    logger.info("BCP plan auto-created from ISMS doc %d: %s",
                                doc.id, doc.original_name)
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


def _create_or_update_policy(
    db: Session, doc: AiDocument, pol_data: dict, owner_id: int | None
) -> int | None:
    """Crea o actualiza la Policy vinculada a este documento."""
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
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        return existing.id

    code = _next_policy_code(db, doc.organization_id)
    pol = Policy(
        organization_id=doc.organization_id,
        code=code,
        title=pol_data.get("title") or doc.original_name,
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
    )
    db.add(pol)
    db.commit()
    db.refresh(pol)
    return pol.id


# ---------- Actualizacion de controles ----------

_STATUS_RANK = {
    ControlStatus.NOT_IMPLEMENTED: 0,
    ControlStatus.PLANNED: 1,
    ControlStatus.PARTIAL: 2,
    ControlStatus.IMPLEMENTED: 3,
}


def _update_controls(
    db: Session, doc: AiDocument, controls_covered: list, owner_id: int | None
) -> int:
    """Actualiza ControlImplementation para los controles cubiertos por el documento."""
    updated = 0
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
        # Nivel de madurez: usar el valor del modelo si viene; sino inferir por coverage
        new_maturity = ctrl_data.get("maturity_current") or (3 if coverage == "full" else 2)
        new_maturity = max(1, min(5, int(new_maturity)))
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
            "url": f"/api/ai/documents/{doc.id}",
            "note": note[:200] if note else "",
        }

        impl = db.query(ControlImplementation).filter_by(
            organization_id=doc.organization_id,
            control_id=control.id,
        ).first()

        if impl:
            # Solo mejorar el estado, nunca degradar
            if _STATUS_RANK.get(new_status, 0) > _STATUS_RANK.get(impl.status, 0):
                impl.status = new_status
            if new_maturity > (impl.maturity or 0):
                impl.maturity = new_maturity
            refs = list(impl.evidence_refs or [])
            if not any(r.get("title") == doc_ref["title"] for r in refs):
                refs.append(doc_ref)
                impl.evidence_refs = refs
            if note and not impl.evidence:
                impl.evidence = note
            # Actualizar gap analysis (sobreescribir siempre con la info mas reciente)
            if gap_note:
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
) -> "AiDocumentCategory | None":
    """Infiere la categoria correcta del documento basandose en el analisis IA.

    Prioridad:
    1. Campo document_category del JSON de la IA (nuevo, explícito)
    2. is_policy=true → policies
    3. Reglas por codigos de control ISO 27002
    4. Palabras clave en el nombre del fichero
    Devuelve None si no hay certeza suficiente para cambiar la categoria actual.
    """
    from app.models import AiDocumentCategory

    # 1. Usar la categoria inferida explicitamente por la IA (campo nuevo en el prompt)
    ai_category = analysis.get("document_category", "").strip().lower()
    _CAT_MAP = {
        "architecture":       AiDocumentCategory.ARCHITECTURE,
        "normative":          AiDocumentCategory.NORMATIVE,
        "policies":           AiDocumentCategory.POLICIES,
        "assets_inventory":   AiDocumentCategory.ASSETS_INVENTORY,
        "risk_assessments":   AiDocumentCategory.RISK_ASSESSMENTS,
        "critical_suppliers": AiDocumentCategory.CRITICAL_SUPPLIERS,
        "incidents_lessons":  AiDocumentCategory.INCIDENTS_LESSONS,
    }
    if ai_category and ai_category != "other" and ai_category in _CAT_MAP:
        return _CAT_MAP[ai_category]

    # 2. Si es politica de seguridad detectada → policies
    if analysis.get("is_policy"):
        return AiDocumentCategory.POLICIES

    covered = {c.get("code", "") for c in (analysis.get("controls_covered") or [])}

    # 3. Reglas por codigos de control ISO 27002
    asset_controls    = {"5.9", "5.10", "5.11", "5.12", "5.13", "5.14"}
    risk_controls     = {"5.1", "5.2", "5.3", "5.4", "6.1", "6.2"}
    supplier_controls = {"5.19", "5.20", "5.21", "5.22", "5.23"}

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
