"""Router del metodo de la organizacion.

Expone lo que hace defendible cada cifra de la plataforma: que parametros usa
esta organizacion, de donde sale cada uno (su politica citada, una decision
manual, o el defecto de la herramienta), que reglas suyas no se saben aplicar
todavia, y donde diverge lo que se calcula de lo que su norma dice.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import get_lang, t as _t
from app.models import MethodBinding, MethodFinding, MethodStatement, User
from app.security import get_current_user, require_analyst
from app.services.audit_service import log_action
from app.services.method import conformance, registry
from app.services.method.bindings import (apply_statement, clear_binding,
                                          method_overview, resolve, set_binding)

logger = logging.getLogger("riskhub.method.router")

router = APIRouter(prefix="/api/method", tags=["method"])


def _org(u: User, lang: str = "es") -> int:
    if not u.organization_id:
        raise HTTPException(400, _t("method.user_no_org", lang))
    return u.organization_id


class BindingIn(BaseModel):
    value: object = None
    notes: Optional[str] = None


class FormulaCheckIn(BaseModel):
    expression: str
    variables: Optional[list] = None
    samples: Optional[list] = None


# ── Parametros ───────────────────────────────────────────────────────────────

@router.get("/parameters")
def list_parameters(module: Optional[str] = None, db: Session = Depends(get_db),
                    u: User = Depends(get_current_user)):
    """Todos los parametros con su valor efectivo y su procedencia."""
    rows = method_overview(db, _org(u))
    if module:
        rows = [r for r in rows if r["module"] == module]
    return rows


@router.get("/parameters/{key}")
def get_parameter(key: str, request: Request, db: Session = Depends(get_db),
                  u: User = Depends(get_current_user)):
    lang = get_lang(request)
    param = registry.get(key)
    if param is None:
        raise HTTPException(404, _t("method.parameter_not_found", lang, key=key))
    resolved = resolve(db, _org(u, lang), key)
    return {
        "key": key, "module": param.module, "label": param.label,
        "type": param.type, "description": param.description,
        "engine": param.engine, "wired": param.wired, "unit": param.unit,
        "choices": list(param.choices or ()) or None,
        "variables": list(param.variables or ()) or None,
        "normative_ref": param.normative_ref, "default": param.default(),
        **resolved.as_dict(),
    }


@router.put("/parameters/{key}")
def put_parameter(key: str, body: BindingIn, request: Request,
                  db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    """Fija el valor a mano. Gana sobre lo extraido de un documento."""
    lang = get_lang(request)
    org = _org(u, lang)
    if registry.get(key) is None:
        raise HTTPException(404, _t("method.parameter_not_found", lang, key=key))
    try:
        set_binding(db, org, key, body.value, source="manual",
                    notes=body.notes, user_id=u.id)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    conformance.refresh(db, org)
    log_action(db, u.id, "update", "method_parameter", key,
               {"value": str(body.value)[:200]})
    return resolve(db, org, key).as_dict()


@router.delete("/parameters/{key}", status_code=204)
def reset_parameter(key: str, request: Request, db: Session = Depends(get_db),
                    u: User = Depends(require_analyst)):
    """Vuelve al valor por defecto de la plataforma."""
    lang = get_lang(request)
    org = _org(u, lang)
    if registry.get(key) is None:
        raise HTTPException(404, _t("method.parameter_not_found", lang, key=key))
    clear_binding(db, org, key)
    conformance.refresh(db, org)


# ── Declaraciones extraidas de la politica ───────────────────────────────────

def _statement_d(s: MethodStatement) -> dict:
    return {
        "id": s.id, "parameter_key": s.parameter_key,
        "proposed_value": s.proposed_value, "quote": s.quote,
        "source_document": s.source_document, "source_section": s.source_section,
        "interpretation": s.interpretation, "confidence": s.confidence,
        "status": s.status, "batch_id": s.batch_id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("/statements")
def list_statements(status: Optional[str] = None, db: Session = Depends(get_db),
                    u: User = Depends(get_current_user)):
    """Lo que el agente leyo en la politica del cliente, con su cita."""
    q = db.query(MethodStatement).filter_by(organization_id=_org(u))
    if status:
        q = q.filter(MethodStatement.status == status)
    return [_statement_d(s) for s in
            q.order_by(MethodStatement.id.desc()).limit(300).all()]


@router.post("/statements/{sid}/apply")
def apply(sid: int, request: Request, force: bool = False,
          db: Session = Depends(get_db), u: User = Depends(require_analyst)):
    """Convierte una declaracion en el valor que usa el motor."""
    lang = get_lang(request)
    org = _org(u, lang)
    st = db.get(MethodStatement, sid)
    if not st or st.organization_id != org:
        raise HTTPException(404, _t("method.statement_not_found", lang))
    out = apply_statement(db, org, st, user_id=u.id, force=force)
    if not out.get("applied"):
        raise HTTPException(422, out.get("reason") or
                            _t("method.cannot_apply", lang))
    conformance.refresh(db, org)
    log_action(db, u.id, "apply", "method_statement", str(sid), out)
    return out


@router.post("/statements/{sid}/reject", status_code=200)
def reject(sid: int, request: Request, db: Session = Depends(get_db),
           u: User = Depends(require_analyst)):
    """Descarta una declaracion. Se conserva con su cita, no se borra."""
    lang = get_lang(request)
    org = _org(u, lang)
    st = db.get(MethodStatement, sid)
    if not st or st.organization_id != org:
        raise HTTPException(404, _t("method.statement_not_found", lang))
    st.status = "rejected"
    st.reviewed_by_id = u.id
    st.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    conformance.refresh(db, org)
    return _statement_d(st)


# ── Conformidad ──────────────────────────────────────────────────────────────

@router.get("/conformance")
def get_conformance(db: Session = Depends(get_db),
                    u: User = Depends(get_current_user)):
    """Resumen y hallazgos: donde el calculo no coincide con tu politica."""
    org = _org(u)
    findings = db.query(MethodFinding).filter_by(organization_id=org).order_by(
        MethodFinding.id.desc()).limit(300).all()
    return {
        "summary": conformance.summary(db, org),
        "findings": [{
            "id": f.id, "kind": f.kind, "parameter_key": f.parameter_key,
            "severity": f.severity, "summary": f.summary,
            "statement_id": f.statement_id,
            "effective_value": f.effective_value, "policy_value": f.policy_value,
            "normative_ref": f.normative_ref, "normative_value": f.normative_value,
            "status": f.status,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        } for f in findings],
    }


@router.post("/conformance/refresh")
def refresh_conformance(db: Session = Depends(get_db),
                        u: User = Depends(require_analyst)):
    return conformance.refresh(db, _org(u))


@router.post("/conformance/findings/{fid}/accept")
def accept_finding(fid: int, request: Request, db: Session = Depends(get_db),
                   u: User = Depends(require_analyst)):
    """Da por bueno un hallazgo. No vuelve a aparecer al recalcular."""
    lang = get_lang(request)
    f = db.get(MethodFinding, fid)
    if not f or f.organization_id != _org(u, lang):
        raise HTTPException(404, _t("method.finding_not_found", lang))
    f.status = "accepted"
    f.resolved_by_id = u.id
    f.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": f.id, "status": f.status}


# ── Formulas ─────────────────────────────────────────────────────────────────

@router.post("/formula/validate")
def validate_formula(body: FormulaCheckIn, db: Session = Depends(get_db),
                     u: User = Depends(require_analyst)):
    """Valida una formula antes de guardarla y muestra que numero produce."""
    from app.services.method.formula import available_functions, validate
    return {**validate(body.expression, body.variables or [], body.samples),
            "functions": available_functions()}


@router.get("/bindings")
def list_bindings(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    rows = db.query(MethodBinding).filter_by(organization_id=_org(u)).all()
    return [{"id": b.id, "parameter_key": b.parameter_key, "value": b.value,
             "source": b.source, "statement_id": b.statement_id,
             "confidence": b.confidence, "notes": b.notes} for b in rows]
