"""Seguridad del administrador: contraseña (scrypt), token JWT (HS256) y límite de intentos de login."""
import base64
import hashlib
import hmac
import os
import time

import jwt

from app import config
from app.errors import ApiError

_N, _R, _P = 2**14, 8, 1                      # costo de scrypt (memoria ≈ 16 MiB)
_MEMORIA_MAX = 64 * 1024 * 1024
_BEARER = {"WWW-Authenticate": "Bearer"}


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def _desb64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


# ------------------------------------------------------------------ contraseña
def hash_password(password: str) -> str:
    """scrypt$N$r$p$sal$hash. La contraseña nunca se guarda, solo este resumen."""
    sal = os.urandom(16)
    derivada = hashlib.scrypt(password.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32, maxmem=_MEMORIA_MAX)
    return f"scrypt${_N}${_R}${_P}${_b64(sal)}${_b64(derivada)}"


def verify_password(password: str, almacenado: str) -> bool:
    try:
        esquema, n, r, p, sal, esperado = almacenado.split("$")
        if esquema != "scrypt":
            return False
        esperado_bytes = _desb64(esperado)
        derivada = hashlib.scrypt(password.encode(), salt=_desb64(sal), n=int(n), r=int(r), p=int(p),
                                  dklen=len(esperado_bytes), maxmem=_MEMORIA_MAX)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derivada, esperado_bytes)


def mismo_texto(a: str, b: str) -> bool:
    """Comparación en tiempo constante (compare_digest exige bytes si hay acentos)."""
    return hmac.compare_digest(a.encode(), b.encode())


# ------------------------------------------------------------------ configuración
def administrador_configurado() -> bool:
    return bool(config.ADMIN_EMAIL and config.ADMIN_PASSWORD_HASH and config.JWT_SECRET)


def exigir_configuracion() -> None:
    if not administrador_configurado():
        raise ApiError(503, "ADMIN_NOT_CONFIGURED",
                       "El administrador aún no está configurado; ejecuta python -m app.configurar_admin")


# ------------------------------------------------------------------ token
def crear_token(email: str) -> tuple[str, int]:
    ahora = int(time.time())
    vigencia = config.TOKEN_EXPIRA_SEGUNDOS
    carga = {"sub": email, "iat": ahora, "exp": ahora + vigencia}
    return jwt.encode(carga, config.JWT_SECRET, algorithm="HS256"), vigencia


def leer_token(token: str) -> str:
    """Devuelve el correo del administrador o responde 401."""
    exigir_configuracion()
    try:
        datos = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "TOKEN_EXPIRED", "El token expiró; inicia sesión de nuevo", headers=_BEARER)
    except jwt.InvalidTokenError:
        raise ApiError(401, "INVALID_TOKEN", "El token no es válido", headers=_BEARER)
    if not mismo_texto(str(datos["sub"]).lower(), config.ADMIN_EMAIL.lower()):
        raise ApiError(401, "INVALID_TOKEN", "El token no es válido", headers=_BEARER)
    return datos["sub"]


# ------------------------------------------------------------------ límite de intentos
_reloj = time.monotonic


class LimitadorDeIntentos:
    """Cuenta intentos fallidos por clave (IP + correo) dentro de una ventana de tiempo.

    Vive en memoria: sirve para una sola instancia de la API (como en capa gratuita)."""

    def __init__(self) -> None:
        self._fallos: dict[str, list[float]] = {}

    def _recientes(self, clave: str) -> tuple[list[float], float]:
        ahora = _reloj()
        lista = [t for t in self._fallos.get(clave, []) if ahora - t < config.LOGIN_VENTANA_SEGUNDOS]
        if lista:
            self._fallos[clave] = lista
        else:
            self._fallos.pop(clave, None)
        return lista, ahora

    def segundos_de_espera(self, clave: str) -> int:
        """0 si puede intentar; si no, cuántos segundos faltan para que expire el bloqueo."""
        lista, ahora = self._recientes(clave)
        if len(lista) < config.LOGIN_MAX_FALLOS:
            return 0
        return max(1, int(config.LOGIN_VENTANA_SEGUNDOS - (ahora - lista[0])) + 1)

    def registrar_fallo(self, clave: str) -> None:
        self._fallos.setdefault(clave, []).append(_reloj())

    def limpiar(self, clave: str) -> None:
        self._fallos.pop(clave, None)

    def reiniciar(self) -> None:
        self._fallos.clear()


limitador_login = LimitadorDeIntentos()
