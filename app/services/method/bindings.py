"""Resolucion del metodo efectivo de una organizacion, con su procedencia.

`resolve()` responde a dos preguntas a la vez, y la segunda es la que hace todo
esto defendible: *que valor uso* y *por que ese*. Un numero en un informe de
continuidad sin saber de donde sale no vale nada delante de un auditor; el mismo
numero con "segun tu ISP_11 §6.3" es una evidencia.

Precedencia: **manual > politica del cliente > defecto de la plataforma**. Un
valor puesto a mano gana siempre, porque alguien lo decidio a sabiendas, y no lo
pisa una reimportacion posterior — mismo criterio que `IngestFieldOverride`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.method import registry

logger = logging.getLogger("riskhub.method.bindings")


@dataclass
class Resolved:
    """Un valor de metodo y de donde sale."""
    key: str
    value: Any
    source: str                 # manual | policy | default
    citation: Optional[dict] = None
    confidence: Optional[float] = None
    statement_id: Optional[int] = None
    is_default: bool = True

    def explain(self) -> str:
        """Frase corta para mostrar junto a la cifra que produce."""
        if self.source == "default":
            return "valor por defecto de la plataforma"
        if self.source == "manual":
            return "fijado manualmente en esta organizacion"
        cite = self.citation or {}
        doc = cite.get("document")
        section = cite.get("section")
        if doc and section:
            return f"segun {doc} {section}"
        if doc:
            return f"segun {doc}"
        return "segun la politica de la organizacion"

    def as_dict(self) -> dict:
        return {"key": self.key, "value": self.value, "source": self.source,
                "citation": self.citation, "confidence": self.confidence,
                "is_default": self.is_default, "explain": self.explain()}


def resolve(db, org_id: Optional[int], key: str) -> Resolved:
    """Valor efectivo de un parametro para una organizacion.

    Nunca lanza: un parametro desconocido o una base sin las tablas devuelve el
    defecto. Un motor de calculo no puede caerse porque falte configuracion.
    """
    param = registry.get(key)
    if param is None:
        logger.warning("method: parametro desconocido %r", key)
        return Resolved(key=key, value=None, source="default")

    binding = _active_binding(db, org_id, key)
    if binding is None:
        return Resolved(key=key, value=param.default(), source="default")

    problem = param.validate(binding.value)
    if problem:
        # Un valor invalido no se aplica en silencio: se registra y se cae al
        # defecto, que es preferible a calcular con algo que el motor no sabe
        # interpretar.
        logger.warning("method: %s tiene un valor invalido (%s); se usa el defecto",
                       key, problem)
        return Resolved(key=key, value=param.default(), source="default")

    return Resolved(
        key=key, value=binding.value,
        source=binding.source or "manual",
        citation=_citation(binding),
        confidence=binding.confidence,
        statement_id=binding.statement_id,
        is_default=False,
    )


def resolve_many(db, org_id: Optional[int], keys) -> dict[str, Resolved]:
    return {k: resolve(db, org_id, k) for k in keys}


def resolve_value(db, org_id: Optional[int], key: str, fallback: Any = None) -> Any:
    """Solo el valor, para los sitios donde la traza no hace falta."""
    resolved = resolve(db, org_id, key)
    return resolved.value if resolved.value is not None else fallback


def _active_binding(db, org_id: Optional[int], key: str):
    if not org_id:
        return None
    try:
        from app.models import MethodBinding
        return db.query(MethodBinding).filter_by(
            organization_id=org_id, parameter_key=key, is_active=True
        ).order_by(MethodBinding.id.desc()).first()
    except Exception:
        logger.debug("method: no se pudo leer el binding de %s", key, exc_info=True)
        return None


def _citation(binding) -> Optional[dict]:
    statement = getattr(binding, "statement", None)
    if statement is None:
        return None
    return {
        "document": statement.source_document,
        "section": statement.source_section,
        "quote": statement.quote,
        "sha256": statement.source_sha256,
    }


# ── Escritura ────────────────────────────────────────────────────────────────

def set_binding(db, org_id: int, key: str, value: Any, *,
                source: str = "manual", statement_id: Optional[int] = None,
                confidence: Optional[float] = None, notes: Optional[str] = None,
                user_id: Optional[int] = None, commit: bool = True):
    """Fija el valor de un parametro. Valida antes de guardar.

    Un valor manual no lo pisa despues una propuesta extraida de un documento:
    `apply_statement` respeta lo que haya con `source == "manual"`.
    """
    param = registry.get(key)
    if param is None:
        raise ValueError(f"Parametro desconocido: {key}")
    problem = param.validate(value)
    if problem:
        raise ValueError(f"{param.label}: {problem}")

    from app.models import MethodBinding
    row = db.query(MethodBinding).filter_by(
        organization_id=org_id, parameter_key=key).first()
    if row is None:
        row = MethodBinding(organization_id=org_id, parameter_key=key)
        db.add(row)
    row.value = value
    row.source = source
    row.statement_id = statement_id
    row.confidence = confidence
    row.notes = notes
    row.applied_by_id = user_id
    row.is_active = True
    if commit:
        db.commit()
    else:
        db.flush()
    return row


def clear_binding(db, org_id: int, key: str, commit: bool = True) -> bool:
    """Vuelve al defecto de la plataforma."""
    from app.models import MethodBinding
    row = db.query(MethodBinding).filter_by(
        organization_id=org_id, parameter_key=key).first()
    if row is None:
        return False
    db.delete(row)
    if commit:
        db.commit()
    return True


def apply_statement(db, org_id: int, statement, *, user_id: Optional[int] = None,
                    force: bool = False, commit: bool = True) -> dict:
    """Convierte una declaracion extraida de un documento en valor efectivo.

    No pisa un valor manual salvo que se fuerce: si alguien lo fijo a sabiendas,
    un documento no le lleva la contraria por su cuenta.
    """
    key = statement.parameter_key
    param = registry.get(key) if key else None
    if param is None:
        return {"applied": False, "reason": "parametro no modelable"}

    existing = _active_binding(db, org_id, key)
    if existing is not None and existing.source == "manual" and not force:
        return {"applied": False, "reason": "hay un valor fijado manualmente"}

    problem = param.validate(statement.proposed_value)
    if problem:
        return {"applied": False, "reason": problem}

    set_binding(db, org_id, key, statement.proposed_value,
                source="policy", statement_id=statement.id,
                confidence=statement.confidence, user_id=user_id, commit=False)
    statement.status = "bound"
    statement.reviewed_by_id = user_id
    statement.reviewed_at = datetime.now(timezone.utc)
    if commit:
        db.commit()
    return {"applied": True, "parameter_key": key, "value": statement.proposed_value}


# ── Vista de conjunto ────────────────────────────────────────────────────────

def method_overview(db, org_id: Optional[int]) -> list[dict]:
    """Todos los parametros con su valor, su origen y si el motor los consume.

    El campo `wired` se muestra tal cual: un parametro declarado pero todavia no
    consumido por su motor se dice, no se disimula.
    """
    out = []
    for key, param in registry.all_params().items():
        resolved = resolve(db, org_id, key)
        out.append({
            "key": key, "module": param.module, "label": param.label,
            "type": param.type, "description": param.description,
            "engine": param.engine, "wired": param.wired,
            "unit": param.unit, "choices": list(param.choices or ()) or None,
            "variables": list(param.variables or ()) or None,
            "normative_ref": param.normative_ref,
            "default": param.default(),
            **resolved.as_dict(),
        })
    return out
