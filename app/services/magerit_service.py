"""Metodología MAGERIT v3 — valoración de activos y análisis de riesgos.

MAGERIT (Metodología de Análisis y Gestión de Riesgos de los Sistemas de Información)
es el estándar español de referencia para análisis de riesgos en el sector público
y ampliamente usado en España/LATAM.

Dimensiones de seguridad MAGERIT:
- D: Disponibilidad
- I: Integridad de los datos
- C: Confidencialidad de los datos
- A: Autenticidad
- T: Trazabilidad

Escala de valoración: 0 (sin valor) a 10 (extremadamente alto)
"""
import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.i18n import t as _t
from app.models import Asset, AssetType, Risk, RiskContext, Threat

logger = logging.getLogger("riskhub.magerit")

_MAGERIT_THREATS_PATH = Path(__file__).parent.parent / "data" / "magerit_threats.json"

# Escala MAGERIT → ISO27005 (probabilidad e impacto)
_MAGERIT_TO_ISO = {1: 1, 2: 2, 3: 3, 4: 4, 5: 4}

# Valoración de activos MAGERIT por dimensión (D, I, C, A, T)
# Guía de niveles (claves i18n, se resuelven con _get_scale_description)
_ASSET_VALUE_SCALE_KEYS = {
    1: "scale_value_1",
    2: "scale_value_2",
    3: "scale_value_3",
    4: "scale_value_4",
    5: "scale_value_5",
    6: "scale_value_6",
    7: "scale_value_7",
    8: "scale_value_8",
}


def _get_asset_value_scale(lang: str = "es") -> dict:
    """Escala de valoración MAGERIT (niveles 1-8) traducida al idioma solicitado."""
    return {
        level: _t(f"magerit_service.{key}", lang)
        for level, key in _ASSET_VALUE_SCALE_KEYS.items()
    }


# Alias retrocompatible en español, usado por codigo que aun no pasa `lang`.
_ASSET_VALUE_SCALE = _get_asset_value_scale("es")

# Tipología de activos MAGERIT (mapeo desde ISO27005 AssetType)
_ASSET_TYPE_MAGERIT = {
    AssetType.PRIMARY_INFORMATION:    "datos",
    AssetType.PRIMARY_PROCESS:        "servicios",
    AssetType.SUPPORT_SOFTWARE:       "aplicaciones",
    AssetType.SUPPORT_HARDWARE:       "equipos",
    AssetType.SUPPORT_NETWORK:        "redes",
    AssetType.SUPPORT_PERSONNEL:      "personal",
    AssetType.SUPPORT_SITE:           "instalaciones",
    AssetType.SUPPORT_ORGANIZATION:   "soportes",
}

# Dimensiones críticas por tipo de activo
_DIMENSIONS_BY_TYPE = {
    "datos":         {"D": 3, "I": 4, "C": 5, "A": 3, "T": 3},
    "servicios":     {"D": 5, "I": 3, "C": 2, "A": 3, "T": 3},
    "aplicaciones":  {"D": 4, "I": 4, "C": 3, "A": 3, "T": 3},
    "equipos":       {"D": 4, "I": 3, "C": 2, "A": 2, "T": 2},
    "redes":         {"D": 4, "I": 3, "C": 3, "A": 2, "T": 3},
    "personal":      {"D": 3, "I": 2, "C": 4, "A": 4, "T": 4},
    "instalaciones": {"D": 3, "I": 2, "C": 2, "A": 1, "T": 1},
    "soportes":      {"D": 3, "I": 3, "C": 4, "A": 2, "T": 2},
}


def load_magerit_threats() -> list[dict]:
    """Carga el catálogo de amenazas MAGERIT v3."""
    try:
        return json.loads(_MAGERIT_THREATS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def get_asset_magerit_value(asset: Asset, lang: str = "es") -> dict:
    """Calcula la valoración MAGERIT de un activo por dimensiones.

    Retorna: {D, I, C, A, T, value_max, magerit_type}
    """
    magerit_type = _ASSET_TYPE_MAGERIT.get(asset.asset_type, "aplicaciones")
    base_dims = _DIMENSIONS_BY_TYPE.get(magerit_type, {"D": 3, "I": 3, "C": 3, "A": 2, "T": 2})

    # Ajustar por clasificación del activo
    classification = (asset.classification or "").lower()
    if "secreto" in classification or "restringido" in classification:
        base_dims["C"] = min(8, base_dims["C"] + 2)
    elif "confidencial" in classification:
        base_dims["C"] = min(7, base_dims["C"] + 1)

    value_max = max(base_dims.values())
    return {
        **base_dims,
        "value_max": value_max,
        "magerit_type": magerit_type,
        "scale_description": _get_asset_value_scale(lang).get(value_max, ""),
    }


def calculate_magerit_risk(
    asset_value: dict,
    threat_likelihood: int,
    threat_consequence: int,
    degradation_pct: int = 50,
    lang: str = "es",
) -> dict:
    """Calcula riesgo MAGERIT: Riesgo = Impacto × Frecuencia.

    Args:
        asset_value: valoración del activo por dimensiones
        threat_likelihood: probabilidad amenaza (0-4 ISO, se convierte)
        threat_consequence: consecuencia (0-4 ISO)
        degradation_pct: % de degradación del activo si amenaza materializa

    Returns: {impact, frequency, risk_value, risk_level_magerit}
    """
    # Impacto = Valor_activo × Degradación
    value_max = asset_value.get("value_max", 3)
    impact = round(value_max * (degradation_pct / 100), 2)

    # Frecuencia (escala MAGERIT 0-4 → 1-10)
    freq_map = {0: 0.01, 1: 0.1, 2: 1, 3: 10, 4: 100}
    frequency = freq_map.get(threat_likelihood, 1)

    # Riesgo MAGERIT = Impacto × Frecuencia (log scale simplificada)
    import math
    if frequency <= 0:
        risk_val = 0
    else:
        risk_val = round(impact * math.log10(max(1, frequency) + 1), 2)

    # Nivel de riesgo MAGERIT
    if risk_val <= 1:
        level = _t("magerit_service.risk_level_low", lang)
    elif risk_val <= 3:
        level = _t("magerit_service.risk_level_medium", lang)
    elif risk_val <= 6:
        level = _t("magerit_service.risk_level_high", lang)
    else:
        level = _t("magerit_service.risk_level_very_high", lang)

    return {
        "impact": impact,
        "frequency": frequency,
        "degradation_pct": degradation_pct,
        "risk_value": risk_val,
        "risk_level_magerit": level,
    }


# Mapeo de origen MAGERIT ("N","E","A") → ThreatOrigin ("E","A","D")
# MAGERIT:  N=Natural, E=Error involuntario, A=Ataque deliberado
# ThreatOrigin: E=Environmental, A=Accidental, D=Deliberate
_MAGERIT_ORIGIN_MAP = {
    "N": "E",   # Natural → Environmental
    "E": "A",   # Error   → Accidental
    "A": "D",   # Ataque  → Deliberate
}


def seed_magerit_threats(db: Session, org_id: int) -> int:
    """Carga las amenazas MAGERIT v3 en el catálogo global de amenazas.

    El catálogo de amenazas es global (sin organization_id).
    Solo crea las que no existen por código. Retorna amenazas creadas.
    """
    from app.models import ThreatOrigin
    threats_data = load_magerit_threats()
    created = 0

    for t in threats_data:
        code = f"MAGERIT-{t['code']}"
        # El catálogo es global — no filtramos por org
        if db.query(Threat).filter(Threat.code == code).first():
            continue

        # Mapear origen MAGERIT → ThreatOrigin
        raw_origin = _MAGERIT_ORIGIN_MAP.get(t.get("origin", "A"), "A")
        try:
            origin = ThreatOrigin(raw_origin)
        except ValueError:
            origin = ThreatOrigin.ACCIDENTAL

        threat = Threat(
            code=code,
            name=t["name"],
            description=f"[MAGERIT v3] {t.get('description', '')} — Categoría: {t.get('category', '')}",
            category=t.get("category", ""),
            origin=origin,
            typical_assets=[],
            affects=t.get("dimension", []),   # D/I/C/A/T — dimensiones afectadas
            is_custom=False,
            catalog="magerit",
        )
        db.add(threat)
        created += 1

    if created:
        try:
            db.commit()
            logger.info("MAGERIT: %d amenazas cargadas en el catalogo global", created)
        except Exception as exc:
            db.rollback()
            logger.exception("Error cargando amenazas MAGERIT: %s", exc)
            return 0
    return created


def get_magerit_analysis(db: Session, org_id: int, lang: str = "es") -> dict:
    """Análisis MAGERIT completo de los activos de la org.

    Retorna valoración de activos, riesgos MAGERIT y métricas.
    """
    assets = db.query(Asset).filter(Asset.organization_id == org_id).all()
    magerit_threats = [t for t in db.query(Threat).filter(
        Threat.organization_id == org_id,
        Threat.code.like("MAGERIT-%"),
    ).all()]

    asset_valuations = []
    for asset in assets:
        val = get_asset_magerit_value(asset, lang)
        asset_valuations.append({
            "asset_id": asset.id,
            "asset_code": asset.code,
            "asset_name": asset.name,
            "asset_type": asset.asset_type.value if hasattr(asset.asset_type, "value") else str(asset.asset_type),
            "magerit_type": val["magerit_type"],
            "dimensions": {k: v for k, v in val.items() if k in ("D", "I", "C", "A", "T")},
            "value_max": val["value_max"],
            "scale": val["scale_description"],
        })

    from app.services.risk_engine import magerit_dimensions

    return {
        "org_id": org_id,
        "total_assets": len(assets),
        "magerit_threats_count": len(magerit_threats),
        "asset_valuations": asset_valuations[:50],
        "dimensions_legend": magerit_dimensions(lang),
        "scale_legend": _get_asset_value_scale(lang),
    }
