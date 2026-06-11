"""
scheduler.py — Tareas programadas recurrentes con runner en background.

Persistencia en config/scheduler_tasks.json.
Frecuencias soportadas: daily, weekly, interval, once.
Acciones soportadas: notify, file_controller, browser_control, custom_script, backup.
"""
from __future__ import annotations
import json
import time
import uuid
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent
TASKS_PATH = BASE_DIR / "config" / "scheduler_tasks.json"

_runner_thread: threading.Thread | None = None
_runner_player = None
_runner_speak = None


# ── Persistencia ─────────────────────────────────────────────────────────────

def _load_tasks() -> list:
    if not TASKS_PATH.exists():
        return []
    try:
        return json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_tasks(tasks: list) -> None:
    TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASKS_PATH.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Cálculo de próxima ejecución ─────────────────────────────────────────────

def _next_run(task: dict, after: datetime | None = None) -> datetime | None:
    """Calcula el próximo datetime de ejecución para una task."""
    after = after or datetime.now()
    freq = task.get("frequency", "daily")
    hour = int(task.get("hour", 0))
    minute = int(task.get("minute", 0))

    if freq == "interval":
        mins = int(task.get("interval_minutes", 60))
        last_run = task.get("last_run")
        if last_run:
            try:
                base = datetime.fromisoformat(last_run)
            except Exception:
                base = after
        else:
            base = after
        return base + timedelta(minutes=mins)

    if freq == "once":
        run_at = task.get("run_at")
        if not run_at:
            return None
        try:
            dt = datetime.fromisoformat(run_at)
            return dt if dt > after else None
        except Exception:
            return None

    candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= after:
        candidate += timedelta(days=1)

    if freq == "weekly":
        weekday_name = (task.get("weekday") or "").lower()
        weekdays = {"monday": 0, "lunes": 0, "tuesday": 1, "martes": 1,
                    "wednesday": 2, "miercoles": 2, "miércoles": 2,
                    "thursday": 3, "jueves": 3, "friday": 4, "viernes": 4,
                    "saturday": 5, "sabado": 5, "sábado": 5,
                    "sunday": 6, "domingo": 6}
        target_wd = weekdays.get(weekday_name)
        if target_wd is None:
            return candidate
        delta = (target_wd - candidate.weekday()) % 7
        return candidate + timedelta(days=delta)

    return candidate


# ── Ejecución de tasks ───────────────────────────────────────────────────────

def _run_task_action(task: dict) -> str:
    """Ejecuta la acción de una task. Devuelve mensaje de resultado."""
    action_type = task.get("task_action", "notify")
    params = task.get("task_parameters", {}) or {}

    try:
        if action_type == "notify":
            from core.platform_utils import notify
            notify(f"JARVIS - {task.get('name', 'Tarea')}", params.get("message", "Recordatorio."))
            return "Notificación enviada."

        if action_type == "reminder":
            # Recordatorio del usuario: notificación nativa + sonido + anuncio por voz si se puede.
            msg = params.get("message", "Recordatorio.")
            from core.platform_utils import notify, IS_WINDOWS
            if IS_WINDOWS:
                try:
                    import winsound
                    winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
                except Exception:
                    pass
            notify("JARVIS — Recordatorio", msg)
            if _runner_speak:
                try:
                    _runner_speak(f"Recordatorio: {msg}")
                except Exception:
                    pass
            return f"⏰ Recordatorio: {msg}"

        if action_type == "file_controller":
            from actions.file_controller import file_controller
            return file_controller(params, player=None)

        if action_type == "browser_control":
            url = params.get("url", "")
            if url:
                import webbrowser
                webbrowser.open(url)
                return f"Abierto {url}."
            return "Sin URL especificada."

        if action_type == "custom_script":
            cmd = params.get("command", "")
            if not cmd:
                return "Sin comando."
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            return f"Script ejecutado (código {r.returncode})."

        if action_type == "backup":
            source = params.get("source", "")
            dest = params.get("destination", "")
            if not source or not dest:
                return "backup requiere source y destination."
            import shutil
            src = Path(source).expanduser().resolve()
            dst = Path(dest).expanduser().resolve()
            dst.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = dst / f"{src.name}_{timestamp}"
            if src.is_dir():
                shutil.copytree(src, backup_path)
            else:
                shutil.copy2(src, backup_path)
            return f"Backup creado en {backup_path}."

        if action_type == "tool_invoke":
            # Permite ejecutar cualquier tool registrada por nombre.
            # params: {"tool": "skill_workshop", "args": {...}}
            tool_name = params.get("tool", "")
            tool_args = params.get("args") or {}
            if not tool_name:
                return "tool_invoke requiere 'tool' en params."
            try:
                from core.tool_resolver import invoke_tool
                return invoke_tool(tool_name, tool_args)[:300]
            except Exception as e:
                return f"tool_invoke error: {e}"

        return f"Acción '{action_type}' no soportada."

    except Exception as e:
        return f"Error ejecutando task: {e}"


def _runner_loop():
    """Loop principal del scheduler — corre en thread daemon."""
    print("[Scheduler] 🕐 Runner iniciado.")
    while True:
        try:
            tasks = _load_tasks()
            now = datetime.now()
            changed = False

            for task in tasks:
                if not task.get("enabled", True):
                    continue

                next_run_str = task.get("next_run")
                if not next_run_str:
                    nr = _next_run(task, now)
                    if nr:
                        task["next_run"] = nr.isoformat()
                        changed = True
                    continue

                try:
                    next_run = datetime.fromisoformat(next_run_str)
                except Exception:
                    continue

                if now >= next_run:
                    print(f"[Scheduler] ⚡ Ejecutando '{task.get('name')}'")
                    result = _run_task_action(task)
                    task["last_run"] = now.isoformat()
                    task["last_result"] = result[:200]

                    if task.get("frequency") == "once":
                        task["enabled"] = False
                        task["next_run"] = None
                    else:
                        new_next = _next_run(task, now)
                        task["next_run"] = new_next.isoformat() if new_next else None
                    changed = True

                    if _runner_player and hasattr(_runner_player, "write_log"):
                        _runner_player.write_log(f"⏰ Scheduler: {task.get('name')} → {result[:80]}")

            if changed:
                _save_tasks(tasks)

        except Exception as e:
            print(f"[Scheduler] Error en loop: {e}")

        time.sleep(30)  # chequear cada 30 segundos


def start_runner(player=None, speak=None) -> None:
    """Arranca el thread del scheduler. Idempotente."""
    global _runner_thread, _runner_player, _runner_speak
    _runner_player = player
    _runner_speak = speak
    if _runner_thread and _runner_thread.is_alive():
        return
    _runner_thread = threading.Thread(target=_runner_loop, daemon=True, name="scheduler-runner")
    _runner_thread.start()


# ── Tool entry point ─────────────────────────────────────────────────────────

@tool(
    name='scheduler',
    description='Tareas recurrentes: list, create, delete, enable, disable, run_now. Frecuencias: daily, weekly, interval, once.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'list | create | delete | enable | disable | run_now'},
                    'name': {'type': 'STRING', 'description': 'Nombre descriptivo de la tarea'},
                    'frequency': {'type': 'STRING', 'description': 'daily | weekly | interval | once'},
                    'hour': {'type': 'INTEGER', 'description': 'Hora de ejecución (0-23)'},
                    'minute': {'type': 'INTEGER', 'description': 'Minuto de ejecución (0-59)'},
                    'weekday': {'type': 'STRING',
                                'description': 'Día de la semana para frequency=weekly'},
                    'interval_minutes': {'type': 'INTEGER',
                                         'description': 'Intervalo en minutos para frequency=interval'},
                    'task_action': {'type': 'STRING',
                                    'description': 'backup | file_controller | notify | custom_script '
                                                   '| browser_control'},
                    'task_parameters': {'type': 'OBJECT',
                                        'description': 'Parámetros de la tarea (source, destination '
                                                       'para backup, etc.)'},
                    'task_id': {'type': 'STRING',
                                'description': 'ID de la tarea (primeros 6 chars) para '
                                               'delete/enable/disable/run_now'}},
     'required': ['action']},
)
def scheduler(parameters: dict, player=None, speak=None) -> str:
    action = (parameters.get("action") or "list").lower()
    tasks = _load_tasks()

    if action == "list":
        if not tasks:
            return "Sin tareas programadas."
        lines = []
        for t in tasks:
            tid = t.get("id", "")[:6]
            status = "✓" if t.get("enabled", True) else "✗"
            nxt = t.get("next_run", "?")
            if nxt and nxt != "?":
                try:
                    nxt = datetime.fromisoformat(nxt).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
            lines.append(f"[{tid}] {status} {t.get('name')} ({t.get('frequency')}) → {nxt}")
        return "Tareas programadas:\n" + "\n".join(lines)

    if action == "create":
        name = parameters.get("name", "").strip()
        if not name:
            return "Error: 'name' obligatorio."
        new_task = {
            "id": uuid.uuid4().hex,
            "name": name,
            "frequency": parameters.get("frequency", "daily"),
            "hour": parameters.get("hour", 9),
            "minute": parameters.get("minute", 0),
            "weekday": parameters.get("weekday", ""),
            "interval_minutes": parameters.get("interval_minutes", 60),
            "run_at": parameters.get("run_at", ""),
            "task_action": parameters.get("task_action", "notify"),
            "task_parameters": parameters.get("task_parameters", {}),
            "enabled": True,
            "created": datetime.now().isoformat(),
            "last_run": None,
        }
        nr = _next_run(new_task)
        new_task["next_run"] = nr.isoformat() if nr else None
        tasks.append(new_task)
        _save_tasks(tasks)
        nxt_str = nr.strftime("%Y-%m-%d %H:%M") if nr else "?"
        return f"Tarea '{name}' creada [{new_task['id'][:6]}]. Próxima ejecución: {nxt_str}."

    def _find(prefix: str):
        for i, t in enumerate(tasks):
            if t.get("id", "").startswith(prefix):
                return i, t
        return None, None

    tid = parameters.get("task_id", "")

    if action == "delete":
        if not tid:
            return "Error: 'task_id' obligatorio."
        idx, t = _find(tid)
        if t is None:
            return f"No se encontró task con id '{tid}'."
        del tasks[idx]
        _save_tasks(tasks)
        return f"Tarea '{t.get('name')}' eliminada."

    if action == "enable":
        idx, t = _find(tid)
        if t is None:
            return f"No se encontró task '{tid}'."
        t["enabled"] = True
        nr = _next_run(t)
        t["next_run"] = nr.isoformat() if nr else None
        _save_tasks(tasks)
        return f"Tarea '{t.get('name')}' habilitada."

    if action == "disable":
        idx, t = _find(tid)
        if t is None:
            return f"No se encontró task '{tid}'."
        t["enabled"] = False
        _save_tasks(tasks)
        return f"Tarea '{t.get('name')}' deshabilitada."

    if action == "run_now":
        idx, t = _find(tid)
        if t is None:
            return f"No se encontró task '{tid}'."
        result = _run_task_action(t)
        t["last_run"] = datetime.now().isoformat()
        t["last_result"] = result[:200]
        _save_tasks(tasks)
        return f"Ejecutada '{t.get('name')}': {result}"

    return f"Acción '{action}' no soportada."
