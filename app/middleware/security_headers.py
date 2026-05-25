"""Middleware de cabeceras de seguridad HTTP (OWASP A05).

Cabeceras aplicadas a todas las respuestas:
- X-Content-Type-Options: evita MIME-sniffing
- X-Frame-Options: evita clickjacking
- X-XSS-Protection: proteccion XSS basica (IE/Chrome antiguos)
- Referrer-Policy: controla informacion de referer
- Permissions-Policy: deshabilita APIs del navegador no usadas
- Content-Security-Policy: restringe origenes de recursos (SPA sin CDN)
- Strict-Transport-Security: solo relevante cuando hay TLS (se incluye siempre)
- Cache-Control: no-store para endpoints /api/* (datos confidenciales)
- X-Permitted-Cross-Domain-Policies: bloquea Adobe Flash/PDF cross-domain
- Cross-Origin-Opener-Policy: aislamiento de origen para proteger de XS-Leaks
- Cross-Origin-Resource-Policy: bloquea carga cross-origin de recursos internos
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
            "geolocation=(), microphone=(), camera=(), payment=(), usb=(), "
            "interest-cohort=()"
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
            "max-age=31536000; includeSubDomains; preload"
        )

        # Bloquear carga cross-domain de recursos internos (Adobe Flash / PDF legacy)
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        # COOP y CORP solo son validos sobre HTTPS o localhost.
        # En HTTP el navegador las ignora y emite un warning en consola.
        is_secure = (
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto") == "https"
            or request.url.hostname in ("localhost", "127.0.0.1")
        )
        if is_secure:
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
            response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

        # Cache-Control: los endpoints de API devuelven datos confidenciales;
        # no deben ser almacenados en cache del navegador, proxies ni CDNs.
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response
