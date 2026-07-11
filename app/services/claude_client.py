"""Cliente Claude unificado: reintentos, circuit breaker y prompt caching.

Antes solo el analisis batch de activos tenia reintentos ante 429/sobrecarga;
el resto de servicios (evidencia, TPRM, regwatch, vision) fallaba a la
primera. Este wrapper centraliza:
  - backoff exponencial ante 429 / overloaded / 5xx (reintenta)
  - circuit breaker cuando la API key se queda sin creditos (corta en seco
    los jobs masivos en lugar de quemar reintentos)
  - soporte de prompt caching (cache_control en bloques de system)

Uso:
    from app.services.claude_client import create_message, CreditsExhausted
    msg = create_message(api_key, model=..., max_tokens=..., system=...,
                         messages=[...])
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_WAIT_S = 10

# api_key[:16] -> True si la key agoto creditos (se resetea al reiniciar)
_credit_exhausted: dict[str, bool] = {}


class CreditsExhausted(RuntimeError):
    """La API key no tiene creditos: no tiene sentido reintentar."""


def _is_credit_error(err: str) -> bool:
    low = err.lower()
    return (
        "credit balance" in low
        or "insufficient_balance" in low
        or "billing" in low
        or "402" in low
    )


def _is_retryable(err: str) -> bool:
    low = err.lower()
    return (
        "429" in low or "rate_limit" in low or "overloaded" in low
        or "529" in low or "500" in low or "502" in low or "503" in low
        or "timeout" in low or "timed out" in low
    )


def cached_system(prompt: str, cached_context: str | None = None) -> list[dict]:
    """Construye bloques de system con prompt caching.

    El bloque grande y estable (catalogos, contexto de la org) se marca con
    cache_control: llamadas consecutivas en <5 min reutilizan el prefijo y
    el coste de input cae ~90% en lotes y pasadas repetidas.
    """
    blocks: list[dict] = [{"type": "text", "text": prompt}]
    if cached_context:
        blocks.append({
            "type": "text",
            "text": cached_context,
            "cache_control": {"type": "ephemeral"},
        })
    else:
        blocks[0]["cache_control"] = {"type": "ephemeral"}
    return blocks


def _log_usage(msg, *, org_id: int | None, call_type: str | None, model: str) -> None:
    """Registra tokens en ai_call_logs (best-effort) para el panel de costes."""
    if not call_type:
        return
    try:
        from app.database import SessionLocal
        from app.models import AiCallLog
        usage = getattr(msg, "usage", None)
        db = SessionLocal()
        try:
            db.add(AiCallLog(
                organization_id=org_id,
                call_type=call_type,
                model=model,
                prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
                completion_tokens=getattr(usage, "output_tokens", 0) or 0,
            ))
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # nunca romper el analisis por el logging
        logger.debug("claude_client: no se pudo registrar el uso: %s", exc)


def structured_message(api_key: str, *, model: str, max_tokens: int,
                       messages: list, tool_name: str, input_schema: dict,
                       tool_description: str = "", system=None,
                       retries: int = _MAX_RETRIES, **kwargs) -> tuple[dict, object]:
    """Salida estructurada garantizada via tool use forzado.

    En lugar de pedir "devuelve SOLO JSON" y reparar la respuesta a
    posteriori (_repair_json, fences, regex), se define una herramienta con
    schema JSON formal y se fuerza al modelo a llamarla: la API valida los
    argumentos contra el schema, por lo que el JSON malformado deja de
    existir como clase de error.

    Devuelve (data, message): data es el dict de argumentos de la tool y
    message el objeto completo (para logging de tokens).
    """
    tools = [{
        "name": tool_name,
        "description": tool_description or f"Entrega el resultado estructurado de {tool_name}",
        "input_schema": input_schema,
    }]
    msg = create_message(
        api_key, model=model, max_tokens=max_tokens, system=system,
        messages=messages, retries=retries,
        tools=tools, tool_choice={"type": "tool", "name": tool_name},
        **kwargs,
    )
    for block in msg.content or []:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return dict(block.input), msg
    raise ValueError(
        f"El modelo no devolvio la llamada a la herramienta '{tool_name}' "
        f"(stop_reason={getattr(msg, 'stop_reason', '?')})"
    )


def create_message(api_key: str, *, model: str, max_tokens: int,
                   messages: list, system=None, retries: int = _MAX_RETRIES,
                   org_id: int | None = None, call_type: str | None = None,
                   **kwargs):
    """Llamada a la API con reintentos y circuit breaker. Lanza CreditsExhausted
    si la key esta sin creditos (los jobs masivos deben abortar, no reintentar).

    Usa streaming internamente: el SDK rechaza peticiones no-streaming que
    estima largas ("Streaming is required for operations that may take longer
    than 10 minutes"), lo que rompia el analisis batch con max_tokens altos.
    El resultado es el mensaje final completo, identico al de messages.create.

    Con org_id + call_type registra los tokens en ai_call_logs (panel de
    costes /api/ai/usage).
    """
    import anthropic

    if _credit_exhausted.get(api_key[:16]):
        raise CreditsExhausted("API key sin creditos (circuit breaker activo)")

    client = anthropic.Anthropic(api_key=api_key)
    params = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system is not None:
        params["system"] = system
    params.update(kwargs)

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with client.messages.stream(**params) as stream:
                msg = stream.get_final_message()
            _log_usage(msg, org_id=org_id, call_type=call_type, model=model)
            return msg
        except Exception as exc:
            err = str(exc)
            if _is_credit_error(err):
                _credit_exhausted[api_key[:16]] = True
                logger.warning("claude_client: creditos agotados — circuit breaker ON")
                raise CreditsExhausted(err) from exc
            if _is_retryable(err) and attempt < retries:
                wait = _BASE_WAIT_S * (2 ** attempt)
                logger.warning(
                    "claude_client: error transitorio (intento %d/%d), espero %ds: %s",
                    attempt + 1, retries, wait, err[:120],
                )
                time.sleep(wait)
                last_exc = exc
                continue
            raise
    raise last_exc  # pragma: no cover
