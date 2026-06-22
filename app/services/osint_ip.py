"""Servicio OSINT para IPs: geolocalizacion, ASN, puertos via APIs gratuitas."""
import asyncio
import socket
from typing import List, Optional
import aiohttp
from app.config import settings


class IPOSINTService:
    """Inteligencia sobre direcciones IP usando APIs publicas gratuitas."""

    async def get_ip_info(self, ip: str) -> Optional[dict]:
        """Geolocalizacion, ISP y ASN via ipinfo.io (HTTPS, gratuito, 50k req/mes)."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f'https://ipinfo.io/{ip}/json'
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    if 'bogon' in data or not data.get('country'):
                        return None
                    # loc viene como "lat,lon"
                    lat, lon = None, None
                    loc = data.get('loc', '')
                    if ',' in loc:
                        parts = loc.split(',', 1)
                        try:
                            lat, lon = float(parts[0]), float(parts[1])
                        except ValueError:
                            pass
                    # org viene como "AS12345 Nombre del ISP"
                    org_raw = data.get('org', '')
                    asn = org_raw.split(' ')[0] if org_raw else None
                    org_name = ' '.join(org_raw.split(' ')[1:]) if org_raw else None
                    return {
                        'ip': data.get('ip', ip),
                        'country': data.get('country'),
                        'country_code': data.get('country'),
                        'region': data.get('region'),
                        'city': data.get('city'),
                        'lat': lat,
                        'lon': lon,
                        'isp': org_name,
                        'org': org_name,
                        'asn': asn,
                        'is_proxy': False,
                        'is_hosting': False,
                    }
        except Exception:
            return None

    async def get_reverse_dns(self, ip: str) -> Optional[str]:
        """Reverse DNS lookup."""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, socket.gethostbyaddr, ip)
            return result[0]
        except Exception:
            return None

    async def check_open_ports(self, ip: str) -> List[int]:
        """Port scanning activo desactivado — riesgo legal (Art. 197 bis CP).
        Usar Shodan para datos de puertos sin realizar escaneos directos."""
        return []

    async def check_shodan(self, ip: str) -> Optional[dict]:
        """Consulta Shodan si hay API key disponible."""
        api_key = getattr(settings, 'shodan_api_key', None)
        if not api_key:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                url = f'https://api.shodan.io/shodan/host/{ip}?key={api_key}'
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    return {
                        'ports': data.get('ports', []),
                        'vulns': list(data.get('vulns', {}).keys()),
                        'tags': data.get('tags', []),
                        'os': data.get('os'),
                        'hostnames': data.get('hostnames', []),
                        'last_update': data.get('last_update')
                    }
        except Exception:
            return None

    def map_to_findings(self, ip: str, info: Optional[dict], rdns: Optional[str],
                        open_ports: List[int], scan_id: int,
                        identifier_id: Optional[int] = None) -> List[dict]:
        """Convierte resultado de analisis de IP a OSINTFindings."""
        findings = []

        if info:
            risk = 'info'
            score = 10.0
            notes = []

            if info.get('is_proxy'):
                notes.append('Proxy/VPN detectado')
                risk = 'medium'
                score = 50.0
            if info.get('is_hosting'):
                notes.append('Hosting/datacenter')
                risk = 'medium' if risk == 'info' else risk

            findings.append({
                'scan_id': scan_id,
                'identifier_id': identifier_id,
                'source': 'ip_intel',
                'finding_type': 'ip_geolocation',
                'title': f"IP {ip} — {info.get('city', '')}, {info.get('country', '')} ({info.get('isp', '')})",
                'description': (
                    f"ASN: {info.get('asn')} | Org: {info.get('org')}\n"
                    f"Proxy: {'Si' if info.get('is_proxy') else 'No'} | "
                    f"Hosting: {'Si' if info.get('is_hosting') else 'No'}\n"
                    + (f"Notas: {', '.join(notes)}" if notes else '')
                ),
                'risk_level': risk,
                'risk_score': score,
                'metadata': {**info, 'reverse_dns': rdns}
            })

        # Puertos peligrosos abiertos
        dangerous_ports = {
            21: 'FTP (cleartext)', 23: 'Telnet (cleartext)',
            445: 'SMB (ransomware vector)', 3389: 'RDP (brute-force)',
            3306: 'MySQL expuesto', 5432: 'PostgreSQL expuesto',
            6379: 'Redis sin auth', 27017: 'MongoDB sin auth',
            110: 'POP3', 143: 'IMAP'
        }

        found_dangerous = [(p, dangerous_ports[p]) for p in open_ports if p in dangerous_ports]

        if open_ports:
            risk = 'critical' if found_dangerous else 'medium'
            score = 85.0 if found_dangerous else 40.0

            findings.append({
                'scan_id': scan_id,
                'identifier_id': identifier_id,
                'source': 'ip_intel',
                'finding_type': 'open_ports',
                'title': f"{len(open_ports)} puertos abiertos en {ip}",
                'description': (
                    f"Puertos: {', '.join(str(p) for p in open_ports)}\n"
                    + (f"Peligrosos: {', '.join(f'{p} ({d})' for p, d in found_dangerous)}"
                       if found_dangerous else '')
                ),
                'risk_level': risk,
                'risk_score': score,
                'metadata': {'open_ports': open_ports, 'dangerous': found_dangerous}
            })

        return findings


ip_osint_service = IPOSINTService()
