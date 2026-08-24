"""Sincronizacion de los datos DRP de VisioX hacia el registro GRC.

Principio rector, el mismo del resto de la plataforma: la fuente externa APORTA
EVIDENCIA; el motor determinista de RiskHub decide. Este conector nunca calcula
un nivel de riesgo ni recalcula un residual — propone entradas y deja que
risk_engine / risk_recalc_service hagan su trabajo.

Tres decisiones que gobiernan el fichero:

1. UPSERT, NO SKIP. El importador generico (external_findings_service) descarta
   los duplicados sin actualizarlos. Para datos DRP eso es un fallo funcional:
   en VisioX el estado vive en bits mutables y el score lo reescribe un worker.
   Un dominio fraudulento dado de baja se quedaria abierto para siempre.

2. CIERRE NO DESTRUCTIVO. Un hallazgo que desaparece del origen solo se marca
   resuelto si el snapshot llego COMPLETO. Si VisioX estaba caido, lento o
   truncó la respuesta, no se cierra nada: la ausencia no prueba la resolucion.

3. LA PII VIAJA CIFRADA. VisioX marca con `sensitive` lo que transporta datos
   personales (credenciales de LeakX, snippets de foros, identidades de VipX).
   Esa evidencia se guarda en `evidence_encrypted` con Fernet y NUNCA se sirve
   en el listado ni entra en un prompt de la IA: exige una peticion explicita
   de un rol autorizado, que queda auditada.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Asset,
    AssetType,
    ExternalFinding,
    ExternalFindingSource,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IntegrationConfig,
    IntegrationSyncRun,
)
from app.services import visiox_service

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "visiox"
SOURCE = ExternalFindingSource.VISIOX.value

# Amenazas sinteticas: UNA por familia, no una por hallazgo. Con un threat_code
# por hallazgo, 8000 hallazgos meterian 8000 entradas basura en el catalogo y la
# dedupe por (activo, amenaza) dejaria de funcionar.
THREAT_CODES = {
    "asm_tls": "DRP-ASM-TLS",
    "asm_mail": "DRP-ASM-MAIL",
    "asm_domain": "DRP-ASM-DOMAIN",
    "leaked_credential": "DRP-LEAKX-CREDS",
    "brand_impersonation": "DRP-PHISHX-BRAND",
    "darkweb_mention": "DRP-DARKWEB",
    "vip_exposure": "DRP-VIPX",
}

# Tope de riesgos creados por ejecucion. Un mal dia en VisioX no puede inundar
# el registro de riesgos: el resto queda como hallazgo, visible y sin perder.
MAX_RISKS_PER_SYNC = 25

_SEVERITY_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


# ---------- credenciales ----------

def _fernet_key() -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())


def encrypt(plain: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_fernet_key()).encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_fernet_key()).decrypt(token.encode()).decode()


def get_config(db: Session, org_id: int) -> Optional[dict]:
    """Config de VisioX de una organizacion. Sin fallback global: una key de
    VisioX pertenece a UN cliente, y compartirla entre tenants seria una fuga."""
    ic = db.query(IntegrationConfig).filter_by(
        name=INTEGRATION_NAME, organization_id=org_id
    ).first()
    if not ic or not ic.config_encrypted:
        return None
    try:
        return json.loads(decrypt(ic.config_encrypted))
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo descifrar la config de VisioX de la org %s", org_id)
        return None


def save_config(db: Session, org_id: int, cfg: dict, user_id: Optional[int] = None) -> None:
    ic = db.query(IntegrationConfig).filter_by(
        name=INTEGRATION_NAME, organization_id=org_id
    ).first()
    if not ic:
        ic = IntegrationConfig(name=INTEGRATION_NAME, organization_id=org_id)
        db.add(ic)
    ic.config_encrypted = encrypt(json.dumps(cfg))
    ic.updated_by_id = user_id
    db.commit()


# ---------- sincronizacion ----------

def sync_organization(
    db: Session,
    org_id: int,
    triggered_by: str = "scheduler",
    triggered_by_id: Optional[int] = None,
) -> dict:
    """Sincroniza los datos DRP de una organizacion. Nunca lanza: cualquier
    fallo se registra en el IntegrationSyncRun y se devuelve como estado."""
    started = datetime.now(timezone.utc)
    run = IntegrationSyncRun(
        organization_id=org_id,
        integration=INTEGRATION_NAME,
        status="running",
        started_at=started,
        triggered_by=triggered_by,
        triggered_by_id=triggered_by_id,
    )
    db.add(run)
    db.commit()

    try:
        cfg = get_config(db, org_id)
        if not cfg or not cfg.get("api_key"):
            raise visiox_service.VisioXError("La integracion con VisioX no esta configurada")

        api_key = cfg["api_key"]
        base_url = cfg.get("base_url") or visiox_service.DEFAULT_BASE_URL

        # 1. Inventario primero: los hallazgos se enlazan mejor si el activo ya existe.
        if cfg.get("create_assets", True):
            run.assets_created = _sync_assets(db, org_id, base_url, api_key)

        # 2. Hallazgos.
        items, complete, pages = visiox_service.fetch_findings(base_url, api_key)
        run.pages_fetched = pages
        run.items_read = len(items)
        run.complete = complete

        stats = _upsert_findings(db, org_id, items)
        run.created = stats["created"]
        run.updated = stats["updated"]

        # 3. Cierre: SOLO si el snapshot es integro.
        if complete:
            run.closed = _close_missing(db, org_id, {i["external_id"] for i in items})
        else:
            logger.warning(
                "VisioX org=%s: snapshot incompleto (%d paginas), no se cierra nada",
                org_id, pages,
            )

        # 4. Reglas de negocio sobre lo NUEVO de esta ejecucion.
        rules = _apply_business_rules(db, org_id, stats["new_ids"])
        run.risks_created = rules["risks"]
        run.incidents_created = rules["incidents"]

        run.status = "ok"
    except visiox_service.VisioXError as exc:
        db.rollback()
        run = db.get(IntegrationSyncRun, run.id)
        run.status = "error"
        run.error_message = str(exc)[:2000]
        logger.warning("Sync de VisioX fallido para la org %s: %s", org_id, exc)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.get(IntegrationSyncRun, run.id)
        run.status = "error"
        run.error_message = f"Error inesperado: {exc}"[:2000]
        logger.exception("Sync de VisioX rompio para la org %s", org_id)

    run.finished_at = datetime.now(timezone.utc)
    run.duration_ms = int((run.finished_at - started).total_seconds() * 1000)
    db.commit()

    return {
        "status": run.status,
        "items_read": run.items_read or 0,
        "created": run.created or 0,
        "updated": run.updated or 0,
        "closed": run.closed or 0,
        "assets_created": run.assets_created or 0,
        "risks_created": run.risks_created or 0,
        "incidents_created": run.incidents_created or 0,
        "complete": bool(run.complete),
        "duration_ms": run.duration_ms,
        "error": run.error_message,
    }


def _sync_assets(db: Session, org_id: int, base_url: str, api_key: str) -> int:
    """Da de alta como activos los dominios que VisioX ya inventaria.

    Se marcan con extra.visiox_external_id para que reimportar no duplique y
    para que se sepa que no los dio de alta una persona: quedan SIN valoracion
    CIA a proposito, porque valorarlos es una decision de negocio que ningun
    conector puede tomar. Aparecen en el inventario como trabajo pendiente.
    """
    created = 0
    offset = 0
    while True:
        payload = visiox_service._request(
            base_url, api_key, "/api/v1/svc/assets", {"limit": 500, "offset": offset}
        )
        rows = payload.get("data") or []
        if not rows:
            break

        for row in rows:
            ext_id = row.get("external_id")
            name = (row.get("name") or "").strip().lower()
            if not ext_id or not name:
                continue

            existing = db.query(Asset).filter(
                Asset.organization_id == org_id,
                Asset.name == name,
            ).first()
            if existing:
                # Sella la procedencia sin tocar nada mas: si alguien ya lo dio
                # de alta a mano, su valoracion y su propietario mandan.
                extra = dict(existing.extra or {})
                if not extra.get("visiox_external_id"):
                    extra["visiox_external_id"] = ext_id
                    extra["visiox_synced_at"] = datetime.now(timezone.utc).isoformat()
                    existing.extra = extra
                continue

            asset = Asset(
                organization_id=org_id,
                code=_next_asset_code(db),
                name=name,
                description=_describe_asset(row),
                asset_type=AssetType.SUPPORT_NETWORK,
                category="Dominio",
                classification="publico",
                extra={
                    "visiox_external_id": ext_id,
                    "visiox_synced_at": datetime.now(timezone.utc).isoformat(),
                    "brand": row.get("brand"),
                    "is_primary": row.get("is_primary"),
                    "registrar": row.get("registrar"),
                    "expires_at": row.get("expires_at"),
                    "handles_mail": row.get("handles_mail"),
                    "hygiene_score": row.get("hygiene_score"),
                },
            )
            db.add(asset)
            db.flush()
            created += 1

        if payload.get("complete") or not payload.get("next_offset"):
            break
        offset = payload["next_offset"]

    db.commit()
    return created


def _describe_asset(row: dict) -> str:
    bits = ["Dominio inventariado automaticamente desde VisioX (DRP)."]
    if row.get("brand"):
        bits.append(f"Marca: {row['brand']}.")
    if row.get("is_primary"):
        bits.append("Dominio principal de la marca.")
    if row.get("registrar"):
        bits.append(f"Registrador: {row['registrar']}.")
    if row.get("expires_at"):
        bits.append(f"Caduca: {str(row['expires_at'])[:10]}.")
    if row.get("handles_mail"):
        bits.append("Con registros MX (maneja correo).")
    bits.append("Pendiente de valoracion CIA y de asignar propietario.")
    return " ".join(bits)[:2000]


def _next_asset_code(db: Session) -> str:
    """Codigo AST-XXXX. El unique es global, asi que se cuenta sobre toda la
    tabla y se busca hueco: dos organizaciones no pueden compartir codigo."""
    n = db.query(Asset).count() + 1
    while db.query(Asset).filter(Asset.code == f"AST-{n:04d}").first():
        n += 1
    return f"AST-{n:04d}"


def _upsert_findings(db: Session, org_id: int, items: list[dict]) -> dict:
    """Inserta o ACTUALIZA por (org, source, external_id). Devuelve los ids de
    los hallazgos nuevos, que son los unicos sobre los que actuan las reglas."""
    from app.services.external_findings_service import _match_asset

    stats = {"created": 0, "updated": 0, "new_ids": []}
    now = datetime.now(timezone.utc)

    existing_map = {
        f.external_id: f
        for f in db.query(ExternalFinding).filter(
            ExternalFinding.organization_id == org_id,
            ExternalFinding.source == SOURCE,
        ).all()
    }

    for item in items:
        ext_id = item.get("external_id")
        if not ext_id:
            continue

        sensitive = bool(item.get("sensitive"))
        evidence = item.get("evidence") or {}
        evidence_raw = json.dumps(evidence, ensure_ascii=False, default=str)[:20000]

        host = (item.get("affected_host") or "")[:512] or None
        detected = _parse_dt(item.get("detected_at")) or now

        f = existing_map.get(ext_id)
        if f is None:
            asset = _match_asset(db, org_id, {"affected_host": host or ""})
            f = ExternalFinding(
                organization_id=org_id,
                source=SOURCE,
                external_id=ext_id[:256],
                asset_id=asset.id if asset else None,
                import_batch_id=None,
                created_at=now,
            )
            db.add(f)
            stats["created"] += 1
            is_new = True
        else:
            stats["updated"] += 1
            is_new = False

        f.title = (item.get("title") or "")[:512]
        f.description = (item.get("description") or "")[:2000] or None
        f.severity = item.get("severity") or "MEDIUM"
        f.finding_type = (item.get("finding_type") or item.get("module") or "")[:64] or None
        f.affected_host = host
        f.iso_control = (item.get("iso_control") or "")[:32] or None
        f.external_url = (item.get("external_url") or "")[:512] or None
        f.detected_at = detected
        f.last_seen_at = now
        f.is_sensitive = sensitive

        # La evidencia va a un campo o al otro, nunca a los dos: si se guardase
        # tambien en claro "por comodidad", el cifrado no serviria de nada.
        if sensitive:
            f.evidence_encrypted = encrypt(evidence_raw)
            f.evidence_json = json.dumps(_public_part(evidence), ensure_ascii=False, default=str)
            f.raw_data = None
        else:
            f.evidence_json = evidence_raw
            f.evidence_encrypted = None
            f.raw_data = None

        # Reabrir lo que la fuente vuelve a reportar: si sigue ahi, no esta resuelto.
        if f.status == "resolved":
            f.status = "open"
            f.resolved_at = None
        elif not f.status:
            f.status = "open"

        db.flush()
        if is_new:
            stats["new_ids"].append(f.id)

    db.commit()
    return stats


# Claves de evidencia que NO son datos personales y pueden vivir en claro: son
# las que necesita la UI para explicar el hallazgo sin revelar a nadie.
_PUBLIC_EVIDENCE_KEYS = {
    "asset_class", "brand", "password_strength", "is_email", "unlocked",
    "status", "critical_host", "source", "keyword_matched", "posted_at",
    "acked", "hit_count", "last_hit_at", "department", "seniority", "country",
    "role", "flag", "is_primary", "asm_risk_score", "registrar",
}


def _public_part(evidence: dict) -> dict:
    """Subconjunto de la evidencia sin datos personales, apto para el listado."""
    return {k: v for k, v in evidence.items() if k in _PUBLIC_EVIDENCE_KEYS}


def _parse_dt(raw) -> Optional[datetime]:
    if not raw:
        return None
    try:
        s = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _close_missing(db: Session, org_id: int, seen_ids: set[str]) -> int:
    """Marca resueltos los hallazgos que ya no reporta la fuente.

    Solo se llama con un snapshot COMPLETO. No borra: deja la fila con
    resolved_at para que quede la historia y se pueda medir el tiempo de cierre.
    """
    # Sin guard por lista vacia: un snapshot COMPLETO con cero hallazgos es una
    # afirmacion legitima de la fuente ("ya no queda nada abierto") y hay que
    # respetarla. La proteccion contra el borrado en masa por un fallo es
    # `complete`, que se comprueba antes de llamar aqui, no el tamano del lote.
    now = datetime.now(timezone.utc)
    closed = 0
    rows = db.query(ExternalFinding).filter(
        ExternalFinding.organization_id == org_id,
        ExternalFinding.source == SOURCE,
        ExternalFinding.status == "open",
    ).all()
    for f in rows:
        if f.external_id not in seen_ids:
            f.status = "resolved"
            f.resolved_at = now
            closed += 1
    db.commit()
    if rows and closed == len(rows) and closed > 10:
        logger.warning(
            "VisioX org=%s: se han cerrado los %d hallazgos abiertos de golpe. "
            "Es correcto si la fuente ya no reporta nada, pero conviene revisarlo.",
            org_id, closed,
        )
    return closed


def _apply_business_rules(db: Session, org_id: int, new_ids: list[int]) -> dict:
    """Convierte los hallazgos NUEVOS en informacion GRC.

    Solo actua sobre lo nuevo: reaplicar las reglas en cada sync sobre todo el
    corpus abriria el mismo incidente cada seis horas.
    """
    out = {"risks": 0, "incidents": 0}
    if not new_ids:
        return out

    from app.models import Risk
    from app.services.risk_auto_generator import auto_generate_risk_from_finding

    findings = db.query(ExternalFinding).filter(ExternalFinding.id.in_(new_ids)).all()

    # auto_generate_risk_from_finding devuelve el riesgo YA EXISTENTE cuando el
    # par (activo, amenaza) esta cubierto, que es lo correcto. Pero contar esas
    # llamadas como creaciones hace que el informe diga 25 riesgos nuevos donde
    # solo hay 13: se cuenta el delta real de la tabla, no las llamadas.
    risks_before = db.query(Risk).filter(Risk.organization_id == org_id).count()

    # --- Riesgos: solo severidad alta y con activo casado ---
    severe = [
        f for f in findings
        if f.severity in ("HIGH", "CRITICAL") and f.asset_id
    ]
    severe.sort(key=lambda f: -_SEVERITY_ORDER.get(f.severity, 0))

    for f in severe[:MAX_RISKS_PER_SYNC]:
        threat_code = THREAT_CODES.get(f.finding_type or "", "DRP-EXPOSURE")
        consequence = 4 if f.severity == "CRITICAL" else 3
        # La probabilidad no es una opinion: si la contrasena ya circula, la
        # explotacion no es hipotetica.
        likelihood = 4 if f.finding_type == "leaked_credential" else 3
        try:
            risk = auto_generate_risk_from_finding(
                db,
                asset_id=f.asset_id,
                title=f.title or "Exposicion detectada por VisioX",
                description=(f.description or f.title or "")[:2000],
                threat_code=threat_code,
                inherent_consequence=consequence,
                inherent_likelihood=likelihood,
            )
            if risk:
                f.risk_id = risk.id
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo generar el riesgo del hallazgo %s", f.id)

    db.flush()
    out["risks"] = db.query(Risk).filter(Risk.organization_id == org_id).count() - risks_before

    # --- Incidente: como MUCHO uno por ejecucion, con los criticos agrupados ---
    criticals = [f for f in findings if f.severity == "CRITICAL" and not f.incident_id]
    if criticals:
        try:
            incident = _create_incident(db, org_id, criticals)
            if incident:
                for f in criticals:
                    f.incident_id = incident.id
                out["incidents"] = 1
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo crear el incidente DRP de la org %s", org_id)

    db.commit()

    # Marcar como desactualizados los riesgos de los activos tocados: el
    # conector NUNCA recalcula un residual, eso es competencia exclusiva de
    # risk_recalc_service. Solo avisa de que hay que revisar.
    try:
        from app.services.risk_recalc_service import mark_risks_stale_for_asset
        for asset_id in {f.asset_id for f in findings if f.asset_id}:
            mark_risks_stale_for_asset(db, asset_id, "Nuevo hallazgo DRP de VisioX")
        db.commit()
    except (ImportError, AttributeError):
        pass
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo marcar el desfase de riesgos tras el sync de VisioX")

    return out


def _create_incident(db: Session, org_id: int, findings: list[ExternalFinding]) -> Optional[Incident]:
    """Un unico incidente con todos los hallazgos criticos del lote.

    La relacion es por clave ajena (ExternalFinding.incident_id), no por un
    marcador embebido en el texto de la descripcion: asi se puede navegar del
    incidente a sus hallazgos y la dedupe no depende de un LIKE.
    """
    now = datetime.now(timezone.utc)
    kinds = sorted({f.finding_type or "drp" for f in findings})
    hosts = sorted({f.affected_host for f in findings if f.affected_host})[:20]

    p1 = any(
        f.finding_type in ("leaked_credential", "darkweb_mention") for f in findings
    )
    severity = IncidentSeverity.P1 if p1 else IncidentSeverity.P2

    lines = [
        f"Se han detectado {len(findings)} exposiciones criticas en la vigilancia "
        f"de riesgo digital (VisioX).",
        "",
        f"Tipos: {', '.join(kinds)}.",
    ]
    if hosts:
        lines.append(f"Activos o dominios afectados: {', '.join(hosts)}.")
    lines += [
        "",
        "Detalle de los hallazgos:",
    ]
    for f in findings[:30]:
        lines.append(f"  - [{f.severity}] {f.title}")
    if len(findings) > 30:
        lines.append(f"  ... y {len(findings) - 30} mas.")

    incident = Incident(
        organization_id=org_id,
        code=_next_incident_code(db),
        title=f"Exposicion digital critica detectada ({len(findings)} hallazgos)",
        description="\n".join(lines)[:4000],
        severity=severity,
        status=IncidentStatus.OPEN,
        detected_at=now,
        nis2_notification_required=(severity == IncidentSeverity.P1),
        affected_systems=hosts or None,
        affected_asset_ids=sorted({f.asset_id for f in findings if f.asset_id}) or None,
    )
    db.add(incident)
    db.flush()
    return incident


def _next_incident_code(db: Session) -> str:
    n = db.query(Incident).count() + 1
    while db.query(Incident).filter(Incident.code == f"INC-{n:04d}").first():
        n += 1
    return f"INC-{n:04d}"


def orgs_with_visiox(db: Session) -> list[int]:
    """Organizaciones con la integracion configurada. Lo usa el scheduler para
    no aplicar una config global a todos los tenants."""
    rows = db.query(IntegrationConfig).filter(
        IntegrationConfig.name == INTEGRATION_NAME,
        IntegrationConfig.organization_id.isnot(None),
        IntegrationConfig.config_encrypted.isnot(None),
    ).all()
    return [r.organization_id for r in rows]
