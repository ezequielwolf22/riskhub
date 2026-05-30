"""Trust portal público y auditor portal con acceso read-only tokenizado."""
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import IntegrationConfig, RiskContext, User
from app.security import get_current_user, require_admin

router = APIRouter(prefix="/api/portal", tags=["portal"])

# ─── Helpers token ─────────────────────────────────────────────────────────────

def _get_or_create_token(db: Session, org_id: int, token_type: str) -> str:
    """Obtiene o crea un token persistente para el portal."""
    import json, base64
    from app.config import settings
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.secret_key.encode()).digest()
    )
    name = f"portal_{token_type}"
    ic = db.query(IntegrationConfig).filter_by(
        name=name, organization_id=org_id
    ).first()
    if ic and ic.config_encrypted:
        try:
            cfg = json.loads(Fernet(key).decrypt(ic.config_encrypted.encode()).decode())
            return cfg.get("token", "")
        except Exception:
            pass
    # Crear nuevo token
    token = secrets.token_urlsafe(32)
    encrypted = Fernet(key).encrypt(json.dumps({"token": token}).encode()).decode()
    if not ic:
        ic = IntegrationConfig(name=name, organization_id=org_id)
        db.add(ic)
    ic.config_encrypted = encrypted
    db.commit()
    return token


def _verify_token(db: Session, org_id: int, token_type: str, token: str) -> bool:
    """Verifica que el token es válido para la org."""
    stored = _get_or_create_token(db, org_id, token_type)
    return secrets.compare_digest(stored, token)


# ─── Trust Portal config ────────────────────────────────────────────────────────

class TrustPortalConfig(BaseModel):
    enabled: bool = True
    show_frameworks: bool = True
    show_risks_summary: bool = False
    show_last_audit: bool = True
    custom_message: Optional[str] = None


def _get_portal_config(db: Session, org_id: int) -> dict:
    import json, base64
    from app.config import settings
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.secret_key.encode()).digest()
    )
    ic = db.query(IntegrationConfig).filter_by(
        name="trust_portal_config", organization_id=org_id
    ).first()
    if ic and ic.config_encrypted:
        try:
            return json.loads(Fernet(key).decrypt(ic.config_encrypted.encode()).decode())
        except Exception:
            pass
    return {"enabled": True, "show_frameworks": True, "show_risks_summary": False,
            "show_last_audit": True, "custom_message": None}


def _save_portal_config(db: Session, org_id: int, cfg: dict) -> None:
    import json, base64
    from app.config import settings
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.secret_key.encode()).digest()
    )
    encrypted = Fernet(key).encrypt(json.dumps(cfg).encode()).decode()
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
def save_trust_config(body: TrustPortalConfig,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(require_admin)):
    _save_portal_config(db, current_user.organization_id, body.model_dump())
    return {"message": "Configuración del Trust Portal guardada"}


@router.post("/trust/regenerate-token")
def regenerate_trust_token(db: Session = Depends(get_db),
                           current_user: User = Depends(require_admin)):
    """Regenera el token del trust portal (invalida el anterior)."""
    import json, base64
    from app.config import settings
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.secret_key.encode()).digest()
    )
    org_id = current_user.organization_id
    new_token = secrets.token_urlsafe(32)
    encrypted = Fernet(key).encrypt(json.dumps({"token": new_token}).encode()).decode()
    ic = db.query(IntegrationConfig).filter_by(
        name="portal_trust", organization_id=org_id
    ).first()
    if not ic:
        ic = IntegrationConfig(name="portal_trust", organization_id=org_id)
        db.add(ic)
    ic.config_encrypted = encrypted
    db.commit()
    return {"token": new_token, "public_url": f"/portal/trust/{org_id}/{new_token}"}


@router.get("/auditor/config")
def get_auditor_config(db: Session = Depends(get_db),
                       current_user: User = Depends(require_admin)):
    org_id = current_user.organization_id
    token = _get_or_create_token(db, org_id, "auditor")
    return {
        "token": token,
        "auditor_url": f"/portal/auditor/{org_id}/{token}",
        "note": "Comparte esta URL con tu auditor externo. Acceso de solo lectura.",
    }


@router.post("/auditor/regenerate-token")
def regenerate_auditor_token(db: Session = Depends(get_db),
                              current_user: User = Depends(require_admin)):
    import json, base64
    from app.config import settings
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.secret_key.encode()).digest()
    )
    org_id = current_user.organization_id
    new_token = secrets.token_urlsafe(32)
    encrypted = Fernet(key).encrypt(json.dumps({"token": new_token}).encode()).decode()
    ic = db.query(IntegrationConfig).filter_by(
        name="portal_auditor", organization_id=org_id
    ).first()
    if not ic:
        ic = IntegrationConfig(name="portal_auditor", organization_id=org_id)
        db.add(ic)
    ic.config_encrypted = encrypted
    db.commit()
    return {"token": new_token, "auditor_url": f"/portal/auditor/{org_id}/{new_token}"}


# ─── Public trust portal (sin auth, acceso por token) ────────────────────────────

@router.get("/trust/data/{org_id}/{token}")
def get_trust_data(org_id: int, token: str, db: Session = Depends(get_db)):
    """API pública del trust portal. Sin auth — acceso solo con token."""
    if not _verify_token(db, org_id, "trust", token):
        raise HTTPException(404, "Portal no encontrado")

    cfg = _get_portal_config(db, org_id)
    if not cfg.get("enabled", True):
        raise HTTPException(404, "Portal no disponible")

    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    org_name = ctx.organization_name if ctx else "Organización"
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
    framework: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """API del auditor portal. Solo lectura — acceso por token."""
    if not _verify_token(db, org_id, "auditor", token):
        raise HTTPException(404, "Portal de auditor no encontrado")

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

    # Evidence index (read-only)
    from app.models import Evidence
    evidences = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.is_current == True,
        Evidence.compliance_framework.isnot(None),
    ).all()
    result["evidence_count"] = len(evidences)
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
        for e in evidences[:200]
    ]

    return result
