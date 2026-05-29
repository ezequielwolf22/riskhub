"""Construye el bloque de contexto para inyectar en el prompt del agente IA."""
from sqlalchemy.orm import Session

from app.models import (
    AiConfig, Asset, ControlImplementation, ControlStatus,
    Incident, NonConformity, Risk, RiskContext, RiskStatus, Supplier,
)
from app.services.rag_service import search_chunks_with_source


def build_context(
    db: Session,
    query: str = "",
    max_chunks: int = 5,
    organization_id: int | None = None,
) -> str:
    """Genera el bloque de contexto completo para inyectar en el prompt.

    organization_id es OBLIGATORIO para uso normal — garantiza que el contexto
    contiene UNICAMENTE datos del tenant del usuario autenticado.
    Solo se omite (None) en contextos de superadmin o pruebas internas.
    """
    parts: list[str] = []

    def _forg(q, model):
        """Aplica filtro de organizacion si se proporciono organization_id."""
        if organization_id is not None:
            return q.filter(model.organization_id == organization_id)
        return q

    # 1. Perfil de organizacion
    ctx = _forg(db.query(RiskContext), RiskContext).first()
    ai_cfg = _forg(db.query(AiConfig), AiConfig).first()

    if ctx:
        parts.append(f"## Organizacion: {ctx.organization_name or 'Sin nombre'}")
        if ctx.scope:
            parts.append(f"Alcance del SGSI: {ctx.scope}")
        if ctx.boundaries:
            parts.append(f"Fronteras: {ctx.boundaries}")
        if ctx.risk_appetite is not None:
            parts.append(f"Apetito de riesgo: nivel {ctx.risk_appetite}/8")

    if ai_cfg:
        if ai_cfg.org_sector:
            parts.append(f"Sector: {ai_cfg.org_sector}")
        if ai_cfg.org_size:
            parts.append(f"Tamano de la organizacion: {ai_cfg.org_size}")
        if ai_cfg.org_critical_processes:
            parts.append(f"Procesos criticos: {ai_cfg.org_critical_processes}")
        if ai_cfg.org_tech_stack:
            parts.append(f"Stack tecnologico: {ai_cfg.org_tech_stack}")

    # 2. Inventario de activos (resumen)
    assets = _forg(db.query(Asset), Asset).limit(50).all()
    if assets:
        parts.append(f"\n## Activos ({len(assets)} en inventario)")
        for a in assets[:15]:
            cia = f"C={a.value_confidentiality} I={a.value_integrity} A={a.value_availability}"
            parts.append(f"- {a.code}: {a.name} [{a.asset_type.value}] {cia}")
        if len(assets) > 15:
            parts.append(f"  ... y {len(assets) - 15} activos adicionales.")

    # 3. Riesgos activos
    risks = (
        _forg(db.query(Risk), Risk)
        .filter(Risk.status != RiskStatus.CLOSED)
        .limit(30)
        .all()
    )
    if risks:
        parts.append(f"\n## Riesgos activos ({len(risks)})")
        for r in risks[:15]:
            desc = (r.description or "Sin descripcion")[:80]
            parts.append(
                f"- {r.code}: {desc} "
                f"[residual={r.residual_level}/8, estado={r.status.value}]"
            )
        if len(risks) > 15:
            parts.append(f"  ... y {len(risks) - 15} riesgos adicionales.")

    # 4. Incidentes recientes
    incidents = (
        _forg(db.query(Incident), Incident)
        .order_by(Incident.created_at.desc())
        .limit(5)
        .all()
    )
    if incidents:
        parts.append(f"\n## Incidentes recientes ({len(incidents)})")
        for i in incidents:
            parts.append(f"- {i.code}: {i.title} [{i.severity.value}, {i.status.value}]")

    # 5. Controles con baja madurez
    weak_controls = (
        _forg(db.query(ControlImplementation), ControlImplementation)
        .filter(
            ControlImplementation.status != ControlStatus.IMPLEMENTED,
            ControlImplementation.maturity <= 2,
        )
        .limit(10)
        .all()
    )
    if weak_controls:
        parts.append(f"\n## Controles con baja madurez ({len(weak_controls)})")
        for c in weak_controls:
            parts.append(
                f"- {c.name}: madurez {c.maturity}/5, estado {c.status.value}"
            )

    # 6. Proveedores criticos
    critical_suppliers = (
        _forg(db.query(Supplier), Supplier)
        .filter(Supplier.is_critical.is_(True))
        .limit(10)
        .all()
    )
    if critical_suppliers:
        parts.append(f"\n## Proveedores criticos ({len(critical_suppliers)})")
        for s in critical_suppliers:
            parts.append(f"- {s.name}: riesgo {s.risk_level.value}, score {s.score}/100")

    # 7. No conformidades abiertas
    ncs = (
        _forg(db.query(NonConformity), NonConformity)
        .filter(NonConformity.status.in_(["open", "in_progress"]))
        .limit(10)
        .all()
    )
    if ncs:
        parts.append(f"\n## No conformidades abiertas ({len(ncs)})")
        for nc in ncs:
            parts.append(f"- {nc.code}: {nc.title} [{nc.severity.value}]")

    # 8. Fragmentos RAG de documentacion interna (filtrados por organizacion)
    # Se incluye el nombre del documento fuente para que el agente pueda citar con precision
    if query:
        results = search_chunks_with_source(
            db, query, top_k=max_chunks, organization_id=organization_id
        )
        if results:
            parts.append("\n## Documentacion interna relevante")
            for r in results:
                source_label = f"[Fuente: {r['doc_name']}]"
                parts.append(f"---\n{source_label}\n{r['content'][:800]}")

    return "\n".join(parts)
