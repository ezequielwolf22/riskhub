"""El registro de documentos por la API, extremo a extremo.

Subir (sin analizar, para no llamar al modelo), listar, excluir, incluir y
quitar. Verifica que los endpoints, el control de organizacion y el estado se
comportan como espera la UI.
"""


def _upload(client, auth_headers, name, content, analyze=False):
    return client.post(
        f"/api/ingest/documents?analyze={'true' if analyze else 'false'}",
        headers=auth_headers,
        files={"files": (name, content, "text/plain")},
    )


def test_flujo_completo_de_documentos(client, auth_headers):
    # Subir sin analizar (analyze=false: no toca el modelo)
    r = _upload(client, auth_headers, "BIA_api.txt", b"contenido del BIA", analyze=False)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["job_id"] is None          # no se lanzo analisis
    doc = body["documents"][0]
    assert doc["included"] is True
    assert doc["status"] == "pending"
    doc_id = doc["id"]

    # Aparece en el listado
    r = client.get("/api/ingest/documents", headers=auth_headers)
    assert r.status_code == 200
    assert any(d["id"] == doc_id for d in r.json())

    # Excluir
    r = client.patch(f"/api/ingest/documents/{doc_id}",
                     headers=auth_headers, json={"included": False})
    assert r.status_code == 200
    assert r.json()["included"] is False and r.json()["status"] == "excluded"

    # Volver a incluir
    r = client.patch(f"/api/ingest/documents/{doc_id}",
                     headers=auth_headers, json={"included": True})
    assert r.status_code == 200 and r.json()["included"] is True

    # Quitar
    r = client.delete(f"/api/ingest/documents/{doc_id}", headers=auth_headers)
    assert r.status_code == 204
    r = client.get("/api/ingest/documents", headers=auth_headers)
    assert not any(d["id"] == doc_id for d in r.json())


def test_subir_el_mismo_fichero_no_duplica_por_la_api(client, auth_headers):
    _upload(client, auth_headers, "dup_api.txt", b"identico", analyze=False)
    _upload(client, auth_headers, "dup_api_2.txt", b"identico", analyze=False)
    r = client.get("/api/ingest/documents", headers=auth_headers)
    dups = [d for d in r.json() if d["sha256"] and
            d["filename"] in ("dup_api.txt", "dup_api_2.txt")]
    assert len(dups) == 1


def test_analizar_sin_documentos_incluidos_da_422(client, auth_headers):
    # Con todo excluido, /analyze responde 422 en vez de encolar en vano.
    r = client.get("/api/ingest/documents", headers=auth_headers)
    for d in r.json():
        client.patch(f"/api/ingest/documents/{d['id']}",
                     headers=auth_headers, json={"included": False})
    r = client.post("/api/ingest/analyze", headers=auth_headers)
    assert r.status_code == 422
