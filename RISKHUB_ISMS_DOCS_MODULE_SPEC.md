# RiskHub — Modulo de Gestion Documental ISMS

Spec de reconstruccion del modulo de documentacion del SGSI sobre un motor de
ingesta agentica compartido por toda la plataforma.

- Version del spec: 1.1
- Fecha: 2026-07-23
- Estado: en ejecucion — F0, F2, F3 y F4 implementados y con tests; F5-F7 pendientes

## Estado de implementacion (2026-07-23)

| Fase | Descripcion | Estado |
|------|-------------|--------|
| F0 | Desbloqueo: borrado con limpieza referencial, `/bulk`, seleccion multiple, error visible | **Hecho** (backend + frontend, verificado en navegador) |
| F2 | Eje `doc_class` (normativa/evidencia/referencia), clasificador sobre `structured_message` | **Hecho** (backend + badge/filtro frontend) |
| F3 | Cadena documento->Evidence->control->madurez->riesgo reconectada | **Hecho** (Evidence enganchada a impl+doc, recalc disparado) |
| F4 | Autoridad de cumplimiento: fin de la heuristica por desplegable, evidencia verificada | **Hecho parcial** (heuristica eliminada, content-gate; falta panel de procedencia en UI) |
| F5 | Reconciliacion SharePoint al tocar carpetas permitidas | **Pendiente** — bloqueado: requiere editar `routers/sharepoint.py`, que tiene trabajo sin commitear de otra sesion |
| F6 | Gestion documental completa: vista arbol, dedup SHA-256, caducidad | **Pendiente** |
| F7 | BCP sobre el motor de ingesta compartido | **Pendiente** |

Nota F3/F4: el motor de riesgo determinista no se toco; el trabajo consistio en
alimentarlo con evidencia real (con `control_implementation_id`, `source_document_id`,
`auto_generated` y calidad `ai_review` E1-E5) en lugar de fichas vacias. Falta,
como continuacion de F3, ejecutar `evidence_understanding_service` sobre la
evidencia auto-generada en el pipeline de ingesta (hoy queda lista para analizar
pero el analisis de contenido de esa evidencia es un paso posterior).

---

## 1. Proposito y principio rector

RiskHub es **antes que nada una herramienta de gestion de riesgo y cumplimiento**.
TPRM, BCP, Plan Director y el resto de modulos son consumidores de ese nucleo, no
dominios independientes. La documentacion no es un archivador: es el sustrato
probatorio del que salen la madurez de los controles, el riesgo residual y el
estado de cumplimiento.

De ahi el objetivo funcional que ordena todo el modulo:

> El cliente sube documentos y se olvida. El agente entiende que es cada
> documento, lo clasifica, lo cruza con la normativa, con los controles, con los
> riesgos y con el resto de modulos, y deja constancia auditable de por que
> cada cosa quedo como quedo.

Y de ahi el principio rector, heredado del motor de riesgo (v6.0.0) y del Plan
Director (v6.3.0):

> **La IA propone entradas comprensibles y citadas; el motor determinista
> calcula el resultado; nada se escribe sin traza reversible.**

La IA nunca fija un residual, un porcentaje de cumplimiento ni una madurez de
forma directa. Aporta lecturas del contenido con confianza y cita; los motores
deterministas ya existentes (`risk_engine`, `risk_recalc_service`,
`initiative_projection_service`) hacen el calculo.

---

## 2. Diagnostico del estado actual

### 2.1 El borrado esta roto

`delete_document()` ([app/services/document_service.py:315](app/services/document_service.py#L315))
hace `db.delete(doc)` sin limpiar referencias. Hay ocho claves foraneas a
`ai_documents.id`:

| Modelo | Campo |
|---|---|
| `Policy` | `source_document_id` |
| `BCPPlan` | `document_id` |
| `Supplier` | `dpa_document_id`, `nda_document_id`, `contract_document_id` |
| `StrategicInitiative` | `source_document_id` |
| `AiDocumentChunk` | `document_id` (si se limpia) |
| `IngestSourceMap` | `document_id` |

`app/database.py:34` activa `PRAGMA foreign_keys=ON`, asi que el borrado lanza
`IntegrityError` y devuelve 500. **El propio analisis ISMS crea la `Policy` que
luego bloquea el borrado de su documento**: cuanto mejor funciona el agente,
menos se puede borrar.

### 2.2 La cadena documento -> riesgo esta cortada

Esta es la rotura mas grave del modulo, porque afecta al nucleo del producto.

La cadena que **deberia** cerrarse ya existe y funciona:

```
Evidence.ai_review.quality_level (E1-E5)
  -> _ai_evidence_factor()            risk_recalc_service.py:78
  -> control_payload()                 risk_recalc_service.py:109
  -> adjusted_maturity()               risk_analysis_helpers
  -> control_reduction_split()         risk_engine.py:170
  -> calc_residual()                   risk_engine.py:187
  -> Risk.residual_level
```

Pero los documentos del SGSI **nunca entran en ella**:

1. `evidence_inference_service` crea filas `Evidence` con
   `control_implementation_id = None` y `risk_id = None`
   ([app/services/evidence_inference_service.py:162](app/services/evidence_inference_service.py#L162)).
   Solo rellena `compliance_framework` y `compliance_requirement`.
2. `_ai_evidence_factor` filtra por `Evidence.control_implementation_id == ci.id`.
   Como ese campo es nulo, **el factor de calidad E1-E5 no se aplica jamas** a
   nada que venga de un documento ISMS.
3. Esas `Evidence` se crean sin `filename`, sin `file_hash`, sin `valid_from` ni
   `expires_at`, y **sin pasar por `evidence_understanding_service`**. Son fichas
   de cartón: no hay contenido que revisar detras.
4. La madurez que llega al motor sale solo de
   `adjusted_maturity(ci.maturity, ci.evidence_refs)`, donde `evidence_refs` son
   dicts sueltos `{title, url, note, document_level, level_maturity}` escritos
   por `_update_controls` ([app/services/isms_analysis_service.py:762](app/services/isms_analysis_service.py#L762)).
   `level_maturity` es **la autodeclaracion de la IA en una sola pasada
   superficial**, sin verificacion de contenido ni caducidad.
5. Peor: esas `Evidence` huerfanas incrementan `evidence_count` del requisito, y
   `auto_update_compliance_from_controls` usa `total_evidence > 0` para saltar de
   PARTIAL 75 a **IMPLEMENTED 100**
   ([app/services/compliance_service.py:435](app/services/compliance_service.py#L435)).
   Es decir: **un documento fabrica su propia evidencia y con ella se
   autocertifica al 100 %**.

Consecuencia de negocio: la documentacion no mueve el riesgo residual por la via
correcta, la madurez es autodeclarada, y el cumplimiento sube sin que nadie haya
leido nada.

### 2.3 El cumplimiento tiene ocho escritores y ningun arbitro

| Origen | Escribe |
|---|---|
| `isms_analysis_service._update_compliance_from_doc_category:463` | PARTIAL 30 % **por la categoria del desplegable de subida** |
| `evidence_inference_service` | PARTIAL/IMPLEMENTED 40-90 % por crossmap |
| `compliance_service.auto_update_compliance_from_controls` | PARTIAL 75 / IMPLEMENTED 100 |
| `ccm_service:948` | PARTIAL 50 |
| `routers/bcp.py:1626` | NIS2 IMPLEMENTED 100 fijo |
| `routers/gdpr.py:268` | PARTIAL 60 |
| `routers/evidence.py:207` | 75 -> 100 |
| `routers/audits.py:403` | AUDITED |

Gana el ultimo que pasa. `ComplianceFrameworkStatus` **no tiene ningun campo de
procedencia**: ni `source`, ni `source_ref`, ni `rationale`. Es imposible
responder a un auditor por que un requisito esta en verde.

### 2.4 El clasificador es fragil por construccion

- `isms_analysis_service` usa el cliente `anthropic` crudo con `json.loads` sobre
  texto libre ([app/services/isms_analysis_service.py:219](app/services/isms_analysis_service.py#L219)).
  **No usa `claude_client.structured_message` ni `model_registry`**, contra lo que
  marca CLAUDE.md. Es la causa probable de los `isms_status = "error"` en
  produccion (JSON truncado o con prosa alrededor).
- Modelo hardcodeado `claude-opus-4-6` en `_get_model`.
- Una sola pasada sobre 25 chunks / 14 000 caracteres.
- Clasifica en cuatro niveles jerarquicos (Politica, Norma, Procedimiento,
  Instruccion Tecnica) que son **todos normativos**. No existe el eje "documento
  normativo frente a registro que lo evidencia". Un informe SOC 2 Type 2 o un
  certificado ISO se fuerzan a uno de los cuatro niveles y salen mal.

### 2.5 Filtrado y gestion

- `document_level` e `isms_type` viven dentro del JSON `isms_summary`, no como
  columnas: no se puede filtrar en servidor.
- `GET /api/documents/` devuelve **todo sin filtros ni paginacion**
  ([app/routers/documents.py:123](app/routers/documents.py#L123)); la vista filtra en cliente.
- `AiDocument` no guarda ruta ni carpeta de origen (solo `source_drive_id` /
  `source_item_id`): **filtrar por carpeta de SharePoint es imposible porque el
  dato no se persiste**.
- No hay endpoint masivo de nada: ni borrado, ni reanalisis, ni recategorizacion.
- La tabla se corta: `<div class="card" style="overflow:hidden">` sin
  `overflow-x:auto` ([app/static/js/views/isms-documents.js:551](app/static/js/views/isms-documents.js#L551)).

### 2.6 SharePoint no reconcilia

`set_allowed_folders` ([app/routers/sharepoint.py:323](app/routers/sharepoint.py#L323))
solo guarda la lista. `sync_organization` recorre unicamente las carpetas
**actualmente** permitidas. Retirar una carpeta deja documentos zombis:
indexados, en el RAG, contando en cumplimiento y madurez. Anadir una carpeta no
dispara nada. Los imports usan `threading.Thread` ([app/routers/sharepoint.py:497](app/routers/sharepoint.py#L497)),
que no sobrevive a un reinicio.

---

## 3. Arquitectura objetivo: motor de ingesta agentica

### 3.1 Lo que ya esta modelado y sin usar

El commit `db8c01f` introdujo cinco tablas en `models.py` que **ningun modulo
usa todavia** (`grep` solo las encuentra en `models.py`):

| Tabla | Proposito |
|---|---|
| `IngestBatch` | Lote con `status: running / awaiting_confirmation / completed / failed / undone`, coste estimado, `undone_at` |
| `IngestSourceMap` | *"El como lo entendi"*: unidades detectadas, entidades destino, `field_mapping`, `ambiguities`, `rationale`, `confidence`, `status: proposed / confirmed / executed / rejected / superseded` |
| `IngestRecordTrace` | Rastro por registro tocado con `before` / `after` y `needs_review`: permite revertir uno solo |
| `IngestFieldOverride` | Campo corregido a mano que **ninguna reingesta pisa**; alimenta `ai_learning_service` |
| `IngestConflict` | Contradiccion entre documentos sobre el mismo campo, con politica `min / max / latest / manual`; el valor descartado nunca se pierde |

`IngestBatch.module` es generico y `IngestRecordTrace.entity` referencia "la clave
del EntitySpec": el diseno ya anticipaba un registro declarativo de entidades
destino. **Este spec lo implementa y hace de ISMS Documents su primer
consumidor.** BCP sera el segundo (F6).

### 3.2 Ciclo de vida de un documento

```
  extraer -> comprender -> declarar -> [confirmar] -> volcar -> reconciliar -> aprender
```

1. **Extraer**: texto o Vision, SHA-256, deduplicacion, ruta de origen.
2. **Comprender**: triaje barato + lectura profunda troceada.
3. **Declarar** (`IngestSourceMap`): que es el documento, que unidades contiene,
   que entidades tocaria y con que confianza. **Antes de escribir nada.**
4. **Confirmar**: automatico por encima del umbral de confianza; a bandeja de
   revision por debajo. El umbral es configurable por organizacion.
5. **Volcar** (`IngestRecordTrace`): cada fila creada o modificada deja traza con
   `before` / `after`, confianza y cita de origen.
6. **Reconciliar** (`IngestConflict`): dos documentos que dicen cosas distintas
   del mismo campo se resuelven por politica declarada, no por orden de llegada.
7. **Aprender**: los `IngestFieldOverride` alimentan `ai_learning_service`, que
   ya destila lecciones por organizacion e inyecta en prompts.

### 3.3 EntitySpec: a donde puede escribir un documento

Registro declarativo, no codigo disperso. Cada spec define entidad destino,
campos escribibles, clave de deduplicacion, umbral de confianza y politica de
conflicto.

| Entidad | Que aporta un documento |
|---|---|
| `Policy` | Documento normativo con nivel, alcance, ciclo de revision |
| `ControlImplementation` | Madurez y estado, **siempre respaldados por `Evidence` real** |
| `Evidence` | Registro probatorio con archivo, hash, vigencia y calidad IA |
| `ComplianceFrameworkStatus` | Propuesta de estado, nunca escritura directa (ver seccion 5) |
| `Risk` / `RiskControl` | Vinculo evidencia-riesgo y contribucion del control |
| `TreatmentTask` | Tarea derivada de un gap documental detectado |
| `BCPPlan` | Plan de continuidad detectado |
| `Supplier` | DPA, NDA, contrato, certificaciones |
| `Asset` | Activos mencionados explicitamente |
| `StrategicInitiative` | Iniciativas del plan director |

Anadir un destino nuevo debe ser declarar un spec, no programar un caso especial.

---

## 4. La cadena documento -> evidencia -> control -> madurez -> riesgo

Este es el capitulo que cierra el modulo contra el nucleo del producto. Sin
esto, lo demas es un gestor documental bonito.

### 4.1 Regla fundamental

> **Todo aporte de madurez a un control debe estar respaldado por una fila
> `Evidence` real, con archivo, hash, vigencia y calidad de contenido evaluada.
> Se acaban los `evidence_refs` como dicts sueltos autodeclarados.**

`ControlImplementation.evidence_refs` pasa a ser cache de presentacion derivada
de las `Evidence` vinculadas, no la fuente de verdad.

### 4.2 Que cambia en la ingesta

Cuando el agente concluye que un documento cubre el control `5.17`:

1. Crea o actualiza una `Evidence` con `control_implementation_id` **relleno**,
   `filename`, `file_hash`, `valid_from`, `expires_at` segun tipo, y
   `previous_version_id` si sustituye a una anterior.
2. Lanza `evidence_understanding_service` sobre el contenido real. El resultado
   (`relevant`, `quality_level` E1-E5, `key_facts`, `controls_supported`,
   `red_flags`) se guarda en `Evidence.ai_review`.
3. A partir de ahi `_ai_evidence_factor` **si encuentra la evidencia** y el
   factor E1-E5 entra en el calculo de madurez ajustada, como estaba disenado.
4. Si `ai_review.relevant == false` o `red_flags` no esta vacio, la evidencia
   **no aporta madurez** y se genera un hallazgo en la bandeja de revision.
5. `recalc_risks_for_impls` se dispara con los `impl_id` afectados: el residual
   de los riesgos que dependen de esos controles se recalcula con el motor
   determinista de siempre. Ya existe y ya funciona; solo hay que llamarlo.

### 4.3 Evidencia vinculada al riesgo, no solo al control

`Evidence.risk_id` existe y hoy no se rellena desde documentos. Se rellena en dos
casos:

- **Directo**: el documento cita explicitamente un riesgo o un escenario.
- **Derivado**: el documento evidencia un control que esta en `risk_controls` de
  un riesgo activo. La evidencia queda visible desde la ficha del riesgo, en el
  panel "Fuentes consideradas" que ya existe en `risks.js`.

Esto responde a "la evidencia tiene que ir asociada a los riesgos y a las
medidas de mitigacion": un riesgo debe poder mostrar, sin intermediarios, que
documentos sostienen su nivel residual y de que fecha son.

### 4.4 Caducidad que degrada el riesgo

Un pentest de 2023 no evidencia nada en 2026. `Evidence.expires_at` ya existe.
Al vencer:

1. La evidencia deja de contar para la madurez ajustada.
2. El control baja de madurez efectiva sin tocar `maturity_raw` (que es la
   declaracion nominal).
3. `recalc_risks_for_impls` recalcula el residual, que sube.
4. El requisito de cumplimiento asociado se degrada con procedencia
   `evidence_expired`.
5. Se avisa por los canales configurados (`notification_channels`, ya soporta
   email / Teams / Power Automate).

Vigencias por defecto por tipo, configurables por organizacion: certificacion 12
meses, pentest 12, revision de accesos 3, acta de comite 12, registro de
formacion 12, politica segun `review_cycle_months`.

### 4.5 Gap documental como entrada al Plan Director

El campo `gap_to_5` ya se calcula documento a documento y **nunca se agrega**.
Se agrega por control y se expone como mapa de cobertura: para cada uno de los
93 controles ISO 27002, que nivel documental existe y cual falta para subir de
madurez. Ese mapa alimenta:

- `InitiativeControlTarget` del Plan Director (control + madurez objetivo).
- `TreatmentTask` para riesgos sobre apetito sin cobertura documental.

Con eso la pregunta "que me falta escribir para bajar este riesgo" tiene
respuesta calculada, no opinada.

### 4.6 Trazabilidad de extremo a extremo

Para cualquier riesgo residual la plataforma debe poder responder:

> Este riesgo esta en residual 2 porque los controles 5.17 y 8.5 tienen madurez
> ajustada 3,4 y 4,1; esa madurez viene de las evidencias EVD-0042 (Norma de
> Contrasenas, calidad E4, vigente hasta 2027-01) y EVD-0051 (revision de
> accesos Q2, calidad E3, vence en 40 dias); ambas proceden del documento X
> ingerido en el lote #17, confirmado por Fulano el 2026-07-20.

---

## 5. Cumplimiento con autoridad unica

Mismo patron que `risk_recalc_service` es la autoridad unica del residual.

1. **`compliance_status_service` es el unico escritor** de
   `ComplianceFrameworkStatus`. Los ocho origenes actuales pasan a **proponer**.
2. Campos nuevos: `source`, `source_ref`, `rationale`, `confidence`,
   `computed_at`.
3. **Precedencia**, de mayor a menor:
   `human_audit` > `human_manual` > `ai_content` > `controls_derived` > `heuristic`.
   Un origen inferior nunca pisa a uno superior.
4. **Se elimina `_update_compliance_from_doc_category`**: pintar verde por la
   categoria del desplegable de subida es indefendible.
5. **`evidence_count` solo cuenta evidencia con contenido verificado**
   (`ai_review.relevant == true`). Se acaba el salto a IMPLEMENTED 100 por fichas
   vacias.
6. Panel "por que esta en este estado" en cada requisito: documento, parrafo
   citado, control, quien y cuando.
7. El recalculo de limpieza corre como un `IngestBatch` con preview y undo.

---

## 6. Fases

### F0 — Desbloqueo (1 sesion, sin riesgo, desplegable de inmediato)

1. Borrado correcto: limpiar referencias por tipo antes de `db.delete`. La
   `Policy` derivada se borra con el documento; el `BCPPlan` se desvincula con
   aviso; el contrato de proveedor solo se desvincula.
2. `POST /api/documents/bulk`: borrar, reanalizar, recategorizar, con preview de
   impacto.
3. Seleccion multiple en la tabla y `overflow-x:auto`.
4. Error real del analisis visible en la UI.

### F1 — Motor de ingesta agentica

5. `services/ingest_engine.py` sobre las cinco tablas existentes.
6. `EntitySpec` declarativo (seccion 3.3).
7. Trazas obligatorias, conflictos explicitos, overrides intocables.
8. Todo sobre `job_queue`, nunca `threading.Thread`. Coste estimado antes de
   lanzar, progreso en Operaciones.
9. Endpoints `/api/ingest`: lotes, source maps, confirmar, deshacer, conflictos,
   overrides.

### F2 — Comprension profunda

10. Reescritura sobre `claude_client.structured_message` + `model_registry`.
11. Tres pasadas: triaje (fast) -> comprension troceada por capitulos (deep) ->
    sintesis y reconciliacion cruzada del lote.
12. Doble eje: `doc_class` (`normative` / `record` / `reference` /
    `unclassified`) y `document_level` dentro de normativo.
13. Evaluacion semantica contra el requisito, trasplantando el patron de
    [`bcm_content_reviewer.py`](app/services/bcm_content_reviewer.py), que ya lo
    hace para ISO 22301.
14. Baja confianza -> bandeja de revision, nunca a un cajon inventado.

### F3 — Cadena de riesgo y evidencia (seccion 4)

15. `Evidence` real por cada aporte de madurez, con hash y vigencia.
16. `evidence_understanding_service` en el pipeline de ingesta.
17. `Evidence.control_implementation_id` y `risk_id` rellenos.
18. `recalc_risks_for_impls` disparado tras cada ingesta.
19. Caducidad que degrada madurez y sube residual.
20. Mapa de cobertura documental por control; alimentacion del Plan Director.
21. Panel de trazabilidad extremo a extremo en la ficha del riesgo.

### F4 — Cumplimiento con autoridad unica (seccion 5)

### F5 — SharePoint reconciliado

22. Tocar carpetas permitidas dispara reconciliacion, con aviso previo de cuantos
    documentos afecta.
23. `source_path` / `source_folder_id` / `source_folder_name` desde
    `get_item_parent_chain` (la funcion ya existe).
24. Barrido de huerfanos e items desaparecidos fuera del delta.

### F6 — Gestion documental completa

25. Filtros en servidor con paginacion: `doc_class`, nivel, tipo, carpeta,
    estado, framework, control cubierto. `document_level` e `isms_type`
    promovidos a columnas indexadas.
26. Vista arbol: Politica -> Norma -> Procedimiento -> Instruccion -> Registros.
    `parent_policy_id` existe y no se explota.
27. Duplicados por SHA-256 y similitud de titulo.
28. Reclasificacion masiva de lo ya subido vía Message Batches (50 % de
    descuento, ya integrado).

### F7 — BCP sobre el mismo motor

29. Migrar la ingesta BCP al motor compartido. Un documento que es a la vez
    politica de continuidad y evidencia de control alimenta ambos modulos desde
    una sola lectura.

**Orden**: F0 -> F1 -> F2 -> F3 -> F4 -> F5 -> F6 -> F7. F1 primero porque el
resto son consumidores suyos.

---

## 7. Cambios de modelo de datos

Migraciones incrementales en `_migrate_columns()` de `seed.py`, patron habitual.

**`AiDocument`**: `doc_class`, `document_level`, `isms_type`, `classification_confidence`,
`analysed_at`, `sha256`, `source_path`, `source_folder_id`, `source_folder_name`,
`source_revoked`.

**`ComplianceFrameworkStatus`**: `source`, `source_ref`, `rationale`,
`confidence`, `computed_at`.

**`Evidence`**: `source_document_id`, `ingest_trace_id`, `auto_generated`.

**`ControlImplementation`**: `evidence_refs` pasa a cache derivada; se documenta
el cambio de semantica.

Backfill: `document_level` e `isms_type` desde `isms_summary`; `source` de
compliance a `legacy_unknown` para lo existente, que la primera pasada de la
autoridad unica recalcula.

---

## 8. Pruebas

- `test_documents_delete.py`: borrado con cada tipo de referencia foranea.
- `test_documents_bulk.py`: operaciones masivas y aislamiento entre organizaciones.
- `test_ingest_engine.py`: source map, confirmacion, trazas, deshacer lote y
  registro individual, override no pisado por reingesta.
- `test_ingest_conflicts.py`: politicas de resolucion, nada se pierde.
- `test_isms_classifier_v2.py`: doble eje, umbrales de confianza, IA mockeada
  con `structured_message`.
- `test_evidence_risk_chain.py`: documento -> Evidence -> quality E1-E5 ->
  madurez ajustada -> residual recalculado. **Test critico del modulo.**
- `test_evidence_expiry.py`: caducidad degrada madurez y sube residual.
- `test_compliance_authority.py`: precedencia, procedencia, ningun escritor
  paralelo.
- `test_sharepoint_reconcile.py`: alta y baja de carpeta, huerfanos.
- `test_documents_filters.py`: filtros de servidor y paginacion.

Validacion contra la API real en organizacion aislada, mismo metodo del
2026-07-19: ejercitar, verificar, borrar sin residuo.

---

## 9. Fuera de alcance

- OCR propio: se sigue usando Claude Vision.
- Edicion de documentos dentro de RiskHub (sigue siendo Office / SharePoint).
- Firma electronica de politicas (existe `plan_approval_service` para el Plan
  Director; no se extiende aqui en esta version).
- Conectores documentales distintos de SharePoint (Drive, Box, Confluence).
- Traduccion automatica de documentos.

---

## 10. Riesgos de la propia reconstruccion

| Riesgo | Mitigacion |
|---|---|
| El recalculo de cumplimiento baja verdes en sistemas de cliente | Corre como `IngestBatch` con preview y undo; el cliente lo lanza cuando quiere |
| Coste de IA al reclasificar historicos | Message Batches (50 %), triaje con tier fast, estimador previo ya existente |
| Regresion en el motor de riesgo | El motor no se toca: solo se le alimenta bien. Tests de cadena antes de tocar ingesta |
| Colision con trabajo en curso de BCP | F1 absorbe la ingesta BCP en F7, no antes; hasta entonces conviven |
