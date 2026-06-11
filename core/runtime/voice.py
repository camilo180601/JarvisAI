# -*- coding: utf-8 -*-
"""
voice.py — Configuración del modelo de VOZ (Gemini Live) y catálogo de voces.

Extraído de main.py (Fase 2). La voz es independiente del cerebro de pensamiento:
siempre Gemini 2.5 Flash audio nativo, salvo que el usuario cambie voice_model.
"""
from __future__ import annotations

import json
from pathlib import Path

LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"  # default de VOZ

_API_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "api_keys.json"

# Voces disponibles del modelo Live (nombre → (género, descripción)).
JARVIS_VOICES = {
    "Aoede":  ("Femenina", "Cálida y sofisticada — ideal para asistente IA"),
    "Kore":   ("Femenina", "Suave y precisa"),
    "Leda":   ("Femenina", "Natural y fluida"),
    "Zephyr": ("Femenina", "Dinámica y expresiva"),
    "Charon": ("Masculina", "Profunda y seria — voz original de JARVIS"),
    "Puck":   ("Masculina", "Ágil y versátil"),
    "Fenrir": ("Masculina", "Grave y autoritaria"),
    "Orus":   ("Masculina", "Clásica y equilibrada"),
}


def voice_model() -> str:
    """Modelo de VOZ (Live API). Siempre Gemini 2.5 Flash audio nativo, salvo que
    el usuario lo cambie (config voice_model). Independiente del cerebro de pensamiento."""
    try:
        from memory.config_manager import cfg
        return cfg("voice_model", "") or LIVE_MODEL
    except Exception:
        return LIVE_MODEL


def jarvis_voice() -> str:
    """Voz elegida en config/api_keys.json (default Aoede)."""
    try:
        cfg = json.loads(_API_CONFIG.read_text(encoding="utf-8"))
        return cfg.get("jarvis_voice", "Aoede")
    except Exception:
        return "Aoede"
