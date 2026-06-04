"""Analisis automatico de riesgos por activo.

Flujo para cada activo:
  1. Filtrar amenazas del catalogo aplicables al tipo de activo.
  2. Filtrar vulnerabilidades relacionadas con esas amenazas.
  3. Obtener ControlImplementations activas de la org.
  4. Llamar al agente IA con el contexto completo para obtener:
       - Que amenazas aplican al activo concreto
       - Likelihood e consequence inherentes (0-4 escala ISO 27005)
       - Vulnerabilidades especificas que contribuyen al riesgo
       - Controles que mitigan el riesgo y su contribucion (0-1)
       - Likelihood/consequence residuales
  5. Crear o actualizar registros Risk en BD.
  6. Vincular vulnerabilidades y controles al riesgo.
  7. Calcular niveles usando risk_engine (matriz 5x5 ISO 27005 Annex E.2).

Metodologia: ISO/IEC 27005:2018 + MAGERIT v3.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import (
    AiCallLog, AiConfig, Asset,
    Control, ControlImplementation, ControlStatus,
    Risk, RiskContext, RiskStatus, TreatmentOption,
    Threat, Vulnerability,
    User, UserRole,
)
from app.services.risk_engine import calc_level, calc_residual, clamp

logger = logging.getLogger(__name__)

# ---------- Tipos de activo → claves de catalogo ----------

# Mapeo entre AssetType y los valores que pueden aparecer en Threat.typical_assets
_ASSET_TYPE_KEYS: dict[str, list[str]] = {
    "primary_process":      ["primary_process", "process", "primary"],
    "primary_information":  ["primary_information", "information", "data", "primary"],
    "support_hardware":     ["support_hardware", "hardware", "server", "device"],
    "support_software":     ["support_software", "software", "application", "app"],
    "support_network":      ["support_network", "network", "communication"],
    "support_personnel":    ["support_personnel", "personnel", "people", "human"],
    "support_site":         ["support_site", "site", "physical", "facility"],
    "support_organization": ["support_organization", "organization", "management"],
}

# ---------- Prompt del sistema ----------

_RISK_SYSTEM_PROMPT = """Eres un experto en analisis de riesgos ISO/IEC 27005:2018, MAGERIT v3 y ENS.

Para el activo descrito, devuelve:
1. Valoracion CIA segun ENS/ISO 27005 (5 dimensiones)
2. Analisis completo de amenazas aplicables

VALORACION CIA — escala 0-4 (0=nulo, 4=critico):
- c (Confidencialidad): dano por revelacion no autorizada
- i (Integridad): dano por modificacion o corrupcion
- a (Disponibilidad): dano por perdida de acceso al activo
- au (Autenticidad ENS): necesidad de verificar identidad
- ac (Trazabilidad ENS): necesidad de audit trail y no-repudio

Escala de valoracion riesgos:
- Likelihood: 0=muy improbable, 1=improbable, 2=posible, 3=probable, 4=muy probable
- Consequence: 0=insignificante, 1=menor, 2=moderado, 3=mayor, 4=critico

Para cada control, estima contribution (0.0-1.0) y aplica la reduccion al residual.

Devuelve UNICAMENTE JSON con esta estructura:
{
  "cia": {"c": <1-4>, "i": <1-4>, "a": <1-4>, "au": <0-4>, "ac": <0-4>},
  "risks": [
    {
      "threat_code": "<codigo>",
      "applies": true,
      "inherent_likelihood": <0-4>,
      "inherent_consequence": <0-4>,
      "rationale": "<max 150 palabras>",
      "consequence_description": "<impacto concreto>",
      "vulnerability_codes": ["<codigo>", ...],
      "control_contributions": [{"impl_id": <id>, "contribution": <0.0-1.0>}],
      "residual_likelihood": <0-4>,
      "residual_consequence": <0-4>,
      "treatment_option": "<modification|retention|avoidance|sharing>"
    }
  ]
}

REGLAS:
- cia: NUNCA dejes los 5 valores a 0. Estima segun el tipo y descripcion del activo.
- risks: solo amenazas donde applies=true e inherente >= 1 en alguna dimension.
- Usa codigos exactos del catalogo.
- treatment_option: modification=hay controles que reducen; retention=riesgo bajo aceptable;
  avoidance=riesgo inaceptable; sharing=transferible.
"""


# ---------- Helpers ----------

def _get_api_key(db: Session, organization_id: int | None) -> str | None:
    cfg = db.query(AiConfig).filter_by(organization_id=organization_id).first()
    if cfg and cfg.api_key_encrypted:
        try:
            from cryptography.fernet import Fernet
            from app.services.document_service import _fernet_key
            return Fernet(_fernet_key()).decrypt(cfg.api_key_encrypted.encode()).decode()
        except Exception:
            pass
    from app.config import settings
    return settings.anthropic_api_key or None


def _get_model(db: Session, organization_id: int | None) -> str:
    cfg = db.query(AiConfig).filter_by(organization_id=organization_id).first()
    return cfg.model if cfg and cfg.model else "claude-opus-4-5"


def _org_owner_id(db: Session, org_id: int | None) -> int | None:
    u = db.query(User).filter_by(organization_id=org_id, is_active=True).order_by(User.id).first()
    return u.id if u else None


def _strip_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```", 2)
        inner = parts[1] if len(parts) > 1 else raw
        if inner.startswith("json"):
            inner = inner[4:]
        raw = inner.rsplit("```", 1)[0].strip()
    return raw


def _get_active_catalogs(db: Session, org_id: int) -> list[str]:
    """Devuelve los catalogos activos de la org o todos si no hay preferencia."""
    ctx = db.query(RiskContext).filter_by(organization_id=org_id).first()
    if ctx and ctx.active_threat_catalogs:
        return ctx.active_threat_catalogs
    return ["iso27005", "magerit", "custom"]


def _threats_for_asset(db: Session, asset_type: str, org_id: int | None = None) -> list[Threat]:
    """Filtra amenazas del catalogo aplicables al tipo de activo, respetando catalogos activos."""
    keys = _ASSET_TYPE_KEYS.get(asset_type, [asset_type])
    threat_q = db.query(Threat)
    if org_id:
        active_catalogs = _get_active_catalogs(db, org_id)
        threat_q = threat_q.filter(Threat.catalog.in_(active_catalogs))
    all_threats = threat_q.all()
    result = []
    for t in all_threats:
        ta = t.typical_assets or []
        if isinstance(ta, str):
            try:
                ta = json.loads(ta)
            except Exception:
                ta = [ta]
        ta_lower = [x.lower() for x in ta]
        if any(k in ta_lower or any(k in s for s in ta_lower) for k in keys):
            result.append(t)
    # Si no hay coincidencias exactas, devolver todas las amenazas (mejor tenerlas todas que ninguna)
    return result if result else all_threats


def _vulns_for_threats(db: Session, threat_codes: list[str]) -> list[Vulnerability]:
    """Filtra vulnerabilidades relacionadas con las amenazas dadas."""
    all_vulns = db.query(Vulnerability).all()
    result = []
    for v in all_vulns:
        rt = v.related_threats or []
        if isinstance(rt, str):
            try:
                rt = json.loads(rt)
            except Exception:
                rt = [rt]
        if any(tc in rt for tc in threat_codes):
            result.append(v)
    return result if result else all_vulns[:30]  # fallback: primeras 30


def _next_risk_code(db: Session) -> str:
    from app.models import Risk as RiskModel
    n = db.query(RiskModel).count() + 1
    code = f"RSK-{n:04d}"
    while db.query(RiskModel).filter_by(code=code).first():
        n += 1
        code = f"RSK-{n:04d}"
    return code


# ---------- Punto de entrada principal ----------

def analyze_asset_risks(db: Session, asset_id: int) -> None:
    """Analiza un activo y crea/actualiza sus riesgos con IA."""
    asset = db.get(Asset, asset_id)
    if not asset:
        return

    asset.ai_risk_status = "analysing"
    db.commit()

    try:
        api_key = _get_api_key(db, asset.organization_id)
        if not api_key:
            asset.ai_risk_status = "skipped"
            asset.ai_risk_summary = {"reason": "No hay API key configurada para el agente IA"}
            db.commit()
            return

        # 1. Obtener catalogo filtrado por tipo de activo Y catalogos activos de la org
        threats = _threats_for_asset(db, asset.asset_type.value if asset.asset_type else "", asset.organization_id)
        threat_codes = [t.code for t in threats]
        vulns = _vulns_for_threats(db, threat_codes)

        # 2. Obtener controles implementados de la org
        impls = db.query(ControlImplementation).filter(
            ControlImplementation.organization_id == asset.organization_id,
            ControlImplementation.status != ControlStatus.NOT_IMPLEMENTED,
        ).all()

        # 3. Construir contexto para la IA
        asset_ctx = _build_asset_context(asset)
        threats_ctx = _build_threats_context(threats)
        vulns_ctx = _build_vulns_context(vulns)
        controls_ctx = _build_controls_context(impls)

        # Contexto organizacional del cuestionario IA (si existe)
        org_ctx_lines = []
        ctx_obj = db.query(RiskContext).filter_by(organization_id=asset.organization_id).first()
        if ctx_obj:
            if ctx_obj.risk_appetite is not None:
                org_ctx_lines.append(f"Apetito de riesgo: {ctx_obj.risk_appetite}/8")
            if ctx_obj.methodology:
                org_ctx_lines.append(f"Metodologia: {ctx_obj.methodology}")
            if ctx_obj.active_frameworks:
                org_ctx_lines.append(f"Normativas: {', '.join(ctx_obj.active_frameworks)}")
            qa = ctx_obj.questionnaire_answers or {}
            _QA_KEYS = ["sector", "employees", "systems", "data_types", "remote_access",
                        "third_parties", "incidents", "maturity", "controls_existing", "additional"]
            for key in _QA_KEYS:
                val = qa.get(key)
                if val:
                    if isinstance(val, list):
                        val = ", ".join(str(v) for v in val)
                    org_ctx_lines.append(f"  {key}: {val}")
        org_ctx_str = "\n".join(org_ctx_lines) if org_ctx_lines else "(no configurado)"

        user_content = (
            f"CONTEXTO DE LA ORGANIZACION:\n{org_ctx_str}\n\n"
            f"ACTIVO A ANALIZAR:\n{asset_ctx}\n\n"
            f"CATALOGO DE AMENAZAS APLICABLES ({len(threats)} amenazas):\n{threats_ctx}\n\n"
            f"CATALOGO DE VULNERABILIDADES ({len(vulns)} vulnerabilidades):\n{vulns_ctx}\n\n"
            f"CONTROLES IMPLEMENTADOS EN LA ORGANIZACION ({len(impls)} controles):\n{controls_ctx}"
        )

        # 4. Llamar al agente IA
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        model = _get_model(db, asset.organization_id)

        message = client.messages.create(
            model=model,
            max_tokens=4096,
            system=_RISK_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw_json = _strip_fence(message.content[0].text)

        # Log de tokens
        db.add(AiCallLog(
            organization_id=asset.organization_id,
            call_type="asset_risk_analysis",
            prompt_tokens=message.usage.input_tokens,
            completion_tokens=message.usage.output_tokens,
            model=model,
            anonymized=False,
            response_summary=f"Risk analysis for asset {asset_id}: {asset.name[:60]}",
        ))

        parsed = json.loads(raw_json)
        owner_id = _org_owner_id(db, asset.organization_id)

        # Soportar formato nuevo {cia, risks} y formato legado [...]
        if isinstance(parsed, dict):
            cia_data = parsed.get("cia") or {}
            risk_items = parsed.get("risks", [])
        else:
            cia_data = {}
            risk_items = parsed  # formato legado: lista directa

        # 5a. Aplicar valores CIA ENS si el activo los tiene todos a 0
        if cia_data:
            _cl = lambda v: max(0, min(4, int(v or 0)))
            all_zero = not any([
                asset.value_confidentiality, asset.value_integrity,
                asset.value_availability, asset.value_authenticity,
                asset.value_accountability,
            ])
            if all_zero:
                asset.value_confidentiality = _cl(cia_data.get("c", 0))
                asset.value_integrity       = _cl(cia_data.get("i", 0))
                asset.value_availability    = _cl(cia_data.get("a", 0))
                asset.value_authenticity    = _cl(cia_data.get("au", 0))
                asset.value_accountability  = _cl(cia_data.get("ac", 0))
                logger.debug("CIA values set for asset %d from AI: C=%d I=%d A=%d Au=%d Ac=%d",
                             asset_id,
                             asset.value_confidentiality, asset.value_integrity,
                             asset.value_availability, asset.value_authenticity,
                             asset.value_accountability)

        # 5b. Procesar cada riesgo devuelto
        threats_by_code = {t.code: t for t in threats}
        vulns_by_code = {v.code: v for v in vulns}
        impls_by_id = {i.id: i for i in impls}

        created, updated = 0, 0
        for item in risk_items:
            if not item.get("applies", True):
                continue
            threat = threats_by_code.get(item.get("threat_code", ""))
            if not threat:
                continue
            c, u = _upsert_risk(
                db, asset, threat, item,
                vulns_by_code, impls_by_id, owner_id,
            )
            created += c
            updated += u

        # 6. Aplicar apetito de riesgo
        appetite_upgrades = _enforce_risk_appetite(db, asset)

        asset.ai_risk_status = "analysed"
        asset.ai_risk_summary = {
            "risks_created": created,
            "risks_updated": updated,
            "threats_analysed": len(threats),
            "appetite_upgrades": appetite_upgrades,
            "summary": (
                f"{created} riesgos creados, {updated} actualizados a partir de {len(threats)} amenazas analizadas"
                + (f". {appetite_upgrades} riesgos escalados por superar el apetito de riesgo." if appetite_upgrades else ".")
            ),
        }
        db.commit()
        logger.info("Risk analysis OK asset=%d created=%d updated=%d appetite_upgrades=%d",
                    asset_id, created, updated, appetite_upgrades)

    except Exception as exc:
        logger.error("Risk analysis failed asset=%d: %s", asset_id, exc)
        try:
            asset.ai_risk_status = "error"
            asset.ai_risk_summary = {"error": str(exc)[:500]}
            db.commit()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# ANALISIS EN PARALELO POR LOTES
# Procesa BATCH_SIZE activos por llamada API, MAX_WORKERS llamadas concurrentes.
# Para 3000 activos: 3000/10 = 300 lotes / 2 workers + rate limiter 2.5s = ~24 req/min
# ──────────────────────────────────────────────────────────────────────────────

_BATCH_SIZE    = 10   # activos por llamada API
_MAX_WORKERS   = 1    # 1 worker serie: evita race condition en codigos RSK + mas simple
_BATCH_MODEL   = "claude-haiku-4-5-20251001"  # modelo rapido para analisis masivo
_MAX_RETRIES   = 4    # reintentos en caso de rate limit 429
_RETRY_BASE_S  = 15   # segundos base entre reintentos (backoff exponencial)
_MIN_CALL_GAP  = 1.5  # segundos minimos entre llamadas API (rate limiter, con 1 worker es suficiente)

# Rate limiter global: evita superar 50 req/min independientemente del paralelismo
import threading as _threading
_api_rate_lock  = _threading.Lock()
_api_last_call  = [0.0]  # mutable para uso en closure

# Circuit breaker: evita reintentos masivos cuando la API key no tiene créditos.
# Se resetea cuando el proceso reinicia (flag en memoria).
_credit_exhausted: dict[str, bool] = {}  # api_key_hash → True si sin créditos
_analysis_org_lock: dict[int, bool] = {}  # org_id → True si ya hay análisis en curso

_BATCH_SYSTEM_PROMPT = """Eres un experto ISO 27005, MAGERIT v3 y ENS (Esquema Nacional de Seguridad).
Analiza cada activo y devuelve: (1) valoracion CIA segun ENS/ISO 27005 y (2) escenarios de riesgo.

VALORACION CIA — 5 dimensiones ENS (escala 0-4):
- c (Confidencialidad): dano por revelacion no autorizada. 0=publico, 4=dato ultrasensible/secreto
- i (Integridad): dano por modificacion o corrupcion. 0=sin valor, 4=critico (financiero/legal)
- a (Disponibilidad): dano por perdida de acceso. 0=sin impacto, 4=parada total del negocio
- au (Autenticidad ENS): necesidad de verificar identidad de usuarios/procesos. 0=no necesario, 4=imprescindible
- ac (Trazabilidad ENS): necesidad de audit trail y no-repudio. 0=no requerido, 4=obligatorio legal/regulatorio

ESCENARIOS DE RIESGO — selecciona 3-5 amenazas reales para el activo:
Escala consecuencia/probabilidad: 0=insignificante/muy improbable, 4=critico/muy probable.
Apetito = {appetite}/8. treatment: "modification" si nivel_residual > {appetite}, "retention" si <=.

REGLAS CRITICAS:
- Devuelve EXCLUSIVAMENTE JSON valido, sin texto adicional
- No uses comillas dentro de strings, no uses backslash, no uses saltos de linea en strings
- Strings de rationale max 80 chars, vulnerability max 60 chars
- TODOS los activos deben tener cia con valores > 0 (nunca dejes los 5 a 0)

Formato de respuesta:
{{"results":[{{"asset_id":<int>,"cia":{{"c":<1-4>,"i":<1-4>,"a":<1-4>,"au":<0-4>,"ac":<0-4>}},"risks":[{{"threat_code":"<cod>","threat_name":"<nombre>","vulnerability":"<desc max 60>","inherent_consequence":<0-4>,"inherent_likelihood":<0-4>,"residual_consequence":<0-4>,"residual_likelihood":<0-4>,"treatment":"modification|retention","rationale":"<max 80>"}}]}}]}}"""


def _build_org_context_str(db: Session, org_id: int) -> str:
    """Construye string de contexto organizacional para incluir en prompts de lote."""
    ctx = db.query(RiskContext).filter_by(organization_id=org_id).first()
    if not ctx:
        return ""
    lines = []
    if ctx.risk_appetite is not None:
        lines.append(f"Apetito de riesgo: {ctx.risk_appetite}/8")
    if ctx.methodology:
        lines.append(f"Metodologia: {ctx.methodology}")
    if ctx.active_frameworks:
        lines.append(f"Normativas: {', '.join(ctx.active_frameworks)}")
    qa = ctx.questionnaire_answers or {}
    for key in ("sector", "employees", "systems", "data_types", "maturity", "incidents"):
        val = qa.get(key)
        if val:
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            lines.append(f"{key}: {val}")
    return "\n".join(lines)


def _build_batch_user_prompt(
    assets: list[Asset],
    threats: list[Threat],
    impls_summary: str,
    org_ctx: str,
) -> str:
    """Construye el user-content para analizar un lote de activos."""
    assets_lines = []
    for a in assets:
        assets_lines.append(
            f"ID:{a.id} [{a.asset_type.value if a.asset_type else 'unknown'}] "
            f"{a.name} | CIA:{a.value_confidentiality}/{a.value_integrity}/{a.value_availability} "
            f"| cat:{a.category or '-'} | desc:{(a.description or '')[:80]}"
        )
    assets_str = "\n".join(assets_lines)

    # Incluir solo las amenazas mas relevantes (max 50)
    threats_lines = [
        f"{t.code}: {t.name} | aplica_a:{','.join((t.typical_assets or [])[:3])}"
        for t in threats[:50]
    ]
    threats_str = "\n".join(threats_lines)

    return (
        f"CONTEXTO ORG:\n{org_ctx}\n\n"
        f"CONTROLES IMPLEMENTADOS:\n{impls_summary}\n\n"
        f"CATALOGO DE AMENAZAS ({len(threats)}):\n{threats_str}\n\n"
        f"ACTIVOS A ANALIZAR ({len(assets)}):\n{assets_str}"
    )


def _parse_batch_response(raw: str) -> dict:
    """Parsea la respuesta batch con intentos de reparacion."""
    import re
    raw = raw.strip()
    # Strip markdown fence
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.strip())

    # Extraer bloque JSON
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"Sin JSON en respuesta: {raw[:200]}")
    chunk = raw[start:end]

    # Intento 1: directo
    try:
        return json.loads(chunk)
    except json.JSONDecodeError:
        pass

    # Intento 2: eliminar trailing commas
    fixed = re.sub(r",\s*([}\]])", r"\1", chunk)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Intento 3: usar resultados individuales extraibles
    asset_results = []
    for m in re.finditer(r'"asset_id"\s*:\s*(\d+)', chunk):
        asset_id = int(m.group(1))
        # Buscar los risks de este asset
        pos = m.start()
        risks = re.findall(
            r'"threat_code"\s*:\s*"([^"]+)".*?"threat_name"\s*:\s*"([^"]+)".*?'
            r'"inherent_consequence"\s*:\s*(\d).*?"inherent_likelihood"\s*:\s*(\d).*?'
            r'"residual_consequence"\s*:\s*(\d).*?"residual_likelihood"\s*:\s*(\d)',
            chunk[pos:pos+3000], re.DOTALL
        )
        risk_objs = [
            {
                "threat_code": r[0], "threat_name": r[1],
                "inherent_consequence": int(r[2]), "inherent_likelihood": int(r[3]),
                "residual_consequence": int(r[4]), "residual_likelihood": int(r[5]),
                "treatment": "modification", "rationale": "Analisis parcial",
            }
            for r in risks
        ]
        if risk_objs:
            asset_results.append({"asset_id": asset_id, "risks": risk_objs})

    if asset_results:
        logger.warning("Batch JSON repaired via regex: %d asset results", len(asset_results))
        return {"results": asset_results}

    raise ValueError(f"No se pudo parsear la respuesta batch (len={len(chunk)})")


def _process_batch_isolated(
    batch_ids: list[int],
    org_id: int,
    api_key: str,
    model: str,
    appetite: int,
    all_threats: list,
    impls_summary: str,
    org_ctx: str,
    owner_id: int | None,
) -> None:
    """Procesa un lote de activos en una sola llamada API. Sesion DB propia."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        assets = db.query(Asset).filter(Asset.id.in_(batch_ids)).all()
        if not assets:
            return

        # Filtrar amenazas relevantes para los tipos de activo del lote
        types_in_batch = {a.asset_type.value if a.asset_type else "" for a in assets}
        relevant_threats = []
        seen_codes = set()
        for t in all_threats:
            ta = t.typical_assets or []
            if isinstance(ta, str):
                try:
                    ta = json.loads(ta)
                except Exception:
                    ta = [ta]
            ta_lower = [x.lower() for x in ta]
            for atype in types_in_batch:
                keys = _ASSET_TYPE_KEYS.get(atype, [atype])
                if any(k in ta_lower or any(k in s for s in ta_lower) for k in keys):
                    if t.code not in seen_codes:
                        relevant_threats.append(t)
                        seen_codes.add(t.code)
                    break
        if not relevant_threats:
            relevant_threats = all_threats[:40]

        user_content = _build_batch_user_prompt(assets, relevant_threats, impls_summary, org_ctx)
        system = _BATCH_SYSTEM_PROMPT.format(appetite=appetite)

        import anthropic
        import time as _time

        # Rate limiter global: esperar si la ultima llamada fue hace menos de _MIN_CALL_GAP s
        with _api_rate_lock:
            now = _time.time()
            gap = now - _api_last_call[0]
            if gap < _MIN_CALL_GAP:
                _time.sleep(_MIN_CALL_GAP - gap)
            _api_last_call[0] = _time.time()

        client = anthropic.Anthropic(api_key=api_key)

        # Retry con backoff exponencial en caso de rate limit 429
        msg = None
        last_exc = None
        for attempt in range(_MAX_RETRIES):
            try:
                msg = client.messages.create(
                    model=model,
                    max_tokens=8192,
                    system=system,
                    messages=[{"role": "user", "content": user_content}],
                )
                last_exc = None
                break
            except Exception as _exc:
                last_exc = _exc
                err_str = str(_exc)
                # Circuit breaker: créditos agotados → abortar inmediatamente
                if "credit balance" in err_str.lower() or "billing" in err_str.lower() or "insufficient_balance" in err_str.lower():
                    _credit_exhausted[api_key[:16]] = True
                    logger.warning("API credit exhausted — aborting batch analysis (batch=%s)", batch_ids[:3])
                    raise
                if "429" in err_str or "rate_limit" in err_str.lower():
                    wait_s = _RETRY_BASE_S * (2 ** attempt)
                    logger.warning(
                        "Rate limit 429 (intento %d/%d), esperando %ds — batch ids=%s",
                        attempt + 1, _MAX_RETRIES, wait_s, batch_ids[:3],
                    )
                    _time.sleep(wait_s)
                else:
                    raise  # otro tipo de error, no reintentar
        if last_exc is not None:
            raise last_exc

        raw = msg.content[0].text

        result = _parse_batch_response(raw)

        threats_by_code = {t.code: t for t in all_threats}

        for ar in result.get("results", []):
            asset_id = ar.get("asset_id")
            asset = next((a for a in assets if a.id == asset_id), None)
            if not asset:
                continue

            # --- Aplicar valores CIA ENS si el activo los tiene todos a 0 ---
            cia = ar.get("cia") or {}
            if cia:
                _clamp = lambda v: max(0, min(4, int(v or 0)))
                all_zero = not any([
                    asset.value_confidentiality, asset.value_integrity,
                    asset.value_availability, asset.value_authenticity,
                    asset.value_accountability,
                ])
                if all_zero:
                    asset.value_confidentiality = _clamp(cia.get("c", 0))
                    asset.value_integrity       = _clamp(cia.get("i", 0))
                    asset.value_availability    = _clamp(cia.get("a", 0))
                    asset.value_authenticity    = _clamp(cia.get("au", 0))
                    asset.value_accountability  = _clamp(cia.get("ac", 0))

            created, updated = 0, 0
            for item in ar.get("risks", []):
                threat = threats_by_code.get(item.get("threat_code", ""))
                if not threat:
                    continue
                c_, l_ = max(0, min(4, int(item.get("inherent_consequence", 2)))), max(0, min(4, int(item.get("inherent_likelihood", 2))))
                rc, rl = max(0, min(4, int(item.get("residual_consequence", 1)))), max(0, min(4, int(item.get("residual_likelihood", 1))))
                inh_lvl = calc_level(c_, l_)
                res_lvl = calc_level(rc, rl)
                tx_str  = item.get("treatment", "")
                treatment_map = {"modification": TreatmentOption.MODIFICATION, "retention": TreatmentOption.RETENTION,
                                 "avoidance": TreatmentOption.AVOIDANCE, "sharing": TreatmentOption.SHARING}
                treatment = treatment_map.get(tx_str, TreatmentOption.MODIFICATION if res_lvl > appetite else TreatmentOption.RETENTION)

                dup = db.query(Risk).filter_by(asset_id=asset.id, threat_id=threat.id).first()
                if dup:
                    dup.inherent_consequence = c_; dup.inherent_likelihood = l_; dup.inherent_level = inh_lvl
                    dup.residual_consequence = rc;  dup.residual_likelihood = rl;  dup.residual_level = res_lvl
                    dup.treatment_option = treatment
                    if item.get("rationale"):
                        dup.description = (item["rationale"] or "")[:1000]
                    updated += 1
                else:
                    # Generar codigo seguro
                    n = db.query(Risk).count() + 1
                    code = f"RSK-{n:04d}"
                    while db.query(Risk).filter_by(code=code).first():
                        n += 1; code = f"RSK-{n:04d}"
                    vuln_txt = (item.get("vulnerability") or "")[:400]
                    rat_txt  = (item.get("rationale") or "")[:400]
                    desc = (vuln_txt + (" — " + rat_txt if rat_txt else ""))[:1000]
                    risk = Risk(
                        code=code,
                        asset_id=asset.id,
                        threat_id=threat.id,
                        inherent_consequence=c_, inherent_likelihood=l_, inherent_level=inh_lvl,
                        residual_consequence=rc,  residual_likelihood=rl,  residual_level=res_lvl,
                        treatment_option=treatment,
                        description=desc,
                        ai_rationale=rat_txt,
                        status=RiskStatus.IDENTIFIED,
                        owner_id=owner_id,
                        organization_id=org_id,
                        ai_generated=True,
                    )
                    db.add(risk)
                    db.flush()  # necesario: autoflush=False → flush manual para que count() vea el nuevo codigo
                    created += 1

            asset.ai_risk_status = "analysed"
            asset.ai_risk_summary = {
                "risks_created": created, "risks_updated": updated,
                "threats_analysed": len(ar.get("risks", [])),
                "summary": f"{created} riesgos creados, {updated} actualizados",
            }

        # Marcar como error los activos que no aparecieron en la respuesta
        responded_ids = {ar.get("asset_id") for ar in result.get("results", [])}
        for asset in assets:
            if asset.id not in responded_ids and asset.ai_risk_status == "analysing":
                asset.ai_risk_status = "error"
                asset.ai_risk_summary = {"error": "No incluido en respuesta del lote. Reintenta."}

        db.commit()
        logger.debug("Batch done: %d assets, org=%d", len(assets), org_id)

    except Exception as exc:
        logger.error("Batch failed (ids=%s…): %s", batch_ids[:3], exc)
        try:
            for asset in db.query(Asset).filter(Asset.id.in_(batch_ids)).all():
                if asset.ai_risk_status == "analysing":
                    asset.ai_risk_status = "error"
                    asset.ai_risk_summary = {"error": str(exc)[:300]}
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


def analyze_all_org_assets(db: Session, org_id: int) -> dict:
    """Analiza en SERIE todos los activos pendientes (null/error) de la org.
    Procesa lotes de _BATCH_SIZE activos por llamada API. Con _MAX_WORKERS=1
    los lotes son secuenciales para evitar race conditions en codigos RSK.
    """
    import concurrent.futures
    from sqlalchemy import or_

    asset_ids = [
        a.id for a in db.query(Asset).filter(
            Asset.organization_id == org_id,
            Asset.is_group_representative.is_(False),
            or_(Asset.ai_risk_status == None, Asset.ai_risk_status == "error"),  # noqa: E711
        ).all()
    ]
    if not asset_ids:
        logger.info("No pending assets for org=%d", org_id)
        return {"total": 0}

    total = len(asset_ids)
    logger.info("Serial batch analysis starting: %d assets, batch=%d, org=%d",
                total, _BATCH_SIZE, org_id)

    # Marcar todos como "analysing" de una vez
    db.query(Asset).filter(Asset.id.in_(asset_ids)).update(
        {"ai_risk_status": "analysing", "ai_risk_summary": None},
        synchronize_session=False,
    )
    db.commit()

    # Datos compartidos (leidos una sola vez para todos los lotes)
    api_key = _get_api_key(db, org_id)
    if not api_key:
        db.query(Asset).filter(Asset.id.in_(asset_ids)).update(
            {"ai_risk_status": "skipped", "ai_risk_summary": {"reason": "Sin API key"}},
            synchronize_session=False,
        )
        db.commit()
        return {"total": 0}

    # Circuit breaker: si ya sabemos que no hay créditos, no reintentar
    if _credit_exhausted.get(api_key[:16]):
        logger.warning("Credit exhausted circuit breaker active — skipping org=%d analysis", org_id)
        return {"total": 0}

    # Anti-duplicación: si ya hay un análisis en curso para esta org, salir
    if _analysis_org_lock.get(org_id):
        logger.info("Analysis already running for org=%d — skipping duplicate", org_id)
        return {"total": 0}
    _analysis_org_lock[org_id] = True

    # Usar haiku para analisis masivo (rapido y barato); mantener config para analisis individual
    model = _BATCH_MODEL

    active_catalogs = _get_active_catalogs(db, org_id)
    all_threats   = db.query(Threat).filter(Threat.catalog.in_(active_catalogs)).all()
    ctx_obj       = db.query(RiskContext).filter_by(organization_id=org_id).first()
    appetite      = ctx_obj.risk_appetite if ctx_obj and ctx_obj.risk_appetite is not None else 3
    owner_id      = _org_owner_id(db, org_id)
    org_ctx       = _build_org_context_str(db, org_id)

    # Resumen de controles implementados
    impls = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == org_id,
        ControlImplementation.status != ControlStatus.NOT_IMPLEMENTED,
    ).all()
    impls_summary = ", ".join(
        f"{i.name}" for i in impls[:20]
    ) or "ninguno"

    # Dividir en lotes
    batches = [asset_ids[i:i + _BATCH_SIZE] for i in range(0, total, _BATCH_SIZE)]
    logger.info("Lotes: %d (tamano=%d), serial", len(batches), _BATCH_SIZE)

    # Ejecutar en paralelo
    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                _process_batch_isolated,
                batch, org_id, api_key, model,
                appetite, all_threats, impls_summary, org_ctx, owner_id,
            ): batch
            for batch in batches
        }
        done, failed = 0, 0
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
                done += 1
            except Exception as exc:
                failed += 1
                logger.error("Future failed batch=%s: %s", futures[future][:2], exc)

    _analysis_org_lock.pop(org_id, None)
    logger.info("Serial analysis complete: %d batches done, %d failed, org=%d",
                done, failed, org_id)
    return {"total": total}


def _analyze_isolated(asset_id: int) -> None:
    """Analiza un activo individual con su propia sesion DB (para botón individual)."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        analyze_asset_risks(db, asset_id)
    except Exception as exc:
        logger.error("Isolated analysis failed asset=%d: %s", asset_id, exc)
        try:
            asset = db.get(Asset, asset_id)
            if asset:
                asset.ai_risk_status = "error"
                asset.ai_risk_summary = {"error": str(exc)[:400]}
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ---------- Construccion de contexto ----------

def _build_asset_context(asset: Asset) -> str:
    lines = [
        f"Nombre: {asset.name}",
        f"Codigo: {asset.code}",
        f"Tipo: {asset.asset_type.value if asset.asset_type else 'desconocido'}",
        f"Categoria: {asset.category or 'N/A'}",
        f"Descripcion: {asset.description or 'N/A'}",
        f"Proceso de negocio: {asset.business_process or 'N/A'}",
        f"Clasificacion: {asset.classification or 'N/A'}",
        f"Valores CIA: Confidencialidad={asset.value_confidentiality}, "
        f"Integridad={asset.value_integrity}, Disponibilidad={asset.value_availability}, "
        f"Autenticidad={asset.value_authenticity}, Responsabilidad={asset.value_accountability}",
        f"Valor maximo CIA: {asset.value_max}",
    ]
    return "\n".join(lines)


def _build_threats_context(threats: list) -> str:
    lines = []
    for t in threats[:40]:  # max 40 amenazas en contexto
        lines.append(
            f"- {t.code}: {t.name} | Categoria: {t.category or 'N/A'} | "
            f"Origen: {t.origin.value if t.origin else 'N/A'} | "
            f"Afecta: {','.join(t.affects or []) if t.affects else 'N/A'}"
        )
    return "\n".join(lines)


def _build_vulns_context(vulns: list) -> str:
    lines = []
    for v in vulns[:40]:  # max 40 vulnerabilidades
        lines.append(
            f"- {v.code}: {v.name} | Categoria: {v.category or 'N/A'} | "
            f"Amenazas relacionadas: {','.join((v.related_threats or [])[:5])}"
        )
    return "\n".join(lines)


def _build_controls_context(impls: list) -> str:
    lines = []
    for impl in impls[:50]:  # max 50 controles
        ctrl_code = impl.control.code if impl.control else "?"
        ctrl_name = impl.control.name if impl.control else impl.name
        lines.append(
            f"- impl_id={impl.id} | {ctrl_code}: {ctrl_name[:60]} | "
            f"Estado: {impl.status.value if impl.status else 'N/A'} | "
            f"Madurez: {impl.maturity}/5"
        )
    return "\n".join(lines) if lines else "Ninguno"


# ---------- Creacion/actualizacion de riesgos ----------

def _upsert_risk(
    db: Session,
    asset: Asset,
    threat: Threat,
    item: dict,
    vulns_by_code: dict,
    impls_by_id: dict,
    owner_id: int | None,
) -> tuple[int, int]:
    """Crea o actualiza el registro Risk para asset×threat. Devuelve (created, updated)."""
    inh_lik = clamp(int(item.get("inherent_likelihood", 2)))
    inh_con = clamp(int(item.get("inherent_consequence", 2)))
    inh_lvl = calc_level(inh_con, inh_lik)

    # Controles con contribucion
    ctrl_list = item.get("control_contributions", [])
    ctrl_dicts = []
    for cc in ctrl_list:
        impl = impls_by_id.get(cc.get("impl_id"))
        if impl:
            ctrl_dicts.append({
                "maturity": impl.maturity or 0,
                "contribution": float(cc.get("contribution", 0.5)),
            })

    res_lik, res_con, res_lvl = (
        calc_residual(inh_lik, inh_con, ctrl_dicts) if ctrl_dicts
        else (inh_lik, inh_con, inh_lvl)
    )
    # Override si el IA proporciona residual directo
    if item.get("residual_likelihood") is not None:
        res_lik = clamp(int(item["residual_likelihood"]))
    if item.get("residual_consequence") is not None:
        res_con = clamp(int(item["residual_consequence"]))
    res_lvl = calc_level(res_con, res_lik)

    treatment_raw = item.get("treatment_option", "modification")
    try:
        treatment = TreatmentOption(treatment_raw)
    except ValueError:
        treatment = TreatmentOption.MODIFICATION

    existing = db.query(Risk).filter_by(
        asset_id=asset.id, threat_id=threat.id
    ).first()

    if existing:
        # Solo actualizar si el riesgo fue generado por IA (no sobreescribir ediciones manuales)
        if existing.ai_generated:
            existing.inherent_likelihood = inh_lik
            existing.inherent_consequence = inh_con
            existing.inherent_level = inh_lvl
            existing.residual_likelihood = res_lik
            existing.residual_consequence = res_con
            existing.residual_level = res_lvl
            existing.description = item.get("rationale", existing.description)
            existing.consequence_description = item.get("consequence_description", existing.consequence_description)
            existing.ai_rationale = item.get("rationale", "")
            existing.treatment_option = treatment
            _sync_vulns(db, existing, item.get("vulnerability_codes", []), vulns_by_code)
            _sync_controls(db, existing, ctrl_list, impls_by_id)
        return 0, 1

    # Crear nuevo riesgo
    code = _next_risk_code(db)
    risk = Risk(
        organization_id=asset.organization_id,
        code=code,
        asset_id=asset.id,
        threat_id=threat.id,
        description=item.get("rationale", ""),
        consequence_description=item.get("consequence_description", ""),
        inherent_likelihood=inh_lik,
        inherent_consequence=inh_con,
        inherent_level=inh_lvl,
        residual_likelihood=res_lik,
        residual_consequence=res_con,
        residual_level=res_lvl,
        status=RiskStatus.ASSESSED,
        owner_id=owner_id,
        treatment_option=treatment,
        ai_generated=True,
        ai_rationale=item.get("rationale", ""),
    )
    db.add(risk)
    db.flush()  # necesario para obtener risk.id

    _sync_vulns(db, risk, item.get("vulnerability_codes", []), vulns_by_code)
    _sync_controls(db, risk, ctrl_list, impls_by_id)
    return 1, 0


def _enforce_risk_appetite(db: Session, asset: Asset) -> int:
    """Escala automaticamente a 'modification' los riesgos del activo cuyo nivel residual
    supera el apetito de riesgo de la organizacion y tienen tratamiento 'retention'.

    Devuelve el numero de riesgos escalados.
    """
    ctx = db.query(RiskContext).filter_by(
        organization_id=asset.organization_id
    ).first()
    if not ctx:
        return 0
    appetite = ctx.risk_appetite or 3

    risks = db.query(Risk).filter(
        Risk.asset_id == asset.id,
        Risk.ai_generated == True,  # noqa: E712 — solo riesgos IA para no pisar ediciones manuales
        Risk.treatment_option == TreatmentOption.RETENTION,
    ).all()

    upgraded = 0
    for r in risks:
        if (r.residual_level or 0) > appetite:
            r.treatment_option = TreatmentOption.MODIFICATION
            upgraded += 1

    if upgraded:
        db.flush()
        logger.info(
            "Appetite enforcement: %d risks escalated to modification (appetite=%d) asset=%d",
            upgraded, appetite, asset.id,
        )
    return upgraded


def _sync_vulns(db: Session, risk: Risk, vuln_codes: list, vulns_by_code: dict) -> None:
    """Vincula las vulnerabilidades al riesgo (sin duplicados)."""
    from app.models import risk_vulnerability_table
    existing_ids = {v.id for v in risk.vulnerabilities}
    for code in vuln_codes:
        v = vulns_by_code.get(code)
        if v and v.id not in existing_ids:
            try:
                db.execute(
                    text("INSERT OR IGNORE INTO risk_vulnerabilities (risk_id, vulnerability_id) VALUES (:r, :v)"),
                    {"r": risk.id, "v": v.id},
                )
                existing_ids.add(v.id)
            except Exception:
                pass


def _sync_controls(db: Session, risk: Risk, ctrl_list: list, impls_by_id: dict) -> None:
    """Vincula los controles con su contribucion al riesgo (sin duplicados)."""
    existing_impl_ids = {impl.id for impl in risk.controls}
    for cc in ctrl_list:
        impl_id = cc.get("impl_id")
        contrib = float(cc.get("contribution", 0.5))
        impl = impls_by_id.get(impl_id)
        if impl and impl.id not in existing_impl_ids:
            try:
                db.execute(
                    text("INSERT OR IGNORE INTO risk_controls "
                         "(risk_id, control_implementation_id, contribution) "
                         "VALUES (:r, :c, :contrib)"),
                    {"r": risk.id, "c": impl.id, "contrib": contrib},
                )
                existing_impl_ids.add(impl.id)
            except Exception:
                pass


# ---------- Pipeline CSV → riesgos ----------

def link_csv_vulnerabilities_to_assets(
    db: Session, org_id: int, csv_findings: list[dict]
) -> dict:
    """Asocia hallazgos de CSV de vulnerabilidades a activos y crea riesgos.

    csv_findings: lista de dicts con keys: product, cve_id, severity, description
    Retorna {linked: N, unmatched: M}
    """
    assets = db.query(Asset).filter_by(organization_id=org_id).all()
    if not assets:
        return {"linked": 0, "unmatched": len(csv_findings)}

    linked, unmatched = 0, 0
    all_threats = db.query(Threat).all()
    owner_id = _org_owner_id(db, org_id)

    for finding in csv_findings:
        product = (finding.get("product") or "").lower()
        cve_id = finding.get("cve_id") or ""
        severity = finding.get("severity", "medium").lower()
        description = finding.get("description", "")

        # Buscar activo que haga match con el producto
        matched_asset = None
        for asset in assets:
            asset_terms = " ".join(filter(None, [
                asset.name, asset.description, asset.category,
                asset.asset_type.value if asset.asset_type else ""
            ])).lower()
            if product and any(word in asset_terms for word in product.split()[:3]):
                matched_asset = asset
                break

        if not matched_asset:
            unmatched += 1
            continue

        # Buscar la vulnerabilidad en el catalogo
        vuln = (
            db.query(Vulnerability)
            .filter(Vulnerability.name.ilike(f"%{product[:20]}%"))
            .first()
        )
        if not vuln and cve_id:
            vuln = db.query(Vulnerability).filter(
                Vulnerability.description.ilike(f"%{cve_id}%")
            ).first()

        # Determinar amenaza (por defecto: vulnerabilidad tecnica / ataque)
        threat = (
            db.query(Threat)
            .filter(Threat.category.ilike("%technical failure%"))
            .first()
            or all_threats[0] if all_threats else None
        )
        if not threat:
            unmatched += 1
            continue

        # Calcular severidad
        sev_map = {"critical": (4, 4), "high": (3, 4), "medium": (2, 3), "low": (1, 2)}
        inh_lik, inh_con = sev_map.get(severity, (2, 2))

        existing = db.query(Risk).filter_by(
            asset_id=matched_asset.id, threat_id=threat.id
        ).first()

        if not existing:
            code = _next_risk_code(db)
            risk = Risk(
                organization_id=org_id,
                code=code,
                asset_id=matched_asset.id,
                threat_id=threat.id,
                description=f"Detectado via CSV. {description[:200]}",
                consequence_description=f"Vulnerabilidad: {cve_id or product}",
                inherent_likelihood=inh_lik,
                inherent_consequence=inh_con,
                inherent_level=calc_level(inh_con, inh_lik),
                residual_likelihood=inh_lik,
                residual_consequence=inh_con,
                residual_level=calc_level(inh_con, inh_lik),
                status=RiskStatus.IDENTIFIED,
                owner_id=owner_id,
                ai_generated=True,
                ai_rationale=f"Importado desde CSV: {cve_id or product}. Severity: {severity}.",
            )
            db.add(risk)
            if vuln:
                db.flush()
                try:
                    db.execute(
                        text("INSERT OR IGNORE INTO risk_vulnerabilities "
                             "(risk_id, vulnerability_id) VALUES (:r, :v)"),
                        {"r": risk.id, "v": vuln.id},
                    )
                except Exception:
                    pass
        linked += 1

    db.commit()
    return {"linked": linked, "unmatched": unmatched}


# ---------- Pipeline OSINT → riesgos ----------

def link_osint_findings_to_assets(
    db: Session, org_id: int, scan_id: int
) -> dict:
    """Crea riesgos a partir de hallazgos OSINT de un escaneo."""
    from app.models import OSINTFinding, OSINTScan

    scan = db.get(OSINTScan, scan_id)
    if not scan:
        return {"created": 0}

    assets = db.query(Asset).filter_by(organization_id=org_id).all()
    if not assets:
        return {"created": 0}

    findings = (
        db.query(OSINTFinding)
        .filter_by(scan_id=scan_id)
        .filter(OSINTFinding.is_remediated == False)  # noqa: E712
        .all()
    )

    target = scan.target.lower()
    owner_id = _org_owner_id(db, org_id)
    all_threats = db.query(Threat).all()
    threats_by_cat: dict[str, Threat] = {}
    for t in all_threats:
        cat = (t.category or "").lower()
        threats_by_cat[cat] = t

    # Buscar activo que coincida con el target del scan
    matched_asset = None
    for asset in assets:
        asset_terms = " ".join(filter(None, [
            asset.name, asset.description, asset.category,
        ])).lower()
        # Match por dominio, IP, nombre de producto
        if any(part in asset_terms for part in target.split(".")[:2] if len(part) > 3):
            matched_asset = asset
            break

    if not matched_asset:
        # Intentar match por tipo: OSINT de dominio → activos de red
        if scan.scan_type.value in ("domain", "url", "ip"):
            matched_asset = (
                db.query(Asset)
                .filter_by(organization_id=org_id, asset_type="support_network")
                .first()
                or db.query(Asset).filter_by(organization_id=org_id).first()
            )

    if not matched_asset:
        return {"created": 0}

    created = 0
    for finding in findings:
        # Mapear finding_type a amenaza
        finding_type = (finding.finding_type or "").lower()
        threat = None
        for cat_key in ["unauthorised", "technical failure", "deliberate", "accidental"]:
            if cat_key in finding_type or finding_type in cat_key:
                threat = threats_by_cat.get(cat_key)
                break
        if not threat:
            threat = all_threats[0] if all_threats else None
        if not threat:
            continue

        # Nivel de riesgo del hallazgo OSINT
        sev_map = {"critical": (4, 4), "high": (3, 4), "medium": (2, 3), "low": (1, 2), "info": (1, 1)}
        inh_lik, inh_con = sev_map.get(finding.risk_level.value if finding.risk_level else "medium", (2, 2))

        existing = db.query(Risk).filter_by(
            asset_id=matched_asset.id, threat_id=threat.id
        ).first()

        if not existing:
            from app.models import RiskContext, TreatmentOption
            from app.services.risk_engine import calc_residual
            from datetime import datetime, timedelta, timezone

            ctx = db.query(RiskContext).filter(
                RiskContext.organization_id == org_id
            ).first()
            appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3
            matrix = ctx.risk_matrix if ctx else None

            inh_level = calc_level(inh_con, inh_lik, matrix)
            rl, rc, rlev = calc_residual(inh_lik, inh_con, [], matrix)

            # Auto-tratamiento segun appetite
            if rlev <= appetite:
                r_status = RiskStatus.ACCEPTED
                r_treatment = TreatmentOption.RETENTION
            else:
                r_status = RiskStatus.IDENTIFIED
                r_treatment = TreatmentOption.MODIFICATION

            review_days = {0: 365, 1: 365, 2: 180, 3: 90, 4: 60, 5: 30, 6: 14, 7: 7, 8: 7}
            treatment_days = {0: 365, 1: 180, 2: 90, 3: 60, 4: 45, 5: 30, 6: 14, 7: 7, 8: 3}
            now = datetime.now(timezone.utc)

            code = _next_risk_code(db)
            risk = Risk(
                organization_id=org_id,
                code=code,
                asset_id=matched_asset.id,
                threat_id=threat.id,
                description=f"OSINT: {finding.title[:200]}",
                consequence_description=f"Fuente: {finding.source.value if finding.source else 'OSINT'}. {(finding.description or '')[:200]}",
                inherent_likelihood=inh_lik,
                inherent_consequence=inh_con,
                inherent_level=inh_level,
                residual_likelihood=rl,
                residual_consequence=rc,
                residual_level=rlev,
                status=r_status,
                treatment_option=r_treatment,
                owner_id=owner_id,
                next_review=now + timedelta(days=review_days.get(rlev, 90)),
                treatment_due_date=now + timedelta(days=treatment_days.get(rlev, 60)),
                ai_generated=True,
                ai_rationale=f"Generado desde hallazgo OSINT [{finding.source.value if finding.source else '?'}]: {finding.title[:100]}",
            )
            db.add(risk)
            created += 1

    if created > 0:
        db.commit()
    return {"created": created}
