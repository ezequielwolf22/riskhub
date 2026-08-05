"""BIA por proceso dirigido por el metodo declarado de la organizacion.

El proceso guarda su impacto por dimension y horizonte; el impacto ponderado y
la banda los calcula el motor determinista (nunca se aceptan del cliente) y
cambian cuando cambia el metodo, igual que los escenarios.
"""


def _crear_proceso(client, auth_headers, **extra):
    body = {"name": "Facturacion", "criticality": "critical", "rto_hours": 1}
    body.update(extra)
    r = client.post("/api/bcp/processes", headers=auth_headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_el_proceso_calcula_impacto_ponderado_desde_sus_impactos(client, auth_headers):
    proc = _crear_proceso(client, auth_headers, impacts={
        "operational": {"0h": 5, ">4h": 5},
        "financial": {"0h": 3},
    })
    assert proc["weighted_impact"] is not None
    assert proc["impact_band"] in ("severe", "critical", "relevant", "trivial", "none")


def test_el_impacto_ponderado_nunca_se_acepta_del_cliente(client, auth_headers):
    # Aunque el cliente mande un weighted_impact absurdo, se ignora: el schema
    # no lo admite y el motor lo recalcula.
    proc = _crear_proceso(client, auth_headers, impacts={"operational": {"0h": 5}})
    calc = proc["weighted_impact"]
    r = client.patch("/api/bcp/processes/%d" % proc["id"], headers=auth_headers,
                     json={"weighted_impact": 999})
    assert r.status_code == 200
    assert r.json()["weighted_impact"] == calc


def test_sin_impactos_no_hay_cifra_inventada(client, auth_headers):
    proc = _crear_proceso(client, auth_headers)
    assert proc["weighted_impact"] is None
    assert proc["impact_band"] is None


def test_cambiar_el_metodo_recalcula_el_bia_del_proceso(client, auth_headers):
    proc = _crear_proceso(client, auth_headers, impacts={"operational": {"0h": 5}})
    before = proc["weighted_impact"]
    # Pasar de producto (impacto x RTO) a suma (RTO + criterio) cambia la cifra.
    r = client.put("/api/bcp/bia-criteria", headers=auth_headers,
                   json={"combination": "sum"})
    assert r.status_code == 200, r.text
    got = client.get("/api/bcp/processes/%d" % proc["id"], headers=auth_headers).json()
    assert got["weighted_impact"] != before
    assert got["weighted_impact"] is not None
