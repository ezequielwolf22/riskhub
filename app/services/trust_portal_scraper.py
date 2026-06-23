"""Analisis automatico del Trust Portal de un proveedor mediante IA.

Descarga la URL configurada, extrae el texto visible y usa Claude para
inferir los campos de la ficha del proveedor (ISO 27005 TPRM).
"""
import json
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Supplier

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 20  # segundos

# Campos que el agente puede inferir del trust portal
_EXTRACTABLE_FIELDS = {
    "name", "description", "services", "category", "vendor_type",
    "contact_email", "website", "country_code", "certifications",
    "is_data_processor", "processes_personal_data", "cross_border_transfers",
    "is_nis2", "is_dora", "is_ens",
    "data_sensitivity", "data_volume", "system_access_type",
    "business_criticality", "geographic_risk", "notes",
}

_SYSTEM_PROMPT = """Eres un experto en ciberseguridad y TPRM (Third Party Risk Management) segun ISO/IEC 27005.

Analiza el contenido de un Trust Portal de un proveedor y extrae informacion estructurada para su ficha GRC.

Devuelve SOLO un objeto JSON valido con los campos que puedas inferir con confianza (omite los demas):

{
  "name": "Nombre comercial del proveedor",
  "description": "Descripcion del proveedor y sus servicios (max 500 chars)",
  "services": "Servicios ofrecidos (max 300 chars)",
  "category": "Software | Hardware | Servicios Profesionales | Cloud | Consultoria | etc.",
  "vendor_type": "technology | cloud_provider | professional_services | consultancy | hardware | subcontractor | other",
  "contact_email": "Email de contacto de seguridad",
  "website": "URL principal",
  "country_code": "Codigo ISO 3166-1 alpha-2 (ej: US, ES, DE)",
  "certifications": ["ISO27001","SOC2","SOC3","CSA_STAR","PCI_DSS","FedRAMP","GDPR","HIPAA","ISO9001"],
  "is_data_processor": true/false,
  "processes_personal_data": true/false,
  "cross_border_transfers": true/false,
  "is_nis2": true/false,
  "is_dora": true/false,
  "data_sensitivity": 1-5,
  "data_volume": 1-5,
  "system_access_type": "none | api_only | saas | paas | iaas | on_prem | read_write | admin_to_our_systems",
  "business_criticality": 1-5,
  "geographic_risk": 1-5,
  "notes": "Resumen de postura de seguridad, certificaciones y aspectos relevantes de riesgo"
}

Escalas numericas (1-5):
- data_sensitivity: 1=datos publicos, 3=datos de negocio, 5=datos criticos/personales sensibles
- data_volume: 1=minimo, 3=moderado, 5=masivo
- business_criticality: 1=no critico, 3=importante, 5=infraestructura critica
- geographic_risk: 1=UE/EEE/US/AU, 3=otros paises, 5=jurisdicciones de alto riesgo

Sin texto adicional. Sin markdown. SOLO el JSON."""


class _TextExtractor(HTMLParser):
    """Extrae texto visible de HTML ignorando scripts, estilos y metadatos."""

    _SKIP_TAGS = frozenset({'script', 'style', 'noscript', 'head', 'svg', 'path', 'iframe', 'img'})
    _BLOCK_TAGS = frozenset({'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr', 'br', 'section', 'article', 'header', 'footer', 'nav'})

    def __init__(self):
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip += 1
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append('\n')

    def handle_endtag(self, tag: str):
        if tag.lower() in self._SKIP_TAGS:
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data: str):
        if self._skip:
            return
        text = data.strip()
        if text:
            self.parts.append(text)

    def get_text(self) -> str:
        raw = ' '.join(self.parts)
        raw = re.sub(r'[ \t]+', ' ', raw)
        raw = re.sub(r'\n{3,}', '\n\n', raw)
        return raw.strip()


def _fetch_html(url: str) -> str:
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (compatible; RiskHub/2.2; TPRM-TrustPortal-Scanner)',
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            'Accept-Language': 'en,es;q=0.9',
        },
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        charset = 'utf-8'
        ct = resp.headers.get('Content-Type', '')
        m = re.search(r'charset=([^\s;]+)', ct)
        if m:
            charset = m.group(1).strip('"\'')
        raw_bytes = resp.read(1_500_000)  # max 1.5 MB
    return raw_bytes.decode(charset, errors='replace')


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.get_text()


def _resolve_ai(db: Session, org_id: Optional[int]) -> tuple[str, str]:
    from app.services.iso_clause_extractor import _resolve_ai_config
    return _resolve_ai_config(db, org_id)


def _call_claude(db: Session, org_id: Optional[int], text: str) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic no instalado")

    api_key, model = _resolve_ai(db, org_id)
    if not api_key:
        raise RuntimeError("API key de Anthropic no configurada")

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Contenido del Trust Portal:\n\n{text[:30000]}",
        }],
    )
    return msg.content[0].text if msg.content else "{}"


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        raw = m.group(0)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return {}


def _apply_fields(supplier: Supplier, extracted: dict) -> list[str]:
    """Vuelca los campos extraidos al modelo Supplier. Devuelve lista de campos actualizados."""
    updated: list[str] = []

    int_fields = {'data_sensitivity', 'data_volume', 'business_criticality', 'geographic_risk'}
    bool_fields = {'is_data_processor', 'processes_personal_data', 'cross_border_transfers', 'is_nis2', 'is_dora', 'is_ens'}
    str_fields = {'name', 'description', 'services', 'category', 'vendor_type',
                  'contact_email', 'website', 'country_code', 'system_access_type', 'notes'}

    for field, value in extracted.items():
        if field not in _EXTRACTABLE_FIELDS:
            continue

        if field == 'certifications':
            if isinstance(value, list) and value:
                current = list(getattr(supplier, 'certifications', None) or [])
                merged = list({*current, *[str(c) for c in value if c]})
                setattr(supplier, 'certifications', merged)
                updated.append('certifications')

        elif field in int_fields:
            try:
                v = int(value)
                if 1 <= v <= 5:
                    setattr(supplier, field, v)
                    updated.append(field)
            except (TypeError, ValueError):
                pass

        elif field in bool_fields:
            if isinstance(value, bool):
                setattr(supplier, field, value)
                updated.append(field)

        elif field in str_fields:
            if value and isinstance(value, str):
                current = getattr(supplier, field, None)
                if not current:
                    setattr(supplier, field, value[:512])
                    updated.append(field)

    return updated


def scrape_and_fill(db: Session, supplier: Supplier) -> dict:
    """Descarga el trust portal, analiza con IA y actualiza la ficha del proveedor.

    Returns dict con: ok, message, updated_fields, extracted (datos crudos IA).
    """
    url = getattr(supplier, 'trust_portal_url', None)
    if not url:
        return {"ok": False, "message": "El proveedor no tiene URL de trust portal configurada.", "updated_fields": []}

    try:
        html = _fetch_html(url)
    except urllib.error.HTTPError as e:
        return {"ok": False, "message": f"Error HTTP {e.code} al acceder a {url}", "updated_fields": []}
    except urllib.error.URLError as e:
        return {"ok": False, "message": f"No se pudo acceder a la URL: {e.reason}", "updated_fields": []}
    except Exception as e:
        return {"ok": False, "message": f"Error descargando trust portal: {str(e)[:200]}", "updated_fields": []}

    text = _html_to_text(html)
    if len(text.strip()) < 80:
        return {"ok": False, "message": "El contenido descargado es insuficiente para el analisis (posiblemente SPA con JS).", "updated_fields": []}

    try:
        raw_response = _call_claude(db, supplier.organization_id, text)
        extracted = _parse_json(raw_response)
    except Exception as e:
        logger.error("trust_portal_scraper[%s]: error Claude: %s", supplier.code, e)
        return {"ok": False, "message": f"Error en el analisis IA: {str(e)[:200]}", "updated_fields": []}

    if not extracted:
        return {"ok": False, "message": "La IA no pudo extraer informacion estructurada.", "updated_fields": []}

    updated_fields = _apply_fields(supplier, extracted)
    supplier.trust_portal_last_scraped_at = datetime.now(timezone.utc)
    supplier.trust_portal_raw_data = extracted

    try:
        db.commit()
        db.refresh(supplier)
        from app.services import tprm_scoring_service
        tprm_scoring_service.recompute_supplier(db, supplier)
    except Exception as e:
        logger.error("trust_portal_scraper[%s]: error guardando: %s", supplier.code, e)
        db.rollback()
        return {"ok": False, "message": "Error al guardar los datos en base de datos.", "updated_fields": []}

    logger.info("trust_portal_scraper[%s]: %d campos actualizados", supplier.code, len(updated_fields))
    return {
        "ok": True,
        "message": f"Analisis completado. {len(updated_fields)} campo(s) actualizado(s).",
        "updated_fields": updated_fields,
        "extracted": extracted,
    }
