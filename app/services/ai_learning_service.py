"""Aprendizaje del agente IA a partir de las decisiones del usuario.

No hay reentrenamiento de modelos: el aprendizaje es in-context. El ciclo:

  1. CAPTURA — los routers registran senales (`record_signal`) cuando el
     usuario toma decisiones: acepta o escala riesgos, corrige los valores
     que propuso la IA, borra riesgos generados, aprueba o rechaza
     evaluaciones de proveedor, revincula controles...
  2. DESTILACION — un job nocturno agrega las senales por organizacion en
     lecciones deterministas con umbral minimo de ocurrencias (nada de
     conclusiones con 1 dato) y las persiste en RiskContext.ai_learned_lessons.
  3. INYECCION — los prompts de analisis (activos, batch, TPRM) incluyen la
     seccion "PATRONES DE DECISION DE LA ORGANIZACION" con esas lecciones:
     el agente propone cada vez mas alineado con el criterio real del CISO.

Las lecciones son ADVISORY: solo tocan el lado del prompt. El motor
determinista de residuales no se modifica nunca por esta via. El admin puede
ver y resetear lo aprendido (GET/DELETE /api/ai/learning).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Minimo de senales coincidentes para emitir una leccion
_MIN_SIGNALS = 3
_MAX_LESSONS = 12


def record_signal(db: Session, org_id: Optional[int], signal_type: str,
                  context: dict, entity_ref: str | None = None,
                  user_id: int | None = None, commit: bool = False) -> None:
    """Registra una senal de decision. Best-effort: nunca lanza al caller."""
    if not org_id:
        return
    try:
        from app.models import AiDecisionSignal
        db.add(AiDecisionSignal(
            organization_id=org_id,
            signal_type=signal_type,
            entity_ref=(entity_ref or "")[:64] or None,
            context=context or {},
            user_id=user_id,
        ))
        if commit:
            db.commit()
        else:
            db.flush()
    except Exception:
        logger.debug("ai_learning: no se pudo registrar senal %s", signal_type,
                     exc_info=True)


def signal_risk_decision(db: Session, risk, decision: str,
                         user_id: int | None = None, extra: dict | None = None) -> None:
    """Helper para senales sobre un riesgo (acepta/escala/edita/borra)."""
    try:
        ctx = {
            "asset_type": (risk.asset.asset_type.value
                           if risk.asset and risk.asset.asset_type else None),
            "threat_code": risk.threat.code if risk.threat else None,
            "threat_category": risk.threat.category if risk.threat else None,
            "residual_level": risk.residual_level,
            "inherent_level": risk.inherent_level,
            "ai_generated": bool(risk.ai_generated),
        }
        if extra:
            ctx.update(extra)
        record_signal(db, risk.organization_id, decision, ctx,
                      entity_ref=risk.code, user_id=user_id)
    except Exception:
        logger.debug("ai_learning: signal_risk_decision fallo", exc_info=True)


# ---------- Destilacion ----------

def distill_lessons(db: Session, org_id: int) -> list[dict]:
    """Agrega las senales de la org en lecciones deterministas.

    Cada leccion: {text, kind, count, updated_at}. Umbral _MIN_SIGNALS para
    no generalizar desde anecdotas.
    """
    from app.models import AiDecisionSignal
    signals = (
        db.query(AiDecisionSignal)
        .filter(AiDecisionSignal.organization_id == org_id)
        .order_by(AiDecisionSignal.id.desc())
        .limit(2000)
        .all()
    )
    if not signals:
        return []

    lessons: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    def _add(text: str, kind: str, count: int) -> None:
        lessons.append({"text": text, "kind": kind, "count": count, "updated_at": now})

    # 1. Aceptacion de riesgos por categoria de amenaza y nivel residual
    accepted: dict[str, list[int]] = {}
    escalated: dict[str, list[int]] = {}
    for s in signals:
        ctx = s.context or {}
        cat = ctx.get("threat_category") or "general"
        lvl = ctx.get("residual_level")
        if s.signal_type == "risk_accepted" and lvl is not None:
            accepted.setdefault(cat, []).append(lvl)
        elif s.signal_type == "risk_escalated" and lvl is not None:
            escalated.setdefault(cat, []).append(lvl)
    for cat, levels in accepted.items():
        if len(levels) >= _MIN_SIGNALS:
            _add(
                f"La organizacion acepta riesgos de categoria '{cat}' hasta nivel "
                f"residual {max(levels)} (aceptados: {len(levels)}, media "
                f"{sum(levels) / len(levels):.1f}). Propon 'retention' en escenarios similares.",
                "risk_acceptance", len(levels),
            )
    for cat, levels in escalated.items():
        if len(levels) >= _MIN_SIGNALS:
            _add(
                f"La organizacion trata activamente los riesgos de categoria '{cat}' "
                f"desde nivel {min(levels)} ({len(levels)} escalados a tratamiento). "
                f"No propongas 'retention' alegremente en esta categoria.",
                "risk_escalation", len(levels),
            )

    # 2. Correcciones sistematicas de los valores que propone la IA
    lik_deltas: dict[str, list[int]] = {}
    con_deltas: dict[str, list[int]] = {}
    for s in signals:
        if s.signal_type != "ai_risk_edited":
            continue
        ctx = s.context or {}
        cat = ctx.get("threat_category") or "general"
        if ctx.get("likelihood_delta") is not None:
            lik_deltas.setdefault(cat, []).append(int(ctx["likelihood_delta"]))
        if ctx.get("consequence_delta") is not None:
            con_deltas.setdefault(cat, []).append(int(ctx["consequence_delta"]))
    for cat, deltas in lik_deltas.items():
        if len(deltas) >= _MIN_SIGNALS:
            mean = sum(deltas) / len(deltas)
            if abs(mean) >= 0.5:
                dir_txt = "REDUCE" if mean < 0 else "AUMENTA"
                _add(
                    f"El usuario {dir_txt} sistematicamente la likelihood que propone la IA "
                    f"en amenazas de '{cat}' (media {mean:+.1f} sobre {len(deltas)} correcciones). "
                    f"Calibra en consecuencia.",
                    "likelihood_calibration", len(deltas),
                )
    for cat, deltas in con_deltas.items():
        if len(deltas) >= _MIN_SIGNALS:
            mean = sum(deltas) / len(deltas)
            if abs(mean) >= 0.5:
                dir_txt = "REDUCE" if mean < 0 else "AUMENTA"
                _add(
                    f"El usuario {dir_txt} sistematicamente la consequence que propone la IA "
                    f"en amenazas de '{cat}' (media {mean:+.1f} sobre {len(deltas)} correcciones). "
                    f"Calibra en consecuencia.",
                    "consequence_calibration", len(deltas),
                )

    # 3. Riesgos IA borrados: amenazas que la org considera no aplicables
    deleted: dict[str, int] = {}
    for s in signals:
        if s.signal_type == "ai_risk_deleted":
            key = (s.context or {}).get("threat_code") or "?"
            deleted[key] = deleted.get(key, 0) + 1
    for code, n in deleted.items():
        if n >= _MIN_SIGNALS:
            _add(
                f"El usuario ha borrado {n} veces riesgos generados para la amenaza "
                f"[{code}]: evita proponerla salvo evidencia clara de aplicabilidad.",
                "threat_rejection", n,
            )

    # 4. Decisiones sobre proveedores por tier
    vendor_dec: dict[str, dict[str, int]] = {}
    for s in signals:
        if s.signal_type != "vendor_assessment_decision":
            continue
        ctx = s.context or {}
        tier = str(ctx.get("tier") or "?")
        dec = str(ctx.get("decision") or "?")
        vendor_dec.setdefault(tier, {}).setdefault(dec, 0)
        vendor_dec[tier][dec] += 1
    for tier, decs in vendor_dec.items():
        total = sum(decs.values())
        if total >= _MIN_SIGNALS:
            resumen = ", ".join(f"{d}: {n}" for d, n in sorted(decs.items()))
            _add(
                f"Decisiones historicas sobre proveedores tier {tier}: {resumen}. "
                f"Alinea la exigencia probatoria con este patron.",
                "vendor_decisions", total,
            )

    # 5. Divergencia de calibracion residual (LLM vs motor)
    divs = [
        (s.context or {}) for s in signals
        if s.signal_type == "residual_divergence"
        and (s.context or {}).get("delta_level") is not None
    ]
    if len(divs) >= _MIN_SIGNALS:
        deltas = [int(d["delta_level"]) for d in divs]
        mean = sum(deltas) / len(deltas)
        if abs(mean) >= 1.0:
            dir_txt = ("por ENCIMA (pesimista)" if mean > 0
                       else "por DEBAJO (optimista)")
            _add(
                f"Tus estimaciones de residual quedan de media {abs(mean):.1f} niveles "
                f"{dir_txt} del calculo del motor sobre {len(deltas)} analisis. "
                f"Ajusta la estimacion de contribuciones de controles.",
                "residual_calibration", len(deltas),
            )

    # Ordenar por soporte (mas senales primero) y limitar
    lessons.sort(key=lambda x: -x["count"])
    return lessons[:_MAX_LESSONS]


def refresh_org_lessons(db: Session, org_id: int) -> int:
    """Destila y persiste las lecciones de una org. Devuelve cuantas hay."""
    from app.models import RiskContext
    lessons = distill_lessons(db, org_id)
    ctx = db.query(RiskContext).filter_by(organization_id=org_id).first()
    if ctx is not None:
        ctx.ai_learned_lessons = lessons
    return len(lessons)


def refresh_all_lessons() -> int:
    """Job nocturno: destila lecciones para todas las orgs con senales."""
    from app.database import SessionLocal
    from app.models import AiDecisionSignal
    db = SessionLocal()
    total = 0
    try:
        org_ids = [r[0] for r in db.query(AiDecisionSignal.organization_id).distinct().all()]
        for org_id in org_ids:
            try:
                total += refresh_org_lessons(db, org_id)
            except Exception:
                logger.exception("ai_learning: destilacion fallo org=%s", org_id)
        db.commit()
    finally:
        db.close()
    if total:
        logger.info("ai_learning: %d lecciones destiladas", total)
    return total


# ---------- Inyeccion en prompts ----------

def lessons_block(db: Session, org_id: Optional[int],
                  kinds: tuple[str, ...] | None = None) -> str:
    """Seccion de prompt con las lecciones aprendidas de la org.

    kinds filtra por tipo de leccion (p.ej. solo vendor_decisions para TPRM).
    Devuelve "" si no hay nada aprendido.
    """
    if not org_id:
        return ""
    try:
        from app.models import RiskContext
        ctx = db.query(RiskContext).filter_by(organization_id=org_id).first()
        lessons = (ctx.ai_learned_lessons or []) if ctx else []
        if kinds:
            lessons = [l for l in lessons if l.get("kind") in kinds]
        if not lessons:
            return ""
        lines = [f"- {l['text']}" for l in lessons[:8]]
        return (
            "PATRONES DE DECISION DE LA ORGANIZACION (aprendidos de sus "
            "decisiones reales; usalos para calibrar tus propuestas, no "
            "sustituyen al apetito de riesgo formal):\n" + "\n".join(lines)
        )
    except Exception:
        return ""
