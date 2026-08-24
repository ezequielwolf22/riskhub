# RiskHub - Contexto para Claude Code

## Que es este proyecto

Aplicacion web GRC (Governance, Risk, Compliance) para gestion del riesgo
de seguridad de la informacion, basada en **ISO/IEC 27005:2018** con
catalogo de controles **ISO/IEC 27002:2022**.

**Uso**: on-premise en servidor interno, no expuesta a internet.
Multi-usuario con roles.

## Infraestructura de produccion

- Servidor: Hetzner CX22 — Ubuntu 24.04 — IP 91.99.83.202
- Acceso SSH: `ssh root@91.99.83.202 -i ~/.ssh/id_ed25519`
- App: http://91.99.83.202 via Docker (puerto 80)
- Repo GitHub: github.com/ezequielwolf22/riskhub (privado)
- Deploy: en el servidor ejecutar `bash /opt/riskhub/deploy.sh`

## Decisiones tecnicas

- **Backend**: Python 3.11 + FastAPI + SQLAlchemy 2.0 + SQLite (default) / PostgreSQL (opcional).
- **Frontend**: HTML + Vanilla JS + CSS. Sin frameworks, sin CDNs, todo servido en local.
- **Autenticacion**: JWT (HS256) + bcrypt. Access token 60 min + refresh token rotativo 12h (`/api/auth/refresh`); revocacion por jti (`revoked_tokens`) = logout real. Roles: `superadmin`, `admin`, `analyst`, `viewer`.
- **PDF**: ReportLab con paleta purple/orange.
- **Despliegue**: Docker + docker compose. Volumen `riskhub-data` para BD persistente.
- **IA**: Claude API (Anthropic). RAG con SQLite FTS5. Anonimizacion regex configurable.
- **Branding**: Paleta purple `#59008D` / orange `#D65200`. Variables CSS: `--brand-purple`, `--brand-orange`. Tipografia: Inter.
- **Seguridad**: Lockout de login por IP y por cuenta (persistido en rate_limits.db), rate limiting global de API por IP (600/min, `RISKHUB_API_RATE_PER_MINUTE`), security headers middleware, magic bytes validation, API docs deshabilitados en produccion.

## Estado actual (v2.2.0)

### Backend

- [x] Modelos ISO 27005 (`app/models.py`)
- [x] Esquemas Pydantic (`app/schemas.py`)
- [x] Motor de calculo (`app/services/risk_engine.py`): matriz 5x5 ISO 27005 Annex E.2
- [x] Endpoints REST en `app/routers/` (auth, users, assets, risks, controls, suppliers, incidents, nonconformities, tasks, policies, audits, gdpr, reports, ai, ai_config, documents, admin, audit, alerts, search, context, catalogues)
- [x] Catalogos precargados: 49 amenazas, 67 vulnerabilidades, 93 controles ISO 27002
- [x] Seed inicial: admin + contexto + catalogos. Migraciones incremetales en `_migrate_columns()` de seed.py
- [x] Agente IA: chat conversacional, RAG FTS5, anonimizacion, feedback loop
- [x] Cifrado Fernet para API key del agente IA
- [x] Hardening OWASP: rate limiting login, security headers, magic bytes upload, autodocs off en produccion
- [x] Multi-tenancy: modelo Organization, organization_id en 25+ modelos, filter_by_org helper, seed auto-migra columnas
- [x] Router /api/organizations: CRUD completo (superadmin), move user, stats de uso de tokens
- [x] OSINT: escaneo email/dominio/IP/URL/username; hallazgos; auto-incidente en CRITICAL/HIGH; re-scan periodico semanal
- [x] Automatizaciones scheduler (APScheduler): escalada de tareas, revision de politicas, degradacion de controles, informe mensual
- [x] Hooks de creacion: Incidente→auto-link risks; NC→auto-link risk; Riesgo→deteccion duplicados (HTTP 409)
- [x] Proveedor→riesgo auto-create: cuando score <= 30, crea riesgo supply-chain ISO 27005 automaticamente
- [x] ISMS analysis: documento→activo linkage automatico por nombre; controles actualizados trigger re-analisis activos
- [x] OSINT→activos: link_osint_findings_to_assets; OSINT→incidente auto-create (v1.7.6)
- [x] CVE integration: NVD API, escaneo automatico, analisis IA, link a activos
- [x] Licenciamiento por plan: PLAN_MODULE_LIMITS (free/starter/pro/enterprise) en `feature_flags.py`; enforcement en PATCH; endpoint GET /api/feature-flags/plans/limits
- [x] SSO OIDC/SAML: backend completo en `routers/sso.py` (Entra ID, Google, Okta); UI config en Integraciones; boton SSO en login.html
- [x] SharePoint: backend completo en `routers/sharepoint.py`; UI config + file browser en Integraciones
- [x] ERP Webhooks: `routers/integrations_erp.py` — SAP/Jagger/Sphera via HMAC-SHA256; mapeo eventos a activos/incidentes; log en memoria; config cifrada Fernet. **Backend existe pero la UI fue retirada a peticion expresa del usuario (2026-07-07): NO volver a anadir la card "ERP Webhooks" en integrations.js ni la seccion en guide.js salvo que el usuario lo pida explicitamente.**
- [x] Extraccion clausulas ISO: `services/iso_clause_extractor.py` — Claude Haiku extrae refs ISO 27001/27002 tras analisis ISMS; campo `extracted_clauses` en AiDocument; modal en ai-documents.js
- [x] TPRM (Sprint 1): `Supplier` ampliado con ciclo de vida, tier, inherent/residual risk y flags regulatorios; `services/tprm_scoring_service.py` (inherent §4.2 / tiering §4.3 / residual §5.2 / scoring cuestionarios §4.7.1); `services/tprm_templates.py` (7 plantillas del sistema clonables con mapeo a controles); `routers/tprm.py` (`/api/tprm`: dashboard, heatmap, recompute, plantillas); `supplier_questionnaires` acepta `template_code` con scoring ponderado; vista `tprm.js` en el hub de Proveedores. Spec: `RISKHUB_TPRM_MODULE_SPEC.md`; changelog `docs/tprm/CHANGELOG.md`.
- [x] TPRM (Sprints 4/5/7): `VendorRiskAssessment` + `routers/vendor_assessments.py` + `services/vendor_assessment_service.py` (evaluacion consolidada, score por dominio, `:approve`, `:push-to-risk-register` a ISO 27005); `services/tprm_ai_service.py` + `POST /api/supplier-questionnaires/{id}/ai-review` (evaluacion IA con guardrails, auto-trigger en submit, resultado en `SupplierQuestionnaire.ai_review`); `VendorIssue` + `routers/vendor_issues.py` (hallazgos con SLA por severidad y vencimiento automatico). Vistas `vendor-assessments.js` y `vendor-issues.js` en el hub de Proveedores. Tests en `tests/test_tprm_*.py`. Backlog cerrado (2026-07-14): editor de plantillas (`vendor-templates.js` + CRUD `/api/tprm/custom-templates`), portal con evidencias (`supplier-q.html` + `/public/{token}/upload` con magic bytes/limite/SHA-256), monitorizacion (`supplier_monitoring_service`: web/SSL/DNS semanal) e **informe TPRM** (`GET /api/reports/tprm`: PDF con inventario por tier/riesgo, evaluaciones vigentes, hallazgos con SLA y estado de cuestionarios; boton en Informes; locale `reports_tprm.json`; `tests/test_reports_tprm.py`). Fuera de alcance: rating de pago (BitSight/SecurityScorecard), export DOCX/XLSX/PPTX del informe, offboarding.
- [x] Regwatch (Vigilancia Normativa Automatica — Sprint 6 completo): modelos `NormativeSource`/`NormativeChangeEvent`/`ChangePack`/`TenantRegwatchSettings`/`TenantChangeInboxItem`; `services/regwatch_sources.py`; `services/regwatch_connectors.py` (11 conectores HTTP reales — EUR-Lex SPARQL, BOE RSS, ENISA RSS, AEPD/EDPB RSS, NIST JSON/RSS, EBA RSS, ISO status, AICPA, PCI, CSA, CIS — todos con degradacion graceful); `services/regwatch_service.py` (toggle, inbox, historial, sweep, pipeline IA Claude Haiku con auto-publicacion); `services/regwatch_propagation.py` (propagacion cross-plataforma: catalog update, flag `ControlImplementation` SoA, `Policy`→status review, `BCPPlan`→under_review, `SupplierQuestionnaire`, `ComplianceFrameworkStatus`, crea `TreatmentTask` en riesgos afectados); `routers/regwatch.py` (20 rutas tenant + admin). Vista `regwatch.js` (wizard con badges de impacto + resumen de propagacion). Columnas v4.0.0: `deprecated_at` en `controls`; `regwatch_review_at`/`regwatch_pack_id` en `control_implementations`, `policies`, `bcp_plans`, `supplier_questionnaires`, `compliance_framework_status`. Backlog cerrado (2026-07-14): digest periodico por canales (email/Teams/PA) via `send_pending_digests` + job diario 8h UTC (respeta `digest_frequency` por org, nunca envia vacio); versionado — `compliance_framework_status.framework_version` sellada con `pack.version_to` al propagar; migracion de plantillas TPRM clonadas — `regwatch_review_at`/`regwatch_pack_id` en `tprm_templates`, con `auto_apply_to_clones` re-sincroniza preguntas nuevas del sistema sin tocar las editadas (`_migrate_cloned_templates`). Tests en `test_regwatch_digest.py` y `test_regwatch_propagation_v67.py`.
- [x] Canales de alerta sin SMTP (Microsoft Teams / Power Automate): `services/notification_channels.py` (send_teams_alert con formato `{"text": "..."}` compatible con la plantilla nativa de Teams Workflows; send_power_automate_alert con JSON generico; dispatch_alert combina email/Teams/PA por org); columnas `teams_webhook_url_encrypted`/`teams_webhook_enabled`/`power_automate_webhook_url_encrypted`/`power_automate_webhook_enabled` en `EmailSettings` (Fernet, igual que SMTP password); endpoints `/api/alerts/channels` (GET/PUT/DELETE/test para teams y power-automate) en `routers/alerts.py`; `_run_alert_rules` en `scheduler.py` y `check_rules`/`send_risk_alert` ya no exigen SMTP — usan `notification_channels.has_any_channel`/`dispatch_alert`. UI en la vista Alertas (`alerts.js`). Pensado para clientes que no permiten SMTP por politica de seguridad.
- [x] Excelencia de analisis IA v6.0.0 (2026-07-10, 6 sprints — commits 2a78d65..7bc836c). Principio rector: la IA propone entradas (amenazas, inherentes calibrados, contribuciones); el motor determinista calcula el residual con trazabilidad. Piezas:
  - Motor residual v2: `risk_engine.control_reduction_split` (reduccion separada likelihood/consequence por tipo de control P/D/C via `classify_control`); madurez ajustada por calidad de evidencia (`adjusted_maturity` + revision IA E1-E5); `services/risk_recalc_service.py` = autoridad unica de recalculo (el router reexporta `_recalc`); recalculo one-shot v2 registrado en tabla `app_migrations`; fin del override del residual del LLM en `_upsert_risk` (se guarda como sugerencia en `risks.ai_context_meta`).
  - Catalogo amenaza->control: `app/data/threat_control_map.json` (97 amenazas ISO 27005 + MAGERIT, revisable; regenerable con `scripts/generate_threat_control_map.py`), tabla `threat_control_overrides` por org, `services/threat_knowledge.py` (candidatos por amenaza + fallback determinista de contribuciones).
  - Paridad batch/individual en `asset_risk_analysis_service`: mismo esquema de salida, criterios de calibracion, controles candidatos con impl_id, persistencia unificada; lote de 5 activos; senales de vigilancia por activo.
  - Triggers de recalculo: degradacion scheduler, analisis ISMS, evidencias analizadas; marcado `analysis_stale`/`stale_reason` en ingesta CVE/OSINT y cambios de madurez (badge DESACT. + panel "Fuentes consideradas" en risks.js).
  - Evidence understanding: `services/evidence_understanding_service.py` (texto o Claude Vision para imagenes/PDF escaneado; salida {relevant, quality_level E1-E5, key_facts, controls_supported, red_flags}; trigger al subir + job nocturno cap 20/org; `evidence.ai_review`); tipos nuevos meeting_minutes/training_record/phishing_campaign; `POST /api/evidence/{id}/analyze`; documents con Vision para escaneados y soporte XLSX.
  - Contexto total: `build_asset_risk_context`/`render_asset_risk_context` en `risk_analysis_helpers` (perfil, criterios calibracion, vigilancia CVE/OSINT/Regwatch, normativa, incidentes, RAG); `build_context` con secciones CVE/OSINT/factor humano/actas/auditorias/GDPR/BCP/TPRM + indice FTS `ai_entity_fts` de entidades de negocio (job nocturno `refresh_entity_index`).
  - TPRM: `tprm_ai_service` analiza el contenido de evidencias de cuestionario (`analyze_questionnaire_evidence`, cache en `q.evidence[qid].ai_review`), VendorIssue automatico si contradice, perfil+historico en el prompt; scoring con 4 estados de evidencia (x0.5/x0.7/x1.0/x0.4).
  - Regwatch: analisis con texto completo descargado + doble pasada fast->deep; evento vinculado a su pack; propagacion TPRM dirigida por `controls_affected_hint`.
  - Gap detallado: 93 controles por temas (fast) + sintesis (deep), con riesgos vinculados, NCs, regwatch y evidencia IA por control. Informes con TPRM/incidentes/regwatch/evidencia; informe mensual con sintesis IA.
  - `services/model_registry.py`: tiers deep=claude-opus-4-6 / fast=claude-haiku-4-5 (fuente unica); chat y suggest-controls en deep por defecto.
- [x] Aprendizaje in-context (2026-07-10): `services/ai_learning_service.py` — senales de decision del usuario (tabla `ai_decision_signals`, hooks en risks/vendor assessments) -> destilacion nocturna determinista (min 3 senales) -> lecciones por org en `RiskContext.ai_learned_lessons` inyectadas en prompts (solo advisory, nunca toca el motor). Endpoints `/api/ai/learning`. `services/claude_client.py`: cliente unificado (retries+circuit breaker), `structured_message` (tool use forzado con schema = JSON validado por la API; obligatorio para codigo IA nuevo con salida JSON) y `cached_system` (prompt caching).
- [x] Ciclo SaaS (2026-07-11, commits 9a2fc00..HEAD):
  - Cola de trabajos en BD: `services/job_queue.py` (claim atomico, backoff, dedupe, recuperacion tras crash; workers en startup); handlers asset_analysis_all / evidence_analysis / document_vision_isms; router `/api/jobs`.
  - Observabilidad: middleware en main.py (X-Request-ID, access log, contadores, captura en tabla `app_errors` con 500 limpio + referencia); `/api/metrics` (Prometheus text, admin); `/api/admin/errors` (superadmin); `/api/ai/usage` (consumo/coste IA del mes por tipo+modelo, tendencia, presupuesto blando por plan en `model_registry.AI_MONTHLY_TOKEN_BUDGETS`).
  - Hardening de acceso: jti en todos los JWT + tabla `revoked_tokens` + `/api/auth/logout` (logout real, cache en memoria TTL 30s); refresh tokens con rotacion (`/api/auth/refresh`, access 60min / refresh 12h, config `jwt_expires_minutes`/`jwt_refresh_expires_minutes`); lockout de login por cuenta ademas de IP; rate limit global de API (`rate_limiter.check_api_rate`); api.js renueva sesion automaticamente ante 401 y reintenta una vez.
  - Backups: `services/backup_service.py` (API de backup de sqlite3 + gzip, nocturno 2:30 UTC, retencion 14d, `RISKHUB_BACKUP_DIR`/`RISKHUB_BACKUP_RETENTION_DAYS`); endpoints `/api/admin/backups` (listar/lanzar/descargar, superadmin); runbook `docs/BACKUP_RESTORE_RUNBOOK.md`. Migracion PostgreSQL: **Fase 0-1 hechas (2026-07-14)** — codigo portable (`database.is_sqlite`/`insert_ignore`; `_migrate_columns` via `sqlalchemy.inspect`; strftime->substr(cast); RAG degrada a ILIKE en PG con `_run_fts_like`, entidades vacio), servicio `db` postgres:16 en compose (perfil `postgres`, `RISKHUB_DATABASE_URL`), job CI `test-postgres` no bloqueante, `conftest` sensible a `RISKHUB_DATABASE_URL`, `scripts/migrate_sqlite_to_postgres.py`. Pendiente: tsvector/entidades (Fase 1 restante) y cutover de datos en prod (ventana del usuario, Fase 3). Detalle en `docs/POSTGRES_MIGRATION_PLAN.md`.
  - CI: `.github/workflows/ci.yml` (pytest + ruff + docker build en push/PR a main).
  - Vista Operaciones (`ops.js`, pestana en Configuracion): consumo IA, cola de jobs, errores capturados y backups.
- [x] Economia del analisis IA (2026-07-13, commits 0258ee0..61592e0): grupos validados cubren a sus miembros (skipped, 0 tokens); tier Haiku en el masivo con Opus para criticos (CIA>=4) e individual; dieta de salida (3-5 escenarios sobre apetito); Message Batches API de Anthropic (50%) para >=25 activos con cancelacion cooperativa; estimador previo `GET /api/assets/analysis-cost-estimate` + confirmacion con coste en la UI; modo maxima calidad por org (`AiConfig.force_deep_analysis`, checkbox en IA->Configuracion). Medido en prod: ~$0.007/activo con Haiku (28x menos que Opus individual). `ruff.toml` con reglas de correccion activas (cazaron 5 bugs latentes: incidents UnboundLocalError, scheduler timedelta/Organization, ai.py logging, claves duplicadas RAG); CI en verde.
- [x] Refacturacion IA superadmin (2026-07-13): columna `ai_call_logs.key_source` ('vendor' = key global de plataforma refacturable | 'org' = key propia del tenant; se registra en `claude_client._log_usage` comparando con `settings.anthropic_api_key`); `GET /api/ai/usage/global` (superadmin: consumo/coste por org del mes con split refacturable, fila Plataforma para org NULL — regwatch —, `?org_id=` detalle por call_type, `?month=YYYY-MM`); panel "Costes IA por organizacion" en ops.js con selector de mes y detalle expandible. El gap detallado usa `structured_message` troceado (12 controles/chunk, fin de los 500 por JSON truncado). Tests en `tests/test_ai_usage_global.py`.
- [x] Plan de Tratamiento y Plan Director (2026-07-16, v6.3.0). Principio rector: maxima automatizacion — la iniciativa declara controles objetivo y madurez, el sistema deriva riesgos afectados y proyecta el residual con el MISMO motor determinista del recalculo real; la IA solo estructura/propone, nunca vincula riesgos directamente. Piezas:
  - Modelos: `StrategicProgram` → `StrategicInitiative` (health ok/at_risk/blocked computado, nunca manual) → `InitiativeObjective` (OKR) + `InitiativeControlTarget` (control + madurez objetivo, nucleo de la automatizacion) + `InitiativeRiskLink` (origin auto/manual/ai_import/ai_draft, baseline/proyectado/conseguido) + `InitiativeLogEntry` (bitacora system/ai_summary/humana). `TreatmentTask.initiative_id` enlaza tareas operativas a una iniciativa.
  - Motor (`services/initiative_projection_service.py`): `residual_from_payloads` extraido de `risk_recalc_service.recalc_risk` (funcion pura reutilizada); `auto_link_risks` (directo via risk_controls + catalogo amenaza-control, solo riesgos sobre apetito); `project_initiative` (simulacion what-if: sube maturity_raw al objetivo asumiendo evidencia razonable, nunca empeora); `verify_initiative` (al completar, sella achieved_maturity/achieved_residual_level y expone gaps sin ocultarlos); `compute_burndown` (historico real `RiskSnapshot` + proyeccion sin doble conteo entre iniciativas); `refresh_initiative_health` (5 reglas objetivas); `send_initiative_digest`. `risk_recalc_service.recalc_risks_for_impls` reproyecta automaticamente las iniciativas activas afectadas (import diferido, sin ciclo).
  - Router `app/routers/initiatives.py` (`/api/initiatives`: programas, iniciativas, OKRs, control-targets, risk-links, log, stats, burndown, import/import-confirm, draft-for-risk); `GET /api/risks/treatment-board` (cockpit agregado: KPIs, columnas por opcion de tratamiento, burndown); `POST /api/risks/{id}/ai-treatment-plan`.
  - IA (`services/initiative_ai_service.py`, `structured_message` + `model_registry`, nunca hardcodeado): `parse_plan_document` (import PDF/DOCX/XLSX/TXT → programas/iniciativas/OKRs/control-targets, codigos de control validados contra catalogo real, fechas invalidas descartadas); `draft_initiative_for_risks` (borrador para riesgos sin cobertura, controles candidatos de `threat_knowledge`); `draft_treatment_plan` (borrador de plan+tareas para un riesgo); `run_monthly_narratives` (narrativa mensual, cap 20/org, solo iniciativas con actividad en 30d).
  - Scheduler: salud semanal (lunes 7h UTC), narrativa mensual (dia 1, 6h UTC), digest al comite (dia 1, 8h UTC vía `notification_channels`, nunca envia si no hay nada relevante).
  - Vistas: `treatment.js` (Cockpit de Tratamiento — pestana "Tratamiento" en hub Riesgos) y `plan-director.js` (Resumen + Plan + wizard + import + detalle con verificacion) — pestana "Plan Director", plan pro/enterprise (`module_plan_director`).
  - Informe: `GET /api/reports/treatment-plan` (PDF: riesgos sobre apetito, plan director, verificaciones, aceptados, tareas vencidas); boton en Informes.
  - Tests: `test_initiatives.py`, `test_initiative_projection.py`, `test_treatment_board.py`, `test_initiative_ai.py` (IA mockeada), `test_initiative_health.py`, `test_reports_treatment.py`.
- [x] Plan Director v6.4.0 — el metodo completo (2026-07-22). El modulo implementaba de la fase 3 en adelante; faltaba donde nace un plan director. Investigado contra INCIBE (canon espanol del PDS), NIST CSF 2.0 (Current/Target Profile) e ISO 27001 6.1.3/8.3/9.3:
  - **Fases 1-2**: `StrategicPlan` (periodo, version, alcance, linea base sellada al aprobar) + `MaturityTarget` (perfil objetivo) + `services/strategic_profile_service.py` (perfil actual desde la madurez real -> gap -> iniciativas candidatas deterministas). El objetivo se fija en el lenguaje del cliente (categoria NIST CSF, requisito ENS) y `data/frameworks/control_crossmap.json` lo traduce a controles ISO 27002. **Limitacion declarada**: el crossmap cubre 16 de las 21 categorias CSF; GV.OC, GV.OV, ID.IM, RC.CO y RS.CO se devuelven como `unresolved_targets` en vez de descartarse en silencio.
  - **Fase 4 (priorizacion INCIBE)**: `compute_portfolio_priorities` — eficiencia (puntos de riesgo por unidad de esfuerzo), quick wins por percentiles de la cartera (exigen ademas estar en el tercio mas eficiente), coste por punto, horizonte corto/medio/largo. Campos `origin`/`action_type`/`effort_human`/`env`(IT|OT|IoT|AI)/`last_achievements`/`next_steps`/`blockers`/`blocked_by`. `GET /api/initiatives/portfolio`.
  - **Fase 5 (aprobacion, ISO 6.1.3f)**: `PlanApproval` en tabla propia + `services/plan_approval_service.py`, dos modos por org (`internal_seal` con hash del contenido | `signature` con token, IP y caducidad). `approved` es **inalcanzable por PATCH**; cambiar el alcance sube version y exige re-aprobacion; el drift tras aprobar se muestra, no se oculta. Aceptacion formal del riesgo residual expuesta en el cockpit.
  - **Cronograma**: `GET /api/initiatives/roadmap`, Gantt SVG vanilla (mes/trimestre, linea de hoy, color por salud, camino critico), `compute_critical_path` + `detect_dependency_cycles`, salud heredada por dependencia, matriz iniciativa x unidad de negocio, analitica presupuestaria (el aprobado deberia seguir al avance), auto-tareas desde controles objetivo.
  - **Informe**: `GET /api/reports/strategic-plan/{id}` con estructura INCIBE y hoja de firmas. El Plan Director alimenta la revision por la direccion (`management_review_service.get_strategic_plan_status`).
  - Router `app/routers/strategic_plans.py`; vistas: pestanas "Diagnostico", "Cronograma" y "Cartera" en `plan-director.js`.
  - Tests: `test_strategic_plan.py`, `test_strategic_plan_method.py`, `test_strategic_roadmap.py`, `test_strategic_plan_report.py`, `test_initiatives_regressions.py`.
- [x] Ingesta cognitiva del modulo BCP (2026-07-22, v6.5.0, rama `claude/bcp-import-agentico`). Principio rector: **el agente comprende y propone; el motor determinista descompone, reconcilia, calcula y deja marcha atras**. El cliente llega con su documentacion en su formato, o sin nada, y el modulo queda montado. Piezas:
  - **Dominio BCM por escenario** (`BCMScenario` / `BCMScenarioAssessment` / `BIACriteria` / `BCMApplicabilityRule`): el BIA canonico de ISO 22301 gira sobre procesos, pero muchas organizaciones lo construyen sobre **escenarios de indisponibilidad valorados en cada sede**; ambos conviven. `BIACriteria` declara el metodo del cliente (dimensiones, horizontes, escala de RTO, bandas) y `bcm_scenario_engine.py` calcula con el: impacto ponderado, banda, aplicabilidad, matriz y huecos. **La aplicabilidad no es un atributo del escenario**: vive en `BCMApplicabilityRule` y por defecto NO hay reglas — todos los escenarios aplican a todas las sedes. Una regla solo puede quitar, y si la sede no tiene informado el atributo del que depende, no dispara. `BCMLocation` gana `site_type`/`staffing_model`/`city`/`business_unit`.
  - **Motor generico de ingesta** (`app/services/ingest/`, agnostico al modulo): `contracts.py` (EntitySpec/FieldSpec, claves naturales y politica de conflicto **por campo**; `describe_for_prompt()` genera el catalogo que ve el modelo desde el registro, nunca a mano), `reader.py` (extraccion **preservando estructura** — hojas, bloques, tablas y secciones con su referencia de origen y el numero de fila real; los extractores de `document_service` aplanan y para un BIA eso destruye la informacion que dice como descomponerlo), `reconciler.py` (crear vs enlazar sin LLM), `conflicts.py` (gana el mas restrictivo, el descartado queda con su fuente citada), `materializer.py`, `batch.py` (deshacer lote, revertir registro, forzar valor). `bcp_targets.py` declara las 10 entidades BCP. Enchufar otro modulo es declarar `EntitySpec`, no tocar el motor.
  - **Comprension** (`comprehension.py`, unico sitio con LLM, `structured_message` + `model_registry`): pasada 1 lee el pack entero y deduce el perfil (`OrganizationProfile`: sedes, unidades, metodo, escenarios, vocabulario); pasada 2 produce el **mapa de volcado** por documento, que declara COMO SE DESCOMPONE y por que ("cada bloque de 7 filas encabezado por el nombre del escenario en la columna B"). `pipeline.py` orquesta y verifica. Una regla de aplicabilidad propuesta por la IA nace **desactivada**; el estado de aprobacion de un plan nunca se importa; un campo `computed` no se escribe aunque venga en el documento.
  - **Garantias**: `IngestBatch`/`IngestRecordTrace`/`IngestSourceMap`/`IngestConflict`/`IngestFieldOverride`. Un campo corregido a mano **sobrevive a reimportar** y emite senal a `ai_learning_service`. Router `/api/ingest` (15 rutas) con estimacion de coste previa.
  - **Sin documentacion** (`generation.py` + `/api/bcp/generate/*`): propone escenarios, BIA, planes y estrategias desde el perfil y lo ya cargado, con un "why" anclado a un dato real. Cuestionario adaptativo que solo pregunta lo que no puede deducir.
  - Tests: `test_bcm_scenario_engine.py`, `test_bcm_scenario_api.py`, `test_ingest_core.py`, `test_ingest_pipeline.py`, `test_bcm_generation.py`.
  - **Pendiente**: `ISP_11` del cliente para sembrar el catalogo canonico de escenarios; validacion end-to-end contra la API real con el pack completo.
- [x] El metodo del cliente gobierna el calculo (2026-07-23, v6.6.0). La plataforma calculaba con SU metodo — escalas, umbrales, pesos y formulas cableados —, asi que un cliente con politica aprobada distinta recibia cifras que no eran las suyas y ademas operaba en incumplimiento de su propia norma. Principio: **el metodo del cliente gobierna sus cifras; la norma gobierna el veredicto de cumplimiento**, y son dos preguntas que no se mezclan. Piezas en `app/services/method/`:
  - `registry.py` — catalogo **en codigo** de que es configurable (18 parametros entre BCM, riesgo y TPRM): se revisa en el diff, no se desincroniza de los motores y le da a la IA un vocabulario cerrado. El campo `wired` dice si el motor ya lo consume de verdad; se muestra tal cual y es la lista de lo que falta por parametrizar.
  - `bindings.py` — `resolve()` con precedencia **manual > politica del cliente > defecto** y **procedencia**: devuelve el valor y de donde sale, para que una cifra lleve al lado "segun tu ISP_11 §6.3". Un valor invalido cae al defecto y se registra en vez de tumbar un recalculo; una propuesta extraida de un documento no pisa lo fijado a mano.
  - `formula.py` — evaluador acotado para lo que los parametros no expresan (`0.4*financiero + 0.6*operativo`). **Sin `eval`**: `ast.parse` + lista blanca de nodos, solo variables declaradas, solo funciones matematicas, topes de longitud/profundidad/exponente. 23 vectores de ataque en los tests.
  - `extraction.py` — enganchado en la pasada 1 de la ingesta: extrae declaraciones de metodo **con cita literal obligatoria**. Lo que no encaja en ningun parametro se guarda como `unmodelled` con su cita, nunca se descarta. No auto-aplica lo que recalcularia datos existentes.
  - `conformance.py` + `data/normative_minima.json` — cuatro hallazgos: `default_used_despite_policy`, `manual_override_diverges_from_policy`, `unmodelled_rule` y `policy_below_norm` (su metodo mas laxo que la norma: **se calcula con el suyo** y se levanta el hallazgo citando ambas fuentes).
  - Router `/api/method`. Modelos `MethodStatement`/`MethodBinding`/`MethodFinding`.
  - **Bug preexistente corregido**: `RiskContext.risk_matrix` se respetaba en `risk_recalc_service` y `risk_auto_generator` pero NO en los riesgos creados desde CVE, OSINT, el agente o import CSV, que llamaban `calc_level` pelado — el mismo par consecuencia/probabilidad daba niveles distintos segun quien lo creara. Ahora todos pasan por `risk_engine.org_matrix()`, y `test_method_wiring.py` barre esos cuatro routers para que nadie vuelva a olvidarse.
  - Garantia con test: **sin metodo declarado los tres motores dan exactamente lo mismo que antes**.
  - Tests: `test_method_formula.py`, `test_method_registry.py`, `test_method_wiring.py`, `test_method_conformance.py`.
- [x] Multi-tenancy: la organizacion enfocada por el superadmin manda (2026-07-22). Las lecturas ya respetaban `X-Active-Org` pero las **escrituras** usaban la org propia del superadmin: el POST devolvia 200 y el dato desaparecia de la vista del cliente (365 usos de `current_user.organization_id` en routers). Arreglo **central** en `get_current_user`: si hay org enfocada, esa es la del usuario durante la peticion, via `set_committed_value` para que **nunca** se escriba en su fila. `real_org_id()` para los pocos sitios que necesitan la org de ORIGEN (proteger que el superadmin no borre la suya). Aislamiento auditado: `tests/test_tenant_isolation.py` (incluye el vector de un admin normal falsificando `X-Active-Org`) + barrido de 194 rutas GET sin fugas.

### Frontend

- [x] SPA hash-based (`app/static/`)
- [x] Vistas: dashboard, heatmap, assets, threats, vulnerabilities, risks, controls, reports, context, users, suppliers, incidents, nonconformities, tasks, policies, audits, gdpr, compliance, alerts, integrations, audit, ai-chat, ai-documents, onboarding, guide, organizations
- [x] Vistas nuevas: evidence, webhooks, external-findings, predictive, ccm, itsm-config, trust-portal, magerit, executive, architecture-review, cve, osint, feature-flags, ops (operaciones: consumo IA, jobs, errores, backups), treatment (Cockpit de Tratamiento), plan-director (Plan Director)
- [x] Organizaciones: badges de plan con colores, modulos incluidos/bloqueados segun plan, plan selector actualizado (free/starter/pro/enterprise)
- [x] Integraciones: SSO config form, SharePoint config + browser, ERP webhooks config real (reemplaza placeholder)
- [x] Docs IA: modal de clausulas ISO extraidas con confianza y link a controles

### Despliegue

- [x] Dockerfile (python 3.11-slim, healthcheck, usuario no root)
- [x] docker-compose.yml (volumen persistente, red interna, puerto 80, RISKHUB_ENV=production)
- [x] deploy.sh para actualizaciones desde GitHub

## Pendiente

### Proximas funcionalidades
- [ ] i18n backend (cola larga de mensajes de routers/servicios a patron X-Lang/get_lang/t(); frontend ya migrado a t() con es/en)
- [x] Validacion end-to-end de los flujos IA contra la API real (2026-07-19): los 6 flujos verificados en produccion (91.99.83.202) contra la API real de Claude — analisis de activo (65 amenazas -> riesgos con motor residual determinista), evidencia con Vision (lectura de certificado ISO en PNG, quality E4), cuestionario TPRM (evaluacion estructurada completa), import de plan director (texto -> programas/iniciativas con codigos de control validados), borrador de plan de tratamiento y borrador de iniciativa. Metodo: org de prueba aislada, ejercitar cada servicio, verificar salida, borrar todo (cero residuo). Hay credito Anthropic suficiente. Los tests siguen cubriendo lo determinista con `structured_message` mockeado.
- [ ] Pruebas end-to-end manuales de las vistas nuevas con usuario real
- [ ] Backlog del modulo Plan Director/Tratamiento: priorizado en `RISKHUB_TREATMENT_MODULE_SPEC.md` (seccion "Backlog de mejoras") — no construir hasta validar con uso real

Deploy: prod (91.99.83.202) el 2026-08-05 — Fases 3 y 4 del rework del BCP.
Fase 4 (ingesta reconstruye jerarquia): el motor de ingesta ya no vuelca procesos
planos. `business_process` gana `business_unit` y `parent_process_id` (referencia
a otro proceso del lote por nombre); `bcp_dependency` gana `depends_on_process_id`
(dependencia proceso->proceso). El materializador ordena topologicamente las
entidades autorreferenciadas (`_sort_self_referential`), asi un subproceso listado
antes que su padre encuentra al padre igual; con proteccion de ciclos. La pasada 2
de comprension guia al modelo para deducir unidad de negocio, macro-proceso ->
proceso -> actividad y dependencias proceso->proceso (EXTRACTION_PROMPT_VERSION 5,
invalida la cache de extracciones previas). Tests test_ingest_hierarchy.py.
Fase 3 (dossier): `bcp_hierarchy_service.build_process_dossier` +
`GET /api/bcp/processes/{id}/dossier` reune RTO efectivo vs declarado, avisos de
coherencia, jerarquia (padre/subprocesos navegables), dependencias por categoria,
procesos que dependen de este, escenarios, estrategias, planes y pruebas. En el
Mapa de continuidad los nombres de proceso abren su ficha. Tests
test_bcp_process_dossier.py. Deploy previo 2026-08-03 — Fase 2 del rework del BCP: grafo de
dependencias proceso->proceso. `bcp_hierarchy_service.build_impact_analysis` +
`GET /api/bcp/impact-analysis`: propagacion de impacto transitiva (si cae X,
afecta a N procesos), orden de recuperacion (Kahn), camino critico por RTO (DP
sobre el topologico) y deteccion de ciclos. Panel "Analisis de impacto" en el
tile de dependencias (hubs expandibles, camino critico, ciclos). Tests
test_bcp_impact_analysis.py. Pendiente: Fase 3 (panel unico por proceso) y Fase
4 (ingesta reconstruye jerarquia). Deploy previo 2026-08-02 — Fase 1 del rework del BCP
(jerarquia real + precision, pedido por el usuario que no veia la jerarquia de
procesos/dependencias). BusinessProcess gana `parent_process_id` (macro-proceso
-> proceso -> actividad) y `business_unit`; `location_id` ya se asigna al
crear/editar (faltaba en el schema). Nuevo `bcp_hierarchy_service` +
`GET /api/bcp/continuity-map`: arbol Sede(anidada) -> Unidad -> Proceso ->
Subproceso -> Dependencias, con RTO EFECTIVO propagado (un proceso no se
recupera antes que su dependencia critica mas lenta) y hallazgos de coherencia
(RTO>MTPD, subproceso mas exigente que el padre, dependencia critica mas lenta
que el proceso, critico sin estrategia/plan/prueba, sin sede) + procedencia por
nodo. Nuevo tile "Mapa de continuidad" en el hub BCP; formulario de proceso con
sede/unidad/proceso-padre. Guarda anti-ciclo. Tests test_bcp_continuity_map.py.
Pendiente de este rework: Fase 2 (grafo de dependencias con propagacion) y
Fase 3 (panel unico por proceso). Deploy previo 2026-07-28 — revision UX GLOBAL de la pagina de
ingesta: orden accion-primero (conflictos -> datos por revisar -> huecos ->
"Que encontro" plegado por defecto como referencia -> avisos); stats de
conflictos/dudas clicables que saltan a su seccion; conflictos lado a lado en
rejilla con ambos documentos y su punto exacto, mas acciones en bloque
("preferir documento X" donde difiera, "aceptar todas las automaticas");
"Datos por revisar" con aceptacion en bloque (visibles / alta confianza /
todos los de una entidad). Todo en local sin re-fetch (conserva scroll y
colapsos). Deploy previo ccc0264 — el conflicto de
la ingesta cita AMBOS documentos y su punto exacto: el materializador guarda
procedencia por campo (documento + origen) segun escribe, asi que el valor "ya
cargado" (que lo puso otro documento del mismo pack) se muestra con su
documento real; si venia de una importacion anterior, se etiqueta "valor que
ya estaba" en vez de fingir un documento. Deploy previo 1ecb721 — arreglo de
UX de la vista de revision de la ingesta: aceptar/deshacer/rehacer/editar/
resolver conflicto actualizan en local y re-renderizan preservando el scroll
(se acabo el salto arriba y la perdida de colapsos); las secciones grandes (Que
encontro, Datos dudosos, conflictos) son colapsables como un todo con estado
persistente + barra sticky para saltar entre ellas y colapsar/expandir todo.
Deploy previo d5d70f2 (fix de `organizations.py`: borrado permanente por
introspeccion real del esquema via `Base.metadata` con SAVEPOINT por tabla,
fin del `FOREIGN KEY constraint failed`). Antes, ca15b1a habia traido el
refinamiento completo de la ingesta BCP (cache SHA-256, deshacer/rehacer,
documentacion dinamica, consolidacion ISO 22317, arbol de dependencias, export
a Word, BIA por proceso dirigido por el metodo del cliente, PPTX con tablas,
pasada 2 en paralelo). Health check OK, backup pre-deploy verificado; rollback:
`bash scripts/rollback.sh riskhub:20260728_141901`.
**Pendiente**: validacion end-to-end contra la API real con el pack de OFA en
una org de prueba aislada (credito de API ya recargado). **Recordatorio para
quien deployee**: actualizar esta nota en el mismo commit del deploy, no
despues — asi no se repite el desfase de esta vez.

## Convenciones

- **Naming**: ingles para identificadores, terminos ISO 27005 en ingles.
- **UI**: textos en castellano (es-ES).
- **Python**: PEP 8. Funciones cortas.
- **JS**: vanilla JS moderno, sin build step.
- **Sin emojis** en codigo fuente.
- **Comentarios**: castellano para logica ISO; ingles para tecnicismos.
- **Seguridad**: revisar OWASP antes de añadir funcionalidad que maneje datos del usuario.
- **Vistas nuevas**: siempre actualizar `app/static/js/views/guide.js` con documentacion de la nueva seccion.

## Estructura

```
riskhub/
├── Dockerfile
├── docker-compose.yml
├── deploy.sh
├── .env.example
├── requirements.txt
└── app/
    ├── main.py              # Entrypoint + middleware de seguridad
    ├── config.py
    ├── database.py
    ├── models.py
    ├── schemas.py
    ├── security.py          # JWT + bcrypt + require_role
    ├── seed.py
    ├── middleware/
    │   └── security_headers.py   # X-Content-Type-Options, CSP, etc.
    ├── routers/             # Todos los endpoints REST
    ├── services/
    │   ├── risk_engine.py
    │   ├── audit_service.py
    │   ├── rate_limiter.py         # Brute-force protection en login
    │   ├── rag_service.py
    │   ├── document_service.py
    │   ├── iso_clause_extractor.py # Extraccion clausulas ISO 27001/27002 con Claude
    │   ├── webhook_service.py      # Envio de webhooks salientes con HMAC-SHA256
    │   ├── context_builder.py
    │   └── anonymizer.py
    ├── data/                # JSON catalogos ISO 27005 / ISO 27002
    └── static/
        ├── login.html
        ├── index.html
        ├── css/app.css
        ├── img/logo.svg
        └── js/              # api.js, auth.js, ui.js, app.js, views/
```

## Como continuar

1. Lee este archivo.
2. Verifica localmente: `uvicorn app.main:app --reload --port 8000`
3. Para deploy: `git push origin main` y luego `bash /opt/riskhub/deploy.sh` en el servidor.
