"""Punto de entrada de la API (equivale a estudiantes.py de la práctica guiada).

Arranque:  python -m uvicorn app.main:app --reload      (documentación en /docs)
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config, consola, models  # noqa: F401  (models registra las tablas en Base.metadata)
from app.database import Base, engine
from app.errors import registrar_manejadores
from app.routers import auth, certificates, files, profile, projects, public, tech_stack


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)      # crea las tablas si todavía no existen
    yield


DESCRIPCION = """
API REST de gestión de contenido del **Dev Portfolio / Blog (SEGOPE.dev)**, versión 2.

Implementa la *Especificación de Arquitectura y Contrato de Interfaz* de la materia Aplicaciones Web.
Todas las respuestas exitosas usan `{ status, message, data }` y todos los errores
`{ status, code, message, details[] }`.

**Bloque 1:** lecturas públicas — endpoints 9, 10, 12, 16 y 19.
**Bloque 2:** login y administración de proyectos — endpoints 1 a 8.
**Bloque 3:** certificados, lenguajes y herramientas, perfil y carga de archivos — endpoints 11, 13, 14, 15, 17, 18, 20 y 21.
**Bloque 5 (este):** consola de administración en [/admin/](/admin/).

Para probar la administración desde esta página: ejecuta `POST /api/v1/auth/login`, copia el
`access_token` y pégalo en el botón **Authorize**.
"""

app = FastAPI(
    title="cms-projects-api",
    version="2.0.0",
    description=DESCRIPCION,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Autenticación", "description": "Login del administrador (token JWT Bearer)."},
        {"name": "Proyectos (administración)", "description": "Requieren token. Ciclo de vida: BORRADOR → PUBLICADO → ARCHIVADO."},
        {"name": "Certificados (administración)", "description": "Requieren token. Sin borrador: al crearse son públicos."},
        {"name": "Lenguajes y herramientas (administración)", "description": "Requieren token. Catálogo único que usan los proyectos."},
        {"name": "Perfil (administración)", "description": "Requiere token. Registro único: solo se edita."},
        {"name": "Archivos", "description": "Requiere token. Sube PDF e imágenes y devuelve su URL."},
        {"name": "Lecturas públicas", "description": "Sin autenticación. Con ETag y Cache-Control (max-age 60 s)."},
    ],
)
registrar_manejadores(app)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(certificates.router)
app.include_router(tech_stack.router)
app.include_router(profile.router)
app.include_router(files.router)
app.include_router(public.router)
# Los archivos subidos se sirven en /media (check_dir=False: la carpeta se crea al subir el primer archivo).
app.mount("/media", StaticFiles(directory=config.FILES_DIR, check_dir=False), name="media")
# La consola de administración (admin/) se sirve en /admin/.
consola.montar_consola(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", reload=True)
