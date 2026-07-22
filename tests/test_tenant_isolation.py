"""Aislamiento entre clientes — la garantia de seguridad de la plataforma.

Dos promesas que deben cumplirse siempre:
  1. El superadmin ve y administra a todos sus clientes.
  2. Cada cliente ve y toca EXCLUSIVAMENTE lo suyo, pase lo que pase.

El vector mas peligroso es el punto 2 combinado con la cabecera X-Active-Org:
si un usuario normal pudiera enviarla y que se le hiciera caso, se saltaria el
aislamiento entero con una linea de curl.
"""
import uuid

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _make_tenant(client, name):
    """Crea una organizacion con su admin propio y devuelve sus cabeceras."""
    from app.models import Organization, User, UserRole
    from app.security import hash_password

    db = _TestSession()
    try:
        org = Organization(name=f"{name} {_uid()}", plan="enterprise")
        db.add(org)
        db.flush()
        email = f"admin-{_uid()}@test.internal"
        db.add(User(email=email, full_name=f"Admin {name}", role=UserRole.ADMIN,
                    hashed_password=hash_password("TenantAdmin123!"),
                    organization_id=org.id, is_active=True))
        db.commit()
        org_id = org.id
    finally:
        db.close()

    token = client.post("/api/auth/login", data={
        "username": email, "password": "TenantAdmin123!",
    }).json()["access_token"]
    return {"org_id": org_id, "email": email,
            "headers": {"Authorization": f"Bearer {token}"}}


def _make_superadmin(client):
    from app.models import Organization, User, UserRole
    from app.security import hash_password

    db = _TestSession()
    try:
        own = db.query(Organization).first().id
        email = f"super-{_uid()}@test.internal"
        db.add(User(email=email, full_name="Super", role=UserRole.SUPERADMIN,
                    hashed_password=hash_password("SuperAdmin123!"),
                    organization_id=own, is_active=True))
        db.commit()
    finally:
        db.close()
    token = client.post("/api/auth/login", data={
        "username": email, "password": "SuperAdmin123!",
    }).json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "own_org_id": own}


def _asset_payload():
    return {"name": f"Activo {_uid()}", "asset_type": "support_hardware",
            "value_confidentiality": 3, "value_integrity": 3, "value_availability": 3}


def _seed_asset(org_id, marker="Activo"):
    """Siembra un activo directamente en BD.

    Por API, crear un activo dispara el analisis IA y la suite acabaria saliendo
    a la red real. Para comprobar VISIBILIDAD basta con el dato en la tabla; el
    camino de escritura por API ya lo cubren los tests de arriba.
    """
    from app.models import Asset, AssetType
    db = _TestSession()
    try:
        asset = Asset(organization_id=org_id, code=f"AST-{_uid()}",
                      name=f"{marker} {_uid()}", asset_type=AssetType.SUPPORT_SOFTWARE)
        db.add(asset)
        db.commit()
        return asset.id
    finally:
        db.close()


# ---------- 1. Un cliente no ve lo de otro ----------

def test_tenant_cannot_list_another_tenants_data(client):
    a = _make_tenant(client, "Cliente A")
    b = _make_tenant(client, "Cliente B")

    creado = client.post("/api/assets/", json=_asset_payload(), headers=a["headers"])
    assert creado.status_code in (200, 201), creado.text
    asset_id = creado.json()["id"]

    listado = client.get("/api/assets/", headers=b["headers"])
    assert listado.status_code == 200
    items = listado.json()
    items = items if isinstance(items, list) else items.get("items", [])
    assert not any(x.get("id") == asset_id for x in items), \
        "un cliente ve activos de otro en el listado"


def test_tenant_cannot_read_another_tenants_record_by_id(client):
    a = _make_tenant(client, "Cliente A")
    b = _make_tenant(client, "Cliente B")
    asset_id = _seed_asset(a["org_id"])

    resp = client.get(f"/api/assets/{asset_id}", headers=b["headers"])
    assert resp.status_code in (403, 404), \
        f"acceso directo por id a un activo ajeno devolvio {resp.status_code}"


def test_tenant_cannot_modify_or_delete_another_tenants_record(client):
    a = _make_tenant(client, "Cliente A")
    b = _make_tenant(client, "Cliente B")
    asset_id = _seed_asset(a["org_id"])

    upd = client.put(f"/api/assets/{asset_id}", json=_asset_payload(), headers=b["headers"])
    assert upd.status_code in (403, 404), f"modificacion cruzada devolvio {upd.status_code}"

    dele = client.delete(f"/api/assets/{asset_id}", headers=b["headers"])
    assert dele.status_code in (403, 404), f"borrado cruzado devolvio {dele.status_code}"

    # Y sigue existiendo para su dueno
    assert client.get(f"/api/assets/{asset_id}", headers=a["headers"]).status_code == 200


# ---------- 2. La cabecera X-Active-Org no es una llave maestra ----------

def test_regular_admin_cannot_escalate_with_active_org_header(client):
    """CRITICO: si a un usuario normal se le hiciera caso con X-Active-Org, el
    aislamiento se saltaria con una sola cabecera."""
    a = _make_tenant(client, "Cliente A")
    b = _make_tenant(client, "Cliente B")
    asset_id = _seed_asset(a["org_id"])

    spoof = dict(b["headers"], **{"X-Active-Org": str(a["org_id"])})

    listado = client.get("/api/assets/", headers=spoof)
    items = listado.json()
    items = items if isinstance(items, list) else items.get("items", [])
    assert not any(x.get("id") == asset_id for x in items), \
        "un admin normal se cuela en otra organizacion enviando X-Active-Org"

    directo = client.get(f"/api/assets/{asset_id}", headers=spoof)
    assert directo.status_code in (403, 404), \
        "acceso directo por id con X-Active-Org falsificada"


def test_spoofed_header_does_not_redirect_writes(client):
    """Tampoco debe poder ESCRIBIR en otra organizacion falsificando la cabecera."""
    from app.models import Asset

    a = _make_tenant(client, "Cliente A")
    b = _make_tenant(client, "Cliente B")
    spoof = dict(b["headers"], **{"X-Active-Org": str(a["org_id"])})

    creado = client.post("/api/assets/", json=_asset_payload(), headers=spoof)
    assert creado.status_code in (200, 201), creado.text

    db = _TestSession()
    try:
        asset = db.get(Asset, creado.json()["id"])
        assert asset.organization_id == b["org_id"], \
            "un admin normal ha escrito en otra organizacion falsificando X-Active-Org"
    finally:
        db.close()


# ---------- 3. El superadmin si administra a sus clientes ----------

def test_superadmin_sees_every_tenant_without_selection(client):
    sa = _make_superadmin(client)
    a = _make_tenant(client, "Cliente A")
    b = _make_tenant(client, "Cliente B")
    id_a = _seed_asset(a["org_id"])
    id_b = _seed_asset(b["org_id"])

    items = client.get("/api/assets/", headers=sa["headers"]).json()
    items = items if isinstance(items, list) else items.get("items", [])
    ids = {x.get("id") for x in items}
    assert id_a in ids and id_b in ids, \
        "el superadmin no ve los datos de todos sus clientes"


def test_superadmin_with_selection_sees_only_that_tenant(client):
    sa = _make_superadmin(client)
    a = _make_tenant(client, "Cliente A")
    b = _make_tenant(client, "Cliente B")
    id_a = _seed_asset(a["org_id"])
    id_b = _seed_asset(b["org_id"])

    focused = dict(sa["headers"], **{"X-Active-Org": str(a["org_id"])})
    items = client.get("/api/assets/", headers=focused).json()
    items = items if isinstance(items, list) else items.get("items", [])
    ids = {x.get("id") for x in items}
    assert id_a in ids, "enfocando al cliente A no se ven sus datos"
    assert id_b not in ids, "enfocando al cliente A se cuelan datos del cliente B"


def test_superadmin_can_manage_a_tenants_record(client):
    """Ver no basta: tiene que poder administrar."""
    sa = _make_superadmin(client)
    a = _make_tenant(client, "Cliente A")
    asset_id = _seed_asset(a["org_id"])
    focused = dict(sa["headers"], **{"X-Active-Org": str(a["org_id"])})

    assert client.get(f"/api/assets/{asset_id}", headers=focused).status_code == 200
    upd = client.put(f"/api/assets/{asset_id}",
                     json={**_asset_payload(), "name": "Renombrado por el superadmin"},
                     headers=focused)
    assert upd.status_code in (200, 201), f"el superadmin no puede editar: {upd.text}"


# ---------- 4. El aislamiento aguanta en los modulos nuevos ----------

def test_isolation_holds_for_strategic_plan_module(client):
    a = _make_tenant(client, "Cliente A")
    b = _make_tenant(client, "Cliente B")

    plan = client.post("/api/strategic-plans/", json={"name": f"PDS {_uid()}"},
                       headers=a["headers"]).json()
    prog = client.post("/api/initiatives/programs", json={"name": f"Prog {_uid()}"},
                       headers=a["headers"]).json()
    ini = client.post("/api/initiatives/", json={"title": f"Ini {_uid()}"},
                      headers=a["headers"]).json()

    # B no los ve
    assert not any(x["id"] == plan["id"]
                   for x in client.get("/api/strategic-plans/", headers=b["headers"]).json())
    assert not any(x["id"] == prog["id"]
                   for x in client.get("/api/initiatives/programs", headers=b["headers"]).json())
    assert not any(x["id"] == ini["id"]
                   for x in client.get("/api/initiatives/", headers=b["headers"]).json())

    # Ni accede por id
    for url in (f"/api/strategic-plans/{plan['id']}", f"/api/initiatives/{ini['id']}"):
        assert client.get(url, headers=b["headers"]).status_code in (403, 404), url

    # Ni puede aprobar el plan ajeno
    resp = client.post(f"/api/strategic-plans/{plan['id']}/request-approval",
                       json={}, headers=b["headers"])
    assert resp.status_code in (403, 404)


def test_isolation_holds_for_treatment_cockpit(client):
    """El cockpit agrega muchas fuentes: es donde mas facil se escapa una fuga."""
    a = _make_tenant(client, "Cliente A")
    b = _make_tenant(client, "Cliente B")

    from app.models import Asset, AssetType, Risk, RiskStatus, Threat, TreatmentOption
    db = _TestSession()
    try:
        threat = db.query(Threat).first()
        asset = Asset(organization_id=a["org_id"], code=f"AST-{_uid()}",
                      name=f"Activo {_uid()}", asset_type=AssetType.SUPPORT_SOFTWARE)
        db.add(asset)
        db.flush()
        risk = Risk(organization_id=a["org_id"], code=f"RSK-{_uid()}", asset_id=asset.id,
                    threat_id=threat.id, inherent_likelihood=4, inherent_consequence=4,
                    inherent_level=8, residual_level=8, status=RiskStatus.ASSESSED,
                    treatment_option=TreatmentOption.MODIFICATION,
                    treatment_plan="Plan confidencial del cliente A")
        db.add(risk)
        db.commit()
        risk_id = risk.id
    finally:
        db.close()

    board = client.get("/api/risks/treatment-board", headers=b["headers"]).json()
    items = [it for col in board["columns"].values() for it in col]
    assert not any(it["id"] == risk_id for it in items), \
        "el cockpit de un cliente muestra riesgos de otro"
    assert "confidencial" not in str(board), "se filtra contenido de otro cliente"
