# Changelog — Modulo TPRM (Third-Party Risk Management)

Registro de cambios del modulo TPRM de RiskHub. Sigue la spec
`RISKHUB_TPRM_MODULE_SPEC.md`, adaptada a los patrones consolidados del repo
(SQLite + `_migrate_columns`, JS vanilla, hubs con pestanas) segun §0 de la spec
("prevalece el patron existente").

## [v3.7.0] — Sprints 4-5-7 (Assessments, IA, Issues) + Tests — 2026-06-13

### Anadido
- **Evaluacion consolidada de proveedor** (Sprint 4): modelo `VendorRiskAssessment`,
  `routers/vendor_assessments.py` (`/api/vendor-assessments`) y
  `services/vendor_assessment_service.py`. Agrega inherent risk + cuestionarios
  enviados (media de scores) + score por dominio; calcula residual; `:approve`;
  `:push-to-risk-register` crea una entrada ISO 27005 en el Risk Register central
  (reutiliza el patron de `_auto_create_supplier_risk`) y guarda `linked_risk_id`.
  Vista `vendor-assessments.js` (pestana Evaluaciones).
- **Pipeline de evaluacion IA** (Sprint 5): `services/tprm_ai_service.py` evalua un
  cuestionario respondido con Claude y devuelve salida estructurada (ai_score,
  confidence, control_coverage, evidence_consistency, red_flags, follow_up,
  rationale). Guardrails: confidence < 0.6 fuerza revision manual; nunca inventa
  evidencia; nunca lanza excepciones (devuelve error dict). Endpoint
  `POST /api/supplier-questionnaires/{id}/ai-review` + auto-trigger best-effort en
  background al hacer submit el proveedor. Resultado guardado en
  `SupplierQuestionnaire.ai_review`/`ai_reviewed_at`; visible en la UI de
  cuestionarios.
- **Hallazgos / issues** (Sprint 7 parcial): modelo `VendorIssue` con SLA por
  severidad (critico 7d, alto 30d, medio 90d, bajo 180d), estados completos y
  marcado automatico de vencidos; `routers/vendor_issues.py`
  (`/api/vendor-issues` + `stats/summary`). Vista `vendor-issues.js` (pestana
  Hallazgos).
- **Tests** (§14): `tests/test_tprm_scoring.py` (~40), `tests/test_tprm_templates.py`
  (~30) y `tests/test_tprm_api.py` (~31) cubriendo el motor de scoring, las
  plantillas y los endpoints TPRM.

### Pendiente
- Editor visual de plantillas y versionado; portal externo con subida de
  evidencias + AV scan; conectores de monitorizacion continua; reporting
  (PDF/DOCX/XLSX/PPTX); incidentes de terceros y offboarding completo.

## [v3.6.0] — Sprint 1 (Foundations) — 2026-06-13

Fundacion del modulo construida sobre el registro de proveedores existente
(`Supplier`) y el motor de cuestionarios (`SupplierQuestionnaire`). No se crea
un silo paralelo.

### Anadido
- **Modelo de datos TPRM**: ampliacion de `Supplier` con ciclo de vida
  (`relationship_status`), `tier`, `vendor_type`, atributos de inherent risk
  (`data_sensitivity`, `data_volume`, `system_access_type`,
  `business_criticality`, `geographic_risk`), scoring
  (`inherent_risk_score`, `control_effectiveness`, `residual_risk_score`),
  flags regulatorios (`is_data_processor`, `processes_personal_data`,
  `cross_border_transfers`, `is_nis2`, `is_dora`, `is_ens`), firmographics
  (`country_code`, `website`, `tax_id`, `annual_spend`) y nth-party
  (`parent_supplier_id`, `nth_party_depth`). Enums `SupplierTier` y
  `SupplierRelationship`. Migraciones en `_migrate_columns()` (seed.py).
- **Motor de scoring** (`services/tprm_scoring_service.py`): inherent risk
  ponderado (§4.2), tiering por umbrales (§4.3), residual = inherent x
  (1 - control_effectiveness/100) (§5.2), mapeo a 5 niveles (§5.1) y scoring
  de cuestionarios contra plantillas con pesos y reglas (§4.7.1).
- **Biblioteca de plantillas del sistema** (`services/tprm_templates.py`):
  7 plantillas clonables con pesos, reglas de scoring y mapeo a controles —
  LITE, ISO 27001 completo, GDPR encargado, NIS2, DORA ICT, declaracion IA
  (ISO 42001) y offboarding.
- **API** (`routers/tprm.py`, prefijo `/api/tprm`): dashboard summary, heatmap,
  portfolio por tier; recompute inherent risk por proveedor y de todo el
  portfolio; biblioteca de plantillas.
- **Integracion de cuestionarios**: `supplier_questionnaires` acepta
  `template_code` para usar plantillas del sistema; scoring ponderado en el
  submit; recalculo automatico del residual risk del proveedor. El portal
  publico sanitiza las preguntas (no expone reglas de scoring ni mapeo a
  controles internos).
- **Frontend**: nueva vista `ViewTprm` (dashboard con KPIs, distribucion por
  tier, riesgo residual, heatmap SVG inherent vs residual y top 10), pestana
  "TPRM Dashboard" en el hub de Proveedores, perfil de riesgo inherente y
  columnas tier/inherent/residual + boton Recalcular en la tabla de
  proveedores, selector de plantilla en el formulario de cuestionario.
  Seccion de ayuda en la guia.

### Pendiente (siguientes sprints de la spec)
- Sprint 2-3: editor visual de plantillas, versionado, portal externo con
  evidencias (subida + AV scan) y mensajeria bidireccional.
- Sprint 4: assessment consolidado + push al Risk Register ISO 27005.
- Sprint 5: pipeline de evaluacion por IA (Claude) con guardrails y deteccion
  de inconsistencias.
- Sprint 6: conectores de monitorizacion continua (BitSight, SecurityScorecard,
  UpGuard, crt.sh, HIBP).
- Sprint 7-8: issues/remediacion, incidentes de terceros, offboarding,
  reporting (PDF/DOCX/XLSX/PPTX), regulator pack.
- Tests pytest del motor de scoring y de los endpoints (§14).
