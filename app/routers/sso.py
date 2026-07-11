"""SSO OIDC — integracion con Microsoft Entra ID, Google Workspace, Okta, etc.

Flujo: Authorization Code Flow (confidential client, con client_secret).
Seguridad:
  - state token de 32 bytes con TTL de 10 min (proteccion CSRF)
  - Credenciales cifradas con Fernet (misma clave que ai_config y sharepoint)
  - Validacion de dominio configurable para restringir acceso
  - Auto-provisioning opcional con rol configurable
"""
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.i18n import get_lang, t as _t

from app.database import get_db
from app.models import IntegrationConfig, SSOCode, SSOState, User, UserRole
from app.security import create_access_token, decrypt_secret, encrypt_secret, get_current_user, hash_password, require_admin
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/sso", tags=["sso"])

_INTEGRATION_NAME = "sso_oidc"
_STATE_TTL = 600    # 10 minutos
_CODE_TTL  = 30     # 30 segundos para intercambiar el code por el token


# ---------- Helpers ----------

def _get_config(db: Session, organization_id=None) -> Optional[dict]:
    q = db.query(IntegrationConfig).filter(IntegrationConfig.name == _INTEGRATION_NAME)
    if organization_id is not None:
        q = q.filter(IntegrationConfig.organization_id == organization_id)
    ic = q.first()
    if not ic or not ic.config_encrypted:
        return None
    try:
        return json.loads(decrypt_secret(ic.config_encrypted))
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


# ---------- SSO State en BD (anti-CSRF, multi-worker safe) ----------

def _create_state(db: Session, org_id: Optional[int] = None) -> str:
    """Genera un state token y lo persiste en BD con TTL.

    El org_id se codifica como prefijo "{org_id}:{token}" para vincular el
    flujo SSO a una organizacion concreta sin necesitar columna adicional en BD.
    """
    # Limpiar states expirados
    db.query(SSOState).filter(
        SSOState.expires_at < datetime.now(timezone.utc)
    ).delete(synchronize_session=False)
    raw = secrets.token_hex(32)
    # Formato: "0:token" (sin org) o "123:token" (con org_id)
    state = f"{org_id or 0}:{raw}"
    db.add(SSOState(
        state=state,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=_STATE_TTL),
    ))
    db.commit()
    return state


def _consume_state(db: Session, state: str) -> "tuple[bool, Optional[int]]":
    """Valida y elimina el state. Devuelve (valido, org_id).

    org_id es None si el state no lleva org o si no era valido.
    Compatibilidad hacia atras: states sin prefijo (formato antiguo) devuelven org_id=None.
    """
    record = db.query(SSOState).filter(SSOState.state == state).first()
    if not record:
        return False, None
    valid = record.expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
    # Extraer org_id del prefijo "{org_id}:{token}"
    org_id: Optional[int] = None
    try:
        prefix = state.split(":")[0]
        parsed = int(prefix)
        if parsed > 0:
            org_id = parsed
    except (ValueError, IndexError):
        pass
    db.delete(record)
    db.commit()
    return valid, org_id


# ---------- SSO Code exchange (evita JWT en URL) ----------

def _create_code(db: Session, token: str) -> str:
    """Almacena el JWT bajo un code de un solo uso con TTL de 30s."""
    db.query(SSOCode).filter(
        SSOCode.expires_at < datetime.now(timezone.utc)
    ).delete(synchronize_session=False)
    code = secrets.token_urlsafe(32)
    db.add(SSOCode(
        code=code,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=_CODE_TTL),
    ))
    db.commit()
    return code


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
def sso_status(org_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    """Endpoint publico — indica si SSO esta habilitado (para mostrar boton en login).

    Acepta org_id para devolver el estado correcto en entornos multi-tenant.
    """
    cfg = _get_config(db, org_id)
    return {"enabled": bool(cfg)}


@router.get("/config", response_model=SsoConfigOut)
def get_sso_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve la configuracion SSO actual (sin client_secret)."""
    cfg = _get_config(db, current_user.organization_id)
    if not cfg:
        return SsoConfigOut(configured=False)
    ic = db.query(IntegrationConfig).filter(
        IntegrationConfig.name == _INTEGRATION_NAME,
        IntegrationConfig.organization_id == current_user.organization_id,
    ).first()
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
    request: Request,
    body: SsoConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Guarda la configuracion SSO cifrada. Solo admin."""
    lang = get_lang(request)
    if not all([body.issuer_url, body.client_id, body.client_secret, body.redirect_uri]):
        raise HTTPException(400, _t("common.bad_request", lang))

    valid_roles = [r.value for r in UserRole]
    if body.default_role not in valid_roles:
        raise HTTPException(400, _t("common.bad_request", lang))

    encrypted = encrypt_secret(json.dumps({
        "issuer_url": body.issuer_url.strip().rstrip("/"),
        "client_id": body.client_id.strip(),
        "client_secret": body.client_secret.strip(),
        "redirect_uri": body.redirect_uri.strip(),
        "auto_provision": body.auto_provision,
        "default_role": body.default_role,
        "allowed_domains": body.allowed_domains.strip() if body.allowed_domains else None,
    }))

    ic = db.query(IntegrationConfig).filter(
        IntegrationConfig.name == _INTEGRATION_NAME,
        IntegrationConfig.organization_id == current_user.organization_id,
    ).first()
    if not ic:
        ic = IntegrationConfig(name=_INTEGRATION_NAME, organization_id=current_user.organization_id)
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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Elimina la configuracion SSO. Solo admin."""
    lang = get_lang(request)
    ic = db.query(IntegrationConfig).filter(
        IntegrationConfig.name == _INTEGRATION_NAME,
        IntegrationConfig.organization_id == current_user.organization_id,
    ).first()
    if not ic:
        raise HTTPException(404, _t("auth.sso_not_configured", lang))
    db.delete(ic)
    log_action(db, current_user.id, "delete", "integration_config", _INTEGRATION_NAME, {})
    db.commit()
    return {"ok": True, "message": "Configuracion SSO eliminada."}


@router.post("/test")
def test_sso_config(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Verifica la conectividad con el proveedor OIDC."""
    lang = get_lang(request)
    cfg = _get_config(db, current_user.organization_id)
    if not cfg:
        raise HTTPException(400, _t("auth.sso_not_configured", lang))
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
def sso_login(org_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    """Genera la URL de autorizacion y redirige al proveedor de identidad.

    org_id es necesario en entornos multi-tenant para usar la config SSO correcta.
    """
    cfg = _get_config(db, org_id)
    if not cfg:
        return RedirectResponse(url="/login?sso_error=sso_not_configured", status_code=302)

    try:
        doc = _oidc_discovery(cfg["issuer_url"])
    except ValueError as e:
        err_msg = urllib.parse.quote(str(e)[:200])
        return RedirectResponse(url=f"/login?sso_error={err_msg}", status_code=302)

    # Generar state token vinculado a la org para proteccion CSRF
    state = _create_state(db, org_id)

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

    # Validar y consumir state (proteccion CSRF — un solo uso, BD-backed)
    # _consume_state devuelve (valido, org_id) para mantener el contexto de org
    state_valid, sso_org_id = _consume_state(db, state)
    if not state_valid:
        return RedirectResponse(url="/login?sso_error=invalid_or_expired_state", status_code=302)

    cfg = _get_config(db, sso_org_id)
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
            _raw_role = cfg.get("default_role", "viewer")
            # Restringir a roles no privilegiados para usuarios SSO auto-provisionados
            if _raw_role in (UserRole.SUPERADMIN.value, UserRole.ADMIN.value):
                _raw_role = UserRole.VIEWER.value
            role = UserRole(_raw_role)
        except ValueError:
            role = UserRole.VIEWER

        # Resolver la org: prioridad 1 = org del flujo SSO (via state),
        # prioridad 2 = coincidencia por dominio del email.
        # Si no se puede determinar, rechazar para evitar usuario sin org.
        from app.models import Organization
        sso_org = None
        if sso_org_id:
            sso_org = db.get(Organization, sso_org_id)
        if not sso_org:
            email_domain = email.split("@")[-1].lower() if "@" in email else ""
            if email_domain:
                sso_org = db.query(Organization).filter(
                    Organization.domain == email_domain, Organization.is_active == True
                ).first()
        if not sso_org:
            return RedirectResponse(
                url="/login?sso_error=cannot_determine_org", status_code=302
            )
        user = User(
            email=email,
            full_name=full_name or email,
            # password inutilizable — la cuenta solo funciona por SSO
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            role=role,
            is_active=True,
            organization_id=sso_org.id,
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
    # Generar un code de un solo uso (30s TTL) — el JWT nunca aparece en la URL
    code = _create_code(db, token)
    return RedirectResponse(
        url=f"/?sso_code={urllib.parse.quote(code)}",
        status_code=302,
    )


class SsoExchangeIn(BaseModel):
    code: str


@router.post("/exchange")
def sso_exchange(request: Request, body: SsoExchangeIn, db: Session = Depends(get_db)):
    """Intercambia un SSO code de un solo uso por el JWT de sesion.
    El code caduca en 30 segundos para minimizar la ventana de exposicion."""
    lang = get_lang(request)
    record = db.query(SSOCode).filter(SSOCode.code == body.code).first()
    if not record:
        raise HTTPException(400, _t("auth.sso_invalid_state", lang))
    if record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        db.delete(record)
        db.commit()
        raise HTTPException(400, _t("auth.sso_invalid_state", lang))
    token = record.token
    db.delete(record)
    db.commit()
    # Emitir tambien un refresh token para que la sesion SSO se renueve
    # igual que la de login por contrasena
    refresh = None
    try:
        from app.security import create_refresh_token, decode_token
        payload = decode_token(token)
        refresh = create_refresh_token(subject=payload["sub"], role=payload.get("role", ""))
    except Exception:
        pass
    return {"access_token": token, "refresh_token": refresh, "token_type": "bearer"}
