"""Monitoreo periodico de proveedores: disponibilidad web, SSL, DNS y OSINT basico.

Equivalente on-premise a servicios como isitdownrightnow.com y downdetector:
  - Comprueba disponibilidad HTTP/HTTPS del sitio web del proveedor.
  - Verifica certificado SSL (caducidad, dominio).
  - Resolucion DNS del dominio.
  - Escaneo OSINT basico del dominio/email usando los conectores existentes.

Los hallazgos se almacenan como ExternalFinding con source=SUPPLIER_MONITOR,
vinculados al proveedor mediante supplier_id.
"""
import logging
import socket
import ssl
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

logger = logging.getLogger("riskhub.supplier_monitor")

# Solo crear hallazgos para estados que merecen atencion
_DOWN_HTTP_CODES = {408, 500, 502, 503, 504, 521, 522, 523, 524}


def _extract_domain(url_or_email: str) -> str | None:
    """Extrae el hostname de una URL o email. Devuelve None si no es valido."""
    if not url_or_email:
        return None
    s = url_or_email.strip()
    if "@" in s:
        return s.split("@")[-1].lower().strip()
    try:
        parsed = urlparse(s if "://" in s else "https://" + s)
        return (parsed.hostname or "").lower().strip() or None
    except Exception:
        return None


def _check_http(url: str, timeout: int = 10) -> dict:
    """Comprueba disponibilidad HTTP/HTTPS. Devuelve {ok, status, latency_ms, error}."""
    import urllib.request
    import urllib.error
    import time

    target = url if "://" in url else "https://" + url
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(
            target, method="HEAD",
            headers={"User-Agent": "RiskHub-Monitor/1.0 (internal)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency_ms = int((time.monotonic() - t0) * 1000)
            return {"ok": True, "status": resp.status, "latency_ms": latency_ms, "error": None}
    except urllib.error.HTTPError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        ok = exc.code not in _DOWN_HTTP_CODES
        return {"ok": ok, "status": exc.code, "latency_ms": latency_ms, "error": None}
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {"ok": False, "status": None, "latency_ms": latency_ms, "error": str(exc)[:200]}


def _check_ssl(hostname: str, port: int = 443, timeout: int = 10) -> dict:
    """Verifica el certificado SSL. Devuelve {ok, days_remaining, error}."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                expire_str = cert.get("notAfter", "")
                if expire_str:
                    expire_dt = datetime.strptime(expire_str, "%b %d %H:%M:%S %Y %Z").replace(
                        tzinfo=timezone.utc
                    )
                    days = (expire_dt - datetime.now(timezone.utc)).days
                    return {"ok": days > 14, "days_remaining": days, "error": None}
                return {"ok": True, "days_remaining": None, "error": None}
    except ssl.SSLCertVerificationError as exc:
        return {"ok": False, "days_remaining": None, "error": f"SSL invalido: {exc.reason}"}
    except Exception as exc:
        return {"ok": None, "days_remaining": None, "error": str(exc)[:200]}


def _check_dns(hostname: str) -> dict:
    """Verifica resolucion DNS. Devuelve {ok, ip, error}."""
    try:
        ip = socket.gethostbyname(hostname)
        return {"ok": True, "ip": ip, "error": None}
    except socket.gaierror as exc:
        return {"ok": False, "ip": None, "error": str(exc)[:200]}


def _severity_for_result(http: dict, ssl_r: dict, dns: dict) -> str:
    """Determina la severidad del hallazgo segun los resultados de las comprobaciones."""
    if not dns["ok"]:
        return "HIGH"
    if not http["ok"]:
        return "HIGH"
    if ssl_r.get("ok") is False:
        return "MEDIUM"
    days = ssl_r.get("days_remaining")
    if days is not None and days <= 30:
        return "LOW" if days > 14 else "MEDIUM"
    return "LOW"


def scan_supplier(db, supplier, org_id: int) -> list:
    """Ejecuta el monitoreo completo de un proveedor y persiste hallazgos.

    Devuelve la lista de ExternalFinding creados (puede ser vacia si todo esta OK).
    """
    from app.models import ExternalFinding, ExternalFindingSource

    domain = _extract_domain(supplier.website or supplier.contact_email or "")
    if not domain:
        return []

    url = supplier.website or ("https://" + domain)
    now = datetime.now(timezone.utc)

    http_res = _check_http(url)
    ssl_res = _check_ssl(domain)
    dns_res = _check_dns(domain)

    findings = []

    # Solo crear hallazgo si hay algun problema
    has_issue = (
        not http_res["ok"]
        or (ssl_res.get("ok") is False)
        or (ssl_res.get("days_remaining") is not None and ssl_res["days_remaining"] <= 30)
        or not dns_res["ok"]
    )

    # Registrar siempre la fecha y estado del escaneo en el proveedor
    supplier.last_monitored_at = now
    supplier.monitoring_status = "issue" if has_issue else "ok"

    if not has_issue:
        logger.debug("Supplier %s OK (HTTP %s, SSL %s dias, DNS %s)",
                     supplier.code, http_res.get("status"), ssl_res.get("days_remaining"), dns_res.get("ip"))
        return []

    severity = _severity_for_result(http_res, ssl_res, dns_res)

    # Construir descripcion del hallazgo
    parts = []
    if not dns_res["ok"]:
        parts.append(f"DNS no resuelve '{domain}': {dns_res['error']}")
    elif not http_res["ok"]:
        status = http_res.get("status")
        err = http_res.get("error") or ""
        parts.append(f"Sitio no responde (HTTP {status or 'sin respuesta'}, {http_res['latency_ms']} ms). {err}".strip())
    if ssl_res.get("ok") is False:
        parts.append(f"Certificado SSL invalido: {ssl_res.get('error', '')}")
    elif ssl_res.get("days_remaining") is not None and ssl_res["days_remaining"] <= 30:
        parts.append(f"Certificado SSL expira en {ssl_res['days_remaining']} dias")

    description = " | ".join(parts)
    title = f"Disponibilidad degradada: {supplier.name} ({domain})"

    # Eliminar hallazgo anterior pendiente del mismo proveedor (evitar acumulacion)
    old = (
        db.query(ExternalFinding)
        .filter(
            ExternalFinding.supplier_id == supplier.id,
            ExternalFinding.source == ExternalFindingSource.SUPPLIER_MONITOR,
            ExternalFinding.status == "open",
        )
        .first()
    )
    if old:
        old.description = description
        old.severity = severity
        old.detected_at = now
        db.flush()
        findings.append(old)
        return findings

    finding = ExternalFinding(
        organization_id=org_id,
        source=ExternalFindingSource.SUPPLIER_MONITOR,
        supplier_id=supplier.id,
        title=title,
        description=description,
        severity=severity,
        affected_host=domain,
        detected_at=now,
        status="open",
        raw_data=str({
            "http": http_res,
            "ssl": ssl_res,
            "dns": dns_res,
        })[:4000],
    )
    db.add(finding)
    db.flush()
    findings.append(finding)
    logger.info("Hallazgo creado para proveedor %s: %s [%s]", supplier.code, description, severity)
    return findings
