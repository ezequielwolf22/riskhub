"""Integracion con Microsoft SharePoint via Microsoft Graph API.

Configuracion necesaria (Azure AD App Registration):
  - Permisos de aplicacion: Sites.Read.All, Files.Read.All
  - Tipo de autenticacion: client_credentials (app-only)

Los secretos se almacenan cifrados con Fernet (misma clave que el agente IA).
"""
import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import AiDocumentCategory, AiDocumentStatus, IntegrationConfig, User
from app.security import get_current_user, require_analyst, require_admin
from app.services.audit_service import log_action
from app.services import sharepoint_service as sp

router = APIRouter(prefix="/api/integrations/sharepoint", tags=["sharepoint"])

_INTEGRATION_NAME = "sharepoint"
_MAX_FILE_SIZE = 20 * 1024 * 1024   # 20 MB


# ---------- Cifrado (mismo mecanismo que ai_config) ----------

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


# ---------- Helpers ----------

def _get_config(db: Session, organization_id=None) -> Optional[dict]:
    """Devuelve la configuracion de SharePoint descifrada o None si no existe."""
    q = db.query(IntegrationConfig).filter(IntegrationConfig.name == _INTEGRATION_NAME)
    if organization_id is not None:
        q = q.filter(IntegrationConfig.organization_id == organization_id)
    ic = q.first()
    if not ic or not ic.config_encrypted:
        return None
    try:
        return json.loads(_decrypt(ic.config_encrypted))
    except Exception:
        return None


def _resolve_token(db: Session, organization_id=None) -> str:
    """Obtiene un access token de MS Graph usando las credenciales almacenadas."""
    cfg = _get_config(db, organization_id)
    if not cfg:
        raise HTTPException(400, "SharePoint no configurado. Ve a Integraciones > SharePoint para configurar.")
    try:
        return sp.get_token(cfg["tenant_id"], cfg["client_id"], cfg["client_secret"])
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- Schemas ----------

class SharePointConfigIn(BaseModel):
    tenant_id: str
    client_id: str
    client_secret: str   # nunca se devuelve en la respuesta


class SharePointConfigOut(BaseModel):
    configured: bool
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    updated_at: Optional[str] = None


# ---------- Endpoints ----------

@router.get("/config", response_model=SharePointConfigOut)
def get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve la configuracion actual (sin client_secret)."""
    cfg = _get_config(db, current_user.organization_id)
    if not cfg:
        return SharePointConfigOut(configured=False)
    ic = db.query(IntegrationConfig).filter(
        IntegrationConfig.name == _INTEGRATION_NAME,
        IntegrationConfig.organization_id == current_user.organization_id,
    ).first()
    return SharePointConfigOut(
        configured=True,
        tenant_id=cfg.get("tenant_id"),
        client_id=cfg.get("client_id"),
        updated_at=ic.updated_at.isoformat() if ic and ic.updated_at else None,
    )


@router.put("/config")
def save_config(
    body: SharePointConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Guarda las credenciales de SharePoint (cifradas). Solo admin."""
    if not body.tenant_id or not body.client_id or not body.client_secret:
        raise HTTPException(400, "Todos los campos son obligatorios.")

    encrypted = _encrypt(json.dumps({
        "tenant_id": body.tenant_id.strip(),
        "client_id": body.client_id.strip(),
        "client_secret": body.client_secret.strip(),
    }))

    ic = db.query(IntegrationConfig).filter(
        IntegrationConfig.name == _INTEGRATION_NAME,
        IntegrationConfig.organization_id == current_user.organization_id,
    ).first()
    if not ic:
        ic = IntegrationConfig(name=_INTEGRATION_NAME, organization_id=current_user.organization_id)
        db.add(ic)
    ic.config_encrypted = encrypted
    ic.updated_at = datetime.now(timezone.utc)
    ic.updated_by_id = current_user.id

    log_action(db, current_user.id, "update", "integration_config", _INTEGRATION_NAME,
               {"tenant_id": body.tenant_id, "client_id": body.client_id})
    db.commit()
    return {"ok": True, "message": "Configuracion guardada correctamente."}


@router.post("/test")
def test_connection(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Prueba la conexion con Microsoft Graph API."""
    token = _resolve_token(db, current_user.organization_id)
    try:
        sites = sp.list_sites(token)
        return {
            "ok": True,
            "message": f"Conexion correcta. Se encontraron {len(sites)} sitios accesibles.",
            "sites_count": len(sites),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/sites")
def list_sites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    search: str = Query("*", description="Termino de busqueda de sitios"),
):
    """Lista los sitios de SharePoint accesibles."""
    token = _resolve_token(db, current_user.organization_id)
    try:
        return {"sites": sp.list_sites(token, search)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/drives")
def list_drives(
    site_id: str = Query(..., description="ID del sitio de SharePoint"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista las bibliotecas de documentos de un sitio."""
    token = _resolve_token(db, current_user.organization_id)
    try:
        return {"drives": sp.list_drives(token, site_id)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/files")
def list_files(
    drive_id: str = Query(..., description="ID de la biblioteca"),
    item_id: str = Query("root", description="ID del item (carpeta). 'root' para la raiz."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista el contenido de una carpeta en SharePoint."""
    token = _resolve_token(db, current_user.organization_id)
    try:
        items = sp.list_children(token, drive_id, item_id)
        return {
            "items": items,
            "importable_count": sum(1 for i in items
                                    if i["kind"] == "file"
                                    and sp.is_importable(i["name"], i.get("mime", ""))),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


class ImportRequest(BaseModel):
    items: list[dict]   # lista de {drive_id, item_id, name, mime}
    category: str = "other"


@router.post("/import")
def import_files(
    body: ImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Descarga e importa los archivos seleccionados como documentos del agente IA."""
    from app.models import AiDocument
    from app.services.document_service import process_document, doc_path
    import uuid

    try:
        cat = AiDocumentCategory(body.category)
    except ValueError:
        cat = AiDocumentCategory.OTHER

    token = _resolve_token(db, current_user.organization_id)

    results = {"imported": [], "skipped": [], "errors": []}

    for item in body.items[:20]:   # maximo 20 archivos por lote
        drive_id = item.get("drive_id", "")
        item_id = item.get("item_id", "")
        name = item.get("name", "archivo.bin")
        mime = item.get("mime", "")

        if not sp.is_importable(name, mime):
            results["skipped"].append(f"{name} (tipo no soportado)")
            continue

        try:
            data = sp.download_file(token, drive_id, item_id)
        except ValueError as e:
            results["errors"].append(f"{name}: {e}")
            continue

        if len(data) > _MAX_FILE_SIZE:
            results["skipped"].append(f"{name} (supera 20 MB)")
            continue

        # Inferir MIME real desde extension
        ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        ext_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
            ".csv": "text/plain",
        }
        inferred_mime = ext_map.get(ext, mime or "text/plain")

        unique_name = f"{uuid.uuid4().hex}_{name}"
        dest = doc_path(unique_name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

        doc = AiDocument(
            filename=unique_name,
            original_name=name,
            category=cat,
            status=AiDocumentStatus.PENDING,
            file_size=len(data),
            mime_type=inferred_mime,
            uploaded_by_id=current_user.id,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        try:
            process_document(db, doc.id)
            db.refresh(doc)
            results["imported"].append(name)
        except Exception as e:
            results["errors"].append(f"{name}: error al procesar ({e})")

    log_action(db, current_user.id, "import", "sharepoint", None, {
        "imported": len(results["imported"]),
        "skipped": len(results["skipped"]),
        "errors": len(results["errors"]),
    })
    db.commit()
    return results
