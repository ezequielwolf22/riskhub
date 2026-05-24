"""Endpoints de autenticacion."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
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

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contrasena incorrectos",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado",
        )
    user.last_login_at = datetime.now(timezone.utc)
    log_action(db, user.id, "login", "user", str(user.id),
               {"email": user.email, "role": user.role.value})
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
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="La nueva contrasena debe tener al menos 8 caracteres")
    user.hashed_password = hash_password(body.new_password)
    log_action(db, user.id, "update", "user", str(user.id), {"email": user.email, "action": "password_change"})
    db.commit()
    return {"ok": True, "message": "Contrasena actualizada correctamente"}
