"""Tablas de la base de datos (Paso 3 de la especificación: entidades e invariantes)."""
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index,
    Integer, String, Table, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.ids import nuevo_id


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


# Relación muchos-a-muchos Project <-> TechStackItem.
# RESTRICT cumple el invariante: un elemento referenciado por un proyecto no se puede eliminar.
proyecto_stack = Table(
    "project_stack", Base.metadata,
    Column("project_id", ForeignKey("projects.project_id", ondelete="CASCADE"), primary_key=True),
    Column("stack_id", ForeignKey("tech_stack_items.stack_id", ondelete="RESTRICT"), primary_key=True),
)


class TechStackItem(Base):
    __tablename__ = "tech_stack_items"

    stack_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    name: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(20))
    logo_url: Mapped[str | None] = mapped_column(String(300))
    show_in_profile: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc, onupdate=ahora_utc)

    __table_args__ = (
        CheckConstraint(
            "category IN ('LENGUAJE','FRAMEWORK','BASE_DE_DATOS','NUBE','HERRAMIENTA')",
            name="ck_stack_category",
        ),
    )


# Invariante 1 de TechStackItem: name único sin distinguir mayúsculas.
Index("uq_tech_stack_name_ci", func.lower(TechStackItem.name), unique=True)


class Project(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    title: Mapped[str] = mapped_column(String(120))
    # Invariante 4: slug único en todo el sistema (incluye proyectos ARCHIVADO).
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    # Opcionales en BORRADOR; obligatorios para publicar (contrato de publicación).
    short_description: Mapped[str | None] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text)
    project_date: Mapped[date | None] = mapped_column(Date)
    repo_url: Mapped[str | None] = mapped_column(String(300))
    demo_url: Mapped[str | None] = mapped_column(String(300))
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(12), default="BORRADOR", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc, onupdate=ahora_utc)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    stack_items: Mapped[list[TechStackItem]] = relationship(secondary=proyecto_stack, lazy="selectin")
    tag_rows: Mapped[list["ProjectTag"]] = relationship(
        back_populates="project", cascade="all, delete-orphan",
        order_by="ProjectTag.position", lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("status IN ('BORRADOR','PUBLICADO','ARCHIVADO')", name="ck_project_status"),
    )

    # Vistas de solo lectura que usan los esquemas de salida.
    @property
    def tags(self) -> list[str]:
        return [fila.tag for fila in self.tag_rows]

    @property
    def stack_ids(self) -> list[str]:
        return [item.stack_id for item in self.tech_stack]

    @property
    def tech_stack(self) -> list[TechStackItem]:
        return sorted(self.stack_items, key=lambda i: (i.display_order, i.name.lower()))


class ProjectTag(Base):
    """Etiquetas de un proyecto (0 a 5), conservando el orden en que se escribieron."""
    __tablename__ = "project_tags"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag: Mapped[str] = mapped_column(String(30))

    project: Mapped[Project] = relationship(back_populates="tag_rows")


class Certificate(Base):
    __tablename__ = "certificates"

    certificate_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    title: Mapped[str] = mapped_column(String(120))
    issuer: Mapped[str] = mapped_column(String(80))
    issued_at: Mapped[date] = mapped_column(Date)
    pdf_url: Mapped[str] = mapped_column(String(300))
    image_url: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc, onupdate=ahora_utc)

    # Invariante 1 de Certificate: (title, issuer, issued_at) único.
    __table_args__ = (UniqueConstraint("title", "issuer", "issued_at", name="uq_certificate_title_issuer_date"),)


class Profile(Base):
    """Invariante 1: existe exactamente un perfil (la API no lo crea ni lo elimina)."""
    __tablename__ = "profile"

    profile_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    full_name: Mapped[str] = mapped_column(String(80))
    job_title: Mapped[str] = mapped_column(String(80))
    tagline: Mapped[str] = mapped_column(String(160))
    bio: Mapped[str] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(String(300))
    email: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(30))
    github_url: Mapped[str | None] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc, onupdate=ahora_utc)


class IdempotencyKey(Base):
    """Respuesta guardada de una operación que llegó con Idempotency-Key (se conserva 24 h)."""
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))      # huella de método + ruta + cuerpo
    status_code: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)                   # la respuesta original, en JSON
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
