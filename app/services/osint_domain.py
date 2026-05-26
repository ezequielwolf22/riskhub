"""Servicio OSINT para dominios: DNS, SSL, subdominios via crt.sh, RDAP."""
import asyncio
import socket
import ssl
import datetime
from typing import List, Optional
import aiohttp


class DomainOSINTService:
    """Recopila inteligencia sobre un dominio usando APIs publicas gratuitas."""

    async def get_dns_records(self, domain: str) -> dict:
        """Consulta registros DNS via dns.google DOH (sin dependencias extra)."""
        record_types = ['A', 'AAAA', 'MX', 'NS', 'TXT', 'CNAME', 'SOA']
        results = {}

        async with aiohttp.ClientSession() as session:
            for rtype in record_types:
                try:
                    url = f'https://dns.google/resolve?name={domain}&type={rtype}'
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            answers = data.get('Answer', [])
                            if answers:
                                results[rtype] = [a.get('data', '') for a in answers]
                except Exception:
                    continue

        return results

    async def get_ssl_info(self, domain: str) -> Optional[dict]:
        """Obtiene informacion del certificado SSL del dominio."""
        try:
            loop = asyncio.get_event_loop()

            def _fetch_cert():
                ctx = ssl.create_default_context()
                with ctx.wrap_socket(
                    socket.socket(socket.AF_INET),
                    server_hostname=domain
                ) as s:
                    s.settimeout(8)
                    s.connect((domain, 443))
                    return s.getpeercert()

            cert = await loop.run_in_executor(None, _fetch_cert)
            if not cert:
                return None

            not_after = cert.get('notAfter', '')
            expiry = None
            days_left = None

            if not_after:
                try:
                    expiry = datetime.datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
                    days_left = (expiry - datetime.datetime.utcnow()).days
                except Exception:
                    pass

            subject = dict(x[0] for x in cert.get('subject', []))
            issuer = dict(x[0] for x in cert.get('issuer', []))
            sans = []
            for ext in cert.get('subjectAltName', []):
                if ext[0] == 'DNS':
                    sans.append(ext[1])

            return {
                'subject_cn': subject.get('commonName'),
                'issuer_org': issuer.get('organizationName', issuer.get('commonName')),
                'not_after': not_after,
                'days_left': days_left,
                'san_count': len(sans),
                'sans': sans[:10],
                'expired': days_left is not None and days_left < 0,
                'expiring_soon': days_left is not None and 0 <= days_left <= 30
            }
        except Exception:
            return None

    async def get_subdomains_crtsh(self, domain: str) -> List[str]:
        """Busca subdominios via certificate transparency (crt.sh)."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f'https://crt.sh/?q=%.{domain}&output=json'
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json(content_type=None)
                    seen = set()
                    subs = []
                    for entry in data:
                        name = entry.get('name_value', '')
                        for sub in name.split('\n'):
                            sub = sub.strip().lstrip('*.')
                            if sub and sub not in seen and sub.endswith(domain):
                                seen.add(sub)
                                subs.append(sub)
                    return sorted(subs)[:50]
        except Exception:
            return []

    async def get_rdap_info(self, domain: str) -> Optional[dict]:
        """Obtiene info WHOIS/RDAP del dominio."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f'https://rdap.org/domain/{domain}'
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()

                    registrant = None
                    registrar = None
                    created = None
                    expires = None

                    for entity in data.get('entities', []):
                        roles = entity.get('roles', [])
                        vcard = entity.get('vcardArray', [None, []])[1]
                        name = next((v[3] for v in vcard if v[0] == 'fn'), None)
                        if 'registrant' in roles:
                            registrant = name
                        if 'registrar' in roles:
                            registrar = name

                    for event in data.get('events', []):
                        action = event.get('eventAction', '')
                        date = event.get('eventDate', '')[:10]
                        if action == 'registration':
                            created = date
                        elif action == 'expiration':
                            expires = date

                    return {
                        'registrant': registrant,
                        'registrar': registrar,
                        'created': created,
                        'expires': expires,
                        'status': data.get('status', []),
                        'name_servers': [
                            ns.get('ldhName') for ns in data.get('nameservers', [])
                        ]
                    }
        except Exception:
            return None

    async def get_http_headers(self, domain: str) -> dict:
        """Comprueba cabeceras de seguridad HTTP."""
        security_headers = [
            'strict-transport-security',
            'content-security-policy',
            'x-frame-options',
            'x-content-type-options',
            'referrer-policy',
            'permissions-policy',
        ]
        try:
            async with aiohttp.ClientSession() as session:
                url = f'https://{domain}'
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=10),
                    allow_redirects=True,
                    ssl=False
                ) as resp:
                    headers = dict(resp.headers)
                    present = [h for h in security_headers if h in {k.lower() for k in headers}]
                    missing = [h for h in security_headers if h not in {k.lower() for k in headers}]
                    return {
                        'status_code': resp.status,
                        'headers_present': present,
                        'headers_missing': missing,
                        'score': int((len(present) / len(security_headers)) * 100)
                    }
        except Exception:
            return {}

    def map_to_findings(self, domain: str, dns: dict, ssl_info: Optional[dict],
                        subdomains: List[str], rdap: Optional[dict],
                        http: dict, scan_id: int,
                        identifier_id: Optional[int] = None) -> List[dict]:
        """Convierte resultado de analisis de dominio a OSINTFindings."""
        findings = []

        # DNS: IPs expuestas
        if dns.get('A'):
            findings.append({
                'scan_id': scan_id,
                'identifier_id': identifier_id,
                'source': 'domain',
                'finding_type': 'dns_records',
                'title': f"Registros DNS activos en {domain}",
                'description': (
                    f"A: {', '.join(dns.get('A', []))}\n"
                    f"MX: {', '.join(dns.get('MX', []))}\n"
                    f"NS: {', '.join(dns.get('NS', []))}"
                ),
                'risk_level': 'info',
                'risk_score': 10.0,
                'metadata': dns
            })

        # SSL: caducado o proximos a caducar
        if ssl_info:
            if ssl_info.get('expired'):
                findings.append({
                    'scan_id': scan_id,
                    'identifier_id': identifier_id,
                    'source': 'domain',
                    'finding_type': 'ssl_expired',
                    'title': f"Certificado SSL caducado en {domain}",
                    'description': f"Caducó el: {ssl_info.get('not_after')}. "
                                   f"Emitido por: {ssl_info.get('issuer_org')}",
                    'risk_level': 'critical',
                    'risk_score': 90.0,
                    'metadata': ssl_info
                })
            elif ssl_info.get('expiring_soon'):
                findings.append({
                    'scan_id': scan_id,
                    'identifier_id': identifier_id,
                    'source': 'domain',
                    'finding_type': 'ssl_expiring',
                    'title': f"Certificado SSL caduca en {ssl_info.get('days_left')} dias en {domain}",
                    'description': f"Caduca el: {ssl_info.get('not_after')}. "
                                   f"Emitido por: {ssl_info.get('issuer_org')}",
                    'risk_level': 'high',
                    'risk_score': 70.0,
                    'metadata': ssl_info
                })
            else:
                findings.append({
                    'scan_id': scan_id,
                    'identifier_id': identifier_id,
                    'source': 'domain',
                    'finding_type': 'ssl_info',
                    'title': f"SSL valido en {domain} ({ssl_info.get('days_left')} dias restantes)",
                    'description': f"Emitido por: {ssl_info.get('issuer_org')}",
                    'risk_level': 'info',
                    'risk_score': 5.0,
                    'metadata': ssl_info
                })

        # Subdominios expuestos
        if subdomains:
            findings.append({
                'scan_id': scan_id,
                'identifier_id': identifier_id,
                'source': 'domain',
                'finding_type': 'subdomain_exposure',
                'title': f"{len(subdomains)} subdominios encontrados para {domain}",
                'description': ', '.join(subdomains[:15]),
                'risk_level': 'medium' if len(subdomains) > 10 else 'low',
                'risk_score': min(60.0, len(subdomains) * 2),
                'metadata': {'subdomains': subdomains}
            })

        # Cabeceras HTTP faltantes
        if http and http.get('headers_missing'):
            score = http.get('score', 0)
            findings.append({
                'scan_id': scan_id,
                'identifier_id': identifier_id,
                'source': 'domain',
                'finding_type': 'missing_security_headers',
                'title': f"Cabeceras de seguridad HTTP faltantes en {domain}",
                'description': f"Faltan: {', '.join(http.get('headers_missing', []))}. "
                               f"Score: {score}/100",
                'risk_level': 'high' if score < 40 else ('medium' if score < 70 else 'low'),
                'risk_score': max(0, 100 - score),
                'metadata': http
            })

        return findings


domain_osint_service = DomainOSINTService()
