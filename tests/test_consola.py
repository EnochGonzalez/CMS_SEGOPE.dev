"""La consola de administración (admin/): se sirve bien, es segura y no tiene referencias rotas."""
import re
from pathlib import Path

import pytest

from app.consola import CARPETA_CONSOLA

ARCHIVOS_JS = sorted(CARPETA_CONSOLA.rglob("*.js"))


def test_la_consola_se_sirve_en_admin_con_cabeceras_de_seguridad(client):
    r = client.get("/admin/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "style-src 'self'" in csp and "connect-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["cache-control"] == "no-cache"
    assert 'name="robots" content="noindex, nofollow"' in r.text


def test_admin_sin_barra_redirige_a_admin_barra(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code in (301, 307, 308) and r.headers["location"].endswith("/admin/")


def test_todos_los_archivos_que_pide_la_pagina_existen_y_tienen_el_tipo_correcto(client):
    html = client.get("/admin/").text
    referencias = re.findall(r'(?:src|href)="([^"]+)"', html)
    locales = [r for r in referencias if not r.startswith(("data:", "http", "#"))]
    assert "css/admin.css" in locales and "js/app.js" in locales
    for ruta in locales:
        r = client.get(f"/admin/{ruta}")
        assert r.status_code == 200, ruta
        tipo = r.headers["content-type"]
        assert ("javascript" in tipo) if ruta.endswith(".js") else ("css" in tipo), (ruta, tipo)
        assert "content-security-policy" in r.headers                       # también los CSS y JS llevan las cabeceras


@pytest.mark.parametrize("archivo", ARCHIVOS_JS, ids=lambda a: str(a.relative_to(CARPETA_CONSOLA)))
def test_cada_import_de_javascript_apunta_a_un_archivo_que_existe(client, archivo):
    codigo = archivo.read_text(encoding="utf-8")
    importados = re.findall(r"""(?:from|import)\s+['"](\.{1,2}/[^'"]+)['"]""", codigo)
    for destino in importados:
        ruta = (archivo.parent / destino).resolve()
        assert ruta.is_file(), f"{archivo.name} importa {destino}, que no existe"
        relativa = ruta.relative_to(CARPETA_CONSOLA.resolve()).as_posix()
        assert client.get(f"/admin/{relativa}").status_code == 200


def test_cada_modulo_importa_solo_lo_que_el_otro_exporta(client):
    """Un nombre mal escrito en un import no falla hasta abrir la página; aquí se detecta antes."""
    exportado = {}
    for archivo in ARCHIVOS_JS:
        codigo = archivo.read_text(encoding="utf-8")
        nombres = set(re.findall(r"export\s+(?:async\s+)?(?:function|const|class|let)\s+(\w+)", codigo))
        for grupo in re.findall(r"export\s*\{([^}]+)\}", codigo):
            nombres |= {n.strip().split(" as ")[-1] for n in grupo.split(",")}
        exportado[archivo.resolve()] = nombres
    for archivo in ARCHIVOS_JS:
        codigo = archivo.read_text(encoding="utf-8")
        for nombres, destino in re.findall(r"import\s*\{([^}]+)\}\s*from\s*['\"](\.{1,2}/[^'\"]+)['\"]", codigo):
            pedidos = {n.strip().split(" as ")[0] for n in nombres.split(",") if n.strip()}
            faltan = pedidos - exportado[(archivo.parent / destino).resolve()]
            assert not faltan, f"{archivo.name} importa de {destino} algo que no existe: {sorted(faltan)}"
        for destino in re.findall(r"import\s+\*\s+as\s+\w+\s+from\s+['\"](\.{1,2}/[^'\"]+)['\"]", codigo):
            assert "montar" in exportado[(archivo.parent / destino).resolve()], f"{destino} debe exportar montar()"


def test_la_pagina_no_tiene_codigo_ni_estilos_en_linea(client):
    html = client.get("/admin/").text
    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "hay un <script> en línea (la CSP lo bloquearía)"
    assert not re.search(r"\sstyle=", html) and "<style" not in html and not re.search(r"\son\w+=", html)


@pytest.mark.parametrize("archivo", ARCHIVOS_JS, ids=lambda a: str(a.relative_to(CARPETA_CONSOLA)))
def test_el_javascript_no_usa_patrones_que_permitan_inyectar_codigo(client, archivo):
    codigo = archivo.read_text(encoding="utf-8")
    codigo = re.sub(r"//.*", "", codigo)                                     # los comentarios no cuentan
    prohibidos = [r"\.innerHTML", r"\.outerHTML", r"insertAdjacentHTML", r"document\.write", r"\beval\(", r"new Function",
                  r"setAttribute\(\s*['\"]style['\"]", r"\.cssText", r"javascript:"]
    for patron in prohibidos:
        assert not re.search(patron, codigo), f"{archivo.name} usa {patron}"


def test_un_archivo_inexistente_de_la_consola_responde_404(client):
    assert client.get("/admin/js/no-existe.js").status_code == 404


def test_la_consola_no_expone_nada_de_la_api_sin_token(client):
    """La página es pública (solo código), pero los datos siguen pidiendo token."""
    assert client.get("/api/v1/projects").status_code == 401


def test_los_tipos_de_archivo_de_js_y_css_no_dependen_del_registro_de_windows(monkeypatch):
    """Si el sistema dijera que .js es text/plain, la consola se registra con el tipo correcto de todos modos."""
    import importlib
    import mimetypes

    from app import consola

    mimetypes.add_type("text/plain", ".js")                       # simula una instalación de Windows mal configurada
    mimetypes.add_type("text/plain", ".css")
    importlib.reload(consola)
    assert mimetypes.guess_type("app.js")[0] == "text/javascript"
    assert mimetypes.guess_type("admin.css")[0] == "text/css"
