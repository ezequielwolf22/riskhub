"""Evaluador de formulas aritmeticas declaradas por el cliente.

Algunos metodos no se pueden expresar con parametros sueltos. Un cliente puede
declarar en su politica que el impacto de un proveedor es
`0.4*financiero + 0.6*operativo`, y esa formula tiene que poder ejecutarse tal
cual o la plataforma le estara dando cifras que no son las suyas.

El riesgo evidente es que "ejecutar lo que ponga el cliente" es ejecucion de
codigo. Aqui NO se usa `eval` ni `exec`. La expresion se parsea con `ast` y se
recorre con una **lista blanca**: solo se admiten los tipos de nodo declarados
abajo, los nombres tienen que estar entre las variables permitidas y las
llamadas solo pueden ser a un puñado de funciones matematicas. Cualquier otra
cosa — un atributo, un indice, una lambda, una comprension, un nombre libre —
se rechaza al parsear, antes de evaluar nada.

Ademas la formula se valida CUANDO SE GUARDA, contra casos de prueba, para que
una expresion rota se detecte al declararla y no en mitad de un recalculo.
"""
from __future__ import annotations

import ast
import logging
import math
from typing import Any, Iterable, Optional

logger = logging.getLogger("riskhub.method.formula")

# Limites: una formula de metodo es corta por naturaleza. Los topes evitan que
# una expresion generada o pegada por error consuma tiempo de CPU al parsear.
MAX_LENGTH = 500
MAX_DEPTH = 15
MAX_NODES = 200

# Nodos admitidos. Todo lo que no este aqui se rechaza.
_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp, ast.UnaryOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd,
    ast.Constant,
    ast.Name, ast.Load,
    ast.Call,
    ast.IfExp,                                    # a if cond else b
    ast.Compare, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq,
    ast.BoolOp, ast.And, ast.Or,
)


def _clamp(value, low, high):
    return max(low, min(high, value))


# Funciones permitidas. Todas puras, todas numericas, ninguna con acceso al
# entorno. `round` se envuelve para no admitir el segundo argumento negativo.
_FUNCTIONS = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": lambda v, nd=0: round(v, int(max(0, nd))),
    "clamp": _clamp,
    "floor": math.floor,
    "ceil": math.ceil,
    "sqrt": lambda v: math.sqrt(v) if v >= 0 else 0.0,
}


class FormulaError(ValueError):
    """La formula no se puede aceptar. El mensaje explica por que."""


def _describe(node: ast.AST) -> str:
    """Nombre legible del nodo, para que el error diga que sobra."""
    return {
        "Attribute": "acceso a atributos",
        "Subscript": "indexacion",
        "Lambda": "funciones lambda",
        "ListComp": "comprensiones de lista",
        "DictComp": "comprensiones de diccionario",
        "SetComp": "comprensiones de conjunto",
        "GeneratorExp": "generadores",
        "Await": "await",
        "Starred": "desempaquetado",
        "JoinedStr": "cadenas formateadas",
        "NamedExpr": "asignaciones",
        "List": "listas", "Tuple": "tuplas", "Dict": "diccionarios",
        "Set": "conjuntos",
    }.get(type(node).__name__, type(node).__name__)


def parse(expression: str, variables: Iterable[str]) -> ast.Expression:
    """Valida la expresion y devuelve su AST. Lanza FormulaError si no cabe."""
    if not expression or not str(expression).strip():
        raise FormulaError("La formula esta vacia.")
    text = str(expression).strip()
    if len(text) > MAX_LENGTH:
        raise FormulaError(
            f"La formula supera los {MAX_LENGTH} caracteres."
        )

    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"La formula no es una expresion valida: {exc.msg}") from exc

    allowed_vars = set(variables or ())
    nodes = 0

    for node in ast.walk(tree):
        nodes += 1
        if nodes > MAX_NODES:
            raise FormulaError("La formula es demasiado compleja.")

        if not isinstance(node, _ALLOWED_NODES):
            raise FormulaError(f"No se admite {_describe(node)} en una formula.")

        if isinstance(node, ast.Constant):
            # Solo numeros: una cadena o un booleano en medio de una formula
            # aritmetica es siempre un error de redaccion.
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise FormulaError("Solo se admiten numeros como constantes.")

        elif isinstance(node, ast.Name):
            if node.id in _FUNCTIONS:
                continue
            if node.id not in allowed_vars:
                disponibles = ", ".join(sorted(allowed_vars)) or "ninguna"
                raise FormulaError(
                    f"La variable '{node.id}' no existe. Disponibles: {disponibles}."
                )

        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
                raise FormulaError(
                    "Solo se admiten estas funciones: "
                    + ", ".join(sorted(_FUNCTIONS))
                )
            if node.keywords:
                raise FormulaError("Las funciones no admiten argumentos con nombre.")

        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            # Un exponente grande es una forma clasica de agotar CPU y memoria
            # con una expresion corta (2**2**32).
            exp = node.right
            if not (isinstance(exp, ast.Constant)
                    and isinstance(exp.value, (int, float))
                    and abs(exp.value) <= 4):
                raise FormulaError("El exponente debe ser un numero entre -4 y 4.")

    if _depth(tree) > MAX_DEPTH:
        raise FormulaError("La formula anida demasiados niveles.")

    return tree


def _depth(node: ast.AST, level: int = 0) -> int:
    if level > MAX_DEPTH + 5:      # corta la recursion en expresiones absurdas
        return level
    children = list(ast.iter_child_nodes(node))
    if not children:
        return level
    return max(_depth(child, level + 1) for child in children)


def evaluate(expression: str, variables: dict, *,
             default: Optional[float] = None) -> float:
    """Evalua la formula con las variables dadas.

    Con `default`, un fallo de evaluacion (division por cero, valor no
    numerico) devuelve ese valor en vez de lanzar: los recalculos masivos no
    deben caerse por una formula mal declarada en una organizacion.
    """
    values = {k: _numeric(v) for k, v in (variables or {}).items()}
    try:
        tree = parse(expression, values.keys())
        result = _eval_node(tree.body, values)
        if isinstance(result, bool):
            result = float(result)
        if not isinstance(result, (int, float)) or not math.isfinite(result):
            raise FormulaError("El resultado no es un numero finito.")
        return float(result)
    except FormulaError:
        if default is not None:
            logger.warning("method.formula: formula invalida, se usa el defecto",
                           exc_info=True)
            return float(default)
        raise
    except (ZeroDivisionError, OverflowError, ValueError, TypeError) as exc:
        if default is not None:
            logger.warning("method.formula: fallo al evaluar (%s), se usa el defecto",
                           exc)
            return float(default)
        raise FormulaError(f"No se pudo evaluar la formula: {exc}") from exc


def _numeric(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}

_CMP_OPS = {
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
}


def _eval_node(node: ast.AST, values: dict):
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id in values:
            return values[node.id]
        raise FormulaError(f"La variable '{node.id}' no tiene valor.")

    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise FormulaError("Operador no admitido.")
        return op(_eval_node(node.left, values), _eval_node(node.right, values))

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, values)
        return -operand if isinstance(node.op, ast.USub) else +operand

    if isinstance(node, ast.Call):
        fn = _FUNCTIONS[node.func.id]
        return fn(*[_eval_node(a, values) for a in node.args])

    if isinstance(node, ast.IfExp):
        return (_eval_node(node.body, values) if _eval_node(node.test, values)
                else _eval_node(node.orelse, values))

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, values)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, values)
            fn = _CMP_OPS.get(type(op))
            if fn is None or not fn(left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.BoolOp):
        results = [_eval_node(v, values) for v in node.values]
        return all(results) if isinstance(node.op, ast.And) else any(results)

    raise FormulaError(f"No se admite {_describe(node)} en una formula.")


def validate(expression: str, variables: Iterable[str],
             samples: Optional[list[dict]] = None) -> dict:
    """Comprueba la formula al guardarla, no en el primer recalculo.

    Devuelve {valid, error, results} — con `samples`, evalua cada caso para que
    quien la declara vea el numero que produce antes de aceptarla.
    """
    try:
        parse(expression, variables)
    except FormulaError as exc:
        return {"valid": False, "error": str(exc), "results": []}

    results = []
    for sample in (samples or []):
        try:
            values = {name: sample.get(name, 0) for name in variables}
            results.append({"inputs": sample,
                            "result": evaluate(expression, values)})
        except FormulaError as exc:
            return {"valid": False, "error": f"Con {sample}: {exc}",
                    "results": results}
    return {"valid": True, "error": None, "results": results}


def available_functions() -> list[str]:
    return sorted(_FUNCTIONS)
