"""Router MAGERIT v3 — valoración de activos y catálogo de amenazas."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import get_current_user, require_analyst
from app.services.magerit_service import (
    load_magerit_threats, seed_magerit_threats,
    get_magerit_analysis, get_asset_magerit_value,
    _ASSET_VALUE_SCALE, _DIMENSIONS_BY_TYPE,
)

router = APIRouter(prefix="/api/magerit", tags=["magerit"])


@router.get("/threats")
def list_magerit_threats(current_user: User = Depends(get_current_user)):
    """Catálogo completo de amenazas MAGERIT v3."""
    return load_magerit_threats()


@router.post("/seed")
def seed_threats(db: Session = Depends(get_db),
                 current_user: User = Depends(require_analyst)):
    """Carga el catálogo de amenazas MAGERIT v3 para la organización."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    created = seed_magerit_threats(db, org_id)
    return {"message": f"{created} amenazas MAGERIT cargadas", "created": created}


@router.get("/analysis")
def get_analysis(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """Análisis MAGERIT de todos los activos de la organización."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    return get_magerit_analysis(db, org_id)


@router.get("/assets/{asset_id}/valuation")
def get_asset_valuation(asset_id: int, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """Valoración MAGERIT de un activo específico."""
    from app.models import Asset
    asset = db.get(Asset, asset_id)
    if not asset or asset.organization_id != current_user.organization_id:
        raise HTTPException(404, "Activo no encontrado")
    return get_asset_magerit_value(asset)


@router.get("/scale")
def get_scale(current_user: User = Depends(get_current_user)):
    """Escala de valoración MAGERIT."""
    return {"scale": _ASSET_VALUE_SCALE, "dimensions": {
        "D": "Disponibilidad", "I": "Integridad",
        "C": "Confidencialidad", "A": "Autenticidad", "T": "Trazabilidad",
    }}
