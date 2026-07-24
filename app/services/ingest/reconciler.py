"""Crear o enlazar: la decision determinista de toda importacion.

Sin esta capa, cada importacion duplica el inventario del cliente: el BIA dice
"AMAZON WEB SERVICES, INC.", el contrato dice "Amazon Web Services SARL" y la
base ya tiene un proveedor "AWS". Son tres nombres del mismo proveedor.

Aqui no interviene ningun modelo de lenguaje. La coincidencia se decide con
reglas legibles y un umbral explicito, para que sea reproducible y depurable:
primero clave natural exacta sobre el nombre normalizado, y solo despues
similitud, que ademas exige un margen sobre el segundo mejor candidato para no
elegir a ciegas entre dos parecidos.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Optional

logger = logging.getLogger("riskhub.ingest.reconciler")

# Umbral de similitud para dar dos nombres por equivalentes.
SIMILARITY_THRESHOLD = 0.88
# Margen minimo sobre el segundo mejor candidato. Si dos registros existentes
# se parecen casi igual al nombre entrante, no se elige: se crea uno nuevo y se
# marca para revision. Enlazar con el proveedor equivocado es peor que duplicar.
AMBIGUITY_MARGIN = 0.05

# Sufijos societarios y ruido juridico. No aportan identidad.
_LEGAL_SUFFIXES = (
    "s.a.u.", "s.a.s.", "s.l.u.", "s.l.", "s.a.", "sau", "slu", "sarl", "s.a.r.l.",
    "inc.", "inc", "ltd.", "ltd", "llc", "plc", "gmbh", "b.v.", "bv", "n.v.", "nv",
    "corp.", "corp", "co.", "company", "limited", "sociedad limitada",
    "sociedad anonima", "s.coop", "aie", "ag", "oy", "ab", "as", "a/s", "spa",
    "s.p.a.", "pte", "pty", "kft", "sp. z o.o.", "srl", "s.r.l.",
)


def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


def normalize_name(value: Any) -> str:
    """Forma canonica de un nombre para comparar.

    Minusculas sin acentos, sin sufijo societario, sin puntuacion y con los
    espacios colapsados. "AMAZON WEB SERVICES, INC." -> "amazon web services".
    """
    if value is None:
        return ""
    text = strip_accents(str(value)).lower().strip()
    text = re.sub(r"[\"'`]", "", text)
    # El sufijo societario puede ir al final o entre comas
    for _ in range(2):
        for suffix in _LEGAL_SUFFIXES:
            if text.endswith(" " + suffix) or text.endswith("," + suffix):
                text = text[: -len(suffix)].rstrip(" ,.")
            text = text.replace(", " + suffix + " ", " ").replace(" " + suffix + " ", " ")
    text = re.sub(r"[^\w\s&+-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def similarity(a: str, b: str) -> float:
    """Parecido entre dos nombres ya normalizados, en [0, 1].

    Si los numeros que aparecen en cada nombre no coinciden, el parecido es
    cero por mucho que se escriban igual. "Proceso 1" y "Proceso 2" difieren en
    un solo caracter y SequenceMatcher les da 0,889 — por encima de cualquier
    umbral razonable. Fusionarlos convertiria doce procesos en uno, y lo mismo
    valdria para "Sede 1"/"Sede 2" o los escenarios ALT.01/ALT.02. Cuando un
    numero distingue dos nombres, es justamente lo que los distingue.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if _digits(a) != _digits(b):
        return 0.0
    # Contencion: "aws" dentro de "aws europe" es senal fuerte, pero solo si el
    # termino corto tiene cuerpo suficiente para no ser casual.
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        shorter, longer = (a, b) if len(a) < len(b) else (b, a)
        return max(SequenceMatcher(None, a, b).ratio(), len(shorter) / len(longer))
    return SequenceMatcher(None, a, b).ratio()


def _digits(text: str) -> list[str]:
    """Secuencias numericas del nombre, sin ceros de relleno ('01' == '1')."""
    return [n.lstrip("0") or "0" for n in re.findall(r"\d+", text)]


class MatchResult:
    """Resultado de reconciliar una fila entrante contra lo ya existente."""

    __slots__ = ("record", "score", "how", "ambiguous", "candidates")

    def __init__(self, record=None, score: float = 0.0, how: str = "none",
                 ambiguous: bool = False, candidates: Optional[list] = None):
        self.record = record
        self.score = score
        self.how = how            # natural_key | similarity | none
        self.ambiguous = ambiguous
        self.candidates = candidates or []

    @property
    def matched(self) -> bool:
        return self.record is not None

    def __repr__(self):  # pragma: no cover - depuracion
        return (f"<MatchResult {self.how} score={self.score:.2f} "
                f"ambiguous={self.ambiguous}>")


def find_match(db, spec, org_id: Optional[int], values: dict,
               name_field: str = "name",
               threshold: float = SIMILARITY_THRESHOLD) -> MatchResult:
    """Busca el registro existente que corresponde a `values`.

    1. Clave natural exacta (comparando nombres normalizados, no literales).
    2. Similitud sobre el campo de nombre, con margen frente al segundo.
    """
    model = _resolve_model(spec.model)
    if model is None:
        return MatchResult()

    query = db.query(model)
    if org_id is not None and hasattr(model, "organization_id"):
        query = query.filter(model.organization_id == org_id)

    # -- 1. Clave natural --------------------------------------------------
    for key_fields in (spec.natural_keys or ()):
        if not all(values.get(f) not in (None, "") for f in key_fields):
            continue
        candidates = query
        exact_ok = True
        for fname in key_fields:
            if not hasattr(model, fname):
                exact_ok = False
                break
            candidates = candidates.filter(getattr(model, fname) == values[fname])
        if exact_ok:
            found = candidates.first()
            if found is not None:
                return MatchResult(found, 1.0, "natural_key")

    # Reintento de la clave natural comparando en forma normalizada: es lo que
    # hace que "AMAZON WEB SERVICES, INC." encuentre a "Amazon Web Services".
    for key_fields in (spec.natural_keys or ()):
        if len(key_fields) != 1:
            continue
        fname = key_fields[0]
        wanted = values.get(fname)
        if not wanted or not hasattr(model, fname):
            continue
        target = _normalize_for(spec, wanted)
        if not target:
            continue
        for row in query.all():
            if _normalize_for(spec, getattr(row, fname, None)) == target:
                return MatchResult(row, 1.0, "natural_key")

    # -- 2. Parecido, PERO nunca se fusiona solo -------------------------------
    # Un nombre parecido no es prueba de que sea el mismo registro: "Caida de
    # los sistemas de producto" y "Caida de la infraestructura AWS" se parecen
    # y son escenarios distintos. Antes esto auto-actualizaba el registro
    # parecido y aplastaba datos. Ahora se devuelve como POSIBLE DUPLICADO: el
    # materializador crea uno nuevo y lo marca para que una persona decida si
    # de verdad son el mismo. La ultima palabra es del usuario, nunca del
    # parecido de dos cadenas.
    wanted = values.get(name_field)
    if not wanted or not hasattr(model, name_field):
        return MatchResult()
    target = _normalize_for(spec, wanted)
    if not target:
        return MatchResult()

    scored = []
    for row in query.all():
        score = similarity(target, _normalize_for(spec, getattr(row, name_field, None)))
        if score >= threshold:
            scored.append((score, row))
    if not scored:
        return MatchResult()

    scored.sort(key=lambda t: t[0], reverse=True)
    candidates = [{"id": getattr(r, "id", None),
                   "name": getattr(r, name_field, None), "score": round(s, 3)}
                  for s, r in scored[:5]]
    return MatchResult(None, scored[0][0], "possible_duplicate",
                       candidates=candidates)


def _normalize_for(spec, value) -> str:
    if spec is not None and getattr(spec, "normalizer", None):
        try:
            return spec.normalizer(value)
        except Exception:
            logger.debug("reconciler: normalizador de %s fallo", spec.key, exc_info=True)
    return normalize_name(value)


_MODEL_CACHE: dict = {}


def _resolve_model(name: str):
    """Resuelve el nombre de la clase contra app.models, con cache."""
    if name in _MODEL_CACHE:
        return _MODEL_CACHE[name]
    try:
        from app import models
        model = getattr(models, name, None)
    except Exception:  # pragma: no cover - defensivo
        model = None
    if model is None:
        logger.error("reconciler: modelo desconocido %r", name)
    _MODEL_CACHE[name] = model
    return model
