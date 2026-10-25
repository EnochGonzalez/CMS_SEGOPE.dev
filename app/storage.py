"""Almacenamiento de los archivos que se suben (PDF e imágenes).

`Almacen` es una interfaz: hoy se usa `AlmacenLocal` (guarda en la carpeta uploads/ y la API la sirve en /media).
Al publicar la API se reemplaza por un servicio externo (Cloudinary, S3, Supabase Storage...) sin tocar los
endpoints, porque en servidores gratuitos el disco se borra con cada despliegue.

El tipo de un archivo se decide por su CONTENIDO (los primeros bytes), no por su nombre ni por lo que diga el cliente.
"""
from functools import lru_cache
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


class AlmacenS3:
    """Guarda los archivos en un bucket compatible con S3 (Supabase Storage, R2, B2, AWS...). El bucket debe ser público
    para lectura: así el blog y los visitantes abren los PDF e imágenes directamente, sin pasar por la API."""

    def __init__(self, cliente, bucket: str, base_url: str):
        self.cliente = cliente
        self.bucket = bucket
        self.base_url = base_url.rstrip("/")

    def guardar(self, contenido: bytes, mime_type: str, purpose: str) -> str:
        clave = f"{CARPETAS[purpose]}/{nuevo_id()}.{TIPOS[mime_type][0]}"
        self.cliente.put_object(
            Bucket=self.bucket, Key=clave, Body=contenido, ContentType=mime_type,
            CacheControl="public, max-age=31536000, immutable",        # el nombre nunca se reutiliza: se puede guardar para siempre
        )
        return f"{self.base_url}/{clave}"


@lru_cache(maxsize=4)
def _cliente_s3(endpoint: str, clave_id: str, clave_secreta: str, region: str):
    import boto3                                      # solo se necesita en el servidor; en tu computadora no hace falta
    from botocore.config import Config

    return boto3.client(
        "s3", endpoint_url=endpoint, aws_access_key_id=clave_id, aws_secret_access_key=clave_secreta, region_name=region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 3}, connect_timeout=5, read_timeout=20),
    )


def get_almacen() -> Almacen:
    """Dependencia de FastAPI. Con las variables S3_* completas usa el almacén externo; si no, la carpeta uploads/.
    Las pruebas la reemplazan por un almacén en memoria."""
    if config.s3_configurado():
        cliente = _cliente_s3(config.S3_ENDPOINT_URL, config.S3_ACCESS_KEY_ID, config.S3_SECRET_ACCESS_KEY, config.S3_REGION)
        return AlmacenS3(cliente, config.S3_BUCKET, config.FILES_PUBLIC_URL)
    return AlmacenLocal(config.FILES_DIR, config.FILES_PUBLIC_URL)
