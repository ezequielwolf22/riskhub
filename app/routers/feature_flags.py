"""Gestion de feature flags — modulos habilitados por licencia.

Los flags pueden ser globales (organization_id=None) o especificos de una
organizacion. Un flag de org sobreescribe el valor global para esa org.

- GET /api/feature-flags/           : todos los usuarios autenticados pueden consultar
- PATCH /api/feature-flags/{name}   : superadmin (global o por org) / admin (su org)
- DELETE /api/feature-flags/{name}  : superadmin — elimina override de org (no el global)
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FeatureFlag, Organization, User, UserRole
from app.security import get_current_user, require_superadmin
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/feature-flags", tags=["feature-flags"])

# Modulos incluidos por plan (None = sin restricciones = enterprise)
PLAN_MODULE_LIMITS: dict[str, Optional[set[str]]] = {
    "free": {
        "module_assets", "module_risks", "module_controls",
    },
    "starter": {
        "module_assets", "module_risks", "module_controls",
        "module_incidents", "module_policies", "module_tasks",
        "module_compliance", "module_reports",
    },
    "pro": {
        "module_assets", "module_risks", "module_controls",
        "module_incidents", "module_policies", "module_tasks",
        "module_compliance", "module_reports",
        "module_suppliers", "module_nonconformities", "module_audits",
        "module_gdpr", "module_ai", "module_cve", "module_alerts",
    },
    "enterprise": None,  # todos los modulos sin restriccion
}

# Definicion canonica de los modulos del sistema
_DEFAULT_FLAGS = [
    {
        "name": "module_assets",
        "label": "Inventario de Activos",
        "description": "Gestion de activos de informacion segun ISO 27005 Annex B.",
    },
    {
        "name": "module_risks",
        "label": "Gestion de Riesgos",
        "description": "Identificacion, analisis y tratamiento de riesgos ISO 27005.",
    },
    {
        "name": "module_controls",
        "label": "Controles ISO 27002",
        "description": "Catalogo de 93 controles ISO 27002:2022 y SOA.",
    },
    {
        "name": "module_policies",
        "label": "Politicas de Seguridad",
        "description": "Ciclo de vida de politicas ISO 27001 cl. 5.2.",
    },
    {
        "name": "module_incidents",
        "label": "Gestion de Incidentes (NIS2)",
        "description": "Registro y notificacion de incidentes de seguridad.",
    },
    {
        "name": "module_suppliers",
        "label": "Proveedores (Supply Chain)",
        "description": "Evaluacion y gestion de riesgo de proveedores.",
    },
    {
        "name": "module_nonconformities",
        "label": "No Conformidades",
        "description": "Registro y seguimiento de no conformidades ISO 27001.",
    },
    {
        "name": "module_tasks",
        "label": "Tareas de Tratamiento",
        "description": "Gestion de acciones derivadas del tratamiento de riesgos.",
    },
    {
        "name": "module_audits",
        "label": "Auditoria Interna",
        "description": "Programa de auditoria interna ISO 27001 cl. 9.2.",
    },
    {
        "name": "module_gdpr",
        "label": "RGPD / Privacidad",
        "description": "Registro de actividades de tratamiento y DPIAs.",
    },
    {
        "name": "module_compliance",
        "label": "Cumplimiento Multi-Framework",
        "description": "Dashboard de cumplimiento ISO 27001, NIS2, NIST CSF, ENS.",
    },
    {
        "name": "module_ai",
        "label": "Agente IA",
        "description": "Chat IA, cuestionario, sugerencias y documentos RAG.",
    },
    {
        "name": "module_reports",
        "label": "Informes PDF",
        "description": "Generacion de Risk Register y SoA en PDF.",
    },
    {
        "name": "module_integrations",
        "label": "Integraciones",
        "description": "Configuracion de integraciones con sistemas externos.",
    },
    {
        "name": "module_alerts",
        "label": "Alertas por Email",
        "description": "Notificaciones automaticas por email.",
    },
    {
        "name": "module_cve",
        "label": "CVE Monitor",
        "description": "Monitoreo de vulnerabilidades CVE en tiempo real con analisis de riesgo por IA.",
    },
    {
        "name": "module_awareness",
        "label": "Awareness (Infografias)",
        "description": "Generador de infografias de concienciacion de seguridad impulsado por IA.",
    },
]


def _flag_out(f: FeatureFlag) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "label": f.label,
        "description": f.description,
        "enabled": f.enabled,
        "organization_id": f.organization_id,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        "updated_by": f.updated_by.full_name if f.updated_by else None,
    }


def get_flags_for_org(db: Session, org_id: Optional[int]) -> dict:
    """Devuelve un dict {flag_name: enabled} para la organizacion dada.

    Prioridad: flag especifico de org > flag global (org_id=None).
    """
    global_flags = {
        f.name: f.enabled
        for f in db.query(FeatureFlag).filter(FeatureFlag.organization_id.is_(None)).all()
    }
    if org_id is None:
        return global_flags
    org_flags = {
        f.name: f.enabled
        for f in db.query(FeatureFlag).filter(FeatureFlag.organization_id == org_id).all()
    }
    return {**global_flags, **org_flags}


@router.get("/")
def list_flags(
    org_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista feature flags con logica de herencia global/org.

    - Superadmin sin org_id: devuelve flags globales.
    - Superadmin con ?org_id=X: devuelve flags efectivos para esa org,
      indicando cuales tienen override especifico.
    - Admin/analyst/viewer: devuelve flags efectivos de su propia organizacion.
    """
    global_flags_q = (
        db.query(FeatureFlag)
        .filter(FeatureFlag.organization_id.is_(None))
        .order_by(FeatureFlag.name)
        .all()
    )

    if current_user.role == UserRole.SUPERADMIN and org_id:
        effective = get_flags_for_org(db, org_id)
        org_specific = {
            f.name
            for f in db.query(FeatureFlag).filter(FeatureFlag.organization_id == org_id).all()
        }
        return [
            {
                **_flag_out(f),
                "enabled": effective.get(f.name, f.enabled),
                "org_override": f.name in org_specific,
            }
            for f in global_flags_q
        ]

    if current_user.role != UserRole.SUPERADMIN:
        # Admin/analyst/viewer ven los flags efectivos de su org
        effective = get_flags_for_org(db, current_user.organization_id)
        return [
            {**_flag_out(f), "enabled": effective.get(f.name, f.enabled)}
            for f in global_flags_q
        ]

    # Superadmin sin org_id: solo flags globales
    return [_flag_out(f) for f in global_flags_q]


class FlagUpdate(BaseModel):
    enabled: bool
    organization_id: Optional[int] = None


@router.patch("/{flag_name}")
def update_flag(
    flag_name: str,
    body: FlagUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Activa o desactiva un modulo.

    - Superadmin puede afectar el flag global (organization_id=None en body)
      o crear/actualizar el override de una org especifica.
    - Admin puede crear/actualizar el override de su propia organizacion.
    - Viewer/analyst no tienen acceso.
    """
    if current_user.role == UserRole.SUPERADMIN:
        org_id_to_update = body.organization_id  # None = global, int = org especifica
    elif current_user.role == UserRole.ADMIN:
        org_id_to_update = current_user.organization_id
    else:
        raise HTTPException(403, "Sin permisos para modificar feature flags")

    # Verificar limite de plan al activar un modulo para una org especifica
    if org_id_to_update is not None and body.enabled and current_user.role != UserRole.SUPERADMIN:
        org = db.get(Organization, org_id_to_update)
        if org:
            plan_limits = PLAN_MODULE_LIMITS.get(org.plan or "starter")
            if plan_limits is not None and flag_name not in plan_limits:
                raise HTTPException(
                    403,
                    f"El plan '{org.plan}' no incluye el modulo '{flag_name}'. "
                    "Actualiza el plan para habilitarlo.",
                )

    # Buscar flag existente para el scope solicitado
    query = db.query(FeatureFlag).filter(FeatureFlag.name == flag_name)
    if org_id_to_update is None:
        query = query.filter(FeatureFlag.organization_id.is_(None))
    else:
        query = query.filter(FeatureFlag.organization_id == org_id_to_update)
    flag = query.first()

    if not flag:
        if org_id_to_update is None:
            raise HTTPException(404, f"Feature flag '{flag_name}' no encontrado")
        # Crear override de org basado en el flag global
        global_flag = (
            db.query(FeatureFlag)
            .filter(FeatureFlag.name == flag_name, FeatureFlag.organization_id.is_(None))
            .first()
        )
        if not global_flag:
            raise HTTPException(404, f"Feature flag '{flag_name}' no encontrado")
        flag = FeatureFlag(
            name=flag_name,
            label=global_flag.label,
            description=global_flag.description,
            enabled=body.enabled,
            organization_id=org_id_to_update,
        )
        db.add(flag)
    else:
        flag.enabled = body.enabled

    flag.updated_by_id = current_user.id
    flag.updated_at = datetime.now(timezone.utc)
    log_action(db, current_user.id, "update", "feature_flag", flag_name,
               {"enabled": body.enabled, "organization_id": org_id_to_update})
    db.commit()
    db.refresh(flag)
    return _flag_out(flag)


@router.delete("/{flag_name}")
def delete_flag_override(
    flag_name: str,
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Elimina el override especifico de una organizacion para un flag.

    Solo superadmin. No se pueden eliminar flags globales (organization_id=None).
    Tras eliminar el override, la org hereda el valor global.
    """
    flag = (
        db.query(FeatureFlag)
        .filter(FeatureFlag.name == flag_name, FeatureFlag.organization_id == org_id)
        .first()
    )
    if not flag:
        raise HTTPException(
            404,
            f"No existe override del flag '{flag_name}' para la organizacion {org_id}",
        )
    db.delete(flag)
    log_action(db, current_user.id, "delete", "feature_flag", flag_name,
               {"organization_id": org_id})
    db.commit()
    return {"detail": "Override eliminado. La organizacion hereda el valor global."}


@router.get("/plans/limits")
def get_plan_limits(current_user: User = Depends(get_current_user)):
    """Devuelve los modulos incluidos en cada plan de licencia."""
    return {
        plan: sorted(list(modules)) if modules is not None else None
        for plan, modules in PLAN_MODULE_LIMITS.items()
    }


def seed_default_flags(db: Session) -> None:
    """Crea los flags globales por defecto (organization_id=None) si no existen."""
    for fd in _DEFAULT_FLAGS:
        exists = (
            db.query(FeatureFlag)
            .filter(FeatureFlag.name == fd["name"], FeatureFlag.organization_id.is_(None))
            .first()
        )
        if not exists:
            db.add(FeatureFlag(
                name=fd["name"],
                label=fd["label"],
                description=fd["description"],
                enabled=True,
                organization_id=None,
            ))
    db.commit()
