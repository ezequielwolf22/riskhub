"""Catalogo ISO 27002:2022 + implementaciones especificas de la organizacion."""
import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Control, ControlImplementation, User
from app.schemas import (
    ControlImplIn, ControlImplOut, ControlIn, ControlOut,
)
from app.security import get_current_user, require_analyst
from app.services.audit_service import log_action

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


@catalog_router.get("/export-soa-csv")
def export_soa_csv(db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    """Exporta el Statement of Applicability (SoA) como CSV."""
    controls = db.query(Control).order_by(Control.code).all()
    impls = db.query(ControlImplementation).all()
    impl_by_ctrl = {}
    for i in impls:
        impl_by_ctrl.setdefault(i.control_id, []).append(i)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Codigo", "Nombre", "Tema", "Tipo",
        "Aplicable", "Implementaciones", "Estado_Mejor", "Madurez_Max",
        "Proxima_Revision",
    ])
    for c in controls:
        ci_list = impl_by_ctrl.get(c.id, [])
        applicable = "Si" if ci_list else "No"
        statuses = [i.status.value for i in ci_list] if ci_list else []
        best_status = (
            "implemented" if "implemented" in statuses else
            "partial" if "partial" in statuses else
            "planned" if "planned" in statuses else
            "not_implemented" if statuses else ""
        )
        max_mat = max((i.maturity for i in ci_list), default=0)
        next_revs = [i.next_review for i in ci_list if i.next_review]
        next_rev_str = min(next_revs).strftime("%Y-%m-%d") if next_revs else ""
        writer.writerow([
            c.code, c.name, c.theme or "", ",".join(c.control_type or []),
            applicable, len(ci_list), best_status, max_mat, next_rev_str,
        ])

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    fname = f"soa_{ts}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@catalog_router.post("/", response_model=ControlOut, status_code=201)
def create_control(data: ControlIn, db: Session = Depends(get_db),
                   current_user: User = Depends(require_analyst)):
    code = data.code or _next_custom_code(db)
    if db.query(Control).filter(Control.code == code).first():
        raise HTTPException(400, f"Ya existe control con codigo {code}")
    c = Control(**data.model_dump(exclude={"code"}), code=code, is_custom=True)
    db.add(c)
    log_action(db, current_user.id, "create", "control", None,
               {"code": code, "name": data.name})
    db.commit(); db.refresh(c)
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


@impl_router.post("/", response_model=ControlImplOut, status_code=201)
def create_impl(data: ControlImplIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    if not db.get(Control, data.control_id):
        raise HTTPException(400, "control_id no existe")
    impl = ControlImplementation(**data.model_dump())
    db.add(impl)
    log_action(db, current_user.id, "create", "control_impl", None,
               {"control_id": data.control_id, "name": data.name, "status": str(data.status)})
    db.commit(); db.refresh(impl)
    return impl


@impl_router.put("/{impl_id}", response_model=ControlImplOut)
def update_impl(impl_id: int, data: ControlImplIn,
                db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    impl = db.get(ControlImplementation, impl_id)
    if not impl:
        raise HTTPException(404, "Implementacion no encontrada")
    for k, v in data.model_dump().items():
        setattr(impl, k, v)
    log_action(db, current_user.id, "update", "control_impl", str(impl_id),
               {"name": impl.name, "status": str(impl.status), "maturity": impl.maturity})
    db.commit(); db.refresh(impl)
    return impl


@impl_router.delete("/{impl_id}", status_code=204)
def delete_impl(impl_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    impl = db.get(ControlImplementation, impl_id)
    if not impl:
        raise HTTPException(404, "Implementacion no encontrada")
    name = impl.name
    db.delete(impl)
    log_action(db, current_user.id, "delete", "control_impl", str(impl_id), {"name": name})
    db.commit()
