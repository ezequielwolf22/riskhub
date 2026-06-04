"""Router BCP/BIA — Business Continuity Planning (NIS2 Art. 21.2b + ISO 27001 A.5.29 + ISO 22301)."""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    BCPDependency, BCPExerciseProgramme, BCPPlan, BCPStrategy,
    BCPSupplierLink, BCPTest, BusinessProcess, Supplier, User, UserRole,
)
from app.security import get_current_user, require_admin, require_analyst
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.bcp")

router = APIRouter(prefix="/api/bcp", tags=["bcp"])

VALID_CRITICALITY = ("critical", "high", "medium", "low")
VALID_TEST_TYPES = ("tabletop", "simulation", "full_test")
VALID_TEST_RESULTS = ("passed", "partial", "failed")
VALID_DEP_TYPES = (
    "IT_system", "personnel", "facility", "supplier",
    "utility", "communication", "transport", "external_service",
)
VALID_STRATEGY_TYPES = (
    "hot_site", "cold_site", "warm_site", "work_from_home",
    "outsourcing", "manual_workaround", "dual_site", "cloud_failover",
)
VALID_PLAN_TYPES = ("bcp", "drp", "crp", "ems", "pandemic", "cyber_response", "supply_chain")
VALID_IMPL_STATUS = ("planned", "in_progress", "implemented", "tested")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _org(u: User) -> int:
    if not u.organization_id:
        raise HTTPException(400, "Usuario sin organización asignada")
    return u.organization_id


def _parse_dt(s, field_name: str = "fecha"):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s))
    except (ValueError, TypeError):
        raise HTTPException(422, f"{field_name} debe ser ISO 8601 (ej: 2025-01-15T10:00:00)")


def _next_bct(db: Session, org_id: int) -> str:
    count = db.query(BCPTest).filter_by(organization_id=org_id).count()
    return f"BCT-{count + 1:04d}"


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
        "created_at": p.created_at.isoformat() if p.created_at else None,
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


class StratIn(BaseModel):
    process_id: Optional[int] = None
    strategy_type: str
    name: str
    description: Optional[str] = None
    estimated_cost: Optional[float] = None
    implementation_status: str = "planned"
    responsible_id: Optional[int] = None
    target_date: Optional[str] = None


class StratUpdate(BaseModel):
    process_id: Optional[int] = None
    strategy_type: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    estimated_cost: Optional[float] = None
    implementation_status: Optional[str] = None
    responsible_id: Optional[int] = None
    target_date: Optional[str] = None


class PlanIn(BaseModel):
    plan_type: str = "bcp"
    name: str
    version: str = "1.0"
    scope: Optional[str] = None
    activation_criteria: Optional[str] = None
    content_summary: Optional[str] = None
    document_id: Optional[int] = None
    process_ids: Optional[list] = None
    team_members: Optional[list] = None
    review_date: Optional[str] = None


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


class TestIn(BaseModel):
    test_type: str
    process_ids: Optional[List[int]] = None
    scheduled_at: str
    objective: Optional[str] = None
    scope_description: Optional[str] = None
    participants: Optional[list] = None
    facilitator_id: Optional[int] = None


class TestUpdate(BaseModel):
    conducted_at: Optional[str] = None
    result: Optional[str] = None
    findings: Optional[str] = None
    lessons_learned: Optional[str] = None
    improvement_actions: Optional[str] = None
    evidence_doc_ids: Optional[list] = None


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
def iso22301_status(db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    from app.services.bcp_service import iso22301_status as _status
    return _status(db, _org(u))


# ── BIA completeness ──────────────────────────────────────────────────────────

@router.get("/bia")
def bia_overview(db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    from app.services.bcp_service import bia_completeness
    org = _org(u)
    procs = db.query(BusinessProcess).filter_by(organization_id=org).all()
    return [{"id": p.id, "name": p.name, "criticality": p.criticality,
             **bia_completeness(db, p)} for p in procs]


# ── Procesos ──────────────────────────────────────────────────────────────────

@router.get("/processes")
def list_processes(db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    org = _org(u)
    return [_proc_d(p) for p in db.query(BusinessProcess).filter_by(
        organization_id=org).order_by(BusinessProcess.criticality).all()]


@router.post("/processes", status_code=201)
def create_process(body: ProcessIn, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    if body.criticality not in VALID_CRITICALITY:
        raise HTTPException(422, f"criticality inválido. Válidos: {VALID_CRITICALITY}")
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
def update_process(pid: int, body: ProcessUpdate, db: Session = Depends(get_db),
                   u: User = Depends(require_analyst)):
    p = db.get(BusinessProcess, pid)
    if not p or p.organization_id != _org(u):
        raise HTTPException(404)
    if body.criticality and body.criticality not in VALID_CRITICALITY:
        raise HTTPException(422, "criticality inválido")
    # GDPR: escalation_contacts puede contener datos personales (Art. 6(1)(f) RGPD).
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    db.commit()
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
              u: User = Depends(require_analyst)):
    q = db.query(BCPDependency).filter_by(organization_id=_org(u))
    if process_id:
        q = q.filter_by(process_id=process_id)
    return [_dep_d(d) for d in q.all()]


@router.post("/dependencies", status_code=201)
def create_dep(body: DepIn, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    org = _org(u)
    if body.dependency_type not in VALID_DEP_TYPES:
        raise HTTPException(422, "dependency_type inválido")
    proc = db.get(BusinessProcess, body.process_id)
    if not proc or proc.organization_id != org:
        raise HTTPException(422, "Proceso no encontrado en esta organización")
    d = BCPDependency(organization_id=org, **body.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    log_action(db, u.id, "create", "bcp_dependency", str(d.id),
               {"name": d.name, "type": d.dependency_type})
    return _dep_d(d)


@router.patch("/dependencies/{did}")
def update_dep(did: int, body: DepUpdate, db: Session = Depends(get_db),
               u: User = Depends(require_analyst)):
    d = db.get(BCPDependency, did)
    if not d or d.organization_id != _org(u):
        raise HTTPException(404)
    for k, v in body.model_dump(exclude_none=True).items():
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
def list_strats(db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    return [_strat_d(s) for s in db.query(BCPStrategy).filter_by(
        organization_id=_org(u)).all()]


@router.post("/strategies", status_code=201)
def create_strat(body: StratIn, db: Session = Depends(get_db),
                 u: User = Depends(require_analyst)):
    if body.strategy_type not in VALID_STRATEGY_TYPES:
        raise HTTPException(422, "strategy_type inválido")
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
    return _strat_d(s)


@router.patch("/strategies/{sid}")
def update_strat(sid: int, body: StratUpdate, db: Session = Depends(get_db),
                 u: User = Depends(require_analyst)):
    s = db.get(BCPStrategy, sid)
    if not s or s.organization_id != _org(u):
        raise HTTPException(404)
    for k, v in body.model_dump(exclude_none=True).items():
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
def list_plans(db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    return [_plan_d(p) for p in db.query(BCPPlan).filter_by(
        organization_id=_org(u)).order_by(BCPPlan.created_at.desc()).all()]


@router.post("/plans", status_code=201)
def create_plan(body: PlanIn, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    if body.plan_type not in VALID_PLAN_TYPES:
        raise HTTPException(422, "plan_type inválido")
    org = _org(u)
    # B2 — IDOR prevention: verificar que el documento pertenece a la misma organización
    if body.document_id:
        from app.models import AiDocument
        doc = db.get(AiDocument, body.document_id)
        if not doc or doc.organization_id != org:
            raise HTTPException(422, "Documento no encontrado en esta organización")
    from app.services.bcp_service import next_plan_code
    p = BCPPlan(
        organization_id=org,
        code=next_plan_code(db, org, body.plan_type),
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


@router.patch("/plans/{pid}")
def update_plan(pid: int, body: PlanUpdate, db: Session = Depends(get_db),
                u: User = Depends(require_analyst)):
    p = db.get(BCPPlan, pid)
    if not p or p.organization_id != _org(u):
        raise HTTPException(404)
    data = body.model_dump(exclude_none=True)
    # B2 — IDOR prevention
    if "document_id" in data and data["document_id"]:
        from app.models import AiDocument
        doc = db.get(AiDocument, data["document_id"])
        if not doc or doc.organization_id != _org(u):
            raise HTTPException(422, "Documento no encontrado en esta organización")
    for k, v in data.items():
        if k == "review_date":
            v = _parse_dt(v, "review_date")
        setattr(p, k, v)
    db.commit()
    return _plan_d(p)


@router.delete("/plans/{pid}", status_code=204)
def delete_plan(pid: int, db: Session = Depends(get_db), u: User = Depends(require_admin)):
    p = db.get(BCPPlan, pid)
    if not p or p.organization_id != _org(u):
        raise HTTPException(404)
    db.delete(p)
    db.commit()


@router.post("/plans/{pid}/approve")
def approve_plan(pid: int, db: Session = Depends(get_db), u: User = Depends(require_admin)):
    p = db.get(BCPPlan, pid)
    if not p or p.organization_id != _org(u):
        raise HTTPException(404)
    if p.status not in ("draft", "under_review"):
        raise HTTPException(422, "Solo planes en draft o under_review pueden aprobarse")
    p.status = "approved"
    p.approved_by_id = u.id
    p.approved_at = datetime.now(timezone.utc)
    db.commit()
    log_action(db, u.id, "approve", "bcp_plan", str(p.id), {"code": p.code})
    return _plan_d(p)


# ── Tests ─────────────────────────────────────────────────────────────────────

@router.get("/tests")
def list_tests(db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    return [_test_d(t) for t in db.query(BCPTest).filter_by(
        organization_id=_org(u)).order_by(BCPTest.scheduled_at.desc()).all()]


@router.post("/tests", status_code=201)
def create_test(body: TestIn, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    if body.test_type not in VALID_TEST_TYPES:
        raise HTTPException(422, "test_type inválido")
    scheduled = _parse_dt(body.scheduled_at, "scheduled_at")
    org = _org(u)
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
    db.commit()
    db.refresh(t)
    log_action(db, u.id, "create", "bcp_test", str(t.id), {"code": t.code})
    return _test_d(t)


@router.patch("/tests/{tid}")
def update_test(tid: int, body: TestUpdate, db: Session = Depends(get_db),
                u: User = Depends(require_analyst)):
    t = db.get(BCPTest, tid)
    if not t or t.organization_id != _org(u):
        raise HTTPException(404)
    if body.conducted_at:
        t.conducted_at = _parse_dt(body.conducted_at, "conducted_at")
    if body.result:
        if body.result not in VALID_TEST_RESULTS:
            raise HTTPException(422, "result inválido")
        t.result = body.result
        log_action(db, u.id, "update", "bcp_test", str(t.id),
                   {"result": body.result, "code": t.code})
        for pid in (t.process_ids or []):
            proc = db.get(BusinessProcess, pid)
            if proc and proc.organization_id == _org(u):
                proc.last_tested_at = t.conducted_at or datetime.now(timezone.utc)
                proc.test_result = body.result
        for plan in db.query(BCPPlan).filter_by(organization_id=_org(u)).all():
            if any(pid in (plan.process_ids or []) for pid in (t.process_ids or [])):
                plan.last_exercised_at = t.conducted_at or datetime.now(timezone.utc)
    for f in ("findings", "lessons_learned", "improvement_actions", "evidence_doc_ids"):
        v = getattr(body, f, None)
        if v is not None:
            setattr(t, f, v)
    db.commit()
    return _test_d(t)


# ── Supplier links ────────────────────────────────────────────────────────────

@router.get("/supplier-links")
def list_sl(db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    return [_sl_d(s, db) for s in db.query(BCPSupplierLink).filter_by(
        organization_id=_org(u)).all()]


@router.post("/supplier-links", status_code=201)
def create_sl(body: SupLinkIn, db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    org = _org(u)
    sup = db.get(Supplier, body.supplier_id)
    if not sup or sup.organization_id != org:
        raise HTTPException(422, "Proveedor no encontrado en esta organización")
    existing = db.query(BCPSupplierLink).filter_by(
        organization_id=org, supplier_id=body.supplier_id).first()
    if existing:
        raise HTTPException(409, "Ya existe vínculo BCM para este proveedor")
    data = body.model_dump()
    if data.get("last_review_date"):
        data["last_review_date"] = _parse_dt(data["last_review_date"], "last_review_date")
    sl = BCPSupplierLink(organization_id=org, **data)
    db.add(sl)
    db.commit()
    db.refresh(sl)
    log_action(db, u.id, "create", "bcp_supplier_link", str(sl.id),
               {"supplier_id": sl.supplier_id})
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
            u: User = Depends(require_analyst)):
    q = db.query(BCPExerciseProgramme).filter_by(organization_id=_org(u))
    if year:
        q = q.filter_by(year=year)
    return [{"id": p.id, "year": p.year, "status": p.status,
             "overall_objective": p.overall_objective, "exercises": p.exercises,
             "lessons_learned": p.lessons_learned, "approved_by_id": p.approved_by_id,
             "approved_at": p.approved_at.isoformat() if p.approved_at else None}
            for p in q.order_by(BCPExerciseProgramme.year.desc()).all()]


@router.post("/exercise-programme", status_code=201)
def create_ep(body: EPIn, db: Session = Depends(get_db), u: User = Depends(require_admin)):
    org = _org(u)
    if db.query(BCPExerciseProgramme).filter_by(organization_id=org, year=body.year).first():
        raise HTTPException(409, f"Ya existe programa para {body.year}")
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
def update_ep(eid: int, body: EPUpdate, db: Session = Depends(get_db),
              u: User = Depends(require_analyst)):
    ep = db.get(BCPExerciseProgramme, eid)
    if not ep or ep.organization_id != _org(u):
        raise HTTPException(404)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(ep, k, v)
    db.commit()
    return {"id": ep.id, "year": ep.year, "status": ep.status,
            "exercises": ep.exercises, "lessons_learned": ep.lessons_learned}


# ── Excel import ──────────────────────────────────────────────────────────────

@router.post("/import/preview")
async def import_preview(file: UploadFile = File(...),
                         db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(422, "Solo se aceptan .xlsx / .xls")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "Máx 10 MB")
    from app.services.bcp_excel_service import parse_excel_preview
    try:
        return parse_excel_preview(content)
    except Exception as exc:
        raise HTTPException(422, f"Error leyendo Excel: {exc}")


@router.post("/import/confirm")
async def import_confirm(file: UploadFile = File(...),
                         db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(422, "Solo se aceptan .xlsx / .xls")
    content = await file.read()
    from app.services.bcp_excel_service import parse_excel_preview, confirm_excel_import
    try:
        preview = parse_excel_preview(content)
        if preview["errors"]:
            raise HTTPException(422, f"Errores en Excel: {preview['errors']}")
        created = confirm_excel_import(db, preview, _org(u))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Error importando: {exc}")
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
