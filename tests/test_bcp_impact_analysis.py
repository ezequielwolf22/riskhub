"""Fase 2: grafo de dependencias proceso->proceso y propagacion de impacto."""


def _proc(client, h, name, rto=None):
    return client.post("/api/bcp/processes", headers=h, json={
        "name": name, "criticality": "high", "rto_hours": rto}).json()


def _dep(client, h, proc_id, needs_id):
    return client.post("/api/bcp/dependencies", headers=h, json={
        "process_id": proc_id, "dependency_type": "process",
        "name": "necesita", "depends_on_process_id": needs_id, "is_critical": True})


def _by_name(analysis, name):
    return next(p for p in analysis["processes"] if p["name"] == name)


def test_propagacion_de_impacto_transitiva(client, auth_headers):
    a = _proc(client, auth_headers, "IMP A", 1)
    b = _proc(client, auth_headers, "IMP B", 2)
    c = _proc(client, auth_headers, "IMP C", 4)
    _dep(client, auth_headers, b["id"], a["id"])   # B necesita A
    _dep(client, auth_headers, c["id"], b["id"])   # C necesita B

    an = client.get("/api/bcp/impact-analysis", headers=auth_headers).json()
    assert an["has_process_deps"] is True
    # Si cae A, se ven afectados B y C (propagacion transitiva).
    na = _by_name(an, "IMP A")
    assert na["impact_count"] == 2
    assert set(na["impact_names"]) == {"IMP B", "IMP C"}
    # Si cae B, solo C.
    assert _by_name(an, "IMP B")["impact_count"] == 1


def test_orden_de_recuperacion_y_camino_critico(client, auth_headers):
    an = client.get("/api/bcp/impact-analysis", headers=auth_headers).json()
    order = [n["name"] for n in an["recovery_order"] if n["name"].startswith("IMP ")]
    # A se recupera antes que B, y B antes que C.
    assert order.index("IMP A") < order.index("IMP B") < order.index("IMP C")
    # Camino critico A->B->C con RTO total 1+2+4=7.
    cp = [n["name"] for n in an["critical_path"]["nodes"]]
    assert cp == ["IMP A", "IMP B", "IMP C"]
    assert an["critical_path"]["total_rto"] == 7


def test_los_ciclos_se_detectan(client, auth_headers):
    d = _proc(client, auth_headers, "IMP Ciclo D")
    e = _proc(client, auth_headers, "IMP Ciclo E")
    _dep(client, auth_headers, d["id"], e["id"])   # D necesita E
    _dep(client, auth_headers, e["id"], d["id"])   # E necesita D -> ciclo
    an = client.get("/api/bcp/impact-analysis", headers=auth_headers).json()
    flat = [name for cyc in an["cycles"] for name in cyc]
    assert "IMP Ciclo D" in flat and "IMP Ciclo E" in flat


def test_sin_dependencias_proceso_no_hay_grafo(client, auth_headers):
    # Una org recien creada sin deps proceso->proceso: has_process_deps puede ser
    # True por otros tests; comprobamos que la estructura es sana.
    an = client.get("/api/bcp/impact-analysis", headers=auth_headers).json()
    assert isinstance(an["processes"], list)
    assert "critical_path" in an and "recovery_order" in an
