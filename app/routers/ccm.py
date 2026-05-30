"""Router de Continuous Control Monitoring."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import get_current_user, require_role
from app.services.ccm_service import run_all_tests, run_test_by_id, get_test_catalog

router = APIRouter(prefix="/api/ccm", tags=["ccm"])


@router.get("/catalog")
def list_tests(current_user: User = Depends(get_current_user)):
    """Lista todos los tests CCM disponibles."""
    return get_test_catalog()


@router.post("/run")
def run_ccm(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ejecuta todos los tests CCM y retorna resultados + score."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    return run_all_tests(db, org_id)


@router.post("/run/{test_id}")
def run_single_test(
    test_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ejecuta un test CCM específico."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")
    result = run_test_by_id(db, org_id, test_id)
    if result is None:
        raise HTTPException(404, f"Test '{test_id}' no encontrado")
    return result
