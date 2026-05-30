"""Generador automatico de riesgos — activo × amenaza + CVE + OSINT.

Flujo:
  1. Cuando se carga un asset nuevo → auto-genera riesgos para amenazas aplicables
  2. Cuando se detecta CVE → auto-genera riesgo si afecta asset
  3. Cuando se detecta OSINT hallazgo → auto-genera riesgo si afecta asset
  4. Para cada riesgo auto-generado:
     - Calcula inherent_level (ISO27005 matrix)
     - Asigna controles heredados del asset + amenaza
     - Calcula residual_level
     - Compara contra risk_appetite
     - Si residual <= appetite → ACCEPTANCE automática
     - Si residual > appetite → ASSESSED con email alerta
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Asset, Threat, Risk, RiskStatus, TreatmentOption, RiskContext,
    ControlImplementation, Vulnerability, User, UserRole,
)
from app.services.risk_engine import calc_level, calc_residual

logger = logging.getLogger("riskhub.risk_auto_generator")


def _next_code(db: Session, org_id: int) -> str:
    """Genera codigo unico RSK-XXXX por organizacion."""
    count = db.query(Risk).filter(Risk.organization_id == org_id).count() + 1
    return f"RSK-{count:04d}"


def _inherit_controls(db: Session, asset: Asset, threat: Threat) -> list:
    """Hereda controles del asset type + threat.

    Busca controles activos que mitigan esta amenaza.
    """
    controls = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == asset.organization_id,
        ControlImplementation.status == "IMPLEMENTED",
    ).all()

    # Filtrar controles relevantes a la amenaza
    # (En futuro: mejorar con tabla de mapeo Control-Threat)
    relevant = [c for c in controls if c.mitigation_level and c.mitigation_level > 0]
    return relevant[:5]  # Máximo 5 controles por riesgo


def _get_inherent_values_from_ai(db: Session, asset: Asset, threat: Threat) -> tuple[int, int]:
    """IA analiza asset + threat → propone likelihood y consequence.

    Cae back a defaults si no puede.
    """
    try:
        from app.services.rag_service import rag_service

        prompt = (
            f"Evalúa riesgo de seguridad. Asset: {asset.name} ({asset.description or 'sin desc'}). "
            f"Amenaza: {threat.name} ({threat.description or 'sin desc'}). "
            f"Devuelve 2 números (likelihood,consequence) del 0-4 donde "
            f"0=imposible/nulo, 1=raro, 2=posible, 3=probable, 4=seguro. "
            f"Formato: SOLO '3,2' sin comillas."
        )

        response = rag_service.ask(prompt, org_id=asset.organization_id)
        if response:
            parts = response.strip().split(',')
            if len(parts) == 2:
                l = int(parts[0].strip())
                c = int(parts[1].strip())
                if 0 <= l <= 4 and 0 <= c <= 4:
                    logger.info("IA valuación para %s+%s: L=%d C=%d",
                               asset.code, threat.code, l, c)
                    return (l, c)
    except Exception as e:
        logger.debug("IA valuación falló: %s, usando defaults", e)

    return (2, 2)  # Default: posible + moderado


def auto_generate_risks_for_asset(
    db: Session,
    asset: Asset,
    user_id: Optional[int] = None,
) -> list[Risk]:
    """Auto-genera riesgos para asset nuevo basado en amenazas aplicables.

    Args:
        db: Session
        asset: Asset objeto recientemente creado
        user_id: Usuario que creo el asset (para owner riesgos)

    Returns:
        Lista de riesgos creados
    """
    created_risks = []

    if not asset.organization_id:
        logger.warning("Asset %s sin organization_id, saltando auto-gen", asset.id)
        return created_risks

    # Query: amenazas aplicables al tipo de asset
    applicable_threats = db.query(Threat).filter(
        Threat.organization_id == asset.organization_id,
    ).all()

    if not applicable_threats:
        logger.info("Asset %s: sin amenazas aplicables, saltando", asset.code)
        return created_risks

    # Obtener risk context para appetite y matriz
    ctx = db.query(RiskContext).filter(
        RiskContext.organization_id == asset.organization_id
    ).first()
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3
    matrix = ctx.risk_matrix if ctx and ctx.risk_matrix else None

    # Para cada amenaza: crear riesgo si no existe
    for threat in applicable_threats:
        # Comprobar duplicado
        existing = db.query(Risk).filter(
            Risk.asset_id == asset.id,
            Risk.threat_id == threat.id,
            Risk.organization_id == asset.organization_id,
        ).first()

        if existing:
            logger.debug(
                "Riesgo duplicado asset=%s threat=%s, saltando",
                asset.code, threat.code
            )
            continue

        # IA valuación: likelihood + consequence
        inherent_likelihood, inherent_consequence = _get_inherent_values_from_ai(
            db, asset, threat
        )

        # Crear riesgo
        risk = Risk(
            code=_next_code(db, asset.organization_id),
            organization_id=asset.organization_id,
            asset_id=asset.id,
            threat_id=threat.id,
            description=f"Riesgo generado automaticamente: {asset.name} + {threat.name}",
            consequence_description=f"Impacto por {threat.name} en {asset.name}",
            inherent_likelihood=inherent_likelihood,
            inherent_consequence=inherent_consequence,
            owner_id=user_id,
            status=RiskStatus.IDENTIFIED,
        )

        # Asignar controles heredados: controles IMPLEMENTED que aplican a esta amenaza
        risk.controls = _inherit_controls(db, asset, threat)

        # Calcular inherent y residual
        risk.inherent_level = calc_level(
            inherent_consequence, inherent_likelihood, matrix
        )
        rl, rc, rlev = calc_residual(
            inherent_likelihood, inherent_consequence, risk.controls, matrix
        )
        risk.residual_likelihood = rl
        risk.residual_consequence = rc
        risk.residual_level = rlev

        # Auto-tratamiento segun appetite
        if rlev <= appetite:
            risk.treatment_option = TreatmentOption.ACCEPTANCE
            risk.status = RiskStatus.ACCEPTED
        else:
            risk.treatment_option = None
            risk.status = RiskStatus.ASSESSED

        db.add(risk)
        created_risks.append(risk)

        logger.info(
            "Auto-generado riesgo %s: asset=%s threat=%s "
            "inherent=(%d,%d) residual=%d (appetite=%d, status=%s)",
            risk.code, asset.code, threat.code,
            inherent_likelihood, inherent_consequence,
            risk.residual_level, appetite, risk.status
        )

    try:
        db.commit()
        for r in created_risks:
            db.refresh(r)
    except Exception as exc:
        logger.exception("Error committing auto-generated risks: %s", exc)
        db.rollback()
        return []

    # Iniciar workflow y webhooks para riesgos ASSESSED
    for r in created_risks:
        if r.status == RiskStatus.ASSESSED:
            try:
                from app.services.workflow_engine import start_risk_workflow
                start_risk_workflow(db, r)
            except Exception as exc:
                logger.debug("Error iniciando workflow para %s: %s", r.code, exc)
            try:
                from app.services.webhook_service import fire_risk_created, fire_risk_high
                fire_risk_created(db, r)
                if (r.residual_level or 0) >= 5:
                    fire_risk_high(db, r)
            except Exception as exc:
                logger.debug("Error disparando webhook: %s", exc)

    return created_risks


def auto_generate_risk_from_cve(
    db: Session,
    asset_id: int,
    cve_id: str,
    affected_software: str,
    inherent_consequence: int = 3,
    inherent_likelihood: int = 3,
) -> Optional[Risk]:
    """Auto-genera riesgo cuando CVE afecta a un asset.

    Args:
        db: Session
        asset_id: Asset afectado
        cve_id: Ej. "CVE-2024-1234"
        affected_software: Ej. "Apache 2.4.41"
        inherent_consequence: 0-4 (default 3 = moderado)
        inherent_likelihood: 0-4 (default 3 = probable)

    Returns:
        Risk creado o None si error
    """
    asset = db.get(Asset, asset_id)
    if not asset:
        logger.warning("Asset %s not found, CVE auto-gen aborted", asset_id)
        return None

    org_id = asset.organization_id
    if not org_id:
        logger.warning("Asset %s sin org_id, CVE auto-gen aborted", asset.code)
        return None

    # Comprobar duplicado: riesgo con mismo asset y threat "CVE-XXXX"
    cve_threat_code = f"CVE-{cve_id}"
    existing = db.query(Risk).filter(
        Risk.asset_id == asset_id,
        Risk.threat_id == db.query(Threat.id).filter(
            Threat.code == cve_threat_code,
            Threat.organization_id == org_id,
        ),
    ).first()

    if existing:
        logger.debug("Riesgo duplicado CVE=%s asset=%s, saltando", cve_id, asset.code)
        return None

    # Buscar o crear threat "CVE-XXXX"
    threat = db.query(Threat).filter(
        Threat.code == cve_threat_code,
        Threat.organization_id == org_id,
    ).first()

    if not threat:
        # Crear threat temporal para CVE
        threat = Threat(
            code=cve_threat_code,
            organization_id=org_id,
            name=f"CVE {cve_id}",
            description=f"Vulnerabilidad critica {cve_id} en {affected_software}",
            origin="D",  # Deliberate/software vulnerability
            likelihood=inherent_likelihood,
            consequence=inherent_consequence,
        )
        db.add(threat)
        db.flush()

    # Crear riesgo
    ctx = db.query(RiskContext).filter(
        RiskContext.organization_id == org_id
    ).first()
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3
    matrix = ctx.risk_matrix if ctx and ctx.risk_matrix else None

    risk = Risk(
        code=_next_code(db, org_id),
        organization_id=org_id,
        asset_id=asset_id,
        threat_id=threat.id,
        description=f"Riesgo por {cve_id}: {affected_software}",
        consequence_description=f"Explotacion de {cve_id} en {asset.name}",
        inherent_likelihood=inherent_likelihood,
        inherent_consequence=inherent_consequence,
        status=RiskStatus.IDENTIFIED,
    )

    # Calcular inherent y residual (sin controles por ahora)
    risk.inherent_level = calc_level(
        inherent_consequence, inherent_likelihood, matrix
    )
    rl, rc, rlev = calc_residual(
        inherent_likelihood, inherent_consequence, [], matrix
    )
    risk.residual_likelihood = rl
    risk.residual_consequence = rc
    risk.residual_level = rlev

    # Auto-tratamiento
    if rlev <= appetite:
        risk.treatment_option = TreatmentOption.ACCEPTANCE
        risk.status = RiskStatus.ACCEPTED
    else:
        risk.treatment_option = TreatmentOption.MODIFICATION
        risk.status = RiskStatus.ASSESSED

    db.add(risk)

    try:
        db.commit()
        db.refresh(risk)
        logger.info(
            "Auto-generado riesgo CVE %s para asset %s: residual=%d",
            cve_id, asset.code, risk.residual_level
        )
        return risk
    except Exception as exc:
        logger.exception("Error creating CVE risk: %s", exc)
        db.rollback()
        return None


def auto_generate_risk_from_osint(
    db: Session,
    asset_id: int,
    osint_finding_type: str,
    osint_finding_title: str,
    inherent_consequence: int = 4,
    inherent_likelihood: int = 4,
) -> Optional[Risk]:
    """Auto-genera riesgo cuando OSINT hallazgo afecta asset.

    Tipos: "exposed_credentials", "breached_email", "malicious_url", "leaked_domain"
    """
    asset = db.get(Asset, asset_id)
    if not asset:
        logger.warning("Asset %s not found, OSINT auto-gen aborted", asset_id)
        return None

    org_id = asset.organization_id
    if not org_id:
        logger.warning("Asset %s sin org_id, OSINT auto-gen aborted", asset.code)
        return None

    # Threat code para OSINT
    osint_threat_code = f"OSINT-{osint_finding_type.upper()}"

    # Comprobar duplicado
    existing = db.query(Risk).filter(
        Risk.asset_id == asset_id,
        Risk.threat_id == db.query(Threat.id).filter(
            Threat.code == osint_threat_code,
            Threat.organization_id == org_id,
        ),
    ).first()

    if existing:
        logger.debug(
            "Riesgo duplicado OSINT=%s asset=%s, saltando",
            osint_finding_type, asset.code
        )
        return None

    # Buscar o crear threat
    threat = db.query(Threat).filter(
        Threat.code == osint_threat_code,
        Threat.organization_id == org_id,
    ).first()

    if not threat:
        threat = Threat(
            code=osint_threat_code,
            organization_id=org_id,
            name=f"OSINT: {osint_finding_title}",
            description=f"Hallazgo de seguridad externo: {osint_finding_type}",
            origin="D",
            likelihood=inherent_likelihood,
            consequence=inherent_consequence,
        )
        db.add(threat)
        db.flush()

    # Crear riesgo
    ctx = db.query(RiskContext).filter(
        RiskContext.organization_id == org_id
    ).first()
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3
    matrix = ctx.risk_matrix if ctx and ctx.risk_matrix else None

    risk = Risk(
        code=_next_code(db, org_id),
        organization_id=org_id,
        asset_id=asset_id,
        threat_id=threat.id,
        description=f"Riesgo por hallazgo OSINT: {osint_finding_title}",
        consequence_description=f"Exposicion externa de {asset.name}",
        inherent_likelihood=inherent_likelihood,
        inherent_consequence=inherent_consequence,
        status=RiskStatus.IDENTIFIED,
    )

    # Calcular inherent y residual
    risk.inherent_level = calc_level(
        inherent_consequence, inherent_likelihood, matrix
    )
    rl, rc, rlev = calc_residual(
        inherent_likelihood, inherent_consequence, [], matrix
    )
    risk.residual_likelihood = rl
    risk.residual_consequence = rc
    risk.residual_level = rlev

    # Auto-tratamiento
    if rlev <= appetite:
        risk.treatment_option = TreatmentOption.ACCEPTANCE
        risk.status = RiskStatus.ACCEPTED
    else:
        risk.treatment_option = TreatmentOption.MODIFICATION
        risk.status = RiskStatus.ASSESSED

    db.add(risk)

    try:
        db.commit()
        db.refresh(risk)
        logger.info(
            "Auto-generado riesgo OSINT %s para asset %s: residual=%d",
            osint_finding_type, asset.code, risk.residual_level
        )
        return risk
    except Exception as exc:
        logger.exception("Error creating OSINT risk: %s", exc)
        db.rollback()
        return None
