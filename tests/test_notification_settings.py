"""Tests del control total de notificaciones automaticas (panel Alertas).

Cubre: catalogo, edicion por alerta, umbral, destinatarios custom, validaciones,
silenciar-todo/reset, y la logica del servicio (should_notify + cooldown +
resolucion de destinatarios + gating de send_notification).
"""
from datetime import datetime, timedelta, timezone

from tests.conftest import _TestSession

from app.models import NotificationSetting, User
from app.services import notification_registry as reg
from app.services import notification_settings as ns


def _admin_org_id() -> int:
    db = _TestSession()
    try:
        u = db.query(User).filter(User.email == "admin@test.internal").first()
        return u.organization_id
    finally:
        db.close()


# ---------- Router ----------

def test_catalog_lists_all_alerts(client, auth_headers):
    r = client.get("/api/notification-settings", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    keys = {s["key"] for s in body["settings"]}
    # las alertas del flood deben estar presentes y cubiertas
    assert "kri_breach" in keys
    assert "ccm_fail" in keys
    assert keys == set(reg.VALID_ALERT_KEYS) & {
        e["key"] for e in reg.ALERT_CATALOG if e.get("audience", "org") in ("org", "platform")
    }
    # por defecto todo viene activo
    assert all(s["enabled"] for s in body["settings"])


def test_update_disables_alert(client, auth_headers):
    r = client.put("/api/notification-settings/ccm_fail",
                   json={"enabled": False}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False
    assert r.json()["configured"] is True

    g = client.get("/api/notification-settings", headers=auth_headers)
    ccm = next(s for s in g.json()["settings"] if s["key"] == "ccm_fail")
    assert ccm["enabled"] is False
    # re-activar para no contaminar otros tests
    client.put("/api/notification-settings/ccm_fail", json={"enabled": True}, headers=auth_headers)


def test_threshold_and_channel(client, auth_headers):
    r = client.put("/api/notification-settings/ccm_fail",
                   json={"threshold": 55.0, "channel": "all"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["threshold"] == 55.0
    assert body["channel"] == "all"
    assert body["supports_threshold"] is True
    # restaurar
    client.put("/api/notification-settings/ccm_fail",
               json={"threshold": 70.0, "channel": "email"}, headers=auth_headers)


def test_custom_recipients(client, auth_headers):
    r = client.put("/api/notification-settings/kri_breach",
                   json={"recipient_mode": "custom",
                         "recipients": ["ciso@example.com", "grc@example.com"]},
                   headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recipient_mode"] == "custom"
    assert set(body["recipients"]) == {"ciso@example.com", "grc@example.com"}
    # volver a admins
    client.put("/api/notification-settings/kri_breach",
               json={"recipient_mode": "admins"}, headers=auth_headers)


def test_invalid_key_and_channel(client, auth_headers):
    assert client.put("/api/notification-settings/does_not_exist",
                      json={"enabled": False}, headers=auth_headers).status_code == 404
    assert client.put("/api/notification-settings/ccm_fail",
                      json={"channel": "carrier_pigeon"}, headers=auth_headers).status_code == 422


def test_silence_all_then_reset(client, auth_headers):
    s = client.post("/api/notification-settings/silence-all", json={}, headers=auth_headers)
    assert s.status_code == 200, s.text
    assert s.json()["silenced"] >= 13

    g = client.get("/api/notification-settings", headers=auth_headers)
    assert all(not it["enabled"] for it in g.json()["settings"])

    # reset devuelve cada alerta al default (activa)
    for it in g.json()["settings"]:
        client.delete(f"/api/notification-settings/{it['key']}", headers=auth_headers)
    g2 = client.get("/api/notification-settings", headers=auth_headers)
    assert all(it["enabled"] for it in g2.json()["settings"])
    assert all(it["configured"] is False for it in g2.json()["settings"])


# ---------- Servicio ----------

def test_should_notify_default_true():
    org_id = _admin_org_id()
    db = _TestSession()
    try:
        # sin fila -> default del catalogo (activo)
        db.query(NotificationSetting).filter_by(
            organization_id=org_id, alert_key="soa_review").delete()
        db.commit()
        assert ns.should_notify(db, org_id, "soa_review") is True
    finally:
        db.close()


def test_should_notify_respects_disabled():
    org_id = _admin_org_id()
    db = _TestSession()
    try:
        db.query(NotificationSetting).filter_by(
            organization_id=org_id, alert_key="bcp_bia_gap").delete()
        db.add(NotificationSetting(organization_id=org_id, alert_key="bcp_bia_gap", enabled=False))
        db.commit()
        assert ns.should_notify(db, org_id, "bcp_bia_gap") is False
    finally:
        db.close()


def test_cooldown_blocks_recent_resend():
    org_id = _admin_org_id()
    db = _TestSession()
    try:
        db.query(NotificationSetting).filter_by(
            organization_id=org_id, alert_key="ccm_fail").delete()
        db.add(NotificationSetting(
            organization_id=org_id, alert_key="ccm_fail", enabled=True,
            cooldown_days=7, last_sent_at=datetime.now(timezone.utc) - timedelta(days=2)))
        db.commit()
        # enviado hace 2 dias, cooldown 7 -> bloqueado
        assert ns.should_notify(db, org_id, "ccm_fail") is False

        # enviado hace 10 dias -> permitido
        s = db.query(NotificationSetting).filter_by(
            organization_id=org_id, alert_key="ccm_fail").first()
        s.last_sent_at = datetime.now(timezone.utc) - timedelta(days=10)
        db.commit()
        assert ns.should_notify(db, org_id, "ccm_fail") is True
    finally:
        # limpiar
        db2 = _TestSession()
        db2.query(NotificationSetting).filter_by(
            organization_id=org_id, alert_key="ccm_fail").delete()
        db2.commit()
        db2.close()
        db.close()


def test_resolve_recipients_custom_vs_admins():
    org_id = _admin_org_id()
    db = _TestSession()
    try:
        db.query(NotificationSetting).filter_by(
            organization_id=org_id, alert_key="evidence_expiry").delete()
        db.commit()
        # sin fila -> admins de la org (al menos el admin seed)
        admins = ns.resolve_recipients(db, org_id, "evidence_expiry")
        assert "admin@test.internal" in admins

        db.add(NotificationSetting(
            organization_id=org_id, alert_key="evidence_expiry",
            recipient_mode="custom", recipients='["dpo@example.com"]'))
        db.commit()
        assert ns.resolve_recipients(db, org_id, "evidence_expiry") == ["dpo@example.com"]
    finally:
        db.query(NotificationSetting).filter_by(
            organization_id=org_id, alert_key="evidence_expiry").delete()
        db.commit()
        db.close()


def test_get_threshold_falls_back_to_catalog_default():
    org_id = _admin_org_id()
    db = _TestSession()
    try:
        db.query(NotificationSetting).filter_by(
            organization_id=org_id, alert_key="ccm_fail").delete()
        db.commit()
        # sin override -> default del catalogo (70.0)
        assert ns.get_threshold(db, org_id, "ccm_fail", 999.0) == 70.0
    finally:
        db.close()
