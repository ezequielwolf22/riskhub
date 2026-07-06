"""Gate de onboarding de proveedores — control total por el equipo de ciberseguridad."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import OnboardingGateConfig, Supplier, User
from app.security import get_current_user, require_admin, require_analyst
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/onboarding-gate", tags=["onboarding-gate"])


# ---------- Configuracion del gate (solo admin) ----------

@router.get("/config")
def get_gate_config(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lang = get_lang(request)
    from app.services.onboarding_gate_service import get_or_create_config
    cfg = get_or_create_config(db, current_user.organization_id)
    return {
        "id": cfg.id,
        "auto_approve_below": cfg.auto_approve_below,
        "manual_review_above": cfg.manual_review_above,
        "bypass_min_role": cfg.bypass_min_role,
        "bypass_requires_justification": cfg.bypass_requires_justification,
        "force_controls_allowed": cfg.force_controls_allowed,
        "sign_off_chain": cfg.sign_off_chain or [],
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
        "updated_by_id": cfg.updated_by_id,
    }


@router.put("/config")
def update_gate_config(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    lang = get_lang(request)
    from app.services.onboarding_gate_service import get_or_create_config
    cfg = get_or_create_config(db, current_user.organization_id)

    if "auto_approve_below" in payload:
        val = int(payload["auto_approve_below"])
        if not 0 <= val <= 100:
            raise HTTPException(400, _t("onboarding_gate.auto_approve_range", lang))
        cfg.auto_approve_below = val

    if "manual_review_above" in payload:
        val = int(payload["manual_review_above"])
        if not 0 <= val <= 100:
            raise HTTPException(400, _t("onboarding_gate.manual_review_range", lang))
        cfg.manual_review_above = val

    if cfg.auto_approve_below >= cfg.manual_review_above:
        raise HTTPException(400, _t("onboarding_gate.threshold_order", lang))

    if "bypass_min_role" in payload:
        if payload["bypass_min_role"] not in ("admin", "analyst"):
            raise HTTPException(400, _t("onboarding_gate.bypass_role_invalid", lang))
        cfg.bypass_min_role = payload["bypass_min_role"]

    if "bypass_requires_justification" in payload:
        cfg.bypass_requires_justification = bool(payload["bypass_requires_justification"])

    if "force_controls_allowed" in payload:
        cfg.force_controls_allowed = bool(payload["force_controls_allowed"])

    if "sign_off_chain" in payload:
        chain = payload["sign_off_chain"]
        if not isinstance(chain, list):
            raise HTTPException(400, _t("onboarding_gate.chain_must_be_list", lang))
        for item in chain:
            if "id" not in item or "label" not in item:
                raise HTTPException(400, _t("onboarding_gate.chain_item_fields", lang))
        cfg.sign_off_chain = chain

    cfg.updated_at = datetime.now(timezone.utc)
    cfg.updated_by_id = current_user.id
    db.commit()

    log_action(db, current_user.id, "update", "onboarding_gate_config", str(cfg.id), {
        "auto_approve_below": cfg.auto_approve_below,
        "manual_review_above": cfg.manual_review_above,
    })
    return {
        "ok": True,
        "id": cfg.id,
        "auto_approve_below": cfg.auto_approve_below,
        "manual_review_above": cfg.manual_review_above,
        "bypass_min_role": cfg.bypass_min_role,
        "bypass_requires_justification": cfg.bypass_requires_justification,
        "force_controls_allowed": cfg.force_controls_allowed,
        "sign_off_chain": cfg.sign_off_chain,
    }


# ---------- Evaluacion del gate por proveedor ----------

@router.get("/{sid}/evaluate")
def evaluate_supplier_gate(
    sid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lang = get_lang(request)
    from app.services.onboarding_gate_service import evaluate_gate, get_or_create_config
    sup = db.get(Supplier, sid)
    if not sup or sup.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("onboarding_gate.supplier_not_found", lang))
    cfg = get_or_create_config(db, current_user.organization_id)
    return evaluate_gate(db, sup, cfg)


# ---------- Override del gate (bypass o force_controls) ----------

@router.post("/{sid}/override")
def apply_gate_override(
    sid: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    from app.services.onboarding_gate_service import apply_override, evaluate_gate, get_or_create_config

    sup = db.get(Supplier, sid)
    if not sup or sup.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("onboarding_gate.supplier_not_found", lang))

    cfg = get_or_create_config(db, current_user.organization_id)
    override_type = payload.get("type")

    # Limpiar override
    if override_type in ("clear", None):
        sup.gate_override_type = None
        sup.gate_override_justification = None
        sup.gate_override_by_id = None
        sup.gate_override_at = None
        if payload.get("clear_forced_signoffs"):
            sup.forced_signoffs = None
        db.commit()
        log_action(db, current_user.id, "gate_override_clear", "supplier", str(sid), {})
        return evaluate_gate(db, sup, cfg)

    if override_type not in ("bypass", "force_controls"):
        raise HTTPException(400, _t("onboarding_gate.override_type_invalid", lang))

    # Comprobar rol minimo para bypass
    if override_type == "bypass":
        required_role = cfg.bypass_min_role or "admin"
        if required_role == "admin" and current_user.role.value not in ("admin", "superadmin"):
            raise HTTPException(403, _t("onboarding_gate.bypass_admin_only", lang))

    # Justificacion obligatoria
    justification = payload.get("justification", "").strip()
    if cfg.bypass_requires_justification and not justification:
        raise HTTPException(400, _t("onboarding_gate.justification_required", lang))

    if override_type == "force_controls" and not cfg.force_controls_allowed:
        raise HTTPException(403, _t("onboarding_gate.force_controls_disabled", lang))

    extra_signoffs = payload.get("extra_signoffs", [])
    result = apply_override(db, sup, override_type, justification, extra_signoffs, current_user)
    log_action(db, current_user.id, f"gate_override_{override_type}", "supplier", str(sid), {
        "justification": justification,
        "extra_signoffs": extra_signoffs,
    })
    return result


# ---------- Decision formal de ciberseguridad ----------

@router.post("/{sid}/decision")
def record_onboarding_decision(
    sid: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    from app.services.onboarding_gate_service import record_decision

    sup = db.get(Supplier, sid)
    if not sup or sup.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("onboarding_gate.supplier_not_found", lang))

    decision = payload.get("decision")
    if decision not in ("approved", "rejected", "conditional"):
        raise HTTPException(400, _t("onboarding_gate.decision_invalid", lang))

    notes = payload.get("notes", "").strip()
    conditions = payload.get("conditions", [])

    if decision == "conditional" and not conditions:
        raise HTTPException(400, _t("onboarding_gate.conditional_needs_conditions", lang))

    result = record_decision(db, sup, decision, notes, conditions, current_user)
    log_action(db, current_user.id, f"onboarding_decision_{decision}", "supplier", str(sid), {
        "notes": notes,
        "conditions_count": len(conditions),
    })

    # Auto-promover a activo si aprobado y firmas completas
    if decision == "approved" and result.get("ready_for_active") and sup.lifecycle_stage == "onboarding":
        sup.lifecycle_stage = "active"
        sup.onboarding_completed_at = datetime.now(timezone.utc)
        db.commit()
        result["auto_promoted"] = True

    # Retorno de decision a Power Automate si el proveedor vino via MS Forms (Via 3)
    try:
        from app.services.msforms_service import notify_pa_decision_bg
        notify_pa_decision_bg(
            supplier_id=sup.id,
            org_id=sup.organization_id,
            decision=decision,
            notes=notes,
            conditions=conditions,
            decided_by_email=current_user.email,
        )
    except Exception:
        pass  # no bloquear la respuesta HTTP por el webhook saliente

    return result


# ---------- Firma de un item de la cadena ----------

@router.patch("/{sid}/sign-off/{sign_off_id}")
def sign_chain_item(
    sid: int,
    sign_off_id: str,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    lang = get_lang(request)
    from app.services.onboarding_gate_service import (
        evaluate_gate, get_or_create_config, sign_chain_item as _sign,
    )

    sup = db.get(Supplier, sid)
    if not sup or sup.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("onboarding_gate.supplier_not_found", lang))

    cfg = get_or_create_config(db, current_user.organization_id)
    chain_def = cfg.sign_off_chain or []
    item_def = next((i for i in chain_def if i["id"] == sign_off_id), None)
    forced = sup.forced_signoffs or []

    if not item_def and sign_off_id not in forced:
        raise HTTPException(404, _t("onboarding_gate.signoff_not_found", lang, id=sign_off_id))

    skipped = bool(payload.get("skipped", False))
    if skipped and item_def and not item_def.get("bypass_allowed", True):
        raise HTTPException(403, _t("onboarding_gate.signoff_no_bypass", lang, id=sign_off_id))

    skip_justification = payload.get("skip_justification", "").strip()
    if skipped and not skip_justification:
        raise HTTPException(400, _t("onboarding_gate.skip_justification_required", lang))

    signed_by = payload.get("signed_by") or current_user.full_name or current_user.email
    doc_id = payload.get("document_id")

    result = _sign(db, sup, sign_off_id, signed_by, current_user.id, doc_id, skipped, skip_justification)
    log_action(db, current_user.id, f"sign_off_{'skip' if skipped else 'sign'}_{sign_off_id}", "supplier", str(sid), {
        "signed_by": signed_by, "skipped": skipped,
    })
    return result


# ---------- Desanclar un sign-off (revertir) ----------

@router.delete("/{sid}/sign-off/{sign_off_id}")
def undo_sign_off(
    sid: int,
    sign_off_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    lang = get_lang(request)
    from sqlalchemy.orm.attributes import flag_modified
    from app.services.onboarding_gate_service import evaluate_gate, get_or_create_config

    sup = db.get(Supplier, sid)
    if not sup or sup.organization_id != current_user.organization_id:
        raise HTTPException(404, _t("onboarding_gate.supplier_not_found", lang))

    chain_state = [s for s in (sup.sign_off_chain_state or []) if s.get("id") != sign_off_id]
    sup.sign_off_chain_state = chain_state
    flag_modified(sup, "sign_off_chain_state")

    # Borrar campos legacy si aplica
    if sign_off_id == "dpa":
        sup.dpa_signed_at = None
        sup.dpa_signed_by = None
    elif sign_off_id == "nda":
        sup.nda_signed_at = None

    db.commit()
    log_action(db, current_user.id, f"sign_off_undo_{sign_off_id}", "supplier", str(sid), {})
    cfg = get_or_create_config(db, current_user.organization_id)
    return evaluate_gate(db, sup, cfg)
