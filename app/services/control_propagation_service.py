"""Propagacion inteligente de controles a riesgos candidatos.

Flujo de dos pasos:
  Paso 1 (sin IA): recalcular residual de riesgos YA vinculados al control.
                   Solo matematica, cero tokens.
  Paso 2 (IA):    encontrar riesgos candidatos no vinculados, llamar a Claude
                  con un lote maximo de 50 riesgos, vincular los que apliquen
                  y recalcular su residual.

Ahorro estimado: 1 llamada con ~50 riesgos vs 300 llamadas para 3000 activos.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import (
    AiCallLog, AiConfig, Control, ControlImplementation, ControlStatus,
    Risk, RiskContext, RiskStatus, Threat, TreatmentOption,
    risk_control_table,
)
from app.services.risk_engine import calc_level, calc_residual

logger = logging.getLogger(__name__)

_MAX_CANDIDATES = 50  # riesgos candidatos maximos por llamada IA


# ---------- helpers ----------

def _get_api_key(db: Session, org_id: int | None) -> str | None:
    cfg = db.query(AiConfig).filter_by(organization_id=org_id).first()
    if cfg and cfg.api_key_encrypted:
        try:
            from cryptography.fernet import Fernet
            from app.services.document_service import _fernet_key
            return Fernet(_fernet_key()).decrypt(cfg.api_key_encrypted.encode()).decode()
        except Exception:
            pass
    from app.config import settings
    return settings.anthropic_api_key or None


def _get_model(db: Session, org_id: int | None) -> str:
    cfg = db.query(AiConfig).filter_by(organization_id=org_id).first()
    return cfg.model if cfg and cfg.model else "claude-haiku-4-5"


def _strip_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```", 2)
        inner = parts[1] if len(parts) > 1 else raw
        if inner.startswith("json"):
            inner = inner[4:]
        raw = inner.rsplit("```", 1)[0].strip()
    return raw


# ---------- Paso 1: recalculo matematico sin IA ----------

def recalc_linked_risks(db: Session, impl_id: int, org_id: int) -> int:
    """Recalcula residual de riesgos ya vinculados. Devuelve numero de riesgos actualizados."""
    risk_ids = [
        row[0] for row in db.execute(
            text("SELECT risk_id FROM risk_controls WHERE control_implementation_id = :cid"),
            {"cid": impl_id},
        ).fetchall()
    ]
    if not risk_ids:
        return 0

    ctx = db.query(RiskContext).filter_by(organization_id=org_id).first()
    matrix = ctx.risk_matrix if ctx else None
    appetite = (ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3)

    risks = db.query(Risk).filter(
        Risk.id.in_(risk_ids),
        Risk.organization_id == org_id,
        Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
    ).all()

    updated = 0
    for risk in risks:
        controls_dicts = [
            {"maturity": c.maturity or 0, "contribution": 1.0}
            for c in risk.controls
        ]
        rl, rc, rlev = calc_residual(
            risk.inherent_likelihood, risk.inherent_consequence,
            controls_dicts, matrix,
        )
        risk.residual_likelihood = rl
        risk.residual_consequence = rc
        risk.residual_level = rlev

        if rlev <= appetite and risk.status == RiskStatus.IDENTIFIED:
            risk.treatment_option = TreatmentOption.RETENTION

        updated += 1

    if updated:
        db.commit()
    return updated


# ---------- Paso 2: IA para candidatos ----------

def _candidate_risks(
    db: Session, impl_id: int, org_id: int, ctrl: ControlImplementation
) -> list[Risk]:
    """Devuelve riesgos candidatos: no vinculados al control, con residual > 0, activos."""
    already_linked_ids = {
        row[0] for row in db.execute(
            text("SELECT risk_id FROM risk_controls WHERE control_implementation_id = :cid"),
            {"cid": impl_id},
        ).fetchall()
    }

    base_ctrl = ctrl.control
    theme = base_ctrl.theme if base_ctrl else None
    properties = base_ctrl.properties if base_ctrl else []
    ctrl_type = base_ctrl.control_type if base_ctrl else []

    # Filtrar amenazas que se alinean con el tema/propiedades del control
    threat_theme_map = {
        "organizational": ["D", "A"],          # amenazas deliberadas + accidentales
        "people": ["D", "A"],
        "physical": ["E", "D"],                 # fisicas + ambientales
        "technological": ["D", "A", "E"],
    }
    allowed_origins = threat_theme_map.get(theme or "", ["D", "A", "E"])

    # Mapear propiedades ISO 27002 a dimensiones CIA afectadas
    prop_to_cia = {
        "confidentiality": "C",
        "integrity": "I",
        "availability": "A",
        "authenticity": "Auth",
        "accountability": "Acc",
    }
    ctrl_cia = {prop_to_cia.get(p, p.upper()[:1]) for p in (properties or [])}

    # Obtener candidatos
    query = db.query(Risk).filter(
        Risk.organization_id == org_id,
        Risk.status.notin_([RiskStatus.CLOSED, RiskStatus.ACCEPTED]),
        Risk.residual_level > 0,  # ya en 0 no tiene sentido mitigar mas
    )
    if already_linked_ids:
        query = query.filter(Risk.id.notin_(already_linked_ids))

    # Priorizar los de nivel residual mas alto (mas impacto potencial)
    candidates = query.order_by(Risk.residual_level.desc()).limit(200).all()

    # Filtrar por alineacion CIA del control vs lo que afecta la amenaza
    def _matches(risk: Risk) -> bool:
        threat = risk.threat
        if not threat:
            return True
        # Verificar origen de amenaza
        if threat.origin and threat.origin.value not in allowed_origins:
            return False
        # Verificar dimensiones CIA afectadas
        if ctrl_cia and threat.affects:
            affects = threat.affects if isinstance(threat.affects, list) else []
            if not any(a in ctrl_cia for a in affects):
                return False
        return True

    filtered = [r for r in candidates if _matches(r)]

    # Si el control es "preventive" priorizar riesgos con likelihood alto
    if "preventive" in (ctrl_type or []):
        filtered.sort(key=lambda r: -r.inherent_likelihood)
    else:
        filtered.sort(key=lambda r: -r.residual_level)

    return filtered[:_MAX_CANDIDATES]


_PROPAGATE_SYSTEM = """Eres un experto ISO/IEC 27002:2022 y ISO/IEC 27005:2018.
Evalua si el control dado mitiga cada uno de los riesgos de la lista.

Para cada riesgo donde el control SEA RELEVANTE devuelve la contribucion estimada:
- contribution: 0.0 = no aplica, 0.1-0.3 = mitigacion baja, 0.4-0.6 = media, 0.7-0.9 = alta, 1.0 = control primario

Devuelve UNICAMENTE JSON valido con esta estructura:
{"results":[{"risk_id":<int>,"contribution":<0.0-1.0>,"rationale":"<max 70 chars>"}]}

Solo incluye riesgos con contribution > 0. Si el control no aplica a ninguno, devuelve {"results":[]}."""


def propagate_with_ai(
    db: Session, impl_id: int, org_id: int
) -> dict:
    """Paso 2: IA detecta riesgos candidatos, los vincula y recalcula residual."""
    impl = db.get(ControlImplementation, impl_id)
    if not impl:
        return {"ok": False, "error": "Control no encontrado"}

    api_key = _get_api_key(db, org_id)
    if not api_key:
        return {"ok": False, "error": "Sin API key configurada"}

    candidates = _candidate_risks(db, impl_id, org_id, impl)
    if not candidates:
        return {"ok": True, "linked": 0, "recalculated": 0,
                "message": "No hay riesgos candidatos sin vincular"}

    base_ctrl = impl.control
    ctrl_info = (
        f"Control: {base_ctrl.code if base_ctrl else 'N/A'} — {impl.name}\n"
        f"Descripcion: {(base_ctrl.description or impl.description or '')[:300]}\n"
        f"Tema: {base_ctrl.theme if base_ctrl else 'N/A'}\n"
        f"Tipo: {', '.join(base_ctrl.control_type or []) if base_ctrl else 'N/A'}\n"
        f"Propiedades: {', '.join(base_ctrl.properties or []) if base_ctrl else 'N/A'}\n"
        f"Estado: {impl.status.value if impl.status else 'N/A'} — Madurez: {impl.maturity}/5"
    )

    risks_info = []
    for r in candidates:
        threat_name = r.threat.name if r.threat else "desconocida"
        asset_name = r.asset.name if r.asset else "desconocido"
        risks_info.append(
            f"ID:{r.id} | Amenaza:{threat_name} | Activo:{asset_name[:40]} "
            f"| InhL:{r.inherent_likelihood} InhC:{r.inherent_consequence} "
            f"| ResL:{r.residual_likelihood} ResC:{r.residual_consequence}"
        )

    user_content = (
        f"CONTROL A EVALUAR:\n{ctrl_info}\n\n"
        f"RIESGOS CANDIDATOS ({len(candidates)}):\n" + "\n".join(risks_info)
    )

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    model = _get_model(db, org_id)

    msg = client.messages.create(
        model=model,
        max_tokens=16384,
        system=_PROPAGATE_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )

    db.add(AiCallLog(
        organization_id=org_id,
        call_type="control_propagation",
        prompt_tokens=msg.usage.input_tokens,
        completion_tokens=msg.usage.output_tokens,
        model=model,
        anonymized=False,
        response_summary=f"Control propagation impl_id={impl_id}: {len(candidates)} candidates",
    ))

    result = json.loads(_strip_fence(msg.content[0].text))
    items = result.get("results", [])

    # Vincular nuevos controles y recalcular residual
    ctx = db.query(RiskContext).filter_by(organization_id=org_id).first()
    matrix = ctx.risk_matrix if ctx else None
    appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3

    candidate_by_id = {r.id: r for r in candidates}
    linked = 0

    for item in items:
        risk_id = item.get("risk_id")
        contribution = float(item.get("contribution", 0))
        if not risk_id or contribution <= 0:
            continue

        risk = candidate_by_id.get(risk_id) or db.get(Risk, risk_id)
        if not risk or risk.organization_id != org_id:
            continue

        # Insertar en junction table si no existe
        exists = db.execute(
            text("SELECT 1 FROM risk_controls WHERE risk_id=:rid AND control_implementation_id=:cid"),
            {"rid": risk_id, "cid": impl_id},
        ).fetchone()
        if not exists:
            db.execute(
                text("INSERT INTO risk_controls (risk_id, control_implementation_id, contribution) "
                     "VALUES (:rid, :cid, :contrib)"),
                {"rid": risk_id, "cid": impl_id, "contrib": contribution},
            )
            linked += 1

        # Recalcular residual con el nuevo control incluido
        db.expire(risk, ["controls"])  # refrescar la relacion
        db.flush()
        controls_dicts = [
            {"maturity": c.maturity or 0, "contribution": 1.0}
            for c in risk.controls
        ]
        rl, rc, rlev = calc_residual(
            risk.inherent_likelihood, risk.inherent_consequence,
            controls_dicts, matrix,
        )
        risk.residual_likelihood = rl
        risk.residual_consequence = rc
        risk.residual_level = rlev

        if rlev <= appetite and risk.status == RiskStatus.IDENTIFIED:
            risk.treatment_option = TreatmentOption.RETENTION

    db.commit()

    return {
        "ok": True,
        "candidates_evaluated": len(candidates),
        "linked": linked,
        "recalculated": linked,
        "tokens_used": msg.usage.input_tokens + msg.usage.output_tokens,
    }


# ---------- Punto de entrada principal ----------

def propagate_control(db: Session, impl_id: int, org_id: int) -> dict:
    """Propaga el control a riesgos candidatos en 2 pasos."""
    # Paso 1: recalculo matematico sin IA
    step1 = recalc_linked_risks(db, impl_id, org_id)

    # Paso 2: IA para candidatos no vinculados
    step2 = propagate_with_ai(db, impl_id, org_id)

    if not step2.get("ok"):
        return {
            "ok": False,
            "step1_recalculated": step1,
            "error": step2.get("error"),
        }

    return {
        "ok": True,
        "step1_recalculated": step1,
        "step2_candidates_evaluated": step2["candidates_evaluated"],
        "step2_linked": step2["linked"],
        "tokens_used": step2.get("tokens_used", 0),
        "message": (
            f"Paso 1: {step1} riesgos vinculados recalculados. "
            f"Paso 2: {step2['candidates_evaluated']} candidatos evaluados, "
            f"{step2['linked']} nuevos vínculos creados."
        ),
    }
