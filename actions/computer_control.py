"""
computer_control.py — Control directo de mouse/teclado cross-platform via pyautogui.
"""
import time
from core.registry import tool

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
except ImportError:
    pyautogui = None

try:
    import pyperclip
except ImportError:
    pyperclip = None


@tool(
    name='computer_control',
    description='Mouse/teclado: type, click, hotkey, scroll, screenshot, etc. (pyautogui cross-platform).',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'type | smart_type | click | double_click | right_click '
                                              '| hotkey | press | scroll | move | copy | paste | '
                                              'screenshot | wait | clear_field | focus_window | '
                                              'screen_find | screen_click | random_data | user_data'},
                    'text': {'type': 'STRING', 'description': 'Text to type or paste'},
                    'x': {'type': 'INTEGER', 'description': 'X coordinate'},
                    'y': {'type': 'INTEGER', 'description': 'Y coordinate'},
                    'keys': {'type': 'STRING', 'description': "Key combination e.g. 'ctrl+c'"},
                    'key': {'type': 'STRING', 'description': "Single key e.g. 'enter'"},
                    'direction': {'type': 'STRING', 'description': 'up | down | left | right'},
                    'amount': {'type': 'INTEGER', 'description': 'Scroll amount (default: 3)'},
                    'seconds': {'type': 'NUMBER', 'description': 'Seconds to wait'},
                    'title': {'type': 'STRING', 'description': 'Window title for focus_window'},
                    'description': {'type': 'STRING',
                                    'description': 'Element description for screen_find/screen_click'},
                    'type': {'type': 'STRING', 'description': 'Data type for random_data'},
                    'field': {'type': 'STRING', 'description': 'Field for user_data: name|email|city'},
                    'clear_first': {'type': 'BOOLEAN',
                                    'description': 'Clear field before typing (default: true)'},
                    'path': {'type': 'STRING', 'description': 'Save path for screenshot'}},
     'required': ['action']},
)
def computer_control(parameters: dict, player=None) -> str:
    if pyautogui is None:
        return "Error: pyautogui no instalado."

    action = (parameters.get("action") or "").lower()
    try:
        if action == "type":
            text = parameters.get("text", "")
            if not text:
                return "Error: falta 'text' para type."
            if parameters.get("clear_first"):
                pyautogui.hotkey("ctrl" if not _is_mac() else "cmd", "a")
                pyautogui.press("delete")
            # smart_type: si el texto es largo, usar clipboard
            if len(text) > 50 and pyperclip is not None:
                pyperclip.copy(text)
                pyautogui.hotkey("cmd" if _is_mac() else "ctrl", "v")
            else:
                pyautogui.typewrite(text, interval=0.02)
            return f"Texto escrito ({len(text)} chars)."

        if action in ("smart_type", "paste_type"):
            text = parameters.get("text", "")
            if not text:
                return "Error: falta 'text'."
            if pyperclip is None:
                pyautogui.typewrite(text, interval=0.02)
            else:
                pyperclip.copy(text)
                pyautogui.hotkey("cmd" if _is_mac() else "ctrl", "v")
            return f"Texto pegado ({len(text)} chars)."

        if action == "click":
            x = parameters.get("x")
            y = parameters.get("y")
            if x is not None and y is not None:
                pyautogui.click(int(x), int(y))
            else:
                pyautogui.click()
            return "Clic ejecutado."

        if action == "double_click":
            x = parameters.get("x")
            y = parameters.get("y")
            if x is not None and y is not None:
                pyautogui.doubleClick(int(x), int(y))
            else:
                pyautogui.doubleClick()
            return "Doble clic ejecutado."

        if action == "right_click":
            x = parameters.get("x")
            y = parameters.get("y")
            if x is not None and y is not None:
                pyautogui.rightClick(int(x), int(y))
            else:
                pyautogui.rightClick()
            return "Clic derecho ejecutado."

        if action == "hotkey":
            keys = parameters.get("keys", "")
            if not keys:
                return "Error: falta 'keys' (ej: 'ctrl+c')."
            parts = [k.strip().lower() for k in keys.replace("+", " ").split() if k.strip()]
            # En Mac, mapear ctrl a cmd para los atajos comunes
            if _is_mac():
                parts = ["cmd" if p == "ctrl" else p for p in parts]
            pyautogui.hotkey(*parts)
            return f"Atajo {'+'.join(parts)} ejecutado."

        if action == "press":
            key = parameters.get("key", "")
            if not key:
                return "Error: falta 'key'."
            pyautogui.press(key.lower())
            return f"Tecla {key} presionada."

        if action == "scroll":
            direction = (parameters.get("direction") or "down").lower()
            amount = int(parameters.get("amount", 3))
            delta = amount * (1 if direction == "up" else -1)
            pyautogui.scroll(delta * 100)
            return f"Scroll {direction} ({amount})."

        if action == "move":
            x = int(parameters.get("x", 0))
            y = int(parameters.get("y", 0))
            pyautogui.moveTo(x, y, duration=0.3)
            return f"Mouse movido a ({x}, {y})."

        if action == "copy":
            pyautogui.hotkey("cmd" if _is_mac() else "ctrl", "c")
            time.sleep(0.1)
            content = pyperclip.paste() if pyperclip else "(pyperclip no instalado)"
            return f"Copiado: {content[:120]}"

        if action == "paste":
            pyautogui.hotkey("cmd" if _is_mac() else "ctrl", "v")
            return "Pegado."

        if action == "screenshot":
            path = parameters.get("path", "screenshot.png")
            pyautogui.screenshot(path)
            return f"Captura guardada en {path}."

        if action == "wait":
            seconds = float(parameters.get("seconds", 1))
            time.sleep(seconds)
            return f"Esperado {seconds}s."

        if action == "clear_field":
            mod = "cmd" if _is_mac() else "ctrl"
            pyautogui.hotkey(mod, "a")
            pyautogui.press("delete")
            return "Campo limpiado."

        return f"Acción '{action}' no soportada."

    except pyautogui.FailSafeException:
        return "Error: failsafe activado (mouse en esquina). Aborto."
    except Exception as e:
        return f"Error en computer_control: {e}"


def _is_mac() -> bool:
    import sys
    return sys.platform == "darwin"
