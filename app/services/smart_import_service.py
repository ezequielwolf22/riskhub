"""Smart Import de activos mediante IA.

Acepta cualquier formato de archivo (CSV, XLSX, XLS, JSON, TSV, ODS).
Claude normaliza las columnas al esquema RiskHub y clasifica los asset_type
a partir del contexto, sin requerir ninguna columna específica.

Flujo:
  1. Leer el fichero → DataFrame crudo
  2. Enviar cabeceras + 5 filas de muestra a Claude
  3. Claude devuelve JSON con mapping de columnas y reglas de asset_type
  4. Aplicar el mapping → lista de dicts normalizados
  5. Crear/actualizar activos en BD
"""
from __future__ import annotations

import json
import logging
from io import BytesIO
from typing import Optional

logger = logging.getLogger("riskhub.smart_import")

# Tipos de activo válidos en RiskHub y sus descripciones para orientar a Claude
ASSET_TYPES = {
    "primary_process":      "Proceso de negocio principal (ERP, CRM, proceso critico...)",
    "primary_information":  "Activo de informacion primario (BD de clientes, datos RRHH...)",
    "support_hardware":     "Hardware de soporte (servidor, PC, dispositivo de red, SAI...)",
    "support_software":     "Software de soporte (aplicacion, middleware, SO, herramienta...)",
    "support_network":      "Componente de red (router, firewall, switch, enlace WAN...)",
    "support_personnel":    "Personal (equipo, departamento, proveedor de personas...)",
    "support_site":         "Instalacion fisica (CPD, oficina, edificio...)",
    "support_organization": "Organizacion o estructura (politica, proceso de gestion...)",
}

# Campos RiskHub destino y descripcion para el prompt
RISKHUB_FIELDS = {
    "name":                  "Nombre del activo (obligatorio)",
    "description":           "Descripcion del activo",
    "category":              "Categoria libre (ej: ERP, Cloud, Infraestructura)",
    "location":              "Ubicacion fisica o logica",
    "business_process":      "Proceso de negocio al que da soporte",
    "classification":        "Clasificacion de informacion (publico/interno/confidencial/secreto)",
    "value_confidentiality": "Valor de confidencialidad 0-4",
    "value_integrity":       "Valor de integridad 0-4",
    "value_availability":    "Valor de disponibilidad 0-4",
    "value_authenticity":    "Valor de autenticidad 0-4",
    "value_accountability":  "Valor de trazabilidad 0-4",
    "software_tags":         "Etiquetas de software separadas por coma (para correlacion CVE)",
}


def _read_file(content: bytes, filename: str):
    """Lee cualquier formato y devuelve un DataFrame de pandas."""
    import pandas as pd

    fname = filename.lower()
    try:
        if fname.endswith(".csv"):
            # Intentar detectar separador automáticamente
            for sep in [",", ";", "\t", "|"]:
                try:
                    df = pd.read_csv(BytesIO(content), sep=sep, dtype=str)
                    if len(df.columns) > 1:
                        return df
                except Exception:
                    pass
            return pd.read_csv(BytesIO(content), dtype=str)

        elif fname.endswith((".xlsx", ".xls", ".ods")):
            return pd.read_excel(BytesIO(content), dtype=str)

        elif fname.endswith(".tsv"):
            return pd.read_csv(BytesIO(content), sep="\t", dtype=str)

        elif fname.endswith(".json"):
            import json as _json
            data = _json.loads(content.decode("utf-8", errors="replace"))
            if isinstance(data, list):
                return pd.DataFrame(data)
            elif isinstance(data, dict):
                # Intentar aplanar el dict si tiene una clave que es lista
                for v in data.values():
                    if isinstance(v, list) and v:
                        return pd.DataFrame(v)
            return pd.DataFrame([data])

        else:
            # Fallback: intentar CSV con detección automática
            return pd.read_csv(BytesIO(content), dtype=str, sep=None, engine="python")

    except Exception as exc:
        raise ValueError(f"No se pudo leer el fichero '{filename}': {exc}") from exc


def _build_mapping_prompt(columns: list[str], sample_rows: list[dict]) -> str:
    """Construye el prompt para que Claude mapee las columnas."""
    fields_desc = "\n".join(f"  - {k}: {v}" for k, v in RISKHUB_FIELDS.items())
    types_desc = "\n".join(f"  - {k}: {v}" for k, v in ASSET_TYPES.items())
    sample_json = json.dumps(sample_rows[:5], ensure_ascii=False, indent=2)

    return f"""Eres un experto en gestion de activos ISO 27005. Debes mapear columnas de un inventario externo al esquema de RiskHub.

COLUMNAS DEL FICHERO:
{json.dumps(columns, ensure_ascii=False)}

MUESTRA DE DATOS (hasta 5 filas):
{sample_json}

CAMPOS DESTINO DE RISKHUB:
{fields_desc}

TIPOS DE ACTIVO RISKHUB (campo "asset_type"):
{types_desc}

INSTRUCCIONES:
1. Crea un mapping de cada columna del fichero al campo RiskHub mas apropiado.
2. Si ninguna columna coincide con "name", usa la columna mas descriptiva del activo como nombre.
3. Si no hay columna de "asset_type", crea reglas para inferirlo del contenido.
4. Para value_* (0-4), si hay valores numericos mapealos; si hay texto (Alto/Medio/Bajo) incluye reglas de conversion.
5. Ignora columnas que no tienen equivalente RiskHub (devuelvelas en "ignored_columns").

Responde UNICAMENTE con JSON valido (sin markdown), exactamente con esta estructura:
{{
  "column_mapping": {{
    "NombreColumnaOriginal": "campo_riskhub_o_null"
  }},
  "asset_type_source_column": "columna_que_indica_el_tipo_o_null",
  "asset_type_rules": {{
    "valor_original": "tipo_riskhub"
  }},
  "name_column": "columna_a_usar_como_nombre",
  "value_text_rules": {{
    "Alto": 3, "High": 3, "Medio": 2, "Medium": 2, "Bajo": 1, "Low": 1,
    "Critico": 4, "Critical": 4, "Muy bajo": 0, "Very Low": 0
  }},
  "ignored_columns": ["col1", "col2"],
  "notes": "breve explicacion del mapeo realizado"
}}"""


def _call_claude(prompt: str, api_key: str, model: str) -> dict:
    """Llama a Claude y parsea la respuesta JSON."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    # Extraer JSON si viene envuelto en markdown
    if "```" in text:
        for part in text.split("```"):
            stripped = part.lstrip("json").strip()
            if stripped.startswith("{"):
                text = stripped
                break
    return json.loads(text)


def _apply_mapping(df, mapping: dict) -> list[dict]:
    """Aplica el mapping de Claude a cada fila del DataFrame."""
    import pandas as pd

    col_map = mapping.get("column_mapping", {})
    type_col = mapping.get("asset_type_source_column")
    type_rules = {str(k).lower(): v for k, v in mapping.get("asset_type_rules", {}).items()}
    name_col = mapping.get("name_column")
    value_rules = {str(k).lower(): int(v) for k, v in mapping.get("value_text_rules", {}).items()}

    valid_types = set(ASSET_TYPES.keys())
    rows = []

    for _, row in df.iterrows():
        asset = {}

        # Aplicar mapping de columnas
        for src_col, dst_field in col_map.items():
            if not dst_field or dst_field == "null" or src_col not in df.columns:
                continue
            val = row.get(src_col)
            if pd.isna(val) or str(val).strip() in ("", "nan", "None", "NaN"):
                continue
            val = str(val).strip()

            if dst_field.startswith("value_"):
                # Intentar convertir a int; si es texto, usar las reglas
                try:
                    num = float(val.replace(",", "."))
                    asset[dst_field] = max(0, min(4, int(round(num))))
                except (ValueError, TypeError):
                    mapped = value_rules.get(val.lower())
                    if mapped is not None:
                        asset[dst_field] = mapped
            else:
                asset[dst_field] = val

        # Nombre: asegurar que existe
        if "name" not in asset and name_col and name_col in df.columns:
            raw_name = str(row.get(name_col, "")).strip()
            if raw_name and raw_name.lower() not in ("nan", "none", ""):
                asset["name"] = raw_name

        if not asset.get("name"):
            # Último recurso: primera columna no vacía
            for col in df.columns:
                val = str(row.get(col, "")).strip()
                if val and val.lower() not in ("nan", "none", ""):
                    asset["name"] = val
                    break

        if not asset.get("name"):
            continue  # fila sin nombre útil — saltar

        # Inferir asset_type
        if "asset_type" not in asset:
            inferred = None
            if type_col and type_col in df.columns:
                raw_type = str(row.get(type_col, "")).strip().lower()
                inferred = type_rules.get(raw_type)
                if not inferred:
                    # Búsqueda aproximada en las reglas
                    for rule_key, rule_val in type_rules.items():
                        if rule_key in raw_type or raw_type in rule_key:
                            inferred = rule_val
                            break

            if not inferred:
                # Fallback heurístico por palabras clave del nombre
                name_lower = asset.get("name", "").lower()
                cat_lower = asset.get("category", "").lower()
                combined = name_lower + " " + cat_lower
                if any(k in combined for k in ("servidor", "server", "host", "vm", "virtual machine", "desktop", "pc")):
                    inferred = "support_hardware"
                elif any(k in combined for k in ("aplicacion", "application", "app", "software", "sistema", "system", "plataforma", "platform", "erp", "crm", "saas")):
                    inferred = "support_software"
                elif any(k in combined for k in ("red", "network", "router", "firewall", "switch", "wan", "lan", "vpn")):
                    inferred = "support_network"
                elif any(k in combined for k in ("proceso", "process", "workflow", "negocio", "business")):
                    inferred = "primary_process"
                elif any(k in combined for k in ("datos", "data", "bbdd", "database", "informacion", "information")):
                    inferred = "primary_information"
                elif any(k in combined for k in ("cpe", "datacenter", "cpd", "oficina", "office", "instalacion", "site")):
                    inferred = "support_site"
                elif any(k in combined for k in ("persona", "people", "empleado", "employee", "usuario", "user", "staff")):
                    inferred = "support_personnel"
                else:
                    inferred = "support_software"  # más común en exports CMDB

            if inferred and inferred in valid_types:
                asset["asset_type"] = inferred
            else:
                asset["asset_type"] = "support_software"

        elif asset["asset_type"] not in valid_types:
            asset["asset_type"] = "support_software"

        rows.append(asset)

    return rows


def smart_import(
    content: bytes,
    filename: str,
    org_id: int,
    db,
    api_key: Optional[str],
    model: str = "claude-haiku-4-5",
) -> dict:
    """Importa activos desde cualquier formato usando IA para normalizar.

    Returns: dict con created, updated, skipped, errors, mapping_notes
    """
    from app.models import Asset, AssetType
    from app.routers.assets import _next_code

    # 1. Leer fichero
    df = _read_file(content, filename)
    if df.empty:
        raise ValueError("El fichero está vacío o no contiene datos legibles.")

    # Limpiar columnas: quitar espacios, NaN en cabeceras
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all")

    columns = list(df.columns)
    sample = [
        {col: (str(val) if not __import__("pandas").isna(val) else "") for col, val in row.items()}
        for _, row in df.head(5).iterrows()
    ]

    mapping_notes = "Sin informacion de mapeo (modo sin IA)"
    normalized_rows = []

    # 2. Normalizar con Claude si hay API key
    if api_key:
        try:
            prompt = _build_mapping_prompt(columns, sample)
            mapping = _call_claude(prompt, api_key, model)
            mapping_notes = mapping.get("notes", "Mapeo completado")
            logger.info("Smart import mapping: %s", mapping_notes)
            normalized_rows = _apply_mapping(df, mapping)
        except Exception as exc:
            logger.warning("Claude mapping failed, falling back to heuristic: %s", exc)
            mapping_notes = f"IA no disponible, usando heuristica: {exc}"
            # Fallback heurístico sin IA
            mapping = _build_heuristic_mapping(columns)
            normalized_rows = _apply_mapping(df, mapping)
    else:
        # Sin API key: mapeo heurístico puro
        mapping = _build_heuristic_mapping(columns)
        normalized_rows = _apply_mapping(df, mapping)
        mapping_notes = "Mapeo heuristico (sin IA configurada)"

    # 3. Crear/actualizar activos en BD
    created = 0
    updated = 0
    skipped = 0
    errors = []

    for idx, row in enumerate(normalized_rows):
        try:
            name = row.get("name", "").strip()
            if not name:
                skipped += 1
                continue

            atype_raw = row.get("asset_type", "support_software")
            try:
                atype = AssetType(atype_raw)
            except ValueError:
                atype = AssetType.SUPPORT_SOFTWARE

            payload = {
                "name": name,
                "asset_type": atype,
            }
            for field in ("description", "category", "location", "business_process",
                          "classification", "value_confidentiality", "value_integrity",
                          "value_availability", "value_authenticity", "value_accountability"):
                if field in row and row[field] is not None:
                    payload[field] = row[field]

            # software_tags: convertir string CSV a lista
            if "software_tags" in row and row["software_tags"]:
                tags = [t.strip() for t in str(row["software_tags"]).split(",") if t.strip()]
                payload["software_tags"] = tags

            # Buscar por nombre dentro de la org (sin código fijo)
            existing = (
                db.query(Asset)
                .filter(
                    Asset.organization_id == org_id,
                    Asset.name == name,
                )
                .first()
            )

            if existing:
                for k, v in payload.items():
                    setattr(existing, k, v)
                existing.ai_risk_status = None
                existing.ai_risk_summary = None
                updated += 1
                db.flush()
            else:
                code = _next_code(db, org_id)
                a = Asset(code=code, organization_id=org_id, **payload)
                db.add(a)
                db.flush()
                created += 1

        except Exception as exc:
            skipped += 1
            errors.append(f"Fila {idx + 2}: {exc}")

    db.commit()

    return {
        "total": len(normalized_rows),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "mapping_notes": mapping_notes,
        "columns_detected": columns,
    }


def _build_heuristic_mapping(columns: list[str]) -> dict:
    """Mapeo heurístico por similitud de nombre de columna cuando Claude no está disponible."""
    NAME_HINTS = ["name", "nombre", "asset", "activo", "title", "titulo", "item", "recurso", "resource", "hostname", "host", "application", "aplicacion", "app name", "display name"]
    DESC_HINTS = ["description", "descripcion", "desc", "details", "detalle", "detail", "notes", "notas", "comment", "comentario"]
    CAT_HINTS = ["category", "categoria", "type", "tipo", "class", "clase", "kind", "grupo", "group", "tag", "tags", "technology", "tecnologia", "tier"]
    LOC_HINTS = ["location", "ubicacion", "site", "sitio", "datacenter", "region", "country", "pais", "city", "ciudad"]
    PROC_HINTS = ["process", "proceso", "business process", "proceso negocio", "department", "departamento", "owner", "propietario", "responsible"]
    CLASS_HINTS = ["classification", "clasificacion", "sensitivity", "sensibilidad", "confidentiality level", "data class"]
    TYPE_HINTS = ["asset type", "tipo activo", "category", "categoria", "type", "tipo", "clase", "kind"]
    SW_HINTS = ["software", "application", "app", "product", "producto", "vendor", "fabricante", "solution"]

    col_map = {}
    asset_type_col = None
    name_col = None

    col_lower = {c: c.lower() for c in columns}

    def _best(hints, already_mapped):
        for hint in hints:
            for col, lower in col_lower.items():
                if col in already_mapped:
                    continue
                if hint == lower or hint in lower or lower in hint:
                    return col
        return None

    mapped = set()

    name_col = _best(NAME_HINTS, mapped) or (columns[0] if columns else "name")
    if name_col:
        col_map[name_col] = "name"
        mapped.add(name_col)

    desc = _best(DESC_HINTS, mapped)
    if desc:
        col_map[desc] = "description"
        mapped.add(desc)

    cat = _best(CAT_HINTS, mapped)
    if cat:
        col_map[cat] = "category"
        mapped.add(cat)
        asset_type_col = cat  # usar category como fuente de asset_type también

    loc = _best(LOC_HINTS, mapped)
    if loc:
        col_map[loc] = "location"
        mapped.add(loc)

    proc = _best(PROC_HINTS, mapped)
    if proc:
        col_map[proc] = "business_process"
        mapped.add(proc)

    cls = _best(CLASS_HINTS, mapped)
    if cls:
        col_map[cls] = "classification"
        mapped.add(cls)

    type_col = _best(TYPE_HINTS, mapped)
    if type_col:
        col_map[type_col] = "asset_type"
        asset_type_col = type_col
        mapped.add(type_col)

    sw = _best(SW_HINTS, mapped)
    if sw:
        col_map[sw] = "software_tags"
        mapped.add(sw)

    # Marcar el resto como ignorados
    for col in columns:
        if col not in col_map:
            col_map[col] = None

    return {
        "column_mapping": col_map,
        "asset_type_source_column": asset_type_col,
        "asset_type_rules": {},
        "name_column": name_col,
        "value_text_rules": {
            "Alto": 3, "High": 3, "Medio": 2, "Medium": 2,
            "Bajo": 1, "Low": 1, "Critico": 4, "Critical": 4,
            "Muy bajo": 0, "Very Low": 0,
        },
        "ignored_columns": [c for c, v in col_map.items() if v is None],
        "notes": "Mapeo heuristico por nombre de columna",
    }
