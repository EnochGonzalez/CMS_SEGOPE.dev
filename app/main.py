"""Punto de entrada de la API (equivale a estudiantes.py de la práctica guiada).

Arranque:  python -m uvicorn app.main:app --reload      (documentación en /docs)
"""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import config, consola, models, seed  # noqa: F401  (models registra las tablas en Base.metadata)
from app.database import Base, SessionLocal, activar_seguridad_por_filas, engine, get_db
from app.errors import registrar_manejadores
from app.routers import auth, certificates, files, profile, projects, public, tech_stack


# Los mensajes de la API (avisos al pipeline, errores del almacén) salen en el registro del servidor con el prefijo "cms".
_registro = logging.getLogger("cms")
if not _registro.handlers:
    _manejador = logging.StreamHandler()
    _manejador.setFormatter(logging.Formatter("%(levelname)s:     [%(name)s] %(message)s"))
    _registro.addHandler(_manejador)
    _registro.setLevel(logging.INFO)
log = logging.getLogger("cms.arranque")


@asynccontextmanager
async def lifespan(app: FastAPI):
    problemas = config.problemas_de_configuracion()
    if problemas:                          # mejor no arrancar que guardar archivos con direcciones equivocadas
        raise RuntimeError("Configuración incompleta:\n- " + "\n- ".join(problemas))
    Base.metadata.create_all(engine)      # crea las tablas si todavía no existen
    activar_seguridad_por_filas(engine)   # solo en Postgres
    if config.SEMBRAR_SI_ESTA_VACIA:
        with SessionLocal() as db:
            if seed.base_vacia(db):
                resumen = seed.sembrar(db)
                log.info("Base vacía: se cargó el contenido inicial (%s)", ", ".join(f"{n} {k}" for k, n in resumen.items()))
    if not (config.ADMIN_EMAIL and config.ADMIN_PASSWORD_HASH and config.JWT_SECRET):
        log.warning("El administrador no está configurado: las lecturas públicas funcionan, pero nadie puede iniciar sesión")
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
@app.middleware("http")
async def cabeceras_de_seguridad(request: Request, call_next):
    """El navegador no debe adivinar el tipo de un archivo subido, y las respuestas de una sesión de administrador
    (con Authorization) nunca se guardan en cachés compartidas."""
    respuesta = await call_next(request)
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    if request.headers.get("authorization") and "cache-control" not in respuesta.headers:
        respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@app.get("/health", include_in_schema=False)
def salud(db: Session = Depends(get_db)):
    """Para el servidor y los monitores: responde 200 si la API y su base de datos están vivas."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "error", "database": "no responde"})
    return {"status": "ok", "database": "ok"}


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
