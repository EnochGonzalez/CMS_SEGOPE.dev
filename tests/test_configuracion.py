"""Archivo .env y configurador del administrador (python -m app.configurar_admin)."""
from app import config
from app.configurar_admin import construir_valores, escribir_env
from app.security import verify_password


def test_leer_env_ignora_comentarios_y_quita_comillas(tmp_path):
    archivo = tmp_path / ".env"
    archivo.write_text('# comentario\n\nA=1\nB = "dos"\nC=\'tres\'\nD=con=igual\nsin-igual\n', encoding="utf-8")
    assert config.leer_env(archivo) == {"A": "1", "B": "dos", "C": "tres", "D": "con=igual"}
    assert config.leer_env(tmp_path / "no-existe") == {}


def test_escribir_env_conserva_las_otras_claves_y_reemplaza_las_repetidas(tmp_path):
    archivo = tmp_path / ".env"
    archivo.write_text("DATABASE_URL=sqlite:///./otra.db\nADMIN_EMAIL=viejo@ejemplo.com\n", encoding="utf-8")
    escribir_env(archivo, {"ADMIN_EMAIL": "nuevo@ejemplo.com", "JWT_SECRET": "abc"})
    assert config.leer_env(archivo) == {"DATABASE_URL": "sqlite:///./otra.db", "ADMIN_EMAIL": "nuevo@ejemplo.com", "JWT_SECRET": "abc"}


def test_construir_valores_guarda_el_hash_y_no_la_contrasena():
    valores = construir_valores("admin@ejemplo.com", "mi-clave-segura")
    assert set(valores) == {"ADMIN_EMAIL", "ADMIN_PASSWORD_HASH", "JWT_SECRET"}
    assert "mi-clave-segura" not in "".join(valores.values())
    assert verify_password("mi-clave-segura", valores["ADMIN_PASSWORD_HASH"])
    assert len(valores["JWT_SECRET"]) >= 48
    assert construir_valores("a@b.com", "mi-clave-segura")["JWT_SECRET"] != valores["JWT_SECRET"]
