"""Registro central de modelos Claude por tier de analisis.

Fuente unica de verdad para elegir modelo: los servicios piden un tier
("deep" para razonamiento profundo, "fast" para clasificacion/extraccion
barata) y el registro resuelve el ID respetando el override por organizacion
(AiConfig.model). Evita IDs hardcodeados dispersos por el codigo.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

# Tiers de analisis -> modelo por defecto
# deep: analisis de riesgo por activo, TPRM, informes, gap analysis, sintesis
# fast: clasificacion, extraccion, resumenes de evidencia, regwatch triage
MODEL_TIERS = {
    "deep": "claude-opus-4-6",
    "fast": "claude-haiku-4-5",
}


def get_model(db: Session, organization_id: int | None, tier: str = "deep") -> str:
    """Resuelve el modelo para una organizacion y tier.

    El override de AiConfig.model (si el admin fijo un modelo concreto)
    tiene prioridad sobre el tier solo para "deep": los analisis fast
    siguen usando el modelo barato aunque la org haya elegido uno potente.
    """
    default = MODEL_TIERS.get(tier, MODEL_TIERS["deep"])
    if tier == "fast":
        return default
    try:
        from app.models import AiConfig
        cfg = db.query(AiConfig).filter_by(organization_id=organization_id).first()
        if cfg and cfg.model:
            return cfg.model
    except Exception:
        pass
    return default


def get_api_key(db: Session, organization_id: int | None) -> str | None:
    """API key de Anthropic de la org (Fernet) con fallback a la global."""
    try:
        from app.models import AiConfig
        cfg = db.query(AiConfig).filter_by(organization_id=organization_id).first()
        if cfg and cfg.api_key_encrypted:
            from cryptography.fernet import Fernet
            from app.services.document_service import _fernet_key
            return Fernet(_fernet_key()).decrypt(cfg.api_key_encrypted.encode()).decode()
    except Exception:
        pass
    from app.config import settings
    return settings.anthropic_api_key or None
