"""Idempotency-Key: repetir una petición con la misma clave devuelve la respuesta ORIGINAL
(en vez de un 409 o de hacer la operación dos veces). Se conserva 24 horas.

Reglas:
  - Solo se guardan las respuestas exitosas (2xx).
  - Misma clave + petición distinta (otra ruta u otro cuerpo)  ->  422 IDEMPOTENCY_KEY_REUSED.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app import config
from app.errors import ApiError
from app.models import IdempotencyKey, ahora_utc


def huella(metodo: str, ruta: str, cuerpo: dict | None = None) -> str:
    """Resumen de 'qué se pidió': dos peticiones iguales dan la misma huella."""
    crudo = json.dumps({"m": metodo, "r": ruta, "c": cuerpo}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def _como_utc(fecha: datetime) -> datetime:
    return fecha.replace(tzinfo=timezone.utc) if fecha.tzinfo is None else fecha


def buscar_repetida(db: Session, clave: str, huella_actual: str) -> JSONResponse | None:
    """Si la clave ya se usó con esta misma petición, devuelve la respuesta guardada."""
    fila = db.get(IdempotencyKey, clave)
    if fila is None:
        return None
    if ahora_utc() - _como_utc(fila.created_at) > timedelta(hours=config.IDEMPOTENCIA_HORAS):
        db.delete(fila)                       # venció: se trata como clave nueva
        db.flush()
        return None
    if fila.fingerprint != huella_actual:
        raise ApiError(422, "IDEMPOTENCY_KEY_REUSED",
                       "Esa Idempotency-Key ya se usó con una petición distinta; genera una clave nueva",
                       [{"field": "idempotency-key", "issue": "Clave reutilizada con otra petición"}])
    return JSONResponse(status_code=fila.status_code, content=json.loads(fila.body),
                        headers={"Idempotent-Replayed": "true"})


def guardar_y_confirmar(db: Session, clave: str, huella_actual: str, status_code: int, envelope) -> None:
    """Guarda la respuesta que se va a entregar y confirma la transacción."""
    limite = ahora_utc() - timedelta(hours=config.IDEMPOTENCIA_HORAS)
    db.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < limite))     # limpieza de vencidas
    db.add(IdempotencyKey(key=clave, fingerprint=huella_actual, status_code=status_code,
                          body=json.dumps(jsonable_encoder(envelope), ensure_ascii=False)))
    db.commit()
