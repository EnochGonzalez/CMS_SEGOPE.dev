"""Endpoints 11, 13 y 14: crear, actualizar y eliminar certificados."""
import pytest

from app import config
from tests.conftest import clave_nueva

BASE = "/api/v1/certificates"
PUBLICO = "/api/v1/public/certificates"


def _cuerpo(almacen, **cambios):
    base = {"title": "Curso de prueba", "issuer": "Institución de prueba", "issued_at": "2026-09-01",
            "pdf_url": f"{almacen.base_url}/certificados/a.pdf", "image_url": f"{almacen.base_url}/certificados/a.jpg"}
    return {**base, **cambios}


def _crear(client, auth, almacen, clave=None, **cambios):
    return client.post(BASE, json=_cuerpo(almacen, **cambios), headers={**auth, "Idempotency-Key": clave or clave_nueva()})


def _id_creado(client, auth, almacen, **cambios):
    r = _crear(client, auth, almacen, **cambios)
    assert r.status_code == 201, r.text
    return r.json()["data"]["certificate_id"]


def _publicos(client):
    return client.get(PUBLICO, params={"limit": 50}).json()["data"]["items"]


# ================================================================== 11. crear
def test_crear_certificado(client, auth, almacen, notificador):
    r = _crear(client, auth, almacen)
    assert r.status_code == 201
    datos = r.json()["data"]
    assert set(datos) == {"certificate_id", "title", "issuer", "issued_at", "created_at", "recompilation_triggered"}
    assert datos["title"] == "Curso de prueba" and datos["issued_at"] == "2026-09-01" and datos["recompilation_triggered"] is True
    assert notificador.llamadas == [("CERTIFICATE_CREATED", datos["certificate_id"])]
    publicos = _publicos(client)
    assert len(publicos) == 6 and publicos[0]["title"] == "Curso de prueba"       # el más reciente va primero


def test_acepta_urls_del_almacen_y_de_los_archivos_del_blog(client, auth, almacen):
    blog = {"pdf_url": f"{config.SITE_BASE_URL}/PDF/NuevoCertificado.pdf", "image_url": f"{config.SITE_BASE_URL}/Imagenes/Certificados/Nuevo.jpg"}
    assert _crear(client, auth, almacen, **blog).status_code == 201


def test_crear_exige_idempotency_key(client, auth, almacen):
    for cabeceras in (auth, {**auth, "Idempotency-Key": "corta"}):
        r = client.post(BASE, json=_cuerpo(almacen), headers=cabeceras)
        assert r.status_code == 422 and "idempotency" in r.json()["details"][0]["field"].lower()


def test_la_misma_clave_no_duplica_el_certificado(client, auth, almacen):
    clave = clave_nueva()
    primera, segunda = (_crear(client, auth, almacen, clave=clave) for _ in range(2))
    assert segunda.status_code == 201 and segunda.json() == primera.json()
    assert segunda.headers["idempotent-replayed"] == "true" and len(_publicos(client)) == 6
    otra = _crear(client, auth, almacen, clave=clave, title="Otro título distinto")
    assert otra.status_code == 422 and otra.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_certificado_repetido_responde_409(client, auth, almacen):
    assert _crear(client, auth, almacen).status_code == 201
    r = _crear(client, auth, almacen)
    assert r.status_code == 409 and r.json()["code"] == "CERTIFICATE_ALREADY_EXISTS"
    ya_sembrado = _crear(client, auth, almacen, title="Networking Basics", issuer="Cisco Networking Academy", issued_at="2025-10-26")
    assert ya_sembrado.status_code == 409
    assert _crear(client, auth, almacen, issued_at="2026-09-02").status_code == 201        # otra fecha: ya es otro certificado


def test_urls_de_otro_origen_responden_422_indicando_cual(client, auth, almacen):
    r = _crear(client, auth, almacen, pdf_url="https://otro-sitio.com/a.pdf")
    assert r.status_code == 422 and r.json()["code"] == "FILE_URL_NOT_ALLOWED"
    assert [d["field"] for d in r.json()["details"]] == ["pdf_url"]
    ambas = _crear(client, auth, almacen, pdf_url="https://otro-sitio.com/a.pdf", image_url="https://otro-sitio.com/a.jpg")
    assert [d["field"] for d in ambas.json()["details"]] == ["pdf_url", "image_url"]
    local = _crear(client, auth, almacen, pdf_url="http://localhost:8000/media/certificados/a.pdf")   # pasa el formato, pero no es el almacén de la prueba
    assert local.status_code == 422 and local.json()["code"] == "FILE_URL_NOT_ALLOWED"


@pytest.mark.parametrize("cambio", [
    {"pdf_url": "http://otro-sitio.com/a.pdf"}, {"image_url": "ftp://x.com/a.jpg"}, {"title": "ab"},
    {"issued_at": "2999-01-01"}, {"issued_at": "no-es-fecha"}, {"issuer": ""}, {"extra": "campo"},
])
def test_formato_invalido_responde_422(client, auth, almacen, cambio):
    r = _crear(client, auth, almacen, **cambio)
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"


def test_crear_siempre_responde_201_aunque_el_pipeline_tarde(client, auth, almacen, notificador):
    notificador.aceptada, notificador.lenta = False, True
    r = _crear(client, auth, almacen)
    assert r.status_code == 201 and r.json()["data"]["recompilation_triggered"] is False


# ================================================================== 13. actualizar
def test_actualizar_reemplaza_el_certificado(client, auth, almacen, notificador):
    cid = _id_creado(client, auth, almacen)
    r = client.put(f"{BASE}/{cid}", json=_cuerpo(almacen, title="Título corregido", issuer="Otra institución"), headers=auth)
    assert r.status_code == 200
    assert set(r.json()["data"]) == {"certificate_id", "updated_at", "recompilation_triggered"}
    assert r.json()["data"]["recompilation_triggered"] is True and notificador.llamadas[-1] == ("CERTIFICATE_UPDATED", cid)
    nuevo = next(c for c in _publicos(client) if c["certificate_id"] == cid)
    assert nuevo["title"] == "Título corregido" and nuevo["issuer"] == "Otra institución"


def test_actualizar_con_los_mismos_datos_no_choca_consigo_mismo(client, auth, almacen):
    cid = _id_creado(client, auth, almacen)
    assert client.put(f"{BASE}/{cid}", json=_cuerpo(almacen), headers=auth).status_code == 200


def test_actualizar_a_los_datos_de_otro_certificado_responde_409(client, auth, almacen):
    cid = _id_creado(client, auth, almacen)
    r = client.put(f"{BASE}/{cid}", json=_cuerpo(almacen, title="Networking Basics", issuer="Cisco Networking Academy", issued_at="2025-10-26"), headers=auth)
    assert r.status_code == 409 and r.json()["code"] == "CERTIFICATE_ALREADY_EXISTS"


def test_actualizar_valida_urls_y_existencia(client, auth, almacen):
    cid = _id_creado(client, auth, almacen)
    r = client.put(f"{BASE}/{cid}", json=_cuerpo(almacen, image_url="https://otro-sitio.com/a.jpg"), headers=auth)
    assert r.status_code == 422 and r.json()["code"] == "FILE_URL_NOT_ALLOWED"
    assert client.put(f"{BASE}/no-existe", json=_cuerpo(almacen), headers=auth).json()["code"] == "CERTIFICATE_NOT_FOUND"


def test_actualizar_con_pipeline_lento_responde_202(client, auth, almacen, notificador):
    cid = _id_creado(client, auth, almacen)
    notificador.aceptada, notificador.lenta = False, True
    r = client.put(f"{BASE}/{cid}", json=_cuerpo(almacen, title="Otro título"), headers=auth)
    assert r.status_code == 202 and r.json()["data"]["recompilation_triggered"] is False


# ================================================================== 14. eliminar
def test_eliminar_certificado(client, auth, almacen, notificador):
    cid = _id_creado(client, auth, almacen)
    r = client.delete(f"{BASE}/{cid}", headers=auth)
    assert r.status_code == 200
    assert r.json()["data"] == {"certificate_id": cid, "deleted": True, "recompilation_triggered": True}
    assert notificador.llamadas[-1] == ("CERTIFICATE_DELETED", cid)
    assert len(_publicos(client)) == 5
    assert client.delete(f"{BASE}/{cid}", headers=auth).status_code == 404


def test_se_puede_eliminar_un_certificado_ya_sembrado(client, auth):
    sembrado = next(c for c in _publicos(client) if c["title"] == "Networking Basics")
    assert client.delete(f"{BASE}/{sembrado['certificate_id']}", headers=auth).status_code == 200
    assert "Networking Basics" not in [c["title"] for c in _publicos(client)]


def test_eliminar_con_pipeline_lento_responde_202(client, auth, almacen, notificador):
    cid = _id_creado(client, auth, almacen)
    notificador.aceptada, notificador.lenta = False, True
    r = client.delete(f"{BASE}/{cid}", headers=auth)
    assert r.status_code == 202 and r.json()["data"]["deleted"] is True


@pytest.mark.parametrize("metodo, ruta", [("post", BASE), ("put", f"{BASE}/abc"), ("delete", f"{BASE}/abc")])
def test_sin_token_responde_401(client, metodo, ruta):
    assert getattr(client, metodo)(ruta).status_code == 401
