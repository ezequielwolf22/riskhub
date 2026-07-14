"""Regresion: scores TPRM float heredados no deben romper GET /api/suppliers/.

Datos antiguos guardaron residual_risk_score como float (p.ej. 10.8) en una
columna Integer (SQLite no fuerza el tipo). La validacion de respuesta exigia
int y devolvia 500 para toda la lista."""
from app.schemas import SupplierOut, _coerce_int


def test_coerce_int_helper():
    assert _coerce_int(10.8) == 11
    assert _coerce_int(10.0) == 10
    assert _coerce_int(7) == 7
    assert _coerce_int(None) is None


def test_supplier_list_survives_float_score(client, auth_headers):
    # Crear un proveedor y forzar un residual_risk_score float directo en BD,
    # como los datos heredados de junio en produccion.
    r = client.post("/api/suppliers/",
                    json={"name": "Prov Float Score", "criticality": "high"},
                    headers=auth_headers)
    assert r.status_code in (200, 201), r.text
    sid = r.json()["id"]

    from tests.conftest import _TestSession, _USING_PG
    if _USING_PG:
        return  # PG fuerza el tipo entero: el caso no aplica
    from sqlalchemy import text
    db = _TestSession()
    try:
        db.execute(text("UPDATE suppliers SET residual_risk_score = 10.8, "
                        "inherent_risk_score = 20.4 WHERE id = :i"), {"i": sid})
        db.commit()
    finally:
        db.close()

    # La lista completa debe seguir devolviendo 200 y el score ya como int.
    resp = client.get("/api/suppliers/", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    mine = next((s for s in resp.json() if s["id"] == sid), None)
    assert mine is not None
    assert mine["residual_risk_score"] == 11
    assert mine["inherent_risk_score"] == 20
