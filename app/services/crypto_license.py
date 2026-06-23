"""Validacion criptografica de licencias para despliegues on-premise.

Flujo del vendor:
  1. Vendor genera un JWT firmado con su clave RSA privada (ver tools/gen_license.py)
  2. El fichero license.jwt se entrega al cliente junto con el despliegue Docker
  3. La app valida el JWT en arranque y periodicamente usando la clave publica embebida
  4. Si la licencia expira (no-pago) -> modo restringido (solo lectura)
  5. Para renovar: el vendor genera un nuevo JWT y el admin lo sube via UI

La clave PRIVADA NUNCA se incluye en la imagen Docker ni en el repositorio.
Solo la clave publica esta embebida en este fichero.
"""
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import jwt as pyjwt

logger = logging.getLogger("riskhub.crypto_license")

# ── Clave publica RSA del vendor (embebida en la app) ──────────────────────
# IMPORTANTE: generar un nuevo par de claves para produccion con tools/gen_license.py
# La clave privada correspondiente debe estar SOLO en poder del vendor.
_VENDOR_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAv1o5y/uMyq4c3OLw+Q5q
D+zSpUsPfhO/wBN2PggNyny572iyPu08zM7HDQmGa38tT9Nf93vHjolj5zGN3NtD
6rsEAX9ZdNF/JaLhD89s4FLJrM5zxoSrw6/GJR8PexcSRvUU53PCoFSXu1q/jbWT
jVqX6eAbeje+t+GCFd/2ycnTDo2el0dnneCaN5fUiJLkUYGNComC9OrTUW19/apM
3mkf211QflaRSw9upek4GAZS1kAGEGMZ6fjaqM9wBvDOuPuFY0MyR0mgdDgD5sbD
7aLXFP+6UoQWMGMs+b+f7leUNr2QoMq3JwW8CWwcD3XqL8owAx0kgvkchGS3/yui
swIDAQAB
-----END PUBLIC KEY-----"""

_LICENSE_ISSUER = "riskhub-vendor"
_DEFAULT_LICENSE_PATH = "/srv/data/license.jwt"
_GRACE_DAYS_DEFAULT = 30  # dias en modo solo-lectura tras expirar

# ── Estado global de la licencia ──────────────────────────────────────────

@dataclass
class LicenseState:
    present: bool = False           # fichero license.jwt encontrado
    valid: bool = False             # firma y formato correctos
    expired: bool = False           # JWT expirado
    in_grace: bool = False          # dentro del periodo de gracia post-expiry
    plan: str = "unknown"
    org_name: str = ""
    issued_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    days_left: Optional[int] = None
    grace_days: int = _GRACE_DAYS_DEFAULT
    modules: list = field(default_factory=list)
    error: str = ""

    @property
    def read_only(self) -> bool:
        """True cuando la app debe operar en modo solo lectura."""
        if not self.present:
            return False  # sin fichero: modo dev/vendor, sin restriccion
        return self.expired and not self.in_grace

    @property
    def restricted(self) -> bool:
        """True cuando la app debe bloquear escrituras (fuera del periodo de gracia)."""
        return self.read_only


_state: LicenseState = LicenseState()


def get_state() -> LicenseState:
    return _state


def _license_file_path() -> str:
    return os.environ.get("RISKHUB_LICENSE_FILE", _DEFAULT_LICENSE_PATH)


def load_and_validate() -> LicenseState:
    """Carga y valida el fichero de licencia. Actualiza el estado global."""
    global _state
    path = _license_file_path()

    if not Path(path).exists():
        _state = LicenseState(present=False, valid=False,
                              error="Fichero de licencia no encontrado (modo dev)")
        logger.info("crypto_license: sin fichero de licencia — modo desarrollo")
        return _state

    try:
        token = Path(path).read_text().strip()
    except OSError as e:
        _state = LicenseState(present=True, valid=False, error=f"No se pudo leer: {e}")
        logger.error("crypto_license: error leyendo fichero: %s", e)
        return _state

    try:
        payload = pyjwt.decode(
            token,
            _VENDOR_PUBLIC_KEY,
            algorithms=["RS256"],
            issuer=_LICENSE_ISSUER,
            options={"verify_exp": False},  # comprobamos exp manualmente para el periodo de gracia
        )
    except pyjwt.InvalidSignatureError:
        _state = LicenseState(present=True, valid=False, error="Firma invalida")
        logger.error("crypto_license: firma invalida")
        return _state
    except pyjwt.DecodeError as e:
        _state = LicenseState(present=True, valid=False, error=f"Token malformado: {e}")
        logger.error("crypto_license: token malformado: %s", e)
        return _state
    except Exception as e:
        _state = LicenseState(present=True, valid=False, error=str(e))
        logger.error("crypto_license: error inesperado: %s", e)
        return _state

    now = datetime.now(timezone.utc)
    exp_ts = payload.get("exp")
    iat_ts = payload.get("iat")
    grace_days = int(payload.get("grace_days", _GRACE_DAYS_DEFAULT))

    expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else None
    issued_at = datetime.fromtimestamp(iat_ts, tz=timezone.utc) if iat_ts else None

    expired = bool(expires_at and expires_at < now)
    days_left = None
    in_grace = False

    if expires_at:
        delta = (expires_at - now).days
        days_left = max(delta, 0) if not expired else 0
        if expired:
            days_since_expiry = (now - expires_at).days
            in_grace = days_since_expiry <= grace_days

    _state = LicenseState(
        present=True,
        valid=True,
        expired=expired,
        in_grace=in_grace,
        plan=payload.get("plan", "unknown"),
        org_name=payload.get("sub", ""),
        issued_at=issued_at,
        expires_at=expires_at,
        days_left=days_left,
        grace_days=grace_days,
        modules=payload.get("modules", []),
        error="",
    )

    if expired and not in_grace:
        logger.warning("crypto_license: licencia EXPIRADA — modo solo lectura activo")
    elif expired and in_grace:
        logger.warning("crypto_license: licencia en periodo de gracia (%d dias restantes de gracia)",
                       grace_days - (now - expires_at).days)
    else:
        logger.info("crypto_license: licencia valida — plan=%s org=%s dias_restantes=%s",
                    _state.plan, _state.org_name, _state.days_left)
    return _state


def state_for_api() -> dict:
    """Representacion JSON del estado de la licencia para el endpoint de admin."""
    s = _state
    return {
        "present": s.present,
        "valid": s.valid,
        "expired": s.expired,
        "in_grace": s.in_grace,
        "read_only": s.read_only,
        "plan": s.plan,
        "org_name": s.org_name,
        "issued_at": s.issued_at.isoformat() if s.issued_at else None,
        "expires_at": s.expires_at.isoformat() if s.expires_at else None,
        "days_left": s.days_left,
        "grace_days": s.grace_days,
        "modules": s.modules,
        "error": s.error,
    }
