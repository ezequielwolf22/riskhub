"""Entrypoint FastAPI - monta routers REST + frontend estatico."""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import settings
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import (
    admin, ai, ai_config, alerts, architecture, asset_groups, assets, audit, audits,
    auth, awareness, catalogues, ccm, compliance, context, controls, cve, documents,
    evidence, executive, external_findings, feature_flags, gdpr, incidents, integrations_erp,
    itsm, magerit, nonconformities, organizations, osint, policies, portal, predictive,
    reports, risks, search, sharepoint, sso, supplier_questionnaires, suppliers,
    tasks, users, webhooks,
)
from app.seed import init_db
from app.services import scheduler as sched

logger = logging.getLogger(__name__)

_WEAK_KEY = "change-me-in-production-very-long-random-string"
_MIN_KEY_LEN = 32

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="RiskHub",
    description="Plataforma de gestion de riesgos - ISO/IEC 27005:2018",
    version=__version__,
    # Deshabilitar documentacion automatica en produccion
    docs_url=None if settings.env == "production" else "/docs",
    redoc_url=None if settings.env == "production" else "/redoc",
    openapi_url=None if settings.env == "production" else "/openapi.json",
)

# Cabeceras de seguridad HTTP — se aplican a todas las respuestas (OWASP A05)
app.add_middleware(SecurityHeadersMiddleware)

# CORS solo en dev; en produccion la app se sirve junto al frontend
if settings.env != "production":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("startup")
def startup():
    # OWASP A02 — verificar la solidez de la clave secreta
    key = settings.secret_key
    is_weak = key == _WEAK_KEY or len(key) < _MIN_KEY_LEN

    if is_weak and settings.env == "production":
        # En produccion, una clave debil es un fallo critico de seguridad:
        # todos los JWT, tokens Fernet y cifrados de documentos dependen de ella.
        import sys
        logger.critical(
            "SEGURIDAD CRITICA: RISKHUB_SECRET_KEY usa el valor por defecto o tiene menos "
            "de %d caracteres. En produccion esto es un fallo de seguridad grave. "
            "Genera una clave segura: python -c \"import secrets; print(secrets.token_urlsafe(64))\" "
            "y configurala como variable de entorno RISKHUB_SECRET_KEY. "
            "El servidor se detiene para proteger los datos del tenant.",
            _MIN_KEY_LEN,
        )
        sys.exit(1)

    if is_weak:
        logger.warning(
            "SEGURIDAD: RISKHUB_SECRET_KEY es debil o usa el valor por defecto. "
            "Genera una clave segura: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )

    init_db()
    sched.start(interval_hours=1)


@app.on_event("shutdown")
def shutdown():
    sched.stop()


@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__, "env": settings.env}


# Routers REST
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(context.router)
app.include_router(assets.router)
app.include_router(asset_groups.router)
app.include_router(catalogues.threats_router)
app.include_router(catalogues.vulns_router)
app.include_router(controls.catalog_router)
app.include_router(controls.impl_router)
app.include_router(risks.router)
app.include_router(reports.router)
app.include_router(alerts.router)
app.include_router(audit.router)
app.include_router(ai.router)
app.include_router(search.router)
app.include_router(incidents.router)
app.include_router(suppliers.router)
app.include_router(nonconformities.router)
app.include_router(tasks.router)
app.include_router(policies.router)
app.include_router(audits.router)
app.include_router(supplier_questionnaires.router)
app.include_router(gdpr.router)
app.include_router(documents.router)
app.include_router(ai_config.router)
app.include_router(feature_flags.router)
app.include_router(sharepoint.router)
app.include_router(sso.router)
app.include_router(cve.router)
app.include_router(osint.router)
app.include_router(awareness.router)
app.include_router(organizations.router)
app.include_router(compliance.router)
app.include_router(evidence.router)
app.include_router(executive.router)
app.include_router(webhooks.router)
app.include_router(external_findings.router)
app.include_router(predictive.router)
app.include_router(architecture.router)
app.include_router(itsm.router)
app.include_router(ccm.router)
app.include_router(portal.router)
app.include_router(magerit.router)
app.include_router(integrations_erp.router)


# Frontend estatico
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets" if (STATIC_DIR / "assets").exists() else STATIC_DIR), name="assets")
    app.mount("/css", StaticFiles(directory=STATIC_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=STATIC_DIR / "js"), name="js")
    if (STATIC_DIR / "img").exists():
        app.mount("/img", StaticFiles(directory=STATIC_DIR / "img"), name="img")
    if (STATIC_DIR / "vendor").exists():
        app.mount("/vendor", StaticFiles(directory=STATIC_DIR / "vendor"), name="vendor")

    _NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html", headers=_NO_CACHE)

    @app.get("/login")
    def login_page():
        return FileResponse(STATIC_DIR / "login.html", headers=_NO_CACHE)

    @app.get("/supplier-q")
    def supplier_questionnaire_page():
        return FileResponse(STATIC_DIR / "supplier-q.html", headers=_NO_CACHE)

    @app.get("/portal/trust/{org_id}/{token}")
    def trust_portal_page(org_id: int, token: str):
        """Página pública del Trust Portal — acceso sin autenticación."""
        return FileResponse(STATIC_DIR / "trust.html")

    @app.get("/portal/auditor/{org_id}/{token}")
    def auditor_portal_page(org_id: int, token: str):
        """Portal de auditor — devuelve JSON para uso programático."""
        return FileResponse(STATIC_DIR / "trust.html")

    # SPA fallback
    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        target = STATIC_DIR / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(STATIC_DIR / "index.html", headers=_NO_CACHE)
