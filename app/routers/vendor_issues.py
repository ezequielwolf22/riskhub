"""Hallazgos / issues de proveedores con SLA por severidad (TPRM Sprint 7)."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import Supplier, VendorIssue, VendorIssueSeverity, VendorIssueStatus, User
from app.schemas import VendorIssueCreate, VendorIssueOut, VendorIssueUpdate
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vendor-issues", tags=["vendor-issues"])

# SLA en dias por severidad (None = sin fecha limite)
_SLA_DAYS: dict[VendorIssueSeverity, Optional[int]] = {
    VendorIssueSeverity.CRITICAL: 7,
    VendorIssueSeverity.HIGH: 30,
    VendorIssueSeverity.MEDIUM: 90,
    VendorIssueSeverity.LOW: 180,
    VendorIssueSeverity.INFORMATIONAL: None,
}

# Estados que se consideran "cerrados" (no cuentan como vencidos ni abiertos)
_CLOSED_STATUSES = {VendorIssueStatus.CLOSED, VendorIssueStatus.MITIGATED, VendorIssueStatus.ACCEPTED}

# Estados que cuentan como "abiertos" para el resumen
_OPEN_STATUSES = {VendorIssueStatus.OPEN, VendorIssueStatus.ACKNOWLEDGED, VendorIssueStatus.IN_REMEDIATION}

# Orden de severidad para ordenar (menor indice = mayor criticidad)
_SEVERITY_ORDER = {
    VendorIssueSeverity.CRITICAL: 0,
    VendorIssueSeverity.HIGH: 1,
    VendorIssueSeverity.MEDIUM: 2,
    VendorIssueSeverity.LOW: 3,
    VendorIssueSeverity.INFORMATIONAL: 4,
}


def _next_code(db: Session, org_id: int) -> str:
    # Kept for backward compatibility; real code is assigned post-flush.
    return "VIS-0000"


def _is_overdue(issue: VendorIssue, now: datetime) -> bool:
    """Devuelve True si el issue tiene due_date en el pasado y no esta cerrado."""
    if not issue.due_date:
        return False
    if issue.status in _CLOSED_STATUSES:
        return False
    due = issue.due_date
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due < now


def _mark_overdue_in_db(db: Session, issues: list[VendorIssue], now: datetime) -> bool:
    """Persiste el estado OVERDUE en issues vencidos que aun no lo tienen. Retorna True si hubo cambios."""
    changed = False
    for issue in issues:
        if (
            _is_overdue(issue, now)
            and issue.status in (
                VendorIssueStatus.OPEN,
                VendorIssueStatus.ACKNOWLEDGED,
                VendorIssueStatus.IN_REMEDIATION,
            )
        ):
            issue.status = VendorIssueStatus.OVERDUE
            changed = True
    return changed


@router.get("/stats/summary")
def vendor_issues_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    issues = filter_by_org(db.query(VendorIssue), VendorIssue, current_user).all()
    now = datetime.now(timezone.utc)

    # Persistir overdue antes de calcular estadisticas
    if _mark_overdue_in_db(db, issues, now):
        db.commit()

    total = len(issues)
    open_count = sum(1 for i in issues if i.status in _OPEN_STATUSES)
    overdue_count = sum(
        1 for i in issues
        if i.status == VendorIssueStatus.OVERDUE or (
            _is_overdue(i, now) and i.status not in _CLOSED_STATUSES
        )
    )
    by_severity: dict[str, int] = {s.value: 0 for s in VendorIssueSeverity}
    for i in issues:
        by_severity[i.severity.value] += 1

    return {
        "total": total,
        "open": open_count,
        "overdue": overdue_count,
        "by_severity": by_severity,
    }


@router.get("/", response_model=list[VendorIssueOut])
def list_vendor_issues(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    supplier_id: Optional[int] = None,
    status: Optional[VendorIssueStatus] = None,
    severity: Optional[VendorIssueSeverity] = None,
    overdue: Optional[bool] = None,
):
    q = filter_by_org(db.query(VendorIssue), VendorIssue, current_user)
    if supplier_id is not None:
        q = q.filter(VendorIssue.supplier_id == supplier_id)
    if severity is not None:
        q = q.filter(VendorIssue.severity == severity)

    issues = q.all()
    now = datetime.now(timezone.utc)

    # Persistir overdue antes de filtrar por estado
    if _mark_overdue_in_db(db, issues, now):
        db.commit()

    # Filtrar por estado tras la actualizacion de overdue
    if status is not None:
        issues = [i for i in issues if i.status == status]

    # Filtrar por overdue si se solicita
    if overdue is True:
        issues = [
            i for i in issues
            if i.status == VendorIssueStatus.OVERDUE or (
                _is_overdue(i, now) and i.status not in _CLOSED_STATUSES
            )
        ]
    elif overdue is False:
        issues = [
            i for i in issues
            if not (
                i.status == VendorIssueStatus.OVERDUE or (
                    _is_overdue(i, now) and i.status not in _CLOSED_STATUSES
                )
            )
        ]

    # Ordenar: severidad (critical first), luego due_date ascendente (None al final)
    issues.sort(key=lambda i: (
        _SEVERITY_ORDER.get(i.severity, 99),
        i.due_date or datetime.max.replace(tzinfo=timezone.utc),
    ))

    return issues


@router.get("/{iid}", response_model=VendorIssueOut)
def get_vendor_issue(
    iid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lang = get_lang(request)
    issue = db.query(VendorIssue).filter(VendorIssue.id == iid).first()
    if not issue or not check_org_access(issue.organization_id, current_user):
        raise HTTPException(404, _t("tprm.issue_not_found", lang))
    return issue


@router.post("/", response_model=VendorIssueOut)
def create_vendor_issue(
    body: VendorIssueCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    org_id = current_user.organization_id

    # Validar que el proveedor pertenece a la misma org
    supplier = db.query(Supplier).filter(Supplier.id == body.supplier_id).first()
    if not supplier or not check_org_access(supplier.organization_id, current_user):
        raise HTTPException(404, "Proveedor no encontrado")

    now = datetime.now(timezone.utc)

    # Calcular due_date por SLA si no se proporciona
    due_date = body.due_date
    if due_date is None:
        sla_days = _SLA_DAYS.get(body.severity)
        if sla_days is not None:
            due_date = now + timedelta(days=sla_days)

    issue = VendorIssue(
        organization_id=org_id,
        code="VIS-0000",
        supplier_id=body.supplier_id,
        assessment_id=body.assessment_id,
        source=body.source,
        title=body.title,
        description=body.description,
        severity=body.severity,
        status=VendorIssueStatus.OPEN,
        framework_refs=body.framework_refs,
        discovered_at=now,
        due_date=due_date,
        assigned_to_user_id=body.assigned_to_user_id,
        remediation_plan=body.remediation_plan,
        sla_breaches=body.sla_breaches,
        impact_description=body.impact_description,
        root_cause=body.root_cause,
        action_items=body.action_items,
        evidence_refs=body.evidence_refs,
        created_by_id=current_user.id,
    )
    db.add(issue)
    db.flush()
    issue.code = f"VIS-{issue.id:04d}"
    db.commit()
    db.refresh(issue)
    log_action(db, current_user.id, "create", "vendor_issue", str(issue.id),
               {"code": issue.code, "severity": issue.severity.value})

    # Hallazgo CRITICAL/HIGH en proveedor → notificar a risk owners y crear TreatmentTask
    if issue.severity in (VendorIssueSeverity.CRITICAL, VendorIssueSeverity.HIGH):
        try:
            _notify_vendor_issue_to_risks(db, issue, org_id)
        except Exception as _exc:
            logger.warning("VendorIssue→risk notify failed: %s", _exc)

    # VendorIssue CRITICAL → crear riesgo ISO 27005 en el registro
    if issue.severity == VendorIssueSeverity.CRITICAL:
        try:
            _auto_risk_from_critical_issue(db, issue, org_id, current_user.id)
        except Exception as _exc:
            logger.warning("VendorIssue→Risk auto-create failed: %s", _exc)

    return issue


def _create_orphan_issue_task(db: Session, issue: VendorIssue, org_id: int,
                              created_by_id: int, missing: str) -> None:
    """El issue critico no pudo materializarse como riesgo: crear tarea visible
    en lugar de fallar en silencio (falta activo o amenaza de catalogo)."""
    try:
        from app.models import TaskPriority, TaskStatus, TreatmentTask
        title = f"Issue de proveedor sin riesgo asociado: {issue.code}"
        dup = db.query(TreatmentTask).filter(
            TreatmentTask.organization_id == org_id,
            TreatmentTask.title == title,
            TreatmentTask.status != TaskStatus.DONE,
        ).first()
        if dup:
            return
        count = db.query(TreatmentTask).filter_by(organization_id=org_id).count()
        code = f"TSK-{count + 1:04d}"
        while db.query(TreatmentTask).filter_by(code=code).first():
            count += 1
            code = f"TSK-{count + 1:04d}"
        db.add(TreatmentTask(
            organization_id=org_id,
            code=code,
            title=title,
            description=(
                f"El VendorIssue CRITICAL {issue.code} no pudo registrarse como "
                f"riesgo ISO 27005 porque falta {missing} en la plataforma. "
                f"Registra el elemento que falta y vincula el issue manualmente "
                f"al registro de riesgos."
            ),
            status=TaskStatus.PENDING,
            priority=TaskPriority.HIGH,
            assigned_to_id=created_by_id,
            created_by_id=created_by_id,
        ))
        db.commit()
        logger.info("VendorIssue %s sin riesgo: tarea %s creada (falta %s)",
                    issue.code, code, missing)
    except Exception:
        logger.exception("No se pudo crear la tarea de issue huerfano")


def _auto_risk_from_critical_issue(db: Session, issue: VendorIssue, org_id: int, created_by_id: int) -> None:
    """Crea un riesgo ISO 27005 en el registro cuando un VendorIssue es CRITICAL.

    Bucle cerrado: cuando el VendorIssue se cierra, recompute_supplier_risk_profile
    reduce el likelihood del riesgo vinculado.
    """
    from app.models import Risk, RiskStatus, Threat, Asset

    supplier = db.get(Supplier, issue.supplier_id)
    if not supplier:
        return

    # Activo: preferir uno que mencione al proveedor (servicio/sistema que
    # presta); fallback al de mayor valoracion. Requisito: asset_id NOT NULL.
    asset = None
    sup_name = (supplier.name or "").lower()
    if len(sup_name) >= 4:
        for a in db.query(Asset).filter(Asset.organization_id == org_id).all():
            haystack = " ".join(filter(None, [a.name, a.description, a.category])).lower()
            if sup_name in haystack:
                asset = a
                break
    if not asset:
        asset = (
            db.query(Asset)
            .filter(Asset.organization_id == org_id)
            .order_by(Asset.value_confidentiality.desc(), Asset.id)
            .first()
        )

    # Amenaza: codigo exacto del catalogo ISO 27005 (T.CYB.05 = cadena de
    # suministro); fallback a busqueda heuristica por nombre
    threat = db.query(Threat).filter(Threat.code == "T.CYB.05").first()
    if not threat:
        threat = (
            db.query(Threat)
            .filter(
                Threat.name.ilike("%supply%")
                | Threat.name.ilike("%suministro%")
                | Threat.name.ilike("%proveedor%")
                | Threat.name.ilike("%third party%")
                | Threat.category.ilike("%supply%")
            )
            .first()
        )
    if not threat:
        threat = db.query(Threat).filter(Threat.category.ilike("%organiz%")).first()

    if not asset or not threat:
        # No fallar en silencio: dejar accion visible para el analista
        _create_orphan_issue_task(db, issue, org_id, created_by_id,
                                  missing="activo" if not asset else "amenaza de cadena de suministro")
        return

    # Comprobar si ya existe un riesgo para este par activo+amenaza+proveedor
    existing = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.asset_id == asset.id,
        Risk.threat_id == threat.id,
        Risk.supplier_id == supplier.id,
    ).first()
    if existing:
        # Vincular el issue al riesgo existente si no esta vinculado
        if not issue.linked_risk_id:
            issue.linked_risk_id = existing.id
            db.commit()
        return

    # Generar codigo RSK-XXXX unico
    from app.routers.risks import _next_code as _risk_next_code
    code = _risk_next_code(db, org_id)
    while db.query(Risk).filter_by(code=code).first():
        n = int(code.split("-")[1]) + 1
        code = f"RSK-{n:04d}"

    # Consecuencia acotada por la valoracion del activo afectado
    from app.services.risk_auto_generator import _cap_consequence_by_asset
    from app.services.risk_engine import calc_level
    inh_con = _cap_consequence_by_asset(asset, 4)
    inh_lik = 4  # issue CRITICAL abierto = amenaza materializable ya

    now = datetime.now(timezone.utc)
    risk = Risk(
        organization_id=org_id,
        code=code,
        asset_id=asset.id,
        threat_id=threat.id,
        supplier_id=supplier.id,
        description=(
            f"Riesgo auto-generado a partir de VendorIssue CRITICAL {issue.code} "
            f"del proveedor {supplier.name}. "
            f"Descripcion del issue: {(issue.description or '')[:300]}. "
            f"Para mitigar: resolver el VendorIssue {issue.code} — al cerrarlo, "
            f"el sistema reducira automaticamente el likelihood de este riesgo."
        ),
        inherent_likelihood=inh_lik,
        inherent_consequence=inh_con,
        inherent_level=calc_level(inh_con, inh_lik),
        residual_likelihood=inh_lik,
        residual_consequence=inh_con,
        residual_level=calc_level(inh_con, inh_lik),
        status=RiskStatus.IDENTIFIED,
        owner_id=created_by_id,
        ai_generated=True,
        ai_rationale=f"Creado automaticamente desde VendorIssue CRITICAL {issue.code} del proveedor {supplier.name}.",
        created_at=now,
    )
    db.add(risk)
    db.flush()

    # Vincular el issue al riesgo creado
    issue.linked_risk_id = risk.id

    try:
        from app.routers.risks import _recalc
        _recalc(db, risk)
    except Exception:
        pass

    db.commit()
    logger.info(
        "Auto-created supply-chain risk %s from CRITICAL VendorIssue %s (supplier=%s)",
        code, issue.code, supplier.name,
    )


def _notify_vendor_issue_to_risks(
    db: Session, issue: VendorIssue, org_id: int
) -> None:
    """Para hallazgos CRITICAL/HIGH: notifica a owners de riesgos del proveedor y crea tarea."""
    from app.models import Risk, RiskStatus, TreatmentTask, TaskPriority, TaskStatus
    from app.services import email_service

    tprm_risks = db.query(Risk).filter(
        Risk.supplier_id == issue.supplier_id,
        Risk.organization_id == org_id,
        Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
    ).all()

    cfg = email_service.get_settings_for_org(db, org_id)
    now = datetime.now(timezone.utc)

    for r in tprm_risks:
        # Email al risk owner si tiene email configurado
        if cfg and cfg.smtp_host and r.owner and r.owner.email:
            import html as _html
            sev_label = issue.severity.value.upper()
            subject = f"[RiskHub] Hallazgo {sev_label} en proveedor — riesgo {r.code} afectado"
            body_html = (
                f"<p>Se ha detectado un hallazgo <strong>{sev_label}</strong> en el proveedor "
                f"vinculado al riesgo <strong>{_html.escape(r.code)}</strong>.</p>"
                f"<p><strong>Hallazgo:</strong> {_html.escape(issue.title)}</p>"
                f"<p>Revisa el registro de riesgos y el estado del proveedor en RiskHub.</p>"
            )
            try:
                email_service.send_email(cfg, r.owner.email, subject,
                                          email_service._wrap_html(subject, body_html, ""))
            except Exception:
                pass

        # Crear TreatmentTask si el hallazgo es CRITICAL
        if issue.severity == VendorIssueSeverity.CRITICAL:
            task_count_q = db.query(TreatmentTask).filter(
                TreatmentTask.risk_id == r.id,
                TreatmentTask.organization_id == org_id,
                TreatmentTask.status.notin_([TaskStatus.DONE]),
                TreatmentTask.title.ilike(f"%{issue.code}%"),
            ).count()
            if task_count_q == 0:
                task = TreatmentTask(
                    organization_id=org_id,
                    code="TSK-0000",
                    title=f"[{issue.code}] Revisar impacto hallazgo CRITICO en proveedor: {issue.title[:80]}",
                    risk_id=r.id,
                    priority=TaskPriority.CRITICAL,
                    status=TaskStatus.PENDING,
                    due_date=now + timedelta(days=7),
                )
                db.add(task)
                db.flush()
                task.code = f"TSK-{task.id:04d}"

    if tprm_risks:
        db.commit()


@router.patch("/{iid}", response_model=VendorIssueOut)
def update_vendor_issue(
    iid: int,
    body: VendorIssueUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    issue = db.query(VendorIssue).filter(VendorIssue.id == iid).first()
    if not issue or not check_org_access(issue.organization_id, current_user):
        raise HTTPException(404, "Hallazgo no encontrado")

    update_data = body.model_dump(exclude_none=True)

    # Si se cierra / mitiga / acepta, registrar fecha de cierre y aprobacion de Seguridad
    new_status = update_data.get("status")
    _closed_values = {s.value for s in _CLOSED_STATUSES}
    _new_status_val = new_status.value if isinstance(new_status, VendorIssueStatus) else new_status
    if _new_status_val in _closed_values and not issue.closed_at:
        update_data["closed_at"] = datetime.now(timezone.utc)
        # Punto 9: el cierre queda sellado con quien lo aprobo (require_analyst = Seguridad)
        issue.closure_approved_by_id = current_user.id
        issue.closure_approved_at = datetime.now(timezone.utc)

    for field, value in update_data.items():
        setattr(issue, field, value)

    db.commit()
    db.refresh(issue)
    log_action(db, current_user.id, "update", "vendor_issue", str(issue.id))

    # Bucle cerrado: si el issue cambia a cerrado/mitigado, recomputar perfil del proveedor
    if _new_status_val in _closed_values:
        try:
            from app.services.supplier_lifecycle_service import recompute_supplier_risk_profile
            recompute_supplier_risk_profile(db, issue.supplier_id, triggered_by="vendor_issue_resolved")
        except Exception as _e:
            logger.warning("recompute after issue close failed: %s", _e)

    return issue


@router.post("/{iid}/approve-closure", response_model=VendorIssueOut)
def approve_closure(
    iid: int,
    body: dict = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Cierra un hallazgo con aprobacion formal de Seguridad (punto 9).

    Marca el hallazgo como completado y sella quien lo aprobo, desde la misma caja.
    """
    issue = db.query(VendorIssue).filter(VendorIssue.id == iid).first()
    if not issue or not check_org_access(issue.organization_id, current_user):
        raise HTTPException(404, "Hallazgo no encontrado")
    now = datetime.now(timezone.utc)
    issue.status = VendorIssueStatus.CLOSED
    issue.closed_at = issue.closed_at or now
    issue.closure_approved_by_id = current_user.id
    issue.closure_approved_at = now
    if body and body.get("resolution_notes"):
        issue.resolution_notes = body["resolution_notes"]
    db.commit()
    db.refresh(issue)
    log_action(db, current_user.id, "approve_closure", "vendor_issue", str(issue.id))
    try:
        from app.services.supplier_lifecycle_service import recompute_supplier_risk_profile
        recompute_supplier_risk_profile(db, issue.supplier_id, triggered_by="vendor_issue_closure_approved")
    except Exception as _e:
        logger.warning("recompute after closure approval failed: %s", _e)
    return issue


@router.delete("/{iid}", status_code=204)
def delete_vendor_issue(
    iid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    issue = db.query(VendorIssue).filter(VendorIssue.id == iid).first()
    if not issue or not check_org_access(issue.organization_id, current_user):
        raise HTTPException(404, "Hallazgo no encontrado")
    log_action(db, current_user.id, "delete", "vendor_issue", str(iid), {"code": issue.code})
    db.delete(issue)
    db.commit()
