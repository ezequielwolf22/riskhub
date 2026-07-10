"""Operaciones de administracion del sistema (admin-only)."""
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.i18n import get_lang, t as _t

from app.config import settings
from app.database import get_db
from app.models import Asset, ControlImplementation, Risk, Threat, User, UserRole, Vulnerability
from app.security import filter_by_org, get_current_user, require_admin, require_superadmin
from app.services.audit_service import log_action
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/errors")
def list_app_errors(
    limit: int = 50,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Errores no controlados capturados por el middleware (observabilidad).

    Cada entrada lleva el request_id que el cliente recibio en la respuesta
    500, para correlacionar tickets de soporte con el error real.
    """
    from app.models import AppError
    rows = (
        db.query(AppError)
        .order_by(AppError.id.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "id": e.id,
            "request_id": e.request_id,
            "method": e.method,
            "path": e.path,
            "error_type": e.error_type,
            "error": (e.error or "")[:500],
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]


@router.delete("/errors")
def clear_app_errors(
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Vacia el registro de errores (tras revisarlos)."""
    from app.models import AppError
    n = db.query(AppError).delete(synchronize_session=False)
    db.commit()
    log_action(db, current_user.id, "clear", "app_errors", None, {"deleted": n})
    return {"deleted": n}


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


@router.post("/risks/cleanup-vulnerabilities")
def cleanup_risk_vulnerabilities(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Limpieza masiva: reemplaza las vulnerabilidades de cada riesgo por las
    que corresponden a su amenaza segun el catalogo ISO 27005 (related_threats).

    Solo corrige vulnerabilidades; no toca controles para no alterar decisiones
    de tratamiento ya aprobadas.

    Devuelve estadisticas detalladas por riesgo.
    """
    import json as _json
    import traceback

    try:
        return _do_cleanup_risk_vulnerabilities(db, current_user, _json)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Error interno: {type(exc).__name__}: {exc}\n{traceback.format_exc()}") from exc


def _do_cleanup_risk_vulnerabilities(db, current_user, _json):
    org_id = current_user.organization_id  # superadmin limpia su org activa

    q = db.query(Risk)
    if current_user.role != UserRole.SUPERADMIN:
        q = q.filter(Risk.organization_id == org_id)
    risks = q.all()
    all_vulns = db.query(Vulnerability).all()

    # Indice: threat_code → lista de Vulnerability
    vuln_index: dict[str, list] = {}
    for v in all_vulns:
        rt = v.related_threats or []
        if isinstance(rt, str):
            try:
                rt = _json.loads(rt)
            except Exception:
                rt = [rt]
        for code in rt:
            vuln_index.setdefault(code, []).append(v)

    stats = {
        "checked": 0,
        "fixed": 0,
        "already_correct": 0,
        "no_catalog_match": 0,
        "details": [],
    }

    for risk in risks:
        stats["checked"] += 1
        threat = db.get(Threat, risk.threat_id) if risk.threat_id else None
        if not threat or not threat.code:
            stats["details"].append({
                "risk_code": risk.code,
                "action": "skipped",
                "reason": "sin amenaza asignada",
            })
            continue

        correct_vulns = vuln_index.get(threat.code, [])
        current_ids = {v.id for v in (risk.vulnerabilities or [])}
        correct_ids = {v.id for v in correct_vulns}

        if not correct_vulns:
            stats["no_catalog_match"] += 1
            stats["details"].append({
                "risk_code": risk.code,
                "threat_code": threat.code,
                "action": "skipped",
                "reason": "amenaza sin vulnerabilidades en catalogo",
            })
            continue

        if current_ids == correct_ids:
            stats["already_correct"] += 1
            stats["details"].append({
                "risk_code": risk.code,
                "threat_code": threat.code,
                "action": "ok",
                "vuln_count": len(correct_ids),
            })
            continue

        removed = [v.code for v in (risk.vulnerabilities or []) if v.id not in correct_ids]
        added = [v.code for v in correct_vulns if v.id not in current_ids]

        risk.vulnerabilities = correct_vulns
        stats["fixed"] += 1
        stats["details"].append({
            "risk_code": risk.code,
            "threat_code": threat.code,
            "action": "fixed",
            "removed": removed,
            "added": added,
        })

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Error al guardar cambios: {exc}") from exc

    try:
        log_action(db, current_user.id, "admin_cleanup_risk_vulns",
                   "risk", None, {"fixed": stats["fixed"], "checked": stats["checked"]})
        db.commit()
    except Exception:
        pass  # el log es best-effort, no falla la operacion

    return stats


# Mapeo ISO 27005 threat category → temas ISO 27002 (mismo que risk_auto_generator)
_THREAT_CAT_THEMES: dict[str, list[str]] = {
    "Physical damage":              ["physical"],
    "Natural events":               ["physical"],
    "Loss of essential services":   ["physical", "technological"],
    "Disturbance due to radiation": ["physical"],
    "Compromise of information":    ["technological", "organizational"],
    "Technical failures":           ["technological"],
    "Unauthorized actions":         ["technological", "organizational", "people"],
    "Compromise of functions":      ["organizational", "people"],
}

# Mapeo categoria de vulnerabilidad → prefijos de codigo ISO 27002
_VULN_CAT_CTRL_PREFIXES: dict[str, list[str]] = {
    "network":      ["8.20","8.21","8.22","8.23","8.24","5.14","8.5","5.15","5.16","5.17","8.2","8.3","8.26"],
    "software":     ["8.25","8.26","8.27","8.28","8.29","8.30","8.31","8.32","8.7","8.8","8.9","8.19"],
    "hardware":     ["8.1","8.12","7.8","7.9","7.12","7.13","8.13"],
    "personnel":    ["6.1","6.2","6.3","6.4","6.5","6.6","5.9","5.10","5.18"],
    "site":         ["7.1","7.2","7.3","7.4","7.5","7.6","7.7","7.10","7.11","7.12"],
    "organization": ["5.1","5.2","5.3","5.4","5.5","5.6","5.7","5.31","5.32","5.33","5.34"],
}


@router.post("/risks/cleanup-controls")
def cleanup_risk_controls(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Limpieza masiva de controles: reemplaza los controles de cada riesgo por los
    que corresponden a su amenaza y vulnerabilidades segun el catalogo ISO 27002.

    Logica:
    1. Obtiene las categorias de las vulnerabilidades vinculadas al riesgo
    2. Mapea esas categorias a prefijos de codigo ISO 27002
    3. Filtra los controles implementados del tenant por esos prefijos
    4. Si no hay match por prefijo, usa el tema de la amenaza como fallback
    5. Ordena por madurez descendente y limita a 10 controles por riesgo

    Devuelve estadisticas detalladas por riesgo.
    """
    from app.models import Control, ControlStatus

    org_id = current_user.organization_id
    q = db.query(Risk)
    if current_user.role != UserRole.SUPERADMIN:
        q = q.filter(Risk.organization_id == org_id)
    risks = q.all()

    # Cargar todos los controles implementados del tenant con su Control base
    all_impls = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == org_id,
        ControlImplementation.status.in_([ControlStatus.IMPLEMENTED, ControlStatus.PARTIAL]),
        ControlImplementation.maturity > 0,
    ).all()

    # Indice: prefijo → lista de impl (ej. "8.24" → [...])
    prefix_index: dict[str, list] = {}
    theme_index: dict[str, list] = {}
    for impl in all_impls:
        ctrl = db.get(Control, impl.control_id) if impl.control_id else None
        if ctrl:
            code = ctrl.code or ""
            # Indexar por prefijo (hasta 2 niveles: "8.24" y "8")
            for sep_idx in range(len(code)):
                if code[sep_idx] == '.':
                    prefix_index.setdefault(code[:sep_idx + 3], []).append(impl)
                    break
            prefix_index.setdefault(code, []).append(impl)
            if ctrl.theme:
                theme_index.setdefault(ctrl.theme, []).append(impl)

    stats = {"checked": 0, "fixed": 0, "already_ok": 0, "details": []}

    for risk in risks:
        stats["checked"] += 1
        threat = db.get(Threat, risk.threat_id) if risk.threat_id else None

        # Determinar prefijos relevantes a partir de las vulnerabilidades del riesgo
        vuln_cats = list({v.category for v in (risk.vulnerabilities or []) if v.category})
        prefixes: list[str] = []
        for cat in vuln_cats:
            prefixes.extend(_VULN_CAT_CTRL_PREFIXES.get(cat, []))

        # Buscar controles que empiecen con alguno de los prefijos
        seen: set[int] = set()
        correct_impls: list = []
        for impl in all_impls:
            ctrl = db.get(Control, impl.control_id) if impl.control_id else None
            if ctrl and prefixes and any(ctrl.code.startswith(p) for p in prefixes if ctrl.code):
                if impl.id not in seen:
                    seen.add(impl.id)
                    correct_impls.append(impl)

        # Fallback: filtrar por tema de amenaza si no hay match por prefijo
        if not correct_impls and threat:
            themes = _THREAT_CAT_THEMES.get(threat.category or "", [])
            for impl in all_impls:
                ctrl = db.get(Control, impl.control_id) if impl.control_id else None
                if ctrl and ctrl.theme in themes and impl.id not in seen:
                    seen.add(impl.id)
                    correct_impls.append(impl)

        # Ordenar por madurez desc y limitar
        correct_impls.sort(key=lambda c: c.maturity or 0, reverse=True)
        correct_impls = correct_impls[:10]

        current_ids = {c.id for c in (risk.controls or [])}
        correct_ids  = {c.id for c in correct_impls}

        if current_ids == correct_ids:
            stats["already_ok"] += 1
            stats["details"].append({"risk_code": risk.code, "action": "ok", "count": len(correct_ids)})
            continue

        removed = []
        for c in (risk.controls or []):
            if c.id not in correct_ids:
                ctrl = db.get(Control, c.control_id) if c.control_id else None
                removed.append(ctrl.code if ctrl else str(c.id))
        added = []
        for c in correct_impls:
            if c.id not in current_ids:
                ctrl = db.get(Control, c.control_id) if c.control_id else None
                added.append(ctrl.code if ctrl else str(c.id))

        risk.controls = correct_impls
        stats["fixed"] += 1
        stats["details"].append({
            "risk_code": risk.code,
            "threat_code": threat.code if threat else "?",
            "action": "fixed",
            "vuln_cats": vuln_cats,
            "removed": removed,
            "added": added,
        })

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Error al guardar cambios: {exc}") from exc

    try:
        log_action(db, current_user.id, "admin_cleanup_risk_controls",
                   "risk", None, {"fixed": stats["fixed"], "checked": stats["checked"]})
        db.commit()
    except Exception:
        pass

    return stats
