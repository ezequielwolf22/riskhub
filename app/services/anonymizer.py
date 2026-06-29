"""Anonimizacion de texto antes de enviar a APIs externas.

Aplica sustituciones consistentes (mismo valor -> mismo token) para que
el agente IA pueda razonar con los datos sin exponer PII real.

Niveles:
  low    — IPs + emails
  medium — IPs + emails + dominios + telefonos
  high   — todo lo anterior + DNI/NIF/CIF + IBAN + tarjetas de credito
"""
import re

# ---------- Patrones PII ----------

# IPv4
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# Email
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Dominio (sin capturar palabras sueltas como "local" fuera de contexto FQDN)
_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9\-]+\.)+(?:com|es|net|org|io|eu|de|fr|uk|internal|local|corp|gov|edu|mil)\b"
)

# Telefono espanol e internacional: +34 6XX-XXX-XXX / +1 555 555 5555 / etc.
_PHONE_RE = re.compile(
    r"(?:\+\d{1,3}[\s\-]?)?(?:\(?\d{2,4}\)?[\s\-]?)?\d{3}[\s\-]?\d{3}[\s\-]?\d{3,4}\b"
)

# DNI/NIE espanol: 8 digitos + letra (o X/Y/Z + 7 digitos + letra)
_DNI_RE = re.compile(r"\b(?:\d{8}|[XYZ]\d{7})[A-HJ-NP-TV-Z]\b", re.IGNORECASE)

# CIF espanol (personas juridicas): letra + 7 digitos + digito/letra control
_CIF_RE = re.compile(r"\b[ABCDEFGHJKLMNPQRSUVW]\d{7}[0-9A-J]\b", re.IGNORECASE)

# IBAN (deteccion generica: 2 letras + 2 digitos + hasta 30 alfanumericos con espacios opcionales)
_IBAN_RE = re.compile(
    r"\b[A-Z]{2}\d{2}(?:[\s\-]?[A-Z0-9]{4}){3,7}(?:[\s\-]?[A-Z0-9]{1,4})?\b",
    re.IGNORECASE,
)

# Tarjeta de credito: 13-19 digitos, a menudo en grupos separados por espacio o guion
_CC_RE = re.compile(r"\b(?:\d{4}[\s\-]){3}\d{4}\b")


def anonymize(text: str, level: str) -> str:
    """Reemplaza PII en el texto segun el nivel de anonimizacion.

    Devuelve el texto con tokens del tipo [IP_1], [EMAIL_2], [TELEFONO_1], etc.
    Los tokens son consistentes: el mismo valor original siempre produce el
    mismo token dentro de la misma llamada.
    """
    ip_map: dict[str, int] = {}
    email_map: dict[str, int] = {}
    domain_map: dict[str, int] = {}
    phone_map: dict[str, int] = {}
    doc_map: dict[str, int] = {}
    iban_map: dict[str, int] = {}
    cc_map: dict[str, int] = {}

    def _sub(val: str, store: dict, prefix: str) -> str:
        if val not in store:
            store[val] = len(store) + 1
        return f"[{prefix}_{store[val]}]"

    # Nivel low y superiores
    if level in ("low", "medium", "high"):
        text = _IP_RE.sub(lambda m: _sub(m.group(), ip_map, "IP"), text)
        text = _EMAIL_RE.sub(lambda m: _sub(m.group(), email_map, "EMAIL"), text)

    # Nivel medium y superiores
    if level in ("medium", "high"):
        text = _DOMAIN_RE.sub(lambda m: _sub(m.group(), domain_map, "DOMINIO"), text)
        text = _PHONE_RE.sub(lambda m: _sub(m.group(), phone_map, "TELEFONO"), text)

    # Nivel high: datos identificativos y financieros
    if level == "high":
        text = _IBAN_RE.sub(lambda m: _sub(m.group(), iban_map, "IBAN"), text)
        text = _CC_RE.sub(lambda m: _sub(m.group(), cc_map, "TARJETA"), text)
        text = _DNI_RE.sub(lambda m: _sub(m.group(), doc_map, "DNI"), text)
        text = _CIF_RE.sub(lambda m: _sub(m.group(), doc_map, "CIF"), text)

    return text


def anonymize_messages(messages: list[dict], level: str) -> list[dict]:
    """Anonimiza el contenido de una lista de mensajes {role, content}.

    Solo se aplica en nivel 'high' (para no degradar la experiencia de usuario
    en niveles bajos donde la coherencia conversacional tiene mas peso).
    """
    if level == "low":
        return messages
    return [
        {"role": m["role"], "content": anonymize(m["content"], level)}
        for m in messages
    ]
