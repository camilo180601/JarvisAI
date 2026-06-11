"""
platform_utils.py — Helpers cross-platform para JARVIS.

Centraliza detección de OS y acciones de sistema (volumen, ventanas, terminal)
para que el código de tools no tenga que duplicar branches por plataforma.
"""
from __future__ import annotations
import sys
import os
import shutil
import subprocess
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

OS_NAME = "windows" if IS_WINDOWS else "mac" if IS_MAC else "linux" if IS_LINUX else sys.platform


def get_chrome_path(cfg: dict | None = None) -> str | None:
    """Devuelve la ruta al ejecutable de Chrome según el SO actual.
    Prioriza overrides del config, después rutas conocidas."""
    cfg = cfg or {}
    if IS_WINDOWS:
        candidates = [
            cfg.get("chrome_exe_path_windows"),
            cfg.get("chrome_exe_path"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    elif IS_MAC:
        candidates = [
            cfg.get("chrome_exe_path_mac"),
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    else:
        candidates = [
            cfg.get("chrome_exe_path_linux"),
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            shutil.which("google-chrome"),
            shutil.which("chromium"),
        ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def set_master_volume(percent: int) -> tuple[bool, str]:
    """Ajusta el volumen maestro 0-100. Devuelve (ok, mensaje)."""
    percent = max(0, min(100, int(percent)))
    if IS_WINDOWS:
        try:
            from ctypes import cast, POINTER
            from comtypes import CoInitialize, CoUninitialize
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            CoInitialize()
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, 1, None)
            ctrl = cast(interface, POINTER(IAudioEndpointVolume))
            ctrl.SetMasterVolumeLevelScalar(percent / 100.0, None)
            CoUninitialize()
            return True, f"Volumen ajustado al {percent}%."
        except Exception as e:
            return False, f"Error de volumen (Windows): {e}"
    elif IS_MAC:
        try:
            subprocess.run(
                ["osascript", "-e", f"set volume output volume {percent}"],
                check=True, capture_output=True,
            )
            return True, f"Volumen ajustado al {percent}%."
        except Exception as e:
            return False, f"Error de volumen (Mac): {e}"
    else:
        # Linux: amixer / pactl
        for cmd in (
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"],
            ["amixer", "-D", "pulse", "sset", "Master", f"{percent}%"],
        ):
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, check=True, capture_output=True)
                    return True, f"Volumen ajustado al {percent}%."
                except Exception:
                    continue
        return False, "Sin herramienta de audio disponible (Linux)."


def change_volume(delta: int) -> tuple[bool, str]:
    """Sube (delta>0) o baja (delta<0) el volumen relativo en %."""
    if IS_WINDOWS:
        try:
            import pyautogui
            key = "volumeup" if delta > 0 else "volumedown"
            pyautogui.press(key, presses=max(1, abs(delta) // 2))
            return True, ("Volumen subido." if delta > 0 else "Volumen bajado.")
        except Exception as e:
            return False, f"Error volumen relativo (Windows): {e}"
    elif IS_MAC:
        try:
            r = subprocess.run(
                ["osascript", "-e", "output volume of (get volume settings)"],
                check=True, capture_output=True, text=True,
            )
            current = int(r.stdout.strip() or "50")
            return set_master_volume(current + delta)
        except Exception as e:
            return False, f"Error volumen relativo (Mac): {e}"
    else:
        # Linux: usar pactl con sintaxis +X% / -X%
        if shutil.which("pactl"):
            try:
                sign = "+" if delta > 0 else "-"
                subprocess.run(
                    ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{sign}{abs(delta)}%"],
                    check=True, capture_output=True,
                )
                return True, ("Volumen subido." if delta > 0 else "Volumen bajado.")
            except Exception as e:
                return False, str(e)
        return False, "Sin pactl disponible (Linux)."


def mute_audio(mute: bool = True) -> tuple[bool, str]:
    """Silencia (mute=True) o restaura (mute=False) el audio del sistema."""
    if IS_WINDOWS:
        try:
            import pyautogui
            pyautogui.press("volumemute")
            return True, "Volumen silenciado." if mute else "Volumen restaurado."
        except Exception as e:
            return False, str(e)
    elif IS_MAC:
        try:
            val = "true" if mute else "false"
            subprocess.run(
                ["osascript", "-e", f"set volume output muted {val}"],
                check=True, capture_output=True,
            )
            return True, "Volumen silenciado." if mute else "Volumen restaurado."
        except Exception as e:
            return False, f"Error mute (Mac): {e}"
    else:
        for cmd in (
            ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if mute else "0"],
            ["amixer", "-D", "pulse", "sset", "Master", "mute" if mute else "unmute"],
        ):
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, check=True, capture_output=True)
                    return True, "Volumen silenciado." if mute else "Volumen restaurado."
                except Exception:
                    continue
        return False, "Sin herramienta de audio (Linux)."


def minimize_active_window() -> tuple[bool, str]:
    """Minimiza la ventana activa."""
    if IS_WINDOWS:
        try:
            import pygetwindow as gw
            win = gw.getActiveWindow()
            if win:
                win.minimize()
                return True, "Ventana minimizada."
            return False, "No hay ventana activa."
        except Exception as e:
            return False, f"Error minimizando: {e}"
    elif IS_MAC:
        try:
            script = 'tell application "System Events" to set visible of (first process whose frontmost is true) to false'
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
            return True, "Ventana minimizada."
        except Exception as e:
            return False, f"Error minimizando (Mac): {e}"
    return False, "Acción no soportada en este SO."


def maximize_active_window() -> tuple[bool, str]:
    """Maximiza la ventana activa."""
    if IS_WINDOWS:
        try:
            import pygetwindow as gw
            win = gw.getActiveWindow()
            if win:
                win.maximize()
                return True, "Ventana maximizada."
            return False, "No hay ventana activa."
        except Exception as e:
            return False, f"Error maximizando: {e}"
    elif IS_MAC:
        try:
            # En macOS no existe "maximize" puro — usamos zoom (verde) vía AppleScript
            script = (
                'tell application "System Events" to tell (first process whose frontmost is true) '
                'to set value of attribute "AXFullScreen" of window 1 to true'
            )
            subprocess.run(["osascript", "-e", script], capture_output=True)
            return True, "Ventana en pantalla completa."
        except Exception as e:
            return False, f"Error maximizando (Mac): {e}"
    return False, "Acción no soportada en este SO."


def _find_mac_app(query: str) -> str | None:
    """Busca en las carpetas de apps de macOS un .app cuyo nombre contenga `query`.
    Devuelve el nombre del bundle (sin .app) o None. Prioriza match exacto y luego 'empieza con'."""
    if not query:
        return None
    dirs = ["/Applications", "/Applications/Utilities", "/System/Applications",
            "/System/Applications/Utilities", os.path.expanduser("~/Applications")]
    q = query.lower()
    names = []
    for d in dirs:
        try:
            for f in os.listdir(d):
                if f.endswith(".app"):
                    names.append(f[:-4])
                else:
                    # apps anidadas un nivel (ej Adobe: /Applications/Adobe Photoshop 2026/*.app)
                    sub = os.path.join(d, f)
                    if os.path.isdir(sub):
                        try:
                            for g in os.listdir(sub):
                                if g.endswith(".app"):
                                    names.append(g[:-4])
                        except OSError:
                            pass
        except OSError:
            continue
    if not names:
        return None
    lows = [(n, n.lower()) for n in names]
    for n, low in lows:                       # match exacto
        if low == q:
            return n
    for n, low in lows:                       # empieza con
        if low.startswith(q):
            return n
    for n, low in lows:                       # contiene
        if q in low:
            return n
    return None


def _find_windows_app(query: str) -> str | None:
    """Busca en los menús de inicio de Windows un acceso directo (.lnk) cuyo nombre
    contenga `query`. Devuelve la RUTA del .lnk (lista para 'start') o None.
    Prioriza match exacto, luego 'empieza con', luego 'contiene'."""
    if not query:
        return None
    roots = [
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                     r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("APPDATA", ""),
                     r"Microsoft\Windows\Start Menu\Programs"),
    ]
    q = query.lower()
    found = []  # (nombre_lower, ruta)
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if f.lower().endswith(".lnk"):
                    found.append((f[:-4].lower(), os.path.join(dirpath, f)))
    if not found:
        return None
    for low, path in found:                   # match exacto
        if low == q:
            return path
    for low, path in found:                   # empieza con
        if low.startswith(q):
            return path
    for low, path in found:                   # contiene
        if q in low:
            return path
    return None


def _find_linux_app(query: str) -> tuple[str, str] | None:
    """Busca en los .desktop de Linux una app cuyo nombre (campo Name= o el id del archivo)
    contenga `query`. Devuelve (desktop_id, exec_cmd) o None.
    Prioriza match exacto, luego 'empieza con', luego 'contiene'."""
    if not query:
        return None
    home = os.path.expanduser("~")
    roots = [
        "/usr/share/applications", "/usr/local/share/applications",
        os.path.join(home, ".local/share/applications"),
        "/var/lib/flatpak/exports/share/applications",
        os.path.join(home, ".local/share/flatpak/exports/share/applications"),
        "/var/lib/snapd/desktop/applications",
    ]
    q = query.lower()
    entries = []  # (name_lower, desktop_id, exec_cmd)
    for root in roots:
        if not os.path.isdir(root):
            continue
        for f in os.listdir(root):
            if not f.endswith(".desktop"):
                continue
            desktop_id = f[:-8]
            name, exec_cmd = desktop_id, ""
            try:
                with open(os.path.join(root, f), encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if line.startswith("Name=") and name == desktop_id:
                            name = line[5:].strip()
                        elif line.startswith("Exec=") and not exec_cmd:
                            # quitar placeholders %U %f etc.
                            exec_cmd = " ".join(t for t in line[5:].strip().split() if not t.startswith("%"))
            except OSError:
                continue
            entries.append((name.lower(), desktop_id, exec_cmd))
    if not entries:
        return None
    for nm, did, ex in entries:                      # match exacto
        if nm == q or did.lower() == q:
            return did, ex
    for nm, did, ex in entries:                      # empieza con
        if nm.startswith(q) or did.lower().startswith(q):
            return did, ex
    for nm, did, ex in entries:                      # contiene
        if q in nm or q in did.lower():
            return did, ex
    return None


def open_application(app_name: str) -> tuple[bool, str]:
    """Abre una app por nombre. Cross-platform."""
    if not app_name:
        return False, "Nombre de app vacío."
    if IS_WINDOWS:
        # Nombres en español (o alias) → ejecutable conocido en PATH.
        win_map = {
            "notepad": "notepad.exe", "bloc de notas": "notepad.exe", "notas": "notepad.exe",
            "calculator": "calc.exe", "calculadora": "calc.exe",
            "chrome": "chrome.exe", "google chrome": "chrome.exe",
            "edge": "msedge.exe", "microsoft edge": "msedge.exe",
            "explorer": "explorer.exe", "explorador de archivos": "explorer.exe", "archivos": "explorer.exe",
            "cmd": "cmd.exe", "terminal": "wt.exe", "powershell": "powershell.exe", "consola": "cmd.exe",
            "paint": "mspaint.exe", "wordpad": "write.exe",
            "ajustes": "ms-settings:", "configuracion": "ms-settings:", "configuración": "ms-settings:",
            "ajustes del sistema": "ms-settings:", "panel de control": "control.exe",
            "tienda": "ms-windows-store:", "microsoft store": "ms-windows-store:",
            "administrador de tareas": "taskmgr.exe", "task manager": "taskmgr.exe",
            "spotify": "spotify.exe", "whatsapp": "whatsapp:", "telegram": "telegram.exe",
            "word": "winword.exe", "excel": "excel.exe", "powerpoint": "powerpnt.exe", "outlook": "outlook.exe",
            "vscode": "code.cmd", "code": "code.cmd", "visual studio code": "code.cmd",
            # Adobe en Windows (ejecutables sin año)
            "photoshop": "Photoshop.exe", "illustrator": "Illustrator.exe",
            "indesign": "InDesign.exe", "premiere": "Adobe Premiere Pro.exe",
        }
        target = win_map.get(app_name.lower(), app_name)
        # 1) intento directo (ejecutable en PATH, comando, o URI ms-settings:/whatsapp:)
        try:
            if target.endswith(":"):
                # protocolo/URI (ms-settings:, ms-windows-store:, whatsapp:) → usar 'start'
                os.system(f'start "" "{target}"')
            else:
                subprocess.Popen(target, shell=True)
            return True, f"Abriendo {app_name}..."
        except Exception:
            pass
        # 2) match difuso: buscar el acceso directo (.lnk) en el menú de inicio
        lnk = _find_windows_app(target) or _find_windows_app(app_name)
        if lnk:
            try:
                os.startfile(lnk)  # type: ignore[attr-defined]  # solo existe en Windows
                return True, f"Abriendo {app_name}..."
            except Exception:
                try:
                    os.system(f'start "" "{lnk}"')
                    return True, f"Abriendo {app_name}..."
                except Exception:
                    pass
        return False, f"No encontré '{app_name}' en esta PC. ¿Está instalada?"
    elif IS_MAC:
        # Nombres en español (o alias) → nombre real del bundle .app en macOS.
        mac_map = {
            "notepad": "TextEdit", "bloc de notas": "TextEdit", "textedit": "TextEdit",
            "calculator": "Calculator", "calculadora": "Calculator",
            "chrome": "Google Chrome", "google chrome": "Google Chrome",
            "explorer": "Finder", "explorador de archivos": "Finder", "archivos": "Finder", "finder": "Finder",
            "cmd": "Terminal", "terminal": "Terminal", "consola": "Terminal",
            "paint": "Preview", "vista previa": "Preview", "preview": "Preview",
            "safari": "Safari", "vscode": "Visual Studio Code",
            "code": "Visual Studio Code", "spotify": "Spotify",
            "whatsapp": "WhatsApp", "telegram": "Telegram",
            # apps del sistema con nombre localizado distinto del bundle
            "notas": "Notes", "notes": "Notes",
            "musica": "Music", "música": "Music", "music": "Music",
            "mapas": "Maps", "maps": "Maps",
            "mensajes": "Messages", "messages": "Messages",
            "correo": "Mail", "mail": "Mail",
            "fotos": "Photos", "photos": "Photos",
            "calendario": "Calendar", "calendar": "Calendar",
            "contactos": "Contacts", "contacts": "Contacts",
            "recordatorios": "Reminders", "reminders": "Reminders",
            "reloj": "Clock", "clock": "Clock",
            "ajustes": "System Settings", "configuracion": "System Settings",
            "configuración": "System Settings", "preferencias del sistema": "System Settings",
            "ajustes del sistema": "System Settings", "tienda": "App Store", "app store": "App Store",
            "libros": "Books", "books": "Books", "noticias": "News",
            "fotos booth": "Photo Booth", "photo booth": "Photo Booth",
            "monitor de actividad": "Activity Monitor", "utilidad de discos": "Disk Utility",
            # Adobe (el bundle incluye el año, ej "Adobe Photoshop 2025")
            "photoshop": "Adobe Photoshop", "illustrator": "Adobe Illustrator",
            "indesign": "Adobe InDesign", "premiere": "Adobe Premiere Pro",
            "after effects": "Adobe After Effects", "lightroom": "Adobe Lightroom",
        }
        target = mac_map.get(app_name.lower(), app_name)
        # 1) intento directo (open -a hace match exacto/básico)
        try:
            subprocess.run(["open", "-a", target], check=True, capture_output=True)
            return True, f"Abriendo {target}..."
        except subprocess.CalledProcessError:
            pass
        # 2) match difuso: buscar un .app cuyo nombre contenga lo pedido
        match = _find_mac_app(target) or _find_mac_app(app_name)
        if match:
            try:
                subprocess.run(["open", "-a", match], check=True, capture_output=True)
                return True, f"Abriendo {match}..."
            except Exception:
                pass
        # 3) último recurso: abrir como ruta/bundle/url
        try:
            subprocess.run(["open", target], check=True, capture_output=True)
            return True, f"Abriendo {target}..."
        except Exception:
            return False, f"No encontré '{app_name}' en esta Mac. ¿Está instalada?"
    else:
        # Nombres en español (o alias) → binario/comando conocido en PATH.
        linux_map = {
            "navegador": "xdg-open https://", "chrome": "google-chrome", "google chrome": "google-chrome",
            "firefox": "firefox", "edge": "microsoft-edge",
            "archivos": "xdg-open .", "explorador de archivos": "xdg-open .",
            "terminal": "x-terminal-emulator", "consola": "x-terminal-emulator",
            "calculadora": "gnome-calculator", "calculator": "gnome-calculator",
            "editor de texto": "gedit", "bloc de notas": "gedit", "notas": "gedit",
            "ajustes": "gnome-control-center", "configuracion": "gnome-control-center",
            "configuración": "gnome-control-center", "ajustes del sistema": "gnome-control-center",
            "monitor del sistema": "gnome-system-monitor", "administrador de tareas": "gnome-system-monitor",
            "spotify": "spotify", "whatsapp": "whatsapp-for-linux", "telegram": "telegram-desktop",
            "vscode": "code", "code": "code", "visual studio code": "code", "vs code": "code",
            "gimp": "gimp", "inkscape": "inkscape", "blender": "blender", "discord": "discord",
        }
        target = linux_map.get(app_name.lower(), app_name)
        # 1) intento directo: si el binario existe en PATH, lanzarlo
        bin0 = target.split()[0]
        if shutil.which(bin0):
            try:
                subprocess.Popen(target.split())
                return True, f"Abriendo {app_name}..."
            except Exception:
                pass
        # 2) match difuso en los .desktop (apps con nombre amigable, Flatpak, Snap)
        found = _find_linux_app(target) or _find_linux_app(app_name)
        if found:
            desktop_id, exec_cmd = found
            # preferir gtk-launch (usa el .desktop, maneja Flatpak/Snap); si no, el Exec
            if shutil.which("gtk-launch"):
                try:
                    subprocess.Popen(["gtk-launch", desktop_id])
                    return True, f"Abriendo {app_name}..."
                except Exception:
                    pass
            if shutil.which("gio"):
                try:
                    subprocess.Popen(["gio", "launch", f"{desktop_id}.desktop"])
                    return True, f"Abriendo {app_name}..."
                except Exception:
                    pass
            if exec_cmd:
                try:
                    subprocess.Popen(exec_cmd.split())
                    return True, f"Abriendo {app_name}..."
                except Exception:
                    pass
        return False, f"No encontré '{app_name}' en este sistema. ¿Está instalada?"


def notify(title: str, message: str) -> None:
    """Muestra una notificación nativa del SO."""
    if IS_WINDOWS:
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, message, duration=5, threaded=True)
        except Exception:
            print(f"[NOTIFY] {title}: {message}")
    elif IS_MAC:
        try:
            safe_title = title.replace('"', "'")
            safe_msg = message.replace('"', "'")
            subprocess.Popen(
                ["osascript", "-e", f'display notification "{safe_msg}" with title "{safe_title}"']
            )
        except Exception:
            print(f"[NOTIFY] {title}: {message}")
    else:
        if shutil.which("notify-send"):
            subprocess.Popen(["notify-send", title, message])
        else:
            print(f"[NOTIFY] {title}: {message}")


def acquire_single_instance_lock(name: str = "jarvis_ai") -> object | None:
    """Adquiere un lock de instancia única cross-platform.
    Devuelve un handle si tuvo éxito, None si ya hay otra instancia corriendo.
    El handle debe mantenerse vivo durante toda la sesión."""
    if IS_WINDOWS:
        try:
            import ctypes
            mutex = ctypes.windll.kernel32.CreateMutexW(None, False, name.upper() + "_SINGLE_INSTANCE_MUTEX")
            if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                return None
            return mutex
        except Exception:
            return True  # No bloquear si falla la detección
    else:
        # Unix: usar fcntl con archivo /tmp
        import tempfile
        import fcntl
        lock_path = Path(tempfile.gettempdir()) / f"{name}.lock"
        try:
            f = open(lock_path, "w")
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f  # Mantener referencia para que no se cierre
        except (BlockingIOError, OSError):
            return None
