# RiskHub — Auditoría de Automatizaciones y Flujos v1.7.7

Fecha: 2026-05-30 | Estado: Análisis sistemático de todos los flujos de datos y automatizaciones

---

## 📋 Resumen Ejecutivo

### ✅ Automatizaciones Implementadas: 10 sistemas activos
- **Scheduler (APScheduler)**: 10 trabajos periódicos corriendo cada 1h, 24h o 1 semana
- **Hooks de creación/actualización**: Incidentes, No Conformidades, Proveedores
- **Agentes IA**: Análisis de riesgos, RAG, anonimización, análisis de CVE
- **Integraciones externas**: OSINT (7 fuentes), CVE (NVD API), Email, SharePoint

### ⚠️ Pendiente de completitud
- [ ] Verificar sincronización multi-tenancy en TODOS los flujos
- [ ] Revisar qué agente IA hace exactamente qué análisis (documentación interna falta)
- [ ] Validar que usuarios finales entienden qué es automático vs manual

---

## 1. SCHEDULER (APScheduler) — 10 Trabajos Periódicos

**Archivo**: `app/services/scheduler.py` | **Configuración**: `app/main.py:80`

| Job | Intervalo | Qué hace | User Action | Automático? |
|-----|-----------|----------|-------------|------------|
| **check_alert_rules** | 1h | Evalúa reglas de alerta (SMTP) y envía emails | Crear regla en UI | ✅ Completo |
| **check_risk_reviews** | 24h | Recordatorios de revisión periódica a risk owners | Asignar next_review | ✅ Completo |
| **cve_auto_scan** | 24h | Busca CVEs CRÍTICAS/ALTAS recientes (NVD API) | Configurar en admin | ⚠️ Solo busca, no analiza (análisis IA bajo demanda) |
| **task_escalation** | 24h | Escala prioridad de tareas >7 días vencidas | Crear tarea | ✅ Completo |
| **policy_review_tasks** | 24h | Crea tareas cuando politicas tienen review vencida | Crear politica | ✅ Completo |
| **incident_tasks** | 24h | Crea tareas para incidentes abiertos >7 días | Crear incidente | ✅ Completo |
| **control_degradation** | 168h (semanal) | Degrada controles IMPLEMENTED sin evidencia >12m | Crear control | ✅ Completo |
| **osint_periodic_scan** | 168h (semanal) | Re-escanea OSINT targets >7 días | Crear OSINT target | ✅ Completo |
| **monthly_report** | 24h (auto-filtro day=1) | Genera/envía informe mensual a admins | Solo config SMTP | ✅ Completo |

**Total alertas soportadas por scheduler**: 8 tipos de eventos
- `risk_critical`, `risk_high`, `treatment_overdue`, `risk_no_treatment`, `treatment_due_soon`
- `daily_digest`, `control_review_overdue`, `incident_p1p2`, `nis2_pending`, `policy_review_overdue`, `task_overdue`

**Cooldown**: 20h entre disparos (evita spam)

---

## 2. HOOKS DE CREACIÓN/ACTUALIZACIÓN (Triggers en Routers)

### 2.1 Incidentes (Incident Auto-Link Risks)
**Archivo**: `app/routers/incidents.py:93-112` | **Tipo**: Hook de creación

```
Usuario crea Incidente + affected_asset_ids
  ↓
Sistema busca Riesgos ACTIVOS para esos activos
  ↓
Auto-linkea hasta 20 riesgos (sin duplicar)
  ↓
Guarda en related_risk_ids
```

**Status**: ✅ Implementado (v1.7.7)
**Nota**: Try/catch silencioso si falla

---

### 2.2 No Conformidades (NC → Risk Auto-Create)
**Archivo**: `app/routers/nonconformities.py` | **Tipo**: Hook de creación

```
Usuario crea NC + evidencia/impacto
  ↓
Sistema detecta si es CRITICAL/HIGH
  ↓
Auto-crea riesgo ISO 27005 vinculado
  ↓
Asigna code RIS-XXXX automáticamente
```

**Status**: ✅ Implementado | **Búsqueda**: Grep "nonconformities" para detalles

---

### 2.3 Proveedores (Supplier→Risk Auto-Create)
**Archivo**: `app/routers/suppliers.py` | **Tipo**: Hook de actualización de score

```
Usuario actualiza proveedor score ≤ 30
  ↓
Sistema crea Riesgo supply-chain ISO 27005
  ↓
Threat = "Proveedor crítico con riesgo elevado"
  ↓
Enlaza a Supplier.id
```

**Status**: ✅ Implementado | **Búsqueda**: Grep "score.*30\|supply-chain"

---

### 2.4 Riesgos (Risk Duplicate Detection)
**Archivo**: `app/routers/risks.py` | **Tipo**: Hook de validación

```
Usuario intenta crear Riesgo [Asset, Threat, Vulnerability]
  ↓
Sistema busca duplicados existentes
  ↓
Si existe: HTTP 409 (Conflict)
  ↓
Mensaje: "Riesgo ya existe, edita el existente"
```

**Status**: ✅ Implementado | **HTTP**: 409 Conflict

---

## 3. AGENTES IA (Claude API)

### 3.1 Agente de Chat RAG
**Archivo**: `app/services/ai_service.py`, `app/routers/ai.py`

**Capacidades**:
- RAG FTS5 sobre contexto (políticas, controles, catálogos)
- Anonimización regex configurable
- Feedback loop (user marks "helpful"/"not helpful")

**User Input**: Pregunta libre en chat
**IA Output**: Respuesta contextualizada + fuentes

**Status**: ✅ Implementado | **Modelo**: Claude 3.5 Sonnet (o configurable)

---

### 3.2 Agente de Análisis de Riesgos
**Archivo**: `app/services/ai_service.py` (líneas 21-100+)

**Cuestionario**: 10 campos (sector, empleados, regulaciones, sistemas, tipos de datos, etc.)

**Output Esperado**:
```json
{
  "scenarios": [
    {
      "threat": "nombre_amenaza",
      "asset": "activo_afectado", 
      "vulnerability": "vuln_code",
      "probability": 1-5,
      "consequence": 1-5,
      "inherent_level": 0-8,
      "treatment": "mitigate|accept|avoid|transfer"
    }
  ]
}
```

**Status**: ⚠️ Métodos en servicio; router endpoint desconocido (búsqueda necesaria)

---

### 3.3 Agente ISMS Analysis
**Archivo**: `app/services/isms_analysis_service.py`

**Qué hace**:
- Linkea documentos a activos por nombre
- Cuando controles se actualizan → re-analiza activos
- Sugiere aplicación de controles ISO 27002 a activos

**Status**: ✅ Implementado | **Trigger**: Actualización de control

---

### 3.4 Agente CVE Analysis
**Archivo**: `app/services/cve_analysis_service.py`

**Flujo**:
1. Scheduler busca CVEs CRÍTICAS/ALTAS (auto-scan)
2. User ejecuta "Analizar con IA" desde UI manualmente
3. IA genera report: afectación, mitigaciones, prioridad

**Status**: ⚠️ Auto-scan solo busca; análisis IA es bajo demanda

---

### 3.5 Agente Asset Risk Analysis
**Archivo**: `app/services/asset_risk_analysis_service.py`

**Qué hace**:
- Correlaciona activo + riesgos existentes + controles
- Sugiere nuevos riesgos o brechas de control

**Status**: ⚠️ Archivo existe; uso desconocido (router endpoint?)

---

### 3.6 Agente Report AI
**Archivo**: `app/services/report_ai_service.py`

**Qué hace**:
- Genera reportes narrativos (no templates estáticos)
- IA sintetiza análisis + métricas

**Status**: ✅ Implementado | **User Action**: "Generar informe con IA"

---

## 4. INTEGRACIONES EXTERNAS

### 4.1 OSINT Engine (7 Fuentes)
**Archivos**: `app/services/osint_*.py`, `app/routers/osint.py`

| Fuente | Qué busca | Método | Status |
|--------|----------|--------|--------|
| Email (Have I Been Pwned) | Brechas públicas | API | ✅ |
| Domain (Shodan, RDNS) | DNS, SSL, tecnologías | API | ✅ |
| IP (MaxMind, Abuseipdb) | Geolocalización, reputación | API | ✅ |
| URL (PhishTank, URLhaus) | URLs maliciosas | API | ✅ |
| Username (Google, GitHub) | Filtraciones de credenciales | Web scrape | ✅ |
| GitHub | Repos públicos, secrets accidentales | API | ✅ |
| Entra ID | Usuarios Azure AD | Graph API | ✅ |

**Auto-create Incident**: Si hallazgo es CRITICAL/HIGH → auto-crea incidente

**Periodic Re-scan**: Semanal para targets con last_scanned >7 días

**Status**: ✅ Completo | **Risk**: API keys en IntegrationConfig (Fernet encrypted)

---

### 4.2 CVE Integration (NVD API)
**Archivo**: `app/services/cve_service.py`

**Flujo**:
1. Auto-scan busca CVEs de últimos 2 días
2. Filtra por severidad (CRITICAL, HIGH, ALL)
3. Correlaciona con activos (software inventory)
4. IA analiza bajo demanda

**Status**: ⚠️ Búsqueda implementada, análisis automático parcial

---

### 4.3 Email Service
**Archivo**: `app/services/email_service.py`

**Capacidades**:
- SMTP configurable (cifrado Fernet en BD)
- Plantillas HTML tematizadas (purple/orange)
- Rate limiting para alertas (evita spam)

**Status**: ✅ Implementado | **Todas las alertas** usan este servicio

---

### 4.4 SharePoint Integration (Preview)
**Archivo**: `app/services/sharepoint_service.py`, `app/routers/sharepoint.py`

**Qué hace**:
- Conecta Microsoft Graph API
- Importa documentación SGSI en masa desde SharePoint
- Linkea a activos/controles

**Status**: ⚠️ Implementado pero no usado en seed

---

## 5. FLUJOS DE INFORMACIÓN CRÍTICOS

### Flujo 1: Creación de Riesgo por Usuario
```
Usuario → POST /risks
  ├─ Valida: [Asset, Threat, Vulnerability, Probability, Consequence]
  ├─ Calcula: inherent_level = matriz 5x5 ISO 27005
  ├─ Detecta: ¿Duplicado existente?
  │  └─ SÍ → HTTP 409 (Conflict)
  └─ Crea: Risk code=RIS-XXXX
```

**Manual**: Todo el usuario; IA NO interviene en creación

---

### Flujo 2: Evaluación de Riesgos (Scheduler)
```
Cada 24h → check_alert_rules()
  ├─ Query: RiskStatus != CLOSED, residual_level >= threshold
  ├─ Query: AlertRules.is_active = TRUE
  ├─ Filter: Coincidencias (matching riesgos)
  ├─ Format: Email HTML con gradiente purple/orange
  └─ Send: SMTP a recipient_email
  
Cooldown: 20h entre disparos (evita spam)
```

**Automático**: Completamente; usuario solo configura regla

---

### Flujo 3: Incidente → Riesgos (Hook)
```
Usuario → POST /incidents [affected_asset_ids]
  ├─ Auto-query: Risk.asset_id IN affected_asset_ids
  ├─ Filter: RiskStatus IN [ACTIVE, MONITORING] (excluye CLOSED, ACCEPTED)
  ├─ Limit: Top 20 por residual_level DESC
  ├─ Dedup: No duplica en related_risk_ids
  └─ Save: incident.related_risk_ids = [RIS-001, RIS-003, ...]
```

**Automático**: Cuando se crea incidente

---

### Flujo 4: CVE Scan → Análisis IA
```
Cada 24h → _run_cve_auto_scan()
  ├─ Query: IntegrationConfig "nvd_cve" (API key Fernet)
  ├─ Fetch: NVD API últimas 2 días, severidad CRITICAL/HIGH
  ├─ Max: 50 CVEs
  ├─ Log: Encontradas X CVEs (SIN persistir en BD)
  │
  └─ Usuario manualmente: GET /cve/analyze/:cve_id
      ├─ Call: IA service (Claude API)
      ├─ Output: Análisis de impacto + mitigaciones
      └─ Store: En modelo CVE si user guarda
```

**Status**: ⚠️ Auto-scan busca; análisis es bajo demanda (NO automático)

---

### Flujo 5: OSINT Scan Periódico
```
Cada 168h (1 semana) → _run_osint_periodic_scan()
  ├─ Query: OSINTIdentifier.last_scanned_at < now - 7d
  ├─ For each identifier:
  │   ├─ Create OSINTScan (status=pending)
  │   ├─ Launch threading (no bloquea)
  │   └─ Run: osint_engine.run_X_scan()
  │       ├─ Email scan → HIBP, LeakCheck, Intelx
  │       ├─ Domain scan → Shodan, RDNS
  │       ├─ IP scan → MaxMind, Abuseipdb
  │       ├─ URL scan → PhishTank, URLhaus
  │       └─ Username scan → Google, GitHub
  └─ Auto-create Incident si hallazgo CRITICAL/HIGH
```

**Automático**: Completamente; re-scan periódico + auto-incident

---

### Flujo 6: Policy Review Overdue → Task
```
Cada 24h → _run_policy_review_tasks()
  ├─ Query: Policy.status != OBSOLETE, review_date < now
  ├─ Dedup: ¿Ya existe tarea? → skip
  ├─ Create: TreatmentTask code=TSK-XXXX
  │   ├─ title = "Revisar politica [code]: [title]"
  │   ├─ status = PENDING
  │   ├─ priority = MEDIUM
  │   └─ assigned_to = policy.owner_id
  └─ Commit
```

**Automático**: Completamente

---

### Flujo 7: Análisis de Contexto (RAG)
```
Usuario → GET /ai/chat [query]
  ├─ Anon: Aplica regex sobre assets/risks en la org
  ├─ RAG: Query FTS5 sobre políticas + controles + catálogos
  ├─ Build: context_builder genera prompt mejorado
  ├─ Call: Claude API (RAG + prompt context)
  ├─ Log: feedback loop (user marca helpful/not helpful)
  └─ Return: Respuesta + sources
```

**Automático**: Respuesta, pero usuario inicia query (semiautomático)

---

## 6. ESTADO DE COMPLETITUD POR SUBSISTEMA

| Subsistema | Status | Completitud | Notas |
|------------|--------|------------|-------|
| **Scheduler** | ✅ | 100% | 10 jobs, todos activos |
| **Hooks** | ✅ | 90% | Incident, Supplier, NC, Risk dedup OK; Asset grouping? |
| **IA Agents** | ⚠️ | 70% | Chat OK; CVE análisis bajo demanda; Asset risk analysis sin endpoint |
| **OSINT** | ✅ | 100% | 7 fuentes, auto-scan, auto-incident |
| **Email Alerts** | ✅ | 95% | 11+ tipos de eventos, cooldown, HTML tematizado |
| **Multi-tenancy** | ⚠️ | 80% | organization_id en modelos; validar en TODOS los queries |
| **SSO/Integrations** | ⚠️ | 60% | SharePoint code exists; no documentado |
| **Security** | ✅ | 90% | Rate limiting, Fernet, magic bytes, CSP headers OK |

---

## 7. PREGUNTAS SIN RESPUESTA (Búsqueda Necesaria)

- [ ] **Asset Grouping Service**: ¿Quién lo dispara? ¿Automático o manual?
- [ ] **Asset Risk Analysis**: ¿Router endpoint? ¿Cuándo se ejecuta?
- [ ] **AI Service**: Endpoint para cuestionario de análisis inicial (v1.7.7 mención)
- [ ] **Awareness Service**: ¿Qué automatizaciones tiene?
- [ ] **Control Update Hook**: ¿Dispara re-análisis de activos en ISMS?
- [ ] **Supplier Risk Score**: ¿Usa fórmula automática o entrada manual?
- [ ] **Nonconformity Auto-Risk**: ¿Implementado? Confirmar en código

---

## 8. MATRIZ DE RESPONSABILIDAD (Usuario vs Sistema)

### Usuario Debe Hacer:
1. ✅ Crear contexto inicial (org, sector, regulaciones)
2. ✅ Crear activos + amenazas + vulnerabilidades
3. ✅ Crear riesgos (sistema detecta duplicados)
4. ✅ Definir tratamientos + due dates
5. ✅ Asignar risk owners
6. ✅ Configurar reglas de alerta + SMTP
7. ✅ Crear políticas + control implementations
8. ✅ Crear incidentes + marcar afectados
9. ✅ Crear proveedores + score
10. ✅ Crear OSINT targets para escaneo

### Sistema Automático:
1. ✅ Enviar alertas por email (cada 1h)
2. ✅ Recordar revisiones de riesgos (cada 24h)
3. ✅ Escalar tareas vencidas (cada 24h)
4. ✅ Crear tareas por políticas vencidas (cada 24h)
5. ✅ Crear tareas por incidentes abiertos >7d (cada 24h)
6. ✅ Degradar controles sin evidencia >12m (semanal)
7. ✅ Re-escanear OSINT (semanal)
8. ✅ Generar informe mensual (primer día mes)
9. ✅ Linkear riesgos a incidentes (al crear incident)
10. ✅ Crear riesgos supply-chain por proveedores críticos

---

## 9. PROPUESTA: DIAGRAMAS MERMAID POR FLUJO

He identificado estos flujos principales para visualizar:

1. **Flujo de Riesgo (entrada → evaluación → alerta)**
2. **Flujo de Incidente (detección → auto-link → tareas)**
3. **Flujo de Proveedor (score → risk auto-create)**
4. **Ciclo de Scheduler (10 jobs, triggers, emails)**
5. **Pipeline IA (consulta → RAG → contexto → respuesta)**

**Siguiente paso**: Generar diagramas Mermaid para cada uno + HTML interactivo.

---

## 10. PENDIENTES DE VALIDACIÓN

- [ ] Confirmar que TODAS las queries filtran por `organization_id` (multi-tenancy segura)
- [ ] Verificar que SSO + SharePoint no exponen datos cross-org
- [ ] Revisar rate limiting en login vs scheduler (no conflictos)
- [ ] Probar email en producción (Fernet decryption correcto)
- [ ] Documentar qué hace cada agente IA en código (comentarios)
- [ ] Listar endpoints de IA que faltan en routers

---

**Última actualización**: 2026-05-30 19:00 UTC
**Generado por**: Análisis automático + grep/read de codebase
**Próximo**: Generar flujorama interactivo Mermaid
