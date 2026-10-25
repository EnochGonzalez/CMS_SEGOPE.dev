"""Conexión a la base de datos con SQLAlchemy."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL


def crear_engine(url: str = DATABASE_URL):
    es_sqlite = url.startswith("sqlite")
    engine = create_engine(url, connect_args={"check_same_thread": False} if es_sqlite else {})
    if es_sqlite:
        # SQLite no hace cumplir las llaves foráneas a menos que se le pida.
        @event.listens_for(engine, "connect")
        def _activar_llaves_foraneas(conexion, _registro):
            conexion.execute("PRAGMA foreign_keys=ON")
    return engine


engine = crear_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependencia de FastAPI: abre una sesión por petición y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
