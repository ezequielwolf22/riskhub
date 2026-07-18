"""Plan Director — programas, iniciativas, OKRs, controles objetivo y riesgos
afectados (v6.3.0).

Principio: este router NUNCA escribe residual_level ni maturity reales. Los
riesgos afectados por una iniciativa se derivan automaticamente de sus
controles objetivo (ver services/initiative_projection_service.py); el link
manual solo cubre casos que el sistema no pueda inferir por si solo.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func as _func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import (
    Asset, InitiativeControlTarget, InitiativeLogEntry, InitiativeObjective,
    InitiativeRiskLink, Risk, RiskContext, StrategicInitiative, StrategicProgram,
    Threat, TreatmentTask, User, UserRole,
)
from app.schemas import (
    ControlTargetIn, ControlTargetOut, DraftConfirmIn, DraftDiscardIn,
    DraftForRiskIn, ImportConfirmIn, InitiativeDetailOut, InitiativeIn,
    InitiativeOut, InitiativeUpdate, LogEntryIn, LogEntryOut, ObjectiveIn,
    ObjectiveOut, ObjectiveUpdate, ProgramIn, ProgramOut, ProgramUpdate,
    RiskLinkIn, RiskLinkOut, TaskOut,
)
from app.security import (
    check_org_access, filter_by_org, get_current_user, require_analyst, require_role,
)
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/initiatives", tags=["initiatives"])


# ---------- Helpers ----------

def _next_code(db: Session, model, prefix: str) -> str:
    max_id = db.query(_func.max(model.id)).scalar() or 0
    return f"{prefix}-{max_id + 1:04d}"


def refresh_initiative_progress(db: Session, initiative: StrategicInitiative) -> None:
    """Progreso derivado: media de OKRs si existen; si no, tareas DONE/total.

    Sin OKRs ni tareas, el progreso se mantiene (editable solo indirectamente
    via OKRs/tareas — nunca directo por PATCH de la iniciativa)."""
    objectives = [o for o in initiative.objectives if o.status != "cancelled"]
    if objectives:
        initiative.progress = round(sum(o.progress or 0 for o in objectives) / len(objectives))
        return
    tasks = db.query(TreatmentTask).filter(
        TreatmentTask.initiative_id == initiative.id,
    ).all()
    if not tasks:
        return
    done = sum(1 for t in tasks if str(getattr(t.status, "value", t.status)).lower() == "done")
    initiative.progress = round(done / len(tasks) * 100)


def _program_out(db: Session, p: StrategicProgram) -> dict:
    initiatives = db.query(StrategicInitiative).filter(
        StrategicInitiative.program_id == p.id
    ).all()
    statuses = [i.status for i in initiatives]
    if not statuses:
        derived = "draft"
    elif any(s in ("in_progress",) for s in statuses):
        derived = "in_progress"
    elif any(i.health == "at_risk" or i.health == "blocked" for i in initiatives if i.status not in ("completed", "cancelled")):
        derived = "at_risk"
    elif all(s in ("completed", "cancelled") for s in statuses):
        derived = "completed"
    elif any(s == "approved" for s in statuses):
        derived = "approved"
    else:
        derived = "draft"
    return {
        "id": p.id, "code": p.code, "name": p.name, "description": p.description,
        "area": p.area, "responsible_id": p.responsible_id,
        "responsible_name": p.responsible.full_name if p.responsible else None,
        "budget": p.budget, "budget_approved": p.budget_approved,
        "initiatives_count": len(initiatives), "derived_status": derived,
        "created_at": p.created_at, "updated_at": p.updated_at,
    }


def _initiative_out(db: Session, ini: StrategicInitiative) -> dict:
    risks_count = len(ini.risk_links)
    objectives_count = len(ini.objectives)
    tasks = db.query(TreatmentTask).filter(TreatmentTask.initiative_id == ini.id).all()
    tasks_done = sum(1 for t in tasks if str(getattr(t.status, "value", t.status)).lower() == "done")
    projected_points = sum(
        (link.baseline_residual_level - link.projected_residual_level)
        for link in ini.risk_links
        if link.baseline_residual_level is not None and link.projected_residual_level is not None
    )
    return {
        "id": ini.id, "code": ini.code, "title": ini.title, "description": ini.description,
        "program_id": ini.program_id, "program_name": ini.program.name if ini.program else None,
        "status": ini.status, "health": ini.health, "health_reasons": ini.health_reasons,
        "priority": ini.priority, "nist_function": ini.nist_function,
        "owner_id": ini.owner_id, "owner_name": ini.owner.full_name if ini.owner else None,
        "scope": ini.scope, "business_units": ini.business_units,
        "start_date": ini.start_date, "target_date": ini.target_date,
        "completed_at": ini.completed_at, "progress": ini.progress,
        "budget": ini.budget, "budget_approved": ini.budget_approved,
        "expected_risk_reduction": ini.expected_risk_reduction,
        "source": ini.source, "ai_generated": ini.ai_generated, "ai_rationale": ini.ai_rationale,
        "verification": ini.verification,
        "risks_count": risks_count, "objectives_count": objectives_count,
        "tasks_total": len(tasks), "tasks_done": tasks_done,
        "projected_reduction_points": max(0, projected_points),
        "created_at": ini.created_at, "updated_at": ini.updated_at,
    }


def _control_target_out(ct: InitiativeControlTarget) -> dict:
    ctrl = ct.implementation.control if ct.implementation else None
    return {
        "id": ct.id, "initiative_id": ct.initiative_id,
        "implementation_id": ct.implementation_id,
        "control_code": ctrl.code if ctrl else None,
        "control_name": ctrl.name if ctrl else None,
        "baseline_maturity": ct.baseline_maturity, "target_maturity": ct.target_maturity,
        "achieved_maturity": ct.achieved_maturity,
        "current_maturity": ct.implementation.maturity if ct.implementation else None,
        "created_at": ct.created_at,
    }


def _risk_link_out(link: InitiativeRiskLink) -> dict:
    risk = link.risk
    return {
        "id": link.id, "initiative_id": link.initiative_id, "risk_id": link.risk_id,
        "risk_code": risk.code if risk else None,
        "asset_name": risk.asset.name if risk and risk.asset else None,
        "threat_name": risk.threat.name if risk and risk.threat else None,
        "origin": link.origin,
        "baseline_residual_level": link.baseline_residual_level,
        "projected_residual_level": link.projected_residual_level,
        "current_residual_level": risk.residual_level if risk else None,
        "achieved_residual_level": link.achieved_residual_level,
        "rationale": link.rationale, "ai_confidence": link.ai_confidence,
        "created_at": link.created_at,
    }


def _log_entry_out(entry: InitiativeLogEntry) -> dict:
    return {
        "id": entry.id, "initiative_id": entry.initiative_id,
        "objective_id": entry.objective_id, "entry_type": entry.entry_type,
        "text": entry.text, "author_id": entry.author_id,
        "author_name": entry.author.full_name if entry.author else None,
        "created_at": entry.created_at,
    }


def _get_initiative_or_404(db: Session, initiative_id: int, current_user: User, lang: str) -> StrategicInitiative:
    ini = db.query(StrategicInitiative).options(
        joinedload(StrategicInitiative.program),
        joinedload(StrategicInitiative.owner),
    ).filter(StrategicInitiative.id == initiative_id).first()
    if not ini or not check_org_access(ini.organization_id, current_user):
        raise HTTPException(404, _t("initiatives.not_found", lang))
    return ini


def _validate_program_org(db: Session, program_id, current_user: User, lang: str) -> None:
    """Un program_id de otra organizacion expondria su nombre via program_name."""
    if program_id is None:
        return
    p = db.get(StrategicProgram, program_id)
    if not p or not check_org_access(p.organization_id, current_user):
        raise HTTPException(404, _t("initiatives.program_not_found", lang))


def _validate_owner_org(db: Session, owner_id, current_user: User, lang: str) -> None:
    """Un owner_id de otra organizacion expondria su full_name via owner_name."""
    if owner_id is None:
        return
    u = db.get(User, owner_id)
    if not u or not check_org_access(u.organization_id, current_user):
        raise HTTPException(404, _t("initiatives.owner_not_found", lang))


# ---------- Programas ----------

@router.get("/programs", response_model=list[ProgramOut])
def list_programs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    programs = filter_by_org(db.query(StrategicProgram), StrategicProgram, current_user) \
        .order_by(StrategicProgram.name.asc()).all()
    return [_program_out(db, p) for p in programs]


@router.post("/programs", response_model=ProgramOut)
def create_program(body: ProgramIn, db: Session = Depends(get_db),
                   current_user: User = Depends(require_analyst)):
    org_id = current_user.organization_id
    p = StrategicProgram(
        code=_next_code(db, StrategicProgram, "PRG"), organization_id=org_id,
        name=body.name, description=body.description, area=body.area,
        responsible_id=body.responsible_id, budget=body.budget,
        budget_approved=body.budget_approved,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    log_action(db, current_user.id, "create", "strategic_program", str(p.id), {"code": p.code})
    return _program_out(db, p)


@router.patch("/programs/{program_id}", response_model=ProgramOut)
def update_program(program_id: int, body: ProgramUpdate, request: Request,
                   db: Session = Depends(get_db), current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    p = db.query(StrategicProgram).filter(StrategicProgram.id == program_id).first()
    if not p or not check_org_access(p.organization_id, current_user):
        raise HTTPException(404, _t("initiatives.program_not_found", lang))
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)
    log_action(db, current_user.id, "update", "strategic_program", str(p.id))
    return _program_out(db, p)


@router.delete("/programs/{program_id}", status_code=204)
def delete_program(program_id: int, request: Request, db: Session = Depends(get_db),
                   current_user: User = Depends(require_role(UserRole.ADMIN))):
    lang = get_lang(request)
    p = db.query(StrategicProgram).filter(StrategicProgram.id == program_id).first()
    if not p or not check_org_access(p.organization_id, current_user):
        raise HTTPException(404, _t("initiatives.program_not_found", lang))
    has_initiatives = db.query(StrategicInitiative).filter(
        StrategicInitiative.program_id == program_id).first()
    if has_initiatives:
        raise HTTPException(409, _t("initiatives.program_has_initiatives", lang))
    log_action(db, current_user.id, "delete", "strategic_program", str(program_id), {"code": p.code})
    db.delete(p)
    db.commit()


# ---------- Burndown y Stats (declarar ANTES de /{id}) ----------

@router.get("/burndown")
def initiatives_burndown(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.services.initiative_projection_service import compute_burndown
    org_id = getattr(current_user, "_active_org_id", None) or current_user.organization_id
    return compute_burndown(db, org_id)


# ---------- Stats (declarar ANTES de /{id}) ----------

@router.get("/stats")
def initiatives_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    programs = filter_by_org(db.query(StrategicProgram), StrategicProgram, current_user).all()
    initiatives = filter_by_org(db.query(StrategicInitiative), StrategicInitiative, current_user).all()

    by_status: dict[str, int] = {}
    by_health = {"ok": 0, "at_risk": 0, "blocked": 0}
    for i in initiatives:
        by_status[i.status] = by_status.get(i.status, 0) + 1
        if i.health in by_health:
            by_health[i.health] += 1

    avg_progress = round(sum(i.progress or 0 for i in initiatives) / len(initiatives)) if initiatives else 0
    budget_requested = sum(i.budget or 0 for i in initiatives)
    budget_approved = sum(i.budget_approved or 0 for i in initiatives)

    active_ids = [i.id for i in initiatives if i.status in ("approved", "in_progress")]
    active_links = []
    if active_ids:
        active_links = db.query(InitiativeRiskLink).filter(
            InitiativeRiskLink.initiative_id.in_(active_ids)
        ).all()
    risks_covered = len({link.risk_id for link in active_links})

    ctx = db.query(RiskContext).filter(
        RiskContext.organization_id == current_user.organization_id
    ).first()
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3

    from app.models import RiskStatus
    covered_risk_ids = {link.risk_id for link in active_links}
    all_risks = filter_by_org(db.query(Risk), Risk, current_user).options(
        joinedload(Risk.asset), joinedload(Risk.threat)
    ).filter(Risk.status != RiskStatus.CLOSED).all()
    high_uncovered = sorted(
        [r for r in all_risks
         if (r.residual_level or 0) > appetite and r.id not in covered_risk_ids],
        key=lambda r: -(r.residual_level or 0),
    )[:20]
    high_risks_uncovered = [
        {"id": r.id, "code": r.code, "residual_level": r.residual_level,
         "asset_name": r.asset.name if r.asset else None,
         "threat_name": r.threat.name if r.threat else None}
        for r in high_uncovered
    ]

    # Reduccion proyectada/conseguida por riesgo (evita doble conteo si dos
    # iniciativas activas comparten un riesgo: se usa la mejor proyeccion)
    best_by_risk: dict[int, dict] = {}
    for link in active_links:
        if link.baseline_residual_level is None or link.projected_residual_level is None:
            continue
        cur = best_by_risk.get(link.risk_id)
        if cur is None or link.projected_residual_level < cur["projected"]:
            best_by_risk[link.risk_id] = {
                "baseline": link.baseline_residual_level,
                "projected": link.projected_residual_level,
                "risk_id": link.risk_id,
            }
    projected_points = sum(v["baseline"] - v["projected"] for v in best_by_risk.values())
    risk_by_id = {r.id: r for r in all_risks}
    achieved_points = 0
    for v in best_by_risk.values():
        current_residual = risk_by_id.get(v["risk_id"])
        current_residual = current_residual.residual_level if current_residual else v["baseline"]
        achieved_points += max(0, v["baseline"] - (current_residual if current_residual is not None else v["baseline"]))

    return {
        "programs": len(programs),
        "initiatives_total": len(initiatives),
        "by_status": by_status,
        "by_health": by_health,
        "avg_progress": avg_progress,
        "budget": {"requested": budget_requested, "approved": budget_approved},
        "risks_covered": risks_covered,
        "high_risks_uncovered": high_risks_uncovered,
        "reduction": {
            "projected_points": max(0, projected_points),
            "achieved_points": max(0, achieved_points),
        },
    }


# ---------- IA: import de plan y borradores (declarar ANTES de /{id}) ----------

_IMPORT_MAX_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/import")
async def import_plan_document(request: Request, db: Session = Depends(get_db),
                               current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    from app.routers.documents import _infer_mime, _validate_magic, ALLOWED_MIME
    from app.services.document_service import extract_text
    from app.services.initiative_ai_service import parse_plan_document

    form = await request.form()
    file = form.get("file")
    if not file or not hasattr(file, "read"):
        raise HTTPException(400, _t("initiatives.import_file_required", lang))
    data = await file.read()
    if len(data) > _IMPORT_MAX_SIZE:
        raise HTTPException(413, _t("initiatives.import_too_large", lang))
    mime = _infer_mime(file.filename or "", file.content_type or "")
    if mime not in ALLOWED_MIME or not _validate_magic(mime, data):
        raise HTTPException(415, _t("initiatives.import_invalid_type", lang))

    text = extract_text(data, mime)
    if len(text.strip()) < 100:
        raise HTTPException(422, _t("initiatives.import_no_text", lang))

    org_id = current_user.organization_id
    try:
        preview = parse_plan_document(db, org_id, text, lang)
    except ValueError as e:
        raise HTTPException(422, str(e))
    log_action(db, current_user.id, "ai_import_preview", "strategic_initiative", None,
              {"programs": len(preview["programs"])})
    return preview


@router.post("/import/confirm")
def confirm_plan_import(body: ImportConfirmIn, db: Session = Depends(get_db),
                        current_user: User = Depends(require_analyst)):
    from app.services.initiative_projection_service import auto_link_risks, project_initiative
    org_id = current_user.organization_id

    created_programs = 0
    created_initiatives = 0
    created_objectives = 0
    total_projected_points = 0

    for prog_in in body.programs:
        program = db.query(StrategicProgram).filter(
            StrategicProgram.organization_id == org_id, StrategicProgram.name == prog_in.name,
        ).first()
        if not program:
            program = StrategicProgram(
                code=_next_code(db, StrategicProgram, "PRG"), organization_id=org_id,
                name=prog_in.name, area=prog_in.area,
            )
            db.add(program)
            db.flush()
            created_programs += 1

        for ini_in in prog_in.initiatives:
            initiative = StrategicInitiative(
                code=_next_code(db, StrategicInitiative, "INI"), organization_id=org_id,
                program_id=program.id, title=ini_in.title, description=ini_in.description,
                priority=ini_in.priority, nist_function=ini_in.nist_function,
                start_date=ini_in.start_date, target_date=ini_in.target_date,
                budget=ini_in.budget, expected_risk_reduction=ini_in.expected_risk_reduction,
                source="import", ai_generated=True,
                ai_rationale=_t("initiatives.ai_import_rationale", "es"),
                created_by_id=current_user.id,
            )
            db.add(initiative)
            db.flush()
            created_initiatives += 1

            seen_impl_ids: set[int] = set()
            for ct in ini_in.control_targets:
                if ct.implementation_id in seen_impl_ids:
                    continue  # la IA puede repetir un control: dedupe (uq_initiative_impl)
                from app.models import ControlImplementation
                impl = db.get(ControlImplementation, ct.implementation_id)
                if not impl or impl.organization_id != org_id:
                    continue
                seen_impl_ids.add(ct.implementation_id)
                db.add(InitiativeControlTarget(
                    organization_id=org_id, initiative_id=initiative.id,
                    implementation_id=ct.implementation_id,
                    baseline_maturity=impl.maturity, target_maturity=ct.target_maturity,
                ))
            for okr in ini_in.objectives:
                db.add(InitiativeObjective(
                    organization_id=org_id, initiative_id=initiative.id,
                    code=_next_code(db, InitiativeObjective, "OKR"),
                    definition=okr.definition, target_date=okr.target_date,
                ))
                created_objectives += 1
            db.flush()

            auto_link_risks(db, initiative)
            result = project_initiative(db, initiative)
            total_projected_points += result["projected_reduction_points"]

    db.commit()
    log_action(db, current_user.id, "ai_import_confirm", "strategic_initiative", None,
              {"programs": created_programs, "initiatives": created_initiatives})
    return {
        "created": {"programs": created_programs, "initiatives": created_initiatives,
                    "objectives": created_objectives},
        "total_projected_points": total_projected_points,
    }


@router.post("/draft-for-risk")
def draft_initiative_for_risk(body: DraftForRiskIn, request: Request, db: Session = Depends(get_db),
                              current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    from app.services.initiative_ai_service import draft_initiative_for_risks
    try:
        draft = draft_initiative_for_risks(db, current_user.organization_id, body.risk_ids, lang)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return draft


@router.post("/draft-for-risk/confirm", response_model=InitiativeOut)
def confirm_initiative_draft(body: DraftConfirmIn, db: Session = Depends(get_db),
                             current_user: User = Depends(require_analyst)):
    """Crea la iniciativa a partir de un borrador IA aceptado (source=ai_draft)
    y registra la senal de aprendizaje. Los riesgos que motivaron el borrador
    se vinculan explicitamente; el resto los deriva auto_link_risks."""
    from app.models import ControlImplementation
    from app.services.ai_learning_service import record_signal
    from app.services.initiative_projection_service import auto_link_risks, project_initiative

    org_id = current_user.organization_id
    ini = StrategicInitiative(
        code=_next_code(db, StrategicInitiative, "INI"), organization_id=org_id,
        title=body.title, description=body.description, priority=body.priority,
        expected_risk_reduction=body.expected_risk_reduction,
        source="ai_draft", ai_generated=True, ai_rationale=body.rationale,
        created_by_id=current_user.id,
    )
    db.add(ini)
    db.flush()

    seen_impl_ids: set[int] = set()
    for ct in body.control_targets:
        if ct.implementation_id in seen_impl_ids:
            continue
        impl = db.get(ControlImplementation, ct.implementation_id)
        if not impl or impl.organization_id != org_id:
            continue
        seen_impl_ids.add(ct.implementation_id)
        db.add(InitiativeControlTarget(
            organization_id=org_id, initiative_id=ini.id,
            implementation_id=ct.implementation_id,
            baseline_maturity=impl.maturity, target_maturity=ct.target_maturity,
        ))
    db.flush()

    # Vinculos explicitos para los riesgos que motivaron el borrador
    for rid in body.risk_ids:
        risk = db.get(Risk, rid)
        if not risk or risk.organization_id != org_id:
            continue
        db.add(InitiativeRiskLink(
            organization_id=org_id, initiative_id=ini.id, risk_id=risk.id,
            origin="ai_draft", baseline_residual_level=risk.residual_level,
        ))
    db.flush()

    auto_link_risks(db, ini)
    project_initiative(db, ini)

    record_signal(db, org_id, "initiative_draft_accepted",
                  {"title": body.title[:120], "risk_ids": body.risk_ids[:20],
                   "control_targets": len(body.control_targets)},
                  entity_ref=ini.code, user_id=current_user.id)
    db.commit()
    db.refresh(ini)
    log_action(db, current_user.id, "create", "strategic_initiative", str(ini.id),
              {"code": ini.code, "source": "ai_draft"})
    return _initiative_out(db, ini)


@router.post("/draft-for-risk/discard", status_code=204)
def discard_initiative_draft(body: DraftDiscardIn, db: Session = Depends(get_db),
                             current_user: User = Depends(require_analyst)):
    """Registra el rechazo de un borrador IA (senal de aprendizaje). No persiste nada mas."""
    from app.services.ai_learning_service import record_signal
    record_signal(db, current_user.organization_id, "initiative_draft_rejected",
                  {"title": (body.title or "")[:120], "risk_ids": body.risk_ids[:20]},
                  user_id=current_user.id, commit=True)


# ---------- Iniciativas ----------

@router.get("/", response_model=list[InitiativeOut])
def list_initiatives(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
    health: Optional[str] = None,
    program_id: Optional[int] = None,
    priority: Optional[str] = None,
    nist_function: Optional[str] = None,
    q: Optional[str] = None,
):
    query = filter_by_org(db.query(StrategicInitiative), StrategicInitiative, current_user).options(
        joinedload(StrategicInitiative.program), joinedload(StrategicInitiative.owner),
        joinedload(StrategicInitiative.objectives), joinedload(StrategicInitiative.risk_links),
    )
    if status:
        query = query.filter(StrategicInitiative.status == status)
    if health:
        query = query.filter(StrategicInitiative.health == health)
    if program_id:
        query = query.filter(StrategicInitiative.program_id == program_id)
    if priority:
        query = query.filter(StrategicInitiative.priority == priority)
    if nist_function:
        query = query.filter(StrategicInitiative.nist_function == nist_function)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (StrategicInitiative.title.ilike(like)) | (StrategicInitiative.description.ilike(like))
        )
    initiatives = query.all()
    health_order = {"at_risk": 0, "blocked": 0, "ok": 1}
    initiatives.sort(key=lambda i: (
        health_order.get(i.health, 1),
        i.target_date or datetime.max.replace(tzinfo=None),
    ))
    return [_initiative_out(db, i) for i in initiatives]


@router.post("/", response_model=InitiativeOut)
def create_initiative(body: InitiativeIn, request: Request, db: Session = Depends(get_db),
                      current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    org_id = current_user.organization_id
    _validate_program_org(db, body.program_id, current_user, lang)
    _validate_owner_org(db, body.owner_id, current_user, lang)
    ini = StrategicInitiative(
        code=_next_code(db, StrategicInitiative, "INI"), organization_id=org_id,
        title=body.title, description=body.description, program_id=body.program_id,
        status=body.status, priority=body.priority, nist_function=body.nist_function,
        owner_id=body.owner_id, scope=body.scope, business_units=body.business_units,
        start_date=body.start_date, target_date=body.target_date, budget=body.budget,
        budget_approved=body.budget_approved, expected_risk_reduction=body.expected_risk_reduction,
        source="manual", created_by_id=current_user.id,
    )
    if ini.status == "completed":
        ini.completed_at = datetime.now(timezone.utc)
        ini.progress = 100
    db.add(ini)
    db.commit()
    db.refresh(ini)
    log_action(db, current_user.id, "create", "strategic_initiative", str(ini.id), {"code": ini.code})
    return _initiative_out(db, ini)


@router.get("/{initiative_id}", response_model=InitiativeDetailOut)
def get_initiative(initiative_id: int, request: Request, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    lang = get_lang(request)
    ini = _get_initiative_or_404(db, initiative_id, current_user, lang)
    tasks = db.query(TreatmentTask).filter(
        TreatmentTask.initiative_id == ini.id,
        TreatmentTask.organization_id == ini.organization_id,
    ).order_by(TreatmentTask.created_at.desc()).all()
    log_entries = db.query(InitiativeLogEntry).filter(
        InitiativeLogEntry.initiative_id == ini.id
    ).order_by(InitiativeLogEntry.created_at.desc()).limit(50).all()
    out = _initiative_out(db, ini)
    out["objectives"] = [
        {
            "id": o.id, "code": o.code, "initiative_id": o.initiative_id,
            "definition": o.definition, "status": o.status, "confidence": o.confidence,
            "owner_id": o.owner_id, "collaborator": o.collaborator,
            "target_date": o.target_date, "progress": o.progress,
            "created_at": o.created_at, "updated_at": o.updated_at,
        }
        for o in ini.objectives
    ]
    out["control_targets"] = [_control_target_out(ct) for ct in ini.control_targets]
    out["risk_links"] = [_risk_link_out(link) for link in ini.risk_links]
    out["log_entries"] = [_log_entry_out(e) for e in log_entries]
    out["tasks"] = tasks
    return out


@router.patch("/{initiative_id}", response_model=InitiativeOut)
def update_initiative(initiative_id: int, body: InitiativeUpdate, request: Request,
                      db: Session = Depends(get_db), current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    ini = _get_initiative_or_404(db, initiative_id, current_user, lang)
    data = body.model_dump(exclude_unset=True)
    if "program_id" in data:
        _validate_program_org(db, data["program_id"], current_user, lang)
    if "owner_id" in data:
        _validate_owner_org(db, data["owner_id"], current_user, lang)
    new_status = data.get("status")
    old_status = ini.status
    for field, value in data.items():
        setattr(ini, field, value)
    if new_status == "completed" and ini.completed_at is None:
        ini.completed_at = datetime.now(timezone.utc)
        ini.progress = 100
        try:
            from app.services.initiative_projection_service import verify_initiative
            verify_initiative(db, ini)
        except Exception:
            pass
    if new_status and new_status != old_status:
        try:
            from app.services.initiative_projection_service import log_system_event
            log_system_event(db, ini.id, f"Estado cambiado de '{old_status}' a '{new_status}'.")
        except Exception:
            pass
    db.commit()
    db.refresh(ini)
    log_action(db, current_user.id, "update", "strategic_initiative", str(ini.id))
    return _initiative_out(db, ini)


@router.delete("/{initiative_id}", status_code=204)
def delete_initiative(initiative_id: int, request: Request, db: Session = Depends(get_db),
                      current_user: User = Depends(require_role(UserRole.ADMIN))):
    lang = get_lang(request)
    ini = _get_initiative_or_404(db, initiative_id, current_user, lang)
    db.query(TreatmentTask).filter(TreatmentTask.initiative_id == ini.id).update(
        {"initiative_id": None}, synchronize_session=False)
    log_action(db, current_user.id, "delete", "strategic_initiative", str(initiative_id), {"code": ini.code})
    db.delete(ini)
    db.commit()


# ---------- Objetivos (OKR) ----------

@router.post("/{initiative_id}/objectives", response_model=ObjectiveOut)
def create_objective(initiative_id: int, body: ObjectiveIn, request: Request,
                     db: Session = Depends(get_db), current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    ini = _get_initiative_or_404(db, initiative_id, current_user, lang)
    _validate_owner_org(db, body.owner_id, current_user, lang)
    obj = InitiativeObjective(
        organization_id=ini.organization_id, initiative_id=ini.id,
        code=_next_code(db, InitiativeObjective, "OKR"),
        definition=body.definition, status=body.status, confidence=body.confidence,
        owner_id=body.owner_id, collaborator=body.collaborator,
        target_date=body.target_date, progress=body.progress,
    )
    db.add(obj)
    db.flush()
    refresh_initiative_progress(db, ini)
    db.commit()
    db.refresh(obj)
    log_action(db, current_user.id, "create", "initiative_objective", str(obj.id))
    return obj


@router.patch("/{initiative_id}/objectives/{objective_id}", response_model=ObjectiveOut)
def update_objective(initiative_id: int, objective_id: int, body: ObjectiveUpdate, request: Request,
                     db: Session = Depends(get_db), current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    ini = _get_initiative_or_404(db, initiative_id, current_user, lang)
    obj = db.query(InitiativeObjective).filter(
        InitiativeObjective.id == objective_id, InitiativeObjective.initiative_id == ini.id
    ).first()
    if not obj:
        raise HTTPException(404, _t("initiatives.objective_not_found", lang))
    data = body.model_dump(exclude_unset=True)
    if "owner_id" in data:
        _validate_owner_org(db, data["owner_id"], current_user, lang)
    for field, value in data.items():
        setattr(obj, field, value)
    refresh_initiative_progress(db, ini)
    db.commit()
    db.refresh(obj)
    log_action(db, current_user.id, "update", "initiative_objective", str(obj.id))
    return obj


@router.delete("/{initiative_id}/objectives/{objective_id}", status_code=204)
def delete_objective(initiative_id: int, objective_id: int, request: Request,
                     db: Session = Depends(get_db), current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    ini = _get_initiative_or_404(db, initiative_id, current_user, lang)
    obj = db.query(InitiativeObjective).filter(
        InitiativeObjective.id == objective_id, InitiativeObjective.initiative_id == ini.id
    ).first()
    if not obj:
        raise HTTPException(404, _t("initiatives.objective_not_found", lang))
    log_action(db, current_user.id, "delete", "initiative_objective", str(objective_id))
    db.delete(obj)
    db.flush()
    refresh_initiative_progress(db, ini)
    db.commit()


# ---------- Controles objetivo ----------

@router.post("/{initiative_id}/control-targets", response_model=ControlTargetOut)
def create_control_target(initiative_id: int, body: ControlTargetIn, request: Request,
                          db: Session = Depends(get_db), current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    ini = _get_initiative_or_404(db, initiative_id, current_user, lang)
    from app.models import ControlImplementation
    impl = db.query(ControlImplementation).filter(
        ControlImplementation.id == body.implementation_id
    ).first()
    if not impl or not check_org_access(impl.organization_id, current_user):
        raise HTTPException(404, _t("initiatives.control_not_found", lang))
    existing = db.query(InitiativeControlTarget).filter(
        InitiativeControlTarget.initiative_id == ini.id,
        InitiativeControlTarget.implementation_id == body.implementation_id,
    ).first()
    if existing:
        raise HTTPException(409, _t("initiatives.control_target_duplicate", lang))
    ct = InitiativeControlTarget(
        organization_id=ini.organization_id, initiative_id=ini.id,
        implementation_id=body.implementation_id,
        baseline_maturity=impl.maturity, target_maturity=body.target_maturity,
    )
    db.add(ct)
    db.commit()
    db.refresh(ct)
    log_action(db, current_user.id, "create", "initiative_control_target", str(ct.id))
    try:
        from app.services.initiative_projection_service import auto_link_risks, project_initiative
        auto_link_risks(db, ini)
        project_initiative(db, ini)
        db.commit()
    except Exception:
        pass
    return _control_target_out(ct)


@router.delete("/{initiative_id}/control-targets/{target_id}", status_code=204)
def delete_control_target(initiative_id: int, target_id: int, request: Request,
                          db: Session = Depends(get_db), current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    ini = _get_initiative_or_404(db, initiative_id, current_user, lang)
    ct = db.query(InitiativeControlTarget).filter(
        InitiativeControlTarget.id == target_id, InitiativeControlTarget.initiative_id == ini.id
    ).first()
    if not ct:
        raise HTTPException(404, _t("initiatives.control_target_not_found", lang))
    db.delete(ct)
    db.commit()
    log_action(db, current_user.id, "delete", "initiative_control_target", str(target_id))
    try:
        from app.services.initiative_projection_service import auto_link_risks, project_initiative
        auto_link_risks(db, ini)
        project_initiative(db, ini)
        db.commit()
    except Exception:
        pass


# ---------- Riesgos vinculados ----------

@router.post("/{initiative_id}/risks", response_model=RiskLinkOut)
def link_risk(initiative_id: int, body: RiskLinkIn, request: Request,
             db: Session = Depends(get_db), current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    ini = _get_initiative_or_404(db, initiative_id, current_user, lang)
    risk = db.query(Risk).filter(Risk.id == body.risk_id).first()
    if not risk or not check_org_access(risk.organization_id, current_user):
        raise HTTPException(404, _t("initiatives.risk_not_found", lang))
    existing = db.query(InitiativeRiskLink).filter(
        InitiativeRiskLink.initiative_id == ini.id, InitiativeRiskLink.risk_id == risk.id
    ).first()
    if existing:
        raise HTTPException(409, _t("initiatives.risk_link_duplicate", lang))
    link = InitiativeRiskLink(
        organization_id=ini.organization_id, initiative_id=ini.id, risk_id=risk.id,
        origin="manual", baseline_residual_level=risk.residual_level,
        rationale=body.rationale,
    )
    db.add(link)
    db.flush()
    # Proyectar el residual del riesgo recien vinculado (spec 2.2: el vinculo
    # manual tambien dispara la proyeccion; sin esto quedaria en None hasta
    # el siguiente reproject)
    try:
        from app.services.initiative_projection_service import project_initiative
        project_initiative(db, ini)
    except Exception:
        pass
    db.commit()
    db.refresh(link)
    log_action(db, current_user.id, "create", "initiative_risk_link", str(link.id))
    return _risk_link_out(link)


@router.delete("/{initiative_id}/risks/{risk_id}", status_code=204)
def unlink_risk(initiative_id: int, risk_id: int, request: Request,
               db: Session = Depends(get_db), current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    ini = _get_initiative_or_404(db, initiative_id, current_user, lang)
    link = db.query(InitiativeRiskLink).filter(
        InitiativeRiskLink.initiative_id == ini.id, InitiativeRiskLink.risk_id == risk_id
    ).first()
    if not link:
        raise HTTPException(404, _t("initiatives.risk_link_not_found", lang))
    if link.origin == "auto":
        raise HTTPException(409, _t("initiatives.risk_link_is_auto", lang))
    db.delete(link)
    db.commit()
    log_action(db, current_user.id, "delete", "initiative_risk_link", str(risk_id))


# ---------- Bitacora ----------

@router.post("/{initiative_id}/log", response_model=LogEntryOut)
def add_log_entry(initiative_id: int, body: LogEntryIn, request: Request,
                  db: Session = Depends(get_db), current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    ini = _get_initiative_or_404(db, initiative_id, current_user, lang)
    if body.objective_id is not None:
        obj = db.query(InitiativeObjective).filter(
            InitiativeObjective.id == body.objective_id,
            InitiativeObjective.initiative_id == ini.id,
        ).first()
        if not obj:
            raise HTTPException(404, _t("initiatives.objective_not_found", lang))
    entry = InitiativeLogEntry(
        organization_id=ini.organization_id, initiative_id=ini.id,
        objective_id=body.objective_id, entry_type=body.entry_type,
        text=body.text, author_id=current_user.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _log_entry_out(entry)


@router.post("/{initiative_id}/reproject")
def reproject(initiative_id: int, request: Request, db: Session = Depends(get_db),
             current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    ini = _get_initiative_or_404(db, initiative_id, current_user, lang)
    from app.services.initiative_projection_service import auto_link_risks, project_initiative
    auto_link_risks(db, ini)
    result = project_initiative(db, ini)
    db.commit()
    return result


@router.post("/{initiative_id}/verify")
def verify(initiative_id: int, request: Request, db: Session = Depends(get_db),
          current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    ini = _get_initiative_or_404(db, initiative_id, current_user, lang)
    from app.services.initiative_projection_service import verify_initiative
    result = verify_initiative(db, ini)
    db.commit()
    return result
