"""Contradicciones entre documentos.

Es la norma, no la excepcion: el BIA fija el RTO de un sistema en 4 horas y el
DRP del mismo sistema dice 6. Los dos documentos existen, los dos estan
aprobados y los dos dicen cosas distintas.

Politica del motor: **gana el valor mas restrictivo**. En continuidad de
negocio equivocarse por prudencia es lo correcto — planificar para 4 horas y
tener 6 es un margen; planificar para 6 y tener 4 es un incumplimiento. La
politica se declara campo a campo en el `FieldSpec`, porque "mas restrictivo"
significa `min` en un RTO y `max` en una criticidad.

Lo que nunca ocurre es que un valor desaparezca en silencio: el descartado
queda en `ingest_conflicts` con el documento del que salio, para que se pueda
revisar y cambiar la decision.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("riskhub.ingest.conflicts")

# Orden de severidad para campos categoricos, de menos a mas grave. Permite
# aplicar min/max sobre valores que no son numeros.
_ORDINAL_SCALES = {
    "criticality": ("low", "medium", "high", "critical"),
    "impact_band": ("none", "trivial", "relevant", "severe", "critical"),
    "priority": ("low", "medium", "high", "critical"),
    "risk_level": ("LOW", "MEDIUM", "HIGH", "CRITICAL"),
}


class Candidate:
    """Un valor propuesto para un campo, con la fuente de la que salio."""

    __slots__ = ("value", "source_filename", "source_ref", "sha256",
                 "confidence", "document_date")

    def __init__(self, value: Any, source_filename: str = None,
                 source_ref: str = None, sha256: str = None,
                 confidence: float = None, document_date=None):
        self.value = value
        self.source_filename = source_filename
        self.source_ref = source_ref
        self.sha256 = sha256
        self.confidence = confidence
        self.document_date = document_date

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "source_filename": self.source_filename,
            "source_ref": self.source_ref,
            "sha256": self.sha256,
            "confidence": self.confidence,
            "document_date": (self.document_date.isoformat()
                              if hasattr(self.document_date, "isoformat")
                              else self.document_date),
        }


def _ordinal(field_name: str, value: Any) -> Optional[int]:
    scale = _ORDINAL_SCALES.get(field_name)
    if not scale or value is None:
        return None
    try:
        return scale.index(str(value).strip().lower() if field_name != "risk_level"
                           else str(value).strip().upper())
    except ValueError:
        return None


def _numeric(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def resolve(field_name: str, policy: str, candidates: list[Candidate]) -> dict:
    """Elige el valor ganador entre varios candidatos.

    Devuelve {value, policy, decided, reason, discarded}. `decided` a False
    significa que el motor no ha querido decidir y hace falta una persona.
    """
    usable = [c for c in candidates if c.value not in (None, "")]
    if not usable:
        return {"value": None, "policy": policy, "decided": True,
                "reason": "sin candidatos", "discarded": []}
    if len(usable) == 1:
        return {"value": usable[0].value, "policy": policy, "decided": True,
                "reason": "valor unico", "discarded": []}

    # Todos coinciden: no hay conflicto real
    distinct = {_comparable(c.value) for c in usable}
    if len(distinct) == 1:
        return {"value": usable[0].value, "policy": policy, "decided": True,
                "reason": "todas las fuentes coinciden", "discarded": []}

    if policy == "manual":
        return {"value": None, "policy": policy, "decided": False,
                "reason": "el campo exige decision humana",
                "discarded": [c.as_dict() for c in usable]}

    if policy == "first":
        winner = usable[0]
        reason = "primera fuente que lo declaro"
    elif policy == "latest":
        dated = [c for c in usable if c.document_date]
        if dated:
            winner = max(dated, key=lambda c: c.document_date)
            reason = "documento mas reciente"
        else:
            winner = usable[-1]
            reason = "ultima fuente leida (ninguna trae fecha)"
    elif policy in ("min", "max"):
        winner, reason = _extreme(field_name, policy, usable)
    else:  # pragma: no cover - CONFLICT_POLICIES lo impide
        winner, reason = usable[0], "politica desconocida"

    discarded = [c.as_dict() for c in usable if c is not winner]
    return {"value": winner.value, "policy": policy, "decided": True,
            "reason": reason, "discarded": discarded}


def _extreme(field_name: str, policy: str, usable: list[Candidate]):
    """Aplica min/max sobre numeros o sobre una escala ordinal conocida."""
    keyed = []
    for c in usable:
        k = _numeric(c.value)
        if k is None:
            k = _ordinal(field_name, c.value)
        if k is not None:
            keyed.append((k, c))

    if not keyed:
        # Ni numero ni escala conocida: no se inventa un orden.
        return usable[0], "valores no comparables, se conserva el primero"

    if policy == "min":
        winner = min(keyed, key=lambda t: t[0])[1]
        reason = "valor mas exigente (el menor)"
    else:
        winner = max(keyed, key=lambda t: t[0])[1]
        reason = "valor mas alto"
    return winner, reason


def _comparable(value: Any):
    if isinstance(value, (dict, list)):
        return str(value)
    if isinstance(value, str):
        return value.strip().lower()
    return value


def record_conflict(db, org_id: Optional[int], batch_id: Optional[int],
                    entity: str, table_name: str, record_id: Optional[int],
                    field_name: str, candidates: list[Candidate],
                    resolution: dict) -> None:
    """Deja constancia del conflicto y de lo que se descarto.

    Best-effort: un fallo registrando la traza nunca debe tumbar la ingesta.
    """
    from app.models import IngestConflict
    try:
        db.add(IngestConflict(
            organization_id=org_id,
            batch_id=batch_id,
            entity=entity,
            table_name=table_name,
            record_id=record_id,
            field_name=field_name,
            candidates=[c.as_dict() for c in candidates],
            policy=resolution.get("policy"),
            resolved_value=resolution.get("value"),
            status="auto_resolved" if resolution.get("decided") else "pending",
            resolved_at=(datetime.now(timezone.utc)
                         if resolution.get("decided") else None),
        ))
        db.flush()
    except Exception:
        logger.warning("ingest: no se pudo registrar el conflicto de %s.%s",
                       table_name, field_name, exc_info=True)
