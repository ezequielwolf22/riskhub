"""Endpoints para agrupacion de activos — criterios, propuesta IA y validacion."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, AssetGroup, AssetGroupingConfig, AssetGroupStatus, User
from app.schemas import (
    AssetGroupIn, AssetGroupOut, AssetGroupUpdate, AssetGroupingConfigIn,
    AssetGroupingConfigOut, AssetMiniOut, MoveAssetIn, SplitGroupIn,
)
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.asset_grouping_service import (
    delete_group, get_or_create_config, move_asset,
    propose_groups, split_group, update_config, validate_group,
)
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/asset-groups", tags=["asset-groups"])


def _group_out(g: AssetGroup, db: Session) -> AssetGroupOut:
    members = db.query(Asset).filter_by(group_id=g.id, is_group_representative=False).all()
    return AssetGroupOut(
        id=g.id,
        name=g.name,
        description=g.description,
        status=g.status.value if g.status else "proposed",
        criteria_snapshot=g.criteria_snapshot,
        ai_rationale=g.ai_rationale,
        representative_asset_id=g.representative_asset_id,
        member_count=len(members),
        members=[AssetMiniOut.model_validate(a) for a in members],
        created_at=g.created_at,
        updated_at=g.updated_at,
    )


# ---------- Configuracion de criterios ----------

@router.get("/config", response_model=AssetGroupingConfigOut)
def get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = get_or_create_config(db, current_user.organization_id)
    return AssetGroupingConfigOut.model_validate(cfg)


@router.delete("/config", status_code=204)
def reset_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Elimina la configuracion de criterios para volver a los valores por defecto."""
    cfg = db.query(AssetGroupingConfig).filter_by(
        organization_id=current_user.organization_id
    ).first()
    if cfg:
        db.delete(cfg)
        db.commit()


@router.put("/config", response_model=AssetGroupingConfigOut)
def save_config(
    data: AssetGroupingConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    criteria = [c.model_dump() for c in data.criteria]
    cfg = update_config(db, current_user.organization_id, criteria)
    return AssetGroupingConfigOut.model_validate(cfg)


# ---------- Propuesta IA ----------

@router.post("/propose")
def propose(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Llama a la IA para agrupar activos. Reemplaza grupos PROPOSED anteriores."""
    result = propose_groups(db, current_user.organization_id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Error desconocido"))
    log_action(db, current_user.id, "propose_groups", "asset_group", None,
               {"groups_created": result["groups_created"]})
    return result


# ---------- CRUD de grupos ----------

@router.get("/", response_model=list[AssetGroupOut])
def list_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
):
    query = filter_by_org(db.query(AssetGroup), AssetGroup, current_user)
    if status:
        query = query.filter(AssetGroup.status == status)
    groups = query.order_by(AssetGroup.status, AssetGroup.name).all()
    return [_group_out(g, db) for g in groups]


@router.post("/", response_model=AssetGroupOut, status_code=201)
def create_group(
    data: AssetGroupIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Crea un grupo manual (sin IA)."""
    g = AssetGroup(
        organization_id=current_user.organization_id,
        name=data.name,
        description=data.description,
        status=AssetGroupStatus.PROPOSED,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    log_action(db, current_user.id, "create", "asset_group", str(g.id), {"name": g.name})
    return _group_out(g, db)


@router.get("/{group_id}", response_model=AssetGroupOut)
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    g = db.get(AssetGroup, group_id)
    if not g or not check_org_access(g.organization_id, current_user):
        raise HTTPException(404, "Grupo no encontrado")
    return _group_out(g, db)


@router.put("/{group_id}", response_model=AssetGroupOut)
def update_group(
    group_id: int,
    data: AssetGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    g = db.get(AssetGroup, group_id)
    if not g or not check_org_access(g.organization_id, current_user):
        raise HTTPException(404, "Grupo no encontrado")
    if data.name is not None:
        g.name = data.name
    if data.description is not None:
        g.description = data.description
    db.commit()
    db.refresh(g)
    return _group_out(g, db)


@router.delete("/{group_id}", status_code=204)
def remove_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    g = db.get(AssetGroup, group_id)
    if not g or not check_org_access(g.organization_id, current_user):
        raise HTTPException(404, "Grupo no encontrado")
    log_action(db, current_user.id, "delete", "asset_group", str(group_id), {"name": g.name})
    delete_group(db, g)


# ---------- Validacion ----------

@router.post("/{group_id}/validate", response_model=AssetGroupOut)
def validate(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Valida el grupo y crea su activo representativo para el analisis de riesgo."""
    g = db.get(AssetGroup, group_id)
    if not g or not check_org_access(g.organization_id, current_user):
        raise HTTPException(404, "Grupo no encontrado")
    try:
        validate_group(db, g)
    except ValueError as e:
        raise HTTPException(400, str(e))
    log_action(db, current_user.id, "validate", "asset_group", str(group_id), {"name": g.name})
    db.refresh(g)
    return _group_out(g, db)


@router.post("/validate-all")
def validate_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Valida todos los grupos en estado PROPOSED."""
    proposed = db.query(AssetGroup).filter_by(
        organization_id=current_user.organization_id,
        status=AssetGroupStatus.PROPOSED,
    ).all()
    validated = 0
    errors = []
    for g in proposed:
        try:
            validate_group(db, g)
            validated += 1
        except Exception as e:
            errors.append({"group": g.name, "error": str(e)})
    log_action(db, current_user.id, "validate_all", "asset_group", None, {"validated": validated})
    return {"ok": True, "validated": validated, "errors": errors}


# ---------- Mover activo ----------

@router.post("/move-asset")
def move(
    data: MoveAssetIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    try:
        move_asset(db, data.asset_id, data.target_group_id, current_user.organization_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ---------- Dividir grupo ----------

@router.post("/{group_id}/split", response_model=AssetGroupOut)
def split(
    group_id: int,
    data: SplitGroupIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    g = db.get(AssetGroup, group_id)
    if not g or not check_org_access(g.organization_id, current_user):
        raise HTTPException(404, "Grupo no encontrado")
    try:
        new_grp = split_group(db, g, data.asset_ids, data.new_group_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    log_action(db, current_user.id, "split", "asset_group", str(group_id),
               {"original": g.name, "new": new_grp.name})
    return _group_out(new_grp, db)
