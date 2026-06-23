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
    PENDING_ACCEPTANCE = "pending_acceptance"   # esperando aprobacion formal del risk owner
    ACCEPTED = "accepted"
    CLOSED = "closed"


class ControlStatus(str, PyEnum):
    PLANNED = "planned"
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    NOT_IMPLEMENTED = "not_implemented"


class AssetGroupStatus(str, PyEnum):
    PROPOSED = "proposed"
    VALIDATED = "validated"
    REJECTED = "rejected"


# ---------- ORGANIZACIONES (multi-tenancy) ----------

class Organization(Base):
    """Tenant / cliente — unidad de aislamiento de datos."""
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    domain = Column(String(255), nullable=True, index=True)  # dominio email para auto-asignacion
    plan = Column(String(64), default="starter")             # free/starter/pro/enterprise
    is_active = Column(Boolean, default=True)
    max_users = Column(Integer, default=10)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # owner_id se rellena despues de crear el primer admin
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner = relationship("User", foreign_keys="Organization.owner_id")
    # MFA obligatorio para todos los usuarios de la org (v1.8)
    mfa_required = Column(Boolean, default=False)


class LicenseStatus(str, PyEnum):
    """Estados de una licencia."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"


class License(Base):
    """Licencia de una organizacion — gestion de planes y vencimiento."""
    __tablename__ = "licenses"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), unique=True, nullable=False, index=True)
    plan = Column(String(64), nullable=False)  # free/starter/pro/enterprise
    status = Column(Enum(LicenseStatus), default=LicenseStatus.ACTIVE, nullable=False)
    issued_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=True)  # NULL = sin límite (pago anual/indefinido)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    # Para auditoría
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = relationship("User", foreign_keys="License.updated_by_id")
    organization = relationship("Organization", foreign_keys="License.organization_id")


class LicenseAudit(Base):
    """Registro de cambios en licencias — trazabilidad completa."""
    __tablename__ = "license_audits"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    changed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    plan_old = Column(String(64), nullable=True)
    plan_new = Column(String(64), nullable=True)
    status_old = Column(String(64), nullable=True)
    status_new = Column(String(64), nullable=True)
    expires_at_old = Column(DateTime, nullable=True)
    expires_at_new = Column(DateTime, nullable=True)
    reason = Column(String(255), nullable=True)  # "expiration_auto", "manual_suspension", "plan_upgrade", etc
    changed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    changed_by = relationship("User", foreign_keys="LicenseAudit.changed_by_id")


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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    organization = relationship("Organization", foreign_keys="User.organization_id")
    # OTP primer login (v1.8)
    must_change_password = Column(Boolean, default=False)
    # MFA/TOTP (v1.8) — secret cifrado con Fernet
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String(255), nullable=True)
    # Codigos de recuperacion MFA — lista de hashes SHA-256
    mfa_backup_codes = Column(JSON, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    action = Column(String(64), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(64), nullable=True)
    detail = Column(JSON, nullable=True)
    user = relationship("User")


class IntegrationConfig(Base):
    """Configuracion de integraciones externas (credenciales cifradas)."""
    __tablename__ = "integration_configs"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False, index=True)  # ej: "sharepoint", "sap"
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    config_encrypted = Column(Text, nullable=True)   # JSON cifrado con Fernet
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = relationship("User")


class FeatureFlag(Base):
    """Control de modulos por licencia — gestionado exclusivamente por superadmin.

    organization_id=None indica un flag global (valor por defecto para todas las orgs).
    Un flag con organization_id especifico sobreescribe el valor global para esa org.
    """
    __tablename__ = "feature_flags"
    __table_args__ = (
        UniqueConstraint("name", "organization_id", name="uq_flag_name_org"),
    )
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False, index=True)
    label = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = relationship("User")
    organization = relationship("Organization")


# ---------- CONTEXTO ----------

class RiskContext(Base):
    """ISO 27005 cl. 7 - Context establishment (una fila por organizacion)."""
    __tablename__ = "risk_context"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    organization_name = Column(String(255), default="Organization")
    scope = Column(Text)
    boundaries = Column(Text)
    impact_criteria = Column(JSON)         # niveles y descripciones
    likelihood_criteria = Column(JSON)
    risk_acceptance_criteria = Column(JSON)
    risk_matrix = Column(JSON)             # matriz 5x5 ISO 27005 Annex E.2
    risk_appetite = Column(Integer, default=3)  # nivel 0..8 maximo aceptable
    ai_gap_cache = Column(JSON, nullable=True)   # cache gap analysis detallado (v1.8)
    # Normativas activas seleccionadas en el cuestionario IA
    active_frameworks = Column(JSON, nullable=True)  # ["iso27001","nis2","gdpr","ens",...]
    ens_level = Column(String(16), nullable=True)    # "basico" | "medio" | "alto"
    # Metodologia de analisis de riesgos
    # "iso27005" (default) | "magerit" | "combined"
    methodology = Column(String(16), default="iso27005", nullable=False)
    # Respuestas completas del cuestionario IA (persistidas para no tener que rellenar cada vez)
    questionnaire_answers = Column(JSON, nullable=True)
    # Catalogos de amenazas activos para análisis: ["iso27005", "magerit", "custom"]
    active_threat_catalogs = Column(JSON, nullable=True)  # None = todos activos
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


# ---------- AGRUPACION DE ACTIVOS (v1.8.0) ----------

class AssetGroupingConfig(Base):
    """Criterios de agrupacion de activos configurados por organizacion."""
    __tablename__ = "asset_grouping_configs"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    criteria = Column(JSON, nullable=False)  # [{id, name, description, level, enabled}]
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class AssetGroup(Base):
    """Grupo de activos para analisis de riesgo consolidado (ISO 27005 8.2)."""
    __tablename__ = "asset_groups"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    criteria_snapshot = Column(JSON, nullable=True)  # criterios habilitados al crear el grupo
    status = Column(Enum(AssetGroupStatus), default=AssetGroupStatus.PROPOSED)
    # Sin FK constraint para evitar referencia circular con assets.id
    representative_asset_id = Column(Integer, nullable=True)
    ai_rationale = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    members = relationship(
        "Asset",
        foreign_keys="[Asset.group_id]",
        back_populates="group",
    )


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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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
    # Analisis de riesgos automatico con IA (v1.7.5)
    ai_risk_status = Column(String(32), nullable=True)   # analysing|analysed|error
    ai_risk_summary = Column(JSON, nullable=True)         # {risks_created, risks_updated, summary}
    # Agrupacion de activos (v1.8.0)
    group_id = Column(Integer, ForeignKey("asset_groups.id"), nullable=True, index=True)
    is_group_representative = Column(Boolean, default=False)

    # Etiquetas de software para correlacion CPE/CVE (v2.2.5)
    # Lista de nombres de productos/vendors: ["apache", "nginx", "openssl", ...]
    software_tags = Column(JSON, nullable=True)

    # Import audit (v2.5.0)
    external_id = Column(String(255), nullable=True, index=True)  # ID externo (LeanIX, CMDB, etc)
    import_session_id = Column(String(64), nullable=True, index=True)  # para audit + rollback
    imported_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=True)

    # BCM location link — FK a BCMLocation, opcional (no reemplaza el campo 'location' String)
    bcm_location_id = Column(Integer, ForeignKey("bcm_locations.id"), nullable=True)

    group = relationship("AssetGroup", foreign_keys="[Asset.group_id]", back_populates="members")
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
    """Catalogo de amenazas - ISO 27005 Annex C + MAGERIT v3."""
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
    # Catalogo de origen: "iso27005" | "magerit" | "custom" (amenazas creadas por usuario)
    catalog = Column(String(32), default="iso27005", nullable=False, index=True)


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
    is_mandatory = Column(Boolean, default=False)  # v5.3.0 — control obligatorio ISO 27001 Annex A
    # v4.0.0 — regwatch: control retirado en nueva edicion de la norma
    deprecated_at = Column(DateTime, nullable=True)


class ControlImplementation(Base):
    """Implementacion concreta del control en la organizacion."""
    __tablename__ = "control_implementations"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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

    # v4.0.0 — regwatch: flag de revision requerida por cambio normativo
    regwatch_review_at = Column(DateTime, nullable=True)
    regwatch_pack_id = Column(Integer, ForeignKey("regwatch_change_packs.id"), nullable=True)

    # v5.2.0 — motor de riesgo: penalizaciones automaticas
    nc_penalty_factor = Column(Float, nullable=True)    # null=sin NC, 0.4=NC major activa
    ccm_last_status = Column(String(10), nullable=True) # PASS|FAIL|WARNING — ultimo test CCM
    ccm_tested_at = Column(DateTime, nullable=True)     # timestamp del ultimo test CCM

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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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
    treatment_progress = Column(Integer, default=0)  # 0-100: % de tareas de tratamiento completadas
    accepted_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    acceptance_justification = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    next_review = Column(DateTime, nullable=True)
    last_review_notified_at = Column(DateTime, nullable=True)  # dedup emails de revision
    # Campos MAGERIT v3 (cuando methodology="magerit"|"combined")
    magerit_dimension = Column(String(4), nullable=True)  # D|I|C|A|T — dimension primaria afectada
    degradation_pct = Column(Integer, nullable=True)       # % degradacion del activo (0-100)
    magerit_impact = Column(Float, nullable=True)          # impacto calculado = valor_dim × degrad/100

    # IA generado (v1.7.5)
    ai_generated = Column(Boolean, default=False)
    ai_rationale = Column(Text, nullable=True)   # justificacion del agente

    # Risk Acceptance formal workflow (ISO 27001 cl. 6.1.2e)
    acceptance_requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    acceptance_requested_at = Column(DateTime, nullable=True)
    acceptance_approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    acceptance_review_date = Column(DateTime, nullable=True)   # cuando re-evaluar la aceptacion

    # BCP coverage (ISO 22301 / ISO 27001 A.5.29) — calculado periodicamente por scheduler
    bcp_coverage = Column(JSON, nullable=True)
    # {"plan_id": 1, "plan_code": "BCP-0001", "plan_type": "bcp", "rto_hours": 4,
    #  "last_tested": "2025-01-01", "coverage_pct": 80}

    # Origen TPRM: si el riesgo fue generado desde una evaluacion de proveedor
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)

    # v5.2.0 — retroalimentacion y seguimiento de tratamiento
    likelihood_adjusted_reason = Column(Text, nullable=True)  # razon del ultimo ajuste de likelihood
    target_residual_level = Column(Integer, nullable=True)    # nivel residual objetivo tras tratamiento
    target_date = Column(DateTime, nullable=True)              # fecha limite para alcanzar el objetivo
    baseline_residual_level = Column(Integer, nullable=True)  # nivel residual en T0 (fecha de target)

    # v5.2.0 — GDPR Art.35: riesgo generado por actividad que requiere DPIA
    gdpr_activity_id = Column(Integer, ForeignKey("processing_activities.id"), nullable=True)

    asset = relationship("Asset", back_populates="risks")
    threat = relationship("Threat")
    owner = relationship("User", foreign_keys=[owner_id])
    accepted_by = relationship("User", foreign_keys=[accepted_by_id])
    vulnerabilities = relationship("Vulnerability", secondary=risk_vulnerability_table)
    controls = relationship("ControlImplementation", secondary=risk_control_table)
    supplier = relationship("Supplier", foreign_keys=[supplier_id])


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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    smtp_host = Column(String(255), default="")
    smtp_port = Column(Integer, default=587)
    smtp_user = Column(String(255), default="")
    smtp_password = Column(String(255), default="")          # legacy plaintext (deprecated)
    smtp_password_encrypted = Column(Text, nullable=True)    # Fernet-encrypted (v1.8+)
    smtp_from = Column(String(255), default="")
    smtp_use_tls = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class SSOState(Base):
    """State anti-CSRF para el flujo SSO OIDC — en BD para soporte multi-worker."""
    __tablename__ = "sso_states"
    id = Column(Integer, primary_key=True)
    state = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)


class SSOCode(Base):
    """Codigo de intercambio de un solo uso para el callback SSO.
    Evita exponer el JWT de RiskHub en la URL del redirect."""
    __tablename__ = "sso_codes"
    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    token = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class AlertRule(Base):
    """Regla de alerta: cuando se cumple el criterio, envia email al destinatario.

    Soporta reglas simples (event_type + threshold_level) y reglas compuestas
    (conditions JSON array + logic AND|OR) para condiciones multiples.
    """
    __tablename__ = "alert_rules"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    # Tipos simples: risk_high, risk_critical, treatment_overdue, risk_no_treatment
    event_type = Column(String(64), nullable=False)
    recipient_email = Column(String(255), nullable=False)
    threshold_level = Column(Integer, default=5)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_triggered_at = Column(DateTime, nullable=True)
    # v5.3.0 — reglas compuestas
    conditions = Column(JSON, nullable=True)    # [{"field":"residual_level","op":"gte","value":6}, ...]
    logic = Column(String(3), default="AND")    # AND | OR


# ---------- KRI — KEY RISK INDICATORS (v5.3.0) ----------

class KRIMetricType(str, PyEnum):
    """Tipo de metrica que el KRI/KPI monitoriza."""
    # --- KRI: señales de exposicion al riesgo (por riesgo individual) ---
    RESIDUAL_LEVEL = "residual_level"          # nivel residual del riesgo
    INHERENT_LEVEL = "inherent_level"          # nivel inherente
    OPEN_INCIDENTS = "open_incidents"          # incidentes abiertos vinculados
    OPEN_NCS = "open_ncs"                      # no conformidades mayores abiertas
    CONTROL_MATURITY = "control_maturity"      # madurez media de controles del riesgo
    OVERDUE_TASKS = "overdue_tasks"            # tareas de tratamiento vencidas
    # --- KRI: señales de alerta temprana a nivel organizacion (v5.7.1) ---
    KRI_CRITICAL_RISKS = "kri_critical_risks"          # # riesgos activos con residual >= 4
    KRI_STALE_RISKS = "kri_stale_risks"                # # riesgos sin actualizar en >90 dias
    KRI_CRITICAL_CVES = "kri_critical_cves"            # # hallazgos CRITICAL/HIGH con CVE sin remediar
    KRI_HIGH_RISK_SUPPLIERS = "kri_high_risk_suppliers"  # # proveedores tier-1/2 con score residual > 70
    # --- KPI: rendimiento del programa SGSI (nivel organizacion) ---
    # ISO 27001:2022 cl.9.1 — Evaluacion del rendimiento
    KPI_TREATMENT_RATE = "kpi_treatment_rate"           # % riesgos altos con plan de tratamiento
    KPI_MTTT = "kpi_mttt"                               # dias medios identificacion → tratado
    KPI_CONTROL_COVERAGE = "kpi_control_coverage"       # % controles implementados o parciales
    KPI_CONTROL_MATURITY_AVG = "kpi_control_maturity_avg"  # madurez media de controles (0-5)
    KPI_POLICY_REVIEW = "kpi_policy_review"             # % politicas publicadas revisadas en plazo
    KPI_NC_CLOSURE_RATE = "kpi_nc_closure_rate"         # % NCs cerradas en 90 dias
    # ISO 27005:2022 — Gestion del riesgo
    KPI_RISK_REDUCTION_AVG = "kpi_risk_reduction_avg"   # % reduccion media inherente→residual
    KPI_APPETITE_COMPLIANCE = "kpi_appetite_compliance" # % riesgos residual dentro del apetito (<=4)
    KPI_ASSET_COVERAGE = "kpi_asset_coverage"           # % activos con riesgo evaluado
    KPI_RISK_NO_OWNER = "kpi_risk_no_owner_rate"        # % riesgos sin responsable asignado
    KPI_HIGH_RISKS_NO_PLAN = "kpi_high_risks_no_plan"   # # riesgos altos sin plan de tratamiento
    # NIS2 Art.23 / DORA
    KPI_NIS2_NOTIFICATION = "kpi_nis2_notification_rate"  # % incidentes NIS2 notificados a tiempo
    KPI_BCP_COVERAGE = "kpi_bcp_coverage"               # % planes BCP aprobados / total
    # NIST CSF 2.0 — Respond / Recover
    KPI_MTTR_INCIDENTS = "kpi_mttr_incidents"           # MTTR de incidentes (dias promedio)
    # ISO 27036 / TPRM
    KPI_SUPPLIER_COVERAGE = "kpi_supplier_coverage"     # % proveedores tier-1 evaluados
    # TPRM KPIs adicionales
    KPI_SUPPLIER_CONTRACT_EXPIRY = "kpi_supplier_contract_expiry"  # % tier-1/2 con contrato exp en 90d
    KPI_SUPPLIER_CRITICAL_ISSUES = "kpi_supplier_critical_issues"  # # VendorIssues CRITICAL/HIGH abiertos
    KPI_VENDOR_ISSUE_MTTR = "kpi_vendor_issue_mttr"                # dias medios resolucion VendorIssues
    KPI_DORA_SUPPLIERS_ASSESSED = "kpi_dora_suppliers_assessed"    # % is_dora evaluados en 12m
    # BCP KPIs adicionales
    KPI_BCP_RTO_ACHIEVEMENT = "kpi_bcp_rto_achievement"           # % procesos RTO alcanzado <= objetivo
    KPI_BCP_TEST_FREQUENCY = "kpi_bcp_test_frequency"             # dias desde ultimo test BCP
    KPI_CRITICAL_PROCESSES_BCP = "kpi_critical_processes_bcp"    # % procesos criticos con BCP aprobado


class KRIStatus(str, PyEnum):
    NORMAL = "normal"
    WARNING = "warning"
    BREACH = "breach"


class KRI(Base):
    """Key Risk Indicator / KPI: umbral configurable sobre metrica de riesgo o programa SGSI."""
    __tablename__ = "kris"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    risk_id = Column(Integer, ForeignKey("risks.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    metric_type = Column(String(64), nullable=False)            # KRIMetricType value
    warning_threshold = Column(Float, nullable=True)            # umbral de advertencia
    breach_threshold = Column(Float, nullable=True)             # umbral de incumplimiento
    current_value = Column(Float, nullable=True)                # ultimo valor calculado
    status = Column(String(16), default="normal")               # KRIStatus value
    is_active = Column(Boolean, default=True)
    last_evaluated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    alert_on_breach = Column(Boolean, default=True)
    recipient_email = Column(String(255), nullable=True)        # email adicional para alertas
    # Campos KPI/edicion v5.4
    indicator_type = Column(String(8), default="kri")           # 'kri' | 'kpi'
    is_visible = Column(Boolean, default=True)                  # si se muestra en la UI
    custom_name = Column(String(255), nullable=True)            # nombre personalizado por el usuario
    description = Column(Text, nullable=True)                   # descripcion o referencia normativa
    is_system = Column(Boolean, default=False)                  # True = seed del sistema, no borrable
    direction = Column(String(20), default="lower_is_better")  # 'higher_is_better' | 'lower_is_better'


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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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
    affects_continuity = Column(Boolean, default=False)
    bcp_activation_id = Column(Integer, ForeignKey("bcm_activations.id"), nullable=True)
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


class SupplierTier(str, PyEnum):
    """Tier de criticidad derivado del inherent risk (TPRM)."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SupplierRelationship(str, PyEnum):
    """Estado del ciclo de vida del proveedor (TPRM)."""
    PROSPECT = "prospect"
    ACTIVE = "active"
    UNDER_REVIEW = "under_review"
    SUSPENDED = "suspended"
    OFFBOARDING = "offboarding"
    TERMINATED = "terminated"


class Supplier(Base):
    """Proveedor / tercero con evaluacion de riesgo de cadena de suministro."""
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    code = Column(String(32), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    services = Column(Text)               # servicios que presta
    category = Column(String(128), nullable=True)
    is_critical = Column(Boolean, default=False)
    risk_level = Column(String(16), default="medium")
    certifications = Column(JSON)         # ["ISO27001","SOC2",...]
    contact_name = Column(String(255))
    contact_email = Column(String(255))
    contract_ref = Column(String(255), nullable=True)
    contract_expiry = Column(DateTime, nullable=True)
    last_assessment_at = Column(DateTime, nullable=True)
    next_assessment_at = Column(DateTime, nullable=True)
    score = Column(Integer, default=50)   # 0-100 (postura: mayor = mejor)
    notes = Column(Text)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # ---- TPRM (Third-Party Risk Management) ----
    tier = Column(Enum(SupplierTier, values_callable=lambda x: [e.value for e in x]), nullable=True)
    relationship_status = Column(Enum(SupplierRelationship, values_callable=lambda x: [e.value for e in x]), default=SupplierRelationship.ACTIVE)
    vendor_type = Column(String(64), nullable=True)           # technology|cloud_provider|...
    # Atributos para el calculo de inherent risk (1-5 salvo flags)
    data_sensitivity = Column(Integer, default=2)            # 1-5
    data_volume = Column(Integer, default=2)                 # 1-5
    system_access_type = Column(String(32), nullable=True)   # none|api_only|saas|admin_to_our_systems...
    business_criticality = Column(Integer, default=3)       # 1-5
    geographic_risk = Column(Integer, default=1)            # 1-5 (transferencias fuera UE, sanciones)
    # Scoring TPRM (0-100; inherent/residual: mayor = mas riesgo)
    inherent_risk_score = Column(Integer, nullable=True)
    control_effectiveness = Column(Integer, nullable=True)  # 0-100 (mayor = mejor)
    residual_risk_score = Column(Integer, nullable=True)
    # Flags regulatorios
    is_data_processor = Column(Boolean, default=False)       # GDPR art. 28
    processes_personal_data = Column(Boolean, default=False)
    cross_border_transfers = Column(Boolean, default=False)
    is_nis2 = Column(Boolean, default=False)
    is_dora = Column(Boolean, default=False)
    is_ens = Column(Boolean, default=False)
    # Firmographics / nth-party
    country_code = Column(String(2), nullable=True)
    website = Column(String(255), nullable=True)
    tax_id = Column(String(64), nullable=True)
    annual_spend = Column(Float, nullable=True)
    parent_supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    nth_party_depth = Column(Integer, default=1)            # 1=directo, 2=subcontratista...
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    # SLAs definidos para este proveedor
    # [{id, name, metric, category, description}]
    slas = Column(JSON, nullable=True)
    # v4.3.0 — contactos multiples, CC email, ubicacion, departamento, importancia negocio
    cc_email = Column(String(255), nullable=True)
    additional_contacts = Column(JSON, nullable=True)   # [{name, email, role, phone}]
    location = Column(String(255), nullable=True)
    department = Column(String(128), nullable=True)
    business_importance = Column(Integer, nullable=True)  # 1-5
    internal_owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner = relationship("User", foreign_keys="[Supplier.owner_id]")
    internal_owner = relationship("User", foreign_keys="[Supplier.internal_owner_id]")
    # parent_supplier_id (nth-party) se consulta por id; no se mapea relacion
    # self-referencial para evitar ambiguedad de mapper.
    # v5.5 — lifecycle y onboarding
    lifecycle_stage = Column(String(32), default="active")  # prospecting|onboarding|active|under_review|offboarding|terminated
    lifecycle_changed_at = Column(DateTime, nullable=True)
    lifecycle_changed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    onboarding_completed_at = Column(DateTime, nullable=True)
    onboarding_checklist = Column(JSON, nullable=True)  # [{id, title, required, completed, completed_at, completed_by_id, evidence_doc_id, category}]
    stakeholders = Column(JSON, nullable=True)  # [{role, name, email, phone, user_id, notified_on_assessment, notified_on_issue}]
    # Firma y documentacion legal
    dpa_signed_at = Column(DateTime, nullable=True)
    dpa_signed_by = Column(String(255), nullable=True)
    dpa_document_id = Column(Integer, ForeignKey("ai_documents.id"), nullable=True)
    nda_signed_at = Column(DateTime, nullable=True)
    nda_document_id = Column(Integer, ForeignKey("ai_documents.id"), nullable=True)
    contract_document_id = Column(Integer, ForeignKey("ai_documents.id"), nullable=True)
    contract_renewal_reminder_sent_at = Column(DateTime, nullable=True)
    # DORA compliance
    ict_service_category = Column(String(16), nullable=True)  # critical|important|other
    exit_strategy = Column(Text, nullable=True)
    # Mitigacion de concentracion de riesgo
    concentration_risk_flag = Column(Boolean, default=False)  # True si >40% procesos criticos dependen de este proveedor
    concentration_risk_mitigated_at = Column(DateTime, nullable=True)
    concentration_risk_notes = Column(Text, nullable=True)
    # v5.8 — Gate de onboarding cyber: override, decision formal, cadena de firmas
    gate_override_type = Column(String(16), nullable=True)          # bypass | force_controls
    gate_override_justification = Column(Text, nullable=True)
    gate_override_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    gate_override_at = Column(DateTime, nullable=True)
    forced_signoffs = Column(JSON, nullable=True)                   # IDs extra forzados independientemente del score
    onboarding_decision = Column(String(16), nullable=True)         # approved | rejected | conditional
    onboarding_decision_notes = Column(Text, nullable=True)
    onboarding_decision_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    onboarding_decision_at = Column(DateTime, nullable=True)
    onboarding_conditions = Column(JSON, nullable=True)             # [{id, description, due_days, vendor_issue_id}]
    sign_off_chain_state = Column(JSON, nullable=True)              # [{id, signed_at, signed_by_name, signed_by_user_id, doc_id, skipped, skip_justification}]


class OnboardingGateConfig(Base):
    """Configuracion del gate de onboarding de proveedores — editable por admin."""
    __tablename__ = "onboarding_gate_configs"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    # Umbrales de score TPRM (0-100): auto-aproba / standard / revision manual
    auto_approve_below = Column(Integer, default=30)
    manual_review_above = Column(Integer, default=60)
    # Cadena de firmas ordenada — [{id, label, required, required_if, depends_on, score_gate, bypass_allowed}]
    sign_off_chain = Column(JSON, nullable=True)
    # Politica de bypass y forzado
    bypass_min_role = Column(String(16), default="admin")           # admin | analyst
    bypass_requires_justification = Column(Boolean, default=True)
    force_controls_allowed = Column(Boolean, default=True)
    updated_at = Column(DateTime, nullable=True)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = relationship("User", foreign_keys=[updated_by_id])


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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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


class RiskCorrelation(Base):
    """Par de riesgos correlados: si uno se materializa eleva la prob del otro (v5.3.0)."""
    __tablename__ = "risk_correlations"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    risk_id_a = Column(Integer, ForeignKey("risks.id", ondelete="CASCADE"), nullable=False, index=True)
    risk_id_b = Column(Integer, ForeignKey("risks.id", ondelete="CASCADE"), nullable=False, index=True)
    correlation_factor = Column(Float, nullable=False, default=0.5)  # 0=independientes, 1=perfectamente correlados
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RiskSnapshot(Base):
    """Snapshot mensual del nivel de riesgo para historico y tendencias (v5.2.0)."""
    __tablename__ = "risk_snapshots"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    risk_id = Column(Integer, ForeignKey("risks.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_date = Column(DateTime, nullable=False, index=True)   # fecha del snapshot (primer dia del mes)
    inherent_likelihood = Column(Integer, nullable=True)
    inherent_consequence = Column(Integer, nullable=True)
    inherent_level = Column(Integer, nullable=True)
    residual_likelihood = Column(Integer, nullable=True)
    residual_consequence = Column(Integer, nullable=True)
    residual_level = Column(Integer, nullable=True)
    control_count = Column(Integer, nullable=True)                 # num controles vinculados en ese momento
    risk_status = Column(String(32), nullable=True)                # status en ese momento
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TreatmentTask(Base):
    """Tarea de plan de tratamiento asociada a un riesgo (opcional)."""
    __tablename__ = "treatment_tasks"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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
    # Documento origen (v1.7.4)
    source_document_id = Column(Integer, ForeignKey("ai_documents.id"), nullable=True)
    review_cycle_months = Column(Integer, nullable=True)   # ciclo de revision en meses

    # v4.0.0 — regwatch: cambio normativo requiere revision de esta politica
    regwatch_review_at = Column(DateTime, nullable=True)
    regwatch_pack_id = Column(Integer, ForeignKey("regwatch_change_packs.id"), nullable=True)

    # v4.1.0 — versionado: editar una politica aprobada/publicada crea una nueva
    # fila en draft enlazada via previous_version_id; al aprobarse, la version
    # anterior pasa automaticamente a obsoleta (mismo patron que BCPPlan).
    previous_version_id = Column(Integer, ForeignKey("policies.id"), nullable=True)

    # v5.0 — Jerarquia documental ISO: Politica(1) > Norma(2) > Procedimiento(3) > Instruccion Tecnica(4)
    document_level = Column(Integer, default=1, nullable=False)
    parent_policy_id = Column(Integer, ForeignKey("policies.id"), nullable=True)
    intended_controls = Column(JSON, nullable=True)  # codigos ISO 27002 que este doc debe cubrir

    # v5.1 — Checkout para evitar edicion concurrente; auto-release tras 4h
    checked_out_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    checked_out_at = Column(DateTime, nullable=True)

    owner = relationship("User", foreign_keys=[owner_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    source_document = relationship("AiDocument", foreign_keys=[source_document_id])
    previous_version = relationship("Policy", remote_side=[id], foreign_keys=[previous_version_id])
    parent_policy = relationship("Policy", remote_side=[id], foreign_keys=[parent_policy_id])
    checked_out_by = relationship("User", foreign_keys=[checked_out_by_id])
    approval_requests = relationship(
        "ApprovalRequest",
        back_populates="policy",
        order_by="desc(ApprovalRequest.created_at)",
        cascade="all, delete-orphan",
    )


# ---------- APROBACION DOCUMENTAL ----------

class ApprovalRequest(Base):
    """Ronda de aprobacion para una politica ISMS — paralela o secuencial."""
    __tablename__ = "approval_requests"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    policy_id = Column(Integer, ForeignKey("policies.id", ondelete="CASCADE"), nullable=False)
    requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    mode = Column(String(20), default="parallel")    # parallel | sequential
    status = Column(String(20), default="pending")   # pending | approved | rejected | cancelled
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    policy = relationship("Policy", back_populates="approval_requests")
    requested_by = relationship("User")
    approvals = relationship(
        "PolicyApproval",
        back_populates="request",
        order_by="PolicyApproval.order_index",
        cascade="all, delete-orphan",
    )


class PolicyApproval(Base):
    """Registro de aprobacion individual dentro de una ronda."""
    __tablename__ = "policy_approvals"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    request_id = Column(Integer, ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False)
    approver_email = Column(String(255), nullable=False)
    approver_name = Column(String(255), nullable=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    status = Column(String(20), default="waiting")   # waiting | pending | approved | rejected
    order_index = Column(Integer, default=1)
    sent_at = Column(DateTime, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    response_notes = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    expires_at = Column(DateTime, nullable=False)

    request = relationship("ApprovalRequest", back_populates="approvals")


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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    code = Column(String(32), unique=True, nullable=False)   # SEQ-0001
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    title = Column(String(255), nullable=False)
    token = Column(String(64), unique=True, nullable=False)  # acceso publico
    template_code = Column(String(64), nullable=True)        # plantilla TPRM del sistema usada
    questions = Column(JSON)                 # [{id, text, type, weight, scoring_rules, control_refs}]
    answers = Column(JSON, nullable=True)    # {question_id: answer}
    score = Column(Integer, nullable=True)   # 0-100
    submitted_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    notes = Column(Text)
    evidence = Column(JSON, nullable=True)           # TPRM: {question_id: {filename, stored_name, size, uploaded_at}}
    ai_review = Column(JSON, nullable=True)          # TPRM: salida estructurada de la evaluacion IA
    ai_reviewed_at = Column(DateTime, nullable=True)
    major_nc = Column(Integer, nullable=True)        # TPRM: no-conformidades mayores (criticity=Major con respuesta NC)
    minor_nc = Column(Integer, nullable=True)        # TPRM: no-conformidades menores
    residual_risk_level = Column(String(16), nullable=True)  # TPRM: low|medium|high|critical
    # v3.9.0 — flujo evaluacion dos fases: profiling + assessment
    phase = Column(String(16), nullable=True)        # profiling | assessment | None (cuestionario directo)
    parent_assessment_id = Column(Integer, ForeignKey("vendor_risk_assessments.id"), nullable=True)
    next_questionnaire_id = Column(Integer, ForeignKey("supplier_questionnaires.id"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # v4.3.0 — email de notificacion especifico para este cuestionario
    notify_email = Column(String(255), nullable=True)
    # v4.0.0 — regwatch: plantilla desactualizada por cambio normativo
    regwatch_review_at = Column(DateTime, nullable=True)
    regwatch_pack_id = Column(Integer, ForeignKey("regwatch_change_packs.id"), nullable=True)
    # v4.4.0 — asignacion interna: usuario de la plataforma rellena el cuestionario autenticado
    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assignment_type = Column(String(16), nullable=True)  # external (default) | internal
    assigned_at = Column(DateTime, nullable=True)

    supplier = relationship("Supplier")
    created_by = relationship("User", foreign_keys="[SupplierQuestionnaire.created_by_id]")
    assigned_user = relationship("User", foreign_keys="[SupplierQuestionnaire.assigned_user_id]")

    @property
    def supplier_name(self) -> str:
        return self.supplier.name if self.supplier else ""

    @property
    def assigned_user_name(self) -> str:
        if not self.assigned_user:
            return ""
        return self.assigned_user.full_name or self.assigned_user.email or ""


class FormIntegrationConfig(Base):
    """Configuracion de integracion de formularios externos (MS Forms inbound, Monday.com outbound)."""
    __tablename__ = "form_integration_configs"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    # Webhook entrante MS Forms / Power Automate
    inbound_token = Column(String(64), unique=True, nullable=False)
    default_template_code = Column(String(64), nullable=True)
    supplier_field_name = Column(String(255), nullable=True)  # nombre del campo del formulario que identifica al proveedor
    # Webhook saliente Monday.com
    monday_webhook_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


# ---------- TPRM: EVALUACIONES Y HALLAZGOS ----------

class AssessmentRecommendation(str, PyEnum):
    APPROVE = "approve"
    APPROVE_WITH_CONDITIONS = "approve_with_conditions"
    REJECT = "reject"
    REQUEST_MORE_INFO = "request_more_info"


class VendorIssueSeverity(str, PyEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class VendorIssueStatus(str, PyEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    IN_REMEDIATION = "in_remediation"
    MITIGATED = "mitigated"
    ACCEPTED = "accepted"
    CLOSED = "closed"
    OVERDUE = "overdue"


class VendorRiskAssessment(Base):
    """Evaluacion consolidada de riesgo de un proveedor (TPRM §2.1)."""
    __tablename__ = "vendor_risk_assessments"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    code = Column(String(32), nullable=False)            # VAS-0001
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    assessment_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    period_label = Column(String(32), nullable=True)     # ej. 2026-Q2
    inherent_risk_score = Column(Integer, nullable=True)
    inherent_risk_level = Column(String(16), nullable=True)
    control_effectiveness_score = Column(Integer, nullable=True)
    residual_risk_score = Column(Integer, nullable=True)
    residual_risk_level = Column(String(16), nullable=True)
    score_by_domain = Column(JSON, nullable=True)        # {governance: 78, ...}
    summary = Column(Text, nullable=True)
    recommendation = Column(Enum(AssessmentRecommendation), nullable=True)
    assessor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approver_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)
    linked_risk_id = Column(Integer, ForeignKey("risks.id"), nullable=True)  # push a Risk Register
    questionnaire_ids = Column(JSON, nullable=True)      # cuestionarios agregados
    # v3.9.0 — flujo dos fases y decision posterior al envio del proveedor
    assessment_type = Column(String(32), default="direct")     # risk_analysis | direct
    profiling_questionnaire_id = Column(Integer, ForeignKey("supplier_questionnaires.id"), nullable=True)
    assessment_questionnaire_id = Column(Integer, ForeignKey("supplier_questionnaires.id"), nullable=True)
    decision_notes = Column(Text, nullable=True)
    decision_at = Column(DateTime, nullable=True)
    decision_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # v4.1.0 — versionado: re-evaluar un proveedor ya aprobado crea una nueva
    # evaluacion enlazada via previous_version_id; al aprobarse, la anterior
    # deja de estar vigente (is_current=False), mismo patron que BCPPlan/Policy.
    previous_version_id = Column(Integer, ForeignKey("vendor_risk_assessments.id"), nullable=True)
    is_current = Column(Boolean, default=True)

    supplier = relationship("Supplier")
    profiling_q = relationship("SupplierQuestionnaire", foreign_keys="VendorRiskAssessment.profiling_questionnaire_id")
    assessment_q = relationship("SupplierQuestionnaire", foreign_keys="VendorRiskAssessment.assessment_questionnaire_id")
    previous_version = relationship("VendorRiskAssessment", remote_side=[id], foreign_keys=[previous_version_id])

    @property
    def supplier_name(self) -> str:
        return self.supplier.name if self.supplier else ""


class VendorIssue(Base):
    """Hallazgo / issue de un proveedor con SLA por severidad (TPRM §2.1)."""
    __tablename__ = "vendor_issues"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    code = Column(String(32), nullable=False)            # VIS-0001
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    assessment_id = Column(Integer, ForeignKey("vendor_risk_assessments.id"), nullable=True)
    source = Column(String(32), default="manual")        # questionnaire|external_rating|manual|incident|monitoring
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(Enum(VendorIssueSeverity), default=VendorIssueSeverity.MEDIUM)
    status = Column(Enum(VendorIssueStatus), default=VendorIssueStatus.OPEN)
    framework_refs = Column(JSON, nullable=True)
    discovered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    due_date = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    remediation_plan = Column(Text, nullable=True)
    # SLAs incumplidos: [{sla_id, sla_name, details}]
    sla_breaches = Column(JSON, nullable=True)
    impact_description = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    action_items = Column(JSON, nullable=True)     # [{text, done, due_date}]
    evidence_refs = Column(JSON, nullable=True)    # [{name, url}]
    resolution_notes = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # v5.5 — auto-generated flag y risk register link
    auto_generated = Column(Boolean, default=False)      # True si fue creado por OSINT/CVE/scoring
    auto_generated_source = Column(String(64), nullable=True)  # osint|cve|score_decay|concentration
    linked_risk_id = Column(Integer, ForeignKey("risks.id"), nullable=True)
    resolved_by_action = Column(String(255), nullable=True)  # descripcion de como se resolvio

    supplier = relationship("Supplier")

    @property
    def supplier_name(self) -> str:
        return self.supplier.name if self.supplier else ""


class TPRMTemplate(Base):
    """Plantilla de cuestionario editable por el cliente (TPRM §4.5).

    Las plantillas del sistema viven en codigo (services/tprm_templates.py) y son
    de solo lectura; estas son copias clonables/editables por organizacion.
    """
    __tablename__ = "tprm_templates"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    framework_codes = Column(JSON, nullable=True)        # ["ISO_27001", ...]
    questions = Column(JSON, nullable=False)             # [{id, text, type, weight, scoring_rules, requires_evidence, domain, options}]
    created_from = Column(String(64), nullable=True)     # codigo de la plantilla del sistema clonada
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


# ---------- SUPPLIER DOCUMENTS ----------

class SupplierDocument(Base):
    """Documento adjunto a un proveedor (contratos, certificaciones, informes, etc.)."""
    __tablename__ = "supplier_documents"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)       # nombre original del fichero
    stored_name = Column(String(255), nullable=False)    # nombre en disco (cifrado)
    size = Column(Integer, nullable=True)                # bytes
    description = Column(Text, nullable=True)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    supplier = relationship("Supplier")
    uploaded_by = relationship("User")


# ---------- QUESTIONNAIRE SCHEDULES (envio periodico) ----------

class QuestionnaireSchedule(Base):
    """Planificacion de envio periodico de cuestionarios a un proveedor."""
    __tablename__ = "questionnaire_schedules"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    title_template = Column(String(255), nullable=False)     # plantilla de titulo (ej. "Evaluacion anual {year}")
    template_code = Column(String(64), nullable=True)        # plantilla del sistema
    custom_template_id = Column(Integer, ForeignKey("tprm_templates.id"), nullable=True)
    interval_days = Column(Integer, nullable=False, default=365)  # cada cuantos dias
    expires_days = Column(Integer, nullable=False, default=30)    # dias de validez del cuestionario enviado
    notify_email = Column(String(255), nullable=True)        # email a quien notificar cuando el proveedor responde
    notes = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True)
    next_send_at = Column(DateTime, nullable=True)           # proxima fecha de envio
    last_sent_at = Column(DateTime, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    supplier = relationship("Supplier")
    created_by = relationship("User")


# ---------- QUESTIONNAIRE FLOWS (flujos multi-paso) ----------

class QuestionnaireFlow(Base):
    """Flujo de cuestionarios encadenados segun resultado de la fase anterior."""
    __tablename__ = "questionnaire_flows"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # steps: [{id, name, template_code, custom_template_id, expires_days,
    #          condition: null | {score_lt, score_gte, residual_level}}]
    # condition null = primer paso (siempre se envia)
    steps = Column(JSON, nullable=False, default=list)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    created_by = relationship("User")


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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    api_key_encrypted = Column(Text, nullable=True)        # Fernet-encrypted Anthropic key
    voyage_api_key_encrypted = Column(Text, nullable=True) # Fernet-encrypted Voyage AI key
    model = Column(String(64), default="claude-opus-4-6")
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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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
    # Analisis ISMS automatico (v1.7.4)
    isms_status = Column(String(32), nullable=True)   # analysing|analysed|skipped|error
    isms_summary = Column(JSON, nullable=True)         # {policy_id, controls_updated, tasks_created, summary}
    # Auto-categorizacion IA (v1.8)
    auto_categorized = Column(Boolean, default=False)
    detected_category = Column(String(64), nullable=True)
    # Clausulas ISO extraidas automaticamente por IA (v2.2)
    extracted_clauses = Column(JSON, nullable=True)  # [{ref, title, control_id, confidence}]

    uploaded_by = relationship("User")
    chunks = relationship("AiDocumentChunk", back_populates="document",
                          cascade="all, delete-orphan")


class AiDocumentChunk(Base):
    """Fragmento de texto indexado en FTS5 y opcionalmente vectorizado con embeddings."""
    __tablename__ = "ai_document_chunks"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("ai_documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Text, nullable=True)  # JSON float array — Voyage AI vector

    document = relationship("AiDocument", back_populates="chunks")


class AiCallLog(Base):
    """Log de llamadas a la API de IA."""
    __tablename__ = "ai_call_logs"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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
    HIBP = "hibp"                        # Have I Been Pwned
    VIRUSTOTAL = "virustotal"            # VirusTotal
    LEAKCHECK = "leakcheck"              # LeakCheck
    INTELX = "intelx"                    # Intelligence X (short alias)
    INTELLIGENCE_X = "intelligence_x"   # Intelligence X (full alias usado por osint_intelx.py)
    GITHUB = "github"                    # GitHub Recon
    SOCIAL = "social"                    # Social Media Scraping
    DOMAIN = "domain"                    # Escaneo de dominio (DNS, SSL, subdominios, RDAP)
    IP_INTEL = "ip_intel"                # Inteligencia de IP (geolocation, ASN, puertos)


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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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
    source = Column(String(64), nullable=False)          # valor libre: hibp, domain, ip_intel, etc.
    finding_type = Column(String(64), nullable=False)    # data_breach, exposed_password, url_malware, etc.
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    risk_level = Column(String(16), default="medium")    # critical|high|medium|low|info
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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    primary_color = Column(String(7), default="#59008D")
    secondary_color = Column(String(7), default="#D65200")
    logo_filename = Column(String(255))   # archivo almacenado en /srv/data/branding/
    logo_mime = Column(String(64))
    company_name = Column(String(255))
    updated_at = Column(DateTime)
    updated_by_id = Column(Integer, ForeignKey("users.id"))

    updated_by = relationship("User", foreign_keys=[updated_by_id])


class ReportBrandingConfig(Base):
    """Configuracion de marca por tipo de informe para personalizar la salida PDF/Excel."""
    __tablename__ = "report_branding_configs"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    report_type = Column(String(64), nullable=False)
    primary_color = Column(String(7), default="#59008D")
    secondary_color = Column(String(7), default="#D65200")
    logo_filename = Column(String(255), nullable=True)
    logo_mime = Column(String(64), nullable=True)
    template_filename = Column(String(255), nullable=True)
    template_mime = Column(String(128), nullable=True)
    company_name = Column(String(255), nullable=True)
    header_title = Column(String(255), nullable=True)
    footer_text = Column(String(255), nullable=True)
    cover_subtitle = Column(String(255), nullable=True)
    font_family = Column(String(64), default="Helvetica")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


# ---------- COMPLIANCE FRAMEWORKS ----------

class ComplianceRequirementStatus(str, PyEnum):
    NOT_APPLICABLE = "not_applicable"
    PLANNED = "planned"
    PARTIAL = "partial"
    IMPLEMENTED = "implemented"
    AUDITED = "audited"


class ComplianceFrameworkStatus(Base):
    """Estado de cumplimiento por framework y requisito, por org."""
    __tablename__ = "compliance_framework_status"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    framework_code = Column(String(64), nullable=False)       # "iso27001", "gdpr", "hipaa", etc.
    requirement_id = Column(String(64), nullable=False)       # "A.5.1", "Art.25", etc.
    status = Column(Enum(ComplianceRequirementStatus), default=ComplianceRequirementStatus.PLANNED)
    completion_pct = Column(Integer, default=0)               # 0-100
    responsible_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    next_audit_date = Column(DateTime, nullable=True)
    last_reviewed_at = Column(DateTime, nullable=True)
    evidence_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    # v4.0.0 — regwatch: requisito afectado por cambio normativo, requiere revision
    regwatch_review_at = Column(DateTime, nullable=True)
    regwatch_pack_id = Column(Integer, ForeignKey("regwatch_change_packs.id"), nullable=True)

    responsible = relationship("User", foreign_keys=[responsible_id])
    __table_args__ = (
        UniqueConstraint("organization_id", "framework_code", "requirement_id"),
    )


# ---------- EVIDENCE CENTRALIZED ----------

class EvidenceType(str, PyEnum):
    POLICY = "policy"
    PROCEDURE = "procedure"
    RECORD = "record"
    CERTIFICATE = "certificate"
    SCREENSHOT = "screenshot"
    LOG = "log"
    REPORT = "report"
    OTHER = "other"


class Evidence(Base):
    """Evidencia centralizada con versionado y audit trail."""
    __tablename__ = "evidence"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    code = Column(String(32), nullable=False, unique=True)         # EVD-0001
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    evidence_type = Column(Enum(EvidenceType), default=EvidenceType.OTHER)
    filename = Column(String(512), nullable=True)                   # archivo en disco
    mime_type = Column(String(128), nullable=True)
    file_hash = Column(String(128), nullable=True)                  # SHA-256 integridad
    file_size = Column(Integer, nullable=True)
    # Links polimorficos
    control_implementation_id = Column(Integer, ForeignKey("control_implementations.id"), nullable=True)
    risk_id = Column(Integer, ForeignKey("risks.id"), nullable=True)
    policy_id = Column(Integer, ForeignKey("policies.id"), nullable=True)
    compliance_framework = Column(String(64), nullable=True)        # "iso27001"
    compliance_requirement = Column(String(64), nullable=True)      # "A.5.1"
    # Expiración
    valid_from = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    expiry_alert_sent = Column(Boolean, default=False)
    # Audit
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    version = Column(Integer, default=1)
    is_current = Column(Boolean, default=True)
    previous_version_id = Column(Integer, ForeignKey("evidence.id"), nullable=True)

    created_by = relationship("User", foreign_keys=[created_by_id])
    previous_version = relationship("Evidence", remote_side=[id], foreign_keys=[previous_version_id])


# ---------- WEBHOOKS ----------

class WebhookEvent(str, PyEnum):
    RISK_CREATED = "risk.created"
    RISK_HIGH = "risk.high"
    RISK_CLOSED = "risk.closed"
    EVIDENCE_EXPIRED = "evidence.expired"
    SUPPLIER_RISK_CHANGED = "supplier.risk_changed"
    COMPLIANCE_GAP = "compliance.gap"
    INCIDENT_CREATED = "incident.created"
    TASK_OVERDUE = "task.overdue"


class Webhook(Base):
    """Configuracion de webhook para notificaciones externas."""
    __tablename__ = "webhooks"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    url = Column(String(1024), nullable=False)
    secret = Column(String(256), nullable=True)         # HMAC signing secret
    events = Column(JSON, nullable=False)               # lista de WebhookEvent
    is_active = Column(Boolean, default=True)
    headers = Column(JSON, nullable=True)               # headers extra
    retry_count = Column(Integer, default=3)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_triggered_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)

    created_by = relationship("User", foreign_keys=[created_by_id])


class WebhookDelivery(Base):
    """Log de entregas de webhooks."""
    __tablename__ = "webhook_deliveries"
    id = Column(Integer, primary_key=True)
    webhook_id = Column(Integer, ForeignKey("webhooks.id"), nullable=False, index=True)
    event = Column(String(64), nullable=False)
    payload = Column(Text, nullable=True)
    response_status = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    success = Column(Boolean, default=False)
    attempt = Column(Integer, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    webhook = relationship("Webhook")


# ---------- RISK WORKFLOW ----------

class WorkflowStepStatus(str, PyEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    SKIPPED = "skipped"


class RiskWorkflow(Base):
    """Seguimiento del lifecycle automatizado de un riesgo."""
    __tablename__ = "risk_workflows"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    risk_id = Column(Integer, ForeignKey("risks.id"), nullable=False, unique=True)
    step_analysis = Column(Enum(WorkflowStepStatus), default=WorkflowStepStatus.PENDING)
    step_mitigation = Column(Enum(WorkflowStepStatus), default=WorkflowStepStatus.PENDING)
    step_verification = Column(Enum(WorkflowStepStatus), default=WorkflowStepStatus.PENDING)
    step_closure = Column(Enum(WorkflowStepStatus), default=WorkflowStepStatus.PENDING)
    assigned_analyst_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    sla_days = Column(Integer, default=30)
    sla_due_date = Column(DateTime, nullable=True)
    escalated = Column(Boolean, default=False)
    escalated_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    risk = relationship("Risk")
    assigned_analyst = relationship("User", foreign_keys=[assigned_analyst_id])
    assigned_owner = relationship("User", foreign_keys=[assigned_owner_id])


# ---------- EXTERNAL FINDINGS (Nessus, Qualys, Burp, etc) ----------

class ExternalFindingSource(str, PyEnum):
    NESSUS = "nessus"
    QUALYS = "qualys"
    BURP = "burp"
    OPENVAS = "openvas"
    SHODAN = "shodan"
    CENSYS = "censys"
    SIEM = "siem"
    SSL_LABS = "ssl_labs"
    MANUAL = "manual"
    ARCHITECTURE_REVIEW = "architecture_review"
    SUPPLIER_MONITOR = "supplier_monitor"  # v4.3.0 monitoreo periodico de proveedores


class ExternalFinding(Base):
    """Hallazgo importado de herramienta de seguridad externa."""
    __tablename__ = "external_findings"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    source = Column(Enum(ExternalFindingSource), nullable=False)
    external_id = Column(String(256), nullable=True)            # ID en la herramienta
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String(32), nullable=True)                # CRITICAL/HIGH/MEDIUM/LOW
    cvss_score = Column(Float, nullable=True)
    cve_id = Column(String(64), nullable=True)
    affected_host = Column(String(512), nullable=True)
    affected_port = Column(Integer, nullable=True)
    affected_software = Column(String(512), nullable=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)  # link a asset
    risk_id = Column(Integer, ForeignKey("risks.id"), nullable=True)     # risk creado
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)  # incidente creado
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)  # v4.3.0 proveedor monitorizado
    status = Column(String(32), default="open")                 # open/resolved/accepted
    raw_data = Column(Text, nullable=True)                      # XML/JSON original
    import_batch_id = Column(String(64), nullable=True)         # agrupa import
    # Origen del hallazgo cuando proviene de analisis IA (revision de arquitectura, etc.)
    # — permite filtrar resultados por documento/esquema cuando se analizan varios a la vez.
    source_document = Column(String(512), nullable=True)
    iso_control = Column(String(32), nullable=True)             # control ISO 27002 incumplido
    detected_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    asset = relationship("Asset")
    risk = relationship("Risk")
    incident = relationship("Incident")
    supplier_ref = relationship("Supplier", foreign_keys=[supplier_id])


# ---------- MANAGEMENT REVIEW (ISO 27001 cl. 9.3) ----------

class ManagementReview(Base):
    """Revision por la Direccion — ISO 27001 cl. 9.3. Auto-poblada desde BD."""
    __tablename__ = "management_reviews"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    code = Column(String(16))                        # MR-2025-01
    review_date = Column(DateTime, nullable=True)
    attendees = Column(JSON, nullable=True)           # [{name, role, signature_ref}]
    status = Column(String(20), default="draft")      # draft|conducted|approved
    # Entradas ISO 9.3.2 — auto-pobladas por prepare_monthly_review()
    input_previous_actions = Column(JSON, nullable=True)
    input_changes_context = Column(Text, nullable=True)
    input_performance_data = Column(JSON, nullable=True)   # snapshot KPIs
    input_nc_corrections = Column(JSON, nullable=True)
    input_risk_register = Column(JSON, nullable=True)      # top risks snapshot
    input_audit_results = Column(JSON, nullable=True)
    # Salidas ISO 9.3.3 — rellenadas por el usuario
    output_decisions = Column(JSON, nullable=True)
    output_resources = Column(Text, nullable=True)
    output_objectives = Column(JSON, nullable=True)
    minutes_pdf_path = Column(String, nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))

    approved_by = relationship("User", foreign_keys=[approved_by_id])


# ---------- SOA VERSION (ISO 27001 cl. 6.1.3) ----------

class SoAVersion(Base):
    """Version aprobada de la Declaracion de Aplicabilidad — snapshot inmutable."""
    __tablename__ = "soa_versions"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    version = Column(String(16))                      # 2024-v1
    status = Column(String(20), default="draft")      # draft|under_review|approved|superseded
    submitted_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_notes = Column(Text, nullable=True)
    snapshot_json = Column(JSON, nullable=True)   # snapshot completo del SoA (inmutable)
    pdf_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    submitted_by = relationship("User", foreign_keys=[submitted_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])


# ---------- NIS2 NOTIFICATION (NIS2 Art. 23) ----------

class NIS2Notification(Base):
    """Notificacion NIS2 a la autoridad competente (3 fases: early/initial/final)."""
    __tablename__ = "nis2_notifications"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"))
    stage = Column(String(20))            # early_warning|initial_report|final_report
    deadline_at = Column(DateTime)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    recipient_authority = Column(String, default="INCIBE-CERT")
    notification_ref = Column(String, nullable=True)
    content_json = Column(JSON, nullable=True)   # campos del formulario
    pdf_path = Column(String, nullable=True)
    status = Column(String(20), default="pending")   # pending|submitted|acknowledged|overdue
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    incident = relationship("Incident")
    submitted_by = relationship("User", foreign_keys=[submitted_by_id])


# ---------- AUDIT CHECKLIST (ISO 27001 cl. 9.2) ----------

class AuditChecklist(Base):
    """Item de checklist de auditoria — generado automaticamente desde SoA."""
    __tablename__ = "audit_checklists"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    audit_id = Column(Integer, ForeignKey("audit_programs.id"))
    control_id = Column(Integer, ForeignKey("controls.id"), nullable=True)
    iso_clause = Column(String(32), nullable=True)
    question = Column(Text)
    expected_evidence = Column(Text, nullable=True)
    response = Column(String(20), default="pending")  # pending|conformant|minor_nc|major_nc|na
    evidence_ref = Column(String, nullable=True)
    auditor_notes = Column(Text, nullable=True)
    nc_created_id = Column(Integer, ForeignKey("nonconformities.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    audit = relationship("AuditProgram")
    control = relationship("Control")
    nc_created = relationship("NonConformity", foreign_keys=[nc_created_id])


# ---------- CHANGE MANAGEMENT (ISO 27001 cl. 6.3) ----------

class ChangeRequest(Base):
    """Solicitud de cambio controlado en el SGSI — ISO 27001 cl. 6.3."""
    __tablename__ = "change_requests"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    code = Column(String(16))              # CHG-0001
    title = Column(String(255))
    change_type = Column(String(32))       # policy|control|asset|process|infrastructure|other
    description = Column(Text)
    business_reason = Column(Text)
    affected_asset_ids = Column(JSON)
    affected_control_ids = Column(JSON)
    affected_policy_ids = Column(JSON)
    risk_impact = Column(String(16))       # none|low|medium|high
    risk_assessment = Column(Text)
    status = Column(String(20), default="draft")  # draft|under_review|approved|rejected|implemented|verified
    requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    planned_date = Column(DateTime, nullable=True)
    implemented_at = Column(DateTime, nullable=True)
    verification_notes = Column(Text, nullable=True)
    verified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))

    requested_by = relationship("User", foreign_keys=[requested_by_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    verified_by = relationship("User", foreign_keys=[verified_by_id])


# ---------- SCHEDULED REPORTS ----------

class ReportSchedule(Base):
    """Programacion automatica de envio de informes PDF/Excel."""
    __tablename__ = "report_schedules"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    report_type = Column(String(64))       # risk_register|soa|executive_dashboard|committee_minutes
    frequency = Column(String(16))         # weekly|monthly|quarterly
    day_of_month = Column(Integer, nullable=True)
    recipients = Column(JSON)              # [email, ...]
    include_ai_analysis = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    last_sent_at = Column(DateTime, nullable=True)
    next_scheduled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------- BCP/BIA (NIS2 Art. 21.2(b) + ISO 27001 A.5.29) ----------

class BusinessProcess(Base):
    """Proceso de negocio con RTO/RPO para BIA (ISO 22301 cl. 8.2)."""
    __tablename__ = "business_processes"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    criticality = Column(String(16), default="medium")   # critical|high|medium|low
    priority = Column(Integer, nullable=True)
    rto_hours = Column(Integer, nullable=True)     # Recovery Time Objective
    rpo_hours = Column(Integer, nullable=True)     # Recovery Point Objective
    mtpd_hours = Column(Integer, nullable=True)    # Maximum Tolerable Period of Disruption
    mbco = Column(Text, nullable=True)             # Minimum Business Continuity Objective
    # Impactos BIA: 0=ninguno, 1=bajo, 2=medio, 3=alto
    financial_impact = Column(Integer, nullable=True)
    reputational_impact = Column(Integer, nullable=True)
    legal_impact = Column(Integer, nullable=True)
    operational_impact = Column(Integer, nullable=True)
    min_recovery_staff = Column(Integer, nullable=True)
    vital_records = Column(JSON, nullable=True)
    activation_criteria = Column(Text, nullable=True)
    alternative_procedure = Column(Text, nullable=True)
    it_systems = Column(JSON, nullable=True)
    facilities = Column(JSON, nullable=True)
    escalation_contacts = Column(JSON, nullable=True)
    asset_ids = Column(JSON, nullable=True)
    supplier_ids = Column(JSON, nullable=True)
    last_tested_at = Column(DateTime, nullable=True)
    test_result = Column(String(16), nullable=True)   # passed|partial|failed
    bcp_document_path = Column(String, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    recovery_owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))

    # BIA: campos normativos adicionales
    ens_category = Column(String(8), nullable=True)        # ALTA | MEDIA | BÁSICA
    cost_per_hour = Column(Float, nullable=True)           # Coste indisponibilidad €/h
    impact_1h = Column(Integer, nullable=True)             # Impacto a 1h  (0=bajo,1=medio,2=alto)
    impact_24h = Column(Integer, nullable=True)            # Impacto a 24h
    impact_7d = Column(Integer, nullable=True)             # Impacto a 7 dias
    bia_version = Column(String(16), nullable=True)        # Version del BIA (ej. "v1.0")
    bia_review_date = Column(DateTime, nullable=True)      # Proxima revision del BIA
    location_id = Column(Integer, ForeignKey("bcm_locations.id"), nullable=True)

    owner = relationship("User", foreign_keys=[owner_id])
    recovery_owner = relationship("User", foreign_keys=[recovery_owner_id])


class BCPTest(Base):
    """Test de continuidad de negocio programado/realizado."""
    __tablename__ = "bcp_tests"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    code = Column(String(16))              # BCT-0001
    test_type = Column(String(16))         # tabletop|simulation|full_test
    process_ids = Column(JSON)
    scheduled_at = Column(DateTime)
    conducted_at = Column(DateTime, nullable=True)
    objective = Column(Text, nullable=True)
    scope_description = Column(Text, nullable=True)
    participants = Column(JSON, nullable=True)
    facilitator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    result = Column(String(16), nullable=True)   # passed|partial|failed
    findings = Column(Text, nullable=True)
    lessons_learned = Column(Text, nullable=True)
    improvement_actions = Column(Text, nullable=True)
    evidence_doc_ids = Column(JSON, nullable=True)
    nc_ids = Column(JSON, nullable=True)
    # Frecuencia planificada y valores reales medidos en el ejercicio
    frequency = Column(String(16), nullable=True)          # mensual|trimestral|semestral|anual
    rto_achieved_hours = Column(Integer, nullable=True)    # RTO real conseguido en el test
    rpo_achieved_hours = Column(Integer, nullable=True)    # RPO real conseguido en el test
    location_id = Column(Integer, ForeignKey("bcm_locations.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    facilitator = relationship("User", foreign_keys=[facilitator_id])


class BCPDependency(Base):
    """Dependencia de un proceso BCP (ISO 22301 cl. 8.2 — recursos necesarios)."""
    __tablename__ = "bcp_dependencies"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    process_id = Column(Integer, ForeignKey("business_processes.id"), nullable=False)
    dependency_type = Column(String(32))   # IT_system|personnel|facility|supplier|utility|communication|transport|external_service
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    qty_normal = Column(Integer, nullable=True)
    qty_recovery = Column(Integer, nullable=True)
    rto_hours = Column(Integer, nullable=True)
    is_critical = Column(Boolean, default=False)
    alternative = Column(Text, nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    process = relationship("BusinessProcess", foreign_keys=[process_id])
    depends_on_process_id = Column(Integer, ForeignKey("business_processes.id"), nullable=True)
    # FK al proceso del que depende este proceso. Solo para dependency_type == "process"
    recovery_sequence = Column(Integer, nullable=True)
    # Orden en la secuencia de recuperacion (1 = primero que debe estar disponible)
    notes = Column(Text, nullable=True)
    # Notas adicionales sobre esta dependencia

    supplier = relationship("Supplier", foreign_keys=[supplier_id])
    # v3.5.2 — tabla de interconexiones tecnicas (ISO 22301 §8.2)
    connection_type     = Column(String(32), nullable=True)  # API|database|network|file_transfer|manual|messaging
    protocol            = Column(String(32), nullable=True)  # HTTPS|SQL|SMB|SFTP|AMQP|...
    data_direction      = Column(String(8),  nullable=True)  # in|out|both
    data_classification = Column(String(32), nullable=True)  # public|internal|confidential|strictly_confidential


class BCPStrategy(Base):
    """Estrategia de recuperación BCP (ISO 22301 cl. 8.3)."""
    __tablename__ = "bcp_strategies"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    process_id = Column(Integer, ForeignKey("business_processes.id"), nullable=True)
    strategy_type = Column(String(32))   # hot_site|cold_site|warm_site|work_from_home|outsourcing|manual_workaround|dual_site|cloud_failover
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    estimated_cost = Column(Float, nullable=True)
    implementation_status = Column(String(32), default="planned")  # planned|in_progress|implemented|tested
    responsible_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    target_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    process = relationship("BusinessProcess", foreign_keys=[process_id])
    responsible = relationship("User", foreign_keys=[responsible_id])
    # v3.5.2 — configuracion tecnica IT y monitorizacion
    it_config          = Column(JSON, nullable=True)
    # {availability_pct, compute_vcpus, ram_gb, storage_tb, failover_type (none|active-passive|active-active),
    #  virtualization_type, min_hosts, backup_rpo_hours, backup_rto_hours, backup_retention_days, offsite_location}
    monitoring_config  = Column(JSON, nullable=True)
    # {monitoring_tool, threshold_cpu_pct, threshold_mem_pct, alert_email,
    #  maintenance_window, security_patch_days, feature_update_days}


class BCPPlan(Base):
    """Plan de continuidad o recuperación (ISO 22301 cl. 8.4)."""
    __tablename__ = "bcp_plans"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    code = Column(String(16))              # BCP-0001 / DRP-0001
    plan_type = Column(String(32))         # bcp|drp|crp|ems|pandemic|cyber_response|supply_chain
    name = Column(String(255), nullable=False)
    version = Column(String(16), default="1.0")
    status = Column(String(32), default="draft")  # draft|under_review|approved|deprecated
    scope = Column(Text, nullable=True)
    activation_criteria = Column(Text, nullable=True)
    content_summary = Column(Text, nullable=True)
    document_id = Column(Integer, ForeignKey("ai_documents.id"), nullable=True)
    process_ids = Column(JSON, nullable=True)
    team_members = Column(JSON, nullable=True)
    review_date = Column(DateTime, nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    last_exercised_at = Column(DateTime, nullable=True)
    # Campos enriquecidos del plan
    sections = Column(JSON, nullable=True)
    # Array de secciones estructuradas: [{id, title, content, type}]
    roles_matrix = Column(JSON, nullable=True)
    # [{role_name, responsible, actions_notification, actions_recovery, actions_reconstitution}]
    contact_list = Column(JSON, nullable=True)
    # [{name, role, team, phone, email, backup_name, backup_phone}]
    system_dependencies = Column(JSON, nullable=True)
    # [{system_name, dependency_type, rto_hours, notes}]
    kpis = Column(JSON, nullable=True)
    # [{metric, target, current, status}]
    plan_owner_name = Column(String(255), nullable=True)
    # Nombre del propietario del plan
    classification = Column(String(32), nullable=True)
    # "confidential" | "internal" | "restricted"
    dr_site = Column(JSON, nullable=True)
    # DRP: {site_type, location, access_info, capacity, connectivity, rto_hours, infrastructure_notes}
    backup_policy = Column(JSON, nullable=True)
    # DRP: {rule_321, encryption, retention, offsite_location,
    #        items:[{system,backup_type,frequency,retention,rpo_covered,location,last_test_date,last_test_result}]}
    crisis_comms = Column(JSON, nullable=True)
    # {primary_channel, secondary_channel, external_channel, template_internal, template_external}
    location_id = Column(Integer, ForeignKey("bcm_locations.id"), nullable=True)
    checklist_template = Column(JSON, nullable=True)
    # v3.5.2 — campos adicionales de gestion y clasificacion
    installation_type       = Column(String(32), nullable=True)   # cloud_saas|cloud_iaas|on_prem|hybrid|enduser_device
    data_classification_level = Column(String(32), nullable=True) # public|internal|confidential|strictly_confidential
    gdpr_data               = Column(Boolean, default=False)
    affected_users_count    = Column(Integer, nullable=True)
    documentation_links     = Column(JSON, nullable=True)         # [{title, url}]
    related_documents       = Column(JSON, nullable=True)         # [{title, doc_version, valid_from}]
    authorized_activators   = Column(JSON, nullable=True)         # [{name, role, email, phone, is_deputy}]
    # [{order,title,description,action_type,action_config}]
    # action_type: manual|notify_users|create_task|log_timeline
    parent_plan_id = Column(Integer, ForeignKey("bcp_plans.id"), nullable=True)  # versioning
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # v4.0.0 — regwatch: plan requiere revision por cambio normativo
    regwatch_review_at = Column(DateTime, nullable=True)
    regwatch_pack_id = Column(Integer, ForeignKey("regwatch_change_packs.id"), nullable=True)
    # v5.5 — Risk Register link + crisis activation
    risk_ids = Column(JSON, nullable=True)               # IDs de riesgos que este BCP mitiga
    activation_status = Column(String(16), default="standby")  # standby|activated|deactivated
    activated_at = Column(DateTime, nullable=True)
    activated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    deactivated_at = Column(DateTime, nullable=True)
    activation_log = Column(JSON, nullable=True)         # [{timestamp, action, user, notes}]

    approved_by = relationship("User", foreign_keys=[approved_by_id])


class BCPExerciseProgramme(Base):
    """Programa anual de ejercicios de continuidad (ISO 22301 cl. 8.5)."""
    __tablename__ = "bcp_exercise_programmes"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    year = Column(Integer, nullable=False)
    status = Column(String(32), default="draft")   # draft|approved|completed
    overall_objective = Column(Text, nullable=True)
    exercises = Column(JSON, nullable=True)         # [{month, type, processes, objective}]
    lessons_learned = Column(Text, nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    approved_by = relationship("User", foreign_keys=[approved_by_id])


class BCPSupplierLink(Base):
    """Vinculo BCM con proveedor (ISO 22301 cl. 8.2 — cadena de suministro)."""
    __tablename__ = "bcp_supplier_links"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    process_ids = Column(JSON, nullable=True)
    criticality = Column(String(16), default="medium")  # critical|high|medium|low
    rto_impact_hours = Column(Integer, nullable=True)
    has_contingency_plan = Column(Boolean, default=False)
    contingency_description = Column(Text, nullable=True)
    alternative_supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    contract_sla_hours = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    last_review_date = Column(DateTime, nullable=True)

    supplier = relationship("Supplier", foreign_keys=[supplier_id])
    alternative_supplier = relationship("Supplier", foreign_keys=[alternative_supplier_id])


# ══════════════════════════════════════════════════════════════════════════════
# BCM EXPANSION — Localizaciones, Evidencias, Activaciones, ITDR
# ══════════════════════════════════════════════════════════════════════════════

class BCMLocation(Base):
    """
    Localización BCM — sede, filial o unidad organizativa con BCM independiente.
    Árbol jerárquico dentro de la misma organización: parent_id=None = nivel corporativo.
    """
    __tablename__ = "bcm_locations"
    id                    = Column(Integer, primary_key=True)
    organization_id       = Column(Integer, ForeignKey("organizations.id"), index=True)
    parent_id             = Column(Integer, ForeignKey("bcm_locations.id"), nullable=True)
    code                  = Column(String(16))
    name                  = Column(String(255), nullable=False)
    description           = Column(Text, nullable=True)
    address               = Column(Text, nullable=True)
    country               = Column(String(64), nullable=True)
    timezone              = Column(String(64), nullable=True)
    bcm_manager_id        = Column(Integer, ForeignKey("users.id"), nullable=True)
    recovery_site_type    = Column(String(16), nullable=True)
    recovery_site_description = Column(Text, nullable=True)
    alternate_location_id = Column(Integer, ForeignKey("bcm_locations.id"), nullable=True)
    is_active             = Column(Boolean, default=True)
    capacity_details      = Column(JSON, nullable=True)
    # {servers, ram_gb, storage_tb, networking, pre_installed_systems, notes}
    created_at            = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at            = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))

    parent           = relationship("BCMLocation", foreign_keys=[parent_id],
                                    remote_side="BCMLocation.id", backref="children")
    alternate        = relationship("BCMLocation", foreign_keys=[alternate_location_id],
                                    remote_side="BCMLocation.id")
    bcm_manager      = relationship("User", foreign_keys=[bcm_manager_id])


class BCMEvidenceItem(Base):
    """Repositorio de evidencias BCM — cifrado con Fernet, hash SHA-256 para integridad."""
    __tablename__ = "bcm_evidence_items"
    id              = Column(Integer, primary_key=True)
    linked_activation_id = Column(Integer, ForeignKey("bcm_activations.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    location_id     = Column(Integer, ForeignKey("bcm_locations.id"), nullable=True)
    evidence_type   = Column(String(32), nullable=False)
    title           = Column(String(255), nullable=False)
    description     = Column(Text, nullable=True)
    linked_test_id  = Column(Integer, ForeignKey("bcp_tests.id"), nullable=True)
    linked_plan_id  = Column(Integer, ForeignKey("bcp_plans.id"), nullable=True)
    linked_process_id = Column(Integer, ForeignKey("business_processes.id"), nullable=True)
    file_path       = Column(String, nullable=True)
    file_name       = Column(String(255), nullable=True)
    file_size       = Column(Integer, nullable=True)
    mime_type       = Column(String(128), nullable=True)
    sha256_hash     = Column(String(64), nullable=True)
    tags            = Column(JSON, nullable=True)
    review_date     = Column(DateTime, nullable=True)
    is_current      = Column(Boolean, default=True)
    uploaded_by_id  = Column(Integer, ForeignKey("users.id"))
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    uploader        = relationship("User", foreign_keys=[uploaded_by_id])


class BCMTestRecommendation(Base):
    """Test sugerido automáticamente — por el motor de reglas o tras un incidente/CVE."""
    __tablename__ = "bcm_test_recommendations"
    id              = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    location_id     = Column(Integer, ForeignKey("bcm_locations.id"), nullable=True)
    plan_id         = Column(Integer, ForeignKey("bcp_plans.id"), nullable=True)
    process_id      = Column(Integer, ForeignKey("business_processes.id"), nullable=True)
    recommended_test_type = Column(String(32))
    reason          = Column(Text)
    recommended_date = Column(DateTime, nullable=True)
    priority        = Column(String(16), default="medium")
    trigger         = Column(String(32))
    status          = Column(String(20), default="pending")
    accepted_by_id  = Column(Integer, ForeignKey("users.id"), nullable=True)
    resulting_test_id = Column(Integer, ForeignKey("bcp_tests.id"), nullable=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    plan    = relationship("BCPPlan", foreign_keys=[plan_id])
    process = relationship("BusinessProcess", foreign_keys=[process_id])


class BCPTestRunbook(Base):
    """Runbook paso a paso para un ejercicio BCM. Generado por IA o manual."""
    __tablename__ = "bcp_test_runbooks"
    id              = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    location_id     = Column(Integer, ForeignKey("bcm_locations.id"), nullable=True)
    plan_id         = Column(Integer, ForeignKey("bcp_plans.id"), nullable=True)
    test_id         = Column(Integer, ForeignKey("bcp_tests.id"), nullable=True)
    title           = Column(String(255), nullable=False)
    scenario        = Column(Text, nullable=True)
    test_type       = Column(String(32))
    steps           = Column(JSON)
    total_estimated_minutes = Column(Integer, nullable=True)
    generated_by_ai = Column(Boolean, default=False)
    # Campos operacionales DRP (ISO 22301 §8.4.3)
    runbook_type          = Column(String(32), nullable=True)   # recovery|failover|communication|general
    activation_condition  = Column(Text, nullable=True)         # Condicion que activa este procedimiento
    credentials_vault_ref = Column(Text, nullable=True)         # Referencia a boveda de credenciales
    success_criteria      = Column(Text, nullable=True)         # Criterio de exito / verificacion
    responsible_name      = Column(String(255), nullable=True)  # Titular del procedimiento
    backup_responsible_name = Column(String(255), nullable=True) # Suplente
    created_by_id   = Column(Integer, ForeignKey("users.id"))
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))


class BCPRecoverySequence(Base):
    """Secuencia ordenada de recuperación de sistemas IT para un DRP."""
    __tablename__ = "bcp_recovery_sequences"
    id              = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    location_id     = Column(Integer, ForeignKey("bcm_locations.id"), nullable=True)
    plan_id         = Column(Integer, ForeignKey("bcp_plans.id"), nullable=True)
    name            = Column(String(255), nullable=False)
    sequence_items  = Column(JSON)
    activation_status = Column(JSON, nullable=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))


class BCMActivation(Base):
    """Activación real de un plan BCM durante un incidente. Sala de crisis virtual."""
    __tablename__ = "bcm_activations"
    id                  = Column(Integer, primary_key=True)
    organization_id     = Column(Integer, ForeignKey("organizations.id"), index=True)
    location_id         = Column(Integer, ForeignKey("bcm_locations.id"), nullable=True)
    code                = Column(String(16))
    title               = Column(String(255), nullable=False)
    activated_plan_ids  = Column(JSON)
    incident_id         = Column(Integer, ForeignKey("incidents.id"), nullable=True)
    status              = Column(String(20), default="active")
    activated_at        = Column(DateTime, nullable=False)
    activated_by_id     = Column(Integer, ForeignKey("users.id"))
    closed_at           = Column(DateTime, nullable=True)
    closed_by_id        = Column(Integer, ForeignKey("users.id"), nullable=True)
    situation_log       = Column(JSON, nullable=True)
    systems_status      = Column(JSON, nullable=True)
    checklist_items     = Column(JSON, nullable=True)
    # [{order,title,description,action_type,action_config,status,executed_at,executed_by,notes}]
    rto_objective_hours = Column(Integer, nullable=True)
    rto_actual_hours    = Column(Float, nullable=True)
    root_cause          = Column(Text, nullable=True)
    lessons_learned     = Column(Text, nullable=True)
    improvement_actions = Column(JSON, nullable=True)
    # Post-mortem fields
    executive_summary   = Column(Text, nullable=True)
    affected_services   = Column(JSON, nullable=True)   # [{service, impact, status}]
    ai_summary          = Column(Text, nullable=True)   # AI-generated evidence summary
    created_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at          = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))

    activated_by = relationship("User", foreign_keys=[activated_by_id])


# ---------- BCM CONTEXT (Wizard contexto para Agente IA) ----------

class BCMContext(Base):
    """Contexto organizacional BCM recopilado por el wizard — alimenta al Agente IA."""
    __tablename__ = "bcm_context"
    id                   = Column(Integer, primary_key=True)
    organization_id      = Column(Integer, ForeignKey("organizations.id"), nullable=False, unique=True)
    sector               = Column(String(100), nullable=True)
    employees_range      = Column(String(50), nullable=True)
    geographic_scope     = Column(String(50), nullable=True)   # local/national/international
    critical_infra_json  = Column(Text, nullable=True)         # JSON list
    risk_scenarios_json  = Column(Text, nullable=True)         # JSON list
    regulations_json     = Column(Text, nullable=True)         # JSON list
    incident_history     = Column(Text, nullable=True)
    rto_target           = Column(String(20), nullable=True)
    rpo_target           = Column(String(20), nullable=True)
    max_tolerable_downtime = Column(String(20), nullable=True)
    annual_loss_estimate = Column(String(50), nullable=True)
    it_architecture      = Column(Text, nullable=True)         # cloud/on-prem/hybrid + details
    key_suppliers        = Column(Text, nullable=True)         # JSON list
    wizard_completed     = Column(Boolean, default=False)
    wizard_step          = Column(Integer, default=0)
    created_at           = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at           = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))


# ---------- GDPR BREACH NOTIFICATION (GDPR Art. 33-34) ----------

class DataBreachNotification(Base):
    """Notificacion de brecha de datos — GDPR Art. 33 (AEPD) y Art. 34 (interesados)."""
    __tablename__ = "data_breach_notifications"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)
    # Art. 33 — Notificacion a AEPD (72h)
    authority_notified_at = Column(DateTime, nullable=True)
    authority_ref = Column(String, nullable=True)
    art33_justification = Column(Text, nullable=True)   # si no se notifica (excepcion)
    # Art. 34 — Notificacion a interesados
    requires_data_subject_notification = Column(Boolean, default=False)
    data_subjects_notified_at = Column(DateTime, nullable=True)
    notification_channels = Column(JSON, nullable=True)    # [email, carta, web]
    # Formulario AEPD
    breach_type = Column(JSON, nullable=True)              # confidentiality|integrity|availability
    data_categories = Column(JSON, nullable=True)
    estimated_records_affected = Column(Integer, nullable=True)
    likely_consequences = Column(Text, nullable=True)
    measures_taken = Column(Text, nullable=True)
    dpo_consulted_at = Column(DateTime, nullable=True)
    pdf_path = Column(String, nullable=True)
    status = Column(String(32), default="draft")
    # draft|submitted_authority|completed|no_notification_required
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))

    incident = relationship("Incident")


# ---------- IMPORT AUDIT & HEALTH ----------

class ImportSession(Base):
    """Histórico de sesiones de importación para auditoría y rollback."""
    __tablename__ = "import_sessions"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    session_id = Column(String(64), unique=True, index=True)  # UUID corto
    filename = Column(String(255))
    source_system = Column(String(64), nullable=True)  # leanix|cmdb|custom

    # Estadísticas
    total_rows = Column(Integer)
    created = Column(Integer)
    updated = Column(Integer)
    skipped = Column(Integer)
    errors_count = Column(Integer, default=0)

    # Integridad
    expected_processed = Column(Integer)
    actual_processed = Column(Integer)
    data_loss_detected = Column(Boolean, default=False)

    # Deduplicación
    dedup_by_external_id = Column(Integer, default=0)
    dedup_by_name = Column(Integer, default=0)

    # Status & rollback
    status = Column(String(16), default="completed")  # completed|failed|rolled_back
    error_message = Column(Text, nullable=True)
    rolled_back_at = Column(DateTime, nullable=True)
    rolled_back_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Timestamps
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    # Lineage
    mapping_notes = Column(Text, nullable=True)

    rolled_back_by = relationship("User", foreign_keys=[rolled_back_by_id])


# ---------- ENCUESTAS DISTRIBUIDAS ----------

class SurveyTemplate(Base):
    """Plantilla reutilizable de encuesta de riesgos."""
    __tablename__ = "survey_templates"
    id              = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    name            = Column(String(255), nullable=False)
    description     = Column(Text, nullable=True)
    survey_type     = Column(String(32), default="risk_assessment")
    questions       = Column(JSON, nullable=False)
    is_default      = Column(Boolean, default=False)
    created_by_id   = Column(Integer, ForeignKey("users.id"))
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))


class SurveyCampaign(Base):
    """Campaña de encuesta: un envío a uno o varios destinatarios sobre uno o varios riesgos."""
    __tablename__ = "survey_campaigns"
    id              = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    code            = Column(String(16))
    title           = Column(String(255), nullable=False)
    template_id     = Column(Integer, ForeignKey("survey_templates.id"), nullable=True)
    campaign_type   = Column(String(32), default="risk_assessment")
    scope_risk_ids  = Column(JSON, nullable=True)
    scope_asset_ids = Column(JSON, nullable=True)
    scope_control_ids = Column(JSON, nullable=True)
    questions       = Column(JSON, nullable=False)
    deadline_at     = Column(DateTime, nullable=True)
    reminder_days   = Column(Integer, default=3)
    status          = Column(String(20), default="draft")
    created_by_id   = Column(Integer, ForeignKey("users.id"))
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    closed_at       = Column(DateTime, nullable=True)
    intro_text      = Column(Text, nullable=True)
    thank_you_text  = Column(Text, nullable=True)
    show_risk_context = Column(Boolean, default=True)
    allow_comments  = Column(Boolean, default=True)


class SurveyResponse(Base):
    """Respuesta individual de un destinatario a una campaña."""
    __tablename__ = "survey_responses"
    id              = Column(Integer, primary_key=True)
    campaign_id     = Column(Integer, ForeignKey("survey_campaigns.id"), index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    respondent_name  = Column(String(255), nullable=False)
    respondent_email = Column(String(255), nullable=False)
    respondent_role  = Column(String(255), nullable=True)
    respondent_dept  = Column(String(255), nullable=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=True)
    token           = Column(String(64), unique=True, nullable=False, index=True)
    token_expires_at = Column(DateTime, nullable=False)
    status          = Column(String(20), default="pending")
    opened_at       = Column(DateTime, nullable=True)
    completed_at    = Column(DateTime, nullable=True)
    last_reminder_at = Column(DateTime, nullable=True)
    answers         = Column(JSON, nullable=True)
    general_comment = Column(Text, nullable=True)
    applied_to_risks = Column(Boolean, default=False)
    applied_at      = Column(DateTime, nullable=True)
    applied_by_id   = Column(Integer, ForeignKey("users.id"), nullable=True)
    ip_address      = Column(String(45), nullable=True)
    user_agent      = Column(String(255), nullable=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------- REGWATCH — Vigilancia Normativa Automatica ----------
# Modulo "set it and forget it": el tenant activa un toggle y RiskHub mantiene
# su catalogo normativo actualizado. Spec: RISKHUB_REGULATORY_WATCH_MODULE_SPEC.md
# Dos niveles de catalogo (§3.4): central global (estas tablas globales) +
# referencia del tenant (settings + inbox de cambios que requieren decision).

class ChangeSeverity(str, PyEnum):
    """Clasificacion de severidad de un cambio normativo (§3.3)."""
    COSMETIC = "cosmetic"           # redaccion no sustancial -> auto-apply silencioso
    CLARIFICATION = "clarification" # guidance que clarifica -> auto-apply, digest
    SUBSTANTIVE = "substantive"     # control nuevo/eliminado/modificado -> notifica
    BREAKING = "breaking"           # nueva version mayor -> wizard de migracion


class ChangeEventStatus(str, PyEnum):
    """Estado de un hallazgo del pipeline (§4.1)."""
    DETECTED = "detected"
    PARSED = "parsed"
    AI_ANALYZED = "ai_analyzed"
    PENDING_INTERNAL_REVIEW = "pending_internal_review"
    VALIDATED = "validated"
    PUBLISHED = "published"
    REJECTED = "rejected"


class InboxItemStatus(str, PyEnum):
    """Estado de un item del inbox del tenant (§4.2)."""
    PENDING = "pending"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"


class NormativeSource(Base):
    """Fuente normativa maestra (§4.1). Global, no editable por tenant."""
    __tablename__ = "regwatch_sources"
    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    framework_codes = Column(JSON, nullable=False, default=list)   # ["ISO_27001", ...]
    connector_class = Column(String(128), nullable=True)           # BaseNormativeWatcher subclass
    fetch_config_json = Column(JSON, nullable=True)                # URLs, endpoints
    polling_frequency = Column(String(16), default="weekly")       # daily|weekly|monthly
    method = Column(String(64), nullable=True)                     # "API + RSS", etc.
    is_active = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(String(32), nullable=True)            # ok|error|never
    last_run_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ChangePack(Base):
    """Conjunto de cambios atomicos agrupados por norma+fecha+severidad (§4.1)."""
    __tablename__ = "regwatch_change_packs"
    id = Column(Integer, primary_key=True)
    framework_code = Column(String(64), nullable=False, index=True)
    version_from = Column(String(64), nullable=True)
    version_to = Column(String(64), nullable=True)
    severity = Column(Enum(ChangeSeverity), default=ChangeSeverity.SUBSTANTIVE, index=True)
    title_es = Column(String(512), nullable=False)
    title_en = Column(String(512), nullable=True)
    description_es = Column(Text, nullable=True)
    description_en = Column(Text, nullable=True)
    # Cambios atomicos
    controls_added_ids = Column(JSON, nullable=True, default=list)
    controls_modified = Column(JSON, nullable=True, default=list)  # [{control_id, field, before, after}]
    controls_removed_ids = Column(JSON, nullable=True, default=list)
    controls_renumbered = Column(JSON, nullable=True, default=list)
    source_url = Column(String(1024), nullable=True)
    published_at = Column(DateTime, nullable=True)
    applied_to_catalog_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class NormativeChangeEvent(Base):
    """Cada hallazgo del pipeline (§4.1). Cola de validacion interna."""
    __tablename__ = "regwatch_change_events"
    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("regwatch_sources.id"), nullable=True, index=True)
    change_pack_id = Column(Integer, ForeignKey("regwatch_change_packs.id"), nullable=True, index=True)
    framework_code = Column(String(64), nullable=False, index=True)
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    raw_url = Column(String(1024), nullable=True)
    raw_payload_path = Column(String(512), nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)   # SHA-256 idempotencia
    severity = Column(Enum(ChangeSeverity), nullable=True)
    status = Column(Enum(ChangeEventStatus), default=ChangeEventStatus.DETECTED, index=True)
    summary_es = Column(Text, nullable=True)
    summary_en = Column(Text, nullable=True)
    ai_analysis_json = Column(JSON, nullable=True)
    ai_confidence = Column(Float, nullable=True)
    validated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    validated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    source = relationship("NormativeSource")
    change_pack = relationship("ChangePack")


class TenantRegwatchSettings(Base):
    """Configuracion de vigilancia normativa por tenant (§4.2). Una fila por org."""
    __tablename__ = "regwatch_tenant_settings"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), unique=True, nullable=False, index=True)
    is_enabled = Column(Boolean, default=False)                    # el toggle unico
    enabled_at = Column(DateTime, nullable=True)
    enabled_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    notification_email = Column(String(255), nullable=True)
    digest_frequency = Column(String(16), default="weekly")        # daily|weekly|monthly|never
    auto_apply_to_clones = Column(Boolean, default=False)
    muted_frameworks = Column(JSON, nullable=True, default=list)   # frameworks silenciados (§9)
    last_digest_sent_at = Column(DateTime, nullable=True)
    last_sweep_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class TenantChangeInboxItem(Base):
    """Item del inbox del tenant; solo se materializa si requiere atencion (§4.2)."""
    __tablename__ = "regwatch_inbox_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "change_pack_id", name="uq_regwatch_inbox_org_pack"),
    )
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    change_pack_id = Column(Integer, ForeignKey("regwatch_change_packs.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    status = Column(Enum(InboxItemStatus), default=InboxItemStatus.PENDING, index=True)
    snoozed_until = Column(DateTime, nullable=True)
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    impact_summary_json = Column(JSON, nullable=True)   # plantillas/politicas/risks afectados
    decision_json = Column(JSON, nullable=True)         # decision por elemento del wizard
    dismiss_reason = Column(Text, nullable=True)

    change_pack = relationship("ChangePack")


# ---------- RISK LEVEL CONFIG (bandas configurables por organizacion) ----------

class RiskLevelConfig(Base):
    """Configuracion de bandas de nivel de riesgo por organizacion.

    Permite al admin redefinir etiquetas, colores y umbrales de cada banda
    (bajo/medio/alto/critico) para la escala 0-8 de ISO 27005.
    Si no hay configuracion para una org se usan los defaults del motor.
    """
    __tablename__ = "risk_level_configs"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    code            = Column(String(32), nullable=False)  # low / medium / high / critical
    label           = Column(String(64), nullable=False)  # Bajo / Medio / Alto / Critico
    min_level       = Column(Integer,    nullable=False)  # 0-8 inclusive
    max_level       = Column(Integer,    nullable=False)  # 0-8 inclusive
    color           = Column(String(64), nullable=False)  # CSS var o hex
    order           = Column(Integer,    nullable=False)  # 1=menor riesgo, ..., N=mayor
