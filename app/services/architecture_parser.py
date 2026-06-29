"""Parser de diagramas de arquitectura — extrae activos, flujos y amenazas automáticamente.

Soporta:
- diagrams.net XML (.drawio / .xml)
- Imagen PNG/JPG (OCR via Claude Vision)
- Descripción textual (NLP via Claude)
"""
import json
import logging
import re
from defusedxml import ElementTree as ET
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Asset, AssetType, Threat, Risk, RiskContext, TreatmentOption, RiskStatus

logger = logging.getLogger("riskhub.architecture_parser")

# Mapeo de palabras clave a AssetType
_ASSET_TYPE_MAP = {
    "server":    AssetType.SUPPORT_HARDWARE,
    "servidor":  AssetType.SUPPORT_HARDWARE,
    "database":  AssetType.PRIMARY_INFORMATION,
    "db":        AssetType.PRIMARY_INFORMATION,
    "bbdd":      AssetType.PRIMARY_INFORMATION,
    "api":       AssetType.SUPPORT_SOFTWARE,
    "web":       AssetType.SUPPORT_SOFTWARE,
    "app":       AssetType.SUPPORT_SOFTWARE,
    "aplicacion": AssetType.SUPPORT_SOFTWARE,
    "firewall":  AssetType.SUPPORT_NETWORK,
    "router":    AssetType.SUPPORT_NETWORK,
    "network":   AssetType.SUPPORT_NETWORK,
    "red":       AssetType.SUPPORT_NETWORK,
    "user":      AssetType.SUPPORT_PERSONNEL,
    "usuario":   AssetType.SUPPORT_PERSONNEL,
    "cloud":     AssetType.SUPPORT_HARDWARE,
    "internet":  AssetType.SUPPORT_NETWORK,
    "vpn":       AssetType.SUPPORT_NETWORK,
    "load balancer": AssetType.SUPPORT_NETWORK,
    "balanceador": AssetType.SUPPORT_NETWORK,
    "process":   AssetType.PRIMARY_PROCESS,
    "proceso":   AssetType.PRIMARY_PROCESS,
}

# STRIDE por tipo de activo
_STRIDE_THREATS = {
    AssetType.PRIMARY_INFORMATION: [
        ("Acceso no autorizado a datos", "D", 3, 3),
        ("Modificación de datos (tampering)", "D", 2, 4),
        ("Fuga de información sensible", "D", 2, 4),
        ("Borrado de datos sin autorización", "D", 2, 4),
    ],
    AssetType.SUPPORT_SOFTWARE: [
        ("Inyección de código (SQLi/XSS/RCE)", "D", 3, 4),
        ("Autenticación débil o bypass", "D", 3, 4),
        ("Escalada de privilegios", "D", 2, 4),
        ("Vulnerabilidad en dependencias (CVE)", "D", 3, 3),
    ],
    AssetType.SUPPORT_HARDWARE: [
        ("Acceso físico no autorizado al servidor", "D", 2, 4),
        ("Fallo de hardware / indisponibilidad", "A", 2, 3),
        ("Compromiso del sistema operativo", "D", 2, 4),
        ("Ataque de fuerza bruta SSH/RDP", "D", 3, 3),
    ],
    AssetType.SUPPORT_NETWORK: [
        ("Interceptación de tráfico (MITM)", "D", 2, 4),
        ("Denegación de servicio (DDoS)", "D", 3, 3),
        ("Escaneo y reconocimiento de red", "D", 3, 2),
        ("Configuración incorrecta de firewall", "A", 2, 3),
    ],
    AssetType.SUPPORT_PERSONNEL: [
        ("Ingeniería social / phishing", "D", 4, 3),
        ("Uso indebido de accesos privilegiados", "D", 2, 4),
        ("Negligencia o error humano", "A", 3, 2),
    ],
    AssetType.PRIMARY_PROCESS: [
        ("Interrupción del proceso crítico", "D", 2, 4),
        ("Fraude en el proceso", "D", 2, 4),
        ("Fallo de continuidad de negocio", "A", 2, 3),
    ],
}


def parse_drawio_xml(xml_content: bytes) -> list[dict]:
    """Parsea diagrama diagrams.net (.drawio) y extrae nodos y conexiones.

    Retorna lista de {id, label, type, connections: [target_id]}
    """
    nodes = {}
    edges = []

    try:
        root = ET.fromstring(xml_content)

        for cell in root.iter("mxCell"):
            cell_id = cell.get("id", "")
            label = cell.get("label", "").strip()
            style = cell.get("style", "").lower()
            value = cell.get("value", label).strip()

            if not value or cell_id in ("0", "1"):
                continue

            # Detectar si es edge (conexión)
            source = cell.get("source")
            target = cell.get("target")

            if source and target:
                edges.append({"source": source, "target": target})
            elif label or value:
                # Es un nodo
                display_label = value or label
                # Detectar tipo por estilo o label
                asset_type = _infer_asset_type(display_label, style)
                nodes[cell_id] = {
                    "id": cell_id,
                    "label": display_label[:255],
                    "style": style[:100],
                    "asset_type": asset_type,
                    "connections": [],
                }

        # Añadir conexiones a nodos
        for edge in edges:
            src = edge["source"]
            tgt = edge["target"]
            if src in nodes:
                nodes[src]["connections"].append(tgt)

    except Exception as exc:
        logger.exception("Error parsing drawio XML: %s", exc)

    return list(nodes.values())


def _infer_asset_type(label: str, style: str = "") -> str:
    """Infiere el tipo de activo desde el label y estilo."""
    text = (label + " " + style).lower()
    for keyword, asset_type in _ASSET_TYPE_MAP.items():
        if keyword in text:
            return asset_type.value
    return AssetType.SUPPORT_SOFTWARE.value


def parse_text_description(description: str) -> list[dict]:
    """Parsea descripción textual de arquitectura y extrae componentes.

    Busca patrones: "Servidor X", "Base de datos Y", "API Z", etc.
    """
    nodes = []
    seen = set()

    # Patrones comunes
    patterns = [
        r"(?i)(servidor|server|database|base de datos|db|api|aplicacion|app|firewall|"
        r"load balancer|balanceador|vpn|router|switch|cloud|internet|proceso|process)"
        r"\s+(?:de\s+)?([A-Za-z0-9\s_-]{2,40})",
        r"(?i)([A-Za-z0-9][A-Za-z0-9\s_-]{2,30})\s+"
        r"(?:server|database|api|service|servicio|aplicacion)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, description):
            label = match.group(0).strip()[:255]
            if label.lower() not in seen:
                seen.add(label.lower())
                asset_type = _infer_asset_type(label)
                nodes.append({
                    "id": f"txt_{len(nodes)}",
                    "label": label,
                    "style": "",
                    "asset_type": asset_type,
                    "connections": [],
                })

    return nodes


async def analyze_with_ai(content: str, org_id: int, db: Session) -> list[dict]:
    """Usa Claude para analizar descripción/imagen y extraer componentes."""
    try:
        from app.services.rag_service import rag_service

        prompt = (
            "Analiza esta arquitectura de sistema y extrae una lista de componentes. "
            "Para cada componente indica: nombre, tipo (server/database/api/network/user/process), "
            "y con qué otros componentes se comunica. "
            "Responde SOLO con JSON array: "
            '[{"label":"nombre","type":"tipo","connections":["comp1","comp2"]}]. '
            f"Arquitectura: {content[:2000]}"
        )

        response = rag_service.ask(prompt, org_id=org_id)
        if not response:
            return []

        # Extraer JSON de la respuesta
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            components = json.loads(json_match.group(0))
            return [
                {
                    "id": f"ai_{i}",
                    "label": c.get("label", "")[:255],
                    "style": "",
                    "asset_type": _infer_asset_type(c.get("type", "") + " " + c.get("label", "")),
                    "connections": c.get("connections", []),
                }
                for i, c in enumerate(components)
                if isinstance(c, dict) and c.get("label")
            ]
    except Exception as exc:
        logger.debug("Error en análisis IA de arquitectura: %s", exc)
    return []


def create_assets_from_nodes(
    db: Session,
    nodes: list[dict],
    org_id: int,
    user_id: Optional[int] = None,
    diagram_name: str = "Diagrama importado",
) -> dict:
    """Crea Assets en BD desde nodos extraídos del diagrama.

    Retorna: {assets_created, threats_created, risks_created}
    """
    from app.services.risk_auto_generator import auto_generate_risks_for_asset

    stats = {"assets_created": 0, "threats_created": 0, "risks_created": 0}

    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()

    # Contador de códigos
    def _next_asset_code():
        from sqlalchemy import func as _func
        max_id = db.query(_func.max(Asset.id)).scalar() or 0
        return f"AST-{max_id + 1:04d}"

    for node in nodes:
        label = node.get("label", "").strip()
        if not label or len(label) < 2:
            continue

        # Verificar duplicado por nombre
        existing = db.query(Asset).filter(
            Asset.organization_id == org_id,
            Asset.name == label[:255],
        ).first()

        if existing:
            # Generar riesgos para el activo existente también
            new_risks = auto_generate_risks_for_asset(db, existing, user_id)
            stats["risks_created"] += len(new_risks)
            continue

        asset_type_str = node.get("asset_type", AssetType.SUPPORT_SOFTWARE.value)
        try:
            asset_type = AssetType(asset_type_str)
        except ValueError:
            asset_type = AssetType.SUPPORT_SOFTWARE

        asset = Asset(
            organization_id=org_id,
            code=_next_asset_code(),
            name=label,
            description=f"Activo extraído de arquitectura: {diagram_name}",
            asset_type=asset_type,
            owner_id=user_id,
        )
        db.add(asset)
        db.flush()
        stats["assets_created"] += 1

        # Crear amenazas STRIDE para este tipo de activo
        stride_threats = _STRIDE_THREATS.get(asset_type, [])
        for threat_name, origin, likelihood, consequence in stride_threats:
            threat_code = f"STRIDE-{asset_type.value[:4].upper()}-{len(threat_name)%100:02d}"
            existing_threat = db.query(Threat).filter(
                Threat.organization_id == org_id,
                Threat.name == threat_name,
            ).first()

            if not existing_threat:
                existing_threat = Threat(
                    organization_id=org_id,
                    code=threat_code,
                    name=threat_name,
                    description=f"Amenaza STRIDE para {asset_type.value}: {threat_name}",
                    origin=origin,
                    likelihood=likelihood,
                    consequence=consequence,
                )
                db.add(existing_threat)
                db.flush()
                stats["threats_created"] += 1

        # Auto-generar riesgos para el activo
        try:
            db.commit()
            db.refresh(asset)
            new_risks = auto_generate_risks_for_asset(db, asset, user_id)
            stats["risks_created"] += len(new_risks)
        except Exception as exc:
            logger.exception("Error generando riesgos para activo %s: %s", asset.code, exc)
            db.rollback()

    return stats
