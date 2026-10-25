"""Actualización del perfil y contacto (requiere token Bearer).

Endpoint de la especificación v2 que implementa este archivo:
  20. PUT /api/v1/profile     Actualización del perfil
(El 19, la consulta pública, está en public.py.) El perfil es un registro único: la API no lo crea ni lo elimina.
"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import exigir_admin
from app.errors import ApiError
from app.models import Profile, ahora_utc
from app.pipeline import Notificador, codigo_http, fue_aceptada, get_notificador
from app.routers.comunes import ERROR_401, ERROR_404, ERROR_422, RESPUESTA_202
from app.schemas import Envelope, ProfileIn, ProfileUpdatedOut

router = APIRouter(
    prefix="/api/v1/profile",
    tags=["Perfil (administración)"],
    dependencies=[Depends(exigir_admin)],
    responses=ERROR_401,
)


@router.put(
    "", response_model=Envelope[ProfileUpdatedOut],
    summary="20. Actualización del perfil",
    responses={**ERROR_404, **ERROR_422, **RESPUESTA_202},
)
def actualizar_perfil(
    datos: ProfileIn, response: Response, db: Session = Depends(get_db),
    notificador: Notificador = Depends(get_notificador),
):
    """PUT reemplaza el perfil completo (`photo_url`, `phone` y `github_url` son opcionales y, si no los envías, se borran).
    Cada cambio se avisa al pipeline porque el perfil se muestra en el blog."""
    perfil = db.scalar(select(Profile).limit(1))
    if perfil is None:
        raise ApiError(404, "PROFILE_NOT_FOUND", "Todavía no hay un perfil cargado; ejecuta python -m app.seed")

    perfil.full_name = datos.full_name
    perfil.job_title = datos.job_title
    perfil.tagline = datos.tagline
    perfil.bio = datos.bio
    perfil.photo_url = datos.photo_url
    perfil.email = datos.email
    perfil.phone = datos.phone
    perfil.github_url = datos.github_url
    perfil.updated_at = ahora_utc()
    db.commit()

    resultado = notificador.notificar("PROFILE_UPDATED", perfil.profile_id)
    response.status_code = codigo_http(resultado)
    return Envelope[ProfileUpdatedOut](
        message="Perfil actualizado exitosamente",
        data=ProfileUpdatedOut(profile_id=perfil.profile_id, updated_at=perfil.updated_at, recompilation_triggered=fue_aceptada(resultado)),
    )
