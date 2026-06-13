# Vigilancia Normativa Automatica (regwatch)

Modulo "set it and forget it": el tenant activa un toggle y RiskHub mantiene su
catalogo normativo al dia. Inspirado en el patron auto-update de los SO modernos.

Spec funcional: `RISKHUB_REGULATORY_WATCH_MODULE_SPEC.md` (raiz del repo).

## Arquitectura

```
Fuentes publicas (EUR-Lex, BOE, NIST, ENISA, AEPD, ISO, ...)
        |  discover() / fetch() / parse()   (regwatch_connectors.py)
        v
NormativeChangeEvent  --IA + validacion humana interna-->  ChangePack
        |                                                      |
        |                                       publish_change_pack()
        v                                                      v
 catalogo central (global)                      TenantChangeInboxItem (por tenant
                                                con vigilancia ON y framework en uso)
```

Dos niveles de catalogo (spec §3.4):
- **Central** (global, mantenido por el equipo RiskHub): siempre actualizado.
- **Tenant**: consume el central + sus copias (politicas, plantillas). El toggle
  solo controla si recibe notificaciones y si sus copias se ven afectadas.

## Ficheros

| Fichero | Responsabilidad |
|---|---|
| `app/models.py` | Modelos `NormativeSource`, `NormativeChangeEvent`, `ChangePack`, `TenantRegwatchSettings`, `TenantChangeInboxItem` + enums `ChangeSeverity`, `ChangeEventStatus`, `InboxItemStatus`. |
| `app/services/regwatch_sources.py` | Catalogo maestro de fuentes (§3.1) y mapeo framework&rarr;fuente, etiquetas. |
| `app/services/regwatch_connectors.py` | Interfaz `BaseNormativeWatcher` (`discover/fetch/parse`) + conectores concretos y `run_source()` (idempotencia, circuit breaker simple). |
| `app/services/regwatch_service.py` | Logica de negocio: derivacion de frameworks, settings/toggle, estado de la tarjeta, inbox, historial, barrido, publicacion, autoria/validacion interna, seed. |
| `app/routers/regwatch.py` | Endpoints tenant (`/api/regwatch/...`) e internos (`/api/regwatch/admin/...`). |
| `app/static/js/views/regwatch.js` | UI: tarjeta toggle, estado, opciones avanzadas, inbox, wizard, historial, PDF. |

## Derivacion automatica de frameworks (§2)

`regwatch_service.derive_watched_frameworks(db, org_id)` no pide nada al usuario.
Combina:
1. `framework_code` distintos del modulo Compliance (`ComplianceFrameworkStatus`).
2. Flags regulatorios de proveedores TPRM (`is_nis2`, `is_dora`, `is_ens`,
   `is_data_processor`/`processes_personal_data` &rarr; GDPR).

Solo se devuelven frameworks con al menos una fuente vigilable.

## Severidad y routing (§3.3)

- `cosmetic` / `clarification`: `publish_change_pack` los aplica al catalogo y NO
  genera inbox; aparecen solo en el historial.
- `substantive` / `breaking`: generan `TenantChangeInboxItem` (status `pending`)
  para cada tenant con vigilancia ON, que usa ese framework y no lo tiene
  silenciado (`muted_frameworks`).

La clasificacion la propone la IA y la **valida un humano del equipo RiskHub**
antes de publicar (`validate_and_publish_event`). El cliente nunca ve un cambio sin
clasificar/validar.

## Conectores (§3.1, §11)

`BaseNormativeWatcher` define `discover() -> list[ChangeCandidate]`,
`fetch(candidate) -> RawDocument`, `parse(doc) -> ParsedNormative`. Principios:
user-agent identificado, timeout, idempotencia por SHA-256 (`ChangeCandidate.content_hash`),
circuit breaker simple (errores capturados en `run_source`, reflejados en
`last_run_status` / `last_run_error`).

En el despliegue on-premise sin red saliente garantizada, `discover()` degrada con
elegancia devolviendo `[]` (no es error: significa "sin novedades"). La red real y
las API keys se activan desde el panel interno (solo superadmin), nunca por el
tenant. Orden de implementacion de la red real (spec §13): EUR-Lex, BOE, NIST,
ENISA primero; ISO/PCI/CSA/CIS despues.

## Scheduler

`scheduler._run_regwatch_sweep` (job `regwatch_sweep`, cada 24h) ejecuta
`run_sweep()`: barre todas las fuentes activas y actualiza `last_sweep_at` de los
tenants con vigilancia ON.

## API

Tenant (`/api/regwatch`): `GET/PUT settings`, `POST enable|disable`, `GET status`,
`GET watched-frameworks`, `GET inbox`, `GET inbox/{id}`, `POST inbox/{id}/review|snooze|dismiss`,
`GET history`, `GET history.pdf`, `GET faq`.

Interno (solo superadmin): `GET admin/sources`, `GET admin/health`,
`POST admin/sources/{id}/run-now`, `POST admin/sweep`, `GET admin/events`,
`POST admin/change-packs`, `POST admin/events/{id}/validate`.

## RBAC (§8)

- **admin**: toggle, inbox (review/snooze/dismiss), opciones avanzadas.
- **analyst/viewer**: lectura de estado e historial.
- **superadmin (equipo RiskHub)**: gestion de fuentes, validacion de eventos,
  publicacion de change_packs, health. Aislado del tenant.

## Auditoria (§10)

Toda accion se registra via `audit_service.log_action`: enable/disable, cambios de
opciones, decisiones del wizard (review), snooze/dismiss, export PDF, y en el lado
interno: validate y publish.

## Feature flag

`module_regwatch` (incluido en planes pro y enterprise). Sembrado por
`feature_flags.seed_default_flags`.

## Como demostrar el flujo end-to-end (sin red saliente)

Como superadmin, publicar un change_pack de prueba crea inbox items en los tenants
afectados:

```
POST /api/regwatch/admin/change-packs
{
  "framework_code": "ENS",
  "severity": "substantive",
  "title_es": "ENS RD 311/2022 — Actualizacion guidance 2026-Q2",
  "description_es": "3 medidas modificadas, 1 nueva, 0 eliminadas.",
  "version_to": "2026-Q2",
  "controls_modified": [{"control_id":"op.acc.5","field":"texto","before":"...","after":"..."}]
}
```

El tenant (con ENS en uso y vigilancia ON) vera el item en
Cumplimiento &rarr; Vigilancia normativa.
