"""Gestion de usuarios - solo administradores."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Risk, User
from app.schemas import UserIn, UserOut, UserUpdate
from app.security import get_current_user, hash_password, require_admin
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("/", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    counts_q = db.query(Risk.owner_id, func.count(Risk.id)).group_by(Risk.owner_id).all()
    risk_counts = {uid: cnt for uid, cnt in counts_q if uid}
    result = []
    for u in users:
        item = UserOut.model_validate(u)
        result.append(item.model_copy(update={"risk_count": risk_counts.get(u.id, 0)}))
    return result


_MIN_PASSWORD_LEN = 8


@router.post("/", response_model=UserOut, status_code=201)
def create_user(data: UserIn, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "Ya existe un usuario con ese email")
    if len(data.password) < _MIN_PASSWORD_LEN:
        raise HTTPException(
            400,
            f"La contrasena debe tener al menos {_MIN_PASSWORD_LEN} caracteres",
        )
    u = User(
        email=data.email, full_name=data.full_name, role=data.role,
        hashed_password=hash_password(data.password), is_active=True,
    )
    db.add(u)
    log_action(db, current_user.id, "create", "user", None,
               {"email": data.email, "role": str(data.role)})
    db.commit(); db.refresh(u)
    return u


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    if data.full_name is not None: u.full_name = data.full_name
    if data.role is not None: u.role = data.role
    if data.is_active is not None: u.is_active = data.is_active
    if data.password: u.hashed_password = hash_password(data.password)
    log_action(db, current_user.id, "update", "user", str(user_id),
               {"email": u.email, "role": str(u.role), "is_active": u.is_active})
    db.commit(); db.refresh(u)
    return u


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    # OWASP A01 — impedir autoeliminacion
    if user_id == current_user.id:
        raise HTTPException(400, "No puedes eliminar tu propia cuenta de administrador")
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    email = u.email
    db.delete(u)
    log_action(db, current_user.id, "delete", "user", str(user_id), {"email": email})
    db.commit()
