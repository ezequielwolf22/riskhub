"""Conexion a base de datos y sesion SQLAlchemy."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


_is_sqlite = settings.db_url.startswith("sqlite")


def is_sqlite(bind=None) -> bool:
    """True si el motor activo es SQLite. Con `bind` (sesion o engine) consulta
    el dialecto real; sin argumento usa el engine global. Base de las ramas
    dialect-aware (FTS, INSERT OR IGNORE, funciones de fecha)."""
    if bind is None:
        return _is_sqlite
    dialect = getattr(getattr(bind, "bind", bind), "dialect", None)
    name = getattr(dialect, "name", None)
    return name == "sqlite" if name else _is_sqlite

if _is_sqlite:
    engine = create_engine(
        settings.db_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(conn, _record):
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-32000")  # 32 MB cache
        conn.execute("PRAGMA temp_store=MEMORY")

else:
    engine = create_engine(
        settings.db_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=1800,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def insert_ignore(db, table: str, columns: list[str], params: dict) -> None:
    """INSERT que ignora colisiones de clave, portable entre dialectos.

    SQLite: `INSERT OR IGNORE`; PostgreSQL: `ON CONFLICT DO NOTHING`. Usado en
    las tablas de asociacion (risk_vulnerabilities, risk_controls) donde una
    fila duplicada no debe abortar la operacion."""
    from sqlalchemy import text
    cols = ", ".join(columns)
    ph = ", ".join(f":{c}" for c in columns)
    if is_sqlite(db):
        sql = f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({ph})"
    else:
        sql = f"INSERT INTO {table} ({cols}) VALUES ({ph}) ON CONFLICT DO NOTHING"
    db.execute(text(sql), params)


def get_db():
    """Dependencia FastAPI para inyectar sesion de BD."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
