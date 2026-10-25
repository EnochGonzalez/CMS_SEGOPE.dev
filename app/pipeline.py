"""Aviso al Pipeline de Compilación Estática: el que regenera el blog cuando cambia el contenido.

Con DEPLOY_HOOK_URL configurada (el "deploy hook" de Vercel) la API le pide a Vercel que reconstruya el blog en cuanto se
confirma un cambio. Sin ella, `NotificadorNulo` no avisa a nadie y la consola te recuerda que genere el blog a mano.

Reglas (Paso 5 de la especificación):
  - El aviso espera como máximo 10 s la respuesta. Si el pipeline tarda, la operación igual se aplica (HTTP 202,
    recompilation_triggered = false) y el aviso se reintenta en segundo plano hasta 3 veces, con esperas crecientes.
  - Los avisos se agrupan en ventanas de 60 s: el primero sale de inmediato y los que llegan después se juntan en UN
    solo aviso al cerrar la ventana, que ya incluye todos esos cambios. Así 10 ediciones seguidas no lanzan 10 compilaciones.
"""
import logging
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app import config

log = logging.getLogger("cms.pipeline")
# La dirección del deploy hook es un secreto (quien la tenga puede lanzar compilaciones). httpx escribe cada petición con
# su dirección completa en el registro si se le deja, así que se silencia aquí aunque alguien suba el nivel general.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@dataclass(frozen=True)
class ResultadoNotificacion:
    aceptada: bool          # el pipeline aceptó el aviso (o lo hará al cerrar la ventana)  ->  recompilation_triggered
    lenta: bool = False     # no respondió a tiempo: la API responde 202 y reintenta en segundo plano


class Notificador(Protocol):
    def notificar(self, motivo: str, recurso_id: str) -> ResultadoNotificacion: ...


class NotificadorNulo:
    """No hay pipeline conectado: no avisa a nadie (recompilation_triggered = false)."""

    def notificar(self, motivo: str, recurso_id: str) -> ResultadoNotificacion:
        return ResultadoNotificacion(aceptada=False)


def _programar_en_hilo(segundos: float, funcion) -> None:
    temporizador = threading.Timer(segundos, funcion)
    temporizador.daemon = True              # si el servidor se apaga, no espera a los avisos pendientes
    temporizador.start()


class NotificadorDeploy:
    """Avisa a un deploy hook (HTTP POST). Se crea una sola vez y se comparte: recuerda la ventana de 60 s."""

    def __init__(self, url: str, *, cliente: httpx.Client | None = None, timeout: float = 10.0, ventana: float = 60.0,
                 esperas: tuple = (5.0, 15.0, 45.0), reloj=time.monotonic, programar=_programar_en_hilo):
        self._url = url
        self._cliente = cliente or httpx.Client(timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)))
        self._ventana = ventana
        self._esperas = esperas
        self._reloj = reloj
        self._programar = programar
        self._cerrojo = threading.Lock()
        self._ultimo_aviso: float | None = None          # cuándo se aceptó (o se reservó) el último aviso
        self._seguimiento_programado = False             # ya hay un aviso listo para cuando cierre la ventana

    # ------------------------------------------------------------ lo que usan los endpoints
    def notificar(self, motivo: str, recurso_id: str) -> ResultadoNotificacion:
        with self._cerrojo:
            ahora = self._reloj()
            if self._ultimo_aviso is not None and ahora - self._ultimo_aviso < self._ventana:
                if not self._seguimiento_programado:
                    self._seguimiento_programado = True
                    self._programar(self._ventana - (ahora - self._ultimo_aviso) + 1, self._avisar_al_cerrar_ventana)
                log.info("Aviso agrupado en la ventana actual (%s)", motivo)
                return ResultadoNotificacion(aceptada=True)
            self._ultimo_aviso = ahora                   # se reserva: los avisos simultáneos se agrupan con este

        estado = self._enviar()
        if estado == "ok":
            return ResultadoNotificacion(aceptada=True)
        with self._cerrojo:
            self._ultimo_aviso = None                    # no se aceptó: el siguiente aviso lo vuelve a intentar
        if estado == "rechazado":
            return ResultadoNotificacion(aceptada=False)
        self._programar_reintento(0)
        return ResultadoNotificacion(aceptada=False, lenta=True)

    # ------------------------------------------------------------ en segundo plano
    def _avisar_al_cerrar_ventana(self) -> None:
        """Se ejecuta al terminar la ventana: un solo aviso que incluye todos los cambios que llegaron durante ella."""
        with self._cerrojo:
            self._seguimiento_programado = False
            self._ultimo_aviso = None
        if self._enviar() == "lento":
            self._programar_reintento(0)

    def _programar_reintento(self, numero: int) -> None:
        """numero = 0, 1, 2: cuál de los 3 reintentos se programa, con esperas crecientes (5 s, 15 s, 45 s)."""
        if numero >= len(self._esperas):
            log.error("Se agotaron los reintentos del aviso al deploy hook: el blog no se reconstruyó solo")
            return
        self._programar(self._esperas[numero], lambda: self._reintentar(numero))

    def _reintentar(self, numero: int) -> None:
        if self._enviar() == "lento":                    # 'ok' ya anotó la hora; 'rechazado' no se arregla reintentando
            self._programar_reintento(numero + 1)

    # ------------------------------------------------------------ la petición
    def _enviar(self) -> str:
        """'ok', 'lento' (se puede reintentar) o 'rechazado' (error de configuración: reintentar no sirve)."""
        try:
            respuesta = self._cliente.post(self._url)
        except httpx.TimeoutException:
            log.warning("El deploy hook no respondió a tiempo")
            return "lento"
        except httpx.HTTPError as error:
            log.warning("No se pudo contactar el deploy hook (%s)", type(error).__name__)
            return "lento"
        if respuesta.is_success:
            log.info("El deploy hook aceptó el aviso (HTTP %s)", respuesta.status_code)
            with self._cerrojo:
                self._ultimo_aviso = self._reloj()
            return "ok"
        if 400 <= respuesta.status_code < 500 and respuesta.status_code != 429:
            log.error("El deploy hook rechazó el aviso (HTTP %s). Revisa DEPLOY_HOOK_URL", respuesta.status_code)
            return "rechazado"
        log.warning("El deploy hook respondió HTTP %s", respuesta.status_code)
        return "lento"


_notificadores: dict[tuple, NotificadorDeploy] = {}


def codigo_http(resultado: ResultadoNotificacion | None) -> int:
    """200 normalmente; 202 si el pipeline tardó en responder."""
    return 202 if resultado is not None and resultado.lenta else 200


def fue_aceptada(resultado: ResultadoNotificacion | None) -> bool:
    """Valor de recompilation_triggered: ¿el pipeline aceptó el aviso?"""
    return resultado is not None and resultado.aceptada


def get_notificador() -> Notificador:
    """Dependencia de FastAPI. Con DEPLOY_HOOK_URL devuelve SIEMPRE el mismo notificador (así recuerda la ventana de 60 s);
    sin ella, uno nulo. Las pruebas la reemplazan."""
    if not config.DEPLOY_HOOK_URL:
        return NotificadorNulo()
    clave = (config.DEPLOY_HOOK_URL, config.PIPELINE_TIMEOUT_SEGUNDOS, config.PIPELINE_VENTANA_SEGUNDOS)
    if clave not in _notificadores:
        _notificadores[clave] = NotificadorDeploy(config.DEPLOY_HOOK_URL, timeout=config.PIPELINE_TIMEOUT_SEGUNDOS, ventana=config.PIPELINE_VENTANA_SEGUNDOS)
    return _notificadores[clave]
