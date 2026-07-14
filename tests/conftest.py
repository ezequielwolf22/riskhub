"""Fixtures compartidas para todos los tests de RiskHub."""
import os
import pytest

# Variables de entorno antes de importar cualquier modulo de la app
os.environ.setdefault("RISKHUB_ENV", "test")
os.environ.setdefault("RISKHUB_SECRET_KEY", "test-secret-key-for-ci-testing-only-minimum-32-chars")
os.environ.setdefault("RISKHUB_ADMIN_EMAIL", "admin@test.internal")
os.environ.setdefault("RISKHUB_ADMIN_PASSWORD", "TestAdmin123!")
os.environ.setdefault("RISKHUB_DB_PATH", "./test_riskhub.db")
# Sin limite global de API en tests (la suite dispara miles de requests)
os.environ.setdefault("RISKHUB_API_RATE_PER_MINUTE", "0")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

# La suite corre contra SQLite por defecto; si RISKHUB_DATABASE_URL apunta a
# PostgreSQL (CI con servicio postgres, o validacion local), usa ese motor —
# asi el mismo conjunto de tests valida la portabilidad del codigo.
_PG_URL = os.environ.get("RISKHUB_DATABASE_URL")
_USING_PG = bool(_PG_URL and not _PG_URL.startswith("sqlite"))

if _USING_PG:
    _engine = create_engine(_PG_URL, pool_pre_ping=True)
else:
    _engine = create_engine(
        "sqlite:///./test_riskhub.db",
        connect_args={"check_same_thread": False},
    )
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Inicializa el esquema de BD de test al comienzo de la sesion."""
    # Resetear rate limiter para evitar bloqueos por intentos acumulados de runs anteriores
    try:
        from app.services.rate_limiter import reset_all_counters
        reset_all_counters()
    except Exception:
        pass

    # Borrar BD residual de un run anterior (crash, kill, etc.)
    if os.path.exists("./test_riskhub.db"):
        try:
            os.remove("./test_riskhub.db")
        except OSError:
            pass

    Base.metadata.create_all(bind=_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    try:
        Base.metadata.drop_all(bind=_engine)
    except Exception:
        # PostgreSQL: el ciclo de FKs conocido puede impedir el DROP ordenado.
        # No es critico al cerrar la sesion de test (la BD de CI es efimera).
        pass
    # Liberar handles del engine antes de borrar el fichero (Windows bloquea si sigue abierto)
    _engine.dispose()
    # Limpiar archivo de BD de test (best-effort; en Windows puede seguir bloqueado)
    if os.path.exists("./test_riskhub.db"):
        try:
            os.remove("./test_riskhub.db")
        except OSError:
            pass


@pytest.fixture(scope="session")
def client(setup_test_db):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(scope="session")
def admin_token(client):
    """Token JWT de administrador para tests que requieren autenticacion."""
    resp = client.post(
        "/api/auth/login",
        data={"username": "admin@test.internal", "password": "TestAdmin123!"},
    )
    assert resp.status_code == 200, f"Login admin fallo: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
