"""Conexión a la base de datos con SQLAlchemy."""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL


def normalizar_url(url: str) -> str:
    """Los servicios de Postgres entregan postgres:// o postgresql://; SQLAlchemy necesita saber qué driver usar (psycopg)."""
    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


def crear_engine(url: str = DATABASE_URL):
    url = normalizar_url(url)
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        # SQLite no hace cumplir las llaves foráneas a menos que se le pida.
        @event.listens_for(engine, "connect")
        def _activar_llaves_foraneas(conexion, _registro):
            conexion.execute("PRAGMA foreign_keys=ON")
        return engine
    # Postgres en la nube: los servicios gratuitos cierran las conexiones inactivas, así que se comprueba cada una antes
    # de usarla (pool_pre_ping) y se renuevan seguido (pool_recycle). prepare_threshold=None permite usar también el
    # "pooler" de transacciones (PgBouncer), que no admite sentencias preparadas.
    return create_engine(url, pool_pre_ping=True, pool_recycle=300, connect_args={"prepare_threshold": None})


engine = crear_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def activar_seguridad_por_filas(motor) -> None:
    """Solo Postgres. Servicios como Supabase publican además una API automática para las tablas del esquema público,
    abierta a quien tenga su clave "pública". Con la seguridad por filas (RLS) activada y sin políticas, esos roles no ven
    ni modifican nada. Esta API se conecta como DUEÑA de las tablas, así que no se ve afectada. Es seguro repetirlo."""
    if motor.dialect.name != "postgresql":
        return
    with motor.begin() as conexion:
        for tabla in Base.metadata.sorted_tables:
            conexion.execute(text(f'ALTER TABLE "{tabla.name}" ENABLE ROW LEVEL SECURITY'))


def get_db():
    """Dependencia de FastAPI: abre una sesión por petición y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
