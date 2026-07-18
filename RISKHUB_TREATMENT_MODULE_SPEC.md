# RiskHub — Plan Director y Tratamiento de Riesgos (v2)

Especificacion de implementacion. Publico objetivo: un modelo/desarrollador que NO conoce
el proyecto. Seguir los sprints EN ORDEN. Cada sprint termina con la app arrancando
(`uvicorn app.main:app --reload --port 8000`) y sus tests en verde (`pytest tests/ -q`).

> v2 (2026-07-15): reescritura completa tras benchmark de mercado (ServiceNow IRM,
> Archer, Vanta, Balbix/SAFE, Eramba, LogicGate) y analisis de un plan director real
> (jerarquia Programa → Iniciativa → Linea de trabajo → OKR, 13/35/99/275 elementos).

---

## 0. Vision de producto y principio rector

### 0.1 Que hace el mercado y que hacemos mejor

| Capacidad | Mercado | RiskHub (este modulo) |
|---|---|---|
| Plan de remediacion | ServiceNow: Risk Response Tasks con workflow y action items; Archer: findings → remediation plans con due dates | Igual (ya existe TreatmentTask) + cockpit agregado |
| Reduccion esperada del riesgo | Manual: alguien teclea el nivel objetivo | **CALCULADA por el motor determinista** via simulacion what-if de madurez de controles (nadie estima a mano) |
| Vincular iniciativas a riesgos | Manual o con IA generica | **Automatico y determinista**: iniciativa declara controles objetivo → riesgos afectados se derivan de `risk_controls` + `threat_control_map` |
| Estado "At Risk" de una iniciativa | Lo marca una persona | **Computado** por reglas (health check semanal) con razones explicables |
| Informes de avance | Los redactan empleados | Bitacora automatica de eventos + narrativa mensual generada por IA |
| Burndown de riesgo | Balbix/SAFE (CRQ propietario) | Historico real desde `risk_snapshots` (ya existe) + curva proyectada desde las iniciativas activas |
| Cierre de iniciativa | Se marca "completada" y ya | **Cierre verificado**: se comprueba madurez alcanzada y residual real vs proyectado; el gap queda visible |
| Deteccion de huecos | Dashboards pasivos | Riesgos sobre apetito sin cobertura → **borradores de iniciativa generados** (controles candidatos + proyeccion incluidos) a un click de aprobar |

### 0.2 Principio rector (no negociable)

**Maxima automatizacion, minimo trabajo manual.** El empleado solo hace lo que exige
juicio humano: aprobar, decidir prioridades y fechas objetivo. Todo lo demas lo hace el
sistema: vincular, proyectar, vigilar, redactar avances, escalar y reportar.

**Y ademas:** las iniciativas NUNCA modifican `residual_level` de un riesgo. El residual
solo cambia via el motor determinista (`risk_recalc_service`) cuando cambian
controles/madurez/evidencias. Este modulo PROYECTA (simulacion con el mismo motor) y
VERIFICA (compara lo proyectado con lo que el motor calculo de verdad). La IA propone
(imports, borradores, narrativas); el usuario confirma; todo lo propuesto por IA lleva
`ai_generated`/`ai_rationale`.

**Alcance:** gestion y gobierno del riesgo (ISO 27005 9 / ISO 27001 6.1.3e). NO es una
herramienta de remediacion tecnica de vulnerabilidades.

### 0.3 Que se construye

1. **Cockpit de Tratamiento** (`treatment.js`, pestana en hub Riesgos): vision operativa
   unica de todos los planes de tratamiento — KPIs, riesgos por opcion, progreso,
   vencimientos, tareas, cobertura por iniciativas, burndown.
2. **Plan Director** (`plan-director.js`, pestana en hub Riesgos, gated plan pro):
   jerarquia Programa → Iniciativa → Objetivo (OKR) + controles objetivo + riesgos
   auto-vinculados + Gantt + bitacora + import IA + borradores automaticos.

---

## 0.4 Contexto tecnico existente (leer antes de tocar nada)

RiskHub: FastAPI + SQLAlchemy 2.0 + SQLite/PostgreSQL; frontend vanilla JS SPA
hash-based en `app/static/` (sin frameworks ni CDNs). Piezas que este modulo REUTILIZA:

- `Risk` (`app/models.py:476`): ya tiene `treatment_option` (enum: modification/
  retention/avoidance/sharing), `treatment_plan`, `treatment_due_date`,
  `treatment_progress` (0-100), `target_residual_level`, `target_date`,
  `baseline_residual_level`, workflow de aceptacion formal, `analysis_stale`.
- `TreatmentTask` (`app/models.py:1147`) + `app/routers/tasks.py`: tareas TSK-XXXX con
  bucle cerrado tareas DONE → `risk.treatment_progress` → estado TREATED.
- `RiskSnapshot` (`app/models.py:1129`): snapshot mensual inherente/residual por riesgo
  (lo puebla un job — localizarlo en `app/services/scheduler.py`). Base del burndown.
- `RiskContext.risk_appetite` (`app/models.py:248`): nivel 0..8 maximo aceptable (default 3).
- **Motor**: `app/services/risk_engine.py` → `calc_residual(inherent_likelihood,
  inherent_consequence, controls: list[dict], matrix)` es PURA (no toca BD).
  `app/services/risk_recalc_service.py` → `recalc_risk(db, risk)` (autoridad unica de
  recalculo), `control_payload(ci, contribution, db)` (convierte una
  ControlImplementation al dict que consume el motor, con madurez ajustada por
  evidencia), `get_matrix`, `recalc_risks_for_impls`. El recalculo aplica ademas un
  "floor" por controles obligatorios con madurez < 2 (ver `recalc_risk:156-168`).
- `risk_controls` (tabla asociacion riesgo↔ControlImplementation con `contribution`).
- `app/services/threat_knowledge.py`: controles candidatos por amenaza
  (catalogo `app/data/threat_control_map.json`, 97 amenazas) + overrides por org.
- IA: `app/services/claude_client.py` → `structured_message` (tool use forzado con JSON
  schema; OBLIGATORIO para salida JSON) y `cached_system`; modelos SIEMPRE desde
  `app/services/model_registry.py` (tiers `deep`/`fast`, nunca hardcodear model id).
- `app/services/document_service.py` → `extract_text(data, mime_type)` (PDF/DOCX/XLSX/texto).
- `app/services/ai_learning_service.py` → `record_signal(...)` (senales de decision).
- `app/services/notification_channels.py` → `has_any_channel(...)`, `dispatch_alert(...)`
  (email/Teams/Power Automate por org).
- Scheduler APScheduler: `app/services/scheduler.py` (jobs existentes: escalada de
  tareas, degradacion de controles, informe mensual...). Anadir jobs aqui.
- Cola de jobs BD: `app/services/job_queue.py` (para trabajo IA largo).
- Auditoria: `log_action` (`app/services/audit_service.py`) en toda mutacion.
- Multi-tenancy: `filter_by_org(query, Model, current_user)` + `check_org_access`
  (`app/security.py`) en TODO endpoint; todo modelo nuevo lleva `organization_id`.
- Feature flags: `PLAN_MODULE_LIMITS` en `app/routers/feature_flags.py`.
- Migraciones de columnas: lista `migrations` en `_migrate_columns()` de
  `app/seed.py:217`, formato `("ALTER TABLE t ADD COLUMN c TIPO", "t", "c")`. Las
  TABLAS nuevas no necesitan entrada (las crea `create_all`).

### Convenciones (aplicar SIEMPRE)

- Identificadores en ingles; textos de UI SIEMPRE via `t('clave')` con claves anadidas
  en `app/static/js/i18n/es.js` Y `en.js`. Sin emojis en codigo fuente.
- Enums nuevos: `Column(String(N))` + `Literal[...]` en Pydantic (portabilidad PG; NO
  `Column(Enum(...))`). Nada de `strftime` ni SQL especifico de SQLite.
- Mutaciones con `require_analyst` minimo; borrados con rol admin.
- Vistas nuevas: registrar pestana en `app/static/js/views/hubs.js`, `<script>` en
  `app/static/index.html` (`?v=1.0.0`), entrada en `LegacyRedirects` de
  `app/static/js/app.js`, y seccion en `app/static/js/views/guide.js` (obligatorio).
- NO tocar: la UI de ERP Webhooks (retirada a proposito) ni escribir `residual_level`
  desde este modulo.

---

## 1. Modelo de dominio

Jerarquia (inspirada en planes directores reales, colapsada a 3 niveles + satelites):

```
StrategicProgram  PRG-0001   "Governance, Risk & Compliance"     (area, responsable, presupuesto)
  └─ StrategicInitiative INI-0001  "Evolucionar el programa TPRM"  (owner, prioridad, fechas, NIST fn)
       ├─ InitiativeObjective  OKR-0001  resultado medible (progreso, confianza, fecha)
       ├─ InitiativeControlTarget        control + madurez objetivo  ← NUCLEO DE LA AUTOMATIZACION
       ├─ InitiativeRiskLink             riesgos afectados (derivados automaticamente)
       ├─ TreatmentTask.initiative_id    tareas operativas (modelo existente)
       └─ InitiativeLogEntry             bitacora (sistema + humano + IA)
```

El flujo de automatizacion completo:

```
Usuario declara: "esta iniciativa lleva A.8.7 de madurez 1 → 3 y A.8.13 de 2 → 4"
        ↓ (automatico, determinista)
auto_link_risks: riesgos afectados = los vinculados a esos controles + los que el
                 threat_control_map senala como tratables por esos controles
        ↓ (automatico, mismo motor del residual)
project_initiative: residual proyectado por riesgo simulando la madurez objetivo
        ↓ (continuo)
health check semanal + bitacora automatica + narrativa IA mensual + digest Teams/email
        ↓ (al completar)
verify_initiative: ¿se alcanzo la madurez? ¿el residual real bajo lo proyectado?
                   gap visible; el residual real lo puso el motor, nunca este modulo
```

---

## Sprint 1 — Backend: modelos + CRUD

### 1.1 Modelos (`app/models.py`, anadir tras `TreatmentTask` ~linea 1170)

```python
class StrategicProgram(Base):
    """Programa del plan estrategico de ciberseguridad (agrupa iniciativas)."""
    __tablename__ = "strategic_programs"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    code = Column(String(32), unique=True, nullable=False)          # PRG-0001
    name = Column(String(255), nullable=False)
    description = Column(Text)
    area = Column(String(64))                    # GRC | Arquitectura | Operaciones | OT | Personas... (texto libre)
    responsible_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    budget = Column(Float, nullable=True)
    budget_approved = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    responsible = relationship("User", foreign_keys=[responsible_id])
    initiatives = relationship("StrategicInitiative", back_populates="program")
    # status del programa NO se almacena: se deriva en lectura de sus iniciativas
    # (peor estado gana: at_risk > in_progress > approved > draft; completed solo si todas)


class StrategicInitiative(Base):
    """Iniciativa del plan director. Declara QUE controles mejora y hasta que madurez;
    el sistema deriva riesgos afectados y residual proyectado. NUNCA toca el residual real."""
    __tablename__ = "strategic_initiatives"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    code = Column(String(32), unique=True, nullable=False)          # INI-0001
    title = Column(String(255), nullable=False)
    description = Column(Text)
    program_id = Column(Integer, ForeignKey("strategic_programs.id"), nullable=True, index=True)
    status = Column(String(16), default="draft", index=True)        # draft|approved|in_progress|on_hold|completed|cancelled
    health = Column(String(16), default="ok")                       # ok|at_risk|blocked  — COMPUTADO, no editable por API
    health_reasons = Column(JSON, nullable=True)                    # ["target_date vencida", "sin actividad 30d"]
    priority = Column(String(16), default="medium")                 # low|medium|high|critical
    nist_function = Column(String(16), nullable=True)               # govern|identify|protect|detect|respond|recover
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    scope = Column(String(16), default="global")                    # global|regional
    business_units = Column(JSON, nullable=True)                    # ["BU Iberia", ...] texto libre
    start_date = Column(DateTime, nullable=True)
    target_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)                           # 0-100 derivado (ver 1.4)
    budget = Column(Float, nullable=True)
    budget_approved = Column(Float, nullable=True)
    expected_risk_reduction = Column(Text)                          # narrativa
    source = Column(String(16), default="manual")                   # manual|import|ai_draft
    source_document_id = Column(Integer, ForeignKey("ai_documents.id"), nullable=True)
    ai_generated = Column(Boolean, default=False)
    ai_rationale = Column(Text, nullable=True)
    verification = Column(JSON, nullable=True)                      # resultado de verify_initiative al completar
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    program = relationship("StrategicProgram", back_populates="initiatives")
    owner = relationship("User", foreign_keys=[owner_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    objectives = relationship("InitiativeObjective", back_populates="initiative",
                              cascade="all, delete-orphan")
    control_targets = relationship("InitiativeControlTarget", back_populates="initiative",
                                   cascade="all, delete-orphan")
    risk_links = relationship("InitiativeRiskLink", back_populates="initiative",
                              cascade="all, delete-orphan")
    log_entries = relationship("InitiativeLogEntry", back_populates="initiative",
                               cascade="all, delete-orphan")


class InitiativeObjective(Base):
    """Objetivo medible (OKR) de una iniciativa."""
    __tablename__ = "initiative_objectives"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    initiative_id = Column(Integer, ForeignKey("strategic_initiatives.id"), nullable=False, index=True)
    code = Column(String(32), nullable=False)                       # OKR-0001 (unico por org, no global)
    definition = Column(Text, nullable=False)
    status = Column(String(16), default="pending")                  # pending|ongoing|completed|cancelled
    confidence = Column(String(8), default="medium")                # high|medium|low
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    collaborator = Column(String(128), nullable=True)               # texto libre (puede no ser usuario)
    target_date = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)                           # 0-100 manual (slider en UI)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    initiative = relationship("StrategicInitiative", back_populates="objectives")
    owner = relationship("User", foreign_keys=[owner_id])


class InitiativeControlTarget(Base):
    """Control que la iniciativa mejora + madurez objetivo. Nucleo de la proyeccion."""
    __tablename__ = "initiative_control_targets"
    __table_args__ = (UniqueConstraint("initiative_id", "implementation_id",
                                       name="uq_initiative_impl"),)
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    initiative_id = Column(Integer, ForeignKey("strategic_initiatives.id"), nullable=False, index=True)
    implementation_id = Column(Integer, ForeignKey("control_implementations.id"), nullable=False, index=True)
    baseline_maturity = Column(Integer, nullable=True)              # sellada al crear el target
    target_maturity = Column(Integer, nullable=False)               # 0..5
    achieved_maturity = Column(Integer, nullable=True)              # sellada por verify_initiative
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    initiative = relationship("StrategicInitiative", back_populates="control_targets")
    implementation = relationship("ControlImplementation")


class InitiativeRiskLink(Base):
    """Riesgo afectado por una iniciativa. origin='auto' cuando lo derivo el sistema."""
    __tablename__ = "initiative_risk_links"
    __table_args__ = (UniqueConstraint("initiative_id", "risk_id", name="uq_initiative_risk"),)
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    initiative_id = Column(Integer, ForeignKey("strategic_initiatives.id"), nullable=False, index=True)
    risk_id = Column(Integer, ForeignKey("risks.id"), nullable=False, index=True)
    origin = Column(String(16), default="manual")                   # auto|manual|ai_import
    baseline_residual_level = Column(Integer, nullable=True)        # sellado al vincular
    projected_residual_level = Column(Integer, nullable=True)       # CALCULADO por project_initiative
    projected_at = Column(DateTime, nullable=True)
    achieved_residual_level = Column(Integer, nullable=True)        # sellado por verify_initiative
    rationale = Column(Text)                                        # para manual/ai_import
    ai_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    initiative = relationship("StrategicInitiative", back_populates="risk_links")
    risk = relationship("Risk")


class InitiativeLogEntry(Base):
    """Bitacora de la iniciativa: eventos del sistema, notas humanas y resumenes IA."""
    __tablename__ = "initiative_log_entries"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    initiative_id = Column(Integer, ForeignKey("strategic_initiatives.id"), nullable=False, index=True)
    objective_id = Column(Integer, ForeignKey("initiative_objectives.id"), nullable=True)
    entry_type = Column(String(16), nullable=False)  # achievement|risk|next_step|comment|system|ai_summary
    text = Column(Text, nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL = sistema/IA
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    initiative = relationship("StrategicInitiative", back_populates="log_entries")
    author = relationship("User", foreign_keys=[author_id])
```

En `TreatmentTask` anadir columna:

```python
    initiative_id = Column(Integer, ForeignKey("strategic_initiatives.id"), nullable=True, index=True)
```

Migracion en `_migrate_columns()` de `app/seed.py`:

```python
("ALTER TABLE treatment_tasks ADD COLUMN initiative_id INTEGER REFERENCES strategic_initiatives(id)", "treatment_tasks", "initiative_id"),
```

### 1.2 Schemas (`app/schemas.py`)

Con `Literal` para los strings-enum y `ge/le` para rangos. Crear:

- `ProgramIn` / `ProgramUpdate` / `ProgramOut` (Out incluye `initiatives_count`,
  `derived_status`, `responsible_name`).
- `InitiativeIn`: title obligatorio; resto opcional. NO acepta `health`, `progress`,
  `verification` ni `source` (los pone el sistema).
- `InitiativeUpdate`: todo Optional (patron `exclude_unset`). Igual: sin campos de sistema.
- `InitiativeOut`: campos del modelo + `owner_name`, `program_name`, `risks_count`,
  `objectives_count`, `tasks_total`, `tasks_done`,
  `projected_reduction_points` (suma de `baseline - projected` de sus links).
- `InitiativeDetailOut(InitiativeOut)`: + `objectives`, `control_targets` (con
  `control_code`, `control_name`, madurez actual en vivo), `risk_links` (con
  `risk_code`, `asset_name`, `threat_name`, `current_residual_level` en vivo),
  `log_entries` (ultimas 50, desc), `tasks`.
- `ObjectiveIn` / `ObjectiveUpdate` / `ObjectiveOut`.
- `ControlTargetIn`: `implementation_id`, `target_maturity` (ge=0 le=5).
- `RiskLinkIn`: `risk_id`, `rationale` opcional (solo para vinculos manuales).
- `LogEntryIn`: `entry_type Literal["achievement","risk","next_step","comment"]`
  (los tipos system/ai_summary solo los crea el backend), `text`, `objective_id` opcional.

### 1.3 Router (`app/routers/initiatives.py`, nuevo)

Prefix `/api/initiatives`, tags `["initiatives"]`. Registrar en `app/main.py` (copiar el
patron de include_router de tasks). Codigos: `_next_code(db, model, prefix)` generico →
`PRG-/INI-/OKR-{max_id+1:04d}` (copiar patron de `tasks.py`).

**IMPORTANTE FastAPI**: declarar las rutas fijas (`/stats`, `/burndown`, `/programs`,
`/import`...) ANTES de las parametrizadas `/{id}`.

| Metodo | Ruta | Rol | Comportamiento |
|---|---|---|---|
| GET | `/programs` | user | Lista programas con `derived_status` e `initiatives_count`. |
| POST | `/programs` | analyst | Crea PRG. `log_action`. |
| PATCH | `/programs/{id}` | analyst | `exclude_unset`. |
| DELETE | `/programs/{id}` | admin | Solo si no tiene iniciativas (409 si tiene). |
| GET | `/` | user | Lista iniciativas. Filtros: `status`, `health`, `program_id`, `priority`, `nist_function`, `q` (ILIKE title/description). Orden: health at_risk primero, luego target_date asc. |
| POST | `/` | analyst | Crea. `source="manual"`. |
| GET | `/{id}` | user | `InitiativeDetailOut`. |
| PATCH | `/{id}` | analyst | `exclude_unset`. Transiciones de status: a `completed` → llamar `verify_initiative` (Sprint 2; en Sprint 1 dejar TODO) y sellar `completed_at`. |
| DELETE | `/{id}` | admin | Cascade borra satelites; poner `initiative_id=NULL` en sus TreatmentTask (no borrarlas). |
| POST | `/{id}/objectives` | analyst | Crea OKR. |
| PATCH | `/{id}/objectives/{oid}` | analyst | Editar/progreso/confianza/estado. |
| DELETE | `/{id}/objectives/{oid}` | analyst | Borra. |
| POST | `/{id}/control-targets` | analyst | Body `ControlTargetIn`. Sella `baseline_maturity = impl.maturity`. 409 si duplicado. **Dispara auto_link + proyeccion (Sprint 2; en Sprint 1 solo crea).** |
| DELETE | `/{id}/control-targets/{tid}` | analyst | Borra target. **Re-deriva links auto y proyeccion (Sprint 2).** |
| POST | `/{id}/risks` | analyst | Vinculo MANUAL (origin="manual"). Sella baseline. 409 duplicado, 404 si el riesgo no es de la org. |
| DELETE | `/{id}/risks/{risk_id}` | analyst | Solo permite quitar links `origin != "auto"` (los auto desaparecen solos al quitar el control target; 409 con mensaje si se intenta). |
| POST | `/{id}/log` | analyst | Entrada de bitacora humana (`LogEntryIn`). |
| GET | `/stats` | user | Ver 1.5. |

Toda mutacion: `log_action`. Toda query: `filter_by_org`.

### 1.4 Progreso derivado (cero mantenimiento manual)

`initiative.progress` se recalcula en un helper `refresh_initiative_progress(db, initiative)`:

- Si tiene OKRs: media de `objective.progress` de OKRs no cancelados.
- Si no tiene OKRs pero tiene tareas: `done/total*100`.
- Si no tiene nada: se mantiene el valor actual (editable solo via PATCH de OKRs/tareas, no directo).

Llamarlo al mutar OKRs y, en `app/routers/tasks.py`, anadir al final de `update_task` y
`create_task` (tras `_update_risk_treatment_progress`) un
`_update_initiative_progress(db, task)` que localice la iniciativa y llame al helper.
Anadir tambien `initiative_id` opcional a `TaskIn` y al create.

### 1.5 `GET /api/initiatives/stats`

```json
{
  "programs": 5, "initiatives_total": 23,
  "by_status": {"draft": 3, "in_progress": 12, "...": 0},
  "by_health": {"ok": 18, "at_risk": 4, "blocked": 1},
  "avg_progress": 43,
  "budget": {"requested": 250000, "approved": 180000},
  "risks_covered": 31,
  "high_risks_uncovered": [{"id": 4, "code": "RSK-0004", "residual_level": 6,
                             "asset_name": "ERP", "threat_name": "Ransomware"}],
  "reduction": {"projected_points": 24, "achieved_points": 9}
}
```

- `risks_covered`: riesgos distintos con link a iniciativa en estado approved/in_progress.
- `high_risks_uncovered`: `residual_level > risk_appetite` (RiskContext org; default 3)
  sin link a iniciativa activa. Max 20, orden residual desc.
- `reduction.projected_points`: suma `(baseline - projected)` de links de iniciativas activas.
- `reduction.achieved_points`: suma `max(0, baseline - residual_actual_vivo)` de esos links.

### 1.6 Feature flag

En `PLAN_MODULE_LIMITS` (`app/routers/feature_flags.py`): modulo `"plan_director"` en
planes `pro` y `enterprise`. El cockpit de tratamiento NO lleva flag (core de riesgos).

### 1.7 Tests (`tests/test_initiatives.py`)

Copiar fixtures de un test existente con client autenticado y 2 orgs. Casos:

1. CRUD programa e iniciativa; `derived_status` del programa (2 iniciativas: una
   in_progress + una completed → programa in_progress).
2. OKRs: crear 2, progreso 50 y 100 → `initiative.progress == 75`.
3. Control target: sella `baseline_maturity`; duplicado → 409.
4. Link manual de riesgo: sella baseline; riesgo de otra org → 404; quitar link auto → 409.
5. Tarea con `initiative_id`: al completarla se actualiza el progreso (sin OKRs).
6. `stats`: cubierto/no cubierto correcto. Aislamiento entre orgs.
7. Campos de sistema (`health`, `verification`) no editables via POST/PATCH.

---

## Sprint 2 — Motor determinista: proyeccion what-if, auto-link, verificacion, burndown

Todo en un servicio nuevo `app/services/initiative_projection_service.py`. CERO llamadas
IA aqui: es matematica del motor existente.

### 2.1 Refactor previo minimo en `risk_recalc_service.py` (sin cambiar comportamiento)

Extraer de `recalc_risk` (lineas ~142-168) una funcion pura reutilizable:

```python
def residual_from_payloads(db, risk, controls: list[dict], matrix) -> tuple[int, int, int]:
    """Aplica calc_residual + floor de controles obligatorios. NO escribe en el riesgo."""
```

`recalc_risk` la llama (mismo resultado que hoy — los tests existentes lo garantizan;
ejecutar la suite completa tras el refactor). El floor de obligatorios necesita saber
que impls tienen `is_mandatory` y madurez < 2: pasar esa condicion evaluada sobre la
MISMA lista de payloads — anadir a `control_payload` las claves `is_mandatory` y
`maturity_raw` si no estan ya en el dict (mirar que claves construye hoy y NO renombrar
ninguna existente; el motor las consume por nombre).

### 2.2 `project_initiative(db, initiative) -> dict`

Para cada riesgo en `initiative.risk_links`:

1. Reconstruir los payloads de controles EXACTAMENTE como `recalc_risk` (misma query de
   `contribution`, mismo `control_payload`).
2. Para cada impl que este en `initiative.control_targets`: sobrescribir en su payload
   la madurez efectiva con `max(madurez_actual_del_payload, target_maturity)` (una
   iniciativa nunca empeora un control) y recalcular las claves derivadas de madurez
   que use el payload (mirar `control_payload` — la eficacia se deriva de la madurez;
   replicar esa derivacion con el valor objetivo).
3. `residual_from_payloads(...)` → nivel proyectado.
4. Guardar en el link: `projected_residual_level`, `projected_at = now`.

Devuelve resumen `{"risks": [{"risk_id":.., "baseline":.., "current":.., "projected":..}],
"projected_reduction_points": N}`.

**Triggers de reproyeccion** (llamar `project_initiative` y commit):
- POST/DELETE de control-targets y de risk links (Sprint 1 los dejo con TODO).
- Endpoint manual `POST /api/initiatives/{id}/reproject` (analyst).
- Cuando `recalc_risks_for_impls` recalcula riesgos: anadir al final una llamada
  `reproject_for_impls(db, impl_ids)` (nueva, en el servicio de proyeccion) que
  reproyecte las iniciativas activas con targets sobre esos impls. Asi la proyeccion
  nunca queda obsoleta cuando el mundo real cambia. Proteger contra recursion (la
  proyeccion no dispara recalculo real).

### 2.3 `auto_link_risks(db, initiative) -> int`

Deriva que riesgos afecta la iniciativa a partir de sus control targets. Determinista:

1. **Directos**: riesgos (org, status != closed) vinculados en `risk_controls` a
   cualquier `implementation_id` de los targets.
2. **Por catalogo**: para cada riesgo abierto de la org, si su amenaza tiene entre sus
   controles candidatos (via `threat_knowledge` — mirar la funcion publica que devuelve
   candidatos por amenaza, respetando overrides de org) alguno de los codigos ISO de
   los controles objetivo → candidato. Solo si el residual actual > apetito (no llenar
   de links riesgos ya verdes).

Crear links `origin="auto"` (sellando baseline) para los que no existan; ELIMINAR los
links `origin="auto"` que ya no se deriven de ningun target (los manual/ai_import no se
tocan). Llamar siempre antes de `project_initiative` en los triggers de 2.2.

### 2.4 `verify_initiative(db, initiative) -> dict`

Al pasar a `completed` (y via `POST /api/initiatives/{id}/verify` para re-ejecutar):

1. Por control target: sellar `achieved_maturity = impl.maturity` actual;
   `met = achieved >= target`.
2. Por risk link: sellar `achieved_residual_level = risk.residual_level` actual;
   `met = achieved <= projected`.
3. Componer y guardar en `initiative.verification`:

```json
{"verified_at": "...", "controls": {"total": 4, "met": 3},
 "risks": {"total": 6, "met": 4},
 "gaps": [{"type": "control", "code": "A.8.7", "target": 3, "achieved": 2},
          {"type": "risk", "code": "RSK-0012", "projected": 3, "achieved": 5}]}
```

4. Crear `InitiativeLogEntry` tipo `system` con el resumen ("Verificacion: 3/4 controles
   en madurez objetivo; 4/6 riesgos en o por debajo del residual proyectado").
5. NUNCA modificar madurez ni residual: solo leer y sellar.

### 2.5 `GET /api/initiatives/burndown`

Board-level: historico real + curva objetivo.

```json
{"history":  [{"month": "2026-01", "total_residual": 84, "above_appetite": 12}],
 "projected": [{"month": "2026-08", "total_residual": 71}],
 "appetite_line": 3}
```

- `history`: agregado mensual desde `RiskSnapshot` (org, ultimos 18 meses): suma de
  `residual_level` y nº de riesgos sobre apetito. Agrupar por mes EN PYTHON tras traer
  las filas (portabilidad PG; no usar funciones de fecha SQL).
- `projected`: partir del total actual; para cada mes futuro hasta el mayor
  `target_date` de iniciativas activas (cap 18 meses), restar la
  `projected_reduction_points` de las iniciativas cuyo target_date cae ese mes.
  Si dos iniciativas comparten un riesgo, la reduccion combinada sobre ese riesgo se
  capa a `baseline - min(projected de ambas)` (no restar dos veces; calcular por riesgo,
  no por iniciativa).

### 2.6 Tests (`tests/test_initiative_projection.py`)

1. Refactor: la suite existente completa pasa sin cambios (`pytest tests/ -q`).
2. Proyeccion: riesgo con 1 control madurez 1; target madurez 4 → projected < current.
   Riesgo sin relacion → sin cambio. Target con madurez menor a la actual → no empeora.
3. Floor de obligatorios: control obligatorio con target < 2 → el proyectado respeta el
   floor igual que el recalculo real.
4. auto_link: crea links auto por via directa y por catalogo; al borrar el target los
   auto desaparecen y los manuales quedan.
5. Reproyeccion via `recalc_risks_for_impls`: cambiar madurez real de un impl con
   target → el link tiene `projected_at` actualizado.
6. verify: gaps correctos con un control cumplido y otro no.
7. burndown: 3 snapshots sinteticos + 1 iniciativa activa → history y projected coherentes;
   dos iniciativas sobre el mismo riesgo no duplican reduccion.

---

## Sprint 3 — Cockpit de Tratamiento

### 3.1 `GET /api/risks/treatment-board` (en `app/routers/risks.py`, antes de `/{risk_id}`)

Un unico endpoint agregado. Respuesta:

```json
{
  "appetite": 3,
  "kpis": {"total_risks": 120, "above_appetite": 22, "above_appetite_no_plan": 7,
            "above_appetite_no_coverage": 5, "overdue_plans": 4, "avg_progress": 58,
            "pending_acceptance": 3, "tasks_overdue": 9},
  "burndown": { "...": "misma shape que /api/initiatives/burndown, reutilizar la funcion" },
  "columns": {"modification": [], "sharing": [], "avoidance": [], "retention": [],
               "untreated": []}
}
```

Item por riesgo (status != closed; en `untreated` solo `residual > appetite` sin opcion):

```json
{"id": 12, "code": "RSK-0012", "asset_name": "ERP", "threat_name": "Ransomware",
 "residual_level": 6, "target_residual_level": 3, "inherent_level": 7,
 "status": "assessed", "owner_name": "Ana", "treatment_progress": 40,
 "treatment_due_date": "2026-09-01", "overdue": false,
 "treatment_plan_excerpt": "160 chars...",
 "tasks": {"total": 5, "done": 2, "overdue": 1},
 "initiatives": [{"id": 3, "code": "INI-0003", "title": "Segmentacion", "health": "ok",
                   "projected_residual_level": 3}],
 "analysis_stale": false, "acceptance": {"pending": false}}
```

Eficiencia: `joinedload` de asset/threat; tareas con UN `GROUP BY risk_id`; links de
iniciativas activas con un query. `above_appetite_no_coverage` = sobre apetito sin
iniciativa activa NI plan de tratamiento. Orden en columna: overdue primero, residual desc.

### 3.2 Acciones (reutilizar endpoints existentes)

Cambiar opcion/plan/fechas → `PATCH /api/risks/{id}`. Tareas → `POST/PATCH /api/tasks`.
Nada nuevo salvo el board.

### 3.3 Vista `app/static/js/views/treatment.js`

Patron `const ViewTreatment = { async render(el) {...} }` (referencia de estilo:
`tasks.js`; llamadas via `api.get/post/patch`; colores de nivel:
`var(--risk-critical|high|medium|low)`). De arriba a abajo:

1. **6 KPI cards** clicables (aplican filtro): Sobre apetito / Sin plan / **Sin
   cobertura** (sin iniciativa ni plan — el hueco de gobierno) / Vencidos / Progreso
   medio (barra) / Pendientes de aceptacion.
2. **Mini burndown**: SVG inline simple (polyline history en purple solido + projected
   en dashed orange; eje Y = suma residual). Sin librerias. ~700x160.
3. **Filtros**: opcion, owner, "solo vencidos", buscador cliente.
4. **Tablero por opcion**: 5 secciones colapsables — "Sin tratar" PRIMERA con borde
   rojo. Tabla: Codigo | Activo/Amenaza | Residual → Objetivo (badges; si hay
   iniciativa con proyeccion, mostrar tambien "→ P:3" con tooltip "proyectado por
   INI-0003") | Progreso | Vence | Tareas 2/5 | Iniciativas (chips con color de health)
   | Owner | Acciones.
5. **Fila expandible**: plan (excerpt), tareas, botones "Nueva tarea" (modal →
   POST /api/tasks), "Editar tratamiento" (modal → PATCH risk), "Generar plan con IA"
   (Sprint 5; ocultar hasta entonces), "Abrir riesgo" (`#/risk-hub/risks`).
6. Badge "DESACT." si `analysis_stale` (mismo patron que risks.js).

### 3.4 Registro

- `hubs.js` → `ViewRiskHub.tabs` tras `risks`:
  `{ id: 'treatment', label: t('hub.risk.treatment'), view: ViewTreatment, route: 'treatment' }`.
- `index.html`: `<script src="/js/views/treatment.js?v=1.0.0"></script>`.
- `app.js` LegacyRedirects: `treatment: 'risk-hub/treatment'`.
- i18n: prefijo `treatment.` en `es.js` y `en.js`. `guide.js`: seccion nueva.

### 3.5 Tests (`tests/test_treatment_board.py`)

1. Board vacio → kpis 0. 2. Riesgo alto sin opcion → `untreated` +
`above_appetite_no_plan`. 3. Con opcion y 2 tareas (1 done) → progreso/tasks. 4. Vencido
→ overdue + kpi. 5. Con iniciativa activa → chip + `above_appetite_no_coverage` no lo
cuenta. 6. burndown presente.

---

## Sprint 4 — Vista Plan Director

### 4.1 `app/static/js/views/plan-director.js`

Gating: si el plan de la org no incluye `plan_director` (mirar como otras vistas
comprueban feature flags y copiar el patron), render de placeholder "Disponible en plan
Pro". Estructura — segmented control con 3 secciones:

**A) Resumen** (de `/stats` + `/burndown`):
- Cards: iniciativas activas, at-risk (rojo), progreso medio, presupuesto
  solicitado/aprobado, reduccion proyectada vs conseguida (barra doble).
- Burndown grande (mismo SVG que el cockpit, mas alto).
- Panel "Riesgos sobre apetito sin cobertura" con boton por fila "Generar borrador de
  iniciativa" (Sprint 5; hasta entonces "Vincular a iniciativa..." con selector).

**B) Plan** (el corazon):
- Arbol Programa → Iniciativas: cabecera de programa (nombre, area, responsable, estado
  derivado, presupuesto, barra de progreso media) colapsable; dentro, filas de
  iniciativa: Codigo | Titulo | NIST (badge) | Estado | Salud (punto verde/ambar/rojo
  con tooltip de `health_reasons`) | Prioridad | Progreso | Riesgos (nº + reduccion
  proyectada "-5 pts") | OKRs (n/m completados) | Target date (rojo si vencida) | Owner.
- Toggle "Tabla / Cronograma". Cronograma = Gantt CSS puro: grid con una columna por
  mes (18 meses desde hoy-3), una fila por iniciativa, barra `start_date → target_date`
  coloreada por health, linea vertical "hoy". Sin librerias.
- Botones: "Nuevo programa", "Nueva iniciativa" (wizard), "Importar plan" (Sprint 5).

**Wizard nueva iniciativa** (3 pasos, todo lo tedioso automatizado):
1. Datos: titulo, descripcion, programa (select + crear inline), prioridad, owner,
   fechas, presupuesto, NIST (select), narrativa.
2. **Controles objetivo**: buscador sobre los 93 controles de la org
   (`GET /api/controls` o el endpoint existente de implementaciones — localizarlo);
   por control elegido, mostrar madurez actual y selector de objetivo (default
   actual+2, cap 5).
3. **Revision automatica**: al entrar, el wizard llama a crear la iniciativa + targets
   y muestra el resultado de auto_link + proyeccion: "Esta iniciativa afecta a 7
   riesgos; reduccion proyectada 9 puntos" con la lista (riesgo, actual → proyectado).
   El usuario puede quitar/anadir riesgos manualmente. Boton "Aprobar" (status →
   approved) o "Dejar en borrador".

**C) Detalle de iniciativa** (drawer al clicar una fila; `GET /{id}`):
- Cabecera: titulo, badges (estado, salud + razones, NIST, prioridad), progreso,
  fechas, presupuesto, owner. Boton "Editar", menu de transicion de estado
  (completar dispara verificacion y muestra el resultado en un modal).
- Bloque **Controles objetivo**: tabla codigo | nombre | baseline → actual (en vivo) →
  objetivo, con barra. Anadir/quitar (dispara reproyeccion; refrescar).
- Bloque **Riesgos afectados**: tabla riesgo | baseline | proyectado | actual | delta
  (verde si actual <= proyectado) | origen (chip "auto"/"manual"/"IA"). Los auto no se
  pueden quitar (tooltip explica que dependen de los controles objetivo).
- Bloque **OKRs**: definicion, owner, target date, confianza (select), slider de
  progreso (PATCH directo), estado. "Nuevo OKR".
- Bloque **Tareas**: las de `initiative_id` + "Nueva tarea".
- Bloque **Bitacora**: timeline desc con icono por tipo (system = gris, ai_summary =
  purple, humanas = por tipo); composer con select de tipo (logro / riesgo / proximo
  paso / comentario). Si `verification` existe: panel "Verificacion de cierre" con los gaps.
- Si `ai_generated`: banner "Generada con IA" + rationale colapsable.

### 4.2 Registro

- Pestana en `ViewRiskHub` tras `treatment`:
  `{ id: 'plan-director', label: t('hub.risk.plan_director'), view: ViewPlanDirector, route: 'plan-director' }`.
- `index.html`, LegacyRedirects (`'plan-director': 'risk-hub/plan-director'`), i18n
  (prefijo `plandirector.`), `guide.js`.

### 4.3 Tests

Backend ya cubierto. Anadir en `tests/test_initiatives.py`: transicion a completed via
PATCH ejecuta verify y persiste `verification`.

---

## Sprint 5 — IA: import, borradores automaticos, narrativas, plan por riesgo

Reglas IA: `structured_message` siempre (JSON validado); modelos via `model_registry`;
`call_type` descriptivo (queda en `ai_call_logs` para refacturacion); mirar
`app/routers/ai.py:1168` como ejemplo de invocacion real. Tests SIEMPRE con
`structured_message` mockeado.

### 5.1 Servicio `app/services/initiative_ai_service.py`

**a) `parse_plan_document(db, org_id, text, lang) -> dict`** — import de plan completo.

Contexto que se le pasa: catalogo de controles de la org (code + nombre, los 93) y
lista compacta de riesgos abiertos (cap 300, mayores residuales primero:
`[{"code","asset","threat","residual"}]`).

Prompt (system, castellano): "Eres un analista GRC. Extrae del documento la estructura
del plan director: programas, iniciativas y objetivos (OKRs). Para cada iniciativa,
identifica que controles ISO 27002 del catalogo adjunto mejora (SOLO codigos del
catalogo) y estima la madurez objetivo 0-5. No inventes datos que no esten en el
documento; deja null lo desconocido."

Tier `deep`, `call_type="plan_import"`. Schema (programs max 15, initiatives max 60,
objectives max 10 por iniciativa):

```json
{"programs": [{"name": "str", "area": "str|null", "responsible_hint": "str|null",
   "initiatives": [{
     "title": "str", "description": "str|null",
     "priority": "low|medium|high|critical|null",
     "nist_function": "govern|identify|protect|detect|respond|recover|null",
     "start_date": "YYYY-MM-DD|null", "target_date": "YYYY-MM-DD|null",
     "budget": 0, "expected_risk_reduction": "str|null",
     "control_targets": [{"control_code": "A.8.7", "target_maturity": 3}],
     "objectives": [{"definition": "str", "target_date": "YYYY-MM-DD|null",
                      "owner_hint": "str|null"}]}]}]}
```

Post-proceso DETERMINISTA: descartar control_codes fuera del catalogo; clamp madurez
0-5; truncar strings; fechas con try/except → None. Si el texto > ~100k chars,
trocearlo por secciones y fusionar resultados (concatenar programs).

**Nota clave**: el import NO pide a la IA que vincule riesgos. Los riesgos se derivan
despues con `auto_link_risks` (determinista) a partir de los control targets. La IA
solo estructura el documento.

**b) `draft_initiative_for_risks(db, org_id, risks, lang) -> dict`** — borrador inverso.

Entrada: grupo de riesgos sin cobertura + sus controles candidatos (de
`threat_knowledge`, con madurez actual de cada impl). Salida: UNA iniciativa propuesta
(mismo shape que una del import, con control_targets elegidos entre los candidatos +
rationale). Tier `deep`, `call_type="initiative_draft"`.

**c) `draft_treatment_plan(db, risk, lang) -> dict`** — plan por riesgo para el cockpit.

Contexto: riesgo (activo, amenaza, niveles, apetito) + controles vinculados con madurez
+ candidatos del threat_control_map no implementados. Salida:
`{"treatment_option": "...", "plan": "5-10 lineas", "tasks": [{"title","priority","weeks_offset"}],
"rationale": "..."}`. Tier `deep`, `call_type="treatment_plan_draft"`. Es un borrador:
no persiste nada.

**d) `monthly_initiative_summary(db, initiative, lang) -> str`** — narrativa de avance.

Entrada: actividad de los ultimos 30 dias (log entries, tareas completadas/vencidas,
progreso OKRs, delta de residual real de sus riesgos). Salida: 3-6 lineas de status
ejecutivo. Tier `fast`, `call_type="initiative_summary"`. La usa el job del Sprint 6.

### 5.2 Endpoints

En `app/routers/initiatives.py`:

- `POST /import` (analyst, multipart `file`): pdf/docx/xlsx/txt/md, max 10 MB, validar
  magic bytes copiando el patron del upload de documentos existente
  (`routers/documents.py` o `ai.py`); `extract_text`; < 100 chars → 422;
  `parse_plan_document`; **devolver preview SIN persistir**.
- `POST /import/confirm` (analyst): body = preview editado. Re-validar con Pydantic
  (nunca confiar en el cliente). Crear programas (reusar por nombre exacto si ya
  existen), iniciativas (`source="import"`, `ai_generated=True`), targets
  (resolver `control_code` → `implementation_id` de la org; si un codigo no tiene
  implementacion en la org, saltarlo y anotarlo en la respuesta), OKRs. Para cada
  iniciativa: `auto_link_risks` + `project_initiative`. Devolver resumen
  `{created: {programs, initiatives, objectives}, skipped_controls: [...], total_projected_points: N}`.
- `POST /draft-for-risk` (analyst, body `{risk_ids: [..]}`): `draft_initiative_for_risks`
  → devuelve el borrador SIN persistir; la UI lo muestra en el wizard precargado
  (crear al confirmar con `source="ai_draft"`, `ai_generated=True`).

En `app/routers/risks.py`:

- `POST /api/risks/{id}/ai-treatment-plan` (analyst): devuelve borrador de
  `draft_treatment_plan`. El boton del cockpit abre modal editable; "Aplicar" hace
  PATCH del riesgo + POST de las tareas marcadas.

### 5.3 Trazabilidad y aprendizaje

- Aceptar borrador IA (confirm de import o de draft) → `ai_learning_service.record_signal`
  con `signal_type="initiative_draft_accepted"`; descartar → boton "Descartar" en la UI
  que llama `POST /discard-draft` (solo registra `initiative_draft_rejected` con el
  payload minimo). Mirar la firma real de `record_signal`
  (`app/services/ai_learning_service.py:35`) y copiar como la llaman los hooks de risks.
- Todo elemento IA muestra badge "IA" con tooltip del rationale.

### 5.4 UI

- **Import** (en Plan Director → Plan): modal de 3 pasos — upload (patron
  FormData+token de `ai-documents.js`), spinner "Analizando..." (30-90 s), preview
  editable en arbol (checkbox por programa/iniciativa/OKR, inputs de fechas/madurez,
  badge de control descartado si no esta en catalogo), boton "Crear N elementos" →
  confirm → toast con reduccion proyectada total.
- **Borrador inverso** (en Resumen): boton por riesgo sin cobertura (o seleccion
  multiple) "Generar borrador" → llama draft-for-risk → abre el wizard del Sprint 4
  precargado con el borrador (incluidos control targets); paso 3 muestra la proyeccion
  real calculada.

### 5.5 Tests (`tests/test_initiative_ai.py`, mock de `structured_message`)

1. parse: codigo de control inexistente → descartado; fechas invalidas → None.
2. `/import` preview no persiste nada; `/import/confirm` crea jerarquia + auto-links +
   proyeccion; control sin implementacion en la org → en `skipped_controls`.
3. Programa existente por nombre → se reutiliza, no se duplica.
4. draft-for-risk → shape correcto; confirm crea con `source="ai_draft"` y señal registrada.
5. ai-treatment-plan → borrador sin persistencia.

---

## Sprint 6 — Automatizaciones (el modulo trabaja solo)

Todo en `app/services/scheduler.py` siguiendo el patron de los jobs existentes
(mirar como se registran en startup y como iteran por organizacion).

### 6.1 Health check de iniciativas (semanal, lunes 7:00 UTC)

`refresh_initiative_health(db)` en el servicio de proyeccion (para poder testearlo).
Por iniciativa activa (approved/in_progress), evaluar reglas EXPLICABLES:

- `target_date` < hoy y status != completed → "Fecha objetivo vencida".
- Sin ninguna actividad en 30 dias (ni log entry humana, ni tarea tocada, ni OKR
  actualizado — usar updated_at) → "Sin actividad en 30 dias".
- >30% de sus tareas vencidas → "Tareas vencidas".
- Algun OKR con `confidence="low"` y target_date a < 60 dias → "OKR en riesgo".
- Progreso < 20% con mas del 60% del plazo consumido (start→target) → "Progreso insuficiente".

0 razones → `health="ok"`; 1 → `at_risk`; >=2 → `blocked`. Guardar `health_reasons`.
Si la salud EMPEORA: crear log entry `system` + alerta por
`notification_channels.dispatch_alert` al owner/org (si `has_any_channel`; mirar la
firma y como la usa `_run_alert_rules`).

### 6.2 Bitacora automatica (hooks, no job)

Crear helper `log_system_event(db, initiative_id, text)` y llamarlo desde:
- verify_initiative (ya en Sprint 2).
- Cambios de estado de la iniciativa (PATCH).
- `reproject_for_impls`: si el residual real de un riesgo vinculado ALCANZO el
  proyectado → "RSK-0012 alcanzo el residual proyectado (3)".
- Tarea de la iniciativa completada (en el hook de tasks.py).

Los empleados no redactan actas de avance: el sistema las va escribiendo.

### 6.3 Narrativa mensual IA (dia 1, 6:00 UTC)

Por org con API key configurada y por iniciativa activa con actividad en 30 dias:
`monthly_initiative_summary` → log entry `ai_summary`. Cap 20 iniciativas/org/mes.
Degradacion graceful si la IA falla (try/except + log, seguir con la siguiente).

### 6.4 Digest al comite (reutiliza `send_pending_digests` si encaja, si no job propio mensual)

Mensaje breve por org via `dispatch_alert`: iniciativas at-risk/blocked con razones,
reduccion proyectada vs conseguida del mes, riesgos sobre apetito sin cobertura (nº).
Nunca enviar si no hay nada que decir.

### 6.5 Tests (`tests/test_initiative_health.py`)

1. Cada regla de salud por separado (5 casos) + combinacion → blocked.
2. Salud empeora → log entry system creado. Mejora → sin alerta.
3. Narrativa mensual: mock de IA; iniciativa sin actividad → no se llama.
4. Digest: org sin nada at-risk y sin descubiertos → no envia.

---

## Sprint 7 — Informe de comite, integraciones y cierre

### 7.1 Informe PDF "Plan director y tratamiento" (ISO 27005 9 / ISO 27001 6.1.3e)

`GET /api/reports/treatment-plan` en `app/routers/reports.py`. Copiar el mecanismo
completo del informe TPRM (`GET /api/reports/tprm`, su servicio y su locale
`reports_tprm.json` → crear `reports_treatment.json`). ReportLab, paleta purple/orange.
Secciones:

1. Portada + resumen ejecutivo (KPIs del board + reduccion proyectada vs conseguida).
2. Burndown como grafica (reportlab `Drawing`/`LinePlot` o dibujo manual con `Line`).
3. Plan director: tabla por programa → iniciativas (estado, salud con razones,
   progreso, presupuesto, target, riesgos y puntos proyectados).
4. Riesgos sobre apetito: opcion, plan (excerpt), progreso, vencimiento, cobertura.
5. Verificaciones de cierre del periodo (gaps incluidos — transparencia total).
6. Riesgos aceptados con justificacion y fecha de revision.
7. Tareas vencidas (top 20).

Boton en Informes (`reports.js`, copiar la card del informe TPRM). Test
`tests/test_reports_treatment.py` (status 200, content-type pdf, con datos y sin datos).

### 7.2 Integraciones menores

- `risks.js`: en el detalle del riesgo, chips de iniciativas vinculadas (link a
  `#/risk-hub/plan-director`).
- `dashboard.js`: enlace "Ver tratamiento" hacia `#/risk-hub/treatment` (solo un link).
- Los tipos de alerta `treatment_overdue`/`risk_no_treatment` ya existen
  (`app/models.py:747`) — no duplicar.

### 7.3 Checklist de cierre (verificar TODO)

- [ ] `pytest tests/ -q` COMPLETO en verde (incluida la suite previa al refactor 2.1).
- [ ] `ruff check .` limpio.
- [ ] Arranque con BD existente (migraciones seed OK) y con BD vacia.
- [ ] i18n: todas las claves en `es.js` Y `en.js`; cero cadenas hardcodeadas.
- [ ] `guide.js` documenta Tratamiento y Plan Director.
- [ ] Sin emojis; sin CDNs ni librerias nuevas; SVG/CSS puro para burndown y Gantt.
- [ ] `filter_by_org` en todos los endpoints; aislamiento probado con 2 orgs.
- [ ] Ningun codigo del modulo escribe `residual_level`, `maturity` ni campos del motor.
- [ ] `health`, `progress`, `verification`, `projected_*` no son editables via API.
- [ ] Actualizar CLAUDE.md: entrada en "Estado actual".

---

## Backlog de mejoras (post-v1, priorizado — 2026-07-16)

Los 7 sprints estan implementados y revisados. Estas son las ampliaciones
identificadas, en orden de valor. Requisito previo antes de construirlas:
validar los flujos IA contra la API real y usar el modulo con datos reales
unas semanas — el uso real reordenara esta lista.

### Alto valor / bajo esfuerzo
1. **ROI por iniciativa**: `budget / projected_reduction_points` = coste por punto
   de riesgo reducido + ranking de eficiencia de cartera. Con `Asset.monetary_value`
   (campo FAIR existente): euros en riesgo cubiertos por iniciativa. Datos ya existen.
2. **Controles nuevos (no solo mejoras)**: hoy `InitiativeControlTarget` exige una
   `ControlImplementation` existente. Permitir target sobre `Control` del catalogo
   sin implementacion, creando la impl al completar la iniciativa. Gap funcional real.
3. **Auto-tareas desde control targets**: boton "generar una tarea por control
   objetivo" — puente entre lo estrategico y el kanban operativo.
4. **Incidente → bitacora de iniciativa**: si un incidente golpea un riesgo cubierto
   por una iniciativa activa, log automatico `system` + penalizacion de salud.

### Diferenciadores / esfuerzo medio
5. **Simulador de cartera**: el motor de proyeccion es puro — optimizacion tipo
   mochila: "con presupuesto X, que combinacion de iniciativas minimiza el residual".
6. **Dependencias entre iniciativas** (`blocked_by`) + camino critico en el Gantt +
   salud heredada (si A bloquea a B y A esta blocked, B lo hereda).
7. **Aprobacion formal de comite**: reutilizar el flujo de firma de `policy_approvals`
   para que "approved" requiera firma de direccion (ISO 27001 6.1.3e auditable).
8. **Historico de proyecciones**: snapshots de `projected_residual_level` por link
   (hoy cada reproyeccion sobreescribe) — trazabilidad de como cambio la promesa.

### Secundarias
9. Radar de cobertura NIST CSF de la cartera (campo `nist_function` apenas explotado).
10. Gasto real vs presupuesto aprobado (campo `spent` + burn presupuestario).
11. Reduccion proyectada como KRI en el modulo de KRIs (umbrales + alertas).

## Resumen de ficheros

| Accion | Fichero |
|---|---|
| Modificar | `app/models.py` (6 modelos + 1 columna), `app/schemas.py`, `app/seed.py` (1 ALTER), `app/main.py`, `app/routers/tasks.py` (initiative_id + hooks), `app/routers/risks.py` (treatment-board + ai-treatment-plan), `app/routers/reports.py`, `app/routers/feature_flags.py`, `app/services/risk_recalc_service.py` (refactor 2.1 + hook reproyeccion), `app/services/scheduler.py` (3 automatizaciones) |
| Crear | `app/routers/initiatives.py`, `app/services/initiative_projection_service.py`, `app/services/initiative_ai_service.py`, `app/static/js/views/treatment.js`, `app/static/js/views/plan-director.js` |
| Modificar (frontend) | `hubs.js`, `app.js`, `index.html`, `i18n/es.js`, `i18n/en.js`, `guide.js`, `reports.js`, `dashboard.js`, `risks.js` |
| Crear (tests) | `tests/test_initiatives.py`, `tests/test_initiative_projection.py`, `tests/test_treatment_board.py`, `tests/test_initiative_ai.py`, `tests/test_initiative_health.py`, `tests/test_reports_treatment.py` |
