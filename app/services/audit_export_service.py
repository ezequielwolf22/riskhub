"""Exportación de paquete de auditoría: ZIP con evidencias, riesgos, controles y attestation firmada."""
import hashlib
import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Risk, RiskStatus, ControlImplementation, Evidence, AuditLog,
    RiskContext, User, UserRole, ComplianceFrameworkStatus,
)

logger = logging.getLogger("riskhub.audit_export")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _risks_csv(risks: list) -> bytes:
    lines = ["code,description,asset,threat,inherent_level,residual_level,status,treatment,created_at"]
    for r in risks:
        asset_name = r.asset.name if r.asset else ""
        threat_name = r.threat.name if r.threat else ""
        lines.append(",".join([
            f'"{r.code}"', f'"{(r.description or "").replace(chr(34), chr(39))}"',
            f'"{asset_name}"', f'"{threat_name}"',
            str(r.inherent_level or ""), str(r.residual_level or ""),
            str(r.status.value if hasattr(r.status, "value") else r.status),
            str(r.treatment_option.value if r.treatment_option and hasattr(r.treatment_option, "value") else ""),
            str(r.created_at.strftime("%Y-%m-%d") if r.created_at else ""),
        ]))
    return "\n".join(lines).encode("utf-8")


def _controls_csv(controls: list) -> bytes:
    lines = ["name,status,maturity,next_review,owner"]
    for c in controls:
        owner = c.owner.email if c.owner else ""
        lines.append(",".join([
            f'"{(c.name or "").replace(chr(34), chr(39))}"',
            str(c.status.value if hasattr(c.status, "value") else c.status),
            str(c.maturity or ""),
            str(c.next_review.strftime("%Y-%m-%d") if c.next_review else ""),
            f'"{owner}"',
        ]))
    return "\n".join(lines).encode("utf-8")


def _compliance_json(statuses: list) -> bytes:
    data = [
        {
            "framework": s.framework_code,
            "requirement": s.requirement_id,
            "status": s.status.value if hasattr(s.status, "value") else str(s.status),
            "completion_pct": s.completion_pct,
            "last_reviewed": s.last_reviewed_at.isoformat() if s.last_reviewed_at else None,
        }
        for s in statuses
    ]
    return json.dumps(data, indent=2, default=str).encode("utf-8")


def _audit_trail_json(logs: list) -> bytes:
    data = [
        {
            "id": l.id,
            "user_id": l.user_id,
            "action": l.action,
            "detail": l.detail,
            "timestamp": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]
    return json.dumps(data, indent=2, default=str).encode("utf-8")


def generate_audit_package(
    db: Session,
    org_id: int,
    requested_by: User,
    include_evidence_files: bool = False,
) -> bytes:
    """Genera ZIP de paquete de auditoría completo con hash de integridad.

    Contiene:
    - risks.csv — todos los riesgos
    - controls.csv — controles y estado
    - compliance.json — estado por framework/requisito
    - audit_trail.json — log de auditoría
    - evidence_index.json — índice de evidencias con hashes
    - attestation.json — documento de integridad con hashes de todos los archivos
    - (opcional) evidence/ — archivos físicos de evidencia
    """
    now = datetime.now(timezone.utc)
    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    org_name = ctx.organization_name if ctx else f"Org-{org_id}"

    # Recopilar datos
    risks = db.query(Risk).filter(Risk.organization_id == org_id).all()
    controls = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == org_id
    ).all()
    evidences = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.is_current == True,
    ).all()
    compliance_statuses = db.query(ComplianceFrameworkStatus).filter(
        ComplianceFrameworkStatus.organization_id == org_id
    ).all()
    audit_logs = db.query(AuditLog).filter(
        AuditLog.organization_id == org_id,
    ).order_by(AuditLog.created_at.desc()).limit(5000).all()

    # Generar archivos
    files: dict[str, bytes] = {}

    files["risks.csv"] = _risks_csv(risks)
    files["controls.csv"] = _controls_csv(controls)
    files["compliance.json"] = _compliance_json(compliance_statuses)
    files["audit_trail.json"] = _audit_trail_json(audit_logs)

    # Índice de evidencias
    ev_index = []
    from pathlib import Path
    _EV_DIR = Path("/srv/data/evidence")
    for ev in evidences:
        entry = {
            "code": ev.code,
            "title": ev.title,
            "evidence_type": ev.evidence_type.value if hasattr(ev.evidence_type, "value") else str(ev.evidence_type),
            "filename": ev.filename,
            "file_hash_sha256": ev.file_hash,
            "compliance_framework": ev.compliance_framework,
            "compliance_requirement": ev.compliance_requirement,
            "expires_at": ev.expires_at.isoformat() if ev.expires_at else None,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
            "version": ev.version,
        }

        # Incluir archivo físico si se solicita y existe
        if include_evidence_files and ev.filename:
            file_path = _EV_DIR / ev.filename
            if file_path.exists():
                file_bytes = file_path.read_bytes()
                # Verificar integridad
                actual_hash = _sha256_bytes(file_bytes)
                entry["hash_verified"] = (actual_hash == ev.file_hash)
                files[f"evidence/{ev.filename}"] = file_bytes

        ev_index.append(entry)

    files["evidence_index.json"] = json.dumps(ev_index, indent=2, default=str).encode("utf-8")

    # Calcular hashes de todos los archivos generados
    file_hashes = {name: _sha256_bytes(content) for name, content in files.items()}

    # Documento de attestation
    attestation = {
        "attestation_version": "1.0",
        "organization": org_name,
        "organization_id": org_id,
        "generated_at": now.isoformat(),
        "generated_by": requested_by.email or f"user_{requested_by.id}",
        "total_risks": len(risks),
        "total_controls": len(controls),
        "total_evidences": len(evidences),
        "total_audit_logs": len(audit_logs),
        "file_integrity": file_hashes,
        "package_hash": _sha256_bytes(
            json.dumps(file_hashes, sort_keys=True).encode("utf-8")
        ),
        "note": (
            "Este documento certifica la integridad del paquete de auditoría. "
            "Verifique los hashes SHA-256 de cada archivo para confirmar que no han sido alterados."
        ),
    }
    files["attestation.json"] = json.dumps(attestation, indent=2, default=str).encode("utf-8")

    # Empaquetar en ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)

    zip_bytes = zip_buffer.getvalue()
    logger.info(
        "Paquete de auditoría generado para org %d: %d archivos, %d bytes",
        org_id, len(files), len(zip_bytes)
    )
    return zip_bytes


def generate_framework_audit_package(
    db: Session,
    org_id: int,
    framework_code: str,
    requested_by: User,
) -> bytes:
    """Genera ZIP de auditoría estructurado específicamente para un framework.

    La estructura del ZIP sigue el orden oficial de los requisitos del framework.
    Incluye: estado por requisito, evidencias asociadas, gaps, attestation.
    """
    from app.services.compliance_service import (
        load_framework, get_framework_compliance_status, initialize_org_framework
    )

    now = datetime.now(timezone.utc)
    framework = load_framework(framework_code)
    if not framework:
        raise ValueError(f"Framework '{framework_code}' no encontrado")

    ctx = db.query(RiskContext).filter(RiskContext.organization_id == org_id).first()
    org_name = ctx.organization_name if ctx else f"Org-{org_id}"

    initialize_org_framework(db, org_id, framework_code)
    status = get_framework_compliance_status(db, org_id, framework_code)

    files: dict[str, bytes] = {}

    # 1. Resumen de cumplimiento
    summary = {
        "framework": framework["name"],
        "version": framework.get("version", ""),
        "organization": org_name,
        "audit_date": now.isoformat(),
        "overall_pct": status.get("overall_pct", 0),
        "mandatory_pct": status.get("mandatory_pct", 0),
        "is_audit_ready": status.get("is_audit_ready", False),
        "total_requirements": status.get("total_requirements", 0),
        "gaps_count": len(status.get("gaps", [])),
    }
    files["00_resumen_cumplimiento.json"] = json.dumps(summary, indent=2, default=str).encode()

    # 2. Por dominio
    domains = status.get("domains", [])
    if domains:
        files["01_estado_por_dominio.json"] = json.dumps(domains, indent=2).encode()

    # 3. Gaps (requisitos no implementados)
    gaps = status.get("gaps", [])
    if gaps:
        gaps_csv_lines = ["id,nombre,dominio,estado,completion_pct"]
        for g in gaps:
            gaps_csv_lines.append(
                f'"{g["id"]}","{g.get("name","")[:80]}","{g.get("domain","")}",'
                f'"{g.get("status","")}", {g.get("completion_pct",0)}'
            )
        files["02_gaps_pendientes.csv"] = "\n".join(gaps_csv_lines).encode()

    # 4. Evidencias por requisito
    evidences = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        Evidence.compliance_framework == framework_code,
        Evidence.is_current == True,
    ).all()

    ev_index = [
        {
            "code": ev.code,
            "title": ev.title,
            "requirement": ev.compliance_requirement,
            "type": ev.evidence_type.value if hasattr(ev.evidence_type, "value") else str(ev.evidence_type),
            "hash_sha256": ev.file_hash,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
            "expires_at": ev.expires_at.isoformat() if ev.expires_at else None,
        }
        for ev in evidences
    ]
    files["03_evidencias.json"] = json.dumps(ev_index, indent=2, default=str).encode()

    # 5. Estado detallado por requisito
    from app.models import ComplianceFrameworkStatus
    req_statuses = db.query(ComplianceFrameworkStatus).filter(
        ComplianceFrameworkStatus.organization_id == org_id,
        ComplianceFrameworkStatus.framework_code == framework_code,
    ).all()

    req_detail = []
    for s in req_statuses:
        req_detail.append({
            "requirement_id": s.requirement_id,
            "status": s.status.value if hasattr(s.status, "value") else str(s.status),
            "completion_pct": s.completion_pct,
            "evidence_count": s.evidence_count or 0,
            "last_reviewed": s.last_reviewed_at.isoformat() if s.last_reviewed_at else None,
            "notes": s.notes,
        })
    files["04_estado_requisitos.json"] = json.dumps(req_detail, indent=2, default=str).encode()

    # 6. Riesgos asociados
    risks = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.status.notin_([RiskStatus.ARCHIVED]),
    ).all()
    risk_rows = ["code,asset,threat,residual_level,status,treatment"]
    for r in risks:
        risk_rows.append(
            f'"{r.code}","{r.asset.name if r.asset else ""}","'
            f'{r.threat.name if r.threat else ""}",{r.residual_level or 0},'
            f'"{r.status.value if hasattr(r.status,"value") else r.status}",'
            f'"{r.treatment_option.value if r.treatment_option and hasattr(r.treatment_option,"value") else ""}"'
        )
    files["05_riesgos.csv"] = "\n".join(risk_rows).encode()

    # 7. Attestation con hashes
    file_hashes = {name: _sha256_bytes(content) for name, content in files.items()}
    attestation = {
        "attestation_version": "1.0",
        "framework": framework["name"],
        "framework_code": framework_code,
        "organization": org_name,
        "generated_at": now.isoformat(),
        "generated_by": requested_by.email or f"user_{requested_by.id}",
        "compliance_pct": status.get("overall_pct", 0),
        "is_audit_ready": status.get("is_audit_ready", False),
        "file_integrity": file_hashes,
        "package_hash": _sha256_bytes(
            json.dumps(file_hashes, sort_keys=True).encode()
        ),
    }
    files["99_attestation.json"] = json.dumps(attestation, indent=2, default=str).encode()

    # Construir ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(f"{framework_code}/{name}", content)

    logger.info(
        "Paquete de auditoría %s generado para org %d: %d archivos",
        framework_code, org_id, len(files)
    )
    return zip_buffer.getvalue()
