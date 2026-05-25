"""Rate limiting en memoria para endpoints criticos (OWASP A07)."""
import time
from threading import Lock
from typing import Dict, Tuple

# Ventana de 5 minutos; maximo 10 intentos fallidos antes de bloquear
_LOGIN_WINDOW_S: int = 300
_LOGIN_MAX_ATTEMPTS: int = 10

_lock = Lock()
_store: Dict[str, Tuple[int, float]] = {}   # ip -> (intentos, inicio_ventana)


def check_login_allowed(ip: str) -> bool:
    """Devuelve True si la IP tiene permitido intentar login; False si esta bloqueada."""
    now = time.monotonic()
    with _lock:
        if ip in _store:
            count, start = _store[ip]
            # Ventana expirada: resetear
            if now - start > _LOGIN_WINDOW_S:
                _store[ip] = (1, now)
                return True
            # Dentro de la ventana: comprobar limite
            if count >= _LOGIN_MAX_ATTEMPTS:
                return False
            _store[ip] = (count + 1, start)
        else:
            _store[ip] = (1, now)
    return True


def reset_login_counter(ip: str) -> None:
    """Resetea el contador de intentos para una IP tras un login exitoso."""
    with _lock:
        _store.pop(ip, None)


def remaining_lockout_seconds(ip: str) -> int:
    """Segundos restantes de bloqueo para una IP (0 si no esta bloqueada)."""
    now = time.monotonic()
    with _lock:
        if ip not in _store:
            return 0
        count, start = _store[ip]
        if count < _LOGIN_MAX_ATTEMPTS:
            return 0
        elapsed = now - start
        if elapsed >= _LOGIN_WINDOW_S:
            return 0
        return int(_LOGIN_WINDOW_S - elapsed)
