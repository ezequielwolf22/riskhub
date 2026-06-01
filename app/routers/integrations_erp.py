"""Integraciones ERP/GRC via webhooks — SAP, Jagger, Sphera.

Cada sistema puede enviar eventos a RiskHub usando HMAC-SHA256 para autenticar
la peticion. RiskHub mapea los eventos a sus entidades internas (activos, riesgos,
incidentes, no conformidades).

Endpoints:
  POST /api/integrations/erp/sap/webhook     — eventos SAP (activos, usuarios, incidentes)
  POST /api/integrations/erp/jagger/webhook  — eventos Jagger (risks, assets)
  POST /api/integrations/erp/sphera/webhook  — eventos Sphera (incidents, compliance)
  GET  /api/integrations/erp/config          — obtener config (webhook key) por org
  PUT  /api/integrations/erp/config          — guardar config (webhook key) por org
  GET  /api/integrations/erp/events          — log de ultimos eventos recibidos
"""
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (
    Asset, AssetType, Incident, IncidentSeverity, IncidentStatus,
    IntegrationConfig, Organization, Risk, User,
)
from app.security import filter_by_org, get_current_user, require_admin
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/integrations/erp", tags=["integrations-erp"])

_INTEGRATION_NAME = "erp_webhooks"
_MAX_EVENTS = 100  # maximo de eventos en log en memoria por org

# Cache en memoria de eventos recibidos: {org_id: [event_dict, ...]}
_event_log: dict[int, list[dict]] = {}


# ── Cifrado (mismo patron que sharepoint, sso, ai_config) ─────────────────────

def _fernet_key() -> bytes:
    return base64.urlsafe_b64encode(
        hashlib.sha256(settings.secret_key.encode()).digest()
    )


def _encrypt(plain: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_fernet_key()).encrypt(plain.encode()).decode()


def _decrypt(token: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_fernet_key()).decrypt(token.encode()).decode()


# ── Config ─────────────────────────────────────────────────────────────────────

class ErpConfigIn(BaseModel):
    webhook_secret: str   # clave HMAC que el sistema externo usara para firmar
    enabled_sources: list[str] = ["sap", "jagger", "sphera"]


def _get_config(db: Session, org_id: Optional[int]) -> Optional[dict]:
    q = db.query(IntegrationConfig).filter(
        IntegrationConfig.name == _INTEGRATION_NAME,
        IntegrationConfig.organization_id == org_id,
    )
    ic = q.first()
    if not ic or not ic.config_encrypted:
        return None
    try:
        return json.loads(_decrypt(ic.config_encrypted))
    except Exception:
        return None


@router.get("/config")
def get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Devuelve la configuracion ERP (sin webhook_secret para admin normal)."""
    cfg = _get_config(db, current_user.organization_id)
    if not cfg:
        return {"configured": False}
    return {
        "configured": True,
        "webhook_secret": "***" if cfg.get("webhook_secret") else "",
        "enabled_sources": cfg.get("enabled_sources", ["sap", "jagger", "sphera"]),
        "webhook_url_sap":
            f"{settings.base_url if hasattr(settings,'base_url') else ''}/api/integrations/erp/sap/webhook",
        "webhook_url_jagger":
            f"{settings.base_url if hasattr(settings,'base_url') else ''}/api/integrations/erp/jagger/webhook",
        "webhook_url_sphera":
            f"{settings.base_url if hasattr(settings,'base_url') else ''}/api/integrations/erp/sphera/webhook",
    }


@router.put("/config")
def save_config(
    body: ErpConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Guarda o actualiza la configuracion ERP webhook."""
    if not body.webhook_secret or len(body.webhook_secret) < 16:
        raise HTTPException(400, "El webhook_secret debe tener al menos 16 caracteres")

    cfg_data = {
        "webhook_secret": body.webhook_secret,
        "enabled_sources": body.enabled_sources,
    }
    encrypted = _encrypt(json.dumps(cfg_data))

    existing = db.query(IntegrationConfig).filter(
        IntegrationConfig.name == _INTEGRATION_NAME,
        IntegrationConfig.organization_id == current_user.organization_id,
    ).first()

    if existing:
        existing.config_encrypted = encrypted
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(IntegrationConfig(
            name=_INTEGRATION_NAME,
            organization_id=current_user.organization_id,
            config_encrypted=encrypted,
        ))

    log_action(db, current_user.id, "update", "integration_erp", None,
               {"sources": body.enabled_sources})
    db.commit()
    return {"ok": True}


# ── Log de eventos ─────────────────────────────────────────────────────────────

@router.get("/events")
def get_events(
    current_user: User = Depends(require_admin),
):
    """Devuelve los ultimos eventos recibidos de sistemas ERP."""
    org_id = current_user.organization_id
    events = _event_log.get(org_id, [])
    return {"events": list(reversed(events[-_MAX_EVENTS:]))}


def _log_event(org_id: int, source: str, event_type: str, payload: dict, result: str) -> None:
    """Registra un evento en el log en memoria."""
    if org_id not in _event_log:
        _event_log[org_id] = []
    _event_log[org_id].append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "event_type": event_type,
        "result": result,
        "entity_name": payload.get("name") or payload.get("title") or "",
    })
    # Mantener solo los ultimos N eventos
    if len(_event_log[org_id]) > _MAX_EVENTS:
        _event_log[org_id] = _event_log[org_id][-_MAX_EVENTS:]


# ── Validacion HMAC ────────────────────────────────────────────────────────────

def _verify_hmac(secret: str, body: bytes, signature: str) -> bool:
    """Verifica la firma HMAC-SHA256 del payload."""
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    expected = mac.hexdigest()
    # Soporte para prefijo 'sha256=...' (convencion GitHub/estilo)
    sig = signature.replace("sha256=", "").strip()
    return hmac.compare_digest(expected, sig)


def _resolve_org_from_header(db: Session, org_id_header: Optional[str]) -> Optional[Organization]:
    """Resuelve la organizacion desde el header X-Org-Id."""
    if not org_id_header:
        return None
    try:
        org_id = int(org_id_header)
        return db.get(Organization, org_id)
    except (ValueError, TypeError):
        return None


# ── SAP Webhook ────────────────────────────────────────────────────────────────

@router.post("/sap/webhook")
async def sap_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_org_id: Optional[str] = Header(None, alias="X-Org-Id"),
    x_signature: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
):
    """Recibe eventos de SAP y los mapea a entidades de RiskHub.

    SAP debe enviar:
      Header X-Org-Id: <org_id>
      Header X-Hub-Signature-256: sha256=<hmac>
      Body JSON: { event_type, data: {...} }

    Tipos de evento soportados:
      asset.created / asset.updated  — crea/actualiza activo en RiskHub
      incident.created               — crea incidente en RiskHub
    """
    body = await request.body()
    org = _resolve_org_from_header(db, x_org_id)
    if not org:
        raise HTTPException(400, "Header X-Org-Id invalido o ausente")

    cfg = _get_config(db, org.id)
    if not cfg:
        raise HTTPException(400, "Integracion ERP no configurada para esta organizacion")
    if "sap" not in cfg.get("enabled_sources", []):
        raise HTTPException(403, "Fuente SAP deshabilitada en la configuracion")

    # C4: firma HMAC obligatoria — rechazar si ausente
    if not x_signature:
        raise HTTPException(401, "Cabecera X-Hub-Signature-256 requerida")
    if not _verify_hmac(cfg["webhook_secret"], body, x_signature):
        raise HTTPException(401, "Firma HMAC invalida")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Body JSON invalido")

    event_type = payload.get("event_type", "")
    data = payload.get("data", {})

    background_tasks.add_task(_process_sap_event, db, org.id, event_type, data)
    _log_event(org.id, "sap", event_type, data, "queued")
    return {"ok": True, "event_type": event_type}


def _process_sap_event(db: Session, org_id: int, event_type: str, data: dict) -> None:
    """Mapea eventos SAP a entidades RiskHub."""
    from app.database import SessionLocal
    db2 = SessionLocal()
    try:
        if event_type in ("asset.created", "asset.updated"):
            _upsert_asset_from_erp(db2, org_id, data, source="sap")
        elif event_type == "incident.created":
            _create_incident_from_erp(db2, org_id, data, source="sap")
        db2.commit()
        _log_event(org_id, "sap", event_type, data, "ok")
    except Exception as e:
        logger.error("sap_webhook: error procesando evento %s: %s", event_type, e)
        _log_event(org_id, "sap", event_type, data, f"error: {e}")
    finally:
        db2.close()


# ── Jagger Webhook ─────────────────────────────────────────────────────────────

@router.post("/jagger/webhook")
async def jagger_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_org_id: Optional[str] = Header(None, alias="X-Org-Id"),
    x_signature: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
):
    """Recibe eventos de Jagger y los mapea a entidades RiskHub."""
    body = await request.body()
    org = _resolve_org_from_header(db, x_org_id)
    if not org:
        raise HTTPException(400, "Header X-Org-Id invalido o ausente")

    cfg = _get_config(db, org.id)
    if not cfg:
        raise HTTPException(400, "Integracion ERP no configurada para esta organizacion")
    if "jagger" not in cfg.get("enabled_sources", []):
        raise HTTPException(403, "Fuente Jagger deshabilitada en la configuracion")

    # C4: firma HMAC obligatoria
    if not x_signature:
        raise HTTPException(401, "Cabecera X-Hub-Signature-256 requerida")
    if not _verify_hmac(cfg["webhook_secret"], body, x_signature):
        raise HTTPException(401, "Firma HMAC invalida")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Body JSON invalido")

    event_type = payload.get("event_type", "")
    data = payload.get("data", {})

    background_tasks.add_task(_process_jagger_event, db, org.id, event_type, data)
    _log_event(org.id, "jagger", event_type, data, "queued")
    return {"ok": True, "event_type": event_type}


def _process_jagger_event(db: Session, org_id: int, event_type: str, data: dict) -> None:
    from app.database import SessionLocal
    db2 = SessionLocal()
    try:
        if event_type in ("asset.created", "asset.updated"):
            _upsert_asset_from_erp(db2, org_id, data, source="jagger")
        db2.commit()
        _log_event(org_id, "jagger", event_type, data, "ok")
    except Exception as e:
        logger.error("jagger_webhook: error: %s", e)
        _log_event(org_id, "jagger", event_type, data, f"error: {e}")
    finally:
        db2.close()


# ── Sphera Webhook ─────────────────────────────────────────────────────────────

@router.post("/sphera/webhook")
async def sphera_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_org_id: Optional[str] = Header(None, alias="X-Org-Id"),
    x_signature: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
):
    """Recibe eventos de Sphera y los mapea a entidades RiskHub."""
    body = await request.body()
    org = _resolve_org_from_header(db, x_org_id)
    if not org:
        raise HTTPException(400, "Header X-Org-Id invalido o ausente")

    cfg = _get_config(db, org.id)
    if not cfg:
        raise HTTPException(400, "Integracion ERP no configurada para esta organizacion")
    if "sphera" not in cfg.get("enabled_sources", []):
        raise HTTPException(403, "Fuente Sphera deshabilitada en la configuracion")

    # C4: firma HMAC obligatoria
    if not x_signature:
        raise HTTPException(401, "Cabecera X-Hub-Signature-256 requerida")
    if not _verify_hmac(cfg["webhook_secret"], body, x_signature):
        raise HTTPException(401, "Firma HMAC invalida")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Body JSON invalido")

    event_type = payload.get("event_type", "")
    data = payload.get("data", {})

    background_tasks.add_task(_process_sphera_event, db, org.id, event_type, data)
    _log_event(org.id, "sphera", event_type, data, "queued")
    return {"ok": True, "event_type": event_type}


def _process_sphera_event(db: Session, org_id: int, event_type: str, data: dict) -> None:
    from app.database import SessionLocal
    db2 = SessionLocal()
    try:
        if event_type == "incident.created":
            _create_incident_from_erp(db2, org_id, data, source="sphera")
        db2.commit()
        _log_event(org_id, "sphera", event_type, data, "ok")
    except Exception as e:
        logger.error("sphera_webhook: error: %s", e)
        _log_event(org_id, "sphera", event_type, data, f"error: {e}")
    finally:
        db2.close()


# ── Helpers de mapeo ───────────────────────────────────────────────────────────

def _upsert_asset_from_erp(db: Session, org_id: int, data: dict, source: str) -> Asset:
    """Crea o actualiza un activo a partir de datos ERP."""
    name = (data.get("name") or data.get("asset_name") or "").strip()
    if not name:
        raise ValueError("Campo 'name' obligatorio en evento de activo")

    # Buscar activo existente por nombre dentro de la org
    asset = db.query(Asset).filter(
        Asset.organization_id == org_id,
        Asset.name == name,
    ).first()

    asset_type_raw = (data.get("type") or data.get("asset_type") or "support_software").lower()
    try:
        asset_type = AssetType(asset_type_raw)
    except ValueError:
        asset_type = AssetType.SUPPORT_SOFTWARE

    if not asset:
        asset = Asset(
            organization_id=org_id,
            name=name,
            asset_type=asset_type,
            description=f"Importado desde {source.upper()}. {data.get('description','')}"[:500],
            owner=data.get("owner") or data.get("responsible") or "",
            location=data.get("location") or "",
        )
        db.add(asset)
    else:
        # Actualizar campos basicos sin sobreescribir valoracion CIA
        asset.description = (
            f"Actualizado desde {source.upper()}. {data.get('description','')}"[:500]
        )
        if data.get("owner"):
            asset.owner = data["owner"]

    return asset


def _next_incident_code(db: Session) -> str:
    """Genera el siguiente codigo de incidente (INC-XXXX)."""
    n = db.query(Incident).count() + 1
    return f"INC-{n:04d}"


def _create_incident_from_erp(db: Session, org_id: int, data: dict, source: str) -> Incident:
    """Crea un incidente en RiskHub a partir de datos ERP."""
    title = (data.get("title") or data.get("name") or f"Incidente desde {source.upper()}").strip()

    # C5: el enum real usa P1-P4, no CRITICAL/HIGH/MEDIUM/LOW
    severity_raw = str(data.get("severity") or data.get("risk_level") or "medium").lower()
    severity_map = {
        "critical": IncidentSeverity.P1,
        "very_high": IncidentSeverity.P1,
        "high": IncidentSeverity.P2,
        "medium": IncidentSeverity.P3,
        "low": IncidentSeverity.P4,
    }
    severity = severity_map.get(severity_raw, IncidentSeverity.P3)

    source_note = f"[{source.upper()}] "
    incident = Incident(
        code=_next_incident_code(db),
        organization_id=org_id,
        title=(source_note + title)[:255],
        description=(
            f"Importado automaticamente desde {source.upper()}.\n"
            + str(data.get("description") or data.get("details") or "")
        )[:2000],
        severity=severity,
        status=IncidentStatus.OPEN,
    )
    db.add(incident)
    return incident
