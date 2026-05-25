"""Servicio para escaneo en Have I Been Pwned (HIBP)."""
import asyncio
import time
from typing import List, Optional
import aiohttp
from app.config import settings


class HibpService:
    """Integración con API de Have I Been Pwned."""

    def __init__(self):
        self.api_key = getattr(settings, 'HIBP_API_KEY', None)
        self.base_url = 'https://haveibeenpwned.com/api/v3'
        self.last_call_time = 0
        self.rate_limit_ms = 1500  # 1 request cada 1.5s según HIBP

    async def _rate_limit(self):
        """Respetar rate limit de HIBP."""
        elapsed = (time.time() - self.last_call_time) * 1000
        if elapsed < self.rate_limit_ms:
            await asyncio.sleep((self.rate_limit_ms - elapsed) / 1000)
        self.last_call_time = time.time()

    async def check_email(self, email: str) -> List[dict]:
        """
        Verificar si un email está en un breach conocido.
        Retorna lista de breaches.
        """
        if not self.api_key:
            return []

        await self._rate_limit()

        try:
            headers = {
                'hibp-api-key': self.api_key,
                'user-agent': 'RiskHub-OSINT/1.0'
            }
            params = {'truncateResponse': 'false'}

            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/breachedaccount/{email}"
                async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                    if resp.status == 404:
                        return []
                    if resp.status == 401:
                        raise ValueError('HIBP API key inválida')
                    if resp.status != 200:
                        return []

                    breaches = await resp.json()
                    return [
                        {
                            'name': b.get('Name', 'Unknown'),
                            'domain': b.get('Domain', ''),
                            'breach_date': b.get('BreachDate', ''),
                            'pwn_count': b.get('PwnCount', 0),
                            'data_classes': b.get('DataClasses', []),
                            'is_verified': b.get('IsVerified', False),
                            'description': b.get('Description', '')
                        }
                        for b in breaches
                    ]
        except asyncio.TimeoutError:
            return []
        except Exception:
            return []

    async def check_password(self, password: str) -> bool:
        """Verificar si una contraseña ha sido pwneada."""
        if not self.api_key:
            return False

        await self._rate_limit()

        try:
            headers = {'user-agent': 'RiskHub-OSINT/1.0'}

            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/pwnedpassword/{password}"
                async with session.get(url, headers=headers, timeout=10) as resp:
                    return resp.status == 200
        except Exception:
            return False

    def map_breaches_to_findings(self, email: str, breaches: List[dict], scan_id: int,
                                 identifier_id: Optional[int] = None) -> List[dict]:
        """Convertir breaches HIBP a formato de OSINTFinding."""
        findings = []

        for breach in breaches:
            has_password = any(
                'password' in dc.lower() or 'hash' in dc.lower()
                for dc in breach.get('data_classes', [])
            )

            finding = {
                'scan_id': scan_id,
                'identifier_id': identifier_id,
                'source': 'hibp',
                'finding_type': 'data_breach',
                'title': f"Tu email aparece en la brecha de {breach['name']}",
                'description': f"Datos expuestos: {', '.join(breach['data_classes'])}",
                'risk_level': 'high' if has_password else 'medium',
                'risk_score': 72.0 if has_password else 42.0,
                'metadata': {
                    'breach_name': breach['name'],
                    'breach_date': breach['breach_date'],
                    'pwn_count': breach['pwn_count'],
                    'data_classes': breach['data_classes'],
                    'is_verified': breach['is_verified'],
                    'description': breach['description']
                }
            }
            findings.append(finding)

        return findings


hibp_service = HibpService()
