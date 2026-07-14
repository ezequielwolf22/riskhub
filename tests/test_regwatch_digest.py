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


def test_send_pending_digests_no_orgs(client):
    """Con ninguna org con regwatch activo, el resumen queda a cero y no falla."""
    from tests.conftest import _TestSession
    db = _TestSession()
    try:
        summary = rw.send_pending_digests(db)
        assert summary["sent"] == 0
    finally:
        db.close()


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
