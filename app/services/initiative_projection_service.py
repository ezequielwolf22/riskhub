"""Motor determinista del Plan Director (v6.3.0).

Nada de IA aqui: es matematica sobre el mismo motor de riesgo que usa el
recalculo real (risk_engine + risk_recalc_service). Tres piezas:

  - auto_link_risks: deriva que riesgos afecta una iniciativa a partir de sus
    controles objetivo (via risk_controls directo + threat_control_map).
  - project_initiative: simula la madurez objetivo de esos controles con el
    MISMO motor que calcula el residual real, y guarda el residual proyectado
    por riesgo. Nunca escribe residual_level ni maturity reales.
  - verify_initiative: al completar una iniciativa, compara lo proyectado con
    lo que el motor real acabo calculando. El gap queda visible, nunca oculto.

reproject_for_impls se invoca desde risk_recalc_service.recalc_risks_for_impls
(import diferido, evita ciclo) para que la proyeccion nunca quede obsoleta
cuando el mundo real cambia.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

from app.models import (
    ControlImplementation, InitiativeControlTarget, InitiativeLogEntry,
    InitiativeRiskLink, Risk, RiskStatus, StrategicInitiative, risk_control_table,
)
from app.services.risk_recalc_service import control_payload, get_context, get_matrix, residual_from_payloads
from app.services.threat_knowledge import controls_for_threat

logger = logging.getLogger(__name__)


# ---------- Priorizacion determinista (INCIBE fase 4) ----------
#
# INCIBE prioriza los proyectos del Plan Director por el esfuerzo que exigen
# (humano, economico, temporal) frente a la mejora de seguridad que producen, y
# destaca los "quick wins": minimo esfuerzo, mejora sustancial. Aqui eso se
# CALCULA a partir de la reduccion que ya proyecta el motor determinista, en vez
# de dejar que alguien elija una prioridad en un desplegable.

_HORIZON_SHORT_DAYS = 183     # ~6 meses
_HORIZON_MEDIUM_DAYS = 548    # ~18 meses


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Percentil por interpolacion lineal. Lista vacia -> 0."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * pct
    low = int(pos)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)


def initiative_horizon(initiative: StrategicInitiative, now: datetime | None = None) -> str | None:
    """corto | medio | largo segun la fecha objetivo (INCIBE fase 4)."""
    target = _aware(initiative.target_date)
    if not target:
        return None
    now = now or datetime.now(timezone.utc)
    days = (target - now).days
    if days <= _HORIZON_SHORT_DAYS:
        return "corto"
    if days <= _HORIZON_MEDIUM_DAYS:
        return "medio"
    return "largo"


def initiative_effort(initiative: StrategicInitiative) -> float | None:
    """Esfuerzo combinado (economico + humano) en unidades comparables.

    Se toma el presupuesto solicitado y se le suma el coste implicito de los
    dias-persona. Sin ninguno de los dos, el esfuerzo es desconocido (None) y la
    iniciativa no puede rankearse por eficiencia: se dice, no se inventa.
    """
    budget = initiative.budget
    human = initiative.effort_human
    if budget is None and human is None:
        return None
    # 1 dia-persona ~ 400 u.m. — factor de conversion unico y explicito para que
    # esfuerzo humano y economico sean sumables. No pretende ser un coste real.
    return (budget or 0.0) + (human or 0.0) * 400.0


def initiative_budget_health(initiative: StrategicInitiative) -> dict | None:
    """El presupuesto aprobado deberia seguir al progreso: requerido x % avance.

    Si una iniciativa va al 60% pero solo tiene aprobado el 20% de lo que pidio,
    esta infrafinanciada y el avance se va a detener. Idea tomada del cuadro de
    mando real del usuario ("Approved budget follows progress").
    """
    budget = initiative.budget
    if not budget:
        return None
    approved = initiative.budget_approved or 0.0
    progress = max(0, min(100, initiative.progress or 0))
    expected = budget * progress / 100.0
    gap = budget - approved
    return {
        "required": round(budget, 2),
        "approved": round(approved, 2),
        "spent": round(initiative.spent, 2) if initiative.spent is not None else None,
        "expected_approved": round(expected, 2),
        "funding_gap": round(gap, 2),
        "underfunded": approved + 1e-9 < expected,
    }


def compute_portfolio_priorities(initiatives: list[StrategicInitiative]) -> dict[int, dict]:
    """Prioridad sugerida, quick wins y eficiencia de toda una cartera.

    Devuelve {initiative_id: {...}}. Los umbrales son PERCENTILES de la propia
    cartera, no numeros inventados: "poco esfuerzo" y "mucha reduccion"
    significan poco y mucho respecto a lo que esta organizacion tiene sobre la
    mesa. Con una sola iniciativa no hay cartera con la que comparar y no se
    marca quick win.
    """
    now = datetime.now(timezone.utc)

    reductions: dict[int, int] = {}
    efforts: dict[int, float | None] = {}
    for ini in initiatives:
        points = sum(
            (link.baseline_residual_level - link.projected_residual_level)
            for link in ini.risk_links
            if link.baseline_residual_level is not None
            and link.projected_residual_level is not None
        )
        reductions[ini.id] = max(0, points)
        efforts[ini.id] = initiative_effort(ini)

    known_efforts = sorted(e for e in efforts.values() if e is not None and e > 0)
    positive_reductions = sorted(v for v in reductions.values() if v > 0)
    effort_median = _percentile(known_efforts, 0.5)
    reduction_median = _percentile(positive_reductions, 0.5)

    # Eficiencia = puntos de riesgo eliminados por cada 1.000 u.m. de esfuerzo.
    # Hace falta ANTES de decidir los quick wins: sin ella, una iniciativa cara y
    # mediocre puede colarse solo por quedar en el centro de la cartera.
    def _score_of(points: int, effort: float | None) -> float | None:
        if points > 0 and effort is not None and effort > 0:
            return round(points / (effort / 1000.0), 3)
        return None

    all_scores = sorted(
        s for s in (_score_of(reductions[i.id], efforts[i.id]) for i in initiatives)
        if s is not None
    )
    # Tercio superior de eficiencia: umbral relativo a la cartera, no inventado
    efficiency_top = _percentile(all_scores, 0.66)

    out: dict[int, dict] = {}
    for ini in initiatives:
        points = reductions[ini.id]
        effort = efforts[ini.id]
        factors: dict = {
            "reduction_points": points,
            "effort": round(effort, 2) if effort is not None else None,
            "effort_known": effort is not None,
        }

        score = _score_of(points, effort)
        cost_per_point = round(effort / points, 2) if score is not None else None
        if points > 0 and (effort is None or effort == 0):
            factors["note"] = "sin esfuerzo declarado"

        # Quick win (INCIBE): minimo esfuerzo y mejora sustancial. Exige las dos
        # cosas Y estar en el tercio mas eficiente: sin este ultimo filtro, la
        # iniciativa mas cara por punto de riesgo puede acabar marcada como quick
        # win solo por caer en la mediana de ambos ejes.
        quick_win = bool(
            len(initiatives) > 1
            and points > 0
            and effort is not None and effort > 0
            and effort <= effort_median
            and score is not None and score >= efficiency_top
        )
        factors["quick_win_thresholds"] = {
            "reduction_median": round(reduction_median, 2),
            "effort_median": round(effort_median, 2),
            "efficiency_top_third": round(efficiency_top, 3),
        }

        # Prioridad sugerida: los quick wins suben, y a mas reduccion mas alta.
        # Un riesgo que no reduce nada nunca es critico por si solo.
        if points <= 0:
            suggested = "low"
        elif quick_win:
            suggested = "critical" if points >= reduction_median else "high"
        elif points >= _percentile(positive_reductions, 0.75):
            suggested = "critical"
        elif points >= reduction_median:
            suggested = "high"
        else:
            suggested = "medium"

        out[ini.id] = {
            "priority_suggested": suggested,
            "priority_score": score,
            "priority_factors": factors,
            "quick_win": quick_win,
            "cost_per_point": cost_per_point,
            "horizon": initiative_horizon(ini, now),
            "budget_health": initiative_budget_health(ini),
        }
    return out


# ---------- Dependencias y camino critico ----------

def _dependency_graph(initiatives: list[StrategicInitiative]) -> dict[int, list[int]]:
    """blocked_by depurado: solo ids que existen en la cartera y sin auto-ciclos."""
    valid = {i.id for i in initiatives}
    graph: dict[int, list[int]] = {}
    for ini in initiatives:
        deps = ini.blocked_by or []
        graph[ini.id] = [d for d in deps if d in valid and d != ini.id]
    return graph


def detect_dependency_cycles(initiatives: list[StrategicInitiative]) -> list[list[int]]:
    """Ciclos en las dependencias. Un ciclo hace que el plan sea inejecutable,
    asi que se detecta y se muestra en vez de colgar el calculo del camino."""
    graph = _dependency_graph(initiatives)
    cycles: list[list[int]] = []
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(graph, WHITE)

    def visit(node: int, stack: list[int]) -> None:
        colour[node] = GREY
        stack.append(node)
        for dep in graph.get(node, []):
            if colour.get(dep) == GREY:
                cycles.append(stack[stack.index(dep):] + [dep])
            elif colour.get(dep) == WHITE:
                visit(dep, stack)
        stack.pop()
        colour[node] = BLACK

    for node in list(graph):
        if colour[node] == WHITE:
            visit(node, [])
    return cycles


def compute_critical_path(initiatives: list[StrategicInitiative]) -> dict:
    """Cadena de dependencias mas larga en duracion (camino critico).

    La duracion de cada iniciativa sale de sus fechas; sin fechas se asume 0 y
    la iniciativa no alarga el camino: no se inventan plazos.
    """
    graph = _dependency_graph(initiatives)
    by_id = {i.id: i for i in initiatives}
    cycles = detect_dependency_cycles(initiatives)
    in_cycle = {node for cycle in cycles for node in cycle}

    def duration(ini_id: int) -> float:
        ini = by_id.get(ini_id)
        start, target = _aware(ini.start_date) if ini else None, _aware(ini.target_date) if ini else None
        if not start or not target or target < start:
            return 0.0
        return (target - start).days

    memo: dict[int, tuple[float, list[int]]] = {}

    def longest(ini_id: int, seen: frozenset) -> tuple[float, list[int]]:
        if ini_id in memo:
            return memo[ini_id]
        if ini_id in seen or ini_id in in_cycle:
            return 0.0, []          # no se recorre un ciclo
        best_len, best_path = 0.0, []
        for dep in graph.get(ini_id, []):
            length, path = longest(dep, seen | {ini_id})
            if length > best_len:
                best_len, best_path = length, path
        result = (best_len + duration(ini_id), best_path + [ini_id])
        memo[ini_id] = result
        return result

    best_total, best_chain = 0.0, []
    for ini in initiatives:
        total, chain = longest(ini.id, frozenset())
        if total > best_total:
            best_total, best_chain = total, chain

    return {
        "path": [
            {"id": i, "code": by_id[i].code, "title": by_id[i].title,
             "duration_days": duration(i)}
            for i in best_chain if i in by_id
        ],
        "total_days": round(best_total),
        "cycles": [[by_id[n].code for n in cycle if n in by_id] for cycle in cycles],
    }


def log_system_event(db: Session, initiative_id: int, text: str) -> None:
    """Crea una entrada de bitacora sin autor (sistema/IA). No hace commit."""
    initiative = db.get(StrategicInitiative, initiative_id)
    org_id = initiative.organization_id if initiative else None
    db.add(InitiativeLogEntry(
        organization_id=org_id, initiative_id=initiative_id,
        entry_type="system", text=text, author_id=None,
    ))


def auto_link_risks(db: Session, initiative: StrategicInitiative) -> int:
    """Deriva los riesgos afectados por la iniciativa a partir de sus controles
    objetivo. Determinista: no llama a IA. Devuelve el numero de links creados.

    Crea links origin='auto' para los riesgos derivados que no existan y
    elimina los 'auto' que ya no se deriven de ningun control objetivo (los
    manuales/ai_import/ai_draft nunca se tocan aqui).
    """
    org_id = initiative.organization_id
    target_impl_ids = [ct.implementation_id for ct in initiative.control_targets]

    # Todos los links existentes (cualquier origen): un riesgo ya vinculado
    # manualmente/IA no debe generar un duplicado 'auto' (uq_initiative_risk)
    existing_links = db.query(InitiativeRiskLink).filter(
        InitiativeRiskLink.initiative_id == initiative.id,
    ).all()
    existing_by_risk = {link.risk_id: link for link in existing_links}
    existing_auto = {link.risk_id: link for link in existing_links if link.origin == "auto"}

    if not target_impl_ids:
        for link in existing_auto.values():
            db.delete(link)
        db.flush()
        return 0

    open_risks = db.query(Risk).filter(
        Risk.organization_id == org_id, Risk.status != RiskStatus.CLOSED,
    ).all()
    open_risk_ids = {r.id for r in open_risks}
    risk_by_id = {r.id: r for r in open_risks}

    ctx = get_context(db, org_id)
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3

    derived_risk_ids: set[int] = set()

    # 1. Directos: el control objetivo ya mitiga formalmente el riesgo
    direct_rows = db.query(risk_control_table.c.risk_id).filter(
        risk_control_table.c.control_implementation_id.in_(target_impl_ids)
    ).distinct().all()
    derived_risk_ids |= ({rid for (rid,) in direct_rows} & open_risk_ids)

    # 2. Por catalogo: la amenaza del riesgo tiene entre sus controles
    # candidatos alguno de los codigos objetivo (solo riesgos sobre apetito,
    # para no llenar de links riesgos que ya estan en verde)
    target_impls = db.query(ControlImplementation).filter(
        ControlImplementation.id.in_(target_impl_ids)
    ).all()
    target_codes = {
        ci.control.code.strip().lstrip("A.").strip()
        for ci in target_impls if ci.control and ci.control.code
    }
    if target_codes:
        for risk in open_risks:
            if risk.id in derived_risk_ids:
                continue
            if (risk.residual_level or 0) <= appetite:
                continue
            threat = risk.threat
            if not threat or not threat.code:
                continue
            candidate_codes = {c["code"] for c in controls_for_threat(db, org_id, threat.code)}
            if target_codes & candidate_codes:
                derived_risk_ids.add(risk.id)

    created = 0
    for rid in derived_risk_ids:
        if rid in existing_by_risk:
            continue  # ya vinculado (auto, manual o IA): no duplicar
        risk = risk_by_id.get(rid)
        db.add(InitiativeRiskLink(
            organization_id=org_id, initiative_id=initiative.id, risk_id=rid,
            origin="auto", baseline_residual_level=risk.residual_level if risk else None,
        ))
        created += 1

    for rid, link in existing_auto.items():
        if rid not in derived_risk_ids:
            db.delete(link)

    db.flush()
    return created


def project_initiative(db: Session, initiative: StrategicInitiative) -> dict:
    """Simula el residual de cada riesgo vinculado asumiendo que los controles
    objetivo alcanzan su madurez objetivo. Usa el mismo motor que el residual
    real (residual_from_payloads); NUNCA escribe en el riesgo, solo en el link."""
    org_id = initiative.organization_id
    matrix = get_matrix(db, org_id)
    target_by_impl = {ct.implementation_id: ct.target_maturity for ct in initiative.control_targets}

    # Implementaciones objetivo con su codigo de control: hacen falta para
    # poder proyectar sobre riesgos que aun no tienen el control vinculado.
    target_impls = {}
    if target_by_impl:
        for ci in db.query(ControlImplementation).filter(
            ControlImplementation.id.in_(list(target_by_impl.keys()))
        ).all():
            target_impls[ci.id] = ci

    results = []
    total_points = 0
    now = datetime.now(timezone.utc)

    for link in initiative.risk_links:
        risk = link.risk
        if not risk:
            continue
        rows = db.execute(
            _text("SELECT control_implementation_id, contribution FROM risk_controls WHERE risk_id = :rid"),
            {"rid": risk.id},
        ).fetchall()
        contrib_map = {row[0]: (row[1] if row[1] is not None else 1.0) for row in rows}

        controls = []
        linked_impl_ids = {ci.id for ci in risk.controls}
        for ci in risk.controls:
            payload = control_payload(ci, contrib_map.get(ci.id, 1.0), db=db)
            target = target_by_impl.get(ci.id)
            # "maturity" viene ajustada por calidad de evidencia actual (escala
            # distinta de target_maturity, que es CMM en bruto 0..5). Si la
            # iniciativa promete subir la madurez en bruto por encima de la
            # actual, el what-if asume que al alcanzarla habra evidencia de
            # calidad razonable (no tiene sentido penalizar hoy una evidencia
            # que el proyecto aun no ha producido). Una iniciativa nunca
            # empeora un control: si el objetivo no supera lo ya alcanzado,
            # el payload queda intacto.
            if target is not None and target > payload["maturity_raw"]:
                payload["maturity_raw"] = target
                payload["maturity"] = float(target)
            controls.append(payload)

        # Controles objetivo que el riesgo aun NO tiene vinculados. Sin esto la
        # proyeccion de los riesgos derivados por catalogo salia siempre igual
        # al baseline (reduccion 0): el control que la iniciativa promete
        # implantar no entraba en el calculo. Solo se admiten los que el
        # catalogo amenaza->control reconoce como mitigadores de esa amenaza, y
        # la contribucion es su relevancia — nunca se inventa una reduccion.
        candidate_relevance = {}
        threat = risk.threat
        if threat and threat.code:
            candidate_relevance = {
                c["code"]: float(c.get("relevance") or 0.5)
                for c in controls_for_threat(db, org_id, threat.code)
            }
        for impl_id, target in target_by_impl.items():
            if impl_id in linked_impl_ids:
                continue
            ci = target_impls.get(impl_id)
            ctrl = ci.control if ci else None
            if not ctrl or not ctrl.code:
                continue
            relevance = candidate_relevance.get(ctrl.code.strip().lstrip("A.").strip())
            if relevance is None:
                continue  # el catalogo no lo reconoce como mitigador: no proyecta
            payload = control_payload(ci, relevance, db=db)
            if target > payload["maturity_raw"]:
                payload["maturity_raw"] = target
                payload["maturity"] = float(target)
            controls.append(payload)

        _, _, _, projected_level = residual_from_payloads(risk, controls, matrix)
        link.projected_residual_level = projected_level
        link.projected_at = now
        if link.baseline_residual_level is None:
            link.baseline_residual_level = risk.residual_level

        baseline = link.baseline_residual_level if link.baseline_residual_level is not None else projected_level
        results.append({
            "risk_id": risk.id, "risk_code": risk.code,
            "baseline": baseline, "current": risk.residual_level, "projected": projected_level,
        })
        total_points += max(0, (baseline or 0) - projected_level)

    db.flush()
    return {"risks": results, "projected_reduction_points": total_points}


def verify_initiative(db: Session, initiative: StrategicInitiative) -> dict:
    """Al completar una iniciativa: sella lo alcanzado (madurez real, residual
    real) y compara contra el objetivo/proyeccion. El gap queda visible —
    nunca se oculta ni se fuerza a que "cuadre"."""
    controls_total = 0
    controls_met = 0
    gaps: list[dict] = []

    for ct in initiative.control_targets:
        controls_total += 1
        impl = ct.implementation
        achieved = impl.maturity if impl else None
        ct.achieved_maturity = achieved
        if achieved is not None and achieved >= ct.target_maturity:
            controls_met += 1
        else:
            code = impl.control.code if impl and impl.control else "?"
            gaps.append({"type": "control", "code": code,
                        "target": ct.target_maturity, "achieved": achieved})

    risks_total = 0
    risks_met = 0
    for link in initiative.risk_links:
        risk = link.risk
        achieved = risk.residual_level if risk else None
        link.achieved_residual_level = achieved
        projected = link.projected_residual_level
        if projected is None:
            continue  # no evaluable: nunca se proyecto (p.ej. sin control targets)
        risks_total += 1
        if achieved is not None and achieved <= projected:
            risks_met += 1
        else:
            gaps.append({"type": "risk", "code": risk.code if risk else "?",
                        "projected": projected, "achieved": achieved})

    result = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "controls": {"total": controls_total, "met": controls_met},
        "risks": {"total": risks_total, "met": risks_met},
        "gaps": gaps,
    }
    initiative.verification = result
    log_system_event(
        db, initiative.id,
        f"Verificacion de cierre: {controls_met}/{controls_total} controles alcanzaron "
        f"la madurez objetivo; {risks_met}/{risks_total} riesgos quedaron en o por debajo "
        f"del residual proyectado.",
    )
    db.flush()
    return result


def reproject_for_impls(db: Session, impl_ids: list[int]) -> int:
    """Reproyecta las iniciativas activas que tengan alguno de estos controles
    como objetivo, tras un recalculo real (madurez/evidencia/NC/CCM cambiaron).
    Se invoca desde risk_recalc_service.recalc_risks_for_impls."""
    if not impl_ids:
        return 0
    initiative_ids = [
        iid for (iid,) in db.query(InitiativeControlTarget.initiative_id)
        .filter(InitiativeControlTarget.implementation_id.in_(impl_ids))
        .distinct().all()
    ]
    if not initiative_ids:
        return 0
    initiatives = db.query(StrategicInitiative).filter(
        StrategicInitiative.id.in_(initiative_ids),
        StrategicInitiative.status.in_(["approved", "in_progress"]),
    ).all()
    for ini in initiatives:
        try:
            project_initiative(db, ini)
        except Exception:
            logger.exception("reproject_for_impls: fallo en iniciativa id=%s", ini.id)
    return len(initiatives)


def compute_burndown(db: Session, org_id: int | None) -> dict:
    """Historico real (RiskSnapshot mensual) + curva proyectada desde las
    iniciativas activas. Evita doble conteo: si dos iniciativas comparten un
    riesgo, se usa solo la mejor proyeccion de ese riesgo."""
    from app.models import RiskSnapshot

    ctx = get_context(db, org_id)
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3

    since = datetime.now(timezone.utc) - timedelta(days=18 * 30)
    snapshots = db.query(RiskSnapshot).filter(
        RiskSnapshot.organization_id == org_id,
        RiskSnapshot.snapshot_date >= since,
    ).all()
    by_month: dict[str, dict] = defaultdict(lambda: {"total_residual": 0, "above_appetite": 0})
    for s in snapshots:
        month = s.snapshot_date.strftime("%Y-%m")
        by_month[month]["total_residual"] += s.residual_level or 0
        if (s.residual_level or 0) > appetite:
            by_month[month]["above_appetite"] += 1
    history = [{"month": m, **v} for m, v in sorted(by_month.items())]

    initiatives = db.query(StrategicInitiative).filter(
        StrategicInitiative.organization_id == org_id,
        StrategicInitiative.status.in_(["approved", "in_progress"]),
        StrategicInitiative.target_date.isnot(None),
    ).all()

    current_total = sum(
        r.residual_level or 0 for r in
        db.query(Risk).filter(Risk.organization_id == org_id, Risk.status != RiskStatus.CLOSED).all()
    )

    best_by_risk: dict[int, dict] = {}
    for ini in initiatives:
        month = ini.target_date.strftime("%Y-%m")
        for link in ini.risk_links:
            if link.baseline_residual_level is None or link.projected_residual_level is None:
                continue
            cur = best_by_risk.get(link.risk_id)
            if cur is None or link.projected_residual_level < cur["projected"]:
                best_by_risk[link.risk_id] = {
                    "month": month, "baseline": link.baseline_residual_level,
                    "projected": link.projected_residual_level,
                }

    reduction_by_month: dict[str, int] = defaultdict(int)
    for v in best_by_risk.values():
        reduction_by_month[v["month"]] += max(0, v["baseline"] - v["projected"])

    projected = []
    running_total = current_total
    for month in sorted(reduction_by_month.keys()):
        running_total -= reduction_by_month[month]
        projected.append({"month": month, "total_residual": max(0, running_total)})

    return {"history": history, "projected": projected, "appetite_line": appetite}


def _health_rank(health: str) -> int:
    return {"ok": 0, "at_risk": 1, "blocked": 2}.get(health, 0)


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def refresh_initiative_health(db: Session, org_id: int | None = None) -> int:
    """Recalcula la salud (ok/at_risk/blocked) de las iniciativas activas a
    partir de senales objetivas — nunca la marca una persona. Si la salud
    EMPEORA, registra el motivo en la bitacora y alerta al owner de la org
    (Teams/email/Power Automate) si hay algun canal configurado.

    Reglas (>=2 motivos = blocked, 1 = at_risk, 0 = ok):
      - target_date vencida y status != completed
      - sin actividad (bitacora humana, tarea, OKR) en los ultimos 30 dias
      - >30% de las tareas de la iniciativa vencidas
      - algun OKR con confidence=low y target_date a menos de 60 dias
      - progreso < 20% con >60% del plazo (start->target) consumido
    """
    from app.models import InitiativeObjective, TreatmentTask
    from app.services import notification_channels

    now = datetime.now(timezone.utc)
    query = db.query(StrategicInitiative).filter(
        StrategicInitiative.status.in_(["approved", "in_progress"])
    )
    if org_id is not None:
        query = query.filter(StrategicInitiative.organization_id == org_id)
    initiatives = query.all()

    updated = 0
    pending_inheritance: list[StrategicInitiative] = []
    for ini in initiatives:
        reasons: list[str] = []

        target_date = _aware(ini.target_date)
        if target_date and target_date < now:
            reasons.append("Fecha objetivo vencida")

        tasks = db.query(TreatmentTask).filter(TreatmentTask.initiative_id == ini.id).all()
        objectives = ini.objectives or []

        last_activity_candidates = [_aware(ini.updated_at)]
        recent_human_log = (
            db.query(InitiativeLogEntry.created_at)
            .filter(InitiativeLogEntry.initiative_id == ini.id, InitiativeLogEntry.author_id.isnot(None))
            .order_by(InitiativeLogEntry.created_at.desc()).first()
        )
        if recent_human_log:
            last_activity_candidates.append(_aware(recent_human_log[0]))
        last_activity_candidates.extend(_aware(t.updated_at) for t in tasks)
        last_activity_candidates.extend(_aware(o.updated_at) for o in objectives)
        last_activity_candidates = [d for d in last_activity_candidates if d]
        last_activity = max(last_activity_candidates) if last_activity_candidates else None
        if last_activity and (now - last_activity).days > 30:
            reasons.append("Sin actividad en 30 dias")

        if tasks:
            overdue = sum(
                1 for t in tasks
                if t.due_date and str(getattr(t.status, "value", t.status)).lower() != "done"
                and _aware(t.due_date) < now
            )
            if overdue / len(tasks) > 0.3:
                reasons.append("Tareas vencidas")

        if any(
            o.confidence == "low" and _aware(o.target_date)
            and 0 <= (_aware(o.target_date) - now).days < 60
            for o in objectives
        ):
            reasons.append("OKR en riesgo")

        start_date = _aware(ini.start_date)
        if start_date and target_date:
            total = (target_date - start_date).total_seconds()
            elapsed = (now - start_date).total_seconds()
            if total > 0 and elapsed / total > 0.6 and (ini.progress or 0) < 20:
                reasons.append("Progreso insuficiente")

        new_health = "ok" if not reasons else ("at_risk" if len(reasons) == 1 else "blocked")
        old_health = ini.health
        ini.health = new_health
        ini.health_reasons = reasons or None
        updated += 1
        pending_inheritance.append(ini)

        if _health_rank(new_health) > _health_rank(old_health):
            log_system_event(
                db, ini.id,
                f"La salud paso de '{old_health}' a '{new_health}': {', '.join(reasons)}.",
            )
            try:
                from app.models import EmailSettings, RiskContext
                cfg = db.query(EmailSettings).filter_by(organization_id=ini.organization_id).first()
                if notification_channels.has_any_channel(cfg):
                    ctx = db.query(RiskContext).filter_by(organization_id=ini.organization_id).first()
                    org_name = ctx.organization_name if ctx else "Organizacion"
                    recipient = ini.owner.email if ini.owner else None
                    notification_channels.dispatch_alert(
                        db, cfg, org_name, recipient,
                        subject=f"Iniciativa {ini.code} en estado '{new_health}'",
                        summary_text=f"{ini.title}: {', '.join(reasons)}",
                        event="initiative_health_degraded",
                        fields={"code": ini.code, "title": ini.title, "health": new_health, "reasons": reasons},
                    )
            except Exception:
                logger.exception("refresh_initiative_health: fallo alerta org=%s", ini.organization_id)

    # Salud heredada: una iniciativa cuya dependencia esta bloqueada tampoco
    # puede avanzar, por muy bien que vayan sus propios indicadores. Se propaga
    # despues de calcular la salud propia de todas, y se marca como heredada
    # para que el motivo sea explicable y no parezca un fallo suyo.
    _propagate_blocked_health(db, pending_inheritance)

    db.commit()
    return updated


def _propagate_blocked_health(db: Session, initiatives: list[StrategicInitiative]) -> None:
    if not initiatives:
        return
    by_id = {i.id: i for i in initiatives}
    graph = _dependency_graph(initiatives)
    in_cycle = {n for cycle in detect_dependency_cycles(initiatives) for n in cycle}

    # Varias pasadas: la herencia se encadena (A bloquea B, B bloquea C)
    for _ in range(len(initiatives)):
        changed = False
        for ini in initiatives:
            if ini.id in in_cycle:
                continue
            blockers = [
                by_id[d] for d in graph.get(ini.id, [])
                if d in by_id and by_id[d].health == "blocked"
            ]
            if not blockers or ini.health == "blocked":
                continue
            reasons = list(ini.health_reasons or [])
            codes = ", ".join(b.code for b in blockers)
            reason = f"Bloqueada por dependencia: {codes}"
            if reason not in reasons:
                reasons.append(reason)
            ini.health = "blocked"
            ini.health_reasons = reasons
            changed = True
        if not changed:
            break

    for cycle in detect_dependency_cycles(initiatives):
        for node in cycle:
            ini = by_id.get(node)
            if not ini:
                continue
            reasons = list(ini.health_reasons or [])
            reason = "Ciclo de dependencias: el plan no es ejecutable tal cual"
            if reason not in reasons:
                reasons.append(reason)
                ini.health_reasons = reasons
    db.flush()


def send_initiative_digest(db: Session) -> dict:
    """Digest mensual al comite por organizacion: iniciativas en riesgo/bloqueadas
    con motivos, reduccion proyectada vs conseguida y riesgos sobre apetito sin
    cobertura. Nunca envia si no hay nada relevante que decir."""
    from app.models import EmailSettings, Organization, RiskContext
    from app.services import notification_channels

    sent = 0
    orgs = db.query(Organization).filter(Organization.is_active.is_(True)).all()
    for org in orgs:
        initiatives = db.query(StrategicInitiative).filter(
            StrategicInitiative.organization_id == org.id,
            StrategicInitiative.status.in_(["approved", "in_progress"]),
        ).all()
        problematic = [i for i in initiatives if i.health in ("at_risk", "blocked")]

        ctx = db.query(RiskContext).filter_by(organization_id=org.id).first()
        appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3
        covered_risk_ids = {link.risk_id for i in initiatives for link in i.risk_links}
        open_risks = db.query(Risk).filter(
            Risk.organization_id == org.id, Risk.status != RiskStatus.CLOSED,
        ).all()
        uncovered = sum(
            1 for r in open_risks
            if (r.residual_level or 0) > appetite and r.id not in covered_risk_ids
        )

        projected_points = 0
        achieved_points = 0
        for i in initiatives:
            for link in i.risk_links:
                if link.baseline_residual_level is None or link.projected_residual_level is None:
                    continue
                projected_points += max(0, link.baseline_residual_level - link.projected_residual_level)
                risk = link.risk
                current = risk.residual_level if risk else link.baseline_residual_level
                achieved_points += max(0, link.baseline_residual_level - (current or 0))

        if not problematic and uncovered == 0 and projected_points == 0:
            continue  # nada relevante que reportar esta org

        cfg = db.query(EmailSettings).filter_by(organization_id=org.id).first()
        if not notification_channels.has_any_channel(cfg):
            continue

        lines = []
        if problematic:
            lines.append(f"{len(problematic)} iniciativa(s) en riesgo o bloqueadas:")
            for i in problematic[:10]:
                lines.append(f"  - {i.code} {i.title}: {', '.join(i.health_reasons or [])}")
        if uncovered:
            lines.append(f"{uncovered} riesgo(s) sobre apetito sin cobertura del Plan Director.")
        lines.append(f"Reduccion de riesgo: {projected_points} puntos proyectados, {achieved_points} conseguidos.")
        summary_text = "\n".join(lines)

        org_name = ctx.organization_name if ctx else org.name
        result = notification_channels.dispatch_alert(
            db, cfg, org_name, None,
            subject=f"Plan Director — resumen mensual ({org_name})",
            summary_text=summary_text,
            event="initiative_monthly_digest",
            fields={"at_risk": len(problematic), "uncovered": uncovered,
                    "projected_points": projected_points, "achieved_points": achieved_points},
        )
        if any(v for v in result.values()):
            sent += 1

    db.commit()
    return {"sent": sent, "orgs_evaluated": len(orgs)}
