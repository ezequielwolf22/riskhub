"""Esquemas Pydantic para validacion de entrada/salida de la API."""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import (
    AssetType, ThreatOrigin, TreatmentOption,
    RiskStatus, ControlStatus, UserRole,
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


# ---------- USERS ----------
class UserIn(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=8)
    role: UserRole = UserRole.VIEWER


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserOut(ORMBase):
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


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
    parent_id: Optional[int] = None
    owner_ids: list[int] = []
    extra: Optional[dict] = None


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
    value_max: int
    parent_id: Optional[int]
    extra: Optional[dict]
    created_at: datetime
    updated_at: datetime
    risk_count: int = 0


# ---------- THREATS ----------
class ThreatIn(BaseModel):
    code: Optional[str] = None
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    origin: ThreatOrigin
    typical_assets: list[str] = []
    affects: list[str] = []


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
    control: ControlOut


# ---------- RISKS ----------
class RiskIn(BaseModel):
    asset_id: int
    threat_id: int
    description: Optional[str] = None
    consequence_description: Optional[str] = None
    inherent_likelihood: int = 0
    inherent_consequence: int = 0
    vulnerability_ids: list[int] = []
    control_implementation_ids: list[int] = []
    owner_id: Optional[int] = None
    treatment_option: Optional[TreatmentOption] = None
    treatment_plan: Optional[str] = None
    treatment_due_date: Optional[datetime] = None


class RiskUpdate(BaseModel):
    description: Optional[str] = None
    consequence_description: Optional[str] = None
    inherent_likelihood: Optional[int] = None
    inherent_consequence: Optional[int] = None
    vulnerability_ids: Optional[list[int]] = None
    control_implementation_ids: Optional[list[int]] = None
    owner_id: Optional[int] = None
    treatment_option: Optional[TreatmentOption] = None
    treatment_plan: Optional[str] = None
    treatment_due_date: Optional[datetime] = None
    status: Optional[RiskStatus] = None
    acceptance_justification: Optional[str] = None


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


TokenOut.model_rebuild()
