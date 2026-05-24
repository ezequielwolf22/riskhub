"""Carga inicial de datos: admin, catalogos ISO 27005/27002, contexto."""
import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import (
    Control, RiskContext, Threat, ThreatOrigin, User, UserRole, Vulnerability,
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


def seed_admin(db: Session) -> None:
    if db.query(User).count() > 0:
        return
    admin = User(
        email=settings.admin_email,
        full_name="Administrator",
        hashed_password=hash_password(settings.admin_password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(admin)
    db.commit()


def seed_context(db: Session) -> None:
    if db.query(RiskContext).count() > 0:
        return
    ctx = RiskContext(
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


def _migrate_columns() -> None:
    """Agrega columnas nuevas a tablas existentes (SQLite no soporta ALTER TABLE con IF NOT EXISTS en todas las versiones)."""
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
    db = SessionLocal()
    try:
        seed_admin(db)
        seed_context(db)
        seed_threats(db)
        seed_vulnerabilities(db)
        seed_controls(db)
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    print("Base de datos inicializada.")
