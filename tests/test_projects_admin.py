"""Endpoints 2 a 8: creación, listado, detalle, edición, publicación, archivado y eliminación de proyectos."""
import re
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.models import IdempotencyKey, Project, ProjectTag, TechStackItem, ahora_utc, proyecto_stack
from app.pipeline import get_notificador
from tests.conftest import clave_nueva

BASE = "/api/v1/projects"
PUBLICO = "/api/v1/public/projects"


# ------------------------------------------------------------------ ayudas
def _stack(client, nombre):
    items = client.get("/api/v1/public/tech-stack", params={"limit": 50}).json()["data"]["items"]
    return next(i["stack_id"] for i in items if i["name"] == nombre)


def _crear(client, auth, clave=None, **campos):
    cuerpo = {"title": "Proyecto de prueba", "slug": "proyecto-de-prueba", **campos}
    return client.post(BASE, json=cuerpo, headers={**auth, "Idempotency-Key": clave or clave_nueva()})


def _completo(client, **extra):
    """Campos que cumplen el contrato de publicación."""
    return {"short_description": "Resumen breve para la tarjeta",
            "description": "Descripción larga y suficiente para poder publicar.",
            "project_date": "2026-08-01", "stack_ids": [_stack(client, "Kotlin")],
            "tags": ["Android"], "demo_url": "https://demo.ejemplo.com", **extra}


def _id_creado(client, auth, **campos):
    r = _crear(client, auth, **campos)
    assert r.status_code == 201, r.text
    return r.json()["data"]["project_id"]


def _publicar(client, auth, pid, clave=None):
    return client.post(f"{BASE}/{pid}/publish", headers={**auth, "Idempotency-Key": clave or clave_nueva()})


def _archivar(client, auth, pid, clave=None):
    return client.post(f"{BASE}/{pid}/archive", headers={**auth, "Idempotency-Key": clave or clave_nueva()})


def _put(client, auth, pid, **campos):
    cuerpo = {"title": "Proyecto de prueba", "slug": "proyecto-de-prueba", "is_featured": False, **campos}
    return client.put(f"{BASE}/{pid}", json=cuerpo, headers=auth)


def _detalle(client, auth, pid):
    return client.get(f"{BASE}/{pid}", headers=auth).json()["data"]


def _publicado(client, auth, **extra):
    """Crea un proyecto completo y lo publica. Devuelve su project_id."""
    pid = _id_creado(client, auth, **_completo(client, **extra))
    assert _publicar(client, auth, pid).status_code == 200
    return pid


def _slugs_publicos(client):
    return [p["slug"] for p in client.get(PUBLICO).json()["data"]["items"]]


# ================================================================== 2. crear borrador
def test_crear_borrador_minimo(client, auth):
    r = _crear(client, auth)
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["status"] == "success" and cuerpo["message"]
    datos = cuerpo["data"]
    assert set(datos) == {"project_id", "status", "slug", "created_at"}
    assert datos["status"] == "BORRADOR" and datos["slug"] == "proyecto-de-prueba"
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", datos["project_id"])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", datos["created_at"])

    detalle = _detalle(client, auth, datos["project_id"])
    assert detalle["is_featured"] is False and detalle["short_description"] is None
    assert detalle["tags"] == [] and detalle["stack_ids"] == [] and detalle["published_at"] is None
    assert len(_slugs_publicos(client)) == 3                          # un borrador nunca es público


def test_crear_con_contenido_completo(client, auth):
    kotlin = _stack(client, "Kotlin")
    pid = _id_creado(client, auth, **_completo(client, tags=["Android", "Proyecto personal"], is_featured=True))
    d = _detalle(client, auth, pid)
    assert d["is_featured"] is True and d["tags"] == ["Android", "Proyecto personal"]
    assert d["stack_ids"] == [kotlin] and d["tech_stack"][0]["name"] == "Kotlin"
    assert d["project_date"] == "2026-08-01" and d["demo_url"] == "https://demo.ejemplo.com"


@pytest.mark.parametrize("clave", [None, "corta"])
def test_crear_exige_idempotency_key(client, auth, clave):
    cabeceras = dict(auth) if clave is None else {**auth, "Idempotency-Key": clave}
    r = client.post(BASE, json={"title": "Proyecto de prueba", "slug": "proyecto-de-prueba"}, headers=cabeceras)
    assert r.status_code == 422 and "idempotency" in r.json()["details"][0]["field"].lower()


def test_misma_clave_devuelve_la_respuesta_original_sin_duplicar(client, auth, session_factory):
    clave = clave_nueva()
    primera = _crear(client, auth, clave=clave)
    segunda = _crear(client, auth, clave=clave)
    assert primera.status_code == 201 and segunda.status_code == 201
    assert segunda.json() == primera.json()
    assert segunda.headers["idempotent-replayed"] == "true" and "idempotent-replayed" not in primera.headers
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Project).where(Project.slug == "proyecto-de-prueba")) == 1


def test_misma_clave_con_otra_peticion_responde_422(client, auth):
    clave = clave_nueva()
    assert _crear(client, auth, clave=clave).status_code == 201
    r = _crear(client, auth, clave=clave, slug="otro-proyecto")
    assert r.status_code == 422 and r.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_una_clave_de_mas_de_24_horas_se_trata_como_nueva(client, auth, session_factory):
    clave = clave_nueva()
    assert _crear(client, auth, clave=clave).status_code == 201
    with session_factory() as db:
        fila = db.get(IdempotencyKey, clave)
        fila.created_at = ahora_utc() - timedelta(hours=25)
        db.commit()
    r = _crear(client, auth, clave=clave, slug="otro-proyecto")          # distinta petición: ya no choca
    assert r.status_code == 201 and "idempotent-replayed" not in r.headers


def test_slug_duplicado_responde_409(client, auth):
    assert _crear(client, auth).status_code == 201
    r = _crear(client, auth)
    assert r.status_code == 409 and r.json()["code"] == "SLUG_ALREADY_EXISTS"
    assert _crear(client, auth, slug="lawpocket").status_code == 409          # también contra los ya sembrados


def test_stack_inexistente_responde_422(client, auth):
    fantasma = "0192a3c2-7e01-7f12-8a23-1b34c45d5678"                         # UUIDv7 válido pero sin registro
    r = _crear(client, auth, stack_ids=[fantasma])
    assert r.status_code == 422 and r.json()["code"] == "STACK_ID_NOT_FOUND"
    assert fantasma in r.json()["details"][0]["issue"]


@pytest.mark.parametrize("cambio", [
    {"slug": "Mi Slug"}, {"title": "ab"}, {"status": "PUBLICADO"}, {"demo_url": "http://inseguro.com"},
    {"tags": ["uno", "uno"]}, {"stack_ids": ["no-es-uuid"]},
])
def test_crear_con_datos_invalidos_responde_422(client, auth, cambio):
    r = _crear(client, auth, **cambio)
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"


# ================================================================== 3 y 4. listado y detalle
def test_listado_administrativo_incluye_borradores_y_filtra_por_estado(client, auth):
    _crear(client, auth)
    todos = client.get(BASE, headers=auth).json()["data"]["items"]
    assert len(todos) == 4
    assert set(todos[0]) == {"project_id", "title", "slug", "status", "project_date", "is_featured", "updated_at"}
    assert [p["slug"] for p in client.get(BASE, params={"status": "BORRADOR"}, headers=auth).json()["data"]["items"]] == ["proyecto-de-prueba"]
    assert len(client.get(BASE, params={"status": "PUBLICADO"}, headers=auth).json()["data"]["items"]) == 3
    assert client.get(BASE, params={"status": "ARCHIVADO"}, headers=auth).json()["data"]["items"] == []
    assert client.get(BASE, params={"status": "OTRO"}, headers=auth).status_code == 422


def test_listado_va_por_updated_at_descendente_y_pagina(client, auth):
    a, b, c = (_id_creado(client, auth, title=f"Proyecto {x}", slug=f"proyecto-{x}") for x in "abc")

    def pagina(**p):
        return client.get(BASE, params={"status": "BORRADOR", **p}, headers=auth).json()["data"]

    uno = pagina(limit=2)
    assert [i["project_id"] for i in uno["items"]] == [c, b]
    dos = pagina(limit=2, cursor=uno["next_cursor"])
    assert [i["project_id"] for i in dos["items"]] == [a] and dos["next_cursor"] is None

    assert _put(client, auth, a, title="Proyecto a", slug="proyecto-a").status_code == 200   # editar la sube al principio
    assert [i["project_id"] for i in pagina()["items"]] == [a, c, b]


def test_detalle_de_proyecto_inexistente_responde_404(client, auth):
    r = client.get(f"{BASE}/no-existe", headers=auth)
    assert r.status_code == 404 and r.json()["code"] == "PROJECT_NOT_FOUND"


# ================================================================== 5. actualizar
def test_put_reemplaza_todo_y_borra_lo_opcional(client, auth, notificador):
    pid = _id_creado(client, auth, **_completo(client))
    r = _put(client, auth, pid, is_featured=True)                              # sin descripción, tags, stack, demo...
    assert r.status_code == 200
    assert set(r.json()["data"]) == {"project_id", "status", "updated_at", "recompilation_triggered"}
    assert r.json()["data"]["status"] == "BORRADOR" and r.json()["data"]["recompilation_triggered"] is False
    d = _detalle(client, auth, pid)
    assert d["is_featured"] is True
    assert d["short_description"] is None and d["description"] is None and d["project_date"] is None
    assert d["tags"] == [] and d["stack_ids"] == [] and d["demo_url"] is None
    assert notificador.llamadas == []                                          # un borrador no avisa al pipeline


def test_put_exige_is_featured(client, auth):
    pid = _id_creado(client, auth)
    r = client.put(f"{BASE}/{pid}", json={"title": "Proyecto de prueba", "slug": "proyecto-de-prueba"}, headers=auth)
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "is_featured"


def test_put_en_borrador_puede_cambiar_el_slug_pero_no_a_uno_ocupado(client, auth):
    pid = _id_creado(client, auth)
    assert _put(client, auth, pid).status_code == 200                           # el mismo slug: sin conflicto consigo mismo
    assert _put(client, auth, pid, slug="slug-nuevo").status_code == 200
    assert _detalle(client, auth, pid)["slug"] == "slug-nuevo"
    r = _put(client, auth, pid, slug="lawpocket")
    assert r.status_code == 409 and r.json()["code"] == "SLUG_ALREADY_EXISTS"


def test_put_con_stack_inexistente_responde_422(client, auth):
    pid = _id_creado(client, auth)
    r = _put(client, auth, pid, stack_ids=["0192a3c2-7e01-7f12-8a23-1b34c45d5678"])
    assert r.status_code == 422 and r.json()["code"] == "STACK_ID_NOT_FOUND"


def test_put_de_proyecto_inexistente_responde_404(client, auth):
    assert _put(client, auth, "no-existe").status_code == 404


# ================================================================== 6. publicar
def test_publicar_proyecto_completo(client, auth, notificador):
    pid = _id_creado(client, auth, **_completo(client))
    r = _publicar(client, auth, pid)
    assert r.status_code == 200
    datos = r.json()["data"]
    assert set(datos) == {"project_id", "status", "published_at", "recompilation_triggered"}
    assert datos["status"] == "PUBLICADO" and datos["recompilation_triggered"] is True
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", datos["published_at"])
    assert notificador.llamadas == [("PROJECT_PUBLISHED", pid)]
    # ya es visible en las lecturas públicas, el más reciente primero
    assert _slugs_publicos(client)[0] == "proyecto-de-prueba" and len(_slugs_publicos(client)) == 4
    detalle = client.get(f"{PUBLICO}/proyecto-de-prueba").json()["data"]
    assert detalle["description"].startswith("Descripción larga") and detalle["tech_stack"][0]["name"] == "Kotlin"


def test_publicar_con_contrato_incompleto_responde_422_con_el_detalle(client, auth, notificador):
    pid = _id_creado(client, auth)                                              # solo title y slug
    r = _publicar(client, auth, pid)
    assert r.status_code == 422 and r.json()["code"] == "PUBLISH_CONTRACT_INCOMPLETE"
    assert {d["field"] for d in r.json()["details"]} == {"short_description", "description", "project_date", "stack_ids"}
    assert _detalle(client, auth, pid)["status"] == "BORRADOR" and notificador.llamadas == []


def test_el_contrato_exige_al_menos_un_lenguaje(client, auth):
    pid = _id_creado(client, auth, **_completo(client, stack_ids=[_stack(client, "Postman")]))     # Postman es HERRAMIENTA
    r = _publicar(client, auth, pid)
    assert r.status_code == 422 and [d["field"] for d in r.json()["details"]] == ["stack_ids"]
    assert _put(client, auth, pid, **_completo(client, stack_ids=[_stack(client, "Postman"), _stack(client, "Java")])).status_code == 200
    assert _publicar(client, auth, pid).status_code == 200


def test_publicar_dos_veces_responde_409_pero_con_la_misma_clave_repite_la_respuesta(client, auth, notificador):
    pid = _id_creado(client, auth, **_completo(client))
    clave = clave_nueva()
    primera = _publicar(client, auth, pid, clave)
    repetida = _publicar(client, auth, pid, clave)                              # reintento tras un timeout
    assert repetida.status_code == 200 and repetida.json() == primera.json()
    assert repetida.headers["idempotent-replayed"] == "true"
    nueva = _publicar(client, auth, pid)                                        # otra clave: ya no es idempotente
    assert nueva.status_code == 409 and nueva.json()["code"] == "PROJECT_ALREADY_PUBLISHED"
    assert len(notificador.llamadas) == 1                                       # solo se avisó una vez


def test_pipeline_lento_responde_202_y_el_proyecto_igual_queda_publicado(client, auth, notificador):
    notificador.aceptada, notificador.lenta = False, True
    pid = _id_creado(client, auth, **_completo(client))
    clave = clave_nueva()
    r = _publicar(client, auth, pid, clave)
    assert r.status_code == 202 and r.json()["data"]["recompilation_triggered"] is False
    assert _detalle(client, auth, pid)["status"] == "PUBLICADO"
    assert _publicar(client, auth, pid, clave).status_code == 202               # el reintento recibe lo mismo


def test_sin_pipeline_conectado_responde_200_con_recompilation_false(client, auth):
    app.dependency_overrides.pop(get_notificador)                               # vuelve el NotificadorNulo real
    pid = _id_creado(client, auth, **_completo(client))
    r = _publicar(client, auth, pid)
    assert r.status_code == 200 and r.json()["data"]["recompilation_triggered"] is False


def test_publicar_inexistente_responde_404(client, auth):
    assert _publicar(client, auth, "no-existe").status_code == 404


@pytest.mark.parametrize("accion", ["publish", "archive"])
def test_publicar_y_archivar_exigen_idempotency_key(client, auth, accion):
    pid = _id_creado(client, auth)
    assert client.post(f"{BASE}/{pid}/{accion}", headers=auth).status_code == 422


# ================================================================== edición de un proyecto PUBLICADO
def test_editar_un_publicado_avisa_al_pipeline(client, auth, notificador):
    pid = _publicado(client, auth)
    r = _put(client, auth, pid, **_completo(client), title="Título corregido")
    assert r.status_code == 200 and r.json()["data"]["recompilation_triggered"] is True
    assert notificador.llamadas[-1] == ("PROJECT_UPDATED", pid)
    assert client.get(f"{PUBLICO}/proyecto-de-prueba").json()["data"]["title"] == "Título corregido"


def test_un_publicado_no_puede_cambiar_de_slug(client, auth, notificador):
    pid = _publicado(client, auth)
    r = _put(client, auth, pid, **_completo(client), slug="otro-slug")
    assert r.status_code == 409 and r.json()["code"] == "SLUG_IMMUTABLE"
    assert _detalle(client, auth, pid)["slug"] == "proyecto-de-prueba" and len(notificador.llamadas) == 1


def test_un_publicado_debe_seguir_cumpliendo_el_contrato(client, auth, notificador):
    pid = _publicado(client, auth)
    r = _put(client, auth, pid)                                                 # sin descripción ni stack
    assert r.status_code == 422 and r.json()["code"] == "PUBLISH_CONTRACT_INCOMPLETE"
    assert client.get(f"{PUBLICO}/proyecto-de-prueba").json()["data"]["description"].startswith("Descripción larga")
    assert len(notificador.llamadas) == 1                                       # no cambió nada, no se avisó


def test_editar_un_publicado_con_pipeline_lento_responde_202(client, auth, notificador):
    pid = _publicado(client, auth)
    notificador.aceptada, notificador.lenta = False, True
    r = _put(client, auth, pid, **_completo(client), title="Otro título")
    assert r.status_code == 202 and r.json()["data"]["recompilation_triggered"] is False


# ================================================================== 7. archivar
def test_archivar_un_borrador_responde_409(client, auth):
    pid = _id_creado(client, auth)
    r = _archivar(client, auth, pid)
    assert r.status_code == 409 and r.json()["code"] == "PROJECT_NOT_PUBLISHED"


def test_archivar_un_publicado_lo_oculta_y_lo_bloquea_para_siempre(client, auth, notificador):
    pid = _publicado(client, auth)
    clave = clave_nueva()
    r = _archivar(client, auth, pid, clave)
    assert r.status_code == 200
    assert set(r.json()["data"]) == {"project_id", "status", "updated_at", "recompilation_triggered"}
    assert r.json()["data"]["status"] == "ARCHIVADO" and notificador.llamadas[-1] == ("PROJECT_ARCHIVED", pid)

    assert "proyecto-de-prueba" not in _slugs_publicos(client)                  # ya no se ve
    assert client.get(f"{PUBLICO}/proyecto-de-prueba").status_code == 404
    assert _crear(client, auth).status_code == 409                              # su slug sigue ocupado (Invariante 4)
    assert _put(client, auth, pid, **_completo(client)).json()["code"] == "PROJECT_ARCHIVED"
    assert _publicar(client, auth, pid).json()["code"] == "PROJECT_ARCHIVED"
    assert client.delete(f"{BASE}/{pid}", headers=auth).json()["code"] == "PROJECT_NOT_DELETABLE"
    assert _archivar(client, auth, pid).json()["code"] == "PROJECT_NOT_PUBLISHED"        # otra clave: ya no es PUBLICADO
    assert _archivar(client, auth, pid, clave).status_code == 200                         # misma clave: repite la original


def test_los_proyectos_sembrados_tambien_se_administran(client, auth):
    """El contenido que ya tenía tu blog se puede archivar desde la API."""
    lista = client.get(BASE, params={"limit": 50}, headers=auth).json()["data"]["items"]
    lawpocket = next(p["project_id"] for p in lista if p["slug"] == "lawpocket")
    assert _archivar(client, auth, lawpocket).status_code == 200
    assert _slugs_publicos(client) == ["math-english-quest", "series-de-taylor"]


# ================================================================== 8. eliminar
def test_eliminar_borrador_responde_204_y_borra_sus_datos_asociados(client, auth, session_factory):
    pid = _id_creado(client, auth, **_completo(client))
    r = client.delete(f"{BASE}/{pid}", headers=auth)
    assert r.status_code == 204 and r.content == b""
    assert client.get(f"{BASE}/{pid}", headers=auth).status_code == 404
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ProjectTag).where(ProjectTag.project_id == pid)) == 0
        assert db.scalar(select(func.count()).select_from(proyecto_stack).where(proyecto_stack.c.project_id == pid)) == 0
        assert db.scalar(select(func.count()).select_from(TechStackItem)) == 16        # el catálogo no se toca


def test_no_se_eliminan_publicados_ni_archivados(client, auth):
    pid = _publicado(client, auth)
    r = client.delete(f"{BASE}/{pid}", headers=auth)
    assert r.status_code == 409 and r.json()["code"] == "PROJECT_NOT_DELETABLE"
    assert _archivar(client, auth, pid).status_code == 200
    assert client.delete(f"{BASE}/{pid}", headers=auth).status_code == 409


def test_eliminar_inexistente_responde_404(client, auth):
    assert client.delete(f"{BASE}/no-existe", headers=auth).status_code == 404


# ================================================================== invariante en la base de datos
def test_un_elemento_del_catalogo_referenciado_no_se_puede_borrar(client, auth, session_factory):
    """Invariante 2 de TechStackItem: la base de datos lo impide (RESTRICT) aunque aún no exista el endpoint."""
    _id_creado(client, auth, **_completo(client))
    kotlin = _stack(client, "Kotlin")
    with session_factory() as db:
        item = db.get(TechStackItem, kotlin)
        db.delete(item)
        with pytest.raises(IntegrityError):
            db.commit()
