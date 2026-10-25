"""Reglas de negocio de certificados y del catálogo de lenguajes y herramientas (Paso 3: invariantes)."""
from contextlib import contextmanager

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.errors import ApiError
from app.models import Certificate, Project, TechStackItem
from app.storage import Almacen


@contextmanager
def conflicto_unico(db: Session, codigo: str, mensaje: str, campo: str):
    """Si dos peticiones chocan a la vez, la base de datos lo detecta con su llave única y se responde 409."""
    try:
        yield
    except IntegrityError:
        db.rollback()
        raise ApiError(409, codigo, mensaje, [{"field": campo, "issue": mensaje}])


# ------------------------------------------------------------------ certificados
def buscar_certificado(db: Session, certificate_id: str) -> Certificate:
    certificado = db.get(Certificate, certificate_id)
    if certificado is None:
        raise ApiError(404, "CERTIFICATE_NOT_FOUND", f"No existe un certificado con el certificate_id '{certificate_id}'")
    return certificado


def exigir_certificado_unico(db: Session, datos, excepto_id: str | None = None) -> None:
    """Invariante 1 de Certificate: (title, issuer, issued_at) es único."""
    consulta = select(Certificate.certificate_id).where(
        Certificate.title == datos.title, Certificate.issuer == datos.issuer, Certificate.issued_at == datos.issued_at)
    if excepto_id:
        consulta = consulta.where(Certificate.certificate_id != excepto_id)
    if db.scalar(consulta) is not None:
        raise ApiError(409, "CERTIFICATE_ALREADY_EXISTS", "Ya existe un certificado con el mismo título, institución y fecha",
                       [{"field": "title", "issue": "Ya existe (mismo title, issuer e issued_at)"}])


def exigir_urls_de_archivo(almacen: Almacen, **urls: str) -> None:
    """Invariante 3 de Certificate: las URLs deben venir del servicio de archivos.

    Se aceptan las del almacén (POST /api/v1/files) y las de tu propio blog (SITE_BASE_URL), donde ya viven
    los PDF e imágenes que tenías antes de existir el CMS."""
    origenes = [almacen.base_url.rstrip("/") + "/", config.SITE_BASE_URL.rstrip("/") + "/"]
    problemas = [{"field": campo, "issue": "La URL debe venir de POST /api/v1/files (o de los archivos de tu blog)"}
                 for campo, url in urls.items() if not any(url.startswith(origen) for origen in origenes)]
    if problemas:
        raise ApiError(422, "FILE_URL_NOT_ALLOWED", "Alguna URL no proviene del servicio de archivos", problemas)


# ------------------------------------------------------------------ lenguajes y herramientas
def buscar_stack(db: Session, stack_id: str) -> TechStackItem:
    item = db.get(TechStackItem, stack_id)
    if item is None:
        raise ApiError(404, "STACK_NOT_FOUND", f"No existe un elemento del catálogo con el stack_id '{stack_id}'")
    return item


def exigir_nombre_libre(db: Session, nombre: str, excepto_id: str | None = None) -> None:
    """Invariante 1 de TechStackItem: name único sin distinguir mayúsculas."""
    consulta = select(TechStackItem.stack_id).where(func.lower(TechStackItem.name) == nombre.lower())
    if excepto_id:
        consulta = consulta.where(TechStackItem.stack_id != excepto_id)
    if db.scalar(consulta) is not None:
        raise ApiError(409, "STACK_NAME_ALREADY_EXISTS", f"Ya existe un elemento llamado '{nombre}'",
                       [{"field": "name", "issue": "Ya existe (sin distinguir mayúsculas)"}])


def siguiente_orden(db: Session, excepto_id: str | None = None) -> int:
    """Invariante 4: si display_order se omite, se asigna la última posición."""
    consulta = select(func.max(TechStackItem.display_order))
    if excepto_id:
        consulta = consulta.where(TechStackItem.stack_id != excepto_id)
    return (db.scalar(consulta) or 0) + 1


def proyectos_que_lo_usan(db: Session, stack_id: str, solo_publicados: bool = False) -> list[Project]:
    consulta = select(Project).where(Project.stack_items.any(TechStackItem.stack_id == stack_id))
    if solo_publicados:
        consulta = consulta.where(Project.status == "PUBLICADO")
    return list(db.scalars(consulta.order_by(Project.slug)).all())


def cambia_el_blog(db: Session, item: TechStackItem, era_visible: bool) -> bool:
    """¿Un cambio en este elemento se nota en el blog? Sí si aparece (o aparecía) en Lenguajes y herramientas,
    o si lo usa algún proyecto PUBLICADO. Si no, no hace falta avisar al pipeline."""
    return era_visible or item.show_in_profile or bool(proyectos_que_lo_usan(db, item.stack_id, solo_publicados=True))
