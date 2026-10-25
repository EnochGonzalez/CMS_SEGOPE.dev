"""Endpoints 15, 17 y 18: crear, actualizar y eliminar elementos del catálogo de lenguajes y herramientas."""
import pytest

from tests.conftest import clave_nueva

BASE = "/api/v1/tech-stack"
PUBLICO = "/api/v1/public/tech-stack"


def _crear(client, auth, clave=None, **cambios):
    cuerpo = {"name": "Nuevo elemento", "category": "HERRAMIENTA", **cambios}
    return client.post(BASE, json=cuerpo, headers={**auth, "Idempotency-Key": clave or clave_nueva()})


def _id_creado(client, auth, **cambios):
    r = _crear(client, auth, **cambios)
    assert r.status_code == 201, r.text
    return r.json()["data"]["stack_id"]


def _put(client, auth, sid, **cambios):
    cuerpo = {"name": "Nuevo elemento", "category": "HERRAMIENTA", "show_in_profile": False, **cambios}
    return client.put(f"{BASE}/{sid}", json=cuerpo, headers=auth)


def _catalogo(client):
    return client.get(PUBLICO, params={"limit": 50}).json()["data"]["items"]


def _id_de(client, nombre):
    return next(i["stack_id"] for i in _catalogo(client) if i["name"] == nombre)


def _proyecto(client, auth, slug, stack_ids, publicar=False):
    cuerpo = {"title": f"Proyecto {slug}", "slug": slug, "stack_ids": stack_ids, "short_description": "Resumen corto",
              "description": "Descripción suficientemente larga del proyecto.", "project_date": "2026-09-01"}
    r = client.post("/api/v1/projects", json=cuerpo, headers={**auth, "Idempotency-Key": clave_nueva()})
    assert r.status_code == 201, r.text
    pid = r.json()["data"]["project_id"]
    if publicar:
        assert client.post(f"/api/v1/projects/{pid}/publish", headers={**auth, "Idempotency-Key": clave_nueva()}).status_code == 200
    return pid


# ================================================================== 15. crear
def test_crear_sin_orden_queda_al_final_y_si_no_se_ve_no_avisa(client, auth, notificador):
    r = _crear(client, auth)
    assert r.status_code == 201
    datos = r.json()["data"]
    assert set(datos) == {"stack_id", "name", "category", "show_in_profile", "display_order", "created_at", "recompilation_triggered"}
    assert datos["display_order"] == 17 and datos["show_in_profile"] is False and datos["recompilation_triggered"] is False
    assert notificador.llamadas == []                                           # no aparece en el blog: no hay nada que reconstruir
    assert _catalogo(client)[-1]["name"] == "Nuevo elemento"


def test_crear_visible_en_el_perfil_avisa_al_pipeline(client, auth, notificador):
    r = _crear(client, auth, show_in_profile=True, category="LENGUAJE", logo_url="http://localhost:8000/media/logos/x.png")
    assert r.status_code == 201 and r.json()["data"]["recompilation_triggered"] is True
    assert notificador.llamadas == [("STACK_CREATED", r.json()["data"]["stack_id"])]


def test_crear_con_orden_propio(client, auth):
    _crear(client, auth, name="Aaa primero", display_order=1)
    assert [i["name"] for i in _catalogo(client)][:2] == ["Aaa primero", "Java"]          # mismo orden 1: desempata el nombre


def test_nombre_repetido_sin_distinguir_mayusculas_responde_409(client, auth):
    r = _crear(client, auth, name="KOTLIN")
    assert r.status_code == 409 and r.json()["code"] == "STACK_NAME_ALREADY_EXISTS"
    assert _crear(client, auth).status_code == 201 and _crear(client, auth).status_code == 409


@pytest.mark.parametrize("cambio", [
    {"category": "MAGIA"}, {"display_order": 0}, {"name": ""}, {"name": "x" * 41}, {"logo_url": "http://otro.com/a.png"}, {"extra": 1},
])
def test_datos_invalidos_responden_422(client, auth, cambio):
    r = _crear(client, auth, **cambio)
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"


def test_la_misma_clave_no_duplica_el_elemento(client, auth):
    clave = clave_nueva()
    primera, segunda = _crear(client, auth, clave=clave), _crear(client, auth, clave=clave)
    assert segunda.status_code == 201 and segunda.json() == primera.json() and len(_catalogo(client)) == 17


# ================================================================== 17. actualizar
def test_actualizar_reemplaza_todo_y_borra_el_logo_si_no_se_envia(client, auth):
    sid = _id_creado(client, auth, logo_url="http://localhost:8000/media/logos/x.png", display_order=3)
    r = _put(client, auth, sid, name="Nombre nuevo", category="NUBE", display_order=5)
    assert r.status_code == 200 and set(r.json()["data"]) == {"stack_id", "updated_at", "recompilation_triggered"}
    item = next(i for i in _catalogo(client) if i["stack_id"] == sid)
    assert (item["name"], item["category"], item["display_order"], item["logo_url"]) == ("Nombre nuevo", "NUBE", 5, None)


def test_actualizar_exige_show_in_profile(client, auth):
    sid = _id_creado(client, auth)
    r = client.put(f"{BASE}/{sid}", json={"name": "Nuevo elemento", "category": "HERRAMIENTA"}, headers=auth)
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "show_in_profile"


def test_actualizar_nombre_repetido_o_inexistente(client, auth):
    sid = _id_creado(client, auth)
    assert _put(client, auth, sid).status_code == 200                           # su propio nombre: sin conflicto
    assert _put(client, auth, sid, name="java").json()["code"] == "STACK_NAME_ALREADY_EXISTS"
    assert _put(client, auth, "no-existe").json()["code"] == "STACK_NOT_FOUND"


def test_si_no_se_envia_display_order_pasa_al_final(client, auth):
    java = _id_de(client, "Java")
    assert _put(client, auth, java, name="Java", category="LENGUAJE", show_in_profile=True).status_code == 200
    assert _catalogo(client)[-1]["name"] == "Java"


def test_avisos_al_pipeline_al_editar(client, auth, notificador):
    """Solo se avisa cuando el cambio se nota en el blog."""
    oculto = _id_creado(client, auth)                                           # no se ve y nadie lo usa
    assert _put(client, auth, oculto, name="Renombrado").json()["data"]["recompilation_triggered"] is False
    assert notificador.llamadas == []

    java = _id_de(client, "Java")                                               # visible en el perfil
    assert _put(client, auth, java, name="Java", category="LENGUAJE", show_in_profile=True, display_order=1).json()["data"]["recompilation_triggered"] is True

    sql = _id_de(client, "SQL")                                                 # oculto, pero lo usa LawPocket (PUBLICADO)
    assert _put(client, auth, sql, name="SQL", category="LENGUAJE", display_order=7).json()["data"]["recompilation_triggered"] is True
    assert [m for m, _ in notificador.llamadas] == ["STACK_UPDATED", "STACK_UPDATED"]


def test_ocultar_un_elemento_visible_tambien_avisa(client, auth, notificador):
    cpp = _id_de(client, "C++")                                                 # visible y sin proyectos publicados que lo usen
    r = _put(client, auth, cpp, name="C++", category="LENGUAJE", show_in_profile=False, display_order=2)
    assert r.json()["data"]["recompilation_triggered"] is True and notificador.llamadas == [("STACK_UPDATED", cpp)]


def test_un_borrador_que_usa_el_elemento_no_obliga_a_avisar(client, auth, notificador):
    sid = _id_creado(client, auth, name="Solo borrador")
    _proyecto(client, auth, "solo-borrador", [sid])
    assert _put(client, auth, sid, name="Solo borrador 2").json()["data"]["recompilation_triggered"] is False
    assert notificador.llamadas == []


def test_actualizar_con_pipeline_lento_responde_202(client, auth, notificador):
    notificador.aceptada, notificador.lenta = False, True
    java = _id_de(client, "Java")
    assert _put(client, auth, java, name="Java", category="LENGUAJE", show_in_profile=True, display_order=1).status_code == 202


# ================================================================== 18. eliminar
def test_eliminar_elemento_sin_uso(client, auth, notificador):
    sid = _id_creado(client, auth)
    r = client.delete(f"{BASE}/{sid}", headers=auth)
    assert r.status_code == 200 and r.json()["data"] == {"stack_id": sid, "deleted": True, "recompilation_triggered": False}
    assert notificador.llamadas == [] and sid not in [i["stack_id"] for i in _catalogo(client)]
    assert client.delete(f"{BASE}/{sid}", headers=auth).json()["code"] == "STACK_NOT_FOUND"


def test_eliminar_un_elemento_visible_avisa(client, auth, notificador):
    sid = _id_creado(client, auth, name="Visible", show_in_profile=True)
    notificador.llamadas.clear()
    r = client.delete(f"{BASE}/{sid}", headers=auth)
    assert r.json()["data"]["recompilation_triggered"] is True and notificador.llamadas == [("STACK_DELETED", sid)]


def test_no_se_elimina_un_elemento_que_usa_un_proyecto(client, auth):
    java = _id_de(client, "Java")                                               # lo usa lawpocket (PUBLICADO)
    r = client.delete(f"{BASE}/{java}", headers=auth)
    assert r.status_code == 409 and r.json()["code"] == "STACK_IN_USE"
    assert "lawpocket" in r.json()["details"][0]["issue"]
    assert java in [i["stack_id"] for i in _catalogo(client)]


def test_tampoco_si_solo_lo_usa_un_borrador_pero_si_despues_de_borrarlo(client, auth):
    sid = _id_creado(client, auth, name="Con borrador")
    pid = _proyecto(client, auth, "con-borrador", [sid])
    assert client.delete(f"{BASE}/{sid}", headers=auth).status_code == 409
    assert client.delete(f"/api/v1/projects/{pid}", headers=auth).status_code == 204
    assert client.delete(f"{BASE}/{sid}", headers=auth).status_code == 200


def test_eliminar_con_pipeline_lento_responde_202(client, auth, notificador):
    sid = _id_creado(client, auth, name="Visible", show_in_profile=True)
    notificador.aceptada, notificador.lenta = False, True
    assert client.delete(f"{BASE}/{sid}", headers=auth).status_code == 202


@pytest.mark.parametrize("metodo, ruta", [("post", BASE), ("put", f"{BASE}/abc"), ("delete", f"{BASE}/abc")])
def test_sin_token_responde_401(client, metodo, ruta):
    assert getattr(client, metodo)(ruta).status_code == 401
