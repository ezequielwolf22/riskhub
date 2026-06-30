"""Rate limiting para endpoints criticos (OWASP A07).

Persistencia: SQLite via un fichero separado (rate_limits.db) en el mismo
directorio que la BD principal. Esto garantiza que los bloqueos sobreviven
reinicios del contenedor, eliminando el vector de "restart para resetear limites".

Fallback: si no se puede escribir en disco, vuelve al modo en memoria con
un warning. El comportamiento de seguridad se mantiene en el mismo proceso.
"""
import logging
import sqlite3
import os
import time
from pathlib import Path
from threading import Lock
from typing import Dict, Tuple

logger = logging.getLogger("riskhub.rate_limiter")

# Parametros de la politica de bloqueo
_LOGIN_WINDOW_S: int = 300      # ventana de 5 minutos
_LOGIN_MAX_ATTEMPTS: int = 10   # maximo de intentos antes de bloquear

# Fallback en memoria (se usa si SQLite no esta disponible)
_mem_lock = Lock()
_mem_store: Dict[str, Tuple[int, float]] = {}

# SQLite de rate limiting
_db_path: str | None = None
_db_lock = Lock()
_use_sqlite = False


def _resolve_db_path() -> str:
    """Determina la ruta del fichero SQLite de rate limiting."""
    from app.config import settings
    base = Path(settings.db_path)
    if base.name == ":memory:":
        return ":memory:"
    return str(base.parent / "rate_limits.db")


def _init_sqlite() -> bool:
    """Inicializa la tabla SQLite. Devuelve True si tiene exito."""
    global _db_path, _use_sqlite
    try:
        _db_path = _resolve_db_path()
        conn = sqlite3.connect(_db_path, check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                ip TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0,
                window_start REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_window ON login_attempts(window_start)")
        conn.commit()
        conn.close()
        _use_sqlite = True
        logger.debug("Rate limiter: modo persistente SQLite (%s)", _db_path)
        return True
    except Exception as exc:
        logger.warning("Rate limiter: no se pudo inicializar SQLite (%s). Modo en memoria.", exc)
        _use_sqlite = False
        return False


# Intentar inicializar SQLite en la importacion del modulo.
# Si falla, se usa el fallback en memoria silenciosamente.
try:
    _init_sqlite()
except Exception:
    _use_sqlite = False


# ---------- API publica ----------

def check_login_allowed(ip: str) -> bool:
    """Devuelve True si la IP tiene permitido intentar login; False si esta bloqueada."""
    if _use_sqlite:
        return _check_sqlite(ip)
    return _check_memory(ip)


def reset_login_counter(ip: str) -> None:
    """Resetea el contador de intentos para una IP tras un login exitoso."""
    if _use_sqlite:
        _reset_sqlite(ip)
    else:
        _reset_memory(ip)


def reset_all_counters() -> None:
    """Elimina todos los registros de intentos (util para tests y mantenimiento)."""
    if _use_sqlite:
        with _db_lock:
            try:
                conn = sqlite3.connect(_db_path, check_same_thread=False)
                conn.execute("DELETE FROM login_attempts")
                conn.commit()
                conn.close()
            except Exception as exc:
                logger.warning("Rate limiter SQLite error en reset_all: %s", exc)
    else:
        with _mem_lock:
            _mem_store.clear()


def remaining_lockout_seconds(ip: str) -> int:
    """Segundos restantes de bloqueo para una IP (0 si no esta bloqueada)."""
    if _use_sqlite:
        return _remaining_sqlite(ip)
    return _remaining_memory(ip)


# ---------- Implementacion SQLite ----------

def _check_sqlite(ip: str) -> bool:
    now = time.time()
    with _db_lock:
        try:
            conn = sqlite3.connect(_db_path, check_same_thread=False)
            row = conn.execute(
                "SELECT count, window_start FROM login_attempts WHERE ip = ?", (ip,)
            ).fetchone()

            if row is None:
                conn.execute(
                    "INSERT INTO login_attempts (ip, count, window_start) VALUES (?, 1, ?)",
                    (ip, now),
                )
                conn.commit()
                conn.close()
                return True

            count, start = row
            if now - start > _LOGIN_WINDOW_S:
                conn.execute(
                    "UPDATE login_attempts SET count = 1, window_start = ? WHERE ip = ?",
                    (now, ip),
                )
                conn.commit()
                conn.close()
                return True

            if count >= _LOGIN_MAX_ATTEMPTS:
                conn.close()
                return False

            conn.execute(
                "UPDATE login_attempts SET count = count + 1 WHERE ip = ?", (ip,)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as exc:
            logger.warning("Rate limiter SQLite error en check: %s", exc)
            return True  # en caso de error, permitir el intento


def _reset_sqlite(ip: str) -> None:
    with _db_lock:
        try:
            conn = sqlite3.connect(_db_path, check_same_thread=False)
            conn.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("Rate limiter SQLite error en reset: %s", exc)


def _remaining_sqlite(ip: str) -> int:
    now = time.time()
    with _db_lock:
        try:
            conn = sqlite3.connect(_db_path, check_same_thread=False)
            row = conn.execute(
                "SELECT count, window_start FROM login_attempts WHERE ip = ?", (ip,)
            ).fetchone()
            conn.close()
            if not row:
                return 0
            count, start = row
            if count < _LOGIN_MAX_ATTEMPTS:
                return 0
            elapsed = now - start
            if elapsed >= _LOGIN_WINDOW_S:
                return 0
            return int(_LOGIN_WINDOW_S - elapsed)
        except Exception:
            return 0


# ---------- Fallback en memoria ----------

def _check_memory(ip: str) -> bool:
    now = time.monotonic()
    with _mem_lock:
        if ip in _mem_store:
            count, start = _mem_store[ip]
            if now - start > _LOGIN_WINDOW_S:
                _mem_store[ip] = (1, now)
                return True
            if count >= _LOGIN_MAX_ATTEMPTS:
                return False
            _mem_store[ip] = (count + 1, start)
        else:
            _mem_store[ip] = (1, now)
    return True


def _reset_memory(ip: str) -> None:
    with _mem_lock:
        _mem_store.pop(ip, None)


def _remaining_memory(ip: str) -> int:
    now = time.monotonic()
    with _mem_lock:
        if ip not in _mem_store:
            return 0
        count, start = _mem_store[ip]
        if count < _LOGIN_MAX_ATTEMPTS:
            return 0
        elapsed = now - start
        if elapsed >= _LOGIN_WINDOW_S:
            return 0
        return int(_LOGIN_WINDOW_S - elapsed)
