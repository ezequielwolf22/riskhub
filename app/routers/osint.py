"""Endpoints OSINT - Integración de huella-digital en RiskHub."""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    User, OSINTScan, OSINTFinding, OSINTIdentifier, OSINTScanType,
    OSINTFindingRiskLevel
)
from app.security import require_role
from app.schemas import (
    OSINTScanCreate, OSINTScanResponse, OSINTFindingResponse,
    OSINTIdentifierResponse, PaginatedResponse
)
from app.services.osint_engine import osint_engine

router = APIRouter(prefix="/api/v1/osint", tags=["osint"])


@router.post("/scans/email", response_model=OSINTScanResponse, status_code=202)
async def scan_email(
    background_tasks: BackgroundTasks,
    email: str = Query(..., min_length=5, max_length=255),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['analyst', 'admin', 'superadmin']))
):
    """Iniciar escaneo OSINT de email."""
    in_progress = db.query(OSINTScan).filter(
        OSINTScan.user_id == current_user.id,
        OSINTScan.target == email,
        OSINTScan.status == 'in_progress'
    ).first()

    if in_progress:
        raise HTTPException(
            status_code=409,
            detail="Ya hay un escaneo en progreso para este email"
        )

    scan = OSINTScan(
        scan_type=OSINTScanType.EMAIL,
        target=email,
        user_id=current_user.id,
        status='pending'
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    background_tasks.add_task(osint_engine.run_email_scan, scan.id, email, current_user.id)

    return scan


@router.post("/scans/url", response_model=OSINTScanResponse, status_code=202)
async def scan_url(
    background_tasks: BackgroundTasks,
    url: str = Query(..., min_length=10, max_length=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['analyst', 'admin', 'superadmin']))
):
    """Iniciar escaneo OSINT de URL."""
    scan = OSINTScan(
        scan_type=OSINTScanType.URL,
        target=url,
        user_id=current_user.id,
        status='pending'
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    background_tasks.add_task(osint_engine.run_url_scan, scan.id, url, current_user.id)

    return scan


@router.post("/scans/username", response_model=OSINTScanResponse, status_code=202)
async def scan_username(
    background_tasks: BackgroundTasks,
    username: str = Query(..., min_length=2, max_length=255),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['analyst', 'admin', 'superadmin']))
):
    """Iniciar escaneo OSINT de nombre de usuario (GitHub, etc.)."""
    scan = OSINTScan(
        scan_type=OSINTScanType.USERNAME,
        target=username,
        user_id=current_user.id,
        status='pending'
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    background_tasks.add_task(osint_engine.run_username_scan, scan.id, username, current_user.id)

    return scan


@router.get("/scans", response_model=PaginatedResponse)
def list_scans(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    scan_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['analyst', 'admin', 'superadmin']))
):
    """Listar escaneos OSINT del usuario."""
    query = db.query(OSINTScan).filter(OSINTScan.user_id == current_user.id)

    if scan_type:
        query = query.filter(OSINTScan.scan_type == scan_type)
    if status:
        query = query.filter(OSINTScan.status == status)

    total = query.count()
    scans = query.order_by(OSINTScan.started_at.desc()).offset(skip).limit(limit).all()

    return {
        'total': total,
        'skip': skip,
        'limit': limit,
        'items': scans
    }


@router.get("/scans/{scan_id}", response_model=OSINTScanResponse)
def get_scan(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['analyst', 'admin', 'superadmin']))
):
    """Obtener detalles de un escaneo."""
    scan = db.query(OSINTScan).filter(
        OSINTScan.id == scan_id,
        OSINTScan.user_id == current_user.id
    ).first()

    if not scan:
        raise HTTPException(status_code=404, detail="Escaneo no encontrado")

    return scan


@router.get("/findings", response_model=PaginatedResponse)
def list_findings(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    source: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    is_remediated: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['analyst', 'admin', 'superadmin']))
):
    """Listar hallazgos OSINT del usuario."""
    query = db.query(OSINTFinding).join(OSINTScan).filter(
        OSINTScan.user_id == current_user.id
    )

    if source:
        query = query.filter(OSINTFinding.source == source)
    if risk_level:
        query = query.filter(OSINTFinding.risk_level == risk_level)
    if is_remediated is not None:
        query = query.filter(OSINTFinding.is_remediated == is_remediated)

    total = query.count()
    findings = query.order_by(OSINTFinding.risk_score.desc()).offset(skip).limit(limit).all()

    return {
        'total': total,
        'skip': skip,
        'limit': limit,
        'items': findings
    }


@router.get("/findings/{finding_id}", response_model=OSINTFindingResponse)
def get_finding(
    finding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['analyst', 'admin', 'superadmin']))
):
    """Obtener detalles de un hallazgo."""
    finding = db.query(OSINTFinding).join(OSINTScan).filter(
        OSINTFinding.id == finding_id,
        OSINTScan.user_id == current_user.id
    ).first()

    if not finding:
        raise HTTPException(status_code=404, detail="Hallazgo no encontrado")

    return finding


@router.patch("/findings/{finding_id}/remediate", response_model=OSINTFindingResponse)
def remediate_finding(
    finding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['analyst', 'admin', 'superadmin']))
):
    """Marcar un hallazgo como remediado."""
    finding = db.query(OSINTFinding).join(OSINTScan).filter(
        OSINTFinding.id == finding_id,
        OSINTScan.user_id == current_user.id
    ).first()

    if not finding:
        raise HTTPException(status_code=404, detail="Hallazgo no encontrado")

    finding.is_remediated = True
    finding.remediated_at = datetime.now()
    db.commit()
    db.refresh(finding)

    return finding


@router.patch("/findings/{finding_id}/unremediate", response_model=OSINTFindingResponse)
def unremediate_finding(
    finding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['analyst', 'admin', 'superadmin']))
):
    """Marcar un hallazgo como no remediado."""
    finding = db.query(OSINTFinding).join(OSINTScan).filter(
        OSINTFinding.id == finding_id,
        OSINTScan.user_id == current_user.id
    ).first()

    if not finding:
        raise HTTPException(status_code=404, detail="Hallazgo no encontrado")

    finding.is_remediated = False
    finding.remediated_at = None
    db.commit()
    db.refresh(finding)

    return finding


@router.get("/identifiers", response_model=PaginatedResponse)
def list_identifiers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    identifier_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['analyst', 'admin', 'superadmin']))
):
    """Listar identificadores OSINT monitorizados."""
    query = db.query(OSINTIdentifier).filter(OSINTIdentifier.user_id == current_user.id)

    if identifier_type:
        query = query.filter(OSINTIdentifier.identifier_type == identifier_type)

    total = query.count()
    identifiers = query.order_by(OSINTIdentifier.created_at.desc()).offset(skip).limit(limit).all()

    return {
        'total': total,
        'skip': skip,
        'limit': limit,
        'items': identifiers
    }


@router.get("/stats")
def get_osint_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['analyst', 'admin', 'superadmin']))
):
    """Estadísticas de OSINT del usuario."""
    scans_total = db.query(OSINTScan).filter(OSINTScan.user_id == current_user.id).count()
    findings_total = db.query(OSINTFinding).join(OSINTScan).filter(
        OSINTScan.user_id == current_user.id
    ).count()
    findings_remediated = db.query(OSINTFinding).join(OSINTScan).filter(
        OSINTScan.user_id == current_user.id,
        OSINTFinding.is_remediated == True
    ).count()

    findings = db.query(OSINTFinding).join(OSINTScan).filter(
        OSINTScan.user_id == current_user.id
    ).all()

    risk_by_level = {}
    for level in ['critical', 'high', 'medium', 'low', 'info']:
        count = sum(1 for f in findings if f.risk_level == level)
        risk_by_level[level] = count

    return {
        'scans_total': scans_total,
        'findings_total': findings_total,
        'findings_remediated': findings_remediated,
        'findings_pending': findings_total - findings_remediated,
        'risk_by_level': risk_by_level,
        'avg_risk_score': sum(f.risk_score for f in findings) / len(findings) if findings else 0
    }
