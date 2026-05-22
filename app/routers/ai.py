"""Endpoints del agente IA: cuestionario + análisis de riesgos."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Any

from app.database import get_db
from app.models import (
    Asset, AssetType, Risk, RiskStatus, Threat, TreatmentOption, User,
)
from app.security import get_current_user, require_role
from app.services.ai_service import QUESTIONNAIRE, run_analysis

router = APIRouter(prefix="/api/ai", tags=["ai"])


class AnalyzeRequest(BaseModel):
    answers: dict[str, Any]


class ImportRequest(BaseModel):
    scenarios: list[dict[str, Any]]


@router.get("/questionnaire")
def get_questionnaire(_: User = Depends(get_current_user)):
    """Devuelve la definición del cuestionario de contexto organizacional."""
    return {"questions": QUESTIONNAIRE}


@router.post("/analyze")
def analyze(
    req: AnalyzeRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Envía las respuestas al agente IA y devuelve el análisis de riesgos."""
    try:
        result = run_analysis(req.answers, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el análisis: {str(e)}")


@router.post("/import")
def import_risks(
    req: ImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Importa los escenarios seleccionados como riesgos en la base de datos."""
    created = []
    skipped = []

    # Cache de amenazas por código
    threat_by_code = {t.code: t for t in db.query(Threat).all()}
    threat_by_name = {t.name.lower(): t for t in db.query(Threat).all()}

    for sc in req.scenarios:
        # Resolver o crear activo
        asset = None
        if sc.get("asset_id"):
            asset = db.query(Asset).filter(Asset.id == sc["asset_id"]).first()

        if not asset and sc.get("asset_suggestion"):
            existing = db.query(Asset).filter(
                Asset.name == sc["asset_suggestion"]
            ).first()
            if existing:
                asset = existing
            else:
                try:
                    atype = AssetType(sc.get("asset_type", "support_hardware"))
                except ValueError:
                    atype = AssetType.SUPPORT_HARDWARE
                asset = Asset(
                    name=sc["asset_suggestion"],
                    asset_type=atype,
                    description=f"Activo generado por análisis IA",
                    owner=current_user.full_name or current_user.email,
                )
                db.add(asset)
                db.flush()

        if not asset:
            skipped.append(sc.get("asset_suggestion", "desconocido"))
            continue

        # Resolver amenaza
        threat = None
        if sc.get("threat_code"):
            threat = threat_by_code.get(sc["threat_code"])
        if not threat and sc.get("threat_name"):
            threat = threat_by_name.get(sc["threat_name"].lower())
        if not threat:
            skipped.append(f"{sc.get('asset_suggestion')} / {sc.get('threat_name')}")
            continue

        # Comprobar duplicados
        dup = db.query(Risk).filter(
            Risk.asset_id == asset.id,
            Risk.threat_id == threat.id,
        ).first()
        if dup:
            skipped.append(f"{asset.name} × {threat.name} (duplicado)")
            continue

        # Calcular código
        count = db.query(Risk).count() + len(created) + 1
        code = f"RSK-{count:04d}"

        risk = Risk(
            code=code,
            asset_id=asset.id,
            threat_id=threat.id,
            vulnerability_description=sc.get("vulnerability_description", ""),
            inherent_consequence=sc.get("inherent_consequence", 2),
            inherent_likelihood=sc.get("inherent_likelihood", 2),
            inherent_level=sc.get("inherent_level", 4),
            residual_consequence=sc.get("residual_consequence", 1),
            residual_likelihood=sc.get("residual_likelihood", 1),
            residual_level=sc.get("residual_level", 1),
            status=RiskStatus.IDENTIFIED,
            treatment_option=TreatmentOption.MODIFICATION,
            description=sc.get("rationale", ""),
            owner=current_user.full_name or current_user.email,
        )
        db.add(risk)
        created.append(f"{asset.name} × {threat.name}")

    db.commit()
    return {
        "created": len(created),
        "skipped": len(skipped),
        "detail_created": created,
        "detail_skipped": skipped,
    }
