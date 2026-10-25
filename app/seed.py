"""Carga en la base el contenido actual del blog: 3 proyectos, 5 certificados, el catálogo de
lenguajes y herramientas, y el perfil.

Uso:
    python -m app.seed            crea las tablas y siembra si la base está vacía
    python -m app.seed --reset    borra todo y vuelve a sembrar

Los archivos (PDF, imágenes) se publican bajo SITE_BASE_URL (ver app/config.py); mientras no
tengas el dominio real, queda el de ejemplo https://santosgonzalez.dev.
"""
import argparse
from datetime import date, datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.config import SITE_BASE_URL
from app.database import Base, SessionLocal, engine
from app.models import Certificate, Profile, Project, ProjectTag, TechStackItem

# --------------------------------------------------------------------------- datos del blog
# (nombre, categoría, logo, ¿aparece en "Lenguajes y herramientas" de Acerca?)
# El orden de esta lista es el display_order. Los 6 primeros son los de la sección Acerca.
CATALOGO = [
    ("Java", "LENGUAJE", "Imagenes/Java.png", True),
    ("C++", "LENGUAJE", "Imagenes/C++.jpg", True),
    ("JavaScript", "LENGUAJE", "Imagenes/JavaScript.jpg", True),
    ("CSS", "LENGUAJE", "Imagenes/Css.jpg", True),
    ("HTML", "LENGUAJE", "Imagenes/Html.jpg", True),
    ("Kotlin", "LENGUAJE", "Imagenes/Kotlin.png", True),
    ("SQL", "LENGUAJE", None, False),
    ("Figma Site", "HERRAMIENTA", None, False),
    ("AWS (EC2)", "NUBE", None, False),
    ("MariaDB", "BASE_DE_DATOS", None, False),
    ("Postman", "HERRAMIENTA", None, False),
    ("Android Studio", "HERRAMIENTA", None, False),
    ("Room", "FRAMEWORK", None, False),
    ("SharedPreferences", "FRAMEWORK", None, False),
    ("TextToSpeech", "FRAMEWORK", None, False),
    ("HTML5", "FRAMEWORK", None, False),
]

PROYECTOS = [
    {
        "slug": "lawpocket",
        "title": "LawPocket: gestión legal en la nube",
        "project_date": "2026-07-15",
        "tags": ["LawPocket", "Proyecto Integrador"],
        "short_description": "Sistema de gestión legal para digitalizar el control de casos de un despacho, con paneles diferenciados por rol.",
        "description": "Aplicación web para que un despacho legal digitalice el control de sus casos, con un panel de administrador y otro de abogado/asistente para gestionar clientes y expedientes.",
        "demo_url": "https://law-pocket-integrador.vercel.app",
        "stack": ["Java", "SQL", "Figma Site", "AWS (EC2)", "MariaDB", "Postman"],
    },
    {
        "slug": "math-english-quest",
        "title": "Math & English Quest",
        "project_date": "2026-06-20",
        "tags": ["Android", "Proyecto personal"],
        "short_description": "App educativa para que niños de primaria practiquen matemáticas e inglés con un sistema de dado, vidas y rachas.",
        "description": "App educativa dirigida a niños de 6 a 15 años para practicar matemáticas e inglés mediante un sistema de dado, vidas y rachas, con distintos modos de juego.",
        "demo_url": "https://math-english-quest.vercel.app",
        "stack": ["Kotlin", "JavaScript", "Android Studio", "Room", "SharedPreferences", "TextToSpeech"],
    },
    {
        "slug": "series-de-taylor",
        "title": "Series de Taylor",
        "project_date": "2026-05-10",
        "tags": ["Cálculo", "Proyecto de clase"],
        "short_description": "Visualización de cómo un polinomio de Taylor se aproxima a una función real, hecha para la clase de Cálculo.",
        "description": "Actividad de la clase de Cálculo para visualizar, de forma gráfica, cómo un polinomio de Taylor se acerca cada vez más a una función real conforme se agregan términos.",
        "demo_url": "https://serie-de-taylor-one.vercel.app",
        "stack": ["JavaScript", "HTML5"],
    },
]

# (título, institución, fecha de emisión, nombre base del archivo en PDF/ e Imagenes/Certificados/)
CERTIFICADOS = [
    ("Operating Systems Support", "Cisco Networking Academy", "2026-03-16", "OperatingSystemsSupport"),
    ("Introduction to Internet of Things", "Cisco Networking Academy", "2025-12-01", "InternetOfThings"),
    ("AWS Academy Graduate — Cloud Foundations", "Amazon Web Services (AWS)", "2025-10-26", "AWSCloudFoundations"),
    ("Networking Basics", "Cisco Networking Academy", "2025-10-26", "NetworkingBasics"),
    ("Curso Profesional de Desarrollo en C++", "Azul School", "2025-10-25", "CursoCpp"),
]

PERFIL = {
    "full_name": "Santos Enoch González Pérez",
    "job_title": "Estudiante de Ingeniería en Desarrollo de Software",
    "tagline": "Estudiante de Ingeniería en Desarrollo de Software, enfocado en aplicaciones web y móviles.",
    "bio": "Estudiante de Ingeniería en Desarrollo de Software, especializado en crear aplicaciones robustas, eficientes y centradas en el usuario. Me apasiona resolver problemas complejos y diseñar videojuegos.",
    "photo_url": f"{SITE_BASE_URL}/Imagenes/Santos.jpeg",
    "email": "253390@it2id.upchiapas.edu.mx",
    "phone": "960-117-7755",
    "github_url": "https://github.com/EnochGonzalez",
}


# --------------------------------------------------------------------------- siembra
def sembrar(db: Session) -> dict:
    """Inserta el contenido del blog. Devuelve cuántas filas creó de cada tipo."""
    catalogo: dict[str, TechStackItem] = {}
    for orden, (nombre, categoria, logo, visible) in enumerate(CATALOGO, start=1):
        item = TechStackItem(
            name=nombre, category=categoria, show_in_profile=visible, display_order=orden,
            logo_url=f"{SITE_BASE_URL}/{logo}" if logo else None,
        )
        db.add(item)
        catalogo[nombre] = item

    for p in PROYECTOS:
        fecha = date.fromisoformat(p["project_date"])
        db.add(Project(
            slug=p["slug"], title=p["title"], short_description=p["short_description"],
            description=p["description"], project_date=fecha, demo_url=p["demo_url"],
            is_featured=False, status="PUBLICADO",
            # Fecha de publicación de ejemplo: el mediodía (UTC) del día del proyecto.
            published_at=datetime.combine(fecha, time(12, 0), tzinfo=timezone.utc),
            stack_items=[catalogo[nombre] for nombre in p["stack"]],
            tag_rows=[ProjectTag(position=i, tag=t) for i, t in enumerate(p["tags"], start=1)],
        ))

    for titulo, institucion, fecha, base in CERTIFICADOS:
        db.add(Certificate(
            title=titulo, issuer=institucion, issued_at=date.fromisoformat(fecha),
            pdf_url=f"{SITE_BASE_URL}/PDF/{base}.pdf",
            image_url=f"{SITE_BASE_URL}/Imagenes/Certificados/{base}.jpg",
        ))

    db.add(Profile(**PERFIL))
    db.commit()
    return {"proyectos": len(PROYECTOS), "certificados": len(CERTIFICADOS),
            "elementos de catálogo": len(CATALOGO), "perfil": 1}


def base_vacia(db: Session) -> bool:
    """True si no hay ni proyectos, ni certificados, ni catálogo, ni perfil (un servidor recién creado)."""
    return not any(db.scalar(select(func.count()).select_from(modelo)) for modelo in (models.Project, models.Certificate, models.TechStackItem, models.Profile))


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga el contenido actual del blog en la base de datos.")
    parser.add_argument("--reset", action="store_true", help="borra todo antes de sembrar")
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(models.Project)):
            print("La base ya tiene datos. Usa  python -m app.seed --reset  para borrarlos y sembrar de nuevo.")
            return
        resumen = sembrar(db)
    print("Base sembrada:", ", ".join(f"{cantidad} {nombre}" for nombre, cantidad in resumen.items()))


if __name__ == "__main__":
    main()
