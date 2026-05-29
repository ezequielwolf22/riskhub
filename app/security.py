"""Autenticacion JWT, hash de passwords y dependencias FastAPI."""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User, UserRole

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
    return _fernet().decrypt(value.encode()).decode()


def hash_password(plain: str) -> str:
    # bcrypt no soporta passwords > 72 bytes
    return pwd_context.hash(plain[:72])


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain[:72], hashed)


def create_access_token(subject: str, role: str, extra: Optional[dict] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expires_minutes)
    payload = {"sub": subject, "role": role, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


def get_current_user(
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
    except JWTError:
        raise cred_error
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        raise cred_error
    return user


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

    Superadmin ve datos de todos los tenants.
    El resto solo ve datos de su propia organizacion.
    """
    if user.role == UserRole.SUPERADMIN:
        return query
    return query.filter(model.organization_id == user.organization_id)


def check_org_access(record_org_id, user: User) -> bool:
    """Devuelve True si el usuario tiene acceso al registro dado su organization_id."""
    if user.role == UserRole.SUPERADMIN:
        return True
    return record_org_id == user.organization_id
