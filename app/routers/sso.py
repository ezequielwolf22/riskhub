"""SSO OIDC — integracion con Microsoft Entra ID, Google Workspace, Okta, etc.

Flujo: Authorization Code Flow (confidential client, con client_secret).
Seguridad:
  - state token de 32 bytes con TTL de 10 min (proteccion CSRF)
  - Credenciales cifradas con Fernet (misma clave que ai_config y sharepoint)
  - Validacion de dominio configurable para restringir acceso
  - Auto-provisioning opcional con rol configurable
"""
import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import IntegrationConfig, User, UserRole
from app.security import create_access_token, get_current_user, hash_password, require_admin
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/sso", tags=["sso"])

_INTEGRATION_NAME = "sso_oidc"
_STATE_STORE: dict[str, float] = {}   # state_token -> expires_at (monotonic)
_STATE_TTL = 600   # 10 minutos


# ---------- Cifrado ----------

def _fernet_key() -> bytes:
    return base64.urlsafe_b64encode(
        hashlib.sha256(settings.secret_key.encode()).digest()
    )


def _encrypt(plain: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_fernet_key()).encrypt(plain.encode()).decode()


def _decrypt(token: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_fernet_key()).decrypt(token.encode()).decode()


# ---------- Helpers ----------

def _get_config(db: Session) -> Optional[dict]:
    ic = db.query(IntegrationConfig).filter_by(name=_INTEGRATION_NAME).first()
    if not ic or not ic.config_encrypted:
        return None
    try:
        return json.loads(_decrypt(ic.config_encrypted))
    except Exception:
        return None


def _oidc_discovery(issuer: str) -> dict:
    """Obtiene el documento de descubrimiento OIDC del proveedor."""
    issuer = issuer.rstrip("/")
    url = f"{issuer}/.well-known/openid-configuration"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise ValueError(f"OIDC discovery error {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise ValueError(f"No se pudo contactar el proveedor OIDC: {e.reason}")
    except Exception as e:
        raise ValueError(f"Error de descubrimiento OIDC: {e}")


def _exchange_code(token_endpoint: str, code: str, client_id: str,
                   client_secret: str, redirect_uri: str) -> dict:
    """Intercambia el authorization code por tokens de acceso e identidad."""
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    req = urllib.request.Request(token_endpoint, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read())
            msg = err.get("error_description") or err.get("error") or str(e)
        except Exception:
            msg = str(e)
        raise ValueError(f"Error en intercambio de tokens: {msg}")


def _get_userinfo(userinfo_endpoint: str, access_token: str) -> dict:
    """Obtiene el perfil del usuario autenticado desde el endpoint userinfo."""
    req = urllib.request.Request(userinfo_endpoint)
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise ValueError(f"Userinfo error {e.code}: {e.reason}")


def _purge_expired_states() -> None:
    now = time.monotonic()
    expired = [k for k, v in _STATE_STORE.items() if v < now]
    for k in expired:
        del _STATE_STORE[k]


# ---------- Schemas ----------

class SsoConfigIn(BaseModel):
    issuer_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    auto_provision: bool = False
    default_role: str = "viewer"
    allowed_domains: Optional[str] = None   # dominios separados por coma, ej: "corp.com,empresa.es"


class SsoConfigOut(BaseModel):
    configured: bool
    issuer_url: Optional[str] = None
    client_id: Optional[str] = None
    redirect_uri: Optional[str] = None
    auto_provision: Optional[bool] = None
    default_role: Optional[str] = None
    allowed_domains: Optional[str] = None
    updated_at: Optional[str] = None


# ---------- Endpoints ----------

@router.get("/status")
def sso_status(db: Session = Depends(get_db)):
    """Endpoint publico — indica si SSO esta habilitado (para mostrar boton en login)."""
    cfg = _get_config(db)
    return {"enabled": bool(cfg)}


@router.get("/config", response_model=SsoConfigOut)
def get_sso_config(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Devuelve la configuracion SSO actual (sin client_secret)."""
    cfg = _get_config(db)
    if not cfg:
        return SsoConfigOut(configured=False)
    ic = db.query(IntegrationConfig).filter_by(name=_INTEGRATION_NAME).first()
    return SsoConfigOut(
        configured=True,
        issuer_url=cfg.get("issuer_url"),
        client_id=cfg.get("client_id"),
        redirect_uri=cfg.get("redirect_uri"),
        auto_provision=cfg.get("auto_provision", False),
        default_role=cfg.get("default_role", "viewer"),
        allowed_domains=cfg.get("allowed_domains"),
        updated_at=ic.updated_at.isoformat() if ic and ic.updated_at else None,
    )


@router.put("/config")
def save_sso_config(
    body: SsoConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Guarda la configuracion SSO cifrada. Solo admin."""
    if not all([body.issuer_url, body.client_id, body.client_secret, body.redirect_uri]):
        raise HTTPException(400, "issuer_url, client_id, client_secret y redirect_uri son obligatorios.")

    valid_roles = [r.value for r in UserRole]
    if body.default_role not in valid_roles:
        raise HTTPException(400, f"default_role debe ser uno de: {valid_roles}")

    encrypted = _encrypt(json.dumps({
        "issuer_url": body.issuer_url.strip().rstrip("/"),
        "client_id": body.client_id.strip(),
        "client_secret": body.client_secret.strip(),
        "redirect_uri": body.redirect_uri.strip(),
        "auto_provision": body.auto_provision,
        "default_role": body.default_role,
        "allowed_domains": body.allowed_domains.strip() if body.allowed_domains else None,
    }))

    ic = db.query(IntegrationConfig).filter_by(name=_INTEGRATION_NAME).first()
    if not ic:
        ic = IntegrationConfig(name=_INTEGRATION_NAME)
        db.add(ic)
    ic.config_encrypted = encrypted
    ic.updated_at = datetime.now(timezone.utc)
    ic.updated_by_id = current_user.id

    log_action(db, current_user.id, "update", "integration_config", _INTEGRATION_NAME,
               {"issuer_url": body.issuer_url, "client_id": body.client_id,
                "auto_provision": body.auto_provision})
    db.commit()
    return {"ok": True, "message": "Configuracion SSO guardada correctamente."}


@router.delete("/config")
def delete_sso_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Elimina la configuracion SSO. Solo admin."""
    ic = db.query(IntegrationConfig).filter_by(name=_INTEGRATION_NAME).first()
    if not ic:
        raise HTTPException(404, "SSO no configurado.")
    db.delete(ic)
    log_action(db, current_user.id, "delete", "integration_config", _INTEGRATION_NAME, {})
    db.commit()
    return {"ok": True, "message": "Configuracion SSO eliminada."}


@router.post("/test")
def test_sso_config(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Verifica la conectividad con el proveedor OIDC."""
    cfg = _get_config(db)
    if not cfg:
        raise HTTPException(400, "SSO no configurado.")
    try:
        doc = _oidc_discovery(cfg["issuer_url"])
        return {
            "ok": True,
            "message": "Proveedor OIDC accesible correctamente.",
            "issuer": doc.get("issuer"),
            "authorization_endpoint": doc.get("authorization_endpoint"),
            "token_endpoint": doc.get("token_endpoint"),
            "userinfo_endpoint": doc.get("userinfo_endpoint"),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/login")
def sso_login(db: Session = Depends(get_db)):
    """Genera la URL de autorizacion y redirige al proveedor de identidad."""
    cfg = _get_config(db)
    if not cfg:
        return RedirectResponse(url="/login?sso_error=sso_not_configured", status_code=302)

    try:
        doc = _oidc_discovery(cfg["issuer_url"])
    except ValueError as e:
        err_msg = urllib.parse.quote(str(e)[:200])
        return RedirectResponse(url=f"/login?sso_error={err_msg}", status_code=302)

    # Generar state token para proteccion CSRF
    state = secrets.token_hex(32)
    _purge_expired_states()
    _STATE_STORE[state] = time.monotonic() + _STATE_TTL

    auth_url = doc["authorization_endpoint"] + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": "openid email profile",
        "state": state,
    })
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/callback")
def sso_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Callback OIDC — valida code y state, emite JWT de RiskHub y redirige a la SPA."""
    # El proveedor rechazo la autenticacion
    if error:
        desc = urllib.parse.quote((error_description or error)[:200])
        return RedirectResponse(url=f"/login?sso_error={desc}", status_code=302)

    if not code or not state:
        return RedirectResponse(url="/login?sso_error=missing_params", status_code=302)

    # Validar y consumir state (proteccion CSRF — un solo uso)
    _purge_expired_states()
    if state not in _STATE_STORE or _STATE_STORE.get(state, 0) < time.monotonic():
        return RedirectResponse(url="/login?sso_error=invalid_or_expired_state", status_code=302)
    del _STATE_STORE[state]

    cfg = _get_config(db)
    if not cfg:
        return RedirectResponse(url="/login?sso_error=sso_not_configured", status_code=302)

    # Intercambiar code por tokens y obtener perfil del usuario
    try:
        doc = _oidc_discovery(cfg["issuer_url"])
        tokens = _exchange_code(
            doc["token_endpoint"], code,
            cfg["client_id"], cfg["client_secret"], cfg["redirect_uri"],
        )
        userinfo = _get_userinfo(doc["userinfo_endpoint"], tokens["access_token"])
    except ValueError as e:
        err_msg = urllib.parse.quote(str(e)[:200])
        return RedirectResponse(url=f"/login?sso_error={err_msg}", status_code=302)

    # Resolver email — distintos proveedores usan distintos campos
    email = (
        userinfo.get("email")
        or userinfo.get("upn")
        or userinfo.get("preferred_username")
    )
    if not email or "@" not in email:
        return RedirectResponse(url="/login?sso_error=no_email_in_userinfo", status_code=302)
    email = email.lower().strip()

    # Validar restriccion de dominio
    allowed_domains = cfg.get("allowed_domains")
    if allowed_domains:
        domains = [d.strip().lower() for d in allowed_domains.split(",") if d.strip()]
        domain = email.split("@")[-1]
        if domain not in domains:
            return RedirectResponse(url="/login?sso_error=domain_not_allowed", status_code=302)

    user = db.query(User).filter(User.email == email).first()

    if not user:
        if not cfg.get("auto_provision", False):
            return RedirectResponse(url="/login?sso_error=user_not_found", status_code=302)

        # Auto-provisioning — crear el usuario con el rol por defecto
        full_name = (
            userinfo.get("name")
            or f"{userinfo.get('given_name', '')} {userinfo.get('family_name', '')}".strip()
            or email
        )
        try:
            role = UserRole(cfg.get("default_role", "viewer"))
        except ValueError:
            role = UserRole.VIEWER

        user = User(
            email=email,
            full_name=full_name or email,
            # password inutilizable — la cuenta solo funciona por SSO
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        log_action(db, user.id, "create", "user", str(user.id), {
            "email": email, "source": "sso_auto_provision", "role": role.value,
        })

    if not user.is_active:
        return RedirectResponse(url="/login?sso_error=account_disabled", status_code=302)

    user.last_login_at = datetime.now(timezone.utc)
    log_action(db, user.id, "login", "user", str(user.id),
               {"email": email, "role": user.role.value, "source": "sso"})
    db.commit()

    token = create_access_token(subject=user.email, role=user.role.value)
    # Redirigir a la SPA — el token va en el query param para que app.js lo recoja
    return RedirectResponse(
        url=f"/?sso_token={urllib.parse.quote(token)}",
        status_code=302,
    )
