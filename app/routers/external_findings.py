"""Router para importar hallazgos de herramientas externas (Nessus, Qualys, Burp, etc)."""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import ExternalFinding, ExternalFindingSource, User
from app.security import get_current_user, require_role
from app.services.external_findings_service import (
    detect_file_format,
    parse_nessus_xml,
    parse_qualys_xml,
    parse_burp_xml,
    parse_openvas_xml,
    import_findings,
)

router = APIRouter(prefix="/api/findings", tags=["external-findings"])

_PARSERS = {
    "nessus": parse_nessus_xml,
    "qualys": parse_qualys_xml,
    "burp": parse_burp_xml,
    "openvas": parse_openvas_xml,
}


def _finding_out(f: ExternalFinding) -> dict:
    return {
        "id": f.id,
        "source": f.source.value if hasattr(f.source, "value") else f.source,
        "external_id": f.external_id,
        "title": f.title,
        "description": (f.description or "")[:200],
        "severity": f.severity,
        "cvss_score": f.cvss_score,
        "cve_id": f.cve_id,
        "affected_host": f.affected_host,
        "affected_port": f.affected_port,
        "asset_id": f.asset_id,
        "risk_id": f.risk_id,
        "status": f.status,
        "import_batch_id": f.import_batch_id,
        "detected_at": f.detected_at.isoformat() if f.detected_at else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


@router.post("/import")
async def import_findings_file(
    file: UploadFile = File(...),
    source: Optional[str] = None,
    auto_create_risks: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Importa hallazgos desde archivo (Nessus .nessus, Qualys XML, Burp XML, OpenVAS XML).

    Auto-detecta formato si no se especifica source.
    Auto-crea riesgos si severity HIGH/CRITICAL y activo encontrado.
    """
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")

    content = await file.read()

    if not source:
        source = detect_file_format(file.filename or "", content)
    if not source:
        raise HTTPException(
            400,
            "No se pudo detectar el formato. Especifica source: nessus|qualys|burp|openvas"
        )

    source_lower = source.lower()
    parser = _PARSERS.get(source_lower)
    if not parser:
        raise HTTPException(400, f"Fuente no soportada: {source}. Soportadas: {list(_PARSERS.keys())}")

    findings_data = parser(content)
    if not findings_data:
        return {"message": "No se encontraron hallazgos en el archivo", "stats": {}}

    # Mapear source string a enum
    source_enum_map = {
        "nessus": ExternalFindingSource.NESSUS.value,
        "qualys": ExternalFindingSource.QUALYS.value,
        "burp": ExternalFindingSource.BURP.value,
        "openvas": ExternalFindingSource.OPENVAS.value,
    }
    source_value = source_enum_map.get(source_lower, source_lower)

    stats = import_findings(db, org_id, source_value, findings_data, auto_create_risks)
    return {"source": source, "stats": stats}


@router.get("")
def list_findings(
    severity: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    asset_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista hallazgos externos con filtros."""
    org_id = current_user.organization_id
    query = db.query(ExternalFinding).filter(ExternalFinding.organization_id == org_id)

    if severity:
        query = query.filter(ExternalFinding.severity == severity.upper())
    if source:
        query = query.filter(ExternalFinding.source == source.lower())
    if status:
        query = query.filter(ExternalFinding.status == status)
    if asset_id:
        query = query.filter(ExternalFinding.asset_id == asset_id)

    total = query.count()
    items = query.order_by(ExternalFinding.detected_at.desc()).offset(offset).limit(limit).all()

    return {"total": total, "items": [_finding_out(f) for f in items]}


@router.get("/summary")
def findings_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resumen de hallazgos por severity y source."""
    org_id = current_user.organization_id
    from sqlalchemy import func

    by_severity = db.query(
        ExternalFinding.severity, func.count(ExternalFinding.id)
    ).filter(
        ExternalFinding.organization_id == org_id
    ).group_by(ExternalFinding.severity).all()

    by_source = db.query(
        ExternalFinding.source, func.count(ExternalFinding.id)
    ).filter(
        ExternalFinding.organization_id == org_id
    ).group_by(ExternalFinding.source).all()

    return {
        "by_severity": {sev: cnt for sev, cnt in by_severity},
        "by_source": {str(src): cnt for src, cnt in by_source},
        "total": sum(cnt for _, cnt in by_severity),
    }


@router.put("/{finding_id}/resolve")
def resolve_finding(
    finding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Marca hallazgo como resuelto."""
    from datetime import datetime, timezone
    f = db.get(ExternalFinding, finding_id)
    if not f or f.organization_id != current_user.organization_id:
        raise HTTPException(404, "Hallazgo no encontrado")
    f.status = "resolved"
    f.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Hallazgo marcado como resuelto"}
