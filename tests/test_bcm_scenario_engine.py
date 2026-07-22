"""Tests del motor determinista de escenarios de indisponibilidad.

Fijan dos comportamientos que son decisiones de producto, no detalles:

1. **La aplicabilidad por defecto es total.** Sin reglas declaradas, todos los
   escenarios aplican a todas las sedes. Que una sede 100% remota solo sufra
   escenarios de personal es la politica de UN cliente concreto (Once For All):
   se declara como fila en `BCMApplicabilityRule` y se puede desactivar. El
   motor no lleva esa regla cableada, y estos tests lo verifican en ambos
   sentidos.

2. **El impacto ponderado y la banda los calcula el codigo**, con el baremo que
   declare cada organizacion. La IA nunca produce esas cifras.

BD SQLite en memoria propia, al estilo de test_bcp_scoring.py.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (BCMApplicabilityRule, BCMLocation, BCMScenario,
                        BCMScenarioAssessment, BIACriteria)
from app.services.bcm_scenario_engine import (DEFAULT_CRITERIA, applicable_scenarios,
                                              band_for, get_criteria, recompute_org,
                                              rto_factor, scenario_matrix,
                                              weighted_impact)

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)

ORG = 987654
OTHER_ORG = 987655

# Las 4 familias con el reparto real del BIA de Once For All (17 escenarios).
_CATALOG = (
    [("ALT.%02d" % i, "personnel") for i in range(1, 5)]
    + [("ALT.%02d" % i, "systems_comms") for i in range(5, 9)]
    + [("ALT.%02d" % i, "third_party") for i in range(9, 14)]
    + [("ALT.%02d" % i, "facilities") for i in range(14, 18)]
)


@pytest.fixture()
def db():
    session = _Session()
    yield session
    for model in (BCMScenarioAssessment, BCMApplicabilityRule, BCMScenario,
                  BCMLocation, BIACriteria):
        session.query(model).filter(
            model.organization_id.in_([ORG, OTHER_ORG])
        ).delete(synchronize_session=False)
    session.commit()
    session.close()


def _seed_catalog(db, org=ORG):
    scenarios = []
    for code, family in _CATALOG:
        sc = BCMScenario(organization_id=org, code=code, name=f"Escenario {code}",
                         family=family, is_active=True)
        db.add(sc)
        scenarios.append(sc)
    db.flush()
    return scenarios


def _location(db, name, site_type, org=ORG, **kw):
    loc = BCMLocation(organization_id=org, name=name, site_type=site_type,
                      is_active=True, **kw)
    db.add(loc)
    db.flush()
    return loc


# ── Aplicabilidad ────────────────────────────────────────────────────────────

def test_sin_reglas_todos_los_escenarios_aplican_a_toda_sede(db):
    """El defecto conservador: nunca ocultar un escenario por omision."""
    scenarios = _seed_catalog(db)
    remota = _location(db, "Santiago", "remote")
    oficina = _location(db, "Madrid", "office")

    assert len(applicable_scenarios(scenarios, [], remota)) == 17
    assert len(applicable_scenarios(scenarios, [], oficina)) == 17


def test_regla_de_cliente_restringe_solo_donde_aplica(db):
    """La regla de Once For All como lo que es: una fila, no una ley del motor."""
    scenarios = _seed_catalog(db)
    remota = _location(db, "Santiago", "remote")
    oficina = _location(db, "Madrid", "office")
    hibrida = _location(db, "Vigo", "hybrid")

    regla = BCMApplicabilityRule(
        organization_id=ORG,
        name="Sedes 100% remotas: solo escenarios de personal",
        when={"site_type": ["remote"]},
        then={"include_only_families": ["personnel"]},
        rationale="Sin instalaciones propias no hay escenario de instalaciones.",
        source="manual", is_active=True,
    )
    db.add(regla)
    db.flush()

    en_remota = applicable_scenarios(scenarios, [regla], remota)
    assert len(en_remota) == 4
    assert {s.family for s in en_remota} == {"personnel"}

    # La regla no toca a las sedes que no cumplen la condicion
    assert len(applicable_scenarios(scenarios, [regla], oficina)) == 17
    assert len(applicable_scenarios(scenarios, [regla], hibrida)) == 17


def test_regla_desactivada_no_tiene_efecto(db):
    scenarios = _seed_catalog(db)
    remota = _location(db, "Panama", "remote")
    regla = BCMApplicabilityRule(
        organization_id=ORG, when={"site_type": ["remote"]},
        then={"include_only_families": ["personnel"]}, is_active=False,
    )
    db.add(regla)
    db.flush()
    assert len(applicable_scenarios(scenarios, [regla], remota)) == 17


def test_sede_sin_el_atributo_de_la_regla_no_pierde_escenarios(db):
    """Ante datos incompletos se muestra de mas, nunca de menos."""
    scenarios = _seed_catalog(db)
    sin_tipo = _location(db, "Sede sin clasificar", None)
    regla = BCMApplicabilityRule(
        organization_id=ORG, when={"site_type": ["remote"]},
        then={"exclude_families": ["facilities"]}, is_active=True,
    )
    db.add(regla)
    db.flush()
    assert len(applicable_scenarios(scenarios, [regla], sin_tipo)) == 17


def test_exclusiones_por_familia_y_por_codigo_se_acumulan(db):
    scenarios = _seed_catalog(db)
    loc = _location(db, "Bolivia", "remote", country="Bolivia")
    r1 = BCMApplicabilityRule(
        organization_id=ORG, priority=10, when={"site_type": ["remote"]},
        then={"exclude_families": ["facilities"]}, is_active=True,
    )
    r2 = BCMApplicabilityRule(
        organization_id=ORG, priority=20, when={"country": ["Bolivia"]},
        then={"exclude_scenarios": ["ALT.09", "ALT.10"]}, is_active=True,
    )
    db.add_all([r1, r2])
    db.flush()

    result = applicable_scenarios(scenarios, [r1, r2], loc)
    codes = {s.code for s in result}
    assert len(result) == 17 - 4 - 2
    assert "ALT.14" not in codes      # excluido por familia
    assert "ALT.09" not in codes      # excluido por codigo


# ── Impacto ponderado ────────────────────────────────────────────────────────

def test_factor_rto_prioriza_lo_que_no_puede_esperar():
    c = DEFAULT_CRITERIA
    assert rto_factor(c, label="No puede interrumpirse nunca") == 1.5
    assert rto_factor(c, label="1 hora") == 0.5
    # Etiqueta desconocida y sin horas: factor neutro, no se inventa urgencia
    assert rto_factor(c, label="cuando buenamente se pueda") == 1.0
    # Sin etiqueta reconocible se cae a las horas declaradas
    assert rto_factor(c, label=None, hours=24) == 0.9


def test_impacto_ponderado_toma_el_peor_horizonte_y_pondera_por_rto():
    c = DEFAULT_CRITERIA
    impacts = {
        "operational":  {"0h": 2, ">1h": 3, ">4h": 4, ">6h": 5},
        "regulatory":   {"0h": 1, ">1h": 2, ">4h": 2, ">6h": 4},
        "reputational": {"0h": 2, ">1h": 2, ">4h": 3, ">6h": 5},
    }
    # Peor horizonte >6h: max(nivel 5, 4, 5) = nivel 5 -> score 4
    res = weighted_impact(impacts, c, rto_label="3 dias")   # factor 1.0
    assert res["base_impact"] == 4.0
    assert res["weighted_impact"] == 4.0
    assert res["band"] == "critical"

    # Mismo impacto con un proceso que no puede interrumpirse: sube el peso
    urgente = weighted_impact(impacts, c, rto_label="No puede interrumpirse nunca")
    assert urgente["weighted_impact"] == 6.0
    assert urgente["band"] == "critical"   # por encima del techo sigue siendo critico

    # Y con RTO holgado de 1 hora el mismo impacto pesa la mitad
    holgado = weighted_impact(impacts, c, rto_label="1 hora")
    assert holgado["weighted_impact"] == 2.0
    assert holgado["band"] == "severe"


def test_sin_impactos_declarados_no_se_inventa_valoracion():
    res = weighted_impact(None, DEFAULT_CRITERIA, rto_label="1 hora")
    assert res["weighted_impact"] == 0.0
    assert res["band"] == "none"


def test_bandas_se_evaluan_por_minimo_descendente():
    c = DEFAULT_CRITERIA
    assert band_for(0.0, c) == "none"
    assert band_for(0.5, c) == "trivial"
    assert band_for(1.0, c) == "relevant"
    assert band_for(2.0, c) == "severe"
    assert band_for(3.5, c) == "critical"


def test_agregacion_media_es_configurable_por_organizacion():
    criteria = dict(DEFAULT_CRITERIA)
    criteria["aggregation"] = "avg"
    impacts = {
        "operational": {">6h": 5},   # score 4
        "regulatory":  {">6h": 1},   # score 0
    }
    res = weighted_impact(impacts, criteria, rto_label="3 dias")
    assert res["base_impact"] == 2.0     # media, no maximo


# ── Criterios y recalculo ────────────────────────────────────────────────────

def test_criterios_de_la_organizacion_sustituyen_al_baremo_por_defecto(db):
    db.add(BIACriteria(
        organization_id=ORG,
        horizons=["0h", ">24h"],
        rto_scale=[{"label": "inmediato", "hours": 0, "factor": 2.0}],
        aggregation="avg",
    ))
    db.commit()
    criteria = get_criteria(db, ORG)
    assert criteria["horizons"] == ["0h", ">24h"]
    assert criteria["aggregation"] == "avg"
    # Lo no declarado conserva el valor por defecto
    assert criteria["bands"] == DEFAULT_CRITERIA["bands"]


def test_org_sin_criterios_usa_el_baremo_por_defecto(db):
    assert get_criteria(db, OTHER_ORG)["horizons"] == DEFAULT_CRITERIA["horizons"]


def test_cambiar_el_baremo_recalcula_todo_el_bia(db):
    scenarios = _seed_catalog(db)
    loc = _location(db, "Madrid", "office")
    db.add(BCMScenarioAssessment(
        organization_id=ORG, scenario_id=scenarios[0].id, location_id=loc.id,
        impacts={"operational": {">6h": 5}}, rto_label="3 dias",
    ))
    db.commit()

    assert recompute_org(db, ORG) == 1
    row = db.query(BCMScenarioAssessment).filter_by(organization_id=ORG).one()
    assert row.weighted_impact == 4.0
    assert row.impact_band == "critical"

    # El cliente cambia su metodo: mismo dato, otra cifra, sin tocar filas
    db.add(BIACriteria(organization_id=ORG,
                       rto_scale=[{"label": "3 dias", "hours": 72, "factor": 0.5}]))
    db.commit()
    assert recompute_org(db, ORG) == 1
    db.refresh(row)
    assert row.weighted_impact == 2.0
    assert row.impact_band == "severe"


# ── Matriz ───────────────────────────────────────────────────────────────────

def test_matriz_declara_los_huecos_en_vez_de_ocultarlos(db):
    scenarios = _seed_catalog(db)
    loc = _location(db, "Madrid", "office")
    db.add(BCMScenarioAssessment(
        organization_id=ORG, scenario_id=scenarios[0].id, location_id=loc.id,
        impacts={"operational": {">6h": 3}}, rto_label="3 dias",
        weighted_impact=2.0, impact_band="severe",
    ))
    db.commit()

    matrix = scenario_matrix(db, ORG)
    assert matrix["applicable_total"] == 17
    assert matrix["assessed_total"] == 1
    assert len([c for c in matrix["cells"] if c["status"] == "missing"]) == 16
    assert matrix["coverage_pct"] == 5


def test_matriz_respeta_las_reglas_de_aplicabilidad(db):
    _seed_catalog(db)
    _location(db, "Madrid", "office")
    _location(db, "Santiago", "remote")
    db.add(BCMApplicabilityRule(
        organization_id=ORG, when={"site_type": ["remote"]},
        then={"include_only_families": ["personnel"]}, is_active=True,
    ))
    db.commit()

    matrix = scenario_matrix(db, ORG)
    # 17 de la oficina + 4 de la remota
    assert matrix["applicable_total"] == 21
    no_aplica = [c for c in matrix["cells"] if c["status"] == "not_applicable"]
    assert len(no_aplica) == 13
    assert all(c["location_name"] == "Santiago" for c in no_aplica)


def test_la_matriz_no_cruza_organizaciones(db):
    _seed_catalog(db, org=ORG)
    _location(db, "Madrid", "office", org=ORG)
    _seed_catalog(db, org=OTHER_ORG)
    _location(db, "Sede ajena", "office", org=OTHER_ORG)
    db.commit()

    matrix = scenario_matrix(db, ORG)
    assert len(matrix["locations"]) == 1
    assert matrix["locations"][0]["name"] == "Madrid"
    assert matrix["applicable_total"] == 17


# ── Combinacion impacto x RTO ────────────────────────────────────────────────

def test_la_combinacion_suma_es_configurable():
    """Hay metodos que suman el RTO al impacto en vez de multiplicarlo.

    "RTO (numerico) + Criterio de impacto = Impacto total" es una formula real
    de procedimiento de cliente. Con producto y con suma la cifra no se parece,
    asi que la eleccion se declara en el baremo y no se da por supuesta.
    """
    base = dict(DEFAULT_CRITERIA)
    impacts = {"operational": {">6h": 5}}          # nivel 5 -> score 4

    producto = weighted_impact(impacts, {**base, "combination": "product"},
                               rto_label="No puede interrumpirse nunca")
    assert producto["weighted_impact"] == 6.0      # 4 x 1.5

    suma = weighted_impact(impacts, {**base, "combination": "sum"},
                           rto_label="No puede interrumpirse nunca")
    assert suma["weighted_impact"] == 5.5          # 4 + 1.5
    assert suma["combination"] == "sum"


def test_la_suma_no_inventa_impacto_donde_no_lo_hay():
    """Sumar el factor a un impacto vacio daria por severo lo no valorado."""
    criteria = {**DEFAULT_CRITERIA, "combination": "sum"}
    res = weighted_impact(None, criteria, rto_label="No puede interrumpirse nunca")
    assert res["weighted_impact"] == 0.0
    assert res["band"] == "none"


def test_reproduce_los_valores_del_procedimiento_del_cliente():
    """Contraste contra la tabla de un procedimiento real (formula de suma).

    Se comprueban las filas cuya aritmetica cuadra en el documento original.
    Dos de las diecisiete no cuadran alli (1,5+4,00 aparece como 5,05 y
    0,9+3 como 3,09): son erratas del documento, no del motor, y por eso no
    se fijan aqui como comportamiento esperado.
    """
    criteria = {**DEFAULT_CRITERIA, "combination": "sum"}
    casos = [
        # (etiqueta RTO, criterio de impacto, impacto total esperado)
        ("4 horas",          0.2, 0.8),
        ("6 horas",          0.8, 1.5),
        ("Mas de 1 semana",  0.3, 1.5),
        ("1 hora",           3.0, 3.5),
        ("4 horas",          2.7, 3.3),
        ("1 hora",           2.7, 3.2),
        ("12 horas",         0.9, 1.7),
        ("24 horas",         0.3, 1.2),
        ("Mas de 1 semana",  1.2, 2.4),
    ]
    for rto_label, criterio, esperado in casos:
        factor = rto_factor(criteria, label=rto_label)
        assert round(criterio + factor, 2) == esperado, rto_label


def test_los_criterios_de_la_organizacion_declaran_la_combinacion(db):
    db.add(BIACriteria(organization_id=ORG, combination="sum"))
    db.commit()
    assert get_criteria(db, ORG)["combination"] == "sum"


# ── Catalogo del sistema ─────────────────────────────────────────────────────

def test_el_catalogo_del_sistema_trae_17_escenarios_en_4_familias(db):
    from app.services.bcm_scenario_catalog import ISO22301_17, seed_catalog

    assert len(ISO22301_17) == 17
    familias = {}
    for item in ISO22301_17:
        familias[item["family"]] = familias.get(item["family"], 0) + 1
    assert familias == {"personnel": 4, "systems_comms": 4,
                        "third_party": 5, "facilities": 4}

    out = seed_catalog(db, ORG)
    assert out["scenarios_created"] == 17
    creados = db.query(BCMScenario).filter_by(organization_id=ORG).all()
    assert all(s.source == "system" for s in creados)


def test_sembrar_dos_veces_no_duplica(db):
    from app.services.bcm_scenario_catalog import seed_catalog
    seed_catalog(db, ORG)
    out = seed_catalog(db, ORG)
    assert out["scenarios_created"] == 0
    assert out["scenarios_skipped"] == 17
    assert db.query(BCMScenario).filter_by(organization_id=ORG).count() == 17


def test_el_baremo_propio_de_la_organizacion_manda_sobre_el_del_sistema(db):
    from app.services.bcm_scenario_catalog import seed_catalog
    db.add(BIACriteria(organization_id=ORG, combination="sum",
                       horizons=["0h", ">72h"]))
    db.commit()

    out = seed_catalog(db, ORG, baremo_code="producto")
    assert out["baremo_applied"] is None
    criteria = get_criteria(db, ORG)
    assert criteria["combination"] == "sum"
    assert criteria["horizons"] == ["0h", ">72h"]


def test_sembrar_el_baremo_en_una_organizacion_sin_metodo(db):
    from app.services.bcm_scenario_catalog import seed_catalog
    out = seed_catalog(db, ORG, baremo_code="suma")
    assert out["baremo_applied"] == "suma"
    assert get_criteria(db, ORG)["combination"] == "sum"


def test_catalogo_desconocido_se_rechaza(db):
    from app.services.bcm_scenario_catalog import seed_catalog
    with pytest.raises(ValueError):
        seed_catalog(db, ORG, catalog_code="no_existe")
