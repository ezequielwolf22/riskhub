"""Servicio de auditoria: escribe entradas en el log de auditoria."""
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AuditLog


def diff_objects(before: dict, after: dict) -> tuple:
    """Returns (old_value, new_value) containing only changed fields."""
    old, new = {}, {}
    all_keys = set(before) | set(after)
    for k in all_keys:
        v_before = before.get(k)
        v_after = after.get(k)
        if v_before != v_after:
            old[k] = v_before
            new[k] = v_after
    return old, new


def log_action(
    db: Session,
    user_id: Optional[int],
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    detail: Optional[dict] = None,
    organization_id: Optional[int] = None,
    old_value: Optional[dict] = None,
    new_value: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Registra una accion en el log de auditoria.

    Nota: no hace commit — el caller es responsable del commit.
    Si no se provee organization_id explicitamente, se intenta resolver
    a partir del user_id para garantizar el aislamiento multi-tenant.
    """
    resolved_org_id = organization_id
    if resolved_org_id is None and user_id is not None:
        from app.models import User as _User
        user = db.query(_User).filter_by(id=user_id).first()
        if user:
            resolved_org_id = user.organization_id

    entry = AuditLog(
        user_id=user_id,
        organization_id=resolved_org_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail or {},
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
    )
    db.add(entry)
