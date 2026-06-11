# -*- coding: utf-8 -*-
"""
set_timezone.py — Cambiar la zona horaria por voz ("cambiá la zona horaria a México").

Resuelve país/ciudad en español → nombre IANA, lo guarda en config/api_keys.json
(key `timezone`) y lo aplica en vivo. Afecta el saludo (buenos días/tardes/noches),
recordatorios y el scheduler.
"""
from __future__ import annotations
import unicodedata

from core.registry import tool


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


# Alias en español/inglés → nombre IANA.
_TZ_ALIASES = {
    "colombia": "America/Bogota", "bogota": "America/Bogota",
    "mexico": "America/Mexico_City", "cdmx": "America/Mexico_City", "ciudad de mexico": "America/Mexico_City",
    "peru": "America/Lima", "lima": "America/Lima",
    "argentina": "America/Argentina/Buenos_Aires", "buenos aires": "America/Argentina/Buenos_Aires",
    "chile": "America/Santiago", "santiago": "America/Santiago",
    "venezuela": "America/Caracas", "caracas": "America/Caracas",
    "brasil": "America/Sao_Paulo", "brazil": "America/Sao_Paulo", "sao paulo": "America/Sao_Paulo",
    "ecuador": "America/Guayaquil", "quito": "America/Guayaquil", "guayaquil": "America/Guayaquil",
    "bolivia": "America/La_Paz", "la paz": "America/La_Paz",
    "uruguay": "America/Montevideo", "montevideo": "America/Montevideo",
    "paraguay": "America/Asuncion", "asuncion": "America/Asuncion",
    "panama": "America/Panama",
    "costa rica": "America/Costa_Rica",
    "guatemala": "America/Guatemala", "el salvador": "America/El_Salvador", "honduras": "America/Tegucigalpa",
    "nicaragua": "America/Managua",
    "republica dominicana": "America/Santo_Domingo", "dominicana": "America/Santo_Domingo", "santo domingo": "America/Santo_Domingo",
    "puerto rico": "America/Puerto_Rico",
    "estados unidos": "America/New_York", "eeuu": "America/New_York", "usa": "America/New_York",
    "nueva york": "America/New_York", "new york": "America/New_York", "miami": "America/New_York",
    "chicago": "America/Chicago", "texas": "America/Chicago",
    "denver": "America/Denver",
    "los angeles": "America/Los_Angeles", "california": "America/Los_Angeles", "san francisco": "America/Los_Angeles",
    "espana": "Europe/Madrid", "madrid": "Europe/Madrid", "spain": "Europe/Madrid", "barcelona": "Europe/Madrid",
    "reino unido": "Europe/London", "londres": "Europe/London", "london": "Europe/London", "uk": "Europe/London",
    "francia": "Europe/Paris", "paris": "Europe/Paris",
    "alemania": "Europe/Berlin", "berlin": "Europe/Berlin",
    "italia": "Europe/Rome", "roma": "Europe/Rome",
    "utc": "UTC", "gmt": "UTC",
}


def _resolve(query: str) -> str:
    q = _norm(query)
    if not q:
        return ""
    # 1) alias exacto / contenido
    for k, v in _TZ_ALIASES.items():
        if q == _norm(k):
            return v
    for k, v in _TZ_ALIASES.items():
        if _norm(k) in q:
            return v
    # 2) nombre IANA crudo o por ciudad
    try:
        from zoneinfo import available_timezones
        tzs = available_timezones()
        for t in tzs:
            if q == t.lower():
                return t
        for t in tzs:                                  # ciudad dentro del nombre IANA
            if q == t.split("/")[-1].lower().replace("_", " "):
                return t
    except Exception:
        pass
    return ""


@tool(
    name="set_timezone",
    description="Cambia la zona horaria de JARVIS por voz. USAR cuando el usuario diga 'cambiá la zona horaria a X', 'poné la hora de México', 'usá el horario de Buenos Aires/España', etc. Acepta país o ciudad. Afecta el saludo (buenos días/tardes/noches), recordatorios y scheduler. Se aplica en vivo y se guarda.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "place": {"type": "STRING", "description": "País o ciudad de la zona horaria (ej: 'México', 'Buenos Aires', 'España', 'Nueva York') o un nombre IANA (America/Bogota)."}
        },
        "required": ["place"],
    },
    category="system",
)
def set_timezone(parameters: dict, player=None) -> str:
    q = (parameters.get("place") or parameters.get("timezone")
         or parameters.get("query") or parameters.get("location") or "").strip()
    if not q:
        return "¿A qué zona horaria? Decime un país o ciudad (ej: México, Buenos Aires, España)."
    tz = _resolve(q)
    if not tz:
        return (f"No reconocí la zona horaria de '{q}'. Probá con un país o ciudad conocida "
                "(México, Buenos Aires, España, Nueva York…) o el nombre IANA exacto.")
    try:
        from memory.config_manager import set_setting
        set_setting("timezone", tz)
    except Exception as e:
        return f"No pude guardar la zona horaria: {str(e)[:80]}"
    # Aplicar en vivo (clock + contexto de la próxima reconexión).
    try:
        import main
        main._load_tz()
    except Exception:
        pass
    try:
        import ui_widgets
        from zoneinfo import ZoneInfo
        ui_widgets._BA_TZ = ZoneInfo(tz)
    except Exception:
        pass
    return f"✓ Zona horaria cambiada a {tz}. Ya queda activa."
