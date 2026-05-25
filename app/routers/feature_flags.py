"""Gestion de feature flags — modulos habilitados por licencia.

Solo accesible para superadmin. Los demas usuarios pueden hacer GET
para conocer el estado de los modulos (para mostrar/ocultar la navegacion).
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FeatureFlag, User
from app.security import get_current_user, require_superadmin
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/feature-flags", tags=["feature-flags"])

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
]


def _flag_out(f: FeatureFlag) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "label": f.label,
        "description": f.description,
        "enabled": f.enabled,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        "updated_by": f.updated_by.full_name if f.updated_by else None,
    }


@router.get("/")
def list_flags(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),   # cualquier usuario autenticado puede consultar
):
    """Lista todos los feature flags — accesible a todos los usuarios autenticados."""
    flags = db.query(FeatureFlag).order_by(FeatureFlag.name).all()
    return [_flag_out(f) for f in flags]


class FlagUpdate(BaseModel):
    enabled: bool


@router.patch("/{flag_name}")
def update_flag(
    flag_name: str,
    body: FlagUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Activa o desactiva un modulo — solo superadmin."""
    flag = db.query(FeatureFlag).filter_by(name=flag_name).first()
    if not flag:
        raise HTTPException(404, f"Feature flag '{flag_name}' no encontrado")
    flag.enabled = body.enabled
    flag.updated_at = datetime.now(timezone.utc)
    flag.updated_by_id = current_user.id
    log_action(db, current_user.id, "update", "feature_flag", flag_name,
               {"enabled": body.enabled})
    db.commit()
    db.refresh(flag)
    return _flag_out(flag)


def seed_default_flags(db: Session) -> None:
    """Crea los flags por defecto si no existen (llamado desde seed.py)."""
    for fd in _DEFAULT_FLAGS:
        if not db.query(FeatureFlag).filter_by(name=fd["name"]).first():
            db.add(FeatureFlag(
                name=fd["name"],
                label=fd["label"],
                description=fd["description"],
                enabled=True,
            ))
    db.commit()
