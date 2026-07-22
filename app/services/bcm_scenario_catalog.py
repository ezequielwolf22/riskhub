"""Catalogo del sistema: escenarios de indisponibilidad y baremos de referencia.

Mismo patron que `tprm_templates.SYSTEM_TEMPLATES`: datos del sistema que no se
editan, que cada organizacion CLONA al activar el modulo y adapta despues. Sin
esto, una organizacion nueva empieza con una matriz de cobertura vacia y sin
saber por donde empezar.

Los 17 escenarios de `ISO22301_17` estan repartidos en las cuatro familias de
indisponibilidad (personas, sistemas y comunicaciones, terceros, instalaciones)
que usa el metodo BIA mas extendido en la practica espanola. Son un punto de
partida generico y editable, no una verdad: el escenario de infraestructura
cloud se nombra por lo que es, y cada cliente lo concretara con su proveedor.

Los baremos son igual de importantes que los escenarios y se ofrecen aparte,
porque la forma de combinarlos cambia el resultado: `BAREMO_PRODUCTO` pondera
el impacto por un factor de RTO, mientras que `BAREMO_SUMA` los suma
("RTO + Criterio de impacto = Impacto total"). Ambos se usan en la practica.
"""
from __future__ import annotations

from typing import Optional

# ── Escenarios ───────────────────────────────────────────────────────────────

ISO22301_17: list[dict] = [
    # Indisponibilidad de personas
    {"code": "ESC-P01", "family": "personnel", "name": "Huelga de personal",
     "description": "Paro laboral que deja sin cobertura funciones criticas."},
    {"code": "ESC-P02", "family": "personnel", "name": "Situacion de pandemia",
     "description": "Emergencia sanitaria que impide la presencia fisica del "
                    "personal o reduce la plantilla disponible."},
    {"code": "ESC-P03", "family": "personnel", "name": "Accidentes laborales",
     "description": "Siniestro que afecta a personas y, si ocurre en las "
                    "instalaciones, tambien a su disponibilidad."},
    {"code": "ESC-P04", "family": "personnel", "name": "Falta de personal",
     "description": "Bajas, rotacion o ausencia de perfiles clave sin relevo."},

    # Indisponibilidad de sistemas y comunicaciones
    {"code": "ESC-S01", "family": "systems_comms",
     "name": "Caida de las comunicaciones",
     "description": "Perdida de conectividad de red o telefonia."},
    {"code": "ESC-S02", "family": "systems_comms",
     "name": "Caida de los sistemas de producto",
     "description": "Indisponibilidad de las plataformas que sostienen el "
                    "servicio prestado a clientes."},
    {"code": "ESC-S03", "family": "systems_comms",
     "name": "Caida de la infraestructura cloud",
     "description": "Interrupcion del proveedor de infraestructura o de una de "
                    "sus regiones o zonas de disponibilidad."},
    {"code": "ESC-S04", "family": "systems_comms",
     "name": "Ataques de ciberseguridad con impacto en negocio",
     "description": "Incidente de seguridad (ransomware, intrusion, denegacion "
                    "de servicio) que interrumpe la operacion."},

    # Indisponibilidad de terceros
    {"code": "ESC-T01", "family": "third_party", "name": "Corte del suministro",
     "description": "Interrupcion de suministros esenciales prestados por un "
                    "tercero (energia, agua, conectividad)."},
    {"code": "ESC-T02", "family": "third_party",
     "name": "Errores o indisponibilidad del software que da soporte a la actividad",
     "description": "Fallo de una aplicacion de terceros necesaria para operar."},
    {"code": "ESC-T03", "family": "third_party",
     "name": "Cese de actividad de un proveedor o empresa subcontratada",
     "description": "Quiebra, resolucion de contrato o abandono del servicio."},
    {"code": "ESC-T04", "family": "third_party",
     "name": "Interrupcion de servicios y recursos esenciales",
     "description": "Degradacion grave de un servicio externo critico."},
    {"code": "ESC-T05", "family": "third_party",
     "name": "Falta de stock de material necesario para la actividad",
     "description": "Rotura de suministro de material o equipamiento."},

    # Indisponibilidad de instalaciones
    {"code": "ESC-I01", "family": "facilities",
     "name": "Indisponibilidad de instalaciones por factores externos",
     "description": "Huelgas, atentados, amenazas o cortes de acceso que "
                    "impiden ocupar las instalaciones."},
    {"code": "ESC-I02", "family": "facilities",
     "name": "Ocupacion no permitida o forzada de las instalaciones",
     "description": "Ocupacion ilegitima que impide el uso normal de la sede."},
    {"code": "ESC-I03", "family": "facilities",
     "name": "Desastres naturales",
     "description": "Incendio, inundacion, terremoto u otro evento natural que "
                    "danna o inutiliza las instalaciones."},
    {"code": "ESC-I04", "family": "facilities",
     "name": "Fallo fisico en las instalaciones",
     "description": "Averia tecnica o error humano en instalaciones o "
                    "servicios del edificio."},
]

CATALOGS: dict[str, dict] = {
    "iso22301_17": {
        "code": "iso22301_17",
        "name": "Escenarios de indisponibilidad (4 familias)",
        "description": ("Catalogo de referencia con 17 escenarios repartidos en "
                        "personas, sistemas y comunicaciones, terceros e "
                        "instalaciones."),
        "scenarios": ISO22301_17,
    },
}


# ── Baremos ──────────────────────────────────────────────────────────────────

_DIMENSIONS = [
    {"key": "operational",  "label": "Operativo"},
    {"key": "financial",    "label": "Financiero"},
    {"key": "people",       "label": "Personas"},
    {"key": "regulatory",   "label": "Regulatorio"},
    {"key": "reputational", "label": "Reputacional"},
]

_LEVELS = [
    {"value": 1, "score": 0, "label": "Sin impacto"},
    {"value": 2, "score": 1, "label": "Trivial"},
    {"value": 3, "score": 2, "label": "Relevante"},
    {"value": 4, "score": 3, "label": "Severo"},
    {"value": 5, "score": 4, "label": "Critico"},
]

# Escala de RTO de nueve niveles: cuanto menos puede esperar el proceso, mayor
# es el valor. Se usa como factor (producto) o como sumando (suma).
_RTO_SCALE = [
    {"label": "No puede interrumpirse nunca", "hours": 0,   "factor": 1.5},
    {"label": "Mas de 1 semana",              "hours": 336, "factor": 1.2},
    {"label": "1 semana",                     "hours": 168, "factor": 1.1},
    {"label": "3 dias",                       "hours": 72,  "factor": 1.0},
    {"label": "24 horas",                     "hours": 24,  "factor": 0.9},
    {"label": "12 horas",                     "hours": 12,  "factor": 0.8},
    {"label": "6 horas",                      "hours": 6,   "factor": 0.7},
    {"label": "4 horas",                      "hours": 4,   "factor": 0.6},
    {"label": "1 hora",                       "hours": 1,   "factor": 0.5},
]

_BANDS = [
    {"key": "none",     "label": "Sin impacto", "min": 0.0, "max": 0.2},
    {"key": "trivial",  "label": "Trivial",     "min": 0.3, "max": 0.8},
    {"key": "relevant", "label": "Relevante",   "min": 0.8, "max": 1.2},
    {"key": "severe",   "label": "Severo",      "min": 1.2, "max": 2.8},
    {"key": "critical", "label": "Critico",     "min": 2.8, "max": 4.0},
]

BAREMOS: dict[str, dict] = {
    "producto": {
        "code": "producto",
        "name": "Impacto ponderado por RTO (producto)",
        "description": ("El impacto se multiplica por el factor del RTO. Prima "
                        "los procesos que no pueden esperar."),
        "dimensions": _DIMENSIONS, "levels": _LEVELS,
        "horizons": ["0h", ">1h", ">4h", ">6h"],
        "rto_scale": _RTO_SCALE, "bands": _BANDS,
        "aggregation": "max", "combination": "product",
    },
    "suma": {
        "code": "suma",
        "name": "RTO + criterio de impacto (suma)",
        "description": ("El valor numerico del RTO se suma al criterio de "
                        "impacto: 'RTO + Criterio de impacto = Impacto total'."),
        "dimensions": _DIMENSIONS, "levels": _LEVELS,
        "horizons": ["0h", ">1h", ">4h", ">6h"],
        "rto_scale": _RTO_SCALE, "bands": _BANDS,
        "aggregation": "max", "combination": "sum",
    },
}


# ── API ──────────────────────────────────────────────────────────────────────

def list_catalogs() -> list[dict]:
    return [{"code": c["code"], "name": c["name"],
             "description": c["description"], "scenarios": len(c["scenarios"])}
            for c in CATALOGS.values()]


def list_baremos() -> list[dict]:
    return [{"code": b["code"], "name": b["name"],
             "description": b["description"], "combination": b["combination"]}
            for b in BAREMOS.values()]


def seed_catalog(db, org_id: int, catalog_code: str = "iso22301_17",
                 baremo_code: Optional[str] = None) -> dict:
    """Clona el catalogo del sistema en una organizacion.

    Idempotente: no duplica los escenarios que ya existan (por codigo o por
    nombre) ni pisa el baremo que la organizacion ya tenga declarado — el
    metodo del cliente manda siempre sobre el de referencia.
    """
    from app.models import BCMScenario, BIACriteria
    from app.services.ingest.reconciler import normalize_name

    catalog = CATALOGS.get(catalog_code)
    if not catalog:
        raise ValueError(f"Catalogo desconocido: {catalog_code}")

    existing = db.query(BCMScenario).filter_by(organization_id=org_id).all()
    codes = {(s.code or "").strip().lower() for s in existing}
    names = {normalize_name(s.name) for s in existing}

    created = 0
    for item in catalog["scenarios"]:
        if item["code"].lower() in codes or normalize_name(item["name"]) in names:
            continue
        db.add(BCMScenario(
            organization_id=org_id, code=item["code"], name=item["name"],
            family=item["family"], description=item.get("description"),
            source="system", is_active=True,
        ))
        created += 1

    baremo_applied = None
    if baremo_code:
        baremo = BAREMOS.get(baremo_code)
        if not baremo:
            raise ValueError(f"Baremo desconocido: {baremo_code}")
        row = db.query(BIACriteria).filter_by(organization_id=org_id).first()
        if row is None:
            row = BIACriteria(organization_id=org_id)
            db.add(row)
            for key in ("dimensions", "levels", "horizons", "rto_scale",
                        "bands", "aggregation", "combination"):
                setattr(row, key, baremo[key])
            baremo_applied = baremo_code

    db.commit()
    return {
        "catalog": catalog_code,
        "scenarios_created": created,
        "scenarios_skipped": len(catalog["scenarios"]) - created,
        "baremo_applied": baremo_applied,
    }
