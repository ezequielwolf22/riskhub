"""Audit log con filtrado por entidad, usuario y rango de fechas."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditLog, User
from app.security import get_current_user

router = APIRouter(prefix="/api/audit-log", tags=["audit-log"])


class AuditLogEntry(BaseModel):
    id: int
    timestamp: datetime
    user_id: Optional[int]
    organization_id: Optional[int]
    action: str
    entity_type: str
    entity_id: Optional[str]
    detail: Optional[dict]
    old_value: Optional[dict]
    new_value: Optional[dict]
    ip_address: Optional[str]

    class Config:
        from_attributes = True


@router.get("", response_model=List[AuditLogEntry])
def list_audit_log(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista el log de auditoria filtrado por organizacion del usuario autenticado."""
    q = db.query(AuditLog).filter(
        AuditLog.organization_id == current_user.organization_id
    )
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if action:
        q = q.filter(AuditLog.action == action)
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            q = q.filter(AuditLog.timestamp >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            q = q.filter(AuditLog.timestamp <= dt_to)
        except ValueError:
            pass
    entries = (
        q.order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return entries


@router.get("/entity/{entity_type}/{entity_id}", response_model=List[AuditLogEntry])
def get_entity_history(
    entity_type: str,
    entity_id: str,
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Historial completo de cambios de una entidad especifica."""
    entries = (
        db.query(AuditLog)
        .filter(
            AuditLog.organization_id == current_user.organization_id,
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        )
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return entries
