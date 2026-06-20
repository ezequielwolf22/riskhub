"""Auditoria interna — ISO 27001 cl. 9.2."""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditFinding, AuditProgram, AuditStatus, AuditChecklist, User
from app.schemas import (
    AuditFindingIn, AuditFindingOut,
    AuditProgramIn, AuditProgramOut, AuditProgramUpdate,
)
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action

logger = logging.getLogger("riskhub.audits")

router = APIRouter(prefix="/api/audits", tags=["audits"])


def _next_code(db: Session, org_id: int) -> str:
    n = db.query(AuditProgram).filter(AuditProgram.organization_id == org_id).count() + 1
    return f"AUD-{n:04d}"


@router.get("/", response_model=list[AuditProgramOut])
def list_audits(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: Optional[AuditStatus] = None,
):
    q = filter_by_org(db.query(AuditProgram), AuditProgram, current_user)
    if status:
        q = q.filter(AuditProgram.status == status)
    return q.order_by(AuditProgram.planned_start.desc()).all()


@router.get("/stats/summary")
def audits_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    audits = filter_by_org(db.query(AuditProgram), AuditProgram, current_user).all()
    audit_ids = [a.id for a in audits]
    findings = db.query(AuditFinding).filter(AuditFinding.audit_id.in_(audit_ids)).all() if audit_ids else []
    from app.models import AuditFindingType
    open_major = sum(
        1 for f in findings
        if f.finding_type == AuditFindingType.MAJOR_NC and not f.nonconformity_id
    )
    return {
        "total_programs": len(audits),
        "total_findings": len(findings),
        "open_major_ncs": open_major,
        "by_status": {s.value: sum(1 for a in audits if a.status == s) for s in AuditStatus},
    }


@router.get("/{audit_id}", response_model=AuditProgramOut)
def get_audit(audit_id: int, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    a = db.query(AuditProgram).filter(AuditProgram.id == audit_id).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Auditoria no encontrada")
    return a


@router.post("/", response_model=AuditProgramOut)
def create_audit(body: AuditProgramIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_analyst)):
    org_id = current_user.organization_id
    a = AuditProgram(
        code=_next_code(db, org_id),
        organization_id=org_id,
        title=body.title,
        audit_type=body.audit_type,
        scope=body.scope,
        objectives=body.objectives,
        criteria=body.criteria,
        auditor_lead=body.auditor_lead,
        auditor_team=body.auditor_team,
        planned_start=body.planned_start,
        planned_end=body.planned_end,
        owner_id=body.owner_id or current_user.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    log_action(db, current_user.id, "create", "audit", str(a.id), {"code": a.code})
    return a


@router.patch("/{audit_id}", response_model=AuditProgramOut)
def update_audit(audit_id: int, body: AuditProgramUpdate,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(require_analyst)):
    a = db.query(AuditProgram).filter(AuditProgram.id == audit_id).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Auditoria no encontrada")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(a, field, value)
    db.commit()
    db.refresh(a)
    log_action(db, current_user.id, "update", "audit", str(a.id))
    return a


@router.delete("/{audit_id}", status_code=204)
def delete_audit(audit_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(require_analyst)):
    a = db.query(AuditProgram).filter(AuditProgram.id == audit_id).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Auditoria no encontrada")
    log_action(db, current_user.id, "delete", "audit", str(audit_id))
    db.delete(a)
    db.commit()


# -- Findings sub-resource --

@router.get("/{audit_id}/findings", response_model=list[AuditFindingOut])
def list_findings(audit_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    a = db.query(AuditProgram).filter(AuditProgram.id == audit_id).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Auditoria no encontrada")
    return db.query(AuditFinding).filter(AuditFinding.audit_id == audit_id).all()


@router.post("/{audit_id}/findings", response_model=AuditFindingOut)
def create_finding(audit_id: int, body: AuditFindingIn,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(require_analyst)):
    a = db.query(AuditProgram).filter(AuditProgram.id == audit_id).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Auditoria no encontrada")
    f = AuditFinding(
        audit_id=audit_id,
        finding_type=body.finding_type,
        title=body.title,
        description=body.description,
        evidence=body.evidence,
        iso_clause=body.iso_clause,
        recommendation=body.recommendation,
        nonconformity_id=body.nonconformity_id,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    log_action(db, current_user.id, "create", "audit_finding", str(f.id))
    return f


@router.patch("/{audit_id}/findings/{finding_id}", response_model=AuditFindingOut)
def update_finding(audit_id: int, finding_id: int, body: AuditFindingIn,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(require_analyst)):
    audit = filter_by_org(db.query(AuditProgram).filter(AuditProgram.id == audit_id), AuditProgram, current_user).first()
    if not audit:
        raise HTTPException(404, "Auditoria no encontrada")
    f = db.query(AuditFinding).filter(
        AuditFinding.id == finding_id, AuditFinding.audit_id == audit_id
    ).first()
    if not f:
        raise HTTPException(404, "Hallazgo no encontrado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(f, field, value)
    db.commit()
    db.refresh(f)
    return f


@router.delete("/{audit_id}/findings/{finding_id}", status_code=204)
def delete_finding(audit_id: int, finding_id: int,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(require_analyst)):
    audit = filter_by_org(db.query(AuditProgram).filter(AuditProgram.id == audit_id), AuditProgram, current_user).first()
    if not audit:
        raise HTTPException(404, "Auditoria no encontrada")
    f = db.query(AuditFinding).filter(
        AuditFinding.id == finding_id, AuditFinding.audit_id == audit_id
    ).first()
    if not f:
        raise HTTPException(404, "Hallazgo no encontrado")
    db.delete(f)
    db.commit()


# ── Checklist sub-resource (ISO 27001 cl. 9.2 + AI) ─────────────────────────

class ChecklistItemResponse(BaseModel):
    response: str   # pending|conformant|minor_nc|major_nc|na
    auditor_notes: Optional[str] = None
    evidence_ref: Optional[str] = None


def _checklist_to_dict(item: AuditChecklist) -> dict:
    return {
        "id": item.id,
        "audit_id": item.audit_id,
        "control_id": item.control_id,
        "iso_clause": item.iso_clause,
        "question": item.question,
        "expected_evidence": item.expected_evidence,
        "response": item.response,
        "evidence_ref": item.evidence_ref,
        "auditor_notes": item.auditor_notes,
        "nc_created_id": item.nc_created_id,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.post("/{audit_id}/start")
def start_audit(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Cambia estado a IN_PROGRESS y genera checklist automatico desde SoA con IA."""
    a = db.query(AuditProgram).filter(AuditProgram.id == audit_id).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Auditoria no encontrada")

    a.status = AuditStatus.IN_PROGRESS
    a.actual_start = datetime.now(timezone.utc)
    db.commit()

    from app.services.audit_checklist_service import generate_checklist_from_soa
    org_id = current_user.organization_id
    items_created = generate_checklist_from_soa(db, audit_id, org_id)

    # Marcar timestamp de generacion en el programa
    a.checklist_generated_at = datetime.now(timezone.utc)  # type: ignore[attr-defined]
    db.commit()

    log_action(db, current_user.id, "start", "audit", str(audit_id),
               {"checklist_items": items_created})
    return {"status": "in_progress", "checklist_items_created": items_created}


@router.get("/{audit_id}/checklist")
def list_checklist(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista todos los items del checklist de una auditoria."""
    a = db.query(AuditProgram).filter(AuditProgram.id == audit_id).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Auditoria no encontrada")

    items = (
        db.query(AuditChecklist)
        .filter_by(audit_id=audit_id, organization_id=current_user.organization_id)
        .order_by(AuditChecklist.iso_clause, AuditChecklist.id)
        .all()
    )
    counts = {"pending": 0, "conformant": 0, "minor_nc": 0, "major_nc": 0, "na": 0}
    for item in items:
        counts[item.response] = counts.get(item.response, 0) + 1

    total = len(items)
    done = total - counts.get("pending", 0)
    return {
        "audit_id": audit_id,
        "total": total,
        "done": done,
        "progress_pct": round(done / max(1, total) * 100, 1),
        "counts": counts,
        "items": [_checklist_to_dict(i) for i in items],
    }


@router.patch("/{audit_id}/checklist/{item_id}")
def respond_checklist_item(
    audit_id: int,
    item_id: int,
    body: ChecklistItemResponse,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Responde un item del checklist. Si es NC → crea NonConformity automaticamente."""
    a = db.query(AuditProgram).filter(AuditProgram.id == audit_id).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Auditoria no encontrada")

    valid_responses = ("pending", "conformant", "minor_nc", "major_nc", "na")
    if body.response not in valid_responses:
        raise HTTPException(422, f"response invalido. Validos: {valid_responses}")

    item = db.query(AuditChecklist).filter_by(
        id=item_id, audit_id=audit_id
    ).first()
    if not item:
        raise HTTPException(404, "Item de checklist no encontrado")

    item.response = body.response
    if body.auditor_notes is not None:
        item.auditor_notes = body.auditor_notes
    if body.evidence_ref is not None:
        item.evidence_ref = body.evidence_ref

    # Auto-crear NonConformity si el item es NC y no tiene una creada ya
    if body.response in ("minor_nc", "major_nc") and not item.nc_created_id:
        from app.models import NonConformity, NCSeverity, NCStatus
        org_id = current_user.organization_id

        # Generar codigo NC
        nc_count = db.query(NonConformity).filter_by(organization_id=org_id).count()
        nc_code = f"NC-{nc_count + 1:04d}"
        severity = NCSeverity.MINOR if body.response == "minor_nc" else NCSeverity.MAJOR

        nc = NonConformity(
            organization_id=org_id,
            code=nc_code,
            title=f"NC de auditoria: {(item.question or '')[:100]}",
            description=body.auditor_notes or "",
            source="internal_audit",
            severity=severity,
            status=NCStatus.OPEN,
            iso_clause=item.iso_clause,
            related_control_id=item.control_id,
            owner_id=current_user.id,
        )
        db.add(nc)
        db.flush()
        item.nc_created_id = nc.id
        logger.info(
            "NC auto-creada %s desde checklist item %d (audit %d)",
            nc_code, item_id, audit_id,
        )

    # Si el item es conforme y tiene clausula ISO → actualizar compliance a AUDITED
    if body.response == "conformant" and item.iso_clause:
        from app.models import ComplianceFrameworkStatus, ComplianceRequirementStatus
        org_id = current_user.organization_id
        stmt = db.query(ComplianceFrameworkStatus).filter(
            ComplianceFrameworkStatus.organization_id == org_id,
            ComplianceFrameworkStatus.requirement_id == item.iso_clause,
            ComplianceFrameworkStatus.status.in_([
                ComplianceRequirementStatus.PLANNED,
                ComplianceRequirementStatus.PARTIAL,
            ])
        ).first()
        if stmt:
            stmt.status = ComplianceRequirementStatus.AUDITED
            stmt.last_reviewed_at = datetime.now(timezone.utc)

    db.commit()
    return _checklist_to_dict(item)


@router.post("/{audit_id}/close-report")
def close_audit_report(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Cierra la auditoria y genera el informe PDF."""
    a = db.query(AuditProgram).filter(AuditProgram.id == audit_id).first()
    if not a or not check_org_access(a.organization_id, current_user):
        raise HTTPException(404, "Auditoria no encontrada")

    a.status = AuditStatus.COMPLETED
    a.actual_end = datetime.now(timezone.utc)
    db.commit()
    log_action(db, current_user.id, "close", "audit", str(audit_id), {})

    items = db.query(AuditChecklist).filter_by(
        audit_id=audit_id, organization_id=current_user.organization_id
    ).all()

    from app.services.audit_checklist_service import generate_audit_report_pdf
    pdf_bytes = generate_audit_report_pdf(a, items)
    if not pdf_bytes:
        return {"status": "completed", "pdf": False}

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="informe_{a.code}.pdf"'},
    )


@router.post("/{audit_id}/analyze-report")
async def analyze_audit_report(
    audit_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Analiza un informe de auditoria con IA para extraer NC, observaciones y oportunidades."""
    import json

    audit = db.get(AuditProgram, audit_id)
    if not audit or audit.organization_id != current_user.organization_id:
        raise HTTPException(404, "Auditoria no encontrada")

    # Leer el archivo en chunks para no saturar memoria (max 5MB)
    MAX_SIZE = 5 * 1024 * 1024
    chunks = []
    total = 0
    while True:
        chunk = await file.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_SIZE:
            raise HTTPException(400, "Archivo demasiado grande (max 5MB)")
        chunks.append(chunk)
    content = b"".join(chunks)

    # Extraer texto del archivo
    text_content = ""
    filename_lower = file.filename.lower() if file.filename else ""

    if filename_lower.endswith('.pdf'):
        try:
            import io
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            text_content = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            raise HTTPException(400, "No se pudo leer el PDF. Asegurate de que el archivo no esta corrupto o protegido.")
    elif filename_lower.endswith('.docx'):
        try:
            import io
            import docx
            doc = docx.Document(io.BytesIO(content))
            text_content = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception:
            raise HTTPException(400, "No se pudo leer el DOCX. Asegurate de que el archivo no esta corrupto.")
    else:
        text_content = content.decode('utf-8', errors='ignore')

    if len(text_content.strip()) < 50:
        raise HTTPException(400, "No se pudo extraer texto del archivo")

    # Truncar a 15000 chars para el prompt
    text_excerpt = text_content[:15000]

    # Obtener API key usando el mismo patron que iso_clause_extractor
    from app.services.iso_clause_extractor import _resolve_ai_config
    api_key, model = _resolve_ai_config(db, current_user.organization_id)

    if not api_key:
        raise HTTPException(400, "API key de IA no configurada. Configura el Agente IA primero.")

    prompt = f"""Eres un auditor ISO 27001 experto. Analiza el siguiente informe de auditoria (puede estar en cualquier idioma) y extrae TODOS los hallazgos identificados.

Clasifica cada hallazgo en:
- major_nc: No conformidad mayor (incumplimiento grave de un requisito)
- minor_nc: No conformidad menor (incumplimiento parcial o puntual)
- observation: Observacion (area de atencion que no constituye NC)
- opportunity: Oportunidad de mejora
- conformity: Punto conforme destacado

Responde SIEMPRE en castellano (espanol), independientemente del idioma del informe.

INFORME:
{text_excerpt}

Devuelve EXCLUSIVAMENTE un objeto JSON con esta estructura:
{{
  "summary": "Resumen ejecutivo del informe en 2-3 oraciones en castellano",
  "audit_scope": "Alcance del sistema auditado",
  "findings": [
    {{
      "type": "major_nc",
      "title": "Titulo conciso del hallazgo",
      "description": "Descripcion detallada de lo encontrado",
      "iso_clause": "Clausula ISO 27001 o 27002 relacionada, ej: 9.2 o A.12.6.1, o null si no aplica",
      "recommendation": "Accion correctiva o de mejora recomendada",
      "priority": "high",
      "estimated_days": 30
    }}
  ],
  "total_major_nc": 0,
  "total_minor_nc": 0,
  "total_observations": 0,
  "total_opportunities": 0
}}

Extrae TODOS los hallazgos del informe. Si no hay hallazgos de un tipo, usa array vacio. Solo JSON, sin texto adicional, sin markdown."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=32000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        # Extraer JSON si viene con markdown
        if '```' in raw:
            parts = raw.split('```')
            if len(parts) >= 2:
                raw = parts[1]
                if raw.startswith('json'):
                    raw = raw[4:]
        result = json.loads(raw.strip())
    except json.JSONDecodeError:
        raise HTTPException(500, "El modelo devolvio una respuesta con formato incorrecto. Intenta de nuevo.")
    except Exception:
        logger.exception("Error en analyze_audit_report org=%s audit=%s", current_user.organization_id, audit_id)
        raise HTTPException(500, "Error al procesar el informe con IA. Intenta de nuevo.")

    return result
