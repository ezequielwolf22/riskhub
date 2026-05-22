"""Catalogo ISO 27002:2022 + implementaciones especificas de la organizacion."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Control, ControlImplementation, User
from app.schemas import (
    ControlImplIn, ControlImplOut, ControlIn, ControlOut,
)
from app.security import get_current_user, require_analyst

catalog_router = APIRouter(prefix="/api/controls", tags=["controls"])
impl_router = APIRouter(prefix="/api/control-implementations",
                        tags=["control-implementations"])


# ---------- CATALOG ----------

@catalog_router.get("/", response_model=list[ControlOut])
def list_controls(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    q: Optional[str] = None,
    theme: Optional[str] = None,
):
    query = db.query(Control)
    if q:
        like = f"%{q}%"
        query = query.filter((Control.name.ilike(like)) | (Control.code.ilike(like)))
    if theme:
        query = query.filter(Control.theme == theme)
    return query.order_by(Control.code).all()


@catalog_router.post("/", response_model=ControlOut, status_code=201,
                     dependencies=[Depends(require_analyst)])
def create_control(data: ControlIn, db: Session = Depends(get_db)):
    code = data.code or _next_custom_code(db)
    if db.query(Control).filter(Control.code == code).first():
        raise HTTPException(400, f"Ya existe control con codigo {code}")
    c = Control(**data.model_dump(exclude={"code"}), code=code, is_custom=True)
    db.add(c); db.commit(); db.refresh(c)
    return c


def _next_custom_code(db: Session) -> str:
    n = db.query(Control).filter(Control.code.like("CUS.%")).count() + 1
    return f"CUS.{n:03d}"


# ---------- IMPLEMENTATIONS ----------

@impl_router.get("/", response_model=list[ControlImplOut])
def list_impls(db: Session = Depends(get_db),
               _: User = Depends(get_current_user)):
    return db.query(ControlImplementation).order_by(
        ControlImplementation.id.desc()).all()


@impl_router.post("/", response_model=ControlImplOut, status_code=201,
                  dependencies=[Depends(require_analyst)])
def create_impl(data: ControlImplIn, db: Session = Depends(get_db)):
    if not db.get(Control, data.control_id):
        raise HTTPException(400, "control_id no existe")
    impl = ControlImplementation(**data.model_dump())
    db.add(impl); db.commit(); db.refresh(impl)
    return impl


@impl_router.put("/{impl_id}", response_model=ControlImplOut,
                 dependencies=[Depends(require_analyst)])
def update_impl(impl_id: int, data: ControlImplIn,
                db: Session = Depends(get_db)):
    impl = db.get(ControlImplementation, impl_id)
    if not impl:
        raise HTTPException(404, "Implementacion no encontrada")
    for k, v in data.model_dump().items():
        setattr(impl, k, v)
    db.commit(); db.refresh(impl)
    return impl


@impl_router.delete("/{impl_id}", status_code=204,
                    dependencies=[Depends(require_analyst)])
def delete_impl(impl_id: int, db: Session = Depends(get_db)):
    impl = db.get(ControlImplementation, impl_id)
    if not impl:
        raise HTTPException(404, "Implementacion no encontrada")
    db.delete(impl); db.commit()
