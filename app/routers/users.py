"""Gestion de usuarios - solo administradores."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Organization, Risk, User, UserRole
from app.schemas import UserIn, UserOut, UserUpdate
from app.security import filter_by_org, get_current_user, hash_password, require_admin
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("/", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    # Superadmin ve todos los usuarios; admin ve solo los de su org
    if current_user.role == UserRole.SUPERADMIN:
        users = db.query(User).order_by(User.created_at.desc()).all()
    else:
        users = db.query(User).filter(
            User.organization_id == current_user.organization_id
        ).order_by(User.created_at.desc()).all()
    user_ids = [u.id for u in users]
    counts_q = db.query(Risk.owner_id, func.count(Risk.id)).filter(
        Risk.owner_id.in_(user_ids)
    ).group_by(Risk.owner_id).all()
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
    # Determinar org: explicit > auto-assign por dominio > org del admin que crea
    org_id = data.organization_id
    if not org_id:
        if "@" in data.email:
            domain = data.email.split("@", 1)[-1].lower()
            org_by_domain = db.query(Organization).filter(
                Organization.domain == domain, Organization.is_active.is_(True)
            ).first()
            org_id = org_by_domain.id if org_by_domain else None
    if not org_id and current_user.role != UserRole.SUPERADMIN:
        org_id = current_user.organization_id
    u = User(
        email=data.email, full_name=data.full_name, role=data.role,
        hashed_password=hash_password(data.password), is_active=True,
        organization_id=org_id,
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
    # OWASP A01 — IDOR: non-superadmin solo puede editar usuarios de su propia org
    if current_user.role != UserRole.SUPERADMIN and u.organization_id != current_user.organization_id:
        raise HTTPException(403, "No autorizado")
    # Privilege escalation: solo superadmin puede asignar rol superadmin;
    # solo admin/superadmin puede asignar rol admin
    if data.role is not None:
        if data.role == UserRole.SUPERADMIN and current_user.role != UserRole.SUPERADMIN:
            raise HTTPException(403, "Solo superadmin puede asignar el rol superadmin")
        if data.role == UserRole.ADMIN and current_user.role not in (UserRole.SUPERADMIN, UserRole.ADMIN):
            raise HTTPException(403, "Solo admin o superior puede asignar el rol admin")
    if data.full_name is not None: u.full_name = data.full_name
    if data.role is not None: u.role = data.role
    if data.is_active is not None: u.is_active = data.is_active
    if data.password: u.hashed_password = hash_password(data.password)
    # Solo superadmin puede mover un usuario a otra organizacion
    if data.organization_id is not None:
        if current_user.role != UserRole.SUPERADMIN:
            raise HTTPException(403, "Solo superadmin puede cambiar la organizacion de un usuario")
        dest_org = db.get(Organization, data.organization_id)
        if not dest_org:
            raise HTTPException(404, "Organizacion destino no encontrada")
        u.organization_id = data.organization_id
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
    # OWASP A01 — IDOR: non-superadmin solo puede eliminar usuarios de su propia org
    if current_user.role != UserRole.SUPERADMIN and u.organization_id != current_user.organization_id:
        raise HTTPException(403, "No autorizado")
    email = u.email
    db.delete(u)
    log_action(db, current_user.id, "delete", "user", str(user_id), {"email": email})
    db.commit()
