"""Motor de orquestación de escaneos OSINT."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from app.database import SessionLocal
from app.models import (
    OSINTScan, OSINTFinding, OSINTIdentifier, OSINTScanType,
    OSINTFindingRiskLevel
)
from app.services.osint_hibp import hibp_service
from app.services.osint_virustotal import virustotal_service
from app.services.osint_leakcheck import leakcheck_service
from app.services.osint_intelx import intelx_service
from app.services.osint_github import github_service
from app.services.osint_domain import domain_osint_service
from app.services.osint_ip import ip_osint_service

logger = logging.getLogger(__name__)


class OSINTEngine:
    """Orquestador de escaneos OSINT. run_* son wrappers sincronos para background tasks."""

    # --- Wrappers sincronos (se llaman desde FastAPI BackgroundTasks) ---

    def run_email_scan(self, scan_id: int, email: str, user_id: int):
        asyncio.run(self._scan_email(scan_id, email, user_id))

    def run_url_scan(self, scan_id: int, url: str, user_id: int):
        asyncio.run(self._scan_url(scan_id, url, user_id))

    def run_username_scan(self, scan_id: int, username: str, user_id: int):
        asyncio.run(self._scan_username(scan_id, username, user_id))

    def run_domain_scan(self, scan_id: int, domain: str, user_id: int):
        asyncio.run(self._scan_domain(scan_id, domain, user_id))

    def run_ip_scan(self, scan_id: int, ip: str, user_id: int):
        asyncio.run(self._scan_ip(scan_id, ip, user_id))

    # --- Implementaciones asincronas ---

    async def _scan_email(self, scan_id: int, email: str, user_id: int):
        db = SessionLocal()
        try:
            scan = db.query(OSINTScan).filter(OSINTScan.id == scan_id).first()
            if not scan:
                return
            scan.status = 'in_progress'
            db.commit()

            findings_list = []
            identifier = self._get_or_create_identifier(db, OSINTScanType.EMAIL, email, user_id)

            try:
                # HIBP
                breaches = await hibp_service.check_email(email)
                findings_list.extend(
                    hibp_service.map_breaches_to_findings(email, breaches, scan.id, identifier.id)
                )

                # LeakCheck
                sources = await leakcheck_service.check_email(email)
                findings_list.extend(
                    leakcheck_service.map_sources_to_findings(email, sources, scan.id, identifier.id)
                )

                # IntelX
                intelx_results = await intelx_service.search_email(email)
                findings_list.extend(
                    intelx_service.map_results_to_findings(intelx_results, scan.id, identifier.id)
                )

            except Exception as e:
                logger.error("scan_email error for %s: %s", email, e)
                scan.status = 'failed'
                scan.error_message = str(e)[:500]
                db.commit()
                return

            self._save_findings(scan, findings_list, identifier, db)

        finally:
            db.close()

    async def _scan_url(self, scan_id: int, url: str, user_id: int):
        db = SessionLocal()
        try:
            scan = db.query(OSINTScan).filter(OSINTScan.id == scan_id).first()
            if not scan:
                return
            scan.status = 'in_progress'
            db.commit()

            findings_list = []

            # Resolver API key per-tenant (BD primero, env var como fallback)
            try:
                from app.routers.integrations_virustotal import get_vt_api_key
                vt_api_key = get_vt_api_key(db, scan.organization_id)
            except Exception:
                vt_api_key = None

            try:
                vt_result = await virustotal_service.analyze_url(url, api_key=vt_api_key)
                if vt_result:
                    findings_list.extend(
                        virustotal_service.map_vt_to_findings(vt_result, scan.id)
                    )
                # Si VT no esta configurado, generar finding informativo
                if not vt_api_key:
                    findings_list.append({
                        'scan_id': scan.id,
                        'identifier_id': None,
                        'source': 'virustotal',
                        'finding_type': 'config_missing',
                        'title': f"VirusTotal no configurado — URL: {url[:80]}",
                        'description': 'Configura la API key de VirusTotal en Integraciones para analizar URLs.',
                        'risk_level': 'info',
                        'risk_score': 0.0,
                        'metadata': {'url': url}
                    })

            except Exception as e:
                logger.error("scan_url error for %s: %s", url, e)
                scan.status = 'failed'
                scan.error_message = str(e)[:500]
                db.commit()
                return

            self._save_findings(scan, findings_list, None, db)

        finally:
            db.close()

    async def _scan_username(self, scan_id: int, username: str, user_id: int):
        db = SessionLocal()
        try:
            scan = db.query(OSINTScan).filter(OSINTScan.id == scan_id).first()
            if not scan:
                return
            scan.status = 'in_progress'
            db.commit()

            findings_list = []
            identifier = self._get_or_create_identifier(db, OSINTScanType.USERNAME, username, user_id)

            try:
                user_info = await github_service.check_user_info(username)
                repos = await github_service.get_user_repos(username)
                secrets = await github_service.search_secrets_in_code(username)

                findings_list.extend(
                    github_service.map_github_to_findings(
                        username,
                        {'user_info': user_info, 'repos': repos, 'secrets': secrets},
                        scan.id,
                        identifier.id
                    )
                )

            except Exception as e:
                logger.error("scan_username error for %s: %s", username, e)
                scan.status = 'failed'
                scan.error_message = str(e)[:500]
                db.commit()
                return

            self._save_findings(scan, findings_list, identifier, db)

        finally:
            db.close()

    async def _scan_domain(self, scan_id: int, domain: str, user_id: int):
        db = SessionLocal()
        try:
            scan = db.query(OSINTScan).filter(OSINTScan.id == scan_id).first()
            if not scan:
                return
            scan.status = 'in_progress'
            db.commit()

            identifier = self._get_or_create_identifier(db, OSINTScanType.DOMAIN, domain, user_id)

            try:
                dns_records, ssl_info, subdomains, rdap_info, http_headers = await asyncio.gather(
                    domain_osint_service.get_dns_records(domain),
                    domain_osint_service.get_ssl_info(domain),
                    domain_osint_service.get_subdomains_crtsh(domain),
                    domain_osint_service.get_rdap_info(domain),
                    domain_osint_service.get_http_headers(domain),
                    return_exceptions=True
                )

                # Normalizar excepciones a None/{}
                if isinstance(dns_records, Exception): dns_records = {}
                if isinstance(ssl_info, Exception): ssl_info = None
                if isinstance(subdomains, Exception): subdomains = []
                if isinstance(rdap_info, Exception): rdap_info = None
                if isinstance(http_headers, Exception): http_headers = {}

                # IntelX domain search
                intelx_results = await intelx_service.search_domain(domain)

                findings_list = domain_osint_service.map_to_findings(
                    domain, dns_records, ssl_info, subdomains,
                    rdap_info, http_headers, scan.id, identifier.id
                )

                # Agregar findings de IntelX si los hay
                findings_list.extend(
                    intelx_service.map_results_to_findings(intelx_results, scan.id, identifier.id)
                )

            except Exception as e:
                logger.error("scan_domain error for %s: %s", domain, e)
                scan.status = 'failed'
                scan.error_message = str(e)[:500]
                db.commit()
                return

            self._save_findings(scan, findings_list, identifier, db)

        finally:
            db.close()

    async def _scan_ip(self, scan_id: int, ip: str, user_id: int):
        db = SessionLocal()
        try:
            scan = db.query(OSINTScan).filter(OSINTScan.id == scan_id).first()
            if not scan:
                return
            scan.status = 'in_progress'
            db.commit()

            identifier = self._get_or_create_identifier(db, OSINTScanType.IP, ip, user_id)

            try:
                ip_info, rdns, open_ports = await asyncio.gather(
                    ip_osint_service.get_ip_info(ip),
                    ip_osint_service.get_reverse_dns(ip),
                    ip_osint_service.check_open_ports(ip),
                    return_exceptions=True
                )

                if isinstance(ip_info, Exception): ip_info = None
                if isinstance(rdns, Exception): rdns = None
                if isinstance(open_ports, Exception): open_ports = []

                findings_list = ip_osint_service.map_to_findings(
                    ip, ip_info, rdns, open_ports, scan.id, identifier.id
                )

            except Exception as e:
                logger.error("scan_ip error for %s: %s", ip, e)
                scan.status = 'failed'
                scan.error_message = str(e)[:500]
                db.commit()
                return

            self._save_findings(scan, findings_list, identifier, db)

        finally:
            db.close()

    # --- Helpers ---

    def _get_or_create_identifier(self, db, itype: OSINTScanType, value: str, user_id: int):
        obj = db.query(OSINTIdentifier).filter(
            OSINTIdentifier.user_id == user_id,
            OSINTIdentifier.identifier_type == itype,
            OSINTIdentifier.value == value
        ).first()
        if not obj:
            obj = OSINTIdentifier(
                identifier_type=itype,
                value=value,
                user_id=user_id
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        return obj

    def _save_findings(self, scan: OSINTScan, findings_list: List[dict],
                       identifier, db):
        for fd in findings_list:
            finding = OSINTFinding(
                scan_id=scan.id,
                identifier_id=fd.get('identifier_id'),
                source=fd.get('source'),
                finding_type=fd.get('finding_type'),
                title=fd.get('title'),
                description=fd.get('description'),
                risk_level=fd.get('risk_level', 'medium'),
                risk_score=float(fd.get('risk_score', 0)),
                extra_data=fd.get('metadata')
            )
            db.add(finding)

        scan.findings_count = len(findings_list)
        scan.risk_score = (
            sum(f.get('risk_score', 0) for f in findings_list) / len(findings_list)
            if findings_list else 0.0
        )
        scan.status = 'completed'
        scan.completed_at = datetime.now(timezone.utc)

        # Vincular hallazgos a activos y crear riesgos automaticamente (v1.7.5)
        try:
            if scan.organization_id and len(findings_list) > 0:
                from app.services.asset_risk_analysis_service import link_osint_findings_to_assets
                result = link_osint_findings_to_assets(db, scan.organization_id, scan.id)
                logger.info(
                    "OSINT→risks scan=%d created=%d", scan.id, result.get("created", 0)
                )
        except Exception as _e:
            logger.warning("OSINT→risks linkage failed: %s", _e)

        # Auto-crear incidente para hallazgos CRITICAL o HIGH (v1.7.6)
        try:
            if scan.organization_id and findings_list:
                _auto_create_incident_from_osint(db, scan, findings_list)
        except Exception as _e:
            logger.warning("OSINT→incident auto-create failed: %s", _e)

        if identifier:
            identifier.last_scanned_at = datetime.now(timezone.utc)
            s = scan.risk_score or 0
            if s > 70:
                identifier.risk_level = OSINTFindingRiskLevel.CRITICAL
            elif s > 50:
                identifier.risk_level = OSINTFindingRiskLevel.HIGH
            elif s > 30:
                identifier.risk_level = OSINTFindingRiskLevel.MEDIUM
            elif s > 10:
                identifier.risk_level = OSINTFindingRiskLevel.LOW
            else:
                identifier.risk_level = OSINTFindingRiskLevel.INFO

        db.commit()

        # Auto-crear VendorIssue para hallazgos CRITICAL/HIGH que coincidan con dominio de proveedor
        try:
            if scan.organization_id and findings_list:
                _auto_vendor_issue_from_osint_findings(db, scan, findings_list)
        except Exception as _e:
            logger.warning("OSINT→VendorIssue auto-create failed: %s", _e)


def _auto_vendor_issue_from_osint_findings(db, scan, findings_list: list) -> None:
    """Para cada finding CRITICAL/HIGH, busca si hay un proveedor con dominio coincidente
    y crea un VendorIssue automatico si no existe uno previo del mismo finding.
    """
    import re
    from app.models import Supplier, VendorIssue, VendorIssueSeverity, VendorIssueStatus
    from datetime import datetime, timezone, timedelta

    HIGH_SEVERITIES = {"critical", "high"}
    org_id = scan.organization_id

    # Solo procesar findings CRITICAL/HIGH
    severe = [
        f for f in findings_list
        if str(f.get("risk_level", "")).lower() in HIGH_SEVERITIES
    ]
    if not severe:
        return

    # Obtener proveedores activos de la org
    suppliers = db.query(Supplier).filter(
        Supplier.organization_id == org_id,
        Supplier.lifecycle_stage.notin_(["terminated"]),
    ).all()
    if not suppliers:
        return

    # Pre-calcular dominio normalizado de cada proveedor
    def _sup_domain(sup):
        d = (getattr(sup, "domain", "") or "").lower().strip()
        if not d:
            d = (getattr(sup, "website", "") or "").lower()
            d = re.sub(r"https?://", "", d).split("/")[0]
        return d

    sup_domains = [(sup, _sup_domain(sup)) for sup in suppliers if _sup_domain(sup)]

    now = datetime.now(timezone.utc)

    for fd in severe:
        target = scan.target or ""
        m = re.search(r"(?:https?://)?([^/\s@:]+\.[a-z]{2,})", target, re.IGNORECASE)
        if not m:
            continue
        finding_domain = m.group(1).lower()

        # Buscar proveedor coincidente
        matched = None
        for sup, sup_d in sup_domains:
            if sup_d and (sup_d in finding_domain or finding_domain in sup_d):
                matched = sup
                break
        if not matched:
            continue

        # Dedup: usar titulo + proveedor como clave de unicidad
        fd_title = fd.get("title", "")[:120]
        existing = db.query(VendorIssue).filter(
            VendorIssue.supplier_id == matched.id,
            VendorIssue.auto_generated_source == "osint",
            VendorIssue.title.ilike(f"%{fd_title[:50]}%"),
            VendorIssue.status.notin_(["closed", "mitigated", "accepted"]),
        ).first()
        if existing:
            continue

        n = db.query(VendorIssue).filter(VendorIssue.organization_id == org_id).count() + 1
        sev_str = str(fd.get("risk_level", "")).lower()
        severity = VendorIssueSeverity.CRITICAL if sev_str == "critical" else VendorIssueSeverity.HIGH
        days = 30 if severity == VendorIssueSeverity.CRITICAL else 60

        issue = VendorIssue(
            organization_id=org_id,
            code=f"VIS-{n:04d}",
            supplier_id=matched.id,
            source="osint",
            title=f"OSINT {sev_str.upper()}: {fd_title}",
            description=(
                f"Hallazgo OSINT detectado para el dominio {finding_domain} "
                f"(proveedor: {matched.name}). "
                f"Fuente: {fd.get('source', '')}. "
                f"Detalle: {fd.get('description', '')[:300]}. "
                f"Scan ID: {scan.id}. "
                f"Para cerrar: revisar y resolver el hallazgo OSINT, "
                f"luego marcar como mitigado."
            ),
            severity=severity,
            status=VendorIssueStatus.OPEN,
            auto_generated=True,
            auto_generated_source="osint",
            due_date=now + timedelta(days=days),
            created_at=now,
        )
        db.add(issue)
        try:
            db.flush()
        except Exception as _e:
            db.rollback()
            logger.warning("OSINT→VendorIssue flush failed for supplier %s: %s", matched.id, _e)
            continue

    try:
        db.commit()
        # Recomputar perfil de riesgo de proveedores afectados
        affected_sup_ids = {
            issue.supplier_id
            for issue in db.query(VendorIssue).filter(
                VendorIssue.organization_id == org_id,
                VendorIssue.auto_generated_source == "osint",
            ).all()
            if issue.created_at and (now - issue.created_at).total_seconds() < 60
        }
        for sid in affected_sup_ids:
            try:
                from app.services.supplier_lifecycle_service import recompute_supplier_risk_profile
                recompute_supplier_risk_profile(db, sid, triggered_by="osint_finding")
            except Exception as _e:
                logger.warning("recompute_supplier_risk_profile failed for supplier %s: %s", sid, _e)
    except Exception as _e:
        db.rollback()
        logger.warning("OSINT→VendorIssue commit failed: %s", _e)


def _auto_create_incident_from_osint(db, scan, findings_list: list) -> None:
    """Crea automaticamente un incidente de seguridad cuando un escaneo OSINT
    detecta hallazgos de nivel CRITICAL o HIGH. Solo crea uno por escaneo.
    """
    from app.models import Incident, IncidentSeverity, IncidentStatus

    critical_findings = [
        f for f in findings_list
        if str(f.get("risk_level", "")).lower() in ("critical", "high")
    ]
    if not critical_findings:
        return

    # Determinar severidad del incidente segun el hallazgo mas grave
    has_critical = any(str(f.get("risk_level", "")).lower() == "critical" for f in critical_findings)
    severity = IncidentSeverity.P1 if has_critical else IncidentSeverity.P2

    # Evitar duplicados: no crear incidente si ya existe uno para este escaneo
    existing = db.query(Incident).filter(
        Incident.organization_id == scan.organization_id,
        Incident.description.like(f"%OSINT-SCAN-{scan.id}%"),
    ).first()
    if existing:
        return

    # Generar codigo secuencial INC-XXXX
    from sqlalchemy import func
    count = db.query(func.count(Incident.id)).filter(
        Incident.organization_id == scan.organization_id
    ).scalar() or 0
    code = f"INC-{count + 1:04d}"
    # Asegurar unicidad
    while db.query(Incident).filter_by(code=code).first():
        count += 1
        code = f"INC-{count + 1:04d}"

    target = scan.target or "objetivo desconocido"
    titles = [f.get("title", "") for f in critical_findings[:3]]
    title = f"[OSINT] Hallazgos {severity.value.upper()} en {target}"
    description = (
        f"El escaneo OSINT sobre '{target}' ha detectado {len(critical_findings)} "
        f"hallazgo(s) de nivel {'CRITICAL' if has_critical else 'HIGH'}.\n\n"
        f"Hallazgos principales:\n"
        + "\n".join(f"- {t}" for t in titles if t)
        + f"\n\nRef. interna: OSINT-SCAN-{scan.id}\n"
        f"Revisa la seccion OSINT para ver el detalle completo."
    )

    incident = Incident(
        organization_id=scan.organization_id,
        code=code,
        title=title,
        description=description,
        severity=severity,
        status=IncidentStatus.OPEN,
        detected_at=scan.completed_at,
        nis2_notification_required=(severity == IncidentSeverity.P1),
    )
    db.add(incident)
    db.flush()
    logger.info(
        "Auto-created incident %s (severity=%s) from OSINT scan=%d with %d critical findings",
        code, severity.value, scan.id, len(critical_findings),
    )


osint_engine = OSINTEngine()
