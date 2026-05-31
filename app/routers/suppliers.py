"""Gestion de proveedores / supply chain — NIS2 Art. 21.2.d."""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, Risk, RiskStatus, Supplier, SupplierRisk, Threat, User
from app.schemas import SupplierIn, SupplierOut, SupplierUpdate
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


def _next_code(db: Session) -> str:
    n = db.query(Supplier).count() + 1
    return f"SUP-{n:04d}"


@router.get("/", response_model=list[SupplierOut])
def list_suppliers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    risk_level: Optional[SupplierRisk] = None,
    q: Optional[str] = None,
):
    query = filter_by_org(db.query(Supplier), Supplier, current_user)
    if risk_level:
        query = query.filter(Supplier.risk_level == risk_level)
    if q:
        like = f"%{q}%"
        query = query.filter(Supplier.name.ilike(like))
    return query.order_by(Supplier.name).all()


@router.get("/stats/summary")
def suppliers_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    suppliers = filter_by_org(db.query(Supplier), Supplier, current_user).all()
    now = datetime.now(timezone.utc)
    overdue_assessment = sum(
        1 for s in suppliers
        if s.next_assessment_at and s.next_assessment_at.replace(tzinfo=timezone.utc) < now
    )
    critical_high = sum(1 for s in suppliers if s.risk_level in (SupplierRisk.CRITICAL, SupplierRisk.HIGH))
    return {
        "total": len(suppliers),
        "critical_or_high": critical_high,
        "overdue_assessment": overdue_assessment,
    }


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, "Proveedor no encontrado")
    return s


@router.post("/", response_model=SupplierOut)
def create_supplier(body: SupplierIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    s = Supplier(
        code=_next_code(db),
        organization_id=current_user.organization_id,
        name=body.name,
        category=body.category,
        description=body.description,
        services=body.services,
        risk_level=body.risk_level,
        is_critical=body.is_critical,
        certifications=body.certifications,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        contract_ref=body.contract_ref,
        contract_expiry=body.contract_expiry,
        last_assessment_at=body.last_assessment_at,
        next_assessment_at=body.next_assessment_at,
        score=body.score,
        notes=body.notes,
        owner_id=body.owner_id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    log_action(db, current_user.id, "create", "supplier", str(s.id), {"name": s.name})
    return s


@router.patch("/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: int, body: SupplierUpdate,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, "Proveedor no encontrado")
    old_score = s.score
    old_risk_level = s.risk_level
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    log_action(db, current_user.id, "update", "supplier", str(s.id))

    # Auto-crear riesgo ISO 27005 cuando la puntuacion baja al umbral critico
    try:
        _auto_create_supplier_risk(db, s, old_score, old_risk_level, current_user)
    except Exception as _e:
        logger.warning("Supplier→risk auto-create failed for %s: %s", s.code, _e)

    # Recalcular score automaticamente al actualizar campos relevantes para el scoring
    _trigger_supplier_score_update(s.id, s.organization_id)

    return s


def _trigger_supplier_score_update(supplier_id: int, org_id: int) -> None:
    """Recalcula el score del proveedor en background."""
    import threading
    from app.database import SessionLocal

    def _recalc():
        db2 = SessionLocal()
        try:
            from app.services.supplier_scoring_service import calculate_supplier_score
            from app.models import Supplier as _S
            s2 = db2.get(_S, supplier_id)
            if s2 and s2.organization_id == org_id:
                new_score = calculate_supplier_score(db2, s2)
                s2.score = new_score
                db2.commit()
        except Exception:
            pass
        finally:
            db2.close()

    threading.Thread(target=_recalc, daemon=True).start()


# Umbral a partir del cual el proveedor se considera riesgo critico de cadena de suministro
_SCORE_CRITICAL_THRESHOLD = 30


def _auto_create_supplier_risk(
    db: Session,
    supplier: Supplier,
    old_score: Optional[int],
    old_risk_level,
    current_user: User,
) -> None:
    """Crea automaticamente un riesgo ISO 27005 de cadena de suministro cuando la
    puntuacion del proveedor cae por debajo de _SCORE_CRITICAL_THRESHOLD (default 30).

    Solo crea el riesgo si:
    - La puntuacion acaba de cruzar el umbral (no si ya estaba por debajo).
    - La org tiene al menos un activo registrado.
    - Existe una amenaza de tipo supply chain en el catalogo.
    - No existe ya un riesgo para el mismo par activo+amenaza.
    """
    new_score = supplier.score if supplier.score is not None else 50

    # Solo actuar si la puntuacion acaba de cruzar el umbral
    if new_score > _SCORE_CRITICAL_THRESHOLD:
        return
    if old_score is not None and old_score <= _SCORE_CRITICAL_THRESHOLD:
        return  # ya estaba en zona critica — no duplicar

    org_id = supplier.organization_id

    # Buscar activo de tipo organizacion o cualquier activo de la org
    asset = (
        db.query(Asset)
        .filter(Asset.organization_id == org_id)
        .order_by(Asset.value_confidentiality.desc(), Asset.id)
        .first()
    )
    if not asset:
        logger.info(
            "Supplier→risk: sin activos en org=%s, no se crea riesgo para %s",
            org_id, supplier.code,
        )
        return

    # Buscar amenaza de cadena de suministro en el catalogo
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
        # Fallback: amenaza de tipo organizativo / deliberado si no hay supply chain especifica
        threat = db.query(Threat).filter(Threat.category.ilike("%organiz%")).first()
    if not threat:
        logger.info(
            "Supplier→risk: sin amenaza supply-chain en catalogo, no se crea riesgo para %s",
            supplier.code,
        )
        return

    # Comprobar si ya existe un riesgo para este par activo+amenaza (UniqueConstraint)
    existing = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.asset_id == asset.id,
        Risk.threat_id == threat.id,
    ).first()
    if existing:
        logger.info(
            "Supplier→risk: riesgo %s ya existe para asset=%d threat=%d, sin duplicar.",
            existing.code, asset.id, threat.id,
        )
        return

    # Asignar nivel de riesgo inherente segun puntuacion del proveedor
    if new_score <= 10:
        likelihood, consequence = 4, 4   # riesgo muy alto
    elif new_score <= 20:
        likelihood, consequence = 4, 3
    else:
        likelihood, consequence = 3, 3   # new_score <= 30

    # Calcular nivel inherente (matriz 5x5 ISO 27005 Annex E.2 simplificada)
    inherent_level = likelihood + consequence  # max 8

    # Generar codigo unico RSK-XXXX
    count = db.query(Risk).filter(Risk.organization_id == org_id).count()
    code = f"RSK-{count + 1:04d}"
    while db.query(Risk).filter_by(code=code).first():
        count += 1
        code = f"RSK-{count + 1:04d}"

    risk = Risk(
        organization_id=org_id,
        code=code,
        asset_id=asset.id,
        threat_id=threat.id,
        description=(
            f"Riesgo de cadena de suministro detectado automaticamente.\n"
            f"Proveedor: {supplier.name} ({supplier.code}) — Puntuacion: {new_score}/100.\n"
            f"El proveedor ha bajado del umbral critico ({_SCORE_CRITICAL_THRESHOLD}). "
            f"Revisar los servicios prestados y el impacto en los activos de la organizacion."
        ),
        inherent_likelihood=likelihood,
        inherent_consequence=consequence,
        inherent_level=inherent_level,
        residual_likelihood=likelihood,
        residual_consequence=consequence,
        residual_level=inherent_level,
        status=RiskStatus.IDENTIFIED,
        owner_id=supplier.owner_id or current_user.id,
        ai_generated=True,
        ai_rationale=(
            f"Creado automaticamente: proveedor {supplier.code} bajo umbral "
            f"(score={new_score}, threshold={_SCORE_CRITICAL_THRESHOLD})."
        ),
    )
    db.add(risk)
    db.commit()
    logger.info(
        "Auto-created supply-chain risk %s (level=%d) for supplier %s (score=%d)",
        code, inherent_level, supplier.code, new_score,
    )


@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, "Proveedor no encontrado")
    log_action(db, current_user.id, "delete", "supplier", str(supplier_id), {"name": s.name})
    db.delete(s)
    db.commit()
