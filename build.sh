#!/usr/bin/env bash
# build.sh — Compila JARVIS y arma el instalador del SISTEMA OPERATIVO ACTUAL.
#
#   ./build.sh
#
# ⚠️ PyInstaller NO cross-compila:
#   • en macOS  → genera  release/JARVIS.dmg
#   • en Linux  → genera  release/JARVIS-linux.tar.gz
#   • el .exe de Windows SOLO se compila en Windows (ver abajo o el CI).
#
# Para obtener los 3 a la vez sin tener las 3 máquinas, usá el CI:
#   .github/workflows/build.yml  (compila en macos-/windows-/ubuntu-latest y sube los 3).
set -euo pipefail
cd "$(dirname "$0")"

# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || true
pip install -q pyinstaller

echo "[build] Congelando con PyInstaller (puede tardar varios minutos)…"
pyinstaller build.spec --noconfirm --clean

mkdir -p release
OS="$(uname -s)"
case "$OS" in
  Darwin)
    echo "[build] Creando .dmg…"
    rm -f release/JARVIS.dmg
    hdiutil create -volname "JARVIS" -srcfolder "dist/JARVIS.app" -ov -format UDZO "release/JARVIS.dmg"
    echo "[build] ✓ release/JARVIS.dmg"
    ;;
  Linux)
    echo "[build] Empaquetando Linux (tar.gz)…"
    tar -czf release/JARVIS-linux.tar.gz -C dist JARVIS
    echo "[build] ✓ release/JARVIS-linux.tar.gz   (descomprimí y corré ./JARVIS/JARVIS)"
    ;;
  *)
    echo "[build] SO '$OS' no soportado por este script."
    echo "        En Windows (PowerShell):  pyinstaller build.spec --noconfirm --clean"
    echo "        El ejecutable queda en:    dist\\JARVIS\\JARVIS.exe"
    exit 1
    ;;
esac
