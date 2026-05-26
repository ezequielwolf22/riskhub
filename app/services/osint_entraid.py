"""Servicio de importacion de targets desde Microsoft Entra ID (Azure AD) via MS Graph API."""
import logging
from typing import List, Optional
import aiohttp

logger = logging.getLogger(__name__)


class EntraIDService:
    """Importa usuarios, grupos y dominios desde Microsoft Entra ID para escaneo OSINT."""

    GRAPH_URL = 'https://graph.microsoft.com/v1.0'
    TOKEN_URL = 'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'

    async def get_access_token(self, tenant_id: str, client_id: str, client_secret: str) -> Optional[str]:
        """Obtiene token de acceso via Client Credentials Flow."""
        try:
            url = self.TOKEN_URL.format(tenant_id=tenant_id)
            data = {
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': client_secret,
                'scope': 'https://graph.microsoft.com/.default'
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("Entra ID token error %s: %s", resp.status, body[:200])
                        return None
                    result = await resp.json()
                    return result.get('access_token')
        except Exception as e:
            logger.error("Entra ID token exception: %s", e)
            return None

    async def list_users(self, token: str, limit: int = 200) -> List[dict]:
        """Lista usuarios del tenant con email, UPN y nombre."""
        try:
            headers = {'Authorization': f'Bearer {token}'}
            params = {
                '$select': 'id,displayName,userPrincipalName,mail,jobTitle,department,accountEnabled',
                '$top': str(min(limit, 999)),
                '$filter': 'accountEnabled eq true'
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'{self.GRAPH_URL}/users',
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    users = []
                    for u in data.get('value', []):
                        email = u.get('mail') or u.get('userPrincipalName', '')
                        if email and '#EXT#' not in email:
                            users.append({
                                'id': u.get('id'),
                                'name': u.get('displayName', ''),
                                'email': email,
                                'upn': u.get('userPrincipalName', ''),
                                'job_title': u.get('jobTitle', ''),
                                'department': u.get('department', ''),
                                'enabled': u.get('accountEnabled', True)
                            })
                    return users
        except Exception as e:
            logger.error("Entra ID list_users error: %s", e)
            return []

    async def list_domains(self, token: str) -> List[dict]:
        """Lista dominios verificados del tenant."""
        try:
            headers = {'Authorization': f'Bearer {token}'}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'{self.GRAPH_URL}/domains',
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    return [
                        {
                            'id': d.get('id'),
                            'is_verified': d.get('isVerified', False),
                            'is_default': d.get('isDefault', False),
                            'authentication_type': d.get('authenticationType', '')
                        }
                        for d in data.get('value', [])
                        if d.get('isVerified')
                    ]
        except Exception as e:
            logger.error("Entra ID list_domains error: %s", e)
            return []

    async def list_groups(self, token: str) -> List[dict]:
        """Lista grupos de seguridad del tenant."""
        try:
            headers = {'Authorization': f'Bearer {token}'}
            params = {
                '$select': 'id,displayName,mail,groupTypes',
                '$top': '100',
                '$filter': "securityEnabled eq true"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'{self.GRAPH_URL}/groups',
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    return [
                        {
                            'id': g.get('id'),
                            'name': g.get('displayName', ''),
                            'mail': g.get('mail', '')
                        }
                        for g in data.get('value', [])
                    ]
        except Exception as e:
            logger.error("Entra ID list_groups error: %s", e)
            return []

    async def test_connection(self, tenant_id: str, client_id: str, client_secret: str) -> dict:
        """Prueba la conexion con Entra ID y devuelve info del tenant."""
        token = await self.get_access_token(tenant_id, client_id, client_secret)
        if not token:
            return {'success': False, 'error': 'No se pudo obtener token. Revisa tenant_id, client_id y client_secret.'}

        try:
            headers = {'Authorization': f'Bearer {token}'}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'{self.GRAPH_URL}/organization',
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        return {'success': False, 'error': f'Graph API error: {resp.status}'}
                    data = await resp.json()
                    org = data.get('value', [{}])[0]
                    return {
                        'success': True,
                        'tenant_name': org.get('displayName', 'Unknown'),
                        'tenant_id': org.get('id'),
                        'country': org.get('country'),
                        'token': token
                    }
        except Exception as e:
            return {'success': False, 'error': str(e)}


entraid_service = EntraIDService()
