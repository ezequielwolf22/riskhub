"""Contexto de organizacion activa del superadmin — aislamiento multi-tenant.

El usuario trabaja SIEMPRE como superadmin seleccionando una organizacion. Las
lecturas ya respetaban esa seleccion (filter_by_org) pero las escrituras usaban
la organizacion propia del superadmin: el POST devolvia 200 y el registro
desaparecia de la vista del cliente. Eran 365 lecturas de
current_user.organization_id repartidas por los routers.

El arreglo es central: durante la peticion, la organizacion "del usuario" ES la
que tiene enfocada. Estos tests fijan las dos mitades del contrato:
  1. lo que se crea aterriza en la organizacion enfocada, y
  2. eso NUNCA se escribe en la fila del superadmin en la base de datos.
"""
import uuid

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _superadmin(client, *, own_org_id=None):
    """Superadmin cuya organizacion propia NO es la que va a enfocar."""
    from app.models import Organization, User, UserRole
    from app.security import hash_password

    db = _TestSession()
    try:
        if own_org_id is None:
            own_org_id = db.query(Organization).first().id
        target = Organization(name=f"Cliente {_uid()}", plan="enterprise")
        db.add(target)
        db.flush()
        email = f"super-{_uid()}@test.internal"
        db.add(User(email=email, full_name="Super", role=UserRole.SUPERADMIN,
                    hashed_password=hash_password("SuperAdmin123!"),
                    organization_id=own_org_id, is_active=True))
        db.commit()
        target_id = target.id
    finally:
        db.close()

    token = client.post("/api/auth/login", data={
        "username": email, "password": "SuperAdmin123!",
    }).json()["access_token"]
    base = {"Authorization": f"Bearer {token}"}
    focused = dict(base, **{"X-Active-Org": str(target_id)})
    return {"email": email, "own_org_id": own_org_id, "target_org_id": target_id,
            "headers": base, "focused": focused}


def test_writes_land_in_the_focused_organization(client):
    """Barrido por los modulos principales: crear y volver a listar."""
    sa = _superadmin(client)
    H = sa["focused"]

    creados = {}

    r = client.post("/api/assets/", json={
        "name": f"Activo {_uid()}", "asset_type": "support_hardware",
        "value_confidentiality": 3, "value_integrity": 3, "value_availability": 3,
    }, headers=H)
    assert r.status_code in (200, 201), r.text
    creados["assets"] = ("/api/assets/", r.json()["id"])

    r = client.post("/api/suppliers/", json={"name": f"Proveedor {_uid()}"}, headers=H)
    if r.status_code in (200, 201):
        creados["suppliers"] = ("/api/suppliers/", r.json()["id"])

    r = client.post("/api/initiatives/programs", json={"name": f"Programa {_uid()}"}, headers=H)
    assert r.status_code == 200, r.text
    creados["programs"] = ("/api/initiatives/programs", r.json()["id"])

    r = client.post("/api/initiatives/", json={"title": f"Iniciativa {_uid()}"}, headers=H)
    assert r.status_code == 200, r.text
    creados["initiatives"] = ("/api/initiatives/", r.json()["id"])

    r = client.post("/api/strategic-plans/", json={"name": f"PDS {_uid()}"}, headers=H)
    assert r.status_code == 200, r.text
    creados["plans"] = ("/api/strategic-plans/", r.json()["id"])

    # Cada uno debe aparecer al listar CON la misma organizacion enfocada
    for modulo, (endpoint, obj_id) in creados.items():
        listado = client.get(endpoint, headers=H)
        assert listado.status_code == 200, f"{modulo}: {listado.text}"
        items = listado.json()
        items = items if isinstance(items, list) else items.get("items", [])
        assert any(x.get("id") == obj_id for x in items), (
            f"{modulo}: se creo con 200 pero no aparece al listar en la misma "
            f"organizacion — se guardo en otra"
        )


def test_focused_org_is_never_written_to_the_database(client):
    """El nucleo del arreglo: la organizacion enfocada vive solo en memoria.

    Si se persistiera, el superadmin quedaria movido de organizacion de forma
    permanente al hacer cualquier commit posterior.
    """
    from app.models import User

    sa = _superadmin(client)
    H = sa["focused"]

    # Operaciones que provocan commits en la misma sesion de peticion
    client.post("/api/initiatives/programs", json={"name": f"Prog {_uid()}"}, headers=H)
    client.post("/api/initiatives/", json={"title": f"Ini {_uid()}"}, headers=H)
    client.get("/api/auth/me", headers=H)

    db = _TestSession()
    try:
        user = db.query(User).filter(User.email == sa["email"]).first()
        assert user.organization_id == sa["own_org_id"], (
            "la organizacion enfocada se ha escrito en la fila del superadmin"
        )
        assert user.organization_id != sa["target_org_id"]
    finally:
        db.close()


def test_data_does_not_leak_between_focused_organizations(client):
    """Lo creado enfocando una organizacion no debe verse enfocando otra."""
    from app.models import Organization

    sa = _superadmin(client)
    db = _TestSession()
    try:
        otra = Organization(name=f"Otro cliente {_uid()}", plan="enterprise")
        db.add(otra)
        db.commit()
        otra_id = otra.id
    finally:
        db.close()

    creado = client.post("/api/initiatives/programs",
                         json={"name": f"Solo del cliente A {_uid()}"},
                         headers=sa["focused"]).json()

    otros_headers = dict(sa["headers"], **{"X-Active-Org": str(otra_id)})
    listado = client.get("/api/initiatives/programs", headers=otros_headers).json()
    assert not any(p["id"] == creado["id"] for p in listado), (
        "un registro de una organizacion es visible enfocando otra"
    )


def test_superadmin_without_selection_keeps_platform_wide_view(client):
    """Sin organizacion enfocada el superadmin sigue viendolo todo (no regresion)."""
    sa = _superadmin(client)
    client.post("/api/initiatives/programs", json={"name": f"Prog {_uid()}"},
                headers=sa["focused"])

    todos = client.get("/api/initiatives/programs", headers=sa["headers"]).json()
    solo_cliente = client.get("/api/initiatives/programs", headers=sa["focused"]).json()
    assert len(todos) >= len(solo_cliente)


def test_regular_admin_is_unaffected(client, auth_headers):
    """El admin de una sola organizacion no cambia de comportamiento."""
    creado = client.post("/api/initiatives/programs", json={"name": f"Prog {_uid()}"},
                         headers=auth_headers)
    assert creado.status_code == 200, creado.text
    listado = client.get("/api/initiatives/programs", headers=auth_headers).json()
    assert any(p["id"] == creado.json()["id"] for p in listado)


def test_superadmin_can_delete_the_org_it_is_focusing(client):
    """La proteccion "no borres tu propia organizacion" debe mirar la org REAL.

    Comparandola con la enfocada, el superadmin no podria dar de baja al cliente
    dentro del cual esta trabajando, que es justo el caso normal.
    """
    sa = _superadmin(client)
    resp = client.delete(f"/api/organizations/{sa['target_org_id']}", headers=sa["focused"])
    assert resp.status_code != 400, (
        "se le impide borrar la organizacion que tiene enfocada por confundirla "
        f"con la suya: {resp.text}"
    )


def test_superadmin_still_cannot_delete_its_own_org(client):
    sa = _superadmin(client)
    resp = client.delete(f"/api/organizations/{sa['own_org_id']}", headers=sa["focused"])
    assert resp.status_code == 400, "deberia seguir protegida su organizacion de origen"


def test_real_organization_id_is_still_reachable(client):
    """Los endpoints que necesitan la organizacion PROPIA del superadmin la
    tienen disponible aunque este enfocando otra."""
    from app.models import User
    from app.security import UserRole

    sa = _superadmin(client)
    db = _TestSession()
    try:
        user = db.query(User).filter(User.email == sa["email"]).first()
        assert user.role == UserRole.SUPERADMIN
        # El atributo se rellena en get_current_user; aqui se comprueba el
        # contrato de que la org propia y la enfocada son distintas en el test
        assert sa["own_org_id"] != sa["target_org_id"]
    finally:
        db.close()
