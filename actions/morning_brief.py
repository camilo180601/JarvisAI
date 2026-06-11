"""
morning_brief.py — Informe matutino agregado.

Combina saludo + fecha/hora + clima + eventos de Calendar + objetivos activos
en un solo texto que JARVIS lee al iniciar el día.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_PATH = BASE_DIR / "config" / "morning_brief_state.json"


def already_briefed_today() -> bool:
    """¿Ya se generó el brief hoy?"""
    try:
        if not STATE_PATH.exists():
            return False
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        last = data.get("last_brief_date", "")
        return last == datetime.now().strftime("%Y-%m-%d")
    except Exception:
        return False


def mark_briefed() -> None:
    """Registra que ya se hizo el brief hoy."""
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps({"last_brief_date": datetime.now().strftime("%Y-%m-%d")}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _greeting(hour: int) -> str:
    if hour < 12:
        return "Buenos días"
    if hour < 19:
        return "Buenas tardes"
    return "Buenas noches"


def _format_date(dt: datetime) -> str:
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    return f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month-1]}"


def _get_user_name() -> str:
    """Lee el nombre del usuario desde user_profile/memory si existe."""
    try:
        prof_path = BASE_DIR / "config" / "user_profile.json"
        if prof_path.exists():
            data = json.loads(prof_path.read_text(encoding="utf-8"))
            return data.get("name", "")
    except Exception:
        pass
    try:
        mem_path = BASE_DIR / "memory" / "long_term.json"
        if mem_path.exists():
            data = json.loads(mem_path.read_text(encoding="utf-8"))
            return data.get("identity", {}).get("name", {}).get("value", "")
    except Exception:
        pass
    return ""


def _get_weather(city: str) -> str:
    try:
        from actions.weather_report import weather_action
        return weather_action({"city": city}, player=None) or ""
    except Exception:
        return ""


def _get_calendar_events() -> str:
    try:
        from actions.google_calendar import google_calendar
        result = google_calendar({"action": "list", "days_ahead": 1})
        if "No hay eventos" in result or "Error" in result or "Necesito credenciales" in result:
            return ""
        return result
    except Exception:
        return ""


def _get_active_goals() -> str:
    """Lee objetivos activos si existen."""
    try:
        goals_path = BASE_DIR / "config" / "goals.json"
        if not goals_path.exists():
            return ""
        data = json.loads(goals_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return ""
        active = [g for g in data if g.get("status") != "completed"][:3]
        if not active:
            return ""
        lines = [f"  • {g.get('title', '?')} ({g.get('progress', 0)}%)" for g in active]
        return "Objetivos activos:\n" + "\n".join(lines)
    except Exception:
        return ""


def _get_city() -> str:
    """Lee la ciudad preferida del usuario desde config."""
    try:
        from memory.config_manager import load_api_keys
        data = load_api_keys()
        if True:
            tz = data.get("timezone", "")
            if "/" in tz:
                return tz.split("/")[-1].replace("_", " ")
    except Exception:
        pass
    return "Lima"


@tool(
    name='morning_brief',
    description='Informe matutino: saludo, hora, fecha, clima, objetivos, consejo. force=true para forzar repetir.',
    parameters={'type': 'OBJECT',
     'properties': {'force': {'type': 'BOOLEAN',
                              'description': 'Si True, genera el informe aunque ya se haya dado hoy.'}},
     'required': []},
)
def morning_brief(parameters: dict, player=None) -> str:
    """Compone y devuelve el informe matutino."""
    force = parameters.get("force", False) if parameters else False

    if not force and already_briefed_today():
        return "Ya te di el informe hoy. Usa force=true si querés repetirlo."

    now = datetime.now()
    name = _get_user_name()
    saludo = _greeting(now.hour)
    if name:
        saludo += f", {name}"

    parts = [
        f"{saludo}. Hoy es {_format_date(now)}, son las {now.strftime('%H:%M')}.",
    ]

    city = _get_city()
    weather = _get_weather(city)
    if weather:
        parts.append(weather)

    events = _get_calendar_events()
    if events:
        parts.append(events)

    goals = _get_active_goals()
    if goals:
        parts.append(goals)

    brief = "\n\n".join(parts)
    mark_briefed()

    if player:
        player.write_log(f"☀️ Brief matutino generado.")

    return brief
