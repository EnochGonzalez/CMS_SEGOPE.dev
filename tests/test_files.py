"""Endpoint 21 (carga de archivos) y el almacén local."""
import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app import config
from app.storage import AlmacenLocal, detectar_tipo
from tests.conftest import JPEG, PDF, PNG, WEBP, clave_nueva

RUTA = "/api/v1/files"


def _subir(client, auth, contenido, purpose, nombre="archivo.bin", tipo="application/octet-stream", clave=None):
    return client.post(RUTA, headers={**auth, "Idempotency-Key": clave or clave_nueva()},
                       data={"purpose": purpose}, files={"file": (nombre, contenido, tipo)})


# ------------------------------------------------------------------ carga correcta
def test_subir_un_pdf_devuelve_la_url_el_tipo_y_el_tamano(client, auth, almacen):
    r = _subir(client, auth, PDF, "CERTIFICATE_PDF", "constancia.pdf", "application/pdf")
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["status"] == "success" and set(cuerpo["data"]) == {"url", "mime_type", "size_bytes"}
    datos = cuerpo["data"]
    assert datos["mime_type"] == "application/pdf" and datos["size_bytes"] == len(PDF)
    assert datos["url"].startswith(almacen.base_url + "/") and datos["url"].endswith(".pdf")
    assert almacen.archivos[datos["url"]] == PDF


@pytest.mark.parametrize("contenido, mime, purpose", [
    (PNG, "image/png", "CERTIFICATE_IMAGE"), (JPEG, "image/jpeg", "STACK_LOGO"), (WEBP, "image/webp", "PROFILE_PHOTO"),
])
def test_subir_imagenes_de_cada_tipo(client, auth, contenido, mime, purpose):
    r = _subir(client, auth, contenido, purpose)
    assert r.status_code == 201 and r.json()["data"]["mime_type"] == mime


def test_el_tipo_se_decide_por_el_contenido_no_por_el_nombre(client, auth):
    mentiroso = _subir(client, auth, PDF, "CERTIFICATE_PDF", "foto.png", "image/png")      # dice ser PNG, es PDF
    assert mentiroso.status_code == 201 and mentiroso.json()["data"]["mime_type"] == "application/pdf"
    falso = _subir(client, auth, b"esto es solo texto", "CERTIFICATE_PDF", "documento.pdf", "application/pdf")
    assert falso.status_code == 415                                                         # dice ser PDF, no lo es


# ------------------------------------------------------------------ 415, 413, 422
@pytest.mark.parametrize("contenido", [b"hola mundo", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", b"MZ\x90\x00", b"", b"%PD"])
def test_tipos_no_permitidos_responden_415(client, auth, contenido):
    r = _subir(client, auth, contenido, "CERTIFICATE_PDF")
    assert r.status_code == 415 and r.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_limites_de_tamano_exactos(client, auth):
    exacto_pdf = PDF + b"0" * (config.MAX_PDF_BYTES - len(PDF))
    exacta_img = PNG + b"0" * (config.MAX_IMAGEN_BYTES - len(PNG))
    assert len(exacto_pdf) == 5_242_880 and len(exacta_img) == 2_097_152
    assert _subir(client, auth, exacto_pdf, "CERTIFICATE_PDF").status_code == 201
    assert _subir(client, auth, exacta_img, "STACK_LOGO").status_code == 201
    grande_pdf = _subir(client, auth, exacto_pdf + b"0", "CERTIFICATE_PDF")
    assert grande_pdf.status_code == 413 and grande_pdf.json()["code"] == "FILE_TOO_LARGE"
    assert _subir(client, auth, exacta_img + b"0", "STACK_LOGO").status_code == 413
    assert _subir(client, auth, PNG + b"0" * (config.MAX_PDF_BYTES * 2), "STACK_LOGO").status_code == 413   # mucho más grande


@pytest.mark.parametrize("contenido, purpose", [
    (PDF, "STACK_LOGO"), (PDF, "CERTIFICATE_IMAGE"), (PDF, "PROFILE_PHOTO"), (PNG, "CERTIFICATE_PDF"), (JPEG, "CERTIFICATE_PDF"),
])
def test_proposito_incompatible_con_el_tipo_responde_422(client, auth, contenido, purpose):
    r = _subir(client, auth, contenido, purpose)
    assert r.status_code == 422 and r.json()["code"] == "FILE_PURPOSE_MISMATCH"
    assert r.json()["details"][0]["field"] == "purpose"


def test_faltan_campos_o_son_invalidos(client, auth):
    cabeceras = {**auth, "Idempotency-Key": clave_nueva()}
    sin_proposito = client.post(RUTA, headers=cabeceras, files={"file": ("a.pdf", PDF, "application/pdf")})
    sin_archivo = client.post(RUTA, headers=cabeceras, data={"purpose": "CERTIFICATE_PDF"})
    proposito_raro = client.post(RUTA, headers=cabeceras, data={"purpose": "OTRO"}, files={"file": ("a.pdf", PDF, "application/pdf")})
    assert sin_proposito.status_code == sin_archivo.status_code == proposito_raro.status_code == 422
    assert sin_proposito.json()["details"][0]["field"] == "purpose" and sin_archivo.json()["details"][0]["field"] == "file"


# ------------------------------------------------------------------ idempotencia y seguridad
def test_misma_clave_y_mismo_archivo_no_se_guarda_dos_veces(client, auth, almacen):
    clave = clave_nueva()
    primera = _subir(client, auth, PDF, "CERTIFICATE_PDF", clave=clave)
    segunda = _subir(client, auth, PDF, "CERTIFICATE_PDF", clave=clave)
    assert segunda.status_code == 201 and segunda.json() == primera.json()
    assert segunda.headers["idempotent-replayed"] == "true" and len(almacen.archivos) == 1


def test_misma_clave_con_otro_archivo_responde_422(client, auth):
    clave = clave_nueva()
    assert _subir(client, auth, PDF, "CERTIFICATE_PDF", clave=clave).status_code == 201
    r = _subir(client, auth, PDF + b"distinto", "CERTIFICATE_PDF", clave=clave)
    assert r.status_code == 422 and r.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_exige_idempotency_key_y_token(client, auth):
    sin_clave = client.post(RUTA, headers=auth, data={"purpose": "CERTIFICATE_PDF"}, files={"file": ("a.pdf", PDF, "application/pdf")})
    assert sin_clave.status_code == 422 and "idempotency" in sin_clave.json()["details"][0]["field"].lower()
    sin_token = client.post(RUTA, headers={"Idempotency-Key": clave_nueva()}, data={"purpose": "CERTIFICATE_PDF"},
                            files={"file": ("a.pdf", PDF, "application/pdf")})
    assert sin_token.status_code == 401


def test_flujo_completo_subir_archivos_y_crear_un_certificado(client, auth):
    pdf = _subir(client, auth, PDF, "CERTIFICATE_PDF").json()["data"]["url"]
    imagen = _subir(client, auth, PNG, "CERTIFICATE_IMAGE").json()["data"]["url"]
    r = client.post("/api/v1/certificates", headers={**auth, "Idempotency-Key": clave_nueva()}, json={
        "title": "Certificado con archivos subidos", "issuer": "Institución", "issued_at": "2026-09-01", "pdf_url": pdf, "image_url": imagen})
    assert r.status_code == 201
    primero = client.get("/api/v1/public/certificates").json()["data"]["items"][0]
    assert primero["pdf_url"] == pdf and primero["image_url"] == imagen


# ------------------------------------------------------------------ detección de tipo y almacén local
def test_detectar_tipo_por_los_primeros_bytes():
    assert detectar_tipo(PDF) == "application/pdf" and detectar_tipo(PNG) == "image/png"
    assert detectar_tipo(JPEG) == "image/jpeg" and detectar_tipo(WEBP) == "image/webp"
    assert detectar_tipo(b"RIFF\x00\x00\x00\x00WAVEfmt ") is None                      # RIFF pero no WebP (es audio WAV)
    assert detectar_tipo(b"") is None and detectar_tipo(b"GIF89a") is None


def test_almacen_local_guarda_con_nombre_propio_y_devuelve_la_url(tmp_path):
    almacen = AlmacenLocal(tmp_path, "http://localhost:8000/media/")
    url1 = almacen.guardar(PDF, "application/pdf", "CERTIFICATE_PDF")
    url2 = almacen.guardar(PNG, "image/png", "STACK_LOGO")
    assert url1.startswith("http://localhost:8000/media/certificados/") and url1.endswith(".pdf")
    assert url2.startswith("http://localhost:8000/media/logos/") and url2.endswith(".png")
    assert (tmp_path / "certificados" / url1.rsplit("/", 1)[1]).read_bytes() == PDF
    assert (tmp_path / "logos" / url2.rsplit("/", 1)[1]).read_bytes() == PNG
    assert url1 != almacen.guardar(PDF, "application/pdf", "CERTIFICATE_PDF")             # cada archivo, un nombre nuevo


def test_los_archivos_guardados_se_sirven_por_http(tmp_path):
    almacen = AlmacenLocal(tmp_path, "/media")
    url = almacen.guardar(PDF, "application/pdf", "CERTIFICATE_PDF")
    mini = FastAPI()
    mini.mount("/media", StaticFiles(directory=tmp_path, check_dir=False))
    cliente = TestClient(mini)
    r = cliente.get(url)
    assert r.status_code == 200 and r.content == PDF and r.headers["content-type"] == "application/pdf"
    assert cliente.get("/media/certificados/no-existe.pdf").status_code == 404
