"""Router MAGERIT v3 — valoración de activos y catálogo de amenazas."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
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
def seed_threats(request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(require_analyst)):
    """Carga el catálogo de amenazas MAGERIT v3 para la organización."""
    lang = get_lang(request)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, _t("magerit.org_id_required", lang))
    created = seed_magerit_threats(db, org_id)
    return {"message": _t("magerit.threats_seeded", lang, created=created), "created": created}


@router.get("/analysis")
def get_analysis(request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """Análisis MAGERIT de todos los activos de la organización."""
    lang = get_lang(request)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, _t("magerit.org_id_required", lang))
    return get_magerit_analysis(db, org_id)


@router.get("/assets/{asset_id}/valuation")
def get_asset_valuation(asset_id: int, request: Request, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """Valoración MAGERIT de un activo específico."""
    lang = get_lang(request)
    from app.models import Asset
    asset = db.get(Asset, asset_id)
    if not asset or asset.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("magerit.asset_not_found", lang))
    return get_asset_magerit_value(asset)


@router.delete("/catalog", status_code=200)
def delete_magerit_catalog(request: Request, db: Session = Depends(get_db),
                            current_user: User = Depends(require_analyst)):
    """Elimina todas las amenazas del catalogo MAGERIT (codigo MAGERIT-*).

    Las amenazas que tengan riesgos asociados se omiten y se reportan.
    """
    lang = get_lang(request)
    from app.models import Risk, Threat
    from app.services.audit_service import log_action

    magerit_threats = db.query(Threat).filter(Threat.code.like("MAGERIT-%")).all()
    deleted = 0
    skipped = []

    for th in magerit_threats:
        linked = db.query(Risk).filter(Risk.threat_id == th.id).count()
        if linked > 0:
            skipped.append({"code": th.code, "name": th.name, "risks": linked})
            continue
        db.delete(th)
        deleted += 1

    if deleted:
        log_action(db, current_user.id, "delete", "magerit_catalog", None,
                   {"deleted": deleted, "skipped": len(skipped)})
        db.commit()

    message = _t("magerit.catalog_deleted", lang, deleted=deleted)
    if skipped:
        message += _t("magerit.catalog_deleted_with_skipped", lang, skipped=len(skipped))

    return {
        "deleted": deleted,
        "skipped": skipped,
        "message": message,
    }


@router.get("/scale")
def get_scale(current_user: User = Depends(get_current_user)):
    """Escala de valoración MAGERIT."""
    return {"scale": _ASSET_VALUE_SCALE, "dimensions": {
        "D": "Disponibilidad", "I": "Integridad",
        "C": "Confidencialidad", "A": "Autenticidad", "T": "Trazabilidad",
    }}
