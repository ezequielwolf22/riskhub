"""Mapa de continuidad: jerarquia real, propagacion de RTO y coherencia.

Verifica que el arbol refleja sede anidada -> unidad -> proceso -> subproceso,
que el RTO efectivo se propaga desde la dependencia critica mas lenta, y que las
contradicciones se declaran como hallazgos.
"""


def _find_proc(tree, name):
    """Busca un nodo de proceso por nombre en todo el arbol del mapa."""
    def walk(node):
        if node.get("name") == name:
            return node
        for ch in node.get("children", []):
            r = walk(ch)
            if r:
                return r
        return None
    for loc in tree.get("locations", []):
        found = _walk_loc(loc, walk)
        if found:
            return found
    for unit in tree.get("unassigned", []):
        for p in unit.get("processes", []):
            r = walk(p)
            if r:
                return r
    return None


def _walk_loc(loc, walk):
    for unit in loc.get("units", []):
        for p in unit.get("processes", []):
            r = walk(p)
            if r:
                return r
    for sub in loc.get("sublocations", []):
        r = _walk_loc(sub, walk)
        if r:
            return r
    return None


def _codes(node):
    return {f["code"] for f in node.get("findings", [])}


def test_mapa_refleja_sede_anidada_unidad_y_subprocesos(client, auth_headers):
    hq = client.post("/api/bcp/locations", headers=auth_headers,
                     json={"name": "CMAP HQ Madrid"}).json()
    sub = client.post("/api/bcp/locations", headers=auth_headers,
                      json={"name": "CMAP Sucursal Chile", "parent_id": hq["id"]}).json()
    ventas = client.post("/api/bcp/processes", headers=auth_headers, json={
        "name": "CMAP Ventas", "criticality": "critical", "rto_hours": 4,
        "location_id": hq["id"], "business_unit": "Comercial"}).json()
    fact = client.post("/api/bcp/processes", headers=auth_headers, json={
        "name": "CMAP Facturacion", "criticality": "high", "rto_hours": 8,
        "location_id": hq["id"], "business_unit": "Comercial",
        "parent_process_id": ventas["id"]}).json()
    assert fact["parent_process_id"] == ventas["id"]

    tree = client.get("/api/bcp/continuity-map", headers=auth_headers).json()

    hq_node = next(loc for loc in tree["locations"] if loc["id"] == hq["id"])
    # La sede hija cuelga de la padre (jerarquia de sedes, no plano).
    assert any(s["id"] == sub["id"] for s in hq_node["sublocations"])
    # Unidad de negocio agrupa los procesos.
    unit = next(u for u in hq_node["units"] if u["business_unit"] == "Comercial")
    ventas_node = next(p for p in unit["processes"] if p["id"] == ventas["id"])
    # El subproceso cuelga del proceso (jerarquia de procesos).
    assert any(c["id"] == fact["id"] for c in ventas_node["children"])


def test_el_rto_efectivo_se_propaga_desde_la_dependencia_critica(client, auth_headers):
    p = client.post("/api/bcp/processes", headers=auth_headers, json={
        "name": "CMAP Portal", "criticality": "critical", "rto_hours": 4}).json()
    # Dependencia critica mas lenta (24h) que el RTO declarado (4h).
    client.post("/api/bcp/dependencies", headers=auth_headers, json={
        "process_id": p["id"], "dependency_type": "IT_system",
        "name": "CRM externo", "is_critical": True, "rto_hours": 24})

    tree = client.get("/api/bcp/continuity-map", headers=auth_headers).json()
    node = _find_proc(tree, "CMAP Portal")
    assert node is not None
    assert node["declared_rto"] == 4
    assert node["effective_rto"] == 24
    assert node["rto_gap"] is True
    assert "dep_slower_than_process" in _codes(node)


def test_subproceso_mas_exigente_que_el_padre_se_marca(client, auth_headers):
    tree = client.get("/api/bcp/continuity-map", headers=auth_headers).json()
    ventas = _find_proc(tree, "CMAP Ventas")
    # Facturacion (8h) tiene RTO mayor que su padre Ventas (4h).
    assert ventas is not None
    assert "child_rto_gt_parent" in _codes(ventas)
    # Proceso critico sin estrategia/plan/prueba tambien se declara.
    assert "critical_no_strategy" in _codes(ventas)


def test_la_jerarquia_de_procesos_no_admite_ciclos(client, auth_headers):
    a = client.post("/api/bcp/processes", headers=auth_headers, json={
        "name": "CMAP Ciclo A", "criticality": "medium"}).json()
    b = client.post("/api/bcp/processes", headers=auth_headers, json={
        "name": "CMAP Ciclo B", "criticality": "medium",
        "parent_process_id": a["id"]}).json()
    # A no puede ser su propio padre.
    r1 = client.patch(f"/api/bcp/processes/{a['id']}", headers=auth_headers,
                      json={"parent_process_id": a["id"]})
    assert r1.status_code == 422
    # A no puede colgar de B, que ya cuelga de A (ciclo).
    r2 = client.patch(f"/api/bcp/processes/{a['id']}", headers=auth_headers,
                      json={"parent_process_id": b["id"]})
    assert r2.status_code == 422


def test_desvincular_el_padre_con_null(client, auth_headers):
    parent = client.post("/api/bcp/processes", headers=auth_headers, json={
        "name": "CMAP Padre", "criticality": "low"}).json()
    child = client.post("/api/bcp/processes", headers=auth_headers, json={
        "name": "CMAP Hijo", "criticality": "low",
        "parent_process_id": parent["id"]}).json()
    assert child["parent_process_id"] == parent["id"]
    got = client.patch(f"/api/bcp/processes/{child['id']}", headers=auth_headers,
                       json={"parent_process_id": None}).json()
    assert got["parent_process_id"] is None
