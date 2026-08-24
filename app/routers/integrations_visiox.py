"""Integracion VisioX — Digital Risk Protection.

Configuracion (API key cifrada por organizacion), prueba de conexion,
sincronizacion manual e historial de ejecuciones.

La API key la emite VisioX y esta atada a UN cliente suyo. El tenant destino en
RiskHub es la organizacion activa: la correspondencia entre ambos la establece
quien configura, y por eso el endpoint de prueba devuelve SIEMPRE el nombre del
cliente al que resuelve la key. Un 200 pelado no basta para confiar en que los
datos que se van a importar son los del cliente correcto.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ExternalFinding, IntegrationConfig, IntegrationSyncRun, User
from app.security import get_current_user, require_admin
from app.services import visiox_service, visiox_sync_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/integrations/visiox", tags=["integrations"])
logger = logging.getLogger(__name__)


class VisioXConfigIn(BaseModel):
    api_key: Optional[str] = None     # si viene vacio, se conserva la existente
    enabled: bool = True
    create_assets: bool = True
    auto_sync: bool = True


@router.get("/config")
def get_config(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Estado de la integracion. NUNCA devuelve la API key, solo si la hay."""
    cfg = visiox_sync_service.get_config(db, user.organization_id) or {}
    last = db.query(IntegrationSyncRun).filter(
        IntegrationSyncRun.organization_id == user.organization_id,
        IntegrationSyncRun.integration == visiox_sync_service.INTEGRATION_NAME,
    ).order_by(IntegrationSyncRun.id.desc()).first()

    return {
        "configured": bool(cfg.get("api_key")),
        "enabled": cfg.get("enabled", False),
        "create_assets": cfg.get("create_assets", True),
        "auto_sync": cfg.get("auto_sync", True),
        "base_url": cfg.get("base_url") or visiox_service.DEFAULT_BASE_URL,
        "client_name": cfg.get("client_name"),
        "client_slug": cfg.get("client_slug"),
        "last_run": _run_dict(last) if last else None,
    }


@router.put("/config")
def put_config(
    body: VisioXConfigIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    cfg = visiox_sync_service.get_config(db, user.organization_id) or {}

    if body.api_key:
        # Se valida contra VisioX ANTES de guardar: una key mal pegada que se
        # persiste produce un sync roto que nadie mira hasta semanas despues.
        try:
            who = visiox_service.whoami(visiox_service.DEFAULT_BASE_URL, body.api_key.strip())
        except visiox_service.VisioXError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        client = who.get("client") or {}
        cfg["api_key"] = body.api_key.strip()
        cfg["client_name"] = client.get("name")
        cfg["client_slug"] = client.get("slug")
        cfg["client_id"] = client.get("id")

    if not cfg.get("api_key"):
        raise HTTPException(status_code=400, detail="Falta la API key de VisioX")

    cfg["enabled"] = body.enabled
    cfg["create_assets"] = body.create_assets
    cfg["auto_sync"] = body.auto_sync
    cfg.setdefault("base_url", visiox_service.DEFAULT_BASE_URL)

    visiox_sync_service.save_config(db, user.organization_id, cfg, user.id)
    log_action(db, user.id, "update", "integration_config", visiox_sync_service.INTEGRATION_NAME,
               {"client_slug": cfg.get("client_slug"), "enabled": body.enabled,
                "create_assets": body.create_assets, "key_updated": bool(body.api_key)},
               organization_id=user.organization_id, ip_address=_ip(request))
    db.commit()
    return {"status": "ok", "client_name": cfg.get("client_name"), "client_slug": cfg.get("client_slug")}


@router.delete("/config")
def delete_config(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    ic = db.query(IntegrationConfig).filter_by(
        name=visiox_sync_service.INTEGRATION_NAME,
        organization_id=user.organization_id,
    ).first()
    if ic:
        db.delete(ic)
        db.commit()
    log_action(db, user.id, "delete", "integration_config", visiox_sync_service.INTEGRATION_NAME,
               {"integration": "visiox"},
               organization_id=user.organization_id, ip_address=_ip(request))
    db.commit()
    return {"status": "ok"}


@router.post("/test")
def test_connection(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Comprueba la key guardada y dice a que cliente de VisioX resuelve."""
    cfg = visiox_sync_service.get_config(db, user.organization_id)
    if not cfg or not cfg.get("api_key"):
        raise HTTPException(status_code=400, detail="La integracion con VisioX no esta configurada")
    try:
        who = visiox_service.whoami(
            cfg.get("base_url") or visiox_service.DEFAULT_BASE_URL, cfg["api_key"]
        )
    except visiox_service.VisioXError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "ok", "client": who.get("client"), "key": who.get("key")}


@router.post("/sync")
def run_sync(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Sincronizacion manual. Sincrona a proposito: el usuario acaba de pulsar
    el boton y quiere ver el resultado, no un 'se ha encolado'."""
    cfg = visiox_sync_service.get_config(db, user.organization_id)
    if not cfg or not cfg.get("api_key"):
        raise HTTPException(status_code=400, detail="La integracion con VisioX no esta configurada")

    result = visiox_sync_service.sync_organization(
        db, user.organization_id, triggered_by="manual", triggered_by_id=user.id
    )
    log_action(db, user.id, "sync", "integration_config", visiox_sync_service.INTEGRATION_NAME,
               {k: result.get(k) for k in
                ("status", "items_read", "created", "updated", "closed",
                 "assets_created", "risks_created", "incidents_created")},
               organization_id=user.organization_id, ip_address=_ip(request))
    db.commit()
    if result["status"] == "error":
        raise HTTPException(status_code=502, detail=result.get("error") or "Fallo la sincronizacion")
    return result


@router.get("/runs")
def list_runs(
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = db.query(IntegrationSyncRun).filter(
        IntegrationSyncRun.organization_id == user.organization_id,
        IntegrationSyncRun.integration == visiox_sync_service.INTEGRATION_NAME,
    ).order_by(IntegrationSyncRun.id.desc()).limit(min(limit, 100)).all()
    return [_run_dict(r) for r in rows]


@router.get("/summary")
def get_summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """KPIs en vivo desde VisioX. No dependen de que el sync haya corrido."""
    cfg = visiox_sync_service.get_config(db, user.organization_id)
    if not cfg or not cfg.get("api_key"):
        raise HTTPException(status_code=400, detail="La integracion con VisioX no esta configurada")
    try:
        return visiox_service.summary(
            cfg.get("base_url") or visiox_service.DEFAULT_BASE_URL, cfg["api_key"]
        )
    except visiox_service.VisioXError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/findings/{finding_id}/evidence")
def reveal_evidence(
    finding_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Revela la evidencia sensible de un hallazgo (credenciales, identidades).

    Cuatro salvaguardas, porque esto devuelve datos personales:
      - Exige rol de administracion, no basta con estar autenticado.
      - Es un endpoint aparte: el listado normal NUNCA sirve estos campos.
      - Cada lectura queda registrada en el log de auditoria con quien y cuando.
      - Solo alcanza hallazgos de la organizacion activa.
    """
    f = db.query(ExternalFinding).filter(
        ExternalFinding.id == finding_id,
        ExternalFinding.organization_id == user.organization_id,
    ).first()
    if not f:
        raise HTTPException(status_code=404, detail="Hallazgo no encontrado")
    if not f.evidence_encrypted:
        raise HTTPException(status_code=404, detail="Este hallazgo no tiene evidencia protegida")

    try:
        import json
        evidence = json.loads(visiox_sync_service.decrypt(f.evidence_encrypted))
    except Exception as exc:  # noqa: BLE001
        logger.exception("No se pudo descifrar la evidencia del hallazgo %s", finding_id)
        raise HTTPException(status_code=500, detail="No se pudo descifrar la evidencia") from exc

    # Cada revelacion de datos personales queda con nombre y hora.
    log_action(db, user.id, "read", "external_finding", str(finding_id),
               {"external_id": f.external_id, "reason": "reveal_protected_evidence"},
               organization_id=user.organization_id, ip_address=_ip(request))
    db.commit()
    return {"finding_id": finding_id, "external_id": f.external_id, "evidence": evidence}


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request and request.client else None


def _run_dict(r: IntegrationSyncRun) -> dict:
    return {
        "id": r.id,
        "status": r.status,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "duration_ms": r.duration_ms,
        "items_read": r.items_read,
        "created": r.created,
        "updated": r.updated,
        "closed": r.closed,
        "assets_created": r.assets_created,
        "risks_created": r.risks_created,
        "incidents_created": r.incidents_created,
        "complete": r.complete,
        "error_message": r.error_message,
        "triggered_by": r.triggered_by,
    }
