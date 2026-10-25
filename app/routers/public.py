"""Lecturas públicas (/api/v1/public/*): no requieren autenticación y se pueden cachear.

Endpoints de la especificación v2 que implementa este archivo:
   9. GET /api/v1/public/projects            Consulta y listado público de proyectos
  10. GET /api/v1/public/projects/{slug}     Obtención pública de proyecto por slug
  12. GET /api/v1/public/certificates        Listado público de certificados
  16. GET /api/v1/public/tech-stack          Listado público de lenguajes y herramientas
  19. GET /api/v1/public/profile             Consulta pública del perfil
"""
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import ApiError
from app.http_cache import con_cache
from app.models import Certificate, Profile, Project, ProjectTag, TechStackItem
from app.pagination import Clave, paginar
from app.routers.comunes import CURSOR, ERROR_404, ERROR_422, LIMITE
from app.schemas import (
    CertificateOut, Envelope, Page, ProfileOut, ProjectCardOut,
    ProjectDetailOut, StackCategory, TechStackOut,
)

router = APIRouter(prefix="/api/v1/public", tags=["Lecturas públicas"])



# ------------------------------------------------------------------ 9. proyectos (lista)
@router.get(
    "/projects",
    response_model=Envelope[Page[ProjectCardOut]],
    summary="9. Consulta y listado público de proyectos",
    responses=ERROR_422,
)
def listar_proyectos_publicos(
    request: Request, response: Response,
    is_featured: bool | None = Query(None, description="Solo destacados (true) o no destacados (false)"),
    tag: str | None = Query(None, description="Filtra por etiqueta (sin distinguir mayúsculas)"),
    cursor: str | None = CURSOR,
    limit: int = LIMITE,
    db: Session = Depends(get_db),
):
    """Solo retorna proyectos en estado PUBLICADO, ordenados por `project_date` descendente
    (con `published_at` como desempate)."""
    consulta = select(Project).where(Project.status == "PUBLICADO")
    if is_featured is not None:
        consulta = consulta.where(Project.is_featured == is_featured)
    if tag:
        consulta = consulta.where(Project.tag_rows.any(func.lower(ProjectTag.tag) == tag.lower()))

    claves = [
        Clave(Project.project_date, "project_date", "date", descendente=True),
        Clave(Project.published_at, "published_at", "datetime", descendente=True),
        Clave(Project.project_id, "project_id", "str", descendente=True),
    ]
    filas, siguiente = paginar(db, consulta, claves, cursor, limit)
    envelope = Envelope[Page[ProjectCardOut]](
        message="Listado de proyectos obtenido exitosamente",
        data=Page[ProjectCardOut](items=[ProjectCardOut.model_validate(f) for f in filas], next_cursor=siguiente),
    )
    return con_cache(request, response, envelope)


# ------------------------------------------------------------------ 10. proyecto por slug
@router.get(
    "/projects/{slug}",
    response_model=Envelope[ProjectDetailOut],
    summary="10. Obtención pública de proyecto por slug",
    responses=ERROR_404,
)
def obtener_proyecto_publico(
    slug: str, request: Request, response: Response, db: Session = Depends(get_db),
):
    """404 si el slug no existe **o** si el proyecto no está PUBLICADO (borradores y archivados no se ven)."""
    proyecto = db.scalar(select(Project).where(Project.slug == slug, Project.status == "PUBLICADO"))
    if proyecto is None:
        raise ApiError(404, "PROJECT_NOT_FOUND", f"No existe un proyecto publicado con el slug '{slug}'")
    envelope = Envelope[ProjectDetailOut](
        message="Proyecto obtenido exitosamente", data=ProjectDetailOut.model_validate(proyecto),
    )
    return con_cache(request, response, envelope)


# ------------------------------------------------------------------ 12. certificados
@router.get(
    "/certificates",
    response_model=Envelope[Page[CertificateOut]],
    summary="12. Listado público de certificados",
    responses=ERROR_422,
)
def listar_certificados_publicos(
    request: Request, response: Response,
    cursor: str | None = CURSOR, limit: int = LIMITE, db: Session = Depends(get_db),
):
    """Los certificados no tienen borrador: todos son públicos. Orden: `issued_at` descendente
    (si coinciden, por título para que el orden sea siempre el mismo)."""
    claves = [
        Clave(Certificate.issued_at, "issued_at", "date", descendente=True),
        Clave(Certificate.title, "title", "str"),
        Clave(Certificate.certificate_id, "certificate_id", "str"),
    ]
    filas, siguiente = paginar(db, select(Certificate), claves, cursor, limit)
    envelope = Envelope[Page[CertificateOut]](
        message="Listado de certificados obtenido exitosamente",
        data=Page[CertificateOut](items=[CertificateOut.model_validate(f) for f in filas], next_cursor=siguiente),
    )
    return con_cache(request, response, envelope)


# ------------------------------------------------------------------ 16. lenguajes y herramientas
@router.get(
    "/tech-stack",
    response_model=Envelope[Page[TechStackOut]],
    summary="16. Listado público de lenguajes y herramientas",
    responses=ERROR_422,
)
def listar_tech_stack_publico(
    request: Request, response: Response,
    category: StackCategory | None = Query(None, description="LENGUAJE, FRAMEWORK, BASE_DE_DATOS, NUBE o HERRAMIENTA"),
    show_in_profile: bool | None = Query(None, description="true = solo los que aparecen en la sección Lenguajes y herramientas"),
    cursor: str | None = CURSOR, limit: int = LIMITE, db: Session = Depends(get_db),
):
    """Orden: `display_order` ascendente y luego `name`."""
    consulta = select(TechStackItem)
    if category is not None:
        consulta = consulta.where(TechStackItem.category == category.value)
    if show_in_profile is not None:
        consulta = consulta.where(TechStackItem.show_in_profile == show_in_profile)
    claves = [
        Clave(TechStackItem.display_order, "display_order", "int"),
        Clave(TechStackItem.name, "name", "str"),
    ]
    filas, siguiente = paginar(db, consulta, claves, cursor, limit)
    envelope = Envelope[Page[TechStackOut]](
        message="Listado de lenguajes y herramientas obtenido exitosamente",
        data=Page[TechStackOut](items=[TechStackOut.model_validate(f) for f in filas], next_cursor=siguiente),
    )
    return con_cache(request, response, envelope)


# ------------------------------------------------------------------ 19. perfil
@router.get(
    "/profile",
    response_model=Envelope[ProfileOut],
    summary="19. Consulta pública del perfil",
    responses=ERROR_404,
)
def obtener_perfil_publico(request: Request, response: Response, db: Session = Depends(get_db)):
    """Existe exactamente un perfil (Invariante 1 de Profile)."""
    perfil = db.scalar(select(Profile).limit(1))
    if perfil is None:
        raise ApiError(404, "PROFILE_NOT_FOUND", "Todavía no hay un perfil cargado; ejecuta python -m app.seed")
    envelope = Envelope[ProfileOut](message="Perfil obtenido exitosamente", data=ProfileOut.model_validate(perfil))
    return con_cache(request, response, envelope)
