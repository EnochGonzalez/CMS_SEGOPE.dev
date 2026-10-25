"""Carga de archivos (requiere token Bearer).

Endpoint de la especificación v2 que implementa este archivo:
  21. POST /api/v1/files     Carga de archivo (multipart/form-data)

Primero se sube el archivo aquí; la respuesta trae la `url` que luego se usa en un certificado, un logo o la foto del perfil.
"""
import hashlib

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app import config
from app import idempotency as idem
from app.database import get_db
from app.dependencies import exigir_admin
from app.errors import ApiError
from app.routers.comunes import CLAVE_IDEMPOTENCIA, ERROR_401, ERROR_422
from app.schemas import Envelope, ErrorEnvelope, FilePurpose, FileUploadedOut
from app.storage import TIPOS, Almacen, detectar_tipo, get_almacen

router = APIRouter(
    prefix="/api/v1/files",
    tags=["Archivos"],
    dependencies=[Depends(exigir_admin)],
    responses=ERROR_401,
)


@router.post(
    "", status_code=201, response_model=Envelope[FileUploadedOut],
    summary="21. Carga de archivo",
    responses={
        **ERROR_422,
        413: {"model": ErrorEnvelope, "description": "El archivo excede el límite (PDF 5 MB, imágenes 2 MB)"},
        415: {"model": ErrorEnvelope, "description": "Solo se aceptan PDF, JPEG, PNG y WebP"},
    },
)
def cargar_archivo(
    purpose: FilePurpose = Form(description="CERTIFICATE_PDF, CERTIFICATE_IMAGE, STACK_LOGO o PROFILE_PHOTO"),
    file: UploadFile = File(description="El archivo (PDF de hasta 5 MB o imagen JPEG/PNG/WebP de hasta 2 MB)"),
    idempotency_key: str = CLAVE_IDEMPOTENCIA,
    db: Session = Depends(get_db), almacen: Almacen = Depends(get_almacen),
):
    """El tipo se decide por el **contenido** del archivo, no por su nombre.

    - 415: no es PDF, JPEG, PNG ni WebP.
    - 413: PDF de más de 5 MB o imagen de más de 2 MB.
    - 422: el `purpose` no coincide con el tipo (`CERTIFICATE_PDF` exige un PDF; los demás exigen una imagen)."""
    contenido = file.file.read(config.MAX_PDF_BYTES + 1)           # nunca se lee más del límite mayor
    h = idem.huella("POST", "/api/v1/files", {"purpose": purpose.value, "sha256": hashlib.sha256(contenido).hexdigest()})
    repetida = idem.buscar_repetida(db, idempotency_key, h)
    if repetida:
        return repetida

    tipo = detectar_tipo(contenido)
    if tipo is None:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Solo se aceptan archivos PDF, JPEG, PNG o WebP")
    limite = config.MAX_PDF_BYTES if tipo == "application/pdf" else config.MAX_IMAGEN_BYTES
    if len(contenido) > limite:
        raise ApiError(413, "FILE_TOO_LARGE", f"El archivo excede el límite de {limite // (1024 * 1024)} MB para este tipo")
    es_imagen = TIPOS[tipo][1]
    if (purpose == FilePurpose.CERTIFICATE_PDF) == es_imagen:      # PDF para un propósito de imagen, o al revés
        esperado = "un PDF" if purpose == FilePurpose.CERTIFICATE_PDF else "una imagen (JPEG, PNG o WebP)"
        raise ApiError(422, "FILE_PURPOSE_MISMATCH", f"El propósito {purpose.value} exige {esperado}",
                       [{"field": "purpose", "issue": f"El archivo enviado es {tipo}"}])

    url = almacen.guardar(contenido, tipo, purpose.value)
    envelope = Envelope[FileUploadedOut](message="Archivo cargado exitosamente",
                                         data=FileUploadedOut(url=url, mime_type=tipo, size_bytes=len(contenido)))
    idem.guardar_y_confirmar(db, idempotency_key, h, 201, envelope)
    return envelope
