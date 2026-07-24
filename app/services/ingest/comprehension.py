"""La parte que piensa: el agente lee el pack y decide como descomponerlo.

Es lo unico de todo el motor que usa un modelo de lenguaje, y hace exactamente
dos cosas:

**Pasada 1 — el pack entero, antes de escribir nada.** Deduce el perfil de la
organizacion: sus sedes, sus unidades de negocio, el metodo con el que valora
el impacto, su catalogo de escenarios y su vocabulario. Todo lo que venga
despues se interpreta contra ese marco. Si ya hay perfil, propone un diff.

**Pasada 2 — documento a documento.** Con el perfil delante, produce el *mapa
de volcado*: que unidades contiene el documento, con que clave se descomponen y
cuantas filas de que entidad genera cada una. Aqui vive la inteligencia real:
un BIA puede venir como escenario x sede en bloques de siete filas, como una
fila por proceso, o como una narracion en Word — y de cada forma salen filas
distintas. El agente lo deduce; no hay una plantilla esperando.

Lo que este modulo NO hace: escribir en la base de datos, calcular impactos ni
decidir si un registro existe. Eso es del materializador, del motor de
escenarios y del reconciliador, que son deterministas y auditables.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.claude_client import structured_message
from app.services.ingest import contracts
from app.services.ingest.reader import render_for_llm
from app.services.model_registry import get_model

logger = logging.getLogger("riskhub.ingest.comprehension")

DOC_KINDS = ("bia", "policy", "bcp", "drp", "test_report", "exercise_programme",
             "contact_list", "supplier_list", "risk_assessment", "other")

# Tope de caracteres por documento. Un BIA real ronda los 55.000; el margen
# cubre libros grandes sin dispararse en coste.
MAX_DOC_CHARS = 90000
MAX_PROFILE_CHARS = 70000


def _api_key_and_model(db, org_id: Optional[int], tier: str) -> tuple[str, str]:
    """Key de la organizacion (o la de plataforma) y modelo segun el tier."""
    from app.models import AiConfig
    from app.routers.ai import _resolve_api_key

    cfg = db.query(AiConfig).filter_by(organization_id=org_id).first()
    api_key = _resolve_api_key(cfg)
    if not api_key:
        raise ValueError("No hay API key del agente IA configurada")
    return api_key, get_model(db, org_id, tier)


# ── Pasada 1: perfil de la organizacion ──────────────────────────────────────

_PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "narrative": {"type": "string", "maxLength": 2000},
        "confidence": {"type": "number"},
        "structure": {
            "type": "object",
            "properties": {
                "locations": {
                    "type": "array", "maxItems": 80,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "country": {"type": "string"},
                            "city": {"type": "string"},
                            "business_unit": {"type": "string"},
                            "site_type": {"type": "string",
                                          "enum": ["office", "remote", "hybrid"]},
                            "staffing_model": {"type": "string",
                                               "enum": ["internal", "external", "both"]},
                            "evidence": {"type": "string", "maxLength": 300},
                        },
                        "required": ["name"],
                    },
                },
                "business_units": {"type": "array", "maxItems": 40,
                                   "items": {"type": "string"}},
            },
        },
        "bia_method": {
            "type": "object",
            "properties": {
                "style": {"type": "string",
                          "enum": ["scenario_x_location", "process", "service", "mixed",
                                   "unknown"]},
                "dimensions": {
                    "type": "array", "maxItems": 12,
                    "items": {"type": "object",
                              "properties": {"key": {"type": "string"},
                                             "label": {"type": "string"}},
                              "required": ["key", "label"]},
                },
                "horizons": {"type": "array", "maxItems": 10,
                             "items": {"type": "string"}},
                "rto_scale": {
                    "type": "array", "maxItems": 15,
                    "items": {"type": "object",
                              "properties": {"label": {"type": "string"},
                                             "hours": {"type": "number"},
                                             "factor": {"type": "number"}},
                              "required": ["label"]},
                },
                "bands": {
                    "type": "array", "maxItems": 10,
                    "items": {"type": "object",
                              "properties": {"key": {"type": "string"},
                                             "label": {"type": "string"},
                                             "min": {"type": "number"},
                                             "max": {"type": "number"}},
                              "required": ["key", "label", "min"]},
                },
                "aggregation": {"type": "string", "enum": ["max", "avg"]},
            },
        },
        "scenarios": {
            "type": "array", "maxItems": 60,
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "name": {"type": "string"},
                    "family": {"type": "string",
                               "enum": ["personnel", "systems_comms",
                                        "third_party", "facilities"]},
                    "description": {"type": "string"},
                },
                "required": ["name", "family"],
            },
        },
        "applicability_rules": {
            "type": "array", "maxItems": 15,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "when": {"type": "object"},
                    "then": {"type": "object"},
                    "rationale": {"type": "string", "maxLength": 500},
                },
                "required": ["when", "then", "rationale"],
            },
        },
        "vocabulary": {"type": "object"},
        "regulations": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
        "open_questions": {"type": "array", "maxItems": 15,
                           "items": {"type": "string"}},
    },
    "required": ["narrative", "confidence"],
}

_PROFILE_SYSTEM = """Eres un consultor senior de continuidad de negocio (ISO 22301) que recibe la
documentacion completa de un cliente y debe entender COMO trabaja esa
organizacion antes de tocar nada.

No extraigas datos todavia. Tu unica tarea ahora es construir el perfil:

1. ESTRUCTURA: que sedes y unidades de negocio existen. Para cada sede deduce
   si tiene oficina fisica, si es 100% remota o mixta, y si su plantilla es
   propia, subcontratada o ambas. Si el documento no lo dice, DEJA EL CAMPO
   VACIO: un dato inventado aqui contamina todo lo que venga despues.

2. METODO BIA: con que dimensiones valora el impacto esta organizacion, en que
   horizontes temporales, con que escala de RTO y con que bandas. Cada cliente
   usa el suyo; transcribe el suyo, no el que te parezca mejor.

3. ESCENARIOS: el catalogo de escenarios de indisponibilidad que maneja, con su
   codigo propio si lo tiene, agrupados en las cuatro familias.

4. REGLAS DE APLICABILIDAD: si el cliente dice explicitamente que ciertos
   escenarios no aplican a ciertas sedes, declaralo como regla CON SU
   JUSTIFICACION. Solo si el documento lo afirma. Por omision todos los
   escenarios aplican a todas las sedes, y ese es el valor por defecto correcto:
   una regla de mas oculta un riesgo real.

5. VOCABULARIO: terminos propios del cliente y su equivalente estandar.

Lo que no sepas, dejalo vacio y anotalo en open_questions. Prefiero un perfil
con huecos declarados a uno completo e inventado."""


def build_profile(db, org_id: Optional[int], documents: list[dict],
                  existing_profile=None, lang: str = "es") -> dict:
    """Pasada 1: deduce el perfil de la organizacion a partir del pack."""
    api_key, model = _api_key_and_model(db, org_id, "deep")

    budget = MAX_PROFILE_CHARS // max(1, len(documents))
    corpus = "\n\n".join(
        render_for_llm(doc, max_chars=max(3000, budget)) for doc in documents
    )

    prior = ""
    if existing_profile is not None:
        prior = (
            "\n\nPERFIL YA REGISTRADO (propon solo cambios justificados; si algo "
            "sigue siendo valido, repitelo tal cual):\n"
            f"estructura={existing_profile.structure}\n"
            f"metodo={existing_profile.method}\n"
        )

    parsed, msg = structured_message(
        api_key, model=model, max_tokens=8192,
        system=_PROFILE_SYSTEM + f"\n\nResponde en el idioma: {lang}.",
        messages=[{"role": "user",
                   "content": f"Documentacion del cliente:\n{corpus}{prior}"}],
        tool_name="registrar_perfil_organizacion",
        tool_description="Registra el perfil deducido de la documentacion",
        input_schema=_PROFILE_SCHEMA,
        org_id=org_id, call_type="ingest_profile",
    )
    return _sanitize_profile(parsed)


def _sanitize_profile(parsed: dict) -> dict:
    """Descarta lo que el motor no sabria interpretar.

    Una regla de aplicabilidad mal formada es peligrosa: silenciaria escenarios
    sin que nadie se entere. Se valida contra el mismo vocabulario que el router.
    """
    from app.routers.bcp import (_RULE_THEN_KEYS, _RULE_WHEN_FIELDS,
                                 VALID_SCENARIO_FAMILIES)

    rules = []
    for rule in (parsed.get("applicability_rules") or []):
        when, then = rule.get("when") or {}, rule.get("then") or {}
        if not isinstance(when, dict) or not isinstance(then, dict) or not when:
            continue
        if any(k not in _RULE_WHEN_FIELDS for k in when):
            continue
        if not any(k in then for k in _RULE_THEN_KEYS):
            continue
        bad_family = any(
            fam not in VALID_SCENARIO_FAMILIES
            for key in ("exclude_families", "include_only_families")
            for fam in (then.get(key) or [])
        )
        if bad_family or not rule.get("rationale"):
            continue
        rules.append(rule)
    parsed["applicability_rules"] = rules
    return parsed


# ── Pasada 2: mapa de volcado por documento ──────────────────────────────────

def _sourcemap_schema() -> dict:
    """Schema del mapa. Las entidades validas salen del registro."""
    return {
        "type": "object",
        "properties": {
            "doc_kind": {"type": "string", "enum": list(DOC_KINDS)},
            "language": {"type": "string"},
            "document_date": {"type": "string"},
            "rationale": {"type": "string", "maxLength": 1500},
            "confidence": {"type": "number"},
            "units": {
                "type": "array", "maxItems": 25,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "maxLength": 200},
                        "source_ref": {"type": "string", "maxLength": 120},
                        "decomposition_key": {"type": "string", "maxLength": 300},
                        "target_entity": {"type": "string",
                                          "enum": contracts.entity_keys()},
                        "confidence": {"type": "number"},
                        "rows": {
                            "type": "array", "maxItems": 200,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "fields": {"type": "object"},
                                    "source_ref": {"type": "string", "maxLength": 120},
                                    "confidence": {"type": "number"},
                                },
                                "required": ["fields"],
                            },
                        },
                    },
                    "required": ["label", "target_entity", "decomposition_key", "rows"],
                },
            },
            "ambiguities": {
                "type": "array", "maxItems": 15,
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "chosen": {"type": "string"},
                        "why": {"type": "string"},
                    },
                    "required": ["question", "chosen"],
                },
            },
        },
        "required": ["doc_kind", "units", "rationale", "confidence"],
    }


_MAP_SYSTEM = """Eres un consultor de continuidad de negocio volcando la documentacion de un
cliente en una plataforma GRC. Ya conoces como trabaja esa organizacion.

Tu tarea es decidir COMO SE DESCOMPONE este documento y extraer las filas.

Lo primero es la descomposicion, y es lo que mas importa. Un mismo tipo de
documento se organiza de formas distintas segun el cliente: un BIA puede ser
una hoja por proceso, un bloque de filas por escenario y sede, una tabla de
servicios TI, o una narracion en Word. Mira la estructura real que tienes
delante y decide cuantas unidades hay y que las separa. Declara esa decision en
"decomposition_key" con palabras ("cada bloque de 7 filas encabezado por el
nombre del escenario en la columna B") para que una persona pueda comprobarla.

Reglas que no se negocian:

- NO INVENTES. Si un campo no esta en el documento, omitelo. Un hueco es
  recuperable; un dato falso en un plan de continuidad no.
- Usa SOLO los campos y vocabularios del catalogo de entidades. Un valor fuera
  de la lista se descarta despues en silencio, asi que no lo propongas.
- Para enlazar con otra entidad usa "_ref_<campo>" con su nombre o codigo tal y
  como aparece en el documento. Nunca inventes identificadores numericos.
- Los campos marcados como calculados NO se extraen, aunque el documento traiga
  el numero: los recalcula el motor con el baremo del cliente.
- El estado de aprobacion de un plan NUNCA se extrae. Que un documento se
  titule "aprobado" no aprueba nada.
- Pon "confidence" bajo en las filas de las que dudes. Se guardaran igual,
  marcadas para revision: es mejor que descartarlas.
- Si una fila se puede leer de dos formas, elige la mas conservadora y anotalo
  en "ambiguities".

Reglas especificas del BIA (bcm_scenario_assessment) — son las que mas fallan:
- CADA valoracion debe llevar A LA VEZ, en la MISMA fila: la sede
  ("_ref_location_id"), el escenario ("_ref_scenario_id") y los impactos
  ("impacts"). NO partas una valoracion en dos filas (una con sede sin impactos
  y otra con impactos sin sede): eso deja la matriz vacia y es el error mas
  comun. Si el documento da los impactos por escenario y la sede aparece en una
  columna, cabecera o titulo ("Localizacion: Madrid"), usa esa sede en cada fila.
- Si el BIA valora un escenario para VARIAS sedes, genera una fila por sede,
  todas con sus impactos.
- Extrae TODOS los procesos y TODAS las valoraciones de la plantilla, no una
  muestra. Si una hoja tiene doce procesos, saca los doce.
- "impacts" tiene la forma {dimension: {horizonte: nivel}} usando las dimensiones
  y horizontes del metodo del cliente que aparecen en el perfil."""


def build_source_map(db, org_id: Optional[int], document: dict,
                     profile: Optional[dict] = None, lang: str = "es",
                     tier: str = "deep") -> dict:
    """Pasada 2: mapa de volcado y filas extraidas de un documento."""
    api_key, model = _api_key_and_model(db, org_id, tier)

    profile_block = ""
    if profile:
        locations = [
            loc.get("name") for loc in
            ((profile.get("structure") or {}).get("locations") or [])
            if loc.get("name")
        ]
        scenarios = [
            f"{s.get('code') or ''} {s.get('name')}".strip()
            for s in (profile.get("scenarios") or [])
        ]
        profile_block = (
            "\n\nPERFIL DE LA ORGANIZACION (usa estos nombres exactos al "
            "referenciar sedes y escenarios):\n"
            f"- sedes: {', '.join(locations) or 'ninguna conocida'}\n"
            f"- escenarios: {', '.join(scenarios) or 'ninguno conocido'}\n"
            f"- metodo BIA: {profile.get('bia_method') or 'no declarado'}\n"
        )

    body = render_for_llm(document, max_chars=MAX_DOC_CHARS)
    parsed, msg = structured_message(
        api_key, model=model, max_tokens=16000,
        system=_MAP_SYSTEM + f"\n\nResponde en el idioma: {lang}.",
        messages=[{
            "role": "user",
            "content": (f"CATALOGO DE ENTIDADES DESTINO:{contracts.describe_for_prompt()}"
                        f"{profile_block}\n\n{body}"),
        }],
        tool_name="registrar_mapa_de_volcado",
        tool_description=("Declara como se descompone el documento y entrega las "
                          "filas extraidas"),
        input_schema=_sourcemap_schema(),
        org_id=org_id, call_type="ingest_sourcemap",
    )
    return _sanitize_map(parsed, document)


def _sanitize_map(parsed: dict, document: dict) -> dict:
    """Filtra unidades hacia entidades desconocidas y filas vacias."""
    valid = set(contracts.entity_keys())
    units = []
    for unit in (parsed.get("units") or []):
        entity = unit.get("target_entity")
        if entity not in valid:
            logger.info("ingest: unidad descartada, entidad desconocida %r", entity)
            continue
        rows = [r for r in (unit.get("rows") or []) if isinstance(r.get("fields"), dict)
                and r["fields"]]
        if not rows:
            continue
        unit["rows"] = rows
        units.append(unit)
    parsed["units"] = units
    parsed["filename"] = document.get("filename")
    parsed["sha256"] = document.get("sha256")
    return parsed


def rows_for_materializer(unit: dict) -> list[dict]:
    """Convierte las filas del mapa al formato que espera el materializador."""
    out = []
    for row in unit.get("rows") or []:
        payload = dict(row.get("fields") or {})
        payload["_confidence"] = row.get("confidence", unit.get("confidence", 1.0))
        payload["_source_ref"] = row.get("source_ref") or unit.get("source_ref")
        out.append(payload)
    return out
