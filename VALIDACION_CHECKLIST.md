# RiskHub v1.7.7 — Checklist de Validación de Automatizaciones

**Fecha**: 2026-05-30 | **Objetivo**: Verificar que TODAS las automatizaciones funcionan correctamente

---

## 📋 Cómo Usar Este Checklist

1. **Ejecuta los tests en orden** (algunos dependen de otros)
2. **Marca ✅ cuando se complete cada paso**
3. **Si algo falla**: busca la sección "🔧 Troubleshooting"
4. **Documentación**: AUTOMATIONS_AUDIT.md + FLOWS_VISUALIZATION.html

---

## 1️⃣ SCHEDULER — Validar Que Los 10 Trabajos Se Ejecutan

### 1.1 Verificar que Scheduler está activo

```bash
# En producción, ver logs:
docker logs riskhub-app | grep "Scheduler iniciado"
```

**Expected Output:**
```
Scheduler iniciado — intervalo: 1h.
```

**Status**: [ ] ✅ OK | [ ] ❌ FALLA

**Troubleshooting**:
- Si no aparece: revisar `app/main.py` line 80 (`sched.start()`)
- Si falla: verificar APScheduler version en `requirements.txt`

---

### 1.2 Verificar Jobs Registrados

En la BD, durante runtime, ejecutar:

```python
from app.services import scheduler as sched

if sched._scheduler and sched._scheduler.running:
    jobs = sched._scheduler.get_jobs()
    for job in jobs:
        print(f"{job.id}: {job.name} → próximo disparo {job.next_run_time}")
```

**Expected Output:**
```
check_alert_rules: Evaluacion periodica de reglas de alerta → ...
check_risk_reviews: Recordatorios de revision periodica de riesgos → ...
cve_auto_scan: Escaneo automatico diario de CVEs → ...
task_escalation: Escalada automatica de prioridad de tareas vencidas → ...
policy_review_tasks: Creacion de tareas por politicas con revision vencida → ...
incident_tasks: Creacion de tareas para incidentes sin resolver >7 dias → ...
control_degradation: Degradacion de controles IMPLEMENTED sin evidencia → ...
osint_periodic_scan: Re-escaneo periodico de objetivos OSINT → ...
monthly_report: Informe mensual de seguridad por email → ...
```

**Status**: [ ] ✅ 10/10 Jobs activos | [ ] ⚠️ Algunos faltan | [ ] ❌ 0 Jobs

---

### 1.3 Validar Cada Job Individualmente

#### 1.3.1 **check_alert_rules** (cada 1h)

**Setup**:
1. Ir a UI → Alertas → Crear regla de alerta
2. Event type = `risk_critical`
3. Recipient = tu email
4. Threshold = 6

**Test**:
1. Crea un Riesgo con residual_level ≥ 6
2. Espera 1 hora O fuerza disparo manual:
   ```python
   from app.services.scheduler import _run_alert_rules
   _run_alert_rules()
   ```

**Expected**: Email recibido con alerta

**Status**: [ ] ✅ Email recibido | [ ] ⚠️ Retrasado | [ ] ❌ No recibido

**Si falla**:
- Verificar SMTP configurado: UI → Admin → Configuración Email
- Ver logs: `docker logs riskhub-app | grep "Evaluacion periodica"`
- Comprobar BD: `SELECT * FROM AlertRule WHERE is_active=1`

---

#### 1.3.2 **check_risk_reviews** (cada 24h)

**Setup**:
1. Crea un Riesgo
2. Asigna `next_review` = HOY + 1 día
3. Asigna `owner_id` = usuario con email

**Test**:
```python
from app.services.scheduler import _run_risk_reviews
_run_risk_reviews()
```

**Expected**: Email recordatorio enviado al owner

**Status**: [ ] ✅ OK | [ ] ❌ FALLA

---

#### 1.3.3 **cve_auto_scan** (cada 24h)

**Setup**:
1. Ir a UI → Admin → Integración NVD CVE
2. API Key = (obtener de https://nvd.nist.gov/developers)
3. Auto-scan enabled = TRUE
4. Severity = CRITICAL

**Test**:
```python
from app.services.scheduler import _run_cve_auto_scan
_run_cve_auto_scan()
```

**Expected**: Log muestra "CVE auto-scan: X CVEs encontradas"

**Status**: [ ] ✅ CVEs detectadas | [ ] ⚠️ Sin CVEs (esperado si es período tranquilo) | [ ] ❌ Error API

**Si falla**:
- Verificar API key válida
- Ver logs: `grep "CVE auto-scan" docker logs`
- Probar NVD API directamente (curl)

---

#### 1.3.4 **task_escalation** (cada 24h)

**Setup**:
1. Crea TreatmentTask con due_date = hace 8 días
2. priority = LOW
3. status = PENDING

**Test**:
```python
from app.services.scheduler import _run_task_escalation
_run_task_escalation()

# Verificar en BD:
SELECT * FROM TreatmentTask WHERE code = 'TSK-XXXX';
# priority debería estar escalada (MEDIUM o superior)
```

**Expected**: priority escalada de LOW → MEDIUM

**Status**: [ ] ✅ Escalada | [ ] ❌ Sin cambios

---

#### 1.3.5 **policy_review_tasks** (cada 24h)

**Setup**:
1. Crea una Policy
2. review_date = hace 1 día
3. status != OBSOLETE

**Test**:
```python
from app.services.scheduler import _run_policy_review_tasks
_run_policy_review_tasks()

# Verificar en BD:
SELECT * FROM TreatmentTask WHERE title LIKE '%Revisar politica%';
```

**Expected**: Nueva TreatmentTask creada con código TSK-XXXX

**Status**: [ ] ✅ Creada | [ ] ⚠️ Ya existe (dedup) | [ ] ❌ No creada

---

#### 1.3.6 **incident_tasks** (cada 24h)

**Setup**:
1. Crea Incident
2. status = OPEN
3. created_at = hace 8 días

**Test**:
```python
from app.services.scheduler import _run_incident_tasks
_run_incident_tasks()

# Verificar:
SELECT * FROM TreatmentTask WHERE title LIKE '%Resolver incidente%';
```

**Expected**: Nueva TreatmentTask creada

**Status**: [ ] ✅ Creada | [ ] ⚠️ Dedup | [ ] ❌ No creada

---

#### 1.3.7 **control_degradation** (cada 168h = 1 semana)

**Setup**:
1. Crea ControlImplementation
2. status = IMPLEMENTED
3. next_review = hace 12.5 meses

**Test**:
```python
from app.services.scheduler import _run_control_degradation
_run_control_degradation()

# Verificar:
SELECT status, maturity FROM ControlImplementation WHERE id = X;
# status debería ser PARTIAL
```

**Expected**: status IMPLEMENTED → PARTIAL, maturity--

**Status**: [ ] ✅ Degradado | [ ] ❌ Sin cambios

---

#### 1.3.8 **osint_periodic_scan** (cada 168h)

**Setup**:
1. Crea OSINTIdentifier (p.ej., email = `test@example.com`)
2. last_scanned_at = hace 8 días (o NULL)

**Test**:
```python
from app.services.scheduler import _run_osint_periodic_scan
_run_osint_periodic_scan()

# Espera 2-5 segundos (threading)
# Verificar:
SELECT * FROM OSINTScan WHERE target = 'test@example.com' AND status = 'pending';
```

**Expected**: OSINTScan creado con status=pending

**Status**: [ ] ✅ Iniciado | [ ] ⚠️ En progreso | [ ] ❌ Error

---

#### 1.3.9 **monthly_report** (cada 24h, auto-filtra day=1)

**Test** (solo primer día del mes):
```python
from datetime import datetime
if datetime.now().day == 1:
    from app.services.scheduler import _run_monthly_report
    _run_monthly_report()
```

**Expected**: Email enviado a todos los admins activos

**Status**: [ ] ✅ (si día=1) | [ ] ⏸️ No es primer día (esperar mes siguiente)

---

## 2️⃣ HOOKS DE CREACIÓN — Validar Triggers Automáticos

### 2.1 Incident → Auto-Link Risks

**Setup**:
1. Crea 3 Riesgos para Asset_ID = 5
2. Crea Incident con affected_asset_ids = [5]

**Test**:
```python
# Verificar en BD:
SELECT related_risk_ids FROM Incident WHERE code = 'INC-XXXX';
# Debería contener los RIS IDs
```

**Expected**: related_risk_ids populate automáticamente (hasta 20)

**Status**: [ ] ✅ Auto-linked | [ ] ❌ Vacío

**Si falla**:
- Ver logs: grep "auto-link" docker logs
- Revisar: app/routers/incidents.py line 93-112

---

### 2.2 Nonconformity → Auto-Create Risk

**Setup**:
1. Crea Non-Conformity
2. severity = CRITICAL o HIGH
3. evidencia + impacto

**Test**:
```python
# Verificar en BD:
SELECT * FROM Risk WHERE title LIKE '%No Conformidad%';
```

**Expected**: Risk auto-creado con severity=CRITICAL/HIGH

**Status**: [ ] ✅ Auto-created | [ ] ❓ Desconocido (falta validación)

**Búsqueda de código**: `app/routers/nonconformities.py` → grep "auto\|hook"

---

### 2.3 Supplier Score ≤30 → Auto-Create Risk

**Setup**:
1. Crea Supplier con score = 35 (safe)
2. PATCH score = 28 (trigger)

**Test**:
```python
# Verificar en BD:
SELECT * FROM Risk WHERE supplier_id = X AND title LIKE '%supply%';
```

**Expected**: Risk auto-creado con threat="Proveedor crítico"

**Status**: [ ] ✅ Auto-created | [ ] ❌ No creado

**Si falla**:
- Revisar: app/routers/suppliers.py → grep "30\|supply"

---

### 2.4 Risk Duplicate Detection

**Setup**:
1. Crea Risk [Asset=5, Threat=1, Vuln=10]

**Test**:
```python
# Intenta crear el mismo:
# Debería devolver 409 Conflict
POST /api/risks {
  "asset_id": 5,
  "threat_id": 1,
  "vulnerability_id": 10,
  ...
}
```

**Expected**: HTTP 409 + "Riesgo ya existe"

**Status**: [ ] ✅ 409 Conflict | [ ] ❌ Se crea duplicado

---

## 3️⃣ AGENTES IA — Validar Pipeline Claude

### 3.1 Chat RAG

**Setup**:
1. Configura Claude API key en `app/config.py` o `.env`

**Test**:
```bash
curl -X POST http://localhost:8000/api/ai/chat \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"¿Cuáles son los controles ISO 27002 para acceso?"}'
```

**Expected**: Respuesta contextualizada + sources

**Status**: [ ] ✅ Respuesta OK | [ ] ⚠️ Context limitado | [ ] ❌ API error

**Si falla**:
- Verificar: `grep "CLAUDE_API_KEY" app/config.py`
- Ver logs: `grep "IA Service" docker logs`

---

### 3.2 CVE Analysis (Bajo Demanda)

**Setup**:
1. Obtén CVE ID (ej: CVE-2024-12345)

**Test**:
```bash
curl -X GET "http://localhost:8000/api/cve/CVE-2024-12345/analyze" \
  -H "Authorization: Bearer TOKEN"
```

**Expected**: JSON con impacto, affected_systems, mitigations

**Status**: [ ] ✅ Análisis generado | [ ] ❌ Error

---

### 3.3 Risk Analysis (Cuestionario)

**Búsqueda**: ¿Dónde está el endpoint? `app/routers/ai.py` → grep "questionnaire\|analysis"

**Test** (cuando encuentres el endpoint):
```bash
curl -X POST "http://localhost:8000/api/ai/analyze-risk" \
  -d "{cuestionario}"
```

**Expected**: Scenarios JSON con threats, probabilities, treatments

**Status**: [ ] ✅ Endpoint encontrado | [ ] ❓ No encontrado | [ ] ❌ Error

---

## 4️⃣ INTEGRACIONES EXTERNAS

### 4.1 OSINT Email Scan

**Setup**:
1. Crea OSINTIdentifier type=email value=test@example.com
2. Asegura que HIBP/LeakCheck API keys están configuradas

**Test**:
```python
from app.services.osint_engine import osint_engine

scan_id = 123  # crear OSINTScan primero
osint_engine.run_email_scan(scan_id, "test@example.com", user_id=1)

# Verificar:
SELECT * FROM OSINTFinding WHERE scan_id = 123;
```

**Expected**: Hallazgos encontrados (si email en breach) o "Sin hallazgos"

**Status**: [ ] ✅ OK | [ ] ⚠️ Sin hallazgos (esperado) | [ ] ❌ Error

---

### 4.2 OSINT Domain Scan

**Setup**:
1. Crea OSINTIdentifier type=domain value=example.com
2. Shodan API key configurada (opcional, muchos resultados sin key)

**Test**:
```python
from app.services.osint_engine import osint_engine
osint_engine.run_domain_scan(scan_id, "example.com", user_id=1)

SELECT * FROM OSINTFinding WHERE scan_id = X;
```

**Expected**: Registros DNS, SSL cert, tecnologías detectadas

**Status**: [ ] ✅ OK | [ ] ❌ Error

---

### 4.3 SharePoint Integration

**Status**: ⚠️ Código existe pero no usado en producción

**Si necesitas**:
1. Configurar Microsoft Graph API credentials
2. Ir a UI → Admin → Integración SharePoint
3. Conectar y testear "Importar documentación"

**Status**: [ ] ✅ Integrado | [ ] ⏸️ No usado | [ ] ❌ Error

---

## 5️⃣ MULTI-TENANCY — Validar Isolamiento

### 5.1 Verificar organization_id en Queries

**Test** (como Admin de Org A, intenta acceder a Org B):
```bash
curl -X GET "http://localhost:8000/api/risks" \
  -H "Authorization: Bearer TOKEN_ORG_A"
  # Debería devolver solo risks de Org A
```

**Expected**: Riesgos de Org A solo; HTTP 403 si intenta acceso directo a Org B

**Status**: [ ] ✅ Aislado | [ ] ❌ Filtra mal

**Si falla**:
- Revisar: `app/security.py` → `filter_by_org()`
- Comprobar: TODOS los routers usan `filter_by_org()`

---

### 5.2 Verificar Scheduler No Filtra Orgs (Intencionado)

**Test**:
```python
# Scheduler debería procesar TODAS las orgs
db.query(Risk).all()  # No debe tener WHERE organization_id
```

**Status**: [ ] ✅ Scheduler procesa todas orgs | [ ] ❌ Filtra por org

---

## 6️⃣ EMAIL — Validar SMTP

### 6.1 Configurar SMTP

**UI Path**: Admin → Configuración → Email

**Campos**:
- SMTP Host: (ej: smtp.gmail.com)
- SMTP Port: 587
- Username: tu@email.com
- Password: (cifrado Fernet automático)
- From: sistema@tudominio.com

**Test**:
```python
from app.services import email_service
from app.database import SessionLocal

db = SessionLocal()
cfg = email_service.get_settings(db)
if cfg:
    email_service.send_email(
        cfg,
        "test@example.com",
        "Test Subject",
        "<h1>Test Body</h1>"
    )
    print("✅ Email enviado")
```

**Expected**: Email recibido en 30 segundos

**Status**: [ ] ✅ Enviado | [ ] ❌ Error

**Si falla**:
- Verificar host/port correcto
- Comprobar credenciales
- Ver logs: `grep -i "email\|smtp" docker logs`

---

## 7️⃣ REPORTS — Validar Generación

### 7.1 Informe Mensual Manual

**Test** (no esperes al 1º de mes):
```python
from datetime import datetime
from app.services.scheduler import _run_monthly_report

# Fuerza ejecución
_run_monthly_report()
```

**Expected**: Email enviado a todos los admins con gráficos + KPIs

**Status**: [ ] ✅ Enviado | [ ] ❌ Error

---

### 7.2 Reportes con IA

**UI Path**: Reports → Generar Informe con IA

**Expected**: Informe narrativo (no template estático)

**Status**: [ ] ✅ Generado | [ ] ❌ Error

---

## 📊 RESULTADO FINAL

**Copia y pega tu checklist completado aquí**:

```
✅ SCHEDULER (10/10 jobs)
✅ HOOKS (4/4 triggers)
✅ IA AGENTS (5/6 working)
⚠️ OSINT (7/7 sources, algunas sin API key)
✅ EMAIL (SMTP working)
❓ PENDIENTE: Asset Risk Analysis endpoint

SCORE: 85% — Funcional; algunas gaps documentadas
```

---

## 🔧 TROUBLESHOOTING RÁPIDO

| Problema | Causa Probable | Solución |
|----------|---|---|
| Scheduler no inicia | APScheduler no instalado | `pip install apscheduler` |
| Jobs no se disparan | Scheduler no corre en thread daemon | Ver `app/services/scheduler.py:1029` |
| Emails no enviados | SMTP no configurado | UI → Admin → Email config |
| Auto-link no funciona | Hook tiene try/except silencioso | Ver logs; revisar `incidents.py` |
| CVE analysis lento | NVD API rate limit | Esperar o usar cache |
| OSINT scan cuelga | Thread no inicia correctamente | Revisar `threading.Thread()` en scheduler |
| Multi-tenancy falla | Query sin `filter_by_org()` | Revisar router específico |
| IA devuelve genérico | RAG no recupera contexto | Verificar FTS5 indexed; query syntax |

---

**Última actualización**: 2026-05-30
**Próximo paso**: Ejecutar checklist completo y documentar gaps
