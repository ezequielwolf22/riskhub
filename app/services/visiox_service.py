"""Cliente HTTP de la API de servicio de VisioX (Digital Risk Protection).

VisioX expone /api/v1/svc/* autenticado con una service key emitida en su lado.
La key esta atada a UN cliente de VisioX: el `client_id` no viaja en la peticion,
lo impone el servidor a partir de la key. Aqui no se puede elegir tenant, y es
deliberado.

Solo lectura. Sin dependencias nuevas: urllib de la biblioteca estandar, igual
que cve_service.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Base fija en codigo, no configurable por el tenant: el certificado valido lo
# sirve Cloudflare para visiox.app. Apuntar a la IP del origen daria error de
# certificado (Caddy usa tls internal), y dejar que un tenant elija destino
# convertiria la integracion en un SSRF con credenciales.
DEFAULT_BASE_URL = "https://visiox.app"

API_KEY_HEADER = "X-VisioX-Key"

# El router de VisioX tiene un timeout global de 60s. Se corta antes para no
# quedarse colgado ocupando un hilo del pool de uvicorn.
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 45

# Tope de paginas por ejecucion. Con limit=1000 cubre 40.000 hallazgos, muy por
# encima del corpus real; existe para que un bug de cursor no haga un bucle
# infinito. Si se alcanza, el snapshot se marca INCOMPLETO y no se cierra nada.
MAX_PAGES = 40

PAGE_SIZE = 1000


class VisioXError(Exception):
    """Fallo al hablar con VisioX. Lleva el codigo HTTP cuando lo hay."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def _request(base_url: str, api_key: str, path: str, params: Optional[dict] = None) -> dict:
    """GET autenticado contra VisioX. Devuelve el JSON o lanza VisioXError."""
    url = base_url.rstrip("/") + path
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)

    req = urllib.request.Request(url, method="GET")
    # La key va en cabecera, nunca en query string: el logger de VisioX escribe
    # la query completa al journal de systemd.
    req.add_header(API_KEY_HEADER, api_key)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "RiskHub-VisioX-Connector/1.0")

    try:
        with urllib.request.urlopen(req, timeout=READ_TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        if exc.code == 401:
            raise VisioXError("La API key de VisioX no es valida o ha sido revocada", 401)
        if exc.code == 403:
            raise VisioXError("La API key no tiene permiso para esta operacion", 403)
        raise VisioXError(f"VisioX devolvio HTTP {exc.code}: {detail}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise VisioXError(f"No se pudo conectar con VisioX: {exc.reason}") from exc
    except TimeoutError as exc:
        raise VisioXError("Tiempo de espera agotado hablando con VisioX") from exc

    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise VisioXError("VisioX devolvio una respuesta que no es JSON valido") from exc


def whoami(base_url: str, api_key: str) -> dict:
    """Verifica la key y devuelve a que cliente de VisioX resuelve.

    Es lo que consume el boton de probar conexion: no basta con un 200, quien
    configura la integracion tiene que ver en pantalla el nombre del cliente
    antes de fiarse de los datos que va a importar.
    """
    return _request(base_url, api_key, "/api/v1/svc/whoami")


def summary(base_url: str, api_key: str) -> dict:
    """KPIs agregados por modulo, ya calculados en VisioX."""
    return _request(base_url, api_key, "/api/v1/svc/summary")


def fetch_findings(
    base_url: str,
    api_key: str,
    modules: Optional[list[str]] = None,
    page_size: int = PAGE_SIZE,
) -> tuple[list[dict], bool, int]:
    """Recorre el snapshot completo de hallazgos.

    Devuelve (items, complete, pages). `complete` solo es True si se llego al
    final del recorrido: el consumidor NO debe cerrar hallazgos ausentes si es
    False, porque la ausencia no probaria que se resolvieron.
    """
    items: list[dict] = []
    cursor = ""
    pages = 0
    seen_cursors: set[str] = set()

    while True:
        params: dict[str, Any] = {"limit": page_size}
        if modules:
            params["modules"] = ",".join(modules)
        if cursor:
            params["cursor"] = cursor

        payload = _request(base_url, api_key, "/api/v1/svc/findings", params)
        pages += 1

        batch = payload.get("data") or []
        items.extend(batch)

        cursor = payload.get("next_cursor") or ""
        if not cursor:
            return items, bool(payload.get("complete")), pages

        # Un cursor repetido significa que el servidor no avanza. Cortar aqui
        # evita el bucle infinito y, sobre todo, evita marcar como completo un
        # snapshot que no lo es.
        if cursor in seen_cursors:
            logger.warning("VisioX devolvio un cursor repetido; se corta el recorrido")
            return items, False, pages
        seen_cursors.add(cursor)

        if pages >= MAX_PAGES:
            logger.warning(
                "VisioX: alcanzado el tope de %d paginas con %d items; "
                "el snapshot queda incompleto y no se cerrara nada",
                MAX_PAGES, len(items),
            )
            return items, False, pages

        # Cortesia con el origen: es un VPS de 2 vCPU compartido con los workers.
        time.sleep(0.1)
