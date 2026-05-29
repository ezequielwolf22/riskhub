"""Endpoints de autenticacion."""
import re
import secrets
import string
from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import EmailSettings, Organization, User
from app.schemas import TokenOut, UserOut
from app.security import (
    create_access_token, decrypt_secret, encrypt_secret,
    get_current_user, hash_password, verify_password,
)
from app.services.audit_service import log_action
from app.services.rate_limiter import (
    check_login_allowed, remaining_lockout_seconds, reset_login_counter,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_MIN_PASSWORD_LEN = 8
# Caracteres especiales permitidos en contrasenas
_SPECIAL_CHARS = r"!@#$%^&*()\-_=+\[\]{}|;:',.<>?/"

# Duracion (minutos) del token intermedio de MFA
_MFA_TOKEN_MINUTES = 5


# ---------- Helpers de validacion de contrasenas ----------

def _validate_password_strength(password: str) -> str | None:
    """Valida la fortaleza de la contrasena.

    Devuelve None si cumple todos los requisitos, o un mensaje de error en castellano.
    """
    if len(password) < _MIN_PASSWORD_LEN:
        return f"La contrasena debe tener al menos {_MIN_PASSWORD_LEN} caracteres."
    if not re.search(r"[A-Z]", password):
        return "La contrasena debe contener al menos una letra mayuscula."
    if not re.search(r"[a-z]", password):
        return "La contrasena debe contener al menos una letra minuscula."
    if not re.search(r"\d", password):
        return "La contrasena debe contener al menos un digito (0-9)."
    if not re.search(rf"[{_SPECIAL_CHARS}]", password):
        return ("La contrasena debe contener al menos un caracter especial "
                "(!@#$%^&*()-_=+[]{}|;:',.<>?/).")
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
    """Extrae la IP real del cliente, respetando proxies de confianza."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
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
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as srv:
            if cfg.smtp_use_tls:
                srv.starttls()
            if cfg.smtp_user:
                srv.login(cfg.smtp_user, cfg.smtp_password or "")
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
    ip = _client_ip(request)

    # OWASP A07 — comprobar rate limit antes de consultar la BD
    if not check_login_allowed(ip):
        secs = remaining_lockout_seconds(ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Intenta de nuevo en {secs} segundos.",
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
            detail="Email o contrasena incorrectos",
        )
    if not user.is_active:
        log_action(
            db, user.id, "login_failed", "user", str(user.id),
            {"ip": ip, "reason": "account_disabled"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado",
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
                detail="La organizacion esta desactivada. Contacta con el administrador.",
            )

    # Login exitoso: resetear contador de intentos
    reset_login_counter(ip)
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
        user=UserOut.model_validate(user),
        must_change_password=bool(user.must_change_password),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


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


@router.post("/mfa/setup")
def mfa_setup(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Genera un secreto TOTP y devuelve el otpauth URL para configurar la app."""
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
    """Confirma el secreto TOTP y activa MFA para el usuario."""
    totp = pyotp.TOTP(body.secret)
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Codigo TOTP incorrecto")
    user.mfa_secret = encrypt_secret(body.secret)
    user.mfa_enabled = True
    log_action(db, user.id, "update", "user", str(user.id),
               {"email": user.email, "action": "mfa_enabled"})
    db.commit()
    return {"ok": True, "message": "MFA activado correctamente"}


@router.post("/mfa/disable")
def mfa_disable(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Desactiva MFA para el usuario autenticado."""
    user.mfa_enabled = False
    user.mfa_secret = None
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
    log_action(db, current_user.id, "update", "user", str(target.id),
               {"email": target.email, "action": "mfa_disabled_by_admin"})
    db.commit()
    return {"ok": True, "message": f"MFA desactivado para {target.email}"}


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
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Codigo TOTP incorrecto")
    token = create_access_token(subject=user.email, role=user.role.value)
    return TokenOut(
        access_token=token,
        user=UserOut.model_validate(user),
        must_change_password=bool(user.must_change_password),
    )
