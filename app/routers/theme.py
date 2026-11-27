"""Apariencia del blog: lectura pública (la usa el generador) y actualización (requiere token Bearer).

  GET /api/v1/public/theme            La apariencia actual, con las variables CSS ya resueltas
  GET /api/v1/public/theme/options    Los estilos y opciones disponibles (para la consola)
  PUT /api/v1/theme                   Actualización de la apariencia (avisa al pipeline: el blog debe regenerarse)

La apariencia es un registro único. Si nunca se ha guardado, se devuelve el diseño original del blog.
"""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import exigir_admin
from app.http_cache import con_cache
from app.models import ThemeSettings, ahora_utc
from app.pipeline import Notificador, codigo_http, fue_aceptada, get_notificador
from app.routers.comunes import ERROR_401, ERROR_422, RESPUESTA_202
from app.schemas import Envelope, ThemeIn, ThemeOptionsOut, ThemeOut, ThemeUpdatedOut
from app.services import tema

publico = APIRouter(prefix="/api/v1/public/theme", tags=["Lecturas públicas"])
router = APIRouter(prefix="/api/v1/theme", tags=["Apariencia (administración)"], dependencies=[Depends(exigir_admin)], responses=ERROR_401)


def _salida(fila: ThemeSettings | None) -> dict:
    seleccion = (dict(preset=fila.preset, accent=fila.accent, font_body=fila.font_body, font_mono=fila.font_mono,
                      radius=fila.radius, text_size=fila.text_size) if fila else dict(tema.PREDETERMINADO))
    return {**seleccion, "resolved": tema.resolver(seleccion), "updated_at": fila.updated_at if fila else None}


@publico.get("", response_model=Envelope[ThemeOut], summary="Consulta pública de la apariencia del blog")
def obtener_apariencia(request: Request, response: Response, db: Session = Depends(get_db)):
    """`resolved.vars` son las variables CSS que el blog debe usar; `resolved.is_default` indica si no hace falta CSS extra."""
    fila = db.scalar(select(ThemeSettings).limit(1))
    return con_cache(request, response, Envelope[ThemeOut](message="Apariencia obtenida exitosamente", data=ThemeOut(**_salida(fila))))


@publico.get("/options", response_model=Envelope[ThemeOptionsOut], summary="Estilos y opciones de apariencia disponibles")
def obtener_opciones(request: Request, response: Response):
    return con_cache(request, response, Envelope[ThemeOptionsOut](message="Opciones obtenidas exitosamente", data=ThemeOptionsOut(**tema.catalogo())))


@router.put("", response_model=Envelope[ThemeUpdatedOut], summary="Actualización de la apariencia del blog",
            responses={**ERROR_422, **RESPUESTA_202})
def actualizar_apariencia(datos: ThemeIn, response: Response, db: Session = Depends(get_db),
                          notificador: Notificador = Depends(get_notificador)):
    """PUT reemplaza la apariencia completa. Un `accent` propio se rechaza (422) si no se lee bien sobre el fondo del estilo
    o si el texto blanco de los botones no se lee sobre él. Cada cambio se avisa al pipeline: el blog se regenera con el nuevo CSS."""
    if datos.accent:
        tema.comprobar_acento(datos.preset, datos.accent)
    fila = db.scalar(select(ThemeSettings).limit(1))
    if fila is None:
        fila = ThemeSettings()
        db.add(fila)
    fila.preset, fila.accent = datos.preset, datos.accent.lower() if datos.accent else None
    fila.font_body, fila.font_mono, fila.radius, fila.text_size = datos.font_body, datos.font_mono, datos.radius, datos.text_size
    fila.updated_at = ahora_utc()
    db.commit()

    resultado = notificador.notificar("THEME_UPDATED", fila.theme_id)
    response.status_code = codigo_http(resultado)
    return Envelope[ThemeUpdatedOut](message="Apariencia actualizada exitosamente",
                                     data=ThemeUpdatedOut(**_salida(fila), recompilation_triggered=fue_aceptada(resultado)))
