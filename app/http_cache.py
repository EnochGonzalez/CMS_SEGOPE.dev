"""Caché HTTP de las lecturas públicas: ETag + Cache-Control (max-age 60 s).

Si el cliente repite la petición con If-None-Match y nada cambió, se responde 304 sin cuerpo.
Igual que en la sección 7 de la práctica guiada, las cabeceras se inyectan con la clase Response.
"""
import hashlib
import json

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder

CACHE_CONTROL = "public, max-age=60"


def con_cache(request: Request, response: Response, envelope):
    cuerpo = json.dumps(jsonable_encoder(envelope), sort_keys=True, ensure_ascii=False).encode("utf-8")
    etag = '"' + hashlib.sha1(cuerpo).hexdigest() + '"'
    cabeceras = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=cabeceras)
    response.headers.update(cabeceras)
    return envelope
