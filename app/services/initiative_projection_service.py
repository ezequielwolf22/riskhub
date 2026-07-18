"""Motor determinista del Plan Director (v6.3.0).

Nada de IA aqui: es matematica sobre el mismo motor de riesgo que usa el
recalculo real (risk_engine + risk_recalc_service). Tres piezas:

  - auto_link_risks: deriva que riesgos afecta una iniciativa a partir de sus
    controles objetivo (via risk_controls directo + threat_control_map).
  - project_initiative: simula la madurez objetivo de esos controles con el
    MISMO motor que calcula el residual real, y guarda el residual proyectado
    por riesgo. Nunca escribe residual_level ni maturity reales.
  - verify_initiative: al completar una iniciativa, compara lo proyectado con
    lo que el motor real acabo calculando. El gap queda visible, nunca oculto.

reproject_for_impls se invoca desde risk_recalc_service.recalc_risks_for_impls
(import diferido, evita ciclo) para que la proyeccion nunca quede obsoleta
cuando el mundo real cambia.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import text as _text
from sqlalchemy.orm import Session

from app.models import (
    ControlImplementation, InitiativeControlTarget, InitiativeLogEntry,
    InitiativeRiskLink, Risk, RiskStatus, StrategicInitiative, risk_control_table,
)
from app.services.risk_recalc_service import control_payload, get_context, get_matrix, residual_from_payloads
from app.services.threat_knowledge import controls_for_threat

logger = logging.getLogger(__name__)


def log_system_event(db: Session, initiative_id: int, text: str) -> None:
    """Crea una entrada de bitacora sin autor (sistema/IA). No hace commit."""
    initiative = db.get(StrategicInitiative, initiative_id)
    org_id = initiative.organization_id if initiative else None
    db.add(InitiativeLogEntry(
        organization_id=org_id, initiative_id=initiative_id,
        entry_type="system", text=text, author_id=None,
    ))


def auto_link_risks(db: Session, initiative: StrategicInitiative) -> int:
    """Deriva los riesgos afectados por la iniciativa a partir de sus controles
    objetivo. Determinista: no llama a IA. Devuelve el numero de links creados.

    Crea links origin='auto' para los riesgos derivados que no existan y
    elimina los 'auto' que ya no se deriven de ningun control objetivo (los
    manuales/ai_import/ai_draft nunca se tocan aqui).
    """
    org_id = initiative.organization_id
    target_impl_ids = [ct.implementation_id for ct in initiative.control_targets]

    # Todos los links existentes (cualquier origen): un riesgo ya vinculado
    # manualmente/IA no debe generar un duplicado 'auto' (uq_initiative_risk)
    existing_links = db.query(InitiativeRiskLink).filter(
        InitiativeRiskLink.initiative_id == initiative.id,
    ).all()
    existing_by_risk = {link.risk_id: link for link in existing_links}
    existing_auto = {link.risk_id: link for link in existing_links if link.origin == "auto"}

    if not target_impl_ids:
        for link in existing_auto.values():
            db.delete(link)
        db.flush()
        return 0

    open_risks = db.query(Risk).filter(
        Risk.organization_id == org_id, Risk.status != RiskStatus.CLOSED,
    ).all()
    open_risk_ids = {r.id for r in open_risks}
    risk_by_id = {r.id: r for r in open_risks}

    ctx = get_context(db, org_id)
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3

    derived_risk_ids: set[int] = set()

    # 1. Directos: el control objetivo ya mitiga formalmente el riesgo
    direct_rows = db.query(risk_control_table.c.risk_id).filter(
        risk_control_table.c.control_implementation_id.in_(target_impl_ids)
    ).distinct().all()
    derived_risk_ids |= ({rid for (rid,) in direct_rows} & open_risk_ids)

    # 2. Por catalogo: la amenaza del riesgo tiene entre sus controles
    # candidatos alguno de los codigos objetivo (solo riesgos sobre apetito,
    # para no llenar de links riesgos que ya estan en verde)
    target_impls = db.query(ControlImplementation).filter(
        ControlImplementation.id.in_(target_impl_ids)
    ).all()
    target_codes = {
        ci.control.code.strip().lstrip("A.").strip()
        for ci in target_impls if ci.control and ci.control.code
    }
    if target_codes:
        for risk in open_risks:
            if risk.id in derived_risk_ids:
                continue
            if (risk.residual_level or 0) <= appetite:
                continue
            threat = risk.threat
            if not threat or not threat.code:
                continue
            candidate_codes = {c["code"] for c in controls_for_threat(db, org_id, threat.code)}
            if target_codes & candidate_codes:
                derived_risk_ids.add(risk.id)

    created = 0
    for rid in derived_risk_ids:
        if rid in existing_by_risk:
            continue  # ya vinculado (auto, manual o IA): no duplicar
        risk = risk_by_id.get(rid)
        db.add(InitiativeRiskLink(
            organization_id=org_id, initiative_id=initiative.id, risk_id=rid,
            origin="auto", baseline_residual_level=risk.residual_level if risk else None,
        ))
        created += 1

    for rid, link in existing_auto.items():
        if rid not in derived_risk_ids:
            db.delete(link)

    db.flush()
    return created


def project_initiative(db: Session, initiative: StrategicInitiative) -> dict:
    """Simula el residual de cada riesgo vinculado asumiendo que los controles
    objetivo alcanzan su madurez objetivo. Usa el mismo motor que el residual
    real (residual_from_payloads); NUNCA escribe en el riesgo, solo en el link."""
    matrix = get_matrix(db, initiative.organization_id)
    target_by_impl = {ct.implementation_id: ct.target_maturity for ct in initiative.control_targets}

    results = []
    total_points = 0
    now = datetime.now(timezone.utc)

    for link in initiative.risk_links:
        risk = link.risk
        if not risk:
            continue
        rows = db.execute(
            _text("SELECT control_implementation_id, contribution FROM risk_controls WHERE risk_id = :rid"),
            {"rid": risk.id},
        ).fetchall()
        contrib_map = {row[0]: (row[1] if row[1] is not None else 1.0) for row in rows}

        controls = []
        for ci in risk.controls:
            payload = control_payload(ci, contrib_map.get(ci.id, 1.0), db=db)
            target = target_by_impl.get(ci.id)
            # "maturity" viene ajustada por calidad de evidencia actual (escala
            # distinta de target_maturity, que es CMM en bruto 0..5). Si la
            # iniciativa promete subir la madurez en bruto por encima de la
            # actual, el what-if asume que al alcanzarla habra evidencia de
            # calidad razonable (no tiene sentido penalizar hoy una evidencia
            # que el proyecto aun no ha producido). Una iniciativa nunca
            # empeora un control: si el objetivo no supera lo ya alcanzado,
            # el payload queda intacto.
            if target is not None and target > payload["maturity_raw"]:
                payload["maturity_raw"] = target
                payload["maturity"] = float(target)
            controls.append(payload)

        _, _, _, projected_level = residual_from_payloads(risk, controls, matrix)
        link.projected_residual_level = projected_level
        link.projected_at = now
        if link.baseline_residual_level is None:
            link.baseline_residual_level = risk.residual_level

        baseline = link.baseline_residual_level if link.baseline_residual_level is not None else projected_level
        results.append({
            "risk_id": risk.id, "risk_code": risk.code,
            "baseline": baseline, "current": risk.residual_level, "projected": projected_level,
        })
        total_points += max(0, (baseline or 0) - projected_level)

    db.flush()
    return {"risks": results, "projected_reduction_points": total_points}


def verify_initiative(db: Session, initiative: StrategicInitiative) -> dict:
    """Al completar una iniciativa: sella lo alcanzado (madurez real, residual
    real) y compara contra el objetivo/proyeccion. El gap queda visible —
    nunca se oculta ni se fuerza a que "cuadre"."""
    controls_total = 0
    controls_met = 0
    gaps: list[dict] = []

    for ct in initiative.control_targets:
        controls_total += 1
        impl = ct.implementation
        achieved = impl.maturity if impl else None
        ct.achieved_maturity = achieved
        if achieved is not None and achieved >= ct.target_maturity:
            controls_met += 1
        else:
            code = impl.control.code if impl and impl.control else "?"
            gaps.append({"type": "control", "code": code,
                        "target": ct.target_maturity, "achieved": achieved})

    risks_total = 0
    risks_met = 0
    for link in initiative.risk_links:
        risk = link.risk
        achieved = risk.residual_level if risk else None
        link.achieved_residual_level = achieved
        projected = link.projected_residual_level
        if projected is None:
            continue  # no evaluable: nunca se proyecto (p.ej. sin control targets)
        risks_total += 1
        if achieved is not None and achieved <= projected:
            risks_met += 1
        else:
            gaps.append({"type": "risk", "code": risk.code if risk else "?",
                        "projected": projected, "achieved": achieved})

    result = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "controls": {"total": controls_total, "met": controls_met},
        "risks": {"total": risks_total, "met": risks_met},
        "gaps": gaps,
    }
    initiative.verification = result
    log_system_event(
        db, initiative.id,
        f"Verificacion de cierre: {controls_met}/{controls_total} controles alcanzaron "
        f"la madurez objetivo; {risks_met}/{risks_total} riesgos quedaron en o por debajo "
        f"del residual proyectado.",
    )
    db.flush()
    return result


def reproject_for_impls(db: Session, impl_ids: list[int]) -> int:
    """Reproyecta las iniciativas activas que tengan alguno de estos controles
    como objetivo, tras un recalculo real (madurez/evidencia/NC/CCM cambiaron).
    Se invoca desde risk_recalc_service.recalc_risks_for_impls."""
    if not impl_ids:
        return 0
    initiative_ids = [
        iid for (iid,) in db.query(InitiativeControlTarget.initiative_id)
        .filter(InitiativeControlTarget.implementation_id.in_(impl_ids))
        .distinct().all()
    ]
    if not initiative_ids:
        return 0
    initiatives = db.query(StrategicInitiative).filter(
        StrategicInitiative.id.in_(initiative_ids),
        StrategicInitiative.status.in_(["approved", "in_progress"]),
    ).all()
    for ini in initiatives:
        try:
            project_initiative(db, ini)
        except Exception:
            logger.exception("reproject_for_impls: fallo en iniciativa id=%s", ini.id)
    return len(initiatives)


def compute_burndown(db: Session, org_id: int | None) -> dict:
    """Historico real (RiskSnapshot mensual) + curva proyectada desde las
    iniciativas activas. Evita doble conteo: si dos iniciativas comparten un
    riesgo, se usa solo la mejor proyeccion de ese riesgo."""
    from app.models import RiskSnapshot

    ctx = get_context(db, org_id)
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3

    since = datetime.now(timezone.utc) - timedelta(days=18 * 30)
    snapshots = db.query(RiskSnapshot).filter(
        RiskSnapshot.organization_id == org_id,
        RiskSnapshot.snapshot_date >= since,
    ).all()
    by_month: dict[str, dict] = defaultdict(lambda: {"total_residual": 0, "above_appetite": 0})
    for s in snapshots:
        month = s.snapshot_date.strftime("%Y-%m")
        by_month[month]["total_residual"] += s.residual_level or 0
        if (s.residual_level or 0) > appetite:
            by_month[month]["above_appetite"] += 1
    history = [{"month": m, **v} for m, v in sorted(by_month.items())]

    initiatives = db.query(StrategicInitiative).filter(
        StrategicInitiative.organization_id == org_id,
        StrategicInitiative.status.in_(["approved", "in_progress"]),
        StrategicInitiative.target_date.isnot(None),
    ).all()

    current_total = sum(
        r.residual_level or 0 for r in
        db.query(Risk).filter(Risk.organization_id == org_id, Risk.status != RiskStatus.CLOSED).all()
    )

    best_by_risk: dict[int, dict] = {}
    for ini in initiatives:
        month = ini.target_date.strftime("%Y-%m")
        for link in ini.risk_links:
            if link.baseline_residual_level is None or link.projected_residual_level is None:
                continue
            cur = best_by_risk.get(link.risk_id)
            if cur is None or link.projected_residual_level < cur["projected"]:
                best_by_risk[link.risk_id] = {
                    "month": month, "baseline": link.baseline_residual_level,
                    "projected": link.projected_residual_level,
                }

    reduction_by_month: dict[str, int] = defaultdict(int)
    for v in best_by_risk.values():
        reduction_by_month[v["month"]] += max(0, v["baseline"] - v["projected"])

    projected = []
    running_total = current_total
    for month in sorted(reduction_by_month.keys()):
        running_total -= reduction_by_month[month]
        projected.append({"month": month, "total_residual": max(0, running_total)})

    return {"history": history, "projected": projected, "appetite_line": appetite}


def _health_rank(health: str) -> int:
    return {"ok": 0, "at_risk": 1, "blocked": 2}.get(health, 0)


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def refresh_initiative_health(db: Session, org_id: int | None = None) -> int:
    """Recalcula la salud (ok/at_risk/blocked) de las iniciativas activas a
    partir de senales objetivas — nunca la marca una persona. Si la salud
    EMPEORA, registra el motivo en la bitacora y alerta al owner de la org
    (Teams/email/Power Automate) si hay algun canal configurado.

    Reglas (>=2 motivos = blocked, 1 = at_risk, 0 = ok):
      - target_date vencida y status != completed
      - sin actividad (bitacora humana, tarea, OKR) en los ultimos 30 dias
      - >30% de las tareas de la iniciativa vencidas
      - algun OKR con confidence=low y target_date a menos de 60 dias
      - progreso < 20% con >60% del plazo (start->target) consumido
    """
    from app.models import InitiativeObjective, TreatmentTask
    from app.services import notification_channels

    now = datetime.now(timezone.utc)
    query = db.query(StrategicInitiative).filter(
        StrategicInitiative.status.in_(["approved", "in_progress"])
    )
    if org_id is not None:
        query = query.filter(StrategicInitiative.organization_id == org_id)
    initiatives = query.all()

    updated = 0
    for ini in initiatives:
        reasons: list[str] = []

        target_date = _aware(ini.target_date)
        if target_date and target_date < now:
            reasons.append("Fecha objetivo vencida")

        tasks = db.query(TreatmentTask).filter(TreatmentTask.initiative_id == ini.id).all()
        objectives = ini.objectives or []

        last_activity_candidates = [_aware(ini.updated_at)]
        recent_human_log = (
            db.query(InitiativeLogEntry.created_at)
            .filter(InitiativeLogEntry.initiative_id == ini.id, InitiativeLogEntry.author_id.isnot(None))
            .order_by(InitiativeLogEntry.created_at.desc()).first()
        )
        if recent_human_log:
            last_activity_candidates.append(_aware(recent_human_log[0]))
        last_activity_candidates.extend(_aware(t.updated_at) for t in tasks)
        last_activity_candidates.extend(_aware(o.updated_at) for o in objectives)
        last_activity_candidates = [d for d in last_activity_candidates if d]
        last_activity = max(last_activity_candidates) if last_activity_candidates else None
        if last_activity and (now - last_activity).days > 30:
            reasons.append("Sin actividad en 30 dias")

        if tasks:
            overdue = sum(
                1 for t in tasks
                if t.due_date and str(getattr(t.status, "value", t.status)).lower() != "done"
                and _aware(t.due_date) < now
            )
            if overdue / len(tasks) > 0.3:
                reasons.append("Tareas vencidas")

        if any(
            o.confidence == "low" and _aware(o.target_date)
            and 0 <= (_aware(o.target_date) - now).days < 60
            for o in objectives
        ):
            reasons.append("OKR en riesgo")

        start_date = _aware(ini.start_date)
        if start_date and target_date:
            total = (target_date - start_date).total_seconds()
            elapsed = (now - start_date).total_seconds()
            if total > 0 and elapsed / total > 0.6 and (ini.progress or 0) < 20:
                reasons.append("Progreso insuficiente")

        new_health = "ok" if not reasons else ("at_risk" if len(reasons) == 1 else "blocked")
        old_health = ini.health
        ini.health = new_health
        ini.health_reasons = reasons or None
        updated += 1

        if _health_rank(new_health) > _health_rank(old_health):
            log_system_event(
                db, ini.id,
                f"La salud paso de '{old_health}' a '{new_health}': {', '.join(reasons)}.",
            )
            try:
                from app.models import EmailSettings, RiskContext
                cfg = db.query(EmailSettings).filter_by(organization_id=ini.organization_id).first()
                if notification_channels.has_any_channel(cfg):
                    ctx = db.query(RiskContext).filter_by(organization_id=ini.organization_id).first()
                    org_name = ctx.organization_name if ctx else "Organizacion"
                    recipient = ini.owner.email if ini.owner else None
                    notification_channels.dispatch_alert(
                        db, cfg, org_name, recipient,
                        subject=f"Iniciativa {ini.code} en estado '{new_health}'",
                        summary_text=f"{ini.title}: {', '.join(reasons)}",
                        event="initiative_health_degraded",
                        fields={"code": ini.code, "title": ini.title, "health": new_health, "reasons": reasons},
                    )
            except Exception:
                logger.exception("refresh_initiative_health: fallo alerta org=%s", ini.organization_id)

    db.commit()
    return updated


def send_initiative_digest(db: Session) -> dict:
    """Digest mensual al comite por organizacion: iniciativas en riesgo/bloqueadas
    con motivos, reduccion proyectada vs conseguida y riesgos sobre apetito sin
    cobertura. Nunca envia si no hay nada relevante que decir."""
    from app.models import EmailSettings, Organization, RiskContext
    from app.services import notification_channels

    sent = 0
    orgs = db.query(Organization).filter(Organization.is_active.is_(True)).all()
    for org in orgs:
        initiatives = db.query(StrategicInitiative).filter(
            StrategicInitiative.organization_id == org.id,
            StrategicInitiative.status.in_(["approved", "in_progress"]),
        ).all()
        problematic = [i for i in initiatives if i.health in ("at_risk", "blocked")]

        ctx = db.query(RiskContext).filter_by(organization_id=org.id).first()
        appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3
        covered_risk_ids = {link.risk_id for i in initiatives for link in i.risk_links}
        open_risks = db.query(Risk).filter(
            Risk.organization_id == org.id, Risk.status != RiskStatus.CLOSED,
        ).all()
        uncovered = sum(
            1 for r in open_risks
            if (r.residual_level or 0) > appetite and r.id not in covered_risk_ids
        )

        projected_points = 0
        achieved_points = 0
        for i in initiatives:
            for link in i.risk_links:
                if link.baseline_residual_level is None or link.projected_residual_level is None:
                    continue
                projected_points += max(0, link.baseline_residual_level - link.projected_residual_level)
                risk = link.risk
                current = risk.residual_level if risk else link.baseline_residual_level
                achieved_points += max(0, link.baseline_residual_level - (current or 0))

        if not problematic and uncovered == 0 and projected_points == 0:
            continue  # nada relevante que reportar esta org

        cfg = db.query(EmailSettings).filter_by(organization_id=org.id).first()
        if not notification_channels.has_any_channel(cfg):
            continue

        lines = []
        if problematic:
            lines.append(f"{len(problematic)} iniciativa(s) en riesgo o bloqueadas:")
            for i in problematic[:10]:
                lines.append(f"  - {i.code} {i.title}: {', '.join(i.health_reasons or [])}")
        if uncovered:
            lines.append(f"{uncovered} riesgo(s) sobre apetito sin cobertura del Plan Director.")
        lines.append(f"Reduccion de riesgo: {projected_points} puntos proyectados, {achieved_points} conseguidos.")
        summary_text = "\n".join(lines)

        org_name = ctx.organization_name if ctx else org.name
        result = notification_channels.dispatch_alert(
            db, cfg, org_name, None,
            subject=f"Plan Director — resumen mensual ({org_name})",
            summary_text=summary_text,
            event="initiative_monthly_digest",
            fields={"at_risk": len(problematic), "uncovered": uncovered,
                    "projected_points": projected_points, "achieved_points": achieved_points},
        )
        if any(v for v in result.values()):
            sent += 1

    db.commit()
    return {"sent": sent, "orgs_evaluated": len(orgs)}
