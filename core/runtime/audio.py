# -*- coding: utf-8 -*-
"""
audio.py — Constantes y selección de dispositivo del audio de la voz (Live API).

Extraído de main.py (Fase 2). Sin estado: parámetros del stream de mic/parlante y
resolución del dispositivo elegido en config (mic_device/speaker_device).
"""
from __future__ import annotations

import sounddevice as sd

# Parámetros de los streams de audio (mic in / playback).
CHANNELS = 1
SEND_SAMPLE_RATE = 16000        # mic
RECEIVE_SAMPLE_RATE = 24000     # playback
CHUNK_SIZE = 256                # 16ms — mic input (chico = baja latencia)
PLAY_CHUNK_SIZE = 480           # 20ms — playback (más chico = menos latencia)


def audio_device(key: str):
    """Índice de dispositivo elegido en la config (mic_device/speaker_device).
    None = usar el default del sistema. Valida que exista y soporte la dirección
    correcta; si es inválido/viejo → None (nunca rompe el audio)."""
    try:
        from memory.config_manager import cfg
        v = cfg(key, "")
        if v == "" or v is None:
            return None
        idx = int(v)
        dev = sd.query_devices(idx)
        need = "max_input_channels" if "mic" in key else "max_output_channels"
        return idx if dev.get(need, 0) > 0 else None
    except Exception:
        return None
