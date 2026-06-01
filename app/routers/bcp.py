"""Router BCP/BIA — Business Continuity Planning (NIS2 Art. 21.2b + ISO 27001 A.5.29)."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import BusinessProcess, BCPTest, User
from app.security import get_current_user, require_admin, require_analyst
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.bcp")

router = APIRouter(prefix="/api/bcp", tags=["bcp"])

VALID_CRITICALITY = ("critical", "high", "medium", "low")
VALID_TEST_TYPES = ("tabletop", "simulation", "full_test")
VALID_TEST_RESULTS = ("passed", "partial", "failed")


def _next_bct_code(db: Session, org_id: int) -> str:
    count = db.query(BCPTest).filter_by(organization_id=org_id).count()
    return f"BCT-{count + 1:04d}"


def _proc_to_dict(p: BusinessProcess) -> dict:
    return {
        "id": p.id,
        "organization_id": p.organization_id,
        "name": p.name,
        "description": p.description,
        "criticality": p.criticality,
        "rto_hours": p.rto_hours,
        "rpo_hours": p.rpo_hours,
        "mtpd_hours": p.mtpd_hours,
        "asset_ids": p.asset_ids,
        "supplier_ids": p.supplier_ids,
        "last_tested_at": p.last_tested_at.isoformat() if p.last_tested_at else None,
        "test_result": p.test_result,
        "owner_id": p.owner_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _test_to_dict(t: BCPTest) -> dict:
    return {
        "id": t.id,
        "organization_id": t.organization_id,
        "code": t.code,
        "test_type": t.test_type,
        "process_ids": t.process_ids,
        "scheduled_at": t.scheduled_at.isoformat() if t.scheduled_at else None,
        "conducted_at": t.conducted_at.isoformat() if t.conducted_at else None,
        "result": t.result,
        "findings": t.findings,
        "nc_ids": t.nc_ids,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


class ProcessCreate(BaseModel):
    name: str
    description: Optional[str] = None
    criticality: str = "medium"
    rto_hours: Optional[int] = None
    rpo_hours: Optional[int] = None
    mtpd_hours: Optional[int] = None
    asset_ids: Optional[list] = None
    supplier_ids: Optional[list] = None
    owner_id: Optional[int] = None


class ProcessUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    criticality: Optional[str] = None
    rto_hours: Optional[int] = None
    rpo_hours: Optional[int] = None
    mtpd_hours: Optional[int] = None
    asset_ids: Optional[list] = None
    supplier_ids: Optional[list] = None
    owner_id: Optional[int] = None


class TestCreate(BaseModel):
    test_type: str
    process_ids: List[int]
    scheduled_at: str


class TestUpdate(BaseModel):
    conducted_at: Optional[str] = None
    result: Optional[str] = None
    findings: Optional[str] = None


# ── Procesos ──────────────────────────────────────────────────────────────────

@router.get("/processes")
def list_processes(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    procs = (
        db.query(BusinessProcess)
        .filter_by(organization_id=current_user.organization_id)
        .order_by(BusinessProcess.criticality)
        .all()
    )
    return [_proc_to_dict(p) for p in procs]


@router.post("/processes", status_code=201)
def create_process(
    body: ProcessCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    if body.criticality not in VALID_CRITICALITY:
        raise HTTPException(422, f"criticality invalido. Validos: {VALID_CRITICALITY}")

    p = BusinessProcess(
        organization_id=current_user.organization_id,
        name=body.name,
        description=body.description,
        criticality=body.criticality,
        rto_hours=body.rto_hours,
        rpo_hours=body.rpo_hours,
        mtpd_hours=body.mtpd_hours,
        asset_ids=body.asset_ids or [],
        supplier_ids=body.supplier_ids or [],
        owner_id=body.owner_id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    log_action(db, current_user.id, "create", "business_process", str(p.id), {"name": p.name})
    return _proc_to_dict(p)


@router.get("/processes/{proc_id}")
def get_process(
    proc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    p = db.get(BusinessProcess, proc_id)
    if not p or p.organization_id != current_user.organization_id:
        raise HTTPException(404, "Proceso no encontrado")
    return _proc_to_dict(p)


@router.patch("/processes/{proc_id}")
def update_process(
    proc_id: int,
    body: ProcessUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    p = db.get(BusinessProcess, proc_id)
    if not p or p.organization_id != current_user.organization_id:
        raise HTTPException(404, "Proceso no encontrado")

    for field in ("name", "description", "criticality", "rto_hours", "rpo_hours",
                  "mtpd_hours", "asset_ids", "supplier_ids", "owner_id"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(p, field, val)
    db.commit()
    return _proc_to_dict(p)


@router.delete("/processes/{proc_id}", status_code=204)
def delete_process(
    proc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    p = db.get(BusinessProcess, proc_id)
    if not p or p.organization_id != current_user.organization_id:
        raise HTTPException(404, "Proceso no encontrado")
    db.delete(p)
    db.commit()


# ── Tests BCP ────────────────────────────────────────────────────────────────

@router.get("/tests")
def list_tests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    tests = (
        db.query(BCPTest)
        .filter_by(organization_id=current_user.organization_id)
        .order_by(BCPTest.scheduled_at.desc())
        .all()
    )
    return [_test_to_dict(t) for t in tests]


@router.post("/tests", status_code=201)
def create_test(
    body: TestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    if body.test_type not in VALID_TEST_TYPES:
        raise HTTPException(422, f"test_type invalido")

    try:
        scheduled = datetime.fromisoformat(body.scheduled_at)
    except ValueError:
        raise HTTPException(422, "scheduled_at debe ser ISO 8601")

    org_id = current_user.organization_id
    t = BCPTest(
        organization_id=org_id,
        code=_next_bct_code(db, org_id),
        test_type=body.test_type,
        process_ids=body.process_ids,
        scheduled_at=scheduled,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    log_action(db, current_user.id, "create", "bcp_test", str(t.id), {"code": t.code})
    return _test_to_dict(t)


@router.patch("/tests/{test_id}")
def update_test(
    test_id: int,
    body: TestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    t = db.get(BCPTest, test_id)
    if not t or t.organization_id != current_user.organization_id:
        raise HTTPException(404, "Test no encontrado")

    if body.conducted_at:
        try:
            t.conducted_at = datetime.fromisoformat(body.conducted_at)
        except ValueError:
            pass
    if body.result:
        if body.result not in VALID_TEST_RESULTS:
            raise HTTPException(422, f"result invalido")
        t.result = body.result
        # Actualizar last_tested_at en los procesos afectados
        for proc_id in (t.process_ids or []):
            proc = db.get(BusinessProcess, proc_id)
            if proc and proc.organization_id == current_user.organization_id:
                proc.last_tested_at = t.conducted_at or datetime.now(timezone.utc)
                proc.test_result = body.result
    if body.findings is not None:
        t.findings = body.findings

    db.commit()
    return _test_to_dict(t)


@router.get("/dashboard")
def bcp_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Resumen BCP/BIA para la organizacion."""
    from datetime import timedelta
    org_id = current_user.organization_id
    procs = db.query(BusinessProcess).filter_by(organization_id=org_id).all()
    tests = db.query(BCPTest).filter_by(organization_id=org_id).all()
    now = datetime.now(timezone.utc)

    critical = [p for p in procs if p.criticality == "critical"]
    overdue_tests = [
        p for p in procs
        if not p.last_tested_at or
        (now - p.last_tested_at.replace(tzinfo=timezone.utc)).days > 365
    ]

    return {
        "total_processes": len(procs),
        "critical_processes": len(critical),
        "processes_overdue_test": len(overdue_tests),
        "total_tests": len(tests),
        "last_test_date": max(
            (t.conducted_at for t in tests if t.conducted_at), default=None
        ),
    }
