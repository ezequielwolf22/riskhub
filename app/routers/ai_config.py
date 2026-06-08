"""Configuracion del agente IA — API key, modelo, anonimizacion, perfil org."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import AiAnonymizationLevel, AiConfig, User
from app.security import decrypt_secret, encrypt_secret, filter_by_org, get_current_user, require_role

router = APIRouter(prefix="/api/ai/config", tags=["ai-config"])


# ---------- Utilidades de cifrado ----------

def resolve_api_key(cfg: AiConfig | None) -> str | None:
    """Devuelve la API key activa: primero per-tenant, luego global."""
    if cfg and cfg.api_key_encrypted:
        try:
            return decrypt_secret(cfg.api_key_encrypted)
        except Exception:
            return None
    return settings.anthropic_api_key


# ---------- Schemas ----------

class AiConfigIn(BaseModel):
    api_key: str | None = None
    model: str | None = None
    anonymization_level: AiAnonymizationLevel | None = None
    setup_completed: bool | None = None
    org_sector: str | None = None
    org_size: str | None = None
    org_critical_processes: str | None = None
    org_tech_stack: str | None = None


# ---------- Endpoints ----------

@router.get("/")
def get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = filter_by_org(db.query(AiConfig), AiConfig, current_user).first()
    if not cfg:
        return _default_out()
    return _cfg_out(cfg)


@router.put("/")
def update_config(
    payload: AiConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    cfg = filter_by_org(db.query(AiConfig), AiConfig, current_user).first()
    if not cfg:
        cfg = AiConfig(organization_id=current_user.organization_id)
        db.add(cfg)

    if payload.api_key is not None:
        cfg.api_key_encrypted = (
            encrypt_secret(payload.api_key) if payload.api_key else None
        )
    if payload.model is not None:
        cfg.model = payload.model
    if payload.anonymization_level is not None:
        cfg.anonymization_level = payload.anonymization_level
    if payload.setup_completed is not None:
        cfg.setup_completed = payload.setup_completed
    if payload.org_sector is not None:
        cfg.org_sector = payload.org_sector
    if payload.org_size is not None:
        cfg.org_size = payload.org_size
    if payload.org_critical_processes is not None:
        cfg.org_critical_processes = payload.org_critical_processes
    if payload.org_tech_stack is not None:
        cfg.org_tech_stack = payload.org_tech_stack

    db.commit()
    db.refresh(cfg)
    return _cfg_out(cfg)


@router.post("/test")
def test_connection(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    cfg = filter_by_org(db.query(AiConfig), AiConfig, current_user).first()
    api_key = resolve_api_key(cfg)
    if not api_key:
        raise HTTPException(400, "No hay API key configurada.")
    try:
        import anthropic
        model = (cfg.model if cfg else None) or "claude-haiku-4-5"
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}],
        )
        reply = resp.content[0].text if resp.content else ""
        return {"ok": True, "model": model, "reply": reply}
    except Exception as e:
        raise HTTPException(400, f"Error de conexion con la API: {e}")


def _cfg_out(cfg: AiConfig) -> dict:
    return {
        "model": cfg.model or "claude-opus-4-5",
        "anonymization_level": (
            cfg.anonymization_level.value if cfg.anonymization_level else "medium"
        ),
        "setup_completed": cfg.setup_completed or False,
        "org_sector": cfg.org_sector,
        "org_size": cfg.org_size,
        "org_critical_processes": cfg.org_critical_processes,
        "org_tech_stack": cfg.org_tech_stack,
        "has_api_key": bool(cfg.api_key_encrypted),
    }


def _default_out() -> dict:
    return {
        "model": "claude-opus-4-5",
        "anonymization_level": "medium",
        "setup_completed": False,
        "org_sector": None,
        "org_size": None,
        "org_critical_processes": None,
        "org_tech_stack": None,
        "has_api_key": bool(settings.anthropic_api_key),
    }
