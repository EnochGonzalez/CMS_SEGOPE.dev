"""Pruebas del Diccionario de Tipos (esquemas XxxIn) y de los identificadores UUIDv7."""
import time
import uuid
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.ids import nuevo_id, uuid7
from app.schemas import CertificateIn, ProfileIn, ProjectCreateIn, ProjectUpdateIn, TechStackIn, TechStackUpdateIn
from app.seed import CATALOGO, CERTIFICADOS, PERFIL, PROYECTOS, SITE_BASE_URL

UUID_VALIDO = "0192a3c2-7e01-7f12-8a23-1b34c45d5678"
MINIMO = {"title": "Mi proyecto", "slug": "mi-proyecto"}


# ------------------------------------------------------------------ UUIDv7
def test_uuid7_tiene_version_7_y_formato_de_36_caracteres():
    u = uuid7()
    assert u.version == 7 and u.variant == uuid.RFC_4122
    assert len(nuevo_id()) == 36


def test_uuid7_se_ordena_por_fecha_de_creacion():
    primero = str(uuid7())
    time.sleep(0.005)
    assert primero < str(uuid7())


# ------------------------------------------------------------------ Project
def test_borrador_minimo_solo_pide_titulo_y_slug():
    p = ProjectCreateIn(**MINIMO)
    assert p.is_featured is False and p.tags == [] and p.stack_ids == []


@pytest.mark.parametrize("slug", ["Mi Proyecto", "mi_proyecto", "-mi", "mi-", "mi--proyecto", "acción", ""])
def test_slug_invalido(slug):
    with pytest.raises(ValidationError):
        ProjectCreateIn(title="Mi proyecto", slug=slug)


@pytest.mark.parametrize("url", ["http://sitio.com", "ftp://sitio.com", "sitio.com", "https://con espacio.com"])
def test_las_urls_deben_ser_https(url):
    with pytest.raises(ValidationError):
        ProjectCreateIn(**MINIMO, demo_url=url)


def test_titulo_y_descripcion_respetan_sus_longitudes():
    with pytest.raises(ValidationError):
        ProjectCreateIn(title="ab", slug="mi-proyecto")                           # mínimo 3
    with pytest.raises(ValidationError):
        ProjectCreateIn(**MINIMO, description="muy corta")                         # mínimo 20
    with pytest.raises(ValidationError):
        ProjectCreateIn(**MINIMO, short_description="x" * 251)                     # máximo 250


def test_reglas_de_tags_y_stack_ids():
    assert ProjectCreateIn(**MINIMO, tags=["a1", "b2", "c3", "d4", "e5"]).tags[0] == "a1"
    for tags in (["a1", "b2", "c3", "d4", "e5", "f6"], ["x"], ["Android", "android"], ["x" * 31]):
        with pytest.raises(ValidationError):
            ProjectCreateIn(**MINIMO, tags=tags)
    assert ProjectCreateIn(**MINIMO, stack_ids=[UUID_VALIDO]).stack_ids == [UUID_VALIDO]
    for stack_ids in (["no-es-uuid"], [UUID_VALIDO, UUID_VALIDO], [str(uuid.uuid4())]):   # uuid4 no es v7
        with pytest.raises(ValidationError):
            ProjectCreateIn(**MINIMO, stack_ids=stack_ids)


def test_no_se_aceptan_campos_extra_ni_se_pueden_fijar_los_de_solo_lectura():
    with pytest.raises(ValidationError):
        ProjectCreateIn(**MINIMO, status="PUBLICADO")
    with pytest.raises(ValidationError):
        ProjectCreateIn(**MINIMO, project_id=UUID_VALIDO)


def test_put_exige_is_featured_pero_post_no():
    with pytest.raises(ValidationError):
        ProjectUpdateIn(**MINIMO)
    assert ProjectUpdateIn(**MINIMO, is_featured=True).is_featured is True


# ------------------------------------------------------------------ Certificate
def _certificado(**cambios):
    base = {"title": "Networking Basics", "issuer": "Cisco Networking Academy", "issued_at": date(2025, 10, 26),
            "pdf_url": "https://x.com/a.pdf", "image_url": "https://x.com/a.jpg"}
    return CertificateIn(**{**base, **cambios})


def test_certificado_no_puede_tener_fecha_futura():
    assert _certificado().issued_at == date(2025, 10, 26)
    with pytest.raises(ValidationError):
        _certificado(issued_at=date.today() + timedelta(days=1))
    with pytest.raises(ValidationError):
        _certificado(pdf_url="http://x.com/a.pdf")


# ------------------------------------------------------------------ TechStackItem y Profile
def test_catalogo_valida_categoria_y_orden():
    assert TechStackIn(name="Kotlin", category="LENGUAJE").show_in_profile is False
    with pytest.raises(ValidationError):
        TechStackIn(name="Kotlin", category="MAGIA")
    with pytest.raises(ValidationError):
        TechStackIn(name="Kotlin", category="LENGUAJE", display_order=0)
    with pytest.raises(ValidationError):
        TechStackIn(name="", category="LENGUAJE")


def test_perfil_valida_correo_telefono_y_github():
    assert ProfileIn(**PERFIL).email == PERFIL["email"]
    for cambio in ({"email": "sin-arroba"}, {"phone": "abc"}, {"github_url": "https://gitlab.com/x"},
                   {"tagline": "x" * 161}, {"bio": "corta"}):
        with pytest.raises(ValidationError):
            ProfileIn(**{**PERFIL, **cambio})


# ------------------------------------------------------------------ los datos sembrados cumplen el Diccionario
def test_los_datos_sembrados_cumplen_el_diccionario_de_tipos():
    for titulo, institucion, fecha, base in CERTIFICADOS:
        CertificateIn(title=titulo, issuer=institucion, issued_at=date.fromisoformat(fecha),
                      pdf_url=f"{SITE_BASE_URL}/PDF/{base}.pdf", image_url=f"{SITE_BASE_URL}/Imagenes/Certificados/{base}.jpg")
    for nombre, categoria, logo, visible in CATALOGO:
        TechStackIn(name=nombre, category=categoria, show_in_profile=visible,
                    logo_url=f"{SITE_BASE_URL}/{logo}" if logo else None)
    for p in PROYECTOS:
        ProjectCreateIn(title=p["title"], slug=p["slug"], short_description=p["short_description"],
                        description=p["description"], project_date=date.fromisoformat(p["project_date"]),
                        tags=p["tags"], demo_url=p["demo_url"])
        assert any(nombre in p["stack"] for nombre, categoria, _, _ in CATALOGO if categoria == "LENGUAJE")  # contrato: ≥1 lenguaje


# ------------------------------------------------------------------ Bloque 3: URLs de archivos
@pytest.mark.parametrize("url", ["https://sitio.com/a.pdf", "http://localhost:8000/media/a.pdf", "http://127.0.0.1:8000/media/a.pdf", "http://localhost/a.pdf"])
def test_urls_de_archivo_aceptadas(url):
    assert _certificado(pdf_url=url).pdf_url == url


@pytest.mark.parametrize("url", ["http://sitio.com/a.pdf", "http://localhost.evil.com/a.pdf", "http://localhost:80evil/a.pdf",
                                 "http://localhostx/a.pdf", "ftp://localhost/a.pdf", "https://con espacio.com/a.pdf"])
def test_urls_de_archivo_rechazadas(url):
    with pytest.raises(ValidationError):
        _certificado(pdf_url=url)


def test_demo_y_repo_siguen_exigiendo_https_aunque_sea_localhost():
    with pytest.raises(ValidationError):
        ProjectCreateIn(**MINIMO, demo_url="http://localhost:3000/")


def test_tech_stack_update_exige_show_in_profile():
    with pytest.raises(ValidationError):
        TechStackUpdateIn(name="Kotlin", category="LENGUAJE")
    assert TechStackUpdateIn(name="Kotlin", category="LENGUAJE", show_in_profile=False).display_order is None
