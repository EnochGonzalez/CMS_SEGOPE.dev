"""Registro público de visitas (POST /api/v1/track, GET /t.js) y estadísticas (GET /api/v1/stats)."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import config
from app.models import PageView, Site
from app.services import analitica
from tests.conftest import clave_nueva

NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
DOMINIO = "segope.vercel.app"


@pytest.fixture(autouse=True)
def _limpiar_limitador():
    analitica.limitador_vistas.reiniciar()
    yield
    analitica.limitador_vistas.reiniciar()


@pytest.fixture()
def sitio(client, auth):
    r = client.post("/api/v1/sites", json={"name": "Mi blog", "domain": DOMINIO, "color": "#ef4444"},
                    headers={**auth, "Idempotency-Key": clave_nueva()})
    assert r.status_code == 201
    return r.json()["data"]["site_id"]


def _visita(client, cuerpo=None, origen=f"https://{DOMINIO}", agente=NAVEGADOR, ip="203.0.113.7", texto=True):
    cuerpo = cuerpo if cuerpo is not None else {"site": DOMINIO, "path": "/index.html"}
    cabeceras = {"User-Agent": agente, "X-Forwarded-For": ip}
    if origen:
        cabeceras["Origin"] = origen
    if texto:           # así lo manda sendBeacon: texto plano
        import json
        return client.post("/api/v1/track", content=json.dumps(cuerpo) if isinstance(cuerpo, dict) else cuerpo,
                           headers={**cabeceras, "Content-Type": "text/plain;charset=UTF-8"})
    return client.post("/api/v1/track", json=cuerpo, headers=cabeceras)


def _guardadas(session_factory):
    with session_factory() as db:
        return db.scalars(select(PageView).order_by(PageView.view_id)).all()


def _poner(session_factory, site_id, ruta, dias_atras=0, visitante="v1", fuente=None, hora=12):
    """Inserta una visita con fecha controlada (para probar los cálculos). Como en la realidad, el hash del visitante
    es distinto cada día: «b» hoy y «b» ayer son dos visitantes."""
    dia = analitica.hoy_local() - timedelta(days=dias_atras)
    with session_factory() as db:
        db.add(PageView(site_id=site_id, path=ruta, visitor=f"{visitante}-{dias_atras}", referrer_host=fuente, day=dia, hour=hora,
                        occurred_at=analitica.ahora_local()))
        db.commit()


# ================================================================== registrar visitas
def test_visita_valida_se_guarda_con_ruta_normalizada(client, sitio, session_factory):
    r = _visita(client, {"site": DOMINIO, "path": "/HTML/proyecto/index.html?utm=1#x", "referrer": "https://www.google.com/search?q=a"})
    assert r.status_code == 204 and r.content == b""
    (vista,) = _guardadas(session_factory)
    assert vista.path == "/HTML/proyecto"
    assert vista.referrer_host == "www.google.com"
    assert len(vista.visitor) == 16 and "203.0.113.7" not in vista.visitor            # hash, no la IP
    assert vista.day == analitica.hoy_local()


def test_tambien_acepta_json_normal(client, sitio, session_factory):
    assert _visita(client, texto=False).status_code == 204
    assert len(_guardadas(session_factory)) == 1


def test_inicio_y_index_html_son_la_misma_pagina():
    assert analitica.normalizar_ruta("/index.html") == "/"
    assert analitica.normalizar_ruta("") == "/"
    assert analitica.normalizar_ruta("//a//b/") == "/a/b"
    assert analitica.normalizar_ruta("/x\x00y") == "/xy"
    assert len(analitica.normalizar_ruta("/" + "a" * 500)) == 200


def test_referencia_interna_directa_y_externa():
    assert analitica.host_de_referencia(None, DOMINIO) is None
    assert analitica.host_de_referencia("", DOMINIO) is None
    assert analitica.host_de_referencia(f"https://{DOMINIO}/otra", DOMINIO) == analitica.REFERENCIA_INTERNA
    assert analitica.host_de_referencia("https://GitHub.com/x", DOMINIO) == "github.com"
    assert analitica.host_de_referencia("esto no es una url", DOMINIO) is None


def test_origen_distinto_da_403_y_no_guarda(client, sitio, session_factory):
    r = _visita(client, origen="https://otro-sitio.com")
    assert r.status_code == 403 and r.json()["code"] == "ORIGIN_NOT_ALLOWED"
    assert _visita(client, origen=None).status_code == 403                               # sin Origin tampoco
    assert _guardadas(session_factory) == []


def test_sitio_desconocido_o_en_pausa_da_404(client, auth, sitio, session_factory):
    r = _visita(client, {"site": "no-registrado.com", "path": "/"}, origen="https://no-registrado.com")
    assert r.status_code == 404 and r.json()["code"] == "SITE_NOT_FOUND"
    client.put(f"/api/v1/sites/{sitio}", headers=auth, json={"name": "Mi blog", "domain": DOMINIO, "color": "#ef4444", "is_active": False})
    assert _visita(client).status_code == 404
    assert _guardadas(session_factory) == []


def test_los_robots_se_ignoran_sin_error(client, sitio, session_factory):
    for agente in ("Googlebot/2.1 (+http://www.google.com/bot.html)", "curl/8.0", "HeadlessChrome/120", ""):
        assert _visita(client, agente=agente).status_code == 204
    assert _guardadas(session_factory) == []


def test_cuerpo_invalido_o_enorme(client, sitio):
    assert _visita(client, "esto no es json").status_code == 422
    r = _visita(client, {"site": DOMINIO})
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "path"
    assert _visita(client, {"site": DOMINIO, "path": "/", "relleno": "x" * 5000}).status_code == 413


def test_limite_de_visitas_por_visitante(client, sitio, session_factory, monkeypatch):
    monkeypatch.setattr(config, "ANALITICA_MAX_VISTAS", 3)
    codigos = [_visita(client).status_code for _ in range(5)]
    assert codigos == [204, 204, 204, 429, 429]
    assert len(_guardadas(session_factory)) == 3
    assert _visita(client, ip="198.51.100.9").status_code == 204                         # otro visitante sí puede


def test_el_hash_cambia_por_dia_sitio_y_visitante():
    hoy = analitica.hoy_local()
    base = analitica.huella_visitante("1.1.1.1", NAVEGADOR, "sitio-a", hoy)
    assert base == analitica.huella_visitante("1.1.1.1", NAVEGADOR, "sitio-a", hoy)
    assert base != analitica.huella_visitante("1.1.1.1", NAVEGADOR, "sitio-a", hoy + timedelta(days=1))
    assert base != analitica.huella_visitante("1.1.1.1", NAVEGADOR, "sitio-b", hoy)
    assert base != analitica.huella_visitante("1.1.1.2", NAVEGADOR, "sitio-a", hoy)


def test_se_borran_las_visitas_mas_viejas_que_la_retencion(client, sitio, session_factory, monkeypatch):
    monkeypatch.setattr(config, "ANALITICA_DIAS_RETENCION", 30)
    _poner(session_factory, sitio, "/vieja", dias_atras=31)
    _poner(session_factory, sitio, "/limite", dias_atras=30)
    _poner(session_factory, sitio, "/nueva", dias_atras=0)
    with session_factory() as db:
        assert analitica.purgar_antiguas(db) == 1
    assert sorted(v.path for v in _guardadas(session_factory)) == ["/limite", "/nueva"]


def test_el_script_de_seguimiento_se_sirve(client):
    r = client.get("/t.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/javascript")
    assert "sendBeacon" in r.text and "/api/v1/track" in r.text


# ================================================================== estadísticas
def test_estadisticas_exigen_token_y_periodo_valido(client, auth):
    assert client.get("/api/v1/stats").status_code == 401
    r = client.get("/api/v1/stats", params={"period": "5y"}, headers=auth)
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "period"
    assert client.get("/api/v1/stats", params={"site_id": "no-existe"}, headers=auth).status_code == 404


def test_estadisticas_sin_visitas_son_ceros_con_serie_completa(client, auth, sitio):
    datos = client.get("/api/v1/stats", params={"period": "1w"}, headers=auth).json()["data"]
    assert datos["totals"] == {"views": 0, "visitors": 0, "pages": 0, "views_prev": 0, "visitors_prev": 0,
                               "views_delta_pct": None, "visitors_delta_pct": None}
    assert len(datos["series"]) == 7 and all(p["views"] == 0 for p in datos["series"])
    assert datos["top_pages"] == [] and datos["referrers"] == []
    assert [s["domain"] for s in datos["sites"]] == [DOMINIO]                              # el sitio aparece con 0


def test_totales_delta_series_paginas_y_fuentes(client, auth, sitio, session_factory):
    # Esta semana (7 días): 5 visitas de 4 visitantes (por día) en 2 páginas. La semana anterior: 2 visitas de 2 visitantes.
    _poner(session_factory, sitio, "/", 0, "a", "github.com")
    _poner(session_factory, sitio, "/", 0, "a", analitica.REFERENCIA_INTERNA)
    _poner(session_factory, sitio, "/", 1, "b", None)
    _poner(session_factory, sitio, "/HTML/lawpocket", 2, "b", "github.com")
    _poner(session_factory, sitio, "/HTML/lawpocket", 6, "c", "www.google.com")
    _poner(session_factory, sitio, "/", 7, "x")
    _poner(session_factory, sitio, "/", 13, "y")
    _poner(session_factory, sitio, "/", 14, "z")                                           # fuera de los dos periodos

    d = client.get("/api/v1/stats", params={"period": "1w"}, headers=auth).json()["data"]
    assert d["totals"] == {"views": 5, "visitors": 4, "pages": 2, "views_prev": 2, "visitors_prev": 2,
                           "views_delta_pct": 150.0, "visitors_delta_pct": 100.0}
    assert [p["views"] for p in d["series"]] == [1, 0, 0, 0, 1, 1, 2]                      # del día 6 atrás a hoy
    assert d["series"][-1]["label"] == analitica.hoy_local().isoformat()
    assert [(p["path"], p["views"]) for p in d["top_pages"]] == [("/", 3), ("/HTML/lawpocket", 2)]
    fuentes = {f["source"]: f["views"] for f in d["referrers"]}
    assert fuentes == {"github.com": 2, None: 1, "www.google.com": 1}                       # lo interno no cuenta como fuente
    assert d["sites"][0]["views"] == 5 and d["sites"][0]["share_pct"] == 100.0 and d["sites"][0]["delta_pct"] == 150.0


def test_hoy_se_agrupa_por_hora(client, auth, sitio, session_factory):
    _poner(session_factory, sitio, "/", 0, "a", hora=9)
    _poner(session_factory, sitio, "/", 0, "b", hora=9)
    _poner(session_factory, sitio, "/", 0, "c", hora=22)
    _poner(session_factory, sitio, "/", 1, "d", hora=9)                                     # ayer: solo cuenta como «anterior»
    d = client.get("/api/v1/stats", params={"period": "1d"}, headers=auth).json()["data"]
    assert d["granularity"] == "hour" and len(d["series"]) == 24
    assert d["series"][9] == {"label": "09:00", "views": 2, "visitors": 2}
    assert d["series"][22]["views"] == 1
    assert d["totals"]["views"] == 3 and d["totals"]["views_prev"] == 1


def test_cada_periodo_tiene_los_dias_esperados(client, auth, sitio):
    for periodo, dias in [("1w", 7), ("2w", 14), ("1m", 30), ("3m", 90), ("1y", 365)]:
        d = client.get("/api/v1/stats", params={"period": periodo}, headers=auth).json()["data"]
        assert d["granularity"] == "day" and len(d["series"]) == dias, periodo
        assert d["series"][0]["label"] == (analitica.hoy_local() - timedelta(days=dias - 1)).isoformat()


def test_filtrar_por_sitio_y_porcentaje_de_cada_uno(client, auth, sitio, session_factory):
    otro = client.post("/api/v1/sites", json={"name": "Otro", "domain": "otro.com", "color": "#2563eb"},
                       headers={**auth, "Idempotency-Key": clave_nueva()}).json()["data"]["site_id"]
    for _ in range(3):
        _poner(session_factory, sitio, "/", 0, "a")
    _poner(session_factory, otro, "/", 0, "b")
    todos = client.get("/api/v1/stats", params={"period": "1w"}, headers=auth).json()["data"]
    assert [(s["domain"], s["views"], s["share_pct"]) for s in todos["sites"]] == [(DOMINIO, 3, 75.0), ("otro.com", 1, 25.0)]
    solo = client.get("/api/v1/stats", params={"period": "1w", "site_id": otro}, headers=auth).json()["data"]
    assert solo["totals"]["views"] == 1 and [s["domain"] for s in solo["sites"]] == ["otro.com"]
    assert [p["site_name"] for p in solo["top_pages"]] == ["Otro"]


def test_flujo_completo_desde_el_navegador_hasta_el_panel(client, auth, sitio):
    for ruta in ("/index.html", "/index.html", "/HTML/taylor"):
        assert _visita(client, {"site": DOMINIO, "path": ruta, "referrer": "https://github.com/"}, ip=f"10.0.0.{len(ruta)}").status_code == 204
    d = client.get("/api/v1/stats", params={"period": "1d"}, headers=auth).json()["data"]
    assert d["totals"]["views"] == 3 and d["totals"]["pages"] == 2
    assert d["top_pages"][0]["path"] == "/" and d["referrers"][0] == {"source": "github.com", "views": 3}
