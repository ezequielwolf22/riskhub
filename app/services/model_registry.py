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


# Precios USD por millon de tokens (input, output) — fuente: docs de Anthropic.
# Cache read ~0.1x input, cache write 1.25x (TTL 5 min); AiCallLog no separa
# tokens cacheados, asi que la estimacion es un techo (coste real <= estimado).
MODEL_PRICES = {
    "claude-opus-4-6": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Presupuesto mensual BLANDO de tokens IA por plan (solo aviso, nunca corta).
# None = sin limite. Ajustable segun politica comercial.
AI_MONTHLY_TOKEN_BUDGETS = {
    "free": 2_000_000,
    "starter": 10_000_000,
    "pro": 50_000_000,
    "enterprise": None,
}


def price_for_model(model: str | None) -> tuple[float, float, bool]:
    """(precio_input, precio_output, exacto) por MTok para un ID de modelo.

    Los IDs con fecha o combinados ("fast+deep" del gap) se resuelven por
    substring; si no se reconoce, se asume precio Opus (estimacion techo).
    """
    m = (model or "").lower()
    for known, prices in MODEL_PRICES.items():
        if known in m:
            return prices[0], prices[1], True
    if "haiku" in m:
        return MODEL_PRICES["claude-haiku-4-5"][0], MODEL_PRICES["claude-haiku-4-5"][1], False
    return MODEL_PRICES["claude-opus-4-6"][0], MODEL_PRICES["claude-opus-4-6"][1], False


def estimate_cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float:
    """Coste estimado en USD de una llamada (techo: no descuenta cache reads)."""
    p_in, p_out, _ = price_for_model(model)
    return (input_tokens or 0) / 1_000_000 * p_in + (output_tokens or 0) / 1_000_000 * p_out


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
