"""IA del Plan Director (v6.3.0) — import de planes, borradores automaticos,
narrativas de avance y plan de tratamiento por riesgo.

Principio: la IA solo PROPONE estructura y candidatos; el vinculo real
riesgo<->iniciativa lo deriva siempre el motor determinista
(initiative_projection_service.auto_link_risks) despues de crear los control
targets. La IA nunca inventa un vinculo riesgo-iniciativa directamente aqui.

Toda llamada usa structured_message (tool use forzado, JSON validado por la
API) y el modelo se resuelve siempre via model_registry — nunca hardcodeado.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.services.claude_client import structured_message
from app.services.model_registry import get_model

logger = logging.getLogger(__name__)

_MAX_INITIATIVES = 30
_MAX_RISK_LINKS_PER_INITIATIVE = 15
_MAX_CATALOG_RISKS = 300
_MAX_CATALOG_CONTROLS = 120


def _api_key_and_model(db: Session, org_id: Optional[int], tier: str = "deep") -> tuple[str, str]:
    from app.models import AiConfig
    from app.routers.ai import _resolve_api_key
    cfg = db.query(AiConfig).filter(AiConfig.organization_id == org_id).first()
    api_key = _resolve_api_key(cfg)
    if not api_key:
        raise ValueError("No hay API key de Claude configurada para esta organizacion.")
    model = get_model(db, org_id, tier)
    return api_key, model


def _clamp_date(value) -> Optional[str]:
    if not value:
        return None
    try:
        datetime.strptime(value[:10], "%Y-%m-%d")
        return value[:10]
    except (ValueError, TypeError):
        return None


def _clamp_maturity(value) -> int:
    try:
        return max(0, min(5, int(value)))
    except (TypeError, ValueError):
        return 0


def controls_catalog(db: Session, org_id: Optional[int]) -> list[dict]:
    """Catalogo compacto de controles de la org (code + nombre) para el prompt."""
    from app.models import Control, ControlImplementation
    rows = (
        db.query(Control.code, Control.name)
        .join(ControlImplementation, ControlImplementation.control_id == Control.id)
        .filter(ControlImplementation.organization_id == org_id)
        .distinct()
        .limit(_MAX_CATALOG_CONTROLS)
        .all()
    )
    return [{"code": code, "name": name} for code, name in rows]


def risks_catalog(db: Session, org_id: Optional[int]) -> list[dict]:
    """Riesgos abiertos de la org, mayor residual primero (cap para el prompt)."""
    from app.models import Risk, RiskStatus
    from sqlalchemy.orm import joinedload
    risks = (
        db.query(Risk)
        .options(joinedload(Risk.asset), joinedload(Risk.threat))
        .filter(Risk.organization_id == org_id, Risk.status != RiskStatus.CLOSED)
        .order_by(Risk.residual_level.desc())
        .limit(_MAX_CATALOG_RISKS)
        .all()
    )
    return [
        {"code": r.code, "asset": r.asset.name if r.asset else "", "threat": r.threat.name if r.threat else "",
         "residual": r.residual_level or 0}
        for r in risks
    ]


def _resolve_control_targets(db: Session, org_id: Optional[int], catalog_codes: set[str],
                             control_targets: list[dict]) -> tuple[list[dict], list[str]]:
    """Convierte [{control_code, target_maturity}] en [{implementation_id, target_maturity}].

    Descarta codigos fuera del catalogo o sin implementacion en la org
    (determinista, nunca confia en lo que devuelve el LLM)."""
    from app.models import Control, ControlImplementation
    resolved = []
    skipped = []
    for ct in control_targets or []:
        code = (ct.get("control_code") or "").strip()
        if code not in catalog_codes:
            skipped.append(code)
            continue
        impl = (
            db.query(ControlImplementation)
            .join(Control, ControlImplementation.control_id == Control.id)
            .filter(ControlImplementation.organization_id == org_id, Control.code == code)
            .first()
        )
        if not impl:
            skipped.append(code)
            continue
        resolved.append({
            "implementation_id": impl.id,
            "target_maturity": max(_clamp_maturity(ct.get("target_maturity")), impl.maturity or 0),
        })
    return resolved, skipped


# ---------- a) Import de plan completo ----------

_IMPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "programs": {
            "type": "array", "maxItems": 15,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "maxLength": 255},
                    "area": {"type": ["string", "null"], "maxLength": 64},
                    "responsible_hint": {"type": ["string", "null"], "maxLength": 128},
                    "initiatives": {
                        "type": "array", "maxItems": _MAX_INITIATIVES,
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "maxLength": 255},
                                "description": {"type": ["string", "null"]},
                                "priority": {"type": ["string", "null"], "enum": ["low", "medium", "high", "critical", None]},
                                "nist_function": {"type": ["string", "null"],
                                                   "enum": ["govern", "identify", "protect", "detect", "respond", "recover", None]},
                                "start_date": {"type": ["string", "null"]},
                                "target_date": {"type": ["string", "null"]},
                                "budget": {"type": ["number", "null"]},
                                "expected_risk_reduction": {"type": ["string", "null"]},
                                "control_targets": {
                                    "type": "array", "maxItems": 10,
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "control_code": {"type": "string"},
                                            "target_maturity": {"type": "integer", "minimum": 0, "maximum": 5},
                                        },
                                        "required": ["control_code", "target_maturity"],
                                    },
                                },
                                "objectives": {
                                    "type": "array", "maxItems": 10,
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "definition": {"type": "string"},
                                            "target_date": {"type": ["string", "null"]},
                                        },
                                        "required": ["definition"],
                                    },
                                },
                            },
                            "required": ["title"],
                        },
                    },
                },
                "required": ["name", "initiatives"],
            },
        },
    },
    "required": ["programs"],
}


def parse_plan_document(db: Session, org_id: Optional[int], text: str, lang: str = "es") -> dict:
    """Estructura un plan director (texto extraido de PDF/DOCX/XLSX/TXT) en
    programas/iniciativas/objetivos + controles objetivo candidatos.

    NO vincula riesgos: eso lo hace siempre auto_link_risks tras confirmar."""
    controls = controls_catalog(db, org_id)
    api_key, model = _api_key_and_model(db, org_id, "deep")

    system = (
        "Eres un analista GRC experto en planes directores de ciberseguridad (ISO 27005, "
        "ISO 27001, NIST CSF). Extrae del documento adjunto la estructura del plan: "
        "programas, iniciativas y objetivos (OKR). Para cada iniciativa, identifica que "
        "controles del catalogo adjunto mejora (SOLO codigos que aparezcan literalmente en "
        "el catalogo, nunca inventes codigos) y estima la madurez objetivo 0-5 en base al "
        "texto. No inventes datos que no esten en el documento; deja null lo desconocido. "
        f"Responde en el idioma: {lang}."
    )
    text = text[:100_000]
    parsed, _msg = structured_message(
        api_key, model=model, max_tokens=8192, system=system,
        messages=[{
            "role": "user",
            "content": f"Catalogo de controles disponibles:\n{controls}\n\nDocumento:\n{text}",
        }],
        tool_name="registrar_plan_director",
        tool_description="Registra la estructura del plan director extraida del documento",
        input_schema=_IMPORT_SCHEMA,
        org_id=org_id, call_type="plan_import",
    )

    catalog_codes = {c["code"] for c in controls}
    programs = []
    skipped_all: list[str] = []
    for prog in (parsed.get("programs") or [])[:15]:
        initiatives = []
        for ini in (prog.get("initiatives") or [])[:_MAX_INITIATIVES]:
            targets, skipped = _resolve_control_targets(db, org_id, catalog_codes, ini.get("control_targets"))
            skipped_all.extend(skipped)
            initiatives.append({
                "title": (ini.get("title") or "")[:255],
                "description": ini.get("description"),
                "priority": ini.get("priority") if ini.get("priority") in
                            ("low", "medium", "high", "critical") else "medium",
                "nist_function": ini.get("nist_function") if ini.get("nist_function") in
                                 ("govern", "identify", "protect", "detect", "respond", "recover") else None,
                "start_date": _clamp_date(ini.get("start_date")),
                "target_date": _clamp_date(ini.get("target_date")),
                "budget": ini.get("budget"),
                "expected_risk_reduction": ini.get("expected_risk_reduction"),
                "control_targets": targets,
                "objectives": [
                    {"definition": (o.get("definition") or "")[:500],
                     "target_date": _clamp_date(o.get("target_date"))}
                    for o in (ini.get("objectives") or [])[:10] if o.get("definition")
                ],
            })
        if initiatives:
            programs.append({
                "name": (prog.get("name") or "Programa")[:255],
                "area": prog.get("area"),
                "initiatives": initiatives,
            })

    return {"programs": programs, "skipped_controls": sorted(set(skipped_all))}


# ---------- b) Borrador de iniciativa para riesgos sin cobertura ----------

_DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "maxLength": 255},
        "description": {"type": "string"},
        "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "expected_risk_reduction": {"type": "string"},
        "control_targets": {
            "type": "array", "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "control_code": {"type": "string"},
                    "target_maturity": {"type": "integer", "minimum": 0, "maximum": 5},
                    "rationale": {"type": "string", "maxLength": 300},
                },
                "required": ["control_code", "target_maturity"],
            },
        },
        "rationale": {"type": "string", "maxLength": 600},
    },
    "required": ["title", "control_targets", "rationale"],
}


def draft_initiative_for_risks(db: Session, org_id: Optional[int], risk_ids: list[int], lang: str = "es") -> dict:
    """Genera un borrador de iniciativa para un grupo de riesgos sin cobertura,
    eligiendo controles candidatos del catalogo amenaza->control existente."""
    from app.models import Risk
    from app.services.threat_knowledge import candidate_impls_for_threat

    risks = db.query(Risk).filter(Risk.id.in_(risk_ids), Risk.organization_id == org_id).all()
    if not risks:
        raise ValueError("No se encontraron riesgos validos para generar el borrador.")

    candidates_by_risk = []
    all_candidate_codes: set[str] = set()
    for r in risks:
        threat = r.threat
        if not threat or not threat.code:
            continue
        candidates = candidate_impls_for_threat(db, org_id, threat.code)[:8]
        codes = [c["code"] for c in candidates]
        all_candidate_codes.update(codes)
        candidates_by_risk.append({
            "risk_code": r.code, "asset": r.asset.name if r.asset else "",
            "threat": threat.name, "residual": r.residual_level,
            "candidate_controls": [{"code": c["code"], "name": c["name"], "maturity": c["maturity"]} for c in candidates],
        })

    api_key, model = _api_key_and_model(db, org_id, "deep")
    system = (
        "Eres un analista GRC. Con base en los riesgos y sus controles candidatos adjuntos, "
        "propone UNA iniciativa que los reduzca. Elige control_code SOLO entre los codigos "
        "candidatos listados (nunca inventes otros) y una madurez objetivo realista (0-5). "
        f"Responde en el idioma: {lang}."
    )
    parsed, _msg = structured_message(
        api_key, model=model, max_tokens=2048, system=system,
        messages=[{"role": "user", "content": f"Riesgos y candidatos:\n{candidates_by_risk}"}],
        tool_name="registrar_borrador_iniciativa",
        tool_description="Registra el borrador de iniciativa propuesto",
        input_schema=_DRAFT_SCHEMA,
        org_id=org_id, call_type="initiative_draft",
    )

    targets, skipped = _resolve_control_targets(
        db, org_id, all_candidate_codes,
        [{"control_code": ct.get("control_code"), "target_maturity": ct.get("target_maturity")}
         for ct in (parsed.get("control_targets") or [])],
    )
    return {
        "title": (parsed.get("title") or "Iniciativa propuesta")[:255],
        "description": parsed.get("description"),
        "priority": parsed.get("priority") if parsed.get("priority") in
                    ("low", "medium", "high", "critical") else "medium",
        "expected_risk_reduction": parsed.get("expected_risk_reduction"),
        "control_targets": targets,
        "skipped_controls": skipped,
        "rationale": parsed.get("rationale"),
        "risk_ids": [r.id for r in risks],
    }


# ---------- c) Plan de tratamiento por riesgo (para el cockpit) ----------

_TREATMENT_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "treatment_option": {"type": "string", "enum": ["modification", "retention", "avoidance", "sharing"]},
        "plan": {"type": "string", "maxLength": 1500},
        "tasks": {
            "type": "array", "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 255},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    "weeks_offset": {"type": "integer", "minimum": 0, "maximum": 52},
                },
                "required": ["title"],
            },
        },
        "rationale": {"type": "string", "maxLength": 600},
    },
    "required": ["treatment_option", "plan", "tasks", "rationale"],
}


def draft_treatment_plan(db: Session, risk, lang: str = "es") -> dict:
    """Borrador de plan de tratamiento para UN riesgo (cockpit de tratamiento).
    Es solo un borrador: no persiste nada, el usuario confirma/edita."""
    from app.services.threat_knowledge import candidate_impls_for_threat

    linked_controls = [
        {"code": ci.control.code, "name": ci.control.name, "maturity": ci.maturity}
        for ci in (risk.controls or []) if ci.control
    ]
    candidates = []
    if risk.threat and risk.threat.code:
        linked_ids = {ci.id for ci in (risk.controls or [])}
        candidates = [
            {"code": c["code"], "name": c["name"], "maturity": c["maturity"]}
            for c in candidate_impls_for_threat(db, risk.organization_id, risk.threat.code)
            if c["impl_id"] not in linked_ids
        ][:6]

    api_key, model = _api_key_and_model(db, risk.organization_id, "deep")
    system = (
        "Eres un analista GRC ISO 27005. Propone un plan de tratamiento operativo para el "
        "riesgo adjunto: opcion de tratamiento, un plan breve (5-10 lineas) y hasta 6 tareas "
        f"concretas con prioridad y semanas estimadas desde hoy. Responde en el idioma: {lang}."
    )
    context = {
        "risk_code": risk.code, "asset": risk.asset.name if risk.asset else "",
        "threat": risk.threat.name if risk.threat else "",
        "inherent_level": risk.inherent_level, "residual_level": risk.residual_level,
        "current_treatment_option": risk.treatment_option.value if risk.treatment_option else None,
        "controls_implemented": linked_controls,
        "controls_candidate": candidates,
    }
    parsed, _msg = structured_message(
        api_key, model=model, max_tokens=1536, system=system,
        messages=[{"role": "user", "content": f"Contexto del riesgo:\n{context}"}],
        tool_name="registrar_plan_tratamiento",
        tool_description="Registra el plan de tratamiento propuesto para el riesgo",
        input_schema=_TREATMENT_PLAN_SCHEMA,
        org_id=risk.organization_id, call_type="treatment_plan_draft",
    )
    tasks = [
        {"title": (tk.get("title") or "")[:255],
         "priority": tk.get("priority") if tk.get("priority") in ("low", "medium", "high", "critical") else "medium",
         "weeks_offset": max(0, min(52, int(tk.get("weeks_offset") or 0)))}
        for tk in (parsed.get("tasks") or [])[:6] if tk.get("title")
    ]
    return {
        "treatment_option": parsed.get("treatment_option") if parsed.get("treatment_option") in
                            ("modification", "retention", "avoidance", "sharing") else "modification",
        "plan": parsed.get("plan"),
        "tasks": tasks,
        "rationale": parsed.get("rationale"),
    }


# ---------- d) Narrativa mensual de avance (usada por el scheduler) ----------

def monthly_initiative_summary(db: Session, initiative, lang: str = "es") -> str:
    """Resumen ejecutivo breve (3-6 lineas) del avance del ultimo mes."""
    from app.models import InitiativeLogEntry, TreatmentTask
    since_entries = (
        db.query(InitiativeLogEntry)
        .filter(InitiativeLogEntry.initiative_id == initiative.id)
        .order_by(InitiativeLogEntry.created_at.desc())
        .limit(20)
        .all()
    )
    tasks = db.query(TreatmentTask).filter(TreatmentTask.initiative_id == initiative.id).all()
    done = sum(1 for t in tasks if str(getattr(t.status, "value", t.status)).lower() == "done")

    context = {
        "title": initiative.title, "status": initiative.status, "progress": initiative.progress,
        "health": initiative.health, "tasks_done": done, "tasks_total": len(tasks),
        "recent_log": [{"type": e.entry_type, "text": e.text} for e in since_entries],
    }
    api_key, model = _api_key_and_model(db, initiative.organization_id, "fast")
    system = (
        "Eres un PMO de ciberseguridad. Redacta un resumen ejecutivo de 3-6 lineas del avance "
        f"del ultimo mes de esta iniciativa, en tono neutro para comite. Idioma: {lang}."
    )
    schema = {
        "type": "object",
        "properties": {"summary": {"type": "string", "maxLength": 800}},
        "required": ["summary"],
    }
    parsed, _msg = structured_message(
        api_key, model=model, max_tokens=512, system=system,
        messages=[{"role": "user", "content": f"Contexto:\n{context}"}],
        tool_name="registrar_resumen_mensual",
        tool_description="Registra el resumen ejecutivo mensual de la iniciativa",
        input_schema=schema,
        org_id=initiative.organization_id, call_type="initiative_summary",
    )
    return parsed.get("summary", "")


_MAX_NARRATIVES_PER_ORG = 20


def run_monthly_narratives(db: Session) -> int:
    """Job mensual: narrativa de avance para iniciativas activas con actividad
    en los ultimos 30 dias (cap por org). Degradacion graceful: si la IA falla
    para una iniciativa, se registra y se continua con las demas."""
    from app.models import InitiativeLogEntry, Organization, StrategicInitiative

    since = datetime.now(timezone.utc) - timedelta(days=30)
    created = 0

    for org in db.query(Organization).filter(Organization.is_active.is_(True)).all():
        initiatives = db.query(StrategicInitiative).filter(
            StrategicInitiative.organization_id == org.id,
            StrategicInitiative.status.in_(["approved", "in_progress"]),
        ).all()
        count = 0
        for ini in initiatives:
            if count >= _MAX_NARRATIVES_PER_ORG:
                break
            has_recent_activity = db.query(InitiativeLogEntry).filter(
                InitiativeLogEntry.initiative_id == ini.id,
                InitiativeLogEntry.created_at >= since,
            ).first()
            if not has_recent_activity:
                continue
            try:
                summary = monthly_initiative_summary(db, ini, "es")
                if summary:
                    db.add(InitiativeLogEntry(
                        organization_id=ini.organization_id, initiative_id=ini.id,
                        entry_type="ai_summary", text=summary, author_id=None,
                    ))
                    created += 1
                    count += 1
            except Exception:
                logger.exception("run_monthly_narratives: fallo en iniciativa id=%s", ini.id)
        db.commit()

    return created
