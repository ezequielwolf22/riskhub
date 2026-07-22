"""Tests del registro de metodo y de la resolucion con procedencia.

Lo que se fija aqui:

- la precedencia (manual > politica del cliente > defecto) y que una correccion
  manual no la pisa una propuesta extraida de un documento;
- que cada valor sabe decir DE DONDE sale, porque una cifra sin procedencia no
  es defendible en una auditoria;
- que un valor invalido o un parametro desconocido no tumban un motor: se cae
  al defecto y se registra.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import MethodBinding, MethodStatement
from app.services.method import registry
from app.services.method.bindings import (apply_statement, clear_binding,
                                          method_overview, resolve, set_binding)

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)

ORG = 660001


@pytest.fixture()
def db():
    session = _Session()
    yield session
    for model in (MethodBinding, MethodStatement):
        session.query(model).filter_by(organization_id=ORG).delete(
            synchronize_session=False)
    session.commit()
    session.close()


def _statement(db, key, value, **kw):
    st = MethodStatement(
        organization_id=ORG, parameter_key=key, proposed_value=value,
        source_document=kw.get("document", "ISP_11.docx"),
        source_section=kw.get("section", "6.3"),
        quote=kw.get("quote", "RTO + Criterio de Impacto = Impacto total"),
        confidence=kw.get("confidence", 0.9), status="proposed",
    )
    db.add(st)
    db.flush()
    return st


# ── Catalogo ─────────────────────────────────────────────────────────────────

def test_el_catalogo_declara_los_tres_modulos():
    for module in ("bcm", "risk", "tprm"):
        assert registry.by_module(module), f"sin parametros en {module}"
    assert "bcm.impact.combination" in registry.keys()
    assert "risk.matrix" in registry.keys()
    assert "tprm.inherent.weights" in registry.keys()


def test_los_defectos_salen_de_los_motores_reales():
    """Un defecto escrito aparte se desincroniza del motor que lo usa."""
    from app.services.bcm_scenario_engine import DEFAULT_CRITERIA
    from app.services.tprm_scoring_service import INHERENT_WEIGHTS

    assert registry.get("bcm.impact.combination").default() == \
        DEFAULT_CRITERIA["combination"]
    assert registry.get("tprm.inherent.weights").default() == INHERENT_WEIGHTS
    assert len(registry.get("risk.matrix").default()) == 5


def test_el_catalogo_del_prompt_sale_del_registro():
    described = registry.describe_for_prompt()
    assert "bcm.impact.combination" in described
    assert "product|sum" in described
    # Las formulas declaran sus variables para que la IA no invente nombres
    assert "data_sensitivity" in described


def test_un_parametro_declara_si_su_motor_ya_lo_consume():
    """`wired` se muestra tal cual: es mas honesto que disimularlo."""
    assert registry.get("bcm.impact.combination").wired is True
    assert registry.get("bcm.iso22301.clause_weights").wired is False


# ── Resolucion ───────────────────────────────────────────────────────────────

def test_sin_nada_declarado_se_usa_el_defecto(db):
    r = resolve(db, ORG, "bcm.impact.combination")
    assert r.value == "product"
    assert r.source == "default"
    assert r.is_default is True
    assert "defecto" in r.explain()


def test_un_parametro_desconocido_no_rompe_nada(db):
    r = resolve(db, ORG, "modulo.inventado.parametro")
    assert r.value is None and r.source == "default"


def test_el_valor_de_politica_gana_al_defecto_y_cita_su_fuente(db):
    st = _statement(db, "bcm.impact.combination", "sum")
    apply_statement(db, ORG, st)

    r = resolve(db, ORG, "bcm.impact.combination")
    assert r.value == "sum"
    assert r.source == "policy"
    assert r.citation["document"] == "ISP_11.docx"
    assert r.citation["section"] == "6.3"
    assert r.explain() == "segun ISP_11.docx 6.3"
    assert st.status == "bound"


def test_el_valor_manual_gana_al_de_politica(db):
    st = _statement(db, "bcm.impact.combination", "sum")
    apply_statement(db, ORG, st)
    set_binding(db, ORG, "bcm.impact.combination", "product", source="manual")

    r = resolve(db, ORG, "bcm.impact.combination")
    assert r.value == "product"
    assert r.source == "manual"


def test_una_propuesta_no_pisa_lo_que_alguien_fijo_a_mano(db):
    """Si alguien lo decidio a sabiendas, un documento no le lleva la contraria."""
    set_binding(db, ORG, "bcm.impact.combination", "product", source="manual")
    st = _statement(db, "bcm.impact.combination", "sum")

    out = apply_statement(db, ORG, st)
    assert out["applied"] is False
    assert "manual" in out["reason"]
    assert resolve(db, ORG, "bcm.impact.combination").value == "product"

    # Pero se puede forzar explicitamente
    assert apply_statement(db, ORG, st, force=True)["applied"] is True
    assert resolve(db, ORG, "bcm.impact.combination").value == "sum"


def test_volver_al_defecto(db):
    set_binding(db, ORG, "bcm.impact.combination", "sum")
    assert clear_binding(db, ORG, "bcm.impact.combination") is True
    assert resolve(db, ORG, "bcm.impact.combination").source == "default"


def test_la_organizacion_sin_id_usa_el_defecto(db):
    assert resolve(db, None, "bcm.impact.combination").source == "default"


# ── Validacion ───────────────────────────────────────────────────────────────

def test_un_valor_fuera_de_las_opciones_se_rechaza_al_guardar(db):
    with pytest.raises(ValueError) as exc:
        set_binding(db, ORG, "bcm.impact.combination", "promedio_ponderado")
    assert "Opciones" in str(exc.value)


def test_una_cadencia_absurda_se_rechaza(db):
    with pytest.raises(ValueError):
        set_binding(db, ORG, "bcm.test.frequency_months", 0)
    with pytest.raises(ValueError):
        set_binding(db, ORG, "bcm.test.frequency_months", -12)
    set_binding(db, ORG, "bcm.test.frequency_months", 6)
    assert resolve(db, ORG, "bcm.test.frequency_months").value == 6


def test_una_formula_peligrosa_se_rechaza_al_guardar(db):
    """La validacion de formula del registro delega en el evaluador seguro."""
    with pytest.raises(ValueError):
        set_binding(db, ORG, "tprm.inherent.formula", "__import__('os').system('x')")
    with pytest.raises(ValueError) as exc:
        set_binding(db, ORG, "tprm.inherent.formula", "data_sensitivity + secreto")
    assert "secreto" in str(exc.value)

    set_binding(db, ORG, "tprm.inherent.formula",
                "0.5*data_sensitivity + 0.5*data_volume")
    assert resolve(db, ORG, "tprm.inherent.formula").value.startswith("0.5*")


def test_unos_pesos_que_no_suman_se_rechazan(db):
    with pytest.raises(ValueError):
        set_binding(db, ORG, "tprm.inherent.weights", {"data_volume": 0})


def test_un_valor_invalido_ya_guardado_cae_al_defecto_sin_romper(db):
    """Un dato corrupto en base no puede tumbar un recalculo masivo."""
    db.add(MethodBinding(organization_id=ORG,
                         parameter_key="bcm.impact.combination",
                         value="ni_producto_ni_suma", source="policy",
                         is_active=True))
    db.commit()
    r = resolve(db, ORG, "bcm.impact.combination")
    assert r.value == "product"
    assert r.source == "default"


def test_una_declaracion_no_modelable_no_se_aplica(db):
    st = _statement(db, None, {"algo": 1})
    out = apply_statement(db, ORG, st)
    assert out["applied"] is False
    # Pero la declaracion sigue ahi con su cita: no se pierde
    assert st.quote and st.status != "bound"


# ── Vista de conjunto ────────────────────────────────────────────────────────

def test_la_vista_de_conjunto_muestra_origen_y_cableado(db):
    st = _statement(db, "bcm.impact.combination", "sum")
    apply_statement(db, ORG, st)

    overview = {p["key"]: p for p in method_overview(db, ORG)}
    assert len(overview) == len(registry.all_params())

    combinacion = overview["bcm.impact.combination"]
    assert combinacion["value"] == "sum"
    assert combinacion["source"] == "policy"
    assert combinacion["wired"] is True
    assert combinacion["default"] == "product"
    assert combinacion["citation"]["quote"]

    # Un parametro declarado pero aun no consumido se dice
    assert overview["bcm.iso22301.clause_weights"]["wired"] is False
