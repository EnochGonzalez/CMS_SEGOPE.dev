"""Prepara, para cada prueba, una base SQLite temporal ya sembrada con el contenido del blog,
un administrador de prueba y un notificador falso del pipeline."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import config, security
from app.database import Base, crear_engine, get_db
from app.main import app
from app.pipeline import ResultadoNotificacion, get_notificador
from app.seed import sembrar

CORREO_ADMIN = "admin@ejemplo.com"
CLAVE_ADMIN = "clave-segura-123"


@pytest.fixture()
def session_factory(tmp_path):
    engine = crear_engine(f"sqlite:///{tmp_path / 'prueba.db'}")
    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with fabrica() as db:
        sembrar(db)
    yield fabrica
    engine.dispose()


@pytest.fixture()
def admin_configurado(monkeypatch):
    """Administrador de prueba (no toca tu .env) y contador de intentos de login en cero."""
    monkeypatch.setattr(config, "ADMIN_EMAIL", CORREO_ADMIN)
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", security.hash_password(CLAVE_ADMIN))
    monkeypatch.setattr(config, "JWT_SECRET", "clave-secreta-solo-para-pruebas-0123456789abcdef")
    security.limitador_login.reiniciar()
    yield
    security.limitador_login.reiniciar()


class NotificadorFalso:
    """Registra los avisos al pipeline y responde lo que cada prueba necesite."""

    def __init__(self):
        self.llamadas: list[tuple[str, str]] = []
        self.aceptada = True
        self.lenta = False

    def notificar(self, motivo, recurso_id):
        self.llamadas.append((motivo, recurso_id))
        return ResultadoNotificacion(aceptada=self.aceptada, lenta=self.lenta)


@pytest.fixture()
def notificador():
    return NotificadorFalso()


@pytest.fixture()
def client(session_factory, admin_configurado, notificador):
    def _get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_notificador] = lambda: notificador
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def auth(client):
    """Cabecera Authorization con un token válido del administrador."""
    r = client.post("/api/v1/auth/login", json={"email": CORREO_ADMIN, "password": CLAVE_ADMIN})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def clave_nueva() -> str:
    return f"prueba-{uuid.uuid4()}"
