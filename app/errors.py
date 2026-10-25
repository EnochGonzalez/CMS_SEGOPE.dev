"""Formato único de errores: { status: "error", code, message, details[] } (Paso 6, contrato)."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Error de negocio con código HTTP propio (404, 409, 422...)."""

    def __init__(self, status_code: int, code: str, message: str,
                 details: list[dict] | None = None, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []
        self.headers = headers


def _respuesta(status_code: int, code: str, message: str, details: list[dict] | None = None,
               headers: dict[str, str] | None = None) -> JSONResponse:
    cuerpo = {"status": "error", "code": code, "message": message, "details": details or []}
    return JSONResponse(status_code=status_code, content=cuerpo, headers=headers)


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _error_de_negocio(request: Request, exc: ApiError):
        return _respuesta(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _error_de_validacion(request: Request, exc: RequestValidationError):
        detalles = []
        for error in exc.errors():
            ruta = [str(parte) for parte in error["loc"]]
            if ruta and ruta[0] in ("query", "path", "header", "cookie", "body"):
                ruta = ruta[1:]
            detalles.append({"field": ".".join(ruta) or "(cuerpo)", "issue": error["msg"]})
        return _respuesta(422, "VALIDATION_ERROR", "Los datos enviados no cumplen el Diccionario de Tipos", detalles)

    @app.exception_handler(StarletteHTTPException)
    async def _error_http(request: Request, exc: StarletteHTTPException):
        codigos = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        return _respuesta(exc.status_code, codigos.get(exc.status_code, "HTTP_ERROR"), str(exc.detail))
