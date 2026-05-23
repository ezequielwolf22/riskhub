"""Modelos del dominio - alineados con ISO/IEC 27005:2018.

Terminologia oficial usada:
 - Risk identification (Activos, Amenazas, Vulnerabilidades, Controles existentes)
 - Risk analysis (Likelihood x Consequence -> Risk level)
 - Risk evaluation (comparar contra criterios)
 - Risk treatment (modification / retention / avoidance / sharing)
 - Risk acceptance
 - Risk monitoring & review
"""
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer,
    JSON, String, Table, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ---------- ENUMERACIONES ----------

class UserRole(str, PyEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class AssetType(str, PyEnum):
    """ISO 27005 B.1 - Primary vs Supporting assets."""
    PRIMARY_PROCESS = "primary_process"
    PRIMARY_INFORMATION = "primary_information"
    SUPPORT_HARDWARE = "support_hardware"
    SUPPORT_SOFTWARE = "support_software"
    SUPPORT_NETWORK = "support_network"
    SUPPORT_PERSONNEL = "support_personnel"
    SUPPORT_SITE = "support_site"
    SUPPORT_ORGANIZATION = "support_organization"


class ThreatOrigin(str, PyEnum):
    """ISO 27005 Annex C - D/A/E."""
    DELIBERATE = "D"
    ACCIDENTAL = "A"
    ENVIRONMENTAL = "E"


class TreatmentOption(str, PyEnum):
    """ISO 27005 9.2-9.5."""
    MODIFICATION = "modification"   # mitigar
    RETENTION = "retention"         # aceptar
    AVOIDANCE = "avoidance"         # evitar
    SHARING = "sharing"             # transferir/compartir


class RiskStatus(str, PyEnum):
    IDENTIFIED = "identified"
    ASSESSED = "assessed"
    TREATED = "treated"
    ACCEPTED = "accepted"
    CLOSED = "closed"


class ControlStatus(str, PyEnum):
    PLANNED = "planned"
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    NOT_IMPLEMENTED = "not_implemented"


# ---------- USUARIOS ----------

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.VIEWER)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(64), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(64), nullable=True)
    detail = Column(JSON, nullable=True)
    user = relationship("User")


# ---------- CONTEXTO ----------

class RiskContext(Base):
    """ISO 27005 cl. 7 - Context establishment (single row)."""
    __tablename__ = "risk_context"
    id = Column(Integer, primary_key=True)
    organization_name = Column(String(255), default="Organization")
    scope = Column(Text)
    boundaries = Column(Text)
    impact_criteria = Column(JSON)         # niveles y descripciones
    likelihood_criteria = Column(JSON)
    risk_acceptance_criteria = Column(JSON)
    risk_matrix = Column(JSON)             # matriz 5x5 ISO 27005 Annex E.2
    risk_appetite = Column(Integer, default=3)  # nivel 0..8 maximo aceptable
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


# ---------- ASSETS ----------

asset_owner_table = Table(
    "asset_owners", Base.metadata,
    Column("asset_id", ForeignKey("assets.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
)


class Asset(Base):
    """ISO 27005 8.2.2 + Annex B."""
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)  # ej. AST-0001
    name = Column(String(255), nullable=False)
    description = Column(Text)
    asset_type = Column(Enum(AssetType), nullable=False)
    category = Column(String(128))            # libre, ej. "ERP", "Building 1"
    location = Column(String(255))
    business_process = Column(String(255))
    classification = Column(String(64))       # publico/interno/confidencial/secreto

    # Valoracion CIA (ISO 27005 B.2 - escala 0..4)
    value_confidentiality = Column(Integer, default=0)
    value_integrity = Column(Integer, default=0)
    value_availability = Column(Integer, default=0)
    value_authenticity = Column(Integer, default=0)
    value_accountability = Column(Integer, default=0)

    parent_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    parent = relationship("Asset", remote_side=[id], backref="dependents")

    owners = relationship("User", secondary=asset_owner_table)
    extra = Column(JSON)  # campos personalizados de cada organizacion

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    risks = relationship("Risk", back_populates="asset", cascade="all, delete-orphan")

    @property
    def value_max(self) -> int:
        return max(
            self.value_confidentiality or 0,
            self.value_integrity or 0,
            self.value_availability or 0,
            self.value_authenticity or 0,
            self.value_accountability or 0,
        )


# ---------- AMENAZAS / VULNERABILIDADES (catalogo + instancias) ----------

class Threat(Base):
    """Catalogo de amenazas - ISO 27005 Annex C."""
    __tablename__ = "threats"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(128))    # ej. "Physical damage"
    origin = Column(Enum(ThreatOrigin), nullable=False)
    typical_assets = Column(JSON)     # tipos de activo a los que aplica
    affects = Column(JSON)            # ["C","I","A","Auth","Acc"]
    is_custom = Column(Boolean, default=False)


class Vulnerability(Base):
    """Catalogo de vulnerabilidades - ISO 27005 Annex D."""
    __tablename__ = "vulnerabilities"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(128))    # hardware/software/network/personnel/site/organization
    related_threats = Column(JSON)    # codigos de amenazas relacionadas
    is_custom = Column(Boolean, default=False)


# ---------- CONTROLES (ISO 27002:2022) ----------

class Control(Base):
    """Catalogo ISO 27002:2022 + controles personalizados."""
    __tablename__ = "controls"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)  # 5.1, 8.23...
    name = Column(String(255), nullable=False)
    description = Column(Text)
    theme = Column(String(64))     # organizational/people/physical/technological
    control_type = Column(JSON)    # preventive/detective/corrective
    properties = Column(JSON)      # confidentiality/integrity/availability
    cybersec_concepts = Column(JSON)   # identify/protect/detect/respond/recover
    operational = Column(JSON)
    is_custom = Column(Boolean, default=False)


class ControlImplementation(Base):
    """Implementacion concreta del control en la organizacion."""
    __tablename__ = "control_implementations"
    id = Column(Integer, primary_key=True)
    control_id = Column(Integer, ForeignKey("controls.id"), nullable=False)
    name = Column(String(255), nullable=False)    # nombre interno
    description = Column(Text)
    status = Column(Enum(ControlStatus), default=ControlStatus.NOT_IMPLEMENTED)
    maturity = Column(Integer, default=0)         # 0..5 (CMM)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    evidence = Column(Text)
    last_review = Column(DateTime, nullable=True)
    next_review = Column(DateTime, nullable=True)
    notes = Column(Text)

    control = relationship("Control")
    owner = relationship("User")


# ---------- RIESGOS ----------

risk_vulnerability_table = Table(
    "risk_vulnerabilities", Base.metadata,
    Column("risk_id", ForeignKey("risks.id"), primary_key=True),
    Column("vulnerability_id", ForeignKey("vulnerabilities.id"), primary_key=True),
)

risk_control_table = Table(
    "risk_controls", Base.metadata,
    Column("risk_id", ForeignKey("risks.id"), primary_key=True),
    Column("control_implementation_id", ForeignKey("control_implementations.id"),
           primary_key=True),
    Column("contribution", Float, default=1.0),  # 0..1 cuanto reduce el control
)


class Risk(Base):
    """Riesgo = combinacion activo x amenaza (ISO 27005 8.3).

    Sigue el modelo de matriz 5x5 del Annex E.2 (escala 0..8).
    """
    __tablename__ = "risks"
    __table_args__ = (UniqueConstraint("asset_id", "threat_id", name="uq_asset_threat"),)

    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)  # RSK-0001

    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    threat_id = Column(Integer, ForeignKey("threats.id"), nullable=False)
    description = Column(Text)

    # Risk identification
    consequence_description = Column(Text)

    # Risk analysis - INHERENTE (sin controles)
    inherent_likelihood = Column(Integer, default=0)    # 0..4
    inherent_consequence = Column(Integer, default=0)   # 0..4
    inherent_level = Column(Integer, default=0)          # 0..8 (segun matriz)

    # RESIDUAL (tras controles)
    residual_likelihood = Column(Integer, default=0)
    residual_consequence = Column(Integer, default=0)
    residual_level = Column(Integer, default=0)

    status = Column(Enum(RiskStatus), default=RiskStatus.IDENTIFIED)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Treatment
    treatment_option = Column(Enum(TreatmentOption), nullable=True)
    treatment_plan = Column(Text)
    treatment_due_date = Column(DateTime, nullable=True)
    accepted_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    acceptance_justification = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    next_review = Column(DateTime, nullable=True)

    asset = relationship("Asset", back_populates="risks")
    threat = relationship("Threat")
    owner = relationship("User", foreign_keys=[owner_id])
    accepted_by = relationship("User", foreign_keys=[accepted_by_id])
    vulnerabilities = relationship("Vulnerability", secondary=risk_vulnerability_table)
    controls = relationship("ControlImplementation", secondary=risk_control_table)


class Questionnaire(Base):
    """Cuestionarios para semiautomatizar el cruce activo x amenaza."""
    __tablename__ = "questionnaires"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    questions = Column(JSON)   # estructura ver schemas.QuestionnaireSchema
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class QuestionnaireResponse(Base):
    __tablename__ = "questionnaire_responses"
    id = Column(Integer, primary_key=True)
    questionnaire_id = Column(Integer, ForeignKey("questionnaires.id"))
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    respondent_id = Column(Integer, ForeignKey("users.id"))
    answers = Column(JSON)
    generated_risks = Column(JSON)  # listas de RSK creados
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    questionnaire = relationship("Questionnaire")
    asset = relationship("Asset")
    respondent = relationship("User")


# ---------- ALERTAS Y EMAIL ----------

class EmailSettings(Base):
    """Configuracion SMTP para envio de alertas por correo."""
    __tablename__ = "email_settings"
    id = Column(Integer, primary_key=True)
    smtp_host = Column(String(255), default="")
    smtp_port = Column(Integer, default=587)
    smtp_user = Column(String(255), default="")
    smtp_password = Column(String(255), default="")
    smtp_from = Column(String(255), default="")
    smtp_use_tls = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class AlertRule(Base):
    """Regla de alerta: cuando se cumple el criterio, envia email al destinatario."""
    __tablename__ = "alert_rules"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    # Tipos: risk_high, risk_critical, treatment_overdue, risk_no_treatment
    event_type = Column(String(64), nullable=False)
    recipient_email = Column(String(255), nullable=False)
    threshold_level = Column(Integer, default=5)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_triggered_at = Column(DateTime, nullable=True)
