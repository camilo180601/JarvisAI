"""computer_settings.py — Control cross-platform de volumen y ventanas."""
from core.platform_utils import (
    set_master_volume, change_volume, mute_audio,
    minimize_active_window, maximize_active_window,
)
from core.registry import tool


@tool(
    name='computer_settings',
    description="Volumen, ventana minimize/maximize. action='volume' con value (número 0-100, up, down, mute).",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING', 'description': 'The action to perform'},
                    'description': {'type': 'STRING',
                                    'description': 'Natural language description of what to do'},
                    'value': {'type': 'STRING',
                              'description': 'Optional value: volume level, text to type, etc.'}},
     'required': []},
)
def computer_settings(parameters: dict, response=None, player=None) -> str:
    """Ajusta volumen o estado de ventana activa."""
    action = parameters.get("action", "").lower()
    value = parameters.get("value", "")

    if action == "volume":
        if str(value).isdigit():
            _, msg = set_master_volume(int(value))
        else:
            v = str(value).lower()
            if "up" in v or "subir" in v:
                _, msg = change_volume(+10)
            elif "down" in v or "bajar" in v:
                _, msg = change_volume(-10)
            elif "mute" in v or "silenciar" in v:
                _, msg = mute_audio(True)
            else:
                msg = f"Acción de volumen no reconocida: {value}"
        if player:
            player.write_log(f"🔊 {msg}")
        return msg

    elif action in ("minimize", "window_minimize"):
        _, msg = minimize_active_window()
        return msg

    elif action in ("maximize", "window_maximize"):
        _, msg = maximize_active_window()
        return msg

    return f"Settings action '{action}' is not supported yet, sir."
