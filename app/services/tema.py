"""Apariencia del blog: los estilos disponibles y cómo se convierten en las variables CSS del blog.

El blog ya declara sus colores y tipografías como variables en `:root` (CSS/index.css, about.css y proyecto.css). Cambiar la
apariencia es dar otros valores a esas mismas variables: el diseño (la estructura de las páginas) no se toca.

Los valores de «segope» son EXACTAMENTE los del CSS actual del blog. Si algún día cambias los colores del CSS, cambia aquí
también el estilo «segope» (una prueba de cada repositorio avisa si se desfasan).
"""
from app.errors import ApiError

# Contrastes mínimos (WCAG): el acento se usa como TEXTO sobre el fondo (etiquetas, enlaces) y como FONDO de botones con texto blanco.
CONTRASTE_MIN_TEXTO = 4.5
CONTRASTE_MIN_BOTON = 3.0

PRESETS = {
    "segope": {"label": "SEGOPE (original)", "bg": "#0c0404", "bg_elevated": "#160808", "ink": "#ffffff", "ink_soft": "#a39898",
               "line": "#301010", "line_strong": "#4a1c1c", "accent": "#ef4444", "accent_warm": "#dc2626"},
    "azul-noche": {"label": "Azul noche", "bg": "#060b18", "bg_elevated": "#0d1426", "ink": "#ffffff", "ink_soft": "#94a3b8",
                   "line": "#1b2744", "line_strong": "#2a3a63", "accent": "#3b82f6", "accent_warm": "#2563eb"},
    "verde-terminal": {"label": "Verde terminal", "bg": "#040a06", "bg_elevated": "#08140c", "ink": "#e8fff0", "ink_soft": "#8fae9a",
                       "line": "#10301a", "line_strong": "#1c4a2a", "accent": "#16a34a", "accent_warm": "#15803d"},
    "violeta": {"label": "Violeta", "bg": "#0a0612", "bg_elevated": "#130c20", "ink": "#ffffff", "ink_soft": "#a99fbf",
                "line": "#2a1b45", "line_strong": "#3d2766", "accent": "#a855f7", "accent_warm": "#9333ea"},
}
# Solo tipografías que ya traen los sistemas (no se descarga nada de internet: el blog sigue siendo rápido y sin terceros).
FUENTES_CUERPO = {
    "sistema": ("Del sistema (original)", "'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif"),
    "serif": ("Con serifas", "Georgia, 'Times New Roman', Times, serif"),
    "humanista": ("Humanista", "'Trebuchet MS', Verdana, Geneva, sans-serif"),
}
FUENTES_MONO = {
    "clasica": ("Clásica (original)", "'Courier New', Courier, monospace"),
    "moderna": ("Moderna", "Consolas, 'SF Mono', Menlo, 'DejaVu Sans Mono', monospace"),
}
ESQUINAS = {"cuadradas": ("Cuadradas", "0px"), "normales": ("Normales (original)", "3px"), "redondeadas": ("Redondeadas", "10px")}
TAMANOS = {"pequeno": ("Pequeño", "94%"), "normal": ("Normal (original)", "100%"), "grande": ("Grande", "110%")}

# Colores de acento que ya cumplen los dos contrastes sobre TODOS los estilos (hay una prueba que lo verifica). Un color propio
# tiene que caer en una franja estrecha: lo bastante claro para leerse sobre el fondo oscuro y lo bastante oscuro para llevar texto blanco.
ACENTOS_SUGERIDOS = ["#ef4444", "#ea580c", "#d97706", "#16a34a", "#0d9488", "#0284c7", "#8b5cf6", "#ec4899"]

PREDETERMINADO = {"preset": "segope", "accent": None, "font_body": "sistema", "font_mono": "clasica", "radius": "normales", "text_size": "normal"}

NOMBRES_CSS = {"bg": "--bg", "bg_elevated": "--bg-elevated", "ink": "--ink", "ink_soft": "--ink-soft", "line": "--line",
               "line_strong": "--line-strong", "accent": "--accent", "accent_warm": "--accent-warm"}


# ------------------------------------------------------------------ contraste (WCAG 2.x)
def _canal(valor: int) -> float:
    c = valor / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminancia(color: str) -> float:
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _canal(r) + 0.7152 * _canal(g) + 0.0722 * _canal(b)


def contraste(a: str, b: str) -> float:
    claro, oscuro = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


def acento_calido(acento: str) -> str:
    """La variante que el blog usa al pasar el cursor: el mismo color un 14 % más oscuro. Se calcula con enteros (redondeo hacia
    arriba en la mitad) para que la vista previa de la consola, en JavaScript, dé exactamente el mismo resultado."""
    return "#" + "".join(f"{(int(acento[i:i + 2], 16) * 86 + 50) // 100:02x}" for i in (1, 3, 5))


def comprobar_acento(preset: str, acento: str) -> None:
    """Un color propio debe leerse bien: si no, el blog quedaría ilegible. Aquí se rechaza con un mensaje que dice qué hacer."""
    fondo = PRESETS[preset]["bg"]
    como_texto = contraste(acento, fondo)
    if como_texto < CONTRASTE_MIN_TEXTO:
        raise ApiError(422, "VALIDATION_ERROR", "Ese color de acento no se lee bien sobre el fondo del estilo elegido",
                       [{"field": "accent", "issue": f"Contraste {como_texto:.1f}:1 sobre el fondo; el mínimo es {CONTRASTE_MIN_TEXTO}:1. Prueba un color más claro."}])
    en_boton = contraste("#ffffff", acento)
    if en_boton < CONTRASTE_MIN_BOTON:
        raise ApiError(422, "VALIDATION_ERROR", "El texto blanco de los botones no se lee sobre ese color de acento",
                       [{"field": "accent", "issue": f"Contraste {en_boton:.1f}:1 con el texto blanco; el mínimo es {CONTRASTE_MIN_BOTON}:1. Prueba un color más oscuro."}])


# ------------------------------------------------------------------ de la selección a las variables CSS
def resolver(seleccion: dict) -> dict:
    paleta = PRESETS[seleccion["preset"]]
    acento = (seleccion.get("accent") or paleta["accent"]).lower()
    calido = acento_calido(acento) if seleccion.get("accent") else paleta["accent_warm"]
    variables = {NOMBRES_CSS[k]: paleta[k] for k in NOMBRES_CSS if k not in ("accent", "accent_warm")}
    variables["--accent"], variables["--accent-warm"] = acento, calido
    variables["--font-body"] = FUENTES_CUERPO[seleccion["font_body"]][1]
    variables["--font-mono"] = FUENTES_MONO[seleccion["font_mono"]][1]
    variables["--radius"] = ESQUINAS[seleccion["radius"]][1]
    return {"vars": variables, "root_font_size": TAMANOS[seleccion["text_size"]][1], "is_default": _sin_cambios(variables, seleccion["text_size"])}


def _sin_cambios(variables: dict, tamano: str) -> bool:
    base = PREDETERMINADO
    paleta = PRESETS[base["preset"]]
    original = {NOMBRES_CSS[k]: paleta[k] for k in NOMBRES_CSS}
    original.update({"--font-body": FUENTES_CUERPO[base["font_body"]][1], "--font-mono": FUENTES_MONO[base["font_mono"]][1],
                     "--radius": ESQUINAS[base["radius"]][1]})
    return variables == original and tamano == base["text_size"]


def catalogo() -> dict:
    """Todo lo que la consola necesita para dibujar las opciones (y la vista previa) sin repetir los valores."""
    return {
        "presets": [{"key": k, "label": p["label"], "palette": {n: p[n] for n in NOMBRES_CSS}} for k, p in PRESETS.items()],
        "fonts_body": [{"key": k, "label": e, "stack": s} for k, (e, s) in FUENTES_CUERPO.items()],
        "fonts_mono": [{"key": k, "label": e, "stack": s} for k, (e, s) in FUENTES_MONO.items()],
        "radius": [{"key": k, "label": e, "value": v} for k, (e, v) in ESQUINAS.items()],
        "text_size": [{"key": k, "label": e, "value": v} for k, (e, v) in TAMANOS.items()],
        "default": dict(PREDETERMINADO),
        "accent_suggestions": list(ACENTOS_SUGERIDOS),
        "min_contrast_text": CONTRASTE_MIN_TEXTO,
        "min_contrast_button": CONTRASTE_MIN_BOTON,
    }
