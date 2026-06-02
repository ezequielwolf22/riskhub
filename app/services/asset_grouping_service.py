"""Servicio de agrupacion inteligente de activos para analisis de riesgo ISO 27005.

Flujo:
  1. Obtener activos no representativos que no pertenecen a grupos validados.
  2. Obtener/crear la configuracion de criterios de la organizacion.
  3. Llamar a Claude con el inventario comprimido y los criterios habilitados.
  4. Parsear la respuesta JSON y persistir los grupos propuestos.
  5. Los grupos validados generan un activo representativo (virtual) para el analisis de riesgo.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import (
    AiCallLog, AiConfig, Asset, AssetGroup, AssetGroupingConfig,
    AssetGroupStatus, AssetType,
)

logger = logging.getLogger(__name__)

# ---------- Criterios por defecto (ISO 27005 / ISO 27002 alineados) ----------

DEFAULT_CRITERIA: list[dict] = [
    {
        "id": "asset_type",
        "name": "Tipo de activo (ISO 27005 Annex B)",
        "description": (
            "Agrupa por categoria ISO 27005: procesos primarios, informacion primaria, "
            "hardware, software, red, personal, instalaciones, organizacion. "
            "Es el criterio mas importante porque determina las amenazas aplicables."
        ),
        "level": 1,
        "enabled": True,
    },
    {
        "id": "technology_platform",
        "name": "Plataforma tecnologica / Sistema operativo",
        "description": (
            "Distingue SO (Linux/Windows/macOS/AIX) y tipo de despliegue "
            "(fisico/virtual/contenedor/cloud/SaaS). Las amenazas y vulnerabilidades "
            "difieren significativamente entre plataformas."
        ),
        "level": 2,
        "enabled": True,
    },
    {
        "id": "data_classification",
        "name": "Clasificacion de la informacion",
        "description": (
            "Separa activos que procesan datos confidenciales/secretos de los "
            "publicos/internos segun el esquema de clasificacion de la organizacion."
        ),
        "level": 2,
        "enabled": True,
    },
    {
        "id": "criticality_cia",
        "name": "Criticidad CIA",
        "description": (
            "Agrupa por nivel de valoracion maxima CIA (critico >=4, alto 3, medio 2, "
            "bajo <=1). Activos con el mismo perfil de riesgo comparten tratamiento."
        ),
        "level": 2,
        "enabled": True,
    },
    {
        "id": "location_environment",
        "name": "Ubicacion / entorno de despliegue",
        "description": (
            "Distingue CPD propio / cloud publico (AWS, Azure, GCP) / oficina / remoto. "
            "Aplica controles fisicos y de conectividad diferentes."
        ),
        "level": 3,
        "enabled": False,
    },
    {
        "id": "owner_department",
        "name": "Propietario / departamento responsable",
        "description": (
            "Agrupa cuando las responsabilidades organizacionales y controles aplicables "
            "difieren entre departamentos."
        ),
        "level": 3,
        "enabled": False,
    },
    {
        "id": "business_process",
        "name": "Proceso de negocio soportado",
        "description": (
            "Activos que dan soporte al mismo proceso comparten contexto de amenaza "
            "(ej. todos los activos del proceso 'Facturacion')."
        ),
        "level": 3,
        "enabled": False,
    },
]

_GROUPING_SYSTEM_PROMPT = """Eres un experto en gestion de riesgos ISO/IEC 27005:2018 y MAGERIT v3.
Tu tarea es agrupar un inventario de activos de informacion para optimizar el analisis de riesgo.

OBJETIVO DE AGRUPACION:
- Crear grupos cuyos activos compartan el mismo perfil de amenazas y vulnerabilidades aplicables
- Activos que requieren los mismos controles de seguridad deben ir juntos
- El perfil CIA similar justifica un tratamiento conjunto
- Es ineficiente analizar miles de activos identicos por separado

CRITERIOS APLICADOS (jerarquicos, aplica del nivel 1 al 3):
{criteria_text}

REGLAS METODOLOGICAS:
- Aplica los criterios en orden jerarquico: nivel 1 primero, luego refina con nivel 2 y 3
- Nombre del grupo: descriptivo y especifico (ej. "Servidores Linux - Web (Produccion)")
- Maximo 80 activos por grupo; si un grupo supera ese limite, subdivide
- Minimo 1 activo por grupo (activos unicos se analizan solos)
- Justificacion metodologica clara referenciando ISO 27005
- NO elimines, modifiques ni renombres los activos originales

Devuelve UNICAMENTE JSON valido con esta estructura exacta:
{{
  "groups": [
    {{
      "name": "Nombre descriptivo del grupo",
      "description": "Descripcion de las caracteristicas comunes (opcional, omitir si hay >80 activos)",
      "rationale": "Justificacion ISO 27005 (opcional, omitir si hay >80 activos)",
      "asset_ids": [1, 2, 3]
    }}
  ],
  "summary": "Resumen ejecutivo (opcional, omitir si hay >80 activos)"
}}
IMPORTANTE: si el inventario es grande (>80 activos), omite los campos description, rationale y summary para no exceder el limite de tokens. Solo incluye name y asset_ids en cada grupo."""


# ---------- Helpers ----------

def _get_api_key(db: Session, organization_id: int | None) -> str | None:
    cfg = db.query(AiConfig).filter_by(organization_id=organization_id).first()
    if cfg and cfg.api_key_encrypted:
        try:
            from cryptography.fernet import Fernet
            from app.services.document_service import _fernet_key
            return Fernet(_fernet_key()).decrypt(cfg.api_key_encrypted.encode()).decode()
        except Exception:
            pass
    from app.config import settings
    return settings.anthropic_api_key or None


def _get_model(db: Session, organization_id: int | None) -> str:
    cfg = db.query(AiConfig).filter_by(organization_id=organization_id).first()
    return cfg.model if cfg and cfg.model else "claude-opus-4-5"


def _strip_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```", 2)
        inner = parts[1] if len(parts) > 1 else raw
        if inner.startswith("json"):
            inner = inner[4:]
        raw = inner.rsplit("```", 1)[0].strip()
    return raw


def _cia_level(asset: Asset) -> str:
    v = max(
        asset.value_confidentiality or 0,
        asset.value_integrity or 0,
        asset.value_availability or 0,
        asset.value_authenticity or 0,
        asset.value_accountability or 0,
    )
    if v >= 4:
        return "critico"
    if v == 3:
        return "alto"
    if v == 2:
        return "medio"
    return "bajo"


def _asset_row(a: Asset, compact: bool = False) -> dict:
    if compact:
        # Modo compacto para inventarios grandes: solo campos clave, claves cortas
        row: dict = {"i": a.id, "n": (a.name or "")[:60], "t": a.asset_type.value if a.asset_type else ""}
        cia = _cia_level(a)
        if cia != "bajo":
            row["c"] = cia
        if a.classification:
            row["cl"] = a.classification[:15]
        if a.category:
            row["cat"] = a.category[:25]
        return row
    return {
        "id": a.id,
        "name": a.name,
        "type": a.asset_type.value if a.asset_type else "",
        "category": a.category or "",
        "classification": a.classification or "",
        "cia": _cia_level(a),
        "desc": (a.description or "")[:60],
    }


# ---------- Config de criterios ----------

def get_or_create_config(db: Session, org_id: int | None) -> AssetGroupingConfig:
    cfg = db.query(AssetGroupingConfig).filter_by(organization_id=org_id).first()
    if not cfg:
        cfg = AssetGroupingConfig(organization_id=org_id, criteria=DEFAULT_CRITERIA)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def update_config(db: Session, org_id: int | None, criteria: list[dict]) -> AssetGroupingConfig:
    cfg = get_or_create_config(db, org_id)
    cfg.criteria = criteria
    db.commit()
    db.refresh(cfg)
    return cfg


# ---------- Agrupacion IA ----------

def propose_groups(db: Session, org_id: int | None) -> dict:
    """Llama a la IA para proponer grupos y persiste los resultados como PROPOSED."""
    api_key = _get_api_key(db, org_id)
    if not api_key:
        return {"ok": False, "error": "No hay API key configurada para el agente IA"}

    cfg = get_or_create_config(db, org_id)
    enabled_criteria = [c for c in cfg.criteria if c.get("enabled")]
    if not enabled_criteria:
        return {"ok": False, "error": "No hay criterios de agrupacion habilitados"}

    # Solo activos reales (no representativos) que no estén en grupos validados
    validated_group_ids = [
        g.id for g in db.query(AssetGroup).filter_by(
            organization_id=org_id, status=AssetGroupStatus.VALIDATED
        ).all()
    ]
    query = db.query(Asset).filter(
        Asset.organization_id == org_id,
        Asset.is_group_representative.is_(False),
    )
    if validated_group_ids:
        query = query.filter(
            (Asset.group_id == None) | (Asset.group_id.notin_(validated_group_ids))  # noqa: E711
        )

    assets = query.limit(1000).all()
    if not assets:
        return {"ok": False, "error": "No hay activos disponibles para agrupar"}

    n_assets = len(assets)
    # Modo compacto cuando hay muchos activos para reducir tokens de entrada y salida
    compact = n_assets > 80

    criteria_text = "\n".join(
        f"  Nivel {c['level']} - {c['name']}: {c['description']}"
        for c in sorted(enabled_criteria, key=lambda x: x["level"])
    )

    asset_payload = json.dumps(
        [_asset_row(a, compact=compact) for a in assets],
        ensure_ascii=False,
        separators=(',', ':') if compact else (', ', ': '),
    )

    compact_hint = (
        "\nNOTA: inventario grande. Usa nombres de grupo CORTOS (<50 chars). "
        "Omite campos 'description' y 'rationale' del JSON de salida para ahorrar tokens. "
        "Solo devuelve: name, asset_ids. No incluyas summary."
        if compact else ""
    )
    user_content = (
        f"INVENTARIO A AGRUPAR ({n_assets} activos):\n{asset_payload}\n\n"
        f"Aplica los criterios jerarquicos y devuelve los grupos propuestos.{compact_hint}"
    )

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    model = _get_model(db, org_id)

    system = _GROUPING_SYSTEM_PROMPT.format(criteria_text=criteria_text)
    # max_tokens: usar 16384 para modelos modernos; 8192 como fallback seguro
    max_tok = 16384
    try:
        message = client.messages.create(
            model=model,
            max_tokens=max_tok,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.BadRequestError as exc:
        err_body = str(exc).lower()
        # Algunos modelos no soportan 16384; reintentar con 8192
        if "max_tokens" in err_body or "maximum" in err_body:
            try:
                message = client.messages.create(
                    model=model,
                    max_tokens=8192,
                    system=system,
                    messages=[{"role": "user", "content": user_content}],
                )
            except Exception as exc2:
                return {"ok": False, "error": f"Error Anthropic API: {exc2}"}
        elif "credit balance" in err_body or "billing" in err_body:
            return {"ok": False, "error": "Saldo insuficiente en la cuenta Anthropic. Recarga creditos en console.anthropic.com/settings/billing."}
        else:
            return {"ok": False, "error": f"Error Anthropic API: {exc}"}
    except anthropic.AuthenticationError:
        return {"ok": False, "error": "API key de Anthropic invalida o no configurada en Configuracion > Agente IA."}
    except Exception as exc:
        logger.exception("Error en propuesta de grupos IA")
        return {"ok": False, "error": f"Error al llamar a la IA: {exc}"}

    # Detectar truncado por limite de tokens
    if getattr(message, 'stop_reason', None) == 'max_tokens':
        logger.warning(f"Grouping response truncated at max_tokens ({max_tok}). Assets={n_assets}")

    raw = _strip_fence(message.content[0].text)

    db.add(AiCallLog(
        organization_id=org_id,
        call_type="asset_grouping",
        prompt_tokens=message.usage.input_tokens,
        completion_tokens=message.usage.output_tokens,
        model=model,
        anonymized=False,
        response_summary=f"Asset grouping: {n_assets} assets analyzed",
    ))

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        stop = getattr(message, 'stop_reason', 'unknown')
        logger.error(f"JSONDecodeError in grouping (stop_reason={stop}, len={len(raw)}): {exc}")
        if stop == 'max_tokens':
            return {"ok": False, "error": (
                f"La respuesta de la IA fue demasiado larga y se corto ({n_assets} activos). "
                "Intenta reducir el numero de criterios habilitados o procesa el inventario en bloques "
                "eliminando activos ya agrupados."
            )}
        return {"ok": False, "error": f"La IA devolvio JSON invalido. Intenta de nuevo."}

    groups_data = result.get("groups", [])
    summary = result.get("summary", "")

    # Borrar TODOS los grupos anteriores (propuestos y validados) para empezar limpio
    all_existing = db.query(AssetGroup).filter_by(organization_id=org_id).all()
    for g in all_existing:
        # Eliminar activo representativo si existe (cascade borra sus riesgos IA)
        if g.representative_asset_id:
            rep = db.get(Asset, g.representative_asset_id)
            if rep and rep.is_group_representative:
                db.delete(rep)
        # Desagrupar los miembros
        db.query(Asset).filter_by(group_id=g.id).update(
            {"group_id": None}, synchronize_session=False
        )
        db.delete(g)
    db.commit()

    # Crear nuevos grupos propuestos
    asset_ids_set = {a.id for a in assets}
    criteria_ids = [c["id"] for c in enabled_criteria]
    created = 0
    for gd in groups_data:
        member_ids = [aid for aid in gd.get("asset_ids", []) if aid in asset_ids_set]
        if not member_ids:
            continue
        grp = AssetGroup(
            organization_id=org_id,
            name=gd.get("name", "Grupo sin nombre"),
            description=gd.get("description"),
            criteria_snapshot=criteria_ids,
            status=AssetGroupStatus.PROPOSED,
            ai_rationale=gd.get("rationale"),
        )
        db.add(grp)
        db.flush()
        db.query(Asset).filter(
            Asset.id.in_(member_ids),
            Asset.organization_id == org_id,
        ).update({"group_id": grp.id}, synchronize_session=False)
        created += 1

    db.commit()
    return {"ok": True, "groups_created": created, "assets_analyzed": len(assets), "summary": summary}


# ---------- Operaciones sobre grupos ----------

def validate_group(db: Session, group: AssetGroup) -> Asset:
    """Valida el grupo y crea el activo representativo para el analisis de riesgo."""
    members = db.query(Asset).filter_by(group_id=group.id).all()
    if not members:
        raise ValueError("El grupo no tiene miembros")

    # CIA: valores maximos entre todos los miembros (criterio conservador ISO 27005)
    vc = max(a.value_confidentiality or 0 for a in members)
    vi = max(a.value_integrity or 0 for a in members)
    va = max(a.value_availability or 0 for a in members)
    vau = max(a.value_authenticity or 0 for a in members)
    vacc = max(a.value_accountability or 0 for a in members)

    # Tipo de activo mayoritario
    from collections import Counter
    type_counts = Counter(a.asset_type for a in members)
    dominant_type = type_counts.most_common(1)[0][0]

    # Crear o actualizar el activo representativo
    if group.representative_asset_id:
        rep = db.get(Asset, group.representative_asset_id)
    else:
        rep = None

    if not rep:
        n = db.query(Asset).count() + 1
        code = f"GRP-{n:04d}"
        while db.query(Asset).filter_by(code=code).first():
            n += 1
            code = f"GRP-{n:04d}"
        rep = Asset(
            code=code,
            organization_id=group.organization_id,
            name=f"{group.name}",
            description=f"Activo representativo del grupo '{group.name}' ({len(members)} activos)",
            asset_type=dominant_type,
            is_group_representative=True,
            group_id=group.id,
        )
        db.add(rep)
        db.flush()

    rep.value_confidentiality = vc
    rep.value_integrity = vi
    rep.value_availability = va
    rep.value_authenticity = vau
    rep.value_accountability = vacc
    rep.asset_type = dominant_type
    rep.category = members[0].category if members else None
    rep.location = members[0].location if members else None

    group.status = AssetGroupStatus.VALIDATED
    group.representative_asset_id = rep.id
    db.commit()
    db.refresh(rep)
    return rep


def delete_group(db: Session, group: AssetGroup) -> None:
    """Elimina el grupo y desagrupa sus miembros."""
    if group.representative_asset_id:
        rep = db.get(Asset, group.representative_asset_id)
        if rep:
            db.delete(rep)
    db.query(Asset).filter_by(group_id=group.id).update(
        {"group_id": None}, synchronize_session=False
    )
    db.delete(group)
    db.commit()


def move_asset(db: Session, asset_id: int, target_group_id: int | None, org_id: int | None) -> None:
    """Mueve un activo a otro grupo (o lo desagrupa si target_group_id es None)."""
    asset = db.get(Asset, asset_id)
    if not asset or asset.organization_id != org_id:
        raise ValueError("Activo no encontrado")
    if asset.is_group_representative:
        raise ValueError("No se puede mover un activo representativo")

    if target_group_id is not None:
        grp = db.get(AssetGroup, target_group_id)
        if not grp or grp.organization_id != org_id:
            raise ValueError("Grupo destino no encontrado")
        asset.group_id = target_group_id
    else:
        asset.group_id = None

    db.commit()


def split_group(
    db: Session,
    group: AssetGroup,
    asset_ids_for_new: list[int],
    new_name: str,
) -> AssetGroup:
    """Divide el grupo creando uno nuevo con los activos indicados."""
    if not asset_ids_for_new:
        raise ValueError("Debe seleccionar al menos un activo para el nuevo grupo")

    new_group = AssetGroup(
        organization_id=group.organization_id,
        name=new_name,
        description=f"Derivado de '{group.name}'",
        criteria_snapshot=group.criteria_snapshot,
        status=AssetGroupStatus.PROPOSED,
    )
    db.add(new_group)
    db.flush()

    db.query(Asset).filter(
        Asset.id.in_(asset_ids_for_new),
        Asset.group_id == group.id,
    ).update({"group_id": new_group.id}, synchronize_session=False)
    db.commit()
    db.refresh(new_group)
    return new_group
