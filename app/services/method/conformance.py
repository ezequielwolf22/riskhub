"""Conformidad de la plataforma con la politica del propio cliente.

Responde a una pregunta que hasta ahora nadie hacia: *lo que esta calculando la
herramienta, ¿coincide con lo que dice la norma interna aprobada de esta
organizacion?* Un informe de continuidad producido con parametros distintos a
los de su procedimiento es, para un auditor, un incumplimiento.

Cuatro hallazgos, y el ultimo es el que marca la linea de diseno:

- `default_used_despite_policy` — el cliente lo declaro y la plataforma sigue
  con su defecto.
- `manual_override_diverges_from_policy` — alguien lo cambio a mano y ya no
  coincide con la politica. No es un error (puede estar justificado), pero debe
  verse.
- `unmodelled_rule` — el agente leyo una regla suya que la plataforma no sabe
  aplicar.
- `policy_below_norm` — su metodo es mas laxo que el minimo normativo. **Se
  sigue calculando con el suyo**, porque es su politica aprobada y la
  herramienta no debe mentirle sobre sus propias cifras; lo que se hace es
  levantar el hallazgo citando las dos fuentes. Como calculo y si cumplo son dos
  preguntas distintas y mezclarlas las estropea las dos.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.services.method import registry
from app.services.method.bindings import resolve

logger = logging.getLogger("riskhub.method.conformance")

_MINIMA_PATH = Path(__file__).resolve().parents[2] / "data" / "normative_minima.json"
_minima_cache: Optional[list] = None


def normative_minima() -> list[dict]:
    global _minima_cache
    if _minima_cache is None:
        try:
            _minima_cache = json.loads(
                _MINIMA_PATH.read_text(encoding="utf-8")).get("minima", [])
        except Exception:
            logger.warning("method: no se pudieron leer los minimos normativos",
                           exc_info=True)
            _minima_cache = []
    return _minima_cache


def check(db, org_id: Optional[int]) -> list[dict]:
    """Calcula los hallazgos. No escribe: `refresh` es quien persiste."""
    from app.models import MethodStatement

    findings: list[dict] = []
    if not org_id:
        return findings

    statements = db.query(MethodStatement).filter_by(
        organization_id=org_id).filter(
        MethodStatement.status != "rejected").all()
    by_key: dict[str, list] = {}
    for st in statements:
        if st.parameter_key:
            by_key.setdefault(st.parameter_key, []).append(st)

    # 1) Reglas que la plataforma no sabe modelar
    for st in statements:
        if st.status == "unmodelled":
            findings.append({
                "kind": "unmodelled_rule", "parameter_key": None,
                "severity": "medium", "statement_id": st.id,
                "summary": (
                    "La plataforma no sabe aplicar esta regla de tu politica: "
                    f"\"{(st.quote or '')[:180]}\""),
                "policy_value": st.proposed_value,
            })

    # 2) y 3) Divergencias entre lo declarado y lo que usa el motor
    for key, sts in by_key.items():
        param = registry.get(key)
        if param is None:
            continue
        resolved = resolve(db, org_id, key)
        declared = sts[-1]

        if resolved.source == "default":
            findings.append({
                "kind": "default_used_despite_policy", "parameter_key": key,
                "severity": "high", "statement_id": declared.id,
                "summary": (
                    f"Tu politica fija '{param.label}' pero la plataforma sigue "
                    f"calculando con el valor por defecto."),
                "effective_value": resolved.value,
                "policy_value": declared.proposed_value,
            })
        elif (resolved.source == "manual"
              and not _same(resolved.value, declared.proposed_value)):
            findings.append({
                "kind": "manual_override_diverges_from_policy",
                "parameter_key": key, "severity": "medium",
                "statement_id": declared.id,
                "summary": (
                    f"'{param.label}' se fijo manualmente con un valor distinto "
                    f"al de tu politica."),
                "effective_value": resolved.value,
                "policy_value": declared.proposed_value,
            })

    # 4) Metodo del cliente mas laxo que el minimo normativo
    findings.extend(_check_norm(db, org_id, by_key))
    return findings


def _check_norm(db, org_id, by_key: dict) -> list[dict]:
    out = []
    for rule in normative_minima():
        key = rule.get("parameter_key")
        param = registry.get(key)
        if param is None:
            continue
        resolved = resolve(db, org_id, key)
        if resolved.is_default:
            continue        # el defecto de la plataforma ya cumple
        if not _below_norm(resolved.value, rule):
            continue
        declared = (by_key.get(key) or [None])[-1]
        out.append({
            "kind": "policy_below_norm", "parameter_key": key,
            "severity": rule.get("severity", "medium"),
            "statement_id": getattr(declared, "id", None),
            "summary": (
                f"Tu metodo para '{param.label}' es mas laxo que "
                f"{rule['normative_ref']}. Se sigue calculando con el tuyo; "
                f"esto es un hallazgo de cumplimiento, no un error de calculo."),
            "effective_value": resolved.value,
            "policy_value": resolved.value,
            "normative_ref": rule["normative_ref"],
            "normative_value": rule["value"],
        })
    return out


def _below_norm(value: Any, rule: dict) -> bool:
    """True si el valor del cliente incumple el minimo declarado."""
    comparison = rule.get("comparison")
    limit = rule.get("value")
    try:
        if comparison == "max":
            # Una cadencia mayor que el maximo normativo es mas laxa
            return float(value) > float(limit)
        if comparison == "min":
            return float(value) < float(limit)
        if comparison == "max_by_key" and isinstance(value, dict):
            return any(float(value.get(k, 0)) > float(v)
                       for k, v in (limit or {}).items() if k in value)
    except (TypeError, ValueError):
        return False
    return False


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    return a == b


def refresh(db, org_id: int) -> dict:
    """Recalcula los hallazgos y los persiste, conservando los ya aceptados."""
    from app.models import MethodFinding

    existing = db.query(MethodFinding).filter_by(organization_id=org_id).all()
    accepted = {(f.kind, f.parameter_key, f.statement_id)
                for f in existing if f.status == "accepted"}

    db.query(MethodFinding).filter_by(organization_id=org_id).filter(
        MethodFinding.status != "accepted").delete(synchronize_session=False)

    created = 0
    for data in check(db, org_id):
        signature = (data["kind"], data.get("parameter_key"),
                     data.get("statement_id"))
        if signature in accepted:
            continue        # ya lo revisaron y lo dieron por bueno
        db.add(MethodFinding(
            organization_id=org_id, kind=data["kind"],
            parameter_key=data.get("parameter_key"),
            severity=data.get("severity", "medium"),
            summary=data.get("summary"),
            statement_id=data.get("statement_id"),
            effective_value=data.get("effective_value"),
            policy_value=data.get("policy_value"),
            normative_ref=data.get("normative_ref"),
            normative_value=data.get("normative_value"),
            status="open",
        ))
        created += 1
    db.commit()
    return {"findings": created, "accepted_kept": len(accepted)}


def summary(db, org_id: Optional[int]) -> dict:
    """Cabecera para la vista: cuantos parametros son suyos y cuantos no."""
    params = registry.all_params()
    from_policy = manual = default = 0
    for key in params:
        source = resolve(db, org_id, key).source
        if source == "policy":
            from_policy += 1
        elif source == "manual":
            manual += 1
        else:
            default += 1

    findings = check(db, org_id)
    by_kind: dict[str, int] = {}
    for f in findings:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1

    return {
        "parameters_total": len(params),
        "from_policy": from_policy, "manual": manual, "default": default,
        "wired": sum(1 for p in params.values() if p.wired),
        "findings_total": len(findings), "findings_by_kind": by_kind,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
