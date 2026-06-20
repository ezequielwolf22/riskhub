"""Servicio de aprobacion de documentos ISMS — rondas paralelas y secuenciales."""
import html
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import ApprovalRequest, PolicyApproval, Policy, Organization, PolicyStatus
from app.services import email_service


def create_approval_request(
    db: Session,
    policy_id: int,
    requested_by_id: int,
    approvers: list[dict],  # [{email, name, order_index}]
    mode: str,
    org_id: Optional[int],
    app_base_url: str,
) -> ApprovalRequest:
    """Crea una ronda de aprobacion y envia los primeros emails."""
    # Cancelar rondas pendientes previas para esta politica
    existing = db.query(ApprovalRequest).filter_by(policy_id=policy_id, status="pending").all()
    for req in existing:
        req.status = "cancelled"

    req = ApprovalRequest(
        organization_id=org_id,
        policy_id=policy_id,
        requested_by_id=requested_by_id,
        mode=mode,
        status="pending",
    )
    db.add(req)
    db.flush()

    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    policy = db.query(Policy).filter_by(id=policy_id).first()
    if policy:
        policy.status = PolicyStatus.REVIEW

    approval_objs = []
    for item in approvers:
        idx = item.get("order_index", 1)
        if mode == "parallel":
            initial_status = "pending"
        else:
            initial_status = "pending" if idx == 1 else "waiting"

        approval = PolicyApproval(
            organization_id=org_id,
            request_id=req.id,
            approver_email=item["email"],
            approver_name=item.get("name") or None,
            token=secrets.token_urlsafe(32),
            status=initial_status,
            order_index=idx,
            expires_at=expires_at,
        )
        db.add(approval)
        approval_objs.append(approval)

    db.flush()

    cfg = email_service.get_settings(db, org_id)
    if cfg and cfg.smtp_host:
        for approval in approval_objs:
            if approval.status == "pending":
                _send_approval_email(cfg, approval, policy, app_base_url, db)
                approval.sent_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(req)
    return req


def _send_approval_email(cfg, approval: PolicyApproval, policy: Policy, app_base_url: str, db: Session):
    """Envia email de solicitud de aprobacion a un aprobador."""
    org_name = "RiskHub"
    if policy and policy.organization_id:
        org = db.query(Organization).filter_by(id=policy.organization_id).first()
        if org:
            org_name = org.name

    base = app_base_url.rstrip("/")
    approve_url = f"{base}/approve.html?token={approval.token}"

    p_code = html.escape(policy.code if policy else "")
    p_title = html.escape(policy.title if policy else "")
    p_version = html.escape(policy.version if policy else "1.0")

    body = f"""
    <p>Has recibido una solicitud de aprobacion para el siguiente documento de seguridad:</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0;background:#f9f9f9;
                  border-radius:8px;overflow:hidden;border:1px solid #e5e7eb;">
      <tr>
        <td style="padding:10px 14px;font-size:12px;color:#6b7280;font-weight:600;width:130px;
                   border-bottom:1px solid #e5e7eb;">Documento</td>
        <td style="padding:10px 14px;font-size:13px;border-bottom:1px solid #e5e7eb;">
          <strong>{p_code} — {p_title}</strong></td>
      </tr>
      <tr>
        <td style="padding:10px 14px;font-size:12px;color:#6b7280;font-weight:600;
                   border-bottom:1px solid #e5e7eb;">Version</td>
        <td style="padding:10px 14px;font-size:13px;border-bottom:1px solid #e5e7eb;">{p_version}</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;font-size:12px;color:#6b7280;font-weight:600;">Aplicacion</td>
        <td style="padding:10px 14px;font-size:13px;">
          <a href="{html.escape(base)}" style="color:#59008D;">{html.escape(base)}</a></td>
      </tr>
    </table>
    <div style="margin:28px 0;text-align:center;">
      <a href="{html.escape(approve_url)}"
         style="display:inline-block;background:linear-gradient(90deg,#59008D,#D65200);
                color:#fff;text-decoration:none;padding:13px 36px;border-radius:8px;
                font-weight:700;font-size:15px;letter-spacing:.2px;">
        Revisar y responder
      </a>
    </div>
    <p style="font-size:12px;color:#9ca3af;margin-top:16px;line-height:1.6;">
      Este enlace caduca en 30 dias. Si el boton no funciona, copia esta URL en tu navegador:<br>
      <span style="color:#59008D;word-break:break-all;">{html.escape(approve_url)}</span>
    </p>
    <p style="font-size:12px;color:#9ca3af;">
      Si no esperabas esta solicitud puedes ignorar este correo.
    </p>
    """

    full_html = _wrap_html(
        f"Solicitud de aprobacion: {p_code} — {p_title}",
        body,
        org_name,
    )
    try:
        email_service.send_email(
            cfg,
            approval.approver_email,
            f"[RiskHub] Solicitud de aprobacion: {p_code} — {p_title}",
            full_html,
        )
    except Exception:
        pass  # No bloquear si el email falla


def process_decision(
    db: Session,
    token: str,
    decision: str,
    notes: str,
    ip_address: str,
    app_base_url: str,
) -> dict:
    """Procesa la decision de un aprobador (approved | rejected)."""
    approval = db.query(PolicyApproval).filter_by(token=token).first()
    if not approval:
        return {"error": "Token no encontrado o invalido"}

    if approval.status not in ("pending",):
        return {"error": "Este enlace ya fue utilizado o no esta disponible"}

    now = datetime.now(timezone.utc)
    expires = approval.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if now > expires:
        return {"error": "Este enlace ha caducado (30 dias de vigencia)"}

    approval.status = decision
    approval.responded_at = now
    approval.response_notes = notes or None
    approval.ip_address = ip_address

    req = approval.request
    policy = req.policy if req else None

    if decision == "rejected":
        req.status = "rejected"
        req.completed_at = now
        if policy:
            policy.status = PolicyStatus.DRAFT
        _notify_creator(db, req, policy, rejected_by=approval, app_base_url=app_base_url)
        db.commit()
        return {"status": "rejected", "policy_title": policy.title if policy else ""}

    # approved — verificar si hay siguiente en secuencial o si todos aprobaron
    all_approvals = list(req.approvals)

    if req.mode == "sequential":
        next_approval = next(
            (a for a in sorted(all_approvals, key=lambda x: x.order_index)
             if a.order_index > approval.order_index and a.status == "waiting"),
            None,
        )
        if next_approval:
            next_approval.status = "pending"
            db.flush()
            cfg = email_service.get_settings(db, req.organization_id)
            if cfg and cfg.smtp_host:
                _send_approval_email(cfg, next_approval, policy, app_base_url, db)
                next_approval.sent_at = now
            db.commit()
            return {"status": "approved_partial", "policy_title": policy.title if policy else ""}

    # Verificar si todos aprobaron
    all_done = all(a.status == "approved" for a in all_approvals)
    if all_done:
        req.status = "approved"
        req.completed_at = now
        if policy:
            policy.status = PolicyStatus.APPROVED
            policy.approved_at = now
            if policy.previous_version_id:
                prev = db.query(Policy).filter_by(id=policy.previous_version_id).first()
                if prev and prev.status not in (PolicyStatus.OBSOLETE,):
                    prev.status = PolicyStatus.OBSOLETE
        _notify_creator(db, req, policy, rejected_by=None, app_base_url=app_base_url)
        db.commit()
        return {"status": "approved", "policy_title": policy.title if policy else ""}

    db.commit()
    return {"status": "approved_partial", "policy_title": policy.title if policy else ""}


def _notify_creator(db, req: ApprovalRequest, policy, rejected_by, app_base_url: str):
    """Notifica al creador sobre el resultado de la ronda de aprobacion."""
    creator = req.requested_by
    if not creator or not creator.email:
        return
    cfg = email_service.get_settings(db, req.organization_id)
    if not cfg or not cfg.smtp_host:
        return

    org_name = "RiskHub"
    if req.organization_id:
        org = db.query(Organization).filter_by(id=req.organization_id).first()
        if org:
            org_name = org.name

    base = app_base_url.rstrip("/")
    p_code = html.escape(policy.code if policy else "")
    p_title = html.escape(policy.title if policy else "")
    p_ver = html.escape(policy.version if policy else "1.0")

    if rejected_by:
        color, verb = "#dc2626", "RECHAZADO"
        extra = f"<p><strong>Rechazado por:</strong> {html.escape(rejected_by.approver_email)}</p>"
        if rejected_by.response_notes:
            extra += f"<p><strong>Comentarios:</strong> {html.escape(rejected_by.response_notes)}</p>"
        extra += "<p>El estado del documento ha vuelto a <strong>Borrador</strong>.</p>"
        subject = f"[RiskHub] Documento rechazado: {p_code}"
    else:
        color, verb = "#22c55e", "APROBADO"
        extra = "<p>El estado del documento ha sido actualizado a <strong>Aprobado</strong>.</p>"
        subject = f"[RiskHub] Documento aprobado: {p_code}"

    body = f"""
    <p>El documento <strong>{p_code} — {p_title}</strong> (v{p_ver}) ha sido
       <strong style="color:{color};">{verb}</strong>.</p>
    {extra}
    <div style="margin:20px 0;text-align:center;">
      <a href="{html.escape(base)}"
         style="display:inline-block;background:#59008D;color:#fff;text-decoration:none;
                padding:10px 24px;border-radius:6px;font-weight:600;">
        Ver en RiskHub
      </a>
    </div>
    """
    full_html = _wrap_html(f"Documento {verb.lower()}: {p_code}", body, org_name)
    try:
        email_service.send_email(cfg, creator.email, subject, full_html)
    except Exception:
        pass


def get_approval_info(db: Session, token: str) -> dict:
    """Info publica para la pagina de aprobacion (sin autenticacion)."""
    approval = db.query(PolicyApproval).filter_by(token=token).first()
    if not approval:
        return {"error": "Token no encontrado o invalido"}

    req = approval.request
    policy = req.policy if req else None

    now = datetime.now(timezone.utc)
    expires = approval.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    total = len(req.approvals) if req else 1
    approved_count = sum(1 for a in req.approvals if a.status == "approved") if req else 0

    return {
        "token": token,
        "policy_code": policy.code if policy else "",
        "policy_title": policy.title if policy else "",
        "policy_version": policy.version if policy else "1.0",
        "policy_scope": policy.scope or "" if policy else "",
        "approver_email": approval.approver_email,
        "approver_name": approval.approver_name or "",
        "status": approval.status,
        "mode": req.mode if req else "parallel",
        "order_index": approval.order_index,
        "total_approvers": total,
        "approved_count": approved_count,
        "expires_at": expires.isoformat(),
        "expired": now > expires,
        "already_responded": approval.status not in ("pending", "waiting"),
        "is_waiting": approval.status == "waiting",
    }


def _wrap_html(subject: str, body: str, org: str) -> str:
    """Envoltura HTML para emails de aprobacion (misma paleta que la app)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:24px;background:#F5F5F5;font-family:Inter,Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:10px;
              border:1px solid #E9E9E9;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <div style="background:linear-gradient(90deg,#59008D,#D65200);padding:20px 28px;">
      <h1 style="color:#fff;margin:0;font-size:18px;font-weight:700;">{subject}</h1>
      <p style="color:rgba(255,255,255,.75);margin:4px 0 0;font-size:13px;">{html.escape(org)}</p>
    </div>
    <div style="padding:28px;font-size:14px;color:#262626;line-height:1.6;">
      {body}
      <p style="color:#9D9D9D;font-size:11px;margin-top:24px;margin-bottom:0;">
        Generado automaticamente por RiskHub el {now}.
      </p>
    </div>
  </div>
</body>
</html>"""
