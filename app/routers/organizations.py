"""Gestion de organizaciones / tenants — administracion multi-org."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AiCallLog, Organization, User, UserRole,
)
from app.schemas import OrganizationIn, OrganizationOut, OrganizationUpdate
from app.security import get_current_user, require_admin, require_superadmin
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


def _to_out(org: Organization, db: Session) -> OrganizationOut:
    user_count = db.query(User).filter(User.organization_id == org.id).count()
    token_usage = db.query(
        func.coalesce(func.sum(AiCallLog.prompt_tokens + AiCallLog.completion_tokens), 0)
    ).filter(AiCallLog.organization_id == org.id).scalar() or 0
    o = OrganizationOut.model_validate(org)
    return o.model_copy(update={"user_count": user_count, "token_usage": token_usage})


# ── Listar (superadmin ve todo; admin solo ve la suya) ─────────────────────────

@router.get("/", response_model=list[OrganizationOut])
def list_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if current_user.role == UserRole.SUPERADMIN:
        orgs = db.query(Organization).order_by(Organization.created_at.desc()).all()
    else:
        orgs = db.query(Organization).filter(
            Organization.id == current_user.organization_id
        ).all()
    return [_to_out(o, db) for o in orgs]


@router.get("/current", response_model=OrganizationOut)
def get_current_org(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve la organizacion del usuario autenticado."""
    if not current_user.organization_id:
        raise HTTPException(404, "El usuario no pertenece a ninguna organizacion")
    org = db.get(Organization, current_user.organization_id)
    if not org:
        raise HTTPException(404, "Organizacion no encontrada")
    return _to_out(org, db)


@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organizacion no encontrada")
    # Admin solo puede ver su propia org
    if current_user.role != UserRole.SUPERADMIN and org.id != current_user.organization_id:
        raise HTTPException(403, "No autorizado")
    return _to_out(org, db)


# ── Crear (solo superadmin) ─────────────────────────────────────────────────────

@router.post("/", response_model=OrganizationOut, status_code=201)
def create_organization(
    data: OrganizationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    if data.domain:
        existing = db.query(Organization).filter(
            Organization.domain == data.domain.lower()
        ).first()
        if existing:
            raise HTTPException(400, f"Ya existe una organizacion con el dominio {data.domain}")
    org = Organization(
        name=data.name,
        domain=data.domain.lower() if data.domain else None,
        plan=data.plan,
        is_active=data.is_active,
        max_users=data.max_users,
    )
    db.add(org)
    log_action(db, current_user.id, "create", "organization", None,
               {"name": data.name, "domain": data.domain, "plan": data.plan})
    db.commit()
    db.refresh(org)
    return _to_out(org, db)


# ── Actualizar ─────────────────────────────────────────────────────────────────

@router.patch("/{org_id}", response_model=OrganizationOut)
def update_organization(
    org_id: int,
    data: OrganizationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organizacion no encontrada")
    # Admin solo puede editar su propia org; superadmin puede editar cualquiera
    if current_user.role != UserRole.SUPERADMIN and org.id != current_user.organization_id:
        raise HTTPException(403, "No autorizado")
    # Admin no puede cambiar plan ni max_users (solo superadmin)
    if current_user.role != UserRole.SUPERADMIN:
        data.plan = None
        data.max_users = None

    if data.name is not None:
        org.name = data.name
    if data.domain is not None:
        org.domain = data.domain.lower()
    if data.plan is not None:
        org.plan = data.plan
    if data.is_active is not None:
        org.is_active = data.is_active
    if data.max_users is not None:
        org.max_users = data.max_users

    log_action(db, current_user.id, "update", "organization", str(org_id),
               data.model_dump(exclude_none=True))
    db.commit()
    db.refresh(org)
    return _to_out(org, db)


# ── Desactivar / eliminar (solo superadmin) ────────────────────────────────────

@router.delete("/{org_id}", status_code=204)
def delete_organization(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organizacion no encontrada")
    # Seguridad: no eliminar la org del superadmin
    if org.id == current_user.organization_id:
        raise HTTPException(400, "No puedes eliminar tu propia organizacion")
    log_action(db, current_user.id, "delete", "organization", str(org_id),
               {"name": org.name})
    # Desactivar en lugar de borrar fisicamente para preservar integridad referencial
    org.is_active = False
    db.commit()


# ── Usuarios de una organizacion (superadmin) ─────────────────────────────────

@router.get("/{org_id}/users")
def list_org_users(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if current_user.role != UserRole.SUPERADMIN and org_id != current_user.organization_id:
        raise HTTPException(403, "No autorizado")
    users = db.query(User).filter(User.organization_id == org_id).order_by(User.created_at).all()
    return [
        {
            "id": u.id, "email": u.email, "full_name": u.full_name,
            "role": u.role.value, "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


class MoveUserIn(BaseModel):
    target_org_id: int


@router.patch("/{org_id}/users/{user_id}/move")
def move_user_to_org(
    org_id: int,
    user_id: int,
    body: MoveUserIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Transfiere un usuario a otra organizacion (solo superadmin)."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    if user.organization_id != org_id:
        raise HTTPException(400, "El usuario no pertenece a la organizacion indicada")
    target_org = db.get(Organization, body.target_org_id)
    if not target_org:
        raise HTTPException(404, "Organizacion destino no encontrada")
    old_org = user.organization_id
    user.organization_id = body.target_org_id
    log_action(db, current_user.id, "update", "user", str(user_id),
               {"action": "move_org", "from": old_org, "to": body.target_org_id})
    db.commit()
    return {"ok": True, "user_id": user_id, "organization_id": body.target_org_id}


# ── Estadisticas de uso de tokens por org (superadmin) ────────────────────────

@router.get("/{org_id}/stats")
def org_stats(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if current_user.role != UserRole.SUPERADMIN and org_id != current_user.organization_id:
        raise HTTPException(403, "No autorizado")
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organizacion no encontrada")

    user_count = db.query(User).filter(User.organization_id == org_id).count()
    active_users = db.query(User).filter(
        User.organization_id == org_id, User.is_active.is_(True)
    ).count()

    token_rows = db.query(
        func.coalesce(func.sum(AiCallLog.prompt_tokens), 0),
        func.coalesce(func.sum(AiCallLog.completion_tokens), 0),
        func.count(AiCallLog.id),
    ).filter(AiCallLog.organization_id == org_id).first()
    prompt_tokens, completion_tokens, ai_calls = token_rows or (0, 0, 0)

    return {
        "organization_id": org_id,
        "name": org.name,
        "plan": org.plan,
        "is_active": org.is_active,
        "max_users": org.max_users,
        "user_count": user_count,
        "active_users": active_users,
        "ai_calls": ai_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": (prompt_tokens or 0) + (completion_tokens or 0),
    }
