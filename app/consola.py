"""Consola de administración: la carpeta admin/ (HTML, CSS y JS) la sirve la propia API en /admin/.

Al salir del mismo servidor que los datos no hace falta configurar CORS y funciona igual en tu computadora y ya publicada.
Las cabeceras impiden que la página ejecute código que no sea suyo (CSP), que la incrusten en otro sitio y que el
navegador guarde versiones viejas de los archivos mientras desarrollas.
"""
import mimetypes

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config

CARPETA_CONSOLA = config.RAIZ / "admin"

# En algunas instalaciones de Windows, Python toma de su registro que .js es "text/plain", y el navegador se niega
# a cargar módulos de JavaScript con ese tipo. Se fijan aquí para que la consola funcione igual en cualquier computadora.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

CABECERAS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'self' data: blob: https: http://localhost:* http://127.0.0.1:*; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-cache",            # el navegador revisa con la API si el archivo cambió (ETag) antes de usarlo
}


class ArchivosConsola(StaticFiles):
    def file_response(self, *args, **kwargs):
        respuesta = super().file_response(*args, **kwargs)
        respuesta.headers.update(CABECERAS)
        return respuesta


def montar_consola(app: FastAPI) -> None:
    app.mount("/admin", ArchivosConsola(directory=CARPETA_CONSOLA, html=True), name="consola")
