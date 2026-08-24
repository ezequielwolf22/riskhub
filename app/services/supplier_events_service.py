"""Timeline / historial de proveedores (feedback cliente, punto 12).

Registro cronologico auditable. Muchos eventos se generan automaticamente desde
los hooks ya existentes (cambios de estado, propiedad, contrato, revisiones,
reclasificaciones); tambien admite entradas manuales.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Supplier, SupplierEvent

logger = logging.getLogger(__name__)

EVENT_TYPES = [
    "security_incident",
    "sla_breach",
    "ownership_change",
    "contract_change",
    "review_completed",
    "risk_reclassified",
    "status_change",
    "assessment_completed",
    "note",
    "other",
]


def log_event(
    db: Session,
    supplier: Supplier,
    event_type: str,
    title: str,
    *,
    description: Optional[str] = None,
    detail: Optional[dict] = None,
    source: str = "manual",
    ref_type: Optional[str] = None,
    ref_id: Optional[int] = None,
    user_id: Optional[int] = None,
    occurred_at: Optional[datetime] = None,
    commit: bool = True,
) -> SupplierEvent:
    """Registra un evento en el timeline del proveedor. Nunca lanza al llamante."""
    ev = SupplierEvent(
        organization_id=supplier.organization_id,
        supplier_id=supplier.id,
        event_type=event_type if event_type in EVENT_TYPES else "other",
        title=title[:255],
        description=description,
        detail=detail,
        source=source,
        ref_type=ref_type,
        ref_id=ref_id,
        created_by_id=user_id,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    db.add(ev)
    if commit:
        db.commit()
        db.refresh(ev)
    return ev


def log_event_safe(db: Session, supplier: Supplier, event_type: str, title: str, **kwargs) -> None:
    """Variante que engulle errores: el timeline nunca debe romper el flujo principal."""
    try:
        log_event(db, supplier, event_type, title, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SupplierEvent log failed for supplier %s: %s",
                       getattr(supplier, "id", "?"), exc)


def list_events(db: Session, supplier_id: int, org_id: Optional[int], limit: int = 200):
    q = db.query(SupplierEvent).filter(SupplierEvent.supplier_id == supplier_id)
    if org_id is not None:
        q = q.filter(SupplierEvent.organization_id == org_id)
    return q.order_by(SupplierEvent.occurred_at.desc()).limit(limit).all()
