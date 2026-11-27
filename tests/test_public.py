"""Pruebas de las lecturas públicas (endpoints 9, 10, 12, 16 y 19 de la especificación v2)."""
import re
from datetime import date, datetime, timezone

import pytest

from app.models import Project
from app.seed import CATALOGO

RUTA = "/api/v1/public"
ENDPOINTS_PUBLICOS = ["/projects", "/projects/lawpocket", "/certificates", "/tech-stack", "/profile"]


def _recorrer(client, ruta, limit):
    """Sigue next_cursor hasta el final. Devuelve la lista de páginas (cada una, su lista de items)."""
    paginas, cursor = [], None
    while True:
        params = {"limit": limit, **({"cursor": cursor} if cursor else {})}
        cuerpo = client.get(f"{RUTA}{ruta}", params=params).json()["data"]
        paginas.append(cuerpo["items"])
        cursor = cuerpo["next_cursor"]
        if cursor is None:
            return paginas


# ------------------------------------------------------------------ 9. proyectos
def test_listado_de_proyectos_con_envoltorio_y_orden(client):
    r = client.get(f"{RUTA}/projects")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["status"] == "success" and cuerpo["message"]
    assert cuerpo["data"]["next_cursor"] is None
    # project_date descendente: el más reciente primero
    assert [p["slug"] for p in cuerpo["data"]["items"]] == ["lawpocket", "math-english-quest", "series-de-taylor"]


def test_tarjeta_de_proyecto_solo_expone_los_campos_del_contrato(client):
    """Como EstudianteOut en la práctica guiada: status, created_at, etc. no deben salir."""
    item = client.get(f"{RUTA}/projects").json()["data"]["items"][0]
    assert set(item) == {
        "project_id", "title", "slug", "short_description", "project_date", "tags",
        "tech_stack", "repo_url", "demo_url", "is_featured", "published_at",
    }
    assert item["tags"] == ["LawPocket", "Proyecto Integrador"]
    assert item["demo_url"] == "https://law-pocket-integrador.vercel.app"
    assert item["repo_url"] is None
    assert {"stack_id", "name", "category"} == set(item["tech_stack"][0])
    assert [t["name"] for t in item["tech_stack"]] == ["Java", "SQL", "Figma Site", "AWS (EC2)", "MariaDB", "Postman"]


def test_published_at_va_en_iso_8601_utc(client):
    item = client.get(f"{RUTA}/projects").json()["data"]["items"][0]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", item["published_at"])
    assert item["project_date"] == "2026-07-15"


def test_paginacion_por_cursor_recorre_todo_sin_repetir(client):
    paginas = _recorrer(client, "/projects", limit=1)
    assert [len(p) for p in paginas] == [1, 1, 1]
    slugs = [p["slug"] for pagina in paginas for p in pagina]
    assert slugs == ["lawpocket", "math-english-quest", "series-de-taylor"]


def test_filtros_por_etiqueta_y_destacados(client):
    por_tag = client.get(f"{RUTA}/projects", params={"tag": "android"}).json()["data"]["items"]
    assert [p["slug"] for p in por_tag] == ["math-english-quest"]          # sin distinguir mayúsculas
    assert client.get(f"{RUTA}/projects", params={"tag": "no-existe"}).json()["data"]["items"] == []
    destacados = client.get(f"{RUTA}/projects", params={"is_featured": "true"}).json()["data"]["items"]
    assert destacados == []                                                  # el blog aún no destaca ninguno
    no_destacados = client.get(f"{RUTA}/projects", params={"is_featured": "false"}).json()["data"]["items"]
    assert len(no_destacados) == 3


def test_borradores_y_archivados_nunca_son_publicos(client, session_factory):
    with session_factory() as db:
        db.add(Project(title="Borrador de prueba", slug="borrador-x", status="BORRADOR",
                       project_date=date(2026, 8, 1)))
        db.add(Project(title="Archivado de prueba", slug="archivado-x", status="ARCHIVADO",
                       short_description="Resumen", description="Una descripción lo bastante larga",
                       project_date=date(2026, 8, 2), published_at=datetime(2026, 8, 2, tzinfo=timezone.utc)))
        db.commit()
    slugs = [p["slug"] for p in client.get(f"{RUTA}/projects").json()["data"]["items"]]
    assert "borrador-x" not in slugs and "archivado-x" not in slugs and len(slugs) == 3
    for slug in ("borrador-x", "archivado-x"):
        r = client.get(f"{RUTA}/projects/{slug}")
        assert r.status_code == 404 and r.json()["code"] == "PROJECT_NOT_FOUND"


# ------------------------------------------------------------------ 10. proyecto por slug
def test_proyecto_por_slug(client):
    r = client.get(f"{RUTA}/projects/math-english-quest")
    assert r.status_code == 200
    datos = r.json()["data"]
    assert datos["title"] == "Math & English Quest"
    assert datos["description"].startswith("App educativa dirigida a niños")
    assert set(datos) == {
        "project_id", "title", "slug", "short_description", "description", "project_date",
        "tags", "tech_stack", "repo_url", "demo_url", "published_at",
    }


def test_slug_inexistente_responde_404_con_el_formato_de_error(client):
    r = client.get(f"{RUTA}/projects/no-existe")
    assert r.status_code == 404
    assert r.json() == {
        "status": "error", "code": "PROJECT_NOT_FOUND", "details": [],
        "message": "No existe un proyecto publicado con el slug 'no-existe'",
    }


# ------------------------------------------------------------------ 12. certificados
def test_certificados_en_el_mismo_orden_que_el_blog(client):
    items = client.get(f"{RUTA}/certificates").json()["data"]["items"]
    assert [c["title"] for c in items] == [
        "Operating Systems Support", "Introduction to Internet of Things",
        "AWS Academy Graduate — Cloud Foundations", "Networking Basics",
        "Curso Profesional de Desarrollo en C++",
    ]
    assert [c["issued_at"] for c in items] == ["2026-03-16", "2025-12-01", "2025-10-26", "2025-10-26", "2025-10-25"]
    assert set(items[0]) == {"certificate_id", "title", "issuer", "issued_at", "pdf_url", "image_url"}
    assert items[1]["pdf_url"].endswith("/PDF/InternetOfThings.pdf") and items[1]["pdf_url"].startswith("https://")


def test_paginacion_de_certificados_con_fechas_repetidas(client):
    """AWS y Networking Basics tienen la misma fecha: el desempate por título evita saltos o repetidos."""
    paginas = _recorrer(client, "/certificates", limit=2)
    assert [len(p) for p in paginas] == [2, 2, 1]
    titulos = [c["title"] for pagina in paginas for c in pagina]
    assert len(set(titulos)) == 5 and titulos[2:4] == ["AWS Academy Graduate — Cloud Foundations", "Networking Basics"]


# ------------------------------------------------------------------ 16. lenguajes y herramientas
def test_tech_stack_filtros(client):
    perfil = client.get(f"{RUTA}/tech-stack", params={"show_in_profile": "true"}).json()["data"]["items"]
    assert [i["name"] for i in perfil] == ["Java", "C++", "JavaScript", "CSS", "HTML", "Kotlin"]
    assert perfil[0]["logo_url"].endswith("/Imagenes/Java.png")
    lenguajes = client.get(f"{RUTA}/tech-stack", params={"category": "LENGUAJE"}).json()["data"]["items"]
    assert [i["name"] for i in lenguajes][-1] == "SQL" and len(lenguajes) == 7
    assert {i["category"] for i in lenguajes} == {"LENGUAJE"}


def test_tech_stack_paginado_respeta_display_order(client):
    paginas = _recorrer(client, "/tech-stack", limit=5)
    assert [len(p) for p in paginas] == [5, 5, 5, 1]
    assert [i["name"] for pagina in paginas for i in pagina] == [fila[0] for fila in CATALOGO]
    assert [i["display_order"] for pagina in paginas for i in pagina] == list(range(1, len(CATALOGO) + 1))


# ------------------------------------------------------------------ 19. perfil
def test_perfil_publico(client):
    r = client.get(f"{RUTA}/profile")
    assert r.status_code == 200
    datos = r.json()["data"]
    assert set(datos) == {"profile_id", "full_name", "job_title", "tagline", "bio", "photo_url",
                          "email", "phone", "github_url", "updated_at"}
    assert datos["full_name"] == "Santos Enoch González Pérez"
    assert datos["github_url"] == "https://github.com/EnochGonzalez"


# ------------------------------------------------------------------ caché HTTP
@pytest.mark.parametrize("ruta", ENDPOINTS_PUBLICOS)
def test_etag_y_respuesta_304(client, ruta):
    primera = client.get(f"{RUTA}{ruta}")
    assert primera.status_code == 200
    assert primera.headers["cache-control"] == "public, max-age=60"
    etag = primera.headers["etag"]
    segunda = client.get(f"{RUTA}{ruta}", headers={"If-None-Match": etag})
    assert segunda.status_code == 304 and segunda.content == b"" and segunda.headers["etag"] == etag
    otra = client.get(f"{RUTA}{ruta}", headers={"If-None-Match": '"otro"'})
    assert otra.status_code == 200


# ------------------------------------------------------------------ errores
@pytest.mark.parametrize("parametros, campo", [
    ({"limit": 0}, "limit"), ({"limit": 51}, "limit"), ({"is_featured": "quizas"}, "is_featured"),
])
def test_parametros_invalidos_responden_422_con_detalle(client, parametros, campo):
    r = client.get(f"{RUTA}/projects", params=parametros)
    assert r.status_code == 422
    cuerpo = r.json()
    assert cuerpo["status"] == "error" and cuerpo["code"] == "VALIDATION_ERROR"
    assert cuerpo["details"][0]["field"] == campo


def test_categoria_inexistente_responde_422(client):
    r = client.get(f"{RUTA}/tech-stack", params={"category": "MAGIA"})
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "category"


@pytest.mark.parametrize("ruta", ["/projects", "/certificates", "/tech-stack"])
def test_cursor_invalido_responde_422(client, ruta):
    r = client.get(f"{RUTA}{ruta}", params={"cursor": "esto-no-es-un-cursor"})
    assert r.status_code == 422 and r.json()["code"] == "INVALID_CURSOR"


def test_ruta_inexistente_usa_el_mismo_formato_de_error(client):
    r = client.get("/api/v1/public/nada")
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND" and r.json()["status"] == "error"


def test_documentacion_openapi_lista_todas_las_rutas(client):
    assert client.get("/docs").status_code == 200
    rutas = set(client.get("/openapi.json").json()["paths"])
    publicas = {f"{RUTA}{r}" for r in ["/projects", "/projects/{slug}", "/certificates", "/tech-stack", "/profile"]}
    admin = {"/api/v1/auth/login", "/api/v1/projects", "/api/v1/projects/{project_id}",
             "/api/v1/projects/{project_id}/publish", "/api/v1/projects/{project_id}/archive",
             "/api/v1/certificates", "/api/v1/certificates/{certificate_id}",
             "/api/v1/tech-stack", "/api/v1/tech-stack/{stack_id}", "/api/v1/profile", "/api/v1/files"}
    # Mejora posterior a la especificación: monitoreo de visitas (sitios, estadísticas y registro público).
    monitoreo = {"/api/v1/sites", "/api/v1/sites/{site_id}", "/api/v1/stats", "/api/v1/track"}
    apariencia = {"/api/v1/public/theme", "/api/v1/public/theme/options", "/api/v1/theme"}      # mejora: apariencia del blog
    assert rutas == publicas | admin | monitoreo | apariencia
