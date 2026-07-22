"""Plan Director de Seguridad / Security Strategic Plan (v6.4.0).

Cubre las fases que faltaban del metodo (INCIBE / NIST CSF 2.0 / ISO 27001):

  1. Situacion actual  -> GET /{id}/current-profile
  2. Objetivo          -> PUT /{id}/targets
  3. Gap y proyectos   -> GET /{id}/gap, POST /{id}/generate-initiatives
  5. Aprobacion        -> POST /{id}/request-approval, /approvals/{id}/decide

El estado 'approved' NO se alcanza por PATCH: solo cerrando una ronda de
aprobacion (ISO 27001 cl. 6.1.3f).
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func as _func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import (
    Control, MaturityTarget, PlanApproval, StrategicInitiative, StrategicPlan,
    StrategicProgram, User, UserRole,
)
from app.schemas import (
    MaturityTargetsIn, PlanApprovalDecisionIn, PlanApprovalIn, PlanApprovalOut,
    StrategicPlanIn, StrategicPlanOut, StrategicPlanUpdate,
)
from app.security import (
    check_org_access, filter_by_org, get_current_user, require_analyst,
    require_role, resolve_org_id,
)
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/strategic-plans", tags=["strategic-plans"])


def _next_code(db: Session) -> str:
    max_id = db.query(_func.max(StrategicPlan.id)).scalar() or 0
    return f"PLN-{max_id + 1:04d}"


def _plan_out(db: Session, plan: StrategicPlan) -> dict:
    programs = db.query(StrategicProgram).filter(
        StrategicProgram.plan_id == plan.id).all()
    initiatives_count = 0
    if programs:
        initiatives_count = db.query(StrategicInitiative).filter(
            StrategicInitiative.program_id.in_([p.id for p in programs])
        ).count()
    return {
        "id": plan.id, "code": plan.code, "name": plan.name,
        "description": plan.description,
        "period_start": plan.period_start, "period_end": plan.period_end,
        "framework_code": plan.framework_code, "status": plan.status,
        "version": plan.version, "scope_statement": plan.scope_statement,
        "strategy_notes": plan.strategy_notes,
        "investment_capacity": plan.investment_capacity,
        "baseline_sealed_at": plan.baseline_sealed_at,
        "approved_at": plan.approved_at, "approved_by_id": plan.approved_by_id,
        "approved_by_name": plan.approved_by.full_name if plan.approved_by else None,
        "programs_count": len(programs), "initiatives_count": initiatives_count,
        "targets_count": len(plan.targets),
        "created_at": plan.created_at, "updated_at": plan.updated_at,
    }


def _get_plan_or_404(db: Session, plan_id: int, current_user: User, lang: str) -> StrategicPlan:
    plan = db.query(StrategicPlan).options(
        joinedload(StrategicPlan.targets), joinedload(StrategicPlan.approved_by),
    ).filter(StrategicPlan.id == plan_id).first()
    if not plan or not check_org_access(plan.organization_id, current_user):
        raise HTTPException(404, _t("strategic_plans.not_found", lang))
    return plan


# ---------- CRUD del plan ----------

@router.get("/", response_model=list[StrategicPlanOut])
def list_plans(db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
               status: Optional[str] = None):
    query = filter_by_org(db.query(StrategicPlan), StrategicPlan, current_user).options(
        joinedload(StrategicPlan.targets), joinedload(StrategicPlan.approved_by))
    if status:
        query = query.filter(StrategicPlan.status == status)
    plans = query.order_by(StrategicPlan.created_at.desc()).all()
    return [_plan_out(db, p) for p in plans]


@router.post("/", response_model=StrategicPlanOut)
def create_plan(body: StrategicPlanIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    org_id = resolve_org_id(current_user)
    plan = StrategicPlan(
        code=_next_code(db), organization_id=org_id, name=body.name,
        description=body.description, period_start=body.period_start,
        period_end=body.period_end, framework_code=body.framework_code,
        scope_statement=body.scope_statement, strategy_notes=body.strategy_notes,
        investment_capacity=body.investment_capacity,
        created_by_id=current_user.id,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    log_action(db, current_user.id, "create", "strategic_plan", str(plan.id), {"code": plan.code})
    return _plan_out(db, plan)


@router.get("/{plan_id}", response_model=StrategicPlanOut)
def get_plan(plan_id: int, request: Request, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    plan = _get_plan_or_404(db, plan_id, current_user, get_lang(request))
    return _plan_out(db, plan)


@router.patch("/{plan_id}", response_model=StrategicPlanOut)
def update_plan(plan_id: int, body: StrategicPlanUpdate, request: Request,
                db: Session = Depends(get_db), current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    plan = _get_plan_or_404(db, plan_id, current_user, lang)
    data = body.model_dump(exclude_unset=True)
    # Cambiar el alcance de un plan ya aprobado crea una version nueva: lo
    # aprobado por la direccion no puede mutar en silencio (ISO 6.1.3f).
    scope_fields = {"scope_statement", "period_start", "period_end", "framework_code"}
    if plan.status in ("approved", "active") and scope_fields & set(data):
        plan.version += 1
        plan.status = "draft"
        plan.approved_at = None
        plan.approved_by_id = None
    for field, value in data.items():
        setattr(plan, field, value)
    db.commit()
    db.refresh(plan)
    log_action(db, current_user.id, "update", "strategic_plan", str(plan.id))
    return _plan_out(db, plan)


@router.delete("/{plan_id}", status_code=204)
def delete_plan(plan_id: int, request: Request, db: Session = Depends(get_db),
                current_user: User = Depends(require_role(UserRole.ADMIN))):
    lang = get_lang(request)
    plan = _get_plan_or_404(db, plan_id, current_user, lang)
    db.query(StrategicProgram).filter(StrategicProgram.plan_id == plan.id).update(
        {"plan_id": None}, synchronize_session=False)
    log_action(db, current_user.id, "delete", "strategic_plan", str(plan_id), {"code": plan.code})
    db.delete(plan)
    db.commit()


# ---------- Fase 1: situacion actual ----------

@router.get("/{plan_id}/current-profile")
def current_profile(plan_id: int, request: Request, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """Perfil de madurez actual (INCIBE fase 1 / NIST CSF Current Profile)."""
    from app.services.strategic_profile_service import compute_current_profile

    plan = _get_plan_or_404(db, plan_id, current_user, get_lang(request))
    return compute_current_profile(db, plan.organization_id)


@router.get("/{plan_id}/progress")
def plan_progress_endpoint(plan_id: int, request: Request, db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    """Avance contra la linea base sellada y el objetivo del plan."""
    from app.services.plan_approval_service import approval_integrity
    from app.services.strategic_profile_service import plan_progress

    plan = _get_plan_or_404(db, plan_id, current_user, get_lang(request))
    out = plan_progress(db, plan)
    out["approval"] = approval_integrity(db, plan)
    return out


# ---------- Fase 2: perfil objetivo ----------

@router.get("/{plan_id}/targets")
def list_targets(plan_id: int, request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    from app.services.strategic_profile_service import resolve_targets_detailed

    plan = _get_plan_or_404(db, plan_id, current_user, get_lang(request))
    detailed = resolve_targets_detailed(db, plan)
    return {
        "declared": [
            {"id": t.id, "control_id": t.control_id, "framework_code": t.framework_code,
             "requirement_id": t.requirement_id, "target_maturity": t.target_maturity,
             "rationale": t.rationale, "mandatory_by": t.mandatory_by}
            for t in plan.targets
        ],
        # Resueltos a controles ISO 27002 concretos (un requisito de framework
        # puede expandirse a varios controles)
        "resolved": list(detailed["resolved"].values()),
        # Y los que no tienen equivalencia en el catalogo: el usuario debe
        # saberlo, no descubrirlo cuando el plan no cubra lo que creia
        "unresolved": detailed["unresolved"],
    }


@router.put("/{plan_id}/targets")
def set_targets(plan_id: int, body: MaturityTargetsIn, request: Request,
                db: Session = Depends(get_db), current_user: User = Depends(require_analyst)):
    """Fija el perfil objetivo (INCIBE fase 2 / NIST CSF Target Profile)."""
    lang = get_lang(request)
    plan = _get_plan_or_404(db, plan_id, current_user, lang)
    org_id = plan.organization_id

    if body.replace:
        db.query(MaturityTarget).filter(MaturityTarget.plan_id == plan.id).delete(
            synchronize_session=False)
        db.flush()

    existing = {
        (t.control_id, t.framework_code, t.requirement_id): t
        for t in db.query(MaturityTarget).filter(MaturityTarget.plan_id == plan.id).all()
    }
    created = updated = 0
    for item in body.targets:
        if item.control_id is not None:
            control = db.get(Control, item.control_id)
            if not control:
                raise HTTPException(404, _t("strategic_plans.control_not_found", lang))
        key = (item.control_id, item.framework_code, item.requirement_id)
        target = existing.get(key)
        if target:
            target.target_maturity = item.target_maturity
            target.rationale = item.rationale
            target.mandatory_by = item.mandatory_by
            updated += 1
        else:
            db.add(MaturityTarget(
                organization_id=org_id, plan_id=plan.id, control_id=item.control_id,
                framework_code=item.framework_code, requirement_id=item.requirement_id,
                target_maturity=item.target_maturity, rationale=item.rationale,
                mandatory_by=item.mandatory_by,
            ))
            created += 1
    db.commit()
    log_action(db, current_user.id, "update", "strategic_plan_targets", str(plan.id),
               {"created": created, "updated": updated})
    return {"created": created, "updated": updated}


# ---------- Fase 3: gap y generacion de iniciativas ----------

@router.get("/{plan_id}/gap")
def gap(plan_id: int, request: Request, db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)):
    """Delta objetivo - actual, ordenado por obligatoriedad y tamano del hueco."""
    from app.services.strategic_profile_service import compute_gap

    plan = _get_plan_or_404(db, plan_id, current_user, get_lang(request))
    return compute_gap(db, plan)


@router.post("/{plan_id}/generate-initiatives")
def generate_initiatives(plan_id: int, request: Request, db: Session = Depends(get_db),
                         current_user: User = Depends(require_analyst)):
    """Propuesta determinista de iniciativas a partir del gap. No persiste nada:
    devuelve candidatas para que el usuario confirme (igual que el import IA)."""
    from app.services.strategic_profile_service import generate_candidate_initiatives

    plan = _get_plan_or_404(db, plan_id, current_user, get_lang(request))
    return generate_candidate_initiatives(db, plan)


@router.post("/{plan_id}/generate-initiatives/confirm")
def confirm_generated_initiatives(plan_id: int, body: dict, request: Request,
                                  db: Session = Depends(get_db),
                                  current_user: User = Depends(require_analyst)):
    """Crea las iniciativas candidatas aceptadas, con sus controles objetivo.

    Los riesgos afectados y la reduccion proyectada los deriva despues el motor
    determinista (auto_link_risks + project_initiative), igual que siempre.
    """
    from app.routers.initiatives import (
        _next_code as _ini_code, resolve_implementation,
    )
    from app.services.initiative_projection_service import auto_link_risks, project_initiative

    lang = get_lang(request)
    plan = _get_plan_or_404(db, plan_id, current_user, lang)
    org_id = plan.organization_id
    candidates = body.get("candidates") or []
    if not candidates:
        raise HTTPException(422, _t("strategic_plans.no_candidates", lang))

    program_name = body.get("program_name") or f"Plan {plan.code}"
    program = db.query(StrategicProgram).filter(
        StrategicProgram.organization_id == org_id,
        StrategicProgram.plan_id == plan.id,
        StrategicProgram.name == program_name,
    ).first()
    if not program:
        from app.routers.initiatives import _next_code as _code_for
        program = StrategicProgram(
            code=_code_for(db, StrategicProgram, "PRG"), organization_id=org_id,
            plan_id=plan.id, name=program_name,
        )
        db.add(program)
        db.flush()

    created = 0
    total_points = 0
    from app.models import InitiativeControlTarget

    for cand in candidates:
        ini = StrategicInitiative(
            code=_ini_code(db, StrategicInitiative, "INI"), organization_id=org_id,
            program_id=program.id, title=cand.get("title") or "Iniciativa",
            description=cand.get("description"),
            origin=cand.get("origin"), action_type=cand.get("action_type"),
            effort_human=cand.get("effort_human"),
            source="gap", created_by_id=current_user.id,
        )
        db.add(ini)
        db.flush()
        created += 1

        seen: set[int] = set()
        for ct in cand.get("control_targets") or []:
            target_maturity = ct.get("target_maturity")
            if target_maturity is None:
                continue

            class _T:
                implementation_id = None
                control_id = ct.get("control_id")

            try:
                impl = resolve_implementation(db, org_id, _T(), lang)
            except HTTPException:
                continue
            if impl.id in seen:
                continue
            seen.add(impl.id)
            db.add(InitiativeControlTarget(
                organization_id=org_id, initiative_id=ini.id, implementation_id=impl.id,
                baseline_maturity=impl.maturity, target_maturity=int(target_maturity),
            ))
        db.flush()
        auto_link_risks(db, ini)
        total_points += project_initiative(db, ini)["projected_reduction_points"]

    db.commit()
    log_action(db, current_user.id, "create", "strategic_plan_initiatives", str(plan.id),
               {"created": created})
    return {"created": created, "program_id": program.id,
            "total_projected_points": total_points}


# ---------- Fase 5: aprobacion formal (ISO 27001 cl. 6.1.3f) ----------

@router.get("/{plan_id}/approvals", response_model=list[PlanApprovalOut])
def list_approvals(plan_id: int, request: Request, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    plan = _get_plan_or_404(db, plan_id, current_user, get_lang(request))
    return db.query(PlanApproval).filter(
        PlanApproval.plan_id == plan.id
    ).order_by(PlanApproval.requested_at.desc()).all()


@router.post("/{plan_id}/request-approval")
def request_plan_approval(plan_id: int, body: PlanApprovalIn, request: Request,
                          db: Session = Depends(get_db),
                          current_user: User = Depends(require_analyst)):
    """Abre la ronda de aprobacion del plan por la direccion."""
    from app.services.plan_approval_service import request_approval

    lang = get_lang(request)
    plan = _get_plan_or_404(db, plan_id, current_user, lang)
    try:
        approvals = request_approval(
            db, plan, mode=body.mode, approvers=body.approvers,
            requested_by_id=current_user.id, notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.commit()
    log_action(db, current_user.id, "request_approval", "strategic_plan", str(plan.id),
               {"mode": approvals[0].mode, "approvers": len(approvals)})
    return {
        "plan_status": plan.status, "mode": approvals[0].mode,
        "approvals": [{"id": a.id, "approver_email": a.approver_email,
                       "order_index": a.order_index} for a in approvals],
    }


@router.post("/approvals/{approval_id}/decide")
def decide_approval(approval_id: int, body: PlanApprovalDecisionIn, request: Request,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(require_role(UserRole.ADMIN))):
    """Aprueba o rechaza desde dentro de la app (modo sello interno).

    Exige rol admin: aprobar el Plan Director es un acto de direccion, no una
    edicion mas. La firma externa por token va por su propia ruta publica.
    """
    from app.services.plan_approval_service import record_decision

    lang = get_lang(request)
    approval = db.get(PlanApproval, approval_id)
    if not approval or not check_org_access(approval.organization_id, current_user):
        raise HTTPException(404, _t("strategic_plans.approval_not_found", lang))
    try:
        result = record_decision(
            db, approval, decision=body.decision, user_id=current_user.id,
            notes=body.notes,
            ip_address=request.client.host if request.client else None,
        )
    except ValueError as e:
        raise HTTPException(409, str(e))
    db.commit()
    log_action(db, current_user.id, body.decision, "strategic_plan", str(approval.plan_id),
               {"approval_id": approval.id})
    return result


@router.post("/{plan_id}/activate", response_model=StrategicPlanOut)
def activate_plan(plan_id: int, request: Request, db: Session = Depends(get_db),
                  current_user: User = Depends(require_analyst)):
    """Pone en ejecucion un plan ya aprobado (INCIBE fase 6)."""
    lang = get_lang(request)
    plan = _get_plan_or_404(db, plan_id, current_user, lang)
    if plan.status != "approved":
        raise HTTPException(409, _t("strategic_plans.must_be_approved", lang))
    plan.status = "active"
    db.commit()
    db.refresh(plan)
    log_action(db, current_user.id, "activate", "strategic_plan", str(plan.id))
    return _plan_out(db, plan)


@router.post("/{plan_id}/close", response_model=StrategicPlanOut)
def close_plan(plan_id: int, request: Request, db: Session = Depends(get_db),
               current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    plan = _get_plan_or_404(db, plan_id, current_user, lang)
    plan.status = "closed"
    if not plan.period_end:
        plan.period_end = datetime.now(timezone.utc)
    db.commit()
    db.refresh(plan)
    log_action(db, current_user.id, "close", "strategic_plan", str(plan.id))
    return _plan_out(db, plan)
