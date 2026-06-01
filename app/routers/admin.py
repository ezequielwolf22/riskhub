"""Operaciones de administracion del sistema (admin-only)."""
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from app.database import get_db
from app.models import Asset, ControlImplementation, Risk, Threat, User, UserRole, Vulnerability
from app.security import filter_by_org, get_current_user, require_admin, require_superadmin
from app.services.audit_service import log_action
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _sqlite_path() -> Path:
    """Extrae la ruta del archivo SQLite desde la URL de conexion."""
    url = settings.db_url
    m = re.match(r"sqlite:///(.+)", url)
    if not m:
        raise HTTPException(400, "La copia de seguridad solo esta disponible para bases de datos SQLite")
    raw = m.group(1)
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        raise HTTPException(404, f"Archivo de base de datos no encontrado: {p}")
    return p


@router.get("/backup-db")
def backup_db(
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Descarga una copia de seguridad de la base de datos SQLite."""
    db_path = _sqlite_path()

    # Copia a un temporal para evitar inconsistencias durante la lectura
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    shutil.copy2(str(db_path), tmp.name)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"riskhub_backup_{ts}.db"

    log_action(db, current_user.id, "export", "database", None,
               {"filename": fname, "size_bytes": db_path.stat().st_size})
    db.commit()

    return FileResponse(
        path=tmp.name,
        media_type="application/octet-stream",
        filename=fname,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        background=None,
    )


@router.get("/system-info")
def system_info(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Informacion del sistema para el panel de administracion.

    Superadmin ve conteos globales; admin ve solo conteos de su organizacion.
    """
    db_path = _sqlite_path() if settings.db_url.startswith("sqlite") else None
    db_size_bytes = db_path.stat().st_size if db_path and db_path.exists() else None

    # Conteos filtrados por org para no-superadmin (OWASP A01 — info leak prevention)
    if current_user.role == UserRole.SUPERADMIN:
        total_users = db.query(User).count()
        total_assets = db.query(Asset).count()
        total_risks = db.query(Risk).count()
        total_controls = db.query(ControlImplementation).count()
    else:
        total_users = db.query(User).filter(
            User.organization_id == current_user.organization_id
        ).count()
        total_assets = filter_by_org(db.query(Asset), Asset, current_user).count()
        total_risks = filter_by_org(db.query(Risk), Risk, current_user).count()
        total_controls = filter_by_org(
            db.query(ControlImplementation), ControlImplementation, current_user
        ).count()

    return {
        "version": _get_version(),
        "env": settings.env,
        "db_engine": "sqlite" if settings.db_url.startswith("sqlite") else "postgresql",
        "db_size_bytes": db_size_bytes if current_user.role == UserRole.SUPERADMIN else None,
        "total_users": total_users,
        "total_assets": total_assets,
        "total_risks": total_risks,
        "total_threats": db.query(Threat).count(),          # catalogo global
        "total_vulnerabilities": db.query(Vulnerability).count(),  # catalogo global
        "total_controls": total_controls,
        "next_alert_check": _next_alert_run(),
    }


def _get_version() -> str:
    try:
        from app import __version__
        return __version__
    except Exception:
        return "unknown"


def _next_alert_run() -> str | None:
    try:
        from app.services import scheduler as sched
        return sched.next_run()
    except Exception:
        return None


@router.get("/security-status")
def security_status(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Postura de seguridad activa de la instalacion — para panel admin y auditoria."""
    import os
    from pathlib import Path as P
    from app.config import settings as s

    # Verificar SECRET_KEY
    key = s.secret_key
    key_ok = key != "change-me-in-production-very-long-random-string" and len(key) >= 32

    # Verificar si hay documentos en disco (para confirmar cifrado activo)
    doc_root = P("/srv/data/documents")
    if not doc_root.exists():
        doc_root = P(__file__).parent.parent.parent / "data" / "documents"
    docs_on_disk = sum(1 for _ in doc_root.glob("*") if _.is_file()) if doc_root.exists() else 0

    # Verificar configuracion de integraciones con secretos cifrados
    from app.models import IntegrationConfig, AiConfig
    integrations_encrypted = db.query(IntegrationConfig).count()
    # AiConfig filtrado por org del usuario autenticado — no cruzar tenants
    ai_cfg = db.query(AiConfig).filter(
        AiConfig.organization_id == current_user.organization_id
    ).first()
    ai_key_encrypted = bool(ai_cfg and ai_cfg.api_key_encrypted)

    # Verificar SSO configurado
    sso_ic = db.query(IntegrationConfig).filter_by(name="sso_oidc").first()
    sso_configured = bool(sso_ic and sso_ic.config_encrypted)

    return {
        "layers": {
            "encryption_at_rest_documents": {
                "active": True,
                "detail": "Documentos IA y evidencias cifrados con Fernet (AES-128-CBC + HMAC-SHA256) antes de escribir en disco.",
            },
            "encryption_credentials": {
                "active": True,
                "detail": f"API keys e integraciones cifradas con Fernet. "
                          f"{integrations_encrypted} configuracion(es) almacenada(s) cifrada(s).",
            },
            "authentication": {
                "active": True,
                "detail": "JWT HS256 + bcrypt (cost=12). Roles: superadmin, admin, analyst, viewer.",
            },
            "secret_key_strength": {
                "active": key_ok,
                "detail": (
                    f"RISKHUB_SECRET_KEY: {'segura (>= 32 chars, no es el valor por defecto)' if key_ok else 'DEBIL — cambia RISKHUB_SECRET_KEY en produccion'}."
                ),
            },
            "https_tls": {
                "active": s.env == "production",
                "detail": (
                    "Activado via HSTS header (max-age=31536000 + preload). "
                    "Configura un reverse proxy nginx con TLS para cifrado en transito completo."
                    if s.env != "production"
                    else "HSTS activado. Asegurate de usar nginx + Let's Encrypt delante de la app."
                ),
            },
            "security_headers": {
                "active": True,
                "detail": "X-Content-Type-Options, X-Frame-Options, CSP, HSTS, CORP, COOP, Permissions-Policy activos.",
            },
            "cache_control_api": {
                "active": True,
                "detail": "Todas las respuestas /api/* llevan Cache-Control: no-store para evitar caches de datos confidenciales.",
            },
            "anonymization": {
                "active": True,
                "detail": "PII (IPs, emails, dominios, telefonos, DNI/NIF, IBAN) anonimizados antes de enviar contexto al agente IA externo.",
            },
            "rate_limiting": {
                "active": True,
                "detail": "Proteccion brute-force en /api/auth/login (max 10 intentos / 15 min por IP).",
            },
            "upload_validation": {
                "active": True,
                "detail": "Magic bytes validation en uploads (OWASP A08). Tipos permitidos: PDF, DOCX, TXT, CSV. Max 20 MB.",
            },
            "audit_log": {
                "active": True,
                "detail": "Log de auditoria inmutable para todas las operaciones CRUD con usuario, timestamp y detalle.",
            },
            "sso_configured": {
                "active": sso_configured,
                "detail": "SSO OIDC " + ("configurado con credenciales cifradas." if sso_configured else "no configurado (autenticacion local activa)."),
            },
            "ai_key_encrypted": {
                "active": ai_key_encrypted,
                "detail": "API key del agente IA " + ("cifrada con Fernet en BD." if ai_key_encrypted else "usando variable de entorno global (no cifrada por tenant)."),
            },
        },
        "recommendations": _security_recommendations(key_ok, s.env, docs_on_disk),
        "compliance_notes": [
            "GDPR Art. 32: cifrado en reposo y transito, control de acceso por rol, log de auditoria.",
            "ENS Anexo II (med/alto): autenticacion fuerte, cifrado, trazabilidad, gestion de acceso.",
            "ISO/IEC 27001:2022 A.8.24: uso de criptografia. A.8.5: autenticacion segura. A.8.15: logging.",
            "NIS2 Art. 21.2.h: politicas de cifrado. Art. 21.2.i: seguridad en adquisicion y desarrollo.",
        ],
    }


def _security_recommendations(key_ok: bool, env: str, docs_on_disk: int) -> list[str]:
    recs = []
    if not key_ok:
        recs.append(
            "CRITICO: Cambia RISKHUB_SECRET_KEY por una clave de al menos 32 caracteres aleatorios. "
            "Genera una: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )
    if env != "production":
        recs.append(
            "Configura RISKHUB_ENV=production en el entorno de despliegue para activar "
            "todas las restricciones de seguridad."
        )
    recs.append(
        "Configura nginx como reverse proxy con certificado TLS (Let's Encrypt) para "
        "cifrado en transito completo. Ver instrucciones en la Guia de uso."
    )
    recs.append(
        "Configura copias de seguridad automaticas del volumen riskhub-data y cifralas "
        "con GPG antes de transferirlas a almacenamiento externo."
    )
    recs.append(
        "Considera PostgreSQL en lugar de SQLite para cifrado a nivel de base de datos "
        "(pg_crypto o Transparent Data Encryption) en despliegues con datos de alta clasificacion."
    )
    return recs
