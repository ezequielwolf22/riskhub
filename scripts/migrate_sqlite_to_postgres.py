#!/usr/bin/env python3
"""Migra datos de SQLite a PostgreSQL respetando el orden de FKs.

Uso:
  python scripts/migrate_sqlite_to_postgres.py \
    --sqlite /srv/data/riskhub.db \
    --postgres postgresql://riskhub:password@localhost:5432/riskhub

El script es idempotente: si una tabla ya tiene datos en PG la salta
(a menos que se pase --force que trunca y re-inserta).
"""
import argparse
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def get_table_order(metadata):
    """Devuelve tablas en orden topologico (padres antes que hijos)."""
    from sqlalchemy import MetaData
    resolved = []
    visited = set()

    def visit(table):
        if table.name in visited:
            return
        visited.add(table.name)
        for fk in table.foreign_keys:
            parent = fk.column.table
            if parent.name != table.name:
                visit(parent)
        resolved.append(table)

    for table in metadata.sorted_tables:
        visit(table)
    return resolved


def migrate(sqlite_url: str, pg_url: str, force: bool = False):
    from sqlalchemy import create_engine, text, inspect
    from sqlalchemy import MetaData

    log.info("Conectando a SQLite: %s", sqlite_url)
    src_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

    log.info("Conectando a PostgreSQL: %s", pg_url.replace("://", "://***@", 1).rsplit("@", 1)[-1])
    dst_engine = create_engine(pg_url, pool_pre_ping=True)

    # Importar modelos para que Base.metadata este completo
    sys.path.insert(0, ".")
    from app.database import Base
    import app.models  # noqa: F401 — registra todos los modelos en Base.metadata

    # Crear tablas en PostgreSQL si no existen
    log.info("Creando esquema en PostgreSQL...")
    Base.metadata.create_all(dst_engine)

    tables = get_table_order(Base.metadata)
    log.info("Migrando %d tablas...", len(tables))

    with src_engine.connect() as src, dst_engine.connect() as dst:
        # Deshabilitar FK checks temporalmente en PostgreSQL
        dst.execute(text("SET session_replication_role = 'replica'"))

        for table in tables:
            rows = src.execute(table.select()).mappings().all()
            if not rows:
                log.info("  %s — vacia, omitida", table.name)
                continue

            count_dst = dst.execute(text(f"SELECT COUNT(*) FROM \"{table.name}\"")).scalar()

            if count_dst > 0 and not force:
                log.info("  %s — ya tiene %d filas en PG, omitida (usa --force para sobreescribir)", table.name, count_dst)
                continue

            if force and count_dst > 0:
                dst.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
                log.info("  %s — truncada", table.name)

            # Insertar en bloques de 500
            rows_list = [dict(r) for r in rows]
            chunk = 500
            for i in range(0, len(rows_list), chunk):
                dst.execute(table.insert(), rows_list[i:i + chunk])

            log.info("  %s — %d filas migradas", table.name, len(rows_list))

        dst.execute(text("SET session_replication_role = 'origin'"))
        dst.commit()

    # Sincronizar secuencias de PG para que los autoincrementales no colisionen
    log.info("Sincronizando secuencias de autoincremento...")
    insp = inspect(dst_engine)
    with dst_engine.connect() as dst:
        for table in tables:
            pk_cols = [c for c in table.columns if c.primary_key and c.autoincrement is not False and str(c.type) in ("INTEGER", "BIGINT")]
            for col in pk_cols:
                seq_sql = f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', '{col.name}'), COALESCE(MAX(\"{col.name}\"), 1)) FROM \"{table.name}\""
                try:
                    dst.execute(text(seq_sql))
                except Exception as e:
                    log.warning("    No se pudo sincronizar secuencia %s.%s: %s", table.name, col.name, e)
        dst.commit()

    log.info("Migracion completada correctamente.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migra RiskHub de SQLite a PostgreSQL")
    parser.add_argument("--sqlite", required=True, help="Ruta al fichero SQLite, ej: /srv/data/riskhub.db")
    parser.add_argument("--postgres", required=True, help="URL PostgreSQL, ej: postgresql://user:pass@host/db")
    parser.add_argument("--force", action="store_true", help="Truncar tablas existentes y re-insertar")
    args = parser.parse_args()

    migrate(f"sqlite:///{args.sqlite}", args.postgres, force=args.force)
