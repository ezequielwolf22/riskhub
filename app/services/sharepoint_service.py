"""Servicio de integracion con Microsoft SharePoint via Graph API.

Usa el flujo OAuth2 client_credentials (app-only) para autenticacion.
Requiere un Azure AD App Registration con permisos:
  - Sites.Read.All (Application)
  - Files.Read.All (Application)
"""
import base64
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional


_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}   # key -> (token, expires_at monotonic)
_INTEGRATION_NAME = "sharepoint"


def get_token(tenant_id: str, client_id: str, client_secret: str,
              org_id: int | None = None) -> str:
    """Obtiene un access token usando client_credentials. Cachea por 55 minutos.

    A4: org_id incluido en la clave de cache para evitar que dos orgs con el mismo
    tenant/client_id compartan el mismo token en memoria.
    """
    import time
    cache_key = f"{org_id}:{tenant_id}:{client_id}"
    if cache_key in _TOKEN_CACHE:
        token, exp = _TOKEN_CACHE[cache_key]
        if time.monotonic() < exp:
            return token

    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        raise ValueError(f"Error al obtener token: {err.get('error_description', str(e))}")

    token = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    import time as t
    _TOKEN_CACHE[cache_key] = (token, t.monotonic() + min(expires_in - 60, 3300))
    return token


def _endpoint_of(url: str) -> str:
    """Ruta relativa de Graph, sin querystring. Para mensajes de error legibles."""
    path = urllib.parse.urlparse(url).path
    return path[len("/v1.0"):] if path.startswith("/v1.0") else path


def _graph_get_url(token: str, url: str) -> dict:
    """Hace un GET a una URL absoluta de Graph (usado para paginacion/delta) y devuelve el JSON."""
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            err = json.loads(body)
            msg = err.get("error", {}).get("message", str(e))
        except Exception:
            msg = str(e)
        # El endpoint concreto importa: /sites (busqueda global) exige permiso de
        # todo el tenant, mientras que /sites/{host}:{ruta} y /drives funcionan con
        # Sites.Selected. Sin saber cual fallo, un 403 no se puede diagnosticar.
        raise ValueError(f"Graph API error {e.code}: {msg} [GET {_endpoint_of(url)}]")


def describe_token(token: str) -> dict:
    """Descompone el access token (sin verificar firma) para diagnostico.

    Graph responde 403 "Access denied" tanto si la aplicacion no tiene el rol
    concedido como si el token es de otro tenant. El claim `roles` distingue los
    dos casos sin necesidad de entrar en Azure.
    """
    try:
        import jwt as _jwt
        claims = _jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return {}
    return {
        "token_tenant_id": claims.get("tid"),
        "token_app_id": claims.get("appid") or claims.get("azp"),
        "token_app_name": claims.get("app_displayname"),
        "roles": claims.get("roles") or [],
    }


def _graph_get(token: str, path: str, params: Optional[dict] = None) -> dict:
    """Hace un GET a la Graph API y devuelve el JSON parseado."""
    url = f"{_GRAPH_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return _graph_get_url(token, url)


def resolve_site(token: str, site_url: str) -> dict:
    """Resuelve un sitio de SharePoint a partir de su URL completa.

    Necesario cuando el permiso de la app esta restringido a un sitio concreto
    (Sites.Selected): en ese caso /sites?search= devuelve 403 porque requiere
    acceso de busqueda a nivel de todo el tenant, pero el direccionamiento
    /sites/{hostname}:{ruta} si funciona porque apunta a un sitio ya autorizado.
    """
    url = site_url.strip()
    if "://" not in url:
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.netloc
    path = parsed.path.rstrip("/")
    if not hostname:
        raise ValueError("URL de sitio no valida")
    graph_path = f"/sites/{hostname}:{path}" if path else f"/sites/{hostname}"
    data = _graph_get(token, graph_path, {"$select": "id,displayName,webUrl,name"})
    return {
        "id": data["id"],
        "name": data.get("displayName") or data.get("name") or data["id"],
        "url": data.get("webUrl", ""),
    }


def list_sites(token: str, search: str = "*") -> list[dict]:
    """Lista los sitios de SharePoint accesibles."""
    data = _graph_get(token, "/sites", {"search": search, "$select": "id,displayName,webUrl,name"})
    return [
        {
            "id": s["id"],
            "name": s.get("displayName") or s.get("name") or s["id"],
            "url": s.get("webUrl", ""),
        }
        for s in data.get("value", [])
    ]


def list_drives(token: str, site_id: str) -> list[dict]:
    """Lista las bibliotecas de documentos de un sitio."""
    data = _graph_get(token, f"/sites/{site_id}/drives",
                      {"$select": "id,name,driveType,webUrl"})
    return [
        {
            "id": d["id"],
            "name": d.get("name", d["id"]),
            "type": d.get("driveType", ""),
            "url": d.get("webUrl", ""),
        }
        for d in data.get("value", [])
        if d.get("driveType") == "documentLibrary"
    ]


def list_children(token: str, drive_id: str, item_id: str = "root") -> list[dict]:
    """Lista el contenido (archivos y carpetas) de un directorio."""
    path = f"/drives/{drive_id}/items/{item_id}/children"
    data = _graph_get(token, path, {
        "$select": "id,name,size,file,folder,webUrl,lastModifiedDateTime",
        "$top": "200",
    })
    items = []
    for it in data.get("value", []):
        kind = "folder" if "folder" in it else "file"
        mime = it.get("file", {}).get("mimeType", "") if kind == "file" else ""
        items.append({
            "id": it["id"],
            "name": it["name"],
            "kind": kind,
            "size": it.get("size", 0),
            "mime": mime,
            "url": it.get("webUrl", ""),
            "modified": it.get("lastModifiedDateTime", ""),
            "child_count": it.get("folder", {}).get("childCount", 0) if kind == "folder" else 0,
        })
    return items


def download_file(token: str, drive_id: str, item_id: str) -> bytes:
    """Descarga el contenido de un archivo de SharePoint."""
    url = f"{_GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise ValueError(f"Error al descargar archivo: {e.code} {e.reason}")


# Tipos MIME soportados para importar en el RAG
_IMPORTABLE_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/csv",
}

_EXT_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".csv": "text/plain",
}


def is_importable(filename: str, mime: str) -> bool:
    """Devuelve True si el archivo puede importarse como documento RAG."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    inferred = _EXT_MIME.get(ext, mime)
    return inferred in _IMPORTABLE_MIME or any(k in mime for k in ("pdf", "wordprocessingml", "plain", "csv"))


# ---------- Deteccion de cambios (delta query) ----------

def delta_scan(token: str, drive_id: str, item_id: str,
                delta_link: Optional[str] = None) -> tuple[list[dict], Optional[str]]:
    """Escanea cambios (nuevos/modificados/eliminados) bajo un item usando delta query de Graph.

    Si delta_link es None hace un escaneo inicial completo del arbol bajo item_id.
    Si se pasa un delta_link (guardado de una llamada anterior), Graph devuelve solo
    los cambios desde entonces. Devuelve (items, next_delta_link) — next_delta_link
    debe guardarse para la siguiente sincronizacion incremental.
    """
    url = delta_link or (
        f"{_GRAPH_BASE}/drives/{drive_id}/items/{item_id}/delta"
        "?$select=id,name,size,file,folder,deleted,parentReference,lastModifiedDateTime"
    )
    items: list[dict] = []
    next_delta_link = delta_link
    while True:
        data = _graph_get_url(token, url)
        for it in data.get("value", []):
            is_deleted = "deleted" in it
            if "folder" in it and not is_deleted:
                continue   # las carpetas no se importan, solo archivos
            mime = it.get("file", {}).get("mimeType", "") if not is_deleted else ""
            items.append({
                "id": it["id"],
                "name": it.get("name", ""),
                "deleted": is_deleted,
                "size": it.get("size", 0),
                "mime": mime,
                "modified": it.get("lastModifiedDateTime", ""),
            })
        if "@odata.nextLink" in data:
            url = data["@odata.nextLink"]
            continue
        next_delta_link = data.get("@odata.deltaLink", next_delta_link)
        break
    return items, next_delta_link


def get_item_parent_chain(token: str, drive_id: str, item_id: str, max_depth: int = 20) -> list[str]:
    """Devuelve la cadena de IDs ancestros del item, desde el propio item hasta la raiz."""
    chain = []
    current_id = item_id
    for _ in range(max_depth):
        chain.append(current_id)
        try:
            data = _graph_get(token, f"/drives/{drive_id}/items/{current_id}",
                              {"$select": "id,parentReference"})
        except ValueError:
            break
        parent_id = (data.get("parentReference") or {}).get("id")
        if not parent_id or parent_id == current_id:
            break
        current_id = parent_id
    return chain


def item_is_allowed(token: str, allowed_folders: list[dict], drive_id: str, item_id: str) -> bool:
    """Comprueba si un item esta dentro de alguna de las carpetas permitidas.

    Si no hay carpetas configuradas se permite todo (compatibilidad con instalaciones
    que aun no han configurado el allowlist). "root" es un alias especial que permite
    toda la biblioteca (no aparece en la cadena de ancestros real de Graph).
    """
    if not allowed_folders:
        return True
    allowed_ids = {f["item_id"] for f in allowed_folders if f.get("drive_id") == drive_id}
    if not allowed_ids:
        return False
    if "root" in allowed_ids or item_id in allowed_ids:
        return True
    chain = get_item_parent_chain(token, drive_id, item_id)
    return any(cid in allowed_ids for cid in chain)


# ---------- Configuracion cifrada (compartida entre router y scheduler) ----------

def _fernet_key() -> bytes:
    from app.config import settings
    return base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())


def encrypt_json(data: dict) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_fernet_key()).encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str) -> dict:
    from cryptography.fernet import Fernet
    return json.loads(Fernet(_fernet_key()).decrypt(token.encode()).decode())


def configured_org_ids(db) -> list:
    """Organizaciones que tienen credenciales de SharePoint guardadas."""
    from app.models import IntegrationConfig
    return [
        ic.organization_id
        for ic in db.query(IntegrationConfig).filter(
            IntegrationConfig.name == _INTEGRATION_NAME).all()
        if ic.config_encrypted
    ]


def get_config(db, organization_id: int | None = None) -> Optional[dict]:
    """Devuelve la configuracion de SharePoint descifrada, o None si no existe.

    El filtro por organizacion es SIEMPRE estricto. Antes, con organization_id
    None (superadmin sin organizacion propia), la consulta no filtraba y devolvia
    la primera fila de la tabla: las credenciales de Azure de OTRO cliente. El
    token se obtenia sin error y Graph respondia 403 al pedir un sitio que ese
    tenant no conoce, con toda la pinta de ser un problema de permisos ajeno.
    """
    from app.models import IntegrationConfig
    ic = db.query(IntegrationConfig).filter(
        IntegrationConfig.name == _INTEGRATION_NAME,
        IntegrationConfig.organization_id == organization_id,
    ).first()
    if not ic or not ic.config_encrypted:
        return None
    try:
        return decrypt_json(ic.config_encrypted)
    except Exception:
        return None


def update_config(db, organization_id: int | None, updated_by_id: int | None, **fields) -> dict:
    """Actualiza (merge) campos sueltos de la config existente y la persiste cifrada."""
    from app.models import IntegrationConfig
    ic = db.query(IntegrationConfig).filter(
        IntegrationConfig.name == _INTEGRATION_NAME,
        IntegrationConfig.organization_id == organization_id,
    ).first()
    if not ic or not ic.config_encrypted:
        raise ValueError("SharePoint no configurado")
    cfg = decrypt_json(ic.config_encrypted)
    cfg.update(fields)
    ic.config_encrypted = encrypt_json(cfg)
    ic.updated_at = datetime.now(timezone.utc)
    ic.updated_by_id = updated_by_id
    db.commit()
    return cfg


def list_configured_organizations(db) -> list[int]:
    """Devuelve los organization_id con sincronizacion de SharePoint activada."""
    from app.models import IntegrationConfig
    org_ids = []
    for ic in db.query(IntegrationConfig).filter(IntegrationConfig.name == _INTEGRATION_NAME).all():
        if not ic.config_encrypted or ic.organization_id is None:
            continue
        try:
            cfg = decrypt_json(ic.config_encrypted)
        except Exception:
            continue
        if cfg.get("sync_enabled") and cfg.get("allowed_folders"):
            org_ids.append(ic.organization_id)
    return org_ids
