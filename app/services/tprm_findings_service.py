"""Generacion automatica de hallazgos desde cuestionarios (feedback cliente, punto 10).

Determinista: reutiliza la criticidad (Major/Minor) y el scoring por pregunta que
ya traen las plantillas TPRM. Una respuesta no-conforme en una pregunta Major crea
un hallazgo HIGH; en una Minor, MEDIUM. El ejemplo del cliente (MFA=No -> Finding
High/Open) sale directo: la pregunta de MFA es criticity Major y "sin MFA" puntua 0.

La IA sigue aportando el analisis cualitativo (tprm_ai_service); esto es el suelo
determinista que no depende de que haya API key configurada.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import VendorIssue, VendorIssueSeverity, VendorIssueStatus

logger = logging.getLogger(__name__)

# Umbral de score por pregunta por debajo del cual la respuesta es no-conforme
_NC_THRESHOLD = 50.0

# SLA en dias por severidad (alineado con vendor_issues._SLA_DAYS)
_SLA_DAYS = {
    VendorIssueSeverity.CRITICAL: 7,
    VendorIssueSeverity.HIGH: 30,
    VendorIssueSeverity.MEDIUM: 90,
    VendorIssueSeverity.LOW: 180,
}

_MARKER = "[auto:questionnaire_finding]"


def _severity_for(criticity: str, score: float) -> Optional[VendorIssueSeverity]:
    """Severidad del hallazgo segun la criticidad de la pregunta y el score."""
    crit = (criticity or "").lower()
    if score >= _NC_THRESHOLD:
        return None
    if crit == "major":
        return VendorIssueSeverity.CRITICAL if score <= 0 else VendorIssueSeverity.HIGH
    if crit == "minor":
        return VendorIssueSeverity.MEDIUM
    return None


def _next_code(db: Session, org_id: int) -> str:
    from app.models import VendorIssue as _VI
    n = db.query(_VI).filter(_VI.organization_id == org_id).count()
    return f"VIS-{n + 1:04d}"


def generate_from_questionnaire(db: Session, q, user_id: Optional[int] = None,
                                commit: bool = True) -> int:
    """Crea hallazgos deterministas para las respuestas no-conformes del cuestionario.

    Idempotente por (proveedor, pregunta): no duplica un hallazgo abierto ya creado
    para la misma pregunta.
    """
    from app.services.tprm_scoring_service import _score_answer

    questions = q.questions or []
    answers = q.answers or {}
    if not questions or not answers:
        return 0

    org_id = q.organization_id
    supplier_id = q.supplier_id

    # Hallazgos abiertos ya generados para este proveedor, por pregunta (dedupe)
    existing = db.query(VendorIssue).filter(
        VendorIssue.supplier_id == supplier_id,
        VendorIssue.auto_generated_source == "questionnaire_finding",
        VendorIssue.status.notin_([
            VendorIssueStatus.CLOSED, VendorIssueStatus.MITIGATED, VendorIssueStatus.ACCEPTED,
        ]),
    ).all()
    existing_qids = set()
    for iss in existing:
        for ref in (iss.framework_refs or []):
            if isinstance(ref, str) and ref.startswith("__qid:"):
                existing_qids.add(ref[6:])

    created = 0
    now = datetime.now(timezone.utc)
    for qq in questions:
        qid = str(qq.get("id"))
        if qid in existing_qids:
            continue
        ans = answers.get(qid)
        if ans is None or ans == "":
            continue
        score = _score_answer(qq, ans)
        if score is None:
            continue
        severity = _severity_for(qq.get("criticity"), score)
        if severity is None:
            continue

        control_refs = list(qq.get("control_refs") or [])
        title = (qq.get("finding_title")
                 or f"No conformidad: {qq.get('text', qid)}")[:255]
        due_days = _SLA_DAYS.get(severity)
        issue = VendorIssue(
            organization_id=org_id,
            code=_next_code(db, org_id),
            supplier_id=supplier_id,
            source="questionnaire",
            title=title,
            description=(
                f"Generado automaticamente desde el cuestionario {q.code}. "
                f"Respuesta: {ans}. Score de la pregunta: {int(score)}/100. {_MARKER}"
            ),
            severity=severity,
            status=VendorIssueStatus.OPEN,
            framework_refs=control_refs + [f"__qid:{qid}"],
            discovered_at=now,
            due_date=(now + timedelta(days=due_days)) if due_days else None,
            auto_generated=True,
            auto_generated_source="questionnaire_finding",
            created_by_id=user_id,
        )
        db.add(issue)
        db.flush()
        issue.code = f"VIS-{issue.id:04d}"
        created += 1

    if created and commit:
        db.commit()
    return created
