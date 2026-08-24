"""Fase 3: panel unico por proceso (dossier)."""


def test_el_dossier_reune_todo_del_proceso(client, auth_headers):
    a = client.post("/api/bcp/processes", headers=auth_headers, json={
        "name": "DOS Nucleo", "criticality": "critical", "rto_hours": 4,
        "business_unit": "Ops"}).json()
    b = client.post("/api/bcp/processes", headers=auth_headers, json={
        "name": "DOS Soporte", "criticality": "high", "rto_hours": 24}).json()
    child = client.post("/api/bcp/processes", headers=auth_headers, json={
        "name": "DOS Sub", "criticality": "medium",
        "parent_process_id": a["id"]}).json()
    # A necesita B (critico, mas lento) -> RTO efectivo de A sube a 24.
    client.post("/api/bcp/dependencies", headers=auth_headers, json={
        "process_id": a["id"], "dependency_type": "process",
        "name": "necesita soporte", "depends_on_process_id": b["id"],
        "is_critical": True, "rto_hours": 24})
    # C necesita A -> A aparece en depended_on_by.
    c = client.post("/api/bcp/processes", headers=auth_headers, json={
        "name": "DOS Cliente", "criticality": "high"}).json()
    client.post("/api/bcp/dependencies", headers=auth_headers, json={
        "process_id": c["id"], "dependency_type": "process",
        "name": "usa nucleo", "depends_on_process_id": a["id"]})

    d = client.get(f"/api/bcp/processes/{a['id']}/dossier", headers=auth_headers).json()
    assert d["name"] == "DOS Nucleo"
    assert d["business_unit"] == "Ops"
    assert d["effective_rto"] == 24 and d["rto_gap"] is True
    assert any(ch["id"] == child["id"] for ch in d["children"])
    assert any(x["name"] == "DOS Cliente" for x in d["depended_on_by"])
    assert "process" in d["dependencies"]
    assert "bia_pct" in d and isinstance(d["findings"], list)


def test_dossier_de_proceso_inexistente_da_404(client, auth_headers):
    r = client.get("/api/bcp/processes/9999999/dossier", headers=auth_headers)
    assert r.status_code == 404
