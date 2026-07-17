"""Analisis automatico de documentos adjuntos a proveedores mediante IA.

Lee el contenido del documento (PDF/DOCX/TXT/CSV/XLSX) y usa Claude para
inferir los campos de la ficha del proveedor, incluyendo SLAs y contactos.
Solo sobreescribe campos vacios; fusiona SLAs y contactos con los existentes.
"""
import json
import logging

from app.i18n import t as _t
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Supplier

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Eres un experto en ciberseguridad y TPRM (Third Party Risk Management) segun ISO/IEC 27005.

Analiza el contenido de un documento de un proveedor (contrato, politica de seguridad, acuerdo de nivel de servicio, certificacion, propuesta comercial, etc.) y extrae informacion estructurada para la ficha GRC del proveedor.

Devuelve SOLO un objeto JSON valido con los campos que puedas inferir con ALTA CONFIANZA. Omite completamente los campos sobre los que no haya informacion clara en el documento.

{
  "name": "Nombre comercial del proveedor",
  "description": "Descripcion del proveedor y sus servicios (max 500 chars)",
  "services": "Servicios ofrecidos segun el documento (max 300 chars)",
  "category": "Software | Hardware | Servicios Profesionales | Cloud | Consultoria | Subcontratista | etc.",
  "vendor_type": "technology | cloud_provider | professional_services | consultancy | hardware | subcontractor | other",
  "contact_name": "Nombre del contacto principal del proveedor que aparezca en el documento",
  "contact_email": "Email del contacto principal",
  "cc_email": "Email secundario de copia o responsable de cuenta",
  "website": "URL principal del proveedor",
  "country_code": "Codigo ISO 3166-1 alpha-2 del pais del proveedor (ej: US, ES, DE, FR)",
  "certifications": ["lista de certificaciones mencionadas: ISO27001, SOC2, SOC3, CSA_STAR, PCI_DSS, FedRAMP, GDPR, HIPAA, ISO9001, ISAE3402, TISAX"],
  "contract_ref": "Numero o referencia del contrato si aparece explicitamente",
  "contract_expiry": "Fecha de vencimiento del contrato en formato YYYY-MM-DD",
  "location": "Ciudad y pais de la sede del proveedor (ej: Madrid, ES)",
  "department": "Departamento interno responsable segun el documento (ej: TI, Legal, Compras)",
  "is_data_processor": true/false (true si el documento menciona tratamiento de datos por cuenta del cliente),
  "processes_personal_data": true/false (true si el proveedor trata datos personales),
  "cross_border_transfers": true/false (true si hay transferencias internacionales de datos),
  "is_critical": true/false (true si el proveedor se describe como critico o esencial),
  "is_nis2": true/false (true si el documento menciona NIS2 o el proveedor es entidad esencial/importante),
  "is_dora": true/false (true si el documento menciona DORA o aplica a entidades financieras),
  "is_ens": true/false (true si el documento menciona ENS o es proveedor de la Administracion Publica espanola),
  "data_sensitivity": 1-5,
  "data_volume": 1-5,
  "system_access_type": "none | api_only | saas | paas | iaas | on_prem | read_write | admin_to_our_systems",
  "business_criticality": 1-5,
  "geographic_risk": 1-5,
  "business_importance": 1-5,
  "notes": "Resumen de aspectos clave del documento relevantes para la gestion del riesgo (max 600 chars)",
  "additional_contacts": [
    {
      "name": "Nombre completo del contacto",
      "email": "email@proveedor.com",
      "role": "Cargo o funcion (ej: Account Manager, Soporte Tecnico, DPO, Legal)",
      "phone": "+34 xxx xxx xxx"
    }
  ],
  "slas": [
    {
      "name": "Nombre descriptivo del SLA (ej: Disponibilidad del servicio, Tiempo de respuesta soporte P1)",
      "metric": "Valor objetivo cuantificable (ej: 99.9% uptime mensual, < 4h respuesta, RTO 2h)",
      "category": "availability | support | security | performance | recovery | other",
      "description": "Descripcion breve del alcance de este SLA"
    }
  ]
}

Escalas numericas (1-5):
- data_sensitivity: 1=datos publicos, 3=datos de negocio confidenciales, 5=datos criticos o personales sensibles
- data_volume: 1=volumen minimo, 3=moderado, 5=masivo (millones de registros)
- business_criticality: 1=no critico, 3=importante para el negocio, 5=infraestructura critica / imposible sustituir
- geographic_risk: 1=UE/EEE/US/AU/UK, 3=otros paises con acuerdos, 5=jurisdicciones de alto riesgo o sin transferencia adecuada
- business_importance: 1=poco relevante, 3=importante, 5=critico para continuidad del negocio

Para los SLAs: extrae TODOS los acuerdos de nivel de servicio que encuentres (uptime, tiempos de respuesta de soporte por prioridad, RTO/RPO de recuperacion, SLA de seguridad/incidentes, tiempos de parche, etc.).
Para los contactos adicionales: extrae todos los contactos del proveedor que aparezcan (comercial, soporte, seguridad/CISO, legal/DPO, gestor de cuenta, etc.).

Sin texto adicional. Sin markdown. SOLO el JSON."""


def _resolve_ai(db: Session, org_id: Optional[int]) -> tuple[str, str]:
    from app.services.iso_clause_extractor import _resolve_ai_config
    api_key, model, _anon = _resolve_ai_config(db, org_id)
    return api_key, model


def _read_doc_bytes(stored_name: str) -> bytes:
    from app.services.document_service import decrypt_doc
    for base in ("/srv/data/documents", "data/documents"):
        p = Path(base) / stored_name
        if p.exists():
            raw = p.read_bytes()
            return decrypt_doc(raw)
    raise FileNotFoundError(f"Documento no encontrado en disco: {stored_name}")


def _extract_text(data: bytes, filename: str) -> str:
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext == ".pdf":
        from app.services.document_service import _extract_text_pdf
        return _extract_text_pdf(data)
    if ext in (".docx", ".doc"):
        from app.services.document_service import _extract_text_docx
        return _extract_text_docx(data)
    if ext in (".xlsx", ".xls"):
        return _extract_text_xlsx(data)
    from app.services.document_service import _extract_text_plain
    return _extract_text_plain(data)


def _extract_text_xlsx(data: bytes) -> str:
    try:
        import io
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        parts = []
        for ws in wb.worksheets:
            parts.append(f"[Hoja: {ws.title}]")
            for row in ws.iter_rows(values_only=True):
                row_text = " | ".join(str(c) for c in row if c is not None)
                if row_text.strip():
                    parts.append(row_text)
        wb.close()
        return "\n".join(parts)
    except ImportError:
        return ""
    except Exception as e:
        logger.warning("Error extrayendo XLSX: %s", e)
        return ""


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
            "content": f"Contenido del documento del proveedor:\n\n{text[:40000]}",
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


def _sla_id() -> str:
    import random
    ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    rand = random.randint(1000, 9999)
    return f"sla_{ts}_{rand}"


def _contact_id() -> str:
    import random
    ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    rand = random.randint(1000, 9999)
    return f"cnt_{ts}_{rand}"


_SLA_CATEGORIES = frozenset({'availability', 'support', 'security', 'performance', 'recovery', 'other'})

_BOOL_FIELDS = frozenset({
    'is_data_processor', 'processes_personal_data', 'cross_border_transfers',
    'is_nis2', 'is_dora', 'is_ens', 'is_critical',
})
_INT_FIELDS = frozenset({
    'data_sensitivity', 'data_volume', 'business_criticality', 'geographic_risk', 'business_importance',
})
_STR_FIELDS = frozenset({
    'name', 'description', 'services', 'category', 'vendor_type',
    'contact_name', 'contact_email', 'cc_email',
    'website', 'country_code', 'system_access_type', 'notes',
    'contract_ref', 'location', 'department',
})


def _apply_fields(supplier: Supplier, extracted: dict) -> list[str]:
    """Vuelca los campos extraidos al modelo Supplier.

    - Campos escalares: solo rellena si estan vacios en la ficha.
    - SLAs: fusiona evitando duplicados por nombre.
    - Contactos adicionales: fusiona evitando duplicados por email.
    - Certificaciones: union de sets.
    Devuelve lista de nombres de campos actualizados.
    """
    updated: list[str] = []

    for field, value in extracted.items():

        if field == 'slas':
            if not isinstance(value, list) or not value:
                continue
            existing = list(getattr(supplier, 'slas', None) or [])
            existing_names = {
                (s.get('name') or '').strip().lower()
                for s in existing if isinstance(s, dict)
            }
            new_slas = []
            for sla in value:
                if not isinstance(sla, dict) or not sla.get('name'):
                    continue
                name_key = sla['name'].strip().lower()
                if name_key in existing_names:
                    continue
                cat = sla.get('category', 'other')
                new_slas.append({
                    'id': _sla_id(),
                    'name': str(sla['name'])[:200],
                    'metric': str(sla.get('metric') or '')[:200],
                    'category': cat if cat in _SLA_CATEGORIES else 'other',
                    'description': str(sla.get('description') or '')[:300],
                })
                existing_names.add(name_key)
            if new_slas:
                setattr(supplier, 'slas', existing + new_slas)
                updated.append('slas')

        elif field == 'additional_contacts':
            if not isinstance(value, list) or not value:
                continue
            existing = list(getattr(supplier, 'additional_contacts', None) or [])
            existing_emails = {
                (c.get('email') or '').strip().lower()
                for c in existing if isinstance(c, dict)
            }
            new_contacts = []
            for c in value:
                if not isinstance(c, dict):
                    continue
                email = (c.get('email') or '').strip().lower()
                if email and email in existing_emails:
                    continue
                new_contacts.append({
                    'id': _contact_id(),
                    'name': str(c.get('name') or '')[:200],
                    'email': str(c.get('email') or '')[:200],
                    'role': str(c.get('role') or '')[:200],
                    'phone': str(c.get('phone') or '')[:50],
                })
                if email:
                    existing_emails.add(email)
            if new_contacts:
                setattr(supplier, 'additional_contacts', existing + new_contacts)
                updated.append('additional_contacts')

        elif field == 'certifications':
            if not isinstance(value, list) or not value:
                continue
            current = list(getattr(supplier, 'certifications', None) or [])
            merged = list({*current, *[str(c) for c in value if c]})
            if merged != current:
                setattr(supplier, 'certifications', merged)
                updated.append('certifications')

        elif field == 'contract_expiry':
            if not value or not isinstance(value, str):
                continue
            if getattr(supplier, 'contract_expiry', None):
                continue
            try:
                from datetime import date
                parsed = date.fromisoformat(str(value)[:10])
                dt = datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
                setattr(supplier, 'contract_expiry', dt)
                updated.append('contract_expiry')
            except (ValueError, TypeError):
                pass

        elif field in _INT_FIELDS:
            try:
                v = int(value)
                if 1 <= v <= 5:
                    setattr(supplier, field, v)
                    updated.append(field)
            except (TypeError, ValueError):
                pass

        elif field in _BOOL_FIELDS:
            if isinstance(value, bool):
                setattr(supplier, field, value)
                updated.append(field)

        elif field in _STR_FIELDS:
            if not value or not isinstance(value, str):
                continue
            current = getattr(supplier, field, None)
            if not current:
                setattr(supplier, field, value[:512])
                updated.append(field)

    return updated


def analyze_document(db: Session, supplier: Supplier, stored_name: str, filename: str, lang: str = "es") -> dict:
    """Lee el documento, analiza con IA y actualiza la ficha del proveedor.

    Returns dict: ok, message, updated_fields, extracted.
    """
    try:
        raw_bytes = _read_doc_bytes(stored_name)
    except FileNotFoundError as e:
        return {"ok": False, "message": str(e), "updated_fields": []}
    except Exception as e:
        return {"ok": False, "message": _t("supplier_document_analyzer.read_error", lang, error=str(e)[:200]), "updated_fields": []}

    try:
        text = _extract_text(raw_bytes, filename)
    except Exception as e:
        return {"ok": False, "message": _t("supplier_document_analyzer.extract_error", lang, error=str(e)[:200]), "updated_fields": []}

    if len(text.strip()) < 30:
        return {"ok": False, "message": _t("supplier_document_analyzer.no_text", lang), "updated_fields": []}

    try:
        raw_response = _call_claude(db, supplier.organization_id, text)
        extracted = _parse_json(raw_response)
    except Exception as e:
        logger.error("supplier_document_analyzer[%s]: Claude error: %s", supplier.code, e)
        return {"ok": False, "message": _t("supplier_document_analyzer.ai_error", lang, error=str(e)[:200]), "updated_fields": []}

    if not extracted:
        return {"ok": False, "message": _t("supplier_document_analyzer.no_structured", lang), "updated_fields": []}

    updated_fields = _apply_fields(supplier, extracted)

    try:
        db.commit()
        db.refresh(supplier)
        from app.services import tprm_scoring_service
        tprm_scoring_service.recompute_supplier(db, supplier)
    except Exception as e:
        logger.error("supplier_document_analyzer[%s]: save error: %s", supplier.code, e)
        db.rollback()
        return {"ok": False, "message": _t("supplier_document_analyzer.db_error", lang), "updated_fields": []}

    logger.info("supplier_document_analyzer[%s]: %d campos actualizados desde '%s'",
                supplier.code, len(updated_fields), filename)
    return {
        "ok": True,
        "message": _t("supplier_document_analyzer.success", lang, count=len(updated_fields)),
        "updated_fields": updated_fields,
        "extracted": extracted,
    }
