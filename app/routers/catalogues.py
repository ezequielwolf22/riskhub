"""Catalogos: amenazas (ISO 27005 C) y vulnerabilidades (ISO 27005 D)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Threat, Vulnerability, User
from app.schemas import ThreatIn, ThreatOut, VulnerabilityIn, VulnerabilityOut
from app.security import get_current_user, require_analyst

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
    return query.order_by(Threat.code).all()


@threats_router.post("/", response_model=ThreatOut, status_code=201,
                     dependencies=[Depends(require_analyst)])
def create_threat(data: ThreatIn, db: Session = Depends(get_db)):
    code = data.code or _next_code(db, Threat, "T.CUS")
    if db.query(Threat).filter(Threat.code == code).first():
        raise HTTPException(400, f"Ya existe amenaza con codigo {code}")
    t = Threat(**data.model_dump(exclude={"code"}), code=code, is_custom=True)
    db.add(t); db.commit(); db.refresh(t)
    return t


@threats_router.put("/{tid}", response_model=ThreatOut,
                    dependencies=[Depends(require_analyst)])
def update_threat(tid: int, data: ThreatIn, db: Session = Depends(get_db)):
    t = db.get(Threat, tid)
    if not t:
        raise HTTPException(404, "Amenaza no encontrada")
    if not t.is_custom:
        raise HTTPException(400, "No se pueden modificar amenazas del catalogo oficial")
    for k, v in data.model_dump(exclude={"code"}).items():
        setattr(t, k, v)
    db.commit(); db.refresh(t)
    return t


@threats_router.delete("/{tid}", status_code=204,
                       dependencies=[Depends(require_analyst)])
def delete_threat(tid: int, db: Session = Depends(get_db)):
    t = db.get(Threat, tid)
    if not t or not t.is_custom:
        raise HTTPException(400, "Solo se pueden borrar amenazas personalizadas")
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
    return query.order_by(Vulnerability.code).all()


@vulns_router.post("/", response_model=VulnerabilityOut, status_code=201,
                   dependencies=[Depends(require_analyst)])
def create_vuln(data: VulnerabilityIn, db: Session = Depends(get_db)):
    code = data.code or _next_code(db, Vulnerability, "V.CUS")
    if db.query(Vulnerability).filter(Vulnerability.code == code).first():
        raise HTTPException(400, f"Ya existe vulnerabilidad con codigo {code}")
    v = Vulnerability(**data.model_dump(exclude={"code"}), code=code, is_custom=True)
    db.add(v); db.commit(); db.refresh(v)
    return v


@vulns_router.put("/{vid}", response_model=VulnerabilityOut,
                  dependencies=[Depends(require_analyst)])
def update_vuln(vid: int, data: VulnerabilityIn, db: Session = Depends(get_db)):
    v = db.get(Vulnerability, vid)
    if not v:
        raise HTTPException(404, "Vulnerabilidad no encontrada")
    if not v.is_custom:
        raise HTTPException(400, "No se pueden modificar vulnerabilidades del catalogo oficial")
    for k, val in data.model_dump(exclude={"code"}).items():
        setattr(v, k, val)
    db.commit(); db.refresh(v)
    return v


def _next_code(db: Session, model, prefix: str) -> str:
    n = db.query(model).filter(model.code.like(f"{prefix}%")).count() + 1
    return f"{prefix}.{n:03d}"
