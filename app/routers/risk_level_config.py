"""Endpoints para configuracion de niveles de riesgo por organizacion.

GET  /api/risk-levels          → devuelve config org (o defaults)
PUT  /api/risk-levels          → reemplaza config org (admin)
DELETE /api/risk-levels        → elimina config custom, vuelve a defaults (admin)
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import RiskLevelConfig
from app.security import get_current_user, require_role
from app.services.risk_engine import _DEFAULT_BANDS

router = APIRouter(prefix="/api/risk-levels", tags=["risk-levels"])


# ---------- Schemas ----------

class RiskBandIn(BaseModel):
    code: str
    label: str
    min_level: int
    max_level: int
    color: str
    order: int

    @field_validator("min_level", "max_level")
    @classmethod
    def _in_range(cls, v):
        if not (0 <= v <= 8):
            raise ValueError("level must be 0-8")
        return v

    @field_validator("code")
    @classmethod
    def _valid_code(cls, v):
        if len(v) > 32:
            raise ValueError("code too long")
        return v.lower().strip()


class RiskBandOut(BaseModel):
    code: str
    label: str
    min_level: int
    max_level: int
    color: str
    order: int
    is_default: bool = False

    class Config:
        from_attributes = True


# ---------- Helpers ----------

def _org_id(current_user) -> int | None:
    return getattr(current_user, "organization_id", None)


def _get_custom(db: Session, org_id) -> list[RiskLevelConfig]:
    return (
        db.query(RiskLevelConfig)
        .filter(RiskLevelConfig.organization_id == org_id)
        .order_by(RiskLevelConfig.order)
        .all()
    )


# ---------- Endpoints ----------

_DEFAULT_LABEL_KEYS = {
    "low": "risk_level_config.band_label_low",
    "medium": "risk_level_config.band_label_medium",
    "high": "risk_level_config.band_label_high",
}


@router.get("", response_model=list[RiskBandOut])
def get_risk_levels(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    lang = get_lang(request)
    org_id = _org_id(current_user)
    rows = _get_custom(db, org_id)
    if rows:
        return [RiskBandOut(
            code=r.code, label=r.label, min_level=r.min_level,
            max_level=r.max_level, color=r.color, order=r.order,
            is_default=False,
        ) for r in rows]
    return [
        RiskBandOut(**{
            **b,
            "label": _t(_DEFAULT_LABEL_KEYS.get(b["code"], ""), lang) if b["code"] in _DEFAULT_LABEL_KEYS else b["label"],
            "is_default": True,
        })
        for b in _DEFAULT_BANDS
    ]


@router.put("", response_model=list[RiskBandOut])
def update_risk_levels(
    bands: list[RiskBandIn],
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    lang = get_lang(request)
    if not bands:
        raise HTTPException(400, _t("risk_level_config.at_least_one_band", lang))
    if len(bands) > 10:
        raise HTTPException(400, _t("risk_level_config.max_ten_bands", lang))

    # Validar que cubren 0-8 sin solapamientos
    sorted_bands = sorted(bands, key=lambda b: b.order)
    for b in sorted_bands:
        if b.min_level > b.max_level:
            raise HTTPException(400, _t("risk_level_config.min_greater_than_max", lang, code=b.code))

    org_id = _org_id(current_user)

    # Borrar config previa
    db.query(RiskLevelConfig).filter(RiskLevelConfig.organization_id == org_id).delete()

    # Insertar nueva
    new_rows = []
    for b in sorted_bands:
        row = RiskLevelConfig(
            organization_id=org_id,
            code=b.code,
            label=b.label,
            min_level=b.min_level,
            max_level=b.max_level,
            color=b.color,
            order=b.order,
        )
        db.add(row)
        new_rows.append(row)

    db.commit()
    for r in new_rows:
        db.refresh(r)

    return [RiskBandOut(
        code=r.code, label=r.label, min_level=r.min_level,
        max_level=r.max_level, color=r.color, order=r.order,
        is_default=False,
    ) for r in new_rows]


@router.delete("", status_code=204)
def reset_risk_levels(
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    org_id = _org_id(current_user)
    db.query(RiskLevelConfig).filter(RiskLevelConfig.organization_id == org_id).delete()
    db.commit()
