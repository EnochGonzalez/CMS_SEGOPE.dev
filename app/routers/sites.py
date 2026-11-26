"""Administración de los sitios que el CMS monitorea (requiere token Bearer).

  GET    /api/v1/sites              Lista de sitios, con sus visitas totales
  POST   /api/v1/sites              Agregar un sitio a monitorear
  PUT    /api/v1/sites/{site_id}    Actualización (reemplazo completo; también pausa o reanuda el monitoreo)
  DELETE /api/v1/sites/{site_id}    Eliminar el sitio y todas sus visitas

Cambiar un sitio no modifica el blog, así que estos endpoints no avisan al pipeline.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import idempotency as idem
from app.database import get_db
from app.dependencies import exigir_admin
from app.models import PageView, Site, ahora_utc
from app.routers.comunes import CLAVE_IDEMPOTENCIA, ERROR_401, ERROR_404, ERROR_409, ERROR_422
from app.schemas import Envelope, Page, SiteDeletedOut, SiteIn, SiteListItemOut, SiteOut, SiteUpdateIn
from app.services import analitica as reglas
from app.services import catalogo

router = APIRouter(
    prefix="/api/v1/sites",
    tags=["Sitios monitoreados (administración)"],
    dependencies=[Depends(exigir_admin)],
    responses=ERROR_401,
)
CONFLICTO = ("SITE_DOMAIN_ALREADY_EXISTS", "Ya existe un sitio con ese dominio", "domain")


@router.get("", response_model=Envelope[Page[SiteListItemOut]], summary="Lista de sitios monitoreados")
def listar_sitios(db: Session = Depends(get_db)):
    """Todos los sitios (activos y pausados), del más antiguo al más nuevo, con sus visitas totales y la fecha de la última."""
    conteo = (select(PageView.site_id, func.count().label("total"), func.max(PageView.occurred_at).label("ultima"))
              .group_by(PageView.site_id).subquery())
    filas = db.execute(
        select(Site, conteo.c.total, conteo.c.ultima)
        .outerjoin(conteo, conteo.c.site_id == Site.site_id)
        .order_by(Site.created_at, Site.site_id)).all()
    items = [SiteListItemOut(**SiteOut.model_validate(s).model_dump(), views_total=total or 0, last_view_at=ultima) for s, total, ultima in filas]
    return Envelope[Page[SiteListItemOut]](message="Sitios obtenidos exitosamente", data=Page(items=items, next_cursor=None))


@router.post("", status_code=201, response_model=Envelope[SiteOut], summary="Agregar un sitio a monitorear",
             responses={**ERROR_409, **ERROR_422})
def crear_sitio(datos: SiteIn, idempotency_key: str = CLAVE_IDEMPOTENCIA, db: Session = Depends(get_db)):
    """409 si el dominio ya está registrado. Acepta también una dirección completa (https://sitio.com/pagina)."""
    h = idem.huella("POST", "/api/v1/sites", datos.model_dump(mode="json"))
    repetida = idem.buscar_repetida(db, idempotency_key, h)
    if repetida:
        return repetida

    reglas.exigir_dominio_libre(db, datos.domain)
    sitio = Site(name=datos.name, domain=datos.domain, color=datos.color.lower(), is_active=datos.is_active)
    with catalogo.conflicto_unico(db, *CONFLICTO):
        db.add(sitio)
        db.commit()
    envelope = Envelope[SiteOut](message="Sitio agregado exitosamente", data=SiteOut.model_validate(sitio))
    idem.guardar_y_confirmar(db, idempotency_key, h, 201, envelope)
    return envelope


@router.put("/{site_id}", response_model=Envelope[SiteOut], summary="Actualización de un sitio",
            responses={**ERROR_404, **ERROR_409, **ERROR_422})
def actualizar_sitio(site_id: str, datos: SiteUpdateIn, db: Session = Depends(get_db)):
    """PUT reemplaza el sitio completo. `is_active: false` pausa el monitoreo (las visitas anteriores se conservan)."""
    sitio = reglas.buscar_sitio(db, site_id)
    reglas.exigir_dominio_libre(db, datos.domain, excepto_id=sitio.site_id)
    with catalogo.conflicto_unico(db, *CONFLICTO):
        sitio.name = datos.name
        sitio.domain = datos.domain
        sitio.color = datos.color.lower()
        sitio.is_active = datos.is_active
        sitio.updated_at = ahora_utc()
        db.commit()
    return Envelope[SiteOut](message="Sitio actualizado exitosamente", data=SiteOut.model_validate(sitio))


@router.delete("/{site_id}", response_model=Envelope[SiteDeletedOut], summary="Eliminación de un sitio",
               responses=ERROR_404)
def eliminar_sitio(site_id: str, db: Session = Depends(get_db)):
    """Borra el sitio y TODAS sus visitas (no se puede deshacer). Para conservar el historial, mejor pausa el sitio."""
    sitio = reglas.buscar_sitio(db, site_id)
    borradas = db.execute(delete(PageView).where(PageView.site_id == sitio.site_id)).rowcount or 0
    db.delete(sitio)
    db.commit()
    return Envelope[SiteDeletedOut](message="Sitio eliminado exitosamente",
                                    data=SiteDeletedOut(site_id=site_id, views_deleted=borradas))
