"""Trust portal público y auditor portal con acceso read-only tokenizado."""
import json
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import IntegrationConfig, RiskContext, User
from app.i18n import get_lang, t as _t
from app.security import decrypt_secret, encrypt_secret, get_current_user, require_admin

router = APIRouter(prefix="/api/portal", tags=["portal"])

# Simple in-memory rate limiter for unauthenticated portal endpoints
_portal_rl_lock = Lock()
_portal_rl: dict = defaultdict(list)   # ip -> [timestamps]
_PORTAL_WINDOW = 60    # 1 minute
_PORTAL_MAX_REQ = 20   # max 20 requests per minute per IP


def _portal_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _portal_rl_lock:
        _portal_rl[ip] = [t for t in _portal_rl[ip] if now - t < _PORTAL_WINDOW]
        if len(_portal_rl[ip]) >= _PORTAL_MAX_REQ:
            raise HTTPException(429, _t("portal.rate_limited", get_lang(request)))
        _portal_rl[ip].append(now)

# ─── Helpers token ─────────────────────────────────────────────────────────────

def _get_or_create_token(db: Session, org_id: int, token_type: str) -> str:
    """Obtiene o crea un token persistente para el portal."""
    name = f"portal_{token_type}"
    ic = db.query(IntegrationConfig).filter_by(
        name=name, organization_id=org_id
    ).first()
    if ic and ic.config_encrypted:
        try:
            cfg = json.loads(decrypt_secret(ic.config_encrypted))
            return cfg.get("token", "")
        except Exception:
            pass
    # Crear nuevo token
    token = secrets.token_urlsafe(32)
    encrypted = encrypt_secret(json.dumps({"token": token}))
    if not ic:
        ic = IntegrationConfig(name=name, organization_id=org_id)
        db.add(ic)
    ic.config_encrypted = encrypted
    db.commit()
    return token


def _verify_token(db: Session, org_id: int, token_type: str, token: str) -> bool:
    """Verifica que el token es válido para la org sin crearlo si no existe."""
    name = f"portal_{token_type}"
    ic = db.query(IntegrationConfig).filter_by(name=name, organization_id=org_id).first()
    if not ic or not ic.config_encrypted:
        return False
    try:
        cfg = json.loads(decrypt_secret(ic.config_encrypted))
        stored = cfg.get("token", "")
        if not stored:
            return False
        return secrets.compare_digest(stored, token)
    except Exception:
        return False


# ─── Trust Portal config ────────────────────────────────────────────────────────

class TrustPortalConfig(BaseModel):
    enabled: bool = True
    show_frameworks: bool = True
    show_risks_summary: bool = False
    show_last_audit: bool = True
    custom_message: Optional[str] = None


def _get_portal_config(db: Session, org_id: int) -> dict:
    ic = db.query(IntegrationConfig).filter_by(
        name="trust_portal_config", organization_id=org_id
    ).first()
    if ic and ic.config_encrypted:
        try:
            return json.loads(decrypt_secret(ic.config_encrypted))
        except Exception:
            pass
    return {"enabled": True, "show_frameworks": True, "show_risks_summary": False,
            "show_last_audit": True, "custom_message": None}


def _save_portal_config(db: Session, org_id: int, cfg: dict) -> None:
    encrypted = encrypt_secret(json.dumps(cfg))
    ic = db.query(IntegrationConfig).filter_by(
        name="trust_portal_config", organization_id=org_id
    ).first()
    if not ic:
        ic = IntegrationConfig(name="trust_portal_config", organization_id=org_id)
        db.add(ic)
    ic.config_encrypted = encrypted
    db.commit()


# ─── Admin endpoints (configuración) ────────────────────────────────────────────

@router.get("/trust/config")
def get_trust_config(db: Session = Depends(get_db),
                     current_user: User = Depends(require_admin)):
    org_id = current_user.organization_id
    token = _get_or_create_token(db, org_id, "trust")
    cfg = _get_portal_config(db, org_id)
    return {
        "token": token,
        "public_url": f"/portal/trust/{org_id}/{token}",
        **cfg,
    }


@router.put("/trust/config")
def save_trust_config(request: Request, body: TrustPortalConfig,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(require_admin)):
    _save_portal_config(db, current_user.organization_id, body.model_dump())
    return {"message": _t("portal.config_saved", get_lang(request))}


@router.post("/trust/regenerate-token")
def regenerate_trust_token(db: Session = Depends(get_db),
                           current_user: User = Depends(require_admin)):
    """Regenera el token del trust portal (invalida el anterior)."""
    from app.services.audit_service import log_action
    org_id = current_user.organization_id
    new_token = secrets.token_urlsafe(32)
    encrypted = encrypt_secret(json.dumps({"token": new_token}))
    ic = db.query(IntegrationConfig).filter_by(
        name="portal_trust", organization_id=org_id
    ).first()
    if not ic:
        ic = IntegrationConfig(name="portal_trust", organization_id=org_id)
        db.add(ic)
    ic.config_encrypted = encrypted
    db.commit()
    log_action(db, current_user.id, "regenerate", "portal_token", "trust", {})
    return {"token": new_token, "public_url": f"/portal/trust/{org_id}/{new_token}"}


@router.get("/auditor/config")
def get_auditor_config(request: Request, db: Session = Depends(get_db),
                       current_user: User = Depends(require_admin)):
    org_id = current_user.organization_id
    token = _get_or_create_token(db, org_id, "auditor")
    return {
        "token": token,
        "auditor_url": f"/portal/auditor/{org_id}/{token}",
        "note": _t("portal.share_hint", get_lang(request)),
    }


@router.post("/auditor/regenerate-token")
def regenerate_auditor_token(db: Session = Depends(get_db),
                              current_user: User = Depends(require_admin)):
    from app.services.audit_service import log_action
    org_id = current_user.organization_id
    new_token = secrets.token_urlsafe(32)
    encrypted = encrypt_secret(json.dumps({"token": new_token}))
    ic = db.query(IntegrationConfig).filter_by(
        name="portal_auditor", organization_id=org_id
    ).first()
    if not ic:
        ic = IntegrationConfig(name="portal_auditor", organization_id=org_id)
        db.add(ic)
    ic.config_encrypted = encrypted
    db.commit()
    log_action(db, current_user.id, "regenerate", "portal_token", "auditor", {})
    return {"token": new_token, "auditor_url": f"/portal/auditor/{org_id}/{new_token}"}


# ─── Public trust portal (sin auth, acceso por token) ────────────────────────────

@router.get("/trust/data/{org_id}/{token}")
def get_trust_data(org_id: int, token: str, request: Request, db: Session = Depends(get_db)):
    """API pública del trust portal. Sin auth — acceso solo con token."""
    _portal_rate_limit(request)
    if not _verify_token(db, org_id, "trust", token):
        raise HTTPException(404, _t("portal.not_found", get_lang(request)))

    cfg = _get_portal_config(db, org_id)
    if not cfg.get("enabled", True):
        raise HTTPException(404, _t("portal.not_available", get_lang(request)))

    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    org_name = ctx.organization_name if ctx else _t("portal.org_fallback", get_lang(request))
    active_frameworks = (ctx.active_frameworks or []) if ctx else []

    result = {
        "org_name": org_name,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "config": cfg,
    }

    if cfg.get("show_frameworks") and active_frameworks:
        from app.services.compliance_service import get_framework_compliance_status
        fw_statuses = []
        for fw_code in active_frameworks:
            try:
                status = get_framework_compliance_status(db, org_id, fw_code)
                fw_statuses.append({
                    "framework": fw_code,
                    "framework_name": status.get("framework_name", fw_code),
                    "overall_pct": status.get("overall_pct", 0),
                    "mandatory_pct": status.get("mandatory_pct", 0),
                    "is_audit_ready": status.get("is_audit_ready", False),
                })
            except Exception:
                pass
        result["frameworks"] = fw_statuses

    if cfg.get("show_risks_summary"):
        from app.models import Risk, RiskStatus
        total = db.query(Risk).filter(Risk.organization_id == org_id).count()
        accepted = db.query(Risk).filter(
            Risk.organization_id == org_id,
            Risk.status == RiskStatus.ACCEPTED,
        ).count()
        result["risks"] = {
            "total": total,
            "accepted_pct": int(accepted / total * 100) if total else 100,
        }

    return result


# ─── Auditor portal data (read-only por token) ────────────────────────────────────

@router.get("/auditor/data/{org_id}/{token}")
def get_auditor_data(
    org_id: int,
    token: str,
    request: Request,
    framework: Optional[str] = Query(None),
    evidence_limit: int = Query(50, ge=1, le=200),
    evidence_offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """API del auditor portal. Solo lectura — acceso por token."""
    _portal_rate_limit(request)
    if not _verify_token(db, org_id, "auditor", token):
        raise HTTPException(404, _t("portal.auditor_not_found", get_lang(request)))

    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    active_frameworks = (ctx.active_frameworks or []) if ctx else []

    result = {
        "org_name": ctx.organization_name if ctx else "Organización",
        "active_frameworks": active_frameworks,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Framework overview
    from app.services.compliance_service import get_framework_compliance_status
    fw_list = [framework] if framework and framework in active_frameworks else active_frameworks
    result["frameworks"] = []
    for fw_code in fw_list:
        try:
            status = get_framework_compliance_status(db, org_id, fw_code)
            result["frameworks"].append(status)
        except Exception:
            pass

    # Evidence index (read-only, paginated)
    from app.models import Evidence
    ev_q = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.is_current == True,
        Evidence.compliance_framework.isnot(None),
    )
    result["evidence_count"] = ev_q.count()
    evidences = ev_q.offset(evidence_offset).limit(evidence_limit).all()
    result["evidence_limit"] = evidence_limit
    result["evidence_offset"] = evidence_offset
    result["evidence_index"] = [
        {
            "code": e.code,
            "title": e.title,
            "framework": e.compliance_framework,
            "requirement": e.compliance_requirement,
            "type": e.evidence_type.value if hasattr(e.evidence_type, "value") else str(e.evidence_type),
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "expires_at": e.expires_at.isoformat() if e.expires_at else None,
            "file_hash": e.file_hash,
        }
        for e in evidences
    ]

    return result
