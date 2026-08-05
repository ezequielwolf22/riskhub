"""Mapa de continuidad: la jerarquia REAL del BCP y su coherencia.

El modulo mostraba procesos en plano. Aqui se reconstruye el arbol que un BIA
necesita de verdad — Sede (anidada) -> Unidad de negocio -> Proceso ->
Subproceso -> Dependencias — y se calcula lo que da precision a las cifras:

1. **RTO efectivo (propagacion).** Un proceso no se recupera mas rapido que su
   dependencia critica mas lenta. Si el RTO declarado es 4h pero necesita un
   sistema con RTO 24h, su RTO efectivo es 24h. Se muestran ambos y el hueco.

2. **Hallazgos de coherencia.** Contradicciones que delatan datos imprecisos:
   RTO por encima del MTPD, subproceso mas exigente que su padre, dependencia
   critica mas lenta que el proceso, proceso critico sin estrategia/plan/prueba,
   proceso sin sede. No se corrigen solos: se muestran para que una persona
   decida.

Todo es determinista y de solo lectura: ni la vista ni un LLM calculan estas
cifras.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

# Criticidades que exigen tratamiento (estrategia/plan/prueba).
_CRITICAL = ("critical", "high")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _dep_rto(dep, proc_rto: dict) -> Optional[float]:
    """RTO que impone una dependencia: el del proceso del que depende, o el suyo."""
    if getattr(dep, "depends_on_process_id", None):
        return proc_rto.get(dep.depends_on_process_id)
    return _num(dep.rto_hours)


def _effective_rto(declared: Optional[float], crit_dep_rtos: list) -> Optional[float]:
    """El proceso no puede recuperarse antes que su dependencia critica mas lenta."""
    vals = [d for d in crit_dep_rtos if d is not None]
    if declared is not None:
        vals.append(declared)
    return max(vals) if vals else None


def _process_findings(p, node: dict, deps: list, children: list,
                      proc_rto: dict) -> list[dict]:
    """Contradicciones de un proceso. Cada una con severidad y mensaje claro."""
    out = []
    rto, rpo, mtpd = _num(p.rto_hours), _num(p.rpo_hours), _num(p.mtpd_hours)
    crit = p.criticality in _CRITICAL

    if rto is not None and mtpd is not None and rto > mtpd:
        out.append({"code": "rto_gt_mtpd", "severity": "high",
                    "message": f"El RTO ({_h(rto)}) supera el MTPD ({_h(mtpd)}): "
                               "no se puede recuperar dentro del tiempo maximo tolerable."})
    if rpo is not None and mtpd is not None and rpo > mtpd:
        out.append({"code": "rpo_gt_mtpd", "severity": "medium",
                    "message": f"El RPO ({_h(rpo)}) supera el MTPD ({_h(mtpd)})."})
    if crit and rto is None:
        out.append({"code": "critical_no_rto", "severity": "high",
                    "message": "Proceso critico sin RTO definido."})
    if node.get("effective_rto") is not None and rto is not None \
            and node["effective_rto"] > rto:
        out.append({"code": "dep_slower_than_process", "severity": "high",
                    "message": f"Una dependencia critica es mas lenta ({_h(node['effective_rto'])}) "
                               f"que el RTO del proceso ({_h(rto)}). El RTO efectivo es "
                               f"{_h(node['effective_rto'])}."})
    for ch in children:
        c_rto = _num(ch.get("rto_hours"))
        if c_rto is not None and rto is not None and c_rto > rto:
            out.append({"code": "child_rto_gt_parent", "severity": "medium",
                        "message": f"El subproceso «{ch.get('name')}» tiene un RTO ({_h(c_rto)}) "
                                   f"mayor que el de su proceso padre ({_h(rto)})."})
    if crit and not node.get("has_strategy"):
        out.append({"code": "critical_no_strategy", "severity": "medium",
                    "message": "Proceso critico sin estrategia de recuperacion."})
    if crit and not node.get("has_plan"):
        out.append({"code": "critical_no_plan", "severity": "medium",
                    "message": "Proceso critico sin plan de continuidad."})
    if crit and not node.get("test_ok"):
        out.append({"code": "critical_not_tested", "severity": "low",
                    "message": "Proceso critico sin prueba de continuidad en los ultimos 12 meses."})
    if not getattr(p, "location_id", None):
        out.append({"code": "no_location", "severity": "low",
                    "message": "Proceso sin sede asignada."})
    return out


def _h(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    return (str(int(v)) if v.is_integer() else str(v)) + "h"


def build_continuity_map(db: Session, org_id: Optional[int]) -> dict:
    """Arbol Sede(anidada) -> Unidad de negocio -> Proceso -> Subproceso -> deps,
    con RTO efectivo, hallazgos de coherencia y procedencia por nodo."""
    from app.models import (BCMLocation, BCPDependency, BCPPlan, BCPStrategy,
                            BCPTest, BusinessProcess)
    from app.services.bcp_service import bia_completeness

    if not org_id:
        return {"locations": [], "unassigned": [], "totals": {}, "findings_total": 0}

    procs = db.query(BusinessProcess).filter_by(organization_id=org_id).all()
    deps = db.query(BCPDependency).filter_by(organization_id=org_id).all()
    strategies = db.query(BCPStrategy).filter_by(organization_id=org_id).all()
    plans = db.query(BCPPlan).filter_by(organization_id=org_id).all()
    tests = db.query(BCPTest).filter_by(organization_id=org_id).all()
    locs = db.query(BCMLocation).filter_by(organization_id=org_id).all()

    proc_rto = {p.id: _num(p.rto_hours) for p in procs}
    proc_name = {p.id: p.name for p in procs}
    deps_by_proc: dict = {}
    for d in deps:
        deps_by_proc.setdefault(d.process_id, []).append(d)

    with_strategy = {s.process_id for s in strategies if s.process_id}
    with_plan: set = set()
    for pl in plans:
        for pid in (pl.process_ids or []):
            with_plan.add(pid)
    now = datetime.now(timezone.utc)
    tested_ok: set = set()
    for t in tests:
        if not t.conducted_at:
            continue
        fresh = (now - t.conducted_at.replace(tzinfo=timezone.utc)).days <= 365
        for pid in (t.process_ids or []):
            if fresh:
                tested_ok.add(pid)

    children_of: dict = {}
    roots: list = []
    for p in procs:
        pp = getattr(p, "parent_process_id", None)
        if pp and pp in proc_name:
            children_of.setdefault(pp, []).append(p)
        else:
            roots.append(p)

    findings_counter = {"n": 0}

    def _proc_node(p) -> dict:
        try:
            bia = bia_completeness(None, p)["pct"]
        except Exception:
            bia = 0
        my_deps = deps_by_proc.get(p.id, [])
        grouped: dict = {}
        crit_dep_rtos = []
        for d in my_deps:
            grouped.setdefault(d.dependency_type or "other", []).append({
                "id": d.id, "name": d.name, "is_critical": bool(d.is_critical),
                "rto_hours": d.rto_hours,
                "depends_on_process_id": getattr(d, "depends_on_process_id", None),
                "depends_on_process": proc_name.get(getattr(d, "depends_on_process_id", None)),
                "recovery_sequence": getattr(d, "recovery_sequence", None),
            })
            if d.is_critical:
                crit_dep_rtos.append(_dep_rto(d, proc_rto))
        # Hijos primero (para poder detectar subproceso mas exigente que el padre)
        child_nodes = [_proc_node(c) for c in
                       sorted(children_of.get(p.id, []), key=lambda x: x.name or "")]
        declared = _num(p.rto_hours)
        eff = _effective_rto(declared, crit_dep_rtos)
        node = {
            "id": p.id, "name": p.name, "criticality": p.criticality,
            "priority": p.priority, "business_unit": getattr(p, "business_unit", None),
            "rto_hours": p.rto_hours, "rpo_hours": p.rpo_hours, "mtpd_hours": p.mtpd_hours,
            "declared_rto": declared, "effective_rto": eff,
            "rto_gap": bool(eff is not None and declared is not None and eff > declared),
            "bia_pct": bia, "weighted_impact": getattr(p, "weighted_impact", None),
            "impact_band": getattr(p, "impact_band", None),
            "source": getattr(p, "source", None),
            "import_confidence": getattr(p, "import_confidence", None),
            "needs_review": bool(getattr(p, "needs_review", False)),
            "has_strategy": p.id in with_strategy,
            "has_plan": p.id in with_plan,
            "test_ok": p.id in tested_ok,
            "last_tested_at": p.last_tested_at.isoformat() if p.last_tested_at else None,
            "dependencies": grouped, "dep_count": len(my_deps),
            "children": child_nodes,
        }
        node["findings"] = _process_findings(p, node, my_deps, child_nodes, proc_rto)
        findings_counter["n"] += len(node["findings"])
        node["findings_subtree"] = len(node["findings"]) + sum(
            c.get("findings_subtree", 0) for c in child_nodes)
        return node

    # Procesos raiz agrupados por sede y unidad de negocio.
    roots_by_loc: dict = {}
    unassigned_roots: list = []
    for p in roots:
        if getattr(p, "location_id", None):
            roots_by_loc.setdefault(p.location_id, []).append(p)
        else:
            unassigned_roots.append(p)

    def _units(proc_list) -> list:
        by_unit: dict = {}
        for p in proc_list:
            by_unit.setdefault(getattr(p, "business_unit", None) or "", []).append(p)
        out = []
        for unit in sorted(by_unit, key=lambda x: (x == "", x)):
            nodes = [_proc_node(p) for p in sorted(by_unit[unit], key=lambda x: x.name or "")]
            out.append({
                "business_unit": unit or None,
                "processes": nodes,
                "process_count": sum(1 + _count_children(n) for n in nodes),
                "findings": sum(n.get("findings_subtree", 0) for n in nodes),
            })
        return out

    def _count_children(n) -> int:
        return len(n.get("children", [])) + sum(_count_children(c) for c in n.get("children", []))

    children_locs: dict = {}
    root_locs: list = []
    for loc in locs:
        pp = getattr(loc, "parent_id", None)
        if pp:
            children_locs.setdefault(pp, []).append(loc)
        else:
            root_locs.append(loc)

    def _loc_node(loc) -> dict:
        units = _units(roots_by_loc.get(loc.id, []))
        sublocs = [_loc_node(c) for c in
                   sorted(children_locs.get(loc.id, []), key=lambda x: x.name or "")]
        direct = sum(u["process_count"] for u in units)
        return {
            "id": loc.id, "name": loc.name, "code": getattr(loc, "code", None),
            "city": getattr(loc, "city", None), "country": getattr(loc, "country", None),
            "site_type": getattr(loc, "site_type", None),
            "business_unit": getattr(loc, "business_unit", None),
            "units": units,
            "sublocations": sublocs,
            "process_count": direct + sum(s["process_count"] for s in sublocs),
            "findings": sum(u["findings"] for u in units)
                        + sum(s["findings"] for s in sublocs),
        }

    location_nodes = [_loc_node(loc) for loc in
                      sorted(root_locs, key=lambda x: x.name or "")]
    unassigned = _units(unassigned_roots)

    return {
        "locations": location_nodes,
        "unassigned": unassigned,
        "totals": {"locations": len(locs), "processes": len(procs),
                   "dependencies": len(deps)},
        "findings_total": findings_counter["n"],
    }


# ── Fase 2: grafo de dependencias proceso->proceso y propagacion de impacto ────

def build_impact_analysis(db: Session, org_id: Optional[int]) -> dict:
    """Analiza el grafo proceso->proceso: quien depende de quien, a cuantos
    procesos afecta la caida de cada uno (propagacion transitiva), el orden de
    recuperacion, el camino critico por RTO y los ciclos (que impiden un orden).

    Semantica de la arista: una dependencia de tipo `process` sobre P que apunta
    a Q significa "P NECESITA a Q". Por tanto Q debe recuperarse antes que P, y
    si Q cae, P se ve afectado.
    """
    from app.models import BCPDependency, BusinessProcess

    if not org_id:
        return {"processes": [], "hubs": [], "recovery_order": [], "cycles": [],
                "critical_path": {"nodes": [], "total_rto": 0}, "has_process_deps": False}

    procs = db.query(BusinessProcess).filter_by(organization_id=org_id).all()
    pmap = {p.id: p for p in procs}
    deps = db.query(BCPDependency).filter_by(organization_id=org_id).all()

    depends_on: dict = {p.id: set() for p in procs}   # P -> {Q que necesita}
    enables: dict = {p.id: set() for p in procs}       # Q -> {P que lo necesitan}
    for d in deps:
        q = getattr(d, "depends_on_process_id", None)
        if q and q in pmap and d.process_id in pmap and q != d.process_id:
            depends_on[d.process_id].add(q)
            enables[q].add(d.process_id)

    has_edges = any(depends_on.values())

    # Propagacion: a cuantos procesos afecta la caida de X (cierre transitivo
    # siguiendo `enables`, con corte por si hubiera ciclos).
    def _impact(start: int) -> set:
        seen, stack = set(), [start]
        while stack:
            cur = stack.pop()
            for nxt in enables.get(cur, ()):  # quien depende de cur
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        seen.discard(start)
        return seen

    impact_sets = {p.id: _impact(p.id) for p in procs}

    # Orden de recuperacion (Kahn sobre Q->P: la dependencia va antes que quien
    # la usa). Si quedan nodos sin procesar, hay ciclo.
    indeg = {p.id: len(depends_on[p.id]) for p in procs}
    queue = sorted([pid for pid, d in indeg.items() if d == 0])
    order: list = []
    indeg_work = dict(indeg)
    while queue:
        pid = queue.pop(0)
        order.append(pid)
        for nxt in sorted(enables.get(pid, ())):
            indeg_work[nxt] -= 1
            if indeg_work[nxt] == 0:
                queue.append(nxt)
    has_cycle = len(order) < len(procs)

    # Ciclos concretos (para poder mostrarlos): DFS de deteccion.
    cycles = _find_cycles(depends_on) if has_cycle else []

    # Camino critico: cadena de dependencias mas larga por RTO (DP sobre el orden
    # topologico). Solo si no hay ciclo que lo invalide.
    critical_path = {"nodes": [], "total_rto": 0}
    if not has_cycle and order:
        best_to = {pid: (_num(pmap[pid].rto_hours) or 0.0) for pid in order}
        prev = {pid: None for pid in order}
        for pid in order:  # topo: dependencias antes
            for nxt in enables.get(pid, ()):
                cand = best_to[pid] + (_num(pmap[nxt].rto_hours) or 0.0)
                if cand > best_to[nxt]:
                    best_to[nxt] = cand
                    prev[nxt] = pid
        end = max(order, key=lambda x: best_to[x]) if order else None
        chain = []
        cur = end
        while cur is not None:
            chain.append(cur)
            cur = prev[cur]
        chain.reverse()
        if len(chain) > 1:
            critical_path = {
                "nodes": [{"id": c, "name": pmap[c].name,
                           "rto_hours": pmap[c].rto_hours} for c in chain],
                "total_rto": round(best_to[end], 2),
            }

    proc_out = []
    for p in procs:
        imp = impact_sets[p.id]
        proc_out.append({
            "id": p.id, "name": p.name, "criticality": p.criticality,
            "rto_hours": p.rto_hours,
            "depends_on": [{"id": q, "name": pmap[q].name} for q in sorted(depends_on[p.id])],
            "enables": [{"id": q, "name": pmap[q].name} for q in sorted(enables[p.id])],
            "impact_count": len(imp),
            "impact_names": [pmap[i].name for i in sorted(imp)][:20],
        })
    hubs = sorted([p for p in proc_out if p["impact_count"] > 0],
                  key=lambda x: -x["impact_count"])[:10]

    return {
        "processes": proc_out,
        "hubs": hubs,
        "recovery_order": [{"id": pid, "name": pmap[pid].name,
                            "rto_hours": pmap[pid].rto_hours} for pid in order],
        "cycles": [[pmap[i].name for i in cyc] for cyc in cycles],
        "critical_path": critical_path,
        "has_process_deps": has_edges,
        "total_processes": len(procs),
    }


def build_process_dossier(db: Session, org_id: Optional[int], pid: int) -> Optional[dict]:
    """Todo sobre un proceso en un sitio: jerarquia, BIA, RTO efectivo,
    dependencias (y quien depende de el), escenarios, estrategias, planes,
    pruebas y hallazgos de coherencia. Alimenta el panel unico de Fase 3."""
    from app.models import (BCMScenario, BCMScenarioAssessment, BCPDependency,
                            BCPPlan, BCPStrategy, BCPTest, BusinessProcess)
    from app.services.bcp_service import bia_completeness

    p = db.get(BusinessProcess, pid)
    if not p or p.organization_id != org_id:
        return None

    procs = db.query(BusinessProcess).filter_by(organization_id=org_id).all()
    pmap = {x.id: x for x in procs}
    proc_rto = {x.id: _num(x.rto_hours) for x in procs}
    deps = db.query(BCPDependency).filter_by(organization_id=org_id).all()

    my_deps = [d for d in deps if d.process_id == pid]
    grouped: dict = {}
    crit_dep_rtos = []
    for d in my_deps:
        grouped.setdefault(d.dependency_type or "other", []).append({
            "id": d.id, "name": d.name, "is_critical": bool(d.is_critical),
            "rto_hours": d.rto_hours,
            "depends_on_process": pmap[d.depends_on_process_id].name
            if getattr(d, "depends_on_process_id", None) in pmap else None,
            "recovery_sequence": getattr(d, "recovery_sequence", None),
            "alternative": getattr(d, "alternative", None),
        })
        if d.is_critical:
            crit_dep_rtos.append(_dep_rto(d, proc_rto))

    depended_on_by = [{"id": pmap[d.process_id].id, "name": pmap[d.process_id].name}
                      for d in deps
                      if getattr(d, "depends_on_process_id", None) == pid
                      and d.process_id in pmap]

    children = [{"id": c.id, "name": c.name, "criticality": c.criticality,
                 "rto_hours": c.rto_hours}
                for c in procs if getattr(c, "parent_process_id", None) == pid]
    parent = None
    if getattr(p, "parent_process_id", None) in pmap:
        par = pmap[p.parent_process_id]
        parent = {"id": par.id, "name": par.name}

    declared = _num(p.rto_hours)
    eff = _effective_rto(declared, crit_dep_rtos)

    strategies = db.query(BCPStrategy).filter_by(
        organization_id=org_id, process_id=pid).all()
    all_plans = db.query(BCPPlan).filter_by(organization_id=org_id).all()
    plans = [pl for pl in all_plans if pid in (pl.process_ids or [])]
    all_tests = db.query(BCPTest).filter_by(organization_id=org_id).all()
    tests = [t for t in all_tests if pid in (t.process_ids or [])]

    scen = {s.id: s for s in db.query(BCMScenario).filter_by(organization_id=org_id).all()}
    assessments = db.query(BCMScenarioAssessment).filter_by(
        organization_id=org_id, process_id=pid).all()

    node = {
        "effective_rto": eff,
        "has_strategy": bool(strategies),
        "has_plan": bool(plans),
        "test_ok": any(
            t.conducted_at and
            (datetime.now(timezone.utc) - t.conducted_at.replace(tzinfo=timezone.utc)).days <= 365
            for t in tests),
    }
    findings = _process_findings(p, node, my_deps, children, proc_rto)

    try:
        bia = bia_completeness(None, p)
    except Exception:
        bia = {"pct": 0, "missing": []}

    return {
        "id": p.id, "name": p.name, "description": p.description,
        "criticality": p.criticality, "business_unit": getattr(p, "business_unit", None),
        "location_id": getattr(p, "location_id", None),
        "rto_hours": p.rto_hours, "rpo_hours": p.rpo_hours, "mtpd_hours": p.mtpd_hours,
        "declared_rto": declared, "effective_rto": eff,
        "rto_gap": bool(eff is not None and declared is not None and eff > declared),
        "weighted_impact": getattr(p, "weighted_impact", None),
        "impact_band": getattr(p, "impact_band", None),
        "bia_pct": bia["pct"], "bia_missing": bia.get("missing", []),
        "source": getattr(p, "source", None),
        "import_confidence": getattr(p, "import_confidence", None),
        "needs_review": bool(getattr(p, "needs_review", False)),
        "parent": parent, "children": children,
        "dependencies": grouped, "dep_count": len(my_deps),
        "depended_on_by": depended_on_by,
        "strategies": [{"id": s.id, "name": s.name, "strategy_type": s.strategy_type,
                        "implementation_status": s.implementation_status} for s in strategies],
        "plans": [{"id": pl.id, "code": pl.code, "name": pl.name,
                   "status": pl.status, "version": pl.version} for pl in plans],
        "tests": [{"id": t.id, "code": t.code, "test_type": t.test_type,
                   "result": t.result,
                   "conducted_at": t.conducted_at.isoformat() if t.conducted_at else None}
                  for t in tests],
        "scenarios": [{"id": a.id, "scenario_name": scen[a.scenario_id].name
                       if a.scenario_id in scen else None,
                       "rto_label": a.rto_label, "weighted_impact": a.weighted_impact,
                       "impact_band": a.impact_band} for a in assessments],
        "findings": findings,
    }


def _find_cycles(depends_on: dict) -> list:
    """Devuelve algunas listas de ids que forman ciclo (deteccion por DFS)."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in depends_on}
    cycles, stack = [], []

    def dfs(n):
        color[n] = GRAY
        stack.append(n)
        for m in depends_on.get(n, ()):
            if color.get(m) == GRAY:
                if m in stack:
                    cycles.append(stack[stack.index(m):] + [m])
            elif color.get(m) == WHITE:
                dfs(m)
        stack.pop()
        color[n] = BLACK

    for n in depends_on:
        if color[n] == WHITE:
            dfs(n)
    return cycles[:5]
