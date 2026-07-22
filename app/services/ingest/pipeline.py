"""Orquestacion de la ingesta de un pack documental.

Encadena las piezas en el orden que hace que el resultado sea coherente:

    leer  ->  perfil del cliente  ->  mapa por documento  ->  volcado  ->  verificar

El perfil va primero por una razon de fondo: sin saber que sedes tiene el
cliente ni con que metodo valora el impacto, cada documento se interpretaria
por su cuenta y el resultado seria un mosaico incoherente. Con el perfil
delante, todos los documentos hablan del mismo mapa de sedes y del mismo
baremo, y las referencias cruzadas encajan.

Al final se recalcula el motor determinista y se declaran los huecos: importar
no es solo escribir filas, es dejar claro que falta para cerrar ISO 22301.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.services.ingest import batch as batch_mod
from app.services.ingest import comprehension, contracts, reader
from app.services.ingest.materializer import MaterializationResult, materialize

logger = logging.getLogger("riskhub.ingest.pipeline")

# Coste aproximado por documento, para la estimacion previa. Ordenes de
# magnitud medidos en produccion, no precios de tarifa.
_COST_PER_1K_CHARS = {"deep": 0.0009, "fast": 0.00006}


class PackCancelled(Exception):
    """El usuario cancelo el trabajo desde la cola."""


# ── Estimacion previa ────────────────────────────────────────────────────────

def estimate_pack(files: list[tuple[str, bytes]], tier: str = "deep") -> dict:
    """Cuanto costaria comprender este pack, antes de lanzarlo.

    Mismo criterio que `analysis_pool_summary` para el analisis masivo de
    activos: cifras antes de gastar, no una sorpresa en la factura.
    """
    documents, unsupported = [], []
    total_chars = 0
    for filename, data in files:
        if not reader.is_supported(filename):
            unsupported.append(filename)
            continue
        try:
            doc = reader.read_document(data, filename)
        except Exception as exc:
            unsupported.append(f"{filename} ({exc})")
            continue
        chars = len(reader.render_for_llm(doc))
        total_chars += chars
        documents.append({"filename": filename, "format": doc["format"],
                          "chars": chars, "stats": doc["stats"]})

    rate = _COST_PER_1K_CHARS.get(tier, _COST_PER_1K_CHARS["deep"])
    # Dos pasadas sobre el material: perfil (recortado) y mapa por documento.
    cost = (total_chars / 1000.0) * rate * 1.4
    return {
        "documents": documents,
        "documents_total": len(documents),
        "unsupported": unsupported,
        "total_chars": total_chars,
        "tier": tier,
        "estimated_cost_usd": round(cost, 4),
    }


# ── Ejecucion ────────────────────────────────────────────────────────────────

def run_pack(db, org_id: Optional[int], files: list[tuple[str, bytes]], *,
             user_id: Optional[int] = None, job_id: Optional[int] = None,
             tier: str = "deep", lang: str = "es",
             apply_profile: bool = True,
             cancel_check=None) -> dict:
    """Ingesta completa de un pack. Devuelve el resumen del lote."""
    estimate = estimate_pack(files, tier)
    bat = batch_mod.create_batch(
        db, org_id, module="bcm", job_id=job_id, user_id=user_id,
        files=[{"filename": d["filename"], "format": d["format"],
                "status": "pending"} for d in estimate["documents"]],
        estimated_cost_usd=estimate["estimated_cost_usd"],
    )
    summary = dict(bat.summary or {})
    warnings: list[str] = [f"Formato no soportado: {f}"
                           for f in estimate["unsupported"]]

    try:
        documents = []
        for filename, data in files:
            if not reader.is_supported(filename):
                continue
            try:
                documents.append(reader.read_document(data, filename))
            except Exception as exc:
                warnings.append(f"No se pudo leer {filename}: {exc}")

        if not documents:
            return _finish(db, bat, summary, warnings, status="failed")

        # ── Pasada 1: el perfil del cliente ──────────────────────────────
        profile_data = None
        if apply_profile:
            _check_cancel(cancel_check)
            try:
                existing = _get_profile(db, org_id)
                profile_data = comprehension.build_profile(
                    db, org_id, documents, existing_profile=existing, lang=lang)
                bat.profile_diff = profile_data
                db.commit()
            except Exception as exc:
                logger.warning("ingest: no se pudo construir el perfil: %s", exc,
                               exc_info=True)
                warnings.append(f"No se pudo deducir el perfil: {exc}")

        result = MaterializationResult()
        if profile_data:
            _materialize_profile(db, org_id, bat, profile_data, result, warnings)
            _save_profile(db, org_id, profile_data)

        # ── Pasada 2 y 3: mapa por documento y volcado ───────────────────
        file_reports = []
        for doc in documents:
            _check_cancel(cancel_check)
            report = {"filename": doc["filename"], "format": doc["format"]}
            try:
                smap = comprehension.build_source_map(
                    db, org_id, doc, profile=profile_data, lang=lang, tier=tier)
                map_row = _save_source_map(db, org_id, bat, smap)
                report.update({
                    "doc_kind": smap.get("doc_kind"),
                    "confidence": smap.get("confidence"),
                    "units": len(smap.get("units") or []),
                    "rows": sum(len(u.get("rows") or []) for u in smap.get("units") or []),
                    "source_map_id": map_row.id if map_row else None,
                    "status": "ok",
                })
                _materialize_map(db, org_id, bat, smap, result, map_row)
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.warning("ingest: fallo con %s: %s", doc["filename"], exc,
                               exc_info=True)
                report.update({"status": "failed", "error": str(exc)[:300]})
                warnings.append(f"{doc['filename']}: {exc}")
            file_reports.append(report)

        # ── Verificacion: recalcular y declarar huecos ───────────────────
        gaps = _verify(db, org_id, warnings)

        summary.update({
            "created": result.created, "updated": result.updated,
            "linked": result.linked, "needs_review": result.needs_review,
            "conflicts": result.conflicts, "skipped": result.skipped[:50],
            "gaps": gaps,
        })
        bat.files = file_reports
        warnings.extend(result.warnings)
        return _finish(db, bat, summary, warnings, status="completed")

    except PackCancelled:
        return _finish(db, bat, summary, warnings + ["Cancelado por el usuario"],
                       status="failed")
    except Exception as exc:
        logger.exception("ingest: el pack fallo por completo")
        return _finish(db, bat, summary, warnings + [str(exc)[:300]], status="failed")


def _check_cancel(cancel_check) -> None:
    if cancel_check and cancel_check():
        raise PackCancelled()


def _finish(db, bat, summary: dict, warnings: list, status: str) -> dict:
    summary["warnings"] = warnings[:80]
    bat.summary = summary
    bat.status = status
    bat.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"batch_id": bat.id, "status": status, **summary}


# ── Perfil ───────────────────────────────────────────────────────────────────

def _get_profile(db, org_id: Optional[int]):
    from app.models import OrganizationProfile
    return db.query(OrganizationProfile).filter_by(organization_id=org_id).first()


def _save_profile(db, org_id: Optional[int], data: dict) -> None:
    from app.models import OrganizationProfile
    row = _get_profile(db, org_id)
    if not row:
        row = OrganizationProfile(organization_id=org_id)
        db.add(row)
    row.structure = data.get("structure")
    row.method = {"bcm": data.get("bia_method") or {}}
    row.vocabulary = data.get("vocabulary")
    row.narrative = data.get("narrative")
    row.confidence = data.get("confidence")
    row.derived_from = "documents"
    db.commit()


def _materialize_profile(db, org_id, bat, profile: dict,
                         result: MaterializationResult, warnings: list) -> None:
    """Crea sedes, escenarios, baremo y reglas deducidos del pack.

    Va antes que los documentos porque el resto de filas los referencian por
    nombre: si las sedes no existen todavia, cada valoracion se queda huerfana.
    """
    structure = profile.get("structure") or {}
    locations = [
        {k: v for k, v in loc.items() if k != "evidence"}
        for loc in (structure.get("locations") or []) if loc.get("name")
    ]
    if locations:
        materialize(db, org_id, bat, "bcm_location", locations,
                    source_filename="(perfil deducido del pack)", result=result)

    scenarios = [s for s in (profile.get("scenarios") or []) if s.get("name")]
    if scenarios:
        materialize(db, org_id, bat, "bcm_scenario", scenarios,
                    source_filename="(perfil deducido del pack)", result=result)

    _save_bia_criteria(db, org_id, profile.get("bia_method") or {}, warnings)
    _save_rules(db, org_id, bat, profile.get("applicability_rules") or [], warnings)
    db.commit()


def _save_bia_criteria(db, org_id, method: dict, warnings: list) -> None:
    """Registra el metodo del cliente. Solo lo que venga completo."""
    from app.models import BIACriteria
    fields = {k: method.get(k) for k in
              ("dimensions", "horizons", "rto_scale", "bands", "aggregation")
              if method.get(k)}
    if not fields:
        return
    row = db.query(BIACriteria).filter_by(organization_id=org_id).first()
    if row is None:
        row = BIACriteria(organization_id=org_id)
        db.add(row)
    elif row.dimensions or row.horizons:
        # Ya tenia metodo propio: no se pisa desde un documento.
        warnings.append(
            "La organizacion ya tenia baremo BIA declarado; se conserva el suyo."
        )
        return
    for key, value in fields.items():
        setattr(row, key, value)


def _save_rules(db, org_id, bat, rules: list, warnings: list) -> None:
    """Guarda las reglas propuestas, siempre DESACTIVADAS.

    Una regla activa oculta escenarios de la matriz de cobertura. Que el agente
    proponga una a partir de una frase de un documento no basta para que empiece
    a ocultar riesgo: se guarda con su justificacion y una persona la activa.
    """
    from app.models import BCMApplicabilityRule
    for rule in rules:
        exists = db.query(BCMApplicabilityRule).filter_by(
            organization_id=org_id).filter(
            BCMApplicabilityRule.when == rule.get("when")).first()
        if exists:
            continue
        db.add(BCMApplicabilityRule(
            organization_id=org_id, name=rule.get("name"),
            when=rule.get("when"), then=rule.get("then"),
            rationale=rule.get("rationale"),
            source="proposed", is_active=False,
            import_batch_id=bat.id,
        ))
        warnings.append(
            f"Regla de aplicabilidad propuesta (desactivada hasta que la "
            f"revises): {rule.get('rationale', '')[:120]}"
        )


# ── Mapa y volcado ───────────────────────────────────────────────────────────

def _save_source_map(db, org_id, bat, smap: dict):
    """Guarda el "como lo entendi", sin las filas completas."""
    from app.models import IngestSourceMap
    row = IngestSourceMap(
        organization_id=org_id, batch_id=bat.id,
        filename=smap.get("filename"), sha256=smap.get("sha256"),
        doc_kind=smap.get("doc_kind"),
        units_detected=[
            {"label": u.get("label"), "source_ref": u.get("source_ref"),
             "decomposition_key": u.get("decomposition_key"),
             "target_entity": u.get("target_entity"),
             "unit_count": len(u.get("rows") or []),
             "confidence": u.get("confidence"),
             "sample": (u.get("rows") or [{}])[0].get("fields")}
            for u in (smap.get("units") or [])
        ],
        ambiguities=smap.get("ambiguities"),
        rationale=smap.get("rationale"),
        confidence=smap.get("confidence"),
        status="executed",
    )
    db.add(row)
    db.flush()
    return row


def _materialize_map(db, org_id, bat, smap: dict,
                     result: MaterializationResult, map_row) -> None:
    """Vuelca las unidades en orden de dependencia.

    El orden importa: un escenario debe existir antes que su valoracion, y una
    sede antes que el proceso que la referencia. `ordered_keys` lo resuelve a
    partir de `depends_on`, asi que el agente no tiene que acertar el orden.
    """
    by_entity: dict[str, list] = {}
    for unit in smap.get("units") or []:
        by_entity.setdefault(unit["target_entity"], []).extend(
            comprehension.rows_for_materializer(unit))

    document_date = _parse_doc_date(smap.get("document_date"))
    for entity_key in contracts.ordered_keys():
        rows = by_entity.get(entity_key)
        if not rows:
            continue
        materialize(db, org_id, bat, entity_key, rows,
                    source_filename=smap.get("filename"),
                    sha256=smap.get("sha256"), document_date=document_date,
                    source_map_id=getattr(map_row, "id", None), result=result)


def _parse_doc_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:19]).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ── Verificacion ─────────────────────────────────────────────────────────────

def _verify(db, org_id: Optional[int], warnings: list) -> dict:
    """Recalcula lo determinista y cuenta los huecos que quedan.

    Importar sin esto seria escribir filas y callarse: el valor esta en decir
    que falta para cerrar la norma.
    """
    from app.services.bcm_scenario_engine import coverage_gaps, recompute_org
    out = {"recalculated": 0, "by_reason": {}, "total": 0}
    try:
        out["recalculated"] = recompute_org(db, org_id)
    except Exception as exc:
        warnings.append(f"No se pudo recalcular el BIA: {exc}")
    try:
        gaps = coverage_gaps(db, org_id)
        out["total"] = len(gaps)
        for gap in gaps:
            for reason in gap["reasons"]:
                out["by_reason"][reason] = out["by_reason"].get(reason, 0) + 1
    except Exception as exc:
        warnings.append(f"No se pudieron calcular los huecos: {exc}")
    return out
