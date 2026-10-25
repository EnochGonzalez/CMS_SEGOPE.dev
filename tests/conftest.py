"""Prepara, para cada prueba, una base SQLite temporal ya sembrada con el contenido del blog."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import Base, crear_engine, get_db
from app.main import app
from app.seed import sembrar


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
def client(session_factory):
    def _get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
