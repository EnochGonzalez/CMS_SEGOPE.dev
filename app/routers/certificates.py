"""Administración de certificados (requiere token Bearer).

Endpoints de la especificación v2 que implementa este archivo:
  11. POST   /api/v1/certificates                     Creación de certificado
  13. PUT    /api/v1/certificates/{certificate_id}    Actualización (reemplazo completo)
  14. DELETE /api/v1/certificates/{certificate_id}    Eliminación
(El 12, el listado público, está en public.py.) Los certificados no tienen borrador: al existir son públicos,
por eso cada cambio avisa al pipeline.
"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app import idempotency as idem
from app.database import get_db
from app.dependencies import exigir_admin
from app.models import Certificate, ahora_utc
from app.pipeline import Notificador, codigo_http, fue_aceptada, get_notificador
from app.routers.comunes import CLAVE_IDEMPOTENCIA, ERROR_401, ERROR_404, ERROR_409, ERROR_422, RESPUESTA_202
from app.schemas import (
    CertificateCreatedOut, CertificateDeletedOut, CertificateIn, CertificateUpdatedOut, Envelope,
)
from app.services import catalogo as reglas
from app.storage import Almacen, get_almacen

router = APIRouter(
    prefix="/api/v1/certificates",
    tags=["Certificados (administración)"],
    dependencies=[Depends(exigir_admin)],
    responses=ERROR_401,
)
CONFLICTO = ("CERTIFICATE_ALREADY_EXISTS", "Ya existe un certificado con el mismo título, institución y fecha", "title")


# ------------------------------------------------------------------ 11. crear
@router.post(
    "", status_code=201, response_model=Envelope[CertificateCreatedOut],
    summary="11. Creación de certificado",
    responses={**ERROR_409, **ERROR_422},
)
def crear_certificado(
    datos: CertificateIn, idempotency_key: str = CLAVE_IDEMPOTENCIA, db: Session = Depends(get_db),
    notificador: Notificador = Depends(get_notificador), almacen: Almacen = Depends(get_almacen),
):
    """Sube antes el PDF y la imagen con `POST /api/v1/files` y usa aquí las URLs que devuelve.

    409 si ya existe un certificado con el mismo `title`, `issuer` e `issued_at`.
    Siempre responde 201: el aviso al pipeline no retrasa la creación."""
    h = idem.huella("POST", "/api/v1/certificates", datos.model_dump(mode="json"))
    repetida = idem.buscar_repetida(db, idempotency_key, h)
    if repetida:
        return repetida

    reglas.exigir_urls_de_archivo(almacen, pdf_url=datos.pdf_url, image_url=datos.image_url)
    reglas.exigir_certificado_unico(db, datos)
    certificado = Certificate(title=datos.title, issuer=datos.issuer, issued_at=datos.issued_at,
                              pdf_url=datos.pdf_url, image_url=datos.image_url)
    with reglas.conflicto_unico(db, *CONFLICTO):
        db.add(certificado)
        db.commit()

    resultado = notificador.notificar("CERTIFICATE_CREATED", certificado.certificate_id)
    envelope = Envelope[CertificateCreatedOut](
        message="Certificado creado exitosamente",
        data=CertificateCreatedOut(certificate_id=certificado.certificate_id, title=certificado.title, issuer=certificado.issuer,
                                   issued_at=certificado.issued_at, created_at=certificado.created_at,
                                   recompilation_triggered=fue_aceptada(resultado)),
    )
    idem.guardar_y_confirmar(db, idempotency_key, h, 201, envelope)
    return envelope


# ------------------------------------------------------------------ 13. actualizar
@router.put(
    "/{certificate_id}", response_model=Envelope[CertificateUpdatedOut],
    summary="13. Actualización de certificado",
    responses={**ERROR_404, **ERROR_409, **ERROR_422, **RESPUESTA_202},
)
def actualizar_certificado(
    certificate_id: str, datos: CertificateIn, response: Response, db: Session = Depends(get_db),
    notificador: Notificador = Depends(get_notificador), almacen: Almacen = Depends(get_almacen),
):
    """PUT reemplaza el certificado completo. 409 si el nuevo título + institución + fecha ya los tiene otro certificado."""
    certificado = reglas.buscar_certificado(db, certificate_id)
    reglas.exigir_urls_de_archivo(almacen, pdf_url=datos.pdf_url, image_url=datos.image_url)
    reglas.exigir_certificado_unico(db, datos, excepto_id=certificado.certificate_id)

    with reglas.conflicto_unico(db, *CONFLICTO):
        certificado.title = datos.title
        certificado.issuer = datos.issuer
        certificado.issued_at = datos.issued_at
        certificado.pdf_url = datos.pdf_url
        certificado.image_url = datos.image_url
        certificado.updated_at = ahora_utc()
        db.commit()

    resultado = notificador.notificar("CERTIFICATE_UPDATED", certificado.certificate_id)
    response.status_code = codigo_http(resultado)
    return Envelope[CertificateUpdatedOut](
        message="Certificado actualizado exitosamente",
        data=CertificateUpdatedOut(certificate_id=certificado.certificate_id, updated_at=certificado.updated_at,
                                   recompilation_triggered=fue_aceptada(resultado)),
    )


# ------------------------------------------------------------------ 14. eliminar
@router.delete(
    "/{certificate_id}", response_model=Envelope[CertificateDeletedOut],
    summary="14. Eliminación de certificado",
    responses={**ERROR_404, **RESPUESTA_202},
)
def eliminar_certificado(
    certificate_id: str, response: Response, db: Session = Depends(get_db),
    notificador: Notificador = Depends(get_notificador),
):
    """Eliminación física y definitiva. Los archivos (PDF e imagen) NO se borran del almacenamiento."""
    certificado = reglas.buscar_certificado(db, certificate_id)
    db.delete(certificado)
    db.commit()

    resultado = notificador.notificar("CERTIFICATE_DELETED", certificate_id)
    response.status_code = codigo_http(resultado)
    return Envelope[CertificateDeletedOut](
        message="Certificado eliminado exitosamente",
        data=CertificateDeletedOut(certificate_id=certificate_id, recompilation_triggered=fue_aceptada(resultado)),
    )
