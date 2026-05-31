"""CRUD de riesgos + calculo automatico inherente/residual + tratamiento."""
import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Asset, ControlImplementation, Risk, RiskContext, RiskStatus,
    Threat, TreatmentOption, User, Vulnerability, risk_control_table,
)
from app.schemas import RiskIn, RiskOut, RiskUpdate
from app.security import check_org_access, filter_by_org, get_current_user, require_analyst
from app.services.audit_service import log_action
from app.services.risk_engine import (
    calc_level, calc_residual,
    calc_consequence_magerit, primary_dimension_for_threat, MAGERIT_DIM_FIELD,
)

router = APIRouter(prefix="/api/risks", tags=["risks"])


def _next_code(db: Session) -> str:
    n = db.query(Risk).count() + 1
    return f"RSK-{n:04d}"


def _get_context(db: Session, org_id=None) -> RiskContext | None:
    q = db.query(RiskContext)
    if org_id:
        q = q.filter(RiskContext.organization_id == org_id)
    return q.first()


def _get_matrix(db: Session, org_id=None):
    ctx = _get_context(db, org_id)
    return ctx.risk_matrix if ctx and ctx.risk_matrix else None


def _apply_magerit_consequence(risk: Risk, db: Session) -> None:
    """Si la metodologia del contexto es magerit|combined y el riesgo tiene
    dimension + degradacion, recalcula inherent_consequence desde el activo."""
    if not risk.asset_id:
        return
    ctx = _get_context(db, risk.organization_id)
    if not ctx or ctx.methodology not in ("magerit", "combined"):
        return
    if risk.degradation_pct is None:
        return

    asset = db.get(Asset, risk.asset_id)
    if not asset:
        return

    # Determinar dimension primaria si no esta guardada
    if not risk.magerit_dimension:
        threat = db.get(Threat, risk.threat_id)
        affects = getattr(threat, "affects", None) or []
        risk.magerit_dimension = primary_dimension_for_threat(affects, asset)

    # Calcular consecuencia MAGERIT
    field = MAGERIT_DIM_FIELD.get(risk.magerit_dimension, "value_availability")
    dim_value = getattr(asset, field, 0) or 0
    consequence, magerit_impact = calc_consequence_magerit(dim_value, risk.degradation_pct)
    risk.inherent_consequence = consequence
    risk.magerit_impact = magerit_impact


def _recalc(db: Session, risk: Risk) -> None:
    matrix = _get_matrix(db, risk.organization_id)

    # MAGERIT: si aplica, sobrescribir inherent_consequence antes de calcular
    _apply_magerit_consequence(risk, db)

    risk.inherent_level = calc_level(
        risk.inherent_consequence, risk.inherent_likelihood, matrix)
    controls = [{"maturity": ci.maturity, "contribution": 1.0} for ci in risk.controls]
    rl, rc, rlev = calc_residual(
        risk.inherent_likelihood, risk.inherent_consequence, controls, matrix)
    risk.residual_likelihood = rl
    risk.residual_consequence = rc
    risk.residual_level = rlev

    # Auto-tratamiento basado en apetito de riesgo
    ctx = _get_context(db, risk.organization_id)
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3
    if rlev <= appetite and risk.status not in (RiskStatus.CLOSED,):
        if risk.treatment_option in (None, TreatmentOption.MODIFICATION, TreatmentOption.RETENTION):
            risk.treatment_option = TreatmentOption.ACCEPTANCE
            if risk.status in (RiskStatus.IDENTIFIED, RiskStatus.ASSESSED):
                risk.status = RiskStatus.ACCEPTED
                # Riesgos aceptados deben revisarse anualmente
                if not risk.next_review:
                    from datetime import timedelta
                    risk.next_review = datetime.now(timezone.utc) + timedelta(days=365)


@router.get("/", response_model=list[RiskOut])
def list_risks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    asset_id: Optional[int] = None,
    threat_id: Optional[int] = None,
    vulnerability_id: Optional[int] = None,
    status: Optional[RiskStatus] = None,
    min_level: Optional[int] = Query(None, ge=0, le=8),
    overdue: Optional[bool] = None,
    owner_id: Optional[int] = None,
    treatment: Optional[str] = None,
):
    now = datetime.now(timezone.utc)
    q = filter_by_org(db.query(Risk), Risk, current_user)
    if asset_id:
        q = q.filter(Risk.asset_id == asset_id)
    if threat_id:
        q = q.filter(Risk.threat_id == threat_id)
    if vulnerability_id:
        from app.models import risk_vulnerability_table
        vuln_risk_ids = db.query(risk_vulnerability_table.c.risk_id).filter(
            risk_vulnerability_table.c.vulnerability_id == vulnerability_id
        ).subquery()
        q = q.filter(Risk.id.in_(vuln_risk_ids))
    if status:
        q = q.filter(Risk.status == status)
    if min_level is not None:
        q = q.filter(Risk.residual_level >= min_level)
    if overdue:
        active = [RiskStatus.IDENTIFIED, RiskStatus.ASSESSED]
        q = q.filter(
            Risk.status.in_(active),
            Risk.treatment_due_date.isnot(None),
            Risk.treatment_due_date < now,
        )
    if owner_id is not None:
        q = q.filter(Risk.owner_id == owner_id)
    if treatment:
        if treatment == "__none__":
            q = q.filter(Risk.treatment_option.is_(None))
        else:
            q = q.filter(Risk.treatment_option == treatment)
    return q.order_by(Risk.residual_level.desc(), Risk.code).all()


@router.get("/{risk_id}", response_model=RiskOut)
def get_risk(risk_id: int, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    r = db.get(Risk, risk_id)
    if not r or not check_org_access(r.organization_id, current_user):
        raise HTTPException(404, "Riesgo no encontrado")
    return r


@router.post("/", response_model=RiskOut, status_code=201)
def create_risk(data: RiskIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    asset = db.get(Asset, data.asset_id)
    if not asset or not check_org_access(asset.organization_id, current_user):
        raise HTTPException(400, "asset_id no existe")
    if not db.get(Threat, data.threat_id):
        raise HTTPException(400, "threat_id no existe")
    # Deteccion de duplicado: mismo asset + amenaza en la org (v1.7.7)
    if hasattr(data, 'asset_id') and hasattr(data, 'threat_id') and data.asset_id and data.threat_id:
        from app.models import Risk as _Risk
        existing_dup = db.query(_Risk).filter(
            _Risk.asset_id == data.asset_id,
            _Risk.threat_id == data.threat_id,
            _Risk.organization_id == current_user.organization_id,
        ).first()
        if existing_dup:
            raise HTTPException(
                409,
                f"Ya existe el riesgo {existing_dup.code} para este activo y amenaza. "
                f"Edita el riesgo existente en lugar de crear uno nuevo."
            )

    r = Risk(
        code=_next_code(db),
        organization_id=current_user.organization_id,
        asset_id=data.asset_id, threat_id=data.threat_id,
        description=data.description,
        consequence_description=data.consequence_description,
        inherent_likelihood=data.inherent_likelihood,
        inherent_consequence=data.inherent_consequence,
        owner_id=data.owner_id,
        treatment_option=data.treatment_option,
        treatment_plan=data.treatment_plan,
        treatment_due_date=data.treatment_due_date,
        status=RiskStatus.ASSESSED,
        # MAGERIT v3 (si se proporcionan)
        magerit_dimension=data.magerit_dimension,
        degradation_pct=data.degradation_pct,
    )
    if data.vulnerability_ids:
        r.vulnerabilities = db.query(Vulnerability).filter(
            Vulnerability.id.in_(data.vulnerability_ids)).all()
    if data.control_implementation_ids:
        r.controls = db.query(ControlImplementation).filter(
            ControlImplementation.id.in_(data.control_implementation_ids)).all()
    _recalc(db, r)
    db.add(r)
    log_action(db, current_user.id, "create", "risk", None,
               {"asset_id": data.asset_id, "threat_id": data.threat_id})
    db.commit(); db.refresh(r)

    # Disparar alerta inmediata si el riesgo es CRITICO o ALTO (no esperar al scheduler)
    if (r.residual_level or 0) >= 5:
        import threading
        from app.database import SessionLocal as _SL

        def _fire_alert(risk_id=r.id, org_id=r.organization_id):
            db2 = _SL()
            try:
                from app.services import email_service
                from app.models import AlertRule, Risk as _R, RiskContext as _RC
                cfg = email_service.get_settings(db2)
                if not cfg or not cfg.smtp_host:
                    return
                risk_obj = db2.get(_R, risk_id)
                if not risk_obj:
                    return
                ctx = db2.query(_RC).filter(_RC.organization_id == org_id).first()
                org_name = ctx.organization_name if ctx else "Organizacion"
                rules = db2.query(AlertRule).filter(
                    AlertRule.is_active.is_(True),
                    AlertRule.organization_id == org_id,
                    AlertRule.event_type.in_(["risk_critical", "risk_high"]),
                ).all()
                for rule in rules:
                    if risk_obj.residual_level >= rule.threshold_level:
                        body = f"Se ha creado el riesgo {risk_obj.code} con nivel residual {risk_obj.residual_level}/8."
                        email_service.send_email(
                            cfg, rule.recipient_email,
                            f"RiskHub [NUEVO] — Riesgo {risk_obj.code} requiere atencion ({org_name})",
                            email_service.risk_alert_html(risk_obj, org_name, body),
                        )
            except Exception:
                pass
            finally:
                db2.close()

        threading.Thread(target=_fire_alert, daemon=True).start()

    return r


@router.patch("/{risk_id}", response_model=RiskOut)
def update_risk(risk_id: int, data: RiskUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_analyst)):
    r = db.get(Risk, risk_id)
    if not r or not check_org_access(r.organization_id, user):
        raise HTTPException(404, "Riesgo no encontrado")

    update_data = data.model_dump(exclude_unset=True)
    if "vulnerability_ids" in update_data:
        ids = update_data.pop("vulnerability_ids")
        r.vulnerabilities = db.query(Vulnerability).filter(
            Vulnerability.id.in_(ids or [])).all()
    if "control_implementation_ids" in update_data:
        ids = update_data.pop("control_implementation_ids")
        r.controls = db.query(ControlImplementation).filter(
            ControlImplementation.id.in_(ids or [])).all()

    # Acceptance bookkeeping
    if update_data.get("status") == RiskStatus.ACCEPTED:
        r.accepted_by_id = user.id
        r.accepted_at = datetime.now(timezone.utc)

    for k, v in update_data.items():
        setattr(r, k, v)
    _recalc(db, r)
    log_action(db, user.id, "update", "risk", str(risk_id),
               {"code": r.code, "status": str(r.status), "residual_level": r.residual_level})
    db.commit(); db.refresh(r)
    return r


@router.get("/methodology")
def get_methodology(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve la metodologia activa y sus metadatos (para el formulario de riesgos)."""
    from app.services.risk_engine import MAGERIT_DIMENSIONS, MAGERIT_FREQ_LABELS
    ctx = _get_context(db, current_user.organization_id)
    methodology = ctx.methodology if ctx and ctx.methodology else "iso27005"
    return {
        "methodology": methodology,
        "magerit_dimensions": MAGERIT_DIMENSIONS,
        "magerit_freq_labels": MAGERIT_FREQ_LABELS,
        "risk_appetite": ctx.risk_appetite if ctx else 3,
    }


@router.post("/magerit-preview")
def magerit_consequence_preview(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Calcula en tiempo real la consecuencia MAGERIT para un activo + dimension + degradacion.

    Body: {asset_id, dimension, degradation_pct}
    Respuesta: {consequence, magerit_impact, dim_value, label}
    """
    from app.services.risk_engine import calc_consequence_magerit, MAGERIT_DIM_FIELD, CONSEQUENCE_LABELS
    asset_id = body.get("asset_id")
    dimension = body.get("dimension", "D")
    degrad = int(body.get("degradation_pct", 50))

    asset = db.get(Asset, asset_id) if asset_id else None
    if not asset or not check_org_access(asset.organization_id, current_user):
        return {"consequence": 0, "magerit_impact": 0.0, "dim_value": 0, "label": "-"}

    field = MAGERIT_DIM_FIELD.get(dimension, "value_availability")
    dim_value = getattr(asset, field, 0) or 0
    consequence, impact = calc_consequence_magerit(dim_value, degrad)
    return {
        "consequence": consequence,
        "magerit_impact": impact,
        "dim_value": dim_value,
        "label": CONSEQUENCE_LABELS[consequence] if 0 <= consequence < len(CONSEQUENCE_LABELS) else "-",
        "asset_dims": {
            "D": asset.value_availability or 0,
            "I": asset.value_integrity or 0,
            "C": asset.value_confidentiality or 0,
            "A": asset.value_authenticity or 0,
            "T": asset.value_accountability or 0,
        },
    }


@router.delete("/{risk_id}", status_code=204)
def delete_risk(risk_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    r = db.get(Risk, risk_id)
    if not r or not check_org_access(r.organization_id, current_user):
        raise HTTPException(404, "Riesgo no encontrado")
    code = r.code
    db.delete(r)
    log_action(db, current_user.id, "delete", "risk", str(risk_id), {"code": code})
    db.commit()


@router.get("/export/csv")
def export_risks_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exporta todos los riesgos como CSV."""
    risks = filter_by_org(db.query(Risk), Risk, current_user).order_by(
        Risk.residual_level.desc(), Risk.code
    ).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Codigo", "Activo", "Amenaza", "Descripcion",
        "Nivel_Inherente", "Prob_Inherente", "Cons_Inherente",
        "Nivel_Residual", "Prob_Residual", "Cons_Residual",
        "Estado", "Tratamiento", "Plan_Tratamiento",
        "Fecha_Vencimiento", "Creado",
    ])
    for r in risks:
        writer.writerow([
            r.code,
            r.asset.name if r.asset else "",
            r.threat.name if r.threat else "",
            r.description or "",
            r.inherent_level, r.inherent_likelihood, r.inherent_consequence,
            r.residual_level, r.residual_likelihood, r.residual_consequence,
            r.status.value if r.status else "",
            r.treatment_option.value if r.treatment_option else "",
            r.treatment_plan or "",
            r.treatment_due_date.strftime("%Y-%m-%d") if r.treatment_due_date else "",
            r.created_at.strftime("%Y-%m-%d") if r.created_at else "",
        ])
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    fname = f"riesgos_{ts}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/import/template")
def risks_import_template(_: User = Depends(get_current_user)):
    """Devuelve una plantilla CSV para importacion masiva de riesgos."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Activo_Codigo", "Amenaza_Codigo", "Descripcion",
        "Prob_Inherente", "Cons_Inherente",
        "Prob_Residual", "Cons_Residual",
        "Estado", "Tratamiento", "Plan_Tratamiento",
        "Fecha_Vencimiento",
    ])
    writer.writerow([
        "AST-0001", "T-CYB-01", "Acceso no autorizado al servidor de produccion",
        "3", "3", "1", "2",
        "identified", "modification", "Implantar MFA y revisar politica de acceso",
        "2025-12-31",
    ])
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="risks_template.csv"'},
    )


@router.post("/import")
async def import_risks_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Importa riesgos desde un CSV. Busca activo por codigo y amenaza por codigo."""
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # soporta BOM de Excel
        reader = csv.DictReader(io.StringIO(text))
    except Exception as exc:
        raise HTTPException(400, f"Error al leer el CSV: {exc}") from exc

    # Cache de activos y amenazas para lookups rapidos (filtrados por org)
    org_assets = filter_by_org(db.query(Asset), Asset, current_user).all()
    assets_by_code = {a.code: a for a in org_assets}
    assets_by_name = {a.name.lower(): a for a in org_assets}
    # Threat es catalogo global (sin organization_id) — se accede sin filtro de org
    all_threats = db.query(Threat).all()
    threats_by_code = {t.code: t for t in all_threats}
    threats_by_name = {t.name.lower(): t for t in all_threats}

    def _parse_int(val: str, default: int = 0, lo: int = 0, hi: int = 4) -> int:
        try:
            return max(lo, min(hi, int(str(val).strip())))
        except (ValueError, TypeError):
            return default

    created, skipped = [], []

    for row in reader:
        asset_key = (row.get("Activo_Codigo") or "").strip()
        threat_key = (row.get("Amenaza_Codigo") or "").strip()

        asset = assets_by_code.get(asset_key) or assets_by_name.get(asset_key.lower())
        threat = threats_by_code.get(threat_key) or threats_by_name.get(threat_key.lower())

        if not asset:
            skipped.append(f"Activo no encontrado: '{asset_key}'")
            continue
        if not threat:
            skipped.append(f"Amenaza no encontrada: '{threat_key}'")
            continue

        # Detectar duplicados dentro de la misma org
        dup = db.query(Risk).filter(
            Risk.asset_id == asset.id,
            Risk.threat_id == threat.id,
            Risk.organization_id == current_user.organization_id,
        ).first()
        if dup:
            skipped.append(f"{asset.code} x {threat.code} (duplicado: {dup.code})")
            continue

        il = _parse_int(row.get("Prob_Inherente", "2"), 2)
        ic = _parse_int(row.get("Cons_Inherente", "2"), 2)
        rl = _parse_int(row.get("Prob_Residual", "1"), 1)
        rc = _parse_int(row.get("Cons_Residual", "1"), 1)

        status_val = (row.get("Estado") or "identified").strip().lower()
        try:
            status = RiskStatus(status_val)
        except ValueError:
            status = RiskStatus.IDENTIFIED

        treat_val = (row.get("Tratamiento") or "").strip().lower()
        try:
            treatment = TreatmentOption(treat_val) if treat_val else None
        except ValueError:
            treatment = None

        due_str = (row.get("Fecha_Vencimiento") or "").strip()
        due_date = None
        if due_str:
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    due_date = datetime.strptime(due_str, fmt)
                    break
                except ValueError:
                    continue

        n = db.query(Risk).count() + len(created) + 1
        code = f"RSK-{n:04d}"

        risk = Risk(
            code=code,
            asset_id=asset.id,
            threat_id=threat.id,
            description=(row.get("Descripcion") or "").strip(),
            inherent_likelihood=il,
            inherent_consequence=ic,
            inherent_level=calc_level(ic, il),
            residual_likelihood=rl,
            residual_consequence=rc,
            residual_level=calc_residual(ic, il, rc, rl),
            status=status,
            treatment_option=treatment,
            treatment_plan=(row.get("Plan_Tratamiento") or "").strip(),
            treatment_due_date=due_date,
            owner_id=current_user.id,
        )
        db.add(risk)
        created.append(code)

    if created:
        db.commit()
        log_action(db, current_user.id, "import", "risk", None,
                   {"count": len(created), "source": "csv"})
        db.commit()

    return {
        "created": len(created),
        "skipped": len(skipped),
        "detail_created": created,
        "detail_skipped": skipped,
    }


@router.get("/heatmap/data")
def heatmap(db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user),
            mode: str = Query("residual", regex="^(residual|inherent)$")):
    """Devuelve matriz 5x5 con conteo y referencias de riesgo."""
    matrix = [[{"count": 0, "risks": []} for _ in range(5)] for _ in range(5)]
    for r in filter_by_org(db.query(Risk), Risk, current_user).all():
        if mode == "residual":
            x, y = r.residual_likelihood, r.residual_consequence
        else:
            x, y = r.inherent_likelihood, r.inherent_consequence
        x = max(0, min(4, x)); y = max(0, min(4, y))
        matrix[4 - y][x]["count"] += 1
        matrix[4 - y][x]["risks"].append({
            "id": r.id, "code": r.code,
            "asset": r.asset.name if r.asset else "",
            "threat": r.threat.name if r.threat else "",
            "level": r.residual_level if mode == "residual" else r.inherent_level,
        })
    return {"mode": mode, "matrix": matrix}


@router.get("/stats/summary")
def summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Resumen para el dashboard."""
    now = datetime.now(timezone.utc)
    risks = filter_by_org(db.query(Risk), Risk, current_user).all()
    by_band = {"low": 0, "medium": 0, "high": 0}
    for r in risks:
        if r.residual_level <= 2: by_band["low"] += 1
        elif r.residual_level <= 5: by_band["medium"] += 1
        else: by_band["high"] += 1
    by_status = {s.value: 0 for s in RiskStatus}
    for r in risks:
        by_status[r.status.value] += 1
    by_treatment = {t.value: 0 for t in TreatmentOption}
    for r in risks:
        if r.treatment_option:
            by_treatment[r.treatment_option.value] += 1

    # Metricas adicionales
    active_statuses = {RiskStatus.IDENTIFIED, RiskStatus.ASSESSED}
    active_risks = [r for r in risks if r.status in active_statuses]
    overdue = sum(
        1 for r in active_risks
        if r.treatment_due_date and r.treatment_due_date.replace(tzinfo=timezone.utc) < now
    )
    no_treatment_high = sum(
        1 for r in active_risks
        if r.residual_level >= 5 and not r.treatment_option
    )
    no_owner = sum(1 for r in risks if r.owner_id is None
                   and r.status not in {RiskStatus.ACCEPTED, RiskStatus.CLOSED})
    total_inh = sum(r.inherent_level for r in risks)
    total_res = sum(r.residual_level for r in risks)
    reduction_pct = round((1 - total_res / total_inh) * 100) if total_inh else 0

    # Control maturity stats
    from app.models import ControlStatus
    impls = filter_by_org(db.query(ControlImplementation), ControlImplementation, current_user).all()
    impl_implemented = sum(1 for c in impls if c.status == ControlStatus.IMPLEMENTED)
    avg_maturity = round(sum(c.maturity for c in impls) / len(impls), 1) if impls else 0
    controls_overdue_reviews = sum(
        1 for c in impls
        if c.next_review
        and c.next_review.replace(tzinfo=timezone.utc) < now
        and c.status != ControlStatus.NOT_IMPLEMENTED
    )

    return {
        "total_risks": len(risks),
        "total_assets": db.query(Asset).count(),
        "total_threats": db.query(Threat).count(),
        "total_vulnerabilities": db.query(Vulnerability).count(),
        "total_controls": len(impls),
        "controls_implemented": impl_implemented,
        "controls_avg_maturity": avg_maturity,
        "controls_overdue_reviews": controls_overdue_reviews,
        "by_band": by_band,
        "by_status": by_status,
        "by_treatment": by_treatment,
        "overdue_treatments": overdue,
        "no_treatment_high": no_treatment_high,
        "no_owner": no_owner,
        "risk_reduction_pct": reduction_pct,
        "top_risks": [
            {"code": r.code, "asset": r.asset.name if r.asset else "",
             "threat": r.threat.name if r.threat else "",
             "level": r.residual_level, "inherent_level": r.inherent_level, "id": r.id}
            for r in sorted(risks, key=lambda x: -x.residual_level)[:10]
        ],
    }
