"""Tests del evaluador de formulas del cliente.

La mayor parte de este fichero es seguridad. Aceptar una formula escrita por un
usuario y evaluarla es, si se hace mal, ejecucion remota de codigo: el clasico
`__import__("os").system(...)` dentro de un `eval`. Aqui se comprueba que el
parser rechaza toda esa familia ANTES de evaluar nada, y que las formulas
legitimas de un metodo BIA o de scoring de proveedores funcionan.
"""
import pytest

from app.services.method.formula import (FormulaError, available_functions,
                                         evaluate, parse, validate)

VARS = ("financial", "operational", "rto", "dims")


# ── Ataques ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("expr", [
    '__import__("os").system("echo pwned")',
    '__import__("subprocess")',
    "().__class__.__bases__[0].__subclasses__()",
    "financial.__class__",
    "financial.real",
    "open('/etc/passwd').read()",
    "eval('1+1')",
    "exec('x=1')",
    "globals()",
    "locals()",
    "getattr(financial, 'real')",
    "[x for x in range(10)]",
    "{k: 1 for k in range(3)}",
    "(x for x in range(3))",
    "lambda x: x",
    "financial[0]",
    "financial if True else __import__('os')",
    "f'{financial}'",
    "[1, 2, 3]",
    "{'a': 1}",
    "(1, 2)",
    "print(financial)",
    "financial := 5",
])
def test_expresiones_peligrosas_se_rechazan_al_parsear(expr):
    """Ninguna de estas debe llegar siquiera a evaluarse."""
    with pytest.raises(FormulaError):
        parse(expr, VARS)


def test_una_variable_no_declarada_se_rechaza():
    with pytest.raises(FormulaError) as exc:
        parse("financial + secreto", VARS)
    # El error dice cuales hay, para que sea util al que la escribe
    assert "secreto" in str(exc.value)
    assert "financial" in str(exc.value)


def test_las_cadenas_no_son_constantes_validas():
    with pytest.raises(FormulaError):
        parse("financial + 'texto'", VARS)


def test_exponentes_grandes_se_rechazan():
    """2**2**32 agota memoria con una expresion de nueve caracteres."""
    with pytest.raises(FormulaError):
        parse("2 ** 2 ** 32", VARS)
    with pytest.raises(FormulaError):
        parse("financial ** 999", VARS)
    # Un exponente razonable si vale
    assert evaluate("financial ** 2", {"financial": 3}) == 9.0


def test_expresiones_desmesuradas_se_rechazan():
    # Demasiado larga
    with pytest.raises(FormulaError):
        parse("financial + " * 200 + "1", VARS)
    # Demasiado anidada. Los parentesis redundantes no cuentan (no generan
    # nodos AST); lo que se acota es el anidamiento real de operaciones.
    with pytest.raises(FormulaError):
        parse("1+(" * 60 + "1" + ")" * 60, VARS)
    # Y una anidacion razonable sigue valiendo
    assert evaluate("1+(1+(1+(1+1)))", {}) == 5.0


def test_sintaxis_invalida_da_error_legible():
    with pytest.raises(FormulaError) as exc:
        parse("financial +", VARS)
    assert "expresion valida" in str(exc.value)


def test_formula_vacia_se_rechaza():
    for value in ("", "   ", None):
        with pytest.raises(FormulaError):
            parse(value, VARS)


def test_funciones_no_declaradas_se_rechazan():
    with pytest.raises(FormulaError):
        parse("suma(financial, operational)", VARS)


def test_argumentos_con_nombre_se_rechazan():
    with pytest.raises(FormulaError):
        parse("round(financial, ndigits=2)", VARS)


# ── Formulas legitimas ───────────────────────────────────────────────────────

def test_formula_ponderada_de_un_metodo_real():
    """El caso que motiva todo esto: pesos propios del cliente."""
    result = evaluate("0.4*financial + 0.6*operational",
                      {"financial": 5, "operational": 3})
    assert result == pytest.approx(3.8)


def test_impacto_por_rto_en_sus_dos_formas():
    # Producto
    assert evaluate("dims * rto", {"dims": 4, "rto": 1.5}) == 6.0
    # Suma, que es lo que declara el procedimiento de Once For All
    assert evaluate("dims + rto", {"dims": 4, "rto": 1.5}) == 5.5


def test_funciones_matematicas():
    assert evaluate("max(financial, operational)",
                    {"financial": 2, "operational": 7}) == 7.0
    assert evaluate("clamp(financial, 0, 4)", {"financial": 9}) == 4.0
    assert evaluate("round(financial / 3, 2)", {"financial": 10}) == 3.33
    assert evaluate("sqrt(financial)", {"financial": 16}) == 4.0
    # sqrt de un negativo devuelve 0 en vez de estallar en un recalculo masivo
    assert evaluate("sqrt(financial)", {"financial": -1}) == 0.0


def test_condicional_para_umbrales():
    expr = "4 if financial >= 4 else financial"
    assert evaluate(expr, {"financial": 5}) == 4.0
    assert evaluate(expr, {"financial": 2}) == 2.0


def test_las_variables_se_convierten_a_numero():
    """Los valores llegan de columnas JSON y a veces son texto."""
    assert evaluate("financial + operational",
                    {"financial": "3,5", "operational": "1.5"}) == 5.0
    # Un valor no numerico cuenta como cero, no rompe el recalculo
    assert evaluate("financial + operational",
                    {"financial": "n/a", "operational": 2}) == 2.0


# ── Errores en tiempo de evaluacion ──────────────────────────────────────────

def test_division_por_cero_sin_defecto_lanza():
    with pytest.raises(FormulaError):
        evaluate("financial / operational", {"financial": 1, "operational": 0})


def test_division_por_cero_con_defecto_no_tumba_el_recalculo():
    """Un recalculo de mil filas no puede caerse por una formula mal declarada."""
    assert evaluate("financial / operational",
                    {"financial": 1, "operational": 0}, default=0.0) == 0.0


def test_formula_invalida_con_defecto_devuelve_el_defecto():
    assert evaluate("__import__('os')", {"financial": 1}, default=2.5) == 2.5


# ── Validacion al guardar ────────────────────────────────────────────────────

def test_validar_devuelve_el_resultado_de_cada_caso():
    out = validate("0.4*financial + 0.6*operational", VARS, samples=[
        {"financial": 5, "operational": 3},
        {"financial": 0, "operational": 0},
    ])
    assert out["valid"] is True
    assert out["error"] is None
    assert out["results"][0]["result"] == pytest.approx(3.8)
    assert out["results"][1]["result"] == 0.0


def test_validar_rechaza_y_explica():
    out = validate("__import__('os')", VARS)
    assert out["valid"] is False
    assert out["error"]


def test_validar_detecta_el_fallo_en_un_caso_concreto():
    """Una formula que parsea pero revienta con ciertos datos."""
    out = validate("financial / operational", VARS,
                   samples=[{"financial": 1, "operational": 0}])
    assert out["valid"] is False
    assert "operational" in out["error"]


def test_las_funciones_disponibles_se_pueden_listar():
    """La UI necesita decirle al usuario que puede usar."""
    fns = available_functions()
    assert "min" in fns and "max" in fns and "clamp" in fns
    assert "eval" not in fns and "open" not in fns
