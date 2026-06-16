# Backlog — pendientes acumulados

Generado el 2026-06-16. Recoge todo lo que se ha hablado, planificado o
diagnosticado en sesiones recientes y que **todavia no esta hecho**, mas lo
que ya quedaba pendiente en `CLAUDE.md`. Lo que se completo y desplego en
esta sesion no aparece aqui (ver seccion "Hecho hoy" al final, solo a modo de
referencia de contexto).

## 1. Re-auditoria pendiente (accion a futuro, explicita)

- [ ] **Re-auditar todo el modulo BCP completo** con todos los cambios
  acumulados (versionado, sticky actions column, PATCH guard) y **volver a
  auditar todos los ultimos deploys** de la app en conjunto, no solo el
  ultimo commit. Pedido explicito del usuario, todavia no ejecutado mas alla
  de las comprobaciones puntuales de esta sesion (mapa de dependencias,
  orden de modos).

## 2. Versionado draft -> aprobado -> obsoleto: estado real por modulo

Patron ya implementado: **BCPPlan** (preexistente) y, en esta sesion,
**Policy** y **VendorRiskAssessment** (backend + UI minima). Ojo: la UI de
VendorRiskAssessment no tenia un formulario de edicion de contenido previo;
solo se anadio el boton "Nueva version" en el modal de detalle — sigue sin
existir un formulario para editar manualmente inherent/control/residual
score antes de aprobar la nueva version (hoy se copian los valores de la
version anterior tal cual).

- [ ] **SupplierQuestionnaire**: NO se aplico el patron de versionado. Es un
  cuestionario de punto-en-tiempo (con `submitted_at`, `score`,
  `next_questionnaire_id` para re-muestreo periodico) y no tiene un ciclo
  draft/aprobado equivalente — requiere decision de producto sobre si tiene
  sentido aqui o si el ciclo de "evaluacion -> nueva evaluacion" de
  `VendorRiskAssessment` ya cubre la necesidad real del usuario.
- [ ] **Evidence**: ya tenia patron de versionado (`previous_version_id`,
  `is_current`) pero **se detecto un bug latente real**: en
  `app/routers/evidence.py::upload_new_version` (linea ~285) la nueva fila
  reutiliza `code=ev.code`, y `Evidence.code` tiene `unique=True` en el
  modelo → si alguna vez se sube una segunda version de una evidencia,
  el `INSERT` deberia fallar por violacion de constraint UNIQUE. No se
  reprodujo en local (no habia filas de evidencia) ni se ha arreglado.
  **Revisar y corregir** (generar un `code` nuevo por version, igual que se
  hizo para `Policy`/`VendorRiskAssessment` en esta sesion).
- [ ] **Resto de "documentacion" de la plataforma** (el usuario pidio
  aplicar el patron "a lo largo de toda la documentacion"): no se ha
  evaluado exhaustivamente que otras entidades documentales existen
  (p.ej. `AiDocument`, plantillas TPRM clonadas, `ComplianceFrameworkStatus`)
  para decidir si necesitan el mismo ciclo de vida. Pendiente de barrido.

## 3. Infraestructura / deploy

- [ ] **Backup pre-deploy roto en produccion**: cada `deploy.sh` muestra
  `ERROR: No se encontro la BD en /var/lib/docker/volumes/riskhub-data/_data/riskhub.db`
  (visto de nuevo en el deploy de hoy, commit `e21dd7e`). El script
  continua igualmente ("no critico") pero **no hay red de seguridad real**
  antes de aplicar migraciones de esquema en produccion. Hay que localizar
  la ruta real del volumen Docker en el host y corregir el script de
  backup.

## 4. CLAUDE.md — "Pendiente" (no tocado en esta sesion)

- [ ] **Multi-idioma i18n (es/en/de/fr)**: decision ya tomada (selector en
  header, `app/static/js/i18n/{es,en}.json`, funcion global `t('key')`,
  primero refactorizar vistas a `t()` manteniendo ES, luego anadir EN).
  Diferido hasta que la app este estable — sigue diferido.
- [ ] **`guide.js`** sin actualizar con documentacion de las secciones:
  evidence, webhooks, external-findings, magerit, ccm, itsm, trust-portal,
  executive, architecture-review, erp-webhooks, clausulas-iso. Tambien
  faltaria documentar ahi el nuevo flujo de versionado de Politicas/TPRM.
- [ ] **Pruebas end-to-end manuales** de las vistas nuevas con un usuario
  real (evidence, webhooks, external-findings, predictive, ccm,
  itsm-config, trust-portal, magerit, executive, architecture-review, cve,
  osint, feature-flags) — no realizadas.

## 5. TPRM — pendientes ya anotados en `docs/tprm/CHANGELOG.md` / spec

- [ ] Editor de plantillas TPRM.
- [ ] Portal con evidencias para proveedores.
- [ ] Conectores de monitorizacion continua.
- [ ] Reporting TPRM dedicado.

## 6. Regwatch — pendientes ya anotados en spec v4.0.0

- [ ] Digest por email de cambios normativos.
- [ ] Versionado de `compliance_control` (catalogo).
- [ ] Migracion de plantillas clonadas cuando cambia la fuente normativa.

## 7. Otros hallazgos de esta sesion, sin resolver

- [ ] `app/routers/ai.py` tenia un cambio local sin commitear desde antes de
  esta sesion (max_tokens 4096->8192 en `architecture_review` + manejo de
  `stop_reason == "max_tokens"`). Se incluyo en el commit de hoy
  (`e21dd7e`) y ya esta desplegado, pero no fue verificado en vivo en esta
  sesion (no se ejecuto un architecture review real contra produccion) —
  conviene probarlo la prox vez que se use esa funcionalidad.

---

## Hecho hoy (contexto, no backlog)

- Fix BCP: PATCH `/api/bcp/plans/{id}` ya no permite mutar contenido ni
  forzar `status=approved` en un plan ya aprobado; obliga a usar
  `/plans/{id}/approve` o el flujo de nueva version desde la UI.
- Policies: nuevo `POST /api/policies/{id}/new-version`, PATCH bloqueado
  para contenido si `status in (approved, published)`, auto-obsoleta la
  version anterior al aprobar la nueva (`previous_version_id`).
- TPRM: nuevo `POST /api/vendor-assessments/{id}/new-version`, PATCH
  bloqueado tras `approved_at`, `is_current` se pone a `False` en la
  version anterior al aprobar la nueva re-evaluacion.
- Desplegado en produccion (commit `e21dd7e`), migracion de columnas
  verificada en la BD de produccion via `docker exec`.
