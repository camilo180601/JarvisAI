from datetime import datetime


def _now():
    """Hora actual en la zona horaria CONFIGURADA de JARVIS (config: timezone),
    o la del sistema si no está configurada / falla."""
    try:
        from memory.config_manager import load_api_keys
        tz_name = (load_api_keys().get("timezone") or "").strip()
        if tz_name:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(tz_name))
    except Exception:
        pass
    return datetime.now()


def _greeting(hour: int) -> str:
    if 5 <= hour < 12:
        return "Buenos días"
    if 12 <= hour < 20:
        return "Buenas tardes"
    return "Buenas noches"   # 20:00–04:59 (noche / madrugada)


def run(parameters: dict, player=None, speak=None) -> str:
    now = _now()
    return f"{_greeting(now.hour)}, son las {now.strftime('%H:%M')}."
