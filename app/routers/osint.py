"""Endpoints OSINT - Integración de huella-digital en RiskHub."""
import csv
import io
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
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

_ROLES = ['analyst', 'admin', 'superadmin']


def _create_scan(db, scan_type, target, user_id):
    """Crea y persiste un OSINTScan en estado pending."""
    scan = OSINTScan(
        scan_type=scan_type,
        target=target,
        user_id=user_id,
        status='pending'
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def _check_in_progress(db, user_id, target):
    return db.query(OSINTScan).filter(
        OSINTScan.user_id == user_id,
        OSINTScan.target == target,
        OSINTScan.status.in_(['pending', 'in_progress'])
    ).first()


@router.post("/scans/email", response_model=OSINTScanResponse, status_code=202)
async def scan_email(
    background_tasks: BackgroundTasks,
    email: str = Query(..., min_length=5, max_length=255),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    if _check_in_progress(db, current_user.id, email):
        raise HTTPException(409, "Ya hay un escaneo en progreso para este objetivo")
    scan = _create_scan(db, OSINTScanType.EMAIL, email, current_user.id)
    background_tasks.add_task(osint_engine.run_email_scan, scan.id, email, current_user.id)
    return scan


@router.post("/scans/url", response_model=OSINTScanResponse, status_code=202)
async def scan_url(
    background_tasks: BackgroundTasks,
    url: str = Query(..., min_length=10, max_length=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    scan = _create_scan(db, OSINTScanType.URL, url, current_user.id)
    background_tasks.add_task(osint_engine.run_url_scan, scan.id, url, current_user.id)
    return scan


@router.post("/scans/username", response_model=OSINTScanResponse, status_code=202)
async def scan_username(
    background_tasks: BackgroundTasks,
    username: str = Query(..., min_length=2, max_length=255),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    if _check_in_progress(db, current_user.id, username):
        raise HTTPException(409, "Ya hay un escaneo en progreso para este objetivo")
    scan = _create_scan(db, OSINTScanType.USERNAME, username, current_user.id)
    background_tasks.add_task(osint_engine.run_username_scan, scan.id, username, current_user.id)
    return scan


@router.post("/scans/domain", response_model=OSINTScanResponse, status_code=202)
async def scan_domain(
    background_tasks: BackgroundTasks,
    domain: str = Query(..., min_length=3, max_length=255),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    if _check_in_progress(db, current_user.id, domain):
        raise HTTPException(409, "Ya hay un escaneo en progreso para este objetivo")
    scan = _create_scan(db, OSINTScanType.DOMAIN, domain, current_user.id)
    background_tasks.add_task(osint_engine.run_domain_scan, scan.id, domain, current_user.id)
    return scan


@router.post("/scans/ip", response_model=OSINTScanResponse, status_code=202)
async def scan_ip(
    background_tasks: BackgroundTasks,
    ip: str = Query(..., min_length=7, max_length=45),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    if _check_in_progress(db, current_user.id, ip):
        raise HTTPException(409, "Ya hay un escaneo en progreso para este objetivo")
    scan = _create_scan(db, OSINTScanType.IP, ip, current_user.id)
    background_tasks.add_task(osint_engine.run_ip_scan, scan.id, ip, current_user.id)
    return scan


@router.get("/scans", response_model=PaginatedResponse)
def list_scans(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    scan_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    q = db.query(OSINTScan).filter(OSINTScan.user_id == current_user.id)
    if scan_type:
        q = q.filter(OSINTScan.scan_type == scan_type)
    if status:
        q = q.filter(OSINTScan.status == status)
    total = q.count()
    scans = q.order_by(OSINTScan.started_at.desc()).offset(skip).limit(limit).all()
    return {'total': total, 'skip': skip, 'limit': limit, 'items': scans}


@router.get("/scans/{scan_id}", response_model=OSINTScanResponse)
def get_scan(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    scan = db.query(OSINTScan).filter(
        OSINTScan.id == scan_id,
        OSINTScan.user_id == current_user.id
    ).first()
    if not scan:
        raise HTTPException(404, "Escaneo no encontrado")
    return scan


@router.get("/scans/{scan_id}/findings")
def get_scan_findings(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    """Hallazgos detallados de un escaneo especifico."""
    scan = db.query(OSINTScan).filter(
        OSINTScan.id == scan_id,
        OSINTScan.user_id == current_user.id
    ).first()
    if not scan:
        raise HTTPException(404, "Escaneo no encontrado")
    findings = db.query(OSINTFinding).filter(OSINTFinding.scan_id == scan_id).all()
    return {
        'scan': {
            'id': scan.id, 'target': scan.target, 'scan_type': scan.scan_type,
            'status': scan.status, 'started_at': scan.started_at,
            'completed_at': scan.completed_at, 'findings_count': scan.findings_count,
            'risk_score': scan.risk_score, 'error_message': scan.error_message
        },
        'findings': [
            {
                'id': f.id, 'source': f.source, 'finding_type': f.finding_type,
                'title': f.title, 'description': f.description,
                'risk_level': f.risk_level, 'risk_score': f.risk_score,
                'is_remediated': f.is_remediated, 'remediated_at': f.remediated_at,
                'extra_data': f.extra_data, 'created_at': f.created_at
            }
            for f in findings
        ]
    }


@router.get("/findings", response_model=PaginatedResponse)
def list_findings(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    source: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    finding_type: Optional[str] = Query(None),
    is_remediated: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    q = db.query(OSINTFinding).join(OSINTScan).filter(OSINTScan.user_id == current_user.id)
    if source:
        q = q.filter(OSINTFinding.source == source)
    if risk_level:
        q = q.filter(OSINTFinding.risk_level == risk_level)
    if finding_type:
        q = q.filter(OSINTFinding.finding_type == finding_type)
    if is_remediated is not None:
        q = q.filter(OSINTFinding.is_remediated == is_remediated)
    if search:
        q = q.filter(OSINTFinding.title.ilike(f'%{search}%'))

    total = q.count()
    findings = q.order_by(OSINTFinding.risk_score.desc()).offset(skip).limit(limit).all()
    return {'total': total, 'skip': skip, 'limit': limit, 'items': findings}


@router.get("/findings/export/csv")
def export_findings_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    """Exportar todos los hallazgos a CSV."""
    findings = db.query(OSINTFinding).join(OSINTScan).filter(
        OSINTScan.user_id == current_user.id
    ).order_by(OSINTFinding.risk_score.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Titulo', 'Fuente', 'Tipo', 'Riesgo', 'Score',
                     'Remediado', 'Fecha', 'Descripcion'])
    for f in findings:
        writer.writerow([
            f.id, f.title, f.source, f.finding_type, f.risk_level,
            f.risk_score, 'Si' if f.is_remediated else 'No',
            f.created_at.strftime('%Y-%m-%d %H:%M') if f.created_at else '',
            (f.description or '').replace('\n', ' ')[:200]
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=osint_findings.csv'}
    )


@router.get("/findings/{finding_id}")
def get_finding(
    finding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    finding = db.query(OSINTFinding).join(OSINTScan).filter(
        OSINTFinding.id == finding_id,
        OSINTScan.user_id == current_user.id
    ).first()
    if not finding:
        raise HTTPException(404, "Hallazgo no encontrado")
    return {
        'id': finding.id, 'scan_id': finding.scan_id, 'source': finding.source,
        'finding_type': finding.finding_type, 'title': finding.title,
        'description': finding.description, 'risk_level': finding.risk_level,
        'risk_score': finding.risk_score, 'is_remediated': finding.is_remediated,
        'remediated_at': finding.remediated_at, 'extra_data': finding.extra_data,
        'created_at': finding.created_at, 'updated_at': finding.updated_at
    }


@router.patch("/findings/{finding_id}/remediate")
def remediate_finding(
    finding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    finding = db.query(OSINTFinding).join(OSINTScan).filter(
        OSINTFinding.id == finding_id,
        OSINTScan.user_id == current_user.id
    ).first()
    if not finding:
        raise HTTPException(404, "Hallazgo no encontrado")
    finding.is_remediated = True
    finding.remediated_at = datetime.now()
    db.commit()
    return {'id': finding.id, 'is_remediated': True}


@router.patch("/findings/{finding_id}/unremediate")
def unremediate_finding(
    finding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    finding = db.query(OSINTFinding).join(OSINTScan).filter(
        OSINTFinding.id == finding_id,
        OSINTScan.user_id == current_user.id
    ).first()
    if not finding:
        raise HTTPException(404, "Hallazgo no encontrado")
    finding.is_remediated = False
    finding.remediated_at = None
    db.commit()
    return {'id': finding.id, 'is_remediated': False}


@router.delete("/findings/{finding_id}", status_code=204)
def delete_finding(
    finding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['admin', 'superadmin']))
):
    finding = db.query(OSINTFinding).join(OSINTScan).filter(
        OSINTFinding.id == finding_id,
        OSINTScan.user_id == current_user.id
    ).first()
    if not finding:
        raise HTTPException(404, "Hallazgo no encontrado")
    db.delete(finding)
    db.commit()


@router.delete("/scans/{scan_id}", status_code=204)
def delete_scan(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['admin', 'superadmin']))
):
    scan = db.query(OSINTScan).filter(
        OSINTScan.id == scan_id,
        OSINTScan.user_id == current_user.id
    ).first()
    if not scan:
        raise HTTPException(404, "Escaneo no encontrado")
    db.delete(scan)
    db.commit()


@router.get("/identifiers", response_model=PaginatedResponse)
def list_identifiers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    identifier_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    q = db.query(OSINTIdentifier).filter(OSINTIdentifier.user_id == current_user.id)
    if identifier_type:
        q = q.filter(OSINTIdentifier.identifier_type == identifier_type)
    total = q.count()
    items = q.order_by(OSINTIdentifier.created_at.desc()).offset(skip).limit(limit).all()
    return {'total': total, 'skip': skip, 'limit': limit, 'items': items}


@router.get("/stats")
def get_osint_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(_ROLES))
):
    scans_total = db.query(OSINTScan).filter(OSINTScan.user_id == current_user.id).count()
    findings_q = db.query(OSINTFinding).join(OSINTScan).filter(OSINTScan.user_id == current_user.id)
    findings_total = findings_q.count()
    findings_remediated = findings_q.filter(OSINTFinding.is_remediated == True).count()
    findings = findings_q.all()

    risk_by_level = {level: 0 for level in ['critical', 'high', 'medium', 'low', 'info']}
    for f in findings:
        lvl = str(f.risk_level).replace('OSINTFindingRiskLevel.', '').lower()
        if lvl in risk_by_level:
            risk_by_level[lvl] += 1

    # Por tipo de escaneo
    scans_by_type = {}
    for stype in ['email', 'url', 'username', 'domain', 'ip']:
        scans_by_type[stype] = db.query(OSINTScan).filter(
            OSINTScan.user_id == current_user.id,
            OSINTScan.scan_type == stype
        ).count()

    # Por fuente
    sources = {}
    for f in findings:
        src = str(f.source)
        sources[src] = sources.get(src, 0) + 1

    return {
        'scans_total': scans_total,
        'findings_total': findings_total,
        'findings_remediated': findings_remediated,
        'findings_pending': findings_total - findings_remediated,
        'remediation_rate': round(findings_remediated / findings_total * 100, 1) if findings_total else 0,
        'risk_by_level': risk_by_level,
        'scans_by_type': scans_by_type,
        'findings_by_source': sources,
        'avg_risk_score': round(
            sum(f.risk_score for f in findings) / len(findings), 1
        ) if findings else 0
    }
