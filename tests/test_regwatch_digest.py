"""Digest periodico de regwatch (§5.4): cadencia, render y envio."""
from datetime import datetime, timedelta, timezone

from app.services import regwatch_service as rw


class _S:
    """Stub minimo de TenantRegwatchSettings para _digest_due."""
    def __init__(self, freq, last):
        self.digest_frequency = freq
        self.last_digest_sent_at = last


def test_digest_due_by_frequency():
    now = datetime.now(timezone.utc)
    # Nunca enviado -> toca (salvo 'never')
    assert rw._digest_due(_S("daily", None), now) is True
    assert rw._digest_due(_S("never", None), now) is False
    # Enviado hace 2 dias: daily toca, weekly no
    two_days = now - timedelta(days=2)
    assert rw._digest_due(_S("daily", two_days), now) is True
    assert rw._digest_due(_S("weekly", two_days), now) is False
    # Weekly con 8 dias -> toca; monthly con 8 dias -> no
    eight_days = now - timedelta(days=8)
    assert rw._digest_due(_S("weekly", eight_days), now) is True
    assert rw._digest_due(_S("monthly", eight_days), now) is False
    # Frecuencia None cae al default weekly
    assert rw._digest_due(_S(None, eight_days), now) is True


def test_render_digest_html_escapes_and_counts():
    items = [
        {"severity": "breaking", "framework": "ISO/IEC 27001",
         "title": "Cambio <script>alert(1)</script> critico",
         "change_counts": {"added": 2, "modified": 5, "removed": 1}},
        {"severity": "substantive", "framework": "GDPR",
         "title": "Guia nueva", "change_counts": {}},
    ]
    subject, html = rw._render_digest_html("Acme & Co", items, "weekly")
    assert "2 cambio(s)" in subject
    # Escapado de HTML hostil y del nombre de la org
    assert "<script>" not in html
    assert "Acme &amp; Co" in html
    assert "+2 / ~5 / -1" in html
    assert "CRITICO" in html and "Relevante" in html
    # Sin backlog no se menciona la coletilla de pendientes previos
    assert "avisos anteriores" not in html


def test_render_digest_html_mentions_backlog_without_repeating_it():
    """Lo ya avisado se resume como cifra; no se reenvia entero."""
    items = [{"severity": "substantive", "framework": "GDPR",
              "title": "Guia nueva", "change_counts": {}}]
    _, html = rw._render_digest_html("Acme", items, "weekly", backlog=3)
    assert "avisos anteriores" in html
    assert "<b>3</b>" in html


def test_send_pending_digests_no_orgs(client):
    """Con ninguna org con regwatch activo, el resumen queda a cero y no falla."""
    from tests.conftest import _TestSession
    db = _TestSession()
    try:
        summary = rw.send_pending_digests(db)
        assert summary["sent"] == 0
    finally:
        db.close()


def _setup_org_with_pending_item(db, freq="daily"):
    """Org con regwatch activo, un canal de alerta y un item pendiente."""
    from app.models import (ChangePack, ChangeSeverity, EmailSettings,
                            InboxItemStatus, Organization, TenantChangeInboxItem)
    org = db.query(Organization).first()
    s = rw.get_or_create_settings(db, org.id)
    s.is_enabled = True
    s.digest_frequency = freq
    s.last_digest_sent_at = None
    s.notification_email = "aviso@example.com"

    cfg = db.query(EmailSettings).filter_by(organization_id=org.id).first()
    if not cfg:
        cfg = EmailSettings(organization_id=org.id)
        db.add(cfg)
    cfg.smtp_host = "smtp.example.com"

    pack = ChangePack(framework_code="ISO_27001", severity=ChangeSeverity.BREAKING,
                      title_es="Cambio de prueba", published_at=datetime.now(timezone.utc))
    db.add(pack)
    db.flush()
    item = TenantChangeInboxItem(organization_id=org.id, change_pack_id=pack.id,
                                 status=InboxItemStatus.PENDING)
    db.add(item)
    db.commit()
    return org, s, item


def test_digest_does_not_repeat_an_already_notified_item(client, monkeypatch):
    """El mismo pendiente no se reenvia cada semana: solo se avisa una vez."""
    from tests.conftest import _TestSession
    db = _TestSession()
    org = None
    try:
        org, s, item = _setup_org_with_pending_item(db)
        sent = []
        monkeypatch.setattr(
            "app.services.notification_channels.dispatch_alert",
            lambda *a, **k: sent.append(k.get("html_body") or a) or {},
        )

        assert rw.send_pending_digests(db)["sent"] == 1
        assert len(sent) == 1
        db.refresh(item)
        assert item.notified_at is not None

        # Vence la cadencia otra vez, pero el item sigue siendo el mismo: silencio.
        s.last_digest_sent_at = datetime.now(timezone.utc) - timedelta(days=30)
        db.commit()
        summary = rw.send_pending_digests(db)
        assert summary["sent"] == 0
        assert summary["skipped_no_items"] >= 1
        assert len(sent) == 1  # no ha salido un segundo correo
    finally:
        if org is not None:
            _cleanup(db, org)
        db.close()


def test_digest_reminds_again_when_snooze_expires(client, monkeypatch):
    """"Recordarme luego" cumple lo que promete: al vencer, vuelve a avisar."""
    from tests.conftest import _TestSession
    from app.models import InboxItemStatus
    db = _TestSession()
    org = None
    try:
        org, s, item = _setup_org_with_pending_item(db)
        monkeypatch.setattr(
            "app.services.notification_channels.dispatch_alert", lambda *a, **k: {})
        assert rw.send_pending_digests(db)["sent"] == 1

        # El usuario lo aplaza y el aplazamiento vence
        item.status = InboxItemStatus.SNOOZED
        item.snoozed_until = datetime.now(timezone.utc) - timedelta(hours=1)
        s.last_digest_sent_at = datetime.now(timezone.utc) - timedelta(days=30)
        db.commit()

        assert rw.send_pending_digests(db)["sent"] == 1
        db.refresh(item)
        assert item.status == InboxItemStatus.PENDING
        assert item.snoozed_until is None
    finally:
        if org is not None:
            _cleanup(db, org)
        db.close()


def test_digest_stays_silent_while_snoozed(client, monkeypatch):
    """Un item aplazado y aun vigente no genera correo."""
    from tests.conftest import _TestSession
    from app.models import InboxItemStatus
    db = _TestSession()
    org = None
    try:
        org, s, item = _setup_org_with_pending_item(db)
        item.status = InboxItemStatus.SNOOZED
        item.snoozed_until = datetime.now(timezone.utc) + timedelta(days=5)
        db.commit()
        monkeypatch.setattr(
            "app.services.notification_channels.dispatch_alert", lambda *a, **k: {})
        assert rw.send_pending_digests(db)["sent"] == 0
    finally:
        if org is not None:
            _cleanup(db, org)
        db.close()


def _cleanup(db, org):
    from app.models import ChangePack, EmailSettings, TenantChangeInboxItem
    db.query(TenantChangeInboxItem).filter_by(organization_id=org.id).delete()
    db.query(ChangePack).delete()
    cfg = db.query(EmailSettings).filter_by(organization_id=org.id).first()
    if cfg:
        cfg.smtp_host = None
    s = rw.get_or_create_settings(db, org.id)
    s.is_enabled = False
    db.commit()


def test_send_pending_digests_respects_cadence(client, monkeypatch):
    """Org activa sin items pendientes: marca el envio y no molesta."""
    from tests.conftest import _TestSession
    from app.models import Organization
    db = _TestSession()
    try:
        org = db.query(Organization).first()
        s = rw.get_or_create_settings(db, org.id)
        s.is_enabled = True
        s.digest_frequency = "daily"
        s.last_digest_sent_at = None
        db.commit()

        sent = []
        monkeypatch.setattr(
            "app.services.notification_channels.dispatch_alert",
            lambda *a, **k: sent.append(1) or {},
        )
        summary = rw.send_pending_digests(db)
        # Sin items pendientes -> skipped_no_items y sella last_digest_sent_at
        assert summary["skipped_no_items"] >= 1
        assert sent == []
        db.refresh(s)
        assert s.last_digest_sent_at is not None

        # Segunda pasada inmediata: ya no toca (cadencia daily)
        summary2 = rw.send_pending_digests(db)
        assert summary2["skipped_not_due"] >= 1
    finally:
        # Dejar el toggle como estaba para no contaminar otros tests
        s = rw.get_or_create_settings(db, org.id)
        s.is_enabled = False
        db.commit()
        db.close()
