"""
google_calendar.py — Gestión real de Google Calendar via OAuth.

Acciones: list, create, edit, delete.
"""
from __future__ import annotations
import re
from datetime import datetime, timedelta, timezone

from actions.google_auth import get_service, setup_message
from core.registry import tool


def _parse_dt(s: str) -> datetime:
    """Parsea varias variantes de fecha/hora y devuelve datetime con tz local."""
    if not s:
        raise ValueError("Fecha vacía")
    s = s.strip()
    # Probar formatos comunes
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).astimezone()
        except ValueError:
            continue
    # Último recurso: ISO con timezone
    try:
        return datetime.fromisoformat(s).astimezone()
    except Exception:
        raise ValueError(f"No pude parsear fecha: '{s}'")


def _format_event(ev: dict) -> str:
    start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date") or "?"
    summary = ev.get("summary") or "(sin título)"
    loc = ev.get("location", "")
    eid_short = (ev.get("id") or "")[:8]
    base = f"[{eid_short}] {start}  {summary}"
    if loc:
        base += f"  📍 {loc}"
    return base


@tool(
    name='google_calendar',
    description='Calendar: list (próximos N días), create (summary+start), edit/delete (event_id desde list).',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING', 'description': 'list | create | edit | delete'},
                    'summary': {'type': 'STRING', 'description': 'Event title/name'},
                    'start': {'type': 'STRING',
                              'description': 'Start date/time: ISO, YYYY-MM-DD HH:MM, or DD/MM/YYYY '
                                             'HH:MM'},
                    'end': {'type': 'STRING',
                            'description': 'End date/time (optional — defaults to start + 1 hour)'},
                    'description': {'type': 'STRING', 'description': 'Event notes or description'},
                    'location': {'type': 'STRING', 'description': 'Event location'},
                    'event_id': {'type': 'STRING',
                                 'description': 'Event ID (first 8 chars from list) for edit/delete'},
                    'days_ahead': {'type': 'INTEGER',
                                   'description': 'Days to look ahead for list (default: 7)'}},
     'required': ['action']},
)
def google_calendar(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "list").lower()

    try:
        service = get_service("calendar", "v3")
    except FileNotFoundError as e:
        return str(e)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Error de autenticación Google: {e}"

    try:
        if action == "list":
            days = int(parameters.get("days_ahead", 7))
            now = datetime.now(timezone.utc).isoformat()
            then = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
            res = service.events().list(
                calendarId="primary",
                timeMin=now,
                timeMax=then,
                singleEvents=True,
                orderBy="startTime",
                maxResults=20,
            ).execute()
            events = res.get("items", [])
            if not events:
                return f"No hay eventos en los próximos {days} días."
            lines = [_format_event(e) for e in events]
            return f"Próximos {len(events)} eventos:\n" + "\n".join(lines)

        if action == "create":
            summary = (parameters.get("summary") or "").strip()
            start_raw = (parameters.get("start") or "").strip()
            if not summary or not start_raw:
                return "Error: 'summary' y 'start' son obligatorios para crear."
            start_dt = _parse_dt(start_raw)
            end_raw = (parameters.get("end") or "").strip()
            end_dt = _parse_dt(end_raw) if end_raw else (start_dt + timedelta(hours=1))

            body = {
                "summary": summary,
                "start": {"dateTime": start_dt.isoformat()},
                "end": {"dateTime": end_dt.isoformat()},
            }
            if parameters.get("description"):
                body["description"] = parameters["description"]
            if parameters.get("location"):
                body["location"] = parameters["location"]

            ev = service.events().insert(calendarId="primary", body=body).execute()
            return f"Evento creado: '{summary}' el {start_dt.strftime('%Y-%m-%d %H:%M')} (id: {ev['id'][:8]})"

        if action in ("edit", "update"):
            eid = (parameters.get("event_id") or "").strip()
            if not eid:
                return "Error: 'event_id' obligatorio (lo obtenés con action=list)."
            # Buscar evento que matchee por id prefix
            full_id = _resolve_event_id(service, eid)
            if not full_id:
                return f"No se encontró evento con id que empiece en '{eid}'."
            current = service.events().get(calendarId="primary", eventId=full_id).execute()
            for key, body_key in (("summary","summary"), ("description","description"), ("location","location")):
                if parameters.get(key):
                    current[body_key] = parameters[key]
            if parameters.get("start"):
                sdt = _parse_dt(parameters["start"])
                current["start"] = {"dateTime": sdt.isoformat()}
                if not parameters.get("end"):
                    current["end"] = {"dateTime": (sdt + timedelta(hours=1)).isoformat()}
            if parameters.get("end"):
                current["end"] = {"dateTime": _parse_dt(parameters["end"]).isoformat()}
            updated = service.events().update(calendarId="primary", eventId=full_id, body=current).execute()
            return f"Evento actualizado: '{updated.get('summary')}'"

        if action == "delete":
            eid = (parameters.get("event_id") or "").strip()
            if not eid:
                return "Error: 'event_id' obligatorio."
            full_id = _resolve_event_id(service, eid)
            if not full_id:
                return f"No se encontró evento con id que empiece en '{eid}'."
            service.events().delete(calendarId="primary", eventId=full_id).execute()
            return f"Evento eliminado ({eid})."

        return f"Acción '{action}' no soportada. Usa: list, create, edit, delete."

    except Exception as e:
        return f"Error en google_calendar: {e}"


def _resolve_event_id(service, prefix: str) -> str | None:
    """Busca el evento cuyo ID empieza con `prefix` en los próximos 30 días."""
    if len(prefix) >= 20:
        return prefix  # Probablemente ID completo
    now = datetime.now(timezone.utc).isoformat()
    then = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    res = service.events().list(
        calendarId="primary", timeMin=now, timeMax=then,
        singleEvents=True, maxResults=50,
    ).execute()
    for ev in res.get("items", []):
        if ev.get("id", "").startswith(prefix):
            return ev["id"]
    return None
