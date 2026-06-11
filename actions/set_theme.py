"""
set_theme.py — Cambia el color/tema de la interfaz por voz, en vivo.

Acepta nombres ('rojo', 'azul neón', 'verde', 'morado'...) o hex ('#00e5ff').
Aplica al instante (orb + paneles + bordes) y lo persiste para el próximo arranque.
"""
from __future__ import annotations

from core.registry import tool
from core.runtime.context import ToolContext

_SECRETS = ("gemini_api_key", "openai_api_key", "anthropic_api_key", "openrouter_api_key",
            "minimax_api_key", "tmdb_api_key", "figma_token",
            "spotify_client_id", "spotify_client_secret", "spotify_redirect_uri",
            "tuya_api_key", "tuya_api_secret", "tuya_region")


@tool(
    name="set_theme",
    description="Cambia el color/tema de la interfaz de JARVIS en vivo. USAR cuando el usuario diga 'usá color rojo', 'ponete azul neón', 'cambiá a verde', 'cambiá el tema a morado', o dé un hex. Aplica al instante (orb, paneles, bordes) y lo recuerda.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "color": {"type": "STRING", "description": "Color: rojo, azul, azul neón, verde, morado, rosa, dorado, blanco, turquesa... o un hex '#00e5ff'"}
        },
        "required": ["color"],
    },
    category="ui",
)
def set_theme(ctx: ToolContext) -> str:
    color = (ctx.get("color") or ctx.get("theme") or ctx.get("query") or "").strip()
    if not color:
        return "Decime un color: rojo, azul neón, verde, morado, dorado, o un hex como #00e5ff."

    # Validar que se pueda resolver
    try:
        from core.theme import resolve_palette
        if resolve_palette(color) is None:
            return f"No reconozco el color '{color}'. Probá: rojo, azul, azul neón, verde, morado, rosa, dorado, blanco, o un hex (#rrggbb)."
    except Exception:
        pass

    # Persistir (los secretos van en .env, no acá)
    try:
        from memory.config_manager import load_api_keys, save_api_keys
        cfg = load_api_keys()
        for s in _SECRETS:
            cfg.pop(s, None)
        cfg["jarvis_theme"] = color
        save_api_keys(cfg)
    except Exception:
        pass

    # Aplicar en vivo en el hilo de la UI
    win = getattr(ctx.player, "_win", None)
    if win is not None:
        try:
            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(win, "apply_theme_color",
                                     Qt.ConnectionType.QueuedConnection, Q_ARG(str, color))
            return f"✓ Listo, cambié la interfaz a {color}."
        except Exception as e:
            return f"Guardé el tema {color}, pero no pude aplicarlo en vivo ({str(e)[:60]}). Se verá al reiniciar."
    return f"✓ Tema {color} guardado (se aplica al reiniciar)."
