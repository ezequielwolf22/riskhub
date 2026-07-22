"""Cuando el cliente no tiene documentacion: el agente la propone.

La mitad de los clientes llegan con un pack documental y la otra mitad con
nada. Este modulo cubre el segundo caso, y lo hace por el MISMO camino que la
ingesta: las filas propuestas pasan por el materializador, quedan en un lote y
heredan sus garantias — deshacer, revertir una sola, forzar un valor. Cambia el
origen (el perfil y los datos que ya hay en RiskHub en vez de un documento), no
el destino ni las reglas.

Lo generado nace como borrador, con confianza y con el razonamiento que lo
sostiene. Un BIA inventado sin justificacion no vale nada en una auditoria; uno
propuesto a partir de los activos criticos, los proveedores y los incidentes
reales de la organizacion es un punto de partida defendible que una persona
revisa y firma.

El cuestionario adaptativo va en la misma linea: en vez de un formulario fijo
de tres pasos, se pregunta solo lo que no se puede deducir de lo que ya hay.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.claude_client import structured_message
from app.services.ingest import batch as batch_mod
from app.services.ingest.materializer import MaterializationResult, materialize
from app.services.model_registry import get_model

logger = logging.getLogger("riskhub.ingest.generation")

TARGETS = ("scenarios", "bia", "plan", "strategies")


def _api_key_and_model(db, org_id: Optional[int], tier: str = "deep"):
    from app.models import AiConfig
    from app.routers.ai import _resolve_api_key
    cfg = db.query(AiConfig).filter_by(organization_id=org_id).first()
    api_key = _resolve_api_key(cfg)
    if not api_key:
        raise ValueError("No hay API key del agente IA configurada")
    return api_key, get_model(db, org_id, tier)


# ── Contexto: lo que la organizacion ya tiene ────────────────────────────────

def gather_context(db, org_id: Optional[int]) -> dict:
    """Todo lo que permite proponer sin inventar.

    Mismo espiritu que `context_autofill` del router BCP, que ya deriva
    sistemas y proveedores criticos de los datos existentes, pero completo:
    aqui alimenta a una generacion, no a un formulario.
    """
    from app.models import (Asset, BCMLocation, BCMScenario, BusinessProcess,
                            Incident, OrganizationProfile, Risk, Supplier)

    def _safe(fn, default):
        try:
            return fn()
        except Exception:
            logger.debug("generation: no se pudo leer parte del contexto",
                         exc_info=True)
            return default

    profile = _safe(
        lambda: db.query(OrganizationProfile).filter_by(
            organization_id=org_id).first(), None)

    # Para continuidad, el activo relevante es el que no puede estar caido: la
    # dimension que importa es la disponibilidad, no una "criticidad" generica
    # (que ademas no existe como columna en Asset).
    assets = _safe(lambda: db.query(Asset).filter_by(
        organization_id=org_id).filter(
        Asset.value_availability >= 4).order_by(
        Asset.value_availability.desc()).limit(40).all(), [])
    suppliers = _safe(lambda: db.query(Supplier).filter_by(
        organization_id=org_id).limit(40).all(), [])
    locations = _safe(lambda: db.query(BCMLocation).filter_by(
        organization_id=org_id, is_active=True).all(), [])
    scenarios = _safe(lambda: db.query(BCMScenario).filter_by(
        organization_id=org_id, is_active=True).all(), [])
    processes = _safe(lambda: db.query(BusinessProcess).filter_by(
        organization_id=org_id).limit(60).all(), [])
    incidents = _safe(lambda: db.query(Incident).filter_by(
        organization_id=org_id).order_by(Incident.id.desc()).limit(20).all(), [])
    risks = _safe(lambda: db.query(Risk).filter_by(
        organization_id=org_id).limit(40).all(), [])

    return {
        "profile": {
            "narrative": getattr(profile, "narrative", None),
            "structure": getattr(profile, "structure", None),
            "method": getattr(profile, "method", None),
        } if profile else None,
        "locations": [
            {"name": loc.name, "country": loc.country,
             "site_type": getattr(loc, "site_type", None),
             "business_unit": getattr(loc, "business_unit", None)}
            for loc in locations
        ],
        "scenarios": [
            {"code": s.code, "name": s.name, "family": s.family} for s in scenarios
        ],
        "processes": [
            {"name": p.name, "criticality": p.criticality, "rto_hours": p.rto_hours}
            for p in processes
        ],
        "assets": [
            {"name": a.name, "type": getattr(a, "asset_type", None),
             "availability_value": getattr(a, "value_availability", None)}
            for a in assets
        ],
        "suppliers": [
            {"name": s.name, "services": getattr(s, "services", None),
             "is_critical": bool(getattr(s, "is_critical", False))}
            for s in suppliers
        ],
        "incidents": [
            {"title": getattr(i, "title", None),
             "severity": str(getattr(i, "severity", "") or "")}
            for i in incidents
        ],
        "risks": [{"name": getattr(r, "name", None)} for r in risks],
    }


# ── Cuestionario adaptativo ──────────────────────────────────────────────────

def pending_questions(db, org_id: Optional[int]) -> list[dict]:
    """Lo que hace falta saber y no se puede deducir de lo que ya hay.

    Sustituye al cuestionario fijo: preguntar por el sector cuando ya hay
    cuarenta activos y veinte proveedores cargados es hacerle perder el tiempo
    al cliente. Cada pregunta declara por que se hace y que desbloquea.
    """
    ctx = gather_context(db, org_id)
    questions: list[dict] = []

    if not ctx["locations"]:
        questions.append({
            "key": "locations",
            "question": "En que sedes o paises opera la organizacion?",
            "why": "Sin sedes no se puede valorar el impacto por localizacion.",
            "unlocks": "matriz de cobertura por sede",
            "type": "list",
        })
    else:
        sin_tipo = [loc["name"] for loc in ctx["locations"] if not loc["site_type"]]
        if sin_tipo:
            questions.append({
                "key": "site_types",
                "question": ("Cuales de estas sedes tienen oficina fisica y cuales "
                             "son 100% remotas?"),
                "why": ("El tipo de sede gobierna que escenarios pueden aplicarle. "
                        "Sin informar, se asume que le aplican todos."),
                "unlocks": "reglas de aplicabilidad",
                "type": "map", "items": sin_tipo[:30],
            })

    if not ctx["scenarios"]:
        questions.append({
            "key": "scenarios",
            "question": "Que escenarios de indisponibilidad contempla la organizacion?",
            "why": "Es el eje del BIA por escenario.",
            "unlocks": "catalogo de escenarios y BIA",
            "type": "generate",
        })

    if not ctx["processes"]:
        questions.append({
            "key": "processes",
            "question": "Cuales son los procesos de negocio criticos?",
            "why": "ISO 22301 cl. 8.2 exige identificarlos antes de fijar RTO y RPO.",
            "unlocks": "BIA por proceso",
            "type": "generate",
        })

    if not ctx["assets"]:
        questions.append({
            "key": "assets",
            "question": "Que sistemas sostienen la operacion diaria?",
            "why": "Sin inventario, las dependencias del BIA se quedan vacias.",
            "unlocks": "dependencias y DRP",
            "type": "list",
        })

    return questions


# ── Generacion ───────────────────────────────────────────────────────────────

_SCENARIOS_SCHEMA = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string", "maxLength": 1500},
        "scenarios": {
            "type": "array", "maxItems": 30,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "maxLength": 255},
                    "family": {"type": "string",
                               "enum": ["personnel", "systems_comms",
                                        "third_party", "facilities"]},
                    "description": {"type": "string"},
                    "procedure_notes": {"type": "string"},
                    "why": {"type": "string", "maxLength": 400},
                    "confidence": {"type": "number"},
                },
                "required": ["name", "family", "why"],
            },
        },
    },
    "required": ["scenarios", "rationale"],
}

_BIA_SCHEMA = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string", "maxLength": 1500},
        "processes": {
            "type": "array", "maxItems": 40,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "maxLength": 255},
                    "description": {"type": "string"},
                    "criticality": {"type": "string",
                                    "enum": ["critical", "high", "medium", "low"]},
                    "rto_hours": {"type": "integer"},
                    "rpo_hours": {"type": "integer"},
                    "mtpd_hours": {"type": "integer"},
                    "mbco": {"type": "string"},
                    "activation_criteria": {"type": "string"},
                    "alternative_procedure": {"type": "string"},
                    "why": {"type": "string", "maxLength": 400},
                    "confidence": {"type": "number"},
                },
                "required": ["name", "criticality", "why"],
            },
        },
    },
    "required": ["processes", "rationale"],
}

_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string", "maxLength": 1500},
        "name": {"type": "string", "maxLength": 255},
        "plan_type": {"type": "string",
                      "enum": ["bcp", "drp", "crp", "ems", "pandemic",
                               "cyber_response", "supply_chain"]},
        "scope": {"type": "string"},
        "activation_criteria": {"type": "string"},
        "content_summary": {"type": "string"},
        "sections": {
            "type": "array", "maxItems": 20,
            "items": {"type": "object",
                      "properties": {"title": {"type": "string"},
                                     "content": {"type": "string"}},
                      "required": ["title", "content"]},
        },
        "roles_matrix": {
            "type": "array", "maxItems": 15,
            "items": {"type": "object",
                      "properties": {"role_name": {"type": "string"},
                                     "actions_notification": {"type": "string"},
                                     "actions_recovery": {"type": "string"}},
                      "required": ["role_name"]},
        },
        "backup_policy": {"type": "object"},
        "crisis_comms": {"type": "object"},
        "confidence": {"type": "number"},
    },
    "required": ["name", "plan_type", "sections", "rationale"],
}

_SYSTEM = """Eres un consultor senior de continuidad de negocio (ISO 22301) preparando un
borrador para un cliente que todavia no tiene esta documentacion.

Te doy lo que la organizacion YA tiene cargado en su plataforma GRC: sus sedes,
sus activos criticos, sus proveedores, sus incidentes pasados y sus riesgos.
Propon a partir de ESO, no de un ejemplo generico de manual.

Reglas:

- Cada elemento que propongas lleva un "why" que lo ancla a un dato concreto
  del contexto ("porque hay tres proveedores cloud criticos y ningun escenario
  de indisponibilidad de terceros"). Si no puedes anclarlo, no lo propongas.
- No dupliques lo que ya existe: revisa las listas que te doy.
- Los RTO y RPO son propuestas prudentes de partida, no compromisos. Ponles
  confianza baja si el contexto no los sostiene.
- Es un borrador para que una persona lo revise y lo firme. Prefiero pocas
  propuestas defendibles a un catalogo completo e inventado."""


def _generate(db, org_id, schema, tool_name, instruction, lang, tier="deep"):
    api_key, model = _api_key_and_model(db, org_id, tier)
    ctx = gather_context(db, org_id)
    parsed, _msg = structured_message(
        api_key, model=model, max_tokens=8192,
        system=_SYSTEM + f"\n\nResponde en el idioma: {lang}.",
        messages=[{"role": "user",
                   "content": f"CONTEXTO DE LA ORGANIZACION:\n{ctx}\n\n{instruction}"}],
        tool_name=tool_name,
        tool_description="Entrega el borrador propuesto",
        input_schema=schema,
        org_id=org_id, call_type=f"bcm_generate_{tool_name}",
    )
    return parsed


def _rows(items: list, extra_keys: tuple = ()) -> list[dict]:
    """Traduce las propuestas al formato del materializador.

    El "why" no es un campo del modelo: viaja como parte de la confianza y del
    resumen del lote, para que la revision vea el porque sin ensuciar la tabla.
    """
    out = []
    for item in items or []:
        row = {k: v for k, v in item.items()
               if k not in ("why", "confidence") or k in extra_keys}
        row["_confidence"] = item.get("confidence", 0.6)
        row["_source_ref"] = "generado"
        out.append(row)
    return out


def generate(db, org_id: Optional[int], target: str, *, user_id: Optional[int] = None,
             lang: str = "es", plan_type: str = "bcp",
             scope: Optional[str] = None) -> dict:
    """Genera un borrador y lo materializa en un lote reversible."""
    if target not in TARGETS:
        raise ValueError(f"Objetivo no soportado: {target}")

    bat = batch_mod.create_batch(db, org_id, module="bcm", user_id=user_id,
                                 files=[{"filename": f"(generado: {target})",
                                         "status": "ok"}])
    result = MaterializationResult()
    summary = dict(bat.summary or {})
    proposals: list[dict] = []

    try:
        if target == "scenarios":
            parsed = _generate(
                db, org_id, _SCENARIOS_SCHEMA, "proponer_escenarios",
                ("Propon el catalogo de escenarios de indisponibilidad que deberia "
                 "contemplar esta organizacion, repartidos entre las cuatro familias."),
                lang)
            proposals = parsed.get("scenarios") or []
            materialize(db, org_id, bat, "bcm_scenario", _rows(proposals),
                        source_filename="(generado)", result=result,
                        default_confidence=0.6)

        elif target == "bia":
            parsed = _generate(
                db, org_id, _BIA_SCHEMA, "proponer_bia",
                ("Propon los procesos de negocio criticos con sus objetivos de "
                 "recuperacion, a partir de los activos, proveedores e incidentes."),
                lang)
            proposals = parsed.get("processes") or []
            materialize(db, org_id, bat, "business_process", _rows(proposals),
                        source_filename="(generado)", result=result,
                        default_confidence=0.6)

        elif target == "plan":
            parsed = _generate(
                db, org_id, _PLAN_SCHEMA, "proponer_plan",
                (f"Propon un plan de tipo '{plan_type}'"
                 + (f" con este alcance: {scope}." if scope else ".")),
                lang)
            proposals = [parsed]
            row = {k: parsed.get(k) for k in
                   ("name", "plan_type", "scope", "activation_criteria",
                    "content_summary", "sections", "roles_matrix",
                    "backup_policy", "crisis_comms") if parsed.get(k)}
            row["_confidence"] = parsed.get("confidence", 0.6)
            materialize(db, org_id, bat, "bcp_plan", [row],
                        source_filename="(generado)", result=result,
                        default_confidence=0.6)

        elif target == "strategies":
            parsed = _generate(
                db, org_id, _SCENARIOS_SCHEMA, "proponer_estrategias",
                ("Para cada escenario del catalogo, propon la estrategia o "
                 "alternativa de continuidad mas razonable dado el contexto."),
                lang)
            proposals = parsed.get("scenarios") or []
            rows = [{"name": p.get("name"), "description": p.get("description"),
                     "_ref_scenario_id": p.get("name"),
                     "_confidence": p.get("confidence", 0.5)}
                    for p in proposals if p.get("name")]
            materialize(db, org_id, bat, "bcp_strategy", rows,
                        source_filename="(generado)", result=result,
                        default_confidence=0.5)

        db.commit()
        summary.update({
            "created": result.created, "updated": result.updated,
            "linked": result.linked, "needs_review": result.needs_review,
            "conflicts": result.conflicts,
            "generated": True, "target": target,
            "rationale": parsed.get("rationale"),
            # El porque de cada propuesta, para que la revision no sea a ciegas
            "proposals": [{"name": p.get("name"), "why": p.get("why"),
                           "confidence": p.get("confidence")}
                          for p in proposals if isinstance(p, dict)][:60],
            "warnings": result.warnings[:40],
        })
        bat.summary = summary
        bat.status = "completed"
        db.commit()
        return {"batch_id": bat.id, "status": "completed", **summary}

    except Exception as exc:
        db.rollback()
        logger.exception("generation: fallo generando %s", target)
        bat.status = "failed"
        summary["warnings"] = [str(exc)[:300]]
        bat.summary = summary
        db.commit()
        return {"batch_id": bat.id, "status": "failed", "error": str(exc)[:300]}
