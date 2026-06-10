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
    with open(DATA_DIR / name, "r", encoding="utf-8") as f:
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
    """Crea la tabla FTS5 para busqueda de chunks de documentos IA."""
    with engine.connect() as conn:
        try:
            conn.execute(__import__("sqlalchemy").text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS ai_chunks_fts "
                "USING fts5(content, tokenize='unicode61 remove_diacritics 1')"
            ))
            conn.commit()
        except Exception:
            pass  # SQLite sin soporte FTS5 (entorno de test)


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
    finally:
        db.close()


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
