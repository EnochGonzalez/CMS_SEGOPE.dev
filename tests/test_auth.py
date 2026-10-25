"""Endpoint 1 (login) y protección con token Bearer."""
import time

import jwt
import pytest

from app import config, security
from tests.conftest import CLAVE_ADMIN, CORREO_ADMIN

LOGIN = "/api/v1/auth/login"
RUTAS_PROTEGIDAS = [
    ("post", "/api/v1/projects"), ("get", "/api/v1/projects"), ("get", "/api/v1/projects/abc"),
    ("put", "/api/v1/projects/abc"), ("post", "/api/v1/projects/abc/publish"),
    ("post", "/api/v1/projects/abc/archive"), ("delete", "/api/v1/projects/abc"),
]


# ------------------------------------------------------------------ contraseñas
def test_hash_de_contrasena_usa_sal_y_se_verifica():
    h1, h2 = security.hash_password("clave-segura-123"), security.hash_password("clave-segura-123")
    assert h1 != h2 and h1.startswith("scrypt$")                      # la sal hace distinto cada resumen
    assert security.verify_password("clave-segura-123", h1)
    assert not security.verify_password("otra-clave-123", h1)
    assert not security.verify_password("x", "esto-no-es-un-hash")


# ------------------------------------------------------------------ login
def test_login_correcto_devuelve_token_utilizable(client):
    r = client.post(LOGIN, json={"email": CORREO_ADMIN, "password": CLAVE_ADMIN})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["status"] == "success"
    assert cuerpo["data"]["token_type"] == "Bearer" and cuerpo["data"]["expires_in"] == 3600
    token = cuerpo["data"]["access_token"]
    assert client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_login_ignora_mayusculas_en_el_correo(client):
    assert client.post(LOGIN, json={"email": CORREO_ADMIN.upper(), "password": CLAVE_ADMIN}).status_code == 200


@pytest.mark.parametrize("correo, clave", [(CORREO_ADMIN, "clave-incorrecta-1"), ("otro@ejemplo.com", CLAVE_ADMIN)])
def test_credenciales_incorrectas_responden_401_sin_decir_cual_fallo(client, correo, clave):
    r = client.post(LOGIN, json={"email": correo, "password": clave})
    assert r.status_code == 401
    assert r.json()["code"] == "INVALID_CREDENTIALS" and r.json()["message"] == "Correo o contraseña incorrectos"


@pytest.mark.parametrize("cuerpo, campo", [
    ({"email": "sin-arroba", "password": CLAVE_ADMIN}, "email"),
    ({"email": CORREO_ADMIN, "password": "corta"}, "password"),
    ({"email": CORREO_ADMIN}, "password"),
])
def test_login_con_formato_invalido_responde_422(client, cuerpo, campo):
    r = client.post(LOGIN, json=cuerpo)
    assert r.status_code == 422 and r.json()["details"][0]["field"] == campo


def test_cinco_intentos_fallidos_bloquean_con_429_y_retry_after(client):
    for _ in range(5):
        assert client.post(LOGIN, json={"email": CORREO_ADMIN, "password": "clave-incorrecta-1"}).status_code == 401
    r = client.post(LOGIN, json={"email": CORREO_ADMIN, "password": CLAVE_ADMIN})     # ni con la clave buena
    assert r.status_code == 429 and r.json()["code"] == "TOO_MANY_ATTEMPTS"
    assert 1 <= int(r.headers["retry-after"]) <= config.LOGIN_VENTANA_SEGUNDOS


def test_el_bloqueo_expira_pasados_15_minutos(client, monkeypatch):
    for _ in range(5):
        client.post(LOGIN, json={"email": CORREO_ADMIN, "password": "clave-incorrecta-1"})
    ahora = time.monotonic()
    monkeypatch.setattr(security, "_reloj", lambda: ahora + config.LOGIN_VENTANA_SEGUNDOS + 1)
    assert client.post(LOGIN, json={"email": CORREO_ADMIN, "password": CLAVE_ADMIN}).status_code == 200


def test_un_login_exitoso_reinicia_el_contador(client):
    for _ in range(4):
        client.post(LOGIN, json={"email": CORREO_ADMIN, "password": "clave-incorrecta-1"})
    assert client.post(LOGIN, json={"email": CORREO_ADMIN, "password": CLAVE_ADMIN}).status_code == 200
    for _ in range(4):                                                # otros 4 fallos: todavía no bloquea
        assert client.post(LOGIN, json={"email": CORREO_ADMIN, "password": "clave-incorrecta-1"}).status_code == 401


def test_sin_administrador_configurado_el_login_responde_503(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", "")
    r = client.post(LOGIN, json={"email": CORREO_ADMIN, "password": CLAVE_ADMIN})
    assert r.status_code == 503 and r.json()["code"] == "ADMIN_NOT_CONFIGURED"


# ------------------------------------------------------------------ token
@pytest.mark.parametrize("metodo, ruta", RUTAS_PROTEGIDAS)
def test_sin_token_todas_las_rutas_de_administracion_responden_401(client, metodo, ruta):
    r = getattr(client, metodo)(ruta)
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED" and r.headers["www-authenticate"] == "Bearer"


def test_token_basura_o_con_firma_ajena_responde_401(client):
    ajeno = jwt.encode({"sub": CORREO_ADMIN, "exp": int(time.time()) + 600}, "otra-clave-distinta-0123456789abcdef", algorithm="HS256")
    for token in ("basura", ajeno):
        r = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401 and r.json()["code"] == "INVALID_TOKEN"


def test_token_vencido_responde_401_token_expired(client):
    vencido = jwt.encode({"sub": CORREO_ADMIN, "exp": int(time.time()) - 10}, config.JWT_SECRET, algorithm="HS256")
    r = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {vencido}"})
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_EXPIRED"


def test_token_de_otro_correo_no_sirve(client):
    otro = jwt.encode({"sub": "intruso@ejemplo.com", "exp": int(time.time()) + 600}, config.JWT_SECRET, algorithm="HS256")
    assert client.get("/api/v1/projects", headers={"Authorization": f"Bearer {otro}"}).status_code == 401


def test_las_lecturas_publicas_siguen_sin_token(client):
    assert client.get("/api/v1/public/projects").status_code == 200


def test_el_limite_de_intentos_no_se_salta_cambiando_de_direccion_ip(client):
    """En internet la IP puede falsificarse (X-Forwarded-For): el límite se cuenta por correo, sea cual sea la IP."""
    from fastapi.testclient import TestClient
    from app.main import app
    for i in range(5):
        desde = TestClient(app, client=(f"203.0.113.{i + 1}", 40000 + i))                 # cada intento, "desde otra IP"
        assert desde.post(LOGIN, json={"email": CORREO_ADMIN, "password": "clave-incorrecta-1"}).status_code == 401
    otra_mas = TestClient(app, client=("198.51.100.77", 55555))
    r = otra_mas.post(LOGIN, json={"email": CORREO_ADMIN, "password": CLAVE_ADMIN})
    assert r.status_code == 429 and r.json()["code"] == "TOO_MANY_ATTEMPTS"


def test_el_bloqueo_de_un_correo_no_afecta_a_otro_correo(client):
    for _ in range(5):
        client.post(LOGIN, json={"email": "otro@ejemplo.com", "password": "clave-incorrecta-1"})
    assert client.post(LOGIN, json={"email": CORREO_ADMIN, "password": CLAVE_ADMIN}).status_code == 200
