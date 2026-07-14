"""Informe TPRM (PDF) y carga de sus locale fragments."""


def test_tprm_report_locale_keys_loaded():
    from app.i18n import t as _t
    # Los fragmentos reports_tprm.json (es/en) deben fusionarse en el arbol i18n.
    assert "TPRM" in _t("reports.tprm.title", "es")
    assert "TPRM" in _t("reports.tprm.title", "en")
    # Placeholders formateables
    body = _t("reports.tprm.summary_body", "es", total=3, critical=1)
    assert "3" in body and "1" in body


def test_tprm_report_pdf_ok(client, auth_headers):
    resp = client.get("/api/reports/tprm", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"
    assert len(resp.content) > 800


def test_tprm_report_with_data(client, auth_headers):
    # Crear un proveedor critico y comprobar que el PDF sigue generando bien.
    payload = {"name": "Proveedor Informe TPRM", "criticality": "high"}
    r = client.post("/api/suppliers/", json=payload, headers=auth_headers)
    assert r.status_code in (200, 201), r.text
    resp = client.get("/api/reports/tprm", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"
