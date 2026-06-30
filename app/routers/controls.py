"""Catalogo ISO 27002:2022 + implementaciones especificas de la organizacion."""
import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Control, ControlImplementation, ControlStatus, User, risk_control_table
from app.schemas import (
    ControlImplIn, ControlImplOut, ControlIn, ControlOut,
)
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action
from app.i18n import get_lang, t as _t

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
    limit: int = Query(200, le=2000),
    offset: int = Query(0),
):
    query = db.query(Control)
    if q:
        like = f"%{q}%"
        query = query.filter((Control.name.ilike(like)) | (Control.code.ilike(like)))
    if theme:
        query = query.filter(Control.theme == theme)
    return query.order_by(Control.code).offset(offset).limit(limit).all()


@catalog_router.get("/export-soa-csv")
def export_soa_csv(db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    """Exporta el Statement of Applicability (SoA) como CSV."""
    controls = db.query(Control).order_by(Control.code).all()
    impls = filter_by_org(db.query(ControlImplementation), ControlImplementation, current_user).all()
    impl_by_ctrl = {}
    for i in impls:
        impl_by_ctrl.setdefault(i.control_id, []).append(i)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Codigo", "Nombre", "Tema", "Tipo",
        "Aplicable", "Implementaciones", "Estado_Mejor", "Madurez_Max",
        "Proxima_Revision", "Razon_Inclusion", "Justificacion_Exclusion", "Evidencias",
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
        # SOA ISO 27001:2022 fields (first impl if multiple)
        first_impl = ci_list[0] if ci_list else None
        inclusion_reason = (first_impl.inclusion_reason or "") if first_impl else ""
        excl_just = (first_impl.exclusion_justification or "") if first_impl else ""
        evidence = ""
        if first_impl and first_impl.evidence_refs:
            refs = first_impl.evidence_refs if isinstance(first_impl.evidence_refs, list) else []
            evidence = "; ".join(str(r) for r in refs)
        writer.writerow([
            c.code, c.name, c.theme or "", ",".join(c.control_type or []),
            applicable, len(ci_list), best_status, max_mat, next_rev_str,
            inclusion_reason, excl_just, evidence,
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
    from sqlalchemy import func as _func
    max_code = db.query(_func.max(Control.code)).filter(Control.code.like("CUS.%")).scalar()
    if max_code:
        try:
            n = int(max_code.split(".")[1]) + 1
        except (IndexError, ValueError):
            n = db.query(Control).filter(Control.code.like("CUS.%")).count() + 1
    else:
        n = 1
    return f"CUS.{n:03d}"


class ControlPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_mandatory: Optional[bool] = None


@catalog_router.patch("/catalog/{cid}", response_model=ControlOut)
def patch_control(
    cid: int,
    body: ControlPatch,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    c = db.get(Control, cid)
    if not c:
        raise HTTPException(404, _t("controls.not_found", lang))
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)
    log_action(db, current_user.id, "update", "control", str(cid),
               {"is_mandatory": c.is_mandatory})
    return c


# ---------- IMPLEMENTATIONS ----------

@impl_router.get("/", response_model=list[ControlImplOut])
def list_impls(db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    impls = filter_by_org(db.query(ControlImplementation), ControlImplementation, current_user).order_by(
        ControlImplementation.id.desc()).all()

    # Compute how many risks each control implementation mitigates
    counts_q = (
        db.query(
            risk_control_table.c.control_implementation_id,
            func.count(risk_control_table.c.risk_id),
        )
        .filter(risk_control_table.c.control_implementation_id.in_([i.id for i in impls]))
        .group_by(risk_control_table.c.control_implementation_id)
        .all()
    )
    risk_counts = {cid: cnt for cid, cnt in counts_q}

    result = []
    for impl in impls:
        item = ControlImplOut.model_validate(impl)
        # model_validate returns a Pydantic model which supports field assignment
        result.append(item.model_copy(update={"risk_count": risk_counts.get(impl.id, 0)}))
    return result


def _trigger_compliance_sync(org_id: int) -> None:
    """Dispara sincronizacion de compliance en background tras cambio de control."""
    if not org_id:
        return
    import threading
    from app.database import SessionLocal
    from app.services.compliance_service import auto_update_compliance_from_controls

    def _sync():
        db2 = SessionLocal()
        try:
            auto_update_compliance_from_controls(db2, org_id)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "_trigger_compliance_sync failed for org_id=%d", org_id, exc_info=True
            )
        finally:
            db2.close()

    threading.Thread(target=_sync, daemon=True).start()


def _trigger_risks_recalc_by_ids(risk_ids: list, org_id: int) -> None:
    """Recalcula residual de una lista explicita de risk_ids (usado tras DELETE de control)."""
    import threading
    from app.database import SessionLocal

    def _recalc_risks():
        db2 = SessionLocal()
        try:
            from app.models import Risk, RiskStatus
            from app.routers.risks import _recalc
            risks = db2.query(Risk).filter(
                Risk.id.in_(risk_ids),
                Risk.organization_id == org_id,
                Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
            ).all()
            for risk in risks:
                _recalc(db2, risk)
            if risks:
                db2.commit()
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "_trigger_risks_recalc_by_ids failed for org_id=%d", org_id, exc_info=True
            )
        finally:
            db2.close()

    threading.Thread(target=_recalc_risks, daemon=True).start()


def _trigger_linked_risks_recalc(impl_id: int, org_id: int) -> None:
    """Recalcula residual de todos los riesgos que usan este control.

    Usa _recalc() de risks.py para garantizar logica consistente:
    - contribution real desde risk_control_table (no hardcoded 1.0)
    - nc_penalty_factor y ccm_last_status de ControlImplementation
    """
    import threading
    from app.database import SessionLocal

    def _recalc_risks():
        db2 = SessionLocal()
        try:
            from app.models import Risk, RiskStatus
            from app.routers.risks import _recalc
            import sqlalchemy

            risk_ids = [
                row[0]
                for row in db2.execute(
                    sqlalchemy.text(
                        "SELECT risk_id FROM risk_controls "
                        "WHERE control_implementation_id = :cid"
                    ),
                    {"cid": impl_id},
                ).fetchall()
            ]
            if not risk_ids:
                return

            risks = db2.query(Risk).filter(
                Risk.id.in_(risk_ids),
                Risk.organization_id == org_id,
                Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
            ).all()

            for risk in risks:
                _recalc(db2, risk)

            if risks:
                db2.commit()

        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "_trigger_linked_risks_recalc failed for impl_id=%d", impl_id, exc_info=True
            )
        finally:
            db2.close()

    threading.Thread(target=_recalc_risks, daemon=True).start()


@impl_router.post("/", response_model=ControlImplOut, status_code=201)
def create_impl(data: ControlImplIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    if not db.get(Control, data.control_id):
        raise HTTPException(400, "control_id no existe")
    impl = ControlImplementation(organization_id=current_user.organization_id, **data.model_dump())
    db.add(impl)
    log_action(db, current_user.id, "create", "control_impl", None,
               {"control_id": data.control_id, "name": data.name, "status": str(data.status)})
    db.commit(); db.refresh(impl)
    # Sincronizar compliance automaticamente tras crear un control
    _trigger_compliance_sync(current_user.organization_id)
    return impl


@impl_router.put("/{impl_id}", response_model=ControlImplOut)
def update_impl(impl_id: int, data: ControlImplIn,
                request: Request,
                db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    impl = db.get(ControlImplementation, impl_id)
    if not impl or not check_org_access(impl.organization_id, current_user):
        raise HTTPException(404, _t("controls.implementation_not_found", lang))
    for k, v in data.model_dump().items():
        setattr(impl, k, v)
    log_action(db, current_user.id, "update", "control_impl", str(impl_id),
               {"name": impl.name, "status": str(impl.status), "maturity": impl.maturity})
    db.commit(); db.refresh(impl)
    # Sincronizar compliance automaticamente tras actualizar un control
    _trigger_compliance_sync(impl.organization_id)
    # Recalcular residual de riesgos vinculados a este control
    _trigger_linked_risks_recalc(impl.id, impl.organization_id)
    return impl


@impl_router.post("/{impl_id}/propagate")
def propagate_impl(
    impl_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Propaga el control a riesgos candidatos.
    Paso 1 (sin IA): recalcula residual de riesgos ya vinculados.
    Paso 2 (IA): detecta hasta 50 riesgos candidatos no vinculados, estima contribucion y los vincula.
    """
    lang = get_lang(request)
    impl = db.get(ControlImplementation, impl_id)
    if not impl or not check_org_access(impl.organization_id, current_user):
        raise HTTPException(404, _t("controls.implementation_not_found", lang))
    if impl.status == ControlStatus.NOT_IMPLEMENTED:
        raise HTTPException(400, "El control no esta implementado, no puede propagarse")
    from app.services.control_propagation_service import propagate_control
    result = propagate_control(db, impl_id, current_user.organization_id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Error en propagacion"))
    log_action(db, current_user.id, "propagate", "control_impl", str(impl_id),
               {"linked": result.get("step2_linked", 0), "recalculated": result.get("step1_recalculated", 0)})
    return result


@impl_router.delete("/{impl_id}", status_code=204)
def delete_impl(impl_id: int, request: Request, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    impl = db.get(ControlImplementation, impl_id)
    if not impl or not check_org_access(impl.organization_id, current_user):
        raise HTTPException(404, _t("controls.implementation_not_found", lang))
    name = impl.name
    org_id = impl.organization_id
    # Recopilar risk_ids ANTES del delete (la FK cascade los elimina con el impl)
    import sqlalchemy as _sa
    risk_ids_to_recalc = [
        row[0] for row in db.execute(
            _sa.text("SELECT risk_id FROM risk_controls WHERE control_implementation_id = :cid"),
            {"cid": impl.id},
        ).fetchall()
    ]
    db.delete(impl)
    log_action(db, current_user.id, "delete", "control_impl", str(impl_id), {"name": name})
    db.commit()
    # Recalcular residual de todos los riesgos que usaban este control
    if risk_ids_to_recalc:
        _trigger_risks_recalc_by_ids(risk_ids_to_recalc, org_id)


@catalog_router.get("/stats/by-theme")
def controls_by_theme(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve el resumen de implementaciones por tema ISO 27002 (para el dashboard)."""
    from app.models import ControlStatus
    impls = filter_by_org(db.query(ControlImplementation), ControlImplementation, current_user).all()
    theme_order = ["organizational", "people", "physical", "technological"]
    theme_labels = {
        "organizational": "Organizacional",
        "people": "Personas",
        "physical": "Fisico",
        "technological": "Tecnologico",
    }
    by_theme: dict = {}
    for impl in impls:
        theme = (impl.control.theme if impl.control else None) or "other"
        if theme not in by_theme:
            by_theme[theme] = {"count": 0, "maturity_sum": 0, "implemented": 0}
        by_theme[theme]["count"] += 1
        by_theme[theme]["maturity_sum"] += impl.maturity
        if impl.status == ControlStatus.IMPLEMENTED:
            by_theme[theme]["implemented"] += 1

    result = []
    for theme in theme_order:
        if theme not in by_theme:
            continue
        d = by_theme[theme]
        result.append({
            "theme": theme,
            "label": theme_labels.get(theme, theme.capitalize()),
            "count": d["count"],
            "implemented": d["implemented"],
            "avg_maturity": round(d["maturity_sum"] / d["count"], 1) if d["count"] else 0,
        })
    # Incluir temas no estandar si existen
    for theme, d in by_theme.items():
        if theme not in theme_order:
            result.append({
                "theme": theme,
                "label": theme.capitalize(),
                "count": d["count"],
                "implemented": d["implemented"],
                "avg_maturity": round(d["maturity_sum"] / d["count"], 1) if d["count"] else 0,
            })
    return result
