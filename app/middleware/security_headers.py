"""Middleware de cabeceras de seguridad HTTP (OWASP A05).

Cabeceras aplicadas a todas las respuestas:
- X-Content-Type-Options: evita MIME-sniffing
- X-Frame-Options: evita clickjacking
- X-XSS-Protection: proteccion XSS basica (IE/Chrome antiguos)
- Referrer-Policy: controla informacion de referer
- Permissions-Policy: deshabilita APIs del navegador no usadas
- Content-Security-Policy: restringe origenes de recursos (SPA sin CDN)
- Strict-Transport-Security: solo relevante cuando hay TLS (se incluye siempre)
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Evitar MIME-sniffing — critico para uploads
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Anti-clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # XSS filter para navegadores legacy
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # No exponer URL de referencia cross-origin
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Deshabilitar APIs del navegador no utilizadas
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
        )

        # CSP restrictivo: todo desde 'self', sin CDNs
        # 'unsafe-inline' necesario para la SPA Vanilla JS/CSS
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "worker-src 'none'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none';"
        )

        # HSTS: se activa si la app esta detras de TLS (no hace dano en HTTP)
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

        return response
