"""Servicio para escaneo en Intelligence X."""
import asyncio
import aiohttp
from typing import List, Optional
from app.config import settings


class IntelXService:
    """Integración con API de Intelligence X."""

    def __init__(self):
        self.api_key = settings.intelx_api_key
        self.base_url = 'https://free.intelx.io'

    async def search(self, query: str, max_results: int = 10) -> dict:
        """
        Búsqueda general en Intelligence X.
        """
        if not self.api_key:
            return {'results': [], 'note': 'IntelX no configurado'}

        try:
            headers = {'x-key': self.api_key}
            payload = {
                'term': query,
                'maxresults': max_results,
                'media': 0,
                'target': 0,
                'terminate': [],
                'timeout': 10
            }

            async with aiohttp.ClientSession() as session:
                # Initiate search
                async with session.post(
                    f"{self.base_url}/intelligent/search",
                    json=payload,
                    headers=headers,
                    timeout=30
                ) as resp:
                    if resp.status != 200:
                        return {'results': [], 'error': 'Search initiation failed'}

                    init_data = await resp.json()
                    search_id = init_data.get('id')

                    if not search_id:
                        return {'results': [], 'error': 'No search ID returned'}

                # Wait for results
                await asyncio.sleep(3)

                # Get results
                async with session.get(
                    f"{self.base_url}/intelligent/search/result",
                    params={'id': search_id, 'limit': max_results},
                    headers=headers,
                    timeout=30
                ) as resp:
                    if resp.status != 200:
                        return {'results': []}

                    results_data = await resp.json()
                    records = results_data.get('records', [])

                    return {
                        'results': [
                            {
                                'name': r.get('name'),
                                'date': r.get('date'),
                                'type': r.get('type'),
                                'bucket': r.get('bucket'),
                                'media': r.get('media')
                            }
                            for r in records
                        ],
                        'total': results_data.get('total', 0)
                    }

        except asyncio.TimeoutError:
            return {'results': [], 'error': 'Search timeout'}
        except Exception as e:
            return {'results': [], 'error': str(e)}

    async def search_email(self, email: str) -> List[dict]:
        """Búsqueda específica para email."""
        result = await self.search(email, max_results=10)
        records = result.get('results', [])

        return [
            {
                'source': 'intelligence_x',
                'type': 'paste_exposure',
                'title': f"Email encontrado en: {r.get('name', 'fuente desconocida')}",
                'description': f"Tipo: {r.get('bucket', 'desconocido')} · "
                              f"Fecha: {r.get('date', 'desconocida')}",
                'risk_level': 'high',
                'risk_score': 70.0,
                'metadata': r
            }
            for r in records
        ]

    async def search_domain(self, domain: str) -> List[dict]:
        """Búsqueda específica para dominio."""
        result = await self.search(domain, max_results=10)
        records = result.get('results', [])

        return [
            {
                'source': 'intelligence_x',
                'type': 'domain_exposure',
                'title': f"Dominio expuesto en: {r.get('name', 'fuente desconocida')}",
                'description': f"Bucket: {r.get('bucket', 'desconocido')}",
                'risk_level': 'medium',
                'risk_score': 55.0,
                'metadata': r
            }
            for r in records
        ]

    def map_results_to_findings(self, results: List[dict], scan_id: int,
                               identifier_id: Optional[int] = None) -> List[dict]:
        """Convertir resultados de IntelX a OSINTFinding."""
        findings = []

        for result in results:
            finding = {
                'scan_id': scan_id,
                'identifier_id': identifier_id,
                'source': 'intelx',
                'finding_type': 'paste_exposure',
                'title': result.get('title', 'Datos expuestos en IntelX'),
                'description': result.get('description', ''),
                'risk_level': result.get('risk_level', 'medium'),
                'risk_score': result.get('risk_score', 55.0),
                'metadata': result.get('metadata', {})
            }
            findings.append(finding)

        return findings


intelx_service = IntelXService()
