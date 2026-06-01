"""Servicio de integracion con Microsoft SharePoint via Graph API.

Usa el flujo OAuth2 client_credentials (app-only) para autenticacion.
Requiere un Azure AD App Registration con permisos:
  - Sites.Read.All (Application)
  - Files.Read.All (Application)
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional


_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}   # key -> (token, expires_at monotonic)


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


def _graph_get(token: str, path: str, params: Optional[dict] = None) -> dict:
    """Hace un GET a la Graph API y devuelve el JSON parseado."""
    url = f"{_GRAPH_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
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
        raise ValueError(f"Graph API error {e.code}: {msg}")


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
