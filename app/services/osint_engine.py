"""Motor de orquestación de escaneos OSINT."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from app.database import SessionLocal
from app.models import (
    OSINTScan, OSINTFinding, OSINTIdentifier, OSINTScanType,
    OSINTSourceType, OSINTFindingRiskLevel
)
from app.services.osint_hibp import hibp_service
from app.services.osint_virustotal import virustotal_service
from app.services.osint_leakcheck import leakcheck_service
from app.services.osint_intelx import intelx_service
from app.services.osint_github import github_service

logger = logging.getLogger(__name__)


class OSINTEngine:
    """Orquestador de escaneos OSINT. Los métodos run_* se ejecutan en background tasks."""

    def run_email_scan(self, scan_id: int, email: str, user_id: int):
        """Wrapper síncrono para ejecutar escaneo de email en background task."""
        asyncio.run(self._scan_email(scan_id, email, user_id))

    def run_url_scan(self, scan_id: int, url: str, user_id: int):
        """Wrapper síncrono para ejecutar escaneo de URL en background task."""
        asyncio.run(self._scan_url(scan_id, url, user_id))

    def run_username_scan(self, scan_id: int, username: str, user_id: int):
        """Wrapper síncrono para ejecutar escaneo de username en background task."""
        asyncio.run(self._scan_username(scan_id, username, user_id))

    async def _scan_email(self, scan_id: int, email: str, user_id: int):
        """Escanear email en múltiples fuentes."""
        db = SessionLocal()
        try:
            scan = db.query(OSINTScan).filter(OSINTScan.id == scan_id).first()
            if not scan:
                return
            scan.status = 'in_progress'
            db.commit()

            findings_list = []
            identifier = None

            try:
                identifier = db.query(OSINTIdentifier).filter(
                    OSINTIdentifier.user_id == user_id,
                    OSINTIdentifier.identifier_type == OSINTScanType.EMAIL,
                    OSINTIdentifier.value == email
                ).first()

                if not identifier:
                    identifier = OSINTIdentifier(
                        identifier_type=OSINTScanType.EMAIL,
                        value=email,
                        user_id=user_id
                    )
                    db.add(identifier)
                    db.commit()
                    db.refresh(identifier)

                # HIBP
                breaches = await hibp_service.check_email(email)
                hibp_findings = hibp_service.map_breaches_to_findings(
                    email, breaches, scan.id, identifier.id
                )
                findings_list.extend(hibp_findings)

                # LeakCheck
                leakcheck_sources = await leakcheck_service.check_email(email)
                leakcheck_findings = leakcheck_service.map_sources_to_findings(
                    email, leakcheck_sources, scan.id, identifier.id
                )
                findings_list.extend(leakcheck_findings)

                # IntelX
                intelx_results = await intelx_service.search_email(email)
                intelx_findings = intelx_service.map_results_to_findings(
                    intelx_results, scan.id, identifier.id
                )
                findings_list.extend(intelx_findings)

            except Exception as e:
                logger.error("Error en scan_email %s: %s", email, e)
                scan.status = 'failed'
                scan.error_message = str(e)[:500]
                db.commit()
                return

            self._save_findings(scan, findings_list, identifier, db)

        finally:
            db.close()

    async def _scan_url(self, scan_id: int, url: str, user_id: int):
        """Escanear URL con VirusTotal."""
        db = SessionLocal()
        try:
            scan = db.query(OSINTScan).filter(OSINTScan.id == scan_id).first()
            if not scan:
                return
            scan.status = 'in_progress'
            db.commit()

            findings_list = []

            try:
                vt_result = await virustotal_service.analyze_url(url)
                if vt_result:
                    vt_findings = virustotal_service.map_vt_to_findings(vt_result, scan.id)
                    findings_list.extend(vt_findings)

            except Exception as e:
                logger.error("Error en scan_url %s: %s", url, e)
                scan.status = 'failed'
                scan.error_message = str(e)[:500]
                db.commit()
                return

            self._save_findings(scan, findings_list, None, db)

        finally:
            db.close()

    async def _scan_username(self, scan_id: int, username: str, user_id: int):
        """Escanear nombre de usuario en GitHub."""
        db = SessionLocal()
        try:
            scan = db.query(OSINTScan).filter(OSINTScan.id == scan_id).first()
            if not scan:
                return
            scan.status = 'in_progress'
            db.commit()

            findings_list = []
            identifier = None

            try:
                identifier = db.query(OSINTIdentifier).filter(
                    OSINTIdentifier.user_id == user_id,
                    OSINTIdentifier.identifier_type == OSINTScanType.USERNAME,
                    OSINTIdentifier.value == username
                ).first()

                if not identifier:
                    identifier = OSINTIdentifier(
                        identifier_type=OSINTScanType.USERNAME,
                        value=username,
                        user_id=user_id
                    )
                    db.add(identifier)
                    db.commit()
                    db.refresh(identifier)

                user_info = await github_service.check_user_info(username)
                repos = await github_service.get_user_repos(username)
                secrets = await github_service.search_secrets_in_code(username)

                github_findings = github_service.map_github_to_findings(
                    username,
                    {'user_info': user_info, 'repos': repos, 'secrets': secrets},
                    scan.id,
                    identifier.id
                )
                findings_list.extend(github_findings)

            except Exception as e:
                logger.error("Error en scan_username %s: %s", username, e)
                scan.status = 'failed'
                scan.error_message = str(e)[:500]
                db.commit()
                return

            self._save_findings(scan, findings_list, identifier, db)

        finally:
            db.close()

    def _save_findings(self, scan: OSINTScan, findings_list: List[dict],
                       identifier: Optional[OSINTIdentifier], db):
        """Guardar findings en BD y actualizar scan."""
        for finding_data in findings_list:
            finding = OSINTFinding(
                scan_id=scan.id,
                identifier_id=finding_data.get('identifier_id'),
                source=finding_data.get('source'),
                finding_type=finding_data.get('finding_type'),
                title=finding_data.get('title'),
                description=finding_data.get('description'),
                risk_level=finding_data.get('risk_level', 'medium'),
                risk_score=float(finding_data.get('risk_score', 0)),
                extra_data=finding_data.get('metadata')
            )
            db.add(finding)

        scan.findings_count = len(findings_list)
        if findings_list:
            scan.risk_score = sum(f.get('risk_score', 0) for f in findings_list) / len(findings_list)
        scan.status = 'completed'
        scan.completed_at = datetime.now(timezone.utc)

        if identifier:
            identifier.last_scanned_at = datetime.now(timezone.utc)
            if scan.risk_score and scan.risk_score > 70:
                identifier.risk_level = OSINTFindingRiskLevel.CRITICAL
            elif scan.risk_score and scan.risk_score > 50:
                identifier.risk_level = OSINTFindingRiskLevel.HIGH
            elif scan.risk_score and scan.risk_score > 30:
                identifier.risk_level = OSINTFindingRiskLevel.MEDIUM
            elif scan.risk_score and scan.risk_score > 10:
                identifier.risk_level = OSINTFindingRiskLevel.LOW

        db.commit()


osint_engine = OSINTEngine()
