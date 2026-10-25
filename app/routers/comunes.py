"""Parámetros y descripciones de error que comparten varios routers."""
from fastapi import Header, Query

from app.schemas import ErrorEnvelope

LIMITE = Query(20, ge=1, le=50, description="Elementos por página (1 a 50)")
CURSOR = Query(None, description="Usa el next_cursor de la respuesta anterior")

ERROR_401 = {401: {"model": ErrorEnvelope, "description": "Falta el token Bearer, es inválido o expiró"}}
ERROR_404 = {404: {"model": ErrorEnvelope, "description": "No encontrado"}}
ERROR_409 = {409: {"model": ErrorEnvelope, "description": "Conflicto con el estado actual o con otro registro"}}
ERROR_422 = {422: {"model": ErrorEnvelope, "description": "Datos inválidos (Diccionario de Tipos o contrato de publicación)"}}

# Como en la sección 5 de la práctica guiada: FastAPI convierte idempotency_key en la cabecera Idempotency-Key.
CLAVE_IDEMPOTENCIA = Header(min_length=8, max_length=128, description="Clave única por operación (por ejemplo un UUID). Se recuerda 24 h.")
RESPUESTA_202 = {202: {"description": "La operación se aplicó, pero el pipeline tardó en responder: el aviso se reintenta en segundo plano"}}
