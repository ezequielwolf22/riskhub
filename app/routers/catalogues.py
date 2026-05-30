"""Catalogos: amenazas (ISO 27005 C) y vulnerabilidades (ISO 27005 D)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Risk, Threat, Vulnerability, User, risk_vulnerability_table
from app.schemas import ThreatIn, ThreatOut, VulnerabilityIn, VulnerabilityOut
from app.security import get_current_user, require_analyst
from app.services.audit_service import log_action

threats_router = APIRouter(prefix="/api/threats", tags=["threats"])
vulns_router = APIRouter(prefix="/api/vulnerabilities", tags=["vulnerabilities"])


# ---------- THREATS ----------

@threats_router.get("/", response_model=list[ThreatOut])
def list_threats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    q: Optional[str] = None,
    category: Optional[str] = None,
):
    query = db.query(Threat)
    if q:
        like = f"%{q}%"
        query = query.filter((Threat.name.ilike(like)) | (Threat.code.ilike(like)))
    if category:
        query = query.filter(Threat.category == category)
    threats = query.order_by(Threat.code).all()

    # Compute risk counts in a single query
    counts_q = (
        db.query(Risk.threat_id, func.count(Risk.id))
        .filter(Risk.threat_id.in_([t.id for t in threats]))
        .group_by(Risk.threat_id)
        .all()
    )
    risk_counts = {tid: cnt for tid, cnt in counts_q}

    # Inject risk_count by building dicts (ThreatOut is ORM model)
    result = []
    for t in threats:
        d = {c.key: getattr(t, c.key) for c in t.__table__.columns}
        d["risk_count"] = risk_counts.get(t.id, 0)
        result.append(ThreatOut.model_validate(d))
    return result


@threats_router.post("/", response_model=ThreatOut, status_code=201)
def create_threat(data: ThreatIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_analyst)):
    code = data.code or _next_code(db, Threat, "T.CUS")
    if db.query(Threat).filter(Threat.code == code).first():
        raise HTTPException(400, f"Ya existe amenaza con codigo {code}")
    t = Threat(**data.model_dump(exclude={"code"}), code=code, is_custom=True)
    db.add(t)
    log_action(db, current_user.id, "create", "threat", None,
               {"code": code, "name": data.name})
    db.commit(); db.refresh(t)
    return t


@threats_router.put("/{tid}", response_model=ThreatOut)
def update_threat(tid: int, data: ThreatIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_analyst)):
    t = db.get(Threat, tid)
    if not t:
        raise HTTPException(404, "Amenaza no encontrada")
    if not t.is_custom:
        raise HTTPException(400, "No se pueden modificar amenazas del catalogo oficial")
    for k, v in data.model_dump(exclude={"code"}).items():
        setattr(t, k, v)
    log_action(db, current_user.id, "update", "threat", str(tid),
               {"code": t.code, "name": t.name})
    db.commit(); db.refresh(t)
    return t


@threats_router.delete("/{tid}", status_code=204)
def delete_threat(tid: int, db: Session = Depends(get_db),
                  current_user: User = Depends(require_analyst)):
    t = db.get(Threat, tid)
    if not t:
        raise HTTPException(404, "Amenaza no encontrada")
    # Permitir borrar amenazas personalizadas Y amenazas MAGERIT (code MAGERIT-*)
    is_magerit = t.code.startswith("MAGERIT-")
    if not t.is_custom and not is_magerit:
        raise HTTPException(400, "Solo se pueden borrar amenazas personalizadas o del catálogo MAGERIT")
    # Verificar que no tenga riesgos asociados antes de borrar
    from app.models import Risk
    linked = db.query(Risk).filter(Risk.threat_id == tid).count()
    if linked > 0:
        raise HTTPException(409,
            f"Esta amenaza tiene {linked} riesgo(s) asociado(s). "
            "Elimina o reasigna los riesgos antes de borrar la amenaza.")
    log_action(db, current_user.id, "delete", "threat", str(tid),
               {"code": t.code, "name": t.name})
    db.delete(t); db.commit()


# ---------- VULNERABILITIES ----------

@vulns_router.get("/", response_model=list[VulnerabilityOut])
def list_vulns(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    q: Optional[str] = None,
    category: Optional[str] = None,
):
    query = db.query(Vulnerability)
    if q:
        like = f"%{q}%"
        query = query.filter((Vulnerability.name.ilike(like)) | (Vulnerability.code.ilike(like)))
    if category:
        query = query.filter(Vulnerability.category == category)
    vulns = query.order_by(Vulnerability.code).all()

    # Count linked risks via the many-to-many junction table
    counts_q = (
        db.query(
            risk_vulnerability_table.c.vulnerability_id,
            func.count(risk_vulnerability_table.c.risk_id),
        )
        .filter(risk_vulnerability_table.c.vulnerability_id.in_([v.id for v in vulns]))
        .group_by(risk_vulnerability_table.c.vulnerability_id)
        .all()
    )
    risk_counts = {vid: cnt for vid, cnt in counts_q}

    result = []
    for v in vulns:
        d = {c.key: getattr(v, c.key) for c in v.__table__.columns}
        d["risk_count"] = risk_counts.get(v.id, 0)
        result.append(VulnerabilityOut.model_validate(d))
    return result


@vulns_router.post("/", response_model=VulnerabilityOut, status_code=201)
def create_vuln(data: VulnerabilityIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    code = data.code or _next_code(db, Vulnerability, "V.CUS")
    if db.query(Vulnerability).filter(Vulnerability.code == code).first():
        raise HTTPException(400, f"Ya existe vulnerabilidad con codigo {code}")
    v = Vulnerability(**data.model_dump(exclude={"code"}), code=code, is_custom=True)
    db.add(v)
    log_action(db, current_user.id, "create", "vulnerability", None,
               {"code": code, "name": data.name})
    db.commit(); db.refresh(v)
    return v


@vulns_router.put("/{vid}", response_model=VulnerabilityOut)
def update_vuln(vid: int, data: VulnerabilityIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    v = db.get(Vulnerability, vid)
    if not v:
        raise HTTPException(404, "Vulnerabilidad no encontrada")
    if not v.is_custom:
        raise HTTPException(400, "No se pueden modificar vulnerabilidades del catalogo oficial")
    for k, val in data.model_dump(exclude={"code"}).items():
        setattr(v, k, val)
    log_action(db, current_user.id, "update", "vulnerability", str(vid),
               {"code": v.code, "name": v.name})
    db.commit(); db.refresh(v)
    return v


@vulns_router.delete("/{vid}", status_code=204)
def delete_vuln(vid: int, db: Session = Depends(get_db),
                current_user: User = Depends(require_analyst)):
    v = db.get(Vulnerability, vid)
    if not v or not v.is_custom:
        raise HTTPException(400, "Solo se pueden borrar vulnerabilidades personalizadas")
    log_action(db, current_user.id, "delete", "vulnerability", str(vid),
               {"code": v.code, "name": v.name})
    db.delete(v); db.commit()


def _next_code(db: Session, model, prefix: str) -> str:
    n = db.query(model).filter(model.code.like(f"{prefix}%")).count() + 1
    return f"{prefix}.{n:03d}"
