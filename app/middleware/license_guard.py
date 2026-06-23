"""Middleware que bloquea escrituras cuando la licencia criptografica ha expirado.

Solo actua cuando existe un fichero license.jwt Y ha expirado el periodo de gracia.
Si no hay fichero (modo dev/vendor) o la licencia es valida: sin restriccion.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Rutas que siempre se permiten aunque la licencia haya expirado
_ALWAYS_ALLOWED = {
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/license/status",
    "/api/license/upload",
}


class LicenseGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in _WRITE_METHODS and request.url.path not in _ALWAYS_ALLOWED:
            from app.services.crypto_license import get_state
            state = get_state()
            if state.read_only:
                return JSONResponse(
                    status_code=402,
                    content={
                        "detail": (
                            "Licencia expirada — la aplicacion esta en modo solo lectura. "
                            "Contacta con tu proveedor para renovar la licencia."
                        )
                    },
                )
        return await call_next(request)
