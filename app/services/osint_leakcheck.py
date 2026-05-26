"""Servicio para escaneo en LeakCheck."""
import aiohttp
from typing import List, Optional
from app.config import settings


class LeakCheckService:
    """Integración con API de LeakCheck."""

    def __init__(self):
        self.api_key = settings.leakcheck_api_key
        self.base_url = 'https://leakcheck.io/api/public'

    async def check_email(self, email: str) -> List[dict]:
        """
        Verificar si email está en base de datos de LeakCheck.
        """
        try:
            params = {'check': email}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.base_url,
                    params=params,
                    timeout=10
                ) as resp:
                    if resp.status != 200:
                        return []

                    data = await resp.json()

                    if not data.get('found'):
                        return []

                    sources = data.get('sources', [])
                    return [
                        {
                            'name': s.get('name', 'Unknown Source'),
                            'breach_date': s.get('date'),
                            'data_classes': s.get('fields', []),
                            'is_verified': True,
                            'source': 'leakcheck'
                        }
                        for s in sources
                    ]

        except Exception:
            return []

    def map_sources_to_findings(self, email: str, sources: List[dict], scan_id: int,
                                identifier_id: Optional[int] = None) -> List[dict]:
        """Convertir fuentes LeakCheck a OSINTFinding."""
        findings = []

        for source in sources:
            has_password = any(
                'password' in f.lower() or 'hash' in f.lower()
                for f in source.get('data_classes', [])
            )

            finding = {
                'scan_id': scan_id,
                'identifier_id': identifier_id,
                'source': 'leakcheck',
                'finding_type': 'data_breach',
                'title': f"Email encontrado en: {source['name']}",
                'description': f"Datos expuestos: {', '.join(source.get('data_classes', []))}",
                'risk_level': 'high' if has_password else 'medium',
                'risk_score': 75.0 if has_password else 45.0,
                'metadata': {
                    'source_name': source['name'],
                    'breach_date': source.get('breach_date'),
                    'data_classes': source.get('data_classes', [])
                }
            }
            findings.append(finding)

        return findings


leakcheck_service = LeakCheckService()
