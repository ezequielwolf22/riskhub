"""Carga inicial de datos: admin, catalogos ISO 27005/27002, contexto, organizacion."""
import json
import logging
from pathlib import Path

logger = logging.getLogger("riskhub.seed")

from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import (
    Control, Organization, RiskContext, Threat, ThreatOrigin, User, UserRole, Vulnerability,
)
from app.security import hash_password
from app.services.risk_engine import (
    default_acceptance_criteria, default_impact_criteria,
    default_likelihood_criteria, default_matrix,
)

DATA_DIR = Path(__file__).parent / "data"


def load_json(name: str):
    # utf-8-sig tolera ficheros con BOM (editores en Windows) sin romper json.load
    with open(DATA_DIR / name, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _extract_domain(email: str) -> str:
    """Extrae el dominio del email (ej. 'user@example.com' -> 'example.com')."""
    return email.split("@", 1)[-1].lower() if "@" in email else ""


def seed_organization(db: Session) -> Organization:
    """Crea la organizacion por defecto si no existe. Devuelve la org."""
    org = db.query(Organization).first()
    if org:
        return org
    domain = _extract_domain(settings.admin_email)
    org = Organization(
        name="Default Organization",
        domain=domain,
        plan="starter",
        is_active=True,
        max_users=50,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def seed_admin(db: Session) -> None:
    if db.query(User).count() > 0:
        # Asignar organizacion a usuarios existentes sin org
        org = db.query(Organization).first()
        if org:
            db.query(User).filter(User.organization_id == None).update(  # noqa: E711
                {"organization_id": org.id}
            )
            db.commit()
        return
    org = seed_organization(db)
    admin = User(
        email=settings.admin_email,
        full_name="Administrator",
        hashed_password=hash_password(settings.admin_password),
        role=UserRole.ADMIN,
        is_active=True,
        organization_id=org.id,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    # Vincular owner de la org al admin
    org.owner_id = admin.id
    db.commit()


def seed_context(db: Session) -> None:
    org = db.query(Organization).first()
    org_id = org.id if org else None
    # Crear contexto para la org si no existe
    q = db.query(RiskContext)
    if org_id:
        q = q.filter(RiskContext.organization_id == org_id)
    if q.count() > 0:
        # Asignar org a contextos existentes sin org
        if org_id:
            db.query(RiskContext).filter(RiskContext.organization_id == None).update(  # noqa: E711
                {"organization_id": org_id}
            )
            db.commit()
        return
    ctx = RiskContext(
        organization_id=org_id,
        organization_name="Organization",
        scope="Sistemas de informacion corporativos.",
        boundaries="Activos gestionados por el equipo de TI.",
        impact_criteria=default_impact_criteria(),
        likelihood_criteria=default_likelihood_criteria(),
        risk_acceptance_criteria=default_acceptance_criteria(),
        risk_matrix=default_matrix(),
        risk_appetite=3,
    )
    db.add(ctx)
    db.commit()


def seed_threats(db: Session) -> None:
    # Upsert: actualiza nombre/descripcion de amenazas del catalogo oficial.
    for t in load_json("threats_iso27005.json"):
        existing = db.query(Threat).filter_by(code=t["code"]).first()
        if existing:
            existing.name = t["name"]
            existing.description = t.get("description")
            existing.category = t.get("category")
            existing.typical_assets = t.get("typical_assets", [])
            existing.affects = t.get("affects", [])
            existing.catalog = "iso27005"
        else:
            db.add(Threat(
                code=t["code"], name=t["name"], description=t.get("description"),
                category=t.get("category"),
                origin=ThreatOrigin(t["origin"]),
                typical_assets=t.get("typical_assets", []),
                affects=t.get("affects", []),
                is_custom=False,
                catalog="iso27005",
            ))

    # Normalizar amenazas MAGERIT existentes (código MAGERIT-*)
    db.query(Threat).filter(
        Threat.code.like("MAGERIT-%"),
        (Threat.catalog == None) | (Threat.catalog == "iso27005"),  # noqa: E711
    ).update({"catalog": "magerit"}, synchronize_session=False)

    # Normalizar amenazas custom existentes
    db.query(Threat).filter(
        Threat.is_custom == True,  # noqa: E712
        (Threat.catalog == None) | (Threat.catalog == "iso27005"),  # noqa: E711
        ~Threat.code.like("MAGERIT-%"),
    ).update({"catalog": "custom"}, synchronize_session=False)

    db.commit()


def seed_vulnerabilities(db: Session) -> None:
    # Upsert: actualiza nombre/descripcion de vulnerabilidades del catalogo oficial.
    for v in load_json("vulnerabilities_iso27005.json"):
        existing = db.query(Vulnerability).filter_by(code=v["code"]).first()
        if existing:
            existing.name = v["name"]
            existing.description = v.get("description")
            existing.category = v.get("category")
            existing.related_threats = v.get("related_threats", [])
        else:
            db.add(Vulnerability(
                code=v["code"], name=v["name"], description=v.get("description"),
                category=v.get("category"),
                related_threats=v.get("related_threats", []),
                is_custom=False,
            ))
    db.commit()


def seed_controls(db: Session) -> None:
    if db.query(Control).count() > 0:
        return
    for c in load_json("controls_iso27002_2022.json"):
        db.add(Control(
            code=c["code"], name=c["name"], description=c.get("description"),
            theme=c.get("theme"),
            control_type=c.get("control_type", []),
            properties=c.get("properties", []),
            cybersec_concepts=c.get("cybersec_concepts", []),
            operational=c.get("operational", []),
            is_custom=False,
        ))
    db.commit()


def _create_fts5_table() -> None:
    """Crea las tablas FTS5: chunks de documentos IA y entidades de negocio."""
    with engine.connect() as conn:
        try:
            conn.execute(__import__("sqlalchemy").text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS ai_chunks_fts "
                "USING fts5(content, tokenize='unicode61 remove_diacritics 1')"
            ))
            conn.commit()
        except Exception:
            pass  # SQLite sin soporte FTS5 (entorno de test)
        try:
            # v6.0.0 — entidades de negocio (riesgos, controles, politicas,
            # evidencias analizadas) buscables por el RAG del chat
            conn.execute(__import__("sqlalchemy").text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS ai_entity_fts "
                "USING fts5(content, entity_type UNINDEXED, entity_ref UNINDEXED, "
                "org_id UNINDEXED, tokenize='unicode61 remove_diacritics 1')"
            ))
            conn.commit()
        except Exception:
            pass


def _ensure_doc_dir() -> None:
    """Crea el directorio de almacenamiento de documentos si no existe."""
    from pathlib import Path
    doc_root = Path("/srv/data/documents")
    if not doc_root.exists():
        doc_root = Path(__file__).parent.parent / "data" / "documents"
    doc_root.mkdir(parents=True, exist_ok=True)


def _migrate_columns() -> None:
    """Agrega columnas nuevas a tablas existentes (SQLite ALTER TABLE sin IF NOT EXISTS)."""
    migrations = [
        # assets: valor monetario para FAIR
        ("ALTER TABLE assets ADD COLUMN monetary_value REAL", "assets", "monetary_value"),
        # control_implementations: campos SOA ISO 27001:2022
        ("ALTER TABLE control_implementations ADD COLUMN inclusion_reason VARCHAR(64)", "control_implementations", "inclusion_reason"),
        ("ALTER TABLE control_implementations ADD COLUMN exclusion_justification TEXT", "control_implementations", "exclusion_justification"),
        ("ALTER TABLE control_implementations ADD COLUMN evidence_refs JSON", "control_implementations", "evidence_refs"),
        ("ALTER TABLE control_implementations ADD COLUMN soa_reviewed_at DATETIME", "control_implementations", "soa_reviewed_at"),
        ("ALTER TABLE control_implementations ADD COLUMN soa_reviewed_by_id INTEGER REFERENCES users(id)", "control_implementations", "soa_reviewed_by_id"),
        # incidents: nuevos campos v1.1
        ("ALTER TABLE incidents ADD COLUMN affected_systems JSON", "incidents", "affected_systems"),
        ("ALTER TABLE incidents ADD COLUMN response_actions TEXT", "incidents", "response_actions"),
        # suppliers: nuevos campos v1.1
        ("ALTER TABLE suppliers ADD COLUMN category VARCHAR(128)", "suppliers", "category"),
        ("ALTER TABLE suppliers ADD COLUMN is_critical BOOLEAN DEFAULT 0", "suppliers", "is_critical"),
        ("ALTER TABLE suppliers ADD COLUMN contract_ref VARCHAR(255)", "suppliers", "contract_ref"),
        # risks: dedup de notificaciones de revision periodica (v1.2)
        ("ALTER TABLE risks ADD COLUMN last_review_notified_at DATETIME", "risks", "last_review_notified_at"),
        # v1.7.0 — organization_id en todas las tablas per-org
        ("ALTER TABLE users ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "users", "organization_id"),
        ("ALTER TABLE audit_log ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "audit_log", "organization_id"),
        ("ALTER TABLE integration_configs ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "integration_configs", "organization_id"),
        ("ALTER TABLE risk_context ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "risk_context", "organization_id"),
        ("ALTER TABLE assets ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "assets", "organization_id"),
        ("ALTER TABLE risks ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "risks", "organization_id"),
        ("ALTER TABLE control_implementations ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "control_implementations", "organization_id"),
        ("ALTER TABLE incidents ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "incidents", "organization_id"),
        ("ALTER TABLE suppliers ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "suppliers", "organization_id"),
        ("ALTER TABLE supplier_questionnaires ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "supplier_questionnaires", "organization_id"),
        ("ALTER TABLE nonconformities ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "nonconformities", "organization_id"),
        ("ALTER TABLE treatment_tasks ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "treatment_tasks", "organization_id"),
        ("ALTER TABLE policies ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "policies", "organization_id"),
        ("ALTER TABLE audit_programs ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "audit_programs", "organization_id"),
        ("ALTER TABLE processing_activities ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "processing_activities", "organization_id"),
        ("ALTER TABLE email_settings ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "email_settings", "organization_id"),
        ("ALTER TABLE alert_rules ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "alert_rules", "organization_id"),
        ("ALTER TABLE ai_config ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "ai_config", "organization_id"),
        ("ALTER TABLE ai_documents ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "ai_documents", "organization_id"),
        ("ALTER TABLE ai_call_logs ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "ai_call_logs", "organization_id"),
        ("ALTER TABLE osint_scans ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "osint_scans", "organization_id"),
        ("ALTER TABLE osint_identifiers ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "osint_identifiers", "organization_id"),
        ("ALTER TABLE awareness_items ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "awareness_items", "organization_id"),
        ("ALTER TABLE awareness_branding ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "awareness_branding", "organization_id"),
        # v1.7.5 — analisis de riesgos automatico con IA
        ("ALTER TABLE assets ADD COLUMN ai_risk_status VARCHAR(32)", "assets", "ai_risk_status"),
        ("ALTER TABLE assets ADD COLUMN ai_risk_summary JSON", "assets", "ai_risk_summary"),
        ("ALTER TABLE risks ADD COLUMN ai_generated BOOLEAN DEFAULT 0", "risks", "ai_generated"),
        ("ALTER TABLE risks ADD COLUMN ai_rationale TEXT", "risks", "ai_rationale"),
        # v1.7.4 — analisis ISMS automatico
        ("ALTER TABLE ai_documents ADD COLUMN isms_status VARCHAR(32)", "ai_documents", "isms_status"),
        ("ALTER TABLE ai_documents ADD COLUMN isms_summary JSON", "ai_documents", "isms_summary"),
        ("ALTER TABLE policies ADD COLUMN source_document_id INTEGER REFERENCES ai_documents(id)", "policies", "source_document_id"),
        ("ALTER TABLE policies ADD COLUMN review_cycle_months INTEGER", "policies", "review_cycle_months"),
        # v1.8 — Auth: OTP y MFA
        ("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT 0", "users", "must_change_password"),
        ("ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN DEFAULT 0", "users", "mfa_enabled"),
        ("ALTER TABLE users ADD COLUMN mfa_secret VARCHAR(255)", "users", "mfa_secret"),
        ("ALTER TABLE organizations ADD COLUMN mfa_required BOOLEAN DEFAULT 0", "organizations", "mfa_required"),
        ("ALTER TABLE users ADD COLUMN mfa_override BOOLEAN", "users", "mfa_override"),
        # v1.8 — Feature flags per-org
        ("ALTER TABLE feature_flags ADD COLUMN organization_id INTEGER REFERENCES organizations(id)", "feature_flags", "organization_id"),
        # v1.8 — Compliance/AI: gap cache + auto-categorization
        ("ALTER TABLE risk_context ADD COLUMN ai_gap_cache JSON", "risk_context", "ai_gap_cache"),
        ("ALTER TABLE ai_documents ADD COLUMN auto_categorized BOOLEAN DEFAULT 0", "ai_documents", "auto_categorized"),
        ("ALTER TABLE ai_documents ADD COLUMN detected_category VARCHAR(64)", "ai_documents", "detected_category"),
        # v1.8.0 — agrupacion de activos
        ("ALTER TABLE assets ADD COLUMN group_id INTEGER REFERENCES asset_groups(id)", "assets", "group_id"),
        ("ALTER TABLE assets ADD COLUMN is_group_representative BOOLEAN DEFAULT 0", "assets", "is_group_representative"),
        # v1.8.1 — normativas activas y nivel ENS en contexto
        ("ALTER TABLE risk_context ADD COLUMN active_frameworks JSON", "risk_context", "active_frameworks"),
        ("ALTER TABLE risk_context ADD COLUMN ens_level VARCHAR(16)", "risk_context", "ens_level"),
        # v1.8.2 — seguridad: SMTP cifrado, SSO state/code en BD
        ("ALTER TABLE email_settings ADD COLUMN smtp_password_encrypted TEXT", "email_settings", "smtp_password_encrypted"),
        # v2.2.0 — extraccion automatica de clausulas ISO desde documentos
        ("ALTER TABLE ai_documents ADD COLUMN extracted_clauses JSON", "ai_documents", "extracted_clauses"),
        # v1.8.2 — metodologia unificada (ISO 27005 / MAGERIT / Combined)
        ("ALTER TABLE risk_context ADD COLUMN methodology VARCHAR(16) DEFAULT 'iso27005'", "risk_context", "methodology"),
        ("ALTER TABLE risks ADD COLUMN magerit_dimension VARCHAR(4)", "risks", "magerit_dimension"),
        ("ALTER TABLE risks ADD COLUMN degradation_pct INTEGER", "risks", "degradation_pct"),
        ("ALTER TABLE risks ADD COLUMN magerit_impact REAL", "risks", "magerit_impact"),
        # v2.2.5 — etiquetas de software para correlacion CPE/CVE
        ("ALTER TABLE assets ADD COLUMN software_tags JSON", "assets", "software_tags"),
        # v2.3.0 — Risk Acceptance formal workflow
        ("ALTER TABLE risks ADD COLUMN acceptance_requested_by_id INTEGER REFERENCES users(id)",
         "risks", "acceptance_requested_by_id"),
        ("ALTER TABLE risks ADD COLUMN acceptance_requested_at DATETIME",
         "risks", "acceptance_requested_at"),
        ("ALTER TABLE risks ADD COLUMN acceptance_approved_by_id INTEGER REFERENCES users(id)",
         "risks", "acceptance_approved_by_id"),
        ("ALTER TABLE risks ADD COLUMN acceptance_review_date DATETIME",
         "risks", "acceptance_review_date"),
        # v2.3.0 — Compliance evidence link
        ("ALTER TABLE compliance_framework_status ADD COLUMN evidence_document_id INTEGER REFERENCES ai_documents(id)",
         "compliance_framework_status", "evidence_document_id"),
        # v2.3.0 — Audit checklist generated timestamp
        ("ALTER TABLE audit_programs ADD COLUMN checklist_generated_at DATETIME",
         "audit_programs", "checklist_generated_at"),
        # v2.3.0 — MFA backup codes
        ("ALTER TABLE users ADD COLUMN mfa_backup_codes JSON", "users", "mfa_backup_codes"),
        # v2.4.0 — Licenciamiento
        ("ALTER TABLE licenses ADD COLUMN updated_by_id INTEGER REFERENCES users(id)", "licenses", "updated_by_id"),
        ("ALTER TABLE licenses ADD COLUMN updated_at DATETIME", "licenses", "updated_at"),
        # v2.5.0 — recordatorio de vencimiento de licencia por email
        ("ALTER TABLE licenses ADD COLUMN last_reminder_sent_at DATETIME", "licenses", "last_reminder_sent_at"),
        # v2.4.1 — Persistencia de respuestas del cuestionario IA en RiskContext
        ("ALTER TABLE risk_context ADD COLUMN questionnaire_answers JSON", "risk_context", "questionnaire_answers"),
        # v2.4.2 — Campo catalog en Threat (iso27005 | magerit | custom)
        ("ALTER TABLE threats ADD COLUMN catalog VARCHAR(32) NOT NULL DEFAULT 'iso27005'", "threats", "catalog"),
        # v2.4.2 — Catalogos de amenazas activos por org en RiskContext
        ("ALTER TABLE risk_context ADD COLUMN active_threat_catalogs JSON", "risk_context", "active_threat_catalogs"),
        # v2.5.0 — Importación segura: external_id constraint + audit log
        ("ALTER TABLE assets ADD COLUMN external_id VARCHAR(255)", "assets", "external_id"),
        ("ALTER TABLE assets ADD COLUMN import_session_id VARCHAR(64)", "assets", "import_session_id"),
        ("ALTER TABLE assets ADD COLUMN imported_at DATETIME DEFAULT CURRENT_TIMESTAMP", "assets", "imported_at"),
        # v3.0.0 — BCP/ISO 22301: BusinessProcess ampliado (14 campos BIA)
        ("ALTER TABLE business_processes ADD COLUMN priority INTEGER", "business_processes", "priority"),
        ("ALTER TABLE business_processes ADD COLUMN recovery_owner_id INTEGER REFERENCES users(id)", "business_processes", "recovery_owner_id"),
        ("ALTER TABLE business_processes ADD COLUMN mbco TEXT", "business_processes", "mbco"),
        ("ALTER TABLE business_processes ADD COLUMN financial_impact INTEGER", "business_processes", "financial_impact"),
        ("ALTER TABLE business_processes ADD COLUMN reputational_impact INTEGER", "business_processes", "reputational_impact"),
        ("ALTER TABLE business_processes ADD COLUMN legal_impact INTEGER", "business_processes", "legal_impact"),
        ("ALTER TABLE business_processes ADD COLUMN operational_impact INTEGER", "business_processes", "operational_impact"),
        ("ALTER TABLE business_processes ADD COLUMN min_recovery_staff INTEGER", "business_processes", "min_recovery_staff"),
        ("ALTER TABLE business_processes ADD COLUMN vital_records JSON", "business_processes", "vital_records"),
        ("ALTER TABLE business_processes ADD COLUMN activation_criteria TEXT", "business_processes", "activation_criteria"),
        ("ALTER TABLE business_processes ADD COLUMN alternative_procedure TEXT", "business_processes", "alternative_procedure"),
        ("ALTER TABLE business_processes ADD COLUMN it_systems JSON", "business_processes", "it_systems"),
        ("ALTER TABLE business_processes ADD COLUMN facilities JSON", "business_processes", "facilities"),
        ("ALTER TABLE business_processes ADD COLUMN escalation_contacts JSON", "business_processes", "escalation_contacts"),
        # v3.0.0 — BCP/ISO 22301: BCPTest ampliado (7 campos nuevos)
        ("ALTER TABLE bcp_tests ADD COLUMN objective TEXT", "bcp_tests", "objective"),
        ("ALTER TABLE bcp_tests ADD COLUMN scope_description TEXT", "bcp_tests", "scope_description"),
        ("ALTER TABLE bcp_tests ADD COLUMN participants JSON", "bcp_tests", "participants"),
        ("ALTER TABLE bcp_tests ADD COLUMN facilitator_id INTEGER REFERENCES users(id)", "bcp_tests", "facilitator_id"),
        ("ALTER TABLE bcp_tests ADD COLUMN lessons_learned TEXT", "bcp_tests", "lessons_learned"),
        ("ALTER TABLE bcp_tests ADD COLUMN improvement_actions TEXT", "bcp_tests", "improvement_actions"),
        ("ALTER TABLE bcp_tests ADD COLUMN evidence_doc_ids JSON", "bcp_tests", "evidence_doc_ids"),
        # v3.3.1 — BCP enriquecido: BCPDependency + 3 campos
        ("ALTER TABLE bcp_dependencies ADD COLUMN depends_on_process_id INTEGER REFERENCES business_processes(id)",
         "bcp_dependencies", "depends_on_process_id"),
        ("ALTER TABLE bcp_dependencies ADD COLUMN recovery_sequence INTEGER",
         "bcp_dependencies", "recovery_sequence"),
        ("ALTER TABLE bcp_dependencies ADD COLUMN notes TEXT",
         "bcp_dependencies", "notes"),
        # v3.3.1 — BCP enriquecido: BCPPlan + 7 campos (formulario drawer)
        ("ALTER TABLE bcp_plans ADD COLUMN sections JSON",
         "bcp_plans", "sections"),
        ("ALTER TABLE bcp_plans ADD COLUMN roles_matrix JSON",
         "bcp_plans", "roles_matrix"),
        ("ALTER TABLE bcp_plans ADD COLUMN contact_list JSON",
         "bcp_plans", "contact_list"),
        ("ALTER TABLE bcp_plans ADD COLUMN system_dependencies JSON",
         "bcp_plans", "system_dependencies"),
        ("ALTER TABLE bcp_plans ADD COLUMN kpis JSON",
         "bcp_plans", "kpis"),
        ("ALTER TABLE bcp_plans ADD COLUMN plan_owner_name VARCHAR(255)",
         "bcp_plans", "plan_owner_name"),
        ("ALTER TABLE bcp_plans ADD COLUMN classification VARCHAR(32)",
         "bcp_plans", "classification"),
        # v3.3.1 — Cobertura BCP en el registro de riesgos (ISO 22301 / ISO 27001 A.5.29)
        ("ALTER TABLE risks ADD COLUMN bcp_coverage JSON", "risks", "bcp_coverage"),
        # v3.4.0 — Encuestas distribuidas: contadores en riesgos
        ("ALTER TABLE risks ADD COLUMN last_survey_date DATETIME", "risks", "last_survey_date"),
        ("ALTER TABLE risks ADD COLUMN survey_response_count INTEGER DEFAULT 0", "risks", "survey_response_count"),
        # v3.4.3 — BIA: campos normativos (ENS, impacto progresivo en el tiempo, coste, version)
        ("ALTER TABLE business_processes ADD COLUMN ens_category VARCHAR(8)", "business_processes", "ens_category"),
        ("ALTER TABLE business_processes ADD COLUMN cost_per_hour REAL", "business_processes", "cost_per_hour"),
        ("ALTER TABLE business_processes ADD COLUMN impact_1h INTEGER", "business_processes", "impact_1h"),
        ("ALTER TABLE business_processes ADD COLUMN impact_24h INTEGER", "business_processes", "impact_24h"),
        ("ALTER TABLE business_processes ADD COLUMN impact_7d INTEGER", "business_processes", "impact_7d"),
        ("ALTER TABLE business_processes ADD COLUMN bia_version VARCHAR(16)", "business_processes", "bia_version"),
        ("ALTER TABLE business_processes ADD COLUMN bia_review_date DATETIME", "business_processes", "bia_review_date"),
        # v3.4.3 — BCPTest: frecuencia planificada + RTO/RPO real medido en ejercicio
        ("ALTER TABLE bcp_tests ADD COLUMN frequency VARCHAR(16)", "bcp_tests", "frequency"),
        ("ALTER TABLE bcp_tests ADD COLUMN rto_achieved_hours INTEGER", "bcp_tests", "rto_achieved_hours"),
        ("ALTER TABLE bcp_tests ADD COLUMN rpo_achieved_hours INTEGER", "bcp_tests", "rpo_achieved_hours"),
        # v3.4.3 — BCPPlan: DR Site + politica de backups (solo planes tipo DRP/CRP)
        ("ALTER TABLE bcp_plans ADD COLUMN dr_site JSON", "bcp_plans", "dr_site"),
        ("ALTER TABLE bcp_plans ADD COLUMN backup_policy JSON", "bcp_plans", "backup_policy"),
        # BCM Expansion — location_id en tablas existentes
        ("ALTER TABLE business_processes ADD COLUMN location_id INTEGER REFERENCES bcm_locations(id)",
         "business_processes", "location_id"),
        ("ALTER TABLE bcp_tests ADD COLUMN location_id INTEGER REFERENCES bcm_locations(id)",
         "bcp_tests", "location_id"),
        ("ALTER TABLE bcp_plans ADD COLUMN location_id INTEGER REFERENCES bcm_locations(id)",
         "bcp_plans", "location_id"),
        ("ALTER TABLE bcp_dependencies ADD COLUMN cross_location_id INTEGER REFERENCES bcm_locations(id)",
         "bcp_dependencies", "cross_location_id"),
        ("ALTER TABLE bcp_strategies ADD COLUMN location_id INTEGER REFERENCES bcm_locations(id)",
         "bcp_strategies", "location_id"),
        ("ALTER TABLE bcp_supplier_links ADD COLUMN location_id INTEGER REFERENCES bcm_locations(id)",
         "bcp_supplier_links", "location_id"),
        ("ALTER TABLE assets ADD COLUMN bcm_location_id INTEGER REFERENCES bcm_locations(id)",
         "assets", "bcm_location_id"),
        # v2.3.0 — BCM checklist de activación
        ("ALTER TABLE bcp_plans ADD COLUMN checklist_template JSON", "bcp_plans", "checklist_template"),
        ("ALTER TABLE bcm_activations ADD COLUMN checklist_items JSON", "bcm_activations", "checklist_items"),
        # v3.5.0 — Voyage AI embeddings para busqueda semantica multilingue
        ("ALTER TABLE ai_config ADD COLUMN voyage_api_key_encrypted TEXT", "ai_config", "voyage_api_key_encrypted"),
        ("ALTER TABLE ai_document_chunks ADD COLUMN embedding TEXT", "ai_document_chunks", "embedding"),
        # v3.5.1 — BCM audit: crisis_comms, DR site capacity, campos DRP operacionales en runbooks
        ("ALTER TABLE bcp_plans ADD COLUMN crisis_comms JSON", "bcp_plans", "crisis_comms"),
        ("ALTER TABLE bcm_locations ADD COLUMN capacity_details JSON", "bcm_locations", "capacity_details"),
        ("ALTER TABLE bcp_test_runbooks ADD COLUMN runbook_type VARCHAR(32)", "bcp_test_runbooks", "runbook_type"),
        ("ALTER TABLE bcp_test_runbooks ADD COLUMN activation_condition TEXT", "bcp_test_runbooks", "activation_condition"),
        ("ALTER TABLE bcp_test_runbooks ADD COLUMN credentials_vault_ref TEXT", "bcp_test_runbooks", "credentials_vault_ref"),
        ("ALTER TABLE bcp_test_runbooks ADD COLUMN success_criteria TEXT", "bcp_test_runbooks", "success_criteria"),
        ("ALTER TABLE bcp_test_runbooks ADD COLUMN responsible_name VARCHAR(255)", "bcp_test_runbooks", "responsible_name"),
        ("ALTER TABLE bcp_test_runbooks ADD COLUMN backup_responsible_name VARCHAR(255)", "bcp_test_runbooks", "backup_responsible_name"),
        # v3.6.0 — TPRM: ciclo de vida del proveedor + tiering + inherent/residual risk
        ("ALTER TABLE suppliers ADD COLUMN tier VARCHAR(16)", "suppliers", "tier"),
        ("ALTER TABLE suppliers ADD COLUMN relationship_status VARCHAR(32) DEFAULT 'active'", "suppliers", "relationship_status"),
        ("ALTER TABLE suppliers ADD COLUMN vendor_type VARCHAR(64)", "suppliers", "vendor_type"),
        ("ALTER TABLE suppliers ADD COLUMN data_sensitivity INTEGER DEFAULT 2", "suppliers", "data_sensitivity"),
        ("ALTER TABLE suppliers ADD COLUMN data_volume INTEGER DEFAULT 2", "suppliers", "data_volume"),
        ("ALTER TABLE suppliers ADD COLUMN system_access_type VARCHAR(32)", "suppliers", "system_access_type"),
        ("ALTER TABLE suppliers ADD COLUMN business_criticality INTEGER DEFAULT 3", "suppliers", "business_criticality"),
        ("ALTER TABLE suppliers ADD COLUMN geographic_risk INTEGER DEFAULT 1", "suppliers", "geographic_risk"),
        ("ALTER TABLE suppliers ADD COLUMN inherent_risk_score INTEGER", "suppliers", "inherent_risk_score"),
        ("ALTER TABLE suppliers ADD COLUMN control_effectiveness INTEGER", "suppliers", "control_effectiveness"),
        ("ALTER TABLE suppliers ADD COLUMN residual_risk_score INTEGER", "suppliers", "residual_risk_score"),
        ("ALTER TABLE suppliers ADD COLUMN is_data_processor BOOLEAN DEFAULT 0", "suppliers", "is_data_processor"),
        ("ALTER TABLE suppliers ADD COLUMN processes_personal_data BOOLEAN DEFAULT 0", "suppliers", "processes_personal_data"),
        ("ALTER TABLE suppliers ADD COLUMN cross_border_transfers BOOLEAN DEFAULT 0", "suppliers", "cross_border_transfers"),
        ("ALTER TABLE suppliers ADD COLUMN is_nis2 BOOLEAN DEFAULT 0", "suppliers", "is_nis2"),
        ("ALTER TABLE suppliers ADD COLUMN is_dora BOOLEAN DEFAULT 0", "suppliers", "is_dora"),
        ("ALTER TABLE suppliers ADD COLUMN is_ens BOOLEAN DEFAULT 0", "suppliers", "is_ens"),
        ("ALTER TABLE suppliers ADD COLUMN country_code VARCHAR(2)", "suppliers", "country_code"),
        ("ALTER TABLE suppliers ADD COLUMN website VARCHAR(255)", "suppliers", "website"),
        ("ALTER TABLE suppliers ADD COLUMN tax_id VARCHAR(64)", "suppliers", "tax_id"),
        ("ALTER TABLE suppliers ADD COLUMN annual_spend REAL", "suppliers", "annual_spend"),
        ("ALTER TABLE suppliers ADD COLUMN parent_supplier_id INTEGER REFERENCES suppliers(id)", "suppliers", "parent_supplier_id"),
        ("ALTER TABLE suppliers ADD COLUMN nth_party_depth INTEGER DEFAULT 1", "suppliers", "nth_party_depth"),
        # v3.6.0 — TPRM: cuestionario basado en plantilla del sistema
        ("ALTER TABLE supplier_questionnaires ADD COLUMN template_code VARCHAR(64)", "supplier_questionnaires", "template_code"),
        # v3.7.0 — TPRM: evaluacion IA del cuestionario
        ("ALTER TABLE supplier_questionnaires ADD COLUMN ai_review JSON", "supplier_questionnaires", "ai_review"),
        ("ALTER TABLE supplier_questionnaires ADD COLUMN ai_reviewed_at DATETIME", "supplier_questionnaires", "ai_reviewed_at"),
        # v3.7.2 — TPRM: recoleccion de evidencia en el portal del proveedor
        ("ALTER TABLE supplier_questionnaires ADD COLUMN evidence JSON", "supplier_questionnaires", "evidence"),
        # v3.8.0 — TPRM: scoring no-conformidades y riesgo residual
        ("ALTER TABLE supplier_questionnaires ADD COLUMN major_nc INTEGER", "supplier_questionnaires", "major_nc"),
        ("ALTER TABLE supplier_questionnaires ADD COLUMN minor_nc INTEGER", "supplier_questionnaires", "minor_nc"),
        ("ALTER TABLE supplier_questionnaires ADD COLUMN residual_risk_level VARCHAR(16)", "supplier_questionnaires", "residual_risk_level"),
        # v3.9.0 — TPRM: flujo dos fases (profiling + assessment) y decision
        ("ALTER TABLE supplier_questionnaires ADD COLUMN phase VARCHAR(16)", "supplier_questionnaires", "phase"),
        ("ALTER TABLE supplier_questionnaires ADD COLUMN parent_assessment_id INTEGER", "supplier_questionnaires", "parent_assessment_id"),
        ("ALTER TABLE supplier_questionnaires ADD COLUMN next_questionnaire_id INTEGER", "supplier_questionnaires", "next_questionnaire_id"),
        ("ALTER TABLE vendor_risk_assessments ADD COLUMN assessment_type VARCHAR(32) DEFAULT 'direct'", "vendor_risk_assessments", "assessment_type"),
        ("ALTER TABLE vendor_risk_assessments ADD COLUMN profiling_questionnaire_id INTEGER", "vendor_risk_assessments", "profiling_questionnaire_id"),
        ("ALTER TABLE vendor_risk_assessments ADD COLUMN assessment_questionnaire_id INTEGER", "vendor_risk_assessments", "assessment_questionnaire_id"),
        ("ALTER TABLE vendor_risk_assessments ADD COLUMN decision_notes TEXT", "vendor_risk_assessments", "decision_notes"),
        ("ALTER TABLE vendor_risk_assessments ADD COLUMN decision_at DATETIME", "vendor_risk_assessments", "decision_at"),
        ("ALTER TABLE vendor_risk_assessments ADD COLUMN decision_by_id INTEGER", "vendor_risk_assessments", "decision_by_id"),
        # v3.9.1 — TPRM: origen del riesgo (proveedor que lo genero via push-to-register)
        ("ALTER TABLE risks ADD COLUMN supplier_id INTEGER", "risks", "supplier_id"),
        # v3.9.2 — TPRM: SLAs del proveedor y campos extendidos en hallazgos
        ("ALTER TABLE suppliers ADD COLUMN slas JSON", "suppliers", "slas"),
        ("ALTER TABLE vendor_issues ADD COLUMN sla_breaches JSON", "vendor_issues", "sla_breaches"),
        ("ALTER TABLE vendor_issues ADD COLUMN impact_description TEXT", "vendor_issues", "impact_description"),
        ("ALTER TABLE vendor_issues ADD COLUMN root_cause TEXT", "vendor_issues", "root_cause"),
        ("ALTER TABLE vendor_issues ADD COLUMN action_items JSON", "vendor_issues", "action_items"),
        ("ALTER TABLE vendor_issues ADD COLUMN evidence_refs JSON", "vendor_issues", "evidence_refs"),
        ("ALTER TABLE vendor_issues ADD COLUMN resolution_notes TEXT", "vendor_issues", "resolution_notes"),
        # v3.9.0 — BCM: tabla de interconexiones tecnicas en dependencias
        ("ALTER TABLE bcp_dependencies ADD COLUMN connection_type VARCHAR(32)", "bcp_dependencies", "connection_type"),
        ("ALTER TABLE bcp_dependencies ADD COLUMN protocol VARCHAR(32)", "bcp_dependencies", "protocol"),
        ("ALTER TABLE bcp_dependencies ADD COLUMN data_direction VARCHAR(8)", "bcp_dependencies", "data_direction"),
        ("ALTER TABLE bcp_dependencies ADD COLUMN data_classification VARCHAR(32)", "bcp_dependencies", "data_classification"),
        # v3.8.0 — BCM: configuracion tecnica IT y monitorizacion en estrategias
        ("ALTER TABLE bcp_strategies ADD COLUMN it_config JSON", "bcp_strategies", "it_config"),
        ("ALTER TABLE bcp_strategies ADD COLUMN monitoring_config JSON", "bcp_strategies", "monitoring_config"),
        # v3.8.0 — BCM: campos de gestion adicionales en planes
        ("ALTER TABLE bcp_plans ADD COLUMN installation_type VARCHAR(32)", "bcp_plans", "installation_type"),
        ("ALTER TABLE bcp_plans ADD COLUMN data_classification_level VARCHAR(32)", "bcp_plans", "data_classification_level"),
        ("ALTER TABLE bcp_plans ADD COLUMN gdpr_data BOOLEAN DEFAULT 0", "bcp_plans", "gdpr_data"),
        ("ALTER TABLE bcp_plans ADD COLUMN affected_users_count INTEGER", "bcp_plans", "affected_users_count"),
        ("ALTER TABLE bcp_plans ADD COLUMN documentation_links JSON", "bcp_plans", "documentation_links"),
        ("ALTER TABLE bcp_plans ADD COLUMN related_documents JSON", "bcp_plans", "related_documents"),
        ("ALTER TABLE bcp_plans ADD COLUMN authorized_activators JSON", "bcp_plans", "authorized_activators"),
        # v4.0.0 — regwatch: propagacion cross-plataforma de cambios normativos
        ("ALTER TABLE controls ADD COLUMN deprecated_at DATETIME", "controls", "deprecated_at"),
        ("ALTER TABLE control_implementations ADD COLUMN regwatch_review_at DATETIME", "control_implementations", "regwatch_review_at"),
        ("ALTER TABLE control_implementations ADD COLUMN regwatch_pack_id INTEGER REFERENCES regwatch_change_packs(id)", "control_implementations", "regwatch_pack_id"),
        ("ALTER TABLE policies ADD COLUMN regwatch_review_at DATETIME", "policies", "regwatch_review_at"),
        ("ALTER TABLE policies ADD COLUMN regwatch_pack_id INTEGER REFERENCES regwatch_change_packs(id)", "policies", "regwatch_pack_id"),
        ("ALTER TABLE bcp_plans ADD COLUMN regwatch_review_at DATETIME", "bcp_plans", "regwatch_review_at"),
        ("ALTER TABLE bcp_plans ADD COLUMN regwatch_pack_id INTEGER REFERENCES regwatch_change_packs(id)", "bcp_plans", "regwatch_pack_id"),
        ("ALTER TABLE supplier_questionnaires ADD COLUMN regwatch_review_at DATETIME", "supplier_questionnaires", "regwatch_review_at"),
        ("ALTER TABLE supplier_questionnaires ADD COLUMN regwatch_pack_id INTEGER REFERENCES regwatch_change_packs(id)", "supplier_questionnaires", "regwatch_pack_id"),
        ("ALTER TABLE compliance_framework_status ADD COLUMN regwatch_review_at DATETIME", "compliance_framework_status", "regwatch_review_at"),
        ("ALTER TABLE compliance_framework_status ADD COLUMN regwatch_pack_id INTEGER REFERENCES regwatch_change_packs(id)", "compliance_framework_status", "regwatch_pack_id"),
        # v4.1.0 — hallazgos accionables: revision de arquitectura -> hallazgos persistidos
        # (generico para cualquier fuente futura: source_document filtra por documento/esquema
        # origen, iso_control identifica el control incumplido, incident_id permite transferir
        # el hallazgo a un incidente para su seguimiento y resolucion).
        ("ALTER TABLE external_findings ADD COLUMN source_document VARCHAR(512)", "external_findings", "source_document"),
        ("ALTER TABLE external_findings ADD COLUMN iso_control VARCHAR(32)", "external_findings", "iso_control"),
        ("ALTER TABLE external_findings ADD COLUMN incident_id INTEGER REFERENCES incidents(id)", "external_findings", "incident_id"),
        # v4.1.0 — versionado de politicas (editar aprobada/publicada crea nueva version en draft)
        ("ALTER TABLE policies ADD COLUMN previous_version_id INTEGER REFERENCES policies(id)", "policies", "previous_version_id"),
        # v4.1.0 — versionado de evaluaciones de proveedor (TPRM)
        ("ALTER TABLE vendor_risk_assessments ADD COLUMN previous_version_id INTEGER REFERENCES vendor_risk_assessments(id)", "vendor_risk_assessments", "previous_version_id"),
        ("ALTER TABLE vendor_risk_assessments ADD COLUMN is_current BOOLEAN DEFAULT 1", "vendor_risk_assessments", "is_current"),
        # v4.2.0 — BCP: sala de crisis enriquecida, versionado de planes, sincronizacion incidentes
        ("ALTER TABLE bcm_evidence_items ADD COLUMN linked_activation_id INTEGER REFERENCES bcm_activations(id)", "bcm_evidence_items", "linked_activation_id"),
        ("ALTER TABLE bcm_activations ADD COLUMN executive_summary TEXT", "bcm_activations", "executive_summary"),
        ("ALTER TABLE bcm_activations ADD COLUMN affected_services JSON", "bcm_activations", "affected_services"),
        ("ALTER TABLE bcm_activations ADD COLUMN ai_summary TEXT", "bcm_activations", "ai_summary"),
        ("ALTER TABLE bcp_plans ADD COLUMN parent_plan_id INTEGER REFERENCES bcp_plans(id)", "bcp_plans", "parent_plan_id"),
        ("ALTER TABLE incidents ADD COLUMN affects_continuity BOOLEAN DEFAULT 0", "incidents", "affects_continuity"),
        ("ALTER TABLE incidents ADD COLUMN bcp_activation_id INTEGER REFERENCES bcm_activations(id)", "incidents", "bcp_activation_id"),
        # v4.3.0 — Proveedor: multiples contactos, CC email, ubicacion, departamento, importancia negocio, responsable interno
        ("ALTER TABLE suppliers ADD COLUMN cc_email VARCHAR(255)", "suppliers", "cc_email"),
        ("ALTER TABLE suppliers ADD COLUMN additional_contacts JSON", "suppliers", "additional_contacts"),
        ("ALTER TABLE suppliers ADD COLUMN location VARCHAR(255)", "suppliers", "location"),
        ("ALTER TABLE suppliers ADD COLUMN department VARCHAR(128)", "suppliers", "department"),
        ("ALTER TABLE suppliers ADD COLUMN business_importance INTEGER", "suppliers", "business_importance"),
        ("ALTER TABLE suppliers ADD COLUMN internal_owner_id INTEGER REFERENCES users(id)", "suppliers", "internal_owner_id"),
        # v4.3.0 — Cuestionario: email de notificacion propio del cuestionario
        ("ALTER TABLE supplier_questionnaires ADD COLUMN notify_email VARCHAR(255)", "supplier_questionnaires", "notify_email"),
        # v4.3.0 — ExternalFinding: link a proveedor monitorizado
        ("ALTER TABLE external_findings ADD COLUMN supplier_id INTEGER REFERENCES suppliers(id)", "external_findings", "supplier_id"),
        # v4.4.0 — Cuestionario: asignacion interna a usuario de la plataforma
        ("ALTER TABLE supplier_questionnaires ADD COLUMN assigned_user_id INTEGER REFERENCES users(id)", "supplier_questionnaires", "assigned_user_id"),
        ("ALTER TABLE supplier_questionnaires ADD COLUMN assignment_type VARCHAR(16)", "supplier_questionnaires", "assignment_type"),
        ("ALTER TABLE supplier_questionnaires ADD COLUMN assigned_at DATETIME", "supplier_questionnaires", "assigned_at"),
        # v5.0 — Jerarquia documental ISO: nivel y documento padre en politicas
        ("ALTER TABLE policies ADD COLUMN document_level INTEGER DEFAULT 1", "policies", "document_level"),
        ("ALTER TABLE policies ADD COLUMN parent_policy_id INTEGER REFERENCES policies(id)", "policies", "parent_policy_id"),
        ("ALTER TABLE policies ADD COLUMN intended_controls JSON", "policies", "intended_controls"),
        # v5.1 — Checkout para edicion concurrente + rondas de aprobacion
        ("ALTER TABLE policies ADD COLUMN checked_out_by_id INTEGER REFERENCES users(id)", "policies", "checked_out_by_id"),
        ("ALTER TABLE policies ADD COLUMN checked_out_at DATETIME", "policies", "checked_out_at"),
        # v5.2.0 — Motor de riesgo: penalizaciones automaticas NC/CCM + retroalimentacion de incidentes
        ("ALTER TABLE control_implementations ADD COLUMN nc_penalty_factor REAL", "control_implementations", "nc_penalty_factor"),
        ("ALTER TABLE control_implementations ADD COLUMN ccm_last_status VARCHAR(10)", "control_implementations", "ccm_last_status"),
        ("ALTER TABLE control_implementations ADD COLUMN ccm_tested_at DATETIME", "control_implementations", "ccm_tested_at"),
        # v5.2.0 — Risk: razon de ajuste de likelihood + objetivo de tratamiento
        ("ALTER TABLE risks ADD COLUMN treatment_progress INTEGER DEFAULT 0", "risks", "treatment_progress"),
        ("ALTER TABLE risks ADD COLUMN likelihood_adjusted_reason TEXT", "risks", "likelihood_adjusted_reason"),
        ("ALTER TABLE risks ADD COLUMN target_residual_level INTEGER", "risks", "target_residual_level"),
        ("ALTER TABLE risks ADD COLUMN target_date DATETIME", "risks", "target_date"),
        ("ALTER TABLE risks ADD COLUMN baseline_residual_level INTEGER", "risks", "baseline_residual_level"),
        # v5.2.0 — GDPR Art.35: riesgo vinculado a actividad que requiere DPIA
        ("ALTER TABLE risks ADD COLUMN gdpr_activity_id INTEGER REFERENCES processing_activities(id)", "risks", "gdpr_activity_id"),
        # v5.3.0 — AlertRule: reglas compuestas multi-condicion
        ("ALTER TABLE alert_rules ADD COLUMN conditions JSON", "alert_rules", "conditions"),
        ("ALTER TABLE alert_rules ADD COLUMN logic VARCHAR(3) DEFAULT 'AND'", "alert_rules", "logic"),
        # v5.3.0 — Control: flag de control obligatorio ISO 27001
        ("ALTER TABLE controls ADD COLUMN is_mandatory BOOLEAN DEFAULT 0", "controls", "is_mandatory"),
        # v5.3.0 — RiskCorrelation
        (
            """CREATE TABLE IF NOT EXISTS risk_correlations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                risk_id_a INTEGER NOT NULL REFERENCES risks(id) ON DELETE CASCADE,
                risk_id_b INTEGER NOT NULL REFERENCES risks(id) ON DELETE CASCADE,
                correlation_factor REAL NOT NULL DEFAULT 0.5,
                description TEXT,
                created_at DATETIME
            )""",
            "risk_correlations",
            "id",
        ),
        # v5.3.0 — KRI: key risk indicators
        (
            """CREATE TABLE IF NOT EXISTS kris (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                risk_id INTEGER REFERENCES risks(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                metric_type VARCHAR(64) NOT NULL,
                warning_threshold REAL,
                breach_threshold REAL,
                current_value REAL,
                status VARCHAR(16) DEFAULT 'normal',
                is_active BOOLEAN DEFAULT 1,
                last_evaluated_at DATETIME,
                created_at DATETIME,
                alert_on_breach BOOLEAN DEFAULT 1,
                recipient_email VARCHAR(255)
            )""",
            "kris",
            "id",
        ),
        # v5.4.0 — KRI/KPI: campos de edicion, visibilidad y tipo de indicador
        ("ALTER TABLE kris ADD COLUMN indicator_type VARCHAR(8) DEFAULT 'kri'", "kris", "indicator_type"),
        ("ALTER TABLE kris ADD COLUMN is_visible BOOLEAN DEFAULT 1", "kris", "is_visible"),
        ("ALTER TABLE kris ADD COLUMN custom_name VARCHAR(255)", "kris", "custom_name"),
        ("ALTER TABLE kris ADD COLUMN description TEXT", "kris", "description"),
        ("ALTER TABLE kris ADD COLUMN is_system BOOLEAN DEFAULT 0", "kris", "is_system"),
        ("ALTER TABLE kris ADD COLUMN direction VARCHAR(20) DEFAULT 'lower_is_better'", "kris", "direction"),
        # v5.5.0 — Supplier: lifecycle, onboarding, firma legal, DORA, concentracion
        ("ALTER TABLE suppliers ADD COLUMN lifecycle_stage VARCHAR(32) DEFAULT 'active'", "suppliers", "lifecycle_stage"),
        ("ALTER TABLE suppliers ADD COLUMN lifecycle_changed_at DATETIME", "suppliers", "lifecycle_changed_at"),
        ("ALTER TABLE suppliers ADD COLUMN lifecycle_changed_by_id INTEGER REFERENCES users(id)", "suppliers", "lifecycle_changed_by_id"),
        ("ALTER TABLE suppliers ADD COLUMN onboarding_completed_at DATETIME", "suppliers", "onboarding_completed_at"),
        ("ALTER TABLE suppliers ADD COLUMN onboarding_checklist JSON", "suppliers", "onboarding_checklist"),
        ("ALTER TABLE suppliers ADD COLUMN stakeholders JSON", "suppliers", "stakeholders"),
        ("ALTER TABLE suppliers ADD COLUMN dpa_signed_at DATETIME", "suppliers", "dpa_signed_at"),
        ("ALTER TABLE suppliers ADD COLUMN dpa_signed_by VARCHAR(255)", "suppliers", "dpa_signed_by"),
        ("ALTER TABLE suppliers ADD COLUMN dpa_document_id INTEGER REFERENCES ai_documents(id)", "suppliers", "dpa_document_id"),
        ("ALTER TABLE suppliers ADD COLUMN nda_signed_at DATETIME", "suppliers", "nda_signed_at"),
        ("ALTER TABLE suppliers ADD COLUMN nda_document_id INTEGER REFERENCES ai_documents(id)", "suppliers", "nda_document_id"),
        ("ALTER TABLE suppliers ADD COLUMN contract_document_id INTEGER REFERENCES ai_documents(id)", "suppliers", "contract_document_id"),
        ("ALTER TABLE suppliers ADD COLUMN contract_renewal_reminder_sent_at DATETIME", "suppliers", "contract_renewal_reminder_sent_at"),
        ("ALTER TABLE suppliers ADD COLUMN ict_service_category VARCHAR(16)", "suppliers", "ict_service_category"),
        ("ALTER TABLE suppliers ADD COLUMN exit_strategy TEXT", "suppliers", "exit_strategy"),
        ("ALTER TABLE suppliers ADD COLUMN concentration_risk_flag BOOLEAN DEFAULT 0", "suppliers", "concentration_risk_flag"),
        ("ALTER TABLE suppliers ADD COLUMN concentration_risk_mitigated_at DATETIME", "suppliers", "concentration_risk_mitigated_at"),
        ("ALTER TABLE suppliers ADD COLUMN concentration_risk_notes TEXT", "suppliers", "concentration_risk_notes"),
        # v5.5.0 — BCPPlan: risk_ids, crisis activation
        ("ALTER TABLE bcp_plans ADD COLUMN risk_ids JSON", "bcp_plans", "risk_ids"),
        ("ALTER TABLE bcp_plans ADD COLUMN activation_status VARCHAR(16) DEFAULT 'standby'", "bcp_plans", "activation_status"),
        ("ALTER TABLE bcp_plans ADD COLUMN activated_at DATETIME", "bcp_plans", "activated_at"),
        ("ALTER TABLE bcp_plans ADD COLUMN activated_by_id INTEGER REFERENCES users(id)", "bcp_plans", "activated_by_id"),
        ("ALTER TABLE bcp_plans ADD COLUMN deactivated_at DATETIME", "bcp_plans", "deactivated_at"),
        ("ALTER TABLE bcp_plans ADD COLUMN activation_log JSON", "bcp_plans", "activation_log"),
        # v5.8.0 — Gate de onboarding cyber: override, decision formal, cadena de firmas
        ("ALTER TABLE suppliers ADD COLUMN gate_override_type VARCHAR(16)", "suppliers", "gate_override_type"),
        ("ALTER TABLE suppliers ADD COLUMN gate_override_justification TEXT", "suppliers", "gate_override_justification"),
        ("ALTER TABLE suppliers ADD COLUMN gate_override_by_id INTEGER REFERENCES users(id)", "suppliers", "gate_override_by_id"),
        ("ALTER TABLE suppliers ADD COLUMN gate_override_at DATETIME", "suppliers", "gate_override_at"),
        ("ALTER TABLE suppliers ADD COLUMN forced_signoffs JSON", "suppliers", "forced_signoffs"),
        ("ALTER TABLE suppliers ADD COLUMN onboarding_decision VARCHAR(16)", "suppliers", "onboarding_decision"),
        ("ALTER TABLE suppliers ADD COLUMN onboarding_decision_notes TEXT", "suppliers", "onboarding_decision_notes"),
        ("ALTER TABLE suppliers ADD COLUMN onboarding_decision_by_id INTEGER REFERENCES users(id)", "suppliers", "onboarding_decision_by_id"),
        ("ALTER TABLE suppliers ADD COLUMN onboarding_decision_at DATETIME", "suppliers", "onboarding_decision_at"),
        ("ALTER TABLE suppliers ADD COLUMN onboarding_conditions JSON", "suppliers", "onboarding_conditions"),
        ("ALTER TABLE suppliers ADD COLUMN sign_off_chain_state JSON", "suppliers", "sign_off_chain_state"),
        (
            """CREATE TABLE IF NOT EXISTS onboarding_gate_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER REFERENCES organizations(id),
                auto_approve_below INTEGER DEFAULT 30,
                manual_review_above INTEGER DEFAULT 60,
                sign_off_chain JSON,
                bypass_min_role VARCHAR(16) DEFAULT 'admin',
                bypass_requires_justification BOOLEAN DEFAULT 1,
                force_controls_allowed BOOLEAN DEFAULT 1,
                updated_at DATETIME,
                updated_by_id INTEGER REFERENCES users(id)
            )""",
            "onboarding_gate_configs",
            "id",
        ),
        # v5.5.0 — VendorIssue: auto-generated flag, risk register link
        ("ALTER TABLE vendor_issues ADD COLUMN auto_generated BOOLEAN DEFAULT 0", "vendor_issues", "auto_generated"),
        ("ALTER TABLE vendor_issues ADD COLUMN auto_generated_source VARCHAR(64)", "vendor_issues", "auto_generated_source"),
        ("ALTER TABLE vendor_issues ADD COLUMN linked_risk_id INTEGER REFERENCES risks(id)", "vendor_issues", "linked_risk_id"),
        ("ALTER TABLE vendor_issues ADD COLUMN resolved_by_action VARCHAR(255)", "vendor_issues", "resolved_by_action"),
        # v5.9.0 — ReportBrandingConfig: soporte de fichero de plantilla (.docx/.html)
        ("ALTER TABLE report_branding_configs ADD COLUMN template_filename VARCHAR(255)", "report_branding_configs", "template_filename"),
        ("ALTER TABLE report_branding_configs ADD COLUMN template_mime VARCHAR(128)", "report_branding_configs", "template_mime"),
        # v4.4.0 — Supplier: resultado de monitoreo periodico
        ("ALTER TABLE suppliers ADD COLUMN last_monitored_at DATETIME", "suppliers", "last_monitored_at"),
        ("ALTER TABLE suppliers ADD COLUMN monitoring_status VARCHAR(16)", "suppliers", "monitoring_status"),
        # Trust Portal IA — URL y resultado del ultimo analisis por IA
        ("ALTER TABLE suppliers ADD COLUMN trust_portal_url VARCHAR(512)", "suppliers", "trust_portal_url"),
        ("ALTER TABLE suppliers ADD COLUMN trust_portal_last_scraped_at DATETIME", "suppliers", "trust_portal_last_scraped_at"),
        ("ALTER TABLE suppliers ADD COLUMN trust_portal_raw_data JSON", "suppliers", "trust_portal_raw_data"),
        # v5.10.0 — AuditProgram: auditado (entidad auditada) + equipo auditor
        ("ALTER TABLE audit_programs ADD COLUMN auditee VARCHAR(255)", "audit_programs", "auditee"),
        ("ALTER TABLE audit_programs ADD COLUMN actual_start DATE", "audit_programs", "actual_start"),
        ("ALTER TABLE audit_programs ADD COLUMN actual_end DATE", "audit_programs", "actual_end"),
        # v5.10.0 — ChangeRequest: campos normativos ISO 27001 cl. 6.3
        ("ALTER TABLE change_requests ADD COLUMN urgency VARCHAR(16) DEFAULT 'normal'", "change_requests", "urgency"),
        ("ALTER TABLE change_requests ADD COLUMN rollback_plan TEXT", "change_requests", "rollback_plan"),
        ("ALTER TABLE change_requests ADD COLUMN approval_evidence TEXT", "change_requests", "approval_evidence"),
        ("ALTER TABLE change_requests ADD COLUMN iso_clause_ref VARCHAR(128)", "change_requests", "iso_clause_ref"),
        # v5.10.0 — AuditFinding: ciclo de vida completo ISO 27001 cl. 9.2
        ("ALTER TABLE audit_findings ADD COLUMN status VARCHAR(32) DEFAULT 'open'", "audit_findings", "status"),
        ("ALTER TABLE audit_findings ADD COLUMN responsible_id INTEGER REFERENCES users(id)", "audit_findings", "responsible_id"),
        ("ALTER TABLE audit_findings ADD COLUMN action_plan TEXT", "audit_findings", "action_plan"),
        ("ALTER TABLE audit_findings ADD COLUMN deadline DATETIME", "audit_findings", "deadline"),
        ("ALTER TABLE audit_findings ADD COLUMN closed_at DATETIME", "audit_findings", "closed_at"),
        ("ALTER TABLE audit_findings ADD COLUMN comments JSON DEFAULT '[]'", "audit_findings", "comments"),
        ("ALTER TABLE audit_findings ADD COLUMN resolution_evidence TEXT", "audit_findings", "resolution_evidence"),
        # v5.3.0 — RiskSnapshot: historico mensual de niveles de riesgo
        (
            """CREATE TABLE IF NOT EXISTS risk_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                risk_id INTEGER NOT NULL REFERENCES risks(id) ON DELETE CASCADE,
                snapshot_date DATETIME NOT NULL,
                inherent_likelihood INTEGER,
                inherent_consequence INTEGER,
                inherent_level INTEGER,
                residual_likelihood INTEGER,
                residual_consequence INTEGER,
                residual_level INTEGER,
                control_count INTEGER,
                risk_status VARCHAR(32),
                created_at DATETIME
            )""",
            "risk_snapshots",
            "id",
        ),
        # v5.0 — MS Forms polling: alta automatica de proveedores (Via 3)
        ("ALTER TABLE form_integration_configs ADD COLUMN msforms_poll_enabled BOOLEAN DEFAULT 0", "form_integration_configs", "msforms_poll_enabled"),
        ("ALTER TABLE form_integration_configs ADD COLUMN msforms_tenant_id VARCHAR(255)", "form_integration_configs", "msforms_tenant_id"),
        ("ALTER TABLE form_integration_configs ADD COLUMN msforms_client_id VARCHAR(255)", "form_integration_configs", "msforms_client_id"),
        ("ALTER TABLE form_integration_configs ADD COLUMN msforms_client_secret_enc TEXT", "form_integration_configs", "msforms_client_secret_enc"),
        ("ALTER TABLE form_integration_configs ADD COLUMN msforms_form_id VARCHAR(255)", "form_integration_configs", "msforms_form_id"),
        ("ALTER TABLE form_integration_configs ADD COLUMN msforms_poll_interval_hours INTEGER DEFAULT 4", "form_integration_configs", "msforms_poll_interval_hours"),
        ("ALTER TABLE form_integration_configs ADD COLUMN msforms_last_poll_at DATETIME", "form_integration_configs", "msforms_last_poll_at"),
        ("ALTER TABLE form_integration_configs ADD COLUMN msforms_last_response_ts VARCHAR(64)", "form_integration_configs", "msforms_last_response_ts"),
        ("ALTER TABLE form_integration_configs ADD COLUMN msforms_field_mapping JSON", "form_integration_configs", "msforms_field_mapping"),
        ("ALTER TABLE form_integration_configs ADD COLUMN msforms_auto_ai_review BOOLEAN DEFAULT 1", "form_integration_configs", "msforms_auto_ai_review"),
        ("ALTER TABLE form_integration_configs ADD COLUMN msforms_pa_callback_url VARCHAR(500)", "form_integration_configs", "msforms_pa_callback_url"),
        ("ALTER TABLE suppliers ADD COLUMN msforms_origin BOOLEAN DEFAULT 0", "suppliers", "msforms_origin"),
        ("ALTER TABLE suppliers ADD COLUMN msforms_responder VARCHAR(255)", "suppliers", "msforms_responder"),
        # G04: log persistente de eventos ERP (SAP/Jagger/Sphera)
        (
            """CREATE TABLE IF NOT EXISTS erp_webhook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                source VARCHAR(32) NOT NULL,
                event_type VARCHAR(64) NOT NULL,
                entity_name VARCHAR(255),
                result VARCHAR(64) NOT NULL,
                ts DATETIME NOT NULL
            )""",
            "erp_webhook_events",
            "id",
        ),
        # v6.0.0 — Audit trail inmutable: old/new values + IP
        ("ALTER TABLE audit_log ADD COLUMN old_value TEXT", "audit_log", "old_value"),
        ("ALTER TABLE audit_log ADD COLUMN new_value TEXT", "audit_log", "new_value"),
        ("ALTER TABLE audit_log ADD COLUMN ip_address VARCHAR(64)", "audit_log", "ip_address"),
        # v6.2.0 — Password reset por email
        ("ALTER TABLE users ADD COLUMN password_reset_token VARCHAR(255)", "users", "password_reset_token"),
        ("ALTER TABLE users ADD COLUMN password_reset_expires_at DATETIME", "users", "password_reset_expires_at"),
        # v6.3.0 — BCM: revision semantica IA del contenido de planes BCP/DRP
        ("ALTER TABLE bcp_plans ADD COLUMN ai_content_review JSON", "bcp_plans", "ai_content_review"),
        # v6.3.0 — BCM: revision semantica IA del contenido real de la evidencia subida
        ("ALTER TABLE bcm_evidence_items ADD COLUMN ai_review JSON", "bcm_evidence_items", "ai_review"),
        # v3.9.0 — canales de alerta alternativos a SMTP: Teams webhook / Power Automate
        ("ALTER TABLE email_settings ADD COLUMN teams_webhook_url_encrypted TEXT", "email_settings", "teams_webhook_url_encrypted"),
        ("ALTER TABLE email_settings ADD COLUMN teams_webhook_enabled BOOLEAN DEFAULT 0", "email_settings", "teams_webhook_enabled"),
        ("ALTER TABLE email_settings ADD COLUMN power_automate_webhook_url_encrypted TEXT", "email_settings", "power_automate_webhook_url_encrypted"),
        ("ALTER TABLE email_settings ADD COLUMN power_automate_webhook_enabled BOOLEAN DEFAULT 0", "email_settings", "power_automate_webhook_enabled"),
        # v3.9.1 — SharePoint: sincronizacion automatica de carpetas permitidas
        ("ALTER TABLE ai_documents ADD COLUMN source VARCHAR(32) DEFAULT 'upload'", "ai_documents", "source"),
        ("ALTER TABLE ai_documents ADD COLUMN source_site_id VARCHAR(128)", "ai_documents", "source_site_id"),
        ("ALTER TABLE ai_documents ADD COLUMN source_drive_id VARCHAR(128)", "ai_documents", "source_drive_id"),
        ("ALTER TABLE ai_documents ADD COLUMN source_item_id VARCHAR(128)", "ai_documents", "source_item_id"),
        ("ALTER TABLE ai_documents ADD COLUMN source_deleted BOOLEAN DEFAULT 0", "ai_documents", "source_deleted"),
        # v6.4.0 — Via 4: alta de proveedor por email (polling de buzon, IMAP o Graph Mail)
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_enabled BOOLEAN DEFAULT 0", "form_integration_configs", "email_intake_enabled"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_mode VARCHAR(16)", "form_integration_configs", "email_intake_mode"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_poll_interval_hours INTEGER DEFAULT 2", "form_integration_configs", "email_intake_poll_interval_hours"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_last_poll_at DATETIME", "form_integration_configs", "email_intake_last_poll_at"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_auto_ai_review BOOLEAN DEFAULT 1", "form_integration_configs", "email_intake_auto_ai_review"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_sender_allowlist JSON", "form_integration_configs", "email_intake_sender_allowlist"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_subject_filter VARCHAR(255)", "form_integration_configs", "email_intake_subject_filter"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_field_mapping JSON", "form_integration_configs", "email_intake_field_mapping"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_graph_tenant_id VARCHAR(255)", "form_integration_configs", "email_intake_graph_tenant_id"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_graph_client_id VARCHAR(255)", "form_integration_configs", "email_intake_graph_client_id"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_graph_client_secret_enc TEXT", "form_integration_configs", "email_intake_graph_client_secret_enc"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_graph_mailbox VARCHAR(255)", "form_integration_configs", "email_intake_graph_mailbox"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_graph_last_message_id VARCHAR(255)", "form_integration_configs", "email_intake_graph_last_message_id"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_graph_last_received_ts VARCHAR(64)", "form_integration_configs", "email_intake_graph_last_received_ts"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_imap_host VARCHAR(255)", "form_integration_configs", "email_intake_imap_host"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_imap_port INTEGER DEFAULT 993", "form_integration_configs", "email_intake_imap_port"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_imap_username VARCHAR(255)", "form_integration_configs", "email_intake_imap_username"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_imap_password_enc TEXT", "form_integration_configs", "email_intake_imap_password_enc"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_imap_use_ssl BOOLEAN DEFAULT 1", "form_integration_configs", "email_intake_imap_use_ssl"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_imap_folder VARCHAR(128) DEFAULT 'INBOX'", "form_integration_configs", "email_intake_imap_folder"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_imap_last_uid INTEGER", "form_integration_configs", "email_intake_imap_last_uid"),
        ("ALTER TABLE form_integration_configs ADD COLUMN email_intake_imap_uidvalidity INTEGER", "form_integration_configs", "email_intake_imap_uidvalidity"),
        ("ALTER TABLE suppliers ADD COLUMN email_origin BOOLEAN DEFAULT 0", "suppliers", "email_origin"),
        ("ALTER TABLE suppliers ADD COLUMN email_sender VARCHAR(255)", "suppliers", "email_sender"),
        ("ALTER TABLE suppliers ADD COLUMN email_subject VARCHAR(500)", "suppliers", "email_subject"),
        ("ALTER TABLE suppliers ADD COLUMN email_message_id VARCHAR(255)", "suppliers", "email_message_id"),
        ("ALTER TABLE suppliers ADD COLUMN email_extraction_method VARCHAR(16)", "suppliers", "email_extraction_method"),
        ("ALTER TABLE suppliers ADD COLUMN email_needs_review BOOLEAN DEFAULT 0", "suppliers", "email_needs_review"),
        # v6.5.0 — Alertas: catalogo ampliado (proveedores/TPRM, BCP, vigilancia normativa)
        # y reglas compuestas multi-entidad
        ("ALTER TABLE alert_rules ADD COLUMN entity_type VARCHAR(32)", "alert_rules", "entity_type"),
        # v6.0.0 — Motor residual v2: trazabilidad del analisis IA y frescura
        ("ALTER TABLE risks ADD COLUMN analysis_stale BOOLEAN DEFAULT 0", "risks", "analysis_stale"),
        ("ALTER TABLE risks ADD COLUMN stale_reason VARCHAR(255)", "risks", "stale_reason"),
        ("ALTER TABLE risks ADD COLUMN ai_context_meta JSON", "risks", "ai_context_meta"),
        # v6.0.0 — Evidence understanding: revision IA del contenido de evidencias
        ("ALTER TABLE evidence ADD COLUMN ai_review JSON", "evidence", "ai_review"),
        ("ALTER TABLE evidence ADD COLUMN ai_reviewed_at DATETIME", "evidence", "ai_reviewed_at"),
        # v6.0.0 — registro de migraciones one-shot (pasos de datos que solo corren una vez)
        (
            """CREATE TABLE IF NOT EXISTS app_migrations (
                name VARCHAR(128) PRIMARY KEY,
                applied_at DATETIME
            )""",
            "app_migrations",
            "name",
        ),
    ]
    with engine.connect() as conn:
        for sql, table, col in migrations:
            try:
                # Comprobar si la columna ya existe
                result = conn.execute(
                    __import__("sqlalchemy").text(f"PRAGMA table_info({table})")
                )
                existing_cols = [row[1] for row in result]
                if col not in existing_cols:
                    conn.execute(__import__("sqlalchemy").text(sql))
                    conn.commit()
            except Exception as e:
                # A6: registrar errores reales; silenciar solo "tabla no existe aun"
                err_lower = str(e).lower()
                if "no such table" not in err_lower and "already exists" not in err_lower:
                    logger.error("Migration failed: %s | SQL: %s", e, sql)

        # Migrar indice unico de feature_flags: nombre global -> compuesto (name, org_id)
        try:
            conn.execute(__import__("sqlalchemy").text("DROP INDEX IF EXISTS ix_feature_flags_name"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_flag_name_org "
                "ON feature_flags(name, COALESCE(organization_id, 0))"
            ))
            conn.commit()
        except Exception:
            pass

        # v2.5.0 — Constraint UNIQUE para external_id (previene duplicacion cruzada de imports)
        try:
            conn.execute(__import__("sqlalchemy").text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_asset_external_id_org "
                "ON assets(organization_id, external_id) WHERE external_id IS NOT NULL"
            ))
            conn.commit()
        except Exception:
            pass

        # v2.4.1 — Normalizar valores OSINT a minusculas
        # SQLAlchemy almacenaba enums por NAME (LEAKCHECK) pero el motor los guardaba
        # por VALUE (leakcheck). Unificar todo a minusculas para consistencia.
        for norm_sql in [
            "UPDATE osint_findings SET source = LOWER(source) WHERE source != LOWER(source)",
            "UPDATE osint_findings SET risk_level = LOWER(risk_level) WHERE risk_level != LOWER(risk_level)",
            "UPDATE osint_findings SET finding_type = LOWER(finding_type) WHERE finding_type != LOWER(finding_type)",
        ]:
            try:
                conn.execute(__import__("sqlalchemy").text(norm_sql))
                conn.commit()
            except Exception:
                pass

        # v6.1.0 — Indices de rendimiento: columnas de FK y filtros frecuentes
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS ix_risks_asset_id ON risks (asset_id)",
            "CREATE INDEX IF NOT EXISTS ix_risks_threat_id ON risks (threat_id)",
            "CREATE INDEX IF NOT EXISTS ix_risks_status ON risks (status)",
            "CREATE INDEX IF NOT EXISTS ix_control_implementations_control_id ON control_implementations (control_id)",
            "CREATE INDEX IF NOT EXISTS ix_supplier_questionnaires_supplier_id ON supplier_questionnaires (supplier_id)",
            "CREATE INDEX IF NOT EXISTS ix_vendor_issues_supplier_id ON vendor_issues (supplier_id)",
            "CREATE INDEX IF NOT EXISTS ix_vendor_issues_status ON vendor_issues (status)",
            "CREATE INDEX IF NOT EXISTS ix_treatment_tasks_risk_id ON treatment_tasks (risk_id)",
            "CREATE INDEX IF NOT EXISTS ix_evidence_risk_id ON evidence (risk_id)",
            "CREATE INDEX IF NOT EXISTS ix_evidence_control_implementation_id ON evidence (control_implementation_id)",
            "CREATE INDEX IF NOT EXISTS ix_evidence_compliance_framework ON evidence (compliance_framework)",
            "CREATE INDEX IF NOT EXISTS ix_compliance_framework_status_framework_code ON compliance_framework_status (framework_code)",
            "CREATE INDEX IF NOT EXISTS ix_compliance_framework_status_requirement_id ON compliance_framework_status (requirement_id)",
        ]:
            try:
                conn.execute(__import__("sqlalchemy").text(idx_sql))
                conn.commit()
            except Exception:
                pass


def _seed_licenses(db: Session) -> None:
    """Crea licencias iniciales para todas las organizaciones sin licencia."""
    from app.models import License, LicenseStatus
    from app.services import license_service

    orgs = db.query(Organization).all()
    for org in orgs:
        existing = license_service.get_license(db, org.id)
        if not existing:
            license_service.create_license_for_org(
                db, org.id, org.plan, expires_at=None
            )


def seed_default_survey_templates(db: Session, org_id: int) -> None:
    """Crea plantillas de encuesta por defecto para una organización nueva."""
    from app.models import SurveyTemplate
    if db.query(SurveyTemplate).filter_by(organization_id=org_id).count() > 0:
        return
    templates = [
        {
            "name": "Evaluación de riesgo por propietario de activo",
            "description": "Encuesta corta para que el propietario del activo evalúe la probabilidad e impacto de un riesgo desde su conocimiento operativo.",
            "survey_type": "risk_assessment",
            "is_default": True,
            "questions": [
                {
                    "id": "q1", "type": "likelihood_scale",
                    "text": "En tu opinión, ¿con qué probabilidad podría materializarse este riesgo en los próximos 12 meses?",
                    "help_text": "1=Muy improbable, 2=Improbable, 3=Posible, 4=Probable, 5=Casi seguro",
                    "required": True, "risk_field": "inherent_likelihood",
                    "options": ["1 - Muy improbable", "2 - Improbable", "3 - Posible", "4 - Probable", "5 - Casi seguro"],
                },
                {
                    "id": "q2", "type": "impact_scale",
                    "text": "Si este riesgo se materializara, ¿cuál sería el impacto en tus operaciones?",
                    "help_text": "1=Insignificante, 2=Menor, 3=Moderado, 4=Mayor, 5=Catastrófico",
                    "required": True, "risk_field": "inherent_consequence",
                    "options": ["1 - Insignificante", "2 - Menor", "3 - Moderado", "4 - Mayor", "5 - Catastrófico"],
                },
                {
                    "id": "q3", "type": "control_effectiveness",
                    "text": "¿Qué controles tienes actualmente en tu área para mitigar este riesgo?",
                    "required": False, "risk_field": None,
                    "options": ["No existen controles", "Controles básicos/informales", "Controles parciales documentados", "Controles implementados y revisados", "Controles optimizados y monitorizados continuamente"],
                },
                {
                    "id": "q4", "type": "text_long",
                    "text": "¿Qué medidas adicionales crees que deberían implementarse?",
                    "required": False, "risk_field": None,
                },
                {
                    "id": "q5", "type": "yes_no_na",
                    "text": "¿Has tenido en tu área algún incidente relacionado con este riesgo en los últimos 12 meses?",
                    "required": False, "risk_field": None,
                },
            ],
        },
        {
            "name": "Validación de controles por responsable",
            "description": "Para que los responsables de controles confirmen el estado de implementación y efectividad.",
            "survey_type": "control_validation",
            "is_default": True,
            "questions": [
                {
                    "id": "q1", "type": "control_effectiveness",
                    "text": "¿Cuál es el estado actual de implementación de este control?",
                    "required": True, "risk_field": None,
                    "options": ["No implementado", "En proceso de implementación", "Implementado parcialmente", "Implementado completamente", "Optimizado y bajo mejora continua"],
                },
                {
                    "id": "q2", "type": "yes_no_na",
                    "text": "¿Existe documentación actualizada de este control?",
                    "required": True, "risk_field": None,
                },
                {
                    "id": "q3", "type": "yes_no_na",
                    "text": "¿Se realizan revisiones periódicas del control?",
                    "required": True, "risk_field": None,
                },
                {
                    "id": "q4", "type": "date",
                    "text": "¿Cuándo fue la última revisión o prueba de este control?",
                    "required": False, "risk_field": None,
                },
                {
                    "id": "q5", "type": "text_long",
                    "text": "Describe brevemente cómo funciona este control en la práctica",
                    "required": False, "risk_field": None,
                },
                {
                    "id": "q6", "type": "file_upload",
                    "text": "Adjunta evidencia del control (captura, informe, registro)",
                    "required": False, "risk_field": None,
                },
            ],
        },
        {
            "name": "Revisión anual del registro de riesgos",
            "description": "Encuesta completa para la revisión anual de todos los riesgos de un área.",
            "survey_type": "annual_review",
            "is_default": True,
            "questions": [
                {
                    "id": "q1", "type": "yes_no_na",
                    "text": "¿Sigue siendo este riesgo relevante para tu área de actividad?",
                    "required": True, "risk_field": None,
                },
                {
                    "id": "q2", "type": "likelihood_scale",
                    "text": "Probabilidad actual (considerando los controles existentes)",
                    "required": True, "risk_field": None,
                    "options": ["1 - Muy improbable", "2 - Improbable", "3 - Posible", "4 - Probable", "5 - Casi seguro"],
                },
                {
                    "id": "q3", "type": "impact_scale",
                    "text": "Impacto potencial actual",
                    "required": True, "risk_field": None,
                    "options": ["1 - Insignificante", "2 - Menor", "3 - Moderado", "4 - Mayor", "5 - Catastrófico"],
                },
                {
                    "id": "q4", "type": "multi_select",
                    "text": "¿Qué ha cambiado desde la última evaluación?",
                    "required": False, "risk_field": None,
                    "options": ["El proceso de negocio ha cambiado", "Nueva tecnología implementada", "Cambio de proveedor", "Cambio regulatorio", "Incidente previo en esta área", "Cambio en el equipo responsable", "Nada significativo ha cambiado"],
                },
                {
                    "id": "q5", "type": "text_long",
                    "text": "Comentarios adicionales para el equipo de seguridad",
                    "required": False, "risk_field": None,
                },
            ],
        },
    ]
    for t in templates:
        db.add(SurveyTemplate(organization_id=org_id, created_by_id=None, **t))
    db.commit()


def _backfill_risk_supplier_id(db: Session) -> None:
    """Retrocompatibilidad v3.9.1: asigna supplier_id a riesgos vinculados a evaluaciones TPRM."""
    try:
        from app.models import VendorRiskAssessment, Risk as _Risk
        rows = db.query(VendorRiskAssessment).filter(
            VendorRiskAssessment.linked_risk_id.isnot(None),
            VendorRiskAssessment.supplier_id.isnot(None),
        ).all()
        updated = 0
        for va in rows:
            risk = db.query(_Risk).filter(
                _Risk.id == va.linked_risk_id,
                _Risk.supplier_id.is_(None),
            ).first()
            if risk:
                risk.supplier_id = va.supplier_id
                updated += 1
        if updated:
            db.commit()
            print(f"Backfill: {updated} riesgo(s) TPRM actualizados con supplier_id.")
    except Exception as exc:
        print(f"Backfill risk supplier_id omitido: {exc}")


def _seed_default_kpis(db: Session, org_id: int) -> None:
    """Siembra los KPIs de sistema por defecto (idempotente via is_system + metric_type)."""
    from app.models import KRI, KRIMetricType
    _KPI_CATALOG = [
        # ISO 27001:2022 cl.9.1 — Evaluacion del rendimiento
        {
            "name": "Tasa de tratamiento de riesgos altos",
            "metric_type": KRIMetricType.KPI_TREATMENT_RATE.value,
            "description": "% riesgos de nivel alto (>=4) con plan de tratamiento definido. ISO 27001:2022 cl.6.1.3",
            "direction": "higher_is_better",
            "warning_threshold": 80.0,
            "breach_threshold": 60.0,
        },
        {
            "name": "Tiempo medio de tratamiento (dias)",
            "metric_type": KRIMetricType.KPI_MTTT.value,
            "description": "Dias medios desde identificacion hasta tratamiento activo. ISO 27001:2022 cl.9.1",
            "direction": "lower_is_better",
            "warning_threshold": 60.0,
            "breach_threshold": 90.0,
        },
        {
            "name": "Cobertura de controles ISO 27002",
            "metric_type": KRIMetricType.KPI_CONTROL_COVERAGE.value,
            "description": "% controles del catalogo ISO 27002 con al menos una implementacion. ISO 27001:2022 A.5-8",
            "direction": "higher_is_better",
            "warning_threshold": 60.0,
            "breach_threshold": 40.0,
        },
        {
            "name": "Madurez media de controles",
            "metric_type": KRIMetricType.KPI_CONTROL_MATURITY_AVG.value,
            "description": "Promedio de madurez (0-5) de todas las implementaciones de control. ISO 27001:2022 cl.9.1",
            "direction": "higher_is_better",
            "warning_threshold": 2.5,
            "breach_threshold": 1.5,
        },
        {
            "name": "Cumplimiento revision de politicas",
            "metric_type": KRIMetricType.KPI_POLICY_REVIEW.value,
            "description": "% politicas publicadas con fecha de revision vigente. ISO 27001:2022 cl.5.2",
            "direction": "higher_is_better",
            "warning_threshold": 70.0,
            "breach_threshold": 50.0,
        },
        {
            "name": "Tasa de cierre de no conformidades",
            "metric_type": KRIMetricType.KPI_NC_CLOSURE_RATE.value,
            "description": "% NCs cerradas en <= 90 dias desde su apertura. ISO 27001:2022 cl.10.1",
            "direction": "higher_is_better",
            "warning_threshold": 60.0,
            "breach_threshold": 40.0,
        },
        # ISO 27005:2022 — Gestion del riesgo
        {
            "name": "Reduccion media del riesgo (%)",
            "metric_type": KRIMetricType.KPI_RISK_REDUCTION_AVG.value,
            "description": "Reduccion porcentual promedio de nivel inherente a residual. ISO 27005:2022 §8.6",
            "direction": "higher_is_better",
            "warning_threshold": 30.0,
            "breach_threshold": 15.0,
        },
        {
            "name": "Conformidad con apetito de riesgo (%)",
            "metric_type": KRIMetricType.KPI_APPETITE_COMPLIANCE.value,
            "description": "% riesgos con nivel residual dentro del apetito (<=4). ISO 27005:2022 §7.3",
            "direction": "higher_is_better",
            "warning_threshold": 70.0,
            "breach_threshold": 50.0,
        },
        {
            "name": "Cobertura de activos evaluados (%)",
            "metric_type": KRIMetricType.KPI_ASSET_COVERAGE.value,
            "description": "% activos con al menos un riesgo evaluado. ISO 27005:2022 §8.2",
            "direction": "higher_is_better",
            "warning_threshold": 60.0,
            "breach_threshold": 40.0,
        },
        {
            "name": "Riesgos sin responsable (%)",
            "metric_type": KRIMetricType.KPI_RISK_NO_OWNER.value,
            "description": "% riesgos activos sin owner_id asignado. ISO 27001:2022 cl.5.3",
            "direction": "lower_is_better",
            "warning_threshold": 15.0,
            "breach_threshold": 30.0,
        },
        {
            "name": "Riesgos altos sin plan de tratamiento",
            "metric_type": KRIMetricType.KPI_HIGH_RISKS_NO_PLAN.value,
            "description": "Numero de riesgos residual >= 4 sin plan de tratamiento. ISO 27005:2022 §8.4",
            "direction": "lower_is_better",
            "warning_threshold": 5.0,
            "breach_threshold": 10.0,
        },
        # NIS2 Art.23 / DORA
        {
            "name": "Tasa de notificacion NIS2 en plazo (%)",
            "metric_type": KRIMetricType.KPI_NIS2_NOTIFICATION.value,
            "description": "% incidentes NIS2 notificados dentro de 72h. NIS2 Art.23",
            "direction": "higher_is_better",
            "warning_threshold": 80.0,
            "breach_threshold": 60.0,
        },
        {
            "name": "Cobertura BCP aprobados (%)",
            "metric_type": KRIMetricType.KPI_BCP_COVERAGE.value,
            "description": "% planes de continuidad (BCP) en estado aprobado sobre el total. ISO 22301 / NIS2",
            "direction": "higher_is_better",
            "warning_threshold": 70.0,
            "breach_threshold": 50.0,
        },
        # NIST CSF 2.0 — Respond/Recover
        {
            "name": "MTTR de incidentes (dias)",
            "metric_type": KRIMetricType.KPI_MTTR_INCIDENTS.value,
            "description": "Tiempo medio de resolucion de incidentes en dias. NIST CSF 2.0 RS/RC",
            "direction": "lower_is_better",
            "warning_threshold": 14.0,
            "breach_threshold": 30.0,
        },
        # ISO 27036 / TPRM
        {
            "name": "Cobertura evaluacion proveedores Tier-1 (%)",
            "metric_type": KRIMetricType.KPI_SUPPLIER_COVERAGE.value,
            "description": "% proveedores tier-1 con cuestionario completado en los ultimos 12 meses. ISO 27036 / TPRM",
            "direction": "higher_is_better",
            "warning_threshold": 70.0,
            "breach_threshold": 50.0,
        },
        {
            "name": "Contratos proveedor expirando en 90 dias (%)",
            "metric_type": "kpi_supplier_contract_expiry",
            "description": "% proveedores tier-1/2 con contrato expirando en 90 dias. ISO 27036 §5",
            "direction": "lower_is_better",
            "warning_threshold": 20.0,
            "breach_threshold": 40.0,
        },
        {
            "name": "Issues criticos/altos de proveedores abiertos (#)",
            "metric_type": "kpi_supplier_critical_issues",
            "description": "Numero de VendorIssues con severidad CRITICAL o HIGH en estado abierto. TPRM §2.1",
            "direction": "lower_is_better",
            "warning_threshold": 3.0,
            "breach_threshold": 8.0,
        },
        {
            "name": "MTTR de issues de proveedor (dias)",
            "metric_type": "kpi_vendor_issue_mttr",
            "description": "Dias medios de resolucion de VendorIssues cerrados. ISO 27036",
            "direction": "lower_is_better",
            "warning_threshold": 45.0,
            "breach_threshold": 90.0,
        },
        {
            "name": "Proveedores DORA evaluados (%)",
            "metric_type": "kpi_dora_suppliers_assessed",
            "description": "% proveedores con is_dora=True que tienen assessment completado en 12 meses. DORA Art.28",
            "direction": "higher_is_better",
            "warning_threshold": 70.0,
            "breach_threshold": 50.0,
        },
        {
            "name": "RTO alcanzado en tests BCP (%)",
            "metric_type": "kpi_bcp_rto_achievement",
            "description": "% procesos con BCPTest donde rto_achieved_hours <= rto objetivo. ISO 22301 §9.1",
            "direction": "higher_is_better",
            "warning_threshold": 70.0,
            "breach_threshold": 50.0,
        },
        {
            "name": "Dias desde ultimo test BCP",
            "metric_type": "kpi_bcp_test_frequency",
            "description": "Numero de dias desde el ultimo BCPTest conducido. ISO 22301 §8.5 requiere test anual.",
            "direction": "lower_is_better",
            "warning_threshold": 270.0,
            "breach_threshold": 365.0,
        },
        {
            "name": "Procesos criticos con BCP aprobado (%)",
            "metric_type": "kpi_critical_processes_bcp",
            "description": "% BusinessProcess con criticality=critical que tienen BCPPlan en estado approved. ISO 22301 §8.4",
            "direction": "higher_is_better",
            "warning_threshold": 70.0,
            "breach_threshold": 50.0,
        },
    ]
    inserted = 0
    for kpi_def in _KPI_CATALOG:
        existing = db.query(KRI).filter(
            KRI.organization_id == org_id,
            KRI.metric_type == kpi_def["metric_type"],
            KRI.is_system == True,
        ).first()
        if existing:
            continue
        from datetime import datetime, timezone as _tz
        kpi = KRI(
            organization_id=org_id,
            risk_id=None,
            name=kpi_def["name"],
            metric_type=kpi_def["metric_type"],
            description=kpi_def.get("description"),
            direction=kpi_def.get("direction", "lower_is_better"),
            warning_threshold=kpi_def["warning_threshold"],
            breach_threshold=kpi_def["breach_threshold"],
            is_active=True,
            is_visible=True,
            is_system=True,
            indicator_type="kpi",
            alert_on_breach=True,
            created_at=datetime.now(_tz.utc),
        )
        db.add(kpi)
        inserted += 1
    if inserted:
        db.commit()
        print(f"Seed: {inserted} KPIs de sistema creados para org {org_id}.")


def _seed_default_kris(db: Session, org_id: int) -> None:
    """Siembra los KRIs de sistema por defecto (idempotente via is_system + metric_type)."""
    from app.models import KRI, KRIMetricType
    _KRI_CATALOG = [
        {
            "name": "Riesgos criticos activos",
            "metric_type": KRIMetricType.KRI_CRITICAL_RISKS.value,
            "description": "Numero de riesgos con nivel residual >= 4 que no estan cerrados ni aceptados. ISO 27005:2022 §8.4",
            "direction": "lower_is_better",
            "warning_threshold": 4.0,
            "breach_threshold": 8.0,
        },
        {
            "name": "Riesgos sin revisar (>90 dias)",
            "metric_type": KRIMetricType.KRI_STALE_RISKS.value,
            "description": "Numero de riesgos activos no actualizados en los ultimos 90 dias. ISO 27001:2022 cl.9.1",
            "direction": "lower_is_better",
            "warning_threshold": 5.0,
            "breach_threshold": 10.0,
        },
        {
            "name": "CVEs criticos/altos sin remediar",
            "metric_type": KRIMetricType.KRI_CRITICAL_CVES.value,
            "description": "Numero de hallazgos externos con CVE de severidad CRITICAL o HIGH en estado abierto. NIST CSF 2.0 ID.RA",
            "direction": "lower_is_better",
            "warning_threshold": 1.0,
            "breach_threshold": 3.0,
        },
        {
            "name": "Proveedores Tier-1/2 con riesgo alto",
            "metric_type": KRIMetricType.KRI_HIGH_RISK_SUPPLIERS.value,
            "description": "Numero de proveedores CRITICAL o HIGH tier con score residual > 70. ISO 27036 / NIS2 Art.21.2.d",
            "direction": "lower_is_better",
            "warning_threshold": 1.0,
            "breach_threshold": 2.0,
        },
    ]
    inserted = 0
    for kri_def in _KRI_CATALOG:
        existing = db.query(KRI).filter(
            KRI.organization_id == org_id,
            KRI.metric_type == kri_def["metric_type"],
            KRI.is_system == True,
        ).first()
        if existing:
            continue
        from datetime import datetime, timezone as _tz
        kri = KRI(
            organization_id=org_id,
            risk_id=None,
            name=kri_def["name"],
            metric_type=kri_def["metric_type"],
            description=kri_def.get("description"),
            direction=kri_def.get("direction", "lower_is_better"),
            warning_threshold=kri_def["warning_threshold"],
            breach_threshold=kri_def["breach_threshold"],
            is_active=True,
            is_visible=True,
            is_system=True,
            indicator_type="kri",
            alert_on_breach=True,
            created_at=datetime.now(_tz.utc),
        )
        db.add(kri)
        inserted += 1
    if inserted:
        db.commit()
        print(f"Seed: {inserted} KRIs de sistema creados para org {org_id}.")


def init_db() -> None:
    """Crear tablas y cargar seed inicial."""
    Base.metadata.create_all(bind=engine)
    _migrate_columns()
    _create_fts5_table()
    _ensure_doc_dir()
    db = SessionLocal()
    try:
        org = seed_organization(db)
        seed_admin(db)
        seed_context(db)
        seed_threats(db)
        seed_vulnerabilities(db)
        seed_controls(db)
        _seed_feature_flags(db)
        _seed_licenses(db)
        seed_default_survey_templates(db, org.id)
        _seed_regwatch_sources(db)
        _backfill_risk_supplier_id(db)
        _seed_default_kpis(db, org.id)
        _seed_default_kris(db, org.id)
        _run_one_shot_recalc_v2(db)
    finally:
        db.close()


def _run_one_shot_recalc_v2(db: Session) -> None:
    """Recalcula todos los residuales con el motor v2 (P/D/C + madurez ajustada).

    Se ejecuta una sola vez tras el despliegue del motor v2; queda registrado
    en app_migrations para no repetirse en arranques posteriores.
    """
    from datetime import datetime, timezone
    from sqlalchemy import text as _text
    marker = "residual_engine_v2_recalc"
    try:
        row = db.execute(
            _text("SELECT name FROM app_migrations WHERE name = :n"), {"n": marker}
        ).fetchone()
        if row:
            return
        from app.models import Risk
        from app.services.risk_recalc_service import recalc_risk
        risks = db.query(Risk).all()
        errors = 0
        for r in risks:
            try:
                recalc_risk(db, r)
            except Exception:
                errors += 1
        db.execute(
            _text("INSERT INTO app_migrations (name, applied_at) VALUES (:n, :ts)"),
            {"n": marker, "ts": datetime.now(timezone.utc).isoformat()},
        )
        db.commit()
        print(f"Motor v2: {len(risks)} riesgos recalculados ({errors} errores).")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Recalculo v2 omitido: {exc}")


def _seed_regwatch_sources(db: Session) -> None:
    """Siembra el catalogo de fuentes de vigilancia normativa (regwatch §3.1)."""
    try:
        from app.services.regwatch_service import seed_sources
        n = seed_sources(db)
        if n:
            print(f"Regwatch: {n} fuentes normativas sembradas.")
    except Exception as exc:  # noqa: BLE001
        print(f"Regwatch seed omitido: {exc}")


def _seed_feature_flags(db: Session) -> None:
    """Crea los feature flags por defecto si no existen."""
    try:
        from app.routers.feature_flags import seed_default_flags
        seed_default_flags(db)
    except Exception:
        pass  # silencioso si la tabla aun no existe


if __name__ == "__main__":
    init_db()
    print("Base de datos inicializada.")
