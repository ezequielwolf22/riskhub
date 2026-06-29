"""Integracion de formularios externos.

Opcion B — dos direcciones:
  Entrante: MS Forms / Power Automate → POST /api/integrations/forms/inbound/{token}
            Crea un SupplierQuestionnaire ya respondido a partir de la respuesta del formulario.
  Saliente: Monday.com → cuando se envia un cuestionario (interno o externo), notifica a Monday.com.
"""
import logging
import secrets
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import FormIntegrationConfig, Supplier, SupplierQuestionnaire, User
from app.security import filter_by_org, get_current_user, require_analyst

logger = logging.getLogger("riskhub.integrations_forms")

router = APIRouter(prefix="/api/integrations/forms", tags=["integrations-forms"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cfg_out(cfg: FormIntegrationConfig) -> dict:
    return {
        "id": cfg.id,
        "inbound_token": cfg.inbound_token,
        "default_template_code": cfg.default_template_code,
        "supplier_field_name": cfg.supplier_field_name,
        "monday_webhook_url": cfg.monday_webhook_url,
        # Via 3 — MS Forms polling
        "msforms_poll_enabled": cfg.msforms_poll_enabled or False,
        "msforms_tenant_id": cfg.msforms_tenant_id or "",
        "msforms_client_id": cfg.msforms_client_id or "",
        "msforms_secret_configured": bool(cfg.msforms_client_secret_enc),
        "msforms_form_id": cfg.msforms_form_id or "",
        "msforms_poll_interval_hours": cfg.msforms_poll_interval_hours or 4,
        "msforms_last_poll_at": cfg.msforms_last_poll_at.isoformat() if cfg.msforms_last_poll_at else None,
        "msforms_last_response_ts": cfg.msforms_last_response_ts or None,
        "msforms_field_mapping": cfg.msforms_field_mapping or {},
        "msforms_auto_ai_review": cfg.msforms_auto_ai_review if cfg.msforms_auto_ai_review is not None else True,
        "msforms_pa_callback_url": cfg.msforms_pa_callback_url or "",
    }


def _get_or_create_cfg(db: Session, org_id: int) -> FormIntegrationConfig:
    cfg = db.query(FormIntegrationConfig).filter(
        FormIntegrationConfig.organization_id == org_id
    ).first()
    if not cfg:
        cfg = FormIntegrationConfig(
            organization_id=org_id,
            inbound_token=secrets.token_urlsafe(32),
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


# ── Config endpoints (requieren autenticacion) ────────────────────────────────

@router.get("/config")
def get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Obtiene (o crea) la configuracion de integracion de formularios para la organizacion."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    cfg = _get_or_create_cfg(db, org_id)
    return _cfg_out(cfg)


@router.patch("/config")
def update_config(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Actualiza la configuracion de integracion de formularios."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    cfg = _get_or_create_cfg(db, org_id)
    allowed = ("default_template_code", "supplier_field_name", "monday_webhook_url")
    for key in allowed:
        if key in body:
            setattr(cfg, key, body[key] or None)

    # Via 3 — MS Forms polling config
    if "msforms_poll_enabled" in body:
        cfg.msforms_poll_enabled = bool(body["msforms_poll_enabled"])
    if "msforms_tenant_id" in body:
        cfg.msforms_tenant_id = body["msforms_tenant_id"] or None
    if "msforms_client_id" in body:
        cfg.msforms_client_id = body["msforms_client_id"] or None
    if "msforms_client_secret" in body and body["msforms_client_secret"]:
        from app.services.msforms_service import _fernet_encrypt
        cfg.msforms_client_secret_enc = _fernet_encrypt(body["msforms_client_secret"])
    if "msforms_form_id" in body:
        cfg.msforms_form_id = body["msforms_form_id"] or None
    if "msforms_poll_interval_hours" in body:
        try:
            cfg.msforms_poll_interval_hours = max(1, int(body["msforms_poll_interval_hours"]))
        except (TypeError, ValueError):
            pass
    if "msforms_field_mapping" in body:
        cfg.msforms_field_mapping = body["msforms_field_mapping"] or {}
    if "msforms_auto_ai_review" in body:
        cfg.msforms_auto_ai_review = bool(body["msforms_auto_ai_review"])
    if "msforms_pa_callback_url" in body:
        cfg.msforms_pa_callback_url = body["msforms_pa_callback_url"] or None

    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _cfg_out(cfg)


@router.post("/config/regenerate-token")
def regenerate_token(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Regenera el token de webhook entrante (invalida el anterior)."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    cfg = _get_or_create_cfg(db, org_id)
    cfg.inbound_token = secrets.token_urlsafe(32)
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"inbound_token": cfg.inbound_token}


# ── Webhook entrante MS Forms / Power Automate (publico, protegido por token) ─

@router.post("/inbound/{token}", status_code=200)
def msforms_inbound(
    token: str,
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Recibe la respuesta de un formulario externo (MS Forms via Power Automate).

    Power Automate debe configurarse para enviar un POST JSON a:
      POST {base_url}/api/integrations/forms/inbound/{token}

    Formato esperado del payload (Power Automate → HTTP action → Body):
    {
      "supplier": "Nombre o codigo del proveedor",
      "title": "Titulo opcional del cuestionario",
      "answers": {
        "Pregunta 1": "Si",
        "Pregunta 2": "No",
        ...
      },
      "submitted_by": "email@externo.com"  // opcional
    }
    Si el payload tiene una estructura diferente, se intenta mapear automaticamente:
    cualquier campo llamado igual que supplier_field_name se usa para identificar al proveedor,
    el resto de campos se tratan como respuestas.
    """
    cfg = db.query(FormIntegrationConfig).filter(
        FormIntegrationConfig.inbound_token == token
    ).first()
    if not cfg:
        raise HTTPException(404, "Token no valido")

    org_id = cfg.organization_id

    # Identificar proveedor
    supplier_name = payload.get("supplier") or payload.get(cfg.supplier_field_name or "supplier") or ""
    if not supplier_name:
        raise HTTPException(400, "No se pudo identificar el proveedor. Incluye el campo 'supplier' en el payload.")

    supplier = (
        db.query(Supplier)
        .filter(
            Supplier.organization_id == org_id,
            Supplier.name.ilike(f"%{supplier_name}%"),
        )
        .first()
    )
    if not supplier:
        # Intentar por codigo
        supplier = (
            db.query(Supplier)
            .filter(
                Supplier.organization_id == org_id,
                Supplier.code.ilike(supplier_name),
            )
            .first()
        )
    if not supplier:
        # G01/G10: auto-crear proveedor con datos del payload + field_mapping
        field_mapping = cfg.msforms_field_mapping or {}
        mapped_data: dict = {}
        for form_key, supplier_field in field_mapping.items():
            val = payload.get(form_key, "")
            if val and supplier_field:
                mapped_data[supplier_field] = str(val).strip()

        n = db.query(Supplier).filter(Supplier.organization_id == org_id).count() + 1
        supplier = Supplier(
            code=f"SUP-{n:04d}",
            name=(mapped_data.get("name") or supplier_name).strip(),
            description=mapped_data.get("description"),
            services=mapped_data.get("services"),
            category=mapped_data.get("category"),
            contact_name=mapped_data.get("contact_name"),
            contact_email=mapped_data.get("contact_email"),
            website=mapped_data.get("website"),
            contract_ref=mapped_data.get("contract_ref"),
            notes=(
                f"Alta automatica via MS Forms webhook (Via 1). "
                f"Respondido por: {payload.get('submitted_by', 'desconocido')}."
            ),
            organization_id=org_id,
            risk_level="medium",
            msforms_origin=True,
            msforms_responder=payload.get("submitted_by") or None,
        )
        db.add(supplier)
        db.flush()
        try:
            from app.services.tprm_scoring_service import recompute_supplier
            recompute_supplier(db, supplier, commit=False)
        except Exception:
            pass
        logger.info("MS Forms inbound: proveedor '%s' creado automaticamente (Via 1)", supplier.name)

    # Construir respuestas
    answers = payload.get("answers") or {}
    if not isinstance(answers, dict):
        answers = {}
    # Si el payload es plano (sin nesting de "answers"), tomar todos los campos excepto los conocidos
    if not answers:
        skip = {"supplier", "title", "submitted_by", cfg.supplier_field_name or "supplier"}
        answers = {k: v for k, v in payload.items() if k not in skip}

    title = payload.get("title") or f"Formulario externo — {supplier.name}"
    submitted_by = payload.get("submitted_by", "ms_forms_inbound")
    now = datetime.now(timezone.utc)

    from app.routers.supplier_questionnaires import DEFAULT_QUESTIONS, _next_code, _calculate_score

    questions = DEFAULT_QUESTIONS
    template_code = cfg.default_template_code
    if template_code:
        try:
            from app.services import tprm_templates
            tpl = tprm_templates.get_template(template_code)
            if tpl:
                questions = tpl["questions"]
        except Exception:
            pass

    q = SupplierQuestionnaire(
        code=_next_code(db),
        supplier_id=supplier.id,
        title=title,
        token=secrets.token_urlsafe(32),
        template_code=template_code,
        questions=questions,
        answers=answers,
        score=_calculate_score(answers),
        submitted_at=now,
        notes=f"Importado via MS Forms / Power Automate. Respondido por: {submitted_by}",
        assignment_type="external",
        organization_id=org_id,
    )
    db.add(q)
    db.commit()
    db.refresh(q)

    logger.info("MS Forms inbound: questionnaire %s creado para proveedor %s", q.code, supplier.name)

    # G02: disparar revision IA si esta habilitada (igual que Via 3)
    if cfg.msforms_auto_ai_review:
        from app.services.msforms_service import _trigger_ai_review_bg
        _trigger_ai_review_bg(q.id, org_id)

    # Notificar a Monday.com en background si esta configurado
    if cfg.monday_webhook_url:
        _qid = q.id
        _org = org_id
        def _bg_monday():
            _notify_monday(db_org=_org, questionnaire_id=_qid, monday_url=cfg.monday_webhook_url)
        threading.Thread(target=_bg_monday, daemon=True).start()

    return {
        "success": True,
        "questionnaire_code": q.code,
        "supplier": supplier.name,
        "score": q.score,
    }


# ── Notificacion saliente Monday.com ─────────────────────────────────────────

def _notify_monday(db_org: int, questionnaire_id: int, monday_url: str) -> None:
    """Envia un webhook a Monday.com cuando se completa un cuestionario."""
    import urllib.request
    import json as _json
    try:
        with SessionLocal() as db:
            q = db.get(SupplierQuestionnaire, questionnaire_id)
            if not q:
                return
            payload = {
                "event": "questionnaire_submitted",
                "questionnaire_code": q.code,
                "questionnaire_title": q.title,
                "supplier_name": q.supplier_name,
                "score": q.score,
                "submitted_at": q.submitted_at.isoformat() if q.submitted_at else None,
                "residual_risk_level": q.residual_risk_level,
                "major_nc": q.major_nc,
                "minor_nc": q.minor_nc,
            }
            data = _json.dumps(payload).encode()
            req = urllib.request.Request(
                monday_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.info("Monday.com webhook: %s → %s", q.code, resp.status)
    except Exception as exc:
        logger.warning("Monday.com webhook failed for questionnaire %s: %s", questionnaire_id, exc)


@router.post("/msforms/poll-now")
def msforms_poll_now(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Dispara una sincronizacion manual con MS Forms (Via 3).

    Consulta de inmediato la API de MS Forms, independientemente
    del intervalo de polling automatico configurado.
    """
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    cfg = _get_or_create_cfg(db, org_id)
    if not cfg.msforms_form_id:
        raise HTTPException(400, "Form ID no configurado — guarda la configuracion primero")

    from app.services.msforms_service import poll_org
    result = poll_org(cfg, db)
    return result


def notify_monday_if_configured(db: Session, org_id: int, questionnaire_id: int) -> None:
    """Llamado desde submit_public_questionnaire e internal-submit si hay Monday.com configurado."""
    try:
        cfg = db.query(FormIntegrationConfig).filter(
            FormIntegrationConfig.organization_id == org_id,
        ).first()
        if cfg and cfg.monday_webhook_url:
            _qid = questionnaire_id
            _url = cfg.monday_webhook_url
            def _bg():
                _notify_monday(org_id, _qid, _url)
            threading.Thread(target=_bg, daemon=True).start()
    except Exception:
        pass
