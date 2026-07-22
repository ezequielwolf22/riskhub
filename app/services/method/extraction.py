"""El agente lee la politica del cliente y extrae SU metodo, con cita.

Se engancha en la pasada 1 de la ingesta, que ya lee el pack entero. La
diferencia con el resto de la comprension es que aqui no se extraen datos sino
**reglas**: como calcula el impacto esta organizacion, cada cuanto prueba, que
umbrales usa.

Dos decisiones sostienen que esto sea fiable:

**Cita literal obligatoria.** Un parametro cambiado "porque lo dice su politica"
no vale nada si no se puede senalar el parrafo. Cada declaracion guarda el texto
tal cual, el documento y la seccion.

**Lo que no encaja no se tira.** Si el agente encuentra una regla que la
plataforma no sabe modelar, se guarda como `unmodelled` con su cita. Es el modo
de fallo honesto — el cliente ve que hay algo suyo que la herramienta todavia no
respeta — y a la vez es la lista priorizada de que parametrizar despues.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.claude_client import structured_message
from app.services.method import registry
from app.services.model_registry import get_model

logger = logging.getLogger("riskhub.method.extraction")

MAX_CORPUS_CHARS = 70000

_SCHEMA = {
    "type": "object",
    "properties": {
        "statements": {
            "type": "array", "maxItems": 40,
            "items": {
                "type": "object",
                "properties": {
                    "parameter_key": {"type": "string"},
                    "proposed_value": {},
                    "quote": {"type": "string", "maxLength": 1000},
                    "source_document": {"type": "string", "maxLength": 255},
                    "source_section": {"type": "string", "maxLength": 255},
                    "interpretation": {"type": "string", "maxLength": 600},
                    "confidence": {"type": "number"},
                },
                "required": ["quote", "interpretation"],
            },
        },
    },
    "required": ["statements"],
}

_SYSTEM = """Eres un consultor GRC leyendo las politicas y procedimientos de un cliente para
averiguar COMO CALCULA ESA ORGANIZACION, no que datos tiene.

Te interesan las frases que fijan un metodo: formulas ("el impacto total es RTO
mas criterio de impacto"), escalas y baremos, umbrales, pesos, cadencias ("se
probara al menos anualmente"), criterios de clasificacion.

Reglas:

- **Cita literal siempre.** Copia en "quote" el texto exacto del documento que
  sostiene la declaracion, y anota el documento y la seccion. Sin cita, la
  declaracion no sirve: no la propongas.
- Si la frase encaja en uno de los parametros del catalogo, pon su
  "parameter_key" y el "proposed_value" con el formato que pida ese parametro.
- **Si NO encaja en ninguno, propon la declaracion igualmente y deja
  "parameter_key" vacio.** Es informacion valiosa: significa que el cliente
  tiene una regla que la plataforma todavia no sabe aplicar, y hay que decirlo.
- No deduzcas metodo de los datos. Que una tabla tenga ciertos valores no
  significa que la politica los exija; solo cuenta lo que el texto afirma.
- Pon "confidence" bajo si la frase es ambigua o si la traduccion al parametro
  es interpretativa."""


def extract_method(db, org_id: Optional[int], documents: list[dict],
                   lang: str = "es") -> list[dict]:
    """Extrae declaraciones de metodo del pack. No escribe en base de datos."""
    from app.routers.ai import _resolve_api_key
    from app.models import AiConfig
    from app.services.ingest.reader import render_for_llm

    cfg = db.query(AiConfig).filter_by(organization_id=org_id).first()
    api_key = _resolve_api_key(cfg)
    if not api_key:
        raise ValueError("No hay API key del agente IA configurada")

    budget = MAX_CORPUS_CHARS // max(1, len(documents))
    corpus = "\n\n".join(
        render_for_llm(doc, max_chars=max(3000, budget)) for doc in documents
    )

    parsed, _msg = structured_message(
        api_key, model=get_model(db, org_id, "deep"), max_tokens=8192,
        system=_SYSTEM + f"\n\nResponde en el idioma: {lang}.",
        messages=[{
            "role": "user",
            "content": (f"CATALOGO DE PARAMETROS DE METODO:"
                        f"{registry.describe_for_prompt()}\n\n"
                        f"DOCUMENTACION DEL CLIENTE:\n{corpus}"),
        }],
        tool_name="registrar_metodo_del_cliente",
        tool_description="Registra las reglas de calculo declaradas por el cliente",
        input_schema=_SCHEMA,
        org_id=org_id, call_type="method_extraction",
    )
    return _sanitize(parsed.get("statements") or [])


def _sanitize(statements: list[dict]) -> list[dict]:
    """Descarta lo que no trae cita y valida las claves contra el registro."""
    out = []
    known = set(registry.keys())
    for st in statements:
        if not (st.get("quote") or "").strip():
            continue                      # sin cita no entra
        key = (st.get("parameter_key") or "").strip() or None
        if key and key not in known:
            # La clave no existe: la declaracion sigue valiendo, pero como no
            # modelable en vez de vinculada a un parametro inventado.
            logger.info("method: clave desconocida %r, se guarda sin vincular", key)
            st["interpretation"] = (
                f"[el agente propuso '{key}', que no existe] "
                + (st.get("interpretation") or "")
            )[:600]
            key = None
        st["parameter_key"] = key
        out.append(st)
    return out


def persist(db, org_id: int, statements: list[dict], *,
            batch_id: Optional[int] = None, auto_apply: bool = True) -> dict:
    """Guarda las declaraciones y aplica las que se puedan aplicar sin riesgo.

    Una declaracion que cambiaria como se calcula algo de lo que YA hay datos no
    se auto-aplica: recalcular en silencio el BIA entero de un cliente porque un
    documento decia otra cosa seria una sorpresa desagradable. Queda propuesta y
    una persona la aplica viendo lo que cambia.
    """
    from app.models import MethodStatement
    from app.services.method.bindings import apply_statement

    result = {"created": 0, "applied": 0, "proposed": 0, "unmodelled": 0}
    for data in statements:
        param = registry.get(data.get("parameter_key")) if data.get("parameter_key") else None
        st = MethodStatement(
            organization_id=org_id,
            parameter_key=data.get("parameter_key"),
            proposed_value=data.get("proposed_value"),
            quote=(data.get("quote") or "")[:2000],
            source_document=(data.get("source_document") or "")[:255] or None,
            source_section=(data.get("source_section") or "")[:255] or None,
            interpretation=(data.get("interpretation") or "")[:2000],
            confidence=data.get("confidence"),
            batch_id=batch_id,
            status="unmodelled" if param is None else "proposed",
        )
        db.add(st)
        db.flush()
        result["created"] += 1

        if param is None:
            result["unmodelled"] += 1
            continue

        if not auto_apply or has_dependent_data(db, org_id, param.key):
            result["proposed"] += 1
            continue

        applied = apply_statement(db, org_id, st, commit=False)
        if applied.get("applied"):
            result["applied"] += 1
        else:
            result["proposed"] += 1

    db.commit()
    return result


# Que datos dependen de cada parametro. Si ya existen, cambiar el parametro
# recalcularia cifras que el cliente ya ha visto: eso lo aprueba una persona.
_DEPENDENT_DATA = {
    "bcm": ("BCMScenarioAssessment",),
    "risk": ("Risk",),
    "tprm": ("Supplier",),
}


def has_dependent_data(db, org_id: Optional[int], key: str) -> bool:
    param = registry.get(key)
    if param is None or not org_id:
        return False
    from app import models
    for model_name in _DEPENDENT_DATA.get(param.module, ()):
        model = getattr(models, model_name, None)
        if model is None:
            continue
        try:
            if db.query(model).filter_by(organization_id=org_id).limit(1).count():
                return True
        except Exception:
            logger.debug("method: no se pudo comprobar %s", model_name, exc_info=True)
    return False
