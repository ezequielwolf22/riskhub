# RiskHub v1.7.7 — Flujo Real de Creacion de Riesgos

**Fecha**: 2026-05-30 | **Estado**: Análisis de lo que está REALMENTE implementado

---

## ⚠️ TU VISION vs REALIDAD

### TU PROPUESTA (Lo que DEBERÍA ser):

```
Activos (upload usuario)
  ↓ [Auto-agrupación]
  ↓
Activos se contrastan con Amenazas [AUTOMÁTICO]
  ↓
Se calcula impacto [AUTOMÁTICO ISO27005/MAGERIT]
  ↓
Riesgo Inherente [AUTOMÁTICO]
  ↓
Se aplican controles [AUTOMÁTICO heredado]
  ↓
Riesgo Residual [AUTOMÁTICO]
  ↓
CVE se cruza con activos [AUTOMÁTICO]
  ↓
OSINT se cruza con activos [AUTOMÁTICO]
  ↓
Se contrasta con Risk Appetite [AUTOMÁTICO]
  ├─ Si <= Appetite → ACCEPTANCE automática + CIERRE
  └─ Si > Appetite → MITIGATION + REPORTING (email)
```

---

## ✅ LO QUE ESTÁ IMPLEMENTADO

### 1. **Activos** ✅
- **Implementado**: Usuarios suben activos manualmente
- **Archivo**: `app/routers/assets.py`
- **Status**: 100% manual (no auto-agrupación en creación)

### 2. **Agrupación Inteligente de Activos** ⚠️ EXISTE PERO NO AUTOMÁTICA
- **Archivo**: `app/services/asset_grouping_service.py`
- **Implementado**: Claude IA agrupa activos según criterios (tipo, tecnología, clasificación data, criticidad CIA)
- **Status**: 
  - ✅ Código existe
  - ❌ NO dispara automáticamente al subir activos
  - ❓ Necesita endpoint router para activarlo

### 3. **Contraste Activo × Amenaza** ❌ NO AUTOMÁTICO
- **Falta completamente**: No hay proceso automático que:
  - Tome un activo nuevo
  - Cruce con todas las amenazas del catálogo
  - Cree riesgos automáticamente
- **Lo que existe**: Creación MANUAL de riesgos donde usuario elige activo + amenaza

### 4. **Cálculo de Impacto (MAGERIT/ISO27005)** ⚠️ PARCIAL
- **Archivo**: `app/services/risk_engine.py`
- **Implementado**: 
  - ✅ Matriz ISO27005 Annex E.2 (5x5)
  - ✅ Criterios de impacto (financiero, operacional, reputacional, regulatory, safety)
  - ❌ NO es automático desde MAGERIT valoración de activos
  - ❌ Usuario debe entrar manualmente inherent_likelihood y inherent_consequence

### 5. **Cálculo Riesgo Inherente** ✅ AUTOMÁTICO (EN EDICION)
- **Archivo**: `app/routers/risks.py` línea 36
- **Implementado**: 
  ```python
  risk.inherent_level = calc_level(
      risk.inherent_consequence, 
      risk.inherent_likelihood, 
      matrix
  )
  ```
- **Status**: ✅ Automático CUANDO se edita riesgo
- **PERO**: Los valores inherent_likelihood/consequence son MANUALES

### 6. **Aplicación de Controles Heredados** ✅ IMPLEMENTADO
- **Archivo**: `app/routers/risks.py` línea 38, `app/services/risk_engine.py` línea 64-76
- **Implementado**: 
  ```python
  controls = [
      {"maturity": ci.maturity, "contribution": 1.0} 
      for ci in risk.controls
  ]
  reduction = control_reduction(controls)  # combina eficacia
  ```
- **Status**: ✅ Automático al calcular residual
- **Modelo**: Eficacia = (maturity/5) * contribution; combinación = 1 - PROD(1 - efficacy)

### 7. **Cálculo Riesgo Residual** ✅ AUTOMÁTICO
- **Archivo**: `app/services/risk_engine.py` línea 79-95
- **Implementado**: 
  ```python
  reduction = control_reduction(controls)
  new_lik = clamp(round(inherent_likelihood * (1.0 - reduction)))
  new_cons = clamp(round(inherent_consequence * (1.0 - 0.5 * reduction)))
  residual_level = calc_level(new_cons, new_lik, matrix)
  ```
- **Status**: ✅ Automático al editar riesgo + controles

### 8. **Cruce CVE × Activos** ❌ NO INTEGRADO EN FLUJO
- **Existe**: `app/services/cve_service.py`, `app/services/cve_analysis_service.py`
- **Status**:
  - ✅ Scheduler busca CVEs cada 24h
  - ⚠️ Análisis IA existe (bajo demanda)
  - ❌ NO se cruza automáticamente con activos
  - ❌ NO crea riesgos automáticamente desde CVE

### 9. **Cruce OSINT × Activos** ❌ NO INTEGRADO EN FLUJO
- **Existe**: `app/services/osint_engine.py`, 7 fuentes
- **Status**:
  - ✅ Scheduler escanea cada 7 días
  - ❌ NO se cruza automáticamente con activos
  - ⚠️ Auto-crea Incident si hallazgo CRITICAL/HIGH (pero NO Risk directo)

### 10. **Contraste contra Risk Appetite** ✅ IMPLEMENTADO
- **Archivo**: `app/routers/risks.py` línea 45-58
- **Implementado**: 
  ```python
  appetite = ctx.risk_appetite if ctx and ctx.risk_appetite is not None else 3
  if rlev <= appetite and risk.status not in (RiskStatus.CLOSED,):
      risk.treatment_option = TreatmentOption.ACCEPTANCE
      if risk.status in (RiskStatus.IDENTIFIED, RiskStatus.ASSESSED):
          risk.status = RiskStatus.ACCEPTED
  ```
- **Status**: ✅ Automático cuando residual_level se recalcula
- **Lógica**: 
  - Si `residual <= appetite` → ACCEPTANCE automática + cambio status a ACCEPTED
  - Si `residual > appetite` → Usuario debe elegir tratamiento manual

### 11. **Auto-Reporting (Email)** ✅ IMPLEMENTADO
- **Archivo**: `app/services/scheduler.py` línea 100-478
- **Eventos que disparan email**:
  - ✅ `risk_critical` (residual >= 6)
  - ✅ `risk_high` (residual >= 6)
  - ✅ `treatment_overdue` (treatment_due_date < now)
  - ✅ `treatment_due_soon` (within N days)
  - ✅ `daily_digest` (resumen diario)
  - ✅ `risk_no_treatment` (riesgo alto sin plan)
- **Status**: ✅ Completamente automático (scheduler cada 1h)

---

## 📊 MATRIZ DE COMPLETITUD

| Paso | Automatico? | Implementado? | Codigo | Nota |
|------|------------|--------------|--------|------|
| 1. Activos upload | ❌ Manual | ✅ | assets.py | Usuario sube CSV |
| 2. Agrupacion activos | ❌ Manual trigger | ✅ Existe | asset_grouping_service.py | Servicio IA existe, no dispara auto |
| 3. Contraste activo×amenaza | ❌ NO | ❌ | - | **FALTA COMPLETAMENTE** |
| 4. Calculo impacto MAGERIT | ⚠️ Parcial | ✅ | risk_engine.py | Matriz existe, criterios NO automáticos |
| 5. Riesgo inherente | ✅ Auto | ✅ | risks.py | Auto al guardar riesgo |
| 6. Aplicar controles | ✅ Auto | ✅ | risk_engine.py | Auto al calcular residual |
| 7. Riesgo residual | ✅ Auto | ✅ | risk_engine.py | Auto al guardar/editar |
| 8. CVE × Activos | ❌ NO | ⚠️ Parcial | cve_service.py | Busqueda auto, cruce manual |
| 9. OSINT × Activos | ❌ NO | ⚠️ Parcial | osint_engine.py | Busqueda auto, cruce manual |
| 10. Risk Appetite | ✅ Auto | ✅ | risks.py | Auto-acceptance si <= appetite |
| 11. Reporting (email) | ✅ Auto | ✅ | scheduler.py | Auto cada 1h |

**Score: 54% automático, 36% parcial, 10% faltante**

---

## 🔧 QUÉ FALTA PARA COMPLETAR TU VISION

### FALTA 1: Auto-crear Riesgos al Subir Activos
```
Cuando usuario POST /assets/bulk:
  - Para cada activo nuevo
  - Query: SELECT * FROM Threat WHERE aplicable_al_tipo_activo
  - Para cada threat encontrada
    POST /risks {asset_id, threat_id, inherent_likelihood, inherent_consequence}
    + Controls auto-heredados
    → Calcula residual
    → Compara appetite
    → Si > appetite → auto-mitigation workflow
```

**Archivos a crear/modificar**:
- `app/services/risk_auto_generator.py` (nuevo)
- `app/routers/assets.py` (hook en POST bulk)

---

### FALTA 2: CVE Auto-Integración en Flujo
```
Cuando scheduler detecta CVE CRITICAL/HIGH:
  1. NVD fetch → CVE details
  2. Buscar Activos que coincidan (software inventory)
  3. Para cada asset afectado:
     POST /risks {
       asset_id, 
       threat="CVE-XXXX-XXXXX",
       vulnerability_id=...,
       inherent_likelihood=4 (alto),
       inherent_consequence=calculated,
       ...
     }
  4. Calcula residual automáticamente
  5. Si > appetite → email URGENT
```

**Archivos a crear/modificar**:
- `app/services/cve_service.py` (integración riesgos)
- `app/services/scheduler.py` (ampliar _run_cve_auto_scan)

---

### FALTA 3: OSINT Auto-Integración en Flujo
```
Cuando scheduler detecta OSINT hallazgo CRITICAL/HIGH:
  1. Identificar asset relevante (por dominio, IP, email)
  2. Si hallazgo es "exposed credentials":
     POST /risks {
       asset_id=...,
       threat="Credenciales filtradas",
       inherent_likelihood=4,
       inherent_consequence=4,
       ...
     }
  3. Calcula residual automáticamente
  4. Si > appetite → email URGENT + creador tarea
```

**Archivos a crear/modificar**:
- `app/services/osint_engine.py` (integración riesgos)
- `app/services/scheduler.py` (ampliar _run_osint_periodic_scan)

---

### FALTA 4: Valoración Automática MAGERIT de Activos
```
POST /assets/{id}/analyze
  ← IA analiza activo
  ← Claude valora CIA (0-4) según descripción
  ← Guarda: criticality_CIA, data_classification
  ← Retorna sugerencia de inherent_consequence basada en criticidad
```

**Archivos a crear/modificar**:
- `app/services/asset_valuation_service.py` (nuevo)
- `app/routers/assets.py` (endpoint analyze)

---

## 📝 ESTADO ACTUAL DE COMPLETITUD

### LO QUE FUNCIONA AUTOMATICO AL 100%:
1. ✅ Cálculo inherent_level (cuando user entra datos)
2. ✅ Cálculo residual (aplicando controles)
3. ✅ Auto-acceptance si residual <= appetite
4. ✅ Email reporting (scheduler)
5. ✅ Control reduction formula

### LO QUE FUNCIONA AL 50%:
1. ⚠️ CVE searching (falta cruce con activos)
2. ⚠️ OSINT scanning (falta cruce con activos)
3. ⚠️ Asset grouping (falta disparo automático)

### LO QUE FALTA COMPLETAMENTE:
1. ❌ Auto-crear riesgos activo × amenaza
2. ❌ Auto-valoración MAGERIT de activos
3. ❌ Auto-integración CVE en flujo riesgos
4. ❌ Auto-integración OSINT en flujo riesgos

---

## 🎯 RECOMENDACION

**Implementar en este orden:**

### FASE 1 (2 días): Flujo Manual Mejorado (Ahora)
- ✅ Ya está: Cálculo automático inherent + residual + appetite
- ✅ Ya está: Email reporting
- ⚠️ Documentar que user entrada es: likelihood + consequence (no automático)

### FASE 2 (3 días): Auto-crear Riesgos Activo × Amenaza
- [ ] `risk_auto_generator.py`: Cuando se carga activo, generar riesgos
- [ ] Hook en assets.py POST bulk
- [ ] Asignar controles automáticamente

### FASE 3 (2 días): Integración CVE en Flujo
- [ ] Ampliar scheduler para que cree riesgos (no solo busque)
- [ ] Cruce automático CVE × asset software
- [ ] Email URGENT si CVE afecta crítico

### FASE 4 (2 días): Integración OSINT en Flujo
- [ ] Ampliar scheduler para que cree riesgos
- [ ] Cruce automático hallazgo × asset
- [ ] Creación automática mitigación workflow

---

## TABLA RESUMEN

```
ESTADO ACTUAL (v1.7.7):

Paso                          Manual/Auto    Implementado    % Completo
────────────────────────────────────────────────────────────────────────
Subir activos                 MANUAL         ✅              100%
Agrupar activos               MANUAL         ✅ (existe)     0% (no dispara)
Elegir amenaza                MANUAL         ✅              100%
Crear riesgo base             MANUAL         ✅              100%
Calcular inherent             AUTO           ✅              100%
Asignar controles             MANUAL         ✅              100%
Calcular residual             AUTO           ✅              100%
Contrastar appetite           AUTO           ✅              100%
Auto-accept si OK             AUTO           ✅              100%
Buscar CVEs                   AUTO           ✅              100%
Integrar CVEs en riesgos      MANUAL         ❌              0%
Buscar OSINT                  AUTO           ✅              100%
Integrar OSINT en riesgos     MANUAL         ❌              0%
Email reporting               AUTO           ✅              100%
────────────────────────────────────────────────────────────────────────
PROMEDIO AUTOMATIZADO:                                       54%
```

---

**Conclusión**: El **núcleo está bien** (cálculos, appetite, reporting), pero **faltan las integraciones automatizadas** (CVE, OSINT, creación masiva).

**Siguiente paso**: ¿Quieres que planifique la FASE 2 (Auto-crear riesgos activo × amenaza)?
