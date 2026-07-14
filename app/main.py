"""Entrypoint FastAPI - monta routers REST + frontend estatico."""
import logging
from pathlib import Path

from fastapi import Depends, FastAPI

from app.security import require_role
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from app import __version__
from app.config import settings
from app.logging_config import setup_logging
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.license_guard import LicenseGuardMiddleware

setup_logging(env=settings.env)

from app.routers import bootstrap as bootstrap_router
from app.routers import (
    admin, ai, ai_config, alerts, architecture, asset_groups, assets, audit, audits,
    auth, awareness, bcp, catalogues, ccm, change_requests, compliance, context, controls,
    cve, documents, evidence, executive, external_findings, feature_flags, gdpr, inbox, incidents, jobs,
    integrations_erp, integrations_forms, integrations_virustotal, itsm, licenses, management_review, magerit, nis2, nonconformities, onboarding_gate, organizations,
    osint, policies, portal, predictive, questionnaire_flows, questionnaire_schedules, regwatch, report_schedules,
    report_templates, reports, risk_level_config, risks, search, sharepoint,
    soa_versions, sso, supplier_questionnaires, suppliers, surveys, tasks, tprm,
    vendor_assessments, vendor_issues, users, webhooks,
)
from app.routers import kris, risk_correlations
from app.routers.audit_log import router as audit_log_router
from app.routers.surveys import public_router as survey_public_router
from app.routers.policy_approvals import router as policy_approvals_router, public_router as approvals_public_router
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
# Bloqueo de escrituras cuando la licencia criptografica ha expirado
app.add_middleware(LicenseGuardMiddleware)

# ---------- Observabilidad: request-id, access log, contadores y errores ----------

# Contadores en memoria para /metrics (se resetean al reiniciar)
_METRICS = {"requests_total": {}, "errors_total": 0, "started_at": None}


@app.middleware("http")
async def observability_middleware(request, call_next):
    import time as _time
    import uuid as _uuid

    request_id = request.headers.get("x-request-id") or _uuid.uuid4().hex[:16]

    # Rate limiting global por IP (solo API; health exento para monitores)
    req_path = request.url.path
    if req_path.startswith("/api") and req_path != "/api/health":
        from app.services.rate_limiter import check_api_rate
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_s = check_api_rate(client_ip)
        if not allowed:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={"detail": "Demasiadas peticiones. Intentalo de nuevo en unos segundos."},
                headers={"Retry-After": str(retry_s), "X-Request-ID": request_id},
            )

    t0 = _time.monotonic()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((_time.monotonic() - t0) * 1000)
        _METRICS["errors_total"] += 1
        logger.exception(
            "request_id=%s %s %s -> 500 (%dms): %s",
            request_id, request.method, request.url.path, duration_ms, exc,
        )
        # Persistir el error (best-effort, sesion propia) para la vista admin
        try:
            from app.database import SessionLocal
            from app.models import AppError
            _db = SessionLocal()
            try:
                _db.add(AppError(
                    request_id=request_id,
                    method=request.method,
                    path=str(request.url.path)[:512],
                    error_type=type(exc).__name__[:128],
                    error=str(exc)[:2000],
                ))
                _db.commit()
            finally:
                _db.close()
        except Exception:
            pass
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno. Referencia: " + request_id},
            headers={"X-Request-ID": request_id},
        )

    duration_ms = round((_time.monotonic() - t0) * 1000)
    status_class = f"{response.status_code // 100}xx"
    _METRICS["requests_total"][status_class] = _METRICS["requests_total"].get(status_class, 0) + 1
    response.headers["X-Request-ID"] = request_id
    # Access log solo para la API (el estatico y el health check son ruido)
    path = request.url.path
    if path.startswith("/api") and path != "/api/health":
        logger.info("request_id=%s %s %s -> %d (%dms)",
                    request_id, request.method, path, response.status_code, duration_ms)
    return response

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
    _reset_stuck_analyses()

    # Cola de trabajos asincrona (recovery de jobs interrumpidos + workers)
    from app.services import job_queue
    job_queue.start()

    # Validar licencia criptografica (on-premise)
    from app.services import crypto_license as _lic
    _lic.load_and_validate()


@app.on_event("shutdown")
def shutdown():
    sched.stop()


def _reset_stuck_analyses() -> None:
    """En cada arranque, resetea activos atascados en 'analysing' (proceso interrumpido).
    Esto permite que el siguiente 'Analizar riesgos con IA' los recoja automaticamente."""
    try:
        from app.database import SessionLocal
        from app.models import Asset
        db = SessionLocal()
        try:
            n = db.query(Asset).filter(Asset.ai_risk_status == "analysing").update(
                {"ai_risk_status": None, "ai_risk_summary": None}
            )
            if n:
                db.commit()
                logger.info("Startup: reset %d activos atascados en 'analysing' → null", n)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("No se pudo resetear analyses en startup: %s", exc)


@app.get("/api/metrics")
def metrics(current_user=Depends(require_role("admin"))):
    """Metricas en formato texto plano Prometheus (requiere admin).

    Contadores de proceso (se resetean al reiniciar) + estado de la cola de
    trabajos y errores persistidos, leidos de BD.
    """
    from fastapi.responses import PlainTextResponse
    from app.database import SessionLocal
    from app.models import AppError, BackgroundJob

    lines = [
        "# TYPE riskhub_requests_total counter",
    ]
    for status_class, n in sorted(_METRICS["requests_total"].items()):
        lines.append(f'riskhub_requests_total{{status="{status_class}"}} {n}')
    lines.append("# TYPE riskhub_unhandled_errors_total counter")
    lines.append(f"riskhub_unhandled_errors_total {_METRICS['errors_total']}")

    db = SessionLocal()
    try:
        from sqlalchemy import func as _func
        lines.append("# TYPE riskhub_jobs gauge")
        for status, n in db.query(BackgroundJob.status, _func.count()).group_by(
                BackgroundJob.status).all():
            lines.append(f'riskhub_jobs{{status="{status}"}} {n}')
        lines.append("# TYPE riskhub_app_errors_total counter")
        lines.append(f"riskhub_app_errors_total {db.query(AppError).count()}")
    finally:
        db.close()

    return PlainTextResponse("\n".join(lines) + "\n")


@app.get("/api/health")
def health():
    """Health check con verificacion de BD. Usado por deploy.sh y monitoreo externo."""
    import time
    from app.database import engine
    from sqlalchemy import text

    db_ok = False
    db_latency_ms = None
    try:
        t0 = time.monotonic()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_latency_ms = round((time.monotonic() - t0) * 1000, 1)
        db_ok = True
    except Exception as exc:
        logger.error("Health check: DB no disponible — %s", exc)

    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "env": settings.env,
        "db_ok": db_ok,
        "db_latency_ms": db_latency_ms,
    }


# Routers REST
app.include_router(bootstrap_router.router)
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
app.include_router(risk_level_config.router)
app.include_router(risks.router)
app.include_router(reports.router)
app.include_router(alerts.router)
app.include_router(audit.router)
app.include_router(ai.router)
app.include_router(search.router)
app.include_router(incidents.router)
app.include_router(suppliers.router)
app.include_router(onboarding_gate.router)
app.include_router(tprm.router)
app.include_router(vendor_assessments.router)
app.include_router(vendor_issues.router)
app.include_router(kris.router)
app.include_router(risk_correlations.router)
app.include_router(nonconformities.router)
app.include_router(tasks.router)
app.include_router(policies.router)
app.include_router(audits.router)
app.include_router(supplier_questionnaires.router)
app.include_router(questionnaire_schedules.router)
app.include_router(questionnaire_flows.router)
app.include_router(integrations_forms.router)
app.include_router(gdpr.router)
app.include_router(documents.router)
app.include_router(ai_config.router)
app.include_router(feature_flags.router)
app.include_router(jobs.router)
app.include_router(sharepoint.router)
app.include_router(sso.router)
app.include_router(cve.router)
app.include_router(osint.router)
app.include_router(awareness.router)
app.include_router(organizations.router)
app.include_router(licenses.router)
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
app.include_router(integrations_virustotal.router)
app.include_router(management_review.router)
app.include_router(soa_versions.router)
app.include_router(nis2.router)
app.include_router(inbox.router)
app.include_router(change_requests.router)
app.include_router(report_schedules.router)
app.include_router(report_templates.router)
app.include_router(bcp.router)
app.include_router(regwatch.router)
from app.routers import license_crypto
app.include_router(license_crypto.router)
app.include_router(surveys.router)
app.include_router(survey_public_router)
app.include_router(policy_approvals_router)
app.include_router(approvals_public_router)
app.include_router(audit_log_router)


class VersionedStaticFiles(StaticFiles):
    """StaticFiles con cache larga para assets versionados (?v=X.X.X en index.html).

    JS/CSS/img se sirven con max-age=1 año + immutable: el navegador no hace
    ninguna peticion al servidor en cargas posteriores hasta que cambie la URL.
    Para actualizar basta con subir el numero de version en el ?v= de index.html.
    """

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif response.status_code == 304:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


# Frontend estatico
if STATIC_DIR.exists():
    app.mount("/assets", VersionedStaticFiles(directory=STATIC_DIR / "assets" if (STATIC_DIR / "assets").exists() else STATIC_DIR), name="assets")
    app.mount("/css", VersionedStaticFiles(directory=STATIC_DIR / "css"), name="css")
    app.mount("/js", VersionedStaticFiles(directory=STATIC_DIR / "js"), name="js")
    if (STATIC_DIR / "img").exists():
        app.mount("/img", VersionedStaticFiles(directory=STATIC_DIR / "img"), name="img")
    if (STATIC_DIR / "vendor").exists():
        app.mount("/vendor", VersionedStaticFiles(directory=STATIC_DIR / "vendor"), name="vendor")

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
        # Path traversal guard: resolver el destino y exigir que quede DENTRO de
        # STATIC_DIR. Sin esto, rutas como /../../../root/.ssh/id_ed25519 salen
        # del arbol estatico y filtrarian cualquier fichero legible por la app
        # (BD SQLite, codigo, secretos). Ante duda -> SPA index.
        static_root = STATIC_DIR.resolve()
        try:
            target = (static_root / full_path).resolve()
            if target.is_file() and target.is_relative_to(static_root):
                return FileResponse(target)
        except (OSError, ValueError):
            pass
        return FileResponse(STATIC_DIR / "index.html", headers=_NO_CACHE)
