"""Gestion de licencias por organizacion — CRUD + auditoría."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import License, User, UserRole
from app.schemas import LicenseAuditOut, LicenseIn, LicenseOut, LicenseUpdate
from app.security import get_current_user, require_superadmin
from app.services import license_service as lic_svc

router = APIRouter(prefix="/api/licenses", tags=["licenses"])


# ── Obtener licencia de una organizacion (superadmin) ──────────────────

@router.get("/{org_id}", response_model=LicenseOut)
def get_license(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Obtiene la licencia de una organizacion."""
    license = lic_svc.get_license(db, org_id)
    if not license:
        raise HTTPException(404, "Licencia no encontrada")
    return license


# ── Crear/asignar licencia a una organizacion (superadmin) ─────────────

@router.post("/{org_id}", response_model=LicenseOut, status_code=201)
def create_or_assign_license(
    org_id: int,
    data: LicenseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Crea o asigna una licencia a una organizacion."""
    from app.models import Organization
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organizacion no encontrada")

    existing = lic_svc.get_license(db, org_id)
    if existing:
        raise HTTPException(400, "La organizacion ya tiene una licencia asignada")

    license = lic_svc.create_license_for_org(
        db, org_id, data.plan, data.expires_at
    )

    # Registrar auditoria
    from app.models import LicenseAudit
    audit = LicenseAudit(
        organization_id=org_id,
        changed_by_id=current_user.id,
        plan_new=data.plan,
        status_new="active",
        expires_at_new=data.expires_at,
        reason=data.reason or "initial_assignment",
    )
    db.add(audit)
    db.commit()

    return license


# ── Actualizar licencia (superadmin) ──────────────────────────────────

@router.patch("/{org_id}", response_model=LicenseOut)
def update_license(
    org_id: int,
    data: LicenseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Actualiza una licencia (plan, estado, fecha de vencimiento)."""
    license = lic_svc.get_license(db, org_id)
    if not license:
        raise HTTPException(404, "Licencia no encontrada")

    license = lic_svc.update_license(
        db, org_id,
        plan=data.plan,
        status=data.status,
        expires_at=data.expires_at,
        reason=data.reason,
        changed_by_id=current_user.id,
    )
    return license


# ── Historial de auditoria (superadmin) ──────────────────────────────

@router.get("/{org_id}/audit", response_model=list[LicenseAuditOut])
def get_license_audit_history(
    org_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Obtiene el historial de cambios de una licencia."""
    history = lic_svc.get_license_audit_history(db, org_id, limit)
    return history


# ── Verificar estado de licencia (util para frontend) ──────────────────

class LicenseStatusCheck(object):
    pass


@router.get("/{org_id}/status")
def check_license_status(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verifica si la licencia esta activa (para uso en frontend)."""
    # El usuario debe ser superadmin o pertenece a la org
    if current_user.role != UserRole.SUPERADMIN and current_user.organization_id != org_id:
        raise HTTPException(403, "No autorizado")

    is_active = lic_svc.is_license_active(db, org_id)
    license = lic_svc.get_license(db, org_id)

    return {
        "is_active": is_active,
        "organization_id": org_id,
        "license": license,
    }
