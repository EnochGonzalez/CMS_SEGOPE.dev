"""Configura el administrador del CMS: escribe el archivo .env con el correo, el resumen (hash)
de la contraseña y una clave secreta para firmar los tokens.

Uso:  python -m app.configurar_admin

La contraseña NO se guarda: solo su hash. El archivo .env está en .gitignore; no lo subas a Git.
"""
import getpass
import re
import secrets
from pathlib import Path

from app import config
from app.security import hash_password

CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def construir_valores(email: str, password: str) -> dict[str, str]:
    return {
        "ADMIN_EMAIL": email,
        "ADMIN_PASSWORD_HASH": hash_password(password),
        "JWT_SECRET": secrets.token_urlsafe(48),
    }


def escribir_env(ruta: Path, nuevos: dict[str, str]) -> None:
    """Agrega o reemplaza las claves indicadas y conserva las demás que ya estuvieran en .env."""
    valores = config.leer_env(ruta)
    valores.update(nuevos)
    lineas = ["# Generado por python -m app.configurar_admin. NO lo subas a Git."]
    lineas += [f"{clave}={valor}" for clave, valor in valores.items()]
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main() -> None:
    print("Configuración del administrador del CMS\n")
    ya_hay = bool(config.leer_env(config.ARCHIVO_ENV).get("ADMIN_EMAIL"))
    if ya_hay and input("Ya hay un administrador configurado. ¿Reemplazarlo? (s/N): ").strip().lower() != "s":
        print("Sin cambios.")
        return

    email = input("Correo del administrador: ").strip()
    while not CORREO.match(email):
        email = input("Ese correo no parece válido; escríbelo de nuevo: ").strip()

    while True:
        password = getpass.getpass("Contraseña (mínimo 8 caracteres; no se ve mientras escribes): ")
        if len(password) < 8:
            print("Muy corta: usa al menos 8 caracteres.")
        elif password != getpass.getpass("Repite la contraseña: "):
            print("No coinciden; intenta de nuevo.")
        else:
            break

    escribir_env(config.ARCHIVO_ENV, construir_valores(email, password))
    print(f"\nListo: se escribió {config.ARCHIVO_ENV.name}. Reinicia la API para que lo lea.")


if __name__ == "__main__":
    main()
