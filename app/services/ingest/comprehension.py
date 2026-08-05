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

# Version del prompt de extraccion. Al cambiar los prompts se sube este numero
# para invalidar la cache de lecturas (una lectura vieja podria no reflejar las
# reglas nuevas). Es lo que permite que la cache por SHA sea segura.
EXTRACTION_PROMPT_VERSION = "5"

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
   codigo propio si lo tiene, agrupados en las cuatro familias. Este catalogo
   suele estar declarado en el documento de metodo o procedimiento (una lista
   cerrada). Extrae ESA lista canonica. NO inventes un escenario por cada
   proveedor o tecnologia: "caida de infraestructura AWS", "...GCP", "...OVH" son
   el MISMO escenario de indisponibilidad de sistemas; el proveedor es una
   dependencia, no un escenario. Un catalogo de escenarios bien hecho tiene del
   orden de 10-20 entradas, no cientos.

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
- CONFIANZA bien calibrada. Se CONFIADO (0.9 o mas) cuando el dato esta escrito
  de forma explicita en el documento: no marques como dudoso lo que esta claro,
  o llenas la revision de falsas alarmas. Reserva la confianza baja (por debajo
  de 0.75, que pide revision humana) para cuando de verdad estas INFIRIENDO algo
  que el documento no dice literalmente, o cuando el texto es ambiguo. Un dato
  copiado tal cual de una celda o una frase clara va con confianza alta.
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
  y horizontes del metodo del cliente que aparecen en el perfil.

CONSOLIDACION (lo mas importante para que el resultado tenga sentido):
- No leas este documento como si fuera el unico. Cruza lo que dice con el
  CATALOGO CANONICO de la organizacion que se te da mas abajo. Si algo que
  mencionas ya existe en ese catalogo (un escenario, un proceso, una sede),
  referencialo con su NOMBRE EXACTO. Estas ENRIQUECIENDO esa entidad, no creando
  otra. Crear una variante con otro nombre es el peor error: parte la realidad
  en trozos y llena la revision de dudas falsas.
- El MISMO escenario descrito con otro proveedor o tecnologia (AWS / GCP / OVH /
  un SaaS) o con otras palabras es UN SOLO escenario. El proveedor NO es un
  escenario nuevo: es una DEPENDENCIA del proceso. No multipliques escenarios por
  proveedor ni por sede.

DEPENDENCIAS (metodo ISO/TS 22317) — se modelan POR PROCESO, en categorias:
- Cada proceso depende de: aplicaciones/sistemas (dependency_type "IT_system"),
  personas ("personnel"), proveedores ("supplier"), instalaciones ("facility"),
  comunicaciones ("communication") y otros procesos ("process").
- Cuando el documento nombra el sistema, la app o el proveedor del que depende un
  proceso (p.ej. "corre sobre AWS", "telefonia de RingCentral", "base de datos
  X"), crea una dependencia (entidad bcp_dependency) enlazada al proceso por
  "_ref_process_id", con su nombre y su dependency_type. Ahi es donde vive el
  proveedor de infraestructura, no en un escenario aparte.

JERARQUIA DE PROCESOS (reconstruye la estructura real, no una lista plana):
- UNIDAD DE NEGOCIO: cada proceso pertenece a un area/departamento (Comercial,
  IT, Operaciones, Finanzas...). Cuando el documento lo indique (por columna,
  cabecera, pestana o titulo de bloque), rellena "business_unit" en cada proceso.
- MACRO-PROCESO -> PROCESO -> ACTIVIDAD: si un proceso es una parte o subproceso
  de otro mayor (una actividad dentro de un proceso, un proceso dentro de una
  cadena de valor), enlazalo a su padre con "_ref_parent_process_id" usando el
  NOMBRE EXACTO del proceso padre. No inventes niveles que el documento no marca;
  pero si el documento numera "1. Ventas / 1.1 Captacion / 1.2 Facturacion",
  1.1 y 1.2 son hijos de 1. Ventas.
- PROCESO QUE DEPENDE DE OTRO PROCESO: cuando un proceso necesita de otro proceso
  para operar o recuperarse (p.ej. "Facturacion depende de que Ventas este
  operativo"), crea una bcp_dependency con dependency_type "process", enlazada al
  proceso dependiente por "_ref_process_id" y al proceso del que depende por
  "_ref_depends_on_process_id" (nombre exacto). Eso alimenta el grafo de
  propagacion de impacto y el orden de recuperacion."""


def _cache_get(db, org_id, sha256):
    """Lectura cacheada de un documento por su huella, o None."""
    if not sha256 or not org_id:
        return None
    try:
        from app.models import IngestDocExtraction
        row = db.query(IngestDocExtraction).filter_by(
            organization_id=org_id, sha256=sha256,
            prompt_version=EXTRACTION_PROMPT_VERSION).first()
        return row.result if row else None
    except Exception:
        logger.debug("ingest: no se pudo leer la cache de extraccion", exc_info=True)
        return None


def _cache_put(db, org_id, sha256, filename, result):
    if not sha256 or not org_id:
        return
    try:
        from app.models import IngestDocExtraction
        existing = db.query(IngestDocExtraction).filter_by(
            organization_id=org_id, sha256=sha256,
            prompt_version=EXTRACTION_PROMPT_VERSION).first()
        if existing:
            existing.result = result
        else:
            db.add(IngestDocExtraction(
                organization_id=org_id, sha256=sha256,
                prompt_version=EXTRACTION_PROMPT_VERSION,
                filename=filename, result=result))
        db.commit()
    except Exception:
        db.rollback()
        logger.debug("ingest: no se pudo guardar la cache de extraccion",
                     exc_info=True)


def _canonical_catalog(db, org_id) -> dict:
    """Escenarios, procesos y sedes que YA existen para la org.

    Es la columna vertebral de identidad: crece documento a documento y es lo que
    permite CONSOLIDAR en vez de duplicar. Se lee de la base (no del perfil) para
    que refleje lo realmente materializado hasta ahora.
    """
    out = {"scenarios": [], "processes": [], "locations": []}
    if not org_id:
        return out
    try:
        from app.models import BCMLocation, BCMScenario, BusinessProcess
        out["scenarios"] = [(s.code, s.name) for s in db.query(BCMScenario)
                            .filter_by(organization_id=org_id).all() if s.name]
        out["processes"] = [p.name for p in db.query(BusinessProcess)
                            .filter_by(organization_id=org_id).all() if p.name]
        out["locations"] = [loc.name for loc in db.query(BCMLocation)
                            .filter_by(organization_id=org_id).all() if loc.name]
    except Exception:
        logger.debug("ingest: no se pudo leer el catalogo canonico", exc_info=True)
    return out


def _catalog_block(db, org_id, profile: Optional[dict]) -> str:
    """Bloque de catalogo canonico que se inyecta en la pasada 2.

    Combina lo ya materializado (autoridad) con lo que el perfil dedujo (por si el
    catalogo aun esta vacio en el primer documento). Es lo que el modelo usa para
    mapear cada mencion a una entidad existente en vez de inventar variantes.
    """
    cat = _canonical_catalog(db, org_id)
    prof = profile or {}
    prof_scen = [(s.get("code"), s.get("name"))
                 for s in (prof.get("scenarios") or []) if s.get("name")]
    prof_loc = [loc.get("name") for loc in
                ((prof.get("structure") or {}).get("locations") or []) if loc.get("name")]

    scen = cat["scenarios"] or prof_scen
    locs = cat["locations"] or prof_loc
    procs = cat["processes"]

    def _lines(items, fmt):
        return "\n".join(f"    - {fmt(i)}" for i in items[:120]) or "    (ninguno todavia)"

    scen_txt = _lines(scen, lambda t: f"{(t[0] + ' ') if t[0] else ''}{t[1]}")
    loc_txt = _lines(locs, lambda x: x)
    proc_txt = _lines(procs, lambda x: x)

    return (
        "\n\nCATALOGO CANONICO DE LA ORGANIZACION (ya existe en la plataforma).\n"
        "NO crees variantes de estas entidades: mapea lo que menciona el documento\n"
        "a ellas por su significado y referencialas por su NOMBRE EXACTO. Solo crea\n"
        "una entidad nueva si de verdad no encaja en ninguna.\n"
        f"  ESCENARIOS:\n{scen_txt}\n"
        f"  SEDES:\n{loc_txt}\n"
        f"  PROCESOS:\n{proc_txt}\n"
        f"  METODO BIA del cliente: {prof.get('bia_method') or 'no declarado'}\n"
    )


def build_source_map(db, org_id: Optional[int], document: dict,
                     profile: Optional[dict] = None, lang: str = "es",
                     tier: str = "deep", use_cache: bool = True) -> dict:
    """Pasada 2: mapa de volcado y filas extraidas de un documento.

    Con `use_cache`, la lectura de un documento ya visto (misma huella SHA-256)
    se reutiliza en vez de volver a llamar al modelo: hace que re-importar el
    mismo documento sea reproducible y gratis. Poner `use_cache=False` fuerza
    una lectura fresca.
    """
    sha = document.get("sha256")
    if use_cache:
        cached = _cache_get(db, org_id, sha)
        if cached is not None:
            logger.info("ingest: lectura reutilizada de cache para %s",
                        document.get("filename"))
            cached = dict(cached)
            cached["from_cache"] = True
            return cached

    api_key, model = _api_key_and_model(db, org_id, tier)
    profile_block = _catalog_block(db, org_id, profile)

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
    smap = _sanitize_map(parsed, document)

    # Segundo pase: "que te has dejado". La primera lectura tiende a quedarse
    # corta en documentos densos (un BIA de 11 hojas). Aqui se le ensena lo que
    # ya saco y se le pide, expresamente, lo que falta — sin repetir lo que ya
    # tiene. Es lo que hace que no deje datos atras.
    try:
        smap = _gap_fill(db, org_id, document, smap, profile, lang, api_key, model, body)
    except Exception:
        logger.warning("ingest: el pase de completitud fallo; se sigue con lo "
                       "extraido en la primera lectura", exc_info=True)
    # Guardar la lectura completa para que re-importar este documento sea
    # reproducible y no cueste otra llamada al modelo.
    _cache_put(db, org_id, sha, document.get("filename"), smap)
    return smap


def _gap_fill(db, org_id, document, smap, profile, lang, api_key, model, body) -> dict:
    """Pide al modelo lo que se dejo en la primera lectura y lo anade."""
    # Resumen compacto de lo ya extraido: entidad -> cuantas filas y una muestra
    resumen = []
    for u in (smap.get("units") or []):
        rows = u.get("rows") or []
        muestra = "; ".join(
            str((r.get("fields") or {}).get("name")
                or (r.get("fields") or {}).get("code") or "?")[:40]
            for r in rows[:8])
        resumen.append(f"- {u.get('target_entity')}: {len(rows)} filas ya "
                       f"extraidas ({muestra})")
    ya = "\n".join(resumen) or "(nada extraido todavia)"

    system = (
        "Eres un consultor de continuidad revisando si una PRIMERA lectura de un "
        "documento se dejo datos. Tu unica tarea: devolver las filas que FALTAN, "
        "nunca repetir las que ya estan. Se exhaustivo: si el documento tiene una "
        "tabla de 17 procesos y solo se extrajeron 5, devuelve los 12 restantes. "
        "Presta especial atencion a: procesos de negocio, valoraciones del BIA "
        "(cada una con su sede, su escenario y sus impactos), dependencias, y "
        "cualquier tabla o bloque entero que se haya ignorado. Usa SOLO las "
        "entidades y campos del catalogo, y '_ref_<campo>' para enlazar. Si de "
        "verdad no falta nada, devuelve una lista vacia."
        f"\n\nResponde en el idioma: {lang}."
    )
    parsed, _msg = structured_message(
        api_key, model=model, max_tokens=16000, system=system,
        messages=[{
            "role": "user",
            "content": (f"CATALOGO DE ENTIDADES:{contracts.describe_for_prompt()}\n\n"
                        f"YA EXTRAIDO EN LA PRIMERA LECTURA:\n{ya}\n\n"
                        f"DOCUMENTO COMPLETO:\n{body}\n\n"
                        f"Devuelve SOLO lo que falte."),
        }],
        tool_name="anadir_filas_que_faltan",
        tool_description="Entrega unicamente las filas que la primera lectura omitio",
        input_schema=_sourcemap_schema(),
        org_id=org_id, call_type="ingest_gapfill",
    )
    extra = _sanitize_map(parsed, document)
    extra_units = extra.get("units") or []
    added = sum(len(u.get("rows") or []) for u in extra_units)
    if added:
        smap.setdefault("units", []).extend(extra_units)
        smap["gap_filled_rows"] = added
        logger.info("ingest: el pase de completitud anadio %d filas a %s",
                    added, document.get("filename"))
    return smap


def _sanitize_map(parsed: dict, document: dict) -> dict:
    """Filtra unidades hacia entidades desconocidas y filas vacias."""
    valid = set(contracts.entity_keys())
    units = []
    for unit in (parsed.get("units") or []):
        # El modelo, aunque el schema pida objetos, a veces cuela una unit o una
        # fila como texto suelto. No debe tumbar la lectura del documento entero:
        # se descarta lo malformado y se sigue.
        if not isinstance(unit, dict):
            logger.info("ingest: unidad descartada, no es un objeto: %r", str(unit)[:80])
            continue
        entity = unit.get("target_entity")
        if entity not in valid:
            logger.info("ingest: unidad descartada, entidad desconocida %r", entity)
            continue
        rows = [r for r in (unit.get("rows") or [])
                if isinstance(r, dict) and isinstance(r.get("fields"), dict) and r["fields"]]
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
