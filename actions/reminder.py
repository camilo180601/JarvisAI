# -*- coding: utf-8 -*-
"""
reminder.py — Recordatorios con fecha/hora REAL y persistencia.

Antes: ignoraba `date` y trataba `time` como delay ("recordame mañana a las 9"
terminaba siendo un timer de 60s en un thread que moría al reiniciar). Ahora:
  • date+time se respetan, en la zona horaria CONFIGURADA de JARVIS.
  • delays naturales ("20m", "2h", "en 45 minutos") también funcionan.
  • hora ya pasada y sin fecha → se asume mañana.
  • PERSISTE: delega en el scheduler (config/scheduler_tasks.json, frequency=once),
    así sobrevive reinicios. El runner dispara notificación nativa + sonido.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from core.registry import tool


def _tz_now() -> datetime:
    """Ahora en la zona horaria configurada de JARVIS (config: timezone)."""
    try:
        from memory.config_manager import load_api_keys
        tz_name = (load_api_keys().get("timezone") or "").strip()
        if tz_name:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(tz_name))
    except Exception:
        pass
    return datetime.now()


def _parse_delay(s: str) -> int | None:
    """'30s'/'20m'/'2h'/'1h30m'/'en 45 minutos'/'20' → segundos. None si no es delay."""
    s = (s or "").lower().strip()
    if not s:
        return None
    total = 0
    for amount, unit in re.findall(r"(\d+)\s*(s(?:eg\w*)?|m(?:in\w*)?|h(?:ora\w*)?)", s):
        n = int(amount)
        if unit.startswith("s"):
            total += n
        elif unit.startswith("m"):
            total += n * 60
        else:
            total += n * 3600
    if total:
        return total
    if s.isdigit():            # número pelado → minutos (lo más natural por voz)
        return int(s) * 60
    return None


def compute_target(date_str: str, time_str: str, delay_str: str, now: datetime):
    """Devuelve (datetime objetivo, descripción legible) o (None, error)."""
    date_str = (date_str or "").lower().strip()
    time_str = (time_str or "").strip()
    delay_str = (delay_str or "").strip()

    # 1) delay explícito (param delay, o time que parece delay: "20m", "en 10 minutos")
    secs = _parse_delay(delay_str) or (None if re.fullmatch(r"\d{1,2}:\d{2}", time_str)
                                       else _parse_delay(time_str))
    if secs:
        target = now + timedelta(seconds=secs)
        mins = secs // 60
        desc = f"en {mins} minuto{'s' if mins != 1 else ''}" if secs >= 60 else f"en {secs} segundos"
        return target, desc

    # 2) hora absoluta HH:MM (con fecha opcional)
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", time_str)
    if not m:
        return None, "No entendí cuándo. Decime una hora (ej 15:30) o un plazo (ej '20 minutos')."
    hh, mm = int(m.group(1)), int(m.group(2))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None, f"Hora inválida: {time_str}."

    if date_str in ("", "hoy", "today"):
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:       # ya pasó hoy → mañana
            target += timedelta(days=1)
    elif date_str in ("mañana", "manana", "tomorrow"):
        target = (now + timedelta(days=1)).replace(hour=hh, minute=mm, second=0, microsecond=0)
    else:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            target = now.replace(year=d.year, month=d.month, day=d.day,
                                 hour=hh, minute=mm, second=0, microsecond=0)
        except ValueError:
            return None, f"Fecha inválida: '{date_str}' (usá YYYY-MM-DD, 'hoy' o 'mañana')."
        if target <= now:
            return None, f"Esa fecha/hora ya pasó ({date_str} {time_str})."

    if target.date() == now.date():
        desc = f"hoy a las {target.strftime('%H:%M')}"
    elif target.date() == (now + timedelta(days=1)).date():
        desc = f"mañana a las {target.strftime('%H:%M')}"
    else:
        desc = target.strftime("el %Y-%m-%d a las %H:%M")
    return target, desc


@tool(
    name='reminder',
    description="Recordatorio con notificación nativa (persiste aunque JARVIS se reinicie). Acepta hora exacta (time=HH:MM, date opcional YYYY-MM-DD/'hoy'/'mañana') o un plazo (delay='20m', '2h', '45 minutos').",
    parameters={'type': 'OBJECT',
     'properties': {'date': {'type': 'STRING', 'description': "Fecha: YYYY-MM-DD, 'hoy' o 'mañana' (opcional; default hoy/mañana según la hora)"},
                    'time': {'type': 'STRING', 'description': 'Hora exacta HH:MM (24h), o un plazo si no hay hora (ej \"20m\")'},
                    'delay': {'type': 'STRING', 'description': "Plazo relativo: '30s', '20m', '2h', '45 minutos' (alternativa a date+time)"},
                    'message': {'type': 'STRING', 'description': 'Texto del recordatorio'}},
     'required': ['message']},
)
def reminder(parameters: dict, response=None, player=None) -> str:
    text = (parameters.get("message") or "").strip() or "Recordatorio."
    now = _tz_now()
    target, desc = compute_target(parameters.get("date", ""), parameters.get("time", ""),
                                  parameters.get("delay", ""), now)
    if target is None:
        return desc   # mensaje de error legible

    # Persistir vía scheduler (frequency=once → sobrevive reinicios; corre su runner cada 30s)
    try:
        import uuid
        from actions import scheduler as sch
        tasks = sch._load_tasks()
        tasks.append({
            "id": uuid.uuid4().hex,
            "name": f"Recordatorio: {text[:40]}",
            "frequency": "once",
            # el runner del scheduler compara contra la hora LOCAL del sistema → convertir
            "run_at": target.astimezone().replace(tzinfo=None).isoformat(timespec="seconds"),
            "hour": target.hour, "minute": target.minute,
            "weekday": "", "interval_minutes": 60,
            "task_action": "reminder",
            "task_parameters": {"message": text},
            "enabled": True, "next_run": None,
        })
        sch._save_tasks(tasks)
    except Exception as e:
        return f"No pude guardar el recordatorio: {str(e)[:80]}"

    msg = f"⏰ Listo: te recuerdo '{text}' {desc}."
    if player:
        try:
            player.write_log(msg)
        except Exception:
            pass
    return msg
