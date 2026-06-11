@echo off
REM dev.bat — Inicializa y corre JARVIS en desarrollo (Windows).
REM Equivalente de dev.sh: crea el venv si falta, instala deps, baja Vosk y arranca.
cd /d "%~dp0"

if not exist .venv (
    echo [dev] Creando entorno virtual...
    py -3.11 -m venv .venv 2>/dev/null || python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [dev] Instalando dependencias...
pip install -q --upgrade pip
pip install -q -r requirements.txt

if not exist config\vosk_model (
    echo [dev] Descargando modelo Vosk...
    python download_vosk.py
)

echo [dev] Arrancando JARVIS...
python main.py
