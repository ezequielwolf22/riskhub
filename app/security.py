"""Autenticacion JWT, hash de passwords y dependencias FastAPI."""
import base64
import hashlib
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt.exceptions import InvalidTokenError as JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Organization, RevokedToken, User, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _fernet() -> Fernet:
    """Genera una clave Fernet derivada del secret_key de la aplicacion."""
    key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_secret(value: str) -> str:
    """Cifra un string con Fernet; devuelve la cadena cifrada en UTF-8."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    """Descifra un string previamente cifrado con Fernet."""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except Exception as exc:
        import logging
        logging.getLogger("riskhub.security").error(
            "decrypt_secret failed — RISKHUB_SECRET_KEY may have changed since the value was encrypted: %s", exc
        )
        raise


def hash_password(plain: str) -> str:
    # bcrypt no soporta passwords > 72 bytes
    return pwd_context.hash(plain[:72])


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain[:72], hashed)


def create_access_token(subject: str, role: str, extra: Optional[dict] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expires_minutes)
    # jti unico por token: permite revocacion individual (logout real)
    payload = {"sub": subject, "role": role, "exp": expire, "jti": uuid.uuid4().hex}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, role: str) -> str:
    """Refresh token de larga duracion: solo sirve en /api/auth/refresh."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_refresh_expires_minutes)
    payload = {
        "sub": subject, "role": role, "exp": expire,
        "jti": uuid.uuid4().hex, "type": "refresh",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    # PyJWT devuelve dict directamente; algorithms es obligatorio para evitar alg:none
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


# ---------- Revocacion de tokens (logout real) ----------
# Cache en memoria del conjunto de jti revocados: se refresca desde la tabla
# revoked_tokens cada _REVOKED_TTL_S para no consultar la BD en cada request.

_REVOKED_TTL_S = 30
_revoked_lock = threading.Lock()
_revoked_jtis: set[str] = set()
_revoked_loaded_at: float = 0.0


def _refresh_revoked_cache(db: Session) -> None:
    global _revoked_jtis, _revoked_loaded_at
    now = time.monotonic()
    with _revoked_lock:
        if now - _revoked_loaded_at < _REVOKED_TTL_S and _revoked_loaded_at > 0:
            return
        try:
            rows = db.query(RevokedToken.jti).all()
            _revoked_jtis = {r[0] for r in rows}
            _revoked_loaded_at = now
        except Exception:
            # Si la tabla aun no existe (arranque inicial), no bloquear el login
            _revoked_loaded_at = now


def is_token_revoked(db: Session, jti: Optional[str]) -> bool:
    if not jti:
        # Tokens antiguos sin jti: no revocables individualmente, se aceptan
        # hasta su expiracion natural.
        return False
    _refresh_revoked_cache(db)
    return jti in _revoked_jtis


def revoke_token(db: Session, payload: dict, user_id: Optional[int] = None) -> bool:
    """Revoca el token del payload dado. Devuelve False si no tiene jti."""
    jti = payload.get("jti")
    if not jti:
        return False
    exp = payload.get("exp")
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
    if not db.query(RevokedToken.id).filter(RevokedToken.jti == jti).first():
        db.add(RevokedToken(jti=jti, user_id=user_id, expires_at=expires_at))
        db.commit()
    with _revoked_lock:
        _revoked_jtis.add(jti)
    return True


def purge_expired_revocations(db: Session) -> int:
    """Elimina revocaciones de tokens ya expirados (mantenimiento)."""
    cutoff = datetime.now(timezone.utc)
    n = (
        db.query(RevokedToken)
        .filter(RevokedToken.expires_at.isnot(None), RevokedToken.expires_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return n


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    cred_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales no validas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        email = payload.get("sub")
        if email is None:
            raise cred_error
        # Solo aceptar tokens de sesion completa: los intermedios de MFA y los
        # refresh tokens llevan claim "type" y no valen como access token
        if payload.get("type"):
            raise cred_error
    except JWTError:
        raise cred_error
    # Sesion cerrada explicitamente (logout): el token queda invalido
    if is_token_revoked(db, payload.get("jti")):
        raise cred_error
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        raise cred_error
    # Superadmin puede enfocar una org concreta via X-Active-Org
    if user.role == UserRole.SUPERADMIN:
        raw = request.headers.get("X-Active-Org", "").strip()
        user._active_org_id = int(raw) if raw.isdigit() else None
    return user


def mfa_setup_required(db: Session, user: User) -> bool:
    """Devuelve True si la politica de MFA obliga a este usuario a configurar TOTP.

    Prioridad: override individual (True=forzado, False=exento) sobre la
    politica de la organizacion (Organization.mfa_required). Si el usuario ya
    tiene MFA activo no aplica (ya cumple, sea cual sea la politica).
    """
    if user.mfa_enabled:
        return False
    if user.mfa_override is not None:
        return bool(user.mfa_override)
    if not user.organization_id:
        return False
    org = db.get(Organization, user.organization_id)
    return bool(org and org.mfa_required)


def require_role(*roles: UserRole):
    """Comprueba que el usuario tiene uno de los roles especificados.

    Superadmin siempre pasa (esta por encima de todos los roles).
    Admin pasa en cualquier comprobacion que no sea especificamente superadmin.
    """
    def dependency(user: User = Depends(get_current_user)) -> User:
        # Superadmin tiene acceso total
        if user.role == UserRole.SUPERADMIN:
            return user
        # Admin tiene acceso a todo excepto rutas exclusivas de superadmin
        if user.role == UserRole.ADMIN and UserRole.SUPERADMIN not in roles:
            return user
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operacion restringida a roles: {[r.value for r in roles]}",
            )
        return user
    return dependency


require_superadmin = require_role(UserRole.SUPERADMIN)
require_admin = require_role(UserRole.ADMIN)
require_analyst = require_role(UserRole.ANALYST, UserRole.ADMIN)


def filter_by_org(query, model, user: User):
    """Aplica filtro de organization_id a una query ORM.

    Superadmin sin contexto activo ve datos de todos los tenants.
    Superadmin con X-Active-Org filtra solo esa organizacion.
    El resto solo ve datos de su propia organizacion.
    """
    if user.role == UserRole.SUPERADMIN:
        active_org = getattr(user, "_active_org_id", None)
        if active_org:
            return query.filter(model.organization_id == active_org)
        return query
    return query.filter(model.organization_id == user.organization_id)


def check_org_access(record_org_id, user: User) -> bool:
    """Devuelve True si el usuario tiene acceso al registro dado su organization_id."""
    if user.role == UserRole.SUPERADMIN:
        active_org = getattr(user, "_active_org_id", None)
        if active_org:
            return record_org_id == active_org
        return True
    return record_org_id == user.organization_id


def require_active_license(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Valida que la licencia de la organizacion este activa.

    Se lanza una excepcion 403 si la licencia esta suspendida o expirada.
    Superadmin siempre pasa (no tienen org asignada o pueden administrar).
    """
    from app.services import license_service as lic_svc

    # Superadmin no tiene restriccion
    if user.role == UserRole.SUPERADMIN:
        return user

    # Validar que la org tiene licencia activa
    if not user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario no pertenece a ninguna organizacion",
        )

    if not lic_svc.is_license_active(db, user.organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Licencia expirada o suspendida. Contacte a administrador.",
        )

    return user
