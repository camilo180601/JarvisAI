# -*- mode: python ; coding: utf-8 -*-
"""
build.spec — Receta de PyInstaller para congelar JARVIS. La usan build.sh y el CI
(.github/workflows/build.yml) en las 3 plataformas. Maneja los puntos finos del app:
imports dinámicos (actions.*), datos (assets/vosk/prompt/skills) y QtWebEngine.

⚠️ Es un punto de partida: empaquetar PyQt6 + QtWebEngine + Vosk es delicado y puede
necesitar ajustes en la primera corrida (faltar un hiddenimport o un data).
"""
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

# ── Datos a incluir ──────────────────────────────────────────────────────────
datas = [
    ("assets", "assets"),
    ("core/prompt.txt", "core"),
    ("memory", "memory"),
    ("skills", "skills"),
    ("config/api_keys.example.json", "config"),
]
if os.path.exists("config/mcp_servers.example.json"):
    datas.append(("config/mcp_servers.example.json", "config"))
if os.path.isdir("config/vosk_model"):
    datas.append(("config/vosk_model", "config/vosk_model"))  # ~40 MB

binaries = []
hiddenimports = []

# Las tools se importan dinámicamente (importlib.import_module("actions.<name>")),
# así que PyInstaller no las detecta solo: las agregamos explícitamente.
hiddenimports += collect_submodules("actions")
hiddenimports += collect_submodules("core")

# Dependencias que traen datos/binarios propios.
for pkg in ("PyQt6", "google", "vosk", "qtawesome", "sounddevice",
            "cv2", "mss", "spotipy", "psutil"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_icon = "assets/jarvis_icono.ico" if sys.platform == "win32" else None

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="JARVIS",
    console=False,            # app de ventana, sin consola
    icon=_icon,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="JARVIS")

# En macOS, empaquetar como .app (con permisos de mic/cámara para TCC).
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="JARVIS.app",
        icon=None,
        bundle_identifier="com.jarvis.ia",
        info_plist={
            "NSMicrophoneUsageDescription": "JARVIS usa el micrófono para la voz.",
            "NSCameraUsageDescription": "JARVIS usa la cámara solo cuando lo pedís.",
            "LSUIElement": False,
        },
    )
