# Plan de migración a PostgreSQL

Estado: **documento de diseño — no ejecutado**. SQLite sigue siendo el default
soportado; PostgreSQL es opcional y este plan describe cómo llegar sin romper nada.

## Cuándo migrar

SQLite con WAL aguanta bien el perfil actual (decenas de usuarios, escrituras
moderadas, una sola máquina). Migrar cuando aparezca cualquiera de estos:

- Varias réplicas de la app (SQLite no comparte fichero entre hosts).
- Escrituras concurrentes sostenidas que provoquen `database is locked`.
- Necesidad de backups PITR (point-in-time recovery) o réplica en caliente.
- Clientes enterprise que exijan Postgres por política.

## Lo que ya está preparado

- `app/config.py`: `RISKHUB_DATABASE_URL` ya existe; `db_url` la prioriza.
- `app/database.py`: rama no-SQLite con pool configurado (pool_size 10, overflow 20,
  pre_ping, recycle 1800).
- SQLAlchemy 2.0 en todo el código: el 95% de las queries son portables.
- `rate_limiter.py` usa su propio `rate_limits.db` local — funciona igual con
  la BD principal en Postgres (es estado efímero por instancia; con varias
  réplicas cada una limita por su cuenta, aceptable).
- `backup_service.py` se autodesactiva si la BD no es SQLite.

## Inventario de SQLite-isms a portar

### 1. FTS5 → tsvector (el trabajo grande)

- `app/seed.py:_create_fts5_table()` crea dos tablas virtuales FTS5:
  - `ai_chunks_fts` (chunks de documentos para RAG)
  - `ai_entity_fts` (entidades de negocio: riesgos, controles, políticas…)
- Consumidores con `MATCH`: `app/services/rag_service.py` (líneas ~319, ~330, ~492).

Port: columna generada `tsv tsvector GENERATED ALWAYS AS (to_tsvector('spanish', content)) STORED`
+ índice GIN, y sustituir `MATCH :q` por `tsv @@ plainto_tsquery('spanish', :q)`
con `ts_rank` para ordenar. Encapsular en `rag_service` dos funciones
`_fts_search_sqlite/_fts_search_pg` elegidas por dialecto (`db.bind.dialect.name`).
El tokenizado bilingüe ES/EN que hoy hace `unicode61 remove_diacritics` se
aproxima con `unaccent` + diccionario `spanish`; la expansión bilingüe ya la
hace la app por fuera, no el motor.

### 2. `INSERT OR IGNORE` → `ON CONFLICT DO NOTHING`

- `app/services/asset_risk_analysis_service.py` (3 sitios: risk_vulnerabilities,
  risk_controls). Port directo: `INSERT ... ON CONFLICT DO NOTHING`, o mejor,
  `sqlalchemy.dialects` insert con `on_conflict_do_nothing()` según dialecto.

### 3. `PRAGMA table_info` en migraciones → information_schema

- `app/seed.py:_migrate_columns()` inspecciona columnas con
  `PRAGMA table_info(<tabla>)`. Port: usar `sqlalchemy.inspect(engine).get_columns(table)`
  que abstrae ambos motores (cambio recomendable ya, antes de migrar).

### 4. `func.strftime` → `to_char` / `date_trunc`

- `app/routers/ai.py` (~2937-2944): agrupación mensual del endpoint `/api/ai/usage`
  con `strftime('%Y-%m', created_at)`. Port: `func.to_char(col, 'YYYY-MM')` en PG;
  seleccionar por dialecto o usar `func.substr(func.cast(col, String), 1, 7)` portable.

### 5. PRAGMAs de conexión

- `app/database.py` aplica PRAGMAs solo en la rama SQLite — nada que portar,
  pero revisar equivalentes de tuning en PG (shared_buffers etc. son del servidor).

### 6. Tipos y detalles

- `JSON` de SQLAlchemy mapea a `JSON` en PG — considerar `JSONB` (índices, menor
  tamaño) vía `Column(JSON().with_variant(JSONB, "postgresql"))` en modelos calientes
  (`risks.ai_context_meta`, `background_jobs.payload`, `evidence.ai_review`).
- `DateTime` sin timezone: la app guarda UTC naive de forma consistente; en PG
  usar `timestamp without time zone` (default) y no mezclar con `timestamptz`.
- Booleanos guardados como 0/1 en SQLite: SQLAlchemy los emite bien en PG, sin acción.
- Autoincrement: `Integer primary_key` → `SERIAL` automático vía SQLAlchemy, sin acción.

## Script de migración de datos

Herramienta: `pgloader` (mapea tipos y copia en bulk) o script propio con
SQLAlchemy (leer de sqlite, insertar en PG por tabla en orden de FKs).
Recomendado: script propio `scripts/migrate_sqlite_to_pg.py` porque:

- controla el orden de FKs (organizations → users → assets → risks → …),
- omite las tablas FTS5 virtuales (se reindexan en PG tras migrar con el
  job `refresh_entity_index` + reindexado de chunks),
- resetea las secuencias (`setval`) al max(id) de cada tabla al final.

Esqueleto:

```python
# 1. engine_src = create_engine("sqlite:///riskhub.db")
# 2. engine_dst = create_engine(os.environ["RISKHUB_DATABASE_URL"])
# 3. Base.metadata.create_all(engine_dst)
# 4. for table in Base.metadata.sorted_tables:  # respeta FKs
#        rows = src.execute(table.select()).mappings().all()
#        if rows: dst.execute(table.insert(), rows)  # por lotes de 1000
# 5. for table in ...: SELECT setval(pg_get_serial_sequence(...), max(id))
# 6. Recrear índices FTS (tsvector) y lanzar refresh_entity_index()
```

## Rollout propuesto

1. **Fase 0 (ya)**: cambios portables sin riesgo — `sqlalchemy.inspect` en vez de
   PRAGMA, `on_conflict_do_nothing()` dialect-aware, strftime → variante portable.
   Todo sigue corriendo en SQLite.
2. **Fase 1**: rama FTS por dialecto en `rag_service` + tests con Postgres en CI
   (job adicional con `services: postgres` en GitHub Actions, `RISKHUB_DATABASE_URL`
   apuntando al servicio).
3. **Fase 2**: `scripts/migrate_sqlite_to_pg.py` + ensayo con copia de la BD de
   producción en local (docker `postgres:16`). Verificar: counts por tabla,
   login, dashboard, análisis IA, RAG, informes.
4. **Fase 3 (producción)**: añadir servicio `db` (postgres:16 + volumen) a
   `docker-compose.yml`, ventana de corte: backup SQLite → migrar → arrancar
   con `RISKHUB_DATABASE_URL` → smoke test → dejar el fichero SQLite como
   rollback durante 2 semanas.
5. **Backups en PG**: cron con `pg_dump -Fc` diario + retención (sustituye a
   `backup_service`, que se autodesactiva); documentar restore con `pg_restore`.

## Riesgos conocidos

- La calidad del ranking FTS cambiará (BM25 de FTS5 vs ts_rank): revisar los
  umbrales de score usados en RAG si los hay.
- Case-sensitivity: LIKE en PG es case-sensitive (SQLite no para ASCII) —
  auditar los `.ilike()` vs `.like()` antes de la fase 2.
- Enums de SQLAlchemy: en PG se crean tipos nativos; añadir valores nuevos a un
  enum requiere `ALTER TYPE ... ADD VALUE` (las migraciones de `_migrate_columns`
  deberán contemplarlo).
