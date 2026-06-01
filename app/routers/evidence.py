"""Router de evidencias centralizadas."""
import base64
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Evidence, EvidenceType, User
from app.security import get_current_user, require_role
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

_EVIDENCE_DIR = Path("/srv/data/evidence")


def _ensure_dir():
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


def _next_code(db: Session, org_id: int) -> str:
    count = db.query(Evidence).filter(Evidence.organization_id == org_id).count()
    code = f"EVD-{count + 1:04d}"
    while db.query(Evidence).filter_by(code=code).first():
        count += 1
        code = f"EVD-{count + 1:04d}"
    return code


def _evidence_out(e: Evidence) -> dict:
    return {
        "id": e.id,
        "code": e.code,
        "title": e.title,
        "description": e.description,
        "evidence_type": e.evidence_type.value if hasattr(e.evidence_type, "value") else e.evidence_type,
        "filename": e.filename,
        "mime_type": e.mime_type,
        "file_hash": e.file_hash,
        "file_size": e.file_size,
        "control_implementation_id": e.control_implementation_id,
        "risk_id": e.risk_id,
        "policy_id": e.policy_id,
        "compliance_framework": e.compliance_framework,
        "compliance_requirement": e.compliance_requirement,
        "valid_from": e.valid_from.isoformat() if e.valid_from else None,
        "expires_at": e.expires_at.isoformat() if e.expires_at else None,
        "is_expired": (e.expires_at and e.expires_at < datetime.now(timezone.utc)),
        "version": e.version,
        "is_current": e.is_current,
        "created_by_id": e.created_by_id,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.get("")
def list_evidence(
    framework: Optional[str] = Query(None),
    requirement: Optional[str] = Query(None),
    control_id: Optional[int] = Query(None),
    risk_id: Optional[int] = Query(None),
    evidence_type: Optional[str] = Query(None),
    expired_only: bool = Query(False),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista evidencias con filtros."""
    org_id = current_user.organization_id
    query = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.is_current == True,
    )

    if framework:
        query = query.filter(Evidence.compliance_framework == framework)
    if requirement:
        query = query.filter(Evidence.compliance_requirement == requirement)
    if control_id:
        query = query.filter(Evidence.control_implementation_id == control_id)
    if risk_id:
        query = query.filter(Evidence.risk_id == risk_id)
    if evidence_type:
        query = query.filter(Evidence.evidence_type == evidence_type)
    if expired_only:
        now = datetime.now(timezone.utc)
        query = query.filter(
            Evidence.expires_at.isnot(None),
            Evidence.expires_at < now,
        )

    total = query.count()
    items = query.order_by(Evidence.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "items": [_evidence_out(e) for e in items],
    }


@router.post("")
async def upload_evidence(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    evidence_type: str = Form("other"),
    control_id: Optional[int] = Form(None),
    risk_id: Optional[int] = Form(None),
    policy_id: Optional[int] = Form(None),
    compliance_framework: Optional[str] = Form(None),
    compliance_requirement: Optional[str] = Form(None),
    valid_from: Optional[str] = Form(None),
    expires_at: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Sube un archivo de evidencia."""
    _ensure_dir()
    org_id = current_user.organization_id

    # Validar tipo de evidencia
    valid_types = [t.value for t in EvidenceType]
    if evidence_type not in valid_types:
        raise HTTPException(400, f"Tipo inválido. Válidos: {valid_types}")

    # Leer archivo
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50MB max
        raise HTTPException(413, "Archivo demasiado grande (máximo 50MB)")

    # Hash para integridad (sobre el contenido original, antes de cifrar)
    file_hash = hashlib.sha256(content).hexdigest()

    # Cifrar con Fernet antes de escribir en disco (igual que document_service.py)
    from app.config import settings as _settings
    from cryptography.fernet import Fernet
    _fernet_key = base64.urlsafe_b64encode(
        hashlib.sha256(_settings.secret_key.encode()).digest()
    )
    encrypted_content = Fernet(_fernet_key).encrypt(content)

    # Guardar archivo cifrado
    safe_name = Path(file.filename or "evidence").name
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._- ")[:80]
    code = _next_code(db, org_id)
    stored_name = f"{org_id}_{code}_{safe_name}"
    file_path = _EVIDENCE_DIR / stored_name
    file_path.write_bytes(encrypted_content)

    # Parsear fechas
    def _parse_date(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    ev = Evidence(
        organization_id=org_id,
        code=code,
        title=title[:255],
        description=description,
        evidence_type=evidence_type,
        filename=stored_name,
        mime_type=file.content_type or "application/octet-stream",
        file_hash=file_hash,
        file_size=len(content),
        control_implementation_id=control_id,
        risk_id=risk_id,
        policy_id=policy_id,
        compliance_framework=compliance_framework,
        compliance_requirement=compliance_requirement,
        valid_from=_parse_date(valid_from),
        expires_at=_parse_date(expires_at),
        created_by_id=current_user.id,
        version=1,
        is_current=True,
    )
    db.add(ev)

    # Actualizar evidence_count en compliance
    if compliance_framework and compliance_requirement:
        from app.models import ComplianceFrameworkStatus
        req_status = db.query(ComplianceFrameworkStatus).filter(
            ComplianceFrameworkStatus.organization_id == org_id,
            ComplianceFrameworkStatus.framework_code == compliance_framework,
            ComplianceFrameworkStatus.requirement_id == compliance_requirement,
        ).first()
        if req_status:
            req_status.evidence_count = (req_status.evidence_count or 0) + 1

    db.commit()
    db.refresh(ev)

    log_action(db, current_user.id, "create", "evidence", str(ev.id), {"code": ev.code})

    return _evidence_out(ev)


@router.get("/{evidence_id}")
def get_evidence(
    evidence_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obtiene metadatos de una evidencia."""
    ev = db.get(Evidence, evidence_id)
    if not ev or ev.organization_id != current_user.organization_id:
        raise HTTPException(404, "Evidencia no encontrada")
    return _evidence_out(ev)


@router.get("/{evidence_id}/download")
def download_evidence(
    evidence_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Descarga el archivo de evidencia."""
    ev = db.get(Evidence, evidence_id)
    if not ev or ev.organization_id != current_user.organization_id:
        raise HTTPException(404, "Evidencia no encontrada")
    if not ev.filename:
        raise HTTPException(404, "Sin archivo asociado")

    file_path = _EVIDENCE_DIR / ev.filename
    if not file_path.exists():
        raise HTTPException(404, "Archivo no encontrado en disco")

    # Descifrar Fernet; si falla (archivo legacy sin cifrar) servir en crudo
    from fastapi.responses import Response
    from app.config import settings as _settings
    from cryptography.fernet import Fernet, InvalidToken
    raw = file_path.read_bytes()
    try:
        _fernet_key = base64.urlsafe_b64encode(
            hashlib.sha256(_settings.secret_key.encode()).digest()
        )
        raw = Fernet(_fernet_key).decrypt(raw)
    except (InvalidToken, Exception):
        pass  # archivo legacy no cifrado — servir tal cual

    original_name = ev.filename.split("_", 2)[-1] if "_" in ev.filename else ev.filename
    return Response(
        content=raw,
        media_type=ev.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{original_name}"'},
    )


@router.post("/{evidence_id}/new-version")
async def upload_new_version(
    evidence_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Sube nueva versión de una evidencia existente."""
    _ensure_dir()
    ev = db.get(Evidence, evidence_id)
    if not ev or ev.organization_id != current_user.organization_id:
        raise HTTPException(404, "Evidencia no encontrada")

    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()
    safe_name = file.filename.replace("..", "").replace("/", "").replace("\\", "")
    new_version = (ev.version or 1) + 1
    stored_name = f"{ev.organization_id}_{ev.code}_v{new_version}_{safe_name}"
    file_path = _EVIDENCE_DIR / stored_name
    file_path.write_bytes(content)

    # Marcar anterior como no-current
    ev.is_current = False

    # Crear nueva versión
    new_ev = Evidence(
        organization_id=ev.organization_id,
        code=ev.code,
        title=ev.title,
        description=ev.description,
        evidence_type=ev.evidence_type,
        filename=stored_name,
        mime_type=file.content_type or ev.mime_type,
        file_hash=file_hash,
        file_size=len(content),
        control_implementation_id=ev.control_implementation_id,
        risk_id=ev.risk_id,
        policy_id=ev.policy_id,
        compliance_framework=ev.compliance_framework,
        compliance_requirement=ev.compliance_requirement,
        valid_from=ev.valid_from,
        expires_at=ev.expires_at,
        created_by_id=current_user.id,
        version=new_version,
        is_current=True,
        previous_version_id=ev.id,
    )
    db.add(new_ev)
    db.commit()
    db.refresh(new_ev)

    return _evidence_out(new_ev)


@router.delete("/{evidence_id}")
def delete_evidence(
    evidence_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Elimina una evidencia (solo admin)."""
    ev = db.get(Evidence, evidence_id)
    if not ev or ev.organization_id != current_user.organization_id:
        raise HTTPException(404, "Evidencia no encontrada")

    # Borrar archivo si existe
    if ev.filename:
        file_path = _EVIDENCE_DIR / ev.filename
        if file_path.exists():
            file_path.unlink()

    db.delete(ev)
    db.commit()
    return {"message": "Evidencia eliminada"}
