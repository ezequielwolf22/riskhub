"""Operaciones de administracion del sistema (admin-only)."""
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from app.database import get_db
from app.models import Asset, ControlImplementation, Risk, Threat, User, Vulnerability
from app.security import require_admin
from app.services.audit_service import log_action
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _sqlite_path() -> Path:
    """Extrae la ruta del archivo SQLite desde la URL de conexion."""
    url = settings.db_url
    m = re.match(r"sqlite:///(.+)", url)
    if not m:
        raise HTTPException(400, "La copia de seguridad solo esta disponible para bases de datos SQLite")
    raw = m.group(1)
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        raise HTTPException(404, f"Archivo de base de datos no encontrado: {p}")
    return p


@router.get("/backup-db")
def backup_db(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Descarga una copia de seguridad de la base de datos SQLite."""
    db_path = _sqlite_path()

    # Copia a un temporal para evitar inconsistencias durante la lectura
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    shutil.copy2(str(db_path), tmp.name)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"riskhub_backup_{ts}.db"

    log_action(db, current_user.id, "export", "database", None,
               {"filename": fname, "size_bytes": db_path.stat().st_size})
    db.commit()

    return FileResponse(
        path=tmp.name,
        media_type="application/octet-stream",
        filename=fname,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        background=None,
    )


@router.get("/system-info")
def system_info(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Informacion del sistema para el panel de administracion."""
    db_path = _sqlite_path() if settings.db_url.startswith("sqlite") else None
    db_size_bytes = db_path.stat().st_size if db_path and db_path.exists() else None

    return {
        "version": _get_version(),
        "env": settings.env,
        "db_engine": "sqlite" if settings.db_url.startswith("sqlite") else "postgresql",
        "db_size_bytes": db_size_bytes,
        "total_users": db.query(User).count(),
        "total_assets": db.query(Asset).count(),
        "total_risks": db.query(Risk).count(),
        "total_threats": db.query(Threat).count(),
        "total_vulnerabilities": db.query(Vulnerability).count(),
        "total_controls": db.query(ControlImplementation).count(),
    }


def _get_version() -> str:
    try:
        from app import __version__
        return __version__
    except Exception:
        return "unknown"
