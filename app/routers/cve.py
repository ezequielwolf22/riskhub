"""CVE Monitor — integracion con NVD (NIST) y analisis de riesgo por IA.

Endpoints:
  GET  /api/cve/config          — configuracion actual (sin API key)
  PUT  /api/cve/config          — guardar configuracion (admin)
  GET  /api/cve/search          — buscar CVEs en NVD
  POST /api/cve/analyze         — analisis IA de CVEs contra activos seleccionados
  POST /api/cve/create-risk     — crear riesgo en RiskHub desde un analisis CVE
"""
import base64
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Asset, ControlImplementation, IntegrationConfig, User
from app.security import filter_by_org, get_current_user, require_admin, require_analyst
from app.services import cve_service as cvs
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.cve")

router = APIRouter(prefix="/api/cve", tags=["cve"])

_INTEGRATION_NAME = "nvd_cve"
_MAX_ANALYSIS_PAIRS = 30   # maximo CVEs * activos por peticion


# ---------- Cifrado ----------

def _fernet_key() -> bytes:
    return base64.urlsafe_b64encode(
        hashlib.sha256(settings.secret_key.encode()).digest()
    )


def _encrypt(plain: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_fernet_key()).encrypt(plain.encode()).decode()


def _decrypt(token: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_fernet_key()).decrypt(token.encode()).decode()


# ---------- Config helpers ----------

def _get_config(db: Session) -> Optional[dict]:
    ic = db.query(IntegrationConfig).filter_by(name=_INTEGRATION_NAME).first()
    if not ic or not ic.config_encrypted:
        return None
    try:
        return json.loads(_decrypt(ic.config_encrypted))
    except Exception:
        return None


def _get_api_key(db: Session) -> Optional[str]:
    cfg = _get_config(db)
    return cfg.get("api_key") if cfg else None


# ---------- Schemas ----------

class CveConfigIn(BaseModel):
    api_key: Optional[str] = None   # puede omitirse para usar NVD sin autenticar
    default_days: int = 7
    default_severity: str = "HIGH"  # CRITICAL | HIGH | MEDIUM | LOW | ALL
    auto_scan_enabled: bool = False
    auto_scan_severity: str = "CRITICAL"


class CveConfigOut(BaseModel):
    configured: bool
    has_api_key: bool
    default_days: int = 7
    default_severity: str = "HIGH"
    auto_scan_enabled: bool = False
    auto_scan_severity: str = "CRITICAL"
    updated_at: Optional[str] = None


class AnalyzeRequest(BaseModel):
    cve_ids: list[str]
    asset_ids: list[int]   # lista de IDs de activos; [] = todos los activos
    skip_heuristic: bool = False   # si True, analiza todos los pares sin filtro previo


class CreateRiskRequest(BaseModel):
    cve_id: str
    asset_id: int
    analysis: dict   # el dict de analisis retornado por /analyze
    cve_data: dict   # datos del CVE (score, desc, etc.)


class AutoScanRequest(BaseModel):
    asset_ids: list[int] = []   # vacio = todos los activos (hasta 50)
    days: int = 7
    severity: str = "HIGH"
    skip_heuristic: bool = False
    max_cves: int = 50


# ---------- Endpoints ----------

@router.get("/config", response_model=CveConfigOut)
def get_config(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = _get_config(db)
    if not cfg:
        return CveConfigOut(configured=False, has_api_key=False)
    ic = db.query(IntegrationConfig).filter_by(name=_INTEGRATION_NAME).first()
    return CveConfigOut(
        configured=True,
        has_api_key=bool(cfg.get("api_key")),
        default_days=cfg.get("default_days", 7),
        default_severity=cfg.get("default_severity", "HIGH"),
        auto_scan_enabled=cfg.get("auto_scan_enabled", False),
        auto_scan_severity=cfg.get("auto_scan_severity", "CRITICAL"),
        updated_at=ic.updated_at.isoformat() if ic and ic.updated_at else None,
    )


@router.put("/config")
def save_config(
    body: CveConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    valid_sev = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "ALL"}
    if body.default_severity.upper() not in valid_sev:
        raise HTTPException(400, f"default_severity debe ser uno de: {valid_sev}")
    if body.auto_scan_severity.upper() not in valid_sev:
        raise HTTPException(400, f"auto_scan_severity debe ser uno de: {valid_sev}")
    if not 1 <= body.default_days <= 90:
        raise HTTPException(400, "default_days debe estar entre 1 y 90.")

    data = {
        "api_key": body.api_key.strip() if body.api_key else None,
        "default_days": body.default_days,
        "default_severity": body.default_severity.upper(),
        "auto_scan_enabled": body.auto_scan_enabled,
        "auto_scan_severity": body.auto_scan_severity.upper(),
    }

    encrypted = _encrypt(json.dumps(data))
    ic = db.query(IntegrationConfig).filter_by(name=_INTEGRATION_NAME).first()
    if not ic:
        ic = IntegrationConfig(name=_INTEGRATION_NAME)
        db.add(ic)
    ic.config_encrypted = encrypted
    ic.updated_at = datetime.now(timezone.utc)
    ic.updated_by_id = current_user.id

    log_action(db, current_user.id, "update", "integration_config", _INTEGRATION_NAME,
               {"has_api_key": bool(body.api_key), "auto_scan": body.auto_scan_enabled})
    db.commit()

    # Invalidar cache NVD si cambio la API key
    cvs.invalidate_cache()
    return {"ok": True, "message": "Configuracion CVE Monitor guardada."}


@router.get("/lookup")
def lookup_cve(
    q: str = Query(..., min_length=3, max_length=300,
                   description="CVE ID (CVE-2024-12345) o URL de NVD/MITRE/CVE.org"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Busca un CVE especifico por ID o URL.

    Acepta:
      - CVE-2024-12345
      - https://nvd.nist.gov/vuln/detail/CVE-2024-12345
      - https://www.cve.org/CVERecord?id=CVE-2024-12345
      - https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-12345
    """
    import re
    match = re.search(r'CVE-\d{4}-\d+', q, re.IGNORECASE)
    if not match:
        raise HTTPException(400,
            "No se encontro un ID CVE valido en la entrada. "
            "Formato esperado: CVE-YYYY-NNNNN")
    cve_id = match.group(0).upper()
    api_key = _get_api_key(db)
    cve = cvs.fetch_by_id(api_key, cve_id)
    if not cve:
        raise HTTPException(404,
            f"{cve_id} no encontrado en NVD. "
            "Comprueba que el ID es correcto o que la CVE ya ha sido publicada.")
    return cve


@router.get("/search")
def search_cves(
    days: int = Query(7, ge=1, le=90),
    severity: str = Query("HIGH", description="CRITICAL|HIGH|MEDIUM|LOW|ALL"),
    keyword: Optional[str] = Query(None, max_length=200),
    max_results: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Busca CVEs recientes en NVD. No requiere API key (pero la usa si esta configurada)."""
    api_key = _get_api_key(db)
    sev = None if severity.upper() == "ALL" else severity.upper()
    valid_sev = {"CRITICAL", "HIGH", "MEDIUM", "LOW", None}
    if sev not in valid_sev:
        raise HTTPException(400, "severity debe ser CRITICAL, HIGH, MEDIUM, LOW o ALL")
    try:
        cves = cvs.fetch_recent(api_key, days=days, severity=sev,
                                keyword=keyword, max_results=max_results)
        return {"total": len(cves), "cves": cves}
    except ValueError as e:
        raise HTTPException(502, str(e))


@router.post("/analyze")
def analyze_cves(
    body: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Ejecuta el workflow de analisis IA: CVE x Activo -> riesgo_inherente, cobertura, riesgo_residual, acciones."""
    from app.models import AiConfig
    from app.routers.ai_config import resolve_api_key
    from app.services.cve_analysis_service import analyze_cve_asset, get_rag_context

    if not body.cve_ids:
        raise HTTPException(400, "Se requiere al menos un CVE ID.")
    if len(body.cve_ids) > 20:
        raise HTTPException(400, "Maximo 20 CVEs por analisis.")

    # Configuracion IA — org-scoped primero, fallback a global
    ai_cfg = db.query(AiConfig).filter_by(organization_id=current_user.organization_id).first()
    if not ai_cfg:
        ai_cfg = db.query(AiConfig).first()
    ai_api_key = resolve_api_key(ai_cfg)
    if not ai_api_key:
        raise HTTPException(400, "El Agente IA no esta configurado. Ve a Onboarding para configurarlo.")

    # Configuracion CVE
    api_key = _get_api_key(db)

    # Obtener datos de CVEs
    cve_data = {}
    for cid in body.cve_ids[:20]:
        cid = cid.strip().upper()
        cve = cvs.fetch_by_id(api_key, cid)
        if cve:
            cve_data[cid] = cve
        else:
            logger.warning("CVE no encontrado en NVD: %s", cid)

    if not cve_data:
        raise HTTPException(404, "No se encontraron datos para los CVE IDs proporcionados en NVD.")

    # Obtener activos filtrados por org
    if body.asset_ids:
        assets = filter_by_org(
            db.query(Asset).filter(Asset.id.in_(body.asset_ids)), Asset, current_user
        ).all()
    else:
        assets = filter_by_org(db.query(Asset), Asset, current_user).limit(50).all()

    if not assets:
        raise HTTPException(404, "No se encontraron activos. Revisa el inventario de activos.")

    # Obtener controles implementados filtrados por org (para contexto de cobertura)
    impls = filter_by_org(db.query(ControlImplementation), ControlImplementation, current_user).all()
    controls_context = [
        {
            "name": impl.name,
            "control_code": impl.control.code if impl.control else "",
            "status": impl.implementation_status.value if impl.implementation_status else "",
            "notes": (impl.notes or "")[:200],
        }
        for impl in impls
        if impl.implementation_status and impl.implementation_status.value in ("implemented", "partial")
    ]

    # Limitar pares totales
    pairs_done = 0
    results = []

    for cve_id, cve in cve_data.items():
        for asset in assets:
            if pairs_done >= _MAX_ANALYSIS_PAIRS:
                break

            # Filtro heuristico para evitar analizar pares irrelevantes
            if not body.skip_heuristic:
                match_score = cvs.asset_matches_cve(
                    asset.name or "",
                    asset.description or "",
                    cve,
                )
                # Si hay productos CPE definidos y no hay coincidencia, omitir
                if cve.get("affected_products") and match_score < 0.15:
                    continue

            rag_ctx = get_rag_context(cve, {"name": asset.name, "description": asset.description or ""}, organization_id=current_user.organization_id)

            asset_dict = {
                "name": asset.name,
                "asset_type": asset.asset_type.value if asset.asset_type else "",
                "description": asset.description or "",
                "confidentiality": asset.confidentiality,
                "integrity": asset.integrity,
                "availability": asset.availability,
            }

            analysis = analyze_cve_asset(
                cve=cve,
                asset=asset_dict,
                controls=controls_context,
                rag_context=rag_ctx,
                api_key=ai_api_key,
            )

            results.append({
                "cve_id": cve_id,
                "cve": cve,
                "asset_id": asset.id,
                "asset_name": asset.name,
                "asset_type": asset_dict["asset_type"],
                "analysis": analysis,
            })
            pairs_done += 1

        if pairs_done >= _MAX_ANALYSIS_PAIRS:
            break

    log_action(db, current_user.id, "analyze", "cve", None, {
        "cve_ids": list(cve_data.keys()),
        "asset_count": len(assets),
        "pairs_analyzed": pairs_done,
    })
    db.commit()

    return {
        "analyzed_pairs": pairs_done,
        "results": results,
    }


@router.post("/auto-scan")
def auto_scan_cves(
    body: AutoScanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Busca CVEs recientes en NVD relevantes para los activos seleccionados y los analiza con IA.

    Flujo automatico:
      1. Obtiene activos con sus software_tags.
      2. Busca CVEs en NVD usando los tags como keywords (y busqueda general como fallback).
      3. Ejecuta el analisis IA CVE x Activo sobre los pares con coincidencia heuristica.
    """
    from app.models import AiConfig
    from app.routers.ai_config import resolve_api_key
    from app.services.cve_analysis_service import analyze_cve_asset, get_rag_context

    ai_cfg = db.query(AiConfig).filter_by(organization_id=current_user.organization_id).first()
    if not ai_cfg:
        ai_cfg = db.query(AiConfig).first()
    ai_api_key = resolve_api_key(ai_cfg)
    if not ai_api_key:
        raise HTTPException(400, "El Agente IA no esta configurado. Ve a Configuracion > Agente IA.")

    api_key = _get_api_key(db)
    sev = None if body.severity.upper() == "ALL" else body.severity.upper()
    valid_sev = {"CRITICAL", "HIGH", "MEDIUM", "LOW", None}
    if sev not in valid_sev:
        raise HTTPException(400, "severity invalida.")
    if not 1 <= body.days <= 90:
        raise HTTPException(400, "days debe estar entre 1 y 90.")

    # Obtener activos de la org
    q = filter_by_org(db.query(Asset), Asset, current_user).filter(
        Asset.is_group_representative.is_(False)
    )
    if body.asset_ids:
        q = q.filter(Asset.id.in_(body.asset_ids))
    assets = q.limit(100).all()
    if not assets:
        raise HTTPException(404, "No se encontraron activos.")

    # Extraer keywords de software_tags para busqueda dirigida en NVD.
    # Los tags pueden tener formato LeanIX ("EA | APP | NombreSoftware") u otros
    # separadores (";", "/"). Extraemos tokens individuales significativos.
    _SKIP_TOKENS = {"app", "ea", "erp", "crm", "bi", "api", "ui", "db", "it",
                    "saas", "paas", "iaas", "cloud", "on", "premise", "the", "and",
                    "home", "apac", "emea", "amer", "global", "group", "corp"}

    def _extract_keywords(tags: list) -> list[str]:
        import re
        seen: set[str] = set()
        result: list[str] = []
        for raw in tags:
            # Dividir por separadores comunes en tags de LeanIX / sistemas internos
            parts = re.split(r'[|;/\\,\s]+', raw or "")
            for part in parts:
                word = part.strip().lower()
                # Filtrar: largo minimo 3, no token generico, solo alfanumerico con guion
                if (len(word) >= 3
                        and word not in _SKIP_TOKENS
                        and re.match(r'^[a-z0-9][a-z0-9\-\.]+$', word)
                        and word not in seen):
                    seen.add(word)
                    result.append(word)
        return result

    all_tags = _extract_keywords([t for a in assets for t in (a.software_tags or [])])

    # Buscar CVEs en NVD — una llamada por keyword (max 8 keywords distintas)
    cves_by_id: dict = {}
    if all_tags:
        for tag in all_tags[:8]:
            try:
                partial = cvs.fetch_recent(
                    api_key, days=body.days, severity=sev,
                    keyword=tag, max_results=20,
                )
                for c in partial:
                    if c["id"] not in cves_by_id:
                        cves_by_id[c["id"]] = c
                if len(cves_by_id) >= body.max_cves:
                    break
            except Exception as exc:
                logger.warning("NVD search keyword=%s: %s", tag, exc)

    if not cves_by_id:
        # Fallback: busqueda general sin keyword
        try:
            general = cvs.fetch_recent(
                api_key, days=body.days, severity=sev,
                max_results=min(body.max_cves, 50),
            )
            for c in general:
                cves_by_id[c["id"]] = c
        except ValueError as exc:
            raise HTTPException(502, str(exc))

    if not cves_by_id:
        return {
            "analyzed_pairs": 0,
            "cves_found": 0,
            "results": [],
            "message": (
                f"No se encontraron CVEs en los ultimos {body.days} dias "
                f"con severidad minima {body.severity}. "
                "Amplia la ventana de tiempo o reduce el filtro de severidad."
            ),
        }

    # Controles implementados para contexto de cobertura
    impls = filter_by_org(db.query(ControlImplementation), ControlImplementation, current_user).all()
    controls_context = [
        {
            "name": impl.name,
            "control_code": impl.control.code if impl.control else "",
            "status": impl.implementation_status.value if impl.implementation_status else "",
            "notes": (impl.notes or "")[:200],
        }
        for impl in impls
        if impl.implementation_status and impl.implementation_status.value in ("implemented", "partial")
    ]

    # Analisis CVE x Activo
    pairs_done = 0
    results = []

    for cve_id, cve in cves_by_id.items():
        for asset in assets:
            if pairs_done >= _MAX_ANALYSIS_PAIRS:
                break
            if not body.skip_heuristic:
                match_score = cvs.asset_matches_cve(
                    asset.name or "",
                    asset.description or "",
                    cve,
                )
                if cve.get("affected_products") and match_score < 0.15:
                    continue
            rag_ctx = get_rag_context(
                cve, {"name": asset.name, "description": asset.description or ""},
                organization_id=current_user.organization_id,
            )
            asset_dict = {
                "name": asset.name,
                "asset_type": asset.asset_type.value if asset.asset_type else "",
                "description": asset.description or "",
                "confidentiality": asset.value_confidentiality,
                "integrity": asset.value_integrity,
                "availability": asset.value_availability,
            }
            analysis = analyze_cve_asset(
                cve=cve, asset=asset_dict, controls=controls_context,
                rag_context=rag_ctx, api_key=ai_api_key,
            )
            results.append({
                "cve_id": cve_id,
                "cve": cve,
                "asset_id": asset.id,
                "asset_name": asset.name,
                "asset_type": asset_dict["asset_type"],
                "analysis": analysis,
            })
            pairs_done += 1
        if pairs_done >= _MAX_ANALYSIS_PAIRS:
            break

    log_action(db, current_user.id, "auto_scan", "cve", None, {
        "cves_found": len(cves_by_id),
        "asset_count": len(assets),
        "pairs_analyzed": pairs_done,
        "tags_used": all_tags[:8],
    })
    db.commit()

    return {
        "analyzed_pairs": pairs_done,
        "cves_found": len(cves_by_id),
        "results": results,
    }


@router.post("/create-risk")
def create_risk_from_cve(
    body: CreateRiskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Crea un Riesgo en RiskHub a partir del analisis de una CVE."""
    from app.models import Risk, RiskStatus, TreatmentOption, Threat, Vulnerability
    from app.services.risk_engine import calc_level, clamp
    from app.routers.risks import _next_code

    asset = filter_by_org(db.query(Asset).filter(Asset.id == body.asset_id), Asset, current_user).first()
    if not asset:
        raise HTTPException(404, "Activo no encontrado.")

    analysis = body.analysis
    cve = body.cve_data

    # --- Amenaza: threat_id es NOT NULL, siempre necesitamos una ---
    threat_name = (analysis.get("amenaza_sugerida") or "").strip()
    threat = None
    if threat_name:
        threat = db.query(Threat).filter(Threat.name.ilike(f"%{threat_name[:40]}%")).first()
    if not threat:
        # Fallback: buscar amenaza generica de explotacion de vulnerabilidades
        threat = db.query(Threat).filter(Threat.name.ilike("%vulnerabilidad%")).first()
    if not threat:
        threat = db.query(Threat).first()
    if not threat:
        raise HTTPException(400, "No hay amenazas en el catalogo. Crea al menos una amenaza antes de continuar.")

    # --- Vulnerabilidad: code es NOT NULL y UNIQUE ---
    # Usamos el CVE ID como codigo (maximo 32 chars)
    vuln_code = body.cve_id[:32]
    vuln_name = f"{body.cve_id} — CVSS {cve.get('cvss_score', '?')} ({cve.get('cvss_severity', 'N/A')})"
    vuln = db.query(Vulnerability).filter(Vulnerability.code == vuln_code).first()
    if not vuln:
        vuln = Vulnerability(
            code=vuln_code,
            name=vuln_name[:255],
            description=cve.get("description", "")[:1000],
            category="software",
            is_custom=True,
        )
        db.add(vuln)
        db.flush()

    # --- Verificar que no existe ya un riesgo para este par (asset, threat) ---
    existing = db.query(Risk).filter(
        Risk.asset_id == asset.id,
        Risk.threat_id == threat.id,
    ).first()
    if existing:
        return {
            "ok": True,
            "risk_id": existing.id,
            "risk_code": existing.code,
            "message": (
                f"Ya existe el riesgo {existing.code} para este activo y amenaza. "
                f"Se ha vinculado el CVE {body.cve_id} al riesgo existente."
            ),
        }

    # --- Mapeo de niveles IA (escala 1-5) a escala Risk (0-4) ---
    inherent_15 = int(analysis.get("riesgo_inherente") or cvs.score_to_risk_level(cve.get("cvss_score", 0)))
    residual_15 = int(analysis.get("riesgo_residual") or inherent_15)
    inh_04 = clamp(inherent_15 - 1)   # 1-5 → 0-4
    res_04 = clamp(residual_15 - 1)

    # --- Descripcion del riesgo ---
    actions_text = "\n".join(
        f"  [{a.get('control_iso', '')}] {a.get('accion', '')} ({a.get('prioridad', '')})"
        for a in (analysis.get("acciones_mitigacion") or [])[:5]
    )
    description = (
        f"CVE: {body.cve_id} | CVSS: {cve.get('cvss_score', '?')} ({cve.get('cvss_severity', '?')}) | "
        f"Vector: {cve.get('cvss_vector', '')}\n"
        f"Impacto en activo: {analysis.get('justificacion_afectacion', '')}\n"
        f"Cobertura de controles: {analysis.get('cobertura_controles', '')}\n"
        f"Acciones de mitigacion propuestas:\n{actions_text}"
    )

    # --- Crear el riesgo ---
    risk = Risk(
        code=_next_code(db),
        asset_id=asset.id,
        threat_id=threat.id,
        description=description[:2000],
        inherent_likelihood=inh_04,
        inherent_consequence=inh_04,
        inherent_level=calc_level(inh_04, inh_04),
        residual_likelihood=res_04,
        residual_consequence=res_04,
        residual_level=calc_level(res_04, res_04),
        treatment_option=TreatmentOption.MODIFICATION if res_04 >= 2 else None,
        status=RiskStatus.IDENTIFIED,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    db.add(risk)
    db.flush()

    # M2M: vincular vulnerabilidad al riesgo
    risk.vulnerabilities = [vuln]

    log_action(db, current_user.id, "create", "risk", None, {
        "source": "cve_analysis",
        "cve_id": body.cve_id,
        "asset_id": body.asset_id,
        "inherent_level": risk.inherent_level,
        "residual_level": risk.residual_level,
    })
    db.commit()
    db.refresh(risk)

    return {
        "ok": True,
        "risk_id": risk.id,
        "risk_code": risk.code,
        "message": f"Riesgo {risk.code} creado correctamente desde {body.cve_id}.",
    }
