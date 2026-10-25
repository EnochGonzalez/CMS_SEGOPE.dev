"""Autenticación del administrador.

Endpoint de la especificación v2 que implementa este archivo:
   1. POST /api/v1/auth/login     Inicio de sesión del administrador
"""
from fastapi import APIRouter, Request

from app import config, security
from app.errors import ApiError
from app.routers.comunes import ERROR_401, ERROR_422
from app.schemas import Envelope, ErrorEnvelope, LoginIn, TokenOut

router = APIRouter(prefix="/api/v1/auth", tags=["Autenticación"])


@router.post(
    "/login",
    response_model=Envelope[TokenOut],
    summary="1. Inicio de sesión del administrador",
    responses={
        **ERROR_401, **ERROR_422,
        429: {"model": ErrorEnvelope, "description": "Demasiados intentos fallidos (ver cabecera Retry-After)"},
        503: {"model": ErrorEnvelope, "description": "El administrador aún no está configurado"},
    },
)
def iniciar_sesion(datos: LoginIn, request: Request):
    """Devuelve un `access_token` (JWT) para usar como `Authorization: Bearer <access_token>`.

    Tras 5 intentos fallidos con el mismo correo desde la misma IP, se bloquea por 15 minutos (429)."""
    security.exigir_configuracion()

    ip = request.client.host if request.client else "desconocida"
    clave = f"{ip}|{datos.email.lower()}"
    espera = security.limitador_login.segundos_de_espera(clave)
    if espera > 0:
        raise ApiError(429, "TOO_MANY_ATTEMPTS", f"Demasiados intentos fallidos; intenta de nuevo en {espera} segundos",
                       headers={"Retry-After": str(espera)})

    # Siempre se revisan las dos cosas: así no se revela si fue el correo o la contraseña.
    correo_ok = security.mismo_texto(datos.email.lower(), config.ADMIN_EMAIL.lower())
    clave_ok = security.verify_password(datos.password, config.ADMIN_PASSWORD_HASH)
    if not (correo_ok and clave_ok):
        security.limitador_login.registrar_fallo(clave)
        raise ApiError(401, "INVALID_CREDENTIALS", "Correo o contraseña incorrectos")

    security.limitador_login.limpiar(clave)
    token, vigencia = security.crear_token(config.ADMIN_EMAIL)
    return Envelope[TokenOut](message="Inicio de sesión exitoso", data=TokenOut(access_token=token, expires_in=vigencia))
