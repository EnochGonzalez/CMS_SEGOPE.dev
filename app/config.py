"""Configuración: variables de entorno y, si existe, el archivo .env de la raíz del proyecto.

Las variables de entorno reales tienen prioridad sobre .env. El archivo .env lo genera
`python -m app.configurar_admin` y NO se sube a Git (está en .gitignore).
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_ENV = RAIZ / ".env"


def leer_env(ruta: Path) -> dict[str, str]:
    """Lee líneas CLAVE=VALOR (ignora vacías y comentarios con #)."""
    valores: dict[str, str] = {}
    if not ruta.exists():
        return valores
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


for _clave, _valor in leer_env(ARCHIVO_ENV).items():
    os.environ.setdefault(_clave, _valor)

# ---------------------------------------------------------------- base de datos y archivos
# En desarrollo usamos SQLite (un archivo, sin instalar nada).
# Para Postgres bastará con cambiar esta URL, p. ej. postgresql+psycopg://usuario:clave@host/base
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cms.db")

# Dominio donde viven los archivos del blog (PDF, imágenes). Solo se usa al sembrar
# los datos de ejemplo, para construir URLs https absolutas como exige el Diccionario de Tipos.
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "https://santosgonzalez.dev").rstrip("/")

# ---------------------------------------------------------------- administrador y tokens
# Los tres valores los escribe `python -m app.configurar_admin`. No hay contraseña por defecto.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
TOKEN_EXPIRA_SEGUNDOS = int(os.getenv("TOKEN_EXPIRA_SEGUNDOS", "3600"))

# Límite de intentos fallidos de login (por IP + correo)
LOGIN_MAX_FALLOS = int(os.getenv("LOGIN_MAX_FALLOS", "5"))
LOGIN_VENTANA_SEGUNDOS = int(os.getenv("LOGIN_VENTANA_SEGUNDOS", "900"))     # 15 minutos

# Cuánto tiempo se recuerda una Idempotency-Key
IDEMPOTENCIA_HORAS = 24

# ---------------------------------------------------------------- archivos subidos (Bloque 3)
# El almacén local guarda los archivos en FILES_DIR y la API los sirve en FILES_PUBLIC_URL.
# En producción se cambia por un servicio externo (el almacén es intercambiable: app/storage.py).
FILES_DIR = Path(os.getenv("FILES_DIR", str(RAIZ / "uploads")))
FILES_PUBLIC_URL = os.getenv("FILES_PUBLIC_URL", "http://localhost:8000/media").rstrip("/")
MAX_PDF_BYTES = 5 * 1024 * 1024          # 5 242 880
MAX_IMAGEN_BYTES = 2 * 1024 * 1024       # 2 097 152
