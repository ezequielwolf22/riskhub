"""Perfil de madurez del Plan Director — fases 1 y 2 de la metodologia.

INCIBE (Plan Director de Seguridad):
  Fase 1 "conocer la situacion actual" -> perfil actual, madurez 0-5 por control.
  Fase 2 "conocer la estrategia"       -> perfil objetivo.
  Fase 3 "definir proyectos"           -> el gap se convierte en iniciativas.

NIST CSF 2.0: lo mismo con otro nombre — Current Profile, Target Profile y el
gap entre ambos como motor del plan de accion.

Principio del modulo: DETERMINISTA. El perfil actual se lee de la madurez real
de los controles (ya ajustada por calidad de evidencia); el gap es aritmetica;
las iniciativas candidatas se agrupan por tema del catalogo. La IA solo redacta
narrativa despues, nunca decide que controles entran ni que riesgos se tocan.

El objetivo se puede fijar en el lenguaje del cliente (categoria NIST CSF,
requisito del ENS...) y el crossmap lo traduce a controles ISO 27002, que es el
sustrato que entiende el motor de riesgo.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import (
    Control, ControlImplementation, MaturityTarget, StrategicInitiative, StrategicPlan,
)

logger = logging.getLogger(__name__)

_CROSSMAP_PATH = Path(__file__).parent.parent / "data" / "frameworks" / "control_crossmap.json"
_CROSSMAP: dict | None = None

# Coste tipico de subir un control un escalon de madurez CMM. Sirve para
# ordenar el esfuerzo del gap, no para presupuestar: el presupuesto real lo
# pone una persona en cada iniciativa.
_EFFORT_DAYS_PER_MATURITY_STEP = 5.0


def _load_crossmap() -> dict:
    """Mapeo control ISO 27002 -> requisitos de otros frameworks."""
    global _CROSSMAP
    if _CROSSMAP is None:
        try:
            _CROSSMAP = json.loads(_CROSSMAP_PATH.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("strategic_profile: no se pudo leer el crossmap")
            _CROSSMAP = {}
    return _CROSSMAP


def _norm_code(code: str | None) -> str:
    """'A.5.1' y '5.1' son el mismo control."""
    return (code or "").strip().lstrip("A.").strip()


def controls_for_requirement(framework_code: str, requirement_id: str) -> list[str]:
    """Controles ISO 27002 que cubren un requisito de otro framework.

    El crossmap indexa por control; aqui se invierte. Un requisito de CSF o del
    ENS suele necesitar varios controles ISO.
    """
    out = []
    for control_code, refs in _load_crossmap().items():
        if control_code.startswith("_"):
            continue
        for ref in refs or []:
            if ref.get("f") == framework_code and ref.get("r") == requirement_id:
                out.append(control_code)
                break
    return sorted(out)


def compute_current_profile(db: Session, org_id: int) -> dict:
    """Perfil actual: madurez real por control ISO 27002 (INCIBE fase 1).

    Un control sin implementacion en la organizacion tiene madurez 0 — no se
    omite: que no exista ES el dato relevante para un plan director.
    """
    impl_by_control: dict[int, ControlImplementation] = {}
    for impl in db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == org_id
    ).order_by(ControlImplementation.id.asc()).all():
        # Si hay varias implementaciones del mismo control, manda la mas madura
        current = impl_by_control.get(impl.control_id)
        if current is None or (impl.maturity or 0) > (current.maturity or 0):
            impl_by_control[impl.control_id] = impl

    entries = []
    for c in db.query(Control).order_by(Control.code.asc()).all():
        impl = impl_by_control.get(c.id)
        entries.append({
            "control_id": c.id,
            "code": c.code,
            "name": c.name,
            "theme": c.theme,
            "maturity": (impl.maturity or 0) if impl else 0,
            "implementation_id": impl.id if impl else None,
            "implemented": impl is not None,
            "status": (impl.status.value if hasattr(impl.status, "value") else impl.status)
                      if impl else None,
        })

    total = len(entries)
    avg = round(sum(e["maturity"] for e in entries) / total, 2) if total else 0.0
    by_theme: dict[str, list] = {}
    for e in entries:
        by_theme.setdefault(e["theme"] or "sin_tema", []).append(e["maturity"])
    return {
        "controls": entries,
        "average_maturity": avg,
        "implemented_count": sum(1 for e in entries if e["implemented"]),
        "total_controls": total,
        "by_theme": {
            theme: round(sum(v) / len(v), 2) for theme, v in sorted(by_theme.items())
        },
    }


def resolve_targets_detailed(db: Session, plan: StrategicPlan) -> dict:
    """Objetivos del plan resueltos a controles ISO 27002 concretos.

    Un objetivo fijado sobre un requisito de framework se expande a todos los
    controles que lo cubren. Si un control recibe varios objetivos, gana el mas
    exigente: el plan promete lo maximo que haya prometido.

    Devuelve tambien los objetivos que NO se han podido resolver. El crossmap no
    cubre todas las categorias (p.ej. varias de gobierno y comunicacion de NIST
    CSF no tienen control ISO 27002 equivalente), y un objetivo que se descarta
    en silencio es peor que uno que se declara imposible de traducir: el usuario
    creeria estar cubriendo algo que el plan no toca.
    """
    by_control: dict[int, dict] = {}
    unresolved: list[dict] = []
    controls_by_code = {
        _norm_code(c.code): c for c in db.query(Control).all()
    }

    for target in plan.targets:
        resolved: list[Control] = []
        source = None
        if target.control_id:
            control = db.get(Control, target.control_id)
            if control:
                resolved = [control]
                source = "control"
        elif target.framework_code and target.requirement_id:
            for code in controls_for_requirement(target.framework_code, target.requirement_id):
                control = controls_by_code.get(_norm_code(code))
                if control:
                    resolved.append(control)
            source = f"{target.framework_code}:{target.requirement_id}"

        if not resolved:
            unresolved.append({
                "target_id": target.id,
                "control_id": target.control_id,
                "framework_code": target.framework_code,
                "requirement_id": target.requirement_id,
                "target_maturity": target.target_maturity,
                "mandatory_by": target.mandatory_by,
                "reason": (
                    "sin_control_equivalente"
                    if target.framework_code else "control_inexistente"
                ),
            })
            continue

        for control in resolved:
            existing = by_control.get(control.id)
            if existing and existing["target_maturity"] >= target.target_maturity:
                continue
            by_control[control.id] = {
                "control_id": control.id,
                "code": control.code,
                "name": control.name,
                "theme": control.theme,
                "target_maturity": target.target_maturity,
                "mandatory_by": target.mandatory_by,
                "rationale": target.rationale,
                "source": source,
            }
    return {"resolved": by_control, "unresolved": unresolved}


def resolve_targets(db: Session, plan: StrategicPlan) -> dict[int, dict]:
    """Solo los objetivos resueltos (ver resolve_targets_detailed)."""
    return resolve_targets_detailed(db, plan)["resolved"]


def compute_gap(db: Session, plan: StrategicPlan) -> dict:
    """Delta entre perfil objetivo y perfil actual (INCIBE fase 3, CSF gap).

    Solo aparecen los controles donde el objetivo supera lo que hay hoy: un
    control ya por encima del objetivo no es un hueco, es una fortaleza.
    """
    org_id = plan.organization_id
    current = compute_current_profile(db, org_id)
    current_by_id = {e["control_id"]: e for e in current["controls"]}
    detailed = resolve_targets_detailed(db, plan)
    targets = detailed["resolved"]

    gaps = []
    for control_id, target in targets.items():
        cur = current_by_id.get(control_id)
        current_maturity = cur["maturity"] if cur else 0
        delta = target["target_maturity"] - current_maturity
        if delta <= 0:
            continue
        gaps.append({
            **target,
            "current_maturity": current_maturity,
            "implementation_id": cur["implementation_id"] if cur else None,
            "implemented": bool(cur and cur["implemented"]),
            "gap": delta,
            "effort_days": round(delta * _EFFORT_DAYS_PER_MATURITY_STEP, 1),
        })

    # Los huecos obligatorios (legal/contractual) primero; luego los mas grandes
    _mandatory_rank = {"legal": 0, "contractual": 1, "riesgo": 2, "estrategia": 3}
    gaps.sort(key=lambda g: (
        _mandatory_rank.get(g.get("mandatory_by"), 9), -g["gap"], g["code"],
    ))

    covered = _controls_already_in_plan(db, plan)
    return {
        "plan_id": plan.id,
        "framework_code": plan.framework_code,
        "gaps": gaps,
        "targets_total": len(targets),
        "gap_count": len(gaps),
        "total_gap_points": sum(g["gap"] for g in gaps),
        "total_effort_days": round(sum(g["effort_days"] for g in gaps), 1),
        "current_average_maturity": current["average_maturity"],
        "by_theme": current["by_theme"],
        # Objetivos que no se pueden traducir a un control ISO 27002: se
        # declaran, no se descartan en silencio
        "unresolved_targets": detailed["unresolved"],
        # Controles del gap que YA tiene alguna iniciativa del plan: sirve para
        # no proponer dos veces lo mismo
        "already_covered_control_ids": sorted(covered),
    }


def _controls_already_in_plan(db: Session, plan: StrategicPlan) -> set[int]:
    """Ids de control que ya son objetivo de alguna iniciativa viva del plan."""
    from app.models import InitiativeControlTarget, StrategicProgram

    program_ids = [p.id for p in db.query(StrategicProgram).filter(
        StrategicProgram.plan_id == plan.id).all()]
    if not program_ids:
        return set()
    initiatives = db.query(StrategicInitiative).filter(
        StrategicInitiative.program_id.in_(program_ids),
        StrategicInitiative.status.notin_(["cancelled"]),
    ).all()
    if not initiatives:
        return set()
    rows = db.query(InitiativeControlTarget, ControlImplementation).join(
        ControlImplementation,
        InitiativeControlTarget.implementation_id == ControlImplementation.id,
    ).filter(
        InitiativeControlTarget.initiative_id.in_([i.id for i in initiatives])
    ).all()
    return {impl.control_id for _, impl in rows}


def generate_candidate_initiatives(db: Session, plan: StrategicPlan,
                                   max_initiatives: int = 12) -> dict:
    """Convierte el gap en iniciativas candidatas (INCIBE fase 3).

    Determinista y explicable: agrupa los controles con hueco por tema del
    catalogo ISO 27002, y cada grupo se propone como una iniciativa con sus
    controles objetivo ya puestos. No se persiste nada — es una propuesta que
    el usuario confirma, igual que el import de plan por IA.
    """
    gap = compute_gap(db, plan)
    covered = set(gap["already_covered_control_ids"])
    pending = [g for g in gap["gaps"] if g["control_id"] not in covered]

    by_theme: dict[str, list] = {}
    for g in pending:
        by_theme.setdefault(g.get("theme") or "General", []).append(g)

    candidates = []
    for theme, items in sorted(by_theme.items(), key=lambda kv: -sum(g["gap"] for g in kv[1])):
        items.sort(key=lambda g: (-g["gap"], g["code"]))
        mandatory = [g for g in items if g.get("mandatory_by") in ("legal", "contractual")]
        origin = "legal" if mandatory else "riesgo"
        candidates.append({
            "title": f"Elevar madurez de {theme}",
            "theme": theme,
            "origin": origin,
            "action_type": "tecnica",
            "description": (
                f"Elevar la madurez de {len(items)} controles del ambito '{theme}' "
                f"hasta el objetivo del plan."
            ),
            "effort_human": round(sum(g["effort_days"] for g in items), 1),
            "control_targets": [
                {"control_id": g["control_id"], "code": g["code"], "name": g["name"],
                 "current_maturity": g["current_maturity"],
                 "target_maturity": g["target_maturity"]}
                for g in items
            ],
            "gap_points": sum(g["gap"] for g in items),
            "mandatory": bool(mandatory),
        })

    return {
        "plan_id": plan.id,
        "candidates": candidates[:max_initiatives],
        "controls_pending": len(pending),
        "controls_already_covered": len(covered),
        "total_gap_points": gap["total_gap_points"],
    }


def seal_baseline(db: Session, plan: StrategicPlan) -> dict:
    """Sella el perfil actual como linea base del plan.

    Se ejecuta al aprobar: a partir de ahi el avance se mide contra algo fijo.
    Si se volviera a calcular en cada consulta, el progreso se movaria solo
    porque el mundo cambia, y el plan dejaria de ser medible.
    """
    from datetime import datetime, timezone

    profile = compute_current_profile(db, plan.organization_id)
    plan.baseline_profile = {
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "average_maturity": profile["average_maturity"],
        "controls": {e["code"]: e["maturity"] for e in profile["controls"]},
    }
    plan.baseline_sealed_at = datetime.now(timezone.utc)
    db.flush()
    return plan.baseline_profile


def plan_progress(db: Session, plan: StrategicPlan) -> dict:
    """Avance del plan: perfil actual contra la linea base sellada y el objetivo.

    Sin linea base sellada (plan aun sin aprobar) se informa, no se inventa.
    """
    current = compute_current_profile(db, plan.organization_id)
    targets = resolve_targets(db, plan)
    baseline = (plan.baseline_profile or {}).get("controls") or {}

    current_by_code = {e["code"]: e["maturity"] for e in current["controls"]}
    target_points = 0
    achieved_points = 0
    for control_id, target in targets.items():
        code = target["code"]
        base = baseline.get(code)
        if base is None:
            base = current_by_code.get(code, 0)
        goal = target["target_maturity"]
        now_val = current_by_code.get(code, 0)
        target_points += max(0, goal - base)
        achieved_points += max(0, min(now_val, goal) - base)

    pct = round(achieved_points / target_points * 100) if target_points else 0
    return {
        "baseline_sealed": bool(plan.baseline_sealed_at),
        "baseline_average_maturity": (plan.baseline_profile or {}).get("average_maturity"),
        "current_average_maturity": current["average_maturity"],
        "target_points": target_points,
        "achieved_points": achieved_points,
        "progress_pct": pct,
    }
