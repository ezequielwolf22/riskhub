"""Servicio de auditoria: escribe entradas en el log de auditoria."""
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AuditLog


def log_action(
    db: Session,
    user_id: Optional[int],
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    detail: Optional[dict] = None,
) -> None:
    """Registra una accion en el log de auditoria.

    Nota: no hace commit — el caller es responsable del commit.
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail or {},
    )
    db.add(entry)
