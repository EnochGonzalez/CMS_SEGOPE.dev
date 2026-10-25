"""Lo necesario para publicar la API en internet: Postgres, almacén S3, aviso a Vercel, salud y configuración."""
import logging
import os
import threading
import uuid
from collections import deque

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import config, configurar_admin, main as modulo_main, security, storage
from app.database import Base, crear_engine, get_db, normalizar_url
from app.main import app
from app.pipeline import NotificadorDeploy, NotificadorNulo, ResultadoNotificacion, get_notificador
from tests.conftest import CLAVE_ADMIN, CORREO_ADMIN, PDF, PNG, clave_nueva

URL_SECRETA = "https://api.vercel.com/v1/integrations/deploy/prj_SECRETO123/TOKEN-MUY-SECRETO"


# ================================================================== base de datos
@pytest.mark.parametrize("entrada, esperada", [
    ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
    ("postgresql://u:p@host/db?sslmode=require", "postgresql+psycopg://u:p@host/db?sslmode=require"),
    ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("sqlite:///./cms.db", "sqlite:///./cms.db"),
])
def test_las_direcciones_de_postgres_de_los_servicios_se_normalizan(entrada, esperada):
    assert normalizar_url(entrada) == esperada


# ================================================================== configuración
def test_configuracion_completa_o_vacia_no_da_problemas(monkeypatch):
    assert config.problemas_de_configuracion() == []
    for nombre, valor in [("S3_ENDPOINT_URL", "https://s3.ejemplo.com"), ("S3_BUCKET", "archivos"), ("S3_ACCESS_KEY_ID", "id"), ("S3_SECRET_ACCESS_KEY", "secreto"),
                          ("FILES_PUBLIC_URL", "https://s3.ejemplo.com/publico/archivos"), ("FILES_PUBLIC_URL_DEFINIDA", True), ("DEPLOY_HOOK_URL", URL_SECRETA)]:
        monkeypatch.setattr(config, nombre, valor)
    assert config.s3_configurado() and config.problemas_de_configuracion() == []


def test_se_detectan_configuraciones_a_medias_o_inseguras(monkeypatch):
    monkeypatch.setattr(config, "S3_BUCKET", "archivos")                                   # solo una de las cuatro
    assert any("a medias" in p for p in config.problemas_de_configuracion())
    for nombre, valor in [("S3_ENDPOINT_URL", "https://s3.ejemplo.com"), ("S3_ACCESS_KEY_ID", "id"), ("S3_SECRET_ACCESS_KEY", "secreto")]:
        monkeypatch.setattr(config, nombre, valor)
    assert any("hace falta definir FILES_PUBLIC_URL" in p for p in config.problemas_de_configuracion())    # se olvidó definirla
    monkeypatch.setattr(config, "FILES_PUBLIC_URL_DEFINIDA", True)
    monkeypatch.setattr(config, "FILES_PUBLIC_URL", "http://inseguro.com/archivos")
    assert any("debe empezar con https" in p for p in config.problemas_de_configuracion())
    monkeypatch.setattr(config, "FILES_PUBLIC_URL", "http://localhost:5555/archivos")                       # para probar en tu computadora
    assert config.problemas_de_configuracion() == []
    for disfrazada in ("http://localhost.malo.com/archivos", "http://127.0.0.1.malo.com/x", "http://localhostx/a"):
        monkeypatch.setattr(config, "FILES_PUBLIC_URL", disfrazada)
        assert config.problemas_de_configuracion(), disfrazada                                              # no es tu computadora, es un sitio de otro
    monkeypatch.setattr(config, "FILES_PUBLIC_URL", "https://s3.ejemplo.com/publico")
    monkeypatch.setattr(config, "DEPLOY_HOOK_URL", "http://inseguro.com/hook")
    assert any("DEPLOY_HOOK_URL" in p for p in config.problemas_de_configuracion())


def test_la_api_no_arranca_con_la_configuracion_equivocada(monkeypatch):
    monkeypatch.setattr(config, "S3_BUCKET", "archivos")
    with pytest.raises(RuntimeError, match="Configuración incompleta"):
        with TestClient(app):
            pass


def _con_base_propia(monkeypatch, tmp_path):
    engine = crear_engine(f"sqlite:///{tmp_path / 'arranque.db'}")
    monkeypatch.setattr(modulo_main, "engine", engine)
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(modulo_main, "SessionLocal", fabrica)
    def base_de_la_prueba():                       # FastAPI espera una función "generadora" (con yield) para abrir y cerrar la sesión
        db = fabrica()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = base_de_la_prueba
    return fabrica


def test_la_primera_vez_en_un_servidor_nuevo_se_carga_el_contenido_inicial(monkeypatch, tmp_path):
    fabrica = _con_base_propia(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "SEMBRAR_SI_ESTA_VACIA", True)
    try:
        with TestClient(app) as cliente:
            assert len(cliente.get("/api/v1/public/projects").json()["data"]["items"]) == 3
            assert len(cliente.get("/api/v1/public/certificates").json()["data"]["items"]) == 5
        with TestClient(app) as cliente:                                                    # segundo arranque: no duplica
            assert len(cliente.get("/api/v1/public/projects").json()["data"]["items"]) == 3
    finally:
        app.dependency_overrides.clear()


def test_sin_la_opcion_activada_la_base_nueva_queda_vacia(monkeypatch, tmp_path):
    _con_base_propia(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "SEMBRAR_SI_ESTA_VACIA", False)
    try:
        with TestClient(app) as cliente:
            assert cliente.get("/api/v1/public/projects").json()["data"]["items"] == []
    finally:
        app.dependency_overrides.clear()


# ================================================================== salud y cabeceras
def test_health_responde_200_cuando_todo_esta_bien_y_no_aparece_en_la_documentacion(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": "ok"}
    assert "/health" not in client.get("/openapi.json").json()["paths"]


def test_health_responde_503_si_la_base_de_datos_no_contesta(client):
    class BaseCaida:
        llamadas = 0

        def execute(self, *_):
            BaseCaida.llamadas += 1
            raise RuntimeError("sin conexión")

        def close(self):
            pass

    def base_caida():
        yield BaseCaida()

    app.dependency_overrides[get_db] = base_caida
    r = client.get("/health")
    assert r.status_code == 503 and r.json() == {"status": "error", "database": "no responde"}
    assert BaseCaida.llamadas == 1                    # de verdad se intentó usar la base (no falló por otro motivo)


def test_las_respuestas_de_una_sesion_de_administrador_no_se_guardan_en_caches_compartidas(client, auth):
    assert client.get("/api/v1/projects/no-existe", headers=auth).headers["cache-control"] == "no-store"      # error con token
    assert client.get("/api/v1/projects", headers=auth).headers["cache-control"] == "no-store"
    publica = client.get("/api/v1/public/projects", headers=auth)
    assert publica.headers["cache-control"] == "public, max-age=60"                                          # las públicas conservan su caché
    assert "no-store" not in client.get("/api/v1/public/projects").headers["cache-control"]
    assert all(r.headers["x-content-type-options"] == "nosniff" for r in (client.get("/health"), publica))


# ================================================================== configurar_admin --imprimir
def test_imprimir_muestra_las_tres_variables_y_no_escribe_ningun_archivo(monkeypatch, tmp_path, capsys):
    destino = tmp_path / ".env"
    monkeypatch.setattr(config, "ARCHIVO_ENV", destino)
    monkeypatch.setattr("builtins.input", lambda *_: "admin@ejemplo.com")
    claves = iter(["una-clave-larga-1", "una-clave-larga-1"])
    monkeypatch.setattr(configurar_admin.getpass, "getpass", lambda *_: next(claves))
    configurar_admin.main(["--imprimir"])
    salida = capsys.readouterr().out
    lineas = dict(l.split("=", 1) for l in salida.splitlines() if l.startswith(("ADMIN_", "JWT_")))
    assert set(lineas) == {"ADMIN_EMAIL", "ADMIN_PASSWORD_HASH", "JWT_SECRET"} and lineas["ADMIN_EMAIL"] == "admin@ejemplo.com"
    assert security.verify_password("una-clave-larga-1", lineas["ADMIN_PASSWORD_HASH"]) and "una-clave-larga-1" not in salida
    assert not destino.exists()


# ================================================================== almacén S3 (con un S3 simulado)
@pytest.fixture()
def s3_simulado(monkeypatch):
    pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    import boto3

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "prueba")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "prueba")
    with moto.mock_aws():
        cliente = boto3.client("s3", region_name="us-east-1")
        cliente.create_bucket(Bucket="archivos")
        storage._cliente_s3.cache_clear()
        for nombre, valor in [("S3_ENDPOINT_URL", "https://s3.us-east-1.amazonaws.com"), ("S3_BUCKET", "archivos"), ("S3_ACCESS_KEY_ID", "prueba"),
                              ("S3_SECRET_ACCESS_KEY", "prueba"), ("S3_REGION", "us-east-1"), ("FILES_PUBLIC_URL", "https://cdn.ejemplo.com/archivos"),
                          ("FILES_PUBLIC_URL_DEFINIDA", True)]:
            monkeypatch.setattr(config, nombre, valor)
        yield cliente
        storage._cliente_s3.cache_clear()


def test_el_almacen_s3_guarda_el_archivo_y_devuelve_su_url_publica(s3_simulado):
    almacen = storage.get_almacen()
    assert isinstance(almacen, storage.AlmacenS3) and almacen.base_url == "https://cdn.ejemplo.com/archivos"
    url = almacen.guardar(PDF, "application/pdf", "CERTIFICATE_PDF")
    assert url.startswith("https://cdn.ejemplo.com/archivos/certificados/") and url.endswith(".pdf")
    clave = url.removeprefix("https://cdn.ejemplo.com/archivos/")
    objeto = s3_simulado.get_object(Bucket="archivos", Key=clave)
    assert objeto["Body"].read() == PDF and objeto["ContentType"] == "application/pdf"
    assert "immutable" in objeto["CacheControl"]


def test_sin_variables_s3_se_usa_la_carpeta_local(monkeypatch):
    monkeypatch.setattr(config, "S3_BUCKET", "")
    assert isinstance(storage.get_almacen(), storage.AlmacenLocal)


def test_subir_un_archivo_por_la_api_lo_deja_en_el_bucket(client, auth, s3_simulado):
    del app.dependency_overrides[storage.get_almacen]                                   # usar el almacén real (el simulado de moto)
    r = client.post("/api/v1/files", headers={**auth, "Idempotency-Key": clave_nueva()}, data={"purpose": "STACK_LOGO"}, files={"file": ("l.png", PNG, "image/png")})
    assert r.status_code == 201
    url = r.json()["data"]["url"]
    assert url.startswith("https://cdn.ejemplo.com/archivos/logos/")
    assert s3_simulado.get_object(Bucket="archivos", Key=url.removeprefix("https://cdn.ejemplo.com/archivos/"))["Body"].read() == PNG
    certificado = client.post("/api/v1/certificates", headers={**auth, "Idempotency-Key": clave_nueva()}, json={
        "title": "Con almacén externo", "issuer": "Academia", "issued_at": "2026-09-01", "pdf_url": url.replace("logos", "certificados"), "image_url": url})
    assert certificado.status_code == 201                                               # la URL del bucket pasa la validación de origen


def test_si_el_almacen_externo_falla_la_api_responde_502_sin_datos_internos(client, auth, s3_simulado):
    del app.dependency_overrides[storage.get_almacen]
    s3_simulado.delete_bucket(Bucket="archivos")                                        # el bucket desapareció
    r = client.post("/api/v1/files", headers={**auth, "Idempotency-Key": clave_nueva()}, data={"purpose": "STACK_LOGO"}, files={"file": ("l.png", PNG, "image/png")})
    assert r.status_code == 502 and r.json()["code"] == "STORAGE_UNAVAILABLE"
    assert "archivos" not in r.json()["message"] and "NoSuchBucket" not in r.text


# ================================================================== aviso al deploy hook (Vercel)
class Reloj:
    def __init__(self):
        self.ahora = 1000.0

    def __call__(self):
        return self.ahora


class Programador:
    """En lugar de esperar de verdad, guarda lo que se quiso programar para ejecutarlo a mano."""

    def __init__(self):
        self.tareas = []

    def __call__(self, segundos, funcion):
        self.tareas.append((segundos, funcion))

    def ejecutar_siguiente(self):
        segundos, funcion = self.tareas.pop(0)
        funcion()
        return segundos


class Hook:
    """Un deploy hook de mentiras: cada petición recibe la siguiente respuesta (un código HTTP o una excepción)."""

    def __init__(self, *respuestas):
        self.respuestas = deque(respuestas)
        self.peticiones = []
        self.cliente = httpx.Client(transport=httpx.MockTransport(self._manejar))

    def _manejar(self, peticion):
        self.peticiones.append(str(peticion.url))
        respuesta = self.respuestas[0] if len(self.respuestas) == 1 else self.respuestas.popleft()
        if isinstance(respuesta, Exception):
            raise respuesta
        return httpx.Response(respuesta, json={"job": {"id": "x"}})


def notificador(hook, **extra):
    reloj, programador = Reloj(), Programador()
    return NotificadorDeploy(URL_SECRETA, cliente=hook.cliente, reloj=reloj, programar=programador, **extra), reloj, programador


def test_el_primer_aviso_sale_de_inmediato_y_el_pipeline_lo_acepta():
    hook = Hook(201)
    n, _, programador = notificador(hook)
    assert n.notificar("PROJECT_PUBLISHED", "a") == ResultadoNotificacion(aceptada=True, lenta=False)
    assert hook.peticiones == [URL_SECRETA] and programador.tareas == []


def test_los_avisos_de_una_misma_ventana_se_juntan_en_uno_solo_al_cerrarla():
    hook = Hook(201)
    n, reloj, programador = notificador(hook)
    n.notificar("PROJECT_PUBLISHED", "a")
    reloj.ahora += 10
    for i in range(5):                                                  # 5 ediciones seguidas dentro de la ventana
        assert n.notificar("PROJECT_UPDATED", f"p{i}") == ResultadoNotificacion(aceptada=True)
    assert len(hook.peticiones) == 1 and len(programador.tareas) == 1  # no se avisó otra vez; hay UN aviso programado
    assert programador.tareas[0][0] == pytest.approx(51)               # 60 - 10 + 1: justo después de que cierre la ventana
    reloj.ahora += 51
    programador.ejecutar_siguiente()
    assert len(hook.peticiones) == 2                                    # un único aviso con todos los cambios


def test_pasada_la_ventana_el_siguiente_aviso_sale_de_inmediato():
    hook = Hook(201)
    n, reloj, programador = notificador(hook)
    n.notificar("a", "1")
    reloj.ahora += 61
    assert n.notificar("b", "2").aceptada and len(hook.peticiones) == 2 and programador.tareas == []


def test_si_el_pipeline_no_responde_a_tiempo_se_responde_202_y_se_reintenta_con_esperas_crecientes(caplog):
    hook = Hook(httpx.ReadTimeout("lento"))
    n, _, programador = notificador(hook)
    assert n.notificar("PROJECT_PUBLISHED", "a") == ResultadoNotificacion(aceptada=False, lenta=True)
    esperas = []
    for _ in range(3):                                                  # los 3 reintentos, todos fallan
        esperas.append(programador.ejecutar_siguiente())
    assert esperas == [5.0, 15.0, 45.0] and programador.tareas == [] and len(hook.peticiones) == 4
    assert any("Se agotaron los reintentos" in r.message for r in caplog.records)


def test_un_reintento_exitoso_detiene_la_cadena():
    hook = Hook(httpx.ConnectError("sin red"), 503, 201)
    n, _, programador = notificador(hook)
    assert n.notificar("a", "1").lenta
    programador.ejecutar_siguiente()                                    # 1.er reintento: 503
    programador.ejecutar_siguiente()                                    # 2.º reintento: 201 -> listo
    assert programador.tareas == [] and len(hook.peticiones) == 3


def test_un_aviso_rechazado_por_configuracion_no_se_reintenta(caplog):
    hook = Hook(404)
    n, _, programador = notificador(hook)
    assert n.notificar("a", "1") == ResultadoNotificacion(aceptada=False, lenta=False)    # 200, no 202: no es lentitud
    assert programador.tareas == [] and "Revisa DEPLOY_HOOK_URL" in caplog.text


def test_tras_un_fallo_el_siguiente_aviso_vuelve_a_intentarlo_de_inmediato():
    hook = Hook(500, 201)
    n, _, _ = notificador(hook)
    assert n.notificar("a", "1").lenta
    assert n.notificar("b", "2").aceptada and len(hook.peticiones) == 2


def test_la_direccion_secreta_del_deploy_hook_nunca_sale_en_los_registros(caplog):
    caplog.set_level(logging.DEBUG)
    for respuesta in (201, 404, 503, httpx.ReadTimeout("lento"), httpx.ConnectError("sin red")):
        hook = Hook(respuesta)
        n, reloj, programador = notificador(hook)
        n.notificar("a", "1")
        while programador.tareas:
            programador.ejecutar_siguiente()
    assert URL_SECRETA not in caplog.text and "TOKEN-MUY-SECRETO" not in caplog.text and "SECRETO123" not in caplog.text
    assert caplog.records, "se esperaban mensajes en el registro"


def test_avisos_simultaneos_producen_una_sola_peticion():
    lanzar = threading.Barrier(8)
    hook = Hook(201)
    n, _, _ = notificador(hook)
    resultados = []

    def avisar():
        lanzar.wait()
        resultados.append(n.notificar("PROJECT_UPDATED", "x"))

    hilos = [threading.Thread(target=avisar) for _ in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert len(hook.peticiones) == 1 and all(r.aceptada for r in resultados)


def test_get_notificador_es_nulo_sin_direccion_y_compartido_con_ella(monkeypatch):
    monkeypatch.setattr(config, "DEPLOY_HOOK_URL", "")
    assert isinstance(get_notificador(), NotificadorNulo)
    monkeypatch.setattr(config, "DEPLOY_HOOK_URL", URL_SECRETA)
    primero = get_notificador()
    assert isinstance(primero, NotificadorDeploy) and get_notificador() is primero      # el mismo: así recuerda la ventana de 60 s
    monkeypatch.setattr(config, "DEPLOY_HOOK_URL", URL_SECRETA + "-otro")
    assert get_notificador() is not primero


# ---- el aviso real, de punta a punta con la API
def _crear_y_completar(client, auth):
    kotlin = next(i["stack_id"] for i in client.get("/api/v1/public/tech-stack", params={"limit": 50}).json()["data"]["items"] if i["name"] == "Kotlin")
    cuerpo = {"title": "Proyecto con aviso", "slug": "proyecto-con-aviso", "short_description": "Resumen", "description": "Descripción suficientemente larga del proyecto.",
              "project_date": "2026-09-01", "stack_ids": [kotlin]}
    pid = client.post("/api/v1/projects", json=cuerpo, headers={**auth, "Idempotency-Key": clave_nueva()}).json()["data"]["project_id"]
    return pid, cuerpo


def test_publicar_avisa_a_vercel_y_las_ediciones_seguidas_se_agrupan(client, auth):
    hook = Hook(201)
    n, reloj, programador = notificador(hook)
    app.dependency_overrides[get_notificador] = lambda: n
    pid, cuerpo = _crear_y_completar(client, auth)
    publicado = client.post(f"/api/v1/projects/{pid}/publish", headers={**auth, "Idempotency-Key": clave_nueva()})
    assert publicado.status_code == 200 and publicado.json()["data"]["recompilation_triggered"] is True and len(hook.peticiones) == 1
    for titulo in ("Uno", "Dos", "Tres"):
        r = client.put(f"/api/v1/projects/{pid}", headers=auth, json={**cuerpo, "title": f"Proyecto con aviso {titulo}", "is_featured": False})
        assert r.status_code == 200 and r.json()["data"]["recompilation_triggered"] is True
    assert len(hook.peticiones) == 1 and len(programador.tareas) == 1       # 3 ediciones, ningún aviso extra: uno al cerrar la ventana
    programador.ejecutar_siguiente()
    assert len(hook.peticiones) == 2


def test_si_vercel_no_responde_la_operacion_se_aplica_y_responde_202(client, auth):
    hook = Hook(httpx.ReadTimeout("lento"))
    n, _, programador = notificador(hook)
    app.dependency_overrides[get_notificador] = lambda: n
    pid, _ = _crear_y_completar(client, auth)
    r = client.post(f"/api/v1/projects/{pid}/publish", headers={**auth, "Idempotency-Key": clave_nueva()})
    assert r.status_code == 202 and r.json()["data"]["recompilation_triggered"] is False
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).json()["data"]["status"] == "PUBLICADO"
    assert len(programador.tareas) == 1                                      # y el aviso quedó en reintento


# ================================================================== seguridad por filas (Postgres)
def test_en_sqlite_activar_la_seguridad_por_filas_no_hace_nada(session_factory):
    from app.database import activar_seguridad_por_filas
    activar_seguridad_por_filas(session_factory.kw["bind"])


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="necesita una base Postgres (TEST_DATABASE_URL)")
def test_postgres_otros_roles_no_ven_las_tablas_pero_el_dueno_si(session_factory):
    """Simula la clave 'pública' de Supabase: un rol limitado con permiso de lectura NO debe ver ni una fila."""
    from sqlalchemy import text
    from app.database import activar_seguridad_por_filas

    motor = session_factory.kw["bind"]
    activar_seguridad_por_filas(motor)
    activar_seguridad_por_filas(motor)                                              # repetirlo es seguro
    rol = f"anonimo_{uuid.uuid4().hex[:8]}"
    with motor.begin() as c:
        c.execute(text(f"CREATE ROLE {rol} NOLOGIN"))
        c.execute(text(f"GRANT USAGE ON SCHEMA public TO {rol}"))
        c.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {rol}"))
    try:
        with motor.begin() as c:
            assert c.execute(text("SELECT count(*) FROM projects")).scalar() == 3          # la dueña (la API) ve todo
            assert c.execute(text("SELECT count(*) FROM pg_class WHERE relrowsecurity AND relname IN ('projects','certificates','profile','tech_stack_items','idempotency_keys')")).scalar() == 5
            c.execute(text(f"SET LOCAL ROLE {rol}"))
            assert c.execute(text("SELECT count(*) FROM projects")).scalar() == 0          # el rol limitado, nada
            assert c.execute(text("SELECT count(*) FROM profile")).scalar() == 0
            with pytest.raises(Exception):
                c.execute(text("INSERT INTO certificates (certificate_id, title, issuer, issued_at, pdf_url, image_url, created_at, updated_at) VALUES ('x','t','i','2026-01-01','https://a','https://b',now(),now())"))
    finally:
        with motor.begin() as c:
            c.execute(text(f"DROP OWNED BY {rol}"))
            c.execute(text(f"DROP ROLE {rol}"))
