"""Contrato entre el motor de ingesta y los modulos que lo consumen.

Un modulo declara QUE entidades sabe materializar y COMO se identifican; el
motor no sabe nada de continuidad de negocio, de activos ni de proveedores.
Enchufar un modulo nuevo es escribir sus `EntitySpec`, no tocar el motor.

Dos decisiones viven aqui y son las que dan robustez al conjunto:

- **Claves naturales**: como reconocer que "AMAZON WEB SERVICES, INC." del
  documento y el proveedor "Amazon Web Services" de la base son el mismo. Sin
  esto, cada importacion duplica el inventario.

- **Politica de conflicto por campo**: cuando dos documentos discrepan, que
  valor gana. No es una decision global: en un RTO gana el mas exigente
  (`min`), en una criticidad gana la mas alta (`max`), y en un texto
  descriptivo gana el documento mas reciente (`latest`). Declararlo campo a
  campo es lo que permite resolver contradicciones sin preguntar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Politicas de resolucion de conflicto entre documentos.
#   min     el valor mas exigente gana (RTO, RPO, MTPD)
#   max     el valor mas alto gana (criticidad, impacto)
#   latest  gana el documento mas reciente
#   first   gana el primero que lo declaro (no se pisa)
#   manual  no se decide: se marca y espera a una persona
CONFLICT_POLICIES = ("min", "max", "latest", "first", "manual")


@dataclass(frozen=True)
class FieldSpec:
    """Un campo materializable de una entidad."""
    name: str
    type: str = "str"                 # str|int|float|bool|json|datetime
    conflict_policy: str = "latest"
    max_length: Optional[int] = None
    choices: Optional[tuple] = None
    # Campo calculado por un motor determinista: la ingesta NUNCA lo escribe.
    computed: bool = False

    def __post_init__(self):
        if self.conflict_policy not in CONFLICT_POLICIES:
            raise ValueError(
                f"{self.name}: politica de conflicto invalida "
                f"'{self.conflict_policy}' (validas: {', '.join(CONFLICT_POLICIES)})"
            )


@dataclass(frozen=True)
class EntitySpec:
    """Una entidad que el motor sabe crear o actualizar."""
    key: str                          # identificador estable: "bcm_scenario"
    model: str                        # nombre de la clase en app.models
    label: str                        # etiqueta legible
    fields: tuple[FieldSpec, ...]
    # Combinaciones de campos que identifican al registro. Se prueban en orden;
    # la primera que case, gana.
    natural_keys: tuple[tuple[str, ...], ...] = ()
    # Entidades que deben materializarse antes que esta (los escenarios antes
    # que sus valoraciones). Determina el orden de ejecucion del mapa.
    depends_on: tuple[str, ...] = ()
    # Campos que referencian a otra entidad del lote por su clave natural:
    # {"scenario_id": ("bcm_scenario", "code")}
    references: dict = field(default_factory=dict)
    # Normalizador especifico de la entidad (p.ej. quitar sufijos societarios)
    normalizer: Optional[Callable[[str], str]] = None
    # Si el modulo quiere post-procesar la fila antes de escribirla
    before_write: Optional[Callable[[Any, dict], dict]] = None
    # Tras insertar, cuando hace falta el id para completar el registro (los
    # codigos correlativos del tipo SUP-0007 se asignan asi en todo RiskHub).
    after_write: Optional[Callable[[Any, Any], None]] = None
    # Valores para columnas obligatorias que el documento nunca trae.
    defaults: dict = field(default_factory=dict)
    # Columnas obligatorias que rellena `before_write`. Sin declararlas, la
    # validacion previa descartaria la fila por "falta el codigo" justo antes
    # de que el hook lo generase.
    provided_by_hook: tuple[str, ...] = ()

    def field_map(self) -> dict:
        return {f.name: f for f in self.fields}

    def writable_fields(self) -> tuple:
        return tuple(f for f in self.fields if not f.computed)


_REGISTRY: dict[str, EntitySpec] = {}


def register(spec: EntitySpec) -> EntitySpec:
    """Da de alta una entidad destino. Idempotente por clave."""
    for fname, ref in (spec.references or {}).items():
        if not isinstance(ref, (tuple, list)) or len(ref) != 2:
            raise ValueError(
                f"{spec.key}.references['{fname}'] debe ser (entidad, campo_clave)"
            )
    _REGISTRY[spec.key] = spec
    return spec


def get(key: str) -> Optional[EntitySpec]:
    _ensure_loaded()
    return _REGISTRY.get(key)


def all_specs() -> dict[str, EntitySpec]:
    _ensure_loaded()
    return dict(_REGISTRY)


def ordered_keys() -> list[str]:
    """Entidades en orden de materializacion, respetando `depends_on`.

    Un ciclo de dependencias no puede romper una importacion: se rompe por el
    orden de declaracion y se registra, en vez de lanzar.
    """
    _ensure_loaded()
    resolved: list[str] = []
    visiting: set[str] = set()

    def visit(key: str) -> None:
        if key in resolved or key in visiting:
            return
        visiting.add(key)
        spec = _REGISTRY.get(key)
        for dep in (spec.depends_on if spec else ()):
            if dep in _REGISTRY:
                visit(dep)
        visiting.discard(key)
        if key not in resolved:
            resolved.append(key)

    for key in _REGISTRY:
        visit(key)
    return resolved


def describe_for_prompt(keys: Optional[tuple] = None) -> str:
    """Catalogo de entidades destino, legible por el modelo.

    Se genera del registro y no a mano: si manana un campo cambia de tipo o de
    vocabulario, el prompt se entera solo. Un catalogo escrito aparte se
    desincroniza en la segunda semana y el modelo empieza a proponer campos que
    el motor descarta en silencio.
    """
    _ensure_loaded()
    lines: list[str] = []
    for key in ordered_keys():
        if keys and key not in keys:
            continue
        spec = _REGISTRY[key]
        lines.append(f"\n### {key}  ({spec.label})")
        if spec.natural_keys:
            ident = " o ".join("+".join(k) for k in spec.natural_keys)
            lines.append(f"  se identifica por: {ident}")
        for ref_field, (target, target_key) in (spec.references or {}).items():
            lines.append(
                f"  referencia: usa \"_ref_{ref_field}\" con el {target_key} "
                f"del {target} correspondiente (nunca un id numerico)"
            )
        for f in spec.writable_fields():
            if f.name in (spec.references or {}):
                continue   # se rellena por _ref_, no directamente
            bits = [f.type]
            if f.choices:
                bits.append("uno de: " + "|".join(str(c) for c in f.choices))
            if f.max_length:
                bits.append(f"max {f.max_length}")
            lines.append(f"  - {f.name} ({', '.join(bits)})")
        computed = [f.name for f in spec.fields if f.computed]
        if computed:
            lines.append(f"  NO extraigas (los calcula el motor): {', '.join(computed)}")
    return "\n".join(lines)


def entity_keys() -> list[str]:
    _ensure_loaded()
    return list(_REGISTRY)


_loaded = False


def _ensure_loaded() -> None:
    """Carga perezosa de los modulos que registran entidades.

    Evita el ciclo de importacion: los modulos de destino importan `contracts`
    para declarar sus especificaciones.
    """
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from app.services.ingest import bcp_targets  # noqa: F401
    except Exception:  # pragma: no cover - defensivo
        import logging
        logging.getLogger("riskhub.ingest").warning(
            "No se pudieron cargar las entidades destino de BCP", exc_info=True
        )
