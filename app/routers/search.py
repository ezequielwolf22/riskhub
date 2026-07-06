"""Busqueda global entre activos, riesgos, amenazas y vulnerabilidades."""
from typing import List

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import Asset, ControlImplementation, Risk, Threat, User, Vulnerability
from app.security import filter_by_org, get_current_user

router = APIRouter(prefix="/api/search", tags=["search"])


def _ilike(column, q: str):
    return column.ilike(f"%{q}%")


@router.get("/")
def global_search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Busca en activos, riesgos, amenazas y vulnerabilidades."""
    lang = get_lang(request)
    term = q.strip()

    # Activos (filtrados por org)
    assets = filter_by_org(db.query(Asset), Asset, current_user).filter(
        Asset.name.ilike(f"%{term}%") |
        Asset.description.ilike(f"%{term}%") |
        Asset.category.ilike(f"%{term}%")
    ).limit(10).all()

    # Riesgos (filtrados por org)
    risks = filter_by_org(db.query(Risk), Risk, current_user).filter(
        Risk.code.ilike(f"%{term}%") |
        Risk.description.ilike(f"%{term}%") |
        Risk.consequence_description.ilike(f"%{term}%")
    ).limit(10).all()

    # Amenazas (catalogo global — sin filtro de org)
    threats = db.query(Threat).filter(
        Threat.name.ilike(f"%{term}%") |
        Threat.description.ilike(f"%{term}%")
    ).limit(10).all()

    # Vulnerabilidades (catalogo global — sin filtro de org)
    vulns = db.query(Vulnerability).filter(
        Vulnerability.name.ilike(f"%{term}%") |
        Vulnerability.description.ilike(f"%{term}%")
    ).limit(10).all()

    # Controles implementados (filtrados por org)
    controls = filter_by_org(db.query(ControlImplementation), ControlImplementation, current_user).filter(
        ControlImplementation.name.ilike(f"%{term}%") |
        ControlImplementation.description.ilike(f"%{term}%")
    ).limit(6).all()

    return {
        "query": term,
        "results": {
            "assets": [
                {"id": a.id, "type": "asset", "title": a.name,
                 "subtitle": a.asset_type.value if a.asset_type else "",
                 "meta": a.category or "", "url": f"#/assets"}
                for a in assets
            ],
            "risks": [
                {"id": r.id, "type": "risk", "title": r.code,
                 "subtitle": (r.asset.name if r.asset else "") + " — " + (r.threat.name if r.threat else ""),
                 "meta": _t("search.risk_level_meta", lang, level=r.residual_level), "url": f"#/risks"}
                for r in risks
            ],
            "threats": [
                {"id": t.id, "type": "threat", "title": t.name,
                 "subtitle": t.category or "", "meta": "",
                 "url": "#/threats"}
                for t in threats
            ],
            "vulnerabilities": [
                {"id": v.id, "type": "vulnerability", "title": v.name,
                 "subtitle": v.category or "", "meta": "",
                 "url": "#/vulnerabilities"}
                for v in vulns
            ],
            "controls": [
                {"id": c.id, "type": "control", "title": c.name,
                 "subtitle": c.control.code if c.control else "",
                 "meta": c.status.value if c.status else "",
                 "url": "#/controls"}
                for c in controls
            ],
        },
        "total": len(assets) + len(risks) + len(threats) + len(vulns) + len(controls),
    }
