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
    SUPERADMIN = "superadmin"   # por encima de admin — gestiona licencias y feature flags
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


class IntegrationConfig(Base):
    """Configuracion de integraciones externas (credenciales cifradas)."""
    __tablename__ = "integration_configs"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False, index=True)  # ej: "sharepoint", "sap"
    config_encrypted = Column(Text, nullable=True)   # JSON cifrado con Fernet
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = relationship("User")


class FeatureFlag(Base):
    """Control de modulos por licencia — gestionado exclusivamente por superadmin."""
    __tablename__ = "feature_flags"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    label = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = relationship("User")


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
    monetary_value = Column(Float, nullable=True)  # EUR — para calculo FAIR/ALE

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
    # Campos SOA ISO 27001:2022 cl. 6.1.3
    inclusion_reason = Column(String(64), nullable=True)   # legal|contractual|risk|best_practice
    exclusion_justification = Column(Text, nullable=True)  # si el control no aplica
    evidence_refs = Column(JSON, nullable=True)            # [{title, url}]
    soa_reviewed_at = Column(DateTime, nullable=True)
    soa_reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    control = relationship("Control")
    owner = relationship("User", foreign_keys=[owner_id])
    soa_reviewed_by = relationship("User", foreign_keys=[soa_reviewed_by_id])


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
    last_review_notified_at = Column(DateTime, nullable=True)  # dedup emails de revision

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


# ---------- INCIDENTES DE SEGURIDAD (NIS2 Art. 23) ----------

class IncidentSeverity(str, PyEnum):
    P1 = "p1"   # Critico
    P2 = "p2"   # Alto
    P3 = "p3"   # Medio
    P4 = "p4"   # Bajo


class IncidentStatus(str, PyEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Incident(Base):
    """Incidente de seguridad con flujo NIS2 Art. 23 (24h/72h/1 mes)."""
    __tablename__ = "incidents"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    severity = Column(Enum(IncidentSeverity), nullable=False, default=IncidentSeverity.P3)
    status = Column(Enum(IncidentStatus), default=IncidentStatus.OPEN)
    detected_at = Column(DateTime, nullable=True)
    contained_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    nis2_notification_required = Column(Boolean, default=False)
    nis2_notification_sent_at = Column(DateTime, nullable=True)
    gdpr_notification_required = Column(Boolean, default=False)
    affected_asset_ids = Column(JSON)      # [asset_id, ...]
    affected_systems = Column(JSON)        # [system_name, ...]
    related_risk_ids = Column(JSON)        # [risk_id, ...]
    root_cause = Column(Text)
    response_actions = Column(Text)
    lessons_learned = Column(Text)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    owner = relationship("User")


# ---------- PROVEEDORES / SUPPLY CHAIN (NIS2 Art. 21.2.d) ----------

class SupplierRisk(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Supplier(Base):
    """Proveedor / tercero con evaluacion de riesgo de cadena de suministro."""
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    services = Column(Text)               # servicios que presta
    category = Column(String(128), nullable=True)
    is_critical = Column(Boolean, default=False)
    risk_level = Column(Enum(SupplierRisk), default=SupplierRisk.MEDIUM)
    certifications = Column(JSON)         # ["ISO27001","SOC2",...]
    contact_name = Column(String(255))
    contact_email = Column(String(255))
    contract_ref = Column(String(255), nullable=True)
    contract_expiry = Column(DateTime, nullable=True)
    last_assessment_at = Column(DateTime, nullable=True)
    next_assessment_at = Column(DateTime, nullable=True)
    score = Column(Integer, default=50)   # 0-100
    notes = Column(Text)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    owner = relationship("User")


# ---------- NO CONFORMIDADES / ACCIONES CORRECTIVAS (ISO 27001 cl. 10.1) ----------

class NCSeverity(str, PyEnum):
    OBSERVATION = "observation"
    MINOR = "minor"
    MAJOR = "major"


class NCStatus(str, PyEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PENDING_VERIFICATION = "pending_verification"
    CLOSED = "closed"


class NonConformity(Base):
    """No conformidad / accion correctiva — ISO 27001 cl. 10.1."""
    __tablename__ = "nonconformities"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    source = Column(String(64))           # internal_audit|external_audit|incident|self_assessment
    severity = Column(Enum(NCSeverity), default=NCSeverity.MINOR)
    status = Column(Enum(NCStatus), default=NCStatus.OPEN)
    iso_clause = Column(String(64))       # ej. "6.1.2", "9.1"
    root_cause = Column(Text)
    corrective_action = Column(Text)
    due_date = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    evidence = Column(Text)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    verifier_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    related_control_id = Column(Integer, ForeignKey("controls.id"), nullable=True)
    related_risk_id = Column(Integer, ForeignKey("risks.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    owner = relationship("User", foreign_keys=[owner_id])
    verifier = relationship("User", foreign_keys=[verifier_id])
    related_control = relationship("Control", foreign_keys=[related_control_id])
    related_risk = relationship("Risk", foreign_keys=[related_risk_id])


# ---------- PLAN DE TRATAMIENTO — TAREAS (M3) ----------

class TaskStatus(str, PyEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


class TaskPriority(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TreatmentTask(Base):
    """Tarea de plan de tratamiento asociada a un riesgo (opcional)."""
    __tablename__ = "treatment_tasks"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)   # TSK-0001
    title = Column(String(255), nullable=False)
    description = Column(Text)
    risk_id = Column(Integer, ForeignKey("risks.id"), nullable=True)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    priority = Column(Enum(TaskPriority), default=TaskPriority.MEDIUM)
    due_date = Column(DateTime, nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    risk = relationship("Risk")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
    created_by = relationship("User", foreign_keys=[created_by_id])


# ---------- POLITICAS (M2) ----------

class PolicyStatus(str, PyEnum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"
    OBSOLETE = "obsolete"


class Policy(Base):
    """Politica de seguridad de la informacion — ISO 27001 cl. 5.2."""
    __tablename__ = "policies"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)   # POL-0001
    title = Column(String(255), nullable=False)
    version = Column(String(32), default="1.0")
    category = Column(String(128))              # Seguridad fisica, Uso aceptable, Gestion incidentes...
    status = Column(Enum(PolicyStatus), default=PolicyStatus.DRAFT)
    scope = Column(Text)
    content = Column(Text)
    iso_clauses = Column(JSON)                  # ["5.2","6.1","A.5.1"]
    review_date = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    owner = relationship("User", foreign_keys=[owner_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])


# ---------- AUDITORIA INTERNA (M5) ----------

class AuditType(str, PyEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"
    SURVEILLANCE = "surveillance"
    RECERTIFICATION = "recertification"


class AuditStatus(str, PyEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AuditFindingType(str, PyEnum):
    MAJOR_NC = "major_nc"
    MINOR_NC = "minor_nc"
    OBSERVATION = "observation"
    OPPORTUNITY = "opportunity"
    CONFORMITY = "conformity"


class AuditProgram(Base):
    """Programa de auditoria interna — ISO 27001 cl. 9.2."""
    __tablename__ = "audit_programs"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)   # AUD-0001
    title = Column(String(255), nullable=False)
    audit_type = Column(Enum(AuditType), default=AuditType.INTERNAL)
    status = Column(Enum(AuditStatus), default=AuditStatus.PLANNED)
    scope = Column(Text)
    objectives = Column(Text)
    criteria = Column(Text)                     # normas o requisitos auditados
    auditor_lead = Column(String(255))
    auditor_team = Column(JSON)                 # [nombre, ...]
    planned_start = Column(DateTime, nullable=True)
    planned_end = Column(DateTime, nullable=True)
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)
    conclusion = Column(Text)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    owner = relationship("User")
    findings = relationship("AuditFinding", back_populates="audit", cascade="all, delete-orphan")


class AuditFinding(Base):
    """Hallazgo de auditoria — puede generar una NonConformity."""
    __tablename__ = "audit_findings"
    id = Column(Integer, primary_key=True)
    audit_id = Column(Integer, ForeignKey("audit_programs.id"), nullable=False)
    finding_type = Column(Enum(AuditFindingType), default=AuditFindingType.MINOR_NC)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    evidence = Column(Text)
    iso_clause = Column(String(64))             # clausula o control auditado
    recommendation = Column(Text)
    nonconformity_id = Column(Integer, ForeignKey("nonconformities.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    audit = relationship("AuditProgram", back_populates="findings")
    nonconformity = relationship("NonConformity")


# ---------- EVALUACION DE PROVEEDORES - CUESTIONARIO (M4) ----------

class SupplierQuestionnaire(Base):
    """Cuestionario de evaluacion de seguridad enviado al proveedor."""
    __tablename__ = "supplier_questionnaires"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)   # SEQ-0001
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    title = Column(String(255), nullable=False)
    token = Column(String(64), unique=True, nullable=False)  # acceso publico
    questions = Column(JSON)                 # [{id, text, type}]
    answers = Column(JSON, nullable=True)    # {question_id: answer}
    score = Column(Integer, nullable=True)   # 0-100
    submitted_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    notes = Column(Text)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    supplier = relationship("Supplier")
    created_by = relationship("User")

    @property
    def supplier_name(self) -> str:
        return self.supplier.name if self.supplier else ""


# ---------- GDPR / DPIA (M6) ----------

class ProcessingLegalBasis(str, PyEnum):
    CONSENT = "consent"
    CONTRACT = "contract"
    LEGAL_OBLIGATION = "legal_obligation"
    VITAL_INTERESTS = "vital_interests"
    PUBLIC_TASK = "public_task"
    LEGITIMATE_INTERESTS = "legitimate_interests"


class DPIAStatus(str, PyEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    APPROVED = "approved"


class ProcessingActivity(Base):
    """Registro de actividades de tratamiento — GDPR Art. 30."""
    __tablename__ = "processing_activities"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)   # PAR-0001
    title = Column(String(255), nullable=False)
    purposes = Column(Text)                                  # finalidades del tratamiento
    legal_basis = Column(Enum(ProcessingLegalBasis), default=ProcessingLegalBasis.LEGITIMATE_INTERESTS)
    data_categories = Column(JSON)                           # ["nombre","email","datos_salud",...]
    data_subjects = Column(JSON)                             # ["empleados","clientes",...]
    recipients = Column(JSON)                                # ["nombre del destinatario",...]
    transfers_outside_eu = Column(Boolean, default=False)
    transfer_safeguards = Column(Text)
    retention_period = Column(String(255))
    security_measures = Column(Text)
    controller_name = Column(String(255))
    dpo_contact = Column(String(255))
    requires_dpia = Column(Boolean, default=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    owner = relationship("User")
    dpias = relationship("DPIA", back_populates="activity", cascade="all, delete-orphan")


class DPIA(Base):
    """Evaluacion de Impacto en la Proteccion de Datos — GDPR Art. 35."""
    __tablename__ = "dpias"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)   # DPI-0001
    activity_id = Column(Integer, ForeignKey("processing_activities.id"), nullable=False)
    title = Column(String(255), nullable=False)
    status = Column(Enum(DPIAStatus), default=DPIAStatus.PENDING)
    necessity_assessment = Column(Text)                      # necesidad y proporcionalidad
    risks_identified = Column(Text)                          # riesgos identificados
    risk_measures = Column(Text)                             # medidas para mitigarlos
    residual_risk_level = Column(Integer, default=0)         # 0..8
    dpo_opinion = Column(Text)
    reviewed_at = Column(DateTime, nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    activity = relationship("ProcessingActivity", back_populates="dpias")
    owner = relationship("User", foreign_keys=[owner_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])


# ---------- AGENTE IA (v1.3) ----------

class AiDocumentCategory(str, PyEnum):
    ARCHITECTURE = "architecture"
    NORMATIVE = "normative"
    POLICIES = "policies"
    ASSETS_INVENTORY = "assets_inventory"
    RISK_ASSESSMENTS = "risk_assessments"
    CRITICAL_SUPPLIERS = "critical_suppliers"
    INCIDENTS_LESSONS = "incidents_lessons"
    OTHER = "other"


class AiDocumentStatus(str, PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    ERROR = "error"


class AiAnonymizationLevel(str, PyEnum):
    LOW = "low"       # IPs + emails
    MEDIUM = "medium"  # + dominios
    HIGH = "high"     # + nombres + org


class AiConfig(Base):
    """Configuracion del agente IA — una fila por organizacion."""
    __tablename__ = "ai_config"
    id = Column(Integer, primary_key=True)
    api_key_encrypted = Column(Text, nullable=True)   # Fernet-encrypted
    model = Column(String(64), default="claude-opus-4-5")
    anonymization_level = Column(Enum(AiAnonymizationLevel), default=AiAnonymizationLevel.MEDIUM)
    setup_completed = Column(Boolean, default=False)
    org_sector = Column(String(128), nullable=True)
    org_size = Column(String(64), nullable=True)
    org_critical_processes = Column(Text, nullable=True)
    org_tech_stack = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class AiDocument(Base):
    """Documento subido para alimentar el agente IA."""
    __tablename__ = "ai_documents"
    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    original_name = Column(String(255), nullable=False)
    category = Column(Enum(AiDocumentCategory), nullable=False)
    status = Column(Enum(AiDocumentStatus), default=AiDocumentStatus.PENDING)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(128), nullable=True)
    chunk_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime, nullable=True)

    uploaded_by = relationship("User")
    chunks = relationship("AiDocumentChunk", back_populates="document",
                          cascade="all, delete-orphan")


class AiDocumentChunk(Base):
    """Fragmento de texto indexado en FTS5."""
    __tablename__ = "ai_document_chunks"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("ai_documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)

    document = relationship("AiDocument", back_populates="chunks")


class AiCallLog(Base):
    """Log de llamadas a la API de IA."""
    __tablename__ = "ai_call_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    call_type = Column(String(64), nullable=False)   # risk_suggest|control_gap|chat
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    model = Column(String(64), nullable=True)
    anonymized = Column(Boolean, default=False)
    response_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")


class AiFeedback(Base):
    """Valoracion del usuario sobre una respuesta del agente."""
    __tablename__ = "ai_feedback"
    id = Column(Integer, primary_key=True)
    call_log_id = Column(Integer, ForeignKey("ai_call_logs.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    rating = Column(Integer, nullable=False)   # 1..5
    comment = Column(Text, nullable=True)
    call_type = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    call_log = relationship("AiCallLog")
    user = relationship("User")


# ---------- OSINT (huella-digital integration) ----------

class OSINTScanType(str, PyEnum):
    EMAIL = "email"
    DOMAIN = "domain"
    URL = "url"
    USERNAME = "username"
    IP = "ip"


class OSINTSourceType(str, PyEnum):
    HIBP = "hibp"                    # Have I Been Pwned
    VIRUSTOTAL = "virustotal"        # VirusTotal
    LEAKCHECK = "leakcheck"          # LeakCheck
    INTELX = "intelx"                # Intelligence X
    GITHUB = "github"                # GitHub Recon
    SOCIAL = "social"                # Social Media Scraping


class OSINTFindingRiskLevel(str, PyEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class OSINTScan(Base):
    """Escaneo OSINT iniciado por un usuario."""
    __tablename__ = "osint_scans"
    id = Column(Integer, primary_key=True)
    scan_type = Column(Enum(OSINTScanType), nullable=False)
    target = Column(String(255), nullable=False)  # email, domain, URL, username
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(32), default="pending")  # pending, in_progress, completed, failed
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    findings_count = Column(Integer, default=0)
    risk_score = Column(Float, default=0.0)  # agregado de todos los hallazgos

    user = relationship("User")
    findings = relationship("OSINTFinding", back_populates="scan", cascade="all, delete-orphan")


class OSINTIdentifier(Base):
    """Identificador OSINT monitorizado (email, username, etc.)."""
    __tablename__ = "osint_identifiers"
    id = Column(Integer, primary_key=True)
    identifier_type = Column(Enum(OSINTScanType), nullable=False)
    value = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_monitored = Column(Boolean, default=True)
    last_scanned_at = Column(DateTime, nullable=True)
    risk_level = Column(Enum(OSINTFindingRiskLevel), default=OSINTFindingRiskLevel.INFO)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User")
    __table_args__ = (UniqueConstraint('user_id', 'identifier_type', 'value'),)


class OSINTFinding(Base):
    """Hallazgo OSINT — resultado del escaneo."""
    __tablename__ = "osint_findings"
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey("osint_scans.id"), nullable=False)
    identifier_id = Column(Integer, ForeignKey("osint_identifiers.id"), nullable=True)
    source = Column(Enum(OSINTSourceType), nullable=False)
    finding_type = Column(String(64), nullable=False)  # data_breach, exposed_password, url_malware, etc.
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    risk_level = Column(Enum(OSINTFindingRiskLevel), default=OSINTFindingRiskLevel.MEDIUM)
    risk_score = Column(Float, default=0.0)  # 0..100
    is_remediated = Column(Boolean, default=False)
    remediated_at = Column(DateTime, nullable=True)
    extra_data = Column(JSON, nullable=True)  # información adicional de la fuente
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    scan = relationship("OSINTScan", back_populates="findings")
    identifier = relationship("OSINTIdentifier")
    linked_vulnerabilities = relationship("Vulnerability",
                                          secondary="osint_vulnerability_links",
                                          viewonly=True)


osint_vulnerability_links = Table(
    'osint_vulnerability_links',
    Base.metadata,
    Column('osint_finding_id', Integer, ForeignKey('osint_findings.id'), primary_key=True),
    Column('vulnerability_id', Integer, ForeignKey('vulnerabilities.id'), primary_key=True)
)


class OSINTAPIKey(Base):
    """Claves de API para servicios OSINT."""
    __tablename__ = "osint_api_keys"
    id = Column(Integer, primary_key=True)
    service = Column(Enum(OSINTSourceType), unique=True, nullable=False)
    api_key_encrypted = Column(Text, nullable=False)  # Fernet-encrypted
    is_valid = Column(Boolean, default=False)
    last_check_at = Column(DateTime, nullable=True)
    rate_limit_remaining = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


# ---------- AWARENESS (Infografias de seguridad) ----------

class AwarenessItem(Base):
    """Infografia de concienciacion generada por IA o editada manualmente."""
    __tablename__ = "awareness_items"
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    template_type = Column(String(64), default="risk_alert")
    # risk_alert | best_practices | policy | threat | phishing
    content_json = Column(Text, nullable=False)  # JSON serializado
    status = Column(String(32), default="draft")  # draft | published
    tags = Column(JSON)  # lista de etiquetas
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    created_by = relationship("User", foreign_keys=[created_by_id])


class AwarenessBranding(Base):
    """Configuracion de marca para las infografias de awareness."""
    __tablename__ = "awareness_branding"
    id = Column(Integer, primary_key=True)
    primary_color = Column(String(7), default="#59008D")
    secondary_color = Column(String(7), default="#D65200")
    logo_filename = Column(String(255))   # archivo almacenado en /srv/data/branding/
    logo_mime = Column(String(64))
    company_name = Column(String(255))
    updated_at = Column(DateTime)
    updated_by_id = Column(Integer, ForeignKey("users.id"))

    updated_by = relationship("User", foreign_keys=[updated_by_id])
