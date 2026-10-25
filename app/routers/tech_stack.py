"""Administración del catálogo de lenguajes y herramientas (requiere token Bearer).

Endpoints de la especificación v2 que implementa este archivo:
  15. POST   /api/v1/tech-stack               Creación de elemento del catálogo
  17. PUT    /api/v1/tech-stack/{stack_id}    Actualización (reemplazo completo)
  18. DELETE /api/v1/tech-stack/{stack_id}    Eliminación
(El 16, el listado público, está en public.py.) Solo se avisa al pipeline cuando el cambio se nota en el blog:
el elemento aparece en "Lenguajes y herramientas" (show_in_profile) o lo usa un proyecto PUBLICADO.
"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app import idempotency as idem
from app.database import get_db
from app.dependencies import exigir_admin
from app.errors import ApiError
from app.models import TechStackItem, ahora_utc
from app.pipeline import Notificador, codigo_http, fue_aceptada, get_notificador
from app.routers.comunes import CLAVE_IDEMPOTENCIA, ERROR_401, ERROR_404, ERROR_409, ERROR_422, RESPUESTA_202
from app.schemas import Envelope, TechStackCreatedOut, TechStackDeletedOut, TechStackIn, TechStackUpdatedOut, TechStackUpdateIn
from app.services import catalogo as reglas

router = APIRouter(
    prefix="/api/v1/tech-stack",
    tags=["Lenguajes y herramientas (administración)"],
    dependencies=[Depends(exigir_admin)],
    responses=ERROR_401,
)
CONFLICTO = ("STACK_NAME_ALREADY_EXISTS", "Ya existe un elemento con ese nombre", "name")


# ------------------------------------------------------------------ 15. crear
@router.post(
    "", status_code=201, response_model=Envelope[TechStackCreatedOut],
    summary="15. Creación de elemento del catálogo",
    responses={**ERROR_409, **ERROR_422},
)
def crear_elemento(
    datos: TechStackIn, idempotency_key: str = CLAVE_IDEMPOTENCIA, db: Session = Depends(get_db),
    notificador: Notificador = Depends(get_notificador),
):
    """409 si el `name` ya existe (sin distinguir mayúsculas). Si omites `display_order`, queda en la última posición.
    Solo avisa al pipeline si `show_in_profile` es true."""
    h = idem.huella("POST", "/api/v1/tech-stack", datos.model_dump(mode="json"))
    repetida = idem.buscar_repetida(db, idempotency_key, h)
    if repetida:
        return repetida

    reglas.exigir_nombre_libre(db, datos.name)
    item = TechStackItem(name=datos.name, category=datos.category.value, logo_url=datos.logo_url,
                         show_in_profile=datos.show_in_profile,
                         display_order=datos.display_order or reglas.siguiente_orden(db))
    with reglas.conflicto_unico(db, *CONFLICTO):
        db.add(item)
        db.commit()

    resultado = notificador.notificar("STACK_CREATED", item.stack_id) if item.show_in_profile else None
    envelope = Envelope[TechStackCreatedOut](
        message="Elemento creado exitosamente",
        data=TechStackCreatedOut(stack_id=item.stack_id, name=item.name, category=item.category,
                                 show_in_profile=item.show_in_profile, display_order=item.display_order,
                                 created_at=item.created_at, recompilation_triggered=fue_aceptada(resultado)),
    )
    idem.guardar_y_confirmar(db, idempotency_key, h, 201, envelope)
    return envelope


# ------------------------------------------------------------------ 17. actualizar
@router.put(
    "/{stack_id}", response_model=Envelope[TechStackUpdatedOut],
    summary="17. Actualización de elemento del catálogo",
    responses={**ERROR_404, **ERROR_409, **ERROR_422, **RESPUESTA_202},
)
def actualizar_elemento(
    stack_id: str, datos: TechStackUpdateIn, response: Response, db: Session = Depends(get_db),
    notificador: Notificador = Depends(get_notificador),
):
    """PUT reemplaza el elemento completo. Si no envías `display_order`, pasa a la última posición.
    Avisa al pipeline si el elemento aparece (o aparecía) en el perfil, o si lo usa un proyecto PUBLICADO."""
    item = reglas.buscar_stack(db, stack_id)
    reglas.exigir_nombre_libre(db, datos.name, excepto_id=item.stack_id)
    era_visible = item.show_in_profile

    with reglas.conflicto_unico(db, *CONFLICTO):
        item.name = datos.name
        item.category = datos.category.value
        item.logo_url = datos.logo_url
        item.show_in_profile = datos.show_in_profile
        item.display_order = datos.display_order or reglas.siguiente_orden(db, excepto_id=item.stack_id)
        item.updated_at = ahora_utc()
        db.commit()

    resultado = notificador.notificar("STACK_UPDATED", item.stack_id) if reglas.cambia_el_blog(db, item, era_visible) else None
    response.status_code = codigo_http(resultado)
    return Envelope[TechStackUpdatedOut](
        message="Elemento actualizado exitosamente",
        data=TechStackUpdatedOut(stack_id=item.stack_id, updated_at=item.updated_at, recompilation_triggered=fue_aceptada(resultado)),
    )


# ------------------------------------------------------------------ 18. eliminar
@router.delete(
    "/{stack_id}", response_model=Envelope[TechStackDeletedOut],
    summary="18. Eliminación de elemento del catálogo",
    responses={**ERROR_404, **ERROR_409, **RESPUESTA_202},
)
def eliminar_elemento(
    stack_id: str, response: Response, db: Session = Depends(get_db),
    notificador: Notificador = Depends(get_notificador),
):
    """409 si algún proyecto, en cualquier estado, usa el elemento."""
    item = reglas.buscar_stack(db, stack_id)
    usos = reglas.proyectos_que_lo_usan(db, stack_id)
    if usos:
        raise ApiError(409, "STACK_IN_USE", "No se puede eliminar: hay proyectos que usan este elemento",
                       [{"field": "stack_id", "issue": "Lo usan: " + ", ".join(p.slug for p in usos)}])
    era_visible = item.show_in_profile
    db.delete(item)
    db.commit()

    resultado = notificador.notificar("STACK_DELETED", stack_id) if era_visible else None
    response.status_code = codigo_http(resultado)
    return Envelope[TechStackDeletedOut](
        message="Elemento eliminado exitosamente",
        data=TechStackDeletedOut(stack_id=stack_id, recompilation_triggered=fue_aceptada(resultado)),
    )
