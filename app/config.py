"""Configuración: variables de entorno y, si existe, el archivo .env de la raíz del proyecto.

Las variables de entorno reales tienen prioridad sobre .env. El archivo .env lo genera
`python -m app.configurar_admin` y NO se sube a Git (está en .gitignore).
"""
import os
import re
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
FILES_PUBLIC_URL_DEFINIDA = bool(os.getenv("FILES_PUBLIC_URL"))      # ¿la escribió alguien, o es el valor de ejemplo?
MAX_PDF_BYTES = 5 * 1024 * 1024          # 5 242 880
MAX_IMAGEN_BYTES = 2 * 1024 * 1024       # 2 097 152

# ---------------------------------------------------------------- publicación en internet
# Almacén de archivos externo compatible con S3 (Supabase Storage, Cloudflare R2, Backblaze B2, AWS S3...).
# Si estos cuatro datos están completos se usa en lugar de la carpeta uploads/. FILES_PUBLIC_URL pasa a ser
# la dirección pública (https) desde la que se ven los archivos del bucket.
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "")
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "")
S3_REGION = os.getenv("S3_REGION", "us-east-1")

# Aviso al despliegue (Vercel "deploy hook"): al publicar, la API le pide a Vercel que reconstruya el blog.
DEPLOY_HOOK_URL = os.getenv("DEPLOY_HOOK_URL", "")
PIPELINE_TIMEOUT_SEGUNDOS = float(os.getenv("PIPELINE_TIMEOUT_SEGUNDOS", "10"))
PIPELINE_VENTANA_SEGUNDOS = float(os.getenv("PIPELINE_VENTANA_SEGUNDOS", "60"))

# Primera vez en un servidor nuevo: si la base está vacía, cargar el contenido inicial del blog (python -m app.seed).
SEMBRAR_SI_ESTA_VACIA = os.getenv("SEMBRAR_SI_ESTA_VACIA", "").strip().lower() in ("1", "true", "si", "sí", "yes")


def s3_configurado() -> bool:
    return all([S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY])


def _es_https_o_local(url: str) -> bool:
    """https en internet; http solo si apunta a tu propia computadora (para probar)."""
    return re.match(r"^(https://|http://(localhost|127\.0\.0\.1)(:\d+)?(/|$))", url) is not None


def problemas_de_configuracion() -> list[str]:
    """Errores que impedirían que la API funcione bien en internet. Se revisan al arrancar: es mejor fallar con un
    mensaje claro en el registro del servidor que guardar archivos con direcciones equivocadas."""
    problemas = []
    datos_s3 = [S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY]
    if any(datos_s3) and not all(datos_s3):
        problemas.append("El almacén de archivos está a medias: hacen falta S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID y S3_SECRET_ACCESS_KEY.")
    if s3_configurado() and not FILES_PUBLIC_URL_DEFINIDA:
        problemas.append("Con un almacén S3 hace falta definir FILES_PUBLIC_URL: la dirección pública https del bucket.")
    elif s3_configurado() and not _es_https_o_local(FILES_PUBLIC_URL):
        problemas.append("FILES_PUBLIC_URL debe empezar con https:// (la dirección pública del bucket).")
    if DEPLOY_HOOK_URL and not _es_https_o_local(DEPLOY_HOOK_URL):
        problemas.append("DEPLOY_HOOK_URL debe empezar con https://.")
    return problemas
