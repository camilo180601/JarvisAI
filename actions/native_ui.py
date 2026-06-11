# -*- coding: utf-8 -*-
"""
native_ui.py — Automatización de ventanas nativas (cross-platform).

macOS: AppleScript/System Events (pygetwindow no funciona en Mac).
Windows: pygetwindow + pyautogui (comportamiento original).
"""
import sys
import time
import subprocess

from core.registry import tool

_IS_MAC = sys.platform == "darwin"


def _osa(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    return (r.stdout or "").strip()


# ── macOS (System Events) ────────────────────────────────────────────────────

def _mac_windows() -> list[tuple[str, str]]:
    """[(app, título_de_ventana)] de las apps visibles."""
    out = _osa(
        'set acc to ""\n'
        'tell application "System Events"\n'
        'repeat with p in (processes where background only is false)\n'
        'repeat with w in (windows of p)\n'
        'set acc to acc & (name of p) & "||" & (name of w) & "\\n"\n'
        'end repeat\nend repeat\nend tell\nreturn acc'
    )
    wins = []
    for line in out.splitlines():
        if "||" in line:
            app, title = line.split("||", 1)
            if title.strip():
                wins.append((app.strip(), title.strip()))
    return wins


def _mac_find(window_title: str):
    q = window_title.lower().strip()
    for app, title in _mac_windows():
        if q in title.lower() or q in app.lower():
            return app, title
    return None, None


def _mac_focus(app: str) -> None:
    _osa(f'tell application "{app}" to activate')
    time.sleep(0.4)


def _mac_native_ui(action, window_title, text_to_type) -> str:
    if action == "list_windows":
        wins = _mac_windows()
        if not wins:
            return "No encontré ventanas abiertas (¿permiso de Accesibilidad otorgado?)."
        return "Ventanas abiertas:\n" + "\n".join(f"{a} — {t}" for a, t in wins[:25])

    if not window_title:
        return "Error: se requiere el nombre de la ventana (window_title)."
    app, title = _mac_find(window_title)
    if not app:
        return f"No se encontró ninguna ventana que coincida con '{window_title}'."

    if action == "focus_window":
        _mac_focus(app)
        return f"Ventana '{title}' ({app}) enfocada."

    if action == "type_in_window":
        if not text_to_type:
            return "Error: falta el texto (text)."
        _mac_focus(app)
        esc = text_to_type.replace("\\", "\\\\").replace('"', '\\"')
        _osa(f'tell application "System Events" to keystroke "{esc}"')
        return f"Texto escrito en '{title}' ({app})."

    if action == "click_center":
        _mac_focus(app)
        pos = _osa(f'tell application "System Events" to tell process "{app}" to get position of front window')
        size = _osa(f'tell application "System Events" to tell process "{app}" to get size of front window')
        try:
            x, y = [int(v) for v in pos.split(",")]
            w, h = [int(v) for v in size.split(",")]
            import pyautogui
            pyautogui.click(x + w // 2, y + h // 2)
            return f"Clic en el centro de '{title}' ({app})."
        except Exception as e:
            return f"No pude calcular el centro de la ventana: {str(e)[:80]}"

    return f"Acción '{action}' no soportada por native_ui."


# ── Windows (pygetwindow, comportamiento original) ───────────────────────────

def _win_native_ui(action, window_title, text_to_type) -> str:
    import pygetwindow as gw
    import pyautogui

    if action == "list_windows":
        titles = [t for t in gw.getAllTitles() if t.strip()]
        return "Ventanas abiertas:\n" + "\n".join(titles)

    if not window_title:
        return "Error: se requiere el nombre de la ventana (window_title)."
    windows = gw.getWindowsWithTitle(window_title)
    if not windows:
        return f"No se encontró ninguna ventana con el título: '{window_title}'"
    win = windows[0]

    try:
        if win.isMinimized:
            win.restore()
        win.activate()
        if action == "focus_window":
            return f"Ventana '{win.title}' enfocada exitosamente."
        time.sleep(0.5)
        if action == "type_in_window":
            if not text_to_type:
                return "Error: falta el texto (text)."
            pyautogui.write(text_to_type, interval=0.01)
            return f"Texto escrito en la ventana '{win.title}'."
        if action == "click_center":
            cx = win.left + (win.width // 2)
            cy = win.top + (win.height // 2)
            pyautogui.click(cx, cy)
            return f"Clic realizado en el centro de la ventana '{win.title}'."
        return f"Acción '{action}' no soportada por native_ui."
    except Exception as e:
        return f"Error en native_ui: {str(e)[:100]}"


@tool(
    name='native_ui',
    description='Automatización de ventanas nativas: list_windows, focus_window, type_in_window, click_center. Cross-platform (Mac vía System Events, Windows vía pygetwindow).',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'Acción a realizar: list_windows | focus_window | '
                                              'type_in_window | click_center'},
                    'window_title': {'type': 'STRING',
                                     'description': 'El nombre (o parte del nombre) de la ventana '
                                                    "destino. (Ej: 'WhatsApp', 'Chrome')"},
                    'text': {'type': 'STRING',
                             'description': 'El texto a escribir (solo si action es type_in_window)'}},
     'required': ['action']},
)
def native_ui(parameters: dict, player=None) -> str:
    """Automatización nativa de ventanas: listar, enfocar, escribir y clickear."""
    action = parameters.get("action", "")
    window_title = parameters.get("window_title", "")
    text_to_type = parameters.get("text", "")
    try:
        if _IS_MAC:
            return _mac_native_ui(action, window_title, text_to_type)
        return _win_native_ui(action, window_title, text_to_type)
    except Exception as e:
        return f"Error en native_ui: {str(e)[:100]}"
