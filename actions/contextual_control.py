# -*- coding: utf-8 -*-
import sys
import subprocess
from core.registry import tool

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pygetwindow as gw
except ImportError:
    gw = None


def set_master_volume(volume_percent: int) -> bool:
    """Ajusta el volumen maestro 0-100 (delegado a platform_utils)."""
    try:
        from core.platform_utils import set_master_volume as _set
        ok, _ = _set(volume_percent)
        return ok
    except Exception as e:
        print(f"[Contextual Control] Error setting volume: {e}")
        return False


def get_master_volume() -> int:
    """Obtiene el volumen maestro actual (cross-platform)."""
    if sys.platform == "win32":
        try:
            from ctypes import cast, POINTER
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            volume = devices.EndpointVolume
            return int(round(volume.GetMasterVolumeLevelScalar() * 100))
        except Exception:
            return 50
    elif sys.platform == "darwin":
        try:
            r = subprocess.run(
                ["osascript", "-e", "output volume of (get volume settings)"],
                capture_output=True, text=True, check=True,
            )
            return int(r.stdout.strip() or "50")
        except Exception:
            return 50
    else:
        return 50

def set_brightness(percent: int) -> bool:
    """Ajusta el brillo de pantalla. Windows via WMI, Mac via 'brightness' CLI (si está instalado)."""
    if sys.platform == "win32":
        try:
            cmd = f"powershell -Command \"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{percent})\""
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        except Exception:
            try:
                cmd2 = f"powershell -Command \"Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=0; Brightness={percent}}}\""
                subprocess.run(cmd2, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                return True
            except Exception:
                return False
    elif sys.platform == "darwin":
        # Requiere `brew install brightness`
        try:
            subprocess.run(
                ["brightness", f"{max(0, min(100, percent)) / 100.0}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
            )
            return True
        except FileNotFoundError:
            print("[Contextual Control] CLI 'brightness' no instalada (brew install brightness).")
            return False
        except Exception:
            return False
    elif sys.platform.startswith("linux"):
        import shutil as _sh
        pct = max(0, min(100, percent))
        if _sh.which("brightnessctl"):
            try:
                subprocess.run(["brightnessctl", "set", f"{pct}%"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                return True
            except Exception:
                pass
        if _sh.which("xbacklight"):
            try:
                subprocess.run(["xbacklight", "-set", str(pct)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                return True
            except Exception:
                pass
        print("[Contextual Control] Sin brightnessctl/xbacklight (Linux).")
        return False
    return False


def set_power_plan(plan_name: str) -> bool:
    """Cambia el plan de energía. Windows via powercfg, Mac via pmset (mapeo aproximado)."""
    if sys.platform == "win32":
        plans = {
            "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
            "high_performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
            "power_saver": "a1841308-3541-4fab-bc81-f71556f20b4a"
        }
        guid = plans.get(plan_name.lower())
        if not guid:
            return False
        try:
            subprocess.run(f"powercfg /setactive {guid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        except Exception as e:
            print(f"[Contextual Control] Error setting power plan: {e}")
            return False
    elif sys.platform == "darwin":
        # En Mac no hay "planes" como en Windows. Mapeamos a pmset (requiere sudo, así que solo flags básicos sin sudo).
        # No-op silencioso para no romper adjust_context.
        return False
    return False


def set_focus_assist(level: int) -> bool:
    """Ajusta No Molestar. Windows via registro, Mac via shortcut de Focus (best-effort)."""
    # 0 = Off, 1 = Priority Only, 2 = Alarms Only
    if sys.platform == "win32":
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "Noc", 0, winreg.REG_DWORD, level)
            winreg.CloseKey(key)
            return True
        except Exception as e:
            print(f"[Contextual Control] Error setting Focus Assist: {e}")
            return False
    elif sys.platform == "darwin":
        # macOS Focus mode no es trivial vía CLI. Lo dejamos como no soportado.
        return False
    return False

@tool(
    name='contextual_control',
    description='Auto-ajusta volumen/brillo/energía/DND según ventana activa. action=adjust_context o set_volume/set_brightness/set_power_plan/set_dnd.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'adjust_context (auto-ajustar por ventana activa) | '
                                              'set_volume (fijar volumen) | set_brightness (fijar '
                                              'brillo) | set_power_plan (energía) | set_dnd (no '
                                              'molestar)'},
                    'volume': {'type': 'INTEGER', 'description': 'Nivel de volumen maestro (0-100)'},
                    'brightness': {'type': 'INTEGER',
                                   'description': 'Nivel de brillo de la pantalla (0-100)'},
                    'power_plan': {'type': 'STRING',
                                   'description': 'Plan de energía de Windows: balanced | '
                                                  'high_performance | power_saver'},
                    'state': {'type': 'STRING',
                              'description': 'Estado de No Molestar (Focus Assist): on | off | '
                                             'alarms'}},
     'required': ['action']},
)
def contextual_control(parameters: dict, player=None) -> str:
    """
    Control Contextual de Entorno. Ajusta dinámicamente volumen, brillo, energía y notificaciones
    según la ventana activa, hábitos de uso o comandos manuales.
    """
    action = parameters.get("action", "adjust_context").lower()
    
    if action == "set_volume":
        vol = parameters.get("volume")
        if vol is None:
            return "Error: Falta el parámetro 'volume' (0-100) para la acción 'set_volume'."
        vol = int(vol)
        if set_master_volume(vol):
            return f"Volumen maestro ajustado correctamente al {vol}%."
        return "No se pudo cambiar el volumen maestro."

    elif action == "set_brightness":
        bri = parameters.get("brightness")
        if bri is None:
            return "Error: Falta el parámetro 'brightness' (0-100) para la acción 'set_brightness'."
        bri = int(bri)
        if set_brightness(bri):
            return f"Brillo de pantalla ajustado correctamente al {bri}%."
        return "El ajuste de brillo de pantalla no está soportado en este hardware (común en PC de escritorio sin soporte WMI)."

    elif action == "set_power_plan":
        plan = parameters.get("power_plan")
        if not plan:
            return "Error: Falta el parámetro 'power_plan' (balanced, high_performance, power_saver) para la acción 'set_power_plan'."
        if set_power_plan(plan):
            return f"Plan de energía cambiado correctamente a '{plan}'."
        return f"No se pudo cambiar al plan de energía '{plan}'."

    elif action == "set_dnd":
        # Do Not Disturb / Focus Assist
        state = parameters.get("state", "off").lower()
        level = 0
        if state == "on" or state == "priority":
            level = 1
        elif state == "alarms":
            level = 2
            
        if set_focus_assist(level):
            return f"Focus Assist (No Molestar) configurado al nivel {level} ({state})."
        return "No se pudo ajustar el estado de Focus Assist."

    elif action == "adjust_context":
        # Detección inteligente por ventana en foco
        title = ""
        if sys.platform == "darwin":
            # En Mac pygetwindow importa pero no tiene getActiveWindow → ir directo
            # a osascript. (Antes esta rama era inalcanzable porque gw no es None.)
            try:
                r = subprocess.run(
                    ["osascript", "-e",
                     'tell application "System Events" to get name of first application process whose frontmost is true'],
                    capture_output=True, text=True, check=True,
                )
                title = (r.stdout or "").strip().lower()
            except Exception:
                title = ""
        elif gw is not None:
            try:
                win = gw.getActiveWindow()
                title = win.title.lower() if win and win.title else ""
            except Exception:
                title = ""

        if not title and psutil is not None:
            # Fallback a buscar procesos activos de interés
            active_procs = []
            for proc in psutil.process_iter(['name']):
                try:
                    active_procs.append(proc.info['name'].lower())
                except Exception:
                    pass
            title = " ".join(active_procs)

        result_msgs = []
        
        # Categorías contextuales
        # 1. Comunicación / Reunión
        if any(w in title for w in ["zoom", "teams", "meet", "discord", "skype", "whatsapp"]):
            set_master_volume(40)
            set_brightness(60)
            set_power_plan("balanced")
            set_focus_assist(1)  # Solo Prioridad
            result_msgs.append("Modo Reunión/Comunicación: Volumen 40%, Brillo 60%, Energía Equilibrado, No Molestar Activo.")
            
        # 2. Gaming / Alto Rendimiento
        elif any(w in title for w in ["steam", "epicgames", "cyberpunk", "csgo", "minecraft", "valorant", "gta"]):
            set_master_volume(75)
            set_brightness(90)
            set_power_plan("high_performance")
            set_focus_assist(2)  # Solo Alarmas
            result_msgs.append("Modo Gaming: Volumen 75%, Brillo 90%, Alto Rendimiento activado, No Molestar total.")

        # 3. Multimedia / Entretenimiento
        elif any(w in title for w in ["vlc", "netflix", "prime video", "youtube", "spotify"]):
            set_master_volume(80)
            set_brightness(80)
            set_power_plan("balanced")
            set_focus_assist(0)  # Apagado (para ver notificaciones o según preferencia)
            result_msgs.append("Modo Multimedia: Volumen 80%, Brillo 80%, Energía Equilibrado, No Molestar Desactivado.")

        # 4. Trabajo de Foco / Programación / Oficina
        elif any(w in title for w in ["word", "excel", "powerpoint", "vscode", "notepad", "sublime", "pdf", "python", "jarvis"]):
            set_master_volume(20)
            set_brightness(50)
            set_power_plan("power_saver")
            set_focus_assist(1)
            result_msgs.append("Modo Productividad/Foco: Volumen 20% (silencioso), Brillo 50% (cuidado de vista), Ahorro de Energía, No Molestar Activo.")
            
        else:
            # Valores por defecto para otros contextos
            set_master_volume(50)
            set_brightness(70)
            set_power_plan("balanced")
            set_focus_assist(0)
            result_msgs.append(f"Contexto general ('{title[:40]}...'): Ajustes estándar aplicados (Volumen 50%, Brillo 70%, Plan Equilibrado, Notificaciones activas).")
            
        return result_msgs[0]

    else:
        return f"Acción '{action}' no soportada por el módulo de Control Contextual."
