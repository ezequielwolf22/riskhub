"""Router para hallazgos de seguridad — herramientas externas (Nessus, Qualys, Burp, etc)
y hallazgos generados internamente por IA (revision de arquitectura y futuras fuentes).

Las acciones de este router (resolver, transferir a incidente, transferir a riesgo) son
genericas por diseno: operan sobre cualquier ExternalFinding sin importar su `source`, de
forma que una fuente de hallazgos nueva (otro analisis IA, otro escaner, etc.) hereda estas
acciones automaticamente sin tener que reimplementarlas.
"""
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import ExternalFinding, ExternalFindingSource, Incident, IncidentSeverity, IncidentStatus, User
from app.security import check_org_access, get_current_user, require_role
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
        "incident_id": f.incident_id,
        "source_document": f.source_document,
        "iso_control": f.iso_control,
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
    source_document: Optional[str] = Query(None),
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
    if source_document:
        query = query.filter(ExternalFinding.source_document == source_document)

    total = query.count()
    items = query.order_by(ExternalFinding.detected_at.desc()).offset(offset).limit(limit).all()

    return {"total": total, "items": [_finding_out(f) for f in items]}


@router.get("/source-documents")
def list_source_documents(
    source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista documentos/esquemas origen distintos, para filtrar hallazgos por documento
    cuando un mismo analisis (p.ej. revision de arquitectura) cubre varios a la vez."""
    org_id = current_user.organization_id
    query = db.query(ExternalFinding.source_document).filter(
        ExternalFinding.organization_id == org_id,
        ExternalFinding.source_document.isnot(None),
    )
    if source:
        query = query.filter(ExternalFinding.source == source.lower())
    docs = sorted({row[0] for row in query.distinct().all() if row[0]})
    return {"documents": docs}


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

    open_count = db.query(ExternalFinding).filter(
        ExternalFinding.organization_id == org_id,
        ExternalFinding.status == "open",
    ).count()

    return {
        "by_severity": {sev: cnt for sev, cnt in by_severity},
        "by_source": {str(src): cnt for src, cnt in by_source},
        "total": sum(cnt for _, cnt in by_severity),
        "open": open_count,
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


_SEVERITY_TO_INCIDENT = {
    "CRITICAL": IncidentSeverity.P1,
    "HIGH": IncidentSeverity.P2,
    "MEDIUM": IncidentSeverity.P3,
    "LOW": IncidentSeverity.P4,
}


@router.post("/{finding_id}/create-incident")
def create_incident_from_finding(
    finding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Transfiere un hallazgo (de cualquier fuente) a un incidente para su seguimiento
    y resolucion operativa. Generico: no depende del `source` del hallazgo."""
    from app.routers.incidents import _next_code as _next_incident_code

    f = db.get(ExternalFinding, finding_id)
    if not f or f.organization_id != current_user.organization_id:
        raise HTTPException(404, "Hallazgo no encontrado")
    if f.incident_id:
        raise HTTPException(400, "El hallazgo ya tiene un incidente asociado")

    org_id = current_user.organization_id
    inc = Incident(
        organization_id=org_id,
        code=_next_incident_code(db, org_id),
        title=f.title[:255],
        description=f.description or f.title,
        severity=_SEVERITY_TO_INCIDENT.get((f.severity or "").upper(), IncidentSeverity.P3),
        status=IncidentStatus.OPEN,
        detected_at=f.detected_at,
        affected_asset_ids=[f.asset_id] if f.asset_id else [],
        related_risk_ids=[f.risk_id] if f.risk_id else [],
        owner_id=current_user.id,
    )
    db.add(inc)
    db.flush()
    f.incident_id = inc.id
    db.commit()
    db.refresh(inc)
    return {"message": "Incidente creado", "incident_id": inc.id, "incident_code": inc.code}


@router.post("/{finding_id}/create-risk")
def create_risk_from_finding(
    finding_id: int,
    asset_id: int = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Transfiere un hallazgo (de cualquier fuente) al registro de riesgos ISO 27005,
    asociandolo al activo indicado. Generico: no depende del `source` del hallazgo."""
    from app.services.risk_auto_generator import auto_generate_risk_from_finding

    f = db.get(ExternalFinding, finding_id)
    if not f or f.organization_id != current_user.organization_id:
        raise HTTPException(404, "Hallazgo no encontrado")
    if f.risk_id:
        raise HTTPException(400, "El hallazgo ya tiene un riesgo asociado")
    if not check_org_access(current_user.organization_id, current_user):
        raise HTTPException(403, "Sin acceso")

    sev_map = {"CRITICAL": (4, 3), "HIGH": (3, 3), "MEDIUM": (2, 2), "LOW": (1, 2)}
    consequence, likelihood = sev_map.get((f.severity or "").upper(), (2, 2))
    threat_code = f"FINDING-{f.source}-{f.external_id or f.id}"[:64]

    risk = auto_generate_risk_from_finding(
        db, asset_id, f.title, f.description or f.title, threat_code,
        inherent_consequence=consequence, inherent_likelihood=likelihood,
    )
    if not risk:
        raise HTTPException(400, "No se pudo crear el riesgo (verifica el activo seleccionado)")

    f.risk_id = risk.id
    db.commit()
    return {"message": "Riesgo creado", "risk_id": risk.id, "risk_code": risk.code}
