"""Sitios monitoreados: lista, alta, actualización (también pausar) y eliminación."""
from sqlalchemy import select

from app.models import PageView
from app.services import analitica
from tests.conftest import clave_nueva

BASE = "/api/v1/sites"


def _crear(client, auth, clave=None, **cambios):
    cuerpo = {"name": "Mi blog", "domain": "segope.vercel.app", "color": "#EF4444", **cambios}
    return client.post(BASE, json=cuerpo, headers={**auth, "Idempotency-Key": clave or clave_nueva()})


def _id(client, auth, **cambios):
    r = _crear(client, auth, **cambios)
    assert r.status_code == 201, r.text
    return r.json()["data"]["site_id"]


def _put(client, auth, sid, **cambios):
    cuerpo = {"name": "Mi blog", "domain": "segope.vercel.app", "color": "#ef4444", "is_active": True, **cambios}
    return client.put(f"{BASE}/{sid}", json=cuerpo, headers=auth)


# ------------------------------------------------------------------ acceso
def test_todo_exige_token(client):
    assert client.get(BASE).status_code == 401
    assert client.post(BASE, json={}, headers={"Idempotency-Key": clave_nueva()}).status_code == 401
    assert client.put(f"{BASE}/x", json={}).status_code == 401
    assert client.delete(f"{BASE}/x").status_code == 401


# ------------------------------------------------------------------ crear
def test_crear_devuelve_el_sitio_y_normaliza_dominio_y_color(client, auth):
    r = _crear(client, auth, domain="HTTPS://Segope.Vercel.app/index.html?x=1")
    assert r.status_code == 201
    datos = r.json()["data"]
    assert set(datos) == {"site_id", "name", "domain", "color", "is_active", "created_at", "updated_at"}
    assert datos["domain"] == "segope.vercel.app"
    assert datos["color"] == "#ef4444"                      # se guarda en minúsculas
    assert datos["is_active"] is True


def test_crear_con_la_misma_clave_no_duplica(client, auth):
    clave = clave_nueva()
    primera = _crear(client, auth, clave=clave)
    segunda = _crear(client, auth, clave=clave)
    assert primera.status_code == segunda.status_code == 201
    assert segunda.headers["idempotent-replayed"] == "true"
    assert len(client.get(BASE, headers=auth).json()["data"]["items"]) == 1


def test_dominio_repetido_da_409(client, auth):
    _id(client, auth)
    r = _crear(client, auth, name="Otro", domain="SEGOPE.vercel.app")
    assert r.status_code == 409
    assert r.json()["code"] == "SITE_DOMAIN_ALREADY_EXISTS"
    assert r.json()["details"][0]["field"] == "domain"


def test_datos_invalidos_dan_422_con_el_campo(client, auth):
    for cambios, campo in [({"domain": "no es un dominio"}, "domain"), ({"domain": "a"}, "domain"),
                           ({"color": "rojo"}, "color"), ({"name": "   "}, "name")]:
        r = _crear(client, auth, **cambios)
        assert r.status_code == 422, cambios
        assert r.json()["details"][0]["field"] == campo


def test_crear_sin_clave_de_idempotencia_da_422(client, auth):
    r = client.post(BASE, json={"name": "x", "domain": "a.com"}, headers=auth)
    assert r.status_code == 422


# ------------------------------------------------------------------ lista
def test_la_lista_trae_visitas_totales_y_ultima_visita(client, auth, session_factory):
    sin_visitas = _id(client, auth, name="Sin visitas", domain="vacio.com")
    con_visitas = _id(client, auth, name="Con visitas", domain="blog.com")
    with session_factory() as db:
        for _ in range(3):
            analitica.registrar_vista(db, db.get(analitica.Site, con_visitas), "/", None, "1.1.1.1", "Mozilla/5.0")
    items = {i["site_id"]: i for i in client.get(BASE, headers=auth).json()["data"]["items"]}
    assert items[sin_visitas]["views_total"] == 0 and items[sin_visitas]["last_view_at"] is None
    assert items[con_visitas]["views_total"] == 3
    assert items[con_visitas]["last_view_at"].endswith("Z")


# ------------------------------------------------------------------ actualizar
def test_actualizar_y_pausar(client, auth):
    sid = _id(client, auth)
    r = _put(client, auth, sid, name="Nuevo nombre", color="#00FF00", is_active=False)
    assert r.status_code == 200
    datos = r.json()["data"]
    assert (datos["name"], datos["color"], datos["is_active"]) == ("Nuevo nombre", "#00ff00", False)


def test_put_exige_color_y_estado(client, auth):
    sid = _id(client, auth)
    r = client.put(f"{BASE}/{sid}", json={"name": "x", "domain": "a.com"}, headers=auth)
    assert r.status_code == 422
    assert {d["field"] for d in r.json()["details"]} == {"color", "is_active"}


def test_actualizar_con_dominio_de_otro_sitio_da_409(client, auth):
    _id(client, auth, domain="uno.com")
    otro = _id(client, auth, name="Otro", domain="dos.com")
    assert _put(client, auth, otro, domain="uno.com").status_code == 409
    assert _put(client, auth, otro, domain="dos.com").status_code == 200       # el suyo propio sí


def test_actualizar_o_eliminar_inexistente_da_404(client, auth):
    assert _put(client, auth, "no-existe").json()["code"] == "SITE_NOT_FOUND"
    assert client.delete(f"{BASE}/no-existe", headers=auth).status_code == 404


# ------------------------------------------------------------------ eliminar
def test_eliminar_borra_tambien_sus_visitas(client, auth, session_factory):
    sid = _id(client, auth)
    otro = _id(client, auth, name="Otro", domain="otro.com")
    with session_factory() as db:
        for s in (sid, sid, otro):
            analitica.registrar_vista(db, db.get(analitica.Site, s), "/", None, "1.1.1.1", "Mozilla/5.0")
    r = client.delete(f"{BASE}/{sid}", headers=auth)
    assert r.status_code == 200
    assert r.json()["data"] == {"deleted": True, "site_id": sid, "views_deleted": 2}
    with session_factory() as db:
        assert db.scalars(select(PageView.site_id)).all() == [otro]            # solo quedan las del otro sitio
    assert client.get(BASE, headers=auth).json()["data"]["items"][0]["site_id"] == otro
