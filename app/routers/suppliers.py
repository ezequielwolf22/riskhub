"""Gestion de proveedores / supply chain — NIS2 Art. 21.2.d."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Supplier, SupplierRisk, User
from app.schemas import SupplierIn, SupplierOut, SupplierUpdate
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


def _next_code(db: Session) -> str:
    n = db.query(Supplier).count() + 1
    return f"SUP-{n:04d}"


@router.get("/", response_model=list[SupplierOut])
def list_suppliers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    risk_level: Optional[SupplierRisk] = None,
    q: Optional[str] = None,
):
    query = filter_by_org(db.query(Supplier), Supplier, current_user)
    if risk_level:
        query = query.filter(Supplier.risk_level == risk_level)
    if q:
        like = f"%{q}%"
        query = query.filter(Supplier.name.ilike(like))
    return query.order_by(Supplier.name).all()


@router.get("/stats/summary")
def suppliers_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    suppliers = filter_by_org(db.query(Supplier), Supplier, current_user).all()
    now = datetime.now(timezone.utc)
    overdue_assessment = sum(
        1 for s in suppliers
        if s.next_assessment_at and s.next_assessment_at.replace(tzinfo=timezone.utc) < now
    )
    critical_high = sum(1 for s in suppliers if s.risk_level in (SupplierRisk.CRITICAL, SupplierRisk.HIGH))
    return {
        "total": len(suppliers),
        "critical_or_high": critical_high,
        "overdue_assessment": overdue_assessment,
    }


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, "Proveedor no encontrado")
    return s


@router.post("/", response_model=SupplierOut)
def create_supplier(body: SupplierIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    s = Supplier(
        code=_next_code(db),
        organization_id=current_user.organization_id,
        name=body.name,
        category=body.category,
        description=body.description,
        services=body.services,
        risk_level=body.risk_level,
        is_critical=body.is_critical,
        certifications=body.certifications,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        contract_ref=body.contract_ref,
        contract_expiry=body.contract_expiry,
        last_assessment_at=body.last_assessment_at,
        next_assessment_at=body.next_assessment_at,
        score=body.score,
        notes=body.notes,
        owner_id=body.owner_id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    log_action(db, current_user.id, "create", "supplier", str(s.id), {"name": s.name})
    return s


@router.patch("/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: int, body: SupplierUpdate,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, "Proveedor no encontrado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    log_action(db, current_user.id, "update", "supplier", str(s.id))
    return s


@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, "Proveedor no encontrado")
    log_action(db, current_user.id, "delete", "supplier", str(supplier_id), {"name": s.name})
    db.delete(s)
    db.commit()
