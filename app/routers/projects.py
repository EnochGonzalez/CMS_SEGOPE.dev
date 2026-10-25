"""Administración de proyectos (requiere token Bearer).

Endpoints de la especificación v2 que implementa este archivo:
   2. POST   /api/v1/projects                        Creación de proyecto en borrador
   3. GET    /api/v1/projects                        Listado administrativo (cualquier estado)
   4. GET    /api/v1/projects/{project_id}           Obtención administrativa
   5. PUT    /api/v1/projects/{project_id}           Actualización (reemplazo completo)
   6. POST   /api/v1/projects/{project_id}/publish   Publicación
   7. POST   /api/v1/projects/{project_id}/archive   Archivado definitivo
   8. DELETE /api/v1/projects/{project_id}           Eliminación física de borrador

Ciclo de vida:  BORRADOR --publish--> PUBLICADO --archive--> ARCHIVADO (terminal)
"""
from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import idempotency as idem
from app.database import get_db
from app.dependencies import exigir_admin
from app.errors import ApiError
from app.models import Project, ahora_utc
from app.pagination import Clave, paginar
from app.pipeline import Notificador, get_notificador
from app.routers.comunes import CURSOR, ERROR_401, ERROR_404, ERROR_409, ERROR_422, LIMITE
from app.schemas import (
    Envelope, Page, ProjectAdminDetailOut, ProjectAdminItemOut, ProjectArchivedOut, ProjectCreatedOut,
    ProjectCreateIn, ProjectPublishedOut, ProjectStatus, ProjectUpdatedOut, ProjectUpdateIn,
)
from app.services import proyectos as reglas

router = APIRouter(
    prefix="/api/v1/projects",
    tags=["Proyectos (administración)"],
    dependencies=[Depends(exigir_admin)],          # todo este router exige token
    responses=ERROR_401,
)

# Como en la sección 5 de la práctica guiada: FastAPI convierte idempotency_key en la cabecera Idempotency-Key.
CLAVE_IDEMPOTENCIA = Header(min_length=8, max_length=128, description="Clave única por operación (por ejemplo un UUID). Se recuerda 24 h.")
RESPUESTA_202 = {202: {"description": "La operación se aplicó, pero el pipeline tardó en responder: el aviso se reintenta en segundo plano"}}


def _codigo(resultado) -> int:
    return 202 if resultado is not None and resultado.lenta else 200


def _compilacion_aceptada(resultado) -> bool:
    return resultado is not None and resultado.aceptada


# ------------------------------------------------------------------ 2. crear borrador
@router.post(
    "", status_code=201, response_model=Envelope[ProjectCreatedOut],
    summary="2. Creación de proyecto en borrador",
    responses={**ERROR_409, **ERROR_422},
)
def crear_proyecto(
    datos: ProjectCreateIn, response: Response,
    idempotency_key: str = CLAVE_IDEMPOTENCIA, db: Session = Depends(get_db),
):
    """Solo `title` y `slug` son obligatorios: los demás campos pueden completarse antes de publicar.

    409 si el slug ya existe; 422 si algún campo incumple el Diccionario de Tipos o algún `stack_id` no existe."""
    h = idem.huella("POST", "/api/v1/projects", datos.model_dump(mode="json"))
    repetida = idem.buscar_repetida(db, idempotency_key, h)
    if repetida:
        return repetida

    reglas.exigir_slug_libre(db, datos.slug)
    stack = reglas.cargar_stack(db, datos.stack_ids)
    proyecto = Project(status="BORRADOR")
    with reglas.conflicto_de_slug(db, datos.slug):
        db.add(proyecto)
        reglas.reemplazar_contenido(db, proyecto, datos, stack)
        db.flush()

    envelope = Envelope[ProjectCreatedOut](message="Proyecto creado en borrador", data=ProjectCreatedOut.model_validate(proyecto))
    idem.guardar_y_confirmar(db, idempotency_key, h, 201, envelope)
    return envelope


# ------------------------------------------------------------------ 3. listado administrativo
@router.get(
    "", response_model=Envelope[Page[ProjectAdminItemOut]],
    summary="3. Listado administrativo de proyectos",
    responses=ERROR_422,
)
def listar_proyectos(
    estado: ProjectStatus | None = Query(None, alias="status", description="BORRADOR, PUBLICADO o ARCHIVADO"),
    cursor: str | None = CURSOR, limit: int = LIMITE, db: Session = Depends(get_db),
):
    """Incluye proyectos en cualquier estado, ordenados por `updated_at` descendente."""
    consulta = select(Project)
    if estado is not None:
        consulta = consulta.where(Project.status == estado.value)
    claves = [
        Clave(Project.updated_at, "updated_at", "datetime", descendente=True),
        Clave(Project.project_id, "project_id", "str", descendente=True),
    ]
    filas, siguiente = paginar(db, consulta, claves, cursor, limit)
    return Envelope[Page[ProjectAdminItemOut]](
        message="Listado de proyectos obtenido exitosamente",
        data=Page[ProjectAdminItemOut](items=[ProjectAdminItemOut.model_validate(f) for f in filas], next_cursor=siguiente),
    )


# ------------------------------------------------------------------ 4. un proyecto
@router.get(
    "/{project_id}", response_model=Envelope[ProjectAdminDetailOut],
    summary="4. Obtención administrativa de proyecto",
    responses=ERROR_404,
)
def obtener_proyecto(project_id: str, db: Session = Depends(get_db)):
    proyecto = reglas.buscar_proyecto(db, project_id)
    return Envelope[ProjectAdminDetailOut](message="Proyecto obtenido exitosamente", data=ProjectAdminDetailOut.model_validate(proyecto))


# ------------------------------------------------------------------ 5. actualizar
@router.put(
    "/{project_id}", response_model=Envelope[ProjectUpdatedOut],
    summary="5. Actualización de proyecto",
    responses={**ERROR_404, **ERROR_409, **ERROR_422, **RESPUESTA_202},
)
def actualizar_proyecto(
    project_id: str, datos: ProjectUpdateIn, response: Response,
    db: Session = Depends(get_db), notificador: Notificador = Depends(get_notificador),
):
    """PUT reemplaza el recurso completo (lo opcional que no envíes se borra).

    - 409 si está ARCHIVADO, o si cambias el `slug` de un proyecto que ya no es BORRADOR.
    - 422 si está PUBLICADO y el resultado dejaría de cumplir el contrato de publicación.
    - Si está PUBLICADO, la edición se avisa al pipeline (`recompilation_triggered`)."""
    proyecto = reglas.buscar_proyecto(db, project_id)
    if proyecto.status == "ARCHIVADO":
        raise ApiError(409, "PROJECT_ARCHIVED", "Un proyecto ARCHIVADO no se puede editar")
    if datos.slug != proyecto.slug:
        if proyecto.status != "BORRADOR":
            raise ApiError(409, "SLUG_IMMUTABLE", "El slug solo se puede cambiar mientras el proyecto es BORRADOR",
                           [{"field": "slug", "issue": f"Debe seguir siendo '{proyecto.slug}'"}])
        reglas.exigir_slug_libre(db, datos.slug, excepto_id=proyecto.project_id)

    stack = reglas.cargar_stack(db, datos.stack_ids)
    if proyecto.status == "PUBLICADO":
        reglas.exigir_contrato(datos.short_description, datos.description, datos.project_date, stack,
                               "El proyecto está PUBLICADO y debe seguir cumpliendo el contrato de publicación")

    with reglas.conflicto_de_slug(db, datos.slug):
        reglas.reemplazar_contenido(db, proyecto, datos, stack)
        proyecto.updated_at = ahora_utc()
        db.commit()

    # El aviso va DESPUÉS de confirmar: así el pipeline, al leer la API, ya ve los cambios.
    resultado = notificador.notificar("PROJECT_UPDATED", proyecto.project_id) if proyecto.status == "PUBLICADO" else None
    response.status_code = _codigo(resultado)
    return Envelope[ProjectUpdatedOut](
        message="Proyecto actualizado exitosamente",
        data=ProjectUpdatedOut(project_id=proyecto.project_id, status=proyecto.status, updated_at=proyecto.updated_at,
                               recompilation_triggered=_compilacion_aceptada(resultado)),
    )


# ------------------------------------------------------------------ 6. publicar
@router.post(
    "/{project_id}/publish", response_model=Envelope[ProjectPublishedOut],
    summary="6. Publicación de proyecto",
    responses={**ERROR_404, **ERROR_409, **ERROR_422, **RESPUESTA_202},
)
def publicar_proyecto(
    project_id: str, response: Response, idempotency_key: str = CLAVE_IDEMPOTENCIA,
    db: Session = Depends(get_db), notificador: Notificador = Depends(get_notificador),
):
    """Valida el **contrato de publicación** (short_description, description, project_date y al menos un
    lenguaje) y pasa el proyecto a PUBLICADO. 409 si ya estaba PUBLICADO o ARCHIVADO."""
    h = idem.huella("POST", f"/api/v1/projects/{project_id}/publish")
    repetida = idem.buscar_repetida(db, idempotency_key, h)
    if repetida:
        return repetida

    proyecto = reglas.buscar_proyecto(db, project_id)
    if proyecto.status == "PUBLICADO":
        raise ApiError(409, "PROJECT_ALREADY_PUBLISHED", "El proyecto ya está PUBLICADO")
    if proyecto.status == "ARCHIVADO":
        raise ApiError(409, "PROJECT_ARCHIVED", "Un proyecto ARCHIVADO no se puede publicar")
    reglas.exigir_contrato(proyecto.short_description, proyecto.description, proyecto.project_date,
                           proyecto.stack_items, "El proyecto no cumple el contrato de publicación")

    ahora = ahora_utc()
    proyecto.status = "PUBLICADO"
    proyecto.published_at = ahora
    proyecto.updated_at = ahora
    db.commit()

    resultado = notificador.notificar("PROJECT_PUBLISHED", proyecto.project_id)
    codigo = _codigo(resultado)
    envelope = Envelope[ProjectPublishedOut](
        message="El proyecto se ha publicado exitosamente",
        data=ProjectPublishedOut(project_id=proyecto.project_id, status=proyecto.status, published_at=proyecto.published_at,
                                 recompilation_triggered=_compilacion_aceptada(resultado)),
    )
    # Nota: si el servidor se cayera justo entre el commit y esta línea, el reintento recibiría 409.
    idem.guardar_y_confirmar(db, idempotency_key, h, codigo, envelope)
    response.status_code = codigo
    return envelope


# ------------------------------------------------------------------ 7. archivar
@router.post(
    "/{project_id}/archive", response_model=Envelope[ProjectArchivedOut],
    summary="7. Archivado definitivo de proyecto",
    responses={**ERROR_404, **ERROR_409, **RESPUESTA_202},
)
def archivar_proyecto(
    project_id: str, response: Response, idempotency_key: str = CLAVE_IDEMPOTENCIA,
    db: Session = Depends(get_db), notificador: Notificador = Depends(get_notificador),
):
    """Solo un proyecto PUBLICADO se archiva (409 en otro caso). ARCHIVADO es terminal: ya no se edita,
    no se elimina y su slug no vuelve a quedar libre. Deja de verse en las lecturas públicas."""
    h = idem.huella("POST", f"/api/v1/projects/{project_id}/archive")
    repetida = idem.buscar_repetida(db, idempotency_key, h)
    if repetida:
        return repetida

    proyecto = reglas.buscar_proyecto(db, project_id)
    if proyecto.status != "PUBLICADO":
        raise ApiError(409, "PROJECT_NOT_PUBLISHED", "Solo se puede archivar un proyecto PUBLICADO (los borradores se eliminan con DELETE)")

    proyecto.status = "ARCHIVADO"
    proyecto.updated_at = ahora_utc()
    db.commit()

    resultado = notificador.notificar("PROJECT_ARCHIVED", proyecto.project_id)
    codigo = _codigo(resultado)
    envelope = Envelope[ProjectArchivedOut](
        message="El proyecto se ha archivado",
        data=ProjectArchivedOut(project_id=proyecto.project_id, status=proyecto.status, updated_at=proyecto.updated_at,
                                recompilation_triggered=_compilacion_aceptada(resultado)),
    )
    idem.guardar_y_confirmar(db, idempotency_key, h, codigo, envelope)
    response.status_code = codigo
    return envelope


# ------------------------------------------------------------------ 8. eliminar borrador
@router.delete(
    "/{project_id}", status_code=204, response_class=Response,
    summary="8. Eliminación física de borrador",
    responses={**ERROR_404, **ERROR_409},
)
def eliminar_borrador(project_id: str, db: Session = Depends(get_db)):
    """Solo los BORRADOR se eliminan de verdad; los PUBLICADO y ARCHIVADO responden 409."""
    proyecto = reglas.buscar_proyecto(db, project_id)
    if proyecto.status != "BORRADOR":
        raise ApiError(409, "PROJECT_NOT_DELETABLE", "Solo se pueden eliminar proyectos en estado BORRADOR")
    db.delete(proyecto)
    db.commit()
    return Response(status_code=204)
