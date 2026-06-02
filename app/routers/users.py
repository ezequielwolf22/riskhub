"""Gestion de usuarios - solo administradores."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Organization, Risk, User, UserRole
from app.routers.auth import _generate_otp_password, _try_send_otp_email, _validate_password_strength
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
        org_id_filter = None  # sin filtro para superadmin
    else:
        users = db.query(User).filter(
            User.organization_id == current_user.organization_id
        ).order_by(User.created_at.desc()).all()
        org_id_filter = current_user.organization_id  # filtrar por org para otros

    user_ids = [u.id for u in users]
    # Contar riesgos: superadmin ve todos, otros solo los de su org
    counts_q = db.query(Risk.owner_id, func.count(Risk.id)).filter(
        Risk.owner_id.in_(user_ids)
    )
    if org_id_filter is not None:
        counts_q = counts_q.filter(Risk.organization_id == org_id_filter)

    counts_q = counts_q.group_by(Risk.owner_id).all()
    risk_counts = {uid: cnt for uid, cnt in counts_q if uid}
    result = []
    for u in users:
        item = UserOut.model_validate(u)
        result.append(item.model_copy(update={"risk_count": risk_counts.get(u.id, 0)}))
    return result


@router.post("/", response_model=UserOut, status_code=201)
def create_user(data: UserIn, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "Ya existe un usuario con ese email")

    # Contrasena: si no se proporciona, generar OTP automaticamente
    otp_generated = False
    if not data.password:
        plain_password = _generate_otp_password()
        otp_generated = True
    else:
        plain_password = data.password
        error = _validate_password_strength(plain_password)
        if error:
            raise HTTPException(400, error)

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
        hashed_password=hash_password(plain_password), is_active=True,
        organization_id=org_id,
        must_change_password=otp_generated,
    )
    db.add(u)
    log_action(db, current_user.id, "create", "user", None,
               {"email": data.email, "role": str(data.role), "otp_generated": otp_generated})
    db.commit()
    db.refresh(u)

    # Intentar enviar la contrasena OTP por email si hay SMTP configurado
    email_sent = False
    if otp_generated:
        email_sent = _try_send_otp_email(db, data.email, data.full_name, plain_password, org_id)

    # Devolver la contrasena generada en la respuesta (solo en este momento)
    out = UserOut.model_validate(u)
    if otp_generated:
        # Inyectar la contrasena temporal para que el admin pueda comunicarla
        return out.model_copy(update={
            "otp_password": plain_password,
            "otp_email_sent": email_sent,
        })
    return out


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
    if data.full_name is not None:
        u.full_name = data.full_name
    if data.role is not None:
        u.role = data.role
    if data.is_active is not None:
        u.is_active = data.is_active
    if data.password:
        error = _validate_password_strength(data.password)
        if error:
            raise HTTPException(400, error)
        u.hashed_password = hash_password(data.password)
        u.must_change_password = False
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
    db.commit()
    db.refresh(u)
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


class MfaRequireIn(BaseModel):
    required: bool


@router.patch("/{user_id}/mfa-require")
def set_mfa_required(
    user_id: int,
    body: MfaRequireIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin activa/desactiva la obligatoriedad de MFA para la organizacion del usuario."""
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Usuario no encontrado")
    if (current_user.role != UserRole.SUPERADMIN
            and target.organization_id != current_user.organization_id):
        raise HTTPException(403, "No autorizado")
    # Actualizar el flag org_mfa_required en la organizacion del usuario
    if target.organization_id:
        org = db.get(Organization, target.organization_id)
        if org:
            org.mfa_required = body.required
            db.commit()
    log_action(db, current_user.id, "update", "organization",
               str(target.organization_id),
               {"action": "mfa_required_set", "value": body.required})
    db.commit()
    return {"ok": True, "mfa_required": body.required}
