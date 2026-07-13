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
- [x] TPRM (Sprints 4/5/7): `VendorRiskAssessment` + `routers/vendor_assessments.py` + `services/vendor_assessment_service.py` (evaluacion consolidada, score por dominio, `:approve`, `:push-to-risk-register` a ISO 27005); `services/tprm_ai_service.py` + `POST /api/supplier-questionnaires/{id}/ai-review` (evaluacion IA con guardrails, auto-trigger en submit, resultado en `SupplierQuestionnaire.ai_review`); `VendorIssue` + `routers/vendor_issues.py` (hallazgos con SLA por severidad y vencimiento automatico). Vistas `vendor-assessments.js` y `vendor-issues.js` en el hub de Proveedores. Tests en `tests/test_tprm_*.py`. Pendiente: editor de plantillas, portal con evidencias, conectores de monitorizacion, reporting.
- [x] Regwatch (Vigilancia Normativa Automatica — Sprint 6 completo): modelos `NormativeSource`/`NormativeChangeEvent`/`ChangePack`/`TenantRegwatchSettings`/`TenantChangeInboxItem`; `services/regwatch_sources.py`; `services/regwatch_connectors.py` (11 conectores HTTP reales — EUR-Lex SPARQL, BOE RSS, ENISA RSS, AEPD/EDPB RSS, NIST JSON/RSS, EBA RSS, ISO status, AICPA, PCI, CSA, CIS — todos con degradacion graceful); `services/regwatch_service.py` (toggle, inbox, historial, sweep, pipeline IA Claude Haiku con auto-publicacion); `services/regwatch_propagation.py` (propagacion cross-plataforma: catalog update, flag `ControlImplementation` SoA, `Policy`→status review, `BCPPlan`→under_review, `SupplierQuestionnaire`, `ComplianceFrameworkStatus`, crea `TreatmentTask` en riesgos afectados); `routers/regwatch.py` (20 rutas tenant + admin). Vista `regwatch.js` (wizard con badges de impacto + resumen de propagacion). Columnas v4.0.0: `deprecated_at` en `controls`; `regwatch_review_at`/`regwatch_pack_id` en `control_implementations`, `policies`, `bcp_plans`, `supplier_questionnaires`, `compliance_framework_status`. Pendiente: digest email, versionado compliance_control, migracion plantillas clonadas.
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
  - Backups: `services/backup_service.py` (API de backup de sqlite3 + gzip, nocturno 2:30 UTC, retencion 14d, `RISKHUB_BACKUP_DIR`/`RISKHUB_BACKUP_RETENTION_DAYS`); endpoints `/api/admin/backups` (listar/lanzar/descargar, superadmin); runbook `docs/BACKUP_RESTORE_RUNBOOK.md`. Migracion PostgreSQL: solo diseno en `docs/POSTGRES_MIGRATION_PLAN.md` (FTS5->tsvector, INSERT OR IGNORE, PRAGMA, strftime; rollout 5 fases).
  - CI: `.github/workflows/ci.yml` (pytest + ruff + docker build en push/PR a main).
  - Vista Operaciones (`ops.js`, pestana en Configuracion): consumo IA, cola de jobs, errores capturados y backups.
- [x] Economia del analisis IA (2026-07-13, commits 0258ee0..61592e0): grupos validados cubren a sus miembros (skipped, 0 tokens); tier Haiku en el masivo con Opus para criticos (CIA>=4) e individual; dieta de salida (3-5 escenarios sobre apetito); Message Batches API de Anthropic (50%) para >=25 activos con cancelacion cooperativa; estimador previo `GET /api/assets/analysis-cost-estimate` + confirmacion con coste en la UI; modo maxima calidad por org (`AiConfig.force_deep_analysis`, checkbox en IA->Configuracion). Medido en prod: ~$0.007/activo con Haiku (28x menos que Opus individual). `ruff.toml` con reglas de correccion activas (cazaron 5 bugs latentes: incidents UnboundLocalError, scheduler timedelta/Organization, ai.py logging, claves duplicadas RAG); CI en verde.
- [x] Refacturacion IA superadmin (2026-07-13): columna `ai_call_logs.key_source` ('vendor' = key global de plataforma refacturable | 'org' = key propia del tenant; se registra en `claude_client._log_usage` comparando con `settings.anthropic_api_key`); `GET /api/ai/usage/global` (superadmin: consumo/coste por org del mes con split refacturable, fila Plataforma para org NULL — regwatch —, `?org_id=` detalle por call_type, `?month=YYYY-MM`); panel "Costes IA por organizacion" en ops.js con selector de mes y detalle expandible. El gap detallado usa `structured_message` troceado (12 controles/chunk, fin de los 500 por JSON truncado). Tests en `tests/test_ai_usage_global.py`.

### Frontend

- [x] SPA hash-based (`app/static/`)
- [x] Vistas: dashboard, heatmap, assets, threats, vulnerabilities, risks, controls, reports, context, users, suppliers, incidents, nonconformities, tasks, policies, audits, gdpr, compliance, alerts, integrations, audit, ai-chat, ai-documents, onboarding, guide, organizations
- [x] Vistas nuevas: evidence, webhooks, external-findings, predictive, ccm, itsm-config, trust-portal, magerit, executive, architecture-review, cve, osint, feature-flags, ops (operaciones: consumo IA, jobs, errores, backups)
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
- [ ] Deploy a produccion del ciclo v6 + SaaS (git push + deploy.sh — decision del usuario; el arranque hara el recalculo one-shot de residuales v2)
- [ ] Validacion end-to-end de los flujos IA contra la API real (analisis de activo, evidencia con Vision, cuestionario TPRM con evidencia) — los tests cubren lo determinista
- [ ] Pruebas end-to-end manuales de las vistas nuevas con usuario real

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
