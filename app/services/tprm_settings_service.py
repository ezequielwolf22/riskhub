"""Configuracion del modulo de proveedores por organizacion (feedback cliente).

Singleton por org. Cubre:
 - Punto 4: lista editable de regiones operativas, independiente del pais y de
   las sedes BCM (pero puede sembrarse desde ellas como sugerencia).
 - Punto 7: plantilla y textos de email estandar EN/ES; modulos add-on.
 - Punto 11: destinatarios de notificacion post-review por region.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import BCMLocation, TprmSettings

# Punto 4 — lista de arranque sugerida por el cliente (editable)
DEFAULT_REGIONS = ["Global", "UK", "Spain", "France", "Iberia-Latam"]


def get_or_create(db: Session, org_id: int) -> TprmSettings:
    st = db.query(TprmSettings).filter(TprmSettings.organization_id == org_id).first()
    if not st:
        st = TprmSettings(organization_id=org_id, operating_regions=list(DEFAULT_REGIONS))
        db.add(st)
        db.commit()
        db.refresh(st)
    return st


def get_operating_regions(db: Session, org_id: int) -> list[str]:
    """Lista efectiva de regiones del modulo de proveedores (editable e independiente)."""
    st = db.query(TprmSettings).filter(TprmSettings.organization_id == org_id).first()
    if st and st.operating_regions:
        return list(st.operating_regions)
    return list(DEFAULT_REGIONS)


def bcm_region_suggestions(db: Session, org_id: int) -> list[str]:
    """Regiones candidatas derivadas de las sedes BCM ya configuradas (punto 4).

    Cruza con lo existente sin imponerlo: el usuario decide si las adopta. Se
    sugieren unidad de negocio, ciudad y pais de cada sede activa.
    """
    seen: dict[str, None] = {}
    locs = (
        db.query(BCMLocation)
        .filter(BCMLocation.organization_id == org_id)
        .all()
    )
    for loc in locs:
        for val in (loc.business_unit, loc.city, loc.country):
            v = (val or "").strip()
            if v and v not in seen:
                seen[v] = None
    return list(seen.keys())


def update_settings(db: Session, org_id: int, payload: dict) -> TprmSettings:
    st = get_or_create(db, org_id)
    allowed = {
        "operating_regions", "default_template_code",
        "standard_email_subject_en", "standard_email_subject_es",
        "standard_email_body_en", "standard_email_body_es",
        "trigger_modules", "review_notify_recipients", "review_notify_enabled",
    }
    for key, value in payload.items():
        if key in allowed:
            setattr(st, key, value)
    db.commit()
    db.refresh(st)
    return st


def as_dict(st: Optional[TprmSettings]) -> dict:
    if not st:
        return {
            "operating_regions": list(DEFAULT_REGIONS),
            "default_template_code": None,
            "standard_email_subject_en": None,
            "standard_email_subject_es": None,
            "standard_email_body_en": None,
            "standard_email_body_es": None,
            "trigger_modules": {},
            "review_notify_recipients": {},
            "review_notify_enabled": False,
        }
    return {
        "operating_regions": st.operating_regions or list(DEFAULT_REGIONS),
        "default_template_code": st.default_template_code,
        "standard_email_subject_en": st.standard_email_subject_en,
        "standard_email_subject_es": st.standard_email_subject_es,
        "standard_email_body_en": st.standard_email_body_en,
        "standard_email_body_es": st.standard_email_body_es,
        "trigger_modules": st.trigger_modules or {},
        "review_notify_recipients": st.review_notify_recipients or {},
        "review_notify_enabled": bool(st.review_notify_enabled),
    }
