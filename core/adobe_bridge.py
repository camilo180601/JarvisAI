"""
adobe_bridge.py — Ejecuta ExtendScript (.jsx) en apps de Adobe, cross-platform.

ExtendScript es el lenguaje común de Illustrator/InDesign/Photoshop/AE en Mac y Windows.
Esta capa abstrae CÓMO se ejecuta según el SO:
  - Mac: osascript → AppleScript (do javascript / do script)
  - Windows: win32com COM → DoJavaScript

Para evitar quoting hell, el .jsx se escribe a un archivo temporal y la app lo lee.
"""
from __future__ import annotations
import os
import subprocess
import sys
import tempfile
from pathlib import Path

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

# Catálogo de apps soportadas.
#   applescript_name: nombre para `tell application "..."` en Mac
#   bundle_globs: cómo detectar la instalación en /Applications (Mac)
#   com_progid: ProgID para COM en Windows
#   exec_kind: "do_javascript" (Illustrator/Photoshop) | "do_script_js" (InDesign)
ADOBE_APPS = {
    "illustrator": {
        "label": "Adobe Illustrator",
        "applescript_name": "Adobe Illustrator",
        "bundle_globs": ["Adobe Illustrator*/Adobe Illustrator.app", "Adobe Illustrator*.app"],
        "com_progid": "Illustrator.Application",
        "exec_kind": "do_javascript",
    },
    "photoshop": {
        "label": "Adobe Photoshop",
        "applescript_name": None,   # se resuelve dinámicamente (incluye año)
        "bundle_globs": ["Adobe Photoshop*/Adobe Photoshop*.app"],
        "com_progid": "Photoshop.Application",
        "exec_kind": "do_javascript",
    },
    "indesign": {
        "label": "Adobe InDesign",
        "applescript_name": None,   # incluye año
        "bundle_globs": ["Adobe InDesign*/Adobe InDesign*.app"],
        "com_progid": "InDesign.Application",
        "exec_kind": "do_script_js",
    },
}


def _detect_applescript_name(app_key: str) -> str | None:
    """Resuelve el nombre AppleScript real (con año) desde el bundle instalado."""
    spec = ADOBE_APPS[app_key]
    if spec["applescript_name"]:
        # Verificar que exista alguna instalación
        if _find_bundle(app_key):
            return spec["applescript_name"]
        return None
    # Resolver dinámico: el nombre AppleScript = nombre del .app sin extensión
    bundle = _find_bundle(app_key)
    if not bundle:
        return None
    return Path(bundle).stem  # ej: "Adobe Photoshop 2026"


def _bundle_is_valid(bundle: str) -> bool:
    """Un .app sirve solo si su ejecutable principal existe (no un install roto/parcial)."""
    try:
        import plistlib
        info = Path(bundle) / "Contents" / "Info.plist"
        with open(info, "rb") as fh:
            exe = plistlib.load(fh).get("CFBundleExecutable")
        if not exe:
            return False
        return (Path(bundle) / "Contents" / "MacOS" / exe).is_file()
    except Exception:
        return False


def _find_bundle(app_key: str) -> str | None:
    """Encuentra el .app instalado y funcional (Mac)."""
    if not IS_MAC:
        return None
    apps_dir = Path("/Applications")
    for glob in ADOBE_APPS[app_key]["bundle_globs"]:
        for match in apps_dir.glob(glob):
            if _bundle_is_valid(str(match)):
                return str(match)
    return None


def detect_apps() -> dict:
    """Devuelve {app_key: {installed, applescript_name, bundle}} para apps soportadas."""
    out = {}
    for key, spec in ADOBE_APPS.items():
        if IS_MAC:
            bundle = _find_bundle(key)
            installed = bundle is not None
            asname = _detect_applescript_name(key) if installed else None
            out[key] = {"installed": installed, "applescript_name": asname, "bundle": bundle, "label": spec["label"]}
        elif IS_WIN:
            # En Windows se valida intentando COM (lazy). Marcamos como "posible".
            out[key] = {"installed": None, "com_progid": spec["com_progid"], "label": spec["label"]}
        else:
            out[key] = {"installed": False, "label": spec["label"]}
    return out


def _run_mac(app_key: str, jsx_path: str, timeout: int) -> tuple[bool, str]:
    spec = ADOBE_APPS[app_key]
    asname = _detect_applescript_name(app_key)
    if not asname:
        return False, f"{spec['label']} no está instalado."

    posix = jsx_path
    if spec["exec_kind"] == "do_script_js":
        # InDesign: do script (file) language javascript
        script = (
            f'tell application "{asname}"\n'
            f'  set jsxFile to POSIX file "{posix}"\n'
            f'  set theResult to do script jsxFile language javascript\n'
            f'  return theResult as string\n'
            f'end tell'
        )
    elif app_key == "photoshop":
        # Photoshop: do javascript espera TEXTO (no resuelve bien una ref a archivo).
        # Leemos el .jsx con AppleScript y pasamos el contenido como string.
        script = (
            f'tell application "{asname}"\n'
            f'  set jsxText to (read (POSIX file "{posix}") as «class utf8»)\n'
            f'  set theResult to do javascript jsxText\n'
            f'  return theResult as string\n'
            f'end tell'
        )
    else:
        # Illustrator: do javascript (file)
        script = (
            f'tell application "{asname}"\n'
            f'  set jsxFile to POSIX file "{posix}"\n'
            f'  set theResult to do javascript jsxFile\n'
            f'  return theResult as string\n'
            f'end tell'
        )
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode == 0:
            return True, out or "(ejecutado, sin output)"
        return False, err or out or f"osascript exit {r.returncode}"
    except subprocess.TimeoutExpired:
        return False, f"Timeout {timeout}s (¿la app pidió interacción manual?)"
    except Exception as e:
        return False, str(e)


def _run_win(app_key: str, jsx_path: str, timeout: int) -> tuple[bool, str]:
    spec = ADOBE_APPS[app_key]
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return False, "Falta pywin32 (pip install pywin32) para controlar Adobe en Windows."
    try:
        app = win32com.client.Dispatch(spec["com_progid"])
        jsx_code = Path(jsx_path).read_text(encoding="utf-8")
        if app_key == "indesign":
            # InDesign COM: DoScript(script, language)
            # 1246973031 = idJavascript; usar el enum por string es más simple
            result = app.DoScript(jsx_code, 1246973031)
        else:
            result = app.DoJavaScript(jsx_code)
        return True, str(result) if result is not None else "(ejecutado)"
    except Exception as e:
        return False, f"COM error: {e}"


def run_extendscript(app_key: str, jsx_code: str, timeout: int = 120) -> tuple[bool, str]:
    """Ejecuta código ExtendScript en la app. Devuelve (ok, output/error)."""
    app_key = app_key.lower().strip()
    if app_key not in ADOBE_APPS:
        return False, f"App '{app_key}' no soportada. Usá: {', '.join(ADOBE_APPS)}"

    # Escribir el .jsx en el home (las apps Adobe leen ahí siempre; /private/tmp
    # puede no ser accesible por sandbox en algunas instalaciones — ej. Photoshop).
    script_dir = Path.home() / ".jarvis" / "adobe"
    try:
        script_dir.mkdir(parents=True, exist_ok=True)
        tmp = script_dir / "jarvis_adobe_script.jsx"
        tmp.write_text(jsx_code, encoding="utf-8")
    except Exception:
        # Fallback al temp del sistema si el home no está disponible
        tmp = Path(tempfile.gettempdir()) / "jarvis_adobe_script.jsx"
        try:
            tmp.write_text(jsx_code, encoding="utf-8")
        except Exception as e:
            return False, f"No pude escribir el script temporal: {e}"

    if IS_MAC:
        return _run_mac(app_key, str(tmp), timeout)
    elif IS_WIN:
        return _run_win(app_key, str(tmp), timeout)
    return False, f"SO no soportado para Adobe: {sys.platform}"


def app_status_human() -> str:
    apps = detect_apps()
    lines = ["Apps Adobe:"]
    for key, info in apps.items():
        if IS_MAC:
            flag = "✓" if info.get("installed") else "✗"
            extra = f" ({info.get('applescript_name')})" if info.get("applescript_name") else ""
        else:
            flag = "?"
            extra = " (COM, se valida al usar)"
        lines.append(f"  {flag} {key}{extra}")
    return "\n".join(lines)
