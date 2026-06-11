"""
mac_control.py — Control de macOS y apps nativas vía AppleScript (gratis, sin deps).

Acciones (action=...):
  notes_add / notes_list                  Notas
  reminder_add / reminders_list           Recordatorios
  message_send                            Mensajes (iMessage)
  finder_reveal / finder_new_folder       Finder
  screenshot                              Captura de pantalla a archivo
  dark_mode                               Modo oscuro on/off/toggle
  wifi / bluetooth                        Encender/apagar
  dnd                                     No Molestar (Focus) on/off
  wallpaper                               Cambiar fondo de pantalla
  brightness                              Brillo 0-100
  browser_tab                             Leer pestaña activa de Safari/Chrome
  browser_open                            Abrir URL en el navegador
  empty_trash                             Vaciar papelera
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
from core.registry import tool

IS_MAC = sys.platform == "darwin"


def _osa(script: str, timeout: int = 30) -> tuple[bool, str]:
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode == 0:
            return True, out
        return False, err or out or f"osascript exit {r.returncode}"
    except subprocess.TimeoutExpired:
        return False, f"Timeout {timeout}s"
    except Exception as e:
        return False, str(e)


def _q(s: str) -> str:
    """Escapa una cadena para incrustarla en un literal AppleScript."""
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


@tool(
    name='mac_control',
    description="Controla macOS y apps nativas (gratis, AppleScript). USAR para: crear/listar Notas y Recordatorios, enviar iMessage, mostrar archivos en Finder, screenshot, modo oscuro, WiFi, fondo de pantalla, abrir/leer pestaña del navegador, vaciar papelera. Ej: 'creá una nota', 'recordame X', 'sacá un screenshot', 'poné modo oscuro'. Para algo de macOS que NINGUNA acción cubre: action=run_script con AppleScript propio (escape hatch).",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'permissions (configura los permisos de macOS) | '
                                              'check_permissions | notes_add | notes_list | '
                                              'reminder_add | reminders_list | message_send | '
                                              'finder_reveal | finder_new_folder | empty_trash | '
                                              'screenshot | dark_mode | wifi | bluetooth | wallpaper | '
                                              'brightness | browser_open | browser_tab | run_script'},
                    'script': {'type': 'STRING',
                               'description': 'run_script: AppleScript a ejecutar tal cual (casos que las acciones no cubren). Devuelve el resultado.'},
                    'deep': {'type': 'BOOLEAN',
                             'description': 'permissions: true = también dispara prompts de '
                                            'Notas/Recordatorios/Mensajes/Chrome (las abre).'},
                    'title': {'type': 'STRING', 'description': 'Título (notes_add / reminder_add)'},
                    'text': {'type': 'STRING',
                             'description': 'Cuerpo del texto / mensaje / recordatorio'},
                    'body': {'type': 'STRING', 'description': 'Cuerpo de la nota'},
                    'to': {'type': 'STRING',
                           'description': 'message_send: destinatario (número o nombre)'},
                    'when': {'type': 'STRING',
                             'description': "reminder_add: fecha/hora ej '2026-05-30 09:00'"},
                    'path': {'type': 'STRING',
                             'description': 'Ruta (finder_reveal, finder_new_folder, screenshot, '
                                            'wallpaper)'},
                    'url': {'type': 'STRING', 'description': 'browser_open: URL a abrir'},
                    'state': {'type': 'STRING',
                              'description': 'on | off | toggle (dark_mode, wifi, bluetooth)'},
                    'level': {'type': 'INTEGER', 'description': 'brightness: 0-100'},
                    'mode': {'type': 'STRING', 'description': 'screenshot: full | window | selection'},
                    'limit': {'type': 'INTEGER', 'description': 'notes_list: cuántas listar'}},
     'required': ['action']},
)
def mac_control(parameters: dict, player=None) -> str:
    if not IS_MAC:
        return "mac_control solo funciona en macOS."
    action = (parameters.get("action") or "").lower().strip()

    # ── Escape hatch: AppleScript arbitrario (lo único que ofrecía osascript-dxt) ──
    if action in ("run_script", "applescript", "osascript"):
        script = (parameters.get("script") or parameters.get("text") or "").strip()
        if not script:
            return "Pasame el AppleScript a ejecutar en 'script'."
        ok, out = _osa(script, timeout=30)
        if ok:
            return out or "✓ Script ejecutado (sin salida)."
        return f"El script falló: {out[:200]}"

    # ── Permisos del sistema ──
    if action in ("permissions", "request_permissions", "setup_permissions"):
        from core.permissions import request_all
        deep = bool(parameters.get("deep"))
        return request_all(player=player, deep=deep)
    if action == "check_permissions":
        from core.permissions import status_report
        return status_report()

    # ── Notas ──
    if action == "notes_add":
        title = _q(parameters.get("title") or "Nota de JARVIS")
        body = _q(parameters.get("body") or parameters.get("text") or "")
        ok, out = _osa(
            f'tell application "Notes" to make new note at folder "Notes" '
            f'with properties {{name:"{title}", body:"{title}<br>{body}"}}')
        return "✓ Nota creada." if ok else f"✗ {out}"

    if action == "notes_list":
        n = int(parameters.get("limit") or 10)
        ok, out = _osa(
            'set output to ""\n'
            'tell application "Notes"\n'
            f'  repeat with i from 1 to (count of notes)\n'
            f'    if i > {n} then exit repeat\n'
            '    set output to output & (name of note i) & "\n"\n'
            '  end repeat\n'
            'end tell\n'
            'return output')
        return f"Notas:\n{out}" if ok else f"✗ {out}"

    # ── Recordatorios ──
    if action == "reminder_add":
        text = _q(parameters.get("text") or parameters.get("title") or "Recordatorio")
        when = parameters.get("when")  # ISO opcional, ej "2026-05-30 09:00"
        props = f'name:"{text}"'
        if when:
            props += f', due date:(date "{_q(when)}")'
        ok, out = _osa(f'tell application "Reminders" to make new reminder with properties {{{props}}}')
        return "✓ Recordatorio creado." if ok else f"✗ {out}"

    if action == "reminders_list":
        ok, out = _osa(
            'set output to ""\n'
            'tell application "Reminders"\n'
            '  repeat with r in (reminders whose completed is false)\n'
            '    set output to output & (name of r) & "\n"\n'
            '  end repeat\n'
            'end tell\n'
            'return output')
        return f"Pendientes:\n{out or '(ninguno)'}" if ok else f"✗ {out}"

    # ── Mensajes (iMessage) ──
    if action == "message_send":
        to = _q(parameters.get("to") or parameters.get("contact") or "")
        msg = _q(parameters.get("text") or parameters.get("message") or "")
        if not to or not msg:
            return "Error: faltan 'to' y 'text'."
        ok, out = _osa(
            'tell application "Messages"\n'
            '  set svc to 1st service whose service type = iMessage\n'
            f'  set buddy to buddy "{to}" of svc\n'
            f'  send "{msg}" to buddy\n'
            'end tell')
        return f"✓ Mensaje enviado a {parameters.get('to')}." if ok else f"✗ {out}"

    # ── Finder ──
    if action == "finder_reveal":
        path = _q(parameters.get("path") or "")
        if not path:
            return "Error: falta 'path'."
        ok, out = _osa(f'tell application "Finder" to reveal (POSIX file "{path}") \nactivate application "Finder"')
        return "✓ Mostrado en Finder." if ok else f"✗ {out}"

    if action == "finder_new_folder":
        path = parameters.get("path") or ""
        if not path:
            return "Error: falta 'path' (ruta de la carpeta nueva)."
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return f"✓ Carpeta creada: {path}"
        except Exception as e:
            return f"✗ {e}"

    if action == "empty_trash":
        ok, out = _osa('tell application "Finder" to empty trash')
        return "✓ Papelera vaciada." if ok else f"✗ {out}"

    # ── Captura de pantalla ──
    if action == "screenshot":
        dest = parameters.get("path") or str(Path.home() / "Desktop" / "jarvis_screenshot.png")
        mode = (parameters.get("mode") or "full").lower()  # full | window | selection
        flag = {"window": "-w", "selection": "-s"}.get(mode, "")
        args = ["screencapture"]
        if flag:
            args.append(flag)
        args.append(dest)
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=60)
            if Path(dest).exists():
                return f"✓ Captura guardada en {dest}"
            err = (r.stderr or "").strip()
            if "could not create image" in err.lower() or not err:
                return ("✗ Falta permiso de Grabación de pantalla. Activalo en "
                        "Ajustes del Sistema → Privacidad y seguridad → Grabación de pantalla, "
                        "marcá la app que ejecuta JARVIS (Terminal/Python) y reiniciá JARVIS.")
            return f"✗ {err}"
        except Exception as e:
            return f"✗ {e}"

    # ── Modo oscuro ──
    if action == "dark_mode":
        state = (parameters.get("state") or "toggle").lower()
        if state == "toggle":
            expr = "not dark mode"
        else:
            expr = "true" if state in ("on", "true", "1", "dark") else "false"
        ok, out = _osa(
            f'tell application "System Events" to tell appearance preferences to set dark mode to {expr}')
        return "✓ Modo oscuro cambiado." if ok else f"✗ {out}"

    # ── WiFi / Bluetooth ──
    if action == "wifi":
        on = (parameters.get("state") or "on").lower() in ("on", "true", "1")
        ok, out = _osa(f'do shell script "networksetup -setairportpower en0 {"on" if on else "off"}"')
        return f"✓ WiFi {'encendido' if on else 'apagado'}." if ok else f"✗ {out}"

    if action == "bluetooth":
        on = (parameters.get("state") or "on").lower() in ("on", "true", "1")
        # blueutil no siempre está; usamos toggle por menú si falla
        ok, out = _osa(
            f'do shell script "blueutil --power {1 if on else 0}"')
        if ok:
            return f"✓ Bluetooth {'encendido' if on else 'apagado'}."
        return "⚠️ Necesito 'blueutil' (brew install blueutil) para controlar Bluetooth por CLI."

    # ── No Molestar / Focus ──
    if action == "dnd":
        on = (parameters.get("state") or "on").lower() in ("on", "true", "1")
        # macOS moderno: atajo de Focus. Usamos la app Shortcuts si existe un atajo,
        # si no, informamos. Fallback: menú de Centro de Control no es scripteable fácil.
        return ("⚠️ En macOS moderno el No Molestar del sistema no es scripteable directo. "
                "Usá el DND interno de JARVIS (tool 'notifications' action=dnd_on) que silencia "
                "tus alertas de WhatsApp/iMessage/Gmail.")

    # ── Fondo de pantalla ──
    if action == "wallpaper":
        path = _q(parameters.get("path") or "")
        if not path:
            return "Error: falta 'path' (imagen)."
        ok, out = _osa(
            f'tell application "System Events" to set picture of every desktop to (POSIX file "{path}")')
        return "✓ Fondo cambiado." if ok else f"✗ {out}"

    # ── Brillo ──
    if action == "brightness":
        try:
            level = max(0, min(100, int(parameters.get("level", 50)))) / 100.0
        except Exception:
            return "Error: 'level' debe ser 0-100."
        # Requiere 'brightness' CLI o usamos teclas. Intentamos vía CLI.
        ok, out = _osa(f'do shell script "brightness {level}"')
        if ok:
            return f"✓ Brillo a {int(level*100)}%."
        return "⚠️ Necesito 'brightness' (brew install brightness) para ajustar el brillo por CLI."

    # ── Navegador ──
    if action == "browser_open":
        url = parameters.get("url") or ""
        if not url:
            return "Error: falta 'url'."
        if not url.startswith("http"):
            url = "https://" + url
        ok, out = _osa(f'open location "{_q(url)}"')
        return f"✓ Abriendo {url}" if ok else f"✗ {out}"

    if action == "browser_tab":
        # Lee URL+título de la pestaña activa (Chrome o Safari, el que esté adelante)
        for app, get in (("Google Chrome", "URL of active tab of front window"),
                         ("Safari", "URL of front document")):
            ok, out = _osa(f'tell application "{app}" to return {get}')
            if ok and out:
                return f"{app}: {out}"
        return "No hay Chrome ni Safari con una pestaña abierta."

    return (f"Acción '{action}' no reconocida. Opciones: permissions, check_permissions, notes_add, "
            "notes_list, reminder_add, reminders_list, message_send, finder_reveal, finder_new_folder, "
            "empty_trash, screenshot, dark_mode, wifi, bluetooth, wallpaper, brightness, browser_open, browser_tab.")
