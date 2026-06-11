"""
system_control.py — Control del sistema y apps, CROSS-PLATFORM (Mac / Windows / Linux).

Un solo tool con muchas acciones para no inflar la lista de Gemini:
  apps           lista las apps/ventanas abiertas
  switch         trae una app al frente
  quit           cierra una app (amable)
  force_quit     mata una app/proceso
  processes      top de procesos por CPU o RAM
  kill           mata un proceso por nombre o PID
  battery        estado de la batería
  sysinfo        CPU/RAM/disco/uptime/SO
  caffeinate     evitar/permitir que la máquina se duerma (on/off)
  clipboard_get  leer el portapapeles
  clipboard_set  escribir el portapapeles
  volume         volumen del sistema (level 0-100 | up | down | mute | unmute)
  run_shortcut   correr un Atajo de macOS (Shortcuts)
"""
from __future__ import annotations
import os
import sys
import shutil
import subprocess
from core.registry import tool

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

_caffeinate_proc = None  # handle del proceso que evita la suspensión (Mac/Linux)


def _osa(script: str, timeout: int = 20) -> tuple[bool, str]:
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
        return (r.returncode == 0, (r.stdout or r.stderr or "").strip())
    except Exception as e:
        return False, str(e)


# ───────────────────────── apps / ventanas ─────────────────────────

def _list_apps() -> str:
    if IS_MAC:
        ok, out = _osa('tell application "System Events" to get name of '
                       '(processes whose background only is false)')
        if ok:
            names = sorted(set(n.strip() for n in out.split(",") if n.strip()))
            return "Apps abiertas:\n" + "\n".join(f"  • {n}" for n in names)
        return f"Error: {out}"
    if IS_WIN:
        try:
            import pygetwindow as gw
            titles = sorted(set(t for t in gw.getAllTitles() if t.strip()))
            return "Ventanas abiertas:\n" + "\n".join(f"  • {t}" for t in titles[:40])
        except Exception as e:
            return f"Necesito pygetwindow en Windows: {e}"
    # Linux
    if shutil.which("wmctrl"):
        r = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
        return "Ventanas:\n" + "\n".join("  • " + l.split(None, 3)[-1]
                                          for l in r.stdout.splitlines() if l.strip())
    return "En Linux instalá wmctrl (sudo apt install wmctrl) para listar ventanas."


def _switch(app: str) -> str:
    if not app:
        return "Decime qué app traer al frente."
    if IS_MAC:
        ok, out = _osa(f'tell application "{app}" to activate')
        return f"✓ {app} al frente." if ok else f"✗ {out}"
    if IS_WIN:
        try:
            import pygetwindow as gw
            wins = [w for w in gw.getAllWindows() if app.lower() in (w.title or "").lower()]
            if not wins:
                return f"No encontré una ventana de '{app}'."
            wins[0].activate()
            return f"✓ {app} al frente."
        except Exception as e:
            return f"✗ {e}"
    if shutil.which("wmctrl"):
        subprocess.run(["wmctrl", "-a", app])
        return f"✓ {app} al frente."
    return "No puedo cambiar de ventana en este sistema."


def _quit_app(app: str, force: bool = False) -> str:
    if not app:
        return "Decime qué app cerrar."
    if IS_MAC and not force:
        ok, out = _osa(f'tell application "{app}" to quit')
        return f"✓ {app} cerrada." if ok else f"✗ {out}"
    # force o no-mac → matar por nombre con psutil
    return _kill(app)


# ───────────────────────── procesos ─────────────────────────

def _processes(by: str = "cpu", n: int = 8) -> str:
    try:
        import psutil
    except ImportError:
        return "Falta psutil."
    procs = []
    for p in psutil.process_iter(["name", "pid"]):
        try:
            procs.append((p.info["name"] or "?", p.info["pid"],
                          p.cpu_percent(None), p.memory_info().rss / (1024**2)))
        except Exception:
            continue
    psutil.cpu_percent(None)  # primar medición
    import time
    time.sleep(0.3)
    rows = []
    for p in psutil.process_iter(["name", "pid"]):
        try:
            rows.append((p.info["name"] or "?", p.info["pid"], p.cpu_percent(None),
                         p.memory_info().rss / (1024**2)))
        except Exception:
            continue
    key = 3 if by.lower().startswith("ram") or by.lower().startswith("mem") else 2
    rows.sort(key=lambda r: r[key], reverse=True)
    head = "RAM" if key == 3 else "CPU"
    out = [f"Top {n} procesos por {head}:"]
    for name, pid, cpu, mem in rows[:n]:
        out.append(f"  {name[:28]:28} pid={pid:<7} CPU={cpu:4.0f}%  RAM={mem:6.0f}MB")
    return "\n".join(out)


def _kill(target: str) -> str:
    try:
        import psutil
    except ImportError:
        return "Falta psutil."
    if not target:
        return "Decime el nombre o PID a terminar."
    killed = []
    if str(target).isdigit():
        try:
            psutil.Process(int(target)).terminate()
            killed.append(target)
        except Exception as e:
            return f"✗ No pude terminar PID {target}: {e}"
    else:
        for p in psutil.process_iter(["name"]):
            try:
                if target.lower() in (p.info["name"] or "").lower():
                    p.terminate()
                    killed.append(str(p.pid))
            except Exception:
                continue
    return f"✓ Terminados: {len(killed)} proceso(s)." if killed else f"No encontré '{target}'."


# ───────────────────────── info sistema ─────────────────────────

def _battery() -> str:
    try:
        import psutil
        b = psutil.sensors_battery()
        if not b:
            return "Este equipo no reporta batería (¿de escritorio?)."
        est = ""
        if b.secsleft and b.secsleft > 0 and not b.power_plugged:
            est = f" · ~{b.secsleft//3600}h {(b.secsleft%3600)//60}m restantes"
        return f"🔋 {b.percent:.0f}% · {'enchufado' if b.power_plugged else 'en batería'}{est}"
    except Exception as e:
        return f"No pude leer la batería: {e}"


def _sysinfo() -> str:
    try:
        import psutil, platform, time
        cpu = psutil.cpu_percent(interval=0.3)
        vm = psutil.virtual_memory()
        du = psutil.disk_usage("/")
        up = int(time.time() - psutil.boot_time())
        return (f"💻 {platform.system()} {platform.release()}\n"
                f"  CPU: {cpu:.0f}%  ({psutil.cpu_count()} núcleos)\n"
                f"  RAM: {vm.percent:.0f}% ({vm.used/1024**3:.1f}/{vm.total/1024**3:.1f} GB)\n"
                f"  Disco: {du.percent:.0f}% ({du.used/1024**3:.0f}/{du.total/1024**3:.0f} GB)\n"
                f"  Uptime: {up//3600}h {(up%3600)//60}m")
    except Exception as e:
        return f"Error leyendo el sistema: {e}"


def _caffeinate(on: bool) -> str:
    global _caffeinate_proc
    if IS_WIN:
        try:
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ES_DISPLAY_REQUIRED = 0x00000002
            flags = (ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED) if on else ES_CONTINUOUS
            ctypes.windll.kernel32.SetThreadExecutionState(flags)
            return "☕ Suspensión desactivada." if on else "✓ Suspensión permitida de nuevo."
        except Exception as e:
            return f"✗ {e}"
    # Mac / Linux: proceso que mantiene despierto
    if on:
        if _caffeinate_proc and _caffeinate_proc.poll() is None:
            return "☕ Ya estaba evitando la suspensión."
        cmd = ["caffeinate", "-dimsu"] if IS_MAC else \
              (["systemd-inhibit", "--what=idle:sleep", "sleep", "infinity"] if shutil.which("systemd-inhibit") else None)
        if not cmd:
            return "No tengo cómo evitar la suspensión en este sistema."
        _caffeinate_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "☕ Suspensión desactivada (no se va a dormir)."
    else:
        if _caffeinate_proc and _caffeinate_proc.poll() is None:
            _caffeinate_proc.terminate()
            _caffeinate_proc = None
            return "✓ Suspensión permitida de nuevo."
        return "No estaba activado."


# ───────────────────────── portapapeles / volumen / shortcuts ─────────────────────────

def _clip_get() -> str:
    try:
        import pyperclip
        t = pyperclip.paste()
        return f"📋 Portapapeles:\n{t[:1500]}" if t else "El portapapeles está vacío."
    except Exception as e:
        return f"No pude leer el portapapeles: {e}"


def _clip_set(text: str) -> str:
    try:
        import pyperclip
        pyperclip.copy(text or "")
        return "✓ Copiado al portapapeles."
    except Exception as e:
        return f"No pude escribir el portapapeles: {e}"


def _volume(parameters: dict) -> str:
    from core import platform_utils as pu
    sub = (parameters.get("level") if parameters.get("level") is not None
           else parameters.get("mode") or "").__str__().lower()
    if parameters.get("level") is not None:
        ok, msg = pu.set_master_volume(int(parameters["level"]))
    elif sub in ("mute",):
        ok, msg = pu.mute_audio(True)
    elif sub in ("unmute",):
        ok, msg = pu.mute_audio(False)
    elif sub in ("up", "subir", "+"):
        ok, msg = pu.change_volume(+10)
    elif sub in ("down", "bajar", "-"):
        ok, msg = pu.change_volume(-10)
    else:
        return "Decime level (0-100) o up/down/mute/unmute."
    return ("✓ " + msg) if ok else ("✗ " + msg)


def _run_shortcut(name: str) -> str:
    if not name:
        return "Decime el nombre del Atajo."
    if IS_MAC and shutil.which("shortcuts"):
        r = subprocess.run(["shortcuts", "run", name], capture_output=True, text=True)
        return f"✓ Atajo '{name}' ejecutado." if r.returncode == 0 else f"✗ {r.stderr.strip() or 'no encontrado'}"
    return "Los Atajos (Shortcuts) solo están en macOS."


# ───────────────────────── dispatch ─────────────────────────

@tool(
    name='system_control',
    description="Controla el sistema y las apps (Mac/Windows/Linux). USAR para: 'qué apps tengo abiertas', 'pasá a Chrome', 'cerrá Spotify', 'matá el proceso X', 'cuánta batería queda', 'cómo está el CPU/RAM', 'no dejes que se duerma', 'qué tengo copiado', 'copiá esto', 'subí el volumen', 'corré el atajo X'. Acciones: apps, switch, quit, force_quit, processes, kill, battery, sysinfo, caffeinate, clipboard_get, clipboard_set, volume, run_shortcut.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'apps | switch | quit | force_quit | processes | kill | '
                                              'battery | sysinfo | caffeinate | clipboard_get | '
                                              'clipboard_set | volume | run_shortcut'},
                    'app': {'type': 'STRING',
                            'description': 'Nombre de la app (switch/quit/force_quit)'},
                    'target': {'type': 'STRING', 'description': 'kill: nombre de proceso o PID'},
                    'by': {'type': 'STRING', 'description': "processes: 'cpu' (default) o 'ram'"},
                    'state': {'type': 'STRING', 'description': 'caffeinate: on (no dormir) | off'},
                    'text': {'type': 'STRING', 'description': 'clipboard_set: texto a copiar'},
                    'level': {'type': 'INTEGER', 'description': 'volume: 0-100'},
                    'mode': {'type': 'STRING', 'description': 'volume: up | down | mute | unmute'},
                    'shortcut': {'type': 'STRING',
                                 'description': 'run_shortcut: nombre del Atajo de macOS'}},
     'required': ['action']},
)
def system_control(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "").lower().strip()
    app = parameters.get("app") or parameters.get("name") or ""

    if action in ("apps", "list_apps", "windows"):
        return _list_apps()
    if action in ("switch", "focus", "activate"):
        return _switch(app)
    if action == "quit":
        return _quit_app(app, force=False)
    if action in ("force_quit", "kill_app"):
        return _quit_app(app, force=True)
    if action in ("processes", "top"):
        return _processes(parameters.get("by", "cpu"), int(parameters.get("n", 8)))
    if action == "kill":
        return _kill(parameters.get("target") or app)
    if action == "battery":
        return _battery()
    if action in ("sysinfo", "info", "status"):
        return _sysinfo()
    if action in ("caffeinate", "keep_awake", "prevent_sleep"):
        on = (parameters.get("state") or "on").lower() in ("on", "true", "1", "yes")
        return _caffeinate(on)
    if action in ("clipboard_get", "get_clipboard", "read_clipboard"):
        return _clip_get()
    if action in ("clipboard_set", "set_clipboard", "copy"):
        return _clip_set(parameters.get("text", ""))
    if action == "volume":
        return _volume(parameters)
    if action in ("run_shortcut", "shortcut"):
        return _run_shortcut(parameters.get("shortcut") or app)

    return ("Acciones: apps, switch, quit, force_quit, processes, kill, battery, sysinfo, "
            "caffeinate, clipboard_get, clipboard_set, volume, run_shortcut.")
