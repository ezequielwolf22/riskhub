"""Router de Continuous Control Monitoring."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import User
from app.security import get_current_user, require_analyst, require_role
from app.services.ccm_service import run_all_tests, run_test_by_id, get_test_catalog

router = APIRouter(prefix="/api/ccm", tags=["ccm"])


@router.get("/catalog")
def list_tests(request: Request, current_user: User = Depends(get_current_user)):
    """Lista todos los tests CCM disponibles."""
    return get_test_catalog(get_lang(request))


@router.post("/run")
def run_ccm(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),  # A3: VIEWER no debe ver brecha de seguridad
):
    """Ejecuta todos los tests CCM y retorna resultados + score con paginacion."""
    lang = get_lang(request)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, _t("compliance.org_required", lang))
    return run_all_tests(db, org_id, limit=limit, offset=offset, lang=lang)


@router.post("/run/{test_id}")
def run_single_test(
    test_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),  # A3: idem
):
    """Ejecuta un test CCM específico."""
    lang = get_lang(request)
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, _t("compliance.org_required", lang))
    result = run_test_by_id(db, org_id, test_id, lang=lang)
    if result is None:
        raise HTTPException(404, _t("ccm.test_not_found", lang, test_id=test_id))
    return result
