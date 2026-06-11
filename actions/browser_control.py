# -*- coding: utf-8 -*-
"""
browser_control.py — Controla el navegador ABIERTO del usuario (cross-platform).

macOS: vía AppleScript (confiable, no depende de foco ni de simular teclas).
Windows: pygetwindow + atajos Ctrl. Linux: atajos sobre la ventana activa (best-effort).
"""
import sys
import time
import subprocess
import urllib.parse

from core.registry import tool

_IS_MAC = sys.platform == "darwin"
_IS_WIN = sys.platform == "win32"

# Navegadores soportados, por prioridad. Los Chromium comparten el dict de AppleScript.
_BROWSERS = ["Google Chrome", "Brave Browser", "Microsoft Edge", "Opera", "Arc", "Safari", "Firefox"]
_CHROMIUM = {"Google Chrome", "Brave Browser", "Microsoft Edge", "Opera", "Arc"}


def _osa(script: str):
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)


def _norm_url(u: str) -> str:
    u = (u or "").strip()
    if u and not u.startswith(("http://", "https://", "file://", "about:", "chrome:")):
        u = "https://" + u
    return u


def _search_url(q: str) -> str:
    return "https://www.google.com/search?q=" + urllib.parse.quote((q or "").strip())


def _running_mac_browsers():
    try:
        r = _osa('tell application "System Events" to get name of (processes where background only is false)')
        names = {n.strip() for n in (r.stdout or "").split(",")}
        return [b for b in _BROWSERS if b in names]
    except Exception:
        return []


def _frontmost_mac_app() -> str:
    """Nombre del proceso que está al frente (o '' si falla osascript)."""
    try:
        r = _osa('tell application "System Events" to get name of first process whose frontmost is true')
        return (r.stdout or "").strip()
    except Exception:
        return ""


def _mac_control(action, url, query, direction) -> str:
    running = _running_mac_browsers()
    if not running:
        return "No hay ningún navegador abierto (Chrome, Safari, Firefox…). Abrí uno y reintento."
    # Preferir el navegador que YA está al frente; si no hay ninguno, el de mayor prioridad.
    front = _frontmost_mac_app()
    app = front if front in running else running[0]
    _osa(f'tell application "{app}" to activate')
    time.sleep(0.15)

    if action in ("go_to", "search", "new_tab"):
        target = _search_url(query) if action == "search" else _norm_url(url)
        if not target:
            return "Falta la URL (o el término de búsqueda)."
        t = target.replace('"', '%22')
        if app in _CHROMIUM:
            if action == "new_tab":
                _osa(f'tell application "{app}" to tell front window to make new tab with properties {{URL:"{t}"}}')
            else:
                _osa(f'tell application "{app}"\n'
                     f'if (count of windows) = 0 then make new window\n'
                     f'set URL of active tab of front window to "{t}"\n'
                     f'end tell')
        elif app == "Safari":
            if action == "new_tab":
                _osa(f'tell application "Safari" to tell front window to set current tab to (make new tab with properties {{URL:"{t}"}})')
            else:
                _osa(f'tell application "Safari"\n'
                     f'if (count of windows) = 0 then make new document\n'
                     f'set URL of current tab of front window to "{t}"\n'
                     f'end tell')
        else:  # Firefox u otros sin AppleScript de URL → simular Cmd+L + escribir
            _osa('tell application "System Events" to keystroke "l" using command down')
            time.sleep(0.1)
            ta = t.replace("\\", "\\\\").replace('"', '\\"')
            _osa(f'tell application "System Events" to keystroke "{ta}"')
            _osa('tell application "System Events" to key code 36')  # Return
        verb = "Buscando" if action == "search" else ("Nueva pestaña →" if action == "new_tab" else "Navegando a")
        return f"{verb} {target} en {app}."

    if action == "close_tab":
        _osa('tell application "System Events" to keystroke "w" using command down')
        return f"Pestaña cerrada en {app}."

    if action == "scroll":
        key = 116 if (direction or "down") == "up" else 121  # 116=Page Up, 121=Page Down
        _osa(f'tell application "System Events" to key code {key}')
        return f"Scroll hacia {direction or 'down'} en {app}."

    return f"Acción '{action}' no soportada."


def _keys_control(action, url, query, direction) -> str:
    """Windows / Linux: atajos de teclado con Ctrl sobre la ventana del navegador."""
    import pyautogui
    mod = "ctrl"
    # En Windows enfocamos la ventana del navegador con pygetwindow; en Linux usamos la activa.
    if _IS_WIN:
        try:
            import pygetwindow as gw
            target = None
            for win in gw.getAllWindows():
                if win.title.strip() and any(k.lower() in win.title.lower()
                                             for k in ("chrome", "edge", "firefox", "brave", "opera")):
                    target = win
                    break
            if not target:
                return "No encontré un navegador abierto."
            if target.isMinimized:
                target.restore()
            target.activate()
            time.sleep(0.15)
        except Exception as e:
            return f"No pude enfocar el navegador: {str(e)[:80]}"

    try:
        if action in ("go_to", "search"):
            text = _norm_url(url) if action == "go_to" else (query or "")
            if not text:
                return "Falta URL o término de búsqueda."
            pyautogui.hotkey(mod, "l"); time.sleep(0.05)
            pyautogui.write(text, interval=0.005); pyautogui.press("enter")
            return f"{'Navegando a' if action=='go_to' else 'Buscando'} {text}."
        if action == "new_tab":
            pyautogui.hotkey(mod, "t"); time.sleep(0.25)
            if url:
                pyautogui.write(_norm_url(url), interval=0.01); pyautogui.press("enter")
                return f"Nueva pestaña → {url}."
            return "Nueva pestaña abierta."
        if action == "close_tab":
            pyautogui.hotkey(mod, "w"); return "Pestaña cerrada."
        if action == "scroll":
            pyautogui.press("pgup" if (direction or "down") == "up" else "pgdn")
            return f"Scroll hacia {direction or 'down'}."
        return f"Acción '{action}' no soportada."
    except Exception as e:
        return f"Error controlando el navegador: {str(e)[:80]}"


@tool(
    name='browser_control',
    description='Navegador activo: go_to, search, new_tab, close_tab, scroll.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'Acciones permitidas: go_to | search | new_tab | '
                                              'close_tab | scroll'},
                    'url': {'type': 'STRING', 'description': 'URL para las acciones go_to o new_tab'},
                    'query': {'type': 'STRING',
                              'description': 'Término de búsqueda para la acción search'},
                    'direction': {'type': 'STRING',
                                  'description': 'Dirección de scroll: up | down (solo para scroll)'}},
     'required': ['action']},
)
def browser_control(parameters: dict, player=None) -> str:
    """Controla el navegador abierto del usuario (Chrome/Safari/Firefox/Edge/…)."""
    action = (parameters.get("action") or "").strip()
    url = parameters.get("url", "")
    query = parameters.get("query", "")
    direction = parameters.get("direction", "")
    if not action:
        return "Falta 'action' (go_to | search | new_tab | close_tab | scroll)."
    try:
        if _IS_MAC:
            return _mac_control(action, url, query, direction)
        return _keys_control(action, url, query, direction)
    except Exception as e:
        return f"Error al controlar el navegador: {str(e)[:100]}"
