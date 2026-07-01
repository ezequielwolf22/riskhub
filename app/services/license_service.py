"""Servicio de gestión de licencias."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import License, LicenseAudit, LicenseStatus, Organization


def get_license(db: Session, org_id: int) -> Optional[License]:
    """Obtiene la licencia de una organizacion."""
    return db.query(License).filter(License.organization_id == org_id).first()


def is_license_active(db: Session, org_id: int) -> bool:
    """Verifica si la licencia de una org esta activa y no ha expirado."""
    license = get_license(db, org_id)
    if not license:
        return False
    if license.status != LicenseStatus.ACTIVE:
        return False
    if license.expires_at and license.expires_at <= datetime.now(timezone.utc):
        return False
    return True


def create_license_for_org(db: Session, org_id: int, plan: str, expires_at: Optional[datetime] = None):
    """Crea una licencia inicial para una organizacion."""
    existing = get_license(db, org_id)
    if existing:
        return existing

    license = License(
        organization_id=org_id,
        plan=plan,
        status=LicenseStatus.ACTIVE,
        expires_at=expires_at,
    )
    db.add(license)
    db.commit()
    db.refresh(license)
    return license


def update_license(
    db: Session,
    org_id: int,
    plan: Optional[str] = None,
    status: Optional[LicenseStatus] = None,
    expires_at: Optional[datetime] = None,
    reason: Optional[str] = None,
    changed_by_id: Optional[int] = None,
):
    """Actualiza una licencia y registra en auditoria."""
    license = get_license(db, org_id)
    if not license:
        raise ValueError(f"Licencia no encontrada para org {org_id}")

    # Guardar valores antiguos para auditoria
    old_plan = license.plan
    old_status = license.status
    old_expires_at = license.expires_at

    # Actualizar valores
    if plan is not None:
        license.plan = plan
    if status is not None:
        license.status = status
    if expires_at is not None:
        license.expires_at = expires_at

    license.updated_by_id = changed_by_id
    license.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(license)

    # Registrar en auditoria
    audit = LicenseAudit(
        organization_id=org_id,
        changed_by_id=changed_by_id,
        plan_old=old_plan if plan != old_plan else None,
        plan_new=plan if plan != old_plan else None,
        status_old=old_status.value if status != old_status else None,
        status_new=status.value if status != old_status else None,
        expires_at_old=old_expires_at if expires_at != old_expires_at else None,
        expires_at_new=expires_at if expires_at != old_expires_at else None,
        reason=reason,
    )
    db.add(audit)
    db.commit()

    return license


def auto_expire_licenses(db: Session):
    """Job que marca como EXPIRED las licencias vencidas a las que no se les ha marcado manualmente."""
    now = datetime.now(timezone.utc)
    expired_licenses = db.query(License).filter(
        License.status == LicenseStatus.ACTIVE,
        License.expires_at <= now,
    ).all()

    for license in expired_licenses:
        license.status = LicenseStatus.EXPIRED
        license.updated_at = now

        audit = LicenseAudit(
            organization_id=license.organization_id,
            changed_by_id=None,  # Auto-expiration (sistema)
            status_old=LicenseStatus.ACTIVE.value,
            status_new=LicenseStatus.EXPIRED.value,
            reason="expiration_auto",
        )
        db.add(audit)

    if expired_licenses:
        db.commit()
        import logging
        logger = logging.getLogger("riskhub.licenses")
        logger.info(f"Auto-expiradas {len(expired_licenses)} licencias vencidas")

    return len(expired_licenses)


def get_licenses_expiring_soon(db: Session, days: int = 30) -> list[License]:
    """Licencias activas que vencen dentro de `days` y aun no recibieron aviso."""
    now = datetime.now(timezone.utc)
    threshold = now + timedelta(days=days)
    return db.query(License).filter(
        License.status == LicenseStatus.ACTIVE,
        License.expires_at.isnot(None),
        License.expires_at <= threshold,
        License.expires_at > now,
        License.last_reminder_sent_at.is_(None),
    ).all()


def mark_reminder_sent(db: Session, license: License) -> None:
    license.last_reminder_sent_at = datetime.now(timezone.utc)
    db.commit()


def get_license_audit_history(db: Session, org_id: int, limit: int = 50):
    """Obtiene el historial de cambios de una licencia."""
    return db.query(LicenseAudit).filter(
        LicenseAudit.organization_id == org_id
    ).order_by(LicenseAudit.changed_at.desc()).limit(limit).all()
