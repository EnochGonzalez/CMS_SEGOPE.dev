"""Paginación por cursor (keyset): estable aunque se creen o borren filas entre página y página.

El cursor es un texto opaco (base64url de un JSON) con los valores de la última fila entregada;
la siguiente página pide "todo lo que viene después de esos valores" según el orden elegido.
"""
import base64
import json
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import and_, or_
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.errors import ApiError


@dataclass(frozen=True)
class Clave:
    """Una columna del orden. `tipo` indica cómo guardarla dentro del cursor."""
    columna: InstrumentedAttribute
    atributo: str
    tipo: str                    # "date" | "datetime" | "str" | "int"
    descendente: bool = False


def _a_json(valor, tipo: str):
    return valor.isoformat() if tipo in ("date", "datetime") else valor


def _de_json(valor, tipo: str):
    if tipo == "date":
        return date.fromisoformat(valor)
    if tipo == "datetime":
        return datetime.fromisoformat(valor)
    if tipo == "int":
        return int(valor)
    return str(valor)


def codificar_cursor(fila, claves: list[Clave]) -> str:
    valores = [_a_json(getattr(fila, c.atributo), c.tipo) for c in claves]
    crudo = json.dumps(valores, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(crudo).decode().rstrip("=")


def decodificar_cursor(cursor: str, claves: list[Clave]) -> list:
    try:
        relleno = "=" * (-len(cursor) % 4)
        valores = json.loads(base64.urlsafe_b64decode(cursor + relleno))
        if not isinstance(valores, list) or len(valores) != len(claves):
            raise ValueError("forma incorrecta")
        return [_de_json(v, c.tipo) for v, c in zip(valores, claves)]
    except Exception:
        raise ApiError(422, "INVALID_CURSOR", "El cursor no es válido; usa el next_cursor de la respuesta anterior")


def _despues_de(claves: list[Clave], valores: list):
    """(a, b, c) > (x, y, z) escrito con OR/AND para que funcione con cualquier orden mixto."""
    condiciones = []
    for i, clave in enumerate(claves):
        iguales = [claves[j].columna == valores[j] for j in range(i)]
        mayor_o_menor = clave.columna < valores[i] if clave.descendente else clave.columna > valores[i]
        condiciones.append(and_(*iguales, mayor_o_menor))
    return or_(*condiciones)


def paginar(db: Session, consulta, claves: list[Clave], cursor: str | None, limit: int):
    """Devuelve (filas, next_cursor). Pide limit+1 filas para saber si hay otra página."""
    if cursor:
        consulta = consulta.where(_despues_de(claves, decodificar_cursor(cursor, claves)))
    orden = [c.columna.desc() if c.descendente else c.columna.asc() for c in claves]
    filas = list(db.scalars(consulta.order_by(*orden).limit(limit + 1)).all())
    siguiente = None
    if len(filas) > limit:
        filas = filas[:limit]
        siguiente = codificar_cursor(filas[-1], claves)
    return filas, siguiente
