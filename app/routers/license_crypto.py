"""Endpoints de gestion de la licencia criptografica (on-premise).

GET  /api/license/status              — estado actual de la licencia (admin)
POST /api/license/upload              — subir un nuevo fichero license.jwt (admin)
POST /api/license/generate/{org_id}  — genera y descarga un JWT para una org (superadmin)
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.i18n import get_lang, t as _t
from app.models import User
from app.security import require_admin, require_superadmin
from app.services import crypto_license as lic

logger = logging.getLogger("riskhub.license_crypto")
router = APIRouter(prefix="/api/license", tags=["license"])

_MAX_LICENSE_BYTES = 8 * 1024  # un JWT firmado nunca supera 8 KB


@router.get("/status")
def get_license_status(current_user: User = Depends(require_admin)):
    """Devuelve el estado de la licencia criptografica actual."""
    return lic.state_for_api()


@router.post("/upload")
async def upload_license(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
):
    """Sube un nuevo fichero license.jwt y lo valida antes de guardarlo."""
    lang = get_lang(request)
    content = await file.read()
    if len(content) > _MAX_LICENSE_BYTES:
        raise HTTPException(400, _t("license_crypto.file_too_large", lang))

    token = content.decode("utf-8", errors="ignore").strip()
    if not token.startswith("ey"):
        raise HTTPException(400, _t("license_crypto.invalid_jwt_format", lang))

    # Guardar temporalmente y revalidar
    license_path = Path(os.environ.get("RISKHUB_LICENSE_FILE", "/srv/data/license.jwt"))
    license_path.parent.mkdir(parents=True, exist_ok=True)

    backup_path = license_path.with_suffix(".jwt.bak")
    old_content = license_path.read_text() if license_path.exists() else None

    try:
        license_path.write_text(token)
        new_state = lic.load_and_validate()
        if not new_state.valid:
            # Revertir al fichero anterior si el nuevo no es valido
            if old_content:
                license_path.write_text(old_content)
                lic.load_and_validate()
            else:
                license_path.unlink(missing_ok=True)
                lic.load_and_validate()
            raise HTTPException(422, _t("license_crypto.invalid_license", lang, error=new_state.error))

        logger.info("crypto_license: nueva licencia subida por user=%s plan=%s",
                    current_user.email, new_state.plan)
        return {"ok": True, "license": lic.state_for_api()}

    except HTTPException:
        raise
    except Exception as e:
        if old_content:
            license_path.write_text(old_content)
        logger.error("crypto_license: error guardando licencia: %s", e)
        raise HTTPException(500, _t("license_crypto.save_error", lang, error=e))


@router.post("/generate/{org_id}")
def generate_org_license(
    request: Request,
    org_id: int,
    days: int = 365,
    grace_days: int = 30,
    current_user: User = Depends(require_superadmin),
):
    """Genera un fichero license.jwt firmado para una organizacion concreta.

    Requiere la variable de entorno RISKHUB_LICENSE_PRIVATE_KEY con la clave
    RSA privada del vendor en formato PEM.
    """
    lang = get_lang(request)
    private_key_pem = os.environ.get("RISKHUB_LICENSE_PRIVATE_KEY", "").strip()
    if not private_key_pem:
        raise HTTPException(
            400,
            _t("license_crypto.private_key_not_configured", lang),
        )

    from sqlalchemy.orm import Session
    from app.database import SessionLocal
    from app.models import Organization
    from app.services.license_service import get_license

    db: Session = SessionLocal()
    try:
        org = db.get(Organization, org_id)
        if not org:
            raise HTTPException(404, _t("license_crypto.organization_not_found", lang))

        db_license = get_license(db, org_id)
        plan = db_license.plan if db_license else "starter"

        # Si la DB tiene fecha de expiry, respetar; si no, usar days
        if db_license and db_license.expires_at and db_license.expires_at > datetime.now(timezone.utc):
            exp = db_license.expires_at
        else:
            exp = datetime.now(timezone.utc) + timedelta(days=days)
    finally:
        db.close()

    import jwt as pyjwt
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "riskhub-vendor",
        "sub": org.name,
        "plan": plan,
        "modules": ["all"],
        "grace_days": grace_days,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    try:
        token = pyjwt.encode(payload, private_key_pem, algorithm="RS256")
        if not isinstance(token, str):
            token = token.decode()
    except Exception as e:
        raise HTTPException(500, _t("license_crypto.sign_error", lang, error=e))

    safe_name = org.name.lower().replace(" ", "_")[:32]
    filename = f"license_{safe_name}_{exp.strftime('%Y%m%d')}.jwt"
    logger.info("crypto_license: JWT generado para org=%s plan=%s exp=%s por user=%s",
                org.name, plan, exp.date(), current_user.email)
    return Response(
        content=token,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
