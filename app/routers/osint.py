"""Endpoints OSINT - Integración de huella-digital en RiskHub."""
import csv
import io
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.i18n import get_lang, t as _t

from app.database import get_db
from app.models import (
    User, OSINTScan, OSINTFinding, OSINTIdentifier, OSINTScanType,
    OSINTFindingRiskLevel, Incident, IncidentSeverity, IncidentStatus
)
from app.security import filter_by_org, require_role
from app.schemas import (
    OSINTScanCreate, OSINTScanResponse, OSINTFindingResponse,
    OSINTIdentifierResponse, PaginatedResponse
)
from app.services.osint_engine import osint_engine
from app.services.osint_entraid import entraid_service

router = APIRouter(prefix="/api/v1/osint", tags=["osint"])

from app.models import UserRole as _UserRole
_ROLES = (_UserRole.ANALYST, _UserRole.ADMIN, _UserRole.SUPERADMIN)


def _create_scan(db, scan_type, target, user_id, organization_id=None):
    """Crea y persiste un OSINTScan en estado pending."""
    scan = OSINTScan(
        scan_type=scan_type,
        target=target,
        user_id=user_id,
        organization_id=organization_id,
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
    current_user: User = Depends(require_role(*_ROLES))
):
    if _check_in_progress(db, current_user.id, email):
        raise HTTPException(409, "Ya hay un escaneo en progreso para este objetivo")
    scan = _create_scan(db, OSINTScanType.EMAIL, email, current_user.id, current_user.organization_id)
    background_tasks.add_task(osint_engine.run_email_scan, scan.id, email, current_user.id)
    return scan


@router.post("/scans/url", response_model=OSINTScanResponse, status_code=202)
async def scan_url(
    background_tasks: BackgroundTasks,
    url: str = Query(..., min_length=10, max_length=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    scan = _create_scan(db, OSINTScanType.URL, url, current_user.id, current_user.organization_id)
    background_tasks.add_task(osint_engine.run_url_scan, scan.id, url, current_user.id)
    return scan


@router.post("/scans/username", response_model=OSINTScanResponse, status_code=202)
async def scan_username(
    background_tasks: BackgroundTasks,
    username: str = Query(..., min_length=2, max_length=255),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    if _check_in_progress(db, current_user.id, username):
        raise HTTPException(409, "Ya hay un escaneo en progreso para este objetivo")
    scan = _create_scan(db, OSINTScanType.USERNAME, username, current_user.id, current_user.organization_id)
    background_tasks.add_task(osint_engine.run_username_scan, scan.id, username, current_user.id)
    return scan


@router.post("/scans/domain", response_model=OSINTScanResponse, status_code=202)
async def scan_domain(
    background_tasks: BackgroundTasks,
    domain: str = Query(..., min_length=3, max_length=255),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    if _check_in_progress(db, current_user.id, domain):
        raise HTTPException(409, "Ya hay un escaneo en progreso para este objetivo")
    scan = _create_scan(db, OSINTScanType.DOMAIN, domain, current_user.id, current_user.organization_id)
    background_tasks.add_task(osint_engine.run_domain_scan, scan.id, domain, current_user.id)
    return scan


@router.post("/scans/ip", response_model=OSINTScanResponse, status_code=202)
async def scan_ip(
    background_tasks: BackgroundTasks,
    ip: str = Query(..., min_length=7, max_length=45),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    if _check_in_progress(db, current_user.id, ip):
        raise HTTPException(409, "Ya hay un escaneo en progreso para este objetivo")
    scan = _create_scan(db, OSINTScanType.IP, ip, current_user.id, current_user.organization_id)
    background_tasks.add_task(osint_engine.run_ip_scan, scan.id, ip, current_user.id)
    return scan


@router.post("/scans/bulk", status_code=202)
async def bulk_scan(
    background_tasks: BackgroundTasks,
    scan_type: str = Query(..., description="email|domain|ip|url|username"),
    targets: str = Query(..., description="Targets separados por nueva linea o coma"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    """Inicia multiples escaneos. Targets separados por nueva linea o coma (max 50)."""
    valid_types = {'email', 'domain', 'ip', 'url', 'username'}
    if scan_type not in valid_types:
        raise HTTPException(400, f"Tipo invalido. Validos: {', '.join(valid_types)}")

    raw = targets.replace(',', '\n').splitlines()
    clean = [t.strip() for t in raw if t.strip()]
    if not clean:
        raise HTTPException(400, "No se encontraron targets validos")
    if len(clean) > 50:
        raise HTTPException(400, "Maximo 50 targets por solicitud")

    type_enum = OSINTScanType[scan_type.upper()]
    run_fn_map = {
        'email': osint_engine.run_email_scan,
        'domain': osint_engine.run_domain_scan,
        'ip': osint_engine.run_ip_scan,
        'url': osint_engine.run_url_scan,
        'username': osint_engine.run_username_scan,
    }
    run_fn = run_fn_map[scan_type]

    created = []
    skipped = []
    for target in clean:
        if _check_in_progress(db, current_user.id, target):
            skipped.append(target)
            continue
        scan = _create_scan(db, type_enum, target, current_user.id, current_user.organization_id)
        background_tasks.add_task(run_fn, scan.id, target, current_user.id)
        created.append({'target': target, 'scan_id': scan.id})

    return {'created': len(created), 'skipped': len(skipped), 'scans': created}


@router.get("/scans", response_model=PaginatedResponse)
def list_scans(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    scan_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    q = filter_by_org(db.query(OSINTScan), OSINTScan, current_user)
    if scan_type:
        q = q.filter(OSINTScan.scan_type == scan_type)
    if status:
        q = q.filter(OSINTScan.status == status)
    total = q.count()
    scans = q.order_by(OSINTScan.started_at.desc()).offset(skip).limit(limit).all()
    return {
        'total': total, 'skip': skip, 'limit': limit,
        'items': [OSINTScanResponse.model_validate(s).model_dump(mode='json') for s in scans]
    }


@router.get("/scans/{scan_id}", response_model=OSINTScanResponse)
def get_scan(
    scan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    lang = get_lang(request)
    scan = filter_by_org(
        db.query(OSINTScan).filter(OSINTScan.id == scan_id),
        OSINTScan, current_user
    ).first()
    if not scan:
        raise HTTPException(404, _t("osint.not_found", lang))
    return scan


@router.get("/scans/{scan_id}/findings")
def get_scan_findings(
    scan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    """Hallazgos detallados de un escaneo especifico."""
    lang = get_lang(request)
    scan = filter_by_org(
        db.query(OSINTScan).filter(OSINTScan.id == scan_id),
        OSINTScan, current_user
    ).first()
    if not scan:
        raise HTTPException(404, _t("osint.not_found", lang))
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
    current_user: User = Depends(require_role(*_ROLES))
):
    org_scan_ids = [
        s.id for s in filter_by_org(db.query(OSINTScan), OSINTScan, current_user).all()
    ]
    q = db.query(OSINTFinding).filter(OSINTFinding.scan_id.in_(org_scan_ids))
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
    return {
        'total': total, 'skip': skip, 'limit': limit,
        'items': [OSINTFindingResponse.model_validate(f).model_dump(mode='json') for f in findings]
    }


@router.get("/findings/export/csv")
def export_findings_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    """Exportar todos los hallazgos a CSV."""
    org_scan_ids = [
        s.id for s in filter_by_org(db.query(OSINTScan), OSINTScan, current_user).all()
    ]
    findings = db.query(OSINTFinding).filter(
        OSINTFinding.scan_id.in_(org_scan_ids)
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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    lang = get_lang(request)
    org_scan_ids = [
        s.id for s in filter_by_org(db.query(OSINTScan), OSINTScan, current_user).all()
    ]
    finding = db.query(OSINTFinding).filter(
        OSINTFinding.id == finding_id,
        OSINTFinding.scan_id.in_(org_scan_ids)
    ).first()
    if not finding:
        raise HTTPException(404, _t("osint.not_found", lang))
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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    lang = get_lang(request)
    org_scan_ids = [
        s.id for s in filter_by_org(db.query(OSINTScan), OSINTScan, current_user).all()
    ]
    finding = db.query(OSINTFinding).filter(
        OSINTFinding.id == finding_id,
        OSINTFinding.scan_id.in_(org_scan_ids)
    ).first()
    if not finding:
        raise HTTPException(404, _t("osint.not_found", lang))
    finding.is_remediated = True
    finding.remediated_at = datetime.now(timezone.utc)
    db.commit()
    return {'id': finding.id, 'is_remediated': True}


@router.patch("/findings/{finding_id}/unremediate")
def unremediate_finding(
    finding_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    lang = get_lang(request)
    org_scan_ids = [
        s.id for s in filter_by_org(db.query(OSINTScan), OSINTScan, current_user).all()
    ]
    finding = db.query(OSINTFinding).filter(
        OSINTFinding.id == finding_id,
        OSINTFinding.scan_id.in_(org_scan_ids)
    ).first()
    if not finding:
        raise HTTPException(404, _t("osint.not_found", lang))
    finding.is_remediated = False
    finding.remediated_at = None
    db.commit()
    return {'id': finding.id, 'is_remediated': False}


@router.delete("/findings/{finding_id}", status_code=204)
def delete_finding(
    finding_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['admin', 'superadmin']))
):
    lang = get_lang(request)
    org_scan_ids = [
        s.id for s in filter_by_org(db.query(OSINTScan), OSINTScan, current_user).all()
    ]
    finding = db.query(OSINTFinding).filter(
        OSINTFinding.id == finding_id,
        OSINTFinding.scan_id.in_(org_scan_ids)
    ).first()
    if not finding:
        raise HTTPException(404, _t("osint.not_found", lang))
    db.delete(finding)
    db.commit()


@router.delete("/scans/{scan_id}", status_code=204)
def delete_scan(
    scan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['admin', 'superadmin']))
):
    lang = get_lang(request)
    scan = filter_by_org(
        db.query(OSINTScan).filter(OSINTScan.id == scan_id),
        OSINTScan, current_user
    ).first()
    if not scan:
        raise HTTPException(404, _t("osint.not_found", lang))
    db.delete(scan)
    db.commit()


@router.delete("/identifiers/{identifier_id}", status_code=204)
def delete_identifier(
    identifier_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(['admin', 'analyst', 'superadmin']))
):
    """Elimina un identificador OSINT (y sus escaneos/hallazgos en cascada)."""
    lang = get_lang(request)
    identifier = filter_by_org(
        db.query(OSINTIdentifier).filter(OSINTIdentifier.id == identifier_id),
        OSINTIdentifier, current_user
    ).first()
    if not identifier:
        raise HTTPException(404, _t("osint.not_found", lang))
    db.delete(identifier)
    db.commit()


@router.get("/identifiers", response_model=PaginatedResponse)
def list_identifiers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    identifier_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    q = filter_by_org(db.query(OSINTIdentifier), OSINTIdentifier, current_user)
    if identifier_type:
        q = q.filter(OSINTIdentifier.identifier_type == identifier_type)
    total = q.count()
    items = q.order_by(OSINTIdentifier.created_at.desc()).offset(skip).limit(limit).all()
    return {
        'total': total, 'skip': skip, 'limit': limit,
        'items': [OSINTIdentifierResponse.model_validate(i).model_dump(mode='json') for i in items]
    }


# ── ENTRA ID ────────────────────────────────────────────────────────────────

@router.post("/sources/entraid/test")
async def test_entraid_connection(
    tenant_id: str = Query(..., min_length=1),
    client_id: str = Query(..., min_length=1),
    client_secret: str = Query(..., min_length=1),
    current_user: User = Depends(require_role(*_ROLES))
):
    """Prueba la conexion con Microsoft Entra ID y devuelve info del tenant."""
    return await entraid_service.test_connection(tenant_id, client_id, client_secret)


@router.post("/sources/entraid/preview")
async def preview_entraid_targets(
    tenant_id: str = Query(..., min_length=1),
    client_id: str = Query(..., min_length=1),
    client_secret: str = Query(..., min_length=1),
    current_user: User = Depends(require_role(*_ROLES))
):
    """Lista usuarios y dominios del tenant sin iniciar escaneos."""
    token = await entraid_service.get_access_token(tenant_id, client_id, client_secret)
    if not token:
        raise HTTPException(400, "No se pudo autenticar con Entra ID. Revisa tenant_id, client_id y client_secret.")
    import asyncio
    users, domains = await asyncio.gather(
        entraid_service.list_users(token, limit=200),
        entraid_service.list_domains(token)
    )
    return {
        'users': users,
        'domains': domains,
        'users_count': len(users),
        'domains_count': len(domains)
    }


@router.post("/sources/entraid/import", status_code=202)
async def import_from_entraid(
    background_tasks: BackgroundTasks,
    tenant_id: str = Query(..., min_length=1),
    client_id: str = Query(..., min_length=1),
    client_secret: str = Query(..., min_length=1),
    scan_users: bool = Query(True),
    scan_domains: bool = Query(True),
    user_limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    """Importa targets desde Entra ID e inicia escaneos OSINT en segundo plano."""
    token = await entraid_service.get_access_token(tenant_id, client_id, client_secret)
    if not token:
        raise HTTPException(400, "No se pudo autenticar con Entra ID.")

    users = await entraid_service.list_users(token, limit=user_limit) if scan_users else []
    domains = await entraid_service.list_domains(token) if scan_domains else []

    scans_created = []

    if scan_users:
        for user in users:
            email = user.get('email', '')
            if not email:
                continue
            if _check_in_progress(db, current_user.id, email):
                continue
            scan = _create_scan(db, OSINTScanType.EMAIL, email, current_user.id, current_user.organization_id)
            background_tasks.add_task(osint_engine.run_email_scan, scan.id, email, current_user.id)
            scans_created.append({'type': 'email', 'target': email, 'scan_id': scan.id})

    if scan_domains:
        for domain in domains:
            domain_id = domain.get('id', '')
            if not domain_id:
                continue
            if _check_in_progress(db, current_user.id, domain_id):
                continue
            scan = _create_scan(db, OSINTScanType.DOMAIN, domain_id, current_user.id, current_user.organization_id)
            background_tasks.add_task(osint_engine.run_domain_scan, scan.id, domain_id, current_user.id)
            scans_created.append({'type': 'domain', 'target': domain_id, 'scan_id': scan.id})

    return {
        'scans_created': len(scans_created),
        'targets': scans_created
    }


# ── CREATE INCIDENT FROM FINDING ─────────────────────────────────────────────

@router.post("/findings/{finding_id}/create-incident")
def create_incident_from_finding(
    finding_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    """Genera un incidente de seguridad a partir de un hallazgo OSINT."""
    lang = get_lang(request)
    org_scan_ids = [
        s.id for s in filter_by_org(db.query(OSINTScan), OSINTScan, current_user).all()
    ]
    finding = db.query(OSINTFinding).filter(
        OSINTFinding.id == finding_id,
        OSINTFinding.scan_id.in_(org_scan_ids)
    ).first()
    if not finding:
        raise HTTPException(404, _t("osint.not_found", lang))

    # Verificar si ya existe un incidente con este titulo OSINT en la misma org
    existing_title = f"[OSINT] {finding.title}"
    existing = db.query(Incident).filter(
        Incident.title == existing_title,
        Incident.organization_id == current_user.organization_id,
    ).first()
    if existing:
        return {
            'incident_id': existing.id,
            'incident_code': existing.code,
            'title': existing.title,
            'already_existed': True
        }

    # Mapear nivel de riesgo a severidad P1-P4
    severity_map = {
        'critical': IncidentSeverity.P1,
        'high': IncidentSeverity.P2,
        'medium': IncidentSeverity.P3,
        'low': IncidentSeverity.P4,
        'info': IncidentSeverity.P4
    }
    risk_str = str(finding.risk_level).replace('OSINTFindingRiskLevel.', '').lower()
    severity = severity_map.get(risk_str, IncidentSeverity.P3)

    from sqlalchemy import func as _func
    max_id = db.query(_func.max(Incident.id)).scalar() or 0
    inc = Incident(
        code=f"INC-{max_id + 1:04d}",
        title=existing_title,
        description=(
            f"Incidente generado automaticamente desde hallazgo OSINT.\n\n"
            f"Fuente: {finding.source}\n"
            f"Tipo: {finding.finding_type}\n"
            f"Score de riesgo: {finding.risk_score}\n\n"
            f"{finding.description or ''}"
        ),
        severity=severity,
        status=IncidentStatus.OPEN,
        detected_at=finding.created_at or datetime.now(timezone.utc),
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)

    return {
        'incident_id': inc.id,
        'incident_code': inc.code,
        'title': inc.title,
        'already_existed': False
    }


# ── CREATE RISK FROM FINDING ─────────────────────────────────────────────────

@router.post("/findings/{finding_id}/create-risk")
def create_risk_from_osint_finding(
    finding_id: int,
    request: Request,
    asset_id: int = Query(..., description="ID del activo afectado"),
    threat_id: int = Query(..., description="ID de la amenaza relacionada"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    """Genera un riesgo en el registro de riesgos a partir de un hallazgo OSINT."""
    from app.models import Risk, RiskStatus, Asset, Threat
    from app.services.risk_engine import calc_level
    from app.routers.risks import _next_code as _risk_next_code
    from app.security import check_org_access

    lang = get_lang(request)
    org_scan_ids = [
        s.id for s in filter_by_org(db.query(OSINTScan), OSINTScan, current_user).all()
    ]
    finding = db.query(OSINTFinding).filter(
        OSINTFinding.id == finding_id,
        OSINTFinding.scan_id.in_(org_scan_ids)
    ).first()
    if not finding:
        raise HTTPException(404, _t("osint.not_found", lang))

    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset or not check_org_access(asset.organization_id, current_user):
        raise HTTPException(404, _t("common.not_found", lang))

    threat = db.query(Threat).filter(Threat.id == threat_id).first()
    if not threat:
        raise HTTPException(404, _t("common.not_found", lang))

    # Verificar si ya existe un riesgo para este par activo/amenaza en la misma org
    existing = db.query(Risk).filter(
        Risk.asset_id == asset_id,
        Risk.threat_id == threat_id,
        Risk.organization_id == current_user.organization_id,
    ).first()
    if existing:
        return {
            'risk_id': existing.id,
            'risk_code': existing.code,
            'title': f"{asset.name} / {threat.name}",
            'already_existed': True
        }

    # Mapear score OSINT (0-100) a escala ISO 27005 (0-4)
    score = finding.risk_score or 0
    if score >= 80:
        lh, imp = 4, 4
    elif score >= 60:
        lh, imp = 3, 4
    elif score >= 40:
        lh, imp = 3, 3
    elif score >= 20:
        lh, imp = 2, 2
    else:
        lh, imp = 1, 1

    # calc_level(consequence=impact, likelihood)
    inherent_level = calc_level(imp, lh)

    risk = Risk(
        code=_risk_next_code(db),
        asset_id=asset_id,
        threat_id=threat_id,
        description=(
            f"Riesgo identificado via OSINT.\n"
            f"Fuente: {finding.source} | Tipo: {finding.finding_type}\n"
            f"Score OSINT: {finding.risk_score:.1f}/100\n\n"
            f"{finding.description or ''}"
        ),
        inherent_likelihood=lh,
        inherent_consequence=imp,
        inherent_level=inherent_level,
        residual_likelihood=lh,
        residual_consequence=imp,
        residual_level=inherent_level,
        status=RiskStatus.IDENTIFIED,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)

    return {
        'risk_id': risk.id,
        'risk_code': risk.code,
        'title': f"{asset.name} / {threat.name}",
        'already_existed': False
    }


@router.get("/stats")
def get_osint_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ROLES))
):
    org_scans_q = filter_by_org(db.query(OSINTScan), OSINTScan, current_user)
    scans_total = org_scans_q.count()
    org_scan_ids = [s.id for s in org_scans_q.all()]

    findings_q = db.query(OSINTFinding).filter(OSINTFinding.scan_id.in_(org_scan_ids))
    findings_total = findings_q.count()
    findings_remediated = findings_q.filter(OSINTFinding.is_remediated == True).count()
    findings = findings_q.all()

    risk_by_level = {level: 0 for level in ['critical', 'high', 'medium', 'low', 'info']}
    for f in findings:
        lvl = str(f.risk_level).replace('OSINTFindingRiskLevel.', '').lower()
        if lvl in risk_by_level:
            risk_by_level[lvl] += 1

    # Por tipo de escaneo (filtrado por org)
    scans_by_type = {}
    for stype in ['email', 'url', 'username', 'domain', 'ip']:
        scans_by_type[stype] = filter_by_org(
            db.query(OSINTScan).filter(OSINTScan.scan_type == stype),
            OSINTScan, current_user
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
