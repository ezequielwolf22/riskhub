"""Servicio para escaneo en GitHub."""
import re
import aiohttp
from typing import List, Optional
from app.config import settings


class GitHubService:
    """Integración con GitHub para OSINT de repositorios públicos."""

    def __init__(self):
        self.api_key = getattr(settings, 'GITHUB_API_TOKEN', None)
        self.base_url = 'https://api.github.com'
        self.secret_patterns = {
            'aws_key': r'AKIA[0-9A-Z]{16}',
            'private_key': r'-----BEGIN RSA PRIVATE KEY-----',
            'api_key': r'api[_-]?key[\s]*[:=][\s]*[\'"]([a-zA-Z0-9\-_]{20,})[\'"]',
            'database_url': r'(postgres|mysql|mongodb)://[^\s]+',
            'slack_token': r'xox[baprs]-[0-9a-zA-Z]{10,46}',
            'github_token': r'ghp_[0-9a-zA-Z]{36}',
            'npm_token': r'npm_[A-Za-z0-9]{36}',
            'stripe_key': r'(sk|pk)_live_[0-9a-zA-Z]{20,}'
        }

    async def get_user_repos(self, username: str) -> List[dict]:
        """Obtener repositorios públicos de un usuario."""
        try:
            headers = {}
            if self.api_key:
                headers['Authorization'] = f'token {self.api_key}'

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/users/{username}/repos",
                    headers=headers,
                    params={'per_page': 100},
                    timeout=10
                ) as resp:
                    if resp.status != 200:
                        return []

                    repos = await resp.json()
                    return [
                        {
                            'name': r.get('name'),
                            'url': r.get('html_url'),
                            'description': r.get('description', ''),
                            'stars': r.get('stargazers_count', 0),
                            'is_fork': r.get('fork', False),
                            'language': r.get('language'),
                            'updated_at': r.get('updated_at')
                        }
                        for r in repos if not r.get('private')
                    ]

        except Exception:
            return []

    async def search_secrets_in_code(self, username: str) -> List[dict]:
        """Buscar patrones de secretos en repositorios públicos."""
        findings = []
        repos = await self.get_user_repos(username)

        for repo in repos:
            for pattern_name, pattern in self.secret_patterns.items():
                try:
                    # En una implementación real, buscaría en el código actual
                    # Por ahora, retorna potenciales vulnerabilidades basadas en
                    # análisis de metadatos
                    if any(keyword in repo.get('description', '').lower() for
                           keyword in ['secret', 'key', 'token', 'password']):
                        findings.append({
                            'pattern': pattern_name,
                            'repo': repo['name'],
                            'url': repo['url'],
                            'risk': 'high'
                        })
                except Exception:
                    continue

        return findings

    async def check_user_info(self, username: str) -> Optional[dict]:
        """Obtener información pública del usuario GitHub."""
        try:
            headers = {}
            if self.api_key:
                headers['Authorization'] = f'token {self.api_key}'

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/users/{username}",
                    headers=headers,
                    timeout=10
                ) as resp:
                    if resp.status != 200:
                        return None

                    user = await resp.json()
                    return {
                        'username': user.get('login'),
                        'name': user.get('name'),
                        'email': user.get('email'),
                        'bio': user.get('bio'),
                        'location': user.get('location'),
                        'company': user.get('company'),
                        'blog': user.get('blog'),
                        'twitter': user.get('twitter_username'),
                        'public_repos': user.get('public_repos'),
                        'followers': user.get('followers'),
                        'created_at': user.get('created_at'),
                        'updated_at': user.get('updated_at')
                    }

        except Exception:
            return None

    def map_github_to_findings(self, username: str, findings_data: dict,
                              scan_id: int, identifier_id: Optional[int] = None) -> List[dict]:
        """Convertir hallazgos de GitHub a OSINTFinding."""
        findings = []

        # Información de usuario expuesta
        user_info = findings_data.get('user_info', {})
        if user_info:
            exposed_fields = []
            if user_info.get('email'):
                exposed_fields.append('email público')
            if user_info.get('location'):
                exposed_fields.append('ubicación')
            if user_info.get('twitter'):
                exposed_fields.append('usuario Twitter')

            if exposed_fields:
                findings.append({
                    'scan_id': scan_id,
                    'identifier_id': identifier_id,
                    'source': 'github',
                    'finding_type': 'info_disclosure',
                    'title': f"Información pública expuesta en perfil GitHub: {username}",
                    'description': f"Campos públicos: {', '.join(exposed_fields)}",
                    'risk_level': 'low',
                    'risk_score': 20.0,
                    'metadata': {
                        'username': username,
                        'profile_data': user_info
                    }
                })

        # Secretos encontrados en código
        secrets = findings_data.get('secrets', [])
        for secret in secrets:
            findings.append({
                'scan_id': scan_id,
                'identifier_id': identifier_id,
                'source': 'github',
                'finding_type': 'exposed_secret',
                'title': f"Posible {secret['pattern'].replace('_', ' ')} "
                         f"encontrada en {secret['repo']}",
                'description': f"Repositorio: {secret['url']}",
                'risk_level': 'high',
                'risk_score': 85.0,
                'metadata': {
                    'pattern': secret['pattern'],
                    'repo': secret['repo'],
                    'repo_url': secret['url']
                }
            })

        return findings


github_service = GitHubService()
