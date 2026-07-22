"""Catalogo de lo que cada organizacion puede declarar como SU metodo.

La plataforma calcula muchas cosas: el impacto de un escenario, el nivel de un
riesgo, el riesgo inherente de un proveedor, cada cuanto hay que probar un plan.
Cada uno de esos calculos lleva dentro decisiones — una escala, un umbral, unos
pesos, una formula — que en el mundo real las fija cada organizacion en su
politica aprobada, y que hasta ahora estaban cableadas en el codigo.

Aqui se declara **que es configurable**. Es un catalogo en codigo, no en base de
datos, por tres motivos: se revisa en el diff, no puede desincronizarse de los
motores que lo consumen, y da a la IA un vocabulario cerrado al que vincular lo
que lea en los documentos del cliente.

El campo `wired` es deliberado y se muestra en la interfaz: un parametro puede
estar declarado pero todavia no consumido por su motor. Decirlo es mas honesto
que ocultarlo, y ademas convierte esta tabla en la lista priorizada de lo que
queda por parametrizar.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("riskhub.method.registry")

PARAM_TYPES = ("enum", "number", "scale", "weights", "formula", "cadence",
               "matrix", "bands", "dimensions", "fields")

MODULES = ("bcm", "risk", "tprm")


@dataclass(frozen=True)
class MethodParameter:
    """Un punto de decision de un motor que la organizacion puede fijar."""
    key: str
    module: str
    label: str
    type: str
    description: str
    # El defecto se resuelve perezosamente: evita importar los motores al
    # cargar el registro y garantiza que el defecto mostrado es el real.
    default_factory: Callable[[], Any]
    engine: str                                   # donde se consume
    choices: Optional[tuple] = None
    variables: Optional[tuple] = None             # solo para type="formula"
    unit: Optional[str] = None
    wired: bool = False                           # el motor ya lo consume
    normative_ref: Optional[str] = None           # clausula que lo acota
    validator: Optional[Callable[[Any], Optional[str]]] = None

    def default(self) -> Any:
        try:
            return self.default_factory()
        except Exception:
            logger.warning("method: no se pudo resolver el defecto de %s",
                           self.key, exc_info=True)
            return None

    def validate(self, value: Any) -> Optional[str]:
        """Devuelve el motivo del rechazo, o None si el valor sirve."""
        if self.choices and value not in self.choices:
            return (f"Valor no admitido. Opciones: "
                    f"{', '.join(str(c) for c in self.choices)}.")
        if self.type == "number" and not isinstance(value, (int, float)):
            return "Debe ser un numero."
        if self.type == "cadence":
            if not isinstance(value, (int, float)) or value <= 0:
                return "Debe ser un numero de meses mayor que cero."
        if self.type == "formula":
            from app.services.method.formula import FormulaError, parse
            try:
                parse(str(value), self.variables or ())
            except FormulaError as exc:
                return str(exc)
        if self.type in ("weights",) and isinstance(value, dict):
            total = sum(v for v in value.values() if isinstance(v, (int, float)))
            if total <= 0:
                return "Los pesos deben sumar mas de cero."
        if self.validator:
            return self.validator(value)
        return None


_REGISTRY: dict[str, MethodParameter] = {}


def register(param: MethodParameter) -> MethodParameter:
    if param.type not in PARAM_TYPES:
        raise ValueError(f"{param.key}: tipo desconocido '{param.type}'")
    if param.module not in MODULES:
        raise ValueError(f"{param.key}: modulo desconocido '{param.module}'")
    _REGISTRY[param.key] = param
    return param


def get(key: str) -> Optional[MethodParameter]:
    return _REGISTRY.get(key)


def all_params() -> dict[str, MethodParameter]:
    return dict(_REGISTRY)


def by_module(module: str) -> list[MethodParameter]:
    return [p for p in _REGISTRY.values() if p.module == module]


def keys() -> list[str]:
    return list(_REGISTRY)


def describe_for_prompt() -> str:
    """Vocabulario cerrado para que la IA vincule lo que lee a un parametro.

    Se genera del registro: un catalogo escrito aparte se desincroniza y el
    modelo empieza a proponer claves que nadie consume.
    """
    lines: list[str] = []
    for module in MODULES:
        params = by_module(module)
        if not params:
            continue
        lines.append(f"\n### Modulo {module}")
        for p in params:
            bits = [p.type]
            if p.choices:
                bits.append("uno de: " + "|".join(str(c) for c in p.choices))
            if p.unit:
                bits.append(p.unit)
            if p.variables:
                bits.append("variables: " + ", ".join(p.variables))
            lines.append(f"  - {p.key} ({', '.join(bits)}): {p.description}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# CATALOGO
# ══════════════════════════════════════════════════════════════════════════════

def _bcm_default(field_name: str):
    def _get():
        from app.services.bcm_scenario_engine import DEFAULT_CRITERIA
        return DEFAULT_CRITERIA[field_name]
    return _get


# ── Continuidad de negocio ───────────────────────────────────────────────────

register(MethodParameter(
    key="bcm.impact.dimensions", module="bcm", type="dimensions",
    label="Dimensiones de impacto",
    description=("Dimensiones con las que la organizacion valora el impacto de "
                 "una interrupcion (operativo, financiero, personas...)."),
    default_factory=_bcm_default("dimensions"),
    engine="bcm_scenario_engine.weighted_impact", wired=True,
))

register(MethodParameter(
    key="bcm.impact.levels", module="bcm", type="scale",
    label="Escala de niveles de impacto",
    description="Niveles de la escala de impacto y su puntuacion numerica.",
    default_factory=_bcm_default("levels"),
    engine="bcm_scenario_engine.weighted_impact", wired=True,
))

register(MethodParameter(
    key="bcm.impact.horizons", module="bcm", type="scale",
    label="Horizontes temporales del BIA",
    description=("Momentos en los que se valora el impacto tras la "
                 "interrupcion (0h, >1h, >4h...)."),
    default_factory=_bcm_default("horizons"),
    engine="bcm_scenario_engine.weighted_impact", wired=True,
))

register(MethodParameter(
    key="bcm.impact.aggregation", module="bcm", type="enum",
    label="Agregacion entre dimensiones",
    description=("Como se combina el impacto de las distintas dimensiones "
                 "dentro de un mismo horizonte."),
    choices=("max", "avg"),
    default_factory=_bcm_default("aggregation"),
    engine="bcm_scenario_engine.weighted_impact", wired=True,
))

register(MethodParameter(
    key="bcm.impact.combination", module="bcm", type="enum",
    label="Combinacion del impacto con el RTO",
    description=("Si el valor del RTO multiplica al impacto ('product') o se "
                 "le suma ('sum', como en 'RTO + criterio de impacto = "
                 "impacto total')."),
    choices=("product", "sum"),
    default_factory=_bcm_default("combination"),
    engine="bcm_scenario_engine.weighted_impact", wired=True,
))

register(MethodParameter(
    key="bcm.rto.scale", module="bcm", type="scale",
    label="Baremo de RTO",
    description=("Niveles de tiempo objetivo de recuperacion y su valor "
                 "numerico o factor."),
    default_factory=_bcm_default("rto_scale"),
    engine="bcm_scenario_engine.rto_factor", wired=True,
))

register(MethodParameter(
    key="bcm.impact.bands", module="bcm", type="bands",
    label="Bandas del impacto ponderado",
    description="Intervalos que traducen la cifra final a critico/severo/...",
    default_factory=_bcm_default("bands"),
    engine="bcm_scenario_engine.band_for", wired=True,
))

register(MethodParameter(
    key="bcm.impact.formula", module="bcm", type="formula",
    label="Formula propia del impacto",
    description=("Formula alternativa si el metodo no se puede expresar con "
                 "agregacion y combinacion. Deja vacio para usar el metodo "
                 "declarado arriba."),
    variables=("impact", "rto", "dimensions_max", "dimensions_avg"),
    default_factory=lambda: None,
    engine="bcm_scenario_engine.weighted_impact", wired=True,
))

register(MethodParameter(
    key="bcm.test.frequency_months", module="bcm", type="cadence",
    label="Frecuencia de las pruebas de continuidad",
    description="Cada cuantos meses debe ejercitarse cada escenario o plan.",
    unit="meses", default_factory=lambda: 12,
    engine="bcm_scenario_engine.coverage_gaps", wired=True,
    normative_ref="ISO 22301:2019 cl. 8.5",
))

register(MethodParameter(
    key="bcm.iso22301.clause_weights", module="bcm", type="weights",
    label="Peso de cada clausula ISO 22301",
    description=("Cuanto pesa cada clausula en el porcentaje de conformidad "
                 "del SGCN. Por defecto se reparte a partes iguales."),
    default_factory=lambda: None,
    engine="bcp_service.iso22301_status", wired=False,
))

register(MethodParameter(
    key="bcm.bia.required_fields", module="bcm", type="fields",
    label="Campos exigidos en el BIA",
    description="Que campos debe tener un proceso para dar el BIA por completo.",
    default_factory=lambda: None,
    engine="bcp_service.bia_completeness", wired=False,
))


# ── Riesgo (ISO 27005) ───────────────────────────────────────────────────────

def _default_risk_matrix():
    from app.services.risk_engine import default_matrix
    return default_matrix()


register(MethodParameter(
    key="risk.matrix", module="risk", type="matrix",
    label="Matriz de riesgo",
    description=("Matriz que cruza consecuencia y probabilidad para dar el "
                 "nivel de riesgo."),
    default_factory=_default_risk_matrix,
    engine="risk_engine.calc_level", wired=True,
))

register(MethodParameter(
    key="risk.bands", module="risk", type="bands",
    label="Bandas de nivel de riesgo",
    description="Umbrales que traducen el nivel 0-8 a bajo/medio/alto/critico.",
    default_factory=lambda: None,
    engine="risk_engine.get_risk_bands", wired=True,
))

register(MethodParameter(
    key="risk.appetite_level", module="risk", type="number",
    label="Apetito de riesgo",
    description="Nivel a partir del cual un riesgo residual exige tratamiento.",
    default_factory=lambda: None,
    engine="risk_recalc_service", wired=False,
))


# ── Terceros (TPRM) ──────────────────────────────────────────────────────────

def _tprm_default(name: str):
    def _get():
        from app.services import tprm_scoring_service as t
        return getattr(t, name)
    return _get


register(MethodParameter(
    key="tprm.inherent.weights", module="tprm", type="weights",
    label="Pesos del riesgo inherente de proveedor",
    description=("Cuanto pesa cada factor (sensibilidad de datos, volumen, "
                 "acceso a sistemas, criticidad...) en el riesgo inherente."),
    default_factory=_tprm_default("INHERENT_WEIGHTS"),
    engine="tprm_scoring_service.compute_inherent_risk", wired=True,
))

register(MethodParameter(
    key="tprm.inherent.formula", module="tprm", type="formula",
    label="Formula propia del riesgo inherente",
    description=("Formula alternativa a los pesos. Deja vacio para usar los "
                 "pesos declarados arriba."),
    variables=("data_sensitivity", "data_volume", "system_access",
               "business_criticality", "regulatory_scope", "geographic_risk"),
    default_factory=lambda: None,
    engine="tprm_scoring_service.compute_inherent_risk", wired=True,
))

register(MethodParameter(
    key="tprm.tier.thresholds", module="tprm", type="scale",
    label="Umbrales de clasificacion de proveedor",
    description="Puntuaciones que separan critico / alto / medio / bajo.",
    default_factory=_tprm_default("TIER_THRESHOLDS"),
    engine="tprm_scoring_service.derive_tier", wired=True,
))

register(MethodParameter(
    key="tprm.reassessment.months", module="tprm", type="scale",
    label="Cadencia de reevaluacion por tier",
    description="Cada cuantos meses se reevalua un proveedor segun su tier.",
    unit="meses",
    default_factory=_tprm_default("REASSESSMENT_MONTHS"),
    engine="tprm_scoring_service.recompute_supplier", wired=True,
))
