"""Router BCP/BIA — Business Continuity Planning (NIS2 Art. 21.2b + ISO 27001 A.5.29 + ISO 22301)."""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
import json as _json

from app.models import (
    BCPDependency, BCPExerciseProgramme, BCPPlan, BCPStrategy,
    BCPSupplierLink, BCPTest, BusinessProcess, Supplier, User, UserRole,
    BCMLocation, BCMEvidenceItem, BCMTestRecommendation,
    BCPTestRunbook, BCPRecoverySequence, BCMActivation, BCMContext,
)
from app.services import bcm_location_service, bcm_graph_service, bcm_test_engine
from app.security import get_current_user, require_admin, require_analyst
from app.i18n import ai_lang_directive, get_lang, t as _t
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.bcp")

router = APIRouter(prefix="/api/bcp", tags=["bcp"])

VALID_CRITICALITY = ("critical", "high", "medium", "low")
VALID_TEST_TYPES = ("tabletop", "simulation", "full_test")
VALID_TEST_RESULTS = ("passed", "partial", "failed")
VALID_DEP_TYPES = (
    "IT_system", "personnel", "facility", "supplier",
    "utility", "communication", "transport", "external_service", "process",
)
VALID_STRATEGY_TYPES = (
    "hot_site", "cold_site", "warm_site", "work_from_home",
    "outsourcing", "manual_workaround", "dual_site", "cloud_failover",
)
VALID_PLAN_TYPES = ("bcp", "drp", "crp", "ems", "pandemic", "cyber_response", "supply_chain")
VALID_IMPL_STATUS = ("planned", "in_progress", "implemented", "tested")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _org(u: User, lang: str = "es") -> int:
    if not u.organization_id:
        raise HTTPException(400, _t("bcp.user_no_org", lang))
    return u.organization_id


def _bcm_data_root(subdir: str):
    """Directorio raiz de almacenamiento para archivos BCM (evidencia, docs).

    Mismo patron que document_service._DOC_ROOT: usa el volumen persistente de
    produccion si existe, y cae a <proyecto>/data/<subdir> en desarrollo local.
    FIX: settings.data_dir nunca existio en app/config.py — este era un bug
    presente desde la creacion del modulo de evidencias (500 en cada subida).
    """
    from pathlib import Path
    root = Path("/srv/data") / subdir
    if not root.parent.exists():
        root = Path(__file__).parent.parent.parent / "data" / subdir
    return root


def _parse_dt(s, field_name: str = "fecha", lang: str = "es"):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s))
    except (ValueError, TypeError):
        raise HTTPException(422, _t("bcp.invalid_iso_date", lang, field=field_name))


def _next_bct(db: Session, org_id: int) -> str:
    # BUG1 fix: placeholder; real code assigned after db.flush() using the auto-incremented id
    return "BCT-0000"


def _proc_d(p: BusinessProcess) -> dict:
    from app.services.bcp_service import bia_completeness
    try:
        bia = bia_completeness(None, p)
    except Exception:
        bia = {"pct": 0, "missing": [], "total": 10}
    return {
        "id": p.id,
        "organization_id": p.organization_id,
        "name": p.name,
        "description": p.description,
        "criticality": p.criticality,
        "priority": p.priority,
        "rto_hours": p.rto_hours,
        "rpo_hours": p.rpo_hours,
        "mtpd_hours": p.mtpd_hours,
        "mbco": p.mbco,
        "financial_impact": p.financial_impact,
        "reputational_impact": p.reputational_impact,
        "legal_impact": p.legal_impact,
        "operational_impact": p.operational_impact,
        "min_recovery_staff": p.min_recovery_staff,
        "vital_records": p.vital_records,
        "activation_criteria": p.activation_criteria,
        "alternative_procedure": p.alternative_procedure,
        "it_systems": p.it_systems,
        "facilities": p.facilities,
        "escalation_contacts": p.escalation_contacts,
        "asset_ids": p.asset_ids,
        "supplier_ids": p.supplier_ids,
        "owner_id": p.owner_id,
        "recovery_owner_id": p.recovery_owner_id,
        "last_tested_at": p.last_tested_at.isoformat() if p.last_tested_at else None,
        "test_result": p.test_result,
        "bia_pct": bia["pct"],
        "bia_missing": bia["missing"],
        # BIA campos normativos adicionales
        "ens_category": getattr(p, "ens_category", None),
        "cost_per_hour": getattr(p, "cost_per_hour", None),
        "impact_1h": getattr(p, "impact_1h", None),
        "impact_24h": getattr(p, "impact_24h", None),
        "impact_7d": getattr(p, "impact_7d", None),
        "bia_version": getattr(p, "bia_version", None),
        "bia_review_date": p.bia_review_date.isoformat() if getattr(p, "bia_review_date", None) else None,
        "location_id": getattr(p, "location_id", None),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _test_d(t: BCPTest) -> dict:
    return {
        "id": t.id,
        "organization_id": t.organization_id,
        "code": t.code,
        "test_type": t.test_type,
        "process_ids": t.process_ids,
        "scheduled_at": t.scheduled_at.isoformat() if t.scheduled_at else None,
        "conducted_at": t.conducted_at.isoformat() if t.conducted_at else None,
        "objective": t.objective,
        "scope_description": t.scope_description,
        "participants": t.participants,
        "facilitator_id": t.facilitator_id,
        "result": t.result,
        "findings": t.findings,
        "lessons_learned": t.lessons_learned,
        "improvement_actions": t.improvement_actions,
        "evidence_doc_ids": t.evidence_doc_ids,
        "nc_ids": t.nc_ids,
        "frequency": getattr(t, "frequency", None),
        "rto_achieved_hours": getattr(t, "rto_achieved_hours", None),
        "rpo_achieved_hours": getattr(t, "rpo_achieved_hours", None),
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _dep_d(d: BCPDependency) -> dict:
    return {
        "id": d.id,
        "organization_id": d.organization_id,
        "process_id": d.process_id,
        "dependency_type": d.dependency_type,
        "name": d.name,
        "description": d.description,
        "qty_normal": d.qty_normal,
        "qty_recovery": d.qty_recovery,
        "rto_hours": d.rto_hours,
        "is_critical": d.is_critical,
        "alternative": d.alternative,
        "supplier_id": d.supplier_id,
        "asset_id": d.asset_id,
        "depends_on_process_id": getattr(d, "depends_on_process_id", None),
        "recovery_sequence": getattr(d, "recovery_sequence", None),
        "notes": getattr(d, "notes", None),
        "connection_type": getattr(d, "connection_type", None),
        "protocol": getattr(d, "protocol", None),
        "data_direction": getattr(d, "data_direction", None),
        "data_classification": getattr(d, "data_classification", None),
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def _strat_d(s: BCPStrategy) -> dict:
    return {
        "id": s.id,
        "organization_id": s.organization_id,
        "process_id": s.process_id,
        "strategy_type": s.strategy_type,
        "name": s.name,
        "description": s.description,
        "estimated_cost": s.estimated_cost,
        "implementation_status": s.implementation_status,
        "responsible_id": s.responsible_id,
        "target_date": s.target_date.isoformat() if s.target_date else None,
        "it_config": getattr(s, "it_config", None),
        "monitoring_config": getattr(s, "monitoring_config", None),
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _plan_d(p: BCPPlan) -> dict:
    return {
        "id": p.id,
        "organization_id": p.organization_id,
        "code": p.code,
        "plan_type": p.plan_type,
        "name": p.name,
        "version": p.version,
        "status": p.status,
        "scope": p.scope,
        "activation_criteria": p.activation_criteria,
        "content_summary": p.content_summary,
        "document_id": p.document_id,
        "process_ids": p.process_ids,
        "team_members": p.team_members,
        "review_date": p.review_date.isoformat() if p.review_date else None,
        "approved_by_id": p.approved_by_id,
        "approved_at": p.approved_at.isoformat() if p.approved_at else None,
        "last_exercised_at": p.last_exercised_at.isoformat() if p.last_exercised_at else None,
        # Campos enriquecidos del plan (drawer UI)
        "sections": getattr(p, "sections", None),
        "roles_matrix": getattr(p, "roles_matrix", None),
        "contact_list": getattr(p, "contact_list", None),
        "system_dependencies": getattr(p, "system_dependencies", None),
        "kpis": getattr(p, "kpis", None),
        "plan_owner_name": getattr(p, "plan_owner_name", None),
        "classification": getattr(p, "classification", None),
        "dr_site": getattr(p, "dr_site", None),
        "backup_policy": getattr(p, "backup_policy", None),
        "crisis_comms": getattr(p, "crisis_comms", None),
        "checklist_template": getattr(p, "checklist_template", None),
        "installation_type": getattr(p, "installation_type", None),
        "data_classification_level": getattr(p, "data_classification_level", None),
        "gdpr_data": getattr(p, "gdpr_data", False),
        "affected_users_count": getattr(p, "affected_users_count", None),
        "documentation_links": getattr(p, "documentation_links", None),
        "related_documents": getattr(p, "related_documents", None),
        "authorized_activators": getattr(p, "authorized_activators", None),
        "parent_plan_id": getattr(p, "parent_plan_id", None),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        # v6.3.0 — revision semantica IA del contenido (ISO 22301 cl. 8.4)
        "ai_content_review": getattr(p, "ai_content_review", None),
    }


def _sl_d(s: BCPSupplierLink, db: Session) -> dict:
    sup_name = ""
    if s.supplier_id:
        sup = db.get(Supplier, s.supplier_id)
        sup_name = sup.name if sup else ""
    alt_name = ""
    if s.alternative_supplier_id:
        alt = db.get(Supplier, s.alternative_supplier_id)
        alt_name = alt.name if alt else ""
    return {
        "id": s.id,
        "organization_id": s.organization_id,
        "supplier_id": s.supplier_id,
        "supplier_name": sup_name,
        "process_ids": s.process_ids,
        "criticality": s.criticality,
        "rto_impact_hours": s.rto_impact_hours,
        "has_contingency_plan": s.has_contingency_plan,
        "contingency_description": s.contingency_description,
        "alternative_supplier_id": s.alternative_supplier_id,
        "alternative_supplier_name": alt_name,
        "contract_sla_hours": s.contract_sla_hours,
        "notes": s.notes,
        "last_review_date": s.last_review_date.isoformat() if s.last_review_date else None,
    }


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ProcessIn(BaseModel):
    name: str
    description: Optional[str] = None
    criticality: str = "medium"
    priority: Optional[int] = None
    rto_hours: Optional[int] = None
    rpo_hours: Optional[int] = None
    mtpd_hours: Optional[int] = None
    mbco: Optional[str] = None
    financial_impact: Optional[int] = None
    reputational_impact: Optional[int] = None
    legal_impact: Optional[int] = None
    operational_impact: Optional[int] = None
    min_recovery_staff: Optional[int] = None
    vital_records: Optional[list] = None
    activation_criteria: Optional[str] = None
    alternative_procedure: Optional[str] = None
    it_systems: Optional[list] = None
    facilities: Optional[list] = None
    escalation_contacts: Optional[list] = None
    asset_ids: Optional[list] = None
    supplier_ids: Optional[list] = None
    owner_id: Optional[int] = None
    recovery_owner_id: Optional[int] = None
    # BIA campos normativos
    ens_category: Optional[str] = None
    cost_per_hour: Optional[float] = None
    impact_1h: Optional[int] = None
    impact_24h: Optional[int] = None
    impact_7d: Optional[int] = None
    bia_version: Optional[str] = None
    bia_review_date: Optional[str] = None


class ProcessUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    criticality: Optional[str] = None
    priority: Optional[int] = None
    rto_hours: Optional[int] = None
    rpo_hours: Optional[int] = None
    mtpd_hours: Optional[int] = None
    mbco: Optional[str] = None
    financial_impact: Optional[int] = None
    reputational_impact: Optional[int] = None
    legal_impact: Optional[int] = None
    operational_impact: Optional[int] = None
    min_recovery_staff: Optional[int] = None
    vital_records: Optional[list] = None
    activation_criteria: Optional[str] = None
    alternative_procedure: Optional[str] = None
    it_systems: Optional[list] = None
    facilities: Optional[list] = None
    escalation_contacts: Optional[list] = None
    asset_ids: Optional[list] = None
    supplier_ids: Optional[list] = None
    owner_id: Optional[int] = None
    recovery_owner_id: Optional[int] = None
    ens_category: Optional[str] = None
    cost_per_hour: Optional[float] = None
    impact_1h: Optional[int] = None
    impact_24h: Optional[int] = None
    impact_7d: Optional[int] = None
    bia_version: Optional[str] = None
    bia_review_date: Optional[str] = None


class DepIn(BaseModel):
    process_id: int
    dependency_type: str
    name: str
    description: Optional[str] = None
    qty_normal: Optional[int] = None
    qty_recovery: Optional[int] = None
    rto_hours: Optional[int] = None
    is_critical: bool = False
    alternative: Optional[str] = None
    supplier_id: Optional[int] = None
    asset_id: Optional[int] = None
    depends_on_process_id: Optional[int] = None
    recovery_sequence: Optional[int] = None
    notes: Optional[str] = None


class DepUpdate(BaseModel):
    process_id: Optional[int] = None
    dependency_type: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    qty_normal: Optional[int] = None
    qty_recovery: Optional[int] = None
    rto_hours: Optional[int] = None
    is_critical: Optional[bool] = None
    alternative: Optional[str] = None
    supplier_id: Optional[int] = None
    asset_id: Optional[int] = None
    depends_on_process_id: Optional[int] = None
    recovery_sequence: Optional[int] = None
    notes: Optional[str] = None


class StratIn(BaseModel):
    process_id: Optional[int] = None
    strategy_type: str
    name: str
    description: Optional[str] = None
    estimated_cost: Optional[float] = None
    implementation_status: str = "planned"
    responsible_id: Optional[int] = None
    target_date: Optional[str] = None
    it_config: Optional[dict] = None
    monitoring_config: Optional[dict] = None


class StratUpdate(BaseModel):
    process_id: Optional[int] = None
    strategy_type: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    estimated_cost: Optional[float] = None
    implementation_status: Optional[str] = None
    responsible_id: Optional[int] = None
    target_date: Optional[str] = None
    it_config: Optional[dict] = None
    monitoring_config: Optional[dict] = None


class PlanIn(BaseModel):
    plan_type: str = "bcp"
    name: str
    version: str = "1.0"
    code: Optional[str] = None
    scope: Optional[str] = None
    activation_criteria: Optional[str] = None
    content_summary: Optional[str] = None
    document_id: Optional[int] = None
    process_ids: Optional[list] = None
    team_members: Optional[list] = None
    review_date: Optional[str] = None
    sections: Optional[list] = None
    roles_matrix: Optional[list] = None
    contact_list: Optional[list] = None
    system_dependencies: Optional[list] = None
    kpis: Optional[list] = None
    plan_owner_name: Optional[str] = None
    classification: Optional[str] = None
    dr_site: Optional[dict] = None
    backup_policy: Optional[dict] = None
    crisis_comms: Optional[dict] = None
    installation_type: Optional[str] = None
    data_classification_level: Optional[str] = None
    gdpr_data: Optional[bool] = None
    affected_users_count: Optional[int] = None
    documentation_links: Optional[list] = None
    related_documents: Optional[list] = None
    authorized_activators: Optional[list] = None


class PlanUpdate(BaseModel):
    plan_type: Optional[str] = None
    name: Optional[str] = None
    version: Optional[str] = None
    status: Optional[str] = None
    scope: Optional[str] = None
    activation_criteria: Optional[str] = None
    content_summary: Optional[str] = None
    document_id: Optional[int] = None
    process_ids: Optional[list] = None
    team_members: Optional[list] = None
    review_date: Optional[str] = None
    sections: Optional[list] = None
    roles_matrix: Optional[list] = None
    contact_list: Optional[list] = None
    system_dependencies: Optional[list] = None
    kpis: Optional[list] = None
    plan_owner_name: Optional[str] = None
    classification: Optional[str] = None
    dr_site: Optional[dict] = None
    backup_policy: Optional[dict] = None
    crisis_comms: Optional[dict] = None
    installation_type: Optional[str] = None
    data_classification_level: Optional[str] = None
    gdpr_data: Optional[bool] = None
    affected_users_count: Optional[int] = None
    documentation_links: Optional[list] = None
    related_documents: Optional[list] = None
    authorized_activators: Optional[list] = None


class TestIn(BaseModel):
    test_type: str
    process_ids: Optional[List[int]] = None
    scheduled_at: str
    objective: Optional[str] = None
    scope_description: Optional[str] = None
    participants: Optional[list] = None
    facilitator_id: Optional[int] = None
    frequency: Optional[str] = None


class TestUpdate(BaseModel):
    conducted_at: Optional[str] = None
    result: Optional[str] = None
    findings: Optional[str] = None
    lessons_learned: Optional[str] = None
    improvement_actions: Optional[str] = None
    evidence_doc_ids: Optional[list] = None
    frequency: Optional[str] = None
    rto_achieved_hours: Optional[int] = None
    rpo_achieved_hours: Optional[int] = None


class SupLinkIn(BaseModel):
    supplier_id: int
    process_ids: Optional[list] = None
    criticality: str = "medium"
    rto_impact_hours: Optional[int] = None
    has_contingency_plan: bool = False
    contingency_description: Optional[str] = None
    alternative_supplier_id: Optional[int] = None
    contract_sla_hours: Optional[int] = None
    notes: Optional[str] = None
    last_review_date: Optional[str] = None


class SupLinkUpdate(BaseModel):
    process_ids: Optional[list] = None
    criticality: Optional[str] = None
    rto_impact_hours: Optional[int] = None
    has_contingency_plan: Optional[bool] = None
    contingency_description: Optional[str] = None
    alternative_supplier_id: Optional[int] = None
    contract_sla_hours: Optional[int] = None
    notes: Optional[str] = None
    last_review_date: Optional[str] = None


class EPIn(BaseModel):
    year: int
    overall_objective: Optional[str] = None
    exercises: Optional[list] = None


class EPUpdate(BaseModel):
    status: Optional[str] = None
    overall_objective: Optional[str] = None
    exercises: Optional[list] = None
    lessons_learned: Optional[str] = None


# ── Compliance hooks ──────────────────────────────────────────────────────────

def _update_compliance_from_bcp(db: Session, org_id: int, event: str, data: dict) -> None:
    """
    Actualiza ComplianceFrameworkStatus cuando ocurren eventos BCP relevantes.
    Mapeo normativo:
      ISO 27001 A.5.29, A.5.30 — BCM y ICT readiness
      NIS2 Art.21.2b — business continuity
      ENS op.cont.1/2/3 — medidas de continuidad
    """
    try:
        from app.services.compliance_service import get_or_create_requirement_status  # type: ignore

        def _set(framework: str, req_id: str, status: str, pct: int = 50) -> None:
            try:
                obj = get_or_create_requirement_status(db, org_id, framework, req_id)
                if obj is None:
                    return
                # Solo avanzar el estado, nunca retroceder
                order = {"not_started": 0, "planned": 1, "partial": 2, "implemented": 3}
                if order.get(status, 0) > order.get(obj.status, 0):
                    obj.status = status
                    obj.completion_pct = pct
                    obj.last_reviewed_at = datetime.now(timezone.utc)
            except Exception:
                pass

        if event == "plan_approved":
            plan_type = data.get("plan_type", "")
            _set("iso27001", "A.5.29", "implemented", 80)
            if plan_type in ("drp", "crp"):
                _set("iso27001", "A.5.30", "partial", 60)
            _set("nis2", "Art.21.2b", "partial", 50)
            if plan_type in ("bcp", "drp"):
                _set("ens", "op.cont.2", "implemented", 80)

        elif event == "test_passed":
            _set("iso27001", "A.5.30", "implemented", 90)
            _set("nis2", "Art.21.2b", "implemented", 80)
            _set("ens", "op.cont.3", "implemented", 90)

        elif event == "bia_complete":
            _set("ens", "op.cont.1", "partial", 60)
            _set("iso27001", "A.5.29", "partial", 40)

        elif event == "strategy_created":
            _set("iso27001", "A.5.29", "partial", 30)
            _set("ens", "op.cont.1", "partial", 40)

        elif event == "supplier_link_contingency":
            _set("iso27001", "A.5.19", "partial", 40)
            _set("nis2", "Art.21.2c", "partial", 40)

        db.commit()
    except Exception as exc:
        logger.debug("BCP compliance update skipped: %s", exc)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def bcp_dashboard(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    from app.services.bcp_service import bia_completeness
    from datetime import timedelta

    if u.role == UserRole.SUPERADMIN:
        procs = db.query(BusinessProcess).all()
        tests = db.query(BCPTest).all()
        plans = db.query(BCPPlan).all()
    else:
        if not u.organization_id:
            return {"total_processes": 0, "critical_processes": 0, "processes_overdue_test": 0,
                    "total_tests": 0, "tests_done": 0, "approved_plans": 0,
                    "bia_avg_pct": 0, "last_test_date": None}
        org_id = u.organization_id
        procs = db.query(BusinessProcess).filter_by(organization_id=org_id).all()
        tests = db.query(BCPTest).filter_by(organization_id=org_id).all()
        plans = db.query(BCPPlan).filter_by(organization_id=org_id).all()

    now = datetime.now(timezone.utc)
    critical = [p for p in procs if p.criticality == "critical"]
    overdue = [p for p in procs if not p.last_tested_at or
               (now - p.last_tested_at.replace(tzinfo=timezone.utc)).days > 365]
    tests_done = [t for t in tests if t.conducted_at]
    approved_plans = [p for p in plans if p.status == "approved"]
    bia_pcts = [bia_completeness(None, p)["pct"] for p in procs] if procs else []

    return {
        "total_processes": len(procs),
        "critical_processes": len(critical),
        "processes_overdue_test": len(overdue),
        "total_tests": len(tests),
        "tests_done": len(tests_done),
        "approved_plans": len(approved_plans),
        "bia_avg_pct": int(sum(bia_pcts) / len(bia_pcts)) if bia_pcts else 0,
        "last_test_date": max((t.conducted_at for t in tests_done), default=None).isoformat()
            if tests_done else None,
    }


# ── ISO 22301 status ──────────────────────────────────────────────────────────

@router.get("/iso22301-status")
def iso22301_status_endpoint(
    request: Request,
    location_id: Optional[int] = None,
    db: Session = Depends(get_db),
    u: User = Depends(get_current_user),
):
    org = u.organization_id
    if not org:
        return {"clauses": [], "implemented": 0, "partial": 0, "total": 0, "pct": 0, "is_ready": False}
    from app.services.bcp_service import iso22301_status as _status
    return _status(db, org, location_id, lang=get_lang(request))


# ── BIA completeness ──────────────────────────────────────────────────────────

@router.get("/bia")
def bia_overview(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    org = u.organization_id
    if not org:
        return []
    from app.services.bcp_service import bia_completeness
    procs = db.query(BusinessProcess).filter_by(organization_id=org).all()
    return [{"id": p.id, "name": p.name, "criticality": p.criticality,
             **bia_completeness(db, p)} for p in procs]


# ── Procesos ──────────────────────────────────────────────────────────────────

@router.get("/processes")
def list_processes(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    org = u.organization_id
    if not org:
        return []
    return [_proc_d(p) for p in db.query(BusinessProcess).filter_by(
        organization_id=org).order_by(BusinessProcess.criticality).all()]


@router.post("/processes", status_code=201)
def create_process(body: ProcessIn, request: Request, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    if body.criticality not in VALID_CRITICALITY:
        raise HTTPException(422, _t("bcp.invalid_criticality_valid", get_lang(request), valid=VALID_CRITICALITY))
    org = _org(u)
    # GDPR: escalation_contacts puede contener nombre, email y teléfono (datos personales).
    # Base legal: Art. 6(1)(f) RGPD — interés legítimo (continuidad del negocio).
    # Los datos solo deben ser de empleados de la organización.
    p = BusinessProcess(organization_id=org, **body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    log_action(db, u.id, "create", "business_process", str(p.id), {"name": p.name})
    return _proc_d(p)


@router.get("/processes/{pid}")
def get_process(pid: int, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    p = db.get(BusinessProcess, pid)
    if not p or p.organization_id != _org(u):
        raise HTTPException(404)
    return _proc_d(p)


@router.patch("/processes/{pid}")
def update_process(pid: int, body: ProcessUpdate, request: Request, db: Session = Depends(get_db),
                   u: User = Depends(require_analyst)):
    p = db.get(BusinessProcess, pid)
    if not p or p.organization_id != _org(u):
        raise HTTPException(404)
    if body.criticality and body.criticality not in VALID_CRITICALITY:
        raise HTTPException(422, _t("bcp.invalid_criticality", get_lang(request)))
    # GDPR: escalation_contacts puede contener datos personales (Art. 6(1)(f) RGPD).
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "bia_review_date":
            v = _parse_dt(v, "bia_review_date")
        setattr(p, k, v)
    db.commit()
    # ENS op.cont.1 + ISO 27001 A.5.29 cuando BIA alcanza >= 80%
    from app.services.bcp_service import bia_completeness as _bia
    if _bia(None, p)["pct"] >= 80:
        _update_compliance_from_bcp(db, _org(u), "bia_complete", {})
    return _proc_d(p)


@router.delete("/processes/{pid}", status_code=204)
def delete_process(pid: int, db: Session = Depends(get_db), u: User = Depends(require_admin)):
    p = db.get(BusinessProcess, pid)
    if not p or p.organization_id != _org(u):
        raise HTTPException(404)
    db.delete(p)
    db.commit()


# ── Dependencies ──────────────────────────────────────────────────────────────

@router.get("/dependencies")
def list_deps(process_id: Optional[int] = None, db: Session = Depends(get_db),
              u: User = Depends(get_current_user)):
    org = u.organization_id
    if not org:
        return []
    q = db.query(BCPDependency).filter_by(organization_id=org)
    if process_id:
        q = q.filter_by(process_id=process_id)
    return [_dep_d(d) for d in q.all()]


@router.post("/dependencies", status_code=201)
def create_dep(body: DepIn, request: Request, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    lang = get_lang(request)
    org = _org(u, lang)
    if body.dependency_type not in VALID_DEP_TYPES:
        raise HTTPException(422, _t("bcp.invalid_dependency_type", lang))
    proc = db.get(BusinessProcess, body.process_id)
    if not proc or proc.organization_id != org:
        raise HTTPException(422, _t("bcp.process_not_in_org", lang))
    d = BCPDependency(organization_id=org, **body.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    log_action(db, u.id, "create", "bcp_dependency", str(d.id),
               {"name": d.name, "type": d.dependency_type})
    return _dep_d(d)


@router.patch("/dependencies/{did}")
def update_dep(did: int, body: DepUpdate, request: Request, db: Session = Depends(get_db),
               u: User = Depends(require_analyst)):
    d = db.get(BCPDependency, did)
    if not d or d.organization_id != _org(u):
        raise HTTPException(404)
    data = body.model_dump(exclude_none=True)
    # BUG11 fix: validate dependency_type on update (same as create_dep)
    if "dependency_type" in data and data["dependency_type"] not in VALID_DEP_TYPES:
        raise HTTPException(422, _t("bcp.invalid_dependency_type", get_lang(request)))
    for k, v in data.items():
        setattr(d, k, v)
    db.commit()
    return _dep_d(d)


@router.delete("/dependencies/{did}", status_code=204)
def delete_dep(did: int, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    d = db.get(BCPDependency, did)
    if not d or d.organization_id != _org(u):
        raise HTTPException(404)
    db.delete(d)
    db.commit()


# ── Strategies ────────────────────────────────────────────────────────────────

@router.get("/strategies")
def list_strats(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    org = u.organization_id
    if not org:
        return []
    return [_strat_d(s) for s in db.query(BCPStrategy).filter_by(
        organization_id=org).all()]


@router.post("/strategies", status_code=201)
def create_strat(body: StratIn, request: Request, db: Session = Depends(get_db),
                 u: User = Depends(require_analyst)):
    if body.strategy_type not in VALID_STRATEGY_TYPES:
        raise HTTPException(422, _t("bcp.invalid_strategy_type", get_lang(request)))
    org = _org(u)
    s = BCPStrategy(
        organization_id=org,
        process_id=body.process_id,
        strategy_type=body.strategy_type,
        name=body.name,
        description=body.description,
        estimated_cost=body.estimated_cost,
        implementation_status=body.implementation_status or "planned",
        responsible_id=body.responsible_id,
        target_date=_parse_dt(body.target_date, "target_date") if body.target_date else None,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    log_action(db, u.id, "create", "bcp_strategy", str(s.id),
               {"name": s.name, "type": s.strategy_type})
    # ENS op.cont.1 + ISO 27001 A.5.29
    _update_compliance_from_bcp(db, org, "strategy_created", {})
    return _strat_d(s)


@router.patch("/strategies/{sid}")
def update_strat(sid: int, body: StratUpdate, request: Request, db: Session = Depends(get_db),
                 u: User = Depends(require_analyst)):
    lang = get_lang(request)
    s = db.get(BCPStrategy, sid)
    if not s or s.organization_id != _org(u, lang):
        raise HTTPException(404)
    data = body.model_dump(exclude_none=True)
    # BUG12 fix: validate strategy_type and implementation_status on update
    if "strategy_type" in data and data["strategy_type"] not in VALID_STRATEGY_TYPES:
        raise HTTPException(422, _t("bcp.invalid_strategy_type", lang))
    if "implementation_status" in data and data["implementation_status"] not in VALID_IMPL_STATUS:
        raise HTTPException(422, _t("bcp.invalid_implementation_status", lang))
    for k, v in data.items():
        if k == "target_date":
            v = _parse_dt(v, "target_date")
        setattr(s, k, v)
    db.commit()
    return _strat_d(s)


@router.delete("/strategies/{sid}", status_code=204)
def delete_strat(sid: int, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    s = db.get(BCPStrategy, sid)
    if not s or s.organization_id != _org(u):
        raise HTTPException(404)
    db.delete(s)
    db.commit()


# ── Plans ─────────────────────────────────────────────────────────────────────

@router.get("/plans")
def list_plans(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    org = u.organization_id
    if not org:
        return []
    return [_plan_d(p) for p in db.query(BCPPlan).filter_by(
        organization_id=org).order_by(BCPPlan.created_at.desc()).all()]


@router.post("/plans", status_code=201)
def create_plan(body: PlanIn, request: Request, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    lang = get_lang(request)
    if body.plan_type not in VALID_PLAN_TYPES:
        raise HTTPException(422, _t("bcp.invalid_plan_type", lang))
    org = _org(u, lang)
    # B2 — IDOR prevention: verificar que el documento pertenece a la misma organización
    if body.document_id:
        from app.models import AiDocument
        doc = db.get(AiDocument, body.document_id)
        if not doc or doc.organization_id != org:
            raise HTTPException(422, _t("bcp.document_not_in_org", lang))
    from app.services.bcp_service import next_plan_code
    plan_code = body.code if body.code else next_plan_code(db, org, body.plan_type)
    p = BCPPlan(
        organization_id=org,
        code=plan_code,
        plan_type=body.plan_type,
        name=body.name,
        version=body.version,
        scope=body.scope,
        activation_criteria=body.activation_criteria,
        content_summary=body.content_summary,
        document_id=body.document_id,
        process_ids=body.process_ids,
        team_members=body.team_members,
        review_date=_parse_dt(body.review_date, "review_date") if body.review_date else None,
        installation_type=body.installation_type,
        data_classification_level=body.data_classification_level,
        gdpr_data=body.gdpr_data,
        affected_users_count=body.affected_users_count,
        documentation_links=body.documentation_links,
        related_documents=body.related_documents,
        authorized_activators=body.authorized_activators,
        # BUG6 fix: fields that were silently dropped on create
        sections=body.sections,
        roles_matrix=body.roles_matrix,
        contact_list=body.contact_list,
        system_dependencies=body.system_dependencies,
        kpis=body.kpis,
        plan_owner_name=body.plan_owner_name,
        classification=body.classification,
        dr_site=body.dr_site,
        backup_policy=body.backup_policy,
        crisis_comms=body.crisis_comms,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    log_action(db, u.id, "create", "bcp_plan", str(p.id),
               {"code": p.code, "type": p.plan_type})
    return _plan_d(p)


@router.get("/plans/{pid}")
def get_plan(pid: int, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    p = db.get(BCPPlan, pid)
    if not p or p.organization_id != _org(u):
        raise HTTPException(404)
    return _plan_d(p)


# Campos administrativos que NO alteran el contenido sustantivo del plan y por
# tanto pueden editarse aunque el plan ya este aprobado, sin forzar nueva version.
_PLAN_SAFE_FIELDS_WHEN_APPROVED = {
    "review_date", "team_members", "authorized_activators",
    "documentation_links", "related_documents",
}


@router.patch("/plans/{pid}")
def update_plan(pid: int, body: PlanUpdate, request: Request, db: Session = Depends(get_db),
                u: User = Depends(require_analyst)):
    lang = get_lang(request)
    p = db.get(BCPPlan, pid)
    if not p or p.organization_id != _org(u, lang):
        raise HTTPException(404)
    data = body.model_dump(exclude_none=True)
    # Un plan aprobado es un documento con validez ISO 22301 §8.4: su contenido
    # no debe poder mutarse por PATCH directo. El cambio de estado a 'approved'
    # solo puede hacerse mediante /plans/{id}/approve (que valida y obsoleta versiones previas).
    if data.get("status") == "approved":
        raise HTTPException(422, _t("bcp.use_approve_endpoint", lang))
    if p.status == "approved":
        disallowed = set(data.keys()) - _PLAN_SAFE_FIELDS_WHEN_APPROVED
        if disallowed:
            raise HTTPException(422, _t("bcp.plan_approved_no_edit", lang))
    # B2 — IDOR prevention
    if "document_id" in data and data["document_id"]:
        from app.models import AiDocument
        doc = db.get(AiDocument, data["document_id"])
        if not doc or doc.organization_id != _org(u):
            raise HTTPException(422, _t("bcp.document_not_in_org", lang))
    doc_id_changed = "document_id" in data and data["document_id"] != p.document_id
    for k, v in data.items():
        if k == "review_date":
            v = _parse_dt(v, "review_date")
        setattr(p, k, v)
    if doc_id_changed:
        p.ai_content_review = None
    db.commit()
    if doc_id_changed and p.status == "approved":
        _trigger_checklist_extraction(db, p, _org(u))
        _trigger_content_review(db, p, _org(u))
    return _plan_d(p)


@router.delete("/plans/{pid}", status_code=204)
def delete_plan(pid: int, db: Session = Depends(get_db), u: User = Depends(require_admin)):
    p = db.get(BCPPlan, pid)
    if not p or p.organization_id != _org(u):
        raise HTTPException(404)
    db.delete(p)
    db.commit()


@router.post("/plans/{pid}/approve")
def approve_plan(pid: int, request: Request, db: Session = Depends(get_db), u: User = Depends(require_admin)):
    lang = get_lang(request)
    p = db.get(BCPPlan, pid)
    if not p or p.organization_id != _org(u, lang):
        raise HTTPException(404)
    if p.status not in ("draft", "under_review"):
        raise HTTPException(422, _t("bcp.only_draft_approvable", lang))
    # Validate required fields before approval (ISO 22301 §8.4)
    missing = []
    if not p.name:
        missing.append(_t("bcp.field_name", lang))
    if not p.scope:
        missing.append(_t("bcp.field_scope", lang))
    if not p.activation_criteria:
        missing.append(_t("bcp.field_activation_criteria", lang))
    if not p.process_ids:
        missing.append(_t("bcp.field_processes", lang))
    if missing:
        raise HTTPException(422, _t("bcp.missing_required_fields", lang, fields=", ".join(missing)))
    p.status = "approved"
    p.approved_by_id = u.id
    p.approved_at = datetime.now(timezone.utc)
    # Mark previous approved versions with the same code as obsolete (versioning)
    if p.code:
        prev = db.query(BCPPlan).filter(
            BCPPlan.organization_id == _org(u),
            BCPPlan.code == p.code,
            BCPPlan.id != p.id,
            BCPPlan.status == "approved"
        ).all()
        for old in prev:
            old.status = "obsolete"
    db.commit()
    log_action(db, u.id, "approve", "bcp_plan", str(p.id), {"code": p.code})
    # ISO 27001 A.5.29/A.5.30 + ENS op.cont.2 + NIS2 Art.21.2b
    _update_compliance_from_bcp(db, _org(u), "plan_approved", {"plan_type": p.plan_type})
    # NIS2 Art.21(2)(c): planes cyber_response/disaster_recovery actualizan cobertura NIS2
    _link_bcp_to_nis2(db, p, _org(u))
    # Extraer checklist automaticamente en background si hay documento
    _trigger_checklist_extraction(db, p, _org(u))
    # Revision semantica IA del contenido — ISO 22301 cl. 8.4 (solo si no se
    # analizo ya con esta version del documento)
    if not p.ai_content_review:
        _trigger_content_review(db, p, _org(u))
    return _plan_d(p)


@router.post("/plans/{pid}/ai-content-review")
def trigger_plan_content_review(pid: int, request: Request, db: Session = Depends(get_db),
                                 u: User = Depends(require_analyst)):
    """Dispara (o relanza) manualmente la revision semantica IA del documento
    del plan. Util para planes creados antes de esta funcionalidad o para
    re-analizar tras cambios en el documento."""
    p = db.get(BCPPlan, pid)
    if not p or p.organization_id != _org(u):
        raise HTTPException(404)
    if not p.document_id:
        raise HTTPException(422, _t("bcp.plan_no_document", get_lang(request)))
    _trigger_content_review(db, p, _org(u))
    return {"status": "queued"}


# ── Plan context (consolidated for AI + map + activation) ─────────────────────

@router.get("/plans/{pid}/context")
def plan_context(pid: int, db: Session = Depends(get_db),
                 u: User = Depends(get_current_user)):
    """Devuelve el contexto consolidado de un plan: procesos, runbooks, dependencias,
    proveedores criticos, ubicacion DR y crisis comms. Fuente de verdad para la IA,
    el mapa y la activacion."""
    # BUG2 fix: capture org once to avoid multiple _org() calls
    org = _org(u)
    p = db.get(BCPPlan, pid)
    if not p or p.organization_id != org:
        raise HTTPException(404)

    proc_ids = [int(x) for x in (p.process_ids or []) if str(x).isdigit()]
    processes = []
    for pid_int in proc_ids:
        proc = db.get(BusinessProcess, pid_int)
        if not proc or proc.organization_id != org:
            continue
        deps = db.query(BCPDependency).filter_by(
            organization_id=org, process_id=proc.id
        ).order_by(BCPDependency.recovery_sequence).all()
        slinks = db.query(BCPSupplierLink).filter_by(organization_id=org).all()
        sup_links = [sl for sl in slinks if proc.id in (sl.process_ids or [])]
        processes.append({
            "id": proc.id, "name": proc.name, "criticality": proc.criticality,
            "rto_hours": proc.rto_hours, "rpo_hours": proc.rpo_hours,
            "mtpd_hours": proc.mtpd_hours, "cost_per_hour": getattr(proc, "cost_per_hour", None),
            "recovery_owner_id": getattr(proc, "recovery_owner_id", None),
            "dependencies": [_dep_d(d) for d in deps],
            "suppliers": [_sl_d(sl, db) for sl in sup_links],
        })

    runbooks = db.query(BCPTestRunbook).filter_by(
        organization_id=org, plan_id=p.id
    ).all()

    tests = db.query(BCPTest).filter_by(organization_id=org).filter(
        BCPTest.process_ids.isnot(None)
    ).order_by(BCPTest.scheduled_at.desc()).limit(10).all()

    location = None
    if p.location_id:
        loc = db.get(BCMLocation, p.location_id)
        if loc:
            location = _loc_d(loc)

    return {
        "plan": _plan_d(p),
        "processes": processes,
        "runbooks": [_runbook_d(rb) for rb in runbooks],
        "recent_tests": [_test_d(t) for t in tests],
        "location": location,
    }


@router.post("/tests/{tid}/ai-generate-checklist")
def ai_generate_test_checklist(tid: int, request: Request, db: Session = Depends(get_db),
                                u: User = Depends(require_analyst)):
    """Genera con IA un checklist especifico para el test basado en los procesos,
    dependencias, runbooks y proveedores del plan asociado."""
    from app.models import AiConfig
    from app.security import decrypt_secret
    import anthropic, json as _json

    lang = get_lang(request)
    # BUG2 fix: capture org once to avoid multiple _org() calls
    org = _org(u, lang)
    t = db.get(BCPTest, tid)
    if not t or t.organization_id != org:
        raise HTTPException(404)

    cfg = db.query(AiConfig).filter_by(organization_id=org).first()
    api_key = None
    if cfg and cfg.api_key_encrypted:
        try:
            api_key = decrypt_secret(cfg.api_key_encrypted)
        except Exception:
            pass
    if not api_key:
        api_key = settings.anthropic_api_key
    if not api_key:
        raise HTTPException(422, _t("bcp.ai_not_configured_hint", lang))

    proc_ids = [int(x) for x in (t.process_ids or []) if str(x).isdigit()]
    proc_details = []
    for pid_int in proc_ids:
        proc = db.get(BusinessProcess, pid_int)
        if not proc or proc.organization_id != org:
            continue
        deps = db.query(BCPDependency).filter_by(
            organization_id=org, process_id=proc.id
        ).order_by(BCPDependency.recovery_sequence).all()
        slinks = [sl for sl in db.query(BCPSupplierLink).filter_by(organization_id=org).all()
                  if proc.id in (sl.process_ids or [])]
        proc_details.append({
            "name": proc.name, "rto_hours": proc.rto_hours, "rpo_hours": proc.rpo_hours,
            "deps": [{"name": d.name, "type": d.dependency_type, "rto": d.rto_hours,
                      "critical": d.is_critical, "seq": d.recovery_sequence} for d in deps],
            # BUG10 fix: BCPSupplierLink has no supplier_name attr; look up via DB
            "suppliers": [{"name": (db.get(Supplier, sl.supplier_id).name
                                    if sl.supplier_id and db.get(Supplier, sl.supplier_id)
                                    else ""),
                           "sla_h": sl.contract_sla_hours,
                           "criticality": sl.criticality} for sl in slinks],
        })

    test_type_labels = {
        "tabletop": "simulacro de mesa", "walkthrough": "walkthrough",
        "functional": "prueba funcional", "full_interruption": "interrupcion completa",
    }
    test_label = test_type_labels.get(t.test_type, t.test_type or "prueba")

    prompt = (
        f"Eres experto en continuidad de negocio ISO 22301. "
        f"Genera un checklist completo para un {test_label} programado para "
        f"{t.scheduled_at.strftime('%d/%m/%Y') if t.scheduled_at else 'fecha TBD'}.\n\n"
        f"PROCESOS A TESTEAR ({len(proc_details)}):\n"
        + "\n".join(
            f"- {p['name']} | RTO:{p['rto_hours']}h RPO:{p['rpo_hours']}h | "
            f"Deps criticas: {[d['name'] for d in p['deps'] if d['critical']]} | "
            f"Proveedores: {[s['name'] for s in p['suppliers']]}"
            for p in proc_details
        )
        + f"\n\nObjectivo declarado: {t.objective or 'No especificado'}\n\n"
        "Genera un JSON con esta estructura exacta:\n"
        '{"pre_test": [{"order":1,"title":"...","description":"..."}], '
        '"test_steps": [{"order":1,"title":"...","description":"...","process":"...","expected_rto_h":0}], '
        '"post_test": [{"order":1,"title":"...","description":"..."}], '
        '"notification_list": [{"role":"...","when":"before|during|after","channel":"..."}]}'
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=cfg.model or "claude-haiku-4-5",
            max_tokens=16384,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        checklist = _json.loads(raw[start:end]) if start >= 0 else {}
    except Exception as exc:
        raise HTTPException(500, _t("bcp.ai_error", lang, detail=exc))

    return {"test_id": t.id, "checklist": checklist}


# ── Tests ─────────────────────────────────────────────────────────────────────

@router.get("/tests")
def list_tests(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    org = u.organization_id
    if not org:
        return []
    return [_test_d(t) for t in db.query(BCPTest).filter_by(
        organization_id=org).order_by(BCPTest.scheduled_at.desc()).all()]


@router.post("/tests", status_code=201)
def create_test(body: TestIn, request: Request, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    lang = get_lang(request)
    if body.test_type not in VALID_TEST_TYPES:
        raise HTTPException(422, _t("bcp.invalid_test_type", lang))
    scheduled = _parse_dt(body.scheduled_at, "scheduled_at", lang)
    org = _org(u, lang)
    t = BCPTest(
        organization_id=org,
        code=_next_bct(db, org),
        test_type=body.test_type,
        process_ids=body.process_ids,
        scheduled_at=scheduled,
        objective=body.objective,
        scope_description=body.scope_description,
        participants=body.participants,
        facilitator_id=body.facilitator_id,
    )
    db.add(t)
    db.flush()
    # BUG1 fix: use auto-incremented id for race-condition-safe code generation
    t.code = f"BCT-{t.id:04d}"
    db.commit()
    db.refresh(t)
    log_action(db, u.id, "create", "bcp_test", str(t.id), {"code": t.code})
    return _test_d(t)


@router.patch("/tests/{tid}")
def update_test(tid: int, body: TestUpdate, request: Request, db: Session = Depends(get_db),
                u: User = Depends(require_analyst)):
    lang = get_lang(request)
    # BUG2 fix: capture org once to avoid multiple _org() calls
    org = _org(u, lang)
    t = db.get(BCPTest, tid)
    if not t or t.organization_id != org:
        raise HTTPException(404)
    if body.conducted_at:
        t.conducted_at = _parse_dt(body.conducted_at, "conducted_at", lang)
    if body.result:
        if body.result not in VALID_TEST_RESULTS:
            raise HTTPException(422, _t("bcp.invalid_result", lang))
        t.result = body.result
        # BUG7 fix: ensure conducted_at is always set when a result is recorded
        t.conducted_at = t.conducted_at or datetime.now(timezone.utc)
        log_action(db, u.id, "update", "bcp_test", str(t.id),
                   {"result": body.result, "code": t.code})
        for pid in (t.process_ids or []):
            proc = db.get(BusinessProcess, pid)
            if proc and proc.organization_id == org:
                proc.last_tested_at = t.conducted_at
                proc.test_result = body.result
        for plan in db.query(BCPPlan).filter_by(organization_id=org).all():
            if any(pid in (plan.process_ids or []) for pid in (t.process_ids or [])):
                plan.last_exercised_at = t.conducted_at
    for f in ("findings", "lessons_learned", "improvement_actions", "evidence_doc_ids",
              "frequency", "rto_achieved_hours", "rpo_achieved_hours"):
        v = getattr(body, f, None)
        if v is not None:
            setattr(t, f, v)
    db.commit()
    # ISO 27001 A.5.30 + ENS op.cont.3 + NIS2 Art.21.2b
    if body.result == "passed":
        _update_compliance_from_bcp(db, org, "test_passed", {})
        # Bucle cerrado: cerrar NCs abiertas relacionadas con este test
        _close_nc_on_bcp_pass(db, t, org)
    elif body.result in ("failed", "partial"):
        # Auto-crear NC por fallo (ISO 22301 cl. 10.1)
        _auto_nc_from_bcp_test_failure(db, t, org, u.id, lang)
    return _test_d(t)


# ── Supplier links ────────────────────────────────────────────────────────────

@router.get("/supplier-links")
def list_sl(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    org = u.organization_id
    if not org:
        return []
    return [_sl_d(s, db) for s in db.query(BCPSupplierLink).filter_by(
        organization_id=org).all()]


@router.post("/supplier-links", status_code=201)
def create_sl(body: SupLinkIn, request: Request, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    lang = get_lang(request)
    org = _org(u, lang)
    sup = db.get(Supplier, body.supplier_id)
    if not sup or sup.organization_id != org:
        raise HTTPException(422, _t("bcp.supplier_not_in_org", lang))
    existing = db.query(BCPSupplierLink).filter_by(
        organization_id=org, supplier_id=body.supplier_id).first()
    if existing:
        raise HTTPException(409, _t("bcp.supplier_link_exists", lang))
    data = body.model_dump()
    if data.get("last_review_date"):
        data["last_review_date"] = _parse_dt(data["last_review_date"], "last_review_date", lang)
    sl = BCPSupplierLink(organization_id=org, **data)
    db.add(sl)
    db.commit()
    db.refresh(sl)
    log_action(db, u.id, "create", "bcp_supplier_link", str(sl.id),
               {"supplier_id": sl.supplier_id})
    # ISO 27001 A.5.19 / NIS2 Art.21.2c si tiene plan contingencia
    if body.has_contingency_plan:
        _update_compliance_from_bcp(db, org, "supplier_link_contingency", {})
    return _sl_d(sl, db)


@router.patch("/supplier-links/{lid}")
def update_sl(lid: int, body: SupLinkUpdate, db: Session = Depends(get_db),
              u: User = Depends(require_analyst)):
    sl = db.get(BCPSupplierLink, lid)
    if not sl or sl.organization_id != _org(u):
        raise HTTPException(404)
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "last_review_date":
            v = _parse_dt(v, "last_review_date")
        setattr(sl, k, v)
    db.commit()
    return _sl_d(sl, db)


@router.delete("/supplier-links/{lid}", status_code=204)
def delete_sl(lid: int, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    sl = db.get(BCPSupplierLink, lid)
    if not sl or sl.organization_id != _org(u):
        raise HTTPException(404)
    db.delete(sl)
    db.commit()


# ── Programa de ejercicios ────────────────────────────────────────────────────

@router.get("/exercise-programme")
def list_ep(year: Optional[int] = None, db: Session = Depends(get_db),
            u: User = Depends(get_current_user)):
    org = u.organization_id
    if not org:
        return []
    q = db.query(BCPExerciseProgramme).filter_by(organization_id=org)
    if year:
        q = q.filter_by(year=year)
    return [{"id": p.id, "year": p.year, "status": p.status,
             "overall_objective": p.overall_objective, "exercises": p.exercises,
             "lessons_learned": p.lessons_learned, "approved_by_id": p.approved_by_id,
             "approved_at": p.approved_at.isoformat() if p.approved_at else None}
            for p in q.order_by(BCPExerciseProgramme.year.desc()).all()]


@router.post("/exercise-programme", status_code=201)
def create_ep(body: EPIn, request: Request, db: Session = Depends(get_db), u: User = Depends(require_admin)):
    org = _org(u)
    if db.query(BCPExerciseProgramme).filter_by(organization_id=org, year=body.year).first():
        raise HTTPException(409, _t("bcp.programme_exists", get_lang(request), year=body.year))
    ep = BCPExerciseProgramme(
        organization_id=org,
        year=body.year,
        overall_objective=body.overall_objective,
        exercises=body.exercises,
    )
    db.add(ep)
    db.commit()
    db.refresh(ep)
    return {"id": ep.id, "year": ep.year, "status": ep.status}


@router.patch("/exercise-programme/{eid}")
def update_ep(eid: int, body: EPUpdate, request: Request, db: Session = Depends(get_db),
              u: User = Depends(require_analyst)):
    ep = db.get(BCPExerciseProgramme, eid)
    if not ep or ep.organization_id != _org(u):
        raise HTTPException(404)
    # Security: solo admin puede marcar como aprobado (ISO 27001 A.8.15 — trazabilidad)
    if body.status == "approved" and u.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(403, _t("bcp.only_admin_approve_programme", get_lang(request)))
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(ep, k, v)
    db.commit()
    return {"id": ep.id, "year": ep.year, "status": ep.status,
            "exercises": ep.exercises, "lessons_learned": ep.lessons_learned}


# ── Excel import ──────────────────────────────────────────────────────────────

@router.post("/import/preview")
async def import_preview(request: Request, file: UploadFile = File(...),
                         db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    lang = get_lang(request)
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(422, _t("bcp.only_xlsx", lang))
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, _t("bcp.max_10mb", lang))
    # G11: validacion de magic bytes — ZIP header (PK\x03\x04) requerido para .xlsx
    if not content[:4] == b'PK\x03\x04':
        raise HTTPException(422, _t("bcp.invalid_excel_file", lang))
    from app.services.bcp_excel_service import parse_excel_preview
    try:
        return parse_excel_preview(content)
    except Exception as exc:
        raise HTTPException(422, _t("bcp.excel_read_error", lang, detail=exc))


@router.post("/import/confirm")
async def import_confirm(request: Request, file: UploadFile = File(...),
                         db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    lang = get_lang(request)
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(422, _t("bcp.only_xlsx", lang))
    content = await file.read()
    if not content[:4] == b'PK\x03\x04':
        raise HTTPException(422, _t("bcp.invalid_excel_file", lang))
    from app.services.bcp_excel_service import parse_excel_preview, confirm_excel_import
    try:
        preview = parse_excel_preview(content)
        if preview["errors"]:
            raise HTTPException(422, _t("bcp.excel_errors", lang, detail=preview['errors']))
        created = confirm_excel_import(db, preview, _org(u, lang))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, _t("bcp.import_error", lang, detail=exc))
    log_action(db, u.id, "import", "bcp_excel", "batch",
               {"created": created, "file": file.filename})
    return {"success": True, "created": created}


@router.get("/import/template")
def download_template(u: User = Depends(require_analyst)):
    from app.services.bcp_excel_service import generate_excel_template
    return Response(
        content=generate_excel_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=BCP_Plantilla.xlsx"},
    )


@router.get("/export")
def export_bcp_excel(request: Request, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    """Exporta todos los datos BCP de la organización como Excel."""
    org = u.organization_id
    if not org:
        raise HTTPException(400, _t("bcp.no_org_assigned", get_lang(request)))
    from app.services.bcp_excel_service import export_org_data
    content = export_org_data(db, org)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=BCP_datos.xlsx"},
    )


@router.post("/import/ai-preview")
async def import_ai_preview(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    u: User = Depends(require_analyst),
):
    """Usa Claude para parsear cualquier formato Excel/CSV y mapear columnas BCP."""
    lang = get_lang(request)
    if not file.filename.endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(422, _t("bcp.only_xlsx_csv", lang))
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, _t("bcp.max_10mb", lang))
    from app.models import AiConfig
    org = _org(u, lang)
    cfg = db.query(AiConfig).filter_by(organization_id=org).first()
    # Obtener API key usando el mismo patron que el router ai.py
    import base64
    import hashlib
    from cryptography.fernet import Fernet
    api_key = None
    if cfg and cfg.api_key_encrypted:
        try:
            key = base64.urlsafe_b64encode(
                hashlib.sha256(settings.secret_key.encode()).digest()
            )
            api_key = Fernet(key).decrypt(cfg.api_key_encrypted.encode()).decode()
        except Exception:
            api_key = None
    if not api_key:
        api_key = settings.anthropic_api_key
    if not api_key:
        raise HTTPException(422, _t("bcp.ai_key_missing_configure", lang))
    from app.services.bcp_excel_service import ai_parse_any_format
    bcp_ai_model = (cfg.model if cfg and cfg.model else None) or "claude-haiku-4-5"
    try:
        result = await ai_parse_any_format(content, file.filename, api_key, model=bcp_ai_model)
        return result
    except Exception as exc:
        logger.error("AI BCP import error: %s", exc)
        raise HTTPException(422, _t("bcp.ai_analysis_error", lang, detail=exc))


_BCP_ANALYSIS_PROMPT = """
Eres un Lead Auditor certificado en ISO 22301:2019, ISO 27001:2022 (A.5.29/A.5.30),
NIS2 Art.21.2(b) y ENS (op.cont.1/2/3).

Analiza el estado del SGCN (Sistema de Gestion de Continuidad de Negocio) de esta
organizacion y proporciona un informe ejecutivo estructurado.

ESTADO ACTUAL DEL SGCN:
{bcp_summary}

RESPONDE en este formato exacto (usa Markdown):

## Brechas criticas (bloquean certificacion ISO 22301)
Para cada brecha: * [Clausula ISO 22301] Descripcion del gap -- Accion recomendada

## Brechas importantes (observaciones en auditoria)
Para cada observacion: * [Referencia normativa] Descripcion -- Accion recomendada

## Estado ENS
* op.cont.1 (BIA + Plan): [Estado] -- [Que falta]
* op.cont.2 (Plan documentado): [Estado] -- [Que falta]
* op.cont.3 (Pruebas): [Estado] -- [Que falta]

## Estado ISO 27001
* A.5.29 (Business Continuity): [Estado] -- [Evidencias / Que falta]
* A.5.30 (ICT Readiness): [Estado] -- [Evidencias / Que falta]

## Fortalezas identificadas
Lista breve de lo que esta bien implementado

## Top 5 acciones prioritarias
1. [Accion concreta] -> [Clausula] -> Esfuerzo: [bajo/medio/alto]
2. ...

Se especifico y directo. Referencia clausulas exactas. Maximo 600 palabras total.
"""


def _build_bcp_summary(db: Session, org_id: int) -> str:
    """Construye el resumen del estado BCP para el prompt de analisis IA."""
    from app.services.bcp_service import iso22301_status, bia_completeness

    status = iso22301_status(db, org_id)
    procs = db.query(BusinessProcess).filter_by(organization_id=org_id).all()
    plans = db.query(BCPPlan).filter_by(organization_id=org_id).all()
    tests = db.query(BCPTest).filter_by(organization_id=org_id).all()

    gaps = [c for c in status.get("clauses", []) if c["status"] == "gap"]
    partial = [c for c in status.get("clauses", []) if c["status"] == "partial"]

    bia_scores = [(p.name, bia_completeness(db, p)["pct"]) for p in procs]
    low_bia = [(n, s) for n, s in bia_scores if s < 80]

    return (
        f"CUMPLIMIENTO ISO 22301: {status.get('pct', 0)}% "
        f"({status.get('implemented', 0)}/{status.get('total', 0)} clausulas implementadas)\n\n"
        f"GAPS ({len(gaps)} clausulas):\n"
        + "\n".join(f"- {c['id']}: {c['name']} -- {c['detail']}" for c in gaps[:8])
        + f"\n\nPARCIALES ({len(partial)} clausulas):\n"
        + "\n".join(f"- {c['id']}: {c['name']} -- {c['detail']}" for c in partial[:5])
        + f"\n\nPROCESOS: {len(procs)} total, "
        f"{sum(1 for p in procs if p.criticality=='critical')} criticos\n"
        f"BIA INCOMPLETO: {', '.join(f'{n} ({s}%)' for n, s in low_bia[:5]) or 'ninguno'}\n\n"
        f"PLANES: {len([p for p in plans if p.status=='approved'])} aprobados de {len(plans)} total\n"
        f"TIPOS: {', '.join(set(p.plan_type for p in plans)) or 'ninguno'}\n\n"
        f"TESTS: {len(tests)} total, {sum(1 for t in tests if t.result=='passed')} superados"
    ).strip()


@router.post("/analyze")
def analyze_bcp_with_ai(request: Request, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    """Analiza el estado BCP de la org con IA y devuelve recomendaciones. Consumo manual — no auto."""
    lang = get_lang(request)
    org = _org(u, lang)
    from app.models import AiConfig
    cfg = db.query(AiConfig).filter_by(organization_id=org).first()
    import base64
    import hashlib
    from cryptography.fernet import Fernet
    api_key = None
    if cfg and cfg.api_key_encrypted:
        try:
            key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
            api_key = Fernet(key).decrypt(cfg.api_key_encrypted.encode()).decode()
        except Exception:
            api_key = None
    if not api_key:
        api_key = settings.anthropic_api_key
    if not api_key:
        raise HTTPException(422, _t("bcp.ai_key_missing", lang))

    try:
        import anthropic
        summary = _build_bcp_summary(db, org)
        prompt = _BCP_ANALYSIS_PROMPT.format(bcp_summary=summary)
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=cfg.model or "claude-haiku-4-5",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        analysis_text = msg.content[0].text.strip()
        return {"analysis": analysis_text, "format": "markdown"}
    except Exception as exc:
        logger.error("BCP AI analyze error org=%d: %s", org, exc)
        raise HTTPException(422, _t("bcp.ai_analysis_error", lang, detail=exc))


# ── NC desde test fallido (ISO 22301 cl. 10.1) ────────────────────────────────

def _link_bcp_to_nis2(db: Session, plan: BCPPlan, org_id: int) -> None:
    """Cuando un BCPPlan tipo cyber_response se aprueba, actualiza la cobertura NIS2 Art.21(2)(c).

    Busca la fila ComplianceFrameworkStatus (framework_code='nis2', requirement_id='art21_2c')
    y la actualiza a 'implemented' con evidencia del plan aprobado.
    Si no existe la fila, la crea.
    """
    from app.models import ComplianceFrameworkStatus, ComplianceRequirementStatus

    CYBER_TYPES = {"cyber_response", "cyber_recovery", "incident_response", "disaster_recovery"}
    plan_type = str(getattr(plan, "plan_type", "") or "").lower()
    if plan_type not in CYBER_TYPES:
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    requirement_id = "art21_2c"
    framework_code = "nis2"

    nis2_row = db.query(ComplianceFrameworkStatus).filter(
        ComplianceFrameworkStatus.organization_id == org_id,
        ComplianceFrameworkStatus.framework_code == framework_code,
        ComplianceFrameworkStatus.requirement_id == requirement_id,
    ).first()

    if nis2_row:
        nis2_row.status = ComplianceRequirementStatus.IMPLEMENTED
        nis2_row.completion_pct = 100
        nis2_row.notes = (
            f"BCPPlan aprobado: {plan.name} (ID:{plan.id}, tipo:{plan.plan_type}). "
            f"Aprobado: {now.date()}. Cubre NIS2 Art.21(2)(c) — planes de continuidad de negocio."
        )
        nis2_row.last_reviewed_at = now
    else:
        nis2_row = ComplianceFrameworkStatus(
            organization_id=org_id,
            framework_code=framework_code,
            requirement_id=requirement_id,
            status=ComplianceRequirementStatus.IMPLEMENTED,
            completion_pct=100,
            notes=(
                f"BCPPlan aprobado: {plan.name} (ID:{plan.id}, tipo:{plan.plan_type}). "
                f"Aprobado: {now.date()}. Cubre NIS2 Art.21(2)(c) — planes de continuidad de negocio."
            ),
            last_reviewed_at=now,
        )
        db.add(nis2_row)

    try:
        db.commit()
        logger.info(
            "NIS2 Art.21(2)(c) actualizado a 'implemented' por BCPPlan %s (org %s)",
            plan.id, org_id,
        )
    except Exception as exc:
        db.rollback()
        logger.warning("NIS2 BCP link failed: %s", exc)


def _auto_nc_from_bcp_test_failure(db: Session, test: BCPTest, org_id: int, user_id: int,
                                   lang: str = "es") -> None:
    """Crea NC automaticamente cuando un test BCP falla (ISO 22301 cl. 10.1).

    Bucle cerrado: NC cerrada cuando un test posterior pasa (_close_nc_on_bcp_pass).
    Solo crea una NC por test (evita duplicados por re-PATCH).
    """
    from app.models import NonConformity, NCSeverity, NCStatus

    FAIL_STATUSES = {"failed", "partial"}
    if str(getattr(test, "result", "") or "").lower() not in FAIL_STATUSES:
        return

    # Evitar duplicado: si ya hay NC (auto o manual) vinculada a este test, no crear otra
    if test.nc_ids:
        existing = db.query(NonConformity).filter(
            NonConformity.id.in_(test.nc_ids),
            NonConformity.status.notin_([NCStatus.CLOSED]),  # BUG8 fix: use enum value
        ).first()
        if existing:
            return

    severity = NCSeverity.MAJOR if test.result == "failed" else NCSeverity.MINOR
    now = datetime.now(timezone.utc)
    nc = NonConformity(
        organization_id=org_id,
        code=_next_nc_code(db, org_id),
        title=_t("bcp.auto_nc_title", lang,
                 result=test.result.upper(), code=test.code or f"ID {test.id}"),
        description=_t("bcp.auto_nc_description", lang,
                       type=test.test_type or _t("bcp.unknown", lang),
                       result=test.result, id=test.id),
        source="bcp_test",
        severity=severity,
        status=NCStatus.OPEN,
        iso_clause="8.5",
        owner_id=user_id,
        due_date=now.replace(tzinfo=None) + timedelta(days=90),
        created_at=now.replace(tzinfo=None),
    )
    db.add(nc)
    try:
        db.flush()
        # BUG1 fix: use auto-incremented id for race-condition-safe code generation
        nc.code = f"NC-{nc.id:04d}"
        # Link NC id back to test
        nc_ids = list(test.nc_ids or [])
        nc_ids.append(nc.id)
        test.nc_ids = nc_ids
        db.commit()
        logger.info("Auto-NC %s creada para BCPTest %s (result=%s)", nc.code, test.id, test.result)
    except Exception as exc:
        db.rollback()
        logger.warning("Auto-NC from BCP test failed: %s", exc)


def _close_nc_on_bcp_pass(db: Session, test: BCPTest, org_id: int) -> None:
    """Cierra NCs auto-generadas cuando un test posterior pasa (bucle cerrado)."""
    from app.models import NonConformity, NCStatus

    if str(getattr(test, "result", "") or "").lower() != "passed":
        return

    # Buscar NCs abiertas vinculadas a este test via nc_ids (robusto frente a edicion de descripcion)
    if not test.nc_ids:
        return
    ncs = db.query(NonConformity).filter(
        NonConformity.id.in_(test.nc_ids),
        NonConformity.status.notin_([NCStatus.CLOSED]),  # BUG8 fix: use enum value
    ).all()

    if not ncs:
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for nc in ncs:
        nc.status = NCStatus.CLOSED  # BUG8 fix: use enum value instead of string
        nc.closed_at = now
    try:
        db.commit()
        logger.info("Cerradas %d NC(s) por BCPTest %s pasado", len(ncs), test.id)
    except Exception as exc:
        db.rollback()
        logger.warning("Error cerrando NCs en bcp pass: %s", exc)


def _next_nc_code(db: Session, org_id: int) -> str:
    # BUG1 fix: placeholder; real code assigned after db.flush() using auto-incremented id
    return "NC-0000"


@router.post("/tests/{test_id}/create-nc", status_code=201)
def create_nc_from_test(test_id: int, request: Request, db: Session = Depends(get_db),
                        u: User = Depends(require_analyst)):
    """Crea una No Conformidad vinculada a un test de continuidad fallido.

    ISO 22301 cl. 10.1 — no conformidades y acciones correctoras.
    """
    lang = get_lang(request)
    t = db.get(BCPTest, test_id)
    if not t or t.organization_id != _org(u, lang):
        raise HTTPException(404)
    if t.result not in ("failed", "partial"):
        raise HTTPException(422, _t("bcp.nc_only_failed_tests", lang))
    # G06: evitar duplicado cruzado con NCs auto-generadas
    if t.nc_ids:
        from app.models import NonConformity as _NC, NCStatus as _NCStatus
        open_nc = db.query(_NC).filter(
            _NC.id.in_(t.nc_ids),
            _NC.status.notin_([_NCStatus.CLOSED]),  # BUG8 fix: use enum value
        ).first()
        if open_nc:
            raise HTTPException(409, _t("bcp.nc_already_open", lang, code=open_nc.code))
    try:
        from app.models import NonConformity, NCSeverity, NCStatus
        severity = NCSeverity.MAJOR if t.result == "failed" else NCSeverity.MINOR
        org_id_nc = _org(u)
        nc = NonConformity(
            organization_id=org_id_nc,
            code=_next_nc_code(db, org_id_nc),
            title=_t("bcp.nc_from_test_title", lang, result=t.result.upper(), code=t.code),
            description=_t(
                "bcp.nc_from_test_description", lang,
                type=t.test_type,
                date=t.conducted_at.date() if t.conducted_at else _t("bcp.pending", lang),
                findings=t.findings or _t("bcp.no_findings", lang),
            ),
            source="bcp_test",
            severity=severity,
            status=NCStatus.OPEN,
            iso_clause="8.5",
            owner_id=u.id,
        )
        db.add(nc)
        db.flush()  # obtener nc.id antes de modificar t
        # BUG1 fix: use auto-incremented id for race-condition-safe code generation
        nc.code = f"NC-{nc.id:04d}"
        nc_ids = list(t.nc_ids or [])
        nc_ids.append(nc.id)
        t.nc_ids = nc_ids
        db.commit()
        log_action(db, u.id, "create", "nonconformity_from_bcp_test",
                   str(nc.id), {"test_code": t.code, "result": t.result})
        return {"nc_id": nc.id, "nc_code": nc.code,
                "message": _t("bcp.nc_created", lang, code=nc.code)}
    except ImportError:
        raise HTTPException(500, _t("bcp.nc_module_unavailable", lang))
    except Exception as exc:
        db.rollback()
        logger.error("create_nc_from_test error: %s", exc)
        raise HTTPException(500, _t("bcp.nc_create_error", lang, detail=exc))


# ═══════════════════════════════════════════════════════════════════════════════
# BCM EXPANSION — Schemas nuevos
# ═══════════════════════════════════════════════════════════════════════════════

class LocationCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    description: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    bcm_manager_id: Optional[int] = None
    recovery_site_type: Optional[str] = None
    recovery_site_description: Optional[str] = None
    alternate_location_id: Optional[int] = None
    capacity_details: Optional[dict] = None


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    bcm_manager_id: Optional[int] = None
    recovery_site_type: Optional[str] = None
    recovery_site_description: Optional[str] = None
    is_active: Optional[bool] = None
    capacity_details: Optional[dict] = None


# ── Helpers BCM Expansion ─────────────────────────────────────────────────────

def _chk_loc(db, loc_id, org_id, lang="es"):
    loc = db.get(BCMLocation, loc_id)
    if not loc or loc.organization_id != org_id:
        raise HTTPException(404, _t("bcp.location_not_found", lang))
    return loc


def _chk_act(db, act_id, org_id, lang="es"):
    act = db.get(BCMActivation, act_id)
    if not act or act.organization_id != org_id:
        raise HTTPException(404, _t("bcp.activation_not_found", lang))
    return act


def _trigger_checklist_extraction(db: Session, plan: BCPPlan, org_id: int) -> None:
    """Extrae el checklist del documento del plan usando Claude (sin bloquear la respuesta)."""
    import threading
    from app.models import AiConfig
    from app.services.bcm_checklist_service import extract_plan_checklist
    from app.database import SessionLocal

    config = db.query(AiConfig).filter_by(organization_id=org_id).first()
    if not config or not config.api_key_encrypted:
        # Sin config IA, generar checklist por defecto
        from app.services.bcm_checklist_service import _default_checklist
        plan.checklist_template = _default_checklist(plan)
        db.commit()
        return

    from app.security import decrypt_secret
    try:
        api_key = decrypt_secret(config.api_key_encrypted)
    except Exception:
        return

    plan_id = plan.id
    model = config.model or "claude-haiku-4-5"

    def _extract():
        with SessionLocal() as sess:
            p = sess.get(BCPPlan, plan_id)
            if not p:
                return
            template = extract_plan_checklist(sess, p, api_key, model)
            p.checklist_template = template
            sess.commit()

    t = threading.Thread(target=_extract, daemon=True)
    t.start()


def _trigger_content_review(db: Session, plan: BCPPlan, org_id: int) -> None:
    """Lanza en background la revision semantica IA del documento del plan
    (ISO 22301 cl. 8.4 — bcm_content_reviewer.py). No bloquea la respuesta."""
    import threading
    from app.services.bcm_content_reviewer import run_review_for_plan

    if not plan.document_id:
        return
    plan_id = plan.id
    t = threading.Thread(target=run_review_for_plan, args=(plan_id,), daemon=True)
    t.start()


def _loc_d(loc):
    return {
        "id": loc.id, "code": loc.code, "name": loc.name,
        "description": loc.description, "parent_id": loc.parent_id,
        "address": loc.address, "country": loc.country,
        "bcm_manager_id": loc.bcm_manager_id,
        "recovery_site_type": loc.recovery_site_type,
        "recovery_site_description": loc.recovery_site_description,
        "alternate_location_id": loc.alternate_location_id,
        "is_active": loc.is_active,
        "capacity_details": getattr(loc, "capacity_details", None),
        "created_at": loc.created_at.isoformat() if loc.created_at else None,
    }


def _evid_d(e):
    return {
        "id": e.id, "location_id": e.location_id, "evidence_type": e.evidence_type,
        "title": e.title, "description": e.description, "file_name": e.file_name,
        "file_size": e.file_size, "mime_type": e.mime_type, "sha256_hash": e.sha256_hash,
        "tags": e.tags, "is_current": e.is_current, "uploaded_by_id": e.uploaded_by_id,
        "linked_test_id": e.linked_test_id, "linked_plan_id": e.linked_plan_id,
        "linked_process_id": e.linked_process_id,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        # v6.3.0 — revision semantica IA del contenido real del archivo
        "ai_review": getattr(e, "ai_review", None),
    }


def _rec_d(r, db=None):
    proc_name = None
    if r.process_id and db:
        p = db.get(BusinessProcess, r.process_id)
        proc_name = p.name if p else None
    return {
        "id": r.id, "location_id": r.location_id, "plan_id": r.plan_id,
        "process_id": r.process_id, "process_name": proc_name,
        "recommended_test_type": r.recommended_test_type,
        "reason": r.reason, "priority": r.priority, "trigger": r.trigger,
        "status": r.status,
        "recommended_date": r.recommended_date.isoformat() if r.recommended_date else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _runbook_d(rb):
    return {
        "id": rb.id, "title": rb.title, "test_type": rb.test_type,
        "runbook_type": getattr(rb, "runbook_type", None) or rb.test_type,
        "scenario": rb.scenario, "plan_id": rb.plan_id, "test_id": rb.test_id,
        "location_id": rb.location_id, "steps": rb.steps or [],
        "total_estimated_minutes": rb.total_estimated_minutes,
        "generated_by_ai": rb.generated_by_ai,
        # Campos operacionales DRP (ISO 22301 §8.4.3)
        "activation_condition": getattr(rb, "activation_condition", None),
        "credentials_vault_ref": getattr(rb, "credentials_vault_ref", None),
        "success_criteria": getattr(rb, "success_criteria", None),
        "responsible_name": getattr(rb, "responsible_name", None),
        "backup_responsible_name": getattr(rb, "backup_responsible_name", None),
        "created_at": rb.created_at.isoformat() if rb.created_at else None,
    }


def _seq_d(s):
    return {
        "id": s.id, "name": s.name, "plan_id": s.plan_id, "location_id": s.location_id,
        "sequence_items": s.sequence_items or [],
        "activation_status": s.activation_status,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _act_d(a):
    activated_by_name = ""
    if getattr(a, "activated_by", None):
        activated_by_name = a.activated_by.email or ""
    return {
        "id": a.id, "code": a.code, "title": a.title, "status": a.status,
        "location_id": a.location_id, "activated_plan_ids": a.activated_plan_ids,
        "incident_id": a.incident_id,
        "activated_at": a.activated_at.isoformat() if a.activated_at else None,
        "activated_by_id": a.activated_by_id,
        "activated_by_name": activated_by_name,
        "closed_at": a.closed_at.isoformat() if a.closed_at else None,
        "rto_objective_hours": a.rto_objective_hours,
        "rto_actual_hours": a.rto_actual_hours,
        "systems_status": a.systems_status or [],
        "log_count": len(a.situation_log or []),
        "situation_log": a.situation_log or [],
        "checklist_items": a.checklist_items or [],
        "root_cause": a.root_cause,
        "lessons_learned": a.lessons_learned,
        "improvement_actions": a.improvement_actions,
        "executive_summary": getattr(a, "executive_summary", None),
        "affected_services": getattr(a, "affected_services", None) or [],
        "ai_summary": getattr(a, "ai_summary", None),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ── LOCALIZACIONES BCM ────────────────────────────────────────────────────────

@router.get("/locations")
def list_locations(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    return bcm_location_service.get_location_tree(db, _org(u))


@router.get("/locations/consolidated")
def consolidated(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    return bcm_location_service.get_consolidated_metrics(db, _org(u))


@router.post("/locations", status_code=201)
def create_location(body: LocationCreate, request: Request, db: Session = Depends(get_db),
                    u: User = Depends(require_admin)):
    if body.parent_id:
        p = db.get(BCMLocation, body.parent_id)
        if not p or p.organization_id != _org(u):
            raise HTTPException(422, _t("bcp.parent_location_not_found", get_lang(request)))
    loc = BCMLocation(
        organization_id=_org(u),
        code=bcm_location_service.next_location_code(db, _org(u)),
        **body.model_dump(exclude_none=True),
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    log_action(db, u.id, "create", "bcm_location", str(loc.id), {"name": loc.name})
    return _loc_d(loc)


@router.get("/locations/{loc_id}")
def get_location(loc_id: int, request: Request, db: Session = Depends(get_db),
                 u: User = Depends(get_current_user)):
    loc = _chk_loc(db, loc_id, _org(u), get_lang(request))
    metrics = bcm_location_service.get_location_metrics(db, loc_id, _org(u))
    return {**_loc_d(loc), "metrics": metrics}


@router.patch("/locations/{loc_id}")
def update_location(loc_id: int, body: LocationUpdate, request: Request,
                    db: Session = Depends(get_db), u: User = Depends(require_admin)):
    loc = _chk_loc(db, loc_id, _org(u), get_lang(request))
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(loc, k, v)
    db.commit()
    return _loc_d(loc)


@router.delete("/locations/{loc_id}", status_code=204)
def delete_location(loc_id: int, request: Request, db: Session = Depends(get_db),
                    u: User = Depends(require_admin)):
    lang = get_lang(request)
    loc = _chk_loc(db, loc_id, _org(u, lang), lang)
    try:
        procs = db.query(BusinessProcess).filter_by(
            organization_id=_org(u), location_id=loc_id).count()
        if procs:
            raise HTTPException(422, _t("bcp.cannot_delete_location_processes", lang, n=procs))
    except HTTPException:
        raise
    except Exception:
        pass
    db.delete(loc)
    db.commit()


@router.post("/locations/{loc_id}/sync-deps")
def sync_location_deps(loc_id: int, request: Request, db: Session = Depends(get_db),
                       u: User = Depends(require_analyst)):
    """Auto-crea dependencias BCM cuando una localización tiene localización alternativa.
    ISO 22301 cl. 8.3 — cada proceso debe tener estrategia de localización alternativa.
    Las dependencias creadas son categorizadas como criticas o no segun la criticidad del proceso.
    """
    lang = get_lang(request)
    org = _org(u, lang)
    loc = _chk_loc(db, loc_id, org, lang)
    if not loc.alternate_location_id:
        return {"created": 0, "skipped": 0, "message": _t("bcp.no_alternate_location", lang)}

    alt_loc = db.get(BCMLocation, loc.alternate_location_id)
    if not alt_loc or alt_loc.organization_id != org:
        raise HTTPException(422, _t("bcp.invalid_alternate_location", lang))

    try:
        procs = db.query(BusinessProcess).filter_by(
            organization_id=org, location_id=loc_id).all()
    except Exception:
        procs = []

    created = 0
    skipped = 0
    for proc in procs:
        dep_name = f"Sede alternativa: {alt_loc.name}"
        existing = db.query(BCPDependency).filter_by(
            organization_id=org,
            process_id=proc.id,
            dependency_type="facility",
            name=dep_name,
        ).first()
        if existing:
            skipped += 1
            continue
        is_critical = proc.criticality in ("critical", "high")
        dep = BCPDependency(
            organization_id=org,
            process_id=proc.id,
            dependency_type="facility",
            name=dep_name,
            description=_t("bcp.alt_site_dep_description", lang, loc=loc.name, alt=alt_loc.name),
            is_critical=is_critical,
            alternative=_t(
                "bcp.alt_site_dep_alternative", lang,
                alt=alt_loc.name,
                site_type=alt_loc.recovery_site_type or _t("bcp.alt_site_fallback", lang),
            ),
            notes="auto:location_alternate",
        )
        db.add(dep)
        created += 1

    if created:
        db.commit()
        log_action(db, u.id, "auto_sync", "bcp_dependencies", str(loc_id),
                   {"created": created, "location": loc.name, "alternate": alt_loc.name})

    return {
        "created": created,
        "skipped": skipped,
        "location": loc.name,
        "alternate": alt_loc.name,
        "message": _t("bcp.deps_sync_result", lang, created=created, skipped=skipped),
    }


@router.post("/locations/sync-all-deps")
def sync_all_location_deps(request: Request, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    """Sincroniza dependencias de todas las localizaciones con sede alternativa."""
    lang = get_lang(request)
    org = _org(u, lang)
    locs = db.query(BCMLocation).filter(
        BCMLocation.organization_id == org,
        BCMLocation.alternate_location_id.isnot(None),
        BCMLocation.is_active == True,
    ).all()
    total_created = 0
    for loc in locs:
        try:
            result = sync_location_deps.__wrapped__(loc.id, db, u) if hasattr(sync_location_deps, '__wrapped__') else None
            if result is None:
                alt_loc = db.get(BCMLocation, loc.alternate_location_id)
                if not alt_loc or alt_loc.organization_id != org:
                    continue
                try:
                    procs = db.query(BusinessProcess).filter_by(
                        organization_id=org, location_id=loc.id).all()
                except Exception:
                    procs = []
                for proc in procs:
                    dep_name = f"Sede alternativa: {alt_loc.name}"
                    if db.query(BCPDependency).filter_by(
                        organization_id=org, process_id=proc.id,
                        dependency_type="facility", name=dep_name,
                    ).first():
                        continue
                    dep = BCPDependency(
                        organization_id=org, process_id=proc.id,
                        dependency_type="facility", name=dep_name,
                        description=f"Auto: {loc.name} → {alt_loc.name}",
                        is_critical=proc.criticality in ("critical", "high"),
                        alternative=_t("bcp.alt_site_move", lang, alt=alt_loc.name),
                        notes="auto:location_alternate",
                    )
                    db.add(dep)
                    total_created += 1
        except Exception as e:
            logger.warning("sync_all_location_deps loc=%d: %s", loc.id, e)
    if total_created:
        db.commit()
    return {"created": total_created, "locations_processed": len(locs)}


# ── GRAFO DE DEPENDENCIAS BCM ─────────────────────────────────────────────────

@router.get("/graph")
def get_graph(request: Request, location_id: Optional[int] = None,
              db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    """Grafo de dependencias BCM compatible con Cytoscape.js."""
    if location_id:
        _chk_loc(db, location_id, _org(u), get_lang(request))
    return bcm_graph_service.build_dependency_graph(db, _org(u), location_id)


@router.post("/graph/analyze")
def analyze_graph(request: Request, location_id: Optional[int] = None,
                  db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    """Análisis IA del grafo de dependencias."""
    from app.services.isms_analysis_service import _get_api_key, _get_model
    api_key = _get_api_key(db, _org(u))
    if not api_key:
        raise HTTPException(422, _t("bcp.api_key_not_configured", get_lang(request)))
    graph = bcm_graph_service.build_dependency_graph(db, _org(u), location_id)
    analysis = bcm_graph_service.analyze_graph_with_ai(
        db, graph, _org(u), api_key, _get_model(db, _org(u))
    )
    return {"analysis": analysis, "stats": graph["stats"]}


# ── TEST RECOMMENDATIONS ──────────────────────────────────────────────────────

@router.get("/test-recommendations")
def list_recommendations(location_id: Optional[int] = None,
                          status: Optional[str] = None,
                          db: Session = Depends(get_db),
                          u: User = Depends(get_current_user)):
    q = db.query(BCMTestRecommendation).filter_by(organization_id=_org(u))
    if location_id:
        q = q.filter_by(location_id=location_id)
    if status:
        q = q.filter_by(status=status)
    return [_rec_d(r, db) for r in q.order_by(
        BCMTestRecommendation.priority, BCMTestRecommendation.recommended_date).all()]


@router.post("/test-recommendations/generate")
def generate_recommendations(location_id: Optional[int] = None,
                               db: Session = Depends(get_db),
                               u: User = Depends(require_analyst)):
    n = bcm_test_engine.generate_recommendations(db, _org(u), location_id)
    return {"created": n}


@router.patch("/test-recommendations/{rid}")
def update_recommendation(rid: int, body: dict,
                           db: Session = Depends(get_db),
                           u: User = Depends(require_analyst)):
    rec = db.get(BCMTestRecommendation, rid)
    if not rec or rec.organization_id != _org(u):
        raise HTTPException(404)
    new_status = body.get("status")
    if new_status not in ("accepted", "dismissed"):
        raise HTTPException(422)
    rec.status = new_status
    rec.accepted_by_id = u.id
    db.commit()
    return _rec_d(rec)


@router.get("/tests/filter")
def filter_tests(location_ids: Optional[str] = None,
                 asset_id: Optional[int] = None,
                 plan_type: Optional[str] = None,
                 supplier_id: Optional[int] = None,
                 db: Session = Depends(get_db),
                 u: User = Depends(get_current_user)):
    filters = {}
    if location_ids:
        filters["location_ids"] = [int(x) for x in location_ids.split(",") if x.strip()]
    if asset_id:
        filters["asset_id"] = asset_id
    if plan_type:
        filters["plan_type"] = plan_type
    if supplier_id:
        filters["supplier_id"] = supplier_id
    return bcm_test_engine.filter_tests_ad_hoc(db, _org(u), filters)


# ── EVIDENCIAS BCM ────────────────────────────────────────────────────────────

@router.get("/evidence")
def list_evidence(location_id: Optional[int] = None,
                  evidence_type: Optional[str] = None,
                  linked_test_id: Optional[int] = None,
                  linked_plan_id: Optional[int] = None,
                  db: Session = Depends(get_db),
                  u: User = Depends(get_current_user)):
    q = db.query(BCMEvidenceItem).filter_by(organization_id=_org(u))
    if location_id:
        q = q.filter_by(location_id=location_id)
    if evidence_type:
        q = q.filter_by(evidence_type=evidence_type)
    if linked_test_id:
        q = q.filter_by(linked_test_id=linked_test_id)
    if linked_plan_id:
        q = q.filter_by(linked_plan_id=linked_plan_id)
    return [_evid_d(e) for e in q.order_by(BCMEvidenceItem.created_at.desc()).all()]


@router.post("/evidence", status_code=201)
async def upload_evidence(
    title: str,
    evidence_type: str,
    location_id: Optional[int] = None,
    linked_test_id: Optional[int] = None,
    linked_plan_id: Optional[int] = None,
    linked_process_id: Optional[int] = None,
    description: Optional[str] = None,
    tags: Optional[str] = None,
    request: Request = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    u: User = Depends(require_analyst),
):
    """Sube evidencia BCM con cifrado Fernet y hash SHA-256 de integridad."""
    import hashlib
    import base64
    from pathlib import Path
    from cryptography.fernet import Fernet

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, _t("bcp.file_too_large_50mb", get_lang(request)))

    sha256 = hashlib.sha256(content).hexdigest()

    evidence_dir = _bcm_data_root("bcm_evidence") / str(_org(u))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{sha256[:16]}_{file.filename}"
    fpath = evidence_dir / stored

    try:
        # BUG9 fix: use SHA-256 based key derivation consistent with the rest of the codebase
        key_bytes = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
        fernet = Fernet(key_bytes)
        fpath.write_bytes(fernet.encrypt(content))
    except Exception:
        fpath.write_bytes(content)

    item = BCMEvidenceItem(
        organization_id=_org(u), location_id=location_id,
        evidence_type=evidence_type, title=title, description=description,
        linked_test_id=linked_test_id, linked_plan_id=linked_plan_id,
        linked_process_id=linked_process_id,
        file_path=str(fpath), file_name=file.filename,
        file_size=len(content), mime_type=file.content_type,
        sha256_hash=sha256,
        tags=[t.strip() for t in tags.split(",")] if tags else [],
        uploaded_by_id=u.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    log_action(db, u.id, "upload", "bcm_evidence", str(item.id),
               {"title": title, "type": evidence_type})
    _trigger_evidence_review(item.id)
    return _evid_d(item)


def _trigger_evidence_review(evidence_id: int) -> None:
    """Lanza en background la revision semantica IA del archivo de evidencia
    (bcm_content_reviewer.py). No bloquea la respuesta de subida."""
    import threading
    from app.services.bcm_content_reviewer import run_review_for_evidence
    t = threading.Thread(target=run_review_for_evidence, args=(evidence_id,), daemon=True)
    t.start()


@router.post("/evidence/{eid}/ai-review")
def trigger_evidence_ai_review(eid: int, db: Session = Depends(get_db),
                               u: User = Depends(require_analyst)):
    """Dispara (o relanza) manualmente la revision semantica IA del archivo
    de evidencia. Util para evidencia subida antes de esta funcionalidad."""
    ev = db.get(BCMEvidenceItem, eid)
    if not ev or ev.organization_id != _org(u):
        raise HTTPException(404)
    _trigger_evidence_review(eid)
    return {"status": "queued"}


@router.get("/evidence/{eid}/download")
def download_evidence(eid: int, request: Request, db: Session = Depends(get_db),
                      u: User = Depends(require_analyst)):
    from fastapi.responses import FileResponse
    from pathlib import Path
    ev = db.get(BCMEvidenceItem, eid)
    if not ev or ev.organization_id != _org(u):
        raise HTTPException(404)
    if not ev.file_path or not Path(ev.file_path).exists():
        raise HTTPException(404, _t("bcp.file_not_found_server", get_lang(request)))
    return FileResponse(ev.file_path, filename=ev.file_name,
                        media_type=ev.mime_type or "application/octet-stream")


@router.delete("/evidence/{eid}", status_code=204)
def delete_evidence(eid: int, db: Session = Depends(get_db),
                    u: User = Depends(require_analyst)):
    from pathlib import Path
    ev = db.get(BCMEvidenceItem, eid)
    if not ev or ev.organization_id != _org(u):
        raise HTTPException(404)
    try:
        Path(ev.file_path).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(ev)
    db.commit()


# ── ACTIVACIONES BCM (CRISIS MANAGEMENT) ─────────────────────────────────────

@router.get("/activations")
def list_activations(status: Optional[str] = None,
                     db: Session = Depends(get_db),
                     u: User = Depends(get_current_user)):
    q = db.query(BCMActivation).filter_by(organization_id=_org(u))
    if status:
        q = q.filter_by(status=status)
    return [_act_d(a) for a in q.order_by(BCMActivation.activated_at.desc()).all()]


@router.post("/activations", status_code=201)
def create_activation(body: dict, request: Request, db: Session = Depends(get_db),
                      u: User = Depends(require_analyst)):
    from app.services.bcm_checklist_service import build_activation_checklist
    lang = get_lang(request)
    # BUG2 fix: capture org once to avoid multiple _org() calls
    org = _org(u, lang)
    plan_ids = body.get("activated_plan_ids") or []
    plans = []
    for pid in plan_ids:
        plan = db.get(BCPPlan, pid)
        if not plan or plan.organization_id != org:
            raise HTTPException(422, _t("bcp.plan_id_not_found", lang, id=pid))
        plans.append(plan)

    # Merge checklists de todos los planes activados
    merged_checklist = []
    order = 1
    for plan in plans:
        template = getattr(plan, "checklist_template", None) or []
        checklist = build_activation_checklist(template)
        for item in checklist:
            item["order"] = order
            item["plan_id"] = plan.id
            item["plan_name"] = plan.name
            merged_checklist.append(item)
            order += 1

    act = BCMActivation(
        organization_id=org,
        code="ACT-0000",  # BUG1 fix: placeholder; real code assigned after flush
        title=body.get("title") or _t("bcp.default_activation_title", lang),
        activated_plan_ids=plan_ids,
        incident_id=body.get("incident_id"),
        location_id=body.get("location_id"),
        activated_at=datetime.now(timezone.utc),
        activated_by_id=u.id,
        situation_log=[],
        systems_status=[],
        checklist_items=merged_checklist,
    )
    db.add(act)
    db.flush()
    # BUG1 fix: use auto-incremented id for race-condition-safe code generation
    act.code = f"ACT-{act.id:04d}"
    db.commit()
    db.refresh(act)
    log_action(db, u.id, "create", "bcm_activation", str(act.id), {"code": act.code})
    return _act_d(act)


@router.post("/activations/{aid}/log")
def add_log_entry(aid: int, body: dict, request: Request, db: Session = Depends(get_db),
                  u: User = Depends(require_analyst)):
    act = _chk_act(db, aid, _org(u), get_lang(request))
    log = list(act.situation_log or [])
    valid_types = {"accion", "nota", "escalada", "resolucion", "decision", "comunicacion", "action"}
    entry_type = body.get("entry_type") or body.get("type", "accion")
    if entry_type not in valid_types:
        entry_type = "accion"
    entry = {
        "id": len(log) + 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": u.id, "user_email": u.email,
        "entry_type": entry_type,
        "text": str(body.get("text", "") or body.get("message", ""))[:2000],
    }
    if body.get("action_owner"):
        entry["action_owner"] = str(body["action_owner"])[:255]
    log.append(entry)
    act.situation_log = log
    db.commit()
    return {"entries": len(log), "entry": entry}


@router.patch("/activations/{aid}/systems")
def update_system_status(aid: int, body: dict, request: Request, db: Session = Depends(get_db),
                          u: User = Depends(require_analyst)):
    from app.models import Asset as AssetModel
    act = _chk_act(db, aid, _org(u), get_lang(request))
    systems = list(act.systems_status or [])
    now = datetime.now(timezone.utc).isoformat()
    asset = db.get(AssetModel, body.get("asset_id")) if body.get("asset_id") else None
    found = False
    for s in systems:
        if s.get("asset_id") == body.get("asset_id"):
            s.update({"status": body.get("status"), "notes": body.get("notes"),
                      "updated_at": now})
            found = True
            break
    if not found:
        systems.append({
            "asset_id": body.get("asset_id"),
            "asset_name": asset.name if asset else str(body.get("asset_id")),
            "status": body.get("status", "down"),
            "notes": body.get("notes"),
            "updated_at": now,
        })
    act.systems_status = systems
    db.commit()
    return {"systems_count": len(systems)}


@router.post("/activations/{aid}/close")
def close_activation(aid: int, body: dict, request: Request, db: Session = Depends(get_db),
                     u: User = Depends(require_admin)):
    lang = get_lang(request)
    act = _chk_act(db, aid, _org(u, lang), lang)
    if act.status == "closed":
        raise HTTPException(422, _t("bcp.activation_closed", lang))
    now = datetime.now(timezone.utc)
    rto_real = (now - act.activated_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
    act.status = "closed"
    act.closed_at = now
    act.closed_by_id = u.id
    act.rto_actual_hours = round(rto_real, 2)
    act.root_cause = body.get("root_cause")
    act.lessons_learned = body.get("lessons_learned")
    act.improvement_actions = body.get("improvement_actions")
    _update_compliance_from_bcp(db, _org(u), "test_passed", {})
    log_action(db, u.id, "close", "bcm_activation", str(act.id),
               {"rto_actual_hours": rto_real})
    db.commit()
    return _act_d(act)


@router.patch("/activations/{aid}/checklist/{order}")
def update_checklist_item(aid: int, order: int, body: dict, request: Request,
                          db: Session = Depends(get_db),
                          u: User = Depends(require_analyst)):
    lang = get_lang(request)
    act = _chk_act(db, aid, _org(u, lang), lang)
    items = list(act.checklist_items or [])
    item = next((i for i in items if i.get("order") == order), None)
    if not item:
        raise HTTPException(404, _t("bcp.checklist_item_not_found", lang))
    allowed = {"status", "notes"}
    for k, v in body.items():
        if k in allowed:
            item[k] = v
    if body.get("status") == "done" and not item.get("executed_at"):
        item["executed_at"] = datetime.now(timezone.utc).isoformat()
        item["executed_by"] = u.email
    act.checklist_items = items
    db.commit()
    return {"checklist_items": items}


@router.post("/activations/{aid}/checklist/{order}/execute")
def execute_checklist_item(aid: int, order: int, request: Request,
                           db: Session = Depends(get_db),
                           u: User = Depends(require_analyst)):
    from app.services.bcm_checklist_service import execute_checklist_action
    lang = get_lang(request)
    act = _chk_act(db, aid, _org(u, lang), lang)
    items = list(act.checklist_items or [])
    item = next((i for i in items if i.get("order") == order), None)
    if not item:
        raise HTTPException(404, _t("bcp.checklist_item_not_found", lang))
    if item.get("status") == "done":
        raise HTTPException(422, _t("bcp.checklist_item_executed", lang))
    updated = execute_checklist_action(db, act, item, u, _org(u))
    for i, it in enumerate(items):
        if it.get("order") == order:
            items[i] = updated
            break
    act.checklist_items = items
    db.commit()
    return {"checklist_items": items}


# ── RUNBOOKS Y RECOVERY SEQUENCES ────────────────────────────────────────────

@router.get("/runbooks")
def list_runbooks(plan_id: Optional[int] = None, test_id: Optional[int] = None,
                  db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    q = db.query(BCPTestRunbook).filter_by(organization_id=_org(u))
    if plan_id:
        q = q.filter_by(plan_id=plan_id)
    if test_id:
        q = q.filter_by(test_id=test_id)
    return [_runbook_d(r) for r in q.all()]


@router.post("/runbooks", status_code=201)
def create_runbook(body: dict, db: Session = Depends(get_db),
                   u: User = Depends(require_analyst)):
    rb = BCPTestRunbook(
        organization_id=_org(u), created_by_id=u.id,
        **{k: v for k, v in body.items() if hasattr(BCPTestRunbook, k)}
    )
    db.add(rb)
    db.commit()
    db.refresh(rb)
    return _runbook_d(rb)


@router.post("/runbooks/{rid}/generate-ai")
def generate_runbook_ai(rid: int, request: Request, db: Session = Depends(get_db),
                         u: User = Depends(require_analyst)):
    """Genera los pasos del runbook con IA."""
    import anthropic
    import json
    from app.services.isms_analysis_service import _get_api_key, _get_model
    rb = db.get(BCPTestRunbook, rid)
    if not rb or rb.organization_id != _org(u):
        raise HTTPException(404)
    api_key = _get_api_key(db, _org(u))
    if not api_key:
        raise HTTPException(422, _t("bcp.api_key_not_configured", get_lang(request)))
    plan = db.get(BCPPlan, rb.plan_id) if rb.plan_id else None
    plan_info = f"Plan: {plan.name} ({plan.plan_type})" if plan else ""
    prompt = (
        f"Experto en BCM ISO 22301. Genera runbook para:\n"
        f"Tipo: {rb.test_type}, Escenario: {rb.scenario or 'Simulacro general'}\n{plan_info}\n"
        f'JSON SOLO: {{"steps":[{{"seq":1,"title":"...","responsible_role":"...",'
        f'"description":"...","expected_result":"...","estimated_minutes":15,'
        f'"validation_check":"...","rollback_if_fails":"..."}}]}}\n'
        f"8-12 pasos realistas y accionables."
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(model=_get_model(db, _org(u)), max_tokens=8192,
                                      messages=[{"role": "user", "content": prompt}])
        text = msg.content[0].text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        rb.steps = data.get("steps", [])
        rb.total_estimated_minutes = sum(s.get("estimated_minutes", 0) for s in rb.steps)
        rb.generated_by_ai = True
        db.commit()
        return _runbook_d(rb)
    except Exception as exc:
        raise HTTPException(500, f"Error: {exc}")


@router.patch("/runbooks/{rid}")
def update_runbook(rid: int, body: dict, db: Session = Depends(get_db),
                   u: User = Depends(require_analyst)):
    rb = db.get(BCPTestRunbook, rid)
    if not rb or rb.organization_id != _org(u):
        raise HTTPException(404)
    for k, v in body.items():
        if hasattr(rb, k):
            setattr(rb, k, v)
    db.commit()
    return _runbook_d(rb)


@router.delete("/runbooks/{rid}", status_code=204)
def delete_runbook(rid: int, db: Session = Depends(get_db),
                   u: User = Depends(require_analyst)):
    rb = db.get(BCPTestRunbook, rid)
    if not rb or rb.organization_id != _org(u):
        raise HTTPException(404)
    db.delete(rb)
    db.commit()


@router.get("/recovery-sequences")
def list_sequences(plan_id: Optional[int] = None, db: Session = Depends(get_db),
                   u: User = Depends(get_current_user)):
    q = db.query(BCPRecoverySequence).filter_by(organization_id=_org(u))
    if plan_id:
        q = q.filter_by(plan_id=plan_id)
    return [_seq_d(s) for s in q.all()]


@router.post("/recovery-sequences", status_code=201)
def create_sequence(body: dict, request: Request, db: Session = Depends(get_db),
                    u: User = Depends(require_analyst)):
    from app.models import Asset as AssetModel
    for item in (body.get("sequence_items") or []):
        aid = item.get("asset_id")
        if aid:
            a = db.get(AssetModel, aid)
            if not a or a.organization_id != _org(u):
                raise HTTPException(422, _t("bcp.asset_not_in_org", get_lang(request), id=aid))
    seq = BCPRecoverySequence(
        organization_id=_org(u),
        **{k: v for k, v in body.items() if hasattr(BCPRecoverySequence, k)}
    )
    db.add(seq)
    db.commit()
    db.refresh(seq)
    return _seq_d(seq)


@router.patch("/recovery-sequences/{sid}")
def update_sequence(sid: int, body: dict, db: Session = Depends(get_db),
                    u: User = Depends(require_analyst)):
    seq = db.get(BCPRecoverySequence, sid)
    if not seq or seq.organization_id != _org(u):
        raise HTTPException(404)
    for k, v in body.items():
        if hasattr(seq, k):
            setattr(seq, k, v)
    db.commit()
    return _seq_d(seq)


# ── REPORTING BCM ─────────────────────────────────────────────────────────────

@router.get("/report/executive")
def executive_report(request: Request,
                     location_id: Optional[int] = None,
                     db: Session = Depends(get_db),
                     u: User = Depends(require_analyst)):
    from app.services.bcm_location_service import get_consolidated_metrics
    from app.services.bcp_service import iso22301_status as _iso
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "consolidated_metrics": get_consolidated_metrics(db, _org(u)),
        "iso22301_status": _iso(db, _org(u), lang=get_lang(request)),
    }


@router.get("/report/ens-compliance")
def ens_report(db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    from app.models import ComplianceFrameworkStatus
    items = db.query(ComplianceFrameworkStatus).filter(
        ComplianceFrameworkStatus.organization_id == _org(u),
        ComplianceFrameworkStatus.framework_code == "ens",
        ComplianceFrameworkStatus.requirement_id.in_(["op.cont.1", "op.cont.2", "op.cont.3"]),
    ).all()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ens_measures": [
            {
                "id": i.requirement_id, "status": i.status,
                "completion_pct": i.completion_pct,
                "last_reviewed": i.last_reviewed_at.isoformat() if i.last_reviewed_at else None,
            }
            for i in items
        ],
    }


@router.get("/report/activation-history")
def activation_history(db: Session = Depends(get_db),
                       u: User = Depends(require_analyst)):
    acts = db.query(BCMActivation).filter_by(organization_id=_org(u)).order_by(
        BCMActivation.activated_at.desc()).all()
    closed = [a for a in acts if a.status == "closed" and a.rto_actual_hours]
    avg_rto = sum(a.rto_actual_hours for a in closed) / len(closed) if closed else None
    return {
        "total": len(acts),
        "active_now": sum(1 for a in acts if a.status == "active"),
        "closed": len(closed),
        "avg_rto_actual": round(avg_rto, 1) if avg_rto else None,
        "activations": [_act_d(a) for a in acts[:20]],
    }


@router.get("/risk-coverage-gaps")
def risk_coverage_gaps(location_id: Optional[int] = None,
                       db: Session = Depends(get_db),
                       u: User = Depends(require_analyst)):
    """Riesgos críticos sin cobertura BCM — gap visible en dashboard ejecutivo."""
    from app.models import Risk, RiskStatus, Asset as AssetModel
    risks = db.query(Risk).filter(
        Risk.organization_id == _org(u),
        Risk.status.notin_([RiskStatus.ACCEPTED, RiskStatus.CLOSED]),
        Risk.residual_level >= 6,
    ).all()
    gaps = []
    for r in risks:
        if getattr(r, "bcp_coverage", None):
            continue
        asset = db.get(AssetModel, r.asset_id) if r.asset_id else None
        if location_id and asset and asset.bcm_location_id != location_id:
            continue
        gaps.append({
            "risk_id": r.id, "risk_code": r.code, "risk_name": r.name,
            "residual_level": r.residual_level,
            "asset_id": r.asset_id,
            "asset_name": asset.name if asset else None,
            "asset_location_id": asset.bcm_location_id if asset else None,
        })
    return {"gaps_count": len(gaps), "gaps": gaps[:50]}


# ── SUPPLIER AI ANALYSIS ──────────────────────────────────────────────────────

@router.post("/suppliers/analyze-ai")
def analyze_suppliers_ai(request: Request, location_id: Optional[int] = None,
                          db: Session = Depends(get_db),
                          u: User = Depends(require_analyst)):
    import anthropic
    from app.services.isms_analysis_service import _get_api_key, _get_model
    lang = get_lang(request)
    api_key = _get_api_key(db, _org(u, lang))
    if not api_key:
        raise HTTPException(422, _t("bcp.api_key_not_configured", lang))
    q = db.query(BCPSupplierLink).filter_by(organization_id=_org(u))
    if location_id:
        try:
            q = q.filter_by(location_id=location_id)
        except Exception:
            pass
    links = q.all()
    if not links:
        return {"analysis": _t("bcp.no_bcm_suppliers", lang)}
    lines = []
    for lk in links:
        sup = db.get(Supplier, lk.supplier_id)
        if not sup:
            continue
        procs = [db.get(BusinessProcess, pid) for pid in (lk.process_ids or [])]
        lines.append(
            f"- {sup.name} ({lk.criticality}): RTO {lk.rto_impact_hours or '?'}h, "
            f"contingencia:{'sí' if lk.has_contingency_plan else 'NO'}, "
            f"procesos:{', '.join(p.name for p in procs if p)}"
        )
    prompt = (
        "Experto ISO 22301 y NIS2 Art.21.2c.\n"
        "Analiza proveedores críticos BCM:\n" + "\n".join(lines) +
        "\n\n(1) Concentración de riesgo, (2) Sin plan contingencia, "
        "(3) Gaps SLA vs RTO, (4) Top 3 recomendaciones con referencia normativa. "
        "Máximo 300 palabras."
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(model=_get_model(db, _org(u)), max_tokens=4096,
                                      messages=[{"role": "user", "content": prompt}])
        return {"analysis": msg.content[0].text}
    except Exception as exc:
        raise HTTPException(500, f"Error: {exc}")


# ── UPLOAD DOCUMENTACIÓN BCM ──────────────────────────────────────────────────

@router.post("/documents/upload", status_code=201)
async def upload_bcm_document(
    request: Request,
    file: UploadFile = File(...),
    location_id: Optional[int] = None,
    db: Session = Depends(get_db),
    u: User = Depends(require_analyst),
):
    """Upload de documentación BCM — usa el pipeline del Agente IA con hint BCM."""
    lang = get_lang(request)
    try:
        from app.services.isms_analysis_service import process_document_upload
        return await process_document_upload(
            file=file, db=db, user=u,
            category_hint="bcp",
            location_id=location_id,
        )
    except (ImportError, TypeError):
        import hashlib
        from pathlib import Path
        content = await file.read()
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(413, _t("bcp.max_50mb", lang))
        docs_dir = _bcm_data_root("documents") / str(_org(u))
        docs_dir.mkdir(parents=True, exist_ok=True)
        sha = hashlib.sha256(content).hexdigest()[:16]
        fpath = docs_dir / f"{sha}_{file.filename}"
        fpath.write_bytes(content)
        return {"message": _t("bcp.document_queued", lang), "filename": file.filename}

# â”€â”€ BCM Context (wizard de configuracion IA) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _ctx_to_dict(ctx):
    return {
        "id": ctx.id,
        "sector": ctx.sector,
        "employees_range": ctx.employees_range,
        "geographic_scope": ctx.geographic_scope,
        "critical_infra": _json.loads(ctx.critical_infra_json or "[]"),
        "risk_scenarios": _json.loads(ctx.risk_scenarios_json or "[]"),
        "regulations": _json.loads(ctx.regulations_json or "[]"),
        "incident_history": ctx.incident_history,
        "rto_target": ctx.rto_target,
        "rpo_target": ctx.rpo_target,
        "max_tolerable_downtime": ctx.max_tolerable_downtime,
        "annual_loss_estimate": ctx.annual_loss_estimate,
        "it_architecture": ctx.it_architecture,
        "key_suppliers": _json.loads(ctx.key_suppliers or "[]"),
        "wizard_completed": ctx.wizard_completed,
        "wizard_step": ctx.wizard_step or 0,
    }


@router.get("/context")
def get_bcm_context(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    ctx = db.query(BCMContext).filter_by(organization_id=_org(u)).first()
    return _ctx_to_dict(ctx) if ctx else {}


@router.post("/context")
def save_bcm_context(body: dict, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    org = _org(u)
    ctx = db.query(BCMContext).filter_by(organization_id=org).first()
    if not ctx:
        ctx = BCMContext(organization_id=org)
        db.add(ctx)
    fields = [
        "sector", "employees_range", "geographic_scope", "incident_history",
        "rto_target", "rpo_target", "max_tolerable_downtime", "annual_loss_estimate",
        "it_architecture", "wizard_completed", "wizard_step",
    ]
    for f in fields:
        if f in body:
            setattr(ctx, f, body[f])
    json_fields = {
        "critical_infra": "critical_infra_json",
        "risk_scenarios": "risk_scenarios_json",
        "regulations": "regulations_json",
        "key_suppliers": "key_suppliers",
    }
    for src, dst in json_fields.items():
        if src in body:
            setattr(ctx, dst, _json.dumps(body[src]))
    db.commit()
    db.refresh(ctx)
    return _ctx_to_dict(ctx)


# â”€â”€ ISO 22301 Compliance scoring â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/compliance/iso22301")
def get_iso22301_compliance(
    request: Request,
    location_id: Optional[int] = None,
    db: Session = Depends(get_db),
    u: User = Depends(get_current_user),
):
    """Score y checklist ISO 22301 del SGCN.

    El cálculo real vive en bcp_service.iso22301_clause_scores(): es el único
    motor de scoring de la aplicación (antes había dos, incompatibles entre sí
    y con heurísticas sin base en evidencia — ver auditoría v5.2). Este endpoint
    solo añade los KPIs informativos y el desglose por sede que consume el
    frontend, que no forman parte del cálculo del score.
    """
    from datetime import timedelta
    from app.services.bcp_service import iso22301_clause_scores
    org = _org(u)
    now = datetime.now(timezone.utc)
    cutoff_12m = now - timedelta(days=365)

    def qf(model):
        q = db.query(model).filter_by(organization_id=org)
        if location_id and hasattr(model, "location_id"):
            q = q.filter(getattr(model, "location_id") == location_id)
        return q.all()

    procs   = qf(BusinessProcess)
    plans   = qf(BCPPlan)
    tests   = qf(BCPTest)
    strats  = qf(BCPStrategy)
    evid    = db.query(BCMEvidenceItem).filter_by(organization_id=org).all()
    locs    = db.query(BCMLocation).filter_by(organization_id=org, is_active=True).all()

    from app.services.bcp_service import bia_completeness
    procs_with_bia = [p for p in procs if bia_completeness(db, p)["pct"] >= 80]
    plans_approved = [p for p in plans if p.status == "approved"]

    def safe_ts(dt):
        if dt is None:
            return None
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    tests_recent = [t for t in tests if safe_ts(t.scheduled_at) and safe_ts(t.scheduled_at) >= cutoff_12m]
    tests_passed = [t for t in tests if t.result == "passed"]
    tests_overdue = [t for t in tests if (not safe_ts(t.scheduled_at) or safe_ts(t.scheduled_at) < cutoff_12m)
                     and t.result not in ("passed", "partial")]
    strats_impl = [s for s in strats if s.implementation_status in ("implemented", "tested")]

    def pct(n, d): return round(n * 100 / d) if d else 0

    result = iso22301_clause_scores(db, org, location_id, lang=get_lang(request))

    loc_list = []
    for loc in locs:
        lp = [p for p in plans if getattr(p, "location_id", None) == loc.id]
        lt = [t for t in tests if getattr(t, "location_id", None) == loc.id]
        lr = [t for t in lt if safe_ts(t.scheduled_at) and safe_ts(t.scheduled_at) >= cutoff_12m]
        # Verde requiere ademas que al menos un test reciente tenga resultado
        # passed/partial — no basta con que haya un test programado sin realizar.
        lr_ok = [t for t in lr if t.result in ("passed", "partial")]
        ls = pct(len([p for p in lp if p.status == "approved"]), max(len(lp), 1))
        status = "green" if ls >= 70 and lr_ok else ("yellow" if ls >= 40 or lr else "red")
        last_t = max((t.scheduled_at for t in lt if t.scheduled_at), default=None)
        loc_list.append({
            "id": loc.id, "name": loc.name, "score": ls, "status": status,
            "plans_approved": len([p for p in lp if p.status == "approved"]),
            "plans_total": len(lp), "tests_total": len(lt),
            "last_test_date": last_t.isoformat()[:10] if last_t else None,
        })

    return {
        "score_global": result["score_global"],
        "clauses": result["clauses"],
        "kpis": {
            "processes_total": len(procs), "processes_with_bia": len(procs_with_bia),
            "plans_total": len(plans), "plans_approved": len(plans_approved),
            "tests_total": len(tests), "tests_recent_12m": len(tests_recent),
            "tests_passed": len(tests_passed), "tests_overdue": len(tests_overdue),
            "strategies_total": len(strats), "strategies_implemented": len(strats_impl),
            "evidence_items": len(evid), "locations_total": len(locs),
        },
        "locations": loc_list,
    }


# â”€â”€ BCM AI Quick chat (panel IA contextual) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _BcmAiBody(BaseModel):
    message: str
    context_hint: str = ""


@router.post("/ai/quick")
def bcm_ai_quick(
    body: _BcmAiBody,
    request: Request,
    db: Session = Depends(get_db),
    u: User = Depends(get_current_user),
):
    lang = get_lang(request)
    org = _org(u, lang)
    ctx = db.query(BCMContext).filter_by(organization_id=org).first()
    procs = db.query(BusinessProcess).filter_by(organization_id=org).limit(20).all()
    plans = db.query(BCPPlan).filter_by(organization_id=org).limit(10).all()

    ctx_block = ""
    if ctx and ctx.wizard_completed:
        ctx_block = (
            f"Contexto organizacional BCM:\n"
            f"- Sector: {ctx.sector or 'N/D'}\n"
            f"- Empleados: {ctx.employees_range or 'N/D'}\n"
            f"- Ambito: {ctx.geographic_scope or 'N/D'}\n"
            f"- Infraestructura critica: {ctx.critical_infra_json or 'N/D'}\n"
            f"- Escenarios de riesgo: {ctx.risk_scenarios_json or 'N/D'}\n"
            f"- Regulaciones: {ctx.regulations_json or 'N/D'}\n"
            f"- RTO objetivo: {ctx.rto_target or 'N/D'} | RPO: {ctx.rpo_target or 'N/D'}\n"
            f"- Arquitectura TI: {ctx.it_architecture or 'N/D'}\n"
        )

    procs_block = "\n".join(
        f"- {p.name} (criticidad: {p.criticality}, RTO: {getattr(p,'rto_hours',None)}h)"
        for p in procs
    ) or "Sin procesos definidos."
    plans_block = "\n".join(
        f"- {p.name} ({p.plan_type}, estado: {p.status})"
        for p in plans
    ) or "Sin planes definidos."

    system_prompt = (
        f"{ai_lang_directive(lang)}\n\n"
        "Eres el Asistente de Continuidad de Negocio de RiskHub, experto en ISO 22301, BCP/DRP y gestion de la continuidad.\n"
        "SÃ© conciso pero preciso. Usa ** para destacar puntos clave.\n"
        "Cuando detectes riesgos o gaps, mencionalos con recomendaciones accionables.\n\n"
        f"{ctx_block}\n"
        f"Procesos criticos:\n{procs_block}\n\n"
        f"Planes BCP/DRP:\n{plans_block}\n\n"
        f"Contexto actual del usuario: {body.context_hint}\n"
    )

    try:
        import anthropic
    except ImportError:
        raise HTTPException(503, _t("bcp.anthropic_unavailable", lang))

    from app.models import AiConfig
    from app.security import decrypt_secret
    _ai_cfg = db.query(AiConfig).filter_by(organization_id=org).first()
    api_key = None
    if _ai_cfg and _ai_cfg.api_key_encrypted:
        try:
            api_key = decrypt_secret(_ai_cfg.api_key_encrypted)
        except Exception:
            pass
    if not api_key:
        api_key = settings.anthropic_api_key
    if not api_key:
        raise HTTPException(503, _t("bcp.ai_key_missing_hint2", lang))

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=(_ai_cfg.model if _ai_cfg and _ai_cfg.model else None) or "claude-haiku-4-5",
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": body.message}],
    )
    return {"response": msg.content[0].text}


# ── ACTIVACIONES: endpoints adicionales ───────────────────────────────────────

@router.get("/activations/{aid}")
def get_activation(aid: int, request: Request, db: Session = Depends(get_db),
                   u: User = Depends(get_current_user)):
    act = _chk_act(db, aid, _org(u), get_lang(request))
    d = _act_d(act)
    attachments = db.query(BCMEvidenceItem).filter_by(
        organization_id=_org(u), linked_activation_id=aid
    ).order_by(BCMEvidenceItem.created_at.desc()).all()
    d["attachments"] = [_evid_d(e) for e in attachments]
    return d


@router.patch("/activations/{aid}")
def update_activation(aid: int, body: dict, request: Request, db: Session = Depends(get_db),
                      u: User = Depends(require_analyst)):
    act = _chk_act(db, aid, _org(u), get_lang(request))
    allowed = {"root_cause", "lessons_learned", "improvement_actions",
               "executive_summary", "affected_services", "rto_objective_hours"}
    for k, v in body.items():
        if k in allowed:
            setattr(act, k, v)
    db.commit()
    return _act_d(act)


@router.post("/activations/{aid}/attachments", status_code=201)
async def upload_activation_attachment(
    aid: int,
    title: str,
    entry_type: str = "file",
    description: Optional[str] = None,
    request: Request = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    u: User = Depends(require_analyst),
):
    """Sube un adjunto a la sala de crisis (PDF, DOCX, imagen, Excel)."""
    import hashlib
    lang = get_lang(request)
    act = _chk_act(db, aid, _org(u, lang), lang)
    ALLOWED_MIME = {
        "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword", "text/plain", "text/csv",
        "image/png", "image/jpeg", "image/gif", "image/webp",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    }
    content = await file.read()
    if len(content) > 30 * 1024 * 1024:
        raise HTTPException(413, _t("bcp.file_too_large_30mb", lang))
    sha256 = hashlib.sha256(content).hexdigest()
    from pathlib import Path
    doc_root = Path(settings.document_storage_path)
    doc_root.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in (file.filename or "file") if c.isalnum() or c in "._-")
    fpath = doc_root / f"act_{aid}_{sha256[:8]}_{safe_name}"
    fpath.write_bytes(content)
    item = BCMEvidenceItem(
        organization_id=_org(u),
        linked_activation_id=aid,
        evidence_type=entry_type,
        title=title,
        description=description,
        file_path=str(fpath),
        file_name=file.filename,
        file_size=len(content),
        mime_type=file.content_type,
        sha256_hash=sha256,
        tags=[],
        uploaded_by_id=u.id,
        is_current=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    log_action(db, u.id, "upload", "bcm_activation_attachment", str(item.id),
               {"activation_id": aid, "title": title})
    return _evid_d(item)


@router.get("/activations/{aid}/attachments")
def list_activation_attachments(aid: int, request: Request, db: Session = Depends(get_db),
                                u: User = Depends(get_current_user)):
    _chk_act(db, aid, _org(u), get_lang(request))
    items = db.query(BCMEvidenceItem).filter_by(
        organization_id=_org(u), linked_activation_id=aid
    ).order_by(BCMEvidenceItem.created_at.desc()).all()
    return [_evid_d(e) for e in items]


@router.delete("/activations/{aid}/attachments/{eid}", status_code=204)
def delete_activation_attachment(aid: int, eid: int, request: Request,
                                  db: Session = Depends(get_db),
                                  u: User = Depends(require_analyst)):
    _chk_act(db, aid, _org(u), get_lang(request))
    item = db.get(BCMEvidenceItem, eid)
    if not item or item.organization_id != _org(u) or item.linked_activation_id != aid:
        raise HTTPException(404)
    try:
        from pathlib import Path
        if item.file_path:
            Path(item.file_path).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(item)
    db.commit()


@router.post("/activations/{aid}/ai-summary")
def generate_activation_ai_summary(aid: int, request: Request, db: Session = Depends(get_db),
                                    u: User = Depends(require_analyst)):
    """Genera un resumen IA de toda la evidencia y el log de la activacion."""
    lang = get_lang(request)
    act = _chk_act(db, aid, _org(u, lang), lang)
    attachments = db.query(BCMEvidenceItem).filter_by(
        organization_id=_org(u), linked_activation_id=aid
    ).all()

    log_text = "\n".join(
        f"[{e.get('timestamp','')[:16]}] ({e.get('entry_type','accion')}) {e.get('text','')}"
        for e in (act.situation_log or [])
    )
    att_text = "\n".join(
        f"- {a.title} ({a.mime_type or ''}, {round((a.file_size or 0)/1024)}KB): {a.description or ''}"
        for a in attachments
    )
    checklist_text = "\n".join(
        f"- [{i.get('status','pending')}] {i.get('title','')}"
        for i in (act.checklist_items or [])
    )

    prompt = (
        f"{ai_lang_directive(lang)}\n\n"
        f"Eres un experto en gestion de incidentes de continuidad de negocio (ISO 22301).\n"
        f"Analiza la siguiente informacion de la activacion BCM {act.code} - {act.title} "
        f"y genera un resumen ejecutivo estructurado con:\n"
        f"1. Resumen del incidente\n2. Cronologia clave\n3. Estado de la recuperacion\n"
        f"4. Evidencia adjunta relevante\n5. Acciones pendientes\n\n"
        f"TIMELINE DE EVENTOS:\n{log_text or 'Sin eventos'}\n\n"
        f"ADJUNTOS ({len(attachments)}):\n{att_text or 'Sin adjuntos'}\n\n"
        f"CHECKLIST:\n{checklist_text or 'Sin checklist'}\n\n"
        f"Activado: {act.activated_at.isoformat()[:16] if act.activated_at else '?'} | "
        f"Estado: {act.status}"
    )

    try:
        import anthropic
    except ImportError:
        raise HTTPException(503, _t("bcp.anthropic_unavailable", lang))

    from app.models import AiConfig
    from app.security import decrypt_secret
    _ai_cfg = db.query(AiConfig).filter_by(organization_id=_org(u)).first()
    api_key = None
    if _ai_cfg and _ai_cfg.api_key_encrypted:
        try:
            api_key = decrypt_secret(_ai_cfg.api_key_encrypted)
        except Exception:
            pass
    if not api_key:
        api_key = settings.anthropic_api_key
    if not api_key:
        raise HTTPException(503, _t("bcp.api_key_not_configured", lang))

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=(_ai_cfg.model if _ai_cfg and _ai_cfg.model else None) or "claude-haiku-4-5",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    summary = msg.content[0].text
    act.ai_summary = summary
    db.commit()
    return {"summary": summary}


@router.get("/activations/{aid}/report")
def activation_report(aid: int, request: Request, db: Session = Depends(get_db),
                      u: User = Depends(get_current_user)):
    """Retorna los datos completos para el informe post-mortem de la activacion."""
    act = _chk_act(db, aid, _org(u), get_lang(request))
    attachments = db.query(BCMEvidenceItem).filter_by(
        organization_id=_org(u), linked_activation_id=aid
    ).all()
    plans = []
    for pid in (act.activated_plan_ids or []):
        p = db.get(BCPPlan, pid)
        if p:
            plans.append({"id": p.id, "code": p.code, "name": p.name, "plan_type": p.plan_type})

    # Linked incident
    linked_inc = None
    if act.incident_id:
        from app.models import Incident
        inc = db.get(Incident, act.incident_id)
        if inc:
            linked_inc = {
                "id": inc.id, "code": inc.code, "title": inc.title,
                "severity": inc.severity.value if hasattr(inc.severity, 'value') else str(inc.severity),
                "detected_at": inc.detected_at.isoformat() if inc.detected_at else None,
                "root_cause": inc.root_cause,
            }

    duration_minutes = None
    if act.closed_at and act.activated_at:
        duration_minutes = int(
            (act.closed_at.replace(tzinfo=timezone.utc) - act.activated_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
        )

    return {
        "activation": _act_d(act),
        "plans": plans,
        "linked_incident": linked_inc,
        "attachments": [_evid_d(e) for e in attachments],
        "duration_minutes": duration_minutes,
        "log_entries_count": len(act.situation_log or []),
        "checklist_done": sum(1 for i in (act.checklist_items or []) if i.get("status") == "done"),
        "checklist_total": len(act.checklist_items or []),
    }


# ── PLAN VERSIONING — crear nueva version editable ───────────────────────────

@router.post("/plans/{pid}/new-version", status_code=201)
def create_plan_new_version(pid: int, request: Request, db: Session = Depends(get_db),
                             u: User = Depends(require_analyst)):
    """Crea un borrador editable a partir de un plan aprobado u obsoleto."""
    original = db.get(BCPPlan, pid)
    if not original or original.organization_id != _org(u):
        raise HTTPException(404)
    if original.status not in ("approved", "obsolete", "deprecated", "under_review"):
        raise HTTPException(422, _t("bcp.new_version_only_approved", get_lang(request)))

    # Incrementar version string
    try:
        parts = (original.version or "1.0").split(".")
        new_version = f"{parts[0]}.{int(parts[1]) + 1}" if len(parts) == 2 else f"{original.version}.1"
    except Exception:
        new_version = f"{original.version or '1'}.1"

    n = db.query(BCPPlan).filter_by(organization_id=_org(u)).count()
    new_plan = BCPPlan(
        organization_id=_org(u),
        code=original.code,
        plan_type=original.plan_type,
        name=original.name,
        version=new_version,
        status="draft",
        scope=original.scope,
        activation_criteria=original.activation_criteria,
        content_summary=original.content_summary,
        process_ids=list(original.process_ids or []),
        team_members=list(original.team_members or []),
        sections=list(original.sections or []),
        roles_matrix=list(original.roles_matrix or []),
        contact_list=list(original.contact_list or []),
        system_dependencies=list(original.system_dependencies or []),
        kpis=list(original.kpis or []),
        plan_owner_name=original.plan_owner_name,
        classification=original.classification,
        dr_site=dict(original.dr_site) if original.dr_site else None,
        backup_policy=dict(original.backup_policy) if original.backup_policy else None,
        crisis_comms=dict(original.crisis_comms) if original.crisis_comms else None,
        location_id=original.location_id,
        checklist_template=list(original.checklist_template or []),
        installation_type=original.installation_type,
        data_classification_level=original.data_classification_level,
        gdpr_data=original.gdpr_data,
        affected_users_count=original.affected_users_count,
        documentation_links=list(original.documentation_links or []),
        related_documents=list(original.related_documents or []),
        authorized_activators=list(original.authorized_activators or []),
        parent_plan_id=pid,
    )
    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)
    log_action(db, u.id, "create_version", "bcp_plan", str(new_plan.id),
               {"code": new_plan.code, "version": new_version, "parent_id": pid})
    return _plan_d(new_plan)


# ── CONTEXT AUTOFILL — sugerencias automaticas para el wizard BCM ─────────────

@router.get("/context/autofill")
def context_autofill(request: Request, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    """Sugiere valores para el wizard BCM a partir de activos, documentos y proveedores."""
    from app.models import Asset, AiDocument, Supplier
    lang = get_lang(request)
    org = _org(u, lang)

    # Sistemas criticos por DISPONIBILIDAD, que es la dimension que importa en
    # continuidad. Antes se filtraba por `Asset.criticality`, columna que no
    # existe en el modelo: el endpoint devolvia 500 en cuanto se llamaba.
    assets = db.query(Asset).filter_by(organization_id=org).filter(
        Asset.value_availability >= 4
    ).order_by(Asset.value_availability.desc()).limit(30).all()
    critical_systems = [
        f"{a.name} ({a.asset_type or _t('bcp.asset_type_fallback', lang)})" for a in assets
    ]

    # Proveedores criticos
    suppliers = db.query(Supplier).filter_by(organization_id=org).filter(
        (Supplier.is_critical == True) |
        (Supplier.risk_level == "CRITICAL") |
        (Supplier.tier == "CRITICAL")
    ).limit(20).all()
    key_suppliers = [
        f"{s.name}{' — ' + s.service_type if getattr(s,'service_type',None) else ''}"
        for s in suppliers
    ]

    # Arquitectura TI desde documentos analizados
    docs = db.query(AiDocument).filter_by(organization_id=org).filter(
        AiDocument.isms_status == "analyzed"
    ).limit(5).all()
    it_arch_hint = None
    if docs:
        # Heuristic: check if any doc mention cloud/on-premise/hybrid
        for doc in docs:
            summary = getattr(doc, 'isms_summary', None) or {}
            if isinstance(summary, dict):
                notes = str(summary.get('notes', '') or '')
                if 'cloud' in notes.lower():
                    it_arch_hint = 'cloud'
                    break
                elif 'on-prem' in notes.lower() or 'on premise' in notes.lower():
                    it_arch_hint = 'on_prem'
                    break

    return {
        "critical_systems": critical_systems,
        "key_suppliers": key_suppliers,
        "it_arch_hint": it_arch_hint,
        "sources": {
            "assets_found": len(assets),
            "suppliers_found": len(suppliers),
        },
    }


# ── Activacion de crisis (bucle cerrado con registro de riesgos ISO 27005) ──────

@router.post("/plans/{pid}/activate")
async def activate_bcp_plan(
    pid: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Activa un plan BCP en modo crisis (cierre de bucle: reduce residual risk vinculado)."""
    lang = get_lang(request)
    # BUG3 fix: use _org() which raises HTTP 400 if no org, preventing None != None bypass
    org = _org(current_user, lang)
    plan = db.get(BCPPlan, pid)
    if not plan or plan.organization_id != org:
        raise HTTPException(status_code=404, detail=_t("bcp.plan_not_found", lang))
    if plan.activation_status == "activated":
        raise HTTPException(status_code=409, detail=_t("bcp.plan_already_activated", lang))

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    plan.activation_status = "activated"
    plan.activated_at = now
    plan.activated_by_id = current_user.id

    log_entry = {
        "timestamp": now.isoformat(),
        "action": "activated",
        "user": current_user.full_name,
        "notes": payload.get("notes", ""),
    }
    plan.activation_log = (plan.activation_log or []) + [log_entry]
    db.commit()

    # Bucle cerrado: cuando BCP se activa, reduce el residual de riesgos vinculados
    if plan.risk_ids:
        from app.models import Risk
        for rid in plan.risk_ids:
            r = db.get(Risk, rid)
            if r and r.organization_id == org:
                if r.residual_likelihood and r.residual_likelihood > 0:
                    r.residual_likelihood = max(0, r.residual_likelihood - 1)
                    from app.routers.risks import _recalc
                    try:
                        _recalc(db, r)
                    except Exception:
                        pass
        db.commit()

    return {"plan_id": pid, "activation_status": "activated", "activated_at": now.isoformat()}


@router.post("/plans/{pid}/deactivate")
async def deactivate_bcp_plan(
    pid: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Desactiva un plan BCP de crisis."""
    lang = get_lang(request)
    # BUG3 fix: use _org() which raises HTTP 400 if no org, preventing None != None bypass
    org = _org(current_user, lang)
    plan = db.get(BCPPlan, pid)
    if not plan or plan.organization_id != org:
        raise HTTPException(status_code=404, detail=_t("bcp.plan_not_found", lang))
    # BUG4 fix: verify plan is currently activated before deactivating
    if plan.activation_status != "activated":
        raise HTTPException(status_code=409, detail=_t("bcp.plan_not_activated", lang))

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    plan.activation_status = "standby"
    plan.deactivated_at = now

    log_entry = {
        "timestamp": now.isoformat(),
        "action": "deactivated",
        "user": current_user.full_name,
        "notes": payload.get("notes", ""),
    }
    plan.activation_log = (plan.activation_log or []) + [log_entry]
    db.commit()
    return {"plan_id": pid, "activation_status": "standby"}


@router.patch("/plans/{pid}/risk-links")
async def link_risks_to_bcp(
    pid: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Vincula/desvincula riesgos ISO 27005 a un plan BCP para bucle cerrado de mitigacion."""
    lang = get_lang(request)
    # BUG3/BUG5 fix: use _org() which raises HTTP 400 if no org
    org = _org(current_user, lang)
    plan = db.get(BCPPlan, pid)
    if not plan or plan.organization_id != org:
        raise HTTPException(status_code=404, detail=_t("bcp.plan_not_found", lang))

    risk_ids = payload.get("risk_ids", [])
    if not isinstance(risk_ids, list):
        raise HTTPException(status_code=400, detail=_t("bcp.risk_ids_must_be_list", lang))

    # BUG5 fix: validate each risk belongs to the same org (IDOR prevention)
    from app.models import Risk
    for rid in risk_ids:
        r = db.get(Risk, rid)
        if not r or r.organization_id != org:
            raise HTTPException(status_code=422, detail=_t("bcp.risk_not_in_org", lang, id=rid))

    plan.risk_ids = risk_ids
    db.commit()
    return {"plan_id": pid, "risk_ids": risk_ids}


# ══════════════════════════════════════════════════════════════════════════════
# ESCENARIOS DE INDISPONIBILIDAD — catalogo, reglas, valoraciones y baremos
#
# El BIA canonico de ISO 22301 gira sobre procesos, pero muchas organizaciones
# lo construyen sobre escenarios de indisponibilidad valorados en cada sede.
# Ambos conviven. Todo lo que sea calculo (impacto ponderado, banda,
# aplicabilidad) lo hace bcm_scenario_engine, nunca el cliente ni la IA.
# ══════════════════════════════════════════════════════════════════════════════

VALID_SCENARIO_FAMILIES = ("personnel", "systems_comms", "third_party", "facilities")
_RULE_WHEN_FIELDS = ("site_type", "country", "city", "staffing_model", "business_unit")
_RULE_THEN_KEYS = ("exclude_families", "exclude_scenarios", "include_only_families")


class ScenarioIn(BaseModel):
    code: Optional[str] = None
    name: str
    family: str
    description: Optional[str] = None
    procedure_notes: Optional[str] = None
    responsible_area: Optional[str] = None
    is_active: Optional[bool] = True


class ScenarioUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    family: Optional[str] = None
    description: Optional[str] = None
    procedure_notes: Optional[str] = None
    responsible_area: Optional[str] = None
    is_active: Optional[bool] = None


class ApplicabilityRuleIn(BaseModel):
    name: Optional[str] = None
    when: dict
    then: dict
    rationale: Optional[str] = None
    priority: Optional[int] = 100
    is_active: Optional[bool] = True


class ApplicabilityRuleUpdate(BaseModel):
    name: Optional[str] = None
    when: Optional[dict] = None
    then: Optional[dict] = None
    rationale: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class AssessmentIn(BaseModel):
    scenario_id: int
    location_id: Optional[int] = None
    process_id: Optional[int] = None
    mtpd_hours: Optional[float] = None
    rto_label: Optional[str] = None
    rto_hours: Optional[float] = None
    rpo_label: Optional[str] = None
    rpo_hours: Optional[float] = None
    impacts: Optional[dict] = None
    dependencies_note: Optional[str] = None
    responsible_id: Optional[int] = None


class AssessmentUpdate(BaseModel):
    location_id: Optional[int] = None
    process_id: Optional[int] = None
    mtpd_hours: Optional[float] = None
    rto_label: Optional[str] = None
    rto_hours: Optional[float] = None
    rpo_label: Optional[str] = None
    rpo_hours: Optional[float] = None
    impacts: Optional[dict] = None
    dependencies_note: Optional[str] = None
    responsible_id: Optional[int] = None
    needs_review: Optional[bool] = None


class BIACriteriaIn(BaseModel):
    dimensions: Optional[list] = None
    horizons: Optional[list] = None
    levels: Optional[list] = None
    rto_scale: Optional[list] = None
    bands: Optional[list] = None
    aggregation: Optional[str] = None


def _scenario_d(s) -> dict:
    return {
        "id": s.id, "code": s.code, "name": s.name, "family": s.family,
        "description": s.description, "procedure_notes": s.procedure_notes,
        "responsible_area": s.responsible_area, "source": s.source,
        "is_active": s.is_active, "import_batch_id": s.import_batch_id,
    }


def _rule_d(r) -> dict:
    return {
        "id": r.id, "name": r.name, "when": r.when, "then": r.then,
        "rationale": r.rationale, "source": r.source, "priority": r.priority,
        "is_active": r.is_active,
    }


def _assessment_d(a) -> dict:
    return {
        "id": a.id, "scenario_id": a.scenario_id, "location_id": a.location_id,
        "process_id": a.process_id, "mtpd_hours": a.mtpd_hours,
        "rto_label": a.rto_label, "rto_hours": a.rto_hours,
        "rpo_label": a.rpo_label, "rpo_hours": a.rpo_hours,
        "impacts": a.impacts,
        "weighted_impact": a.weighted_impact, "impact_band": a.impact_band,
        "dependencies_note": a.dependencies_note,
        "responsible_id": a.responsible_id,
        "needs_review": a.needs_review, "import_confidence": a.import_confidence,
        "source": a.source, "import_batch_id": a.import_batch_id,
        "assessed_at": a.assessed_at.isoformat() if a.assessed_at else None,
    }


def _chk_scenario(db, sid, org_id, lang="es"):
    from app.models import BCMScenario
    sc = db.get(BCMScenario, sid)
    if not sc or sc.organization_id != org_id:
        raise HTTPException(404, _t("bcp.scenario_not_found", lang))
    return sc


def _next_scenario_code(db, org_id: int) -> str:
    from app.models import BCMScenario
    n = db.query(BCMScenario).filter_by(organization_id=org_id).count()
    return f"ESC-{n + 1:03d}"


def _validate_rule(when: Optional[dict], then: Optional[dict], lang: str) -> None:
    """Una regla mal formada silenciaria escenarios sin que nadie se entere."""
    if not when or not isinstance(when, dict):
        raise HTTPException(422, _t("bcp.rule_when_required", lang))
    for key in when:
        if key not in _RULE_WHEN_FIELDS:
            raise HTTPException(422, _t("bcp.rule_when_invalid_field", lang, field=key,
                                        valid=", ".join(_RULE_WHEN_FIELDS)))
    if not then or not isinstance(then, dict):
        raise HTTPException(422, _t("bcp.rule_then_required", lang))
    if not any(k in then for k in _RULE_THEN_KEYS):
        raise HTTPException(422, _t("bcp.rule_then_invalid", lang,
                                    valid=", ".join(_RULE_THEN_KEYS)))
    for key in ("exclude_families", "include_only_families"):
        for fam in (then.get(key) or []):
            if fam not in VALID_SCENARIO_FAMILIES:
                raise HTTPException(422, _t("bcp.invalid_scenario_family", lang,
                                            valid=", ".join(VALID_SCENARIO_FAMILIES)))


# ── Catalogo de escenarios ────────────────────────────────────────────────────

@router.get("/scenarios")
def list_scenarios(include_inactive: bool = False, db: Session = Depends(get_db),
                   u: User = Depends(get_current_user)):
    from app.models import BCMScenario
    q = db.query(BCMScenario).filter_by(organization_id=_org(u))
    if not include_inactive:
        q = q.filter(BCMScenario.is_active.is_(True))
    rows = q.order_by(BCMScenario.family, BCMScenario.code).all()
    return [_scenario_d(s) for s in rows]


@router.get("/scenarios/matrix")
def scenarios_matrix(location_id: Optional[int] = None, db: Session = Depends(get_db),
                     u: User = Depends(get_current_user)):
    """Matriz escenario x sede: que aplica, que esta valorado y que falta."""
    from app.services.bcm_scenario_engine import scenario_matrix
    return scenario_matrix(db, _org(u), location_id)


@router.get("/scenarios/gaps")
def scenarios_gaps(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    """Huecos accionables: sin valorar, sin estrategia, sin plan o sin ejercitar."""
    from app.services.bcm_scenario_engine import coverage_gaps
    return coverage_gaps(db, _org(u))


@router.post("/scenarios", status_code=201)
def create_scenario(body: ScenarioIn, request: Request, db: Session = Depends(get_db),
                    u: User = Depends(require_analyst)):
    from app.models import BCMScenario
    lang = get_lang(request)
    org = _org(u, lang)
    if body.family not in VALID_SCENARIO_FAMILIES:
        raise HTTPException(422, _t("bcp.invalid_scenario_family", lang,
                                    valid=", ".join(VALID_SCENARIO_FAMILIES)))
    sc = BCMScenario(
        organization_id=org,
        code=(body.code or _next_scenario_code(db, org)),
        name=body.name, family=body.family,
        description=body.description, procedure_notes=body.procedure_notes,
        responsible_area=body.responsible_area,
        is_active=True if body.is_active is None else body.is_active,
        source="manual",
    )
    db.add(sc)
    db.commit()
    db.refresh(sc)
    log_action(db, u.id, "create", "bcm_scenario", str(sc.id),
               {"code": sc.code, "name": sc.name})
    return _scenario_d(sc)


@router.patch("/scenarios/{sid}")
def update_scenario(sid: int, body: ScenarioUpdate, request: Request,
                    db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    lang = get_lang(request)
    sc = _chk_scenario(db, sid, _org(u, lang), lang)
    data = body.model_dump(exclude_none=True)
    if "family" in data and data["family"] not in VALID_SCENARIO_FAMILIES:
        raise HTTPException(422, _t("bcp.invalid_scenario_family", lang,
                                    valid=", ".join(VALID_SCENARIO_FAMILIES)))
    for k, v in data.items():
        setattr(sc, k, v)
    db.commit()
    return _scenario_d(sc)


@router.delete("/scenarios/{sid}", status_code=204)
def delete_scenario(sid: int, request: Request, db: Session = Depends(get_db),
                    u: User = Depends(require_admin)):
    from app.models import BCMScenarioAssessment
    lang = get_lang(request)
    org = _org(u, lang)
    sc = _chk_scenario(db, sid, org, lang)
    n = db.query(BCMScenarioAssessment).filter_by(
        organization_id=org, scenario_id=sid).count()
    if n:
        # No se borra en silencio lo que sostiene valoraciones del BIA: se
        # desactiva, que conserva la trazabilidad historica.
        raise HTTPException(422, _t("bcp.scenario_has_assessments", lang, n=n))
    db.delete(sc)
    db.commit()


# ── Reglas de aplicabilidad ───────────────────────────────────────────────────

@router.get("/applicability-rules")
def list_applicability_rules(db: Session = Depends(get_db),
                             u: User = Depends(get_current_user)):
    """Reglas que restringen que escenarios aplican a que sedes.

    Lista vacia es el estado normal y correcto: sin reglas, todos los escenarios
    aplican a todas las sedes.
    """
    from app.models import BCMApplicabilityRule
    rows = db.query(BCMApplicabilityRule).filter_by(
        organization_id=_org(u)
    ).order_by(BCMApplicabilityRule.priority).all()
    return [_rule_d(r) for r in rows]


@router.post("/applicability-rules", status_code=201)
def create_applicability_rule(body: ApplicabilityRuleIn, request: Request,
                              db: Session = Depends(get_db),
                              u: User = Depends(require_analyst)):
    from app.models import BCMApplicabilityRule
    lang = get_lang(request)
    _validate_rule(body.when, body.then, lang)
    rule = BCMApplicabilityRule(
        organization_id=_org(u, lang),
        name=body.name, when=body.when, then=body.then,
        rationale=body.rationale,
        priority=body.priority if body.priority is not None else 100,
        is_active=True if body.is_active is None else body.is_active,
        source="manual",
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    log_action(db, u.id, "create", "bcm_applicability_rule", str(rule.id),
               {"when": rule.when, "then": rule.then})
    return _rule_d(rule)


@router.patch("/applicability-rules/{rid}")
def update_applicability_rule(rid: int, body: ApplicabilityRuleUpdate, request: Request,
                              db: Session = Depends(get_db),
                              u: User = Depends(require_analyst)):
    from app.models import BCMApplicabilityRule
    lang = get_lang(request)
    rule = db.get(BCMApplicabilityRule, rid)
    if not rule or rule.organization_id != _org(u, lang):
        raise HTTPException(404, _t("bcp.applicability_rule_not_found", lang))
    data = body.model_dump(exclude_none=True)
    _validate_rule(data.get("when", rule.when), data.get("then", rule.then), lang)
    for k, v in data.items():
        setattr(rule, k, v)
    db.commit()
    return _rule_d(rule)


@router.delete("/applicability-rules/{rid}", status_code=204)
def delete_applicability_rule(rid: int, request: Request, db: Session = Depends(get_db),
                              u: User = Depends(require_analyst)):
    from app.models import BCMApplicabilityRule
    lang = get_lang(request)
    rule = db.get(BCMApplicabilityRule, rid)
    if not rule or rule.organization_id != _org(u, lang):
        raise HTTPException(404, _t("bcp.applicability_rule_not_found", lang))
    db.delete(rule)
    db.commit()


# ── Valoraciones BIA por escenario ────────────────────────────────────────────

@router.get("/scenario-assessments")
def list_assessments(scenario_id: Optional[int] = None, location_id: Optional[int] = None,
                     db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    from app.models import BCMScenarioAssessment
    q = db.query(BCMScenarioAssessment).filter_by(organization_id=_org(u))
    if scenario_id:
        q = q.filter(BCMScenarioAssessment.scenario_id == scenario_id)
    if location_id:
        q = q.filter(BCMScenarioAssessment.location_id == location_id)
    return [_assessment_d(a) for a in q.all()]


@router.post("/scenario-assessments", status_code=201)
def create_assessment(body: AssessmentIn, request: Request, db: Session = Depends(get_db),
                      u: User = Depends(require_analyst)):
    from app.models import BCMScenarioAssessment
    from app.services.bcm_scenario_engine import get_criteria, recompute_assessment
    lang = get_lang(request)
    org = _org(u, lang)
    _chk_scenario(db, body.scenario_id, org, lang)
    if body.location_id:
        _chk_loc(db, body.location_id, org, lang)

    existing = db.query(BCMScenarioAssessment).filter_by(
        organization_id=org, scenario_id=body.scenario_id,
        location_id=body.location_id,
    ).first()
    if existing:
        raise HTTPException(409, _t("bcp.assessment_already_exists", lang))

    a = BCMScenarioAssessment(
        organization_id=org, source="manual",
        assessed_at=datetime.now(timezone.utc),
        **body.model_dump(exclude_none=True),
    )
    # El impacto ponderado y la banda son SIEMPRE calculados, nunca de entrada
    recompute_assessment(a, get_criteria(db, org))
    db.add(a)
    db.commit()
    db.refresh(a)
    log_action(db, u.id, "create", "bcm_scenario_assessment", str(a.id),
               {"scenario_id": a.scenario_id, "location_id": a.location_id})
    return _assessment_d(a)


@router.patch("/scenario-assessments/{aid}")
def update_assessment(aid: int, body: AssessmentUpdate, request: Request,
                      db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    from app.models import BCMScenarioAssessment
    from app.services.bcm_scenario_engine import get_criteria, recompute_assessment
    lang = get_lang(request)
    org = _org(u, lang)
    a = db.get(BCMScenarioAssessment, aid)
    if not a or a.organization_id != org:
        raise HTTPException(404, _t("bcp.assessment_not_found", lang))
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    a.assessed_at = datetime.now(timezone.utc)
    recompute_assessment(a, get_criteria(db, org))
    db.commit()
    return _assessment_d(a)


@router.delete("/scenario-assessments/{aid}", status_code=204)
def delete_assessment(aid: int, request: Request, db: Session = Depends(get_db),
                      u: User = Depends(require_analyst)):
    from app.models import BCMScenarioAssessment
    lang = get_lang(request)
    a = db.get(BCMScenarioAssessment, aid)
    if not a or a.organization_id != _org(u, lang):
        raise HTTPException(404, _t("bcp.assessment_not_found", lang))
    db.delete(a)
    db.commit()


# ── Baremos del BIA ───────────────────────────────────────────────────────────

@router.get("/bia-criteria")
def get_bia_criteria(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    """Metodo de valoracion de la organizacion.

    Devuelve siempre un baremo utilizable: si la organizacion no ha declarado el
    suyo, se sirve el de referencia con `is_default` a true.
    """
    from app.models import BIACriteria
    from app.services.bcm_scenario_engine import get_criteria
    org = _org(u)
    row = db.query(BIACriteria).filter_by(organization_id=org).first()
    return {**get_criteria(db, org), "is_default": row is None}


@router.put("/bia-criteria")
def put_bia_criteria(body: BIACriteriaIn, request: Request, db: Session = Depends(get_db),
                     u: User = Depends(require_analyst)):
    """Cambia el metodo y recalcula el BIA entero. El dato no se toca, la cifra si."""
    from app.models import BIACriteria
    from app.services.bcm_scenario_engine import get_criteria, recompute_org
    lang = get_lang(request)
    org = _org(u, lang)
    row = db.query(BIACriteria).filter_by(organization_id=org).first()
    if not row:
        row = BIACriteria(organization_id=org)
        db.add(row)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(row, k, v)
    db.commit()
    recalculated = recompute_org(db, org)
    log_action(db, u.id, "update", "bia_criteria", str(row.id),
               {"recalculated": recalculated})
    return {**get_criteria(db, org), "is_default": False, "recalculated": recalculated}


# ── Generacion sin documentacion ──────────────────────────────────────────────
#
# La mitad de los clientes llega con un pack documental y la otra mitad con
# nada. Estas rutas cubren el segundo caso por el mismo camino que la ingesta:
# lo propuesto se materializa en un lote reversible y hereda sus garantias.

@router.get("/generate/questions")
def generation_questions(db: Session = Depends(get_db),
                         u: User = Depends(get_current_user)):
    """Lo que hace falta saber y no se puede deducir de lo ya cargado.

    Sustituye al cuestionario fijo: preguntar por el sector cuando ya hay
    cuarenta activos cargados es hacerle perder el tiempo al cliente.
    """
    from app.services.ingest.generation import pending_questions
    return {"questions": pending_questions(db, _org(u))}


@router.get("/generate/context")
def generation_context(db: Session = Depends(get_db),
                       u: User = Depends(get_current_user)):
    """Lo que el agente usaria para proponer. Util para ver por que propone."""
    from app.services.ingest.generation import gather_context
    return gather_context(db, _org(u))


@router.post("/generate/{target}", status_code=201)
def generate_bcm(target: str, body: dict = None, request: Request = None,
                 db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    """Genera un borrador (escenarios, BIA, plan o estrategias) desde el contexto."""
    from app.services.ingest.generation import TARGETS, generate
    lang = get_lang(request)
    org = _org(u, lang)
    if target not in TARGETS:
        raise HTTPException(422, _t("bcp.invalid_generation_target", lang,
                                    valid=", ".join(TARGETS)))
    body = body or {}
    try:
        result = generate(db, org, target, user_id=u.id, lang=lang,
                          plan_type=body.get("plan_type", "bcp"),
                          scope=body.get("scope"))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    log_action(db, u.id, "generate", "bcm_" + target,
               str(result.get("batch_id")), {"status": result.get("status")})
    return result
