"""Servicio de polling de buzon de correo para alta automatica de proveedores.

Via 4 -- Alta de proveedor por email:
  - Poll periodico (nunca webhook entrante) de un buzon configurado por organizacion.
  - Soporta dos modos de conexion, seleccionables por organizacion:
      * Microsoft 365 / Graph Mail (OAuth2 client-credentials, mismo patron que msforms_service)
      * IMAP generico (Gmail, Exchange on-prem, cualquier proveedor) via stdlib imaplib/email
  - Por cada mail nuevo: valida remitente (allowlist opcional) y adjuntos (magic bytes + tamano),
    intenta extraccion deterministica (PDF AcroForm / DOCX content controls) y si no hay campos
    estructurados, delega en supplier_document_analyzer (IA) sobre el adjunto o el cuerpo del mail.
  - SIEMPRE crea el Supplier. Si la extraccion via IA no garantiza 'name', usa un fallback
    (remitente/asunto) y marca email_needs_review=True.

Permisos Azure AD requeridos (modo Graph), mismo tipo de App Registration que Via 3:
  - Mail.Read (Application permission) sobre el buzon a monitorear.
"""
import base64
import email as email_lib
import fnmatch
import html as html_lib
import imaplib
import io
import logging
import re
import unicodedata
import urllib.parse
import uuid
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parseaddr
from typing import Optional

from sqlalchemy.orm import Session

from app.services.msforms_service import _GRAPH, _fernet_decrypt, _graph_get, get_oauth_token

logger = logging.getLogger("riskhub.email_intake")

_MAX_ATTACHMENTS_PER_MAIL = 3
_MAX_MESSAGES_PER_POLL = 50

_INTAKE_ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/csv",
}

_SUPPLIER_NAME_SYNONYMS = [
    "nombre", "name", "empresa", "company", "proveedor", "supplier",
    "nombre del proveedor", "company name", "razon social",
    "nombre empresa", "nombre de la empresa",
]


# ---------- Validacion y saneo de adjuntos (remitente no confiable, OWASP A08) ----------

def validate_attachment(filename: str, content_type: str, data: bytes) -> tuple[bool, str]:
    """Valida un adjunto de email antes de procesarlo, reusando los mismos controles
    que la subida manual de documentos (magic bytes + tamano + whitelist restringida)."""
    from app.routers.documents import MAX_SIZE_BYTES, _infer_mime, _validate_magic
    if not data:
        return False, "adjunto vacio"
    if len(data) > MAX_SIZE_BYTES:
        return False, f"excede el tamano maximo ({MAX_SIZE_BYTES // (1024 * 1024)} MB)"
    mime = _infer_mime(filename or "", content_type or "")
    if mime not in _INTAKE_ALLOWED_MIME:
        return False, f"tipo no soportado ({mime})"
    if not _validate_magic(mime, data):
        return False, "firma de contenido no coincide con el tipo declarado"
    return True, ""


def sanitize_filename(filename: str) -> str:
    import os
    base = os.path.basename(filename or "adjunto")
    base = unicodedata.normalize("NFKC", base)
    base = re.sub(r"[^\w\s.\-]", "_", base)
    return base[:200] or "adjunto"


# ---------- Extraccion deterministica: PDF AcroForm / DOCX content controls ----------

def extract_pdf_form_fields(data: bytes) -> dict:
    """Devuelve {campo: valor} si el PDF tiene un AcroForm con campos rellenos, si no {}."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        fields = reader.get_fields()
        if not fields:
            return {}
        result = {}
        for name, f in fields.items():
            val = f.get("/V") if hasattr(f, "get") else None
            if val:
                result[str(name)] = str(val)
        return result
    except Exception as exc:
        logger.debug("email_intake: sin AcroForm en PDF: %s", exc)
        return {}


def extract_docx_form_fields(data: bytes) -> dict:
    """Devuelve {tag_o_alias: texto} de los content controls (<w:sdt>) del Word, si hay."""
    try:
        from docx import Document
        from docx.oxml.ns import qn
        doc = Document(io.BytesIO(data))
        result: dict = {}
        for sdt in doc.element.body.iter(qn("w:sdt")):
            sdt_pr = sdt.find(qn("w:sdtPr"))
            if sdt_pr is None:
                continue
            tag_el = sdt_pr.find(qn("w:tag"))
            alias_el = sdt_pr.find(qn("w:alias"))
            key = None
            if tag_el is not None:
                key = tag_el.get(qn("w:val"))
            elif alias_el is not None:
                key = alias_el.get(qn("w:val"))
            if not key:
                continue
            content = sdt.find(qn("w:sdtContent"))
            if content is None:
                continue
            text = "".join(t.text or "" for t in content.iter(qn("w:t")))
            if text.strip():
                result[key] = text.strip()
        return result
    except Exception as exc:
        logger.debug("email_intake: sin content controls en DOCX: %s", exc)
        return {}


def _apply_form_classification(supplier, structured_fields: dict) -> None:
    """Aplica la clasificacion inicial declarada en el formulario (punto 1).

    Reutiliza la normalizacion ES/EN del import; solo rellena lo que venga en el
    formulario y no pisa valores ya presentes."""
    from app.services.supplier_import_service import (
        _AGREEMENT_STATUS_MAP, _BUSINESS_IMPORTANCE_MAP, _map_value,
        _REVIEW_FREQUENCY_MAP, _SECURITY_RISK_MAP,
    )
    sf = structured_fields or {}
    mappings = [
        ("business_importance_level", _BUSINESS_IMPORTANCE_MAP),
        ("security_risk_level", _SECURITY_RISK_MAP),
        ("review_frequency", _REVIEW_FREQUENCY_MAP),
        ("agreement_status", _AGREEMENT_STATUS_MAP),
    ]
    for field, table in mappings:
        raw = sf.get(field)
        if raw and not getattr(supplier, field, None):
            mapped = _map_value(str(raw), table)
            if mapped:
                setattr(supplier, field, mapped)
    if sf.get("operating_region") and not supplier.operating_region:
        supplier.operating_region = str(sf["operating_region"])[:64]


def map_structured_fields_to_supplier(fields: dict, field_mapping: Optional[dict]) -> dict:
    """Aplica field_mapping ({campo_form: campo_supplier}) y, si falta 'name',
    intenta resolverlo por sinonimos comunes (mismo concepto que Via 3)."""
    sup: dict = {}
    lower_fields = {str(k).lower(): v for k, v in fields.items()}
    for form_key, supplier_field in (field_mapping or {}).items():
        val = fields.get(form_key) or lower_fields.get(str(form_key).lower(), "")
        if val and supplier_field:
            sup[supplier_field] = val
    if "name" not in sup:
        for key in _SUPPLIER_NAME_SYNONYMS:
            val = lower_fields.get(key, "")
            if val:
                sup["name"] = val
                break
    return sup


# ---------- Parseo comun de mensajes (IMAP y Graph convergen en este shape) ----------

def _decode_hdr(value: str) -> str:
    if not value:
        return ""
    out = []
    for part, enc in decode_header(value):
        if isinstance(part, bytes):
            try:
                out.append(part.decode(enc or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                out.append(part.decode("utf-8", errors="replace"))
        else:
            out.append(part)
    return "".join(out)


def _html_to_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?(</\1>)", " ", raw_html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_email_message(raw_bytes: bytes) -> dict:
    """Parsea un mensaje RFC822 (IMAP) al shape comun usado por process_email()."""
    msg = email_lib.message_from_bytes(raw_bytes)
    subject = _decode_hdr(msg.get("Subject", ""))
    message_id = (msg.get("Message-ID") or "").strip() or None
    from_display, from_addr = parseaddr(_decode_hdr(msg.get("From", "")))

    body_text = ""
    body_html = ""
    attachments: list[dict] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            filename = part.get_filename()
            if filename:
                filename = _decode_hdr(filename)
            if filename and ("attachment" in disp or content_type not in ("text/plain", "text/html")):
                try:
                    data = part.get_payload(decode=True) or b""
                except Exception:
                    data = b""
                if data:
                    attachments.append({"filename": filename, "content_type": content_type, "data": data})
                continue
            if content_type == "text/plain" and not body_text:
                try:
                    body_text = (part.get_payload(decode=True) or b"").decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    pass
            elif content_type == "text/html" and not body_html:
                try:
                    body_html = (part.get_payload(decode=True) or b"").decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    pass
    else:
        content_type = msg.get_content_type()
        try:
            payload = (msg.get_payload(decode=True) or b"").decode(
                msg.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            payload = ""
        if content_type == "text/html":
            body_html = payload
        else:
            body_text = payload

    if not body_text.strip() and body_html:
        body_text = _html_to_text(body_html)

    return {
        "message_id": message_id,
        "subject": subject,
        "from_addr": (from_addr or "").strip().lower(),
        "from_display": from_display or from_addr or "",
        "date": msg.get("Date", ""),
        "body_text": body_text.strip(),
        "attachments": attachments,
    }


def _parse_graph_message(message: dict) -> dict:
    from_info = (message.get("from") or {}).get("emailAddress") or {}
    body = message.get("body") or {}
    content = body.get("content") or ""
    if (body.get("contentType") or "").lower() == "html":
        body_text = _html_to_text(content)
    else:
        body_text = content
    return {
        "message_id": message.get("id"),
        "subject": message.get("subject") or "",
        "from_addr": (from_info.get("address") or "").strip().lower(),
        "from_display": from_info.get("name") or from_info.get("address") or "",
        "date": message.get("receivedDateTime") or "",
        "body_text": (body_text or "").strip(),
        "attachments": [],  # se completan con get_graph_attachments si hasAttachments
    }


# ---------- Modo Graph Mail (Microsoft 365) ----------

def list_new_graph_messages(mailbox: str, token: str, since_iso: str) -> list:
    since = since_iso or "1970-01-01T00:00:00Z"
    url = (
        f"{_GRAPH}/users/{urllib.parse.quote(mailbox, safe='')}/mailFolders/Inbox/messages"
        f"?$filter=receivedDateTime ge {since}"
        f"&$orderby=receivedDateTime asc"
        f"&$select=id,subject,from,receivedDateTime,hasAttachments,body"
        f"&$top={_MAX_MESSAGES_PER_POLL}"
    )
    data = _graph_get(url, token)
    if not data:
        return []
    return data.get("value", [])


def get_graph_attachments(mailbox: str, message_id: str, token: str) -> list:
    data = _graph_get(
        f"{_GRAPH}/users/{urllib.parse.quote(mailbox, safe='')}/messages/{message_id}/attachments", token)
    if not data:
        return []
    result = []
    for att in data.get("value", []):
        if att.get("@odata.type") != "#microsoft.graph.fileAttachment":
            continue  # ignora referenceAttachment (link a OneDrive/SharePoint) -- mitigacion SSRF
        try:
            raw = base64.b64decode(att.get("contentBytes") or "")
        except Exception:
            continue
        result.append({
            "filename": att.get("name") or "adjunto",
            "content_type": att.get("contentType") or "",
            "data": raw,
        })
    return result


def _graph_get_mailbox_probe(mailbox: str, token: str) -> bool:
    data = _graph_get(f"{_GRAPH}/users/{urllib.parse.quote(mailbox, safe='')}", token)
    return bool(data and data.get("id"))


# ---------- Modo IMAP generico (Gmail, Exchange on-prem, cualquier proveedor) ----------

def _imap_connect(host: str, port: int, username: str, password: str, use_ssl: bool) -> imaplib.IMAP4:
    if use_ssl:
        conn = imaplib.IMAP4_SSL(host, port, timeout=30)
    else:
        conn = imaplib.IMAP4(host, port, timeout=30)
        try:
            conn.starttls()
        except Exception:
            logger.warning("email_intake: servidor IMAP %s sin STARTTLS -- conexion sin cifrar", host)
    conn.login(username, password)
    return conn


def get_uidvalidity(conn: imaplib.IMAP4, folder: str) -> Optional[int]:
    conn.select(folder)
    try:
        _typ, data = conn.response("UIDVALIDITY")
        if data and data[0]:
            return int(data[0])
    except Exception:
        pass
    return None


def list_new_imap_messages(conn: imaplib.IMAP4, folder: str, last_uid: Optional[int]) -> list:
    conn.select(folder)
    if last_uid is None:
        typ, data = conn.uid("search", None, "ALL")
        uids = [int(x) for x in data[0].split()] if typ == "OK" and data and data[0] else []
        uids = uids[-_MAX_MESSAGES_PER_POLL:]
    else:
        typ, data = conn.uid("search", None, f"UID {last_uid + 1}:*")
        uids = [int(x) for x in data[0].split()] if typ == "OK" and data and data[0] else []
        uids = [u for u in uids if u > last_uid][:_MAX_MESSAGES_PER_POLL]

    messages = []
    for uid in uids:
        typ, msg_data = conn.uid("fetch", str(uid), "(RFC822)")
        if typ != "OK" or not msg_data or not msg_data[0]:
            continue
        raw = msg_data[0][1]
        messages.append((uid, raw))
    return messages


# ---------- Dispatcher deterministico vs IA + creacion del Supplier ----------

def _next_supplier_code(db: Session) -> str:
    from sqlalchemy import func as _func
    from app.models import Supplier
    max_id = db.query(_func.max(Supplier.id)).scalar() or 0
    return f"SUP-{max_id + 1:04d}"


def _matches_allowlist(sender: str, allowlist: Optional[list]) -> bool:
    if not allowlist:
        return True
    sender = (sender or "").lower()
    for pattern in allowlist:
        if fnmatch.fnmatch(sender, str(pattern).lower().strip()):
            return True
    return False


def _persist_attachment(db: Session, supplier, org_id: Optional[int], filename: str, data: bytes) -> None:
    """Guarda el adjunto original cifrado como SupplierDocument (trazabilidad TPRM)."""
    from app.models import SupplierDocument
    from app.services.document_service import save_document_file
    safe_name = sanitize_filename(filename)
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    try:
        save_document_file(data, stored_name)
        doc = SupplierDocument(
            organization_id=org_id,
            supplier_id=supplier.id,
            filename=safe_name,
            stored_name=stored_name,
            size=len(data),
            description="Adjunto recibido por email (Via 4 — alta automatica)",
        )
        db.add(doc)
    except Exception as exc:
        logger.warning("email_intake: error guardando adjunto '%s': %s", filename, exc)


def process_email(cfg, db: Session, parsed: dict, org_id: Optional[int]) -> dict:
    """Procesa un mail ya parseado y crea el Supplier correspondiente. Ver docstring del modulo."""
    from app.models import Supplier

    sender = parsed.get("from_addr") or ""
    subject = parsed.get("subject") or ""

    if not _matches_allowlist(sender, cfg.email_intake_sender_allowlist):
        return {"ok": False, "skipped": True, "reason": "remitente no permitido"}
    if cfg.email_intake_subject_filter and cfg.email_intake_subject_filter.lower() not in subject.lower():
        return {"ok": False, "skipped": True, "reason": "asunto no coincide con el filtro"}

    message_id = parsed.get("message_id")
    if message_id:
        existing = db.query(Supplier).filter(
            Supplier.organization_id == org_id,
            Supplier.email_message_id == message_id,
        ).first()
        if existing:
            return {"ok": False, "skipped": True, "reason": "mail ya procesado (dedupe por Message-ID)"}

    field_mapping = cfg.email_intake_field_mapping or {}

    structured_fields: dict = {}
    ai_attachment: Optional[dict] = None
    valid_attachments: list[dict] = []

    for att in (parsed.get("attachments") or [])[:_MAX_ATTACHMENTS_PER_MAIL]:
        ok, reason = validate_attachment(att.get("filename", ""), att.get("content_type", ""), att.get("data", b""))
        if not ok:
            logger.info("email_intake: adjunto '%s' descartado: %s", att.get("filename"), reason)
            continue
        valid_attachments.append(att)
        fname = (att.get("filename") or "").lower()
        if fname.endswith(".pdf"):
            fields = extract_pdf_form_fields(att["data"])
        elif fname.endswith(".docx"):
            fields = extract_docx_form_fields(att["data"])
        else:
            fields = {}
        if fields:
            mapped = map_structured_fields_to_supplier(fields, field_mapping)
            for k, v in mapped.items():
                structured_fields.setdefault(k, v)
        elif ai_attachment is None:
            ai_attachment = att

    extraction_method = "deterministic" if structured_fields else "ai"
    extracted_ai: dict = {}

    if not structured_fields:
        try:
            from app.services.supplier_document_analyzer import _call_claude, _extract_text, _parse_json
            if ai_attachment is not None:
                text = _extract_text(ai_attachment["data"], ai_attachment.get("filename", ""))
            else:
                text = parsed.get("body_text") or ""
            if len(text.strip()) >= 30:
                raw = _call_claude(db, org_id, text)
                extracted_ai = _parse_json(raw)
        except Exception as exc:
            logger.warning("email_intake: error en extraccion IA: %s", exc)

    name = structured_fields.get("name") or extracted_ai.get("name")
    needs_review = False
    if not name or not str(name).strip():
        name = (parsed.get("from_display") or parsed.get("from_addr") or subject or "Proveedor sin nombre")[:255]
        needs_review = True
    if extraction_method == "ai" and not extracted_ai:
        needs_review = True

    code = _next_supplier_code(db)
    supplier = Supplier(
        code=code,
        name=str(name).strip()[:255],
        contact_email=(structured_fields.get("contact_email") or extracted_ai.get("contact_email") or sender or None),
        description=structured_fields.get("description"),
        services=structured_fields.get("services"),
        category=structured_fields.get("category"),
        contact_name=structured_fields.get("contact_name"),
        website=structured_fields.get("website"),
        contract_ref=structured_fields.get("contract_ref"),
        notes=f"Alta automatica via email (Via 4). Remitente: {sender or 'desconocido'}. Asunto: {subject[:200]}",
        organization_id=org_id,
        risk_level="medium",
        email_origin=True,
        email_sender=sender or None,
        email_subject=subject[:500] if subject else None,
        email_message_id=message_id,
        email_extraction_method=extraction_method,
        email_needs_review=needs_review,
    )
    # Punto 1: usar respuestas del formulario para la clasificacion inicial
    # (importancia de negocio / riesgo de seguridad / region / frecuencia), con
    # normalizacion ES/EN. Se valida/confirma tras el cuestionario.
    try:
        _apply_form_classification(supplier, structured_fields)
    except Exception as exc:  # noqa: BLE001
        logger.warning("email_intake: error aplicando clasificacion del formulario: %s", exc)

    db.add(supplier)
    db.flush()

    if extracted_ai:
        from app.services.supplier_document_analyzer import _apply_fields
        try:
            _apply_fields(supplier, extracted_ai)
        except Exception as exc:
            logger.warning("email_intake: error aplicando campos IA extra: %s", exc)
    elif structured_fields and cfg.email_intake_auto_ai_review:
        # Pasada IA adicional aditiva sobre el mismo adjunto para enriquecer SLAs/certificaciones/contactos
        # que el formulario no capture como campo. _apply_fields solo rellena campos vacios, nunca pisa
        # lo ya extraido deterministicamente.
        try:
            from app.services.supplier_document_analyzer import _apply_fields, _call_claude, _extract_text, _parse_json
            source_att = valid_attachments[0] if valid_attachments else None
            if source_att is not None:
                text = _extract_text(source_att["data"], source_att.get("filename", ""))
                if len(text.strip()) >= 30:
                    raw = _call_claude(db, org_id, text)
                    extra = _parse_json(raw)
                    if extra:
                        _apply_fields(supplier, extra)
        except Exception as exc:
            logger.warning("email_intake: error en pasada IA aditiva: %s", exc)

    for att in valid_attachments:
        _persist_attachment(db, supplier, org_id, att.get("filename", "adjunto"), att.get("data", b""))

    try:
        from app.services.tprm_scoring_service import recompute_supplier
        recompute_supplier(db, supplier, commit=False)
    except Exception as exc:
        logger.warning("email_intake: error TPRM scoring '%s': %s", supplier.name, exc)

    db.commit()
    db.refresh(supplier)
    logger.info("email_intake: proveedor %s creado desde email (metodo=%s, needs_review=%s)",
                supplier.code, extraction_method, needs_review)
    return {"ok": True, "skipped": False, "supplier_id": supplier.id, "needs_review": needs_review}


# ---------- Entry points de polling ----------

def poll_org_graph(cfg, db: Session) -> dict:
    result: dict = {"checked": 0, "created": 0, "skipped": 0, "errors": []}
    client_secret = _fernet_decrypt(cfg.email_intake_graph_client_secret_enc or "")
    if not client_secret:
        result["errors"].append("Error descifrando client_secret de Graph -- reconfigurar credenciales")
        return result
    token = get_oauth_token(cfg.email_intake_graph_tenant_id, cfg.email_intake_graph_client_id, client_secret)
    if not token:
        result["errors"].append("Error obteniendo token OAuth2 de Azure AD")
        return result

    since_iso = cfg.email_intake_graph_last_received_ts or ""
    messages = list_new_graph_messages(cfg.email_intake_graph_mailbox, token, since_iso)
    result["checked"] = len(messages)

    org_id = cfg.organization_id
    last_ts = since_iso
    last_id = cfg.email_intake_graph_last_message_id

    for message in messages:
        try:
            parsed = _parse_graph_message(message)
            if message.get("hasAttachments"):
                parsed["attachments"] = get_graph_attachments(cfg.email_intake_graph_mailbox, message["id"], token)
            outcome = process_email(cfg, db, parsed, org_id)
            if outcome.get("skipped"):
                result["skipped"] += 1
            elif outcome.get("ok"):
                result["created"] += 1
            received = message.get("receivedDateTime") or ""
            if received >= last_ts:
                last_ts = received
                last_id = message.get("id")
        except Exception as exc:
            logger.error("email_intake: error procesando mensaje Graph %s: %s", message.get("id", "?"), exc)
            result["errors"].append(f"Mensaje {message.get('id', '?')}: {str(exc)[:150]}")
            try:
                db.rollback()
            except Exception:
                pass

    try:
        cfg.email_intake_last_poll_at = datetime.now(timezone.utc)
        cfg.email_intake_graph_last_received_ts = last_ts or since_iso
        cfg.email_intake_graph_last_message_id = last_id
        db.commit()
    except Exception as exc:
        logger.error("email_intake: error guardando cursor Graph: %s", exc)

    return result


def poll_org_imap(cfg, db: Session) -> dict:
    result: dict = {"checked": 0, "created": 0, "skipped": 0, "errors": []}
    password = _fernet_decrypt(cfg.email_intake_imap_password_enc or "")
    if not password:
        result["errors"].append("Error descifrando password IMAP -- reconfigurar credenciales")
        return result

    conn = None
    try:
        conn = _imap_connect(
            cfg.email_intake_imap_host, cfg.email_intake_imap_port or 993,
            cfg.email_intake_imap_username, password,
            cfg.email_intake_imap_use_ssl if cfg.email_intake_imap_use_ssl is not None else True,
        )
        folder = cfg.email_intake_imap_folder or "INBOX"
        uidvalidity = get_uidvalidity(conn, folder)
        last_uid = cfg.email_intake_imap_last_uid
        if cfg.email_intake_imap_uidvalidity and uidvalidity and cfg.email_intake_imap_uidvalidity != uidvalidity:
            logger.warning("email_intake: UIDVALIDITY cambio para %s -- reseteando cursor", cfg.email_intake_imap_host)
            last_uid = None

        messages = list_new_imap_messages(conn, folder, last_uid)
        result["checked"] = len(messages)
        org_id = cfg.organization_id
        max_uid = last_uid

        for uid, raw in messages:
            try:
                parsed = parse_email_message(raw)
                outcome = process_email(cfg, db, parsed, org_id)
                if outcome.get("skipped"):
                    result["skipped"] += 1
                elif outcome.get("ok"):
                    result["created"] += 1
                if max_uid is None or uid > max_uid:
                    max_uid = uid
            except Exception as exc:
                logger.error("email_intake: error procesando mensaje IMAP UID %s: %s", uid, exc)
                result["errors"].append(f"UID {uid}: {str(exc)[:150]}")
                try:
                    db.rollback()
                except Exception:
                    pass

        cfg.email_intake_last_poll_at = datetime.now(timezone.utc)
        cfg.email_intake_imap_last_uid = max_uid
        cfg.email_intake_imap_uidvalidity = uidvalidity
        db.commit()
    except Exception as exc:
        logger.error("email_intake: error de conexion IMAP: %s", exc)
        result["errors"].append(f"Error IMAP: {str(exc)[:150]}")
    finally:
        if conn is not None:
            try:
                conn.logout()
            except Exception:
                pass

    return result


def poll_org(cfg, db: Session) -> dict:
    if cfg.email_intake_mode == "graph":
        return poll_org_graph(cfg, db)
    if cfg.email_intake_mode == "imap":
        return poll_org_imap(cfg, db)
    return {"checked": 0, "created": 0, "skipped": 0, "errors": ["Modo de conexion no configurado"]}


def poll_all_orgs() -> None:
    """Llamado por el scheduler cada hora. Revisa si cada org necesita polling (Via 4)."""
    from app.database import SessionLocal
    from app.models import FormIntegrationConfig

    now = datetime.now(timezone.utc)
    try:
        with SessionLocal() as db:
            cfgs = (
                db.query(FormIntegrationConfig)
                .filter(
                    FormIntegrationConfig.email_intake_enabled.is_(True),
                    FormIntegrationConfig.email_intake_mode.isnot(None),
                )
                .all()
            )
            for cfg in cfgs:
                interval_h = cfg.email_intake_poll_interval_hours or 2
                if cfg.email_intake_last_poll_at:
                    last = cfg.email_intake_last_poll_at
                    if not last.tzinfo:
                        last = last.replace(tzinfo=timezone.utc)
                    elapsed_h = (now - last).total_seconds() / 3600
                    if elapsed_h < interval_h:
                        continue
                try:
                    res = poll_org(cfg, db)
                    logger.info(
                        "email_intake -- org %d: revisados=%d creados=%d omitidos=%d errores=%d",
                        cfg.organization_id or 0, res["checked"], res["created"],
                        res["skipped"], len(res["errors"]),
                    )
                except Exception as exc:
                    logger.error("email_intake -- org %d error inesperado: %s", cfg.organization_id or 0, exc)
    except Exception as exc:
        logger.error("email_intake poll_all_orgs error global: %s", exc)
