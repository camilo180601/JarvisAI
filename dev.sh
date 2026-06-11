#!/usr/bin/env bash
# dev.sh — Inicializa y corre JARVIS en desarrollo (macOS / Linux).
#
#   ./dev.sh
#
# Crea el venv si falta, instala dependencias, baja el modelo Vosk la primera vez
# y arranca main.py. Idempotente: re-correrlo es rápido si ya está todo.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3.11}"
command -v "$PY" >/dev/null 2>&1 || PY="python3"

# 1. Entorno virtual
if [ ! -d .venv ]; then
  echo "[dev] Creando entorno virtual (.venv) con $PY…"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 2. Dependencias (rápido si ya están instaladas)
echo "[dev] Instalando dependencias…"
pip install -q --upgrade pip
pip install -q -r requirements.txt

# 3. Modelo Vosk (reconocimiento offline para el modo suspensión) — solo la 1ª vez
if [ ! -d config/vosk_model ]; then
  echo "[dev] Descargando modelo Vosk (≈39 MB)…"
  python download_vosk.py
fi

# 4. Arrancar
echo "[dev] Arrancando JARVIS…  (cerrá la ventana = bandeja; 'apagá JARVIS' = salir)"
exec python main.py
