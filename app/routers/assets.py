"""CRUD de activos + import CSV/Excel."""
import io
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, AssetType, User
from app.schemas import AssetIn, AssetOut, ImportResult
from app.security import get_current_user, require_analyst

router = APIRouter(prefix="/api/assets", tags=["assets"])


def _next_code(db: Session) -> str:
    n = db.query(Asset).count() + 1
    return f"AST-{n:04d}"


def _to_out(a: Asset) -> AssetOut:
    return AssetOut.model_validate({
        **{k: getattr(a, k) for k in AssetOut.model_fields if k != "value_max"},
        "value_max": a.value_max,
    })


@router.get("/", response_model=list[AssetOut])
def list_assets(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    q: Optional[str] = None,
    asset_type: Optional[AssetType] = None,
    limit: int = Query(500, le=2000),
):
    query = db.query(Asset)
    if q:
        like = f"%{q}%"
        query = query.filter((Asset.name.ilike(like)) | (Asset.code.ilike(like))
                             | (Asset.description.ilike(like)))
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)
    return [_to_out(a) for a in query.order_by(Asset.code).limit(limit).all()]


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: int, db: Session = Depends(get_db),
              _: User = Depends(get_current_user)):
    a = db.get(Asset, asset_id)
    if not a:
        raise HTTPException(404, "Activo no encontrado")
    return _to_out(a)


@router.post("/", response_model=AssetOut, status_code=201,
             dependencies=[Depends(require_analyst)])
def create_asset(data: AssetIn, db: Session = Depends(get_db)):
    code = data.code or _next_code(db)
    if db.query(Asset).filter(Asset.code == code).first():
        raise HTTPException(400, f"Ya existe activo con codigo {code}")
    payload = data.model_dump(exclude={"owner_ids"})
    payload["code"] = code
    a = Asset(**payload)
    db.add(a); db.commit(); db.refresh(a)
    return _to_out(a)


@router.put("/{asset_id}", response_model=AssetOut,
            dependencies=[Depends(require_analyst)])
def update_asset(asset_id: int, data: AssetIn, db: Session = Depends(get_db)):
    a = db.get(Asset, asset_id)
    if not a:
        raise HTTPException(404, "Activo no encontrado")
    for k, v in data.model_dump(exclude={"owner_ids", "code"}).items():
        setattr(a, k, v)
    db.commit(); db.refresh(a)
    return _to_out(a)


@router.delete("/{asset_id}", status_code=204,
               dependencies=[Depends(require_analyst)])
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    a = db.get(Asset, asset_id)
    if not a:
        raise HTTPException(404, "Activo no encontrado")
    db.delete(a); db.commit()


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


@router.post("/import", response_model=ImportResult,
             dependencies=[Depends(require_analyst)])
async def import_assets(file: UploadFile = File(...), db: Session = Depends(get_db)):
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

            code = str(row["code"]).strip() if "code" in df.columns and pd.notna(row.get("code")) else _next_code(db)
            existing = db.query(Asset).filter(Asset.code == code).first()
            if existing:
                for k, v in payload.items():
                    setattr(existing, k, v)
                result.updated += 1
            else:
                a = Asset(code=code, **payload)
                db.add(a); db.flush()
                result.created += 1
        except Exception as e:
            result.skipped += 1
            result.errors.append(f"Fila {idx+2}: {e}")

    db.commit()
    return result


@router.get("/export/csv")
def export_assets_csv(db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)):
    assets = db.query(Asset).order_by(Asset.code).all()
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
