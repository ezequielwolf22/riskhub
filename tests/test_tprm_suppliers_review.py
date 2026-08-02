"""Tests del review del modulo de proveedores (feedback cliente OFA).

Cubre Fase 1: clasificaciones independientes (punto 2), owner/backup (3),
region operativa (4), ciclo de revision (5), estado de seguridad (6/18),
timeline de eventos (12), config del modulo (4/7/11) e import ampliado (13).
"""
from datetime import datetime, timedelta, timezone


def _create_supplier(client, headers, **extra):
    body = {"name": extra.pop("name", "Acme Cloud"), **extra}
    resp = client.post("/api/suppliers/", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestIndependentClassifications:
    def test_create_with_both_classifications(self, client, auth_headers):
        s = _create_supplier(
            client, auth_headers,
            business_importance_level="critical",
            security_risk_level="high",
        )
        assert s["business_importance_level"] == "critical"
        assert s["security_risk_level"] == "high"

    def test_filter_by_security_risk(self, client, auth_headers):
        _create_supplier(client, auth_headers, name="HighRisk Co", security_risk_level="high")
        _create_supplier(client, auth_headers, name="LowRisk Co", security_risk_level="low")
        resp = client.get("/api/suppliers/?security_risk_level=high", headers=auth_headers)
        assert resp.status_code == 200
        names = {s["name"] for s in resp.json()}
        assert "HighRisk Co" in names
        assert "LowRisk Co" not in names

    def test_business_importance_independent_from_security(self, client, auth_headers):
        s = _create_supplier(
            client, auth_headers, name="Independent Co",
            business_importance_level="not_relevant", security_risk_level="critical",
        )
        assert s["business_importance_level"] == "not_relevant"
        assert s["security_risk_level"] == "critical"


class TestReviewLifecycle:
    def test_review_status_overdue(self, client, auth_headers):
        past = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        s = _create_supplier(client, auth_headers, name="Overdue Co",
                             next_assessment_at=past, review_frequency="annual")
        assert s["review_status"] == "review_overdue"
        assert s["review_frequency"] == "annual"

    def test_review_status_due_30(self, client, auth_headers):
        soon = (datetime.now(timezone.utc) + timedelta(days=15)).isoformat()
        s = _create_supplier(client, auth_headers, name="Soon Co", next_assessment_at=soon)
        assert s["review_status"] == "review_due_30"

    def test_review_status_active_when_no_date(self, client, auth_headers):
        s = _create_supplier(client, auth_headers, name="NoDate Co")
        assert s["review_status"] == "active"


class TestSecurityStatusAndEvents:
    def test_status_change_logs_event(self, client, auth_headers):
        s = _create_supplier(client, auth_headers, name="Flow Co",
                             security_status="pending_security_review")
        assert s["next_action_owner"] == "security"
        # transicion a aprobado
        resp = client.patch(f"/api/suppliers/{s['id']}",
                            json={"security_status": "security_approved"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["security_status"] == "security_approved"
        assert resp.json()["security_status_changed_at"] is not None
        # el timeline registra el cambio
        ev = client.get(f"/api/suppliers/{s['id']}/events", headers=auth_headers)
        assert ev.status_code == 200
        types = {e["event_type"] for e in ev.json()}
        assert "status_change" in types

    def test_manual_event(self, client, auth_headers):
        s = _create_supplier(client, auth_headers, name="Manual Ev Co")
        resp = client.post(f"/api/suppliers/{s['id']}/events",
                          json={"event_type": "sla_breach", "title": "SLA de disponibilidad incumplido"},
                          headers=auth_headers)
        assert resp.status_code == 201
        ev = client.get(f"/api/suppliers/{s['id']}/events", headers=auth_headers)
        assert any(e["title"].startswith("SLA") for e in ev.json())

    def test_ownership_change_logs_event(self, client, auth_headers):
        s = _create_supplier(client, auth_headers, name="Owner Co")
        # obtener un user id valido (el admin)
        me = client.get("/api/users/me", headers=auth_headers)
        uid = me.json()["id"] if me.status_code == 200 else 1
        client.patch(f"/api/suppliers/{s['id']}", json={"owner_id": uid}, headers=auth_headers)
        ev = client.get(f"/api/suppliers/{s['id']}/events", headers=auth_headers)
        assert "ownership_change" in {e["event_type"] for e in ev.json()}


class TestTprmSettings:
    def test_get_settings_has_default_regions(self, client, auth_headers):
        resp = client.get("/api/tprm/settings", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "operating_regions" in data
        assert "Spain" in data["operating_regions"]
        assert "region_suggestions" in data

    def test_update_regions_persists(self, client, auth_headers):
        resp = client.put("/api/tprm/settings",
                         json={"operating_regions": ["Global", "DACH", "Nordics"]},
                         headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["operating_regions"] == ["Global", "DACH", "Nordics"]
        # persistencia
        again = client.get("/api/tprm/settings", headers=auth_headers)
        assert again.json()["operating_regions"] == ["Global", "DACH", "Nordics"]


class TestAutomaticFindings:
    def test_mfa_no_generates_finding(self, client, auth_headers):
        s = _create_supplier(client, auth_headers, name="MFA Vendor")
        # cuestionario con una pregunta Major de MFA (sin MFA puntua 0)
        q = client.post("/api/supplier-questionnaires/", json={
            "supplier_id": s["id"], "title": "SSAQ", "apply_trigger_modules": False,
            "questions": [
                {"id": "mfa", "text": "¿MFA implementado?", "type": "yes_no",
                 "criticity": "Major", "scoring_rules": {"yes": 100, "no": 0},
                 "control_refs": ["ISO27001:A.8.5"]},
                {"id": "backups", "text": "¿Backups?", "type": "yes_no",
                 "criticity": "Minor", "scoring_rules": {"yes": 100, "no": 0}},
            ],
        }, headers=auth_headers)
        assert q.status_code == 200, q.text
        token = q.json()["token"]
        sub = client.post(f"/api/supplier-questionnaires/public/{token}/submit",
                         json={"answers": {"mfa": "no", "backups": "yes"}})
        assert sub.status_code == 200, sub.text
        issues = client.get(f"/api/vendor-issues/?supplier_id={s['id']}", headers=auth_headers)
        assert issues.status_code == 200
        auto = [i for i in issues.json() if i.get("source") == "questionnaire"]
        assert auto, "no se generó hallazgo automático"
        assert any(i["severity"] == "critical" for i in auto)  # sin MFA (score 0) en Major

    def test_conformant_answers_no_finding(self, client, auth_headers):
        s = _create_supplier(client, auth_headers, name="Clean Vendor")
        q = client.post("/api/supplier-questionnaires/", json={
            "supplier_id": s["id"], "title": "SSAQ", "apply_trigger_modules": False,
            "questions": [{"id": "mfa", "text": "¿MFA?", "type": "yes_no",
                          "criticity": "Major", "scoring_rules": {"yes": 100, "no": 0}}],
        }, headers=auth_headers)
        token = q.json()["token"]
        client.post(f"/api/supplier-questionnaires/public/{token}/submit",
                   json={"answers": {"mfa": "yes"}})
        issues = client.get(f"/api/vendor-issues/?supplier_id={s['id']}", headers=auth_headers)
        auto = [i for i in issues.json() if i.get("source") == "questionnaire"]
        assert not auto


class TestFindingClosureApproval:
    def test_approve_closure_stamps_approver(self, client, auth_headers):
        s = _create_supplier(client, auth_headers, name="Issue Vendor")
        iss = client.post("/api/vendor-issues/", json={
            "supplier_id": s["id"], "title": "Hallazgo manual", "severity": "high",
        }, headers=auth_headers)
        assert iss.status_code == 200, iss.text
        iid = iss.json()["id"]
        resp = client.post(f"/api/vendor-issues/{iid}/approve-closure",
                          json={"resolution_notes": "Verificado"}, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "closed"
        assert data["closure_approved_by_id"] is not None
        assert data["closure_approved_at"] is not None


class TestPostReviewDecision:
    def test_decision_transition_ok_without_config(self, client, auth_headers):
        # sin notificaciones configuradas, la transicion de decision no debe fallar
        s = _create_supplier(client, auth_headers, name="Decision Vendor",
                            security_status="pending_security_review")
        resp = client.patch(f"/api/suppliers/{s['id']}",
                          json={"security_status": "security_approved"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["security_status"] == "security_approved"


class TestQuestionnaireReuse:
    def test_prefill_from_previous(self, client, auth_headers):
        s = _create_supplier(client, auth_headers, name="Reuse Vendor")
        q1 = client.post("/api/supplier-questionnaires/", json={
            "supplier_id": s["id"], "title": "SSAQ 2025", "apply_trigger_modules": False,
            "questions": [{"id": "mfa", "text": "¿MFA?", "type": "yes_no",
                          "scoring_rules": {"yes": 100, "no": 0}}],
        }, headers=auth_headers)
        token = q1.json()["token"]
        client.post(f"/api/supplier-questionnaires/public/{token}/submit",
                   json={"answers": {"mfa": "yes"}})
        # nuevo cuestionario reutilizando respuestas
        q2 = client.post("/api/supplier-questionnaires/", json={
            "supplier_id": s["id"], "title": "SSAQ 2026", "apply_trigger_modules": False,
            "prefill_from_previous": True,
            "questions": [{"id": "mfa", "text": "¿MFA?", "type": "yes_no",
                          "scoring_rules": {"yes": 100, "no": 0}}],
        }, headers=auth_headers)
        assert q2.status_code == 200, q2.text
        full = client.get(f"/api/supplier-questionnaires/{q2.json()['id']}", headers=auth_headers)
        assert (full.json().get("answers") or {}).get("mfa") == "yes"


class TestImportEnhancements:
    def test_import_new_fields(self, client, auth_headers):
        csv = (
            "name,business importance,security risk,operating region,review frequency,agreement status\n"
            "Imported Vendor,Important,High,Iberia-Latam,Annual,Signed\n"
        )
        resp = client.post(
            "/api/suppliers/import",
            files={"file": ("vendors.csv", csv, "text/csv")},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text
        listed = client.get("/api/suppliers/?q=Imported Vendor", headers=auth_headers)
        rows = [s for s in listed.json() if s["name"] == "Imported Vendor"]
        assert rows, "supplier not imported"
        s = rows[0]
        assert s["business_importance_level"] == "important"
        assert s["security_risk_level"] == "high"
        assert s["operating_region"] == "Iberia-Latam"
        assert s["review_frequency"] == "annual"
        assert s["agreement_status"] == "signed"
