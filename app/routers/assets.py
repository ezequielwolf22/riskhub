"""CRUD de activos + import CSV/Excel."""
import io
from typing import Optional

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from sqlalchemy import func
from app.models import Asset, AssetType, AiDocumentStatus, Risk, User
from app.schemas import AssetIn, AssetOut, ImportResult
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action
from app.services.risk_auto_generator import auto_generate_risks_for_asset


class BulkDeleteIn(BaseModel):
    ids: list[int]

router = APIRouter(prefix="/api/assets", tags=["assets"])


def _next_code(db: Session, org_id: int) -> str:
    n = db.query(Asset).filter(Asset.organization_id == org_id).count() + 1
    return f"AST-{n:04d}"


def _to_out(a: Asset, risk_count: int = 0) -> AssetOut:
    return AssetOut.model_validate({
        **{k: getattr(a, k) for k in AssetOut.model_fields if k not in ("value_max", "risk_count")},
        "value_max": a.value_max,
        "risk_count": risk_count,
    })


@router.get("/", response_model=list[AssetOut])
def list_assets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    q: Optional[str] = None,
    asset_type: Optional[AssetType] = None,
    limit: int = Query(200, le=10000),
):
    query = filter_by_org(db.query(Asset), Asset, current_user)
    # Excluir activos representativos de grupos (virtuales, solo para analisis de riesgo)
    query = query.filter(Asset.is_group_representative.is_(False))
    if q:
        like = f"%{q}%"
        query = query.filter((Asset.name.ilike(like)) | (Asset.code.ilike(like))
                             | (Asset.description.ilike(like)))
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)
    assets = query.order_by(Asset.code).limit(limit).all()

    # Compute risk counts in a single query
    counts_q = (
        db.query(Risk.asset_id, func.count(Risk.id))
        .filter(Risk.asset_id.in_([a.id for a in assets]))
        .group_by(Risk.asset_id)
        .all()
    )
    risk_counts = {asset_id: cnt for asset_id, cnt in counts_q}
    return [_to_out(a, risk_counts.get(a.id, 0)) for a in assets]


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: int, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    a = db.get(Asset, asset_id)
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Activo no encontrado")
    return _to_out(a)


@router.post("/", response_model=AssetOut, status_code=201)
def create_asset(data: AssetIn, background_tasks: BackgroundTasks,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(require_analyst)):
    org_id = current_user.organization_id
    code = data.code or _next_code(db, org_id)
    if db.query(Asset).filter(Asset.code == code, Asset.organization_id == org_id).first():
        raise HTTPException(400, f"Ya existe activo con codigo {code}")
    payload = data.model_dump(exclude={"owner_ids"})
    payload["code"] = code
    payload["organization_id"] = current_user.organization_id
    a = Asset(**payload)
    db.add(a)
    log_action(db, current_user.id, "create", "asset", None,
               {"code": code, "name": data.name, "asset_type": str(data.asset_type)})
    db.commit(); db.refresh(a)
    # Auto-analisis de riesgos IA al crear el activo (v1.7.6)
    background_tasks.add_task(_run_asset_analysis_bg, a.id)
    return _to_out(a)


@router.put("/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: int, data: AssetIn, background_tasks: BackgroundTasks,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(require_analyst)):
    a = db.get(Asset, asset_id)
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Activo no encontrado")
    for k, v in data.model_dump(exclude={"owner_ids", "code"}).items():
        setattr(a, k, v)
    # Resetear estado IA para indicar que el analisis esta desactualizado
    a.ai_risk_status = None
    a.ai_risk_summary = None
    log_action(db, current_user.id, "update", "asset", str(asset_id),
               {"code": a.code, "name": a.name})
    db.commit(); db.refresh(a)
    # Re-analizar riesgos IA cuando el activo cambia (v1.7.6)
    background_tasks.add_task(_run_asset_analysis_bg, asset_id)
    return _to_out(a)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(require_analyst)):
    a = db.get(Asset, asset_id)
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Activo no encontrado")
    code, name = a.code, a.name
    db.query(Risk).filter_by(asset_id=asset_id).update({"asset_id": None}, synchronize_session=False)
    db.delete(a)
    log_action(db, current_user.id, "delete", "asset", str(asset_id),
               {"code": code, "name": name})
    db.commit()


@router.post("/bulk-delete")
def bulk_delete_assets(
    data: BulkDeleteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Elimina multiples activos a la vez."""
    deleted = 0
    errors = []
    for aid in data.ids:
        a = db.get(Asset, aid)
        if not a:
            errors.append(f"Activo {aid} no encontrado")
            continue
        if not check_org_access(a.organization_id, current_user):
            errors.append(f"Activo {aid}: sin permiso")
            continue
        db.query(Risk).filter_by(asset_id=aid).update({"asset_id": None}, synchronize_session=False)
        log_action(db, current_user.id, "delete", "asset", str(aid),
                   {"code": a.code, "name": a.name})
        db.delete(a)
        deleted += 1
    db.commit()
    return {"deleted": deleted, "errors": errors}


# -------- IMPORT/EXPORT --------

EXPECTED_COLUMNS = [
    "name", "asset_type", "description", "category", "location",
    "business_process", "classification",
    "value_confidentiality", "value_integrity", "value_availability",
    "value_authenticity", "value_accountability",
]


@router.get("/import/template", response_class=StreamingResponse)
def download_template(_: User = Depends(require_analyst)):
    """Descarga plantilla CSV con cabeceras y ejemplo."""
    rows = [
        EXPECTED_COLUMNS,
        ["Servidor ERP", "support_hardware", "Servidor principal ERP",
         "Infraestructura", "CPD Madrid", "Procesos administrativos",
         "Confidencial", "3", "4", "4", "2", "2"],
    ]
    buf = io.StringIO()
    pd.DataFrame(rows[1:], columns=rows[0]).to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=assets_template.csv"},
    )


@router.post("/import", response_model=ImportResult)
async def import_assets(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Importa activos desde CSV o Excel."""
    content = await file.read()
    fname = (file.filename or "").lower()
    try:
        if fname.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        elif fname.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            raise HTTPException(400, "Formato no soportado. Usa CSV o XLSX.")
    except Exception as e:
        raise HTTPException(400, f"No se ha podido leer el fichero: {e}")

    missing = [c for c in ["name", "asset_type"] if c not in df.columns]
    if missing:
        raise HTTPException(400, f"Faltan columnas obligatorias: {missing}")

    result = ImportResult(total=len(df), created=0, updated=0, skipped=0, errors=[])
    # Recopilar IDs de activos creados/actualizados para lanzar analisis IA (v1.7.6)
    analyzed_ids: list[int] = []

    for idx, row in df.iterrows():
        try:
            atype_raw = str(row["asset_type"]).strip().lower()
            try:
                atype = AssetType(atype_raw)
            except ValueError:
                result.skipped += 1
                result.errors.append(f"Fila {idx+2}: asset_type invalido '{atype_raw}'")
                continue
            payload = {
                "name": str(row["name"]),
                "asset_type": atype,
            }
            for col in EXPECTED_COLUMNS:
                if col in df.columns and pd.notna(row.get(col)):
                    val = row[col]
                    if col.startswith("value_"):
                        val = int(val)
                    payload[col] = val
            # Hacer override de los dos primeros si quedaron sobreescritos
            payload["name"] = str(row["name"])
            payload["asset_type"] = atype

            org_id = current_user.organization_id
            code = str(row["code"]).strip() if "code" in df.columns and pd.notna(row.get("code")) else _next_code(db, org_id)
            existing = db.query(Asset).filter(Asset.code == code, Asset.organization_id == org_id).first()
            if existing:
                if check_org_access(existing.organization_id, current_user):
                    for k, v in payload.items():
                        setattr(existing, k, v)
                    # Resetear estado IA para indicar re-analisis pendiente
                    existing.ai_risk_status = None
                    existing.ai_risk_summary = None
                    analyzed_ids.append(existing.id)
                    result.updated += 1
                else:
                    result.skipped += 1
                    result.errors.append(f"Fila {idx+2}: activo {code} pertenece a otra organizacion")
            else:
                a = Asset(code=code, organization_id=org_id, **payload)
                db.add(a); db.flush()
                analyzed_ids.append(a.id)
                result.created += 1
        except Exception as e:
            result.skipped += 1
            result.errors.append(f"Fila {idx+2}: {e}")

    db.commit()
    # Auto-analisis de riesgos IA para cada activo importado (v1.7.6)
    if background_tasks and analyzed_ids:
        for aid in analyzed_ids:
            background_tasks.add_task(_run_asset_analysis_bg, aid)
    return result


def _run_asset_analysis_bg(asset_id: int) -> None:
    """Wrapper background para auto-generar riesgos de un activo.

    El análisis IA de activos es ahora manual (botón 'Analizar con IA')
    para evitar consumo masivo de tokens en creaciones en lote.
    """
    db = SessionLocal()
    try:
        # Auto-generar riesgos regla (activo × amenazas) — sin IA, pura lógica
        asset = db.get(Asset, asset_id)
        if asset:
            auto_generate_risks_for_asset(db, asset)
    except Exception:
        pass
    finally:
        db.close()
    # Sugerir proceso BCP para activos críticos (ISO 22301 cl. 8.2) — sin IA
    try:
        from app.services.bcp_service import suggest_bcp_for_asset
        from app.database import SessionLocal as _SL
        db2 = _SL()
        try:
            suggest_bcp_for_asset(db2, asset_id)
            db2.commit()
        finally:
            db2.close()
    except Exception as _e:
        logger.debug("BCP suggest skipped: %s", _e)


@router.post("/smart-import")
async def smart_import_assets(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Importa activos desde cualquier formato usando IA para normalizar columnas.

    Acepta CSV, XLSX, XLS, JSON, TSV, ODS, etc.
    Claude infiere la correspondencia de columnas y el asset_type automaticamente.
    """
    content = await file.read()
    if not content:
        raise HTTPException(400, "El fichero esta vacio.")

    from app.services.smart_import_service import smart_import
    from app.routers.ai_config import resolve_api_key
    from app.models import AiConfig

    # Resolver api_key y modelo per-tenant
    org_id = current_user.organization_id
    try:
        api_key = resolve_api_key(db, org_id)
    except Exception:
        api_key = None

    model = "claude-haiku-4-5"   # modelo rapido y barato para la tarea de mapeo
    try:
        cfg = db.query(AiConfig).filter_by(organization_id=org_id).first()
        if cfg and cfg.model:
            model = cfg.model
    except Exception:
        pass

    try:
        result = smart_import(
            content=content,
            filename=file.filename or "import.csv",
            org_id=org_id,
            db=db,
            api_key=api_key,
            model=model,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Error en la importacion: {exc}")

    # Lanzar auto-analisis de riesgos en background para los activos nuevos
    if background_tasks and result.get("created", 0) > 0:
        background_tasks.add_task(_run_all_assets_analysis_bg, org_id)

    return result


def _run_all_assets_analysis_bg(org_id: int) -> None:
    """Wrapper background para analisis de todos los activos de la org."""
    db = SessionLocal()
    try:
        from app.services.asset_risk_analysis_service import analyze_all_org_assets
        analyze_all_org_assets(db, org_id)
    except Exception:
        pass
    finally:
        db.close()


@router.post("/{asset_id}/analyze")
def analyze_asset(
    asset_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Lanza el analisis de riesgos con IA para un activo concreto."""
    a = db.get(Asset, asset_id)
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Activo no encontrado")
    a.ai_risk_status = None
    a.ai_risk_summary = None
    db.commit()
    background_tasks.add_task(_run_asset_analysis_bg, asset_id)
    return {"ok": True, "message": "Analisis de riesgos iniciado en background"}


@router.post("/analyze-all")
def analyze_all_assets(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Lanza el analisis de riesgos solo para activos SIN analizar (null) o con error.
    No toca activos ya correctamente analizados.
    """
    from sqlalchemy import or_
    org_id = current_user.organization_id
    pending = db.query(Asset).filter(
        Asset.organization_id == org_id,
        Asset.is_group_representative.is_(False),
        or_(Asset.ai_risk_status == None, Asset.ai_risk_status == "error"),  # noqa: E711
    ).count()
    background_tasks.add_task(_run_all_assets_analysis_bg, org_id)
    return {"ok": True, "total": pending, "message": f"Analisis iniciado para {pending} activos pendientes."}


@router.post("/analyze-cia-zero")
def analyze_cia_zero(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Resetea y re-analiza activos que tienen todas las dimensiones CIA a 0.
    No toca activos que ya tienen CIA correctamente valorado.
    """
    org_id = current_user.organization_id
    # Activos con CIA todo a 0 (sin valorar)
    zero_cia = db.query(Asset).filter(
        Asset.organization_id == org_id,
        Asset.is_group_representative.is_(False),
        Asset.value_confidentiality == 0,
        Asset.value_integrity == 0,
        Asset.value_availability == 0,
        Asset.value_authenticity == 0,
        Asset.value_accountability == 0,
    )
    count = zero_cia.count()
    if count:
        zero_cia.update({"ai_risk_status": None, "ai_risk_summary": None})
        db.commit()
        background_tasks.add_task(_run_all_assets_analysis_bg, org_id)
    return {
        "ok": True,
        "total": count,
        "message": f"{count} activos con CIA=0 marcados para re-analisis con estimacion de dimensiones ENS.",
    }


@router.post("/reset-stuck")
def reset_stuck_assets(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Resetea activos atascados en 'analysing' y lanza el analisis de todos los pendientes."""
    from sqlalchemy import or_
    org_id = current_user.organization_id
    stuck = db.query(Asset).filter(
        Asset.organization_id == org_id,
        Asset.is_group_representative.is_(False),
        Asset.ai_risk_status == "analysing",
    )
    stuck_count = stuck.count()
    if stuck_count:
        stuck.update({"ai_risk_status": None, "ai_risk_summary": None})
        db.commit()
    pending = db.query(Asset).filter(
        Asset.organization_id == org_id,
        Asset.is_group_representative.is_(False),
        or_(Asset.ai_risk_status == None, Asset.ai_risk_status == "error"),  # noqa: E711
    ).count()
    if pending:
        background_tasks.add_task(_run_all_assets_analysis_bg, org_id)
    return {
        "ok": True,
        "stuck_reset": stuck_count,
        "pending": pending,
        "message": f"{stuck_count} atascados reseteados. {pending} activos pendientes en cola.",
    }


@router.post("/analyze-all-force")
def analyze_all_assets_force(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Fuerza el re-analisis de TODOS los activos (incluye ya analizados)."""
    org_id = current_user.organization_id
    count = db.query(Asset).filter(
        Asset.organization_id == org_id,
        Asset.is_group_representative.is_(False),
    ).count()
    db.query(Asset).filter(
        Asset.organization_id == org_id,
        Asset.is_group_representative.is_(False),
    ).update({"ai_risk_status": None, "ai_risk_summary": None})
    db.commit()
    background_tasks.add_task(_run_all_assets_analysis_bg, org_id)
    return {"ok": True, "total": count, "message": f"Re-analisis forzado para {count} activos."}


@router.get("/analysis-status")
def get_analysis_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve estadisticas del estado de analisis IA de los activos."""
    from sqlalchemy import or_, func
    org_id = current_user.organization_id
    if not org_id:
        return {
            "total": 0, "analysed": 0, "analysing": 0,
            "error": 0, "skipped": 0, "pending": 0,
            "progress_pct": 0.0,
        }
    base = db.query(Asset).filter(
        Asset.organization_id == org_id,
        Asset.is_group_representative.is_(False),
    )
    total     = base.count()
    analysed  = base.filter(Asset.ai_risk_status == "analysed").count()
    analysing = base.filter(Asset.ai_risk_status == "analysing").count()
    error     = base.filter(Asset.ai_risk_status == "error").count()
    skipped   = base.filter(Asset.ai_risk_status == "skipped").count()
    pending   = base.filter(
        or_(Asset.ai_risk_status == None, Asset.ai_risk_status == "error")  # noqa: E711
    ).count()
    return {
        "total": total, "analysed": analysed, "analysing": analysing,
        "error": error, "skipped": skipped, "pending": pending,
        "progress_pct": round(analysed / total * 100, 1) if total else 0,
    }


@router.get("/export/csv")
def export_assets_csv(db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    assets = filter_by_org(db.query(Asset), Asset, current_user).order_by(Asset.code).all()
    df = pd.DataFrame([{
        "code": a.code, "name": a.name, "asset_type": a.asset_type.value,
        "description": a.description, "category": a.category, "location": a.location,
        "business_process": a.business_process, "classification": a.classification,
        "value_confidentiality": a.value_confidentiality,
        "value_integrity": a.value_integrity,
        "value_availability": a.value_availability,
        "value_authenticity": a.value_authenticity,
        "value_accountability": a.value_accountability,
    } for a in assets])
    buf = io.StringIO(); df.to_csv(buf, index=False); buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=assets_export.csv"},
    )


# ========== IMPORT HEALTH & ROLLBACK ==========

@router.get("/import-health")
def get_import_health(
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Dashboard de salud de importaciones: histórico de sesiones."""
    from app.models import ImportSession

    sessions = (
        db.query(ImportSession)
        .filter_by(organization_id=current_user.organization_id)
        .order_by(ImportSession.started_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "sessions": [
            {
                "id": s.id,
                "session_id": s.session_id,
                "filename": s.filename,
                "source_system": s.source_system,
                "status": s.status,
                "total_rows": s.total_rows,
                "created": s.created,
                "updated": s.updated,
                "skipped": s.skipped,
                "errors_count": s.errors_count,
                "data_loss_detected": s.data_loss_detected,
                "expected_processed": s.expected_processed,
                "actual_processed": s.actual_processed,
                "dedup_by_external_id": s.dedup_by_external_id,
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "rolled_back_at": s.rolled_back_at.isoformat() if s.rolled_back_at else None,
            }
            for s in sessions
        ],
        "total": len(sessions),
    }


@router.post("/import-rollback/{session_id}")
def rollback_import(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Revierte una importación completa (borra todos los activos creados en esa sesión)."""
    from app.services.smart_import_service import rollback_import_session

    result = rollback_import_session(
        db=db,
        session_id=session_id,
        org_id=current_user.organization_id,
        user_id=current_user.id,
    )

    if not result.get("ok"):
        raise HTTPException(400, result.get("error"))

    # Log de auditoría
    log_action(
        db,
        current_user.id,
        "delete",
        "import_session",
        session_id,
        f"Rolled back import: {result['rolled_back_count']} assets deleted",
    )

    return result
