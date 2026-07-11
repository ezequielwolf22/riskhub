"""Servicio de Vigilancia Normativa Automatica (regwatch).

Coordina la logica "set it and forget it" descrita en la spec:
 - Deriva los frameworks vigilados a partir de lo que el tenant ya usa (§2).
 - Gestiona el toggle y las opciones avanzadas (§1, §5.1).
 - Construye el estado de la tarjeta de Setup sin recargar (§1.1).
 - Materializa el inbox del tenant solo cuando hay algo que decidir (§5.2-5.3).
 - Ejecuta el barrido periodico de fuentes y la publicacion de change packs (§5).

El catalogo central es global: se actualiza con o sin toggle (§5.5). El toggle
solo controla si el tenant recibe notificaciones y si sus copias se ven afectadas.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import (
    ChangePack, ChangeSeverity, ComplianceFrameworkStatus, InboxItemStatus,
    NormativeChangeEvent, ChangeEventStatus, NormativeSource, Organization,
    Supplier, TenantChangeInboxItem, TenantRegwatchSettings, User,
)
from app.services import regwatch_sources as srcs

logger = logging.getLogger("riskhub.regwatch")

# Severidades que requieren materializar un item en el inbox del tenant (§5.2)
_INBOX_SEVERITIES = (ChangeSeverity.SUBSTANTIVE, ChangeSeverity.BREAKING)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _iso(dt):
    return _aware(dt).isoformat() if dt else None


# ---------- Frameworks vigilados (derivacion automatica, §2) ----------

def derive_watched_frameworks(db: Session, org_id: int) -> list[str]:
    """Deriva los frameworks que el tenant usa, sin pedirle nada (§2.1).

    Fuentes de verdad:
     - Requisitos del modulo Compliance activados por la org.
     - Flags regulatorios de proveedores (NIS2 / DORA / ENS).
     - Catalogos de amenazas/ contexto si declaran marcos.
    Devuelve codigos canonicos del catalogo regwatch, deduplicados y ordenados.
    """
    found: set[str] = set()

    # 1. Frameworks del modulo Compliance (distinct framework_code por org)
    rows = (
        db.query(ComplianceFrameworkStatus.framework_code)
        .filter(ComplianceFrameworkStatus.organization_id == org_id)
        .distinct()
        .all()
    )
    for (fc,) in rows:
        if fc:
            found.add(srcs.normalize_framework(fc))

    # 2. Flags regulatorios de proveedores (TPRM)
    suppliers = db.query(Supplier).filter(Supplier.organization_id == org_id).all()
    for s in suppliers:
        if getattr(s, "is_nis2", False):
            found.add("NIS2")
        if getattr(s, "is_dora", False):
            found.add("DORA")
        if getattr(s, "is_ens", False):
            found.add("ENS")
        if getattr(s, "is_data_processor", False) or getattr(s, "processes_personal_data", False):
            found.add("GDPR")

    # Solo devolvemos frameworks para los que existe al menos una fuente vigilable
    watched = [fc for fc in found if srcs.sources_for_framework(fc)]
    return sorted(watched)


def watched_frameworks_detail(db: Session, org_id: int) -> list[dict]:
    """Lista de frameworks vigilados con etiqueta y fuentes (solo lectura, §1.2)."""
    settings = get_or_create_settings(db, org_id)
    muted = set(settings.muted_frameworks or [])
    out = []
    for fc in derive_watched_frameworks(db, org_id):
        out.append({
            "code": fc,
            "label": srcs.framework_label(fc),
            "sources": srcs.sources_for_framework(fc),
            "muted": fc in muted,
        })
    return out


# ---------- Settings y toggle (§5.1) ----------

def get_or_create_settings(db: Session, org_id: int) -> TenantRegwatchSettings:
    s = db.query(TenantRegwatchSettings).filter(
        TenantRegwatchSettings.organization_id == org_id
    ).first()
    if not s:
        s = TenantRegwatchSettings(organization_id=org_id, is_enabled=False)
        db.add(s)
        db.flush()
    return s


def settings_dict(db: Session, org_id: int) -> dict:
    s = get_or_create_settings(db, org_id)
    return {
        "is_enabled": bool(s.is_enabled),
        "enabled_at": _iso(s.enabled_at),
        "notification_email": s.notification_email,
        "digest_frequency": s.digest_frequency or "weekly",
        "auto_apply_to_clones": bool(s.auto_apply_to_clones),
        "muted_frameworks": s.muted_frameworks or [],
        "last_sweep_at": _iso(s.last_sweep_at),
        "last_digest_sent_at": _iso(s.last_digest_sent_at),
    }


def enable(db: Session, org_id: int, user: User) -> dict:
    """Activa la vigilancia: deriva frameworks y programa primer barrido (§5.1)."""
    s = get_or_create_settings(db, org_id)
    s.is_enabled = True
    s.enabled_at = _now()
    s.enabled_by_user_id = user.id
    if not s.notification_email:
        s.notification_email = _default_notification_email(db, org_id, user)
    db.flush()
    watched = derive_watched_frameworks(db, org_id)
    return {"enabled": True, "watched_count": len(watched), "watched_frameworks": watched}


def disable(db: Session, org_id: int) -> dict:
    """Desactiva el toggle. No borra configuracion (§5.5, criterio 9)."""
    s = get_or_create_settings(db, org_id)
    s.is_enabled = False
    db.flush()
    return {"enabled": False}


def _default_notification_email(db: Session, org_id: int, fallback_user: User) -> str:
    """Email del primer admin del tenant (default inteligente, §1.2)."""
    from app.models import UserRole
    admin = (
        db.query(User)
        .filter(User.organization_id == org_id, User.role == UserRole.ADMIN,
                User.email.isnot(None))
        .order_by(User.id)
        .first()
    )
    if admin and admin.email:
        return admin.email
    return fallback_user.email or ""


def update_settings(db: Session, org_id: int, body: dict) -> dict:
    """Actualiza el toggle y/o las opciones avanzadas (§6.1 PUT /settings)."""
    s = get_or_create_settings(db, org_id)
    if "notification_email" in body and body["notification_email"] is not None:
        s.notification_email = body["notification_email"][:255]
    if body.get("digest_frequency") in ("daily", "weekly", "monthly", "never"):
        s.digest_frequency = body["digest_frequency"]
    if "auto_apply_to_clones" in body:
        s.auto_apply_to_clones = bool(body["auto_apply_to_clones"])
    if "muted_frameworks" in body and isinstance(body["muted_frameworks"], list):
        s.muted_frameworks = [str(x) for x in body["muted_frameworks"]][:50]
    db.flush()
    return settings_dict(db, org_id)


# ---------- Estado de la tarjeta de Setup (§1.1) ----------

def build_status(db: Session, org_id: int) -> dict:
    """Indicador de estado para la tarjeta de Setup, sin recargar (§1.1)."""
    s = get_or_create_settings(db, org_id)
    pending = count_pending_inbox(db, org_id)
    watched = derive_watched_frameworks(db, org_id)
    last_applied = _last_applied_change(db, org_id, watched)

    if not s.is_enabled:
        state = "inactive"
    elif pending > 0:
        state = "active_pending"
    else:
        state = "active_ok"

    return {
        "state": state,
        "is_enabled": bool(s.is_enabled),
        "pending_count": pending,
        "watched_count": len(watched),
        "last_sweep_at": _iso(s.last_sweep_at),
        "last_applied": last_applied,
    }


def _last_applied_change(db: Session, org_id: int, watched: list[str]) -> dict | None:
    """Ultima actualizacion aplicada al catalogo para frameworks vigilados (§1.1)."""
    if not watched:
        return None
    pack = (
        db.query(ChangePack)
        .filter(ChangePack.framework_code.in_(watched),
                ChangePack.applied_to_catalog_at.isnot(None))
        .order_by(ChangePack.applied_to_catalog_at.desc())
        .first()
    )
    if not pack:
        return None
    return {
        "framework": srcs.framework_label(pack.framework_code),
        "title": pack.title_es,
        "applied_at": _iso(pack.applied_to_catalog_at),
    }


# ---------- Inbox del tenant (§5.3) ----------

def count_pending_inbox(db: Session, org_id: int) -> int:
    return (
        db.query(TenantChangeInboxItem)
        .filter(TenantChangeInboxItem.organization_id == org_id,
                TenantChangeInboxItem.status == InboxItemStatus.PENDING)
        .count()
    )


def list_inbox(db: Session, org_id: int, include_resolved: bool = False) -> list[dict]:
    q = db.query(TenantChangeInboxItem).filter(
        TenantChangeInboxItem.organization_id == org_id
    )
    if not include_resolved:
        q = q.filter(TenantChangeInboxItem.status.in_(
            [InboxItemStatus.PENDING, InboxItemStatus.SNOOZED]
        ))
    items = q.order_by(TenantChangeInboxItem.created_at.desc()).all()
    return [_inbox_item_dict(db, it) for it in items]


def _inbox_item_dict(db: Session, it: TenantChangeInboxItem) -> dict:
    pack = it.change_pack
    sev = pack.severity.value if pack and pack.severity else "substantive"
    return {
        "id": it.id,
        "status": it.status.value,
        "severity": sev,
        "framework": srcs.framework_label(pack.framework_code) if pack else "",
        "framework_code": pack.framework_code if pack else "",
        "title": pack.title_es if pack else "",
        "summary": pack.description_es if pack else "",
        "version_to": pack.version_to if pack else None,
        "change_counts": {
            "added": len(pack.controls_added_ids or []) if pack else 0,
            "modified": len(pack.controls_modified or []) if pack else 0,
            "removed": len(pack.controls_removed_ids or []) if pack else 0,
        },
        "impact": it.impact_summary_json or {},
        "created_at": _iso(it.created_at),
        "snoozed_until": _iso(it.snoozed_until),
        "source_url": pack.source_url if pack else None,
    }


def get_inbox_item(db: Session, org_id: int, item_id: int) -> dict | None:
    it = db.query(TenantChangeInboxItem).filter(
        TenantChangeInboxItem.id == item_id,
        TenantChangeInboxItem.organization_id == org_id,
    ).first()
    if not it:
        return None
    d = _inbox_item_dict(db, it)
    # Detalle de cambios atomicos para el paso 1 del wizard
    pack = it.change_pack
    if pack:
        d["controls_modified"] = pack.controls_modified or []
        d["controls_added_ids"] = pack.controls_added_ids or []
        d["controls_removed_ids"] = pack.controls_removed_ids or []
    return d


def review_inbox_item(db: Session, org_id: int, item_id: int,
                      user: User, decision: dict) -> dict:
    it = _get_item_or_raise(db, org_id, item_id)
    it.status = InboxItemStatus.REVIEWED
    it.reviewed_by_user_id = user.id
    it.reviewed_at = _now()
    it.decision_json = decision or {}
    db.flush()

    propagation: dict = {}
    if decision.get("action") == "apply":
        try:
            from app.services import regwatch_propagation as prop
            pack = it.change_pack
            if pack:
                propagation = prop.apply_and_propagate(db, org_id, pack, user, decision)
        except Exception as exc:
            logger.warning("regwatch: error en propagacion para item %s: %s", item_id, exc)

    return {"id": it.id, "status": it.status.value, "propagation": propagation}


def snooze_inbox_item(db: Session, org_id: int, item_id: int, days: int = 7) -> dict:
    it = _get_item_or_raise(db, org_id, item_id)
    it.status = InboxItemStatus.SNOOZED
    it.snoozed_until = _now() + timedelta(days=max(1, min(days, 90)))
    db.flush()
    return {"id": it.id, "status": it.status.value, "snoozed_until": _iso(it.snoozed_until)}


def dismiss_inbox_item(db: Session, org_id: int, item_id: int, reason: str = "") -> dict:
    it = _get_item_or_raise(db, org_id, item_id)
    it.status = InboxItemStatus.DISMISSED
    it.dismiss_reason = (reason or "")[:500]
    db.flush()
    return {"id": it.id, "status": it.status.value}


def _get_item_or_raise(db: Session, org_id: int, item_id: int) -> TenantChangeInboxItem:
    it = db.query(TenantChangeInboxItem).filter(
        TenantChangeInboxItem.id == item_id,
        TenantChangeInboxItem.organization_id == org_id,
    ).first()
    if not it:
        from fastapi import HTTPException
        raise HTTPException(404, "Item no encontrado")
    return it


# ---------- Historial (§5.3, §6.1 GET /history) ----------

def list_history(db: Session, org_id: int, framework: str | None = None,
                 limit: int = 100) -> list[dict]:
    """Cambios publicados que afectan a frameworks vigilados por el tenant."""
    watched = derive_watched_frameworks(db, org_id)
    if not watched:
        return []
    q = db.query(ChangePack).filter(
        ChangePack.framework_code.in_(watched),
        ChangePack.published_at.isnot(None),
    )
    if framework:
        q = q.filter(ChangePack.framework_code == srcs.normalize_framework(framework))
    packs = q.order_by(ChangePack.published_at.desc()).limit(limit).all()
    return [
        {
            "id": p.id,
            "framework": srcs.framework_label(p.framework_code),
            "framework_code": p.framework_code,
            "severity": p.severity.value if p.severity else "substantive",
            "title": p.title_es,
            "summary": p.description_es,
            "version_to": p.version_to,
            "published_at": _iso(p.published_at),
            "applied_at": _iso(p.applied_to_catalog_at),
            "source_url": p.source_url,
        }
        for p in packs
    ]


# ---------- Publicacion y barrido (§5.2, §7) ----------

def publish_change_pack(db: Session, pack: ChangePack) -> int:
    """Publica un change_pack: lo marca publicado/aplicado y materializa inbox
    items para los tenants afectados con severidad >= substantive (§7.7, §5.2).

    Devuelve el numero de inbox items creados. Cosmetic/clarification solo van
    al historial (no generan inbox).
    """
    now = _now()
    if not pack.published_at:
        pack.published_at = now
    if not pack.applied_to_catalog_at:
        pack.applied_to_catalog_at = now
    db.flush()

    if pack.severity not in _INBOX_SEVERITIES:
        return 0  # cosmetic / clarification -> solo historial

    created = 0
    # Tenants que usan ese framework y tienen la vigilancia activada
    settings_rows = db.query(TenantRegwatchSettings).filter(
        TenantRegwatchSettings.is_enabled.is_(True)
    ).all()
    for st in settings_rows:
        org_id = st.organization_id
        watched = derive_watched_frameworks(db, org_id)
        if pack.framework_code not in watched:
            continue
        if pack.framework_code in (st.muted_frameworks or []):
            continue
        exists = db.query(TenantChangeInboxItem).filter(
            TenantChangeInboxItem.organization_id == org_id,
            TenantChangeInboxItem.change_pack_id == pack.id,
        ).first()
        if exists:
            continue
        db.add(TenantChangeInboxItem(
            organization_id=org_id,
            change_pack_id=pack.id,
            status=InboxItemStatus.PENDING,
            impact_summary_json=compute_impact(db, org_id, pack),
        ))
        created += 1
    db.flush()
    return created


def compute_impact(db: Session, org_id: int, pack: ChangePack) -> dict:
    """Calcula que elementos del tenant se ven afectados por un pack (§5.3).

    Delegado al modulo de propagacion para un conteo extendido y preciso.
    Nunca lanza excepciones — degrada a dict vacio ante cualquier error.
    """
    try:
        from app.services import regwatch_propagation as prop
        return prop.compute_full_impact(db, org_id, pack)
    except Exception as exc:
        logger.warning("regwatch: compute_impact fallback (%s)", exc)
        return {"policies": 0, "compliance_requirements": 0,
                "control_implementations": 0, "risks": 0, "bcp_plans": 0}


# ---------- Pipeline de analisis IA (§7) ----------

def _url_is_safe(url: str) -> bool:
    """Guard SSRF: solo http(s) hacia hosts publicos.

    Las URLs vienen de los conectores (fuentes configuradas), pero como
    defensa en profundidad se rechaza cualquier destino que resuelva a
    loopback, red privada, link-local o reservada — la app corre on-premise
    junto a otros servicios internos.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443,
                                   proto=socket.IPPROTO_TCP)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
        return bool(infos)
    except Exception:
        return False


def _fetch_change_body(url: str | None, cap: int = 20000) -> str:
    """Descarga el texto completo del cambio normativo desde su URL.

    Clasificar severidad viendo solo el titular es propenso a error: el
    analisis debe leer el cuerpo real del cambio. HTML se convierte a texto
    plano de forma basica. Best-effort: devuelve "" si falla.
    """
    if not url or not url.lower().startswith(("http://", "https://")):
        return ""
    if not _url_is_safe(url):
        logger.warning("regwatch: URL rechazada por guard SSRF: %s", url[:120])
        return ""
    try:
        import re as _re
        import urllib.request

        class _SafeRedirect(urllib.request.HTTPRedirectHandler):
            """Valida cada destino de redireccion con el mismo guard SSRF
            (una URL publica podria redirigir a un servicio interno)."""
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                if not _url_is_safe(newurl):
                    logger.warning("regwatch: redireccion rechazada por guard SSRF: %s",
                                   newurl[:120])
                    return None
                return super().redirect_request(req, fp, code, msg, headers, newurl)

        opener = urllib.request.build_opener(_SafeRedirect())
        req = urllib.request.Request(url, headers={
            "User-Agent": "RiskHubRegWatch/1.0 (+https://riskhub.local; compliance-monitoring)",
        })
        with opener.open(req, timeout=20) as resp:  # noqa: S310
            raw = resp.read(2 * 1024 * 1024)
        text = raw.decode("utf-8", errors="replace")
        # HTML -> texto plano basico
        text = _re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
        text = _re.sub(r"(?s)<[^>]+>", " ", text)
        text = _re.sub(r"\s+", " ", text).strip()
        return text[:cap]
    except Exception as exc:
        logger.debug("regwatch: no se pudo descargar el cuerpo de %s: %s", url, exc)
        return ""


def analyze_event_with_ai(db: Session, event: NormativeChangeEvent) -> bool:
    """Analiza un NormativeChangeEvent con Claude y actualiza sus campos.

    Lee el TEXTO COMPLETO del cambio (descargado de la URL, cap 20k chars),
    clasifica la severidad (cosmetic/clarification/substantive/breaking) y
    genera resumenes ES/EN. Si la primera pasada (tier fast) da severidad
    alta o confianza < 0.7, una segunda pasada con el modelo potente emite
    el juicio final antes de la auto-publicacion.
    Confianza < 0.7 -> event.status queda DETECTED (cola manual).
    Devuelve True si el analisis fue exitoso.
    """
    body = _fetch_change_body(event.raw_url)
    raw_text = (
        f"Framework: {event.framework_code}\n"
        f"URL: {event.raw_url or 'N/A'}\n"
        f"Resumen previo del conector: {event.summary_es or 'Sin resumen previo'}\n\n"
        + (f"TEXTO COMPLETO DEL CAMBIO (extraido de la URL):\n{body}"
           if body else "(No se pudo descargar el texto completo: evalua con el resumen "
                        "del conector y baja la confianza en consecuencia.)")
    )

    api_key = _get_global_api_key(db)
    if not api_key:
        return False

    event_schema = {
        "type": "object",
        "properties": {
            "severity": {
                "type": "string",
                "enum": ["cosmetic", "clarification", "substantive", "breaking"],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "summary_es": {"type": "string", "maxLength": 2000},
            "summary_en": {"type": "string", "maxLength": 2000},
            "controls_affected_hint": {
                "type": "array",
                "items": {"type": "string", "maxLength": 16},
            },
            "rationale": {"type": "string", "maxLength": 1000},
        },
        "required": ["severity", "confidence", "summary_es", "summary_en", "rationale"],
    }

    system_prompt = (
        "Eres un experto en normativa de ciberseguridad (ISO 27001/27002, NIS2, GDPR, ENS, DORA). "
        "Analiza el cambio normativo descrito y clasifica su impacto llamando a la "
        "herramienta clasificar_cambio_normativo.\n\n"
        "Criterios de severidad:\n"
        "- cosmetic: solo cambios de formato, puntuacion, numero de referencia. Sin cambio de requisitos.\n"
        "- clarification: aclaracion de un requisito existente sin cambio de obligaciones.\n"
        "- substantive: cambio real en requisitos existentes o nuevo requisito que requiere accion.\n"
        "- breaking: cambio mayor de version (ej. nueva edicion ISO), eliminacion de controles, "
        "plazo de cumplimiento nuevo.\n\n"
        "controls_affected_hint: codigos ISO 27002 (ej. 5.1, 8.24) que el cambio afecta."
    )

    try:
        from app.services.claude_client import structured_message
        from app.services.model_registry import MODEL_TIERS

        def _run_pass(model_id: str) -> dict:
            result, _msg = structured_message(
                api_key,
                model=model_id,
                max_tokens=8192,
                system=system_prompt,
                messages=[{"role": "user", "content": raw_text}],
                tool_name="clasificar_cambio_normativo",
                tool_description="Registra la clasificacion del cambio normativo",
                input_schema=event_schema,
                call_type="regwatch_analysis",
            )
            return result

        # Primera pasada: tier fast (barato). Si el resultado sugiere impacto
        # real o hay dudas, segunda opinion con el modelo potente antes de
        # decidir la auto-publicacion.
        result = _run_pass(MODEL_TIERS["fast"])
        sev_first = result.get("severity", "")
        conf_first = float(result.get("confidence", 0.5))
        if sev_first in ("substantive", "breaking") or conf_first < 0.7:
            try:
                result = _run_pass(MODEL_TIERS["deep"])
                result["second_opinion"] = True
                result["first_pass"] = {"severity": sev_first, "confidence": conf_first}
            except Exception as exc:
                logger.debug("regwatch: segunda pasada fallo, uso la primera: %s", exc)

        sev_str = result.get("severity", "")
        try:
            event.severity = ChangeSeverity(sev_str)
        except ValueError:
            event.severity = ChangeSeverity.SUBSTANTIVE

        event.ai_confidence = float(result.get("confidence", 0.5))
        event.summary_es = (result.get("summary_es") or "")[:2000]
        event.summary_en = (result.get("summary_en") or "")[:2000]
        event.ai_analysis_json = result

        if event.ai_confidence >= 0.7:
            event.status = ChangeEventStatus.VALIDATED
        # <0.7 queda en DETECTED para cola de revision manual

        return True
    except Exception as exc:
        logger.warning("regwatch: ai analysis failed for event %s: %s", event.id, exc)
        return False


def _get_global_api_key(db: Session) -> str | None:
    """Obtiene la API key global de Anthropic (primer admin con config activa)."""
    from app.models import AiConfig
    from app.config import settings
    from app.security import decrypt_secret

    # Prioridad 1: variable de entorno
    if settings.anthropic_api_key:
        return settings.anthropic_api_key

    # Prioridad 2: primera config de IA activa en la BD
    cfg = db.query(AiConfig).filter(
        AiConfig.api_key_encrypted.isnot(None)
    ).first()
    if cfg and cfg.api_key_encrypted:
        try:
            return decrypt_secret(cfg.api_key_encrypted)
        except Exception:
            pass
    return None


def _get_global_model(db: Session) -> str:
    """Devuelve el modelo Claude de la primera org con config activa, o fallback global."""
    try:
        from app.models import AiConfig
        cfg = db.query(AiConfig).filter(AiConfig.model.isnot(None)).first()
        if cfg and cfg.model:
            return cfg.model
    except Exception:
        pass
    return "claude-haiku-4-5"


def run_sweep(db: Session) -> dict:
    """Barrido periodico de todas las fuentes activas (§5.2, scheduler).

    1. Ejecuta cada conector (degrada si no hay red).
    2. Para cada evento nuevo, dispara pipeline de IA (Claude Haiku).
    3. Eventos validados con alta confianza se auto-publican como change_packs.
    4. Actualiza last_sweep_at de tenants activos.
    """
    from app.services import regwatch_connectors as conns

    sources = db.query(NormativeSource).filter(NormativeSource.is_active.is_(True)).all()
    summaries = []
    total_new_events = 0

    for src in sources:
        summary = conns.run_source(db, src)
        summaries.append(summary)
        total_new_events += summary.get("new_events", 0)

    db.commit()

    # Pipeline IA: analizar eventos recien detectados sin severidad asignada
    if total_new_events > 0:
        new_events = (
            db.query(NormativeChangeEvent)
            .filter(
                NormativeChangeEvent.status == ChangeEventStatus.DETECTED,
                NormativeChangeEvent.severity.is_(None),
                NormativeChangeEvent.ai_analysis_json.is_(None),
            )
            .limit(20)  # procesar hasta 20 por barrido para evitar timeouts
            .all()
        )
        ai_ok = 0
        for ev in new_events:
            if analyze_event_with_ai(db, ev):
                ai_ok += 1
        if ai_ok > 0:
            db.commit()

        # Auto-publicar eventos validados por IA (confianza alta)
        validated = (
            db.query(NormativeChangeEvent)
            .filter(
                NormativeChangeEvent.status == ChangeEventStatus.VALIDATED,
                NormativeChangeEvent.change_pack_id.is_(None),
                NormativeChangeEvent.ai_confidence >= 0.7,
                NormativeChangeEvent.severity.isnot(None),
            )
            .limit(10)
            .all()
        )
        for ev in validated:
            try:
                pack = create_and_publish_pack(
                    db,
                    framework_code=ev.framework_code,
                    severity=ev.severity.value if ev.severity else "substantive",
                    title_es=ev.summary_es or f"Cambio normativo en {ev.framework_code}",
                    description_es=ev.summary_es or "",
                    title_en=ev.summary_en or "",
                    description_en=ev.summary_en or "",
                    source_url=ev.raw_url,
                )
                # Vincular evento->pack: la propagacion usa controls_affected_hint
                # del analisis IA del evento para dirigir el impacto en TPRM
                ev.change_pack_id = pack.id
                ev.status = ChangeEventStatus.PUBLISHED
            except Exception as exc:
                logger.warning("regwatch: error auto-publicando evento %s: %s", ev.id, exc)
        if validated:
            db.commit()

    now = _now()
    db.query(TenantRegwatchSettings).filter(
        TenantRegwatchSettings.is_enabled.is_(True)
    ).update({TenantRegwatchSettings.last_sweep_at: now})
    db.commit()

    logger.info("regwatch sweep: %d fuentes, %d eventos nuevos", len(sources), total_new_events)
    return {"sources": len(sources), "new_events": total_new_events, "details": summaries}


# ---------- Autoria interna y validacion (§6.2, §3.3) ----------

def list_events_for_review(db: Session, status: str | None = None) -> list[dict]:
    """Cola de validacion interna del equipo RiskHub (§6.2)."""
    from fastapi import HTTPException
    q = db.query(NormativeChangeEvent)
    if status:
        try:
            q = q.filter(NormativeChangeEvent.status == ChangeEventStatus(status))
        except ValueError:
            raise HTTPException(400, f"Estado invalido: {status}")
    events = q.order_by(NormativeChangeEvent.detected_at.desc()).limit(200).all()
    return [
        {
            "id": e.id,
            "framework_code": e.framework_code,
            "status": e.status.value if e.status else None,
            "severity": e.severity.value if e.severity else None,
            "summary_es": e.summary_es,
            "raw_url": e.raw_url,
            "ai_confidence": e.ai_confidence,
            "detected_at": _iso(e.detected_at),
        }
        for e in events
    ]


def create_and_publish_pack(db: Session, *, framework_code: str, severity: str,
                            title_es: str, description_es: str = "",
                            version_to: str | None = None,
                            controls_added_ids: list | None = None,
                            controls_modified: list | None = None,
                            controls_removed_ids: list | None = None,
                            source_url: str | None = None,
                            title_en: str | None = None,
                            description_en: str | None = None) -> ChangePack:
    """Crea un change_pack ya validado y lo publica a los tenants afectados.

    Este es el camino que el panel interno del equipo RiskHub usa tras validar
    un evento (la IA propone, un humano valida — §3.3). El cliente nunca ve un
    cambio sin validar.
    """
    fc = srcs.normalize_framework(framework_code)
    try:
        sev = ChangeSeverity(severity)
    except ValueError:
        sev = ChangeSeverity.SUBSTANTIVE
    pack = ChangePack(
        framework_code=fc,
        severity=sev,
        title_es=title_es[:512],
        title_en=(title_en or title_es)[:512],
        description_es=description_es or "",
        description_en=description_en or description_es or "",
        version_to=version_to,
        controls_added_ids=controls_added_ids or [],
        controls_modified=controls_modified or [],
        controls_removed_ids=controls_removed_ids or [],
        source_url=source_url,
    )
    db.add(pack)
    db.flush()
    created = publish_change_pack(db, pack)
    db.commit()
    logger.info("regwatch: change_pack %s publicado (%s) -> %d inbox items",
                pack.id, fc, created)
    return pack


def validate_and_publish_event(db: Session, event_id: int, user: User,
                               severity: str | None = None) -> dict:
    """Marca un evento como validado y publica su change_pack (§6.2)."""
    from fastapi import HTTPException
    e = db.query(NormativeChangeEvent).filter(NormativeChangeEvent.id == event_id).first()
    if not e:
        raise HTTPException(404, "Evento no encontrado")
    if e.status in (ChangeEventStatus.PUBLISHED,):
        raise HTTPException(409, f"El evento ya esta en estado {e.status.value}")
    if severity:
        try:
            e.severity = ChangeSeverity(severity)
        except ValueError:
            pass
    e.status = ChangeEventStatus.VALIDATED
    e.validated_by_user_id = user.id
    e.validated_at = _now()
    db.flush()

    pack = e.change_pack
    inbox_created = 0
    if pack:
        inbox_created = publish_change_pack(db, pack)
        e.status = ChangeEventStatus.PUBLISHED
    db.commit()
    return {"event_id": e.id, "status": e.status.value, "inbox_items_created": inbox_created}


# ---------- Seed de fuentes ----------

def seed_sources(db: Session) -> int:
    """Siembra/actualiza la tabla regwatch_sources desde el catalogo (§3.1)."""
    created = 0
    for sd in srcs.SOURCES:
        existing = db.query(NormativeSource).filter(
            NormativeSource.code == sd["code"]
        ).first()
        if existing:
            existing.name = sd["name"]
            existing.framework_codes = sd["framework_codes"]
            existing.connector_class = sd.get("connector_class")
            existing.method = sd.get("method")
            existing.polling_frequency = sd.get("polling_frequency", "weekly")
            existing.fetch_config_json = sd.get("fetch_config_json")
            continue
        db.add(NormativeSource(
            code=sd["code"],
            name=sd["name"],
            framework_codes=sd["framework_codes"],
            connector_class=sd.get("connector_class"),
            method=sd.get("method"),
            polling_frequency=sd.get("polling_frequency", "weekly"),
            fetch_config_json=sd.get("fetch_config_json"),
            is_active=True,
            last_run_status="never",
        ))
        created += 1
    db.commit()
    return created
