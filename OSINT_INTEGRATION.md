# Integración OSINT (huella-digital) en RiskHub

## Resumen

Se ha integrado completamente la funcionalidad OSINT de `huella-digital` en RiskHub como un único producto unificado. La aplicación ahora incluye escaneo de inteligencia de fuentes abiertas directamente en el dashboard.

**Fecha de integración**: 2026-05-25  
**Versión**: 1.4.0+OSINT  
**Arquitectura**: Python/FastAPI + Vanilla JS + SQLite

---

## Componentes Agregados

### Backend (Python/FastAPI)

#### Modelos (`app/models.py`)
- `OSINTScan` — Registro de escaneos OSINT ejecutados
- `OSINTFinding` — Hallazgos/vulnerabilidades descubiertas
- `OSINTIdentifier` — Identificadores monitorizados (email, username, domain, IP, URL)
- `OSINTAPIKey` — Almacenamiento seguro (Fernet-encrypted) de claves API

#### Servicios (`app/services/`)
- `osint_hibp.py` — Integración Have I Been Pwned (emails en breaches)
- `osint_virustotal.py` — Análisis de URLs y archivos maliciosos
- `osint_leakcheck.py` — Búsqueda de exposiciones de datos
- `osint_intelx.py` — Inteligencia X (dumps, pastes, fugas)
- `osint_github.py` — Recon de repositorios públicos y secrets
- `osint_engine.py` — Motor orquestador que coordina todos los servicios

#### Endpoints REST (`app/routers/osint.py`)
```
POST   /api/v1/osint/scans/email        — Iniciar escaneo de email
POST   /api/v1/osint/scans/url          — Iniciar escaneo de URL
POST   /api/v1/osint/scans/username     — Iniciar escaneo de username (GitHub)
GET    /api/v1/osint/scans              — Listar escaneos
GET    /api/v1/osint/scans/{scan_id}    — Detalles de un escaneo
GET    /api/v1/osint/findings           — Listar hallazgos
GET    /api/v1/osint/findings/{id}      — Detalles de hallazgo
PATCH  /api/v1/osint/findings/{id}/remediate    — Marcar como remediado
PATCH  /api/v1/osint/findings/{id}/unremediate  — Desmarcar como remediado
GET    /api/v1/osint/identifiers        — Listar identificadores monitorizados
GET    /api/v1/osint/stats              — Estadísticas OSINT
```

#### Esquemas Pydantic (`app/schemas.py`)
- `OSINTScanCreate`, `OSINTScanResponse`
- `OSINTFindingResponse`
- `OSINTIdentifierResponse`
- `PaginatedResponse`

#### Configuración (`app/config.py`)
```python
RISKHUB_HIBP_API_KEY           # Have I Been Pwned
RISKHUB_VIRUSTOTAL_API_KEY     # VirusTotal
RISKHUB_LEAKCHECK_API_KEY      # LeakCheck
RISKHUB_INTELX_API_KEY         # Intelligence X
RISKHUB_GITHUB_API_TOKEN       # GitHub
```

### Frontend (Vanilla JS)

#### Vista OSINT (`app/static/js/views/osint.js`)
Nueva sección completa con:
- **Escaneos**: Iniciar escaneos (email, URL, username, dominio), monitorear progreso
- **Hallazgos**: Ver hallazgos por remediar, historial, marcar como resueltos
- **Identificadores**: Monitorizar emails, usernames, dominios públicos
- **Estadísticas**: Dashboard con resumen de riesgos, gráficos por nivel

#### Integración UI
- Menú lateral: nuevo item "OSINT" con icono de búsqueda
- Route registrado en `app.js`
- Script cargado en `index.html`

---

## Flujo de Uso

### 1. Configurar API Keys

En `.env`:
```bash
RISKHUB_HIBP_API_KEY=<tu-clave-hibp>
RISKHUB_VIRUSTOTAL_API_KEY=<tu-clave-vt>
RISKHUB_LEAKCHECK_API_KEY=<tu-clave-leakcheck>
RISKHUB_INTELX_API_KEY=<tu-clave-intelx>
RISKHUB_GITHUB_API_TOKEN=<tu-token-github>
```

**Nota**: Sin claves, los escaneos no funcionan pero la UI está disponible.

### 2. Iniciar Escaneos

Usuario analyst/admin entra a OSINT → "Iniciar nuevo escaneo":
- Selecciona tipo (email, URL, username, dominio)
- Ingresa objetivo
- Haz click "Iniciar escaneo"

El escaneo se ejecuta en **background** (no bloquea la UI).

### 3. Ver Hallazgos

Los hallazgos aparecen en tiempo real en la pestaña "Hallazgos":
- Cada hallazgo incluye: título, fuente (HIBP, VT, etc.), nivel de riesgo, score
- Usuario puede marcar como "remediado" cuando se haya solucionado
- Los remedios quedan registrados en BD con timestamp

### 4. Monitorizar Identificadores

Pestaña "Identificadores" lista todos los emails/usernames escaneados:
- Mostra último escaneo y riesgo actual
- Permite re-escanear cuando lo necesites
- Historial automático de cambios de riesgo

### 5. Dashboard de Estadísticas

Pestaña "Estadísticas":
- Total de escaneos realizados
- Hallazgos por nivel de riesgo (crítico, alto, medio, bajo, info)
- Tasa de remediación
- Score de riesgo promedio

---

## Integración con Análisis de Riesgos

Los hallazgos OSINT pueden vincularse a:
- **Vulnerabilidades** del inventario de activos (en progreso)
- **Amenazas** de seguridad identificadas
- **Incidentes** de seguridad posteriores

(La tabla `osint_vulnerability_links` permite mapeo futuro)

---

## Datos Técnicos

### Base de Datos

Nuevas tablas en SQLite:
```
osint_scans           — Escaneos ejecutados
osint_findings        — Resultados de escaneos
osint_identifiers     — Emails/usernames/dominios monitorizados
osint_api_keys        — Credenciales cifradas de APIs
osint_vulnerability_links — Mapping futuro a vulnerabilidades
```

### Límites de Rate Limiting

Respetados por cada servicio:
- **HIBP**: 1.5 segundos entre requests
- **VirusTotal**: 15 segundos entre requests (60/min)
- **LeakCheck**: Sin límite (free API)
- **Intelligence X**: 10 segundos (free API)
- **GitHub**: Según autenticación (60/hr sin token)

### Execución en Background

Los escaneos se lanzan en **background tasks** via FastAPI `BackgroundTasks`:
- No bloquean la respuesta HTTP
- El cliente hace polling cada 3 segundos para actualizar estado
- El estado de progreso se actualiza en tiempo real en BD

---

## Testing

### Checklist Manual

- [ ] **Backend**: `python -m uvicorn app.main:app --reload` en localhost:8000
- [ ] **BD**: Verifica que se crearon las tablas OSINT:
  ```bash
  sqlite3 riskhub.db ".tables" | grep osint
  ```
- [ ] **Frontend**: Accede a http://localhost:8000/#/osint en navegador
- [ ] **Menú**: Verifica que "OSINT" aparece en sidebar
- [ ] **Sin API keys**: Intenta escanear sin claves configuradas (debe indicar error graceful)
- [ ] **Con API keys**: Configura HIBP (la más fácil), intenta escanear un email conocido
- [ ] **Flujo completo**: 
  1. Escanea tu email
  2. Espera resultado
  3. Verifica hallazgos si los hay
  4. Marca como remediado
  5. Verifica estadísticas actualizadas

### Deploy a Producción

1. Actualiza `.env` en servidor con API keys
2. Pull cambios: `git pull origin main`
3. Ejecuta `bash /opt/riskhub/deploy.sh`
4. Verifica logs: `docker logs riskhub`
5. Accede a https://91.99.83.202/#/osint

---

## Limitaciones Conocidas

1. **HIBP**: Requiere API key (gratuita pero necesita registro)
2. **VirusTotal**: Rate limiting estricto, timeout de 30s por URL
3. **Intelligence X**: Free API limitada; pro API es más potente
4. **GitHub**: Búsqueda de secrets es análisis de metadatos, no análisis del código real
5. **No hay webhook**: Los escaneos son on-demand, no hay monitoreo continuo
6. **Multitenancy**: Los API keys son globales (no por usuario/tenant)

---

## Roadmap Futuro

- [ ] Scheduling automático de re-escaneos (mensual, trimestral)
- [ ] Webhooks cuando se descubra un hallazgo crítico
- [ ] Integración con Slack/Teams para notificaciones
- [ ] Análisis de patrones (emails en múltiples breaches = alto riesgo)
- [ ] Vinculación automática a vulnerabilidades registradas
- [ ] SuperAdmin panel para configurar API keys por tenant
- [ ] Soporte para custom OSINT sources (APIs propias)
- [ ] Reportes PDF de escaneos OSINT
- [ ] Comparativa trimestral: "Mejoras en 3 meses"

---

## Arquitectura General (Después de Integración)

```
RiskHub (Unified Product)
├── ISO 27005 Risk Management
├── Asset Inventory & Threats
├── Control Implementation
├── GDPR/Compliance
├── Incidents & Nonconformities
├── Internal Audits
├── CVE Monitoring
└── OSINT (NEW) ← Integrado aquí
    ├── Email Scanning (HIBP, LeakCheck, IntelX)
    ├── URL Analysis (VirusTotal)
    ├── Username Recon (GitHub)
    ├── Domain Intelligence
    └── Findings Dashboard

All data unified in SQLite, single auth, single dashboard.
```

---

## Archivos Modificados/Agregados

### Nuevos
- `app/services/osint_*.py` (5 servicios)
- `app/routers/osint.py`
- `app/static/js/views/osint.js`
- `OSINT_INTEGRATION.md` (este archivo)

### Modificados
- `app/models.py` (+100 líneas de modelos OSINT)
- `app/schemas.py` (+50 líneas de esquemas)
- `app/config.py` (+5 vars de configuración)
- `app/main.py` (import + include_router)
- `app/static/js/app.js` (1 línea: ruta OSINT)
- `app/static/index.html` (1 link + 1 script tag)
- `.env.example` (+25 líneas de variables)

**Total LoC**: ~1800 líneas nuevas (backend + frontend)

---

## Soporte y Preguntas

Para debugg:
1. Verifica `docker logs riskhub`
2. Revisa BD: `sqlite3 riskhub.db "SELECT COUNT(*) FROM osint_scans;"`
3. Testea endpoint: `curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/osint/stats`

---

**Integración completada satisfactoriamente.**
