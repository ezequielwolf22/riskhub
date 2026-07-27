"""Consolidacion del catalogo de escenarios tras la ingesta.

Leer cada documento por separado genera variantes del mismo escenario: el BIA
dice "Caida de la infraestructura AWS", un DRP dice "Azure Hosting failure" y
otro "Caida de infraestructura GCP" — son el MISMO escenario de indisponibilidad
de sistemas, descrito con otro proveedor, otro idioma u otras palabras. Sin
consolidar, el cliente ve decenas de escenarios cuando su catalogo real (ISO
22301 / ISP del cliente) tiene del orden de 15-20.

Este paso agrupa las variantes en su escenario canonico con una unica llamada al
modelo (que ve todos los nombres a la vez y entiende que son lo mismo) y luego,
de forma DETERMINISTA, funde: reapunta las valoraciones y estrategias al
superviviente, deduplica y borra las variantes. La IA solo agrupa; el motor
mueve los datos y deja marcha atras por el rastro del lote.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("riskhub.ingest.consolidation")

# Por debajo de esto el catalogo ya es manejable; no se gasta una llamada.
_MIN_TO_CONSOLIDATE = 6

_GROUP_SCHEMA = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "canonical_name": {"type": "string"},
                    "family": {"type": "string",
                               "enum": ["personnel", "systems_comms",
                                        "third_party", "facilities"]},
                    "member_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["canonical_name", "member_ids"],
            },
        },
    },
    "required": ["groups"],
}

_SYSTEM = """Eres un consultor de continuidad (ISO 22301) ordenando el catalogo de
escenarios de indisponibilidad de un cliente. Te doy la lista de escenarios que
se han extraido de su documentacion, y muchos son la MISMA cosa descrita de
formas distintas.

Agrupa en escenarios CANONICOS. Van en el MISMO grupo:
- El mismo escenario con otro proveedor o tecnologia: "Caida de infraestructura
  AWS", "...GCP", "...OVH", "Azure Hosting failure", "Infrastructure incident"
  son UN escenario de indisponibilidad de sistemas. El proveedor no lo cambia.
- El mismo escenario en otro idioma: "Staff incident" = "Huelga/Falta de
  personal"; "Premises incident" = "Indisponibilidad de instalaciones".
- El mismo escenario con otra redaccion: "Ocupacion no autorizada" y "no
  permitida" de las instalaciones son lo mismo.
- Un producto/plataforma concreto que sufre el escenario (6Conecta, Dokify,
  SAGE, SalesForce) NO es un escenario aparte: es el mismo "caida de sistemas de
  producto" o "fallo de terceros"; el producto es una dependencia.

Reglas:
- El "canonical_name" en el idioma del cliente (el de su documento de metodo,
  normalmente espanol), corto y claro. Si uno de los miembros ya tiene el nombre
  canonico bueno, usalo.
- Escenarios que de verdad son distintos van en grupos distintos (de un solo
  miembro si hace falta). No fuerces fusiones entre cosas diferentes.
- TODO id de la lista debe aparecer en exactamente un grupo. No inventes ids.
- Un catalogo canonico razonable tiene 12-22 grupos. Si te salen 40, no has
  consolidado bastante."""


def consolidate_scenarios(db, org_id: Optional[int], *, lang: str = "es",
                          tier: str = "deep") -> dict:
    """Funde las variantes de escenario en su catalogo canonico. Devuelve resumen."""
    from app.models import BCMScenario

    if not org_id:
        return {"before": 0, "after": 0, "merged": 0}
    scenarios = db.query(BCMScenario).filter_by(organization_id=org_id).all()
    if len(scenarios) < _MIN_TO_CONSOLIDATE:
        return {"before": len(scenarios), "after": len(scenarios), "merged": 0}

    try:
        groups = _group_with_llm(db, org_id, scenarios, lang, tier)
    except Exception as exc:
        logger.warning("ingest: la consolidacion de escenarios fallo: %s", exc,
                       exc_info=True)
        return {"before": len(scenarios), "after": len(scenarios), "merged": 0,
                "error": str(exc)[:200]}

    by_id = {s.id: s for s in scenarios}
    merged = 0
    for group in groups:
        ids = [i for i in (group.get("member_ids") or []) if i in by_id]
        if len(ids) < 2:
            # Un solo miembro: como mucho, fija el nombre canonico si es mejor
            if ids and group.get("canonical_name"):
                _rename(by_id[ids[0]], group)
            continue
        survivor = _pick_survivor([by_id[i] for i in ids], group.get("canonical_name"))
        _rename(survivor, group)
        for vid in ids:
            if vid == survivor.id:
                continue
            _repoint(db, org_id, vid, survivor.id)
            db.query(BCMScenario).filter_by(id=vid, organization_id=org_id).delete(
                synchronize_session=False)
            merged += 1
    db.commit()
    after = db.query(BCMScenario).filter_by(organization_id=org_id).count()
    logger.info("ingest: escenarios consolidados %d -> %d (%d fundidos)",
                len(scenarios), after, merged)
    return {"before": len(scenarios), "after": after, "merged": merged}


def _pick_survivor(members, canonical_name):
    """El superviviente: el que ya se llama como el canonico, o el de menor id."""
    if canonical_name:
        norm = canonical_name.strip().lower()
        for m in members:
            if (m.name or "").strip().lower() == norm:
                return m
    return min(members, key=lambda m: m.id)


def _rename(scenario, group) -> None:
    name = (group.get("canonical_name") or "").strip()
    if name and scenario.name != name:
        scenario.name = name
    fam = group.get("family")
    if fam and getattr(scenario, "family", None) != fam:
        scenario.family = fam


def _repoint(db, org_id, victim_id: int, survivor_id: int) -> None:
    """Reapunta al superviviente lo que colgaba de la variante y deduplica.

    Las valoraciones y estrategias apuntan al escenario por clave foranea. Al
    fundir, dos podrian quedar duplicadas (misma sede/escenario): se conserva una.
    """
    from app.models import BCMScenarioAssessment, BCPStrategy

    # Valoraciones: unicas por (escenario, sede). Reapuntar y deduplicar.
    taken = {
        a.location_id for a in db.query(BCMScenarioAssessment).filter_by(
            organization_id=org_id, scenario_id=survivor_id).all()
    }
    for a in db.query(BCMScenarioAssessment).filter_by(
            organization_id=org_id, scenario_id=victim_id).all():
        if a.location_id in taken:
            db.delete(a)          # ya hay valoracion del superviviente en esa sede
        else:
            a.scenario_id = survivor_id
            taken.add(a.location_id)

    # Estrategias: unicas por (escenario, nombre).
    taken_s = {
        (s.name or "").strip().lower() for s in db.query(BCPStrategy).filter_by(
            organization_id=org_id, scenario_id=survivor_id).all()
    }
    for s in db.query(BCPStrategy).filter_by(
            organization_id=org_id, scenario_id=victim_id).all():
        key = (s.name or "").strip().lower()
        if key in taken_s:
            db.delete(s)
        else:
            s.scenario_id = survivor_id
            taken_s.add(key)
    db.flush()


def _group_with_llm(db, org_id, scenarios, lang, tier) -> list[dict]:
    from app.services.ingest.comprehension import _api_key_and_model
    from app.services.claude_client import structured_message

    api_key, model = _api_key_and_model(db, org_id, tier)
    listado = "\n".join(
        f"  id={s.id} [{s.family or '?'}] {s.name}" for s in scenarios)
    parsed, _msg = structured_message(
        api_key, model=model, max_tokens=8000,
        system=_SYSTEM + f"\n\nResponde en el idioma: {lang}.",
        messages=[{"role": "user",
                   "content": f"Escenarios extraidos:\n{listado}\n\n"
                              f"Agrupa en el catalogo canonico."}],
        tool_name="agrupar_escenarios_canonicos",
        tool_description="Agrupa las variantes en escenarios canonicos",
        input_schema=_GROUP_SCHEMA,
        org_id=org_id, call_type="ingest_consolidate",
    )
    return parsed.get("groups") or []
