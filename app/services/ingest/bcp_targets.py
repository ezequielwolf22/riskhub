"""Entidades del modulo BCP que el motor de ingesta sabe materializar.

Este fichero es el contrato completo entre continuidad de negocio y el motor:
que se puede crear desde un documento, como se reconoce que ya existe, y que
gana cuando dos documentos se contradicen.

La politica de conflicto no es decorativa. En los objetivos de recuperacion
(RTO, RPO, MTPD) se declara `min`: si el BIA dice 4 horas y el DRP dice 6, se
guarda 4. Planificar para 4 y disponer de 6 es margen; al reves es un
incumplimiento. En criticidad e impacto se declara `max` por el mismo motivo.
"""
from __future__ import annotations

import re

from app.services.ingest.contracts import EntitySpec, FieldSpec, register
from app.services.ingest.reconciler import normalize_name

# Vocabularios que ya usa el router BCP. Un valor fuera de estos se descarta en
# vez de colarse en la base.
CRITICALITY = ("critical", "high", "medium", "low")
PLAN_TYPES = ("bcp", "drp", "crp", "ems", "pandemic", "cyber_response", "supply_chain")
TEST_TYPES = ("tabletop", "simulation", "full_test")
TEST_RESULTS = ("passed", "partial", "failed")
DEP_TYPES = ("IT_system", "personnel", "facility", "supplier", "utility",
             "communication", "transport", "external_service", "process")
STRATEGY_TYPES = ("hot_site", "cold_site", "warm_site", "work_from_home",
                  "outsourcing", "manual_workaround", "dual_site", "cloud_failover")
SCENARIO_FAMILIES = ("personnel", "systems_comms", "third_party", "facilities")
SITE_TYPES = ("office", "remote", "hybrid")
STAFFING_MODELS = ("internal", "external", "both")


def _code_setter(prefix: str, model_name: str, width: int = 4):
    """Asigna un codigo correlativo libre antes de insertar.

    No sirve derivarlo del id (el patron `SUP-{id:04d}` de routers/suppliers):
    en `suppliers` la columna es UNIQUE y NOT NULL, asi que un marcador comun
    para todas las filas del lote choca en la segunda insercion, y un codigo
    derivado del id puede pisar a uno que ya existiera con ese numero. Se busca
    el primer hueco real y se reserva en memoria durante el lote.
    """
    def _before_write(db, payload: dict) -> dict:
        if payload.get("code"):
            return payload
        from app import models
        model = getattr(models, model_name, None)
        if model is None or not hasattr(model, "code"):
            return payload
        taken = {
            c for (c,) in db.query(model.code).filter(
                model.code.like(f"{prefix}-%")
            ).all() if c
        }
        n = len(taken) + 1
        while f"{prefix}-{n:0{width}d}" in taken:
            n += 1
        payload["code"] = f"{prefix}-{n:0{width}d}"
        return payload
    return _before_write


def _location_name(value) -> str:
    """Normaliza el nombre de una sede.

    Los documentos las nombran de mil formas: "Madrid - HQ", "Oficina de Madrid",
    "Madrid (wework)". Todas son la misma sede.
    """
    text = normalize_name(value)
    text = re.sub(r"\b(oficina|oficinas|office|offices|sede|sedes|hq|"
                  r"headquarters|sucursal|delegacion|centro|planta)\b", " ", text)
    text = re.sub(r"\b(wework|regus|coworking|remoto|remote|teletrabajo)\b", " ", text)
    # Conectores sueltos: sin esto "Oficina de Madrid" queda como "de madrid" y
    # deja de reconocerse como la sede "Madrid - HQ".
    text = re.sub(r"\b(de|del|la|el|los|las|of|the|en|in|at)\b", " ", text)
    text = re.sub(r"[-–—()]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ── Sedes ────────────────────────────────────────────────────────────────────

register(EntitySpec(
    key="bcm_location",
    model="BCMLocation",
    label="Sede",
    natural_keys=(("name",), ("code",)),
    normalizer=_location_name,
    before_write=_code_setter("LOC", "BCMLocation", 3),
    provided_by_hook=("code",),
    fields=(
        FieldSpec("name", max_length=255, conflict_policy="first"),
        FieldSpec("code", max_length=16, conflict_policy="first"),
        FieldSpec("description"),
        FieldSpec("address"),
        FieldSpec("country", max_length=64),
        FieldSpec("city", max_length=128),
        FieldSpec("business_unit", max_length=128),
        # Gobiernan que escenarios aplican: si el documento no lo dice, se deja
        # vacio y ninguna regla de aplicabilidad dispara sobre esta sede.
        FieldSpec("site_type", max_length=16, choices=SITE_TYPES),
        FieldSpec("staffing_model", max_length=16, choices=STAFFING_MODELS),
        FieldSpec("recovery_site_type", max_length=16),
        FieldSpec("recovery_site_description"),
        FieldSpec("timezone", max_length=64),
    ),
))


# ── Escenarios de indisponibilidad ───────────────────────────────────────────

register(EntitySpec(
    key="bcm_scenario",
    model="BCMScenario",
    label="Escenario de indisponibilidad",
    # Identidad por CODIGO si lo hay y es valido; si no, por NOMBRE normalizado.
    # Muchos BIA traen el codigo roto ("#¡REF!"): sin la clave por nombre, cuatro
    # escenarios distintos con el codigo roto se fundian en uno. La comparacion
    # por nombre es EXACTA (normalizada), no por parecido, asi que "Caida de la
    # infraestructura AWS" y "Caida de las comunicaciones" siguen siendo dos.
    natural_keys=(("code",), ("name",)),
    normalizer=normalize_name,
    before_write=_code_setter("ESC", "BCMScenario", 3),
    provided_by_hook=("code",),
    fields=(
        FieldSpec("code", max_length=16, conflict_policy="first"),
        FieldSpec("name", max_length=255, conflict_policy="first"),
        FieldSpec("family", max_length=32, choices=SCENARIO_FAMILIES),
        FieldSpec("description"),
        FieldSpec("procedure_notes"),
        FieldSpec("responsible_area", max_length=255),
    ),
))


register(EntitySpec(
    key="bcm_scenario_assessment",
    model="BCMScenarioAssessment",
    label="Valoracion BIA de escenario",
    # Una valoracion por escenario y sede: al reimportar se actualiza la misma,
    # no se duplica. Es clave exacta por ids, sin riesgo de fusion indebida.
    natural_keys=(("scenario_id", "location_id"),),
    depends_on=("bcm_scenario", "bcm_location"),
    # El escenario se referencia por NOMBRE: es como lo nombra el BIA (cada
    # bloque encabezado por el nombre del escenario) y su codigo suele venir roto.
    references={"scenario_id": ("bcm_scenario", "name"),
                "location_id": ("bcm_location", "name")},
    fields=(
        FieldSpec("scenario_id", type="int", conflict_policy="first"),
        FieldSpec("location_id", type="int", conflict_policy="first"),
        FieldSpec("process_id", type="int"),
        # Objetivos de recuperacion: gana siempre el mas exigente
        FieldSpec("mtpd_hours", type="float", conflict_policy="min"),
        FieldSpec("rto_label", max_length=64, conflict_policy="latest"),
        FieldSpec("rto_hours", type="float", conflict_policy="min"),
        FieldSpec("rpo_label", max_length=64, conflict_policy="latest"),
        FieldSpec("rpo_hours", type="float", conflict_policy="min"),
        FieldSpec("impacts", type="json", conflict_policy="latest"),
        FieldSpec("dependencies_note"),
        # Los calcula bcm_scenario_engine tras materializar. La ingesta no los
        # escribe aunque vengan en el documento.
        FieldSpec("weighted_impact", type="float", computed=True),
        FieldSpec("impact_band", max_length=32, computed=True),
    ),
))


# ── Procesos de negocio y dependencias ───────────────────────────────────────

register(EntitySpec(
    key="business_process",
    model="BusinessProcess",
    label="Proceso de negocio",
    natural_keys=(("name",),),
    depends_on=("bcm_location",),
    # `parent_process_id` referencia a OTRO proceso del mismo lote por su nombre:
    # es como se reconstruye la jerarquia macro-proceso -> proceso -> actividad
    # desde un documento plano. El materializador ordena padres antes que hijos.
    references={"location_id": ("bcm_location", "name"),
                "parent_process_id": ("business_process", "name")},
    fields=(
        FieldSpec("name", max_length=255, conflict_policy="first"),
        FieldSpec("description"),
        FieldSpec("business_unit", max_length=128, conflict_policy="first"),
        FieldSpec("parent_process_id", type="int", conflict_policy="first"),
        FieldSpec("criticality", max_length=16, choices=CRITICALITY,
                  conflict_policy="max"),
        FieldSpec("priority", type="int", conflict_policy="min"),
        FieldSpec("rto_hours", type="int", conflict_policy="min"),
        FieldSpec("rpo_hours", type="int", conflict_policy="min"),
        FieldSpec("mtpd_hours", type="int", conflict_policy="min"),
        FieldSpec("mbco"),
        FieldSpec("min_recovery_staff", type="int", conflict_policy="max"),
        FieldSpec("activation_criteria"),
        FieldSpec("alternative_procedure"),
        FieldSpec("vital_records", type="json"),
        FieldSpec("it_systems", type="json"),
        FieldSpec("facilities", type="json"),
        FieldSpec("escalation_contacts", type="json"),
        FieldSpec("location_id", type="int"),
        FieldSpec("financial_impact", type="int", conflict_policy="max"),
        FieldSpec("reputational_impact", type="int", conflict_policy="max"),
        FieldSpec("legal_impact", type="int", conflict_policy="max"),
        FieldSpec("operational_impact", type="int", conflict_policy="max"),
        FieldSpec("cost_per_hour", type="float", conflict_policy="max"),
        FieldSpec("ens_category", max_length=8),
        FieldSpec("bia_version", max_length=16),
    ),
))


register(EntitySpec(
    key="bcp_dependency",
    model="BCPDependency",
    label="Dependencia de proceso",
    depends_on=("business_process",),
    # `depends_on_process_id` enlaza una dependencia de tipo "process" con el
    # proceso del que se depende (por nombre): asi el grafo proceso->proceso y su
    # propagacion de impacto se reconstruyen desde el documento, no a mano.
    references={"process_id": ("business_process", "name"),
                "depends_on_process_id": ("business_process", "name")},
    natural_keys=(("process_id", "name"),),
    fields=(
        FieldSpec("process_id", type="int", conflict_policy="first"),
        FieldSpec("depends_on_process_id", type="int", conflict_policy="first"),
        FieldSpec("name", max_length=255, conflict_policy="first"),
        FieldSpec("dependency_type", max_length=32, choices=DEP_TYPES),
        FieldSpec("description"),
        FieldSpec("rto_hours", type="int", conflict_policy="min"),
        FieldSpec("is_critical", type="bool", conflict_policy="max"),
        FieldSpec("alternative"),
        FieldSpec("qty_normal", type="int"),
        FieldSpec("qty_recovery", type="int"),
        FieldSpec("notes"),
    ),
))


# ── Estrategias (las "alternativas" por escenario) ───────────────────────────

register(EntitySpec(
    key="bcp_strategy",
    model="BCPStrategy",
    label="Estrategia de continuidad",
    depends_on=("bcm_scenario", "business_process", "bcm_location"),
    references={"scenario_id": ("bcm_scenario", "name"),
                "process_id": ("business_process", "name"),
                "location_id": ("bcm_location", "name")},
    # Identidad por escenario + nombre: dos estrategias con el mismo nombre bajo
    # escenarios distintos son distintas y no deben pisarse.
    natural_keys=(("scenario_id", "name"),),
    fields=(
        FieldSpec("name", max_length=255, conflict_policy="first"),
        FieldSpec("strategy_type", max_length=32, choices=STRATEGY_TYPES),
        FieldSpec("description"),
        FieldSpec("requirements"),
        FieldSpec("resources"),
        FieldSpec("scenario_id", type="int"),
        FieldSpec("process_id", type="int"),
        FieldSpec("location_id", type="int"),
        FieldSpec("estimated_cost", type="float"),
        FieldSpec("implementation_status", max_length=32,
                  choices=("planned", "in_progress", "implemented", "tested")),
    ),
))


# ── Planes ───────────────────────────────────────────────────────────────────

register(EntitySpec(
    key="bcp_plan",
    model="BCPPlan",
    label="Plan de continuidad o recuperacion",
    natural_keys=(("name",), ("code",)),
    before_write=_code_setter("BCP", "BCPPlan", 4),
    provided_by_hook=("code",),
    depends_on=("bcm_location",),
    references={"location_id": ("bcm_location", "name")},
    fields=(
        FieldSpec("name", max_length=255, conflict_policy="first"),
        FieldSpec("code", max_length=16, conflict_policy="first"),
        FieldSpec("plan_type", max_length=32, choices=PLAN_TYPES),
        FieldSpec("version", max_length=16, conflict_policy="latest"),
        FieldSpec("scope"),
        FieldSpec("activation_criteria"),
        FieldSpec("content_summary"),
        FieldSpec("sections", type="json", conflict_policy="latest"),
        FieldSpec("roles_matrix", type="json", conflict_policy="latest"),
        FieldSpec("contact_list", type="json", conflict_policy="latest"),
        FieldSpec("system_dependencies", type="json", conflict_policy="latest"),
        FieldSpec("dr_site", type="json", conflict_policy="latest"),
        FieldSpec("backup_policy", type="json", conflict_policy="latest"),
        FieldSpec("crisis_comms", type="json", conflict_policy="latest"),
        FieldSpec("authorized_activators", type="json", conflict_policy="latest"),
        FieldSpec("scenario_ids", type="json", conflict_policy="latest"),
        FieldSpec("plan_owner_name", max_length=255),
        FieldSpec("classification", max_length=32),
        FieldSpec("location_id", type="int"),
        FieldSpec("review_date", type="datetime", conflict_policy="latest"),
        FieldSpec("last_exercised_at", type="datetime", conflict_policy="latest"),
        FieldSpec("source_sha256", max_length=64),
        # El estado NUNCA se importa: que un documento se titule "aprobado" no
        # aprueba nada en RiskHub. La aprobacion es un acto con responsable y
        # fecha (POST /plans/{id}/approve), no un adjetivo del documento.
    ),
))


# ── Pruebas y ejercicios ─────────────────────────────────────────────────────

register(EntitySpec(
    key="bcp_test",
    model="BCPTest",
    label="Prueba de continuidad",
    before_write=_code_setter("BCT", "BCPTest", 4),
    provided_by_hook=("code",),
    depends_on=("bcm_location",),
    references={"location_id": ("bcm_location", "name")},
    natural_keys=(("code",),),
    fields=(
        FieldSpec("code", max_length=16, conflict_policy="first"),
        FieldSpec("test_type", max_length=16, choices=TEST_TYPES),
        FieldSpec("objective"),
        FieldSpec("scope_description"),
        FieldSpec("scheduled_at", type="datetime"),
        FieldSpec("conducted_at", type="datetime", conflict_policy="latest"),
        FieldSpec("result", max_length=16, choices=TEST_RESULTS),
        FieldSpec("findings"),
        FieldSpec("lessons_learned"),
        FieldSpec("improvement_actions"),
        FieldSpec("participants", type="json"),
        FieldSpec("frequency", max_length=16),
        FieldSpec("rto_achieved_hours", type="int"),
        FieldSpec("rpo_achieved_hours", type="int"),
        FieldSpec("scenario_ids", type="json"),
        FieldSpec("process_ids", type="json"),
        FieldSpec("location_id", type="int"),
        FieldSpec("source_sha256", max_length=64),
    ),
))


# ── Proveedores criticos ─────────────────────────────────────────────────────

register(EntitySpec(
    key="supplier",
    model="Supplier",
    label="Proveedor",
    natural_keys=(("name",),),
    before_write=_code_setter("SUP", "Supplier", 4),
    provided_by_hook=("code",),
    fields=(
        FieldSpec("name", max_length=255, conflict_policy="first"),
        FieldSpec("services"),
        FieldSpec("contact_email", max_length=255),
        FieldSpec("contact_name", max_length=255),
        FieldSpec("category", max_length=128),
        FieldSpec("is_critical", type="bool", conflict_policy="max"),
    ),
))


register(EntitySpec(
    key="bcp_supplier_link",
    model="BCPSupplierLink",
    label="Proveedor critico para continuidad",
    depends_on=("supplier", "bcm_scenario"),
    references={"supplier_id": ("supplier", "name")},
    natural_keys=(("supplier_id",),),
    fields=(
        FieldSpec("supplier_id", type="int", conflict_policy="first"),
        FieldSpec("criticality", max_length=16, choices=CRITICALITY,
                  conflict_policy="max"),
        FieldSpec("rto_impact_hours", type="int", conflict_policy="min"),
        FieldSpec("contract_sla_hours", type="int", conflict_policy="min"),
        FieldSpec("has_contingency_plan", type="bool", conflict_policy="max"),
        FieldSpec("contingency_description"),
        FieldSpec("scenario_ids", type="json"),
        FieldSpec("notes"),
    ),
))
