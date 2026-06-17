"""Importacion masiva de proveedores desde ficheros externos (TPRM §3.1).

Acepta CSV/XLSX/XLS/ODS/TSV/JSON (exportaciones de Excel y herramientas de
gestion como OneTrust, hojas de compras, ERPs, etc.). Reutiliza el lector de
ficheros de smart_import_service y mapea las cabeceras a los campos de Supplier
mediante heuristica multilingue (ES/EN), sin requerir un formato fijo.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Supplier
from app.services.smart_import_service import _read_file

logger = logging.getLogger("riskhub.supplier_import")

# Candidatos de cabecera por campo (normalizados: minusculas, sin espacios extra)
_FIELD_ALIASES = {
    "name": ["name", "nombre", "proveedor", "supplier", "vendor", "company",
             "empresa", "razon social", "razón social", "company name", "supplier name"],
    "category": ["category", "categoria", "categoría", "tipo", "type", "sector", "rubro"],
    "contact_name": ["contact", "contacto", "contact name", "responsable",
                     "nombre contacto", "contact person", "nombre de contacto",
                     "nombre_contacto", "responsable contacto"],
    "contact_email": ["email", "correo", "e-mail", "mail", "contact email",
                      "correo electronico", "correo electrónico",
                      "email de contacto", "email contacto", "correo de contacto",
                      "correo_contacto", "email_contacto", "mail contacto"],
    "risk_level": ["nivel de riesgo", "nivel riesgo", "nivel_riesgo", "risk level",
                   "risk_level", "riesgo", "nivel", "criticidad", "risk"],
    "services": ["services", "servicios", "service", "servicio", "descripcion",
                 "descripción", "description", "detalle"],
    "website": ["website", "web", "url", "sitio web", "sitio", "dominio", "domain"],
    "country_code": ["country", "pais", "país", "country_code", "country code", "cc"],
    "tax_id": ["tax_id", "cif", "nif", "vat", "rfc", "tax id", "identificacion fiscal"],
    "annual_spend": ["grand total", "total", "gasto anual", "annual spend", "spend",
                     "facturacion", "facturación", "importe", "monto anual"],
    "category2": [],
}


def _normalize(s: str) -> str:
    return str(s or "").strip().lower()


# Traducciones ES/EN de nivel de riesgo al enum SupplierRisk
_RISK_LEVEL_MAP = {
    "critico": "critical", "crítico": "critical", "critical": "critical", "muy alto": "critical",
    "alto": "high", "high": "high", "elevado": "high",
    "medio": "medium", "medium": "medium", "moderate": "medium", "moderado": "medium",
    "bajo": "low", "low": "low", "reducido": "low",
}


def _parse_risk_level(raw: Optional[str]):
    """Convierte 'Alto'/'High'/etc. al valor del enum SupplierRisk, o None si no reconoce."""
    from app.models import SupplierRisk
    if not raw:
        return None
    key = _normalize(raw)
    mapped = _RISK_LEVEL_MAP.get(key)
    if not mapped:
        return None
    try:
        return SupplierRisk(mapped)
    except ValueError:
        return None


def _build_header_map(columns) -> dict:
    """Devuelve {campo_supplier: nombre_columna_real} segun los alias."""
    norm_to_real = {_normalize(c): c for c in columns}
    mapping = {}
    for field, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            if alias in norm_to_real:
                mapping[field] = norm_to_real[alias]
                break
    return mapping


def _cell(row, col) -> Optional[str]:
    if not col:
        return None
    val = row.get(col)
    if val is None:
        return None
    sval = str(val).strip()
    if not sval or sval.lower() in ("nan", "none", "null"):
        return None
    return sval


def import_suppliers(content: bytes, filename: str, org_id: int, db: Session) -> dict:
    """Importa proveedores desde un fichero. Devuelve resumen del resultado.

    - Deduplica por nombre (case-insensitive) dentro de la organizacion.
    - Calcula tier/inherent/residual risk de cada proveedor creado.
    """
    from app.routers.suppliers import _next_code
    from app.services import tprm_scoring_service

    df = _read_file(content, filename)
    if df is None or df.empty:
        raise ValueError("El fichero esta vacio o no contiene datos legibles.")

    header_map = _build_header_map(df.columns)
    if "name" not in header_map:
        raise ValueError(
            "No se encontro una columna de nombre de proveedor. "
            "Incluye una columna 'name' / 'nombre' / 'proveedor'."
        )

    # Nombres existentes en la org para deduplicar
    existing = {
        _normalize(s.name)
        for s in db.query(Supplier.name).filter(Supplier.organization_id == org_id)
    }

    created, skipped, errors = 0, 0, []
    seen_in_file = set()

    for idx, row in df.iterrows():
        try:
            name = _cell(row, header_map.get("name"))
            if not name:
                skipped += 1
                continue
            key = _normalize(name)
            if key in existing or key in seen_in_file:
                skipped += 1
                continue
            seen_in_file.add(key)

            explicit_risk = _parse_risk_level(_cell(row, header_map.get("risk_level")))

            annual_spend_raw = _cell(row, header_map.get("annual_spend"))
            try:
                annual_spend = float(annual_spend_raw) if annual_spend_raw else None
            except (ValueError, TypeError):
                annual_spend = None

            supplier = Supplier(
                organization_id=org_id,
                code=_next_code(db, org_id),
                name=name,
                category=_cell(row, header_map.get("category")),
                contact_name=_cell(row, header_map.get("contact_name")),
                contact_email=_cell(row, header_map.get("contact_email")),
                services=_cell(row, header_map.get("services")),
                website=_cell(row, header_map.get("website")),
                country_code=(_cell(row, header_map.get("country_code")) or "")[:2] or None,
                tax_id=_cell(row, header_map.get("tax_id")),
                annual_spend=annual_spend,
            )
            db.add(supplier)
            db.flush()  # asignar id para el scoring
            tprm_scoring_service.recompute_supplier(db, supplier, commit=False)
            # Si el Excel incluye nivel de riesgo explicito, tiene prioridad sobre el calculado
            if explicit_risk is not None:
                supplier.risk_level = explicit_risk
            created += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Fila {idx + 2}: {exc}")
            logger.warning("Error importando proveedor fila %s: %s", idx, exc)

    db.commit()
    return {
        "created": created,
        "skipped": skipped,
        "total": int(len(df)),
        "errors": errors[:20],
        "detected_columns": {k: v for k, v in header_map.items()},
    }
