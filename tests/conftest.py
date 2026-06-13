"""Fixtures compartidas para todos los tests de RiskHub."""
import os
import pytest

# Variables de entorno antes de importar cualquier modulo de la app
os.environ.setdefault("RISKHUB_ENV", "test")
os.environ.setdefault("RISKHUB_SECRET_KEY", "test-secret-key-for-ci-testing-only-minimum-32-chars")
os.environ.setdefault("RISKHUB_ADMIN_EMAIL", "admin@test.internal")
os.environ.setdefault("RISKHUB_ADMIN_PASSWORD", "TestAdmin123!")
os.environ.setdefault("RISKHUB_DB_PATH", "./test_riskhub.db")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

_TEST_DB_URL = "sqlite:///./test_riskhub.db"

_engine = create_engine(
    _TEST_DB_URL,
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
    Base.metadata.create_all(bind=_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=_engine)
    # Liberar handles del engine antes de borrar el fichero (Windows bloquea si sigue abierto)
    _engine.dispose()
    # Limpiar archivo de BD de test (best-effort; en Windows puede seguir bloqueado)
    import os as _os
    if _os.path.exists("./test_riskhub.db"):
        try:
            _os.remove("./test_riskhub.db")
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
