"""Clasificaciones del modulo de proveedores (feedback cliente OFA, puntos 2/5/6).

Fuente unica de los valores canonicos y del computo de review_status, para que
motor, routers, import y UI hablen el mismo idioma. Las etiquetas visibles viven
en el frontend (i18n); aqui solo los valores y la logica determinista.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

# Punto 2 — dos clasificaciones INDEPENDIENTES
BUSINESS_IMPORTANCE_LEVELS = ["not_relevant", "normal", "important", "critical"]
SECURITY_RISK_LEVELS = ["very_low", "low", "medium", "high", "critical"]

# Punto 5 — frecuencia de revision y estados computados
REVIEW_FREQUENCIES = ["monthly", "quarterly", "semiannual", "annual", "biennial", "none"]
REVIEW_STATUSES = [
    "active",
    "review_due_90",
    "review_due_60",
    "review_due_30",
    "under_review",
    "review_overdue",
]

# Punto 6 — estado del flujo de seguridad (independiente del lifecycle operativo)
SECURITY_STATUSES = [
    "draft",
    "pending_supplier_response",
    "pending_security_review",
    "pending_additional_info",
    "security_approved",
    "security_approved_with_mitigation",
    "risk_accepted",
    "rejected",
    "offboarded",
]

# Estados de seguridad que representan una revision en curso
_UNDER_REVIEW_SECURITY = {"pending_security_review", "pending_additional_info"}

# Punto 13 / general — estado del acuerdo
AGREEMENT_STATUSES = ["none", "draft", "pending_signature", "signed", "expired"]

# Punto 18 — quien tiene la siguiente accion, por estado de seguridad
_NEXT_ACTION_BY_STATUS = {
    "draft": "internal",
    "pending_supplier_response": "supplier",
    "pending_security_review": "security",
    "pending_additional_info": "supplier",
    "security_approved": "none",
    "security_approved_with_mitigation": "internal",
    "risk_accepted": "none",
    "rejected": "none",
    "offboarded": "none",
}

# Meses por frecuencia, para proyectar la proxima revision
_FREQUENCY_MONTHS = {
    "monthly": 1,
    "quarterly": 3,
    "semiannual": 6,
    "annual": 12,
    "biennial": 24,
}


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def compute_review_status(
    next_review_at: Optional[datetime],
    security_status: Optional[str] = None,
    relationship_status: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """Estado de revision derivado de la fecha de proxima revision y el flujo.

    Una revision en curso (security_status o relationship_status) manda sobre la
    proximidad de fecha; sin fecha, se considera 'active'.
    """
    rel = (relationship_status or "").lower()
    sec = (security_status or "").lower()
    if rel == "under_review" or sec in _UNDER_REVIEW_SECURITY:
        return "under_review"
    if not next_review_at:
        return "active"
    now = now or datetime.now(timezone.utc)
    days = (_as_utc(next_review_at) - now).days
    if days < 0:
        return "review_overdue"
    if days <= 30:
        return "review_due_30"
    if days <= 60:
        return "review_due_60"
    if days <= 90:
        return "review_due_90"
    return "active"


def next_action_owner(security_status: Optional[str]) -> str:
    """Quien tiene la siguiente accion (punto 18): internal|supplier|security|none."""
    return _NEXT_ACTION_BY_STATUS.get((security_status or "").lower(), "internal")


def frequency_to_months(frequency: Optional[str]) -> Optional[int]:
    return _FREQUENCY_MONTHS.get((frequency or "").lower())
