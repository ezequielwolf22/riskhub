"""Esquemas Pydantic para validacion de entrada/salida de la API."""
from datetime import datetime
from typing import Literal, Optional, Any
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import (
    AssetType, ThreatOrigin, TreatmentOption,
    RiskStatus, ControlStatus, UserRole,
    IncidentSeverity, IncidentStatus, SupplierRisk, SupplierTier, SupplierRelationship,
    VendorIssueSeverity, VendorIssueStatus, AssessmentRecommendation,
    NCSeverity, NCStatus,
    TaskStatus, TaskPriority,
    PolicyStatus, AuditType, AuditStatus, AuditFindingType,
    ProcessingLegalBasis, DPIAStatus,
    OSINTScanType, OSINTSourceType, OSINTFindingRiskLevel,
    LicenseStatus,
)


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- AUTH ----------
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"
    must_change_password: bool = False
    mfa_required: bool = False
    mfa_token: Optional[str] = None


# ---------- ORGANIZATIONS ----------
class OrganizationIn(BaseModel):
    name: str
    domain: Optional[str] = None
    plan: str = "starter"
    is_active: bool = True
    max_users: int = Field(default=10, ge=1)  # M1: ge=1 evita max_users=-1


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    plan: Optional[str] = None
    is_active: Optional[bool] = None
    max_users: Optional[int] = Field(default=None, ge=1)


class OrganizationOut(ORMBase):
    id: int
    name: str
    domain: Optional[str] = None
    plan: str
    is_active: bool
    max_users: int
    created_at: datetime
    owner_id: Optional[int] = None
    user_count: int = 0
    token_usage: int = 0


# ---------- LICENSES ----------
class LicenseIn(BaseModel):
    plan: str
    expires_at: Optional[datetime] = None
    reason: Optional[str] = None


class LicenseUpdate(BaseModel):
    plan: Optional[str] = None
    status: Optional[LicenseStatus] = None
    expires_at: Optional[datetime] = None
    reason: Optional[str] = None


class LicenseOut(ORMBase):
    id: int
    organization_id: int
    plan: str
    status: LicenseStatus
    issued_at: datetime
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    updated_by_id: Optional[int] = None


class LicenseAuditOut(ORMBase):
    id: int
    organization_id: int
    plan_old: Optional[str] = None
    plan_new: Optional[str] = None
    status_old: Optional[str] = None
    status_new: Optional[str] = None
    expires_at_old: Optional[datetime] = None
    expires_at_new: Optional[datetime] = None
    reason: Optional[str] = None
    changed_at: datetime
    changed_by_id: Optional[int] = None


# ---------- USERS ----------
class UserIn(BaseModel):
    email: EmailStr
    full_name: str
    # password es opcional: si no se provee, el backend genera una OTP automaticamente
    password: Optional[str] = Field(default=None, min_length=8)
    role: UserRole = UserRole.VIEWER
    organization_id: Optional[int] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    organization_id: Optional[int] = None


class UserOut(ORMBase):
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    risk_count: int = 0
    organization_id: Optional[int] = None
    must_change_password: bool = False
    mfa_enabled: bool = False
    # Solo se rellena cuando el admin crea un usuario con OTP generado automaticamente
    otp_password: Optional[str] = None
    otp_email_sent: Optional[bool] = None


# ---------- CONTEXT ----------
class ContextIn(BaseModel):
    organization_name: Optional[str] = None
    scope: Optional[str] = None
    boundaries: Optional[str] = None
    impact_criteria: Optional[dict] = None
    likelihood_criteria: Optional[dict] = None
    risk_acceptance_criteria: Optional[dict] = None
    risk_matrix: Optional[list[list[int]]] = None
    risk_appetite: Optional[int] = None
    active_frameworks: Optional[list[str]] = None
    ens_level: Optional[Literal["basico", "medio", "alto"]] = None  # M1: solo valores validos ENS
    methodology: Optional[Literal["iso27005", "magerit", "combined"]] = None  # M1: valores controlados


class ContextOut(ORMBase):
    id: int
    organization_name: Optional[str]
    scope: Optional[str]
    boundaries: Optional[str]
    impact_criteria: Optional[dict]
    likelihood_criteria: Optional[dict]
    risk_acceptance_criteria: Optional[dict]
    risk_matrix: Optional[list[list[int]]]
    risk_appetite: Optional[int]
    active_frameworks: Optional[list[str]] = None
    ens_level: Optional[str] = None
    methodology: Optional[str] = "iso27005"
    updated_at: datetime


# ---------- ASSETS ----------
class AssetIn(BaseModel):
    code: Optional[str] = None
    name: str
    description: Optional[str] = None
    asset_type: AssetType
    category: Optional[str] = None
    location: Optional[str] = None
    business_process: Optional[str] = None
    classification: Optional[str] = None
    value_confidentiality: int = 0
    value_integrity: int = 0
    value_availability: int = 0
    value_authenticity: int = 0
    value_accountability: int = 0
    monetary_value: Optional[float] = None
    parent_id: Optional[int] = None
    owner_ids: list[int] = []
    extra: Optional[dict] = None
    software_tags: Optional[list[str]] = None  # para correlacion CPE/CVE


class AssetOut(ORMBase):
    id: int
    code: str
    name: str
    description: Optional[str]
    asset_type: AssetType
    category: Optional[str]
    location: Optional[str]
    business_process: Optional[str]
    classification: Optional[str]
    value_confidentiality: int
    value_integrity: int
    value_availability: int
    value_authenticity: int
    value_accountability: int
    monetary_value: Optional[float]
    value_max: int
    parent_id: Optional[int]
    extra: Optional[dict]
    created_at: datetime
    updated_at: datetime
    risk_count: int = 0
    # v1.7.5 — analisis IA
    ai_risk_status: Optional[str] = None
    ai_risk_summary: Optional[dict] = None
    # v1.8.0 — agrupacion
    group_id: Optional[int] = None
    is_group_representative: bool = False
    # v2.2.5 — etiquetas software para correlacion CVE
    software_tags: Optional[list[str]] = None


# ---------- ASSET GROUPS ----------

class GroupingCriterion(BaseModel):
    id: str
    name: str
    description: str
    level: int
    enabled: bool


class AssetGroupingConfigOut(ORMBase):
    id: int
    criteria: list[GroupingCriterion]
    updated_at: Optional[datetime] = None


class AssetGroupingConfigIn(BaseModel):
    criteria: list[GroupingCriterion]


class AssetMiniOut(ORMBase):
    id: int
    code: str
    name: str
    asset_type: AssetType
    category: Optional[str] = None
    location: Optional[str] = None
    classification: Optional[str] = None
    value_confidentiality: int = 0
    value_integrity: int = 0
    value_availability: int = 0
    value_authenticity: int = 0
    value_accountability: int = 0


class AssetGroupOut(ORMBase):
    id: int
    name: str
    description: Optional[str] = None
    status: str
    criteria_snapshot: Optional[list] = None
    ai_rationale: Optional[str] = None
    representative_asset_id: Optional[int] = None
    rep_ai_status: Optional[str] = None
    rep_ai_summary: Optional[dict] = None
    member_count: int = 0
    members: list[AssetMiniOut] = []
    created_at: datetime
    updated_at: Optional[datetime] = None


class AssetGroupIn(BaseModel):
    name: str
    description: Optional[str] = None


class AssetGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class MoveAssetIn(BaseModel):
    asset_id: int
    target_group_id: Optional[int] = None  # None = desagrupar


class SplitGroupIn(BaseModel):
    asset_ids: list[int]  # activos que pasan al nuevo grupo
    new_group_name: str


# ---------- THREATS ----------
class ThreatIn(BaseModel):
    code: Optional[str] = None
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    origin: ThreatOrigin
    typical_assets: list[str] = []
    affects: list[str] = []
    catalog: str = "custom"  # iso27005 | magerit | custom


class ThreatOut(ORMBase):
    id: int
    code: str
    name: str
    description: Optional[str]
    category: Optional[str]
    origin: ThreatOrigin
    typical_assets: Optional[list[str]]
    affects: Optional[list[str]]
    is_custom: bool
    catalog: str = "iso27005"
    risk_count: int = 0


# ---------- VULNERABILITIES ----------
class VulnerabilityIn(BaseModel):
    code: Optional[str] = None
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    related_threats: list[str] = []


class VulnerabilityOut(ORMBase):
    id: int
    code: str
    name: str
    description: Optional[str]
    category: Optional[str]
    related_threats: Optional[list[str]]
    is_custom: bool
    risk_count: int = 0


# ---------- CONTROLS ----------
class ControlIn(BaseModel):
    code: Optional[str] = None
    name: str
    description: Optional[str] = None
    theme: Optional[str] = None
    control_type: list[str] = []
    properties: list[str] = []
    cybersec_concepts: list[str] = []
    operational: list[str] = []


class ControlOut(ORMBase):
    id: int
    code: str
    name: str
    description: Optional[str]
    theme: Optional[str]
    control_type: Optional[list[str]]
    properties: Optional[list[str]]
    cybersec_concepts: Optional[list[str]]
    operational: Optional[list[str]]
    is_custom: bool


class ControlImplIn(BaseModel):
    control_id: int
    name: str
    description: Optional[str] = None
    status: ControlStatus = ControlStatus.NOT_IMPLEMENTED
    maturity: int = 0
    owner_id: Optional[int] = None
    evidence: Optional[str] = None
    last_review: Optional[datetime] = None
    next_review: Optional[datetime] = None
    notes: Optional[str] = None
    inclusion_reason: Optional[str] = None
    exclusion_justification: Optional[str] = None
    evidence_refs: Optional[list[dict]] = None


class ControlImplOut(ORMBase):
    id: int
    control_id: int
    name: str
    description: Optional[str]
    status: ControlStatus
    maturity: int
    owner_id: Optional[int]
    evidence: Optional[str]
    last_review: Optional[datetime]
    next_review: Optional[datetime]
    notes: Optional[str]
    inclusion_reason: Optional[str]
    exclusion_justification: Optional[str]
    evidence_refs: Optional[list[dict]]
    soa_reviewed_at: Optional[datetime]
    soa_reviewed_by_id: Optional[int]
    control: ControlOut
    risk_count: int = 0


# ---------- RISKS ----------
class RiskIn(BaseModel):
    asset_id: int
    threat_id: int
    description: Optional[str] = None
    consequence_description: Optional[str] = None
    inherent_likelihood: int = Field(default=0, ge=0, le=4)  # M1: matriz 5x5 ISO 27005
    inherent_consequence: int = Field(default=0, ge=0, le=4)
    vulnerability_ids: list[int] = []
    control_implementation_ids: list[int] = []
    owner_id: Optional[int] = None
    treatment_option: Optional[TreatmentOption] = None
    treatment_plan: Optional[str] = None
    treatment_due_date: Optional[datetime] = None
    # Campos MAGERIT v3 (opcionales — solo cuando methodology=magerit|combined)
    magerit_dimension: Optional[str] = None   # D|I|C|A|T
    degradation_pct: Optional[int] = None     # 0-100


class RiskUpdate(BaseModel):
    description: Optional[str] = None
    consequence_description: Optional[str] = None
    inherent_likelihood: Optional[int] = Field(default=None, ge=0, le=4)
    inherent_consequence: Optional[int] = Field(default=None, ge=0, le=4)
    vulnerability_ids: Optional[list[int]] = None
    control_implementation_ids: Optional[list[int]] = None
    owner_id: Optional[int] = None
    treatment_option: Optional[TreatmentOption] = None
    treatment_plan: Optional[str] = None
    treatment_due_date: Optional[datetime] = None
    status: Optional[RiskStatus] = None
    acceptance_justification: Optional[str] = None
    next_review: Optional[datetime] = None
    # Campos MAGERIT v3
    magerit_dimension: Optional[str] = None
    degradation_pct: Optional[int] = None


class RiskOut(ORMBase):
    id: int
    code: str
    asset_id: int
    threat_id: int
    description: Optional[str]
    consequence_description: Optional[str]
    inherent_likelihood: int
    inherent_consequence: int
    inherent_level: int
    residual_likelihood: int
    residual_consequence: int
    residual_level: int
    status: RiskStatus
    owner_id: Optional[int]
    treatment_option: Optional[TreatmentOption]
    treatment_plan: Optional[str]
    treatment_due_date: Optional[datetime]
    accepted_by_id: Optional[int]
    accepted_at: Optional[datetime]
    acceptance_justification: Optional[str]
    created_at: datetime
    updated_at: datetime
    next_review: Optional[datetime]
    # v1.7.5 — IA generado
    ai_generated: bool = False
    ai_rationale: Optional[str] = None
    # MAGERIT v3
    magerit_dimension: Optional[str] = None
    degradation_pct: Optional[int] = None
    magerit_impact: Optional[float] = None
    asset: AssetOut
    threat: ThreatOut


# ---------- IMPORT ----------
class ImportPreviewRow(BaseModel):
    row: int
    data: dict
    valid: bool
    errors: list[str] = []


class ImportResult(BaseModel):
    total: int
    created: int
    updated: int
    skipped: int
    errors: list[str] = []


# ---------- QUESTIONNAIRES ----------
class Question(BaseModel):
    id: str
    text: str
    type: str = "yes_no"  # yes_no | single_select | multi_select | scale_0_4
    options: list[str] = []
    # mapping de respuestas a amenazas / vulnerabilidades / valoraciones
    triggers: dict = {}


class QuestionnaireIn(BaseModel):
    name: str
    description: Optional[str] = None
    questions: list[Question]


class QuestionnaireOut(ORMBase):
    id: int
    name: str
    description: Optional[str]
    questions: list[Question]
    created_at: datetime


class QuestionnaireResponseIn(BaseModel):
    questionnaire_id: int
    asset_id: Optional[int] = None
    answers: dict   # {question_id: answer}


class QuestionnaireResponseOut(ORMBase):
    id: int
    questionnaire_id: int
    asset_id: Optional[int]
    respondent_id: int
    answers: dict
    generated_risks: Optional[list[str]]
    submitted_at: datetime


# ---------- INCIDENTS ----------
class IncidentIn(BaseModel):
    title: str
    description: Optional[str] = None
    severity: IncidentSeverity = IncidentSeverity.P3
    status: IncidentStatus = IncidentStatus.OPEN
    detected_at: Optional[datetime] = None
    nis2_notification_required: bool = False
    # C1: nis2_notification_sent_at eliminado del schema de entrada — solo se escribe
    # via POST /incidents/{id}/notify-nis2 para garantizar integridad del registro NIS2
    gdpr_notification_required: bool = False
    affected_systems: list[str] = []
    affected_asset_ids: list[int] = []
    related_risk_ids: list[int] = []
    root_cause: Optional[str] = None
    response_actions: Optional[str] = None
    lessons_learned: Optional[str] = None
    owner_id: Optional[int] = None


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[IncidentSeverity] = None
    status: Optional[IncidentStatus] = None
    detected_at: Optional[datetime] = None
    contained_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    nis2_notification_required: Optional[bool] = None
    # C1: nis2_notification_sent_at no editable directamente — endpoint dedicado notify-nis2
    gdpr_notification_required: Optional[bool] = None
    affected_systems: Optional[list[str]] = None
    affected_asset_ids: Optional[list[int]] = None
    related_risk_ids: Optional[list[int]] = None
    root_cause: Optional[str] = None
    response_actions: Optional[str] = None
    lessons_learned: Optional[str] = None
    owner_id: Optional[int] = None


class IncidentOut(ORMBase):
    id: int
    code: str
    title: str
    description: Optional[str]
    severity: IncidentSeverity
    status: IncidentStatus
    detected_at: Optional[datetime]
    contained_at: Optional[datetime]
    resolved_at: Optional[datetime]
    nis2_notification_required: bool
    nis2_notification_sent_at: Optional[datetime]
    gdpr_notification_required: bool
    affected_systems: Optional[list[str]]
    affected_asset_ids: Optional[list[int]]
    related_risk_ids: Optional[list[int]]
    root_cause: Optional[str]
    response_actions: Optional[str]
    lessons_learned: Optional[str]
    owner_id: Optional[int]
    created_at: datetime
    updated_at: datetime


# ---------- SUPPLIERS ----------
class SupplierIn(BaseModel):
    name: str
    category: Optional[str] = None
    description: Optional[str] = None
    services: Optional[str] = None
    risk_level: SupplierRisk = SupplierRisk.MEDIUM
    is_critical: bool = False
    certifications: list[str] = []
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contract_ref: Optional[str] = None
    contract_expiry: Optional[datetime] = None
    last_assessment_at: Optional[datetime] = None
    next_assessment_at: Optional[datetime] = None
    score: int = Field(default=50, ge=0, le=100)  # M1: 0-100
    notes: Optional[str] = None
    owner_id: Optional[int] = None
    # ---- TPRM ----
    vendor_type: Optional[str] = None
    relationship_status: Optional[SupplierRelationship] = None
    data_sensitivity: Optional[int] = Field(default=None, ge=1, le=5)
    data_volume: Optional[int] = Field(default=None, ge=1, le=5)
    system_access_type: Optional[str] = None
    business_criticality: Optional[int] = Field(default=None, ge=1, le=5)
    geographic_risk: Optional[int] = Field(default=None, ge=1, le=5)
    is_data_processor: Optional[bool] = None
    processes_personal_data: Optional[bool] = None
    cross_border_transfers: Optional[bool] = None
    is_nis2: Optional[bool] = None
    is_dora: Optional[bool] = None
    is_ens: Optional[bool] = None
    country_code: Optional[str] = None
    website: Optional[str] = None
    tax_id: Optional[str] = None
    annual_spend: Optional[float] = None


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    services: Optional[str] = None
    risk_level: Optional[SupplierRisk] = None
    is_critical: Optional[bool] = None
    certifications: Optional[list[str]] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contract_ref: Optional[str] = None
    contract_expiry: Optional[datetime] = None
    last_assessment_at: Optional[datetime] = None
    next_assessment_at: Optional[datetime] = None
    score: Optional[int] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = None
    owner_id: Optional[int] = None
    # ---- TPRM ----
    relationship_status: Optional[SupplierRelationship] = None
    vendor_type: Optional[str] = None
    data_sensitivity: Optional[int] = Field(default=None, ge=1, le=5)
    data_volume: Optional[int] = Field(default=None, ge=1, le=5)
    system_access_type: Optional[str] = None
    business_criticality: Optional[int] = Field(default=None, ge=1, le=5)
    geographic_risk: Optional[int] = Field(default=None, ge=1, le=5)
    control_effectiveness: Optional[int] = Field(default=None, ge=0, le=100)
    is_data_processor: Optional[bool] = None
    processes_personal_data: Optional[bool] = None
    cross_border_transfers: Optional[bool] = None
    is_nis2: Optional[bool] = None
    is_dora: Optional[bool] = None
    is_ens: Optional[bool] = None
    country_code: Optional[str] = None
    website: Optional[str] = None
    tax_id: Optional[str] = None
    annual_spend: Optional[float] = None
    parent_supplier_id: Optional[int] = None
    nth_party_depth: Optional[int] = None


class SupplierOut(ORMBase):
    id: int
    code: str
    name: str
    category: Optional[str]
    description: Optional[str]
    services: Optional[str]
    risk_level: SupplierRisk
    is_critical: bool
    certifications: Optional[list[str]]
    contact_name: Optional[str]
    contact_email: Optional[str]
    contract_ref: Optional[str]
    contract_expiry: Optional[datetime]
    last_assessment_at: Optional[datetime]
    next_assessment_at: Optional[datetime]
    score: int
    notes: Optional[str]
    owner_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    # ---- TPRM ----
    tier: Optional[SupplierTier] = None
    relationship_status: Optional[SupplierRelationship] = None
    vendor_type: Optional[str] = None
    data_sensitivity: Optional[int] = None
    data_volume: Optional[int] = None
    system_access_type: Optional[str] = None
    business_criticality: Optional[int] = None
    geographic_risk: Optional[int] = None
    inherent_risk_score: Optional[int] = None
    control_effectiveness: Optional[int] = None
    residual_risk_score: Optional[int] = None
    is_data_processor: Optional[bool] = None
    processes_personal_data: Optional[bool] = None
    cross_border_transfers: Optional[bool] = None
    is_nis2: Optional[bool] = None
    is_dora: Optional[bool] = None
    is_ens: Optional[bool] = None
    country_code: Optional[str] = None
    website: Optional[str] = None
    tax_id: Optional[str] = None
    annual_spend: Optional[float] = None
    parent_supplier_id: Optional[int] = None
    nth_party_depth: Optional[int] = None


# ---------- NON-CONFORMITIES ----------
class NonConformityIn(BaseModel):
    title: str
    description: Optional[str] = None
    source: Optional[str] = None
    severity: NCSeverity = NCSeverity.MINOR
    iso_clause: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    due_date: Optional[datetime] = None
    evidence: Optional[str] = None
    owner_id: Optional[int] = None
    related_control_id: Optional[int] = None
    related_risk_id: Optional[int] = None


class NonConformityUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    severity: Optional[NCSeverity] = None
    status: Optional[NCStatus] = None
    iso_clause: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    due_date: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    evidence: Optional[str] = None
    owner_id: Optional[int] = None
    verifier_id: Optional[int] = None
    related_control_id: Optional[int] = None
    related_risk_id: Optional[int] = None


class NonConformityOut(ORMBase):
    id: int
    code: str
    title: str
    description: Optional[str]
    source: Optional[str]
    severity: NCSeverity
    status: NCStatus
    iso_clause: Optional[str]
    root_cause: Optional[str]
    corrective_action: Optional[str]
    due_date: Optional[datetime]
    closed_at: Optional[datetime]
    evidence: Optional[str]
    owner_id: Optional[int]
    verifier_id: Optional[int]
    related_control_id: Optional[int]
    related_risk_id: Optional[int]
    created_at: datetime
    updated_at: datetime


# ---------- POLICIES ----------
class PolicyIn(BaseModel):
    title: str
    version: str = "1.0"
    category: Optional[str] = None
    status: PolicyStatus = PolicyStatus.DRAFT
    scope: Optional[str] = None
    content: Optional[str] = None
    iso_clauses: list[str] = []
    review_date: Optional[datetime] = None
    owner_id: Optional[int] = None


class PolicyUpdate(BaseModel):
    title: Optional[str] = None
    version: Optional[str] = None
    category: Optional[str] = None
    status: Optional[PolicyStatus] = None
    scope: Optional[str] = None
    content: Optional[str] = None
    iso_clauses: Optional[list[str]] = None
    review_date: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    owner_id: Optional[int] = None
    approved_by_id: Optional[int] = None
    review_cycle_months: Optional[int] = None


class PolicyOut(ORMBase):
    id: int
    code: str
    title: str
    version: str
    category: Optional[str]
    status: PolicyStatus
    scope: Optional[str]
    content: Optional[str]
    iso_clauses: Optional[list[str]]
    review_date: Optional[datetime]
    approved_at: Optional[datetime]
    owner_id: Optional[int]
    approved_by_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    # v1.7.4 — documento origen e ciclo de revision
    source_document_id: Optional[int] = None
    review_cycle_months: Optional[int] = None


# ---------- AUDIT FINDINGS ----------
class AuditFindingIn(BaseModel):
    finding_type: AuditFindingType = AuditFindingType.MINOR_NC
    title: str
    description: Optional[str] = None
    evidence: Optional[str] = None
    iso_clause: Optional[str] = None
    recommendation: Optional[str] = None
    nonconformity_id: Optional[int] = None


class AuditFindingOut(ORMBase):
    id: int
    audit_id: int
    finding_type: AuditFindingType
    title: str
    description: Optional[str]
    evidence: Optional[str]
    iso_clause: Optional[str]
    recommendation: Optional[str]
    nonconformity_id: Optional[int]
    created_at: datetime


# ---------- AUDIT PROGRAMS ----------
class AuditProgramIn(BaseModel):
    title: str
    audit_type: AuditType = AuditType.INTERNAL
    scope: Optional[str] = None
    objectives: Optional[str] = None
    criteria: Optional[str] = None
    auditor_lead: Optional[str] = None
    auditor_team: list[str] = []
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    owner_id: Optional[int] = None


class AuditProgramUpdate(BaseModel):
    title: Optional[str] = None
    audit_type: Optional[AuditType] = None
    status: Optional[AuditStatus] = None
    scope: Optional[str] = None
    objectives: Optional[str] = None
    criteria: Optional[str] = None
    auditor_lead: Optional[str] = None
    auditor_team: Optional[list[str]] = None
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    conclusion: Optional[str] = None
    owner_id: Optional[int] = None


class AuditProgramOut(ORMBase):
    id: int
    code: str
    title: str
    audit_type: AuditType
    status: AuditStatus
    scope: Optional[str]
    objectives: Optional[str]
    criteria: Optional[str]
    auditor_lead: Optional[str]
    auditor_team: Optional[list[str]]
    planned_start: Optional[datetime]
    planned_end: Optional[datetime]
    actual_start: Optional[datetime]
    actual_end: Optional[datetime]
    conclusion: Optional[str]
    owner_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    findings: list[AuditFindingOut] = []


# ---------- TREATMENT TASKS ----------
class TaskIn(BaseModel):
    title: str
    description: Optional[str] = None
    risk_id: Optional[int] = None
    assigned_to_id: Optional[int] = None
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: Optional[datetime] = None
    notes: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    risk_id: Optional[int] = None
    assigned_to_id: Optional[int] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = None


class TaskOut(ORMBase):
    id: int
    code: str
    title: str
    description: Optional[str]
    risk_id: Optional[int]
    assigned_to_id: Optional[int]
    created_by_id: Optional[int]
    status: TaskStatus
    priority: TaskPriority
    due_date: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    risk: Optional["RiskOut"] = None
    assigned_to: Optional["UserOut"] = None


# ---------- SUPPLIER QUESTIONNAIRES (M4) ----------
class SupplierQuestionnaireCreate(BaseModel):
    supplier_id: int
    title: str
    notes: Optional[str] = None
    expires_at: Optional[datetime] = None
    template_code: Optional[str] = None       # TPRM: plantilla del sistema a usar
    custom_template_id: Optional[int] = None  # TPRM: plantilla personalizada (editable) a usar
    questions: Optional[list[dict]] = None    # TPRM: preguntas ad-hoc (override de la plantilla)


# ---------- TPRM: PLANTILLAS EDITABLES ----------
class TPRMTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    framework_codes: Optional[list[str]] = None
    questions: Optional[list[dict]] = None
    from_system_code: Optional[str] = None   # clona una plantilla del sistema


class TPRMTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    framework_codes: Optional[list[str]] = None
    questions: Optional[list[dict]] = None


class TPRMTemplateOut(ORMBase):
    id: int
    name: str
    description: Optional[str]
    framework_codes: Optional[list[str]]
    questions: Optional[list[dict]]
    created_from: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None


class SupplierQuestionnaireOut(ORMBase):
    id: int
    code: str
    supplier_id: int
    supplier_name: Optional[str] = None
    title: str
    token: str
    template_code: Optional[str] = None
    questions: Optional[list[dict]]
    answers: Optional[dict]
    score: Optional[int]
    submitted_at: Optional[datetime]
    expires_at: Optional[datetime]
    notes: Optional[str]
    evidence: Optional[dict] = None
    ai_review: Optional[dict] = None
    ai_reviewed_at: Optional[datetime] = None
    major_nc: Optional[int] = None
    minor_nc: Optional[int] = None
    residual_risk_level: Optional[str] = None
    phase: Optional[str] = None
    parent_assessment_id: Optional[int] = None
    next_questionnaire_id: Optional[int] = None
    created_at: datetime


# ---------- TPRM: VENDOR ASSESSMENTS & ISSUES ----------
class VendorAssessmentCreate(BaseModel):
    supplier_id: int
    assessment_type: str = "direct"   # risk_analysis | direct
    template_code: Optional[str] = None           # para tipo direct: plantilla del sistema
    custom_template_id: Optional[int] = None      # para tipo direct: plantilla personalizada
    period_label: Optional[str] = None
    valid_until: Optional[datetime] = None
    notes: Optional[str] = None
    email_subject: Optional[str] = None           # asunto personalizado
    email_message: Optional[str] = None           # cuerpo personalizado (texto plano)


class VendorAssessmentUpdate(BaseModel):
    period_label: Optional[str] = None
    summary: Optional[str] = None
    valid_until: Optional[datetime] = None
    control_effectiveness_score: Optional[int] = Field(default=None, ge=0, le=100)


class VendorAssessmentDecide(BaseModel):
    decision: str    # approve | approve_with_conditions | reject | request_more_info
    notes: Optional[str] = None


class VendorAssessmentOut(ORMBase):
    id: int
    code: str
    supplier_id: int
    supplier_name: Optional[str] = None
    assessment_type: Optional[str] = "direct"
    assessment_date: datetime
    period_label: Optional[str]
    inherent_risk_score: Optional[int]
    inherent_risk_level: Optional[str]
    control_effectiveness_score: Optional[int]
    residual_risk_score: Optional[int]
    residual_risk_level: Optional[str]
    score_by_domain: Optional[dict]
    summary: Optional[str]
    recommendation: Optional[AssessmentRecommendation]
    decision_notes: Optional[str] = None
    decision_at: Optional[datetime] = None
    decision_by_id: Optional[int] = None
    profiling_questionnaire_id: Optional[int] = None
    assessment_questionnaire_id: Optional[int] = None
    assessor_user_id: Optional[int]
    approver_user_id: Optional[int]
    approved_at: Optional[datetime]
    valid_until: Optional[datetime]
    linked_risk_id: Optional[int]
    questionnaire_ids: Optional[list[int]]
    created_at: datetime


class VendorIssueCreate(BaseModel):
    supplier_id: int
    assessment_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    severity: VendorIssueSeverity = VendorIssueSeverity.MEDIUM
    source: str = "manual"
    framework_refs: Optional[list[str]] = None
    assigned_to_user_id: Optional[int] = None
    remediation_plan: Optional[str] = None
    due_date: Optional[datetime] = None


class VendorIssueUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[VendorIssueSeverity] = None
    status: Optional[VendorIssueStatus] = None
    framework_refs: Optional[list[str]] = None
    assigned_to_user_id: Optional[int] = None
    remediation_plan: Optional[str] = None
    due_date: Optional[datetime] = None


class VendorIssueOut(ORMBase):
    id: int
    code: str
    supplier_id: int
    supplier_name: Optional[str] = None
    assessment_id: Optional[int]
    source: str
    title: str
    description: Optional[str]
    severity: VendorIssueSeverity
    status: VendorIssueStatus
    framework_refs: Optional[list[str]]
    discovered_at: datetime
    due_date: Optional[datetime]
    closed_at: Optional[datetime]
    assigned_to_user_id: Optional[int]
    remediation_plan: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------- GDPR / DPIA (M6) ----------
class ProcessingActivityIn(BaseModel):
    title: str
    purposes: Optional[str] = None
    legal_basis: ProcessingLegalBasis = ProcessingLegalBasis.LEGITIMATE_INTERESTS
    data_categories: Optional[str] = None
    data_subjects: Optional[str] = None
    recipients: Optional[str] = None
    transfers_outside_eu: bool = False
    transfer_safeguards: Optional[str] = None
    retention_period: Optional[str] = None
    security_measures: Optional[str] = None
    controller_name: Optional[str] = None
    dpo_contact: Optional[str] = None
    requires_dpia: bool = False
    owner_id: Optional[int] = None


class ProcessingActivityUpdate(BaseModel):
    title: Optional[str] = None
    purposes: Optional[str] = None
    legal_basis: Optional[ProcessingLegalBasis] = None
    data_categories: Optional[str] = None
    data_subjects: Optional[str] = None
    recipients: Optional[str] = None
    transfers_outside_eu: Optional[bool] = None
    transfer_safeguards: Optional[str] = None
    retention_period: Optional[str] = None
    security_measures: Optional[str] = None
    controller_name: Optional[str] = None
    dpo_contact: Optional[str] = None
    requires_dpia: Optional[bool] = None
    owner_id: Optional[int] = None


class ProcessingActivityOut(ORMBase):
    id: int
    code: str
    title: str
    purposes: Optional[str]
    legal_basis: ProcessingLegalBasis
    data_categories: Optional[Any]
    data_subjects: Optional[Any]
    recipients: Optional[Any]
    transfers_outside_eu: bool
    transfer_safeguards: Optional[str]
    retention_period: Optional[str]
    security_measures: Optional[str]
    controller_name: Optional[str]
    dpo_contact: Optional[str]
    requires_dpia: bool
    owner_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    dpias: list["DPIAOut"] = []


class DPIAIn(BaseModel):
    activity_id: int
    title: str
    necessity_assessment: Optional[str] = None
    risks_identified: Optional[str] = None
    risk_measures: Optional[str] = None
    residual_risk_level: Optional[int] = None
    dpo_opinion: Optional[str] = None
    owner_id: Optional[int] = None


class DPIAUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[DPIAStatus] = None
    necessity_assessment: Optional[str] = None
    risks_identified: Optional[str] = None
    risk_measures: Optional[str] = None
    residual_risk_level: Optional[int] = None
    dpo_opinion: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    approved_by_id: Optional[int] = None
    owner_id: Optional[int] = None


class DPIAOut(ORMBase):
    id: int
    code: str
    activity_id: int
    title: str
    status: DPIAStatus
    necessity_assessment: Optional[str]
    risks_identified: Optional[str]
    risk_measures: Optional[str]
    residual_risk_level: Optional[int]
    dpo_opinion: Optional[str]
    reviewed_at: Optional[datetime]
    approved_by_id: Optional[int]
    owner_id: Optional[int]
    created_at: datetime
    updated_at: datetime


TokenOut.model_rebuild()


# ---------- OSINT ----------

class OSINTScanCreate(BaseModel):
    scan_type: OSINTScanType
    target: str


class OSINTScanResponse(ORMBase):
    id: int
    scan_type: OSINTScanType
    target: str
    user_id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    findings_count: int
    risk_score: float


class OSINTFindingResponse(ORMBase):
    id: int
    scan_id: int
    identifier_id: Optional[int]
    source: str
    finding_type: str
    title: str
    description: Optional[str]
    risk_level: str
    risk_score: float
    is_remediated: bool
    remediated_at: Optional[datetime]
    extra_data: Optional[dict]
    created_at: datetime
    updated_at: datetime


class OSINTIdentifierResponse(ORMBase):
    id: int
    identifier_type: OSINTScanType
    value: str
    user_id: int
    is_monitored: bool
    last_scanned_at: Optional[datetime]
    risk_level: OSINTFindingRiskLevel
    created_at: datetime
    updated_at: datetime


class PaginatedResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: list
