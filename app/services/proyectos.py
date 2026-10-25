"""Reglas de negocio de los proyectos (Paso 3: invariantes). Los endpoints llaman a estas funciones."""
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Project, ProjectTag, TechStackItem

CODIGO_CONTRATO = "PUBLISH_CONTRACT_INCOMPLETE"


def buscar_proyecto(db: Session, project_id: str) -> Project:
    proyecto = db.get(Project, project_id)
    if proyecto is None:
        raise ApiError(404, "PROJECT_NOT_FOUND", f"No existe un proyecto con el project_id '{project_id}'")
    return proyecto


def exigir_slug_libre(db: Session, slug: str, excepto_id: str | None = None) -> None:
    """Invariante 4: el slug es único en todo el sistema (incluidos los ARCHIVADO)."""
    consulta = select(Project.project_id).where(Project.slug == slug)
    if excepto_id:
        consulta = consulta.where(Project.project_id != excepto_id)
    if db.scalar(consulta) is not None:
        raise ApiError(409, "SLUG_ALREADY_EXISTS", f"El slug '{slug}' ya está en uso",
                       [{"field": "slug", "issue": "Ya existe un proyecto con ese slug (incluidos los archivados)"}])


@contextmanager
def conflicto_de_slug(db: Session, slug: str):
    """Si dos peticiones intentan crear el mismo slug a la vez, la base de datos lo detecta aquí."""
    try:
        yield
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "SLUG_ALREADY_EXISTS", f"El slug '{slug}' ya está en uso",
                       [{"field": "slug", "issue": "Ya existe un proyecto con ese slug (incluidos los archivados)"}])


def cargar_stack(db: Session, stack_ids: list[str]) -> list[TechStackItem]:
    """Invariante 7: cada stack_id debe existir en el catálogo."""
    if not stack_ids:
        return []
    encontrados = db.scalars(select(TechStackItem).where(TechStackItem.stack_id.in_(stack_ids))).all()
    faltan = [i for i in stack_ids if i not in {e.stack_id for e in encontrados}]
    if faltan:
        raise ApiError(422, "STACK_ID_NOT_FOUND", "Algún stack_id no existe en el catálogo de lenguajes y herramientas",
                       [{"field": "stack_ids", "issue": f"No existe: {identificador}"} for identificador in faltan])
    return list(encontrados)


def faltantes_del_contrato(short_description, description, project_date, stack_items) -> list[dict]:
    """Invariante 5 (contrato de publicación): qué le falta al proyecto para poder estar PUBLICADO."""
    faltan = []
    if not (short_description or "").strip():
        faltan.append({"field": "short_description", "issue": "Campo obligatorio para publicar"})
    if not (description or "").strip():
        faltan.append({"field": "description", "issue": "Campo obligatorio para publicar"})
    if project_date is None:
        faltan.append({"field": "project_date", "issue": "Campo obligatorio para publicar"})
    if not any(item.category == "LENGUAJE" for item in stack_items):
        faltan.append({"field": "stack_ids", "issue": "Se requiere al menos un elemento de categoría LENGUAJE"})
    return faltan


def exigir_contrato(short_description, description, project_date, stack_items, mensaje: str) -> None:
    faltan = faltantes_del_contrato(short_description, description, project_date, stack_items)
    if faltan:
        raise ApiError(422, CODIGO_CONTRATO, mensaje, faltan)


def reemplazar_contenido(db: Session, proyecto: Project, datos, stack: list[TechStackItem]) -> None:
    """PUT reemplaza el recurso completo: lo opcional que no se envía se borra."""
    proyecto.title = datos.title
    proyecto.slug = datos.slug
    proyecto.short_description = datos.short_description
    proyecto.description = datos.description
    proyecto.project_date = datos.project_date
    proyecto.repo_url = datos.repo_url
    proyecto.demo_url = datos.demo_url
    proyecto.is_featured = datos.is_featured
    proyecto.stack_items = stack
    # Etiquetas nuevas en lugar de las viejas: SQLAlchemy borra las que sobran y actualiza/inserta el resto.
    proyecto.tag_rows.clear()
    proyecto.tag_rows.extend(ProjectTag(position=i, tag=t) for i, t in enumerate(datos.tags, start=1))
