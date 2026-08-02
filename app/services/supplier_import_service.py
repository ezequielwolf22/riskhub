"""Importacion masiva de proveedores desde ficheros externos (TPRM §3.1).

Acepta CSV/XLSX/XLS/ODS/TSV/JSON (exportaciones de Excel y herramientas de
gestion como OneTrust, hojas de compras, ERPs, etc.). Reutiliza el lector de
ficheros de smart_import_service y mapea las cabeceras a los campos de Supplier
mediante heuristica multilingue (ES/EN), sin requerir un formato fijo.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.i18n import t as _t
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
    # v6.7.0 — Suppliers Module Review (punto 13)
    "business_importance_level": ["business importance", "importancia negocio",
                                  "importancia de negocio", "business_importance",
                                  "importancia"],
    "security_risk_level": ["security risk", "riesgo seguridad", "riesgo de seguridad",
                            "security_risk", "security risk level"],
    "operating_region": ["operating region", "region", "región", "region operativa",
                         "región operativa", "operating_region", "zona"],
    "review_frequency": ["review frequency", "frecuencia revision",
                         "frecuencia de revisión", "review_frequency", "frecuencia"],
    "next_review_date": ["next review date", "next review", "proxima revision",
                        "próxima revisión", "next_review_date", "fecha revision"],
    "security_status": ["security status", "estado seguridad", "estado de seguridad",
                       "security_status", "supplier status", "estado proveedor",
                       "estado del proveedor"],
    "agreement_status": ["agreement status", "estado acuerdo", "estado del acuerdo",
                        "agreement_status", "contract status", "estado contrato"],
    "owner_email": ["owner", "owner email", "propietario", "responsable interno",
                   "owner_email", "dueño"],
    "backup_owner_email": ["backup owner", "backup", "backup_owner", "backup owner email",
                          "propietario suplente", "responsable suplente"],
}


# Mapas de normalizacion de etiquetas ES/EN a los valores canonicos
_BUSINESS_IMPORTANCE_MAP = {
    "not relevant": "not_relevant", "no relevante": "not_relevant", "not_relevant": "not_relevant",
    "normal": "normal",
    "important": "important", "importante": "important",
    "critical": "critical", "critico": "critical", "crítico": "critical",
}
_SECURITY_RISK_MAP = {
    "very low": "very_low", "muy bajo": "very_low", "very_low": "very_low",
    "low": "low", "bajo": "low",
    "medium": "medium", "medio": "medium", "moderado": "medium",
    "high": "high", "alto": "high",
    "critical": "critical", "critico": "critical", "crítico": "critical",
}
_REVIEW_FREQUENCY_MAP = {
    "monthly": "monthly", "mensual": "monthly",
    "quarterly": "quarterly", "trimestral": "quarterly",
    "semiannual": "semiannual", "semestral": "semiannual", "biannual": "semiannual",
    "annual": "annual", "anual": "annual", "yearly": "annual",
    "biennial": "biennial", "bienal": "biennial",
    "none": "none", "ninguna": "none",
}
_AGREEMENT_STATUS_MAP = {
    "none": "none", "ninguno": "none", "sin acuerdo": "none",
    "draft": "draft", "borrador": "draft",
    "pending signature": "pending_signature", "pendiente firma": "pending_signature",
    "pending_signature": "pending_signature",
    "signed": "signed", "firmado": "signed",
    "expired": "expired", "expirado": "expired", "vencido": "expired",
}


def _map_value(raw: Optional[str], table: dict) -> Optional[str]:
    if not raw:
        return None
    return table.get(_normalize(raw))


def _parse_date(raw: Optional[str]):
    """Parseo tolerante de fechas de revision (ISO, dd/mm/yyyy, dd-mm-yyyy)."""
    if not raw:
        return None
    from datetime import datetime
    raw = str(raw).strip().split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt)
        except (ValueError, TypeError):
            continue
    return None


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


def import_suppliers(content: bytes, filename: str, org_id: int, db: Session, lang: str = "es") -> dict:
    """Importa proveedores desde un fichero. Devuelve resumen del resultado.

    - Deduplica por nombre (case-insensitive) dentro de la organizacion.
    - Calcula tier/inherent/residual risk de cada proveedor creado.
    """
    from app.routers.suppliers import _next_code
    from app.services import tprm_scoring_service

    df = _read_file(content, filename)
    if df is None or df.empty:
        raise ValueError(_t("supplier_import_service.empty_file", lang))

    header_map = _build_header_map(df.columns)
    if "name" not in header_map:
        raise ValueError(_t("supplier_import_service.no_name_column", lang))

    # Nombres existentes en la org para deduplicar
    existing = {
        _normalize(s.name)
        for s in db.query(Supplier.name).filter(Supplier.organization_id == org_id)
    }

    # Mapa email -> user_id para resolver owner / backup owner (punto 13)
    from app.models import User
    user_by_email = {
        _normalize(u.email): u.id
        for u in db.query(User.id, User.email).filter(User.organization_id == org_id)
        if u.email
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
                # v6.7.0 — Suppliers Module Review (punto 13)
                business_importance_level=_map_value(
                    _cell(row, header_map.get("business_importance_level")), _BUSINESS_IMPORTANCE_MAP),
                security_risk_level=_map_value(
                    _cell(row, header_map.get("security_risk_level")), _SECURITY_RISK_MAP),
                operating_region=_cell(row, header_map.get("operating_region")),
                review_frequency=_map_value(
                    _cell(row, header_map.get("review_frequency")), _REVIEW_FREQUENCY_MAP),
                next_assessment_at=_parse_date(_cell(row, header_map.get("next_review_date"))),
                agreement_status=_map_value(
                    _cell(row, header_map.get("agreement_status")), _AGREEMENT_STATUS_MAP),
                owner_id=user_by_email.get(_normalize(_cell(row, header_map.get("owner_email")) or "")),
                backup_owner_id=user_by_email.get(_normalize(_cell(row, header_map.get("backup_owner_email")) or "")),
            )
            # security_status: acepta valor canonico directo si es valido
            _sec_status = _normalize(_cell(row, header_map.get("security_status")) or "").replace(" ", "_")
            from app.services.tprm_classification import SECURITY_STATUSES
            if _sec_status in SECURITY_STATUSES:
                supplier.security_status = _sec_status
            db.add(supplier)
            db.flush()  # asignar id para el scoring
            supplier.code = f"SUP-{supplier.id:04d}"
            tprm_scoring_service.recompute_supplier(db, supplier, commit=False)
            # Si el Excel incluye nivel de riesgo explicito, tiene prioridad sobre el calculado
            if explicit_risk is not None:
                supplier.risk_level = explicit_risk
            created += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(_t("supplier_import_service.row_error", lang, row=idx + 2, error=exc))
            logger.warning("Error importando proveedor fila %s: %s", idx, exc)

    db.commit()
    return {
        "created": created,
        "skipped": skipped,
        "total": int(len(df)),
        "errors": errors[:20],
        "detected_columns": {k: v for k, v in header_map.items()},
    }
