"""Integracion con Microsoft SharePoint via Microsoft Graph API.

Configuracion necesaria (Azure AD App Registration):
  - Permisos de aplicacion: Sites.Read.All, Files.Read.All
  - Tipo de autenticacion: client_credentials (app-only)

Los secretos se almacenan cifrados con Fernet (misma clave que el agente IA).
"""
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("riskhub.sharepoint")

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.i18n import get_lang, t as _t

from app.database import get_db
from app.models import AiDocumentCategory, AiDocumentStatus, IntegrationConfig, User
from app.security import get_current_user, require_analyst, require_admin
from app.services.audit_service import log_action
from app.services import sharepoint_service as sp

router = APIRouter(prefix="/api/integrations/sharepoint", tags=["sharepoint"])

_INTEGRATION_NAME = "sharepoint"
_MAX_FILE_SIZE = 20 * 1024 * 1024   # 20 MB


# ---------- Helpers ----------

def _resolve_token(db: Session, organization_id=None) -> str:
    """Obtiene un access token de MS Graph usando las credenciales almacenadas."""
    cfg = sp.get_config(db, organization_id)
    if not cfg:
        raise HTTPException(400, "SharePoint no configurado. Ve a Integraciones > SharePoint para configurar.")
    try:
        # A4: pasar org_id para aislar tokens por tenant en la cache
        return sp.get_token(cfg["tenant_id"], cfg["client_id"], cfg["client_secret"],
                            org_id=organization_id)
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
    cfg = sp.get_config(db, current_user.organization_id)
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
    request: Request,
    body: SharePointConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Guarda las credenciales de SharePoint (cifradas). Solo admin.

    Preserva allowed_folders/delta_links/sync_enabled si ya existian (solo se
    actualizan las credenciales, no se pisa el resto de la configuracion).
    """
    lang = get_lang(request)
    if not body.tenant_id or not body.client_id or not body.client_secret:
        raise HTTPException(400, _t("common.bad_request", lang))

    ic = db.query(IntegrationConfig).filter(
        IntegrationConfig.name == _INTEGRATION_NAME,
        IntegrationConfig.organization_id == current_user.organization_id,
    ).first()
    cfg = {}
    if ic and ic.config_encrypted:
        try:
            cfg = sp.decrypt_json(ic.config_encrypted)
        except Exception:
            cfg = {}
    cfg.update({
        "tenant_id": body.tenant_id.strip(),
        "client_id": body.client_id.strip(),
        "client_secret": body.client_secret.strip(),
    })

    if not ic:
        ic = IntegrationConfig(name=_INTEGRATION_NAME, organization_id=current_user.organization_id)
        db.add(ic)
    ic.config_encrypted = sp.encrypt_json(cfg)
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


@router.get("/sites/resolve")
def resolve_site(
    url: str = Query(..., description="URL completa del sitio de SharePoint"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resuelve un sitio especifico por su URL.

    Alternativa a /sites cuando el permiso de la app esta restringido a un
    sitio concreto (Sites.Selected) y la busqueda general devuelve 403.
    """
    token = _resolve_token(db, current_user.organization_id)
    try:
        return sp.resolve_site(token, url)
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


# ---------- Carpetas permitidas (allowlist de sincronizacion) ----------

class AllowedFolder(BaseModel):
    site_id: str
    site_name: str = ""
    drive_id: str
    drive_name: str = ""
    item_id: str
    path: str = ""
    name: str


class AllowedFoldersIn(BaseModel):
    folders: list[AllowedFolder]


@router.get("/allowed-folders")
def get_allowed_folders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve las carpetas que RiskHub tiene permiso de leer/importar."""
    cfg = sp.get_config(db, current_user.organization_id) or {}
    return {"folders": cfg.get("allowed_folders", [])}


@router.put("/allowed-folders")
def set_allowed_folders(
    body: AllowedFoldersIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Reemplaza la lista de carpetas permitidas. Solo admin.

    Es un allowlist plano: cualquier documento dentro de estas carpetas queda
    disponible para todos los analisis (riesgos, compliance, TPRM, etc.), no
    hay mapeo carpeta->tipo de analisis.
    """
    folders = [f.model_dump() for f in body.folders]
    try:
        sp.update_config(db, current_user.organization_id, current_user.id, allowed_folders=folders)
    except ValueError as e:
        raise HTTPException(400, str(e))
    log_action(db, current_user.id, "update", "integration_config", "sharepoint_allowed_folders",
               {"count": len(folders)})
    db.commit()
    return {"ok": True, "count": len(folders)}


# ---------- Sincronizacion automatica (deteccion de cambios) ----------

class SyncSettingsIn(BaseModel):
    sync_enabled: bool


@router.get("/sync-status")
def get_sync_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = sp.get_config(db, current_user.organization_id) or {}
    return {
        "sync_enabled": bool(cfg.get("sync_enabled", False)),
        "last_sync_at": cfg.get("last_sync_at"),
        "last_sync_summary": cfg.get("last_sync_summary"),
        "allowed_folders_count": len(cfg.get("allowed_folders") or []),
    }


@router.put("/sync-settings")
def set_sync_settings(
    body: SyncSettingsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        sp.update_config(db, current_user.organization_id, current_user.id, sync_enabled=body.sync_enabled)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/sync")
def sync_now(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Lanza una sincronizacion inmediata de las carpetas permitidas."""
    from app.services.sharepoint_sync_service import sync_organization
    if not current_user.organization_id:
        raise HTTPException(400, "Sin organizacion asociada.")
    summary = sync_organization(db, current_user.organization_id)
    log_action(db, current_user.id, "sync", "sharepoint", None, {
        "imported": summary["imported"], "updated": summary["updated"],
        "deleted": summary["deleted"], "errors": len(summary["errors"]),
    })
    db.commit()
    return summary


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
    from app.services.document_service import process_document, save_document_file
    import uuid

    try:
        cat = AiDocumentCategory(body.category)
    except ValueError:
        cat = AiDocumentCategory.OTHER

    token = _resolve_token(db, current_user.organization_id)
    cfg = sp.get_config(db, current_user.organization_id) or {}
    allowed_folders = cfg.get("allowed_folders") or []

    results = {"imported": [], "skipped": [], "errors": []}

    for item in body.items[:20]:   # maximo 20 archivos por lote
        drive_id = item.get("drive_id", "")
        item_id = item.get("item_id", "")
        name = item.get("name", "archivo.bin")
        mime = item.get("mime", "")

        if not sp.is_importable(name, mime):
            results["skipped"].append(f"{name} (tipo no soportado)")
            continue

        if not sp.item_is_allowed(token, allowed_folders, drive_id, item_id):
            results["errors"].append(f"{name}: fuera de las carpetas permitidas configuradas")
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
        save_document_file(data, unique_name)

        doc = AiDocument(
            filename=unique_name,
            original_name=name,
            category=cat,
            status=AiDocumentStatus.PENDING,
            file_size=len(data),
            mime_type=inferred_mime,
            uploaded_by_id=current_user.id,
            organization_id=current_user.organization_id,
            source="sharepoint",
            source_drive_id=drive_id,
            source_item_id=item_id,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        # G09: process_document + analisis ISMS se lanzan en background para no bloquear el request
        doc_id = doc.id
        def _bg_process(did=doc_id):
            try:
                from app.database import SessionLocal
                with SessionLocal() as db_bg:
                    process_document(db_bg, did)
                    doc_bg = db_bg.query(AiDocument).filter_by(id=did).first()
                    if doc_bg and doc_bg.status == AiDocumentStatus.INDEXED:
                        from app.services.isms_analysis_service import analyze_document_for_isms
                        analyze_document_for_isms(db_bg, did)
            except Exception as exc:
                logger.warning("SharePoint: error procesando doc %d: %s", did, exc)
                return
            try:
                from app.services.iso_clause_extractor import run_extraction_for_document
                run_extraction_for_document(did)
            except Exception as exc:
                logger.warning("SharePoint: error extrayendo clausulas doc %d: %s", did, exc)
        threading.Thread(target=_bg_process, daemon=True).start()
        results["imported"].append(name)

    log_action(db, current_user.id, "import", "sharepoint", None, {
        "imported": len(results["imported"]),
        "skipped": len(results["skipped"]),
        "errors": len(results["errors"]),
    })
    db.commit()
    return results
