"""Punto de entrada de la API (equivale a estudiantes.py de la práctica guiada).

Arranque:  python -m uvicorn app.main:app --reload      (documentación en /docs)
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  (registra las tablas en Base.metadata)
from app.database import Base, engine
from app.errors import registrar_manejadores
from app.routers import public


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)      # crea las tablas si todavía no existen
    yield


DESCRIPCION = """
API REST de gestión de contenido del **Dev Portfolio / Blog (SEGOPE.dev)**, versión 2.

Implementa la *Especificación de Arquitectura y Contrato de Interfaz* de la materia Aplicaciones Web.
Todas las respuestas exitosas usan `{ status, message, data }` y todos los errores
`{ status, code, message, details[] }`.

**Bloque 1 (este):** lecturas públicas — endpoints 9, 10, 12, 16 y 19.
"""

app = FastAPI(
    title="cms-projects-api",
    version="2.0.0",
    description=DESCRIPCION,
    lifespan=lifespan,
    openapi_tags=[{"name": "Lecturas públicas", "description": "Sin autenticación. Con ETag y Cache-Control (max-age 60 s)."}],
)
registrar_manejadores(app)
app.include_router(public.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", reload=True)
