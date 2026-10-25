"""Endpoint 20: actualización del perfil y contacto."""
import pytest
from sqlalchemy import delete

from app.models import Profile
from app.seed import PERFIL

RUTA = "/api/v1/profile"
PUBLICO = "/api/v1/public/profile"


def _cuerpo(**cambios):
    base = {clave: valor for clave, valor in PERFIL.items()}
    for clave, valor in cambios.items():
        base.pop(clave, None) if valor is None else base.__setitem__(clave, valor)
    return base


def test_actualizar_el_perfil(client, auth, notificador):
    antes = client.get(PUBLICO).json()["data"]
    r = client.put(RUTA, json=_cuerpo(tagline="Nueva frase corta", phone="960-000-0000"), headers=auth)
    assert r.status_code == 200
    datos = r.json()["data"]
    assert set(datos) == {"profile_id", "updated_at", "recompilation_triggered"}
    assert datos["profile_id"] == antes["profile_id"] and datos["recompilation_triggered"] is True     # sigue siendo el mismo registro
    assert notificador.llamadas == [("PROFILE_UPDATED", antes["profile_id"])]
    despues = client.get(PUBLICO).json()["data"]
    assert despues["tagline"] == "Nueva frase corta" and despues["phone"] == "960-000-0000"


def test_lo_opcional_que_no_se_envia_se_borra(client, auth):
    assert client.put(RUTA, json=_cuerpo(photo_url=None, phone=None, github_url=None), headers=auth).status_code == 200
    datos = client.get(PUBLICO).json()["data"]
    assert datos["photo_url"] is None and datos["phone"] is None and datos["github_url"] is None
    assert datos["email"] == PERFIL["email"]


@pytest.mark.parametrize("cambio", [
    {"email": "sin-arroba"}, {"tagline": "x" * 161}, {"github_url": "https://gitlab.com/usuario"}, {"phone": "abc"},
    {"bio": "corta"}, {"full_name": "ab"}, {"extra": "campo"}, {"bio": None}, {"photo_url": "http://otro.com/foto.jpg"},
])
def test_datos_invalidos_responden_422(client, auth, cambio):
    r = client.put(RUTA, json=_cuerpo(**cambio), headers=auth)
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"


def test_con_pipeline_lento_responde_202(client, auth, notificador):
    notificador.aceptada, notificador.lenta = False, True
    r = client.put(RUTA, json=_cuerpo(), headers=auth)
    assert r.status_code == 202 and r.json()["data"]["recompilation_triggered"] is False


def test_si_no_hay_perfil_responde_404(client, auth, session_factory):
    with session_factory() as db:
        db.execute(delete(Profile))
        db.commit()
    r = client.put(RUTA, json=_cuerpo(), headers=auth)
    assert r.status_code == 404 and r.json()["code"] == "PROFILE_NOT_FOUND"


@pytest.mark.parametrize("metodo", ["post", "delete"])
def test_la_api_no_crea_ni_elimina_el_perfil(client, auth, metodo):
    r = getattr(client, metodo)(RUTA, headers=auth)
    assert r.status_code == 405 and r.json()["code"] == "METHOD_NOT_ALLOWED"


def test_sin_token_responde_401(client):
    assert client.put(RUTA, json=_cuerpo()).status_code == 401
