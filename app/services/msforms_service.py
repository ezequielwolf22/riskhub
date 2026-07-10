"""Servicio de polling a MS Forms via Microsoft Graph API.

Via 3 — Alta automatica de proveedores desde MS Forms:
  - Autenticacion: OAuth2 client credentials (app-only) con Graph API
  - Poll periodico de respuestas nuevas en un formulario MS Forms
  - Por cada respuesta nueva: Supplier + SupplierQuestionnaire + AI review

Permisos Azure AD requeridos en el App Registration:
  - Forms.Read.All  (o Sites.Read.All si el form esta vinculado a SharePoint)
  Conceder como "Application permissions" en Azure Portal > App Registrations
  > API Permissions > Add permission > Microsoft Graph.
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("riskhub.msforms")

_GRAPH = "https://graph.microsoft.com/v1.0"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


# ---------- Cifrado -------------------------------------------------------

def _fernet_encrypt(val: str) -> str:
    from cryptography.fernet import Fernet
    from app.services.document_service import _fernet_key
    return Fernet(_fernet_key()).encrypt(val.encode()).decode()


def _fernet_decrypt(enc: str) -> Optional[str]:
    try:
        from cryptography.fernet import Fernet
        from app.services.document_service import _fernet_key
        return Fernet(_fernet_key()).decrypt(enc.encode()).decode()
    except Exception:
        return None


# ---------- Graph API helpers --------------------------------------------

def get_oauth_token(tenant_id: str, client_id: str, client_secret: str) -> Optional[str]:
    """Obtiene access token via OAuth2 client credentials."""
    url = _TOKEN_URL.format(tenant=tenant_id)
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }).encode()
    try:
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        logger.error("MSForms: error token OAuth2 HTTP %s: %s", exc.code, body[:300])
        return None
    except Exception as exc:
        logger.error("MSForms: error token OAuth2: %s", exc)
        return None


def _graph_get(url: str, token: str) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        logger.error("MSForms: Graph GET %s → HTTP %s: %s", url, exc.code, body[:200])
        return None
    except Exception as exc:
        logger.error("MSForms: Graph GET %s → %s", url, exc)
        return None


def get_form_questions(form_id: str, token: str) -> dict:
    """Devuelve {questionId: question_title}."""
    data = _graph_get(f"{_GRAPH}/forms/{form_id}/questions", token)
    if not data:
        return {}
    return {q["id"]: q.get("title", q["id"]) for q in data.get("value", [])}


def get_form_responses(form_id: str, token: str) -> list:
    """Obtiene todas las respuestas del formulario."""
    data = _graph_get(f"{_GRAPH}/forms/{form_id}/responses", token)
    if not data:
        return []
    return data.get("value", [])


# ---------- Mapeo de respuestas a Supplier --------------------------------

def _build_answer_map(response: dict, question_map: dict) -> dict:
    """Devuelve {question_title_lower: value, question_id: value}."""
    am: dict[str, str] = {}
    for a in response.get("answers", []):
        qid = a.get("questionId", "")
        val = a.get("value", "")
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val)
        else:
            val = str(val).strip()
        am[qid] = val
        title = question_map.get(qid, "")
        if title:
            am[title.lower()] = val
    return am


def extract_supplier_data(response: dict, question_map: dict, field_mapping: dict) -> dict:
    """Mapea una respuesta de MS Forms a campos de Supplier.

    field_mapping: {pregunta_texto_o_id: campo_supplier}
    Campos soportados: name, description, services, category,
                       contact_name, contact_email, website, contract_ref
    """
    am = _build_answer_map(response, question_map)
    sup: dict = {}

    for form_key, supplier_field in (field_mapping or {}).items():
        val = am.get(form_key) or am.get(form_key.lower(), "")
        if val and supplier_field:
            sup[supplier_field] = val

    if "name" not in sup:
        for key in [
            "nombre", "name", "empresa", "company", "proveedor", "supplier",
            "nombre del proveedor", "company name", "razon social",
            "nombre empresa", "nombre de la empresa",
        ]:
            val = am.get(key, "")
            if val:
                sup["name"] = val
                break

    return sup


def build_questionnaire_answers(response: dict, question_map: dict) -> dict:
    """Convierte respuestas de MS Forms a {pregunta: respuesta} para SupplierQuestionnaire."""
    result = {}
    for a in response.get("answers", []):
        qid = a.get("questionId", "")
        title = question_map.get(qid, qid)
        val = a.get("value", "")
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val)
        result[title] = str(val).strip()
    return result


# ---------- Polling principal --------------------------------------------

def poll_org(cfg, db: Session) -> dict:
    """Polling de MS Forms para una organizacion.

    Crea Supplier + SupplierQuestionnaire + AI review (async) por cada
    respuesta nueva encontrada desde la ultima ejecucion.

    Returns dict {checked, created, skipped, errors}.
    """
    result: dict = {"checked": 0, "created": 0, "skipped": 0, "errors": []}

    if not cfg.msforms_poll_enabled:
        return result

    missing = [
        f for f in [
            "msforms_tenant_id", "msforms_client_id",
            "msforms_client_secret_enc", "msforms_form_id",
        ]
        if not getattr(cfg, f, None)
    ]
    if missing:
        result["errors"].append(f"Configuracion incompleta: {missing}")
        return result

    client_secret = _fernet_decrypt(cfg.msforms_client_secret_enc)
    if not client_secret:
        result["errors"].append("Error descifrando client_secret — reconfigurar credenciales")
        return result

    token = get_oauth_token(cfg.msforms_tenant_id, cfg.msforms_client_id, client_secret)
    if not token:
        result["errors"].append("Error obteniendo token OAuth2 de Azure AD")
        return result

    form_id = cfg.msforms_form_id
    question_map = get_form_questions(form_id, token)
    responses = get_form_responses(form_id, token)
    result["checked"] = len(responses)

    last_ts: str = cfg.msforms_last_response_ts or ""
    new_last_ts: str = last_ts
    field_mapping: dict = cfg.msforms_field_mapping or {}
    org_id: int = cfg.organization_id

    # Filtrar solo respuestas posteriores al ultimo timestamp procesado
    new_responses = [
        (r.get("submittedDateTime", ""), r)
        for r in responses
        if not last_ts or r.get("submittedDateTime", "") > last_ts
    ]
    new_responses.sort(key=lambda x: x[0])

    from app.models import Supplier, SupplierQuestionnaire
    import secrets as _sec
    from app.services.tprm_scoring_service import recompute_supplier

    for submitted_at, resp in new_responses:
        try:
            sup_data = extract_supplier_data(resp, question_map, field_mapping)
            name = sup_data.get("name", "").strip()
            if not name:
                result["errors"].append(
                    f"Respuesta {resp.get('id','?')}: sin campo 'name' — "
                    "configura el mapeo de campos en la integracion"
                )
                result["skipped"] += 1
                if submitted_at > new_last_ts:
                    new_last_ts = submitted_at
                continue

            # Evitar duplicados por nombre
            existing = db.query(Supplier).filter(
                Supplier.organization_id == org_id,
                Supplier.name.ilike(name),
            ).first()
            if existing:
                result["skipped"] += 1
                if submitted_at > new_last_ts:
                    new_last_ts = submitted_at
                continue

            # Crear proveedor
            n = db.query(Supplier).filter(Supplier.organization_id == org_id).count() + 1
            responder_email = resp.get("responder", "")
            supplier = Supplier(
                code=f"SUP-{n:04d}",
                name=name,
                description=sup_data.get("description"),
                services=sup_data.get("services"),
                category=sup_data.get("category"),
                contact_name=sup_data.get("contact_name"),
                contact_email=sup_data.get("contact_email") or responder_email or None,
                website=sup_data.get("website"),
                contract_ref=sup_data.get("contract_ref"),
                notes=(
                    f"Alta automatica via MS Forms polling. "
                    f"Respondido por: {responder_email or 'desconocido'}. "
                    f"ID respuesta: {resp.get('id', '')}."
                ),
                organization_id=org_id,
                risk_level="medium",
                msforms_origin=True,
                msforms_responder=responder_email or None,
            )
            db.add(supplier)
            db.flush()

            # TPRM scoring inicial
            try:
                recompute_supplier(db, supplier, commit=False)
            except Exception as exc:
                logger.warning("MSForms: error TPRM scoring '%s': %s", name, exc)

            # Crear cuestionario con las respuestas del formulario
            q_answers = build_questionnaire_answers(resp, question_map)
            q_questions = [
                {"id": str(i + 1), "text": k}
                for i, k in enumerate(q_answers.keys())
            ]
            answered = sum(1 for v in q_answers.values() if str(v).strip())
            score = round(answered / len(q_answers) * 100) if q_answers else 50

            sq_n = db.query(SupplierQuestionnaire).filter(
                SupplierQuestionnaire.organization_id == org_id
            ).count() + 1
            questionnaire = SupplierQuestionnaire(
                code=f"SEQ-{sq_n:04d}",
                supplier_id=supplier.id,
                title=f"Formulario MS Forms — {name}",
                token=_sec.token_urlsafe(32),
                questions=q_questions,
                answers=q_answers,
                score=score,
                submitted_at=datetime.now(timezone.utc),
                notes=(
                    f"Importado automaticamente via polling MS Forms. "
                    f"Respondido por: {resp.get('responder', '')}."
                ),
                assignment_type="external",
                organization_id=org_id,
            )
            db.add(questionnaire)
            db.flush()
            db.commit()
            db.refresh(supplier)
            db.refresh(questionnaire)
            result["created"] += 1

            if cfg.msforms_auto_ai_review:
                _trigger_ai_review_bg(questionnaire.id, org_id)

            if submitted_at > new_last_ts:
                new_last_ts = submitted_at

        except Exception as exc:
            logger.error("MSForms: error procesando respuesta %s: %s", resp.get("id", "?"), exc)
            result["errors"].append(f"Error respuesta {resp.get('id','?')}: {str(exc)[:100]}")
            try:
                db.rollback()
            except Exception:
                pass

    # Persistir timestamps
    try:
        cfg.msforms_last_poll_at = datetime.now(timezone.utc)
        if new_last_ts and new_last_ts != last_ts:
            cfg.msforms_last_response_ts = new_last_ts
        db.commit()
    except Exception as exc:
        logger.error("MSForms: error guardando timestamps: %s", exc)

    return result


def _trigger_ai_review_bg(questionnaire_id: int, org_id: int) -> None:
    """Lanza revision IA del cuestionario en background thread."""
    import threading

    def _bg() -> None:
        try:
            from app.database import SessionLocal
            from app.models import AiConfig, SupplierQuestionnaire
            from app.routers.ai_config import resolve_api_key
            from app.services import tprm_ai_service

            with SessionLocal() as db2:
                q = db2.get(SupplierQuestionnaire, questionnaire_id)
                if not q:
                    return
                ai_cfg = db2.query(AiConfig).filter_by(organization_id=org_id).first()
                key = resolve_api_key(ai_cfg)
                if not key:
                    logger.warning(
                        "MSForms AI review: sin API key para org %d — "
                        "configura la API key en IA > Configuracion",
                        org_id,
                    )
                    return
                model = (ai_cfg.model if ai_cfg else None) or "claude-opus-4-6"
                review = tprm_ai_service.review_questionnaire(db2, q, key, model)
                q.ai_review = review
                q.ai_reviewed_at = datetime.now(timezone.utc)
                from app.services.tprm_scoring_service import recompute_questionnaire_score
                recompute_questionnaire_score(db2, q)
                db2.commit()
                logger.info(
                    "MSForms: AI review completado para questionnaire %d (org %d)",
                    questionnaire_id, org_id,
                )
        except Exception as exc:
            logger.warning(
                "MSForms: error AI review questionnaire %d: %s",
                questionnaire_id, exc,
            )

    threading.Thread(target=_bg, daemon=True).start()


# ---------- Notificacion de retorno a Power Automate --------------------

def notify_pa_decision(
    supplier,
    decision: str,
    notes: str,
    conditions: list,
    decided_by_email: str,
    db: Session,
) -> bool:
    """Envia la decision de seguridad al webhook de Power Automate configurado.

    Llamado desde onboarding_gate.py tras registrar una decision formal.
    Solo actua si:
      - El proveedor tiene msforms_origin=True (fue creado via Via 3)
      - La org tiene msforms_pa_callback_url configurado

    decision: "approved" | "conditional" | "rejected"
    Devuelve True si el webhook se envio correctamente.
    """
    from app.models import FormIntegrationConfig

    if not getattr(supplier, "msforms_origin", False):
        return False

    org_id = supplier.organization_id
    cfg = db.query(FormIntegrationConfig).filter(
        FormIntegrationConfig.organization_id == org_id
    ).first()
    if not cfg or not cfg.msforms_pa_callback_url:
        return False

    payload = {
        "event": "supplier.decision",
        "decision": decision,
        "supplier_code": supplier.code,
        "supplier_name": supplier.name,
        "supplier_contact_email": supplier.contact_email or supplier.msforms_responder or "",
        "msforms_responder": supplier.msforms_responder or "",
        "notes": notes or "",
        "conditions": conditions or [],
        "decided_by": decided_by_email,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "score": supplier.score,
        "risk_level": supplier.risk_level,
    }

    return _send_pa_webhook(cfg.msforms_pa_callback_url, payload)


def notify_pa_decision_bg(
    supplier_id: int,
    org_id: int,
    decision: str,
    notes: str,
    conditions: list,
    decided_by_email: str,
) -> None:
    """Version en background thread para no bloquear la respuesta HTTP."""
    import threading

    def _bg() -> None:
        try:
            from app.database import SessionLocal
            from app.models import Supplier
            with SessionLocal() as db2:
                sup = db2.get(Supplier, supplier_id)
                if sup:
                    notify_pa_decision(sup, decision, notes, conditions, decided_by_email, db2)
        except Exception as exc:
            logger.warning("MSForms PA callback error (supplier %d): %s", supplier_id, exc)

    threading.Thread(target=_bg, daemon=True).start()


def _send_pa_webhook(url: str, payload: dict) -> bool:
    """POST JSON al webhook de Power Automate. Devuelve True si HTTP 2xx."""
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = 200 <= resp.status < 300
            logger.info(
                "MSForms PA webhook → %s: HTTP %s (decision=%s supplier=%s)",
                url[:60], resp.status, payload.get("decision"), payload.get("supplier_code"),
            )
            return ok
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        logger.error("MSForms PA webhook HTTP %s: %s", exc.code, body[:200])
        return False
    except Exception as exc:
        logger.error("MSForms PA webhook error: %s", exc)
        return False


# ---------- Scheduler entrypoint ----------------------------------------

def poll_all_orgs() -> None:
    """Llamado por el scheduler cada hora. Revisa si cada org necesita polling."""
    from app.database import SessionLocal
    from app.models import FormIntegrationConfig

    now = datetime.now(timezone.utc)
    try:
        with SessionLocal() as db:
            cfgs = (
                db.query(FormIntegrationConfig)
                .filter(
                    FormIntegrationConfig.msforms_poll_enabled.is_(True),
                    FormIntegrationConfig.msforms_form_id.isnot(None),
                )
                .all()
            )
            for cfg in cfgs:
                interval_h = cfg.msforms_poll_interval_hours or 4
                if cfg.msforms_last_poll_at:
                    last = cfg.msforms_last_poll_at
                    if not last.tzinfo:
                        last = last.replace(tzinfo=timezone.utc)
                    elapsed_h = (now - last).total_seconds() / 3600
                    if elapsed_h < interval_h:
                        continue
                try:
                    res = poll_org(cfg, db)
                    logger.info(
                        "MSForms — org %d: revisadas=%d creadas=%d omitidas=%d errores=%d",
                        cfg.organization_id or 0,
                        res["checked"], res["created"],
                        res["skipped"], len(res["errors"]),
                    )
                except Exception as exc:
                    logger.error(
                        "MSForms — org %d error inesperado: %s",
                        cfg.organization_id or 0, exc,
                    )
    except Exception as exc:
        logger.error("MSForms poll_all_orgs error global: %s", exc)
