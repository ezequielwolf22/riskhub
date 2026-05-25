"""Endpoints de autenticacion."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import TokenOut, UserOut
from app.security import (
    create_access_token, get_current_user, hash_password, verify_password,
)
from app.services.audit_service import log_action
from app.services.rate_limiter import (
    check_login_allowed, remaining_lockout_seconds, reset_login_counter,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_MIN_PASSWORD_LEN = 8


def _client_ip(request: Request) -> str:
    """Extrae la IP real del cliente, respetando proxies de confianza."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


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
        # OWASP A09 — registrar intento fallido
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

    # Login exitoso: resetear contador de intentos
    reset_login_counter(ip)

    user.last_login_at = datetime.now(timezone.utc)
    log_action(db, user.id, "login", "user", str(user.id),
               {"email": user.email, "role": user.role.value, "ip": ip})
    db.commit()
    token = create_access_token(subject=user.email, role=user.role.value)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


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
    _: User = Depends(get_current_user),
):
    """Lista simplificada de usuarios activos — accesible a cualquier usuario autenticado."""
    users = db.query(User).filter(User.is_active.is_(True)).order_by(User.full_name).all()
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
    if len(body.new_password) < _MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"La nueva contrasena debe tener al menos {_MIN_PASSWORD_LEN} caracteres",
        )
    # Evitar contrasenas que coincidan exactamente con el email del usuario
    if body.new_password.lower() == user.email.lower():
        raise HTTPException(status_code=400, detail="La contrasena no puede ser igual al email")
    user.hashed_password = hash_password(body.new_password)
    log_action(db, user.id, "update", "user", str(user.id),
               {"email": user.email, "action": "password_change"})
    db.commit()
    return {"ok": True, "message": "Contrasena actualizada correctamente"}
