"""Configuración leída de variables de entorno (con valores por defecto para desarrollo)."""
import os

# Base de datos. En desarrollo usamos SQLite (un archivo, sin instalar nada).
# Para Postgres bastará con cambiar esta URL, p. ej. postgresql+psycopg://usuario:clave@host/base
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cms.db")

# Dominio donde viven los archivos del blog (PDF, imágenes). Solo se usa al sembrar
# los datos de ejemplo, para construir URLs https absolutas como exige el Diccionario de Tipos.
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "https://santosgonzalez.dev").rstrip("/")
