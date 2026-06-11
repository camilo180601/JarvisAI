"""
recall.py — Busca en episodios pasados (JSONL sessions).

Usar cuando el usuario pregunte:
  - "¿hicimos esto antes?"
  - "¿qué hicimos ayer?"
  - "¿cuándo abrí Spotify por última vez?"
  - "buscame en el historial..."
"""
from __future__ import annotations
from datetime import datetime, timedelta

from core.episodic import iter_sessions, read_events, session_id_from_path
from core.registry import tool


def _matches(evt: dict, query: str, tool_filter: str) -> bool:
    if tool_filter:
        if evt.get("type") != "tool_call":
            return False
        if evt.get("name", "").lower() != tool_filter.lower():
            return False
    if not query:
        return tool_filter != "" and evt.get("type") == "tool_call"
    q = query.lower()
    # buscar en text, name, args, result
    blob = " ".join([
        str(evt.get("text", "")),
        str(evt.get("name", "")),
        str(evt.get("result", "")),
        " ".join(f"{k}={v}" for k, v in (evt.get("args") or {}).items()),
    ]).lower()
    return q in blob


def _format_event(evt: dict, session_id: str) -> str:
    ts = (evt.get("ts") or "?")[:16]  # YYYY-MM-DDTHH:MM
    t = evt.get("type", "?")
    sid = session_id[:13]
    if t == "user_turn":
        return f"[{ts}] {sid} 👤 {evt.get('text', '')[:120]}"
    if t == "assistant_turn":
        return f"[{ts}] {sid} 🤖 {evt.get('text', '')[:120]}"
    if t == "tool_call":
        name = evt.get("name", "?")
        success = "✓" if evt.get("success") else "✗"
        args_brief = ", ".join(f"{k}={v}" for k, v in (evt.get("args") or {}).items() if v)[:80]
        return f"[{ts}] {sid} 🔧 {success} {name}({args_brief}) → {evt.get('result','')[:60]}"
    return f"[{ts}] {sid} · {t}"


@tool(
    name='recall',
    description="Busca en episodios pasados (sesiones .jsonl). Usar cuando el usuario pregunta '¿hicimos esto antes?', '¿qué hicimos ayer?', '¿cuándo abrí X por última vez?'.",
    parameters={'type': 'OBJECT',
     'properties': {'query': {'type': 'STRING', 'description': 'Texto a buscar en turnos/tool calls'},
                    'tool': {'type': 'STRING', 'description': 'Opcional. Filtrar por nombre de tool'},
                    'days': {'type': 'INTEGER', 'description': 'Días hacia atrás (default 30)'},
                    'limit': {'type': 'INTEGER', 'description': 'Máx resultados (default 15)'}},
     'required': []},
)
def run(parameters: dict, player=None, speak=None) -> str:
    query = (parameters.get("query") or "").strip()
    tool_filter = (parameters.get("tool") or "").strip()
    days = int(parameters.get("days", 30))
    limit = int(parameters.get("limit", 15))

    if not query and not tool_filter:
        return "Error: especificá 'query' (qué buscás) o 'tool' (filtrar por tool)."

    cutoff = datetime.now() - timedelta(days=days)
    matches = []
    sessions_scanned = 0

    for sess_path in iter_sessions(reverse=True):
        # filtrar por fecha del filename si es posible
        try:
            ts_str = sess_path.stem.split("_")[0] + sess_path.stem.split("_")[1]
            session_dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
            if session_dt < cutoff:
                continue
        except Exception:
            pass

        sessions_scanned += 1
        sid = session_id_from_path(sess_path)
        for evt in read_events(sess_path):
            if _matches(evt, query, tool_filter):
                matches.append((evt, sid))
                if len(matches) >= limit:
                    break
        if len(matches) >= limit:
            break

    if not matches:
        return (
            f"Sin coincidencias para "
            f"{'query=' + repr(query) if query else ''}"
            f"{' tool=' + repr(tool_filter) if tool_filter else ''} "
            f"en los últimos {days} días ({sessions_scanned} sesiones revisadas)."
        )

    lines = [_format_event(e, sid) for e, sid in matches]
    return f"Encontradas {len(matches)} coincidencias en {sessions_scanned} sesiones:\n" + "\n".join(lines)
