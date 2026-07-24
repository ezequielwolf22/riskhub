"""Seleccion de credenciales de SharePoint — de quien es el token que enviamos.

Las llamadas a Graph son fijas: si la URL y los permisos de Azure no cambian, lo
unico que puede convertir una integracion que funcionaba en un 403 es enviar las
credenciales equivocadas. Esto lo blinda.
"""
from tests.conftest import _TestSession


def _save_sharepoint_config(org_id, tenant_id, client_id):
    from app.models import IntegrationConfig
    from app.services import sharepoint_service as sp

    db = _TestSession()
    try:
        db.add(IntegrationConfig(
            name="sharepoint",
            organization_id=org_id,
            config_encrypted=sp.encrypt_json({
                "tenant_id": tenant_id,
                "client_id": client_id,
                "client_secret": "secreto",
            }),
        ))
        db.commit()
    finally:
        db.close()


def test_config_de_una_org_no_se_sirve_a_otra():
    """El fallo real: org sin config recibia las credenciales de otro cliente.

    Con organization_id None la consulta no filtraba y devolvia la primera fila
    de la tabla. El token se emitia sin error contra el tenant equivocado y Graph
    respondia 403 al pedir un sitio que ese tenant no conoce.
    """
    from app.services import sharepoint_service as sp

    _save_sharepoint_config(901, "tenant-cliente-A", "app-cliente-A")
    db = _TestSession()
    try:
        assert sp.get_config(db, 901)["tenant_id"] == "tenant-cliente-A"
        # Otra organizacion no hereda las credenciales del vecino
        assert sp.get_config(db, 902) is None
        # Ni un usuario sin organizacion (superadmin) se lleva las del primero
        assert sp.get_config(db, None) is None
    finally:
        db.close()


def test_configured_org_ids_localiza_donde_estan_las_credenciales():
    """Permite decir 'estan guardadas en otra org' en vez de 'no configurado'."""
    from app.services import sharepoint_service as sp

    _save_sharepoint_config(903, "tenant-cliente-B", "app-cliente-B")
    db = _TestSession()
    try:
        assert 903 in sp.configured_org_ids(db)
    finally:
        db.close()


def test_describe_token_distingue_consentimiento_perdido():
    """Un token sin claim 'roles' es consentimiento retirado en Entra ID."""
    import jwt

    from app.services import sharepoint_service as sp

    sin_roles = jwt.encode({"tid": "t1", "appid": "a1"}, "k", algorithm="HS256")
    assert sp.describe_token(sin_roles)["roles"] == []

    con_roles = jwt.encode({"tid": "t1", "appid": "a1", "roles": ["Sites.Read.All"]},
                           "k", algorithm="HS256")
    assert sp.describe_token(con_roles)["roles"] == ["Sites.Read.All"]


def test_test_connection_reporta_consentimiento_perdido(client, auth_headers, monkeypatch):
    """403 de Graph con token valido: el informe debe senalar a Entra ID."""
    import jwt

    from app.services import sharepoint_service as sp

    org_id = client.get("/api/auth/me", headers=auth_headers).json()["organization_id"]
    _save_sharepoint_config(org_id, "tenant-real", "app-real")

    token = jwt.encode({"tid": "tenant-real", "appid": "app-real"}, "k", algorithm="HS256")
    monkeypatch.setattr(sp, "get_token", lambda *a, **k: token)
    monkeypatch.setattr(sp, "list_sites", lambda *a, **k: (_ for _ in ()).throw(
        ValueError("Graph API error 403: Access denied [GET /sites]")))

    r = client.post("/api/integrations/sharepoint/test", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert "403" in body["message"]
    assert body["diagnostics"]["config_organization_id"] == org_id
    # Sin ningun rol concedido no es permiso acotado: es consentimiento retirado
    assert "consentimiento de administrador" in body["diagnostics"]["warning"]


def test_sites_selected_no_se_reporta_como_averia(client, auth_headers, monkeypatch):
    """Caso real (2026-07-22): permiso acotado correcto mostrado como "Access denied".

    Con Sites.Selected la busqueda global de sitios responde 403 por diseno de
    Microsoft, pero la integracion funciona entera por URL del sitio. Presentarlo
    como error manda a diagnosticar una averia inexistente.
    """
    import jwt

    from app.services import sharepoint_service as sp

    org_id = client.get("/api/auth/me", headers=auth_headers).json()["organization_id"]
    _save_sharepoint_config(org_id, "tenant-real", "app-real")

    token = jwt.encode({"tid": "tenant-real", "appid": "app-real",
                        "roles": ["Sites.Selected"]}, "k", algorithm="HS256")
    monkeypatch.setattr(sp, "get_token", lambda *a, **k: token)
    monkeypatch.setattr(sp, "list_sites", lambda *a, **k: (_ for _ in ()).throw(
        ValueError("Graph API error 403: Access denied [GET /sites]")))

    r = client.post("/api/integrations/sharepoint/test", headers=auth_headers)
    assert r.json()["ok"] is True
    assert "Sites.Selected" in r.json()["message"]

    # El listado tampoco es un error: la UI recibe la via alternativa
    r = client.get("/api/integrations/sharepoint/sites", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["restricted"] is True
    assert r.json()["reason"] == "sites_selected"


def test_no_configurado_dice_en_que_organizacion_estan_las_credenciales(client, auth_headers):
    """El superadmin enfocando otra org debe saber por que no las encuentra."""
    from app.models import IntegrationConfig

    db = _TestSession()
    try:
        db.query(IntegrationConfig).filter(IntegrationConfig.name == "sharepoint").delete()
        db.commit()
    finally:
        db.close()
    _save_sharepoint_config(904, "tenant-otro", "app-otro")

    r = client.post("/api/integrations/sharepoint/test", headers=auth_headers)
    assert r.status_code == 400
    assert "904" in r.json()["detail"]


def test_error_de_graph_dice_que_endpoint_fallo():
    """Un 403 sin endpoint no se puede diagnosticar: /sites exige permiso global,
    /sites/{host}:{ruta} y /drives funcionan con Sites.Selected."""
    from app.services import sharepoint_service as sp

    assert sp._endpoint_of("https://graph.microsoft.com/v1.0/sites?search=*") == "/sites"
    assert sp._endpoint_of("https://graph.microsoft.com/v1.0/drives/d1/items/i1/children") \
        == "/drives/d1/items/i1/children"
