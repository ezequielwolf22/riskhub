"""Motor de workflow automatico para riesgos: asignacion, SLA, escalada, cierre."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Risk, RiskStatus, RiskWorkflow, WorkflowStepStatus,
    TreatmentTask, TaskStatus, TaskPriority,
    User, UserRole, Asset,
)
from app.services import email_service

logger = logging.getLogger("riskhub.workflow")

_SLA_BY_LEVEL = {
    # residual_level -> días SLA
    7: 7,    # CRITICAL
    6: 7,
    5: 15,   # HIGH
    4: 15,
    3: 30,   # MEDIUM
    2: 60,
    1: 90,   # LOW
    0: 90,
}


def _next_task_code(db: Session, org_id: int) -> str:
    from app.models import TreatmentTask
    count = db.query(TreatmentTask).filter_by(organization_id=org_id).count()
    code = f"TSK-{count + 1:04d}"
    while db.query(TreatmentTask).filter_by(code=code).first():
        count += 1
        code = f"TSK-{count + 1:04d}"
    return code


def _find_analyst(db: Session, org_id: int) -> Optional[User]:
    """Busca un analyst activo para asignación."""
    analyst = db.query(User).filter(
        User.organization_id == org_id,
        User.role == UserRole.ANALYST,
        User.is_active == True,
    ).first()
    if not analyst:
        analyst = db.query(User).filter(
            User.organization_id == org_id,
            User.role == UserRole.ADMIN,
            User.is_active == True,
        ).first()
    return analyst


def _find_owner(db: Session, risk: Risk) -> Optional[User]:
    """Busca el owner del activo como owner del riesgo.

    Asset.owners es una relacion M2M; no existe Asset.owner_id.
    """
    if risk.owner_id:
        return db.get(User, risk.owner_id)
    if risk.asset_id:
        asset = db.get(Asset, risk.asset_id)
        if asset:
            owners = getattr(asset, "owners", []) or []
            if owners:
                return owners[0]
    return None


def start_risk_workflow(db: Session, risk: Risk) -> Optional[RiskWorkflow]:
    """Inicia workflow automatico para un riesgo.

    Crea RiskWorkflow + 3 tareas (analysis, mitigation, verification).
    Retorna el workflow creado.
    """
    if not risk.organization_id:
        return None

    # Evitar duplicado
    existing = db.query(RiskWorkflow).filter_by(risk_id=risk.id).first()
    if existing:
        return existing

    org_id = risk.organization_id
    residual = risk.residual_level or 2
    sla_days = _SLA_BY_LEVEL.get(residual, 30)

    analyst = _find_analyst(db, org_id)
    owner = _find_owner(db, risk)

    workflow = RiskWorkflow(
        organization_id=org_id,
        risk_id=risk.id,
        step_analysis=WorkflowStepStatus.PENDING,
        step_mitigation=WorkflowStepStatus.PENDING,
        step_verification=WorkflowStepStatus.PENDING,
        step_closure=WorkflowStepStatus.PENDING,
        assigned_analyst_id=analyst.id if analyst else None,
        assigned_owner_id=owner.id if owner else None,
        sla_days=sla_days,
        sla_due_date=datetime.now(timezone.utc) + timedelta(days=sla_days),
    )
    db.add(workflow)
    db.flush()

    # Crear tareas automaticamente
    risk_code = risk.code or f"RSK-{risk.id}"
    risk_name = risk.description or risk_code
    asset_name = ""
    if risk.asset_id:
        asset = db.get(Asset, risk.asset_id)
        if asset:
            asset_name = asset.name or ""

    tasks_def = [
        {
            "title": f"Analizar riesgo {risk_code}",
            "description": (
                f"Analizar el riesgo '{risk_name}' (activo: {asset_name}). "
                f"Revisar residual_level={residual}, inherent_level={risk.inherent_level}. "
                f"Confirmar amenaza y vulnerabilidad. Documentar hallazgos."
            ),
            "priority": TaskPriority.HIGH if residual >= 5 else TaskPriority.MEDIUM,
            "assigned_to_id": analyst.id if analyst else None,
            "due_offset_days": max(3, sla_days // 4),
        },
        {
            "title": f"Mitigar riesgo {risk_code}",
            "description": (
                f"Implementar tratamiento para '{risk_name}'. "
                f"Elegir opción: MODIFICATION / RETENTION / AVOIDANCE / SHARING. "
                f"Documentar controles aplicados."
            ),
            "priority": TaskPriority.HIGH if residual >= 5 else TaskPriority.MEDIUM,
            "assigned_to_id": owner.id if owner else (analyst.id if analyst else None),
            "due_offset_days": max(7, sla_days // 2),
        },
        {
            "title": f"Verificar cierre de {risk_code}",
            "description": (
                f"Verificar que '{risk_name}' ha sido tratado correctamente. "
                f"Recalcular residual con nuevos controles. "
                f"Si residual <= appetite → cerrar riesgo. Subir evidencia."
            ),
            "priority": TaskPriority.MEDIUM,
            "assigned_to_id": analyst.id if analyst else None,
            "due_offset_days": sla_days,
        },
    ]

    now = datetime.now(timezone.utc)
    for t in tasks_def:
        task = TreatmentTask(
            organization_id=org_id,
            code=_next_task_code(db, org_id),
            title=t["title"],
            description=t["description"],
            status=TaskStatus.PENDING,
            priority=t["priority"],
            assigned_to_id=t["assigned_to_id"],
            created_by_id=t["assigned_to_id"],
            risk_id=risk.id,
            due_date=now + timedelta(days=t["due_offset_days"]),
        )
        db.add(task)

    try:
        db.commit()
        db.refresh(workflow)
        logger.info(
            "Workflow iniciado para riesgo %s (residual=%d, SLA=%d días)",
            risk_code, residual, sla_days
        )
        # Notificación
        _notify_workflow_started(db, risk, workflow, analyst, owner)
        return workflow
    except Exception as exc:
        logger.exception("Error creando workflow para %s: %s", risk_code, exc)
        db.rollback()
        return None


def _notify_workflow_started(db: Session, risk: Risk, workflow: RiskWorkflow,
                              analyst: Optional[User], owner: Optional[User]) -> None:
    """Envía email de notificación cuando se inicia workflow."""
    try:
        # B17: usar SMTP por org, nunca global
        cfg = email_service.get_settings(db, org_id=risk.organization_id)
        if not cfg or not cfg.smtp_host:
            return
        recipients = []
        if analyst and analyst.email:
            recipients.append(analyst.email)
        if owner and owner.email and owner.email not in recipients:
            recipients.append(owner.email)
        if not recipients:
            return

        risk_code = risk.code or f"RSK-{risk.id}"
        subject = f"[RiskHub] Nuevo workflow iniciado: {risk_code}"
        body = (
            f"<p>Se ha iniciado el workflow de gestión para el riesgo <strong>{risk_code}</strong>.</p>"
            f"<p><strong>Nivel residual:</strong> {risk.residual_level}</p>"
            f"<p><strong>SLA:</strong> {workflow.sla_days} días "
            f"(vence: {workflow.sla_due_date.strftime('%d/%m/%Y') if workflow.sla_due_date else 'N/A'})</p>"
            f"<p>Se han creado 3 tareas automáticamente en RiskHub. Por favor, revisa y actúa.</p>"
        )
        for recipient in recipients:
            email_service.send_email(cfg, recipient, subject, body)
    except Exception as exc:
        logger.debug("Error enviando notificación workflow: %s", exc)


def check_and_auto_close_risk(db: Session, risk_id: int) -> bool:
    """Verifica si todas las tareas del riesgo están cerradas → auto-cierra riesgo.

    Retorna True si el riesgo fue auto-cerrado.
    """
    risk = db.get(Risk, risk_id)
    if not risk:
        return False

    workflow = db.query(RiskWorkflow).filter_by(risk_id=risk_id).first()
    if not workflow:
        return False

    # Verificar tareas
    tasks = db.query(TreatmentTask).filter(
        TreatmentTask.risk_id == risk_id,
        TreatmentTask.organization_id == risk.organization_id,
    ).all()

    all_done = all(t.status == TaskStatus.DONE for t in tasks) if tasks else False

    if not all_done:
        return False

    # Recalcular residual con controles actuales
    from app.services.risk_engine import calc_residual
    from app.models import RiskContext
    ctx = db.query(RiskContext).filter(
        RiskContext.organization_id == risk.organization_id
    ).first()
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3
    matrix = ctx.risk_matrix if ctx and ctx.risk_matrix else None

    controls = risk.controls or []
    rl, rc, rlev = calc_residual(
        risk.residual_likelihood or risk.inherent_likelihood or 2,
        risk.residual_consequence or risk.inherent_consequence or 2,
        controls,
        matrix,
    )
    risk.residual_likelihood = rl
    risk.residual_consequence = rc
    risk.residual_level = rlev

    from app.models import TreatmentOption
    if rlev <= appetite:
        risk.treatment_option = TreatmentOption.RETENTION  # C2: ACCEPTANCE no existe en el enum
        risk.status = RiskStatus.ACCEPTED
        workflow.step_closure = WorkflowStepStatus.DONE
        workflow.completed_at = datetime.now(timezone.utc)
        logger.info("Riesgo %s auto-cerrado: residual=%d <= appetite=%d", risk.code, rlev, appetite)
    else:
        risk.status = RiskStatus.ASSESSED
        # Escalada
        workflow.escalated = True
        workflow.escalated_at = datetime.now(timezone.utc)
        logger.warning("Riesgo %s requiere escalada: residual=%d > appetite=%d", risk.code, rlev, appetite)

    try:
        db.commit()
        return risk.status == RiskStatus.ACCEPTED
    except Exception as exc:
        logger.exception("Error cerrando riesgo %s: %s", risk.code, exc)
        db.rollback()
        return False


def run_sla_check(db: Session) -> None:
    """Verifica SLAs vencidos y escalada riesgos que no se han tratado a tiempo."""
    from app.models import Organization

    now = datetime.now(timezone.utc)
    overdue_workflows = db.query(RiskWorkflow).filter(
        RiskWorkflow.sla_due_date < now,
        RiskWorkflow.step_closure != WorkflowStepStatus.DONE,
        RiskWorkflow.escalated == False,
    ).all()

    for wf in overdue_workflows:
        risk = db.get(Risk, wf.risk_id)
        if not risk:
            continue

        wf.escalated = True
        wf.escalated_at = now

        # Notificar a admin — B17: SMTP por org
        try:
            cfg = email_service.get_settings(db, org_id=risk.organization_id)
            if cfg and cfg.smtp_host:
                admin = db.query(User).filter(
                    User.organization_id == risk.organization_id,
                    User.role == UserRole.ADMIN,
                    User.is_active == True,
                ).first()
                if admin and admin.email:
                    subject = f"[RiskHub] ESCALADA: Riesgo {risk.code} con SLA vencido"
                    body = (
                        f"<p>El riesgo <strong>{risk.code}</strong> ha superado su SLA de "
                        f"{wf.sla_days} días sin ser cerrado.</p>"
                        f"<p><strong>Nivel residual:</strong> {risk.residual_level}</p>"
                        f"<p>Se requiere atención inmediata.</p>"
                    )
                    email_service.send_email(cfg, admin.email, subject, body)
        except Exception as exc:
            logger.debug("Error escalada email: %s", exc)

        logger.warning("Riesgo %s escalado por SLA vencido", risk.code)

    if overdue_workflows:
        try:
            db.commit()
        except Exception:
            db.rollback()

    logger.info("SLA check: %d workflows escalados", len(overdue_workflows))
