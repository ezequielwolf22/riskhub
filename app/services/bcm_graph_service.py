"""Grafo de dependencias BCM — compatible con Cytoscape.js."""
import logging
from sqlalchemy.orm import Session
from app.models import (BusinessProcess, BCPDependency, Asset, Supplier, BCMLocation,
                        BCPSupplierLink, BCPPlan)

logger = logging.getLogger("riskhub.bcm_graph")

CRIT_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}

NODE_STYLES = {
    "process":  {"color": "#5B00AD", "shape": "ellipse"},
    "asset":    {"color": "#E05500", "shape": "roundrectangle"},
    "supplier": {"color": "#1A7A40", "shape": "hexagon"},
    "plan":     {"color": "#0369a1", "shape": "diamond"},
}


def build_dependency_graph(db: Session, org_id: int, location_id: int = None) -> dict:
    """
    Construye el grafo de dependencias BCM.
    Nodos: procesos + activos referenciados + proveedores referenciados.
    Aristas: process→asset, process→supplier, process→process (deps).
    """
    nodes, edges = {}, []

    q = db.query(BusinessProcess).filter_by(organization_id=org_id)
    if location_id:
        q = q.filter_by(location_id=location_id)
    procs = q.all()

    # Build plan→process mapping for enriching nodes
    plans = db.query(BCPPlan).filter_by(organization_id=org_id).all()
    proc_to_plans = {}
    for plan in plans:
        for pid_raw in (plan.process_ids or []):
            try:
                pid_int = int(pid_raw)
                proc_to_plans.setdefault(pid_int, []).append({
                    "id": plan.id, "name": plan.name, "code": plan.code,
                    "type": plan.plan_type, "status": plan.status,
                })
            except (ValueError, TypeError):
                pass

    for p in procs:
        loc = db.get(BCMLocation, p.location_id) if p.location_id else None
        nodes[f"proc_{p.id}"] = {
            "id": f"proc_{p.id}", "type": "process",
            "label": p.name, "criticality": p.criticality,
            "rto_hours": p.rto_hours, "rpo_hours": getattr(p, "rpo_hours", None),
            "mtpd_hours": getattr(p, "mtpd_hours", None),
            "cost_per_hour": getattr(p, "cost_per_hour", None),
            "location_id": p.location_id,
            "location_name": loc.name if loc else None,
            "plans": proc_to_plans.get(p.id, []),
            **NODE_STYLES["process"],
        }

    asset_ids_used = set()
    for p in procs:
        for aid in (p.asset_ids or []):
            try:
                asset_ids_used.add(int(aid))
            except (ValueError, TypeError):
                pass

    for aid in asset_ids_used:
        a = db.get(Asset, aid)
        if not a or a.organization_id != org_id:
            continue
        nodes[f"asset_{aid}"] = {
            "id": f"asset_{aid}", "type": "asset",
            "label": a.name, "code": a.code,
            "criticality": "critical" if (a.value_max or 0) >= 3 else "medium",
            **NODE_STYLES["asset"],
        }

    sup_ids_used = set()
    for p in procs:
        for sid in (p.supplier_ids or []):
            try:
                sup_ids_used.add(int(sid))
            except (ValueError, TypeError):
                pass

    for sid in sup_ids_used:
        try:
            s = db.get(Supplier, sid)
        except Exception:
            db.rollback()
            continue
        if not s or s.organization_id != org_id:
            continue
        nodes[f"sup_{sid}"] = {
            "id": f"sup_{sid}", "type": "supplier",
            "label": s.name,
            "criticality": getattr(s, "risk_level", "medium"),
            "is_external": True,
            **NODE_STYLES["supplier"],
        }

    for p in procs:
        pn = f"proc_{p.id}"
        for aid in (p.asset_ids or []):
            an = f"asset_{int(aid)}" if str(aid).isdigit() else None
            if an and an in nodes:
                edges.append({"id": f"e_{pn}_{an}", "source": pn, "target": an,
                               "type": "uses_asset", "label": "usa"})
        for sid in (p.supplier_ids or []):
            sn = f"sup_{int(sid)}" if str(sid).isdigit() else None
            if sn and sn in nodes:
                edges.append({"id": f"e_{pn}_{sn}", "source": pn, "target": sn,
                               "type": "uses_supplier", "label": "depende de"})

    deps = db.query(BCPDependency).filter_by(organization_id=org_id).all()
    for dep in deps:
        src = f"proc_{dep.process_id}"
        if src not in nodes:
            continue
        if getattr(dep, "depends_on_process_id", None):
            tgt = f"proc_{dep.depends_on_process_id}"
            if tgt not in nodes:
                dp = db.get(BusinessProcess, dep.depends_on_process_id)
                if dp:
                    loc = db.get(BCMLocation, dp.location_id) if dp.location_id else None
                    nodes[tgt] = {
                        "id": tgt, "type": "process", "label": dp.name,
                        "criticality": dp.criticality, "location_id": dp.location_id,
                        "location_name": loc.name if loc else None,
                        "is_external": location_id and dp.location_id != location_id,
                        **NODE_STYLES["process"],
                    }
            edges.append({"id": f"e_{src}_p{dep.depends_on_process_id}",
                          "source": src, "target": tgt,
                          "type": "process_dep",
                          "label": f"requiere (seq {dep.recovery_sequence or '?'})",
                          "is_critical": dep.is_critical})
        if dep.asset_id:
            tgt = f"asset_{dep.asset_id}"
            if tgt not in nodes:
                a = db.get(Asset, dep.asset_id)
                if a:
                    nodes[tgt] = {"id": tgt, "type": "asset",
                                   "label": a.name, "code": a.code,
                                   **NODE_STYLES["asset"]}
            if tgt in nodes:
                conn_type = getattr(dep, "connection_type", None)
                edge_label = dep.dependency_type or "depende de"
                if conn_type:
                    edge_label = f"{conn_type}"
                edges.append({"id": f"e_{src}_a{dep.asset_id}",
                              "source": src, "target": tgt,
                              "type": "asset_dep",
                              "label": edge_label,
                              "is_critical": dep.is_critical,
                              "connection_type": conn_type,
                              "protocol": getattr(dep, "protocol", None),
                              "data_direction": getattr(dep, "data_direction", None),
                              "data_classification": getattr(dep, "data_classification", None),
                              })

    # Include suppliers linked via BCPSupplierLink (the main way to link suppliers to processes)
    slinks = db.query(BCPSupplierLink).filter_by(organization_id=org_id).all()
    for sl in slinks:
        try:
            s = db.get(Supplier, sl.supplier_id)
        except Exception:
            db.rollback()
            continue
        if not s or s.organization_id != org_id:
            continue
        nid = f"sup_{sl.supplier_id}"
        if nid not in nodes:
            nodes[nid] = {
                "id": nid, "type": "supplier",
                "label": s.name,
                "criticality": sl.criticality or getattr(s, "risk_level", "medium"),
                "is_spof": not sl.has_contingency_plan,
                "is_external": True,
                "contract_sla_hours": sl.contract_sla_hours,
                "rto_impact_hours": sl.rto_impact_hours,
                "has_contingency": sl.has_contingency_plan,
                **NODE_STYLES["supplier"],
            }
        for pid in (sl.process_ids or []):
            try:
                pn = f"proc_{int(pid)}"
            except (ValueError, TypeError):
                continue
            if pn not in nodes:
                continue
            eid = f"e_{pn}_{nid}_sl"
            if not any(e["id"] == eid for e in edges):
                edges.append({
                    "id": eid, "source": pn, "target": nid,
                    "type": "uses_supplier", "label": "proveedor externo",
                    "is_critical": sl.criticality in ("critical", "high"),
                    "is_external": True,
                })

    in_deg = {}
    for e in edges:
        in_deg[e["target"]] = in_deg.get(e["target"], 0) + 1
    for nid, n in nodes.items():
        n["in_degree"] = in_deg.get(nid, 0)
        n["is_spof"] = in_deg.get(nid, 0) >= 3

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "spof_count": sum(1 for n in nodes.values() if n.get("is_spof")),
        }
    }


def analyze_graph_with_ai(db: Session, graph: dict, org_id: int,
                           api_key: str, model: str) -> str:
    import anthropic
    spofs = [n["label"] for n in graph["nodes"] if n.get("is_spof")]
    s = graph["stats"]
    prompt = (
        f"Eres auditor experto ISO 22301 y resiliencia operacional.\n"
        f"Grafo BCM: {s['total_nodes']} nodos, {s['total_edges']} dependencias, "
        f"{s['spof_count']} SPOFs: {', '.join(spofs[:5])}.\n\n"
        f"Proporciona: (1) Riesgos de los SPOFs con cláusula ISO 22301 afectada, "
        f"(2) Cadena crítica de recuperación, (3) Top 3 acciones con esfuerzo estimado. "
        f"Máximo 350 palabras."
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model, max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text
    except Exception as exc:
        return f"Análisis no disponible: {exc}"
