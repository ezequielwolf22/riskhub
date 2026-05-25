"""Servicio de integracion con NVD (National Vulnerability Database) — NIST CVE API v2.

Documentacion: https://nvd.nist.gov/developers/vulnerabilities
Sin API key: 5 req/30s  |  Con API key: 50 req/30s
"""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("riskhub.cve")

_NVD_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"

# Cache en memoria: key -> (data, expires_at monotonic)
_CACHE: dict[str, tuple[list, float]] = {}
_CACHE_TTL = 3600   # 1 hora


def _cache_key(params: dict) -> str:
    return json.dumps(params, sort_keys=True)


def _cached(key: str) -> Optional[list]:
    if key in _CACHE:
        data, exp = _CACHE[key]
        if time.monotonic() < exp:
            return data
        del _CACHE[key]
    return None


def _store(key: str, data: list) -> None:
    _CACHE[key] = (data, time.monotonic() + _CACHE_TTL)


def _nvd_get(params: dict, api_key: Optional[str] = None) -> dict:
    """Realiza una peticion GET a la NVD API v2."""
    url = _NVD_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    if api_key:
        req.add_header("apiKey", api_key)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            msg = json.loads(body).get("message", str(e))
        except Exception:
            msg = str(e)
        raise ValueError(f"NVD API error {e.code}: {msg}")
    except urllib.error.URLError as e:
        raise ValueError(f"No se pudo contactar NVD API: {e.reason}")


def _parse_cvss(cve_item: dict) -> dict:
    """Extrae el CVSS score mas alto disponible (v3.1 > v3.0 > v2)."""
    metrics = cve_item.get("metrics", {})
    for key in ("cvssMetricV31", "cvssMetricV30"):
        items = metrics.get(key, [])
        if items:
            d = items[0].get("cvssData", {})
            return {
                "score": d.get("baseScore", 0.0),
                "severity": d.get("baseSeverity", "UNKNOWN"),
                "vector": d.get("vectorString", ""),
                "attack_vector": d.get("attackVector", ""),
                "exploitability": items[0].get("exploitabilityScore", 0.0),
                "impact": items[0].get("impactScore", 0.0),
                "version": "3.x",
            }
    items = metrics.get("cvssMetricV2", [])
    if items:
        d = items[0].get("cvssData", {})
        sev = items[0].get("baseSeverity", "UNKNOWN")
        score = d.get("baseScore", 0.0)
        return {
            "score": score,
            "severity": sev if sev else ("HIGH" if score >= 7 else "MEDIUM" if score >= 4 else "LOW"),
            "vector": d.get("vectorString", ""),
            "attack_vector": d.get("accessVector", ""),
            "exploitability": items[0].get("exploitabilityScore", 0.0),
            "impact": items[0].get("impactScore", 0.0),
            "version": "2.0",
        }
    return {"score": 0.0, "severity": "UNKNOWN", "vector": "", "attack_vector": "", "version": "?"}


def _parse_cpe_products(cve_item: dict) -> list[str]:
    """Extrae nombres de productos/vendors desde las configuraciones CPE."""
    products = set()
    for config in cve_item.get("configurations", []):
        for node in config.get("nodes", []):
            for match in node.get("cpeMatch", []):
                cpe = match.get("criteria", "")
                # cpe:2.3:a:vendor:product:version:...
                parts = cpe.split(":")
                if len(parts) >= 5:
                    vendor = parts[3].replace("_", " ").replace("-", " ")
                    product = parts[4].replace("_", " ").replace("-", " ")
                    if vendor and vendor != "*":
                        products.add(vendor.lower())
                    if product and product != "*":
                        products.add(product.lower())
    return sorted(products)


def _normalize(raw: dict) -> dict:
    """Convierte un objeto CVE de la API NVD al formato interno de RiskHub."""
    cve = raw.get("cve", {})
    cve_id = cve.get("id", "")
    descriptions = cve.get("descriptions", [])
    desc_en = next((d["value"] for d in descriptions if d.get("lang") == "en"), "")
    cvss = _parse_cvss(cve)
    products = _parse_cpe_products(cve)
    refs = [r.get("url", "") for r in cve.get("references", [])[:5]]
    return {
        "id": cve_id,
        "description": desc_en[:1000],
        "published": cve.get("published", ""),
        "modified": cve.get("lastModified", ""),
        "status": cve.get("vulnStatus", ""),
        "cvss_score": cvss["score"],
        "cvss_severity": cvss["severity"],
        "cvss_vector": cvss["vector"],
        "cvss_attack_vector": cvss["attack_vector"],
        "cvss_exploitability": cvss["exploitability"],
        "cvss_impact": cvss["impact"],
        "cvss_version": cvss["version"],
        "affected_products": products,
        "references": refs,
    }


# ---------- API publica ----------

def fetch_recent(
    api_key: Optional[str],
    days: int = 7,
    severity: Optional[str] = None,
    keyword: Optional[str] = None,
    max_results: int = 100,
) -> list[dict]:
    """Obtiene CVEs publicadas en los ultimos N dias.

    severity: CRITICAL | HIGH | MEDIUM | LOW  (None = todos)
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(1, min(days, 120)))

    params: dict = {
        "pubStartDate": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pubEndDate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resultsPerPage": min(max_results, 2000),
    }
    if severity:
        params["cvssV3Severity"] = severity.upper()
    if keyword:
        params["keywordSearch"] = keyword.strip()[:200]

    cache_key = _cache_key(params)
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        data = _nvd_get(params, api_key)
    except ValueError:
        raise

    vulns = data.get("vulnerabilities", [])
    result = [_normalize(v) for v in vulns]
    _store(cache_key, result)
    return result


def fetch_by_id(api_key: Optional[str], cve_id: str) -> Optional[dict]:
    """Obtiene un CVE especifico por su ID (ej: CVE-2024-12345)."""
    cve_id = cve_id.strip().upper()
    cache_key = f"id:{cve_id}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached[0] if cached else None
    try:
        data = _nvd_get({"cveId": cve_id}, api_key)
    except ValueError:
        return None
    vulns = data.get("vulnerabilities", [])
    if not vulns:
        return None
    result = _normalize(vulns[0])
    _store(cache_key, [result])
    return result


def score_to_risk_level(cvss_score: float) -> int:
    """Convierte CVSS score (0-10) a nivel de riesgo ISO 27005 (1-5)."""
    if cvss_score >= 9.0:
        return 5
    if cvss_score >= 7.0:
        return 4
    if cvss_score >= 4.0:
        return 3
    if cvss_score >= 1.0:
        return 2
    return 1


def asset_matches_cve(asset_name: str, asset_desc: str, cve: dict) -> float:
    """Heuristica de coincidencia entre activo y CVE (0.0 a 1.0).

    Compara los nombres de productos afectados de la CPE con el nombre
    y descripcion del activo. Score >= 0.3 se considera posible coincidencia.
    """
    text = f"{asset_name} {asset_desc}".lower()
    products = cve.get("affected_products", [])
    if not products:
        return 0.0

    matches = sum(1 for p in products if p and len(p) > 2 and p in text)
    if matches == 0:
        return 0.0
    return min(1.0, matches / max(1, len(products)) * 2)


def invalidate_cache() -> None:
    """Limpia el cache (util tras cambiar la API key)."""
    _CACHE.clear()
