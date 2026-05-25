"""Servicio para escaneo en VirusTotal."""
import asyncio
import time
import hashlib
from typing import Optional, Tuple
import aiohttp
from app.config import settings


class VirusTotalService:
    """Integración con API de VirusTotal."""

    def __init__(self):
        self.api_key = getattr(settings, 'VIRUSTOTAL_API_KEY', None)
        self.base_url = 'https://www.virustotal.com/api/v3'
        self.last_call_time = 0
        self.rate_limit_ms = 15000  # 15 segundos entre requests (60 requests/min)

    async def _rate_limit(self):
        """Respetar rate limit de VirusTotal."""
        elapsed = (time.time() - self.last_call_time) * 1000
        if elapsed < self.rate_limit_ms:
            await asyncio.sleep((self.rate_limit_ms - elapsed) / 1000)
        self.last_call_time = time.time()

    def _calc_risk(self, malicious: int, suspicious: int, total: int) -> Tuple[float, str]:
        """Calcular score y nivel de riesgo."""
        if total == 0:
            return 0.0, 'safe'

        score = min(100, ((malicious * 2 + suspicious) / total) * 100)
        level = 'dangerous' if score > 50 else ('suspicious' if score > 15 else 'safe')
        return score, level

    async def analyze_url(self, url: str) -> Optional[dict]:
        """
        Analizar URL con VirusTotal.
        Retorna dict con análisis o None si error.
        """
        if not self.api_key:
            return None

        await self._rate_limit()

        try:
            headers = {'x-apikey': self.api_key}

            async with aiohttp.ClientSession() as session:
                # Submit URL para análisis
                data = {'url': url}
                async with session.post(
                    f"{self.base_url}/urls",
                    data=data,
                    headers=headers,
                    timeout=30
                ) as resp:
                    if resp.status != 200:
                        return None

                    submit_data = await resp.json()
                    analysis_id = submit_data.get('data', {}).get('id')

                    if not analysis_id:
                        return None

                # Esperar y recuperar resultado
                for attempt in range(10):
                    await asyncio.sleep(3)
                    await self._rate_limit()

                    async with session.get(
                        f"{self.base_url}/analyses/{analysis_id}",
                        headers=headers,
                        timeout=30
                    ) as resp:
                        if resp.status != 200:
                            continue

                        analysis = await resp.json()
                        analysis_data = analysis.get('data', {})
                        status = analysis_data.get('attributes', {}).get('status')

                        if status != 'completed':
                            continue

                        stats = analysis_data.get('attributes', {}).get('stats', {})
                        total = (stats.get('malicious', 0) +
                                stats.get('suspicious', 0) +
                                stats.get('harmless', 0) +
                                stats.get('undetected', 0))

                        score, level = self._calc_risk(
                            stats.get('malicious', 0),
                            stats.get('suspicious', 0),
                            total
                        )

                        try:
                            domain = url.split('://')[1].split('/')[0]
                        except (IndexError, ValueError):
                            domain = 'unknown'

                        return {
                            'url': url,
                            'domain': domain,
                            'score': score,
                            'level': level,
                            'malicious': stats.get('malicious', 0),
                            'suspicious': stats.get('suspicious', 0),
                            'harmless': stats.get('harmless', 0),
                            'undetected': stats.get('undetected', 0),
                            'analysis_id': analysis_id
                        }

                return None

        except asyncio.TimeoutError:
            return None
        except Exception:
            return None

    async def analyze_file_hash(self, file_hash: str) -> Optional[dict]:
        """Analizar hash de archivo (MD5, SHA1, SHA256)."""
        if not self.api_key:
            return None

        await self._rate_limit()

        try:
            headers = {'x-apikey': self.api_key}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/files/{file_hash}",
                    headers=headers,
                    timeout=10
                ) as resp:
                    if resp.status == 404:
                        return None
                    if resp.status != 200:
                        return None

                    file_data = await resp.json()
                    attributes = file_data.get('data', {}).get('attributes', {})
                    stats = attributes.get('last_analysis_stats', {})

                    total = (stats.get('malicious', 0) +
                            stats.get('suspicious', 0) +
                            stats.get('harmless', 0) +
                            stats.get('undetected', 0))

                    score, level = self._calc_risk(
                        stats.get('malicious', 0),
                        stats.get('suspicious', 0),
                        total
                    )

                    return {
                        'hash': file_hash,
                        'filename': attributes.get('meaningful_name', 'unknown'),
                        'size': attributes.get('size', 0),
                        'score': score,
                        'level': level,
                        'malicious': stats.get('malicious', 0),
                        'suspicious': stats.get('suspicious', 0)
                    }

        except Exception:
            return None

    def map_vt_to_findings(self, vt_result: dict, scan_id: int,
                           identifier_id: Optional[int] = None) -> list:
        """Convertir resultado de VirusTotal a OSINTFinding."""
        if not vt_result or vt_result.get('level') == 'safe':
            return []

        finding_type = 'url_malware'
        risk_level = {
            'dangerous': 'critical',
            'suspicious': 'high',
            'safe': 'info'
        }.get(vt_result.get('level'), 'medium')

        return [{
            'scan_id': scan_id,
            'identifier_id': identifier_id,
            'source': 'virustotal',
            'finding_type': finding_type,
            'title': f"URL potencialmente maliciosa detectada: {vt_result.get('domain')}",
            'description': f"Malware: {vt_result.get('malicious')}, "
                          f"Sospechoso: {vt_result.get('suspicious')}",
            'risk_level': risk_level,
            'risk_score': float(vt_result.get('score', 0)),
            'metadata': {
                'url': vt_result.get('url'),
                'malicious': vt_result.get('malicious'),
                'suspicious': vt_result.get('suspicious'),
                'harmless': vt_result.get('harmless'),
                'analysis_id': vt_result.get('analysis_id')
            }
        }]


virustotal_service = VirusTotalService()
