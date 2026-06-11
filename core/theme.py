# -*- coding: utf-8 -*-
"""
theme.py — Motor de tema de la interfaz (Fase 3): paletas, tokens de color y
resolución de colores por nombre/hex.

Extraído de ui.py. Los tokens C_* son globals que `apply_theme_tokens` reasigna al
cambiar de color en vivo. Los widgets DEBEN referenciarlos por atributo de módulo
(`theme.C_PRI`) para leer el valor vigente — nunca `from core.theme import C_PRI`
(eso congelaría el valor del momento del import).
"""
from __future__ import annotations

# Paletas predefinidas (nombre → tokens).
THEMES = {
    "cyan": {
        "PRI": "#00d4ff", "PRI_DIM": "#005f77", "BG": "#050c14",
        "PANEL": "rgba(10, 22, 32, 0.65)", "BORDER": "rgba(0, 212, 255, 0.4)", "TEXT": "#7aeeff"
    },
    "green": {
        "PRI": "#00ff88", "PRI_DIM": "#006633", "BG": "#040e08",
        "PANEL": "rgba(8, 26, 16, 0.65)", "BORDER": "rgba(0, 255, 136, 0.4)", "TEXT": "#7affcc"
    },
    "red": {
        "PRI": "#ff3b30", "PRI_DIM": "#7a1a15", "BG": "#0e0404",
        "PANEL": "rgba(26, 8, 8, 0.65)", "BORDER": "rgba(255, 59, 48, 0.4)", "TEXT": "#ffaaaa"
    },
    "purple": {
        "PRI": "#a855f7", "PRI_DIM": "#5b21b6", "BG": "#07030f",
        "PANEL": "rgba(15, 6, 24, 0.65)", "BORDER": "rgba(168, 85, 247, 0.4)", "TEXT": "#c084fc"
    },
    "gold": {
        "PRI": "#f59e0b", "PRI_DIM": "#78350f", "BG": "#0f0a02",
        "PANEL": "rgba(30, 22, 10, 0.65)", "BORDER": "rgba(245, 158, 11, 0.4)", "TEXT": "#fde68a"
    },
    "white": {
        "PRI": "#e2e8f0", "PRI_DIM": "#64748b", "BG": "#050a14",
        "PANEL": "rgba(12, 22, 38, 0.65)", "BORDER": "rgba(226, 232, 240, 0.4)", "TEXT": "#cbd5e1"
    }
}

# Tokens vigentes (los reasigna apply_theme_tokens). Default: gold.
C_PRI = "#f59e0b"
C_PRI_DIM = "#78350f"
C_BG = "#0f0a02"
C_PANEL = "rgba(30, 22, 10, 0.65)"
C_BORDER = "rgba(245, 158, 11, 0.4)"
C_TEXT = "#fde68a"
GREEN = "#00ff88"
RED = "#ff3b30"


def _hx(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _to_hex(r, g, b):
    cl = lambda v: max(0, min(255, int(v)))
    return f"#{cl(r):02x}{cl(g):02x}{cl(b):02x}"


def _dark(hexc, f):
    r, g, b = _hx(hexc); return _to_hex(r * f, g * f, b * f)


def _light(hexc, f):
    r, g, b = _hx(hexc); return _to_hex(r + (255 - r) * f, g + (255 - g) * f, b + (255 - b) * f)


def _rgba(hexc, a):
    r, g, b = _hx(hexc); return f"rgba({r}, {g}, {b}, {a})"


def _palette_from_hex(hexc):
    return {"PRI": hexc, "PRI_DIM": _dark(hexc, 0.42), "BG": _dark(hexc, 0.05),
            "PANEL": _rgba(_dark(hexc, 0.16), 0.68), "BORDER": _rgba(hexc, 0.4),
            "TEXT": _light(hexc, 0.65)}


_NAMED_COLORS = {
    "azul neon": "#00e5ff", "azul neón": "#00e5ff", "neon blue": "#00e5ff",
    "verde neon": "#39ff14", "verde neón": "#39ff14", "neon green": "#39ff14",
    "rosa neon": "#ff2d95", "rosa neón": "#ff2d95",
    "rojo": "#ff2d2d", "red": "#ff2d2d",
    "azul": "#00a8ff", "blue": "#00a8ff", "cyan": "#00e5ff", "cian": "#00e5ff",
    "verde": "#00ff88", "green": "#00ff88",
    "morado": "#a855f7", "violeta": "#a855f7", "purple": "#a855f7", "lila": "#a855f7",
    "rosa": "#ff2d95", "pink": "#ff2d95", "fucsia": "#ff2d95",
    "amarillo": "#ffd400", "yellow": "#ffd400",
    "naranja": "#ff8c00", "orange": "#ff8c00",
    "dorado": "#f59e0b", "gold": "#f59e0b", "oro": "#f59e0b",
    "blanco": "#e2e8f0", "white": "#e2e8f0", "plata": "#e2e8f0",
    "turquesa": "#1de9b6", "celeste": "#38bdf8",
}


def resolve_palette(color: str):
    c = (color or "").lower().strip()
    if c in THEMES:
        return THEMES[c]
    if c.startswith("#") and len(c) in (4, 7):
        return _palette_from_hex(c)
    for name, hexc in _NAMED_COLORS.items():
        if name in c:
            return _palette_from_hex(hexc)
    return None


def apply_theme_tokens(theme_name: str):
    global C_PRI, C_PRI_DIM, C_BG, C_PANEL, C_BORDER, C_TEXT
    t = resolve_palette(theme_name) or THEMES["gold"]
    C_PRI = t["PRI"]
    C_PRI_DIM = t["PRI_DIM"]
    C_BG = t["BG"]
    C_PANEL = t["PANEL"]
    C_BORDER = t["BORDER"]
    C_TEXT = t["TEXT"]


# Auto-inicialización: aplicar el tema guardado en config al importar.
try:
    from memory.config_manager import load_api_keys as _load_keys
    apply_theme_tokens(_load_keys().get("jarvis_theme", "gold"))
except Exception:
    apply_theme_tokens("gold")
