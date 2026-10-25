"""Esquemas Pydantic: aquí vive el Diccionario de Tipos (Paso 4 de la especificación).

Convención del proyecto, igual que en la práctica guiada de FastAPI:
  - XxxIn  = lo que el cliente envía (validado contra el Diccionario de Tipos).
  - XxxOut = lo que la API devuelve. response_model descarta todo campo que no esté
             aquí (por ejemplo status o created_at en las lecturas públicas).
"""
from datetime import date, datetime, timezone
from enum import Enum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints, field_validator

T = TypeVar("T")


# ----------------------------------------------------------------- enumeradores
class ProjectStatus(str, Enum):
    BORRADOR = "BORRADOR"
    PUBLICADO = "PUBLICADO"
    ARCHIVADO = "ARCHIVADO"


class StackCategory(str, Enum):
    LENGUAJE = "LENGUAJE"
    FRAMEWORK = "FRAMEWORK"          # frameworks, librerías y APIs
    BASE_DE_DATOS = "BASE_DE_DATOS"
    NUBE = "NUBE"
    HERRAMIENTA = "HERRAMIENTA"


# ----------------------------------------------------------------- tipos reutilizables
def _a_iso_utc(valor: datetime) -> str:
    """Estampa de tiempo ISO 8601 UTC, p. ej. 2026-10-24T14:00:00Z."""
    if valor.tzinfo is None:                      # SQLite devuelve fechas sin zona: son UTC
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


FechaHoraUTC = Annotated[datetime, PlainSerializer(_a_iso_utc, return_type=str, when_used="json")]

Uuid7 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")]
Slug = Annotated[str, StringConstraints(max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
UrlHttps = Annotated[str, StringConstraints(max_length=300, pattern=r"^https://\S+$")]
Titulo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
Etiqueta = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=30)]


# ----------------------------------------------------------------- envoltorios de respuesta
class Page(BaseModel, Generic[T]):
    """Lista paginada por cursor: items[] y next_cursor (null en la última página)."""
    items: list[T]
    next_cursor: str | None = None


class Envelope(BaseModel, Generic[T]):
    """Toda respuesta exitosa se entrega así: { status, message, data }."""
    status: Literal["success"] = "success"
    message: str
    data: T


class ErrorDetail(BaseModel):
    field: str
    issue: str


class ErrorEnvelope(BaseModel):
    """Toda respuesta de error se entrega así: { status, code, message, details[] }."""
    status: Literal["error"] = "error"
    code: str
    message: str
    details: list[ErrorDetail] = []


# ----------------------------------------------------------------- ENTRADA (XxxIn)
class _ProjectBaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Titulo
    slug: Slug
    # Opcionales mientras sea BORRADOR; obligatorios para publicar (Invariante 5 de Project).
    short_description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)] | None = None
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=2000)] | None = None
    project_date: date | None = None
    stack_ids: list[Uuid7] = Field(default_factory=list)
    tags: list[Etiqueta] = Field(default_factory=list, max_length=5)
    repo_url: UrlHttps | None = None
    demo_url: UrlHttps | None = None

    @field_validator("stack_ids")
    @classmethod
    def _stack_sin_repetidos(cls, valor):
        if len(set(valor)) != len(valor):
            raise ValueError("stack_ids contiene elementos repetidos")
        return valor

    @field_validator("tags")
    @classmethod
    def _tags_sin_repetidos(cls, valor):
        if len({t.casefold() for t in valor}) != len(valor):
            raise ValueError("tags contiene etiquetas repetidas")
        return valor


class ProjectCreateIn(_ProjectBaseIn):
    is_featured: bool = False                     # por defecto false al crear


class ProjectUpdateIn(_ProjectBaseIn):
    is_featured: bool                             # PUT reemplaza el recurso completo: es obligatorio


class CertificateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Titulo
    issuer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
    issued_at: date
    pdf_url: UrlHttps
    image_url: UrlHttps

    @field_validator("issued_at")
    @classmethod
    def _no_futura(cls, valor):
        if valor > date.today():
            raise ValueError("issued_at no puede ser una fecha futura")
        return valor


class TechStackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    category: StackCategory
    logo_url: UrlHttps | None = None
    show_in_profile: bool = False
    display_order: Annotated[int, Field(ge=1)] | None = None   # si se omite, la API asigna la última posición


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=80)]
    job_title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=80)]
    tagline: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    bio: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=1000)]
    photo_url: UrlHttps | None = None
    email: Annotated[str, StringConstraints(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
    phone: Annotated[str, StringConstraints(pattern=r"^\+?[0-9][0-9 -]{6,18}$")] | None = None
    github_url: Annotated[str, StringConstraints(pattern=r"^https://github\.com/[A-Za-z0-9-]+/?$")] | None = None


# ----------------------------------------------------------------- SALIDA (XxxOut)
class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)       # permite construirlos desde filas de la base


class TechStackBriefOut(_Out):
    """Versión corta que va dentro de cada proyecto (tech_stack[])."""
    stack_id: str
    name: str
    category: StackCategory


class TechStackOut(_Out):
    stack_id: str
    name: str
    category: StackCategory
    logo_url: str | None
    show_in_profile: bool
    display_order: int


class ProjectCardOut(_Out):
    """Tarjeta del listado público (endpoint 9)."""
    project_id: str
    title: str
    slug: str
    short_description: str
    project_date: date
    tags: list[str]
    tech_stack: list[TechStackBriefOut]
    repo_url: str | None
    demo_url: str | None
    is_featured: bool
    published_at: FechaHoraUTC


class ProjectDetailOut(_Out):
    """Detalle público de un proyecto (endpoint 10)."""
    project_id: str
    title: str
    slug: str
    short_description: str
    description: str
    project_date: date
    tags: list[str]
    tech_stack: list[TechStackBriefOut]
    repo_url: str | None
    demo_url: str | None
    published_at: FechaHoraUTC


class CertificateOut(_Out):
    certificate_id: str
    title: str
    issuer: str
    issued_at: date
    pdf_url: str
    image_url: str


class ProfileOut(_Out):
    profile_id: str
    full_name: str
    job_title: str
    tagline: str
    bio: str
    photo_url: str | None
    email: str
    phone: str | None
    github_url: str | None
    updated_at: FechaHoraUTC


# ================================================================= BLOQUE 2: login y administración
class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[str, StringConstraints(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
    password: Annotated[str, StringConstraints(min_length=8, max_length=128)]


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int                                   # segundos de vigencia


class ProjectCreatedOut(_Out):
    """Endpoint 2."""
    project_id: str
    status: ProjectStatus
    slug: str
    created_at: FechaHoraUTC


class ProjectAdminItemOut(_Out):
    """Una fila del listado administrativo (endpoint 3): incluye borradores y archivados."""
    project_id: str
    title: str
    slug: str
    status: ProjectStatus
    project_date: date | None
    is_featured: bool
    updated_at: FechaHoraUTC


class ProjectAdminDetailOut(_Out):
    """Endpoint 4: todos los campos del proyecto, en cualquier estado."""
    project_id: str
    title: str
    slug: str
    short_description: str | None
    description: str | None
    project_date: date | None
    stack_ids: list[str]
    tech_stack: list[TechStackBriefOut]
    tags: list[str]
    repo_url: str | None
    demo_url: str | None
    is_featured: bool
    status: ProjectStatus
    created_at: FechaHoraUTC
    updated_at: FechaHoraUTC
    published_at: FechaHoraUTC | None


class ProjectUpdatedOut(BaseModel):
    """Endpoint 5."""
    project_id: str
    status: ProjectStatus
    updated_at: FechaHoraUTC
    recompilation_triggered: bool


class ProjectPublishedOut(BaseModel):
    """Endpoint 6."""
    project_id: str
    status: ProjectStatus
    published_at: FechaHoraUTC
    recompilation_triggered: bool


class ProjectArchivedOut(BaseModel):
    """Endpoint 7."""
    project_id: str
    status: ProjectStatus
    updated_at: FechaHoraUTC
    recompilation_triggered: bool
