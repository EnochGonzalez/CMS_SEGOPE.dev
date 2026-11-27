"""Apariencia del blog: lectura pública, opciones, actualización, validación de contraste y aviso al pipeline."""
import pytest
from sqlalchemy import func, select

from app.models import ThemeSettings
from app.services import tema

PUBLICO = "/api/v1/public/theme"
OPCIONES = "/api/v1/public/theme/options"
RUTA = "/api/v1/theme"

# Los valores del CSS actual del blog (:root de CSS/index.css). La prueba equivalente del repositorio del blog compara su CSS real
# con su copia de estos valores: si alguien cambia los colores en un lado y no en el otro, una de las dos falla.
CSS_ORIGINAL_DEL_BLOG = {
    "--bg": "#0c0404", "--bg-elevated": "#160808", "--ink": "#ffffff", "--ink-soft": "#a39898", "--line": "#301010",
    "--line-strong": "#4a1c1c", "--accent": "#ef4444", "--accent-warm": "#dc2626",
    "--font-body": "'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif", "--font-mono": "'Courier New', Courier, monospace",
    "--radius": "3px",
}


def _cuerpo(**cambios):
    return {**tema.PREDETERMINADO, **cambios}


# ================================================================== lectura pública
def test_sin_personalizar_se_devuelve_el_diseno_original(client):
    r = client.get(PUBLICO)
    assert r.status_code == 200
    datos = r.json()["data"]
    assert datos["updated_at"] is None and datos["preset"] == "segope" and datos["accent"] is None
    assert datos["resolved"]["is_default"] is True and datos["resolved"]["root_font_size"] == "100%"
    assert datos["resolved"]["vars"] == CSS_ORIGINAL_DEL_BLOG                       # idéntico al CSS del blog


def test_la_lectura_publica_no_pide_token_y_usa_cache(client):
    primera = client.get(PUBLICO)
    assert primera.status_code == 200 and primera.headers.get("etag")
    assert client.get(PUBLICO, headers={"If-None-Match": primera.headers["etag"]}).status_code == 304
    assert client.get(OPCIONES).status_code == 200


def test_las_opciones_traen_todo_para_dibujar_la_consola(client):
    d = client.get(OPCIONES).json()["data"]
    assert [p["key"] for p in d["presets"]] == ["segope", "azul-noche", "verde-terminal", "violeta"]
    assert all(set(p["palette"]) == {"bg", "bg_elevated", "ink", "ink_soft", "line", "line_strong", "accent", "accent_warm"} for p in d["presets"])
    assert [f["key"] for f in d["fonts_body"]] == ["sistema", "serif", "humanista"] and [f["key"] for f in d["fonts_mono"]] == ["clasica", "moderna"]
    assert [x["key"] for x in d["radius"]] == ["cuadradas", "normales", "redondeadas"] and [x["key"] for x in d["text_size"]] == ["pequeno", "normal", "grande"]
    assert d["default"] == tema.PREDETERMINADO and d["min_contrast_text"] == 4.5 and d["min_contrast_button"] == 3.0


# ================================================================== actualizar
def test_actualizar_exige_token(client):
    assert client.put(RUTA, json=_cuerpo()).status_code == 401


def test_guardar_aplica_el_estilo_y_avisa_al_pipeline(client, auth, notificador, session_factory):
    r = client.put(RUTA, json=_cuerpo(preset="azul-noche", font_body="serif", radius="redondeadas", text_size="grande"), headers=auth)
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["recompilation_triggered"] is True and d["resolved"]["is_default"] is False
    assert d["resolved"]["vars"]["--accent"] == "#3b82f6" and d["resolved"]["vars"]["--bg"] == "#060b18"
    assert d["resolved"]["vars"]["--font-body"].startswith("Georgia") and d["resolved"]["vars"]["--radius"] == "10px"
    assert d["resolved"]["root_font_size"] == "110%"
    with session_factory() as db:
        fila = db.scalar(select(ThemeSettings))
    assert notificador.llamadas == [("THEME_UPDATED", fila.theme_id)]
    leido = client.get(PUBLICO).json()["data"]                                      # lo que ve el generador
    assert leido["preset"] == "azul-noche" and leido["resolved"]["vars"] == d["resolved"]["vars"] and leido["updated_at"]


def test_es_un_registro_unico_aunque_se_guarde_muchas_veces(client, auth, session_factory):
    for estilo in ("violeta", "verde-terminal", "segope"):
        assert client.put(RUTA, json=_cuerpo(preset=estilo), headers=auth).status_code == 200
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ThemeSettings)) == 1


def test_volver_al_original_deja_el_blog_sin_css_extra(client, auth):
    client.put(RUTA, json=_cuerpo(preset="violeta", radius="cuadradas"), headers=auth)
    r = client.put(RUTA, json=_cuerpo(), headers=auth)
    assert r.json()["data"]["resolved"]["is_default"] is True
    assert client.get(PUBLICO).json()["data"]["resolved"]["vars"] == CSS_ORIGINAL_DEL_BLOG


def test_un_acento_propio_se_guarda_en_minusculas_y_calcula_su_variante_oscura(client, auth):
    r = client.put(RUTA, json=_cuerpo(accent="#0284C7"), headers=auth)
    assert r.status_code == 200
    v = r.json()["data"]["resolved"]["vars"]
    assert r.json()["data"]["accent"] == "#0284c7" and v["--accent"] == "#0284c7" and v["--accent-warm"] == tema.acento_calido("#0284c7")
    assert tema.luminancia(v["--accent-warm"]) < tema.luminancia(v["--accent"])
    assert r.json()["data"]["resolved"]["is_default"] is False


def test_un_acento_demasiado_oscuro_se_rechaza_con_un_mensaje_claro(client, auth, notificador):
    r = client.put(RUTA, json=_cuerpo(accent="#1a1a1a"), headers=auth)
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "accent"
    assert "más claro" in r.json()["details"][0]["issue"]
    assert notificador.llamadas == []                                               # no se guardó ni se avisó
    assert client.get(PUBLICO).json()["data"]["updated_at"] is None


def test_un_acento_demasiado_claro_se_rechaza_porque_el_texto_blanco_no_se_lee(client, auth):
    r = client.put(RUTA, json=_cuerpo(accent="#f97316"), headers=auth)             # naranja claro: se lee sobre oscuro, pero no con texto blanco (2.8:1)
    assert r.status_code == 422 and "más oscuro" in r.json()["details"][0]["issue"]


@pytest.mark.parametrize("cambio", [
    {"preset": "neon"}, {"font_body": "comic-sans"}, {"font_mono": "x"}, {"radius": "ovalada"}, {"text_size": "enorme"},
    {"accent": "rojo"}, {"accent": "#fff"}, {"extra": 1}, {"preset": None}, {"font_body": None},
])
def test_datos_invalidos_dan_422(client, auth, cambio):
    cuerpo = _cuerpo()
    cuerpo.update(cambio)
    assert client.put(RUTA, json=cuerpo, headers=auth).status_code == 422


def test_put_reemplaza_todo_asi_que_faltar_un_campo_es_error(client, auth):
    cuerpo = _cuerpo()
    del cuerpo["radius"]
    r = client.put(RUTA, json=cuerpo, headers=auth)
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "radius"


def test_si_el_pipeline_tarda_la_respuesta_es_202(client, auth, notificador):
    notificador.lenta = True
    r = client.put(RUTA, json=_cuerpo(preset="violeta"), headers=auth)
    assert r.status_code == 202 and r.json()["data"]["recompilation_triggered"] is True


# ================================================================== el catálogo en sí
@pytest.mark.parametrize("estilo", list(tema.PRESETS))
def test_cada_estilo_se_lee_bien(estilo):
    p = tema.PRESETS[estilo]
    assert tema.contraste(p["ink"], p["bg"]) >= 7 and tema.contraste(p["ink"], p["bg_elevated"]) >= 7
    assert tema.contraste(p["ink_soft"], p["bg"]) >= 4.5 and tema.contraste(p["ink_soft"], p["bg_elevated"]) >= 4.5
    assert tema.contraste(p["accent"], p["bg"]) >= tema.CONTRASTE_MIN_TEXTO and tema.contraste(p["accent"], p["bg_elevated"]) >= 4.0
    assert tema.contraste("#ffffff", p["accent"]) >= tema.CONTRASTE_MIN_BOTON
    assert tema.contraste(p["accent_warm"], p["bg"]) >= 3.0                         # la variante oscura también debe verse


@pytest.mark.parametrize("estilo", list(tema.PRESETS))
def test_los_colores_sugeridos_se_aceptan_en_todos_los_estilos(client, auth, estilo):
    for color in tema.ACENTOS_SUGERIDOS:
        assert client.put(RUTA, json=_cuerpo(preset=estilo, accent=color), headers=auth).status_code == 200, (estilo, color)


def test_las_opciones_incluyen_los_colores_sugeridos(client):
    assert client.get(OPCIONES).json()["data"]["accent_suggestions"] == tema.ACENTOS_SUGERIDOS and len(tema.ACENTOS_SUGERIDOS) == 8


def test_las_tipografias_son_solo_las_del_sistema_y_sin_caracteres_peligrosos():
    import re
    for _, pila in [*tema.FUENTES_CUERPO.values(), *tema.FUENTES_MONO.values()]:
        assert re.fullmatch(r"[A-Za-z0-9 ,'\-]+", pila), pila
        assert "http" not in pila and "url" not in pila.lower()


def test_el_contraste_coincide_con_valores_conocidos():
    assert round(tema.contraste("#000000", "#ffffff"), 2) == 21.0
    assert round(tema.contraste("#777777", "#ffffff"), 2) == 4.48                   # el ejemplo clásico de WCAG
