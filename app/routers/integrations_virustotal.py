"""Integracion VirusTotal — configuracion y test de conexion.

Almacena la API key cifrada en IntegrationConfig por organizacion.
El motor OSINT la usa automaticamente al escanear URLs.
"""
import base64
import hashlib
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import IntegrationConfig, User
from app.security import get_current_user, require_admin

router = APIRouter(prefix="/api/integrations/virustotal", tags=["integrations"])

_INTEGRATION_NAME = "virustotal"


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


def _get_config(db: Session, org_id: Optional[int]) -> Optional[dict]:
    ic = db.query(IntegrationConfig).filter_by(
        name=_INTEGRATION_NAME, organization_id=org_id
    ).first()
    if not ic:
        # Fallback: config global (sin org)
        ic = db.query(IntegrationConfig).filter_by(name=_INTEGRATION_NAME).first()
    if not ic or not ic.config_encrypted:
        return None
    try:
        return json.loads(_decrypt(ic.config_encrypted))
    except Exception:
        return None


def get_vt_api_key(db: Session, org_id: Optional[int]) -> Optional[str]:
    """Resuelve la API key de VirusTotal para un tenant: BD primero, entorno como fallback."""
    cfg = _get_config(db, org_id)
    if cfg and cfg.get("api_key"):
        return cfg["api_key"]
    return settings.virustotal_api_key or None


class VtConfigIn(BaseModel):
    api_key: Optional[str] = None


class VtConfigOut(BaseModel):
    configured: bool
    has_api_key: bool


@router.get("/config", response_model=VtConfigOut)
def get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = _get_config(db, current_user.organization_id)
    has_key = bool(
        (cfg and cfg.get("api_key")) or settings.virustotal_api_key
    )
    return VtConfigOut(configured=has_key, has_api_key=has_key)


@router.put("/config")
def save_config(
    body: VtConfigIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    lang = get_lang(request)
    if not body.api_key or not body.api_key.strip():
        raise HTTPException(400, _t("integrations_virustotal.api_key_empty", lang))
    data = {"api_key": body.api_key.strip()}
    encrypted = _encrypt(json.dumps(data))
    ic = db.query(IntegrationConfig).filter_by(
        name=_INTEGRATION_NAME,
        organization_id=current_user.organization_id,
    ).first()
    if not ic:
        ic = IntegrationConfig(
            name=_INTEGRATION_NAME,
            organization_id=current_user.organization_id,
        )
        db.add(ic)
    ic.config_encrypted = encrypted
    ic.updated_by_id = current_user.id
    db.commit()
    return {"ok": True, "message": _t("integrations_virustotal.config_saved", lang)}


@router.delete("/config", status_code=204)
def delete_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ic = db.query(IntegrationConfig).filter_by(
        name=_INTEGRATION_NAME,
        organization_id=current_user.organization_id,
    ).first()
    if ic:
        db.delete(ic)
        db.commit()


@router.post("/test")
async def test_connection(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Prueba la API key contra la API de VirusTotal con una URL conocida benigna."""
    lang = get_lang(request)
    api_key = get_vt_api_key(db, current_user.organization_id)
    if not api_key:
        raise HTTPException(400, _t("integrations_virustotal.no_api_key_configured", lang))

    import aiohttp
    try:
        # Consultar info del usuario (endpoint ligero que valida la key)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://www.virustotal.com/api/v3/users/{api_key}",
                headers={"x-apikey": api_key},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 401:
                    raise HTTPException(400, _t("integrations_virustotal.invalid_api_key", lang))
                if resp.status == 429:
                    raise HTTPException(400, _t("integrations_virustotal.rate_limit_exceeded", lang))
                if resp.status not in (200, 204):
                    raise HTTPException(
                        400,
                        _t("integrations_virustotal.vt_error_status", lang, status=resp.status),
                    )
                data = await resp.json()
                user_data = data.get("data", {}).get("attributes", {})
                quota = user_data.get("quotas", {})
                daily = quota.get("api_requests_daily", {})
                return {
                    "ok": True,
                    "message": _t("integrations_virustotal.connection_ok", lang),
                    "user": user_data.get("email", ""),
                    "quota_used": daily.get("used", 0),
                    "quota_limit": daily.get("allowed", 0),
                }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            400,
            _t("integrations_virustotal.connection_failed", lang, error=exc),
        )
