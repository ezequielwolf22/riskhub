"""Automatizaciones del Plan Director: salud computada, narrativa mensual, digest."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tests.conftest import _TestSession


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _default_org(db):
    from app.models import Organization
    return db.query(Organization).first()


def _fresh_org(db):
    """Org aislada para tests que agregan sobre TODAS las iniciativas de la
    org (narrativa mensual): evita colisionar con iniciativas de otros tests
    que comparten la org por defecto en la misma sesion de BD."""
    from app.models import Organization
    org = Organization(name=f"Org narrativa {_uid()}", plan="enterprise")
    db.add(org)
    db.flush()
    return org


def _make_initiative(db, org_id, **kwargs):
    from app.models import StrategicInitiative
    defaults = dict(
        organization_id=org_id, code=f"INI-HLT-{_uid()}", title=f"Iniciativa {_uid()}",
        status="in_progress", progress=50,
    )
    defaults.update(kwargs)
    ini = StrategicInitiative(**defaults)
    db.add(ini)
    db.flush()
    return ini


# ---------- refresh_initiative_health: reglas individuales ----------

def test_health_ok_when_no_signals(client):
    from app.services.initiative_projection_service import refresh_initiative_health
    db = _TestSession()
    try:
        org = _default_org(db)
        now = datetime.now(timezone.utc)
        ini = _make_initiative(db, org.id, target_date=now + timedelta(days=90),
                               start_date=now - timedelta(days=10), progress=50)
        db.commit()
        refresh_initiative_health(db, org.id)
        db.refresh(ini)
        assert ini.health == "ok"
        assert ini.health_reasons is None
    finally:
        db.close()


def test_health_at_risk_when_target_date_overdue(client):
    from app.services.initiative_projection_service import refresh_initiative_health
    db = _TestSession()
    try:
        org = _default_org(db)
        now = datetime.now(timezone.utc)
        ini = _make_initiative(db, org.id, target_date=now - timedelta(days=5))
        db.commit()
        refresh_initiative_health(db, org.id)
        db.refresh(ini)
        assert ini.health == "at_risk"
        assert "vencida" in " ".join(ini.health_reasons).lower()
    finally:
        db.close()


def test_health_at_risk_when_no_recent_activity(client):
    from app.services.initiative_projection_service import refresh_initiative_health
    db = _TestSession()
    try:
        org = _default_org(db)
        old = datetime.now(timezone.utc) - timedelta(days=45)
        ini = _make_initiative(db, org.id)
        ini.updated_at = old
        db.commit()
        # onupdate sobrescribiria el valor en un UPDATE normal del ORM: forzar via SQL crudo
        from sqlalchemy import text
        db.execute(text("UPDATE strategic_initiatives SET updated_at = :d WHERE id = :id"),
                  {"d": old, "id": ini.id})
        db.commit()

        refresh_initiative_health(db, org.id)
        db.refresh(ini)
        assert ini.health == "at_risk"
        assert any("actividad" in r.lower() for r in ini.health_reasons)
    finally:
        db.close()


def test_health_at_risk_when_many_tasks_overdue(client):
    from app.services.initiative_projection_service import refresh_initiative_health
    from app.models import TreatmentTask, TaskStatus
    db = _TestSession()
    try:
        org = _default_org(db)
        ini = _make_initiative(db, org.id)
        past = datetime.now(timezone.utc) - timedelta(days=5)
        db.add(TreatmentTask(organization_id=org.id, code=f"TSK-HLT-{_uid()}",
                             title="Vencida", initiative_id=ini.id, due_date=past,
                             status=TaskStatus.PENDING))
        db.commit()
        refresh_initiative_health(db, org.id)
        db.refresh(ini)
        assert ini.health == "at_risk"
        assert any("vencida" in r.lower() and "tarea" in r.lower() for r in ini.health_reasons)
    finally:
        db.close()


def test_health_at_risk_when_low_confidence_okr_near_deadline(client):
    from app.services.initiative_projection_service import refresh_initiative_health
    from app.models import InitiativeObjective
    db = _TestSession()
    try:
        org = _default_org(db)
        ini = _make_initiative(db, org.id)
        db.add(InitiativeObjective(
            organization_id=org.id, initiative_id=ini.id, code=f"OKR-HLT-{_uid()}",
            definition="OKR en riesgo", confidence="low",
            target_date=datetime.now(timezone.utc) + timedelta(days=30),
        ))
        db.commit()
        refresh_initiative_health(db, org.id)
        db.refresh(ini)
        assert ini.health == "at_risk"
        assert any("okr" in r.lower() for r in ini.health_reasons)
    finally:
        db.close()


def test_health_at_risk_when_progress_insufficient(client):
    from app.services.initiative_projection_service import refresh_initiative_health
    db = _TestSession()
    try:
        org = _default_org(db)
        now = datetime.now(timezone.utc)
        # 80% del plazo consumido, progreso 10%
        ini = _make_initiative(db, org.id, start_date=now - timedelta(days=80),
                               target_date=now + timedelta(days=20), progress=10)
        db.commit()
        refresh_initiative_health(db, org.id)
        db.refresh(ini)
        assert ini.health == "at_risk"
        assert any("progreso" in r.lower() for r in ini.health_reasons)
    finally:
        db.close()


def test_health_blocked_with_two_or_more_reasons(client):
    from app.services.initiative_projection_service import refresh_initiative_health
    db = _TestSession()
    try:
        org = _default_org(db)
        now = datetime.now(timezone.utc)
        # vencida + progreso insuficiente
        ini = _make_initiative(db, org.id, start_date=now - timedelta(days=80),
                               target_date=now - timedelta(days=1), progress=5)
        db.commit()
        refresh_initiative_health(db, org.id)
        db.refresh(ini)
        assert ini.health == "blocked"
        assert len(ini.health_reasons) >= 2
    finally:
        db.close()


def test_health_worsening_logs_system_event(client):
    from app.services.initiative_projection_service import refresh_initiative_health
    db = _TestSession()
    try:
        org = _default_org(db)
        now = datetime.now(timezone.utc)
        ini = _make_initiative(db, org.id, target_date=now - timedelta(days=1))
        db.commit()
        assert ini.health == "ok"

        refresh_initiative_health(db, org.id)
        db.refresh(ini)
        assert ini.health == "at_risk"

        entries = ini.log_entries
        assert any(e.entry_type == "system" and "salud" in e.text.lower() for e in entries)
    finally:
        db.close()


def test_health_improving_does_not_duplicate_log_entries(client):
    from app.services.initiative_projection_service import refresh_initiative_health
    db = _TestSession()
    try:
        org = _default_org(db)
        now = datetime.now(timezone.utc)
        ini = _make_initiative(db, org.id, target_date=now - timedelta(days=1))
        db.commit()
        refresh_initiative_health(db, org.id)
        db.refresh(ini)
        assert ini.health == "at_risk"
        count_after_degrade = len(ini.log_entries)

        # Corrige la fecha objetivo -> mejora a "ok"; no debe anadir otro log de degradacion
        ini.target_date = now + timedelta(days=90)
        db.commit()
        refresh_initiative_health(db, org.id)
        db.refresh(ini)
        assert ini.health == "ok"
        assert len(ini.log_entries) == count_after_degrade
    finally:
        db.close()


# ---------- Narrativa mensual (IA mockeada) ----------

def test_monthly_narrative_skips_initiative_without_recent_activity(client):
    """La BD de test es compartida entre casos (sesion unica); en vez de
    afirmar que el mock global no se llamo nunca, se comprueba que la
    iniciativa SIN actividad reciente en concreto no recibio narrativa."""
    from app.services import initiative_ai_service as svc
    db = _TestSession()
    try:
        org = _fresh_org(db)
        ini = _make_initiative(db, org.id)  # sin ninguna entrada de bitacora
        db.commit()
        ini_id = ini.id

        called_with_ids = []

        def _fake_summary(db_arg, initiative, lang):
            called_with_ids.append(initiative.id)
            return "Resumen"

        with patch.object(svc, "monthly_initiative_summary", side_effect=_fake_summary):
            svc.run_monthly_narratives(db)
        assert ini_id not in called_with_ids
    finally:
        db.close()


def test_monthly_narrative_created_when_recent_activity_exists(client):
    from app.services import initiative_ai_service as svc
    from app.models import InitiativeLogEntry
    db = _TestSession()
    try:
        org = _fresh_org(db)
        ini = _make_initiative(db, org.id)
        db.add(InitiativeLogEntry(
            organization_id=org.id, initiative_id=ini.id, entry_type="comment",
            text="Actividad reciente", author_id=None,
        ))
        db.commit()
        ini_id = ini.id

        with patch.object(svc, "monthly_initiative_summary", return_value="Resumen del mes."):
            svc.run_monthly_narratives(db)
        db.refresh(ini)
        assert any(e.entry_type == "ai_summary" for e in
                  db.query(InitiativeLogEntry).filter(InitiativeLogEntry.initiative_id == ini_id).all())
    finally:
        db.close()


# ---------- Digest mensual ----------

def test_digest_sends_nothing_when_no_issues(client):
    from app.services.initiative_projection_service import send_initiative_digest
    db = _TestSession()
    try:
        summary = send_initiative_digest(db)
        assert summary["sent"] == 0
    finally:
        db.close()
