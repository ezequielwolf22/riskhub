"""Gestion de organizaciones / tenants — administracion multi-org."""
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("riskhub.organizations")

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import (
    AiCallLog, Organization, User, UserRole,
)
from app.schemas import OrganizationIn, OrganizationOut, OrganizationUpdate
from app.security import get_current_user, require_admin, require_superadmin
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


def _to_out(org: Organization, db: Session) -> OrganizationOut:
    user_count = db.query(User).filter(User.organization_id == org.id).count()
    token_usage = db.query(
        func.coalesce(func.sum(AiCallLog.prompt_tokens + AiCallLog.completion_tokens), 0)
    ).filter(AiCallLog.organization_id == org.id).scalar() or 0
    o = OrganizationOut.model_validate(org)
    return o.model_copy(update={"user_count": user_count, "token_usage": token_usage})


# ── Listar (superadmin ve todo; admin solo ve la suya) ─────────────────────────

@router.get("/", response_model=list[OrganizationOut])
def list_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if current_user.role == UserRole.SUPERADMIN:
        orgs = db.query(Organization).order_by(Organization.created_at.desc()).all()
    else:
        orgs = db.query(Organization).filter(
            Organization.id == current_user.organization_id
        ).all()
    return [_to_out(o, db) for o in orgs]


@router.get("/current", response_model=OrganizationOut)
def get_current_org(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve la organizacion del usuario autenticado."""
    lang = get_lang(request)
    if not current_user.organization_id:
        raise HTTPException(404, _t("organizations.not_found", lang))
    org = db.get(Organization, current_user.organization_id)
    if not org:
        raise HTTPException(404, _t("organizations.not_found", lang))
    return _to_out(org, db)


@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organizacion no encontrada")
    # Admin solo puede ver su propia org
    if current_user.role != UserRole.SUPERADMIN and org.id != current_user.organization_id:
        raise HTTPException(403, "No autorizado")
    return _to_out(org, db)


# ── Crear (solo superadmin) ─────────────────────────────────────────────────────

@router.post("/", response_model=OrganizationOut, status_code=201)
def create_organization(
    data: OrganizationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    if data.domain:
        existing = db.query(Organization).filter(
            Organization.domain == data.domain.lower()
        ).first()
        if existing:
            raise HTTPException(400, f"Ya existe una organizacion con el dominio {data.domain}")
    org = Organization(
        name=data.name,
        domain=data.domain.lower() if data.domain else None,
        plan=data.plan,
        is_active=data.is_active,
        max_users=data.max_users,
    )
    db.add(org)
    log_action(db, current_user.id, "create", "organization", None,
               {"name": data.name, "domain": data.domain, "plan": data.plan})
    db.commit()
    db.refresh(org)
    try:
        from app.seed import seed_default_survey_templates
        seed_default_survey_templates(db, org.id)
    except Exception as _e:
        logger.warning("seed_default_survey_templates failed for org %d: %s", org.id, _e)
    return _to_out(org, db)


# ── Actualizar ─────────────────────────────────────────────────────────────────

@router.patch("/{org_id}", response_model=OrganizationOut)
def update_organization(
    org_id: int,
    data: OrganizationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organizacion no encontrada")
    # Admin solo puede editar su propia org; superadmin puede editar cualquiera
    if current_user.role != UserRole.SUPERADMIN and org.id != current_user.organization_id:
        raise HTTPException(403, "No autorizado")
    # Admin no puede cambiar plan ni max_users (solo superadmin)
    if current_user.role != UserRole.SUPERADMIN:
        data.plan = None
        data.max_users = None

    if data.name is not None:
        org.name = data.name
    if data.domain is not None:
        org.domain = data.domain.lower()
    if data.plan is not None:
        org.plan = data.plan
    if data.is_active is not None:
        org.is_active = data.is_active
    if data.max_users is not None:
        org.max_users = data.max_users

    log_action(db, current_user.id, "update", "organization", str(org_id),
               data.model_dump(exclude_none=True))
    db.commit()
    db.refresh(org)
    return _to_out(org, db)


# ── Desactivar (soft delete) ────────────────────────────────────

@router.delete("/{org_id}", status_code=204)
def delete_organization(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organizacion no encontrada")
    # Seguridad: no eliminar la org del superadmin
    if org.id == current_user.organization_id:
        raise HTTPException(400, "No puedes eliminar tu propia organizacion")
    log_action(db, current_user.id, "delete", "organization", str(org_id),
               {"name": org.name})
    # Desactivar en lugar de borrar fisicamente para preservar integridad referencial
    org.is_active = False
    db.commit()


# ── Eliminar permanentemente (hard delete) ────────────────────────────────────

class PermanentDeleteIn(BaseModel):
    """Confirmación para eliminación permanente."""
    confirmation_text: str  # debe ser exactamente "ELIMINAR PERMANENTEMENTE"


@router.post("/{org_id}/delete-permanently", status_code=200)
def delete_organization_permanently(
    org_id: int,
    data: PermanentDeleteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Elimina una organizacion PERMANENTEMENTE con todo su contenido.

    Esta operacion es IRREVERSIBLE. Se registra en logs de seguridad como evidencia.
    """
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organizacion no encontrada")

    # Seguridad: no permitir eliminar la org del superadmin
    if org.id == current_user.organization_id:
        raise HTTPException(400, "No puedes eliminar tu propia organizacion")

    # Verificar texto de confirmación
    if data.confirmation_text != "ELIMINAR PERMANENTEMENTE":
        raise HTTPException(400, "Texto de confirmacion incorrecto")

    org_name = org.name
    org_id_str = str(org_id)

    # Registrar en auditoria ANTES de borrar (como evidencia)
    log_action(
        db, current_user.id, "delete_permanently", "organization", org_id_str,
        {
            "name": org_name,
            "action": "Eliminacion permanente e irreversible de la organizacion",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "deleted_by_user_id": current_user.id,
            "deleted_by_email": current_user.email,
        }
    )

    # Eliminar datos en cascada
    from sqlalchemy import text

    # Primero, obtener usuarios para borrar referencias cruzadas
    users = db.query(User).filter(User.organization_id == org_id).all()

    # Eliminar tabla por tabla (respetando dependencias)
    # Se hace por SQL directo para eficiencia
    try:
        # Tablas que referencian organization_id
        tables_to_delete = [
            "ai_call_logs",
            "ai_documents",
            "ai_conversations",
            "alert_rules",
            "assets",
            "asset_groups",
            "asset_vulnerability_evidence",
            "audit_log",
            "audit_programs",
            "audit_findings",
            "bcp_continuity_plans",
            "bcp_recovery_plans",
            "ccm_test_results",
            "ccm_tests",
            "change_requests",
            "compliance_framework_status",
            "control_implementations",
            "controls",
            "cve_scans",
            "email_settings",
            "evidence",
            "evidence_attachments",
            "external_findings",
            "feature_flags",
            "gdpr_dpia",
            "gdpr_processing",
            "incidents",
            "integration_configs",
            "itsm_configurations",
            "license_audits",
            "licenses",
            "management_reviews",
            "nonconformities",
            "osint_findings",
            "osint_identifiers",
            "osint_scans",
            "policies",
            "report_schedules",
            "reports",
            "risk_acceptance",
            "risk_context",
            "risk_review_schedules",
            "risks",
            "soa_versions",
            "supplier_questionnaire_responses",
            "supplier_questionnaires",
            "suppliers",
            "threat_vulnerability_mapping",
            "treatment_tasks",
            "webhooks",
            "webhook_events",
        ]

        for table in tables_to_delete:
            try:
                db.execute(
                    text(f"DELETE FROM {table} WHERE organization_id = :org_id"),
                    {"org_id": org_id}
                )
            except Exception:
                # Ignorar errores si la tabla no existe o tiene restricciones
                pass

        # Finalmente, eliminar usuarios asociados
        db.query(User).filter(User.organization_id == org_id).delete()

        # Eliminar la organizacion misma
        db.delete(org)

        db.commit()

        import logging
        logger = logging.getLogger("riskhub.security")
        logger.warning(
            f"ORGANIZACION ELIMINADA PERMANENTEMENTE: {org_name} (ID:{org_id}) "
            f"por {current_user.email} ({current_user.id})"
        )

        return {
            "ok": True,
            "message": f"Organizacion '{org_name}' eliminada permanentemente",
            "organization_id": org_id,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        db.rollback()
        import logging
        logger = logging.getLogger("riskhub.security")
        logger.error(
            f"ERROR al eliminar organizacion {org_name} (ID:{org_id}): {str(e)}"
        )
        raise HTTPException(500, f"Error al eliminar: {str(e)}")


# ── Usuarios de una organizacion (superadmin) ─────────────────────────────────

@router.get("/{org_id}/users")
def list_org_users(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if current_user.role != UserRole.SUPERADMIN and org_id != current_user.organization_id:
        raise HTTPException(403, "No autorizado")
    users = db.query(User).filter(User.organization_id == org_id).order_by(User.created_at).all()
    return [
        {
            "id": u.id, "email": u.email, "full_name": u.full_name,
            "role": u.role.value, "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


class MoveUserIn(BaseModel):
    target_org_id: int


@router.patch("/{org_id}/users/{user_id}/move")
def move_user_to_org(
    org_id: int,
    user_id: int,
    body: MoveUserIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Transfiere un usuario a otra organizacion (solo superadmin)."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    if user.organization_id != org_id:
        raise HTTPException(400, "El usuario no pertenece a la organizacion indicada")
    target_org = db.get(Organization, body.target_org_id)
    if not target_org:
        raise HTTPException(404, "Organizacion destino no encontrada")
    old_org = user.organization_id
    user.organization_id = body.target_org_id
    log_action(db, current_user.id, "update", "user", str(user_id),
               {"action": "move_org", "from": old_org, "to": body.target_org_id})
    db.commit()
    return {"ok": True, "user_id": user_id, "organization_id": body.target_org_id}


# ── Estadisticas de uso de tokens por org (superadmin) ────────────────────────

@router.get("/{org_id}/stats")
def org_stats(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if current_user.role != UserRole.SUPERADMIN and org_id != current_user.organization_id:
        raise HTTPException(403, "No autorizado")
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organizacion no encontrada")

    user_count = db.query(User).filter(User.organization_id == org_id).count()
    active_users = db.query(User).filter(
        User.organization_id == org_id, User.is_active.is_(True)
    ).count()

    token_rows = db.query(
        func.coalesce(func.sum(AiCallLog.prompt_tokens), 0),
        func.coalesce(func.sum(AiCallLog.completion_tokens), 0),
        func.count(AiCallLog.id),
    ).filter(AiCallLog.organization_id == org_id).first()
    prompt_tokens, completion_tokens, ai_calls = token_rows or (0, 0, 0)

    return {
        "organization_id": org_id,
        "name": org.name,
        "plan": org.plan,
        "is_active": org.is_active,
        "max_users": org.max_users,
        "user_count": user_count,
        "active_users": active_users,
        "ai_calls": ai_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": (prompt_tokens or 0) + (completion_tokens or 0),
    }
