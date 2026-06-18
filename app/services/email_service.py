"""Servicio SMTP para envio de alertas por correo electronico."""
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from sqlalchemy.orm import Session

from app.models import EmailSettings, Risk


def _smtp_password(cfg: EmailSettings) -> str:
    """Devuelve la contrasena SMTP descifrada. Usa campo cifrado si existe, si no el legacy."""
    if cfg.smtp_password_encrypted:
        try:
            from app.security import decrypt_secret
            return decrypt_secret(cfg.smtp_password_encrypted)
        except Exception:
            pass
    return cfg.smtp_password or ""


def get_settings(db: Session, org_id: Optional[int] = None) -> Optional[EmailSettings]:
    """Devuelve la config SMTP.

    A1 (audit3): siempre filtrar por org_id para evitar cross-tenant SMTP.
    """
    q = db.query(EmailSettings)
    if org_id is not None:
        q = q.filter(EmailSettings.organization_id == org_id)
    return q.first()


def get_settings_for_org(db: Session, org_id: int) -> Optional[EmailSettings]:
    """Per-org SMTP — usar en jobs del scheduler para evitar cross-tenant SMTP."""
    return db.query(EmailSettings).filter_by(organization_id=org_id).first()


def send_email(
    cfg: EmailSettings,
    recipient: str,
    subject: str,
    body_html: str,
    cc: list[str] | None = None,
) -> None:
    """Envia un email HTML via SMTP. Lanza RuntimeError si falla."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.smtp_from
    msg["To"] = recipient
    cc_clean = [a for a in (cc or []) if a and a.strip() and a.strip() != recipient]
    if cc_clean:
        msg["Cc"] = ", ".join(cc_clean)
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    all_recipients = [recipient] + cc_clean

    try:
        if cfg.smtp_use_tls:
            srv = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15)
            srv.ehlo()
            srv.starttls()
            srv.ehlo()
        else:
            srv = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=15)

        if cfg.smtp_user:
            srv.login(cfg.smtp_user, _smtp_password(cfg))

        srv.sendmail(cfg.smtp_from, all_recipients, msg.as_string())
        srv.quit()
    except Exception as exc:
        raise RuntimeError(f"Error SMTP: {exc}") from exc


def risk_alert_html(risk: Risk, org_name: str, reason: str) -> str:
    lvl = risk.residual_level
    color = "#B91C1C" if lvl >= 7 else "#D97706" if lvl >= 5 else "#59008D"
    label = "CRITICO" if lvl >= 7 else "ALTO" if lvl >= 5 else "MEDIO"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    treatment = risk.treatment_option.value if risk.treatment_option else "No definido"
    return f"""<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:24px;background:#F5F5F5;font-family:Inter,Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:10px;
              border:1px solid #E9E9E9;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <div style="background:linear-gradient(90deg,#59008D,#D65200);padding:20px 28px;">
      <h1 style="color:#fff;margin:0;font-size:20px;font-weight:700;">
        RiskHub &mdash; Alerta de riesgo
      </h1>
      <p style="color:rgba(255,255,255,.75);margin:4px 0 0;font-size:13px;">{org_name}</p>
    </div>
    <div style="padding:28px;">
      <div style="background:#FFF7ED;border-left:4px solid {color};
                  border-radius:0 6px 6px 0;padding:12px 16px;margin-bottom:20px;">
        <strong style="color:{color};font-size:13px;">{label}</strong>
        <p style="margin:4px 0 0;color:#262626;font-size:13px;">{reason}</p>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <tr style="background:#F5F5F5;">
          <td style="padding:9px 12px;font-weight:600;width:38%;">Codigo</td>
          <td style="padding:9px 12px;">{risk.code}</td>
        </tr>
        <tr>
          <td style="padding:9px 12px;font-weight:600;">Activo</td>
          <td style="padding:9px 12px;">{risk.asset.name if risk.asset else '-'}</td>
        </tr>
        <tr style="background:#F5F5F5;">
          <td style="padding:9px 12px;font-weight:600;">Amenaza</td>
          <td style="padding:9px 12px;">{risk.threat.name if risk.threat else '-'}</td>
        </tr>
        <tr>
          <td style="padding:9px 12px;font-weight:600;">Nivel residual</td>
          <td style="padding:9px 12px;">
            <span style="background:{color};color:#fff;padding:2px 10px;
                         border-radius:4px;font-weight:700;">{lvl}</span>
          </td>
        </tr>
        <tr style="background:#F5F5F5;">
          <td style="padding:9px 12px;font-weight:600;">Estado</td>
          <td style="padding:9px 12px;">{risk.status.value if risk.status else '-'}</td>
        </tr>
        <tr>
          <td style="padding:9px 12px;font-weight:600;">Tratamiento</td>
          <td style="padding:9px 12px;">{treatment}</td>
        </tr>
      </table>
      <p style="color:#9D9D9D;font-size:11px;margin-top:24px;margin-bottom:0;">
        Generado automaticamente por RiskHub el {now}.
        Accede al sistema para revisar y actualizar el plan de tratamiento.
      </p>
    </div>
  </div>
</body>
</html>"""


def _wrap_html(subject: str, body: str, org: str) -> str:
    """Envoltura HTML generica para emails de notificacion."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:24px;background:#F5F5F5;font-family:Inter,Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:10px;
              border:1px solid #E9E9E9;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <div style="background:linear-gradient(90deg,#59008D,#D65200);padding:20px 28px;">
      <h1 style="color:#fff;margin:0;font-size:18px;font-weight:700;">{subject}</h1>
      <p style="color:rgba(255,255,255,.75);margin:4px 0 0;font-size:13px;">{org}</p>
    </div>
    <div style="padding:28px;font-size:14px;color:#262626;line-height:1.6;">
      {body}
      <p style="color:#9D9D9D;font-size:11px;margin-top:24px;margin-bottom:0;">
        Generado automaticamente por RiskHub el {now}.
        Accede al sistema para revisar los detalles.
      </p>
    </div>
  </div>
</body>
</html>"""


def test_email_html() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:24px;background:#F5F5F5;font-family:Inter,Arial,sans-serif;">
  <div style="max-width:500px;margin:0 auto;background:#fff;border-radius:10px;
              border:1px solid #E9E9E9;overflow:hidden;">
    <div style="background:linear-gradient(90deg,#59008D,#D65200);padding:20px 28px;">
      <h1 style="color:#fff;margin:0;font-size:18px;">RiskHub &mdash; Email de prueba</h1>
    </div>
    <div style="padding:28px;">
      <p style="color:#262626;font-size:14px;">
        La configuracion SMTP de RiskHub funciona correctamente.
      </p>
      <p style="color:#9D9D9D;font-size:12px;margin-bottom:0;">Enviado el {now}</p>
    </div>
  </div>
</body>
</html>"""
