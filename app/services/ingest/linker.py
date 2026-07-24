"""Enlaces deterministas post-ingesta: lo que da aristas al mapa de dependencias.

El agente extrae dependencias como texto suelto ("Ringcentral Phone System",
"Office 365 / Azure"), pero no las ata al proveedor o al activo real. Sin esos
enlaces, el mapa de dependencias sale sin relaciones — nodos sueltos, nada
profesional. Aqui, ya con todo materializado, se cierran esos enlaces por
nombre, de forma deterministica y reversible (todo queda en el lote).

No hay ningun LLM en este paso: es cruce de nombres, como el reconciliador.
"""
from __future__ import annotations

import logging

from app.services.ingest.reconciler import normalize_name

logger = logging.getLogger("riskhub.ingest.linker")


def _tokens(text: str) -> set:
    return {t for t in normalize_name(text).split() if len(t) >= 3}


def _best_supplier(dep_name: str, suppliers: list) -> object | None:
    """Proveedor cuyo nombre aparece dentro del de la dependencia (o al reves).

    "Ringcentral Phone System" -> proveedor "RingCentral". Se exige que el
    nombre del proveedor (normalizado) este contenido, no un simple parecido:
    enlazar de menos es preferible a atar la dependencia al proveedor
    equivocado.
    """
    dn = normalize_name(dep_name)
    if not dn:
        return None
    best, best_len = None, 0
    for s in suppliers:
        sn = normalize_name(s.name)
        if len(sn) < 3:
            continue
        if (sn in dn or dn in sn) and len(sn) > best_len:
            best, best_len = s, len(sn)
    if best is not None:
        return best
    # Segundo intento por solape de palabras significativas (>= 2 tokens)
    dtok = _tokens(dep_name)
    for s in suppliers:
        if len(_tokens(s.name) & dtok) >= 2:
            return s
    return None


def link_dependencies(db, org_id: int, batch=None) -> dict:
    """Ata dependencias a su proveedor/activo y alimenta el grafo.

    Devuelve cuantos enlaces creo. Idempotente: no repite lo ya enlazado ni
    pisa un enlace puesto a mano.
    """
    from app.models import Asset, BCPDependency, BusinessProcess, Supplier

    suppliers = db.query(Supplier).filter_by(organization_id=org_id).all()
    assets = db.query(Asset).filter_by(organization_id=org_id).all()
    deps = db.query(BCPDependency).filter_by(organization_id=org_id).all()

    linked_sup = linked_asset = 0
    # supplier_ids por proceso, para que el grafo dibuje proceso -> proveedor
    proc_suppliers: dict[int, set] = {}

    for dep in deps:
        if not dep.name:
            continue
        if dep.supplier_id is None:
            sup = _best_supplier(dep.name, suppliers)
            if sup is not None:
                dep.supplier_id = sup.id
                linked_sup += 1
                proc_suppliers.setdefault(dep.process_id, set()).add(sup.id)
        elif dep.process_id:
            proc_suppliers.setdefault(dep.process_id, set()).add(dep.supplier_id)

        if dep.asset_id is None and assets:
            dn = normalize_name(dep.name)
            match = next((a for a in assets
                          if normalize_name(a.name) and
                          (normalize_name(a.name) in dn or dn in normalize_name(a.name))),
                         None)
            if match is not None:
                dep.asset_id = match.id
                linked_asset += 1

    # Volcar los proveedores encontrados al proceso (union con lo que ya tuviera)
    procs_touched = 0
    for pid, sids in proc_suppliers.items():
        p = db.get(BusinessProcess, pid)
        if not p:
            continue
        current = set(p.supplier_ids or [])
        merged = current | sids
        if merged != current:
            p.supplier_ids = sorted(merged)
            procs_touched += 1

    db.flush()
    logger.info("ingest: enlaces de dependencias org=%s sup=%d asset=%d proc=%d",
                org_id, linked_sup, linked_asset, procs_touched)
    return {"suppliers_linked": linked_sup, "assets_linked": linked_asset,
            "processes_touched": procs_touched}
