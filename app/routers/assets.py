"""CRUD de activos + import CSV/Excel."""
import io
from typing import Optional

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from sqlalchemy import func
from app.models import Asset, AssetType, AiDocumentStatus, Risk, User
from app.schemas import AssetIn, AssetOut, ImportResult
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action
from app.services.risk_auto_generator import auto_generate_risks_for_asset

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
    limit: int = Query(500, le=2000),
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
    db.delete(a)
    log_action(db, current_user.id, "delete", "asset", str(asset_id),
               {"code": code, "name": name})
    db.commit()


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
    """Wrapper background para analisis de riesgos de un activo."""
    db = SessionLocal()
    try:
        # 1. Auto-generar riesgos (activo × amenazas)
        asset = db.get(Asset, asset_id)
        if asset:
            auto_generate_risks_for_asset(db, asset)
        # 2. Analisis IA complementario
        from app.services.asset_risk_analysis_service import analyze_asset_risks
        analyze_asset_risks(db, asset_id)
    except Exception:
        pass
    finally:
        db.close()


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
    """Lanza el analisis de riesgos para todos los activos de la organizacion."""
    org_id = current_user.organization_id
    count = db.query(Asset).filter_by(organization_id=org_id).count()
    # Resetear estados
    db.query(Asset).filter_by(organization_id=org_id).update(
        {"ai_risk_status": None, "ai_risk_summary": None}
    )
    db.commit()
    background_tasks.add_task(_run_all_assets_analysis_bg, org_id)
    return {"ok": True, "total": count, "message": f"Analisis lanzado para {count} activos."}


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
