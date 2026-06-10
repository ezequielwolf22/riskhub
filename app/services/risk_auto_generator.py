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
import threading
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


def _controls_to_dicts(controls: list) -> list[dict]:
    """Convierte lista de ControlImplementation ORM a list[dict] para calc_residual."""
    return [{"maturity": c.maturity or 0, "contribution": 1.0} for c in controls]


def _inherit_controls(db: Session, asset: Asset, threat: Threat) -> list:
    """Hereda controles del asset type + threat.

    Busca controles implementados o parcialmente implementados que reducen el residual.
    Usa maturity (0-5) como indicador de contribucion al tratamiento.
    """
    from app.models import ControlStatus
    controls = db.query(ControlImplementation).filter(
        ControlImplementation.organization_id == asset.organization_id,
        ControlImplementation.status.in_([
            ControlStatus.IMPLEMENTED, ControlStatus.PARTIAL
        ]),
        ControlImplementation.maturity > 0,
    ).order_by(ControlImplementation.maturity.desc()).all()

    return controls[:5]  # Máximo 5 controles por riesgo para mantener el calculo rapido


def _get_inherent_values_from_ai(db: Session, asset: Asset, threat: Threat) -> tuple[int, int]:
    """Llama directamente a Anthropic — rag_service.ask() no existe."""
    try:
        from app.services.isms_analysis_service import _get_api_key, _get_model
        import anthropic
        api_key = _get_api_key(db, asset.organization_id)
        if not api_key:
            return (2, 2)
        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            f"Evalúa riesgo ISO 27005. Activo: {asset.name} "
            f"({asset.asset_type.value if asset.asset_type else 'desconocido'}). "
            f"Amenaza: {threat.name}. "
            f"Devuelve SOLO dos enteros separados por coma: likelihood,consequence "
            f"(escala 0-4). Ejemplo: 3,2"
        )
        msg = client.messages.create(
            model=_get_model(db, asset.organization_id), max_tokens=10,
            messages=[{"role": "user", "content": prompt}]
        )
        parts = msg.content[0].text.strip().split(",")
        l, c = int(parts[0].strip()), int(parts[1].strip())
        if 0 <= l <= 4 and 0 <= c <= 4:
            return (l, c)
    except Exception:
        pass
    return (2, 2)


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

    # C3: Threat es catalogo global sin organization_id — no filtrar por org.
    # Usar solo amenazas del catalogo estandar (is_custom=False), max 10 por activo.
    applicable_threats = db.query(Threat).filter(
        Threat.is_custom == False,  # noqa: E712
    ).limit(10).all()

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

        # Heredar controles ANTES de calcular residual
        inherited = _inherit_controls(db, asset, threat)
        risk.controls = inherited  # M2M ORM

        # calc_residual espera list[dict] — convertir ORM objects
        controls_dicts = _controls_to_dicts(inherited)

        # Calcular inherent y residual con controles ya aplicados
        risk.inherent_level = calc_level(
            inherent_consequence, inherent_likelihood, matrix
        )
        rl, rc, rlev = calc_residual(
            inherent_likelihood, inherent_consequence, controls_dicts, matrix
        )
        risk.residual_likelihood = rl
        risk.residual_consequence = rc
        risk.residual_level = rlev

        # Auto-tratamiento segun appetite
        # C2: TreatmentOption.ACCEPTANCE no existe; RETENTION = "aceptar conscientemente"
        if rlev <= appetite:
            risk.treatment_option = TreatmentOption.RETENTION
            risk.status = RiskStatus.ACCEPTED
        else:
            risk.treatment_option = TreatmentOption.MODIFICATION
            risk.status = RiskStatus.ASSESSED

        # Fijar próxima revisión según nivel residual (habilita notificaciones scheduler)
        from datetime import timedelta
        review_days = {0: 365, 1: 365, 2: 180, 3: 90, 4: 60, 5: 30, 6: 14, 7: 7, 8: 7}
        risk.next_review = datetime.now(timezone.utc) + timedelta(
            days=review_days.get(rlev, 90)
        )

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
                    # A5: notify_high_risk es sincrono (hasta 40s) — ejecutar en thread
                    def _notify_itsm_bg(rid: int) -> None:
                        from app.database import SessionLocal
                        _db = SessionLocal()
                        try:
                            from app.models import Risk as _Risk
                            _r = _db.get(_Risk, rid)
                            if _r:
                                from app.services.itsm_service import notify_high_risk
                                notify_high_risk(_db, _r)
                        except Exception as exc2:
                            logger.debug("Error notificando ITSM background: %s", exc2)
                        finally:
                            _db.close()
                    threading.Thread(target=_notify_itsm_bg, args=(r.id,), daemon=True).start()
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

    # C3: Threat es catalogo global — sin organization_id, likelihood ni consequence.
    cve_threat_code = f"CVE-{cve_id}"
    threat = db.query(Threat).filter(
        Threat.code == cve_threat_code,
    ).first()

    # Comprobar duplicado usando threat_id real
    if threat:
        existing = db.query(Risk).filter(
            Risk.asset_id == asset_id,
            Risk.threat_id == threat.id,
            Risk.organization_id == org_id,
        ).first()
        if existing:
            logger.debug("Riesgo duplicado CVE=%s asset=%s, saltando", cve_id, asset.code)
            return None

    if not threat:
        # Crear threat en catalogo global (compartido entre orgs)
        from app.models import ThreatOrigin
        threat = Threat(
            code=cve_threat_code,
            name=f"CVE {cve_id}",
            description=f"Vulnerabilidad critica {cve_id} en {affected_software}",
            origin=ThreatOrigin.DELIBERATE,
            is_custom=False,
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

    # Heredar controles ANTES de decidir tratamiento para residual mas preciso
    applicable_controls = _inherit_controls(db, asset, threat)
    controls_dicts = _controls_to_dicts(applicable_controls)  # list[dict] para calc_residual
    if controls_dicts:
        rl2, rc2, rlev2 = calc_residual(
            inherent_likelihood, inherent_consequence, controls_dicts, matrix
        )
        risk.residual_likelihood = rl2
        risk.residual_consequence = rc2
        risk.residual_level = rlev2
        rlev = rlev2  # nivel post-controles para todas las decisiones

    # Auto-tratamiento basado en nivel residual final
    # C2: TreatmentOption.ACCEPTANCE no existe; RETENTION = aceptar conscientemente
    if rlev <= appetite:
        risk.treatment_option = TreatmentOption.RETENTION
        risk.status = RiskStatus.ACCEPTED
    else:
        risk.treatment_option = TreatmentOption.MODIFICATION
        risk.status = RiskStatus.ASSESSED

    # Fechas basadas en nivel residual final
    from datetime import timedelta
    review_days = {0: 365, 1: 365, 2: 180, 3: 90, 4: 60, 5: 30, 6: 14, 7: 7, 8: 7}
    risk.next_review = datetime.now(timezone.utc) + timedelta(days=review_days.get(rlev, 90))
    treatment_days = {0: 365, 1: 180, 2: 90, 3: 60, 4: 45, 5: 30, 6: 14, 7: 7, 8: 3}
    risk.treatment_due_date = datetime.now(timezone.utc) + timedelta(days=treatment_days.get(rlev, 60))

    # Asignar controles ORM al risk (M2M)
    risk.controls = applicable_controls

    # Asignar propietario
    if not risk.owner_id:
        from app.models import User, UserRole
        owner = db.query(User).filter(
            User.organization_id == org_id,
            User.role.in_([UserRole.ADMIN, UserRole.ANALYST]),
            User.is_active.is_(True),
        ).first()
        if owner:
            risk.owner_id = owner.id

    db.add(risk)

    try:
        db.commit()
        db.refresh(risk)
        logger.info(
            "Auto-generado riesgo CVE %s para asset %s: residual=%d",
            cve_id, asset.code, risk.residual_level
        )
        # Flagear procesos BCP que dependen del activo afectado (ISO 22301 cl. 8.3)
        try:
            from app.services.bcp_service import flag_bcp_process_for_cve
            flag_bcp_process_for_cve(db, asset_id=asset.id, cve_id=cve_id,
                                     org_id=asset.organization_id)
        except Exception:
            pass
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

    # C3: Threat es catalogo global — sin organization_id, likelihood ni consequence.
    osint_threat_code = f"OSINT-{osint_finding_type.upper()}"

    # Buscar o crear threat en catalogo global
    threat = db.query(Threat).filter(
        Threat.code == osint_threat_code,
    ).first()

    # Comprobar duplicado usando threat_id real
    if threat:
        existing = db.query(Risk).filter(
            Risk.asset_id == asset_id,
            Risk.threat_id == threat.id,
            Risk.organization_id == org_id,
        ).first()
        if existing:
            logger.debug(
                "Riesgo duplicado OSINT=%s asset=%s, saltando",
                osint_finding_type, asset.code
            )
            return None

    if not threat:
        from app.models import ThreatOrigin
        threat = Threat(
            code=osint_threat_code,
            name=f"OSINT: {osint_finding_title}",
            description=f"Hallazgo de seguridad externo: {osint_finding_type}",
            origin=ThreatOrigin.DELIBERATE,
            is_custom=False,
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

    # Heredar controles ANTES de decidir tratamiento para residual mas preciso
    applicable_controls = _inherit_controls(db, asset, threat)
    controls_dicts = _controls_to_dicts(applicable_controls)
    if controls_dicts:
        rl2, rc2, rlev2 = calc_residual(
            inherent_likelihood, inherent_consequence, controls_dicts, matrix
        )
        risk.residual_likelihood = rl2
        risk.residual_consequence = rc2
        risk.residual_level = rlev2
        rlev = rlev2

    # Auto-tratamiento basado en nivel residual final
    # C2: TreatmentOption.ACCEPTANCE no existe; RETENTION = aceptar conscientemente
    if rlev <= appetite:
        risk.treatment_option = TreatmentOption.RETENTION
        risk.status = RiskStatus.ACCEPTED
    else:
        risk.treatment_option = TreatmentOption.MODIFICATION
        risk.status = RiskStatus.ASSESSED

    # Fechas basadas en nivel residual final
    from datetime import timedelta
    review_days = {0: 365, 1: 365, 2: 180, 3: 90, 4: 60, 5: 30, 6: 14, 7: 7, 8: 7}
    risk.next_review = datetime.now(timezone.utc) + timedelta(days=review_days.get(rlev, 90))
    treatment_days = {0: 365, 1: 180, 2: 90, 3: 60, 4: 45, 5: 30, 6: 14, 7: 7, 8: 3}
    risk.treatment_due_date = datetime.now(timezone.utc) + timedelta(days=treatment_days.get(rlev, 60))

    # Asignar controles ORM al risk (M2M)
    risk.controls = applicable_controls

    # Asignar propietario
    if not risk.owner_id:
        from app.models import User, UserRole
        owner = db.query(User).filter(
            User.organization_id == org_id,
            User.role.in_([UserRole.ADMIN, UserRole.ANALYST]),
            User.is_active.is_(True),
        ).first()
        if owner:
            risk.owner_id = owner.id

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
