"""Router para importar y analizar diagramas de arquitectura."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.i18n import get_lang
from app.models import User
from app.security import get_current_user, require_role
from app.services.architecture_parser import (
    parse_drawio_xml,
    parse_text_description,
    create_assets_from_nodes,
)

router = APIRouter(prefix="/api/architecture", tags=["architecture"])


@router.post("/import")
async def import_diagram(
    request: Request,
    file: Optional[UploadFile] = File(None),
    description: Optional[str] = Form(None),
    diagram_name: str = Form("Diagrama importado"),
    use_ai: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("analyst")),
):
    """Importa un diagrama de arquitectura y auto-crea activos + amenazas STRIDE + riesgos.

    Acepta:
    - Archivo .drawio o .xml (diagrams.net)
    - Descripción textual (NLP parsing)
    - Ambos (descripción + IA si use_ai=True)
    """
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, "Se requiere organization_id")

    if not file and not description:
        raise HTTPException(400, "Se requiere archivo o descripción")

    nodes = []

    # Parsear archivo si existe
    if file:
        content = await file.read()
        # A6: limite de tamano para evitar DoS por XML masivo o billion-laughs
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(413, "Archivo demasiado grande (max 10 MB)")
        filename = (file.filename or "").lower()

        if filename.endswith(".drawio") or filename.endswith(".xml"):
            nodes = parse_drawio_xml(content)
        else:
            raise HTTPException(400, "Formato no soportado. Use .drawio o .xml de diagrams.net")

    # Parsear descripción textual
    if description and not nodes:
        if use_ai:
            from app.services.architecture_parser import analyze_with_ai
            lang = get_lang(request)
            nodes = await analyze_with_ai(description, org_id, db, lang=lang)

        if not nodes:
            # Fallback: NLP básico
            nodes = parse_text_description(description)

    if not nodes:
        raise HTTPException(
            422,
            "No se pudieron extraer componentes del diagrama. "
            "Verifica el formato o añade una descripción textual."
        )

    # Crear activos, amenazas y riesgos
    stats = create_assets_from_nodes(
        db, nodes, org_id,
        user_id=current_user.id,
        diagram_name=diagram_name,
    )

    return {
        "message": "Arquitectura importada correctamente",
        "nodes_detected": len(nodes),
        "stats": stats,
        "nodes_preview": [
            {"label": n.get("label", ""), "asset_type": n.get("asset_type", "")}
            for n in nodes[:20]
        ],
    }


@router.post("/analyze-text")
async def analyze_text(
    request: Request,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Analiza descripción textual de arquitectura y retorna componentes detectados (sin crear)."""
    description = body.get("description", "")
    if not description or len(description) < 20:
        raise HTTPException(400, "Descripción muy corta (mínimo 20 caracteres)")

    org_id = current_user.organization_id
    nodes = parse_text_description(description)

    if not nodes and body.get("use_ai", True):
        from app.services.architecture_parser import analyze_with_ai
        lang = get_lang(request)
        nodes = await analyze_with_ai(description, org_id, db, lang=lang)

    return {
        "components_detected": len(nodes),
        "components": [
            {"label": n.get("label", ""), "asset_type": n.get("asset_type", "")}
            for n in nodes
        ],
    }
