"""Dependencia que protege los endpoints de administración (Authorization: Bearer <token>)."""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import security
from app.errors import ApiError

# auto_error=False para responder con NUESTRO formato de error. Además hace que /docs muestre el botón "Authorize".
esquema_bearer = HTTPBearer(auto_error=False, description="Pega el access_token que devuelve POST /api/v1/auth/login")


def exigir_admin(credenciales: HTTPAuthorizationCredentials | None = Depends(esquema_bearer)) -> str:
    if credenciales is None:
        raise ApiError(401, "UNAUTHORIZED", "Falta el encabezado Authorization: Bearer <access_token>",
                       headers={"WWW-Authenticate": "Bearer"})
    return security.leer_token(credenciales.credentials)
