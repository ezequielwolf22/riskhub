"""Ejecucion del mapa de volcado contra la base de datos.

Aqui no hay ningun modelo de lenguaje. Recibe filas ya extraidas y decide, con
las reglas del `EntitySpec`, si cada una crea un registro nuevo o actualiza uno
existente, resolviendo por el camino las contradicciones entre documentos.

Cuatro invariantes, y las cuatro importan:

- Un campo marcado `computed` jamas se escribe desde aqui: lo calcula su motor
  determinista (el impacto ponderado, la banda). Que venga en el documento no
  lo convierte en dato de entrada.
- Un campo corregido por el usuario jamas se sobrescribe.
- Todo lo que se toca deja rastro, para poder deshacerlo.
- Lo dudoso se escribe igualmente y se marca `needs_review`. No se pierde
  informacion por no estar seguro, pero tampoco se disfraza de certeza.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.ingest import batch as batch_mod
from app.services.ingest import conflicts as conflicts_mod
from app.services.ingest import contracts, reconciler

logger = logging.getLogger("riskhub.ingest.materializer")

# Por debajo de esta confianza, el registro se crea pero pide revision humana.
REVIEW_THRESHOLD = 0.75

# Valores de error de hoja de calculo. Una celda con una formula rota exporta
# "#¡REF!", "#N/A", etc. No es un dato ni una identidad: si se cuela como codigo
# de un escenario, cuatro escenarios distintos comparten "#¡REF!" y se funden en
# uno. Se tratan como celda vacia. Es generico: vale para cualquier Excel roto.
_EXCEL_ERRORS = {
    "#ref!", "#value!", "#name?", "#n/a", "#num!", "#null!", "#div/0!",
    "#getting_data", "#spill!", "#calc!", "#field!", "#unknown!", "#blocked!",
    "#connect!", "#busy!", "#na", "n/a", "#error", "#ref",
}


def _is_excel_error(text: str) -> bool:
    """True si el texto es un valor de error de Excel (con o sin ¡/¿)."""
    t = str(text).strip().lower().replace("¡", "").replace("¿", "")
    return t in _EXCEL_ERRORS


def _blank(value: Any) -> bool:
    """Un hueco: None, cadena vacia o coleccion vacia. El 0 NO es un hueco."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (dict, list)):
        return len(value) == 0
    return False


def _is_material_conflict(spec_field) -> bool:
    """Un campo cuya contradiccion merece que el usuario decida.

    Materiales: numeros (RTO/RPO/MTPD, impactos), booleanos (critico si/no) y
    vocabularios cerrados (criticidad, tipo). Ahi una discrepancia entre dos
    documentos es una decision de negocio real. El texto libre (nombre,
    descripcion, notas, requisitos) NO es material: dos redacciones del mismo
    hecho no son un conflicto y no deben pedir revision.
    """
    if spec_field is None:
        return False
    if spec_field.type in ("int", "float", "bool"):
        return True
    if spec_field.choices:
        return True
    if spec_field.conflict_policy in ("min", "max"):
        return True
    return False


def _is_placeholder(model, name: str, value: Any) -> bool:
    """True si `value` es el DEFAULT de la columna, no un dato real.

    Un proceso creado sin criticidad recibe 'medium' por defecto. Eso es un
    marcador del sistema, no una decision de nadie: el documento debe poder
    rellenarlo. Un valor DISTINTO del default si es real y no se pisa. Generico:
    no sabe de criticidad, solo compara con el default declarado de la columna.
    """
    col = model.__table__.columns.get(name)
    if col is None or col.default is None:
        return False
    if getattr(col.default, "is_scalar", False):
        try:
            return value == col.default.arg
        except Exception:
            return False
    return False


class MaterializationResult:
    def __init__(self):
        self.created: dict[str, int] = {}
        self.updated: dict[str, int] = {}
        self.linked: dict[str, int] = {}
        self.needs_review = 0
        self.conflicts = 0
        self.skipped: list[dict] = []
        self.warnings: list[str] = []
        # clave natural -> id, para resolver referencias dentro del mismo lote
        self.index: dict[tuple, int] = {}

    def _bump(self, bucket: dict, key: str) -> None:
        bucket[key] = bucket.get(key, 0) + 1

    def as_dict(self) -> dict:
        return {
            "created": self.created, "updated": self.updated, "linked": self.linked,
            "needs_review": self.needs_review, "conflicts": self.conflicts,
            "skipped": self.skipped[:50], "warnings": self.warnings[:50],
            "total_written": sum(self.created.values()) + sum(self.updated.values()),
        }


def materialize(db, org_id: Optional[int], batch, entity_key: str,
                rows: list[dict], *, source_filename: str = None,
                document_date=None, sha256: str = None,
                source_map_id: Optional[int] = None,
                result: Optional[MaterializationResult] = None,
                default_confidence: float = 1.0) -> MaterializationResult:
    """Materializa las filas de una entidad. Reutilizable entidad a entidad."""
    result = result or MaterializationResult()
    spec = contracts.get(entity_key)
    if spec is None:
        result.warnings.append(f"Entidad desconocida: {entity_key}")
        return result

    model = reconciler._resolve_model(spec.model)
    if model is None:
        result.warnings.append(f"Modelo no resuelto para {entity_key}")
        return result

    fmap = spec.field_map()
    writable = {f.name for f in spec.writable_fields()}

    for raw in rows or []:
        # Cada fila va en su propio savepoint: una fila mala se descarta sola y
        # no arrastra a las doscientas siguientes dejando la sesion inservible.
        savepoint = db.begin_nested()
        try:
            values, confidence, source_ref = _clean_row(raw, spec, fmap, writable,
                                                        default_confidence)
            if not values:
                savepoint.rollback()
                result.skipped.append({"entity": entity_key, "reason": "fila vacia"})
                continue

            _resolve_references(db, spec, values, result, org_id)

            missing = _missing_required(model, spec, values, org_id)
            if missing:
                # Una valoracion sin su escenario no es una valoracion. Se
                # descarta con motivo legible en vez de reventar la insercion.
                savepoint.rollback()
                result.skipped.append({
                    "entity": entity_key,
                    "reason": f"faltan campos obligatorios: {', '.join(missing)}",
                    "row": {k: v for k, v in list(values.items())[:5]},
                })
                result.warnings.append(
                    f"{spec.label}: fila descartada, sin {', '.join(missing)}"
                )
                continue

            match = reconciler.find_match(db, spec, org_id, values)
            possible_dup = None
            if match.how == "possible_duplicate":
                # Se parece a algo que ya existe, pero no es identico: se crea
                # aparte y se marca. Nunca se aplasta un registro por parecido.
                possible_dup = match.candidates
                confidence = min(confidence, 0.6)

            if match.matched:
                _update(db, org_id, batch, spec, model, match.record, values,
                        fmap, confidence, source_filename, source_ref, sha256,
                        document_date, source_map_id, result, entity_key)
            else:
                _create(db, org_id, batch, spec, model, values, confidence,
                        source_map_id, result, entity_key,
                        possible_duplicate=possible_dup)
            savepoint.commit()
        except Exception as exc:
            try:
                savepoint.rollback()
            except Exception:  # pragma: no cover - savepoint ya cerrado
                pass
            logger.warning("ingest: fila descartada en %s: %s", entity_key, exc,
                           exc_info=True)
            result.skipped.append({"entity": entity_key, "reason": str(exc)[:200]})

    db.flush()
    return result


def _missing_required(model, spec, values: dict, org_id) -> list[str]:
    """Columnas obligatorias del modelo que la fila no puede satisfacer.

    Se consulta el esquema real en vez de mantener una lista paralela: si
    manana una columna pasa a obligatoria, esto se entera solo.
    """
    missing = []
    supplied = set(spec.defaults or {}) | set(spec.provided_by_hook or ())
    for column in model.__table__.columns:
        name = column.name
        if column.primary_key or column.nullable:
            continue
        if column.default is not None or column.server_default is not None:
            continue
        if name in ("organization_id", "created_at", "updated_at"):
            continue
        if values.get(name) not in (None, "") or name in supplied:
            continue
        missing.append(name)
    return missing


# ── Alta ─────────────────────────────────────────────────────────────────────

def _create(db, org_id, batch, spec, model, values, confidence,
            source_map_id, result, entity_key, possible_duplicate=None) -> None:
    needs_review = confidence < REVIEW_THRESHOLD or bool(possible_duplicate)
    payload = dict(spec.defaults or {})
    payload.update(values)
    if hasattr(model, "organization_id"):
        payload["organization_id"] = org_id
    if hasattr(model, "source"):
        payload["source"] = "imported"
    if hasattr(model, "import_batch_id"):
        payload["import_batch_id"] = getattr(batch, "id", None)
    if hasattr(model, "import_confidence"):
        payload["import_confidence"] = confidence
    if hasattr(model, "needs_review"):
        payload["needs_review"] = needs_review

    if spec.before_write:
        payload = spec.before_write(db, payload) or payload

    payload = {k: v for k, v in payload.items() if hasattr(model, k)}
    record = model(**payload)
    db.add(record)
    db.flush()

    if spec.after_write:
        # Los codigos correlativos necesitan el id ya asignado
        spec.after_write(db, record)
        db.flush()

    tr = batch_mod.trace(db, batch, entity_key, model.__tablename__, record.id,
                         "created", before=None,
                         after=batch_mod.snapshot(record, spec),
                         confidence=confidence, needs_review=needs_review,
                         source_map_id=source_map_id)
    if possible_duplicate:
        # Se anota a quien se parece para que el usuario pueda fusionarlo si
        # de verdad es el mismo. No se decide por el: solo se le avisa.
        try:
            nm = values.get("name") or values.get("code") or "(sin nombre)"
            parecidos = ", ".join(
                f"#{c.get('id')} {c.get('name')}" for c in possible_duplicate[:3])
            result.warnings.append(
                f"{spec.label}: '{nm}' se parece a {parecidos}. Se ha creado "
                f"aparte por si son distintos; revisa si es el mismo.")
            if tr is not None:
                after = dict(tr.after or {})
                after["_possible_duplicate"] = possible_duplicate[:5]
                tr.after = after
        except Exception:
            logger.debug("ingest: no se pudo anotar el posible duplicado",
                         exc_info=True)
    result._bump(result.created, entity_key)
    if needs_review:
        result.needs_review += 1
    _index(result, spec, values, record.id)


# ── Actualizacion ────────────────────────────────────────────────────────────

def _update(db, org_id, batch, spec, model, record, values, fmap, confidence,
            source_filename, source_ref, sha256, document_date, source_map_id,
            result, entity_key) -> None:
    """Refleja lo que dice el documento SIN pisar lo que ya existe.

    Regla del modulo (reflejar, no modificar): la ingesta no cambia un dato que
    ya tiene valor. Un HUECO se rellena (reflejar y completar). Un valor que ya
    existe y DIFIERE no se toca: se levanta como PROPUESTA de cambio (conflicto)
    para que el usuario decida. Asi una importacion nunca destruye nada; en el
    peor caso deja una propuesta encima de la mesa. Un campo corregido a mano
    (override) es intocable, ni siquiera se propone.
    """
    before = batch_mod.snapshot(record, spec)
    protected = batch_mod.overridden_fields(db, org_id, model.__tablename__, record.id)
    filled = False
    had_conflict = False

    for name, incoming in values.items():
        if name in protected:
            # Correccion del usuario: intocable. La decision ya esta tomada.
            continue
        if not hasattr(record, name):
            continue
        current = getattr(record, name, None)
        if _blank(current) or _is_placeholder(model, name, current):
            # Hueco (o default del sistema): se rellena. Reflejar mas completo,
            # nunca destructivo.
            if not _same(current, incoming):
                setattr(record, name, incoming)
                filled = True
            continue
        if _same(current, incoming):
            continue

        # Ya hay un valor y el documento trae otro distinto. NO se sobrescribe.
        # Pero no toda diferencia merece una "duda": que un documento describa un
        # escenario con otras palabras, o traiga una nota mas larga, no es una
        # contradiccion — es la misma realidad redactada distinto. Solo se levanta
        # como conflicto lo MATERIAL: un numero de recuperacion (RTO/RPO/MTPD),
        # una criticidad, un flag. Lo demas (texto libre) se conserva en silencio.
        # Sin esto, un pack rico genera cientos de dudas de redaccion sin sentido.
        spec_field = fmap.get(name)
        if not _is_material_conflict(spec_field):
            continue
        policy = spec_field.conflict_policy if spec_field else "latest"
        candidates = [
            conflicts_mod.Candidate(current, source_filename="valor ya cargado"),
            conflicts_mod.Candidate(incoming, source_filename=source_filename,
                                    source_ref=source_ref, sha256=sha256,
                                    confidence=confidence,
                                    document_date=document_date),
        ]
        resolution = conflicts_mod.resolve(name, policy, candidates)
        conflicts_mod.record_conflict(db, org_id, getattr(batch, "id", None),
                                      entity_key, model.__tablename__, record.id,
                                      name, candidates, resolution)
        had_conflict = True
        result.conflicts += 1

    if hasattr(record, "import_batch_id"):
        record.import_batch_id = getattr(batch, "id", None)
    needs_review = confidence < REVIEW_THRESHOLD or had_conflict
    if hasattr(record, "needs_review") and needs_review:
        record.needs_review = True
    db.flush()

    batch_mod.trace(db, batch, entity_key, model.__tablename__, record.id,
                    "updated" if filled else "linked", before=before,
                    after=batch_mod.snapshot(record, spec),
                    confidence=confidence, needs_review=needs_review,
                    source_map_id=source_map_id)
    if filled:
        result._bump(result.updated, entity_key)
    else:
        result._bump(result.linked, entity_key)
    if needs_review:
        result.needs_review += 1
    _index(result, spec, values, record.id)


# ── Utilidades ───────────────────────────────────────────────────────────────

def _clean_row(raw: dict, spec, fmap: dict, writable: set,
               default_confidence: float) -> tuple[dict, float, Optional[str]]:
    """Valida y acota una fila entrante segun el contrato de la entidad."""
    confidence = raw.get("_confidence")
    confidence = float(confidence) if confidence is not None else default_confidence
    confidence = max(0.0, min(1.0, confidence))
    source_ref = raw.get("_source_ref")

    values: dict = {}
    for name, value in raw.items():
        # Una celda de error de Excel ("#¡REF!") no es dato ni identidad: se
        # trata como vacia antes de nada, tambien en las referencias.
        if isinstance(value, str) and _is_excel_error(value):
            value = None
        # Las referencias por clave natural (_ref_scenario_id) sobreviven al
        # filtrado: las consume _resolve_references justo despues, y sin ellas
        # una valoracion nunca encontraria su escenario.
        if name.startswith("_ref_"):
            if value not in (None, ""):
                values[name] = value
            continue
        if name.startswith("_") or name not in writable:
            continue
        spec_field = fmap.get(name)
        coerced = _coerce(value, spec_field)
        if coerced is None or coerced == "":
            continue
        values[name] = coerced
    return values, confidence, source_ref


def _coerce(value: Any, spec_field) -> Any:
    if value is None or spec_field is None:
        return value
    ftype = spec_field.type
    try:
        if ftype == "int":
            value = int(float(str(value).strip()))
        elif ftype == "float":
            value = float(str(value).strip())
        elif ftype == "bool":
            if isinstance(value, str):
                value = value.strip().lower() in ("si", "sí", "yes", "true", "1", "x")
            else:
                value = bool(value)
        elif ftype == "json":
            if not isinstance(value, (dict, list)):
                return None
        elif ftype == "datetime":
            value = _parse_date(value)
        else:
            value = str(value).strip()
            if spec_field.max_length:
                value = value[: spec_field.max_length]
    except (TypeError, ValueError):
        return None

    if spec_field.choices and value not in spec_field.choices:
        # Un valor fuera del vocabulario declarado se descarta en vez de
        # colarse: en la base solo entran valores que el resto del codigo
        # sabe interpretar.
        return None
    return value


def _parse_date(value):
    if hasattr(value, "isoformat"):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d",
                "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    if hasattr(a, "isoformat") and hasattr(b, "isoformat"):
        return a.replace(tzinfo=None) == b.replace(tzinfo=None)
    return a == b


def _index(result: MaterializationResult, spec, values: dict, record_id: int) -> None:
    """Guarda la fila en el indice del lote para resolver referencias."""
    for key_fields in (spec.natural_keys or ()):
        if all(values.get(f) not in (None, "") for f in key_fields):
            key = (spec.key,) + tuple(
                reconciler.normalize_name(values[f]) if isinstance(values[f], str)
                else values[f] for f in key_fields
            )
            result.index[key] = record_id


def _resolve_references(db, spec, values: dict, result: MaterializationResult,
                        org_id: Optional[int]) -> None:
    """Traduce referencias por clave natural a ids reales.

    El documento dice "esta valoracion es del escenario ALT.05"; en la base hay
    que guardar el id. Primero se busca en lo creado por este mismo lote y
    despues en lo que ya existia.
    """
    for fname, (target_entity, target_field) in (spec.references or {}).items():
        natural = values.pop("_ref_" + fname, None)
        if natural in (None, "") or values.get(fname):
            continue
        key = (target_entity, reconciler.normalize_name(natural)
               if isinstance(natural, str) else natural)
        found = result.index.get(key)
        if found:
            values[fname] = found
            continue
        target_spec = contracts.get(target_entity)
        if target_spec is None:
            continue
        resolved = _match_any_natural(db, target_spec, org_id, natural, target_field)
        if resolved is not None:
            values[fname] = resolved
        else:
            result.warnings.append(
                f"{spec.label}: no se encontro {target_entity} '{natural}'"
            )

    # Referencias que la entidad no declara: se descartan para que no lleguen
    # al constructor del modelo como argumentos inexistentes.
    for leftover in [k for k in values if k.startswith("_ref_")]:
        values.pop(leftover)


def _match_any_natural(db, target_spec, org_id, natural, preferred_field):
    """Resuelve una referencia contra CUALQUIER clave natural del destino.

    El documento puede citar un escenario por su codigo ("ALT.05") o por su
    nombre ("Caida de las comunicaciones"); ambos deben resolver al mismo
    registro. Se prueba primero el campo declarado en `references` y luego el
    resto de claves naturales de una sola columna. Generico para toda entidad.
    """
    fields = [preferred_field]
    for key_fields in (target_spec.natural_keys or ()):
        if len(key_fields) == 1 and key_fields[0] not in fields:
            fields.append(key_fields[0])
    for f in fields:
        match = reconciler.find_match(db, target_spec, org_id, {f: natural},
                                      name_field=f)
        if match.matched:
            return match.record.id
    return None
