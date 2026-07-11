"""Endpoints de autenticacion."""
import hashlib
import re
import secrets
import string
from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
import jwt
from jwt.exceptions import InvalidTokenError as JWTError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import EmailSettings, Organization, User
from app.schemas import TokenOut, UserOut
from app.security import (
    create_access_token, create_refresh_token, decode_token, decrypt_secret,
    encrypt_secret, get_current_user, hash_password, is_token_revoked,
    mfa_setup_required, oauth2_scheme, revoke_token, verify_password,
)
from app.services.audit_service import log_action
from app.services.rate_limiter import (
    check_login_allowed, remaining_lockout_seconds, reset_login_counter,
)
from app.i18n import get_lang, t as _t

router = APIRouter(prefix="/api/auth", tags=["auth"])

_MIN_PASSWORD_LEN = 8
# Caracteres especiales permitidos en contrasenas
_SPECIAL_CHARS = r"!@#$%^&*()\-_=+\[\]{}|;:',.<>?/"

# Duracion (minutos) del token intermedio de MFA
_MFA_TOKEN_MINUTES = 5


# ---------- Helpers de validacion de contrasenas ----------

def _validate_password_strength(password: str, lang: str = "es") -> str | None:
    """Validate password strength. Returns None on success or a translated error message."""
    if len(password) < _MIN_PASSWORD_LEN:
        return _t("auth.password_min_length", lang, min=_MIN_PASSWORD_LEN)
    if not re.search(r"[A-Z]", password):
        return _t("auth.password_needs_uppercase", lang)
    if not re.search(r"[a-z]", password):
        return _t("auth.password_needs_lowercase", lang)
    if not re.search(r"\d", password):
        return _t("auth.password_needs_digit", lang)
    if not re.search(rf"[{_SPECIAL_CHARS}]", password):
        return _t("auth.password_needs_special", lang)
    return None


def _generate_otp_password(length: int = 12) -> str:
    """Genera una contrasena temporal aleatoria segura que cumple todos los requisitos."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    # Garantizar al menos un caracter de cada categoria requerida
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (re.search(r"[A-Z]", pwd) and re.search(r"[a-z]", pwd)
                and re.search(r"\d", pwd) and re.search(r"[!@#$%^&*()\-_=+]", pwd)):
            return pwd


def _client_ip(request: Request) -> str:
    """Extrae la IP real del cliente desde X-Real-IP (seteado por Nginx/proxy).
    X-Forwarded-For es ignorado porque el cliente puede falsificarlo."""
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _try_send_otp_email(db: Session, to_email: str, full_name: str,
                         otp_password: str, org_id: int | None) -> bool:
    """Intenta enviar la contrasena OTP por email. Devuelve True si se envio."""
    try:
        q = db.query(EmailSettings)
        if org_id:
            q = q.filter(EmailSettings.organization_id == org_id)
        cfg = q.first()
        if not cfg or not cfg.smtp_host:
            return False
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(
            f"Hola {full_name},\n\n"
            f"Tu cuenta en RiskHub ha sido creada.\n"
            f"Contrasena temporal: {otp_password}\n\n"
            f"Deberas cambiarla en el primer inicio de sesion.\n\n"
            f"RiskHub - Gestion de Riesgos",
            "plain",
            "utf-8",
        )
        msg["Subject"] = "RiskHub - Credenciales de acceso"
        msg["From"] = cfg.smtp_from or cfg.smtp_user
        msg["To"] = to_email
        smtp_pwd = ""
        if cfg.smtp_password_encrypted:
            try:
                smtp_pwd = decrypt_secret(cfg.smtp_password_encrypted)
            except Exception:
                smtp_pwd = cfg.smtp_password or ""
        else:
            smtp_pwd = cfg.smtp_password or ""
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as srv:
            if cfg.smtp_use_tls:
                srv.starttls()
            if cfg.smtp_user:
                srv.login(cfg.smtp_user, smtp_pwd)
            srv.sendmail(msg["From"], [to_email], msg.as_string())
        return True
    except Exception:
        return False


# ---------- Endpoints ----------

@router.post("/login", response_model=TokenOut)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    ip  = _client_ip(request)
    lang = get_lang(request)

    # OWASP A07 — comprobar rate limit antes de consultar la BD.
    # Doble clave: por IP (ataque desde una maquina) y por cuenta (ataque
    # distribuido contra un mismo email rotando IPs).
    acct_key = "acct:" + (form.username or "").strip().lower()
    ip_ok = check_login_allowed(ip)
    acct_ok = check_login_allowed(acct_key)
    if not ip_ok or not acct_ok:
        secs = max(remaining_lockout_seconds(ip), remaining_lockout_seconds(acct_key))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_t("auth.account_locked", lang, seconds=secs),
            headers={"Retry-After": str(secs)},
        )

    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        log_action(
            db, None, "login_failed", "user", form.username,
            {"ip": ip, "reason": "invalid_credentials"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_t("auth.invalid_credentials", lang),
        )
    if not user.is_active:
        log_action(
            db, user.id, "login_failed", "user", str(user.id),
            {"ip": ip, "reason": "account_disabled"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_t("auth.user_disabled", lang),
        )

    # Bloquear login si la organizacion del usuario esta desactivada
    if user.organization_id:
        org = db.get(Organization, user.organization_id)
        if org and not org.is_active:
            log_action(
                db, user.id, "login_failed", "user", str(user.id),
                {"ip": ip, "reason": "organization_disabled"},
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_t("auth.user_disabled", lang),
            )

    # Login exitoso: resetear contadores de intentos (IP y cuenta)
    reset_login_counter(ip)
    reset_login_counter(acct_key)
    user.last_login_at = datetime.now(timezone.utc)
    log_action(db, user.id, "login", "user", str(user.id),
               {"email": user.email, "role": user.role.value, "ip": ip})
    db.commit()

    # Flujo MFA: si el usuario tiene MFA activo, devolver token intermedio
    if user.mfa_enabled:
        mfa_token = _create_mfa_token(user.email)
        return TokenOut(
            access_token="",
            user=UserOut.model_validate(user),
            mfa_required=True,
            mfa_token=mfa_token,
        )

    token = create_access_token(subject=user.email, role=user.role.value)
    return TokenOut(
        access_token=token,
        refresh_token=create_refresh_token(subject=user.email, role=user.role.value),
        user=UserOut.model_validate(user),
        must_change_password=bool(user.must_change_password),
        must_configure_mfa=mfa_setup_required(db, user),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


class LogoutIn(BaseModel):
    refresh_token: str | None = None


@router.post("/logout")
def logout(
    body: LogoutIn | None = None,
    token: str = Depends(oauth2_scheme),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cierra la sesion revocando el access token actual y, si el cliente
    lo envia, tambien su refresh token (logout real completo).

    Los jti entran en la lista de revocados hasta su expiracion natural;
    cualquier uso posterior devuelve 401.
    """
    try:
        payload = decode_token(token)
    except Exception:
        payload = {}
    revoked = revoke_token(db, payload, user_id=user.id)
    if body and body.refresh_token:
        try:
            rpayload = decode_token(body.refresh_token)
            # Solo revocar refresh tokens del propio usuario
            if rpayload.get("type") == "refresh" and rpayload.get("sub") == user.email:
                revoke_token(db, rpayload, user_id=user.id)
        except Exception:
            pass  # refresh invalido o expirado: nada que revocar
    log_action(db, user.id, "logout", "user", str(user.id), {"revoked": revoked})
    db.commit()
    return {"ok": True, "revoked": revoked}


class RefreshIn(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenOut)
def refresh_session(
    request: Request,
    body: RefreshIn,
    db: Session = Depends(get_db),
):
    """Renueva la sesion: valida el refresh token, lo rota (el usado queda
    revocado) y devuelve un access token nuevo con su refresh nuevo."""
    lang = get_lang(request)
    cred_error = HTTPException(status_code=401, detail=_t("auth.invalid_credentials", lang))
    try:
        payload = decode_token(body.refresh_token)
    except Exception:
        raise cred_error
    if payload.get("type") != "refresh":
        raise cred_error
    if is_token_revoked(db, payload.get("jti")):
        raise cred_error

    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user or not user.is_active:
        raise cred_error
    if user.organization_id:
        org = db.get(Organization, user.organization_id)
        if org and not org.is_active:
            raise cred_error

    # Rotacion: el refresh usado deja de valer (limita el dano si se filtra)
    revoke_token(db, payload, user_id=user.id)
    return TokenOut(
        access_token=create_access_token(subject=user.email, role=user.role.value),
        refresh_token=create_refresh_token(subject=user.email, role=user.role.value),
        user=UserOut.model_validate(user),
        must_change_password=bool(user.must_change_password),
    )


class UserBasic(BaseModel):
    id: int
    email: str
    full_name: str


@router.get("/users", response_model=list[UserBasic])
def list_users_basic(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista simplificada de usuarios activos en la misma organizacion."""
    from app.models import UserRole as _Role
    q = db.query(User).filter(User.is_active.is_(True))
    if current_user.role != _Role.SUPERADMIN:
        q = q.filter(User.organization_id == current_user.organization_id)
    users = q.order_by(User.full_name).all()
    return [UserBasic(id=u.id, email=u.email, full_name=u.full_name or u.email) for u in users]


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


@router.patch("/me/password")
def change_my_password(
    body: PasswordChangeIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Permite al usuario autenticado cambiar su propia contrasena."""
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="La contrasena actual no es correcta")
    error = _validate_password_strength(body.new_password)
    if error:
        raise HTTPException(status_code=400, detail=error)
    if body.new_password.lower() == user.email.lower():
        raise HTTPException(status_code=400, detail="La contrasena no puede ser igual al email")
    user.hashed_password = hash_password(body.new_password)
    log_action(db, user.id, "update", "user", str(user.id),
               {"email": user.email, "action": "password_change"})
    db.commit()
    return {"ok": True, "message": "Contrasena actualizada correctamente"}


# ---------- OTP - Primer login ----------

class SetInitialPasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/set-initial-password")
def set_initial_password(
    body: SetInitialPasswordIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Cambia la contrasena OTP por una definitiva en el primer login."""
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="La contrasena actual (OTP) no es correcta")
    error = _validate_password_strength(body.new_password)
    if error:
        raise HTTPException(status_code=400, detail=error)
    if body.new_password.lower() == user.email.lower():
        raise HTTPException(status_code=400, detail="La contrasena no puede ser igual al email")
    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = False
    log_action(db, user.id, "update", "user", str(user.id),
               {"email": user.email, "action": "initial_password_set"})
    db.commit()
    return {"ok": True, "message": "Contrasena establecida correctamente"}


# ---------- MFA / TOTP ----------

def _create_mfa_token(email: str) -> str:
    """Genera un JWT de corta vida (5 min) para el segundo factor de autenticacion."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=_MFA_TOKEN_MINUTES)
    payload = {"sub": email, "type": "mfa", "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _verify_mfa_token(token: str) -> str:
    """Valida el token MFA y devuelve el email del usuario; lanza HTTPException si falla."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "mfa":
            raise ValueError("tipo incorrecto")
        email = payload.get("sub")
        if not email:
            raise ValueError("sin subject")
        return email
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token MFA invalido o expirado",
        )


def _generate_backup_codes() -> tuple[list[str], list[str]]:
    """Genera 8 codigos de recuperacion de un solo uso.

    Devuelve (plain_codes, hashed_codes).
    Los plain_codes se muestran una sola vez al usuario; los hashed_codes se almacenan en BD.
    """
    plain = [secrets.token_hex(4).upper() for _ in range(8)]
    hashed = [hashlib.sha256(c.encode()).hexdigest() for c in plain]
    return plain, hashed


def _use_backup_code(user: User, code: str) -> bool:
    """Consume un codigo de recuperacion si es valido. Devuelve True si era valido."""
    codes: list[str] = user.mfa_backup_codes or []
    if not codes:
        return False
    code_hash = hashlib.sha256(code.upper().encode()).hexdigest()
    if code_hash not in codes:
        return False
    user.mfa_backup_codes = [h for h in codes if h != code_hash]
    return True


class MfaSetupIn(BaseModel):
    current_password: str


@router.post("/mfa/setup")
def mfa_setup(
    body: MfaSetupIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Genera un secreto TOTP y devuelve el otpauth URL para configurar la app.

    Requiere la contrasena actual para evitar que una sesion robada active MFA.
    """
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="La contrasena actual no es correcta")
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(user.email, issuer_name="RiskHub")
    return {
        "secret": secret,
        "otpauth_url": uri,
        "instructions": (
            "Introduce el siguiente secreto en tu app de autenticacion (Google Authenticator, "
            "Authy, etc.) o escanea el codigo QR generando la URL otpauth en tu app. "
            "Luego confirma con el endpoint /mfa/verify-setup."
        ),
    }


class MfaVerifySetupIn(BaseModel):
    secret: str
    code: str


@router.post("/mfa/verify-setup")
def mfa_verify_setup(
    body: MfaVerifySetupIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Confirma el secreto TOTP y activa MFA. Devuelve los codigos de recuperacion (solo esta vez)."""
    totp = pyotp.TOTP(body.secret)
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Codigo TOTP incorrecto")
    plain_codes, hashed_codes = _generate_backup_codes()
    user.mfa_secret = encrypt_secret(body.secret)
    user.mfa_enabled = True
    user.mfa_backup_codes = hashed_codes
    log_action(db, user.id, "update", "user", str(user.id),
               {"email": user.email, "action": "mfa_enabled"})
    db.commit()
    return {
        "ok": True,
        "message": "MFA activado correctamente",
        "backup_codes": plain_codes,
        "backup_codes_note": (
            "Guarda estos codigos en un lugar seguro. "
            "Cada uno es de un solo uso y no podras verlos de nuevo."
        ),
    }


@router.post("/mfa/backup-codes/regenerate")
def mfa_regenerate_backup_codes(
    body: MfaSetupIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Regenera los codigos de recuperacion MFA. Requiere contrasena actual."""
    if not user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA no esta activado")
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="La contrasena actual no es correcta")
    plain_codes, hashed_codes = _generate_backup_codes()
    user.mfa_backup_codes = hashed_codes
    log_action(db, user.id, "update", "user", str(user.id),
               {"email": user.email, "action": "mfa_backup_codes_regenerated"})
    db.commit()
    return {
        "ok": True,
        "backup_codes": plain_codes,
        "backup_codes_note": (
            "Guarda estos codigos en un lugar seguro. "
            "Los codigos anteriores han quedado invalidados."
        ),
    }


@router.post("/mfa/disable")
def mfa_disable(
    body: MfaSetupIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Desactiva MFA para el usuario autenticado. Requiere contrasena actual."""
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="La contrasena actual no es correcta")
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_backup_codes = None
    log_action(db, user.id, "update", "user", str(user.id),
               {"email": user.email, "action": "mfa_disabled"})
    db.commit()
    return {"ok": True, "message": "MFA desactivado"}


class MfaDisableAdminIn(BaseModel):
    user_id: int


@router.post("/mfa/disable-admin")
def mfa_disable_admin(
    body: MfaDisableAdminIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin desactiva MFA de otro usuario (p.ej. si pierde el dispositivo)."""
    from app.models import UserRole as _Role
    if current_user.role not in (_Role.ADMIN, _Role.SUPERADMIN):
        raise HTTPException(status_code=403, detail="Requiere rol admin o superior")
    target = db.get(User, body.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    # Admin solo puede gestionar usuarios de su propia org
    if (current_user.role == _Role.ADMIN
            and target.organization_id != current_user.organization_id):
        raise HTTPException(status_code=403, detail="No autorizado")
    target.mfa_enabled = False
    target.mfa_secret = None
    target.mfa_backup_codes = None
    log_action(db, current_user.id, "update", "user", str(target.id),
               {"email": target.email, "action": "mfa_disabled_by_admin"})
    db.commit()
    return {"ok": True, "message": f"MFA desactivado para {target.email}"}


# ---------- Password reset por email ----------

class ForgotPasswordIn(BaseModel):
    email: str


def _reset_password_html(full_name: str, reset_url: str) -> str:
    from datetime import datetime as _dt
    now = _dt.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:24px;background:#F5F5F5;font-family:Inter,Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:10px;
              border:1px solid #E9E9E9;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <div style="background:linear-gradient(90deg,#59008D,#D65200);padding:20px 28px;">
      <h1 style="color:#fff;margin:0;font-size:18px;font-weight:700;">
        RiskHub &mdash; Restablecer contrase&ntilde;a
      </h1>
    </div>
    <div style="padding:28px;font-size:14px;color:#262626;line-height:1.6;">
      <p>Hola {full_name},</p>
      <p>Hemos recibido una solicitud para restablecer la contrase&ntilde;a de tu cuenta en RiskHub.
         Haz clic en el siguiente boton para elegir una nueva contrase&ntilde;a:</p>
      <p style="text-align:center;margin:28px 0;">
        <a href="{reset_url}"
           style="background:linear-gradient(90deg,#59008D,#D65200);color:#fff;
                  text-decoration:none;padding:12px 28px;border-radius:6px;
                  font-weight:700;font-size:14px;">
          Restablecer contrase&ntilde;a
        </a>
      </p>
      <p>Este enlace es valido durante <strong>1 hora</strong>.
         Si no solicitaste este restablecimiento puedes ignorar este mensaje.</p>
      <p style="word-break:break-all;font-size:12px;color:#9D9D9D;">
        Enlace directo: {reset_url}
      </p>
      <p style="color:#9D9D9D;font-size:11px;margin-top:24px;margin-bottom:0;">
        Generado automaticamente por RiskHub el {now}.
      </p>
    </div>
  </div>
</body>
</html>"""


@router.post("/forgot-password")
def forgot_password(
    body: ForgotPasswordIn,
    db: Session = Depends(get_db),
):
    """Genera token de restablecimiento y lo envia por email. Siempre devuelve 200."""
    # Usar la URL publica configurada en settings para evitar Host Header Injection.
    # Si no esta configurada, se omite el envio del email pero el flujo no falla.
    public_url = settings.public_url.rstrip("/") if settings.public_url else ""

    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if user and user.is_active:
        token = secrets.token_urlsafe(32)
        user.password_reset_token = token
        user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()
        if public_url:
            try:
                from app.services.email_service import get_settings, send_email as _send
                cfg = get_settings(db, getattr(user, "organization_id", None))
                if cfg and cfg.smtp_host:
                    reset_url = f"{public_url}/login?reset_token={token}"
                    html = _reset_password_html(user.full_name or user.email, reset_url)
                    _send(cfg, user.email, "RiskHub - Restablecer contrasena", html)
            except Exception:
                pass
    return {"ok": True, "message": "Si el email existe en el sistema recibirás un enlace."}


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str


@router.post("/reset-password")
def reset_password(
    body: ResetPasswordIn,
    db: Session = Depends(get_db),
):
    """Restablece la contrasena usando el token enviado por email."""
    user = db.query(User).filter(User.password_reset_token == body.token).first()
    if not user or not user.password_reset_expires_at:
        raise HTTPException(status_code=400, detail="Token invalido o expirado")
    expires = user.password_reset_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        user.password_reset_token = None
        user.password_reset_expires_at = None
        db.commit()
        raise HTTPException(status_code=400, detail="Token invalido o expirado")
    error = _validate_password_strength(body.new_password)
    if error:
        raise HTTPException(status_code=400, detail=error)
    user.hashed_password = hash_password(body.new_password)
    user.password_reset_token = None
    user.password_reset_expires_at = None
    user.must_change_password = False
    log_action(db, user.id, "update", "user", str(user.id),
               {"email": user.email, "action": "password_reset_via_email"})
    db.commit()
    return {"ok": True, "message": "Contrasena restablecida correctamente"}


class MfaCompleteIn(BaseModel):
    mfa_token: str
    code: str


@router.post("/mfa/complete", response_model=TokenOut)
def mfa_complete(
    body: MfaCompleteIn,
    db: Session = Depends(get_db),
):
    """Segundo factor: valida el codigo TOTP y devuelve el JWT completo."""
    email = _verify_mfa_token(body.mfa_token)
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario no encontrado o inactivo")
    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA no configurado para este usuario")
    secret = decrypt_secret(user.mfa_secret)
    totp = pyotp.TOTP(secret)
    totp_valid = totp.verify(body.code, valid_window=1)
    if not totp_valid:
        # Intentar como codigo de recuperacion de un solo uso
        if not _use_backup_code(user, body.code):
            raise HTTPException(status_code=400, detail="Codigo TOTP o de recuperacion incorrecto")
        log_action(db, user.id, "update", "user", str(user.id),
                   {"email": user.email, "action": "mfa_backup_code_used"})
    db.commit()
    token = create_access_token(subject=user.email, role=user.role.value)
    return TokenOut(
        access_token=token,
        refresh_token=create_refresh_token(subject=user.email, role=user.role.value),
        user=UserOut.model_validate(user),
        must_change_password=bool(user.must_change_password),
    )
