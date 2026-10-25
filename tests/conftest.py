"""Prepara, para cada prueba, una base SQLite temporal ya sembrada con el contenido del blog,
un administrador de prueba y un notificador falso del pipeline."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import config, security
from app.database import Base, crear_engine, get_db
from app.ids import nuevo_id
from app.main import app
from app.pipeline import ResultadoNotificacion, get_notificador
from app.seed import sembrar
from app.storage import TIPOS, get_almacen

CORREO_ADMIN = "admin@ejemplo.com"
CLAVE_ADMIN = "clave-segura-123"

# Archivos de ejemplo: lo que importa para la API son sus primeros bytes (así reconoce el tipo).
PDF = b"%PDF-1.4\n% archivo de prueba\n" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"0" * 64


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


class AlmacenEnMemoria:
    """Hace de servicio de archivos sin tocar el disco."""
    base_url = "https://archivos.ejemplo.com/media"

    def __init__(self):
        self.archivos: dict[str, bytes] = {}

    def guardar(self, contenido, mime_type, purpose):
        url = f"{self.base_url}/{purpose.lower()}/{nuevo_id()}.{TIPOS[mime_type][0]}"
        self.archivos[url] = contenido
        return url


@pytest.fixture()
def almacen():
    return AlmacenEnMemoria()


@pytest.fixture()
def client(session_factory, admin_configurado, notificador, almacen):
    def _get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_notificador] = lambda: notificador
    app.dependency_overrides[get_almacen] = lambda: almacen
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
