"""Servicio de evaluacion del gate de onboarding de proveedores.

El equipo cyber controla el proceso completo con:
- Umbrales de score TPRM configurables por el admin (0-100)
- Cadena de firmas ordenada con dependencias y score-gates
- Bypass auditado (con justificacion) para flexibilidad operacional
- Forzado de controles adicionales independientemente del score
- Decision formal documentada: aprobado / rechazado / condicional
"""
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

_DEFAULT_SIGN_OFF_CHAIN = [
    {
        "id": "nda",
        "label": "NDA / Acuerdo de confidencialidad",
        "required": False,
        "required_if": None,
        "depends_on": None,
        "score_gate": None,
        "bypass_allowed": True,
    },
    {
        "id": "dpa",
        "label": "DPA (Art. 28 GDPR)",
        "required": False,
        "required_if": "is_data_processor",
        "depends_on": None,
        "score_gate": None,
        "bypass_allowed": True,
    },
    {
        "id": "cross_border",
        "label": "Clausulas transferencia internacional",
        "required": False,
        "required_if": "cross_border_transfers",
        "depends_on": "dpa",
        "score_gate": None,
        "bypass_allowed": True,
    },
    {
        "id": "nis2_addendum",
        "label": "Addendum NIS2 Art. 21",
        "required": False,
        "required_if": "is_nis2",
        "depends_on": None,
        "score_gate": None,
        "bypass_allowed": True,
    },
    {
        "id": "dora_exit",
        "label": "Estrategia de salida DORA Art. 28(8)",
        "required": False,
        "required_if": "is_dora",
        "depends_on": None,
        "score_gate": None,
        "bypass_allowed": True,
    },
    {
        "id": "ciso_approval",
        "label": "Aprobacion CISO",
        "required": False,
        "required_if": None,
        "depends_on": None,
        "score_gate": 60,
        "bypass_allowed": False,
    },
    {
        "id": "contract",
        "label": "Contrato principal firmado",
        "required": False,
        "required_if": None,
        "depends_on": None,
        "score_gate": None,
        "bypass_allowed": True,
    },
]


def get_or_create_config(db, org_id: int):
    """Obtiene la config del gate para la org, creando el default si no existe."""
    from app.models import OnboardingGateConfig
    cfg = db.query(OnboardingGateConfig).filter_by(organization_id=org_id).first()
    if not cfg:
        cfg = OnboardingGateConfig(
            organization_id=org_id,
            auto_approve_below=30,
            manual_review_above=60,
            bypass_min_role="admin",
            bypass_requires_justification=True,
            force_controls_allowed=True,
            sign_off_chain=_DEFAULT_SIGN_OFF_CHAIN,
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    if not cfg.sign_off_chain:
        cfg.sign_off_chain = _DEFAULT_SIGN_OFF_CHAIN
    return cfg


def _item_applicable(item_def: dict, supplier, score: int) -> bool:
    """Determina si un item de la cadena aplica a este proveedor."""
    req_if = item_def.get("required_if")
    score_gate = item_def.get("score_gate")

    if req_if == "is_data_processor":
        if not (getattr(supplier, "is_data_processor", False) or getattr(supplier, "processes_personal_data", False)):
            return False
    elif req_if == "cross_border_transfers":
        if not getattr(supplier, "cross_border_transfers", False):
            return False
    elif req_if == "is_nis2":
        if not getattr(supplier, "is_nis2", False):
            return False
    elif req_if == "is_dora":
        if not getattr(supplier, "is_dora", False):
            return False
    elif req_if == "is_ens":
        if not getattr(supplier, "is_ens", False):
            return False

    # Score gate: solo activa si el score supera el umbral
    if score_gate is not None:
        if score < score_gate:
            return False

    return True


def _get_item_state(supplier, item_id: str) -> dict:
    """Estado de firma de un item: primero chain_state, luego campos legacy."""
    chain_state = supplier.sign_off_chain_state or []
    for s in chain_state:
        if s.get("id") == item_id:
            return s

    # Fallback a campos legacy para retrocompatibilidad
    if item_id == "dpa" and supplier.dpa_signed_at:
        return {
            "id": "dpa",
            "signed_at": supplier.dpa_signed_at.isoformat() if hasattr(supplier.dpa_signed_at, "isoformat") else str(supplier.dpa_signed_at),
            "signed_by_name": supplier.dpa_signed_by or "Sistema",
            "signed_by_user_id": None,
            "doc_id": supplier.dpa_document_id,
            "skipped": False,
            "skip_justification": None,
        }
    if item_id == "nda" and supplier.nda_signed_at:
        return {
            "id": "nda",
            "signed_at": supplier.nda_signed_at.isoformat() if hasattr(supplier.nda_signed_at, "isoformat") else str(supplier.nda_signed_at),
            "signed_by_name": "Sistema",
            "signed_by_user_id": None,
            "doc_id": supplier.nda_document_id,
            "skipped": False,
            "skip_justification": None,
        }
    if item_id == "contract" and supplier.contract_document_id:
        return {
            "id": "contract",
            "signed_at": None,
            "signed_by_name": "Sistema",
            "signed_by_user_id": None,
            "doc_id": supplier.contract_document_id,
            "skipped": False,
            "skip_justification": None,
        }
    return {}


def evaluate_gate(db, supplier, config=None) -> dict:
    """Evaluacion completa del gate de onboarding para un proveedor."""
    if config is None:
        config = get_or_create_config(db, supplier.organization_id)

    score = supplier.residual_risk_score or supplier.inherent_risk_score or 0
    auto_below = config.auto_approve_below if config.auto_approve_below is not None else 30
    manual_above = config.manual_review_above if config.manual_review_above is not None else 60

    # Nivel de gate segun score
    if score < auto_below:
        gate_level = "auto"
    elif score >= manual_above:
        gate_level = "manual_review"
    else:
        gate_level = "standard"

    # Override activo
    override = None
    effective_level = gate_level
    if supplier.gate_override_type:
        override = {
            "type": supplier.gate_override_type,
            "justification": supplier.gate_override_justification,
            "by_user_id": supplier.gate_override_by_id,
            "at": supplier.gate_override_at.isoformat() if supplier.gate_override_at else None,
        }
        if supplier.gate_override_type == "bypass":
            effective_level = "auto"

    forced = supplier.forced_signoffs or []
    chain_def = config.sign_off_chain or _DEFAULT_SIGN_OFF_CHAIN

    chain_items = []
    for item_def in chain_def:
        item_id = item_def["id"]
        applicable = _item_applicable(item_def, supplier, score) or (item_id in forced)
        if not applicable:
            continue

        state = _get_item_state(supplier, item_id)

        # Dependencias bloqueantes
        depends_on = item_def.get("depends_on")
        blocked_by = None
        if depends_on:
            dep_state = _get_item_state(supplier, depends_on)
            if not dep_state.get("signed_at") and not dep_state.get("skipped") and not dep_state.get("doc_id"):
                blocked_by = depends_on

        is_signed = bool(
            state.get("signed_at")
            or (item_id == "contract" and state.get("doc_id"))
        )
        is_skipped = bool(state.get("skipped"))
        is_forced = item_id in forced

        # En bypass, ningun item es bloqueante (excepto los forzados)
        is_required = item_def.get("required", False) or is_forced
        if not is_required and item_def.get("required_if"):
            is_required = applicable  # si aplica por condicion, es requerido
        if effective_level == "auto" and not is_forced:
            is_required = False

        chain_items.append({
            "id": item_id,
            "label": item_def["label"],
            "required": is_required,
            "applicable": applicable,
            "signed": is_signed,
            "signed_at": state.get("signed_at"),
            "signed_by_name": state.get("signed_by_name"),
            "signed_by_user_id": state.get("signed_by_user_id"),
            "doc_id": state.get("doc_id"),
            "depends_on": depends_on,
            "blocked_by": blocked_by,
            "skipped": is_skipped,
            "skip_justification": state.get("skip_justification"),
            "bypass_allowed": item_def.get("bypass_allowed", True),
            "forced": is_forced,
            "score_gate": item_def.get("score_gate"),
        })

    blocking_items = [
        it["id"] for it in chain_items
        if it["required"] and not it["signed"] and not it["skipped"] and not it["blocked_by"]
    ]

    sign_offs_complete = len(blocking_items) == 0

    decision = None
    if supplier.onboarding_decision:
        decision = {
            "status": supplier.onboarding_decision,
            "notes": supplier.onboarding_decision_notes,
            "by_user_id": supplier.onboarding_decision_by_id,
            "at": supplier.onboarding_decision_at.isoformat() if supplier.onboarding_decision_at else None,
            "conditions": supplier.onboarding_conditions or [],
        }

    ready_for_active = (
        sign_offs_complete
        and (decision is None or decision["status"] in ("approved", "conditional"))
        and supplier.lifecycle_stage in ("onboarding", "active")
    )

    return {
        "score": score,
        "gate_level": gate_level,
        "effective_level": effective_level,
        "thresholds": {"auto": auto_below, "manual": manual_above},
        "override": override,
        "sign_off_chain": chain_items,
        "sign_offs_complete": sign_offs_complete,
        "blocking_items": blocking_items,
        "decision": decision,
        "ready_for_active": ready_for_active,
        "forced_signoffs": forced,
    }


def apply_override(db, supplier, override_type: str, justification: str, extra_signoffs: list, user) -> dict:
    """Aplica un override (bypass o force_controls) con trazabilidad completa."""
    from sqlalchemy.orm.attributes import flag_modified

    supplier.gate_override_type = override_type
    supplier.gate_override_justification = justification
    supplier.gate_override_by_id = user.id
    supplier.gate_override_at = datetime.now(timezone.utc)

    if override_type == "force_controls" and extra_signoffs:
        current = supplier.forced_signoffs or []
        for sf in extra_signoffs:
            if sf not in current:
                current.append(sf)
        supplier.forced_signoffs = current
        flag_modified(supplier, "forced_signoffs")

    db.commit()
    return evaluate_gate(db, supplier)


def record_decision(db, supplier, decision: str, notes: str, conditions: list, user) -> dict:
    """Registra la decision formal de cyber con creacion de VendorIssues por condiciones."""
    from sqlalchemy.orm.attributes import flag_modified
    from app.models import VendorIssue, VendorIssueSeverity, VendorIssueStatus

    supplier.onboarding_decision = decision
    supplier.onboarding_decision_notes = notes
    supplier.onboarding_decision_by_id = user.id
    supplier.onboarding_decision_at = datetime.now(timezone.utc)

    if conditions:
        enriched = []
        for cond in conditions:
            issue_count = db.query(VendorIssue).filter(
                VendorIssue.organization_id == supplier.organization_id
            ).count() + 1
            due_days = int(cond.get("due_days", 30))
            issue = VendorIssue(
                organization_id=supplier.organization_id,
                code=f"VIS-{issue_count:04d}",
                supplier_id=supplier.id,
                source="onboarding",
                title=cond.get("description", "Condicion de onboarding"),
                description=(
                    f"Condicion requerida para el alta del proveedor {supplier.name}: "
                    f"{cond.get('description', '')}. Plazo: {due_days} dias."
                ),
                severity=VendorIssueSeverity.MEDIUM,
                status=VendorIssueStatus.OPEN,
                auto_generated=True,
                auto_generated_source="onboarding_condition",
                due_date=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=due_days),
                created_at=datetime.now(timezone.utc),
            )
            db.add(issue)
            db.flush()
            enriched.append({**cond, "vendor_issue_id": issue.id})
        supplier.onboarding_conditions = enriched
        flag_modified(supplier, "onboarding_conditions")

    db.commit()
    return evaluate_gate(db, supplier)


def sign_chain_item(db, supplier, item_id: str, signed_by_name: str, user_id: int,
                    doc_id=None, skipped=False, skip_justification=None) -> dict:
    """Registra la firma (o el salto justificado) de un item de la cadena."""
    from sqlalchemy.orm.attributes import flag_modified

    now = datetime.now(timezone.utc)
    chain_state = list(supplier.sign_off_chain_state or [])

    existing = next((s for s in chain_state if s["id"] == item_id), None)
    if existing:
        chain_state.remove(existing)

    chain_state.append({
        "id": item_id,
        "signed_at": None if skipped else now.isoformat(),
        "signed_by_name": signed_by_name,
        "signed_by_user_id": user_id,
        "doc_id": doc_id,
        "skipped": skipped,
        "skip_justification": skip_justification,
    })
    supplier.sign_off_chain_state = chain_state
    flag_modified(supplier, "sign_off_chain_state")

    # Retrocompatibilidad con campos legacy
    if not skipped:
        if item_id == "dpa":
            supplier.dpa_signed_at = now.replace(tzinfo=None)
            supplier.dpa_signed_by = signed_by_name
            if doc_id:
                supplier.dpa_document_id = doc_id
        elif item_id == "nda":
            supplier.nda_signed_at = now.replace(tzinfo=None)
            if doc_id:
                supplier.nda_document_id = doc_id
        elif item_id == "contract" and doc_id:
            supplier.contract_document_id = doc_id

    db.commit()

    from app.services.supplier_lifecycle_service import recompute_supplier_risk_profile
    recompute_supplier_risk_profile(db, supplier.id, triggered_by=f"sign_off_{item_id}")

    return evaluate_gate(db, supplier)
