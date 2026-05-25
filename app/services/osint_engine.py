"""Motor de orquestación de escaneos OSINT."""
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models import (
    OSINTScan, OSINTFinding, OSINTIdentifier, OSINTScanType,
    OSINTSourceType, OSINTFindingRiskLevel
)
from app.services.osint_hibp import hibp_service
from app.services.osint_virustotal import virustotal_service
from app.services.osint_leakcheck import leakcheck_service
from app.services.osint_intelx import intelx_service
from app.services.osint_github import github_service


class OSINTEngine:
    """Orquestador de escaneos OSINT."""

    async def scan_email(self, email: str, user_id: int, db: Session) -> OSINTScan:
        """Escanear email en múltiples fuentes."""
        scan = OSINTScan(
            scan_type=OSINTScanType.EMAIL,
            target=email,
            user_id=user_id,
            status='in_progress'
        )
        db.add(scan)
        db.commit()
        db.refresh(scan)

        findings_list = []
        identifier = None

        try:
            # Obtener o crear identificador
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
            scan.status = 'failed'
            scan.error_message = str(e)
            db.commit()
            return scan

        # Guardar findings y actualizar scan
        await self._save_findings(scan, findings_list, identifier, db)
        return scan

    async def scan_url(self, url: str, user_id: int, db: Session) -> OSINTScan:
        """Escanear URL en múltiples fuentes."""
        scan = OSINTScan(
            scan_type=OSINTScanType.URL,
            target=url,
            user_id=user_id,
            status='in_progress'
        )
        db.add(scan)
        db.commit()
        db.refresh(scan)

        findings_list = []

        try:
            # VirusTotal
            vt_result = await virustotal_service.analyze_url(url)
            if vt_result:
                vt_findings = virustotal_service.map_vt_to_findings(
                    vt_result, scan.id
                )
                findings_list.extend(vt_findings)

        except Exception as e:
            scan.status = 'failed'
            scan.error_message = str(e)
            db.commit()
            return scan

        # Guardar findings
        await self._save_findings(scan, findings_list, None, db)
        return scan

    async def scan_username(self, username: str, user_id: int, db: Session) -> OSINTScan:
        """Escanear nombre de usuario en GitHub y redes sociales."""
        scan = OSINTScan(
            scan_type=OSINTScanType.USERNAME,
            target=username,
            user_id=user_id,
            status='in_progress'
        )
        db.add(scan)
        db.commit()
        db.refresh(scan)

        findings_list = []
        identifier = None

        try:
            # Obtener o crear identificador
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

            # GitHub
            user_info = await github_service.check_user_info(username)
            repos = await github_service.get_user_repos(username)
            secrets = await github_service.search_secrets_in_code(username)

            github_findings = github_service.map_github_to_findings(
                username,
                {
                    'user_info': user_info,
                    'repos': repos,
                    'secrets': secrets
                },
                scan.id,
                identifier.id
            )
            findings_list.extend(github_findings)

        except Exception as e:
            scan.status = 'failed'
            scan.error_message = str(e)
            db.commit()
            return scan

        # Guardar findings
        await self._save_findings(scan, findings_list, identifier, db)
        return scan

    async def _save_findings(self, scan: OSINTScan, findings_list: List[dict],
                            identifier: Optional[OSINTIdentifier], db: Session):
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

        # Actualizar estadísticas del scan
        scan.findings_count = len(findings_list)
        if findings_list:
            scan.risk_score = sum(f.get('risk_score', 0) for f in findings_list) / len(findings_list)
        scan.status = 'completed'
        scan.completed_at = datetime.now(timezone.utc)

        # Actualizar last_scanned_at del identificador
        if identifier:
            identifier.last_scanned_at = datetime.now(timezone.utc)
            if scan.risk_score > 70:
                identifier.risk_level = OSINTFindingRiskLevel.CRITICAL
            elif scan.risk_score > 50:
                identifier.risk_level = OSINTFindingRiskLevel.HIGH
            elif scan.risk_score > 30:
                identifier.risk_level = OSINTFindingRiskLevel.MEDIUM
            elif scan.risk_score > 10:
                identifier.risk_level = OSINTFindingRiskLevel.LOW

        db.commit()


osint_engine = OSINTEngine()
