"""Backups automatizados de la base de datos SQLite.

Copia consistente via la API de backup de sqlite3 (segura con WAL y con la
app en caliente), comprimida con gzip y con retencion configurable. Los
backups se guardan junto a la BD (en Docker, dentro del volumen persistente
riskhub-data, por lo que sobreviven a recreaciones del contenedor).

Variables de entorno:
- RISKHUB_BACKUP_DIR: directorio destino (default: <dir de la BD>/backups)
- RISKHUB_BACKUP_RETENTION_DAYS: dias de retencion (default: 14; 0 = sin purga)

Con PostgreSQL (database_url configurada) este servicio se desactiva: el
backup pasa a ser pg_dump gestionado fuera de la app (ver
docs/POSTGRES_MIGRATION_PLAN.md).
"""
import gzip
import logging
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

logger = logging.getLogger("riskhub.backup")

_RETENTION_DAYS = int(os.getenv("RISKHUB_BACKUP_RETENTION_DAYS", "14"))


def _backup_enabled() -> bool:
    return settings.db_url.startswith("sqlite") and settings.db_path != ":memory:"


def backup_dir() -> Path:
    custom = os.getenv("RISKHUB_BACKUP_DIR", "").strip()
    if custom:
        return Path(custom)
    return Path(settings.db_path).resolve().parent / "backups"


def run_backup() -> Path | None:
    """Crea un backup .db.gz consistente. Devuelve la ruta o None si no aplica."""
    if not _backup_enabled():
        logger.debug("Backup omitido: la BD no es un fichero SQLite.")
        return None

    src_path = Path(settings.db_path).resolve()
    if not src_path.exists():
        logger.warning("Backup omitido: la BD %s no existe.", src_path)
        return None

    dest_dir = backup_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"riskhub-{stamp}.db.gz"

    # 1) Copia consistente a un temporal con la API de backup de sqlite3
    #    (coherente aunque haya escrituras concurrentes en modo WAL).
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".db", dir=str(dest_dir))
    os.close(tmp_fd)
    try:
        src = sqlite3.connect(str(src_path))
        dst = sqlite3.connect(tmp_name)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        # 2) Comprimir
        with open(tmp_name, "rb") as f_in, gzip.open(dest, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass

    size_mb = dest.stat().st_size / (1024 * 1024)
    logger.info("Backup creado: %s (%.1f MB)", dest.name, size_mb)
    purge_old_backups()
    return dest


def purge_old_backups(retention_days: int | None = None) -> int:
    """Elimina backups mas antiguos que la retencion. Devuelve cuantos borro."""
    days = _RETENTION_DAYS if retention_days is None else retention_days
    if days <= 0:
        return 0
    cutoff = time.time() - days * 86400
    removed = 0
    d = backup_dir()
    if not d.exists():
        return 0
    for f in d.glob("riskhub-*.db.gz"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        logger.info("Backups purgados por retencion (%d dias): %d", days, removed)
    return removed


def list_backups() -> list[dict]:
    """Lista los backups disponibles, del mas reciente al mas antiguo."""
    d = backup_dir()
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("riskhub-*.db.gz"), reverse=True):
        try:
            st = f.stat()
        except OSError:
            continue
        out.append({
            "filename": f.name,
            "size_bytes": st.st_size,
            "created_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        })
    return out
