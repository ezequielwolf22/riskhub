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
    Risk, RiskStatus, TreatmentOption,
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

_RISK_SYSTEM_PROMPT = """Eres un experto en analisis de riesgos de seguridad de la informacion
aplicando metodologia ISO/IEC 27005:2018 y MAGERIT v3.

Para el activo que te voy a describir, analiza que amenazas del catalogo son REALMENTE APLICABLES
y realiza el analisis de riesgo completo para cada una.

Escala de valoracion:
- Likelihood (probabilidad): 0=muy improbable, 1=improbable, 2=posible, 3=probable, 4=muy probable
- Consequence (impacto): 0=insignificante, 1=menor, 2=moderado, 3=mayor, 4=critico

Para calcular consequence, ten en cuenta los valores CIA del activo:
- Valor C/I/D 0=nulo, 1=bajo, 2=medio, 3=alto, 4=muy alto
- El impacto de la amenaza depende de a que dimension CIA afecta la amenaza

Para cada control existente que mitigues, estima:
- contribution (0.0-1.0): cuanto reduce este control el riesgo
- Ten en cuenta su estado: implemented > partial > planned
- Ten en cuenta su madurez (0-5)

Para el calculo residual aplica la reduccion de controles:
- residual_likelihood: segun reduccion de controles preventivos
- residual_consequence: segun reduccion de controles correctivos/recuperacion
- Solo incluye controles realmente relevantes para la amenaza concreta

Devuelve UNICAMENTE JSON valido con esta estructura exacta:
[
  {
    "threat_code": "<codigo de la amenaza>",
    "applies": true,
    "inherent_likelihood": <0-4>,
    "inherent_consequence": <0-4>,
    "rationale": "<justificacion concisa en espanol, max 150 palabras>",
    "consequence_description": "<descripcion del impacto concreto sobre este activo>",
    "vulnerability_codes": ["<codigo>", ...],
    "control_contributions": [
      {"impl_id": <id de ControlImplementation>, "contribution": <0.0-1.0>}
    ],
    "residual_likelihood": <0-4>,
    "residual_consequence": <0-4>,
    "treatment_option": "<modification|retention|avoidance|sharing>"
  }
]

REGLAS:
- Solo incluye amenazas donde applies=true y el riesgo inherente sea >= 1 en likelihood o consequence.
- No incluyas amenazas trivialmente inaplicables.
- Usa los codigos exactos del catalogo proporcionado.
- control_contributions: solo controles que realmente mitigan la amenaza especifica.
- treatment_option: modification si hay controles que reducen; retention si riesgo es bajo y se acepta;
  avoidance si el riesgo es inaceptable; sharing si es transferible a seguro/proveedor.
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


def _threats_for_asset(db: Session, asset_type: str) -> list[Threat]:
    """Filtra amenazas del catalogo aplicables al tipo de activo."""
    keys = _ASSET_TYPE_KEYS.get(asset_type, [asset_type])
    all_threats = db.query(Threat).all()
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

        # 1. Obtener catalogo filtrado
        threats = _threats_for_asset(db, asset.asset_type.value if asset.asset_type else "")
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

        user_content = (
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

        risk_items = json.loads(raw_json)
        owner_id = _org_owner_id(db, asset.organization_id)

        # 5. Procesar cada riesgo devuelto
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

        asset.ai_risk_status = "analysed"
        asset.ai_risk_summary = {
            "risks_created": created,
            "risks_updated": updated,
            "threats_analysed": len(threats),
            "summary": f"{created} riesgos creados, {updated} actualizados a partir de {len(threats)} amenazas analizadas.",
        }
        db.commit()
        logger.info("Risk analysis OK asset=%d created=%d updated=%d", asset_id, created, updated)

    except Exception as exc:
        logger.error("Risk analysis failed asset=%d: %s", asset_id, exc)
        try:
            asset.ai_risk_status = "error"
            asset.ai_risk_summary = {"error": str(exc)[:500]}
            db.commit()
        except Exception:
            pass


def analyze_all_org_assets(db: Session, org_id: int) -> dict:
    """Lanza el analisis de todos los activos de la organizacion."""
    assets = db.query(Asset).filter_by(organization_id=org_id).all()
    total = len(assets)
    for asset in assets:
        try:
            analyze_asset_risks(db, asset.id)
        except Exception as exc:
            logger.error("Bulk analysis failed asset=%d: %s", asset.id, exc)
    return {"total": total, "message": f"Analisis lanzado para {total} activos."}


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
                inherent_level=calc_level(inh_con, inh_lik),
                residual_likelihood=inh_lik,
                residual_consequence=inh_con,
                residual_level=calc_level(inh_con, inh_lik),
                status=RiskStatus.IDENTIFIED,
                owner_id=owner_id,
                ai_generated=True,
                ai_rationale=f"Generado desde hallazgo OSINT [{finding.source.value if finding.source else '?'}]: {finding.title[:100]}",
            )
            db.add(risk)
            created += 1

    if created > 0:
        db.commit()
    return {"created": created}
