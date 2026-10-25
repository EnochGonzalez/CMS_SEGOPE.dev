"""Almacenamiento de los archivos que se suben (PDF e imágenes).

`Almacen` es una interfaz: hoy se usa `AlmacenLocal` (guarda en la carpeta uploads/ y la API la sirve en /media).
Al publicar la API se reemplaza por un servicio externo (Cloudinary, S3, Supabase Storage...) sin tocar los
endpoints, porque en servidores gratuitos el disco se borra con cada despliegue.

El tipo de un archivo se decide por su CONTENIDO (los primeros bytes), no por su nombre ni por lo que diga el cliente.
"""
from pathlib import Path
from typing import Protocol

from app import config
from app.ids import nuevo_id

# tipo MIME -> (extensión, ¿es imagen?)
TIPOS = {
    "application/pdf": ("pdf", False),
    "image/jpeg": ("jpg", True),
    "image/png": ("png", True),
    "image/webp": ("webp", True),
}

# propósito -> subcarpeta
CARPETAS = {
    "CERTIFICATE_PDF": "certificados",
    "CERTIFICATE_IMAGE": "certificados",
    "STACK_LOGO": "logos",
    "PROFILE_PHOTO": "perfil",
}


def detectar_tipo(contenido: bytes) -> str | None:
    """Reconoce PDF, JPEG, PNG y WebP por sus primeros bytes. Cualquier otra cosa devuelve None."""
    if contenido.startswith(b"%PDF-"):
        return "application/pdf"
    if contenido.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp"
    return None


class Almacen(Protocol):
    base_url: str

    def guardar(self, contenido: bytes, mime_type: str, purpose: str) -> str:
        """Guarda el archivo y devuelve su URL pública."""
        ...


class AlmacenLocal:
    def __init__(self, carpeta: Path, base_url: str):
        self.carpeta = Path(carpeta)
        self.base_url = base_url.rstrip("/")

    def guardar(self, contenido: bytes, mime_type: str, purpose: str) -> str:
        subcarpeta = CARPETAS[purpose]
        nombre = f"{nuevo_id()}.{TIPOS[mime_type][0]}"        # nombre propio: nunca se usa el que manda el cliente
        destino = self.carpeta / subcarpeta
        destino.mkdir(parents=True, exist_ok=True)
        (destino / nombre).write_bytes(contenido)
        return f"{self.base_url}/{subcarpeta}/{nombre}"


def get_almacen() -> Almacen:
    """Dependencia de FastAPI; las pruebas la reemplazan por un almacén en memoria."""
    return AlmacenLocal(config.FILES_DIR, config.FILES_PUBLIC_URL)
