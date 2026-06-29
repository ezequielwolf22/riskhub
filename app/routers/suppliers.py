"""Gestion de proveedores / supply chain — NIS2 Art. 21.2.d."""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, Risk, RiskStatus, Supplier, SupplierRisk, Threat, User
from app.schemas import SupplierIn, SupplierOut, SupplierUpdate
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action
from app.i18n import get_lang, t as _t

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


def _next_code(db: Session, org_id: int) -> str:
    n = db.query(Supplier).filter(Supplier.organization_id == org_id).count() + 1
    return f"SUP-{n:04d}"


@router.get("/", response_model=list[SupplierOut])
def list_suppliers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    risk_level: Optional[str] = None,
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
    from app.models import SupplierQuestionnaire
    suppliers = filter_by_org(db.query(Supplier), Supplier, current_user).all()
    now = datetime.now(timezone.utc)
    overdue_assessment = sum(
        1 for s in suppliers
        if s.next_assessment_at and s.next_assessment_at.replace(tzinfo=timezone.utc) < now
    )
    critical_high = sum(1 for s in suppliers if s.risk_level in (SupplierRisk.CRITICAL, SupplierRisk.HIGH))
    scores = [s.score for s in suppliers if s.score is not None]
    avg_score = round(sum(scores) / len(scores)) if scores else None
    inactive_statuses = {"offboarding", "terminated", "inactive"}
    active_count = sum(1 for s in suppliers if getattr(s, "relationship_status", None) not in inactive_statuses)
    org_id = current_user.organization_id
    pending_q = db.query(SupplierQuestionnaire).filter(
        SupplierQuestionnaire.organization_id == org_id,
        SupplierQuestionnaire.submitted_at.is_(None),
    ).count()
    return {
        "total": len(suppliers),
        "active": active_count,
        "critical_or_high": critical_high,
        "overdue_assessment": overdue_assessment,
        "avg_score": avg_score,
        "pending_questionnaires": pending_q,
    }


@router.get("/monitoring")
def supplier_monitoring_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dashboard de monitoreo periodico: estado HTTP/SSL/DNS de todos los proveedores."""
    from app.models import ExternalFinding, ExternalFindingSource

    suppliers = filter_by_org(db.query(Supplier), Supplier, current_user).filter(
        (Supplier.website.isnot(None)) | (Supplier.contact_email.isnot(None))
    ).order_by(Supplier.name).all()

    # Ultima finding de tipo SUPPLIER_MONITOR por proveedor (open)
    latest_findings: dict[int, ExternalFinding] = {}
    org_id = current_user.organization_id
    if org_id:
        findings = db.query(ExternalFinding).filter(
            ExternalFinding.organization_id == org_id,
            ExternalFinding.source == ExternalFindingSource.SUPPLIER_MONITOR,
            ExternalFinding.supplier_id.isnot(None),
        ).order_by(ExternalFinding.detected_at.desc()).all()
        for f in findings:
            if f.supplier_id not in latest_findings:
                latest_findings[f.supplier_id] = f

    result = []
    for s in suppliers:
        f = latest_findings.get(s.id)
        result.append({
            "id": s.id,
            "code": s.code,
            "name": s.name,
            "website": s.website,
            "contact_email": s.contact_email,
            "tier": s.tier.value if s.tier else None,
            "last_monitored_at": s.last_monitored_at.isoformat() if s.last_monitored_at else None,
            "monitoring_status": s.monitoring_status or "unknown",
            "finding": {
                "id": f.id,
                "title": f.title,
                "description": f.description,
                "severity": f.severity,
                "detected_at": f.detected_at.isoformat() if f.detected_at else None,
                "status": f.status,
            } if f and f.status == "open" else None,
        })
    return result


@router.post("/{supplier_id}/rescan")
def rescan_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Lanza un escaneo manual inmediato de un proveedor."""
    supplier = filter_by_org(db.query(Supplier), Supplier, current_user).filter(
        Supplier.id == supplier_id
    ).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    domain = supplier.website or supplier.contact_email
    if not domain:
        raise HTTPException(status_code=400, detail="El proveedor no tiene website ni email configurado")

    from app.services.supplier_monitoring_service import scan_supplier
    findings = scan_supplier(db, supplier, current_user.organization_id)
    db.commit()
    return {
        "supplier_id": supplier.id,
        "last_monitored_at": supplier.last_monitored_at.isoformat() if supplier.last_monitored_at else None,
        "monitoring_status": supplier.monitoring_status,
        "findings_created": len(findings),
    }


_MAX_IMPORT_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_IMPORT_EXT = (".csv", ".xlsx", ".xls", ".ods", ".tsv", ".json")


@router.post("/import")
async def import_suppliers_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Importa proveedores desde Excel/CSV/exportaciones de otras herramientas."""
    fname = (file.filename or "").lower()
    if not fname.endswith(_ALLOWED_IMPORT_EXT):
        raise HTTPException(400, "Formato no soportado. Usa CSV, XLSX, XLS, ODS, TSV o JSON.")
    content = await file.read()
    if len(content) > _MAX_IMPORT_BYTES:
        raise HTTPException(413, "El fichero supera el limite de 10 MB.")
    if not content:
        raise HTTPException(400, "El fichero esta vacio.")
    from app.services.supplier_import_service import import_suppliers
    try:
        result = import_suppliers(content, file.filename, current_user.organization_id, db)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    log_action(db, current_user.id, "import", "supplier", "*",
               {"created": result["created"], "skipped": result["skipped"]})
    return result


from pydantic import BaseModel as _BM


class _BulkIds(_BM):
    ids: list[int]


@router.post("/bulk-delete")
def bulk_delete_suppliers(body: _BulkIds, db: Session = Depends(get_db),
                          current_user: User = Depends(require_analyst)):
    deleted = 0
    for sid in body.ids:
        s = db.query(Supplier).filter(Supplier.id == sid).first()
        if s and check_org_access(s.organization_id, current_user):
            log_action(db, current_user.id, "delete", "supplier", str(sid), {"name": s.name})
            db.delete(s)
            deleted += 1
    db.commit()
    return {"deleted": deleted}


@router.post("/bulk-recompute")
def bulk_recompute_suppliers(body: _BulkIds, db: Session = Depends(get_db),
                              current_user: User = Depends(require_analyst)):
    from app.services import tprm_scoring_service
    recomputed = 0
    for sid in body.ids:
        s = db.query(Supplier).filter(Supplier.id == sid).first()
        if s and check_org_access(s.organization_id, current_user):
            tprm_scoring_service.recompute_supplier(db, s, commit=False)
            recomputed += 1
    db.commit()
    log_action(db, current_user.id, "bulk_recompute_tprm", "supplier", "*", {"count": recomputed})
    return {"recomputed": recomputed}


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: int, request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    lang = get_lang(request)
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, _t("suppliers.not_found", lang))
    return s


@router.post("/", response_model=SupplierOut)
def create_supplier(body: SupplierIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    org_id = current_user.organization_id
    s = Supplier(
        code=_next_code(db, org_id),
        organization_id=org_id,
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
    # TPRM: aplicar atributos opcionales de riesgo inherente si vienen en el alta
    _tprm_fields = (
        "vendor_type", "relationship_status", "data_sensitivity", "data_volume",
        "system_access_type", "business_criticality", "geographic_risk",
        "is_data_processor", "processes_personal_data", "cross_border_transfers",
        "is_nis2", "is_dora", "is_ens", "country_code", "website", "tax_id", "annual_spend",
        # v4.3.0
        "cc_email", "additional_contacts", "location", "department",
        "business_importance", "internal_owner_id",
    )
    for _f in _tprm_fields:
        _v = getattr(body, _f, None)
        if _v is not None:
            setattr(s, _f, _v)
    db.add(s)
    db.commit()
    db.refresh(s)
    # TPRM: calcular inherent/residual risk y tier inicial
    try:
        from app.services import tprm_scoring_service
        tprm_scoring_service.recompute_supplier(db, s)
    except Exception as _e:
        logger.warning("TPRM recompute failed for %s: %s", s.code, _e)

    # GDPR Art.28: crear tarea de DPA si el proveedor trata datos personales
    try:
        _auto_gdpr_dpa_task(db, s, current_user.organization_id, current_user.id)
    except Exception as _e:
        logger.warning("DPA task creation failed for %s: %s", s.code, _e)

    log_action(db, current_user.id, "create", "supplier", str(s.id), {"name": s.name})
    return s


@router.patch("/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: int, body: SupplierUpdate,
                    request: Request,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, _t("suppliers.not_found", lang))
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

    # TPRM: recalcular inherent/residual risk y tier tras editar atributos
    try:
        from app.services import tprm_scoring_service
        tprm_scoring_service.recompute_supplier(db, s)
        db.refresh(s)
    except Exception as _e:
        logger.warning("TPRM recompute failed for %s: %s", s.code, _e)

    return s


from concurrent.futures import ThreadPoolExecutor as _TPE
_SUPPLIER_EXECUTOR = _TPE(max_workers=3, thread_name_prefix="supplier-score")


def _trigger_supplier_score_update(supplier_id: int, org_id: int) -> None:
    """Recalcula el score del proveedor en background.

    M6: pool compartido — evita acumular un thread por cada PATCH /suppliers/{id}.
    """
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

    _SUPPLIER_EXECUTOR.submit(_recalc)


def _auto_gdpr_dpa_task(db: Session, supplier: Supplier, org_id: int, created_by_id: int) -> None:
    """Crea tarea de firma DPA cuando el proveedor es procesador de datos (GDPR Art.28)."""
    from app.models import TreatmentTask, TaskStatus, TaskPriority
    from datetime import timedelta

    if not (getattr(supplier, "is_data_processor", False) or getattr(supplier, "processes_personal_data", False)):
        return

    # Verificar si ya hay tarea de DPA pendiente para este proveedor
    existing = db.query(TreatmentTask).filter(
        TreatmentTask.organization_id == org_id,
        TreatmentTask.description.like(f"%DPA%{supplier.id}%"),
        TreatmentTask.status.notin_([TaskStatus.DONE]),
    ).first()
    if existing:
        return

    now = datetime.now(timezone.utc)
    n = db.query(TreatmentTask).filter(TreatmentTask.organization_id == org_id).count() + 1
    code = f"TSK-{n:04d}"
    while db.query(TreatmentTask).filter_by(code=code).first():
        n += 1
        code = f"TSK-{n:04d}"

    task = TreatmentTask(
        organization_id=org_id,
        code=code,
        title=f"Firmar DPA con proveedor: {supplier.name} (GDPR Art.28)",
        description=(
            f"El proveedor {supplier.name} (ID:{supplier.id}) trata datos personales. "
            f"GDPR Art.28 obliga a formalizar un Acuerdo de Tratamiento de Datos (DPA) "
            f"antes de iniciar operaciones. "
            f"Accion: firmar DPA y registrarlo en Proveedores > Ciclo de vida > 'Registrar DPA firmado'. "
            f"Al registrar el DPA, esta tarea se cerrara automaticamente."
        ),
        priority=TaskPriority.HIGH,
        status=TaskStatus.PENDING,
        due_date=now + timedelta(days=30),
        assigned_to_id=created_by_id,
        created_at=now,
    )
    db.add(task)
    try:
        db.commit()
        logger.info("Auto-created DPA task %s for supplier %s (GDPR Art.28)", code, supplier.code)
    except Exception as _e:
        db.rollback()
        logger.warning("DPA task creation failed: %s", _e)


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

    # Calcular nivel inherente (matriz 5x5 ISO 27005 Annex E.2)
    from app.services.risk_engine import calc_level as _calc_level
    inherent_level = _calc_level(consequence, likelihood)

    # Generar codigo unico RSK-XXXX
    from sqlalchemy import func as _func
    max_id = db.query(_func.max(Risk.id)).scalar() or 0
    code = f"RSK-{max_id + 1:04d}"

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
def delete_supplier(supplier_id: int, request: Request, db: Session = Depends(get_db),
                    current_user: User = Depends(require_analyst)):
    lang = get_lang(request)
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, _t("suppliers.not_found", lang))
    log_action(db, current_user.id, "delete", "supplier", str(supplier_id), {"name": s.name})
    db.delete(s)
    db.commit()


# ---------- Trust Portal IA ----------

@router.post("/{supplier_id}/scrape-trust-portal")
def scrape_trust_portal(
    supplier_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Descarga el trust portal del proveedor, analiza con IA y vuelca los datos a la ficha."""
    lang = get_lang(request)
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, _t("suppliers.not_found", lang))

    from app.services.trust_portal_scraper import scrape_and_fill
    result = scrape_and_fill(db, s)

    if result.get("ok"):
        log_action(db, current_user.id, "scrape_trust_portal", "supplier", str(s.id), {
            "updated_fields": result.get("updated_fields", []),
        })

    return result


# ---------- Documentacion adjunta al proveedor ----------

_MAX_DOC_BYTES = 20 * 1024 * 1024  # 20 MB
_ALLOWED_DOC_EXT = (
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".txt", ".csv", ".png", ".jpg", ".jpeg", ".zip",
)


@router.get("/{supplier_id}/documents")
def list_supplier_documents(
    supplier_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lang = get_lang(request)
    from app.models import SupplierDocument
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, _t("suppliers.not_found", lang))
    docs = (
        db.query(SupplierDocument)
        .filter(SupplierDocument.supplier_id == supplier_id)
        .order_by(SupplierDocument.uploaded_at.desc())
        .all()
    )
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "size": d.size,
            "description": d.description,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            "uploaded_by": d.uploaded_by.full_name if d.uploaded_by else None,
        }
        for d in docs
    ]


@router.post("/{supplier_id}/documents")
async def upload_supplier_document(
    supplier_id: int,
    request: Request,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    from app.models import SupplierDocument
    from app.services.document_service import save_document_file
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, _t("suppliers.not_found", lang))
    fname = file.filename or "documento"
    ext = "." + fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in _ALLOWED_DOC_EXT:
        raise HTTPException(400, f"Formato no permitido. Sube: {', '.join(_ALLOWED_DOC_EXT)}")
    content = await file.read()
    if len(content) > _MAX_DOC_BYTES:
        raise HTTPException(413, "El fichero supera el limite de 20 MB.")
    stored = save_document_file(content, fname)
    doc = SupplierDocument(
        organization_id=current_user.organization_id,
        supplier_id=supplier_id,
        filename=fname,
        stored_name=stored,
        size=len(content),
        description=description,
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    log_action(db, current_user.id, "upload_document", "supplier", str(supplier_id),
               {"filename": fname})
    return {"id": doc.id, "filename": doc.filename, "size": doc.size}


@router.get("/{supplier_id}/documents/{doc_id}/download")
def download_supplier_document(
    supplier_id: int,
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lang = get_lang(request)
    from app.models import SupplierDocument
    from app.services.document_service import decrypt_doc
    from pathlib import Path
    from fastapi.responses import Response as _Resp
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, _t("suppliers.not_found", lang))
    doc = db.query(SupplierDocument).filter(
        SupplierDocument.id == doc_id,
        SupplierDocument.supplier_id == supplier_id,
    ).first()
    if not doc:
        raise HTTPException(404, _t("common.not_found", lang))
    # Buscar fichero en disco
    for base in ("/srv/data/documents", "data/documents"):
        p = Path(base) / doc.stored_name
        if p.exists():
            raw = p.read_bytes()
            content = decrypt_doc(raw)
            import mimetypes
            mt = mimetypes.guess_type(doc.filename)[0] or "application/octet-stream"
            return _Resp(content=content, media_type=mt,
                         headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'})
    raise HTTPException(404, _t("common.not_found", lang))


@router.delete("/{supplier_id}/documents/{doc_id}", status_code=204)
def delete_supplier_document(
    supplier_id: int,
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    from app.models import SupplierDocument
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, _t("suppliers.not_found", lang))
    doc = db.query(SupplierDocument).filter(
        SupplierDocument.id == doc_id,
        SupplierDocument.supplier_id == supplier_id,
    ).first()
    if not doc:
        raise HTTPException(404, _t("common.not_found", lang))
    log_action(db, current_user.id, "delete_document", "supplier", str(supplier_id),
               {"filename": doc.filename})
    db.delete(doc)
    db.commit()


@router.post("/{supplier_id}/documents/{doc_id}/analyze")
def analyze_supplier_document(
    supplier_id: int,
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Analiza un documento adjunto con IA y autocompleta los campos vacios de la ficha."""
    lang = get_lang(request)
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s or not check_org_access(s.organization_id, current_user):
        raise HTTPException(404, _t("suppliers.not_found", lang))

    from app.models import SupplierDocument
    doc = db.query(SupplierDocument).filter(
        SupplierDocument.id == doc_id,
        SupplierDocument.supplier_id == supplier_id,
    ).first()
    if not doc:
        raise HTTPException(404, _t("common.not_found", lang))

    from app.services.supplier_document_analyzer import analyze_document
    result = analyze_document(db, s, doc.stored_name, doc.filename)

    if result.get("ok"):
        log_action(db, current_user.id, "analyze_document_ai", "supplier", str(s.id), {
            "doc": doc.filename,
            "updated_fields": result.get("updated_fields", []),
        })

    return result


# ---------- Lifecycle endpoints ----------

@router.post("/{sid}/lifecycle")
async def change_lifecycle(
    sid: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Cambia el lifecycle stage de un proveedor con auditoria."""
    lang = get_lang(request)
    from app.services.supplier_lifecycle_service import generate_onboarding_checklist
    sup = db.get(Supplier, sid)
    if not sup or sup.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail=_t("suppliers.not_found", lang))

    valid_stages = {"prospecting", "onboarding", "active", "under_review", "offboarding", "terminated"}
    new_stage = payload.get("stage", "")
    if new_stage not in valid_stages:
        raise HTTPException(status_code=400, detail=f"Stage invalido. Validos: {valid_stages}")

    old_stage = sup.lifecycle_stage or "active"
    sup.lifecycle_stage = new_stage
    sup.lifecycle_changed_at = datetime.utcnow()
    sup.lifecycle_changed_by_id = current_user.id

    # Auto-generar checklist si entra en onboarding
    if new_stage == "onboarding" and not sup.onboarding_checklist:
        sup.onboarding_checklist = generate_onboarding_checklist(sup)

    db.commit()
    return {
        "supplier_id": sid,
        "old_stage": old_stage,
        "new_stage": new_stage,
        "checklist": sup.onboarding_checklist,
    }


@router.patch("/{sid}/checklist/{item_id}")
async def update_checklist_item(
    sid: int,
    item_id: str,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Marca un item del checklist como completado (bucle cerrado: 100% -> active)."""
    lang = get_lang(request)
    from app.services.supplier_lifecycle_service import recompute_supplier_risk_profile
    sup = db.get(Supplier, sid)
    if not sup or sup.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail=_t("suppliers.not_found", lang))

    checklist = sup.onboarding_checklist or []
    item = next((i for i in checklist if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail=_t("common.not_found", lang))

    item["completed"] = payload.get("completed", True)
    if item["completed"]:
        item["completed_at"] = datetime.utcnow().isoformat()
        item["completed_by_id"] = current_user.id
        if payload.get("evidence_doc_id"):
            item["evidence_doc_id"] = payload["evidence_doc_id"]
    else:
        item["completed_at"] = None
        item["completed_by_id"] = None

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(sup, "onboarding_checklist")
    db.commit()

    # Bucle cerrado: si checklist al 100% -> recompute (puede promover a active)
    result = recompute_supplier_risk_profile(db, sid, triggered_by="checklist_update")
    return {"item_id": item_id, "completed": item["completed"], "lifecycle_changes": result.get("changes", [])}


@router.patch("/{sid}/sign-off")
async def record_sign_off(
    sid: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Registra la firma de DPA, NDA o contrato (bucle cerrado: elimina gap de cumplimiento)."""
    lang = get_lang(request)
    from app.services.supplier_lifecycle_service import recompute_supplier_risk_profile
    sup = db.get(Supplier, sid)
    if not sup or sup.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail=_t("suppliers.not_found", lang))

    doc_type = payload.get("type", "")
    signed_by = payload.get("signed_by", current_user.full_name)
    doc_id = payload.get("document_id")
    now = datetime.utcnow()

    if doc_type == "dpa":
        sup.dpa_signed_at = now
        sup.dpa_signed_by = signed_by
        if doc_id:
            sup.dpa_document_id = doc_id
        # Bucle cerrado: cerrar la tarea GDPR DPA si existe
        from app.models import TreatmentTask, TaskStatus
        pending_dpa_task = db.query(TreatmentTask).filter(
            TreatmentTask.organization_id == sup.organization_id,
            TreatmentTask.description.like(f"%DPA%{sup.id}%"),
            TreatmentTask.status.notin_([TaskStatus.DONE]),
        ).first()
        if pending_dpa_task:
            pending_dpa_task.status = TaskStatus.DONE
    elif doc_type == "nda":
        sup.nda_signed_at = now
        if doc_id:
            sup.nda_document_id = doc_id
    elif doc_type == "contract":
        if doc_id:
            sup.contract_document_id = doc_id
        if payload.get("expiry"):
            from datetime import datetime as dt
            try:
                sup.contract_expiry = dt.fromisoformat(payload["expiry"])
            except ValueError:
                pass
    else:
        raise HTTPException(status_code=400, detail="type debe ser dpa|nda|contract")

    db.commit()
    result = recompute_supplier_risk_profile(db, sid, triggered_by=f"sign_off_{doc_type}")
    return {"type": doc_type, "signed_at": now.isoformat(), "lifecycle_changes": result.get("changes", [])}


@router.post("/{sid}/slas-to-kris", status_code=201)
async def slas_to_kris(
    sid: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Convierte SLAs de un contrato de proveedor en KRIs monitorizables.

    payload = {
        "slas": [
            {"name": "Uptime", "target_pct": 99.9, "direction": "higher_is_better"},
            {"name": "MTTR", "target_hours": 4, "direction": "lower_is_better"}
        ]
    }

    Para cada SLA se crea un KRI con umbrales de warning (98% del target en higher,
    120% en lower) y breach (95% / 150%) derivados automaticamente del target.
    """
    lang = get_lang(request)
    from app.models import KRI

    sup = db.get(Supplier, sid)
    if not sup or sup.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail=_t("suppliers.not_found", lang))

    slas = payload.get("slas", [])
    if not slas:
        raise HTTPException(status_code=400, detail="Proporciona al menos un SLA en 'slas'")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    created = []
    for sla in slas:
        name = sla.get("name") or "SLA sin nombre"
        direction = sla.get("direction") or "higher_is_better"
        target = (
            sla.get("target_pct")
            or sla.get("target_value")
            or sla.get("target_hours")
            or 0
        )

        if direction == "higher_is_better":
            warning_threshold = round(float(target) * 0.98, 2)
            breach_threshold = round(float(target) * 0.95, 2)
        else:
            warning_threshold = round(float(target) * 1.2, 2)
            breach_threshold = round(float(target) * 1.5, 2)

        kri = KRI(
            organization_id=current_user.organization_id,
            risk_id=None,
            name=f"SLA {sup.name}: {name}",
            metric_type="custom",
            indicator_type="kri",
            direction=direction,
            description=(
                f"SLA derivado de contrato con {sup.name}. "
                f"Objetivo: {target}. Proveedor ID: {sid}."
            ),
            warning_threshold=warning_threshold,
            breach_threshold=breach_threshold,
            is_system=False,
            is_visible=True,
            is_active=True,
            created_at=now,
        )
        db.add(kri)
        created.append({"name": kri.name, "warning": warning_threshold, "breach": breach_threshold})

    db.commit()
    log_action(
        db, current_user.id, "create", "kri_from_sla",
        str(sid), {"supplier": sup.name, "count": len(created)},
    )
    return {"created": len(created), "kris": created}


@router.patch("/{sid}/concentration-mitigation")
async def set_concentration_mitigation(
    sid: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Registra notas de mitigacion de riesgo de concentracion (bucle cerrado: puede bajar el KRI)."""
    lang = get_lang(request)
    from app.services.supplier_lifecycle_service import recompute_supplier_risk_profile
    sup = db.get(Supplier, sid)
    if not sup or sup.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail=_t("suppliers.not_found", lang))

    sup.concentration_risk_notes = payload.get("notes", sup.concentration_risk_notes)
    sup.exit_strategy = payload.get("exit_strategy", sup.exit_strategy)
    if payload.get("mitigated"):
        sup.concentration_risk_mitigated_at = datetime.utcnow()

    db.commit()
    result = recompute_supplier_risk_profile(db, sid, triggered_by="concentration_mitigation")
    return {"supplier_id": sid, "lifecycle_changes": result.get("changes", [])}


@router.get("/{sid}/audit-log")
async def get_supplier_audit_log(
    sid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Historial de cambios del proveedor desde la tabla de auditoria."""
    lang = get_lang(request)
    from app.models import AuditLog

    sup = db.get(Supplier, sid)
    if not sup or sup.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail=_t("suppliers.not_found", lang))

    logs = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "supplier",
            AuditLog.entity_id == str(sid),
        )
        .order_by(AuditLog.timestamp.desc())
        .limit(100)
        .all()
    )

    return [
        {
            "id": entry.id,
            "action": entry.action,
            "user": entry.user.email if entry.user else entry.user_id,
            "changes": entry.detail,
            "created_at": entry.timestamp.isoformat() if entry.timestamp else None,
        }
        for entry in logs
    ]
