"""Identificadores UUIDv7 (se pueden ordenar por fecha de creación).

Python 3.14 ya incluye uuid.uuid7(); como no todos tienen esa versión, aquí va una
implementación mínima según el RFC 9562: 48 bits de milisegundos Unix, 4 bits de
versión (7), 12 bits aleatorios, 2 bits de variante y 62 bits aleatorios.
"""
import os
import time
import uuid


def uuid7() -> uuid.UUID:
    milisegundos = time.time_ns() // 1_000_000
    azar = int.from_bytes(os.urandom(10), "big")   # 80 bits aleatorios
    rand_a = (azar >> 68) & 0xFFF                   # 12 bits
    rand_b = azar & ((1 << 62) - 1)                 # 62 bits
    valor = (milisegundos & ((1 << 48) - 1)) << 80
    valor |= 0x7 << 76
    valor |= rand_a << 64
    valor |= 0b10 << 62
    valor |= rand_b
    return uuid.UUID(int=valor)


def nuevo_id() -> str:
    """UUIDv7 como texto de 36 caracteres (así se guarda y se expone en la API)."""
    return str(uuid7())
