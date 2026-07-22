"""Tests del cableado de los motores al metodo de la organizacion.

Dos cosas, y la primera es un bug real que existia antes de este trabajo:

1. **La matriz de riesgo del cliente se ignoraba en la mitad de los caminos.**
   `risk_recalc_service` y `risk_auto_generator` la respetaban, pero los riesgos
   creados desde un CVE, desde un hallazgo OSINT, desde el agente o desde una
   importacion CSV llamaban a `calc_level` sin ella. El mismo par
   consecuencia/probabilidad daba un nivel distinto segun quien lo hubiera
   creado. Aqui se fija que todos usan la misma.

2. **Sin metodo declarado, nada cambia.** Es la garantia de que este mecanismo
   no altera el comportamiento de ninguna organizacion que no lo use.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (BIACriteria, MethodBinding, RiskContext, Supplier,
                        SupplierTier)
from app.services import risk_engine, tprm_scoring_service
from app.services.bcm_scenario_engine import DEFAULT_CRITERIA, get_criteria, weighted_impact
from app.services.method.bindings import set_binding

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)

ORG = 670001

# Matriz "invertida" respecto a la de referencia: cualquier celda que se lea
# con la matriz equivocada da un numero distinto y el test lo caza.
CUSTOM_MATRIX = [[8 - c for c in range(5)] for _ in range(5)]


@pytest.fixture()
def db():
    session = _Session()
    yield session
    for model in (MethodBinding, BIACriteria, RiskContext, Supplier):
        session.query(model).filter_by(organization_id=ORG).delete(
            synchronize_session=False)
    session.commit()
    session.close()


# ── Riesgo: la matriz del cliente se respeta en todos los caminos ────────────

def test_sin_matriz_propia_se_usa_la_de_referencia(db):
    assert risk_engine.org_matrix(db, ORG) is None
    assert risk_engine.calc_level_for_org(db, ORG, 4, 4) == \
        risk_engine.calc_level(4, 4)


def test_la_matriz_del_contexto_de_riesgo_se_respeta(db):
    db.add(RiskContext(organization_id=ORG, risk_matrix=CUSTOM_MATRIX))
    db.commit()
    assert risk_engine.org_matrix(db, ORG) == CUSTOM_MATRIX
    assert risk_engine.calc_level_for_org(db, ORG, 0, 0) == 8


def test_el_metodo_declarado_manda_sobre_el_contexto(db):
    db.add(RiskContext(organization_id=ORG, risk_matrix=CUSTOM_MATRIX))
    db.commit()
    otra = [[1 for _ in range(5)] for _ in range(5)]
    set_binding(db, ORG, "risk.matrix", otra, source="policy")
    assert risk_engine.org_matrix(db, ORG) == otra


def test_todos_los_caminos_dan_el_mismo_nivel_con_matriz_propia(db):
    """El bug: un riesgo de un CVE valia distinto que el mismo recalculado.

    Se comprueba que el resultado de resolver la matriz una vez (lo que hacen
    ahora cve, osint, ai y la importacion CSV) coincide con el que usa
    risk_recalc_service, que era el unico camino correcto.
    """
    from app.services.risk_recalc_service import get_matrix
    db.add(RiskContext(organization_id=ORG, risk_matrix=CUSTOM_MATRIX))
    db.commit()

    esperado = risk_engine.calc_level(3, 2, get_matrix(db, ORG))

    # Camino de cve/risks: resuelven la matriz una vez y la pasan
    matriz = risk_engine.org_matrix(db, ORG)
    assert risk_engine.calc_level(3, 2, matriz) == esperado
    # Camino de osint/ai: helper directo
    assert risk_engine.calc_level_for_org(db, ORG, 3, 2) == esperado
    # Y NO coincide con la de referencia, o el test no probaria nada
    assert esperado != risk_engine.calc_level(3, 2)


def test_los_cuatro_routers_resuelven_la_matriz(db):
    """Barrido de codigo: ningun llamador puede volver a olvidarse.

    Si alguien anade un `calc_level(c, l)` pelado en estos routers, el nivel
    dejara de respetar la matriz del cliente sin que nadie se entere. Este test
    es la red que lo impide.
    """
    import io
    import re
    for path in ("app/routers/cve.py", "app/routers/osint.py",
                 "app/routers/ai.py", "app/routers/risks.py"):
        for n, line in enumerate(io.open(path, encoding="utf-8"), 1):
            code = line.split("#", 1)[0]      # los comentarios no calculan nada
            for match in re.finditer(r"(?<!_for_org)calc_level\(([^)]*)\)", code):
                args = match.group(1)
                if "matrix" in args:
                    continue
                pytest.fail(f"{path}:{n}: calc_level sin matriz de la "
                            f"organizacion -> calc_level({args})")


# ── TPRM: pesos y umbrales del cliente ───────────────────────────────────────

def _supplier(db, **kw):
    s = Supplier(organization_id=ORG, code=kw.pop("code", "SUP-7001"),
                 name=kw.pop("name", "Proveedor"), **kw)
    db.add(s)
    db.flush()
    return s


def test_sin_metodo_declarado_el_scoring_no_cambia(db):
    """Garantia de no regresion: nadie nota este mecanismo hasta usarlo."""
    sup = _supplier(db, data_sensitivity=4, data_volume=3,
                    business_criticality=5, geographic_risk=2)
    db.commit()
    assert tprm_scoring_service.compute_inherent_risk(sup, db=db) == \
        tprm_scoring_service.compute_inherent_risk(sup)


def test_los_pesos_del_cliente_cambian_el_riesgo_inherente(db):
    sup = _supplier(db, data_sensitivity=5, data_volume=1,
                    business_criticality=1, geographic_risk=1)
    db.commit()
    por_defecto = tprm_scoring_service.compute_inherent_risk(sup, db=db)

    # Su politica dice que lo unico que pesa es la sensibilidad del dato
    set_binding(db, ORG, "tprm.inherent.weights",
                {"data_sensitivity": 1.0, "data_volume": 0, "system_access": 0,
                 "business_criticality": 0, "regulatory_scope": 0,
                 "geographic_risk": 0}, source="policy")
    con_su_metodo = tprm_scoring_service.compute_inherent_risk(sup, db=db)
    assert con_su_metodo != por_defecto
    assert con_su_metodo == 100      # sensibilidad 5 -> 100 en la escala 0-100


def test_una_formula_propia_manda_sobre_los_pesos(db):
    sup = _supplier(db, data_sensitivity=4, data_volume=2)
    db.commit()
    set_binding(db, ORG, "tprm.inherent.formula",
                "0.5*data_sensitivity + 0.5*data_volume", source="policy")
    # _scale_1_5 normaliza 1-5 a 0-100: sensibilidad 4 -> 75, volumen 2 -> 25
    assert tprm_scoring_service.compute_inherent_risk(sup, db=db) == 50


def test_una_formula_rota_no_tumba_el_recalculo(db):
    """Mil proveedores no pueden caerse por una formula mal declarada."""
    sup = _supplier(db, data_sensitivity=4)
    db.commit()
    db.add(MethodBinding(organization_id=ORG,
                         parameter_key="tprm.inherent.formula",
                         value="data_sensitivity / 0", source="policy",
                         is_active=True))
    db.commit()
    assert tprm_scoring_service.compute_inherent_risk(sup, db=db) == 0


def test_los_umbrales_de_tier_del_cliente_se_respetan(db):
    assert tprm_scoring_service.derive_tier(50, db=db, org_id=ORG) != \
        SupplierTier.CRITICAL
    set_binding(db, ORG, "tprm.tier.thresholds",
                [[40, "critical"], [20, "high"], [10, "medium"]], source="policy")
    assert tprm_scoring_service.derive_tier(50, db=db, org_id=ORG) == \
        SupplierTier.CRITICAL
    assert tprm_scoring_service.derive_tier(5, db=db, org_id=ORG) == \
        SupplierTier.LOW


# ── BCM: el baremo sale del metodo declarado ─────────────────────────────────

def test_sin_metodo_declarado_el_baremo_no_cambia(db):
    criteria = get_criteria(db, ORG)
    assert criteria["combination"] == DEFAULT_CRITERIA["combination"]
    assert criteria["horizons"] == DEFAULT_CRITERIA["horizons"]
    assert "_sources" not in criteria


def test_la_combinacion_declarada_en_su_politica_se_aplica(db):
    set_binding(db, ORG, "bcm.impact.combination", "sum", source="policy")
    criteria = get_criteria(db, ORG)
    assert criteria["combination"] == "sum"
    # Y la cifra cambia de verdad
    res = weighted_impact({"operational": {">6h": 5}}, criteria,
                          rto_label="No puede interrumpirse nunca")
    assert res["weighted_impact"] == 5.5


def test_el_baremo_dice_de_donde_sale_cada_valor(db):
    """Una cifra sin procedencia no es defendible en una auditoria."""
    set_binding(db, ORG, "bcm.impact.combination", "sum", source="manual")
    criteria = get_criteria(db, ORG)
    assert "combination" in criteria["_sources"]
    res = weighted_impact({"operational": {">6h": 5}}, criteria, rto_label="1 hora")
    assert res["sources"]["combination"]


def test_una_formula_propia_de_impacto_se_evalua(db):
    set_binding(db, ORG, "bcm.impact.formula", "impact * rto + 1", source="policy")
    criteria = get_criteria(db, ORG)
    res = weighted_impact({"operational": {">6h": 5}}, criteria, rto_label="3 dias")
    # impacto 4 x factor 1.0 + 1 = 5
    assert res["weighted_impact"] == 5.0
    assert res["combination"] == "formula"


def test_bia_criteria_sigue_funcionando_junto_al_registro(db):
    """Las dos vias conviven: la vista de BCP y lo extraido de la politica."""
    db.add(BIACriteria(organization_id=ORG, horizons=["0h", ">24h"]))
    db.commit()
    set_binding(db, ORG, "bcm.impact.combination", "sum", source="policy")

    criteria = get_criteria(db, ORG)
    assert criteria["horizons"] == ["0h", ">24h"]     # de BIACriteria
    assert criteria["combination"] == "sum"           # del registro de metodo
