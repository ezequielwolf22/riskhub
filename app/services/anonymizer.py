"""Anonimizacion de texto antes de enviar a APIs externas."""
import re

# Patrones de PII
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9\-]+\.)+(?:com|es|net|org|io|eu|de|fr|uk|internal|local|corp)\b"
)


def anonymize(text: str, level: str) -> str:
    """Reemplaza PII en el texto segun el nivel de anonimizacion.

    Niveles:
      low    — IPs + emails
      medium — IPs + emails + dominios
      high   — IPs + emails + dominios (nombres propios requeririan NLP)
    """
    ip_map: dict[str, int] = {}
    email_map: dict[str, int] = {}
    domain_map: dict[str, int] = {}

    def _sub_ip(m: re.Match) -> str:
        v = m.group()
        if v not in ip_map:
            ip_map[v] = len(ip_map) + 1
        return f"[IP_{ip_map[v]}]"

    def _sub_email(m: re.Match) -> str:
        v = m.group()
        if v not in email_map:
            email_map[v] = len(email_map) + 1
        return f"[EMAIL_{email_map[v]}]"

    def _sub_domain(m: re.Match) -> str:
        v = m.group()
        if v not in domain_map:
            domain_map[v] = len(domain_map) + 1
        return f"[DOMINIO_{domain_map[v]}]"

    if level in ("low", "medium", "high"):
        text = _IP_RE.sub(_sub_ip, text)
        text = _EMAIL_RE.sub(_sub_email, text)

    if level in ("medium", "high"):
        text = _DOMAIN_RE.sub(_sub_domain, text)

    return text
