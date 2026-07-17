"""Servicio de analisis de riesgo IA para CVEs.

Workflow por cada par (CVE, Activo):
  1. Comprobar heuristica de coincidencia (CPE vs nombre/descripcion del activo)
  2. Construir contexto: activo, CVE, controles implementados, documentacion RAG
  3. Llamar a Claude para analisis estructurado
  4. Devolver: afecta?, riesgo_inherente, cobertura_controles, riesgo_residual, acciones
"""
import json

from app.i18n import ai_lang_directive, t as _t
import logging
import re
from typing import Optional

logger = logging.getLogger("riskhub.cve_analysis")

_ANALYSIS_SYSTEM = """Eres un experto en gestion de riesgos de seguridad de la informacion (ISO/IEC 27005:2018).
Recibes informacion sobre un activo de una organizacion y una vulnerabilidad CVE.
Debes analizar si la CVE afecta al activo y calcular el riesgo asociado.

Responde SIEMPRE con un JSON valido con esta estructura exacta:
{
  "afecta_activo": true/false,
  "confianza": "alta"|"media"|"baja",
  "justificacion_afectacion": "explicacion breve de por que afecta o no",
  "riesgo_inherente": 1-5,
  "riesgo_inherente_justificacion": "explicacion del nivel inherente",
  "cobertura_controles": "ninguna"|"parcial"|"suficiente",
  "controles_relevantes_detectados": ["lista de controles ISO 27002 activos que mitigan"],
  "riesgo_residual": 1-5,
  "riesgo_residual_justificacion": "explicacion del nivel residual tras controles",
  "acciones_mitigacion": [
    {"accion": "descripcion corta", "control_iso": "cl. X.X", "prioridad": "alta"|"media"|"baja"}
  ],
  "crear_riesgo_recomendado": true/false,
  "amenaza_sugerida": "nombre de amenaza del catalogo ISO 27005 mas apropiada"
}

Escala de riesgo: 1=Muy bajo, 2=Bajo, 3=Medio, 4=Alto, 5=Critico."""


def _build_prompt(cve: dict, asset: dict, controls: list[dict], rag_context: str) -> str:
    """Construye el prompt de usuario para el analisis CVE-Activo."""
    controls_text = ""
    if controls:
        controls_text = "\n\nCONTROLES ISO 27002 ACTUALMENTE IMPLEMENTADOS:\n" + "\n".join(
            f"- {c.get('name', '')} (cl. {c.get('control_code', '')}): {c.get('status', '')} — {c.get('notes', '')}"
            for c in controls[:20]
        )

    rag_text = ""
    if rag_context and rag_context.strip():
        rag_text = f"\n\nCONTEXTO DE DOCUMENTACION INTERNA (SGSI):\n{rag_context[:2000]}"

    products_text = ""
    if cve.get("affected_products"):
        products_text = "\nProductos/Vendors afectados (CPE): " + ", ".join(cve["affected_products"][:15])

    return f"""CVE A ANALIZAR:
ID: {cve['id']}
Descripcion: {cve['description']}
CVSS Score: {cve['cvss_score']} ({cve['cvss_severity']})
Vector CVSS: {cve['cvss_vector']}
Vector de ataque: {cve['cvss_attack_vector']}
Publicada: {cve['published'][:10] if cve.get('published') else 'N/A'}
{products_text}

ACTIVO DE LA ORGANIZACION:
Nombre: {asset.get('name', '')}
Tipo: {asset.get('asset_type', '')}
Descripcion: {asset.get('description', '') or 'Sin descripcion'}
Valoracion CIA — Confidencialidad: {asset.get('confidentiality', '-')}, Integridad: {asset.get('integrity', '-')}, Disponibilidad: {asset.get('availability', '-')}
{controls_text}
{rag_text}

Analiza si esta CVE afecta a este activo especifico y proporciona el analisis de riesgo completo en JSON."""


def analyze_cve_asset(
    cve: dict,
    asset: dict,
    controls: list[dict],
    rag_context: str,
    api_key: str,
    model: str = "claude-haiku-4-5",
    max_tokens: int = 8192,
    lang: str = "es",
) -> dict:
    """Llama a Claude para analizar el impacto de una CVE sobre un activo.

    Retorna el dict de analisis parseado del JSON de respuesta.
    """
    import anthropic

    prompt = _build_prompt(cve, asset, controls, rag_context)

    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=ai_lang_directive(lang) + "\n\n" + _ANALYSIS_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text if resp.content else ""
    except Exception as e:
        logger.error("Error llamando a Claude para analisis CVE %s / activo %s: %s",
                     cve.get("id"), asset.get("name"), e)
        return _fallback_analysis(cve, asset, lang)

    # Parsear JSON de la respuesta
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    logger.warning("No se pudo parsear JSON de analisis CVE %s", cve.get("id"))
    return _fallback_analysis(cve, asset, lang)


def _fallback_analysis(cve: dict, asset: dict, lang: str = "es") -> dict:
    """Analisis de emergencia basado solo en CVSS cuando la IA no esta disponible."""
    from app.services.cve_service import score_to_risk_level
    level = score_to_risk_level(cve.get("cvss_score", 0))
    return {
        "afecta_activo": None,
        "confianza": "baja",
        "justificacion_afectacion": _t("cve_analysis_service.fallback_justification", lang),
        "riesgo_inherente": level,
        "riesgo_inherente_justificacion": _t("cve_analysis_service.fallback_inherent_just", lang, score=f"{cve.get('cvss_score', 0):.1f}", severity=cve.get('cvss_severity', '?')),
        "cobertura_controles": "ninguna",
        "controles_relevantes_detectados": [],
        "riesgo_residual": level,
        "riesgo_residual_justificacion": _t("cve_analysis_service.fallback_residual_just", lang),
        "acciones_mitigacion": [{"accion": _t("cve_analysis_service.fallback_action", lang), "control_iso": "", "prioridad": "alta"}],
        "crear_riesgo_recomendado": level >= 4,
        "amenaza_sugerida": _t("cve_analysis_service.fallback_threat", lang),
        "_fallback": True,
    }


def get_rag_context(cve: dict, asset: dict, organization_id: "int | None" = None) -> str:
    """Obtiene contexto RAG relevante para la combinacion CVE-activo.

    organization_id es obligatorio en entornos multi-tenant para evitar que
    el FTS5 devuelva chunks de otras organizaciones.
    """
    try:
        from app.services.rag_service import search_chunks
        query = f"{cve['id']} {asset.get('name', '')} {' '.join(cve.get('affected_products', [])[:3])}"
        chunks = search_chunks(query, limit=5, organization_id=organization_id)
        if not chunks:
            return ""
        return "\n---\n".join(c.get("chunk_text", "") for c in chunks if c.get("chunk_text"))
    except Exception as e:
        logger.debug("RAG context error: %s", e)
        return ""
