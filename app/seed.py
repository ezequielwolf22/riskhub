"""Carga inicial de datos: admin, catalogos ISO 27005/27002, contexto, organizacion."""
import json
from pathlib import Path

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
        else:
            db.add(Threat(
                code=t["code"], name=t["name"], description=t.get("description"),
                category=t.get("category"),
                origin=ThreatOrigin(t["origin"]),
                typical_assets=t.get("typical_assets", []),
                affects=t.get("affects", []),
                is_custom=False,
            ))
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
        # v1.7.4 — analisis ISMS automatico
        ("ALTER TABLE ai_documents ADD COLUMN isms_status VARCHAR(32)", "ai_documents", "isms_status"),
        ("ALTER TABLE ai_documents ADD COLUMN isms_summary JSON", "ai_documents", "isms_summary"),
        ("ALTER TABLE policies ADD COLUMN source_document_id INTEGER REFERENCES ai_documents(id)", "policies", "source_document_id"),
        ("ALTER TABLE policies ADD COLUMN review_cycle_months INTEGER", "policies", "review_cycle_months"),
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
            except Exception:
                pass  # columna ya existe o tabla no existe aun


def init_db() -> None:
    """Crear tablas y cargar seed inicial."""
    Base.metadata.create_all(bind=engine)
    _migrate_columns()
    _create_fts5_table()
    _ensure_doc_dir()
    db = SessionLocal()
    try:
        seed_organization(db)
        seed_admin(db)
        seed_context(db)
        seed_threats(db)
        seed_vulnerabilities(db)
        seed_controls(db)
        _seed_feature_flags(db)
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
