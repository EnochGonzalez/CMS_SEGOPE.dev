"""Aviso al Pipeline de Compilación Estática (el que regenera el blog cuando cambia el contenido).

Aquí solo está la INTERFAZ y un notificador nulo. La conexión real con el despliegue (deploy hook),
la agrupación en ventanas de 60 s y los reintentos en segundo plano llegan en el Bloque 4.
Mientras tanto, recompilation_triggered será siempre false y el código HTTP será 200.
"""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ResultadoNotificacion:
    aceptada: bool          # el pipeline aceptó el aviso a tiempo  ->  recompilation_triggered
    lenta: bool = False     # no respondió dentro de 10 s: la API responde 202 y reintenta después


class Notificador(Protocol):
    def notificar(self, motivo: str, recurso_id: str) -> ResultadoNotificacion: ...


class NotificadorNulo:
    """Todavía no hay pipeline conectado: no avisa a nadie."""

    def notificar(self, motivo: str, recurso_id: str) -> ResultadoNotificacion:
        return ResultadoNotificacion(aceptada=False)


def codigo_http(resultado: ResultadoNotificacion | None) -> int:
    """200 normalmente; 202 si el pipeline tardó en responder."""
    return 202 if resultado is not None and resultado.lenta else 200


def fue_aceptada(resultado: ResultadoNotificacion | None) -> bool:
    """Valor de recompilation_triggered: ¿el pipeline aceptó el aviso?"""
    return resultado is not None and resultado.aceptada


def get_notificador() -> Notificador:
    """Dependencia de FastAPI. En el Bloque 4 devolverá el notificador real; las pruebas lo reemplazan."""
    return NotificadorNulo()
