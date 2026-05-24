"""Entrypoint FastAPI - monta routers REST + frontend estatico."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import settings
from app.routers import (
    admin, ai, alerts, assets, audit, auth, catalogues, context, controls,
    reports, risks, search, users,
)
from app.seed import init_db
from app.services import scheduler as sched

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="RiskHub",
    description="Plataforma de gestion de riesgos - ISO/IEC 27005:2018",
    version=__version__,
)

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

    # SPA fallback
    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        target = STATIC_DIR / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(STATIC_DIR / "index.html", headers=_NO_CACHE)
