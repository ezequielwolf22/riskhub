"""Extraccion automatica de checklist de activacion BCM usando Claude."""
import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

logger = logging.getLogger("riskhub.bcm_checklist")

SYSTEM_PROMPT = """Eres un experto en continuidad de negocio ISO 22301.
Analiza el contenido de un plan de continuidad/recuperacion y extrae una lista
ordenada de acciones concretas que deben ejecutarse al activar el plan.

Para cada accion devuelve un objeto JSON con:
- order: numero de orden (1, 2, 3...)
- title: titulo corto de la accion (max 80 caracteres)
- description: descripcion detallada de que hay que hacer
- action_type: uno de [manual, notify_users, create_task, log_timeline]
  * manual: el usuario marca manualmente cuando esta hecho
  * notify_users: el sistema debe enviar una alerta interna a los usuarios del plan
  * create_task: el sistema debe crear una tarea en el modulo de tareas
  * log_timeline: el sistema registra automaticamente en el timeline de la activacion
- action_config: objeto con configuracion segun tipo:
  * notify_users: {"message": "texto de la notificacion"}
  * create_task: {"title": "titulo de la tarea", "description": "descripcion"}
  * manual / log_timeline: {}

Reglas:
- Maximo 15 acciones. Si hay mas, prioriza las mas criticas.
- Usa notify_users para notificaciones a personas/equipos.
- Usa create_task para acciones que requieren seguimiento prolongado.
- Usa log_timeline para registros automaticos (ej: "Plan activado a las HH:MM").
- El resto es manual.
- Responde SOLO con un array JSON valido, sin texto adicional.
"""


def extract_plan_checklist(db: Session, plan, api_key: str, model: str) -> list:
    """
    Llama a Claude para extraer el checklist de acciones del plan.
    Devuelve lista de items o [] si falla.
    """
    try:
        import anthropic
        from app.models import AiDocument, AiDocumentChunk

        if not plan.document_id:
            return _default_checklist(plan)

        doc = db.get(AiDocument, plan.document_id)
        if not doc:
            return _default_checklist(plan)

        chunks = db.query(AiDocumentChunk).filter_by(
            document_id=doc.id
        ).order_by(AiDocumentChunk.chunk_index).all()

        if not chunks:
            return _default_checklist(plan)

        # Concatenar chunks (max ~6000 chars para no disparar tokens)
        text = "\n".join(c.content for c in chunks)[:6000]

        plan_info = (
            f"Tipo de plan: {plan.plan_type}\n"
            f"Nombre: {plan.name}\n"
            f"Alcance: {plan.scope or 'No especificado'}\n"
            f"Criterios de activacion: {plan.activation_criteria or 'No especificados'}\n\n"
            f"Contenido del plan:\n{text}"
        )

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=16384,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": plan_info}],
        )
        raw = msg.content[0].text.strip()

        # Extraer JSON del response
        if raw.startswith("["):
            items = json.loads(raw)
        else:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                items = json.loads(raw[start:end])
            else:
                raise ValueError("No JSON array found in response")

        # Normalizar y validar items
        valid_types = {"manual", "notify_users", "create_task", "log_timeline"}
        result = []
        for i, item in enumerate(items[:15], start=1):
            action_type = item.get("action_type", "manual")
            if action_type not in valid_types:
                action_type = "manual"
            result.append({
                "order": item.get("order", i),
                "title": str(item.get("title", f"Accion {i}"))[:80],
                "description": str(item.get("description", ""))[:500],
                "action_type": action_type,
                "action_config": item.get("action_config") or {},
            })
        return result if result else _default_checklist(plan)

    except Exception as exc:
        logger.warning("Error extrayendo checklist del plan %s: %s", plan.id, exc)
        return _default_checklist(plan)


def _default_checklist(plan) -> list:
    """Checklist minimo cuando no hay documento o falla la extraccion."""
    items = [
        {
            "order": 1,
            "title": "Notificar activacion del plan",
            "description": f"Informar a los responsables del plan '{plan.name}' que se ha activado.",
            "action_type": "notify_users",
            "action_config": {"message": f"El plan '{plan.name}' ha sido activado. Reportad al punto de coordinacion."},
        },
        {
            "order": 2,
            "title": "Registrar hora de activacion",
            "description": "Confirmar y registrar la hora oficial de inicio de la activacion.",
            "action_type": "log_timeline",
            "action_config": {},
        },
        {
            "order": 3,
            "title": "Evaluar situacion inicial",
            "description": "Realizar evaluacion rapida del impacto y alcance del incidente.",
            "action_type": "manual",
            "action_config": {},
        },
        {
            "order": 4,
            "title": "Activar equipo de crisis",
            "description": "Convocar a los miembros del equipo de gestion de crisis segun el plan.",
            "action_type": "create_task",
            "action_config": {"title": "Convocar equipo de crisis", "description": f"Plan: {plan.name}"},
        },
        {
            "order": 5,
            "title": "Implementar medidas de continuidad",
            "description": "Ejecutar las estrategias de recuperacion definidas en el plan.",
            "action_type": "manual",
            "action_config": {},
        },
    ]
    return items


def build_activation_checklist(template: list) -> list:
    """Clona el template del plan para una activacion especifica, añadiendo campos de estado."""
    result = []
    for item in template:
        result.append({
            **item,
            "status": "pending",
            "executed_at": None,
            "executed_by": None,
            "notes": None,
        })
    return result


def execute_checklist_action(db: Session, activation, item: dict, user, org_id: int) -> dict:
    """
    Ejecuta la accion automatica de un item del checklist.
    Devuelve el item actualizado.
    """
    action_type = item.get("action_type", "manual")
    config = item.get("action_config") or {}
    now = datetime.now(timezone.utc)

    if action_type == "notify_users":
        _notify_users(db, org_id, activation, item, config, user)

    elif action_type == "create_task":
        _create_task(db, org_id, activation, item, config, user)

    elif action_type == "log_timeline":
        _log_timeline(db, activation, item, user)

    item["status"] = "done"
    item["executed_at"] = now.isoformat()
    item["executed_by"] = user.email
    return item


def _notify_users(db, org_id, activation, item, config, actor):
    """Registra la notificacion en el timeline de la activacion y envia email si hay SMTP."""
    message = config.get("message") or f"Accion requerida: {item['title']} — Activacion {activation.code}"
    now = datetime.now(timezone.utc)
    log = list(activation.situation_log or [])
    log.append({
        "timestamp": now.isoformat(),
        "user_id": actor.id,
        "user_email": actor.email,
        "type": "notification",
        "text": f"[Notificacion enviada] {message}",
    })
    activation.situation_log = log
    db.commit()

    # Intentar envio por email si hay SMTP configurado
    try:
        from app.models import EmailSettings, User as UserModel, UserRole
        from app.services import email_service
        settings = db.query(EmailSettings).filter_by(organization_id=org_id).first()
        if settings and settings.smtp_host:
            recipients = db.query(UserModel).filter(
                UserModel.organization_id == org_id,
                UserModel.role.in_([UserRole.admin, UserRole.analyst]),
                UserModel.is_active == True,
            ).all()
            for u in recipients:
                try:
                    email_service.send_email(
                        settings, u.email,
                        subject=f"[RiskHub BCM] Activacion {activation.code}: {item['title']}",
                        body_html=f"<p>{message}</p>",
                    )
                except Exception:
                    pass
    except Exception:
        pass


def _create_task(db, org_id, activation, item, config, actor):
    """Crea una tarea en el modulo de tareas (TreatmentTask)."""
    from app.models import TreatmentTask, TaskStatus, TaskPriority
    n = db.query(TreatmentTask).filter_by(organization_id=org_id).count()
    code = f"TSK-{n + 1:04d}"
    db.add(TreatmentTask(
        organization_id=org_id,
        code=code,
        title=config.get("title") or item["title"],
        description=config.get("description") or item.get("description", ""),
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
        assigned_to_id=actor.id,
        created_by_id=actor.id,
        notes=f"Creada automaticamente por activacion BCM {activation.code}",
    ))
    db.commit()


def _log_timeline(db, activation, item, actor):
    """Anade entrada al situation_log de la activacion."""
    now = datetime.now(timezone.utc)
    log = list(activation.situation_log or [])
    log.append({
        "timestamp": now.isoformat(),
        "user_id": actor.id,
        "user_email": actor.email,
        "type": "checklist",
        "text": f"[Checklist] {item['title']} — ejecutado automaticamente.",
    })
    activation.situation_log = log
    db.commit()
