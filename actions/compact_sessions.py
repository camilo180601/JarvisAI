"""
compact_sessions.py — Resume sesiones viejas y archiva las JSONL originales.

Estrategia OpenClaw: sesiones > N días → Gemini las resume → resumen va a
SUMMARIES.md → JSONL original se mueve a archive/ (no se borra por seguridad).

Resultado: el catálogo de "memoria episódica" crece linealmente en summaries,
no en eventos crudos.
"""
from __future__ import annotations
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from core.episodic import SESSIONS_DIR, iter_sessions, read_events, session_id_from_path
from core.registry import tool

SUMMARIES_PATH = SESSIONS_DIR / "SUMMARIES.md"
ARCHIVE_DIR = SESSIONS_DIR / "archive"

_PROMPT = """Eres el archivero de memoria de JARVIS. Recibís el log de una sesión
y devolvés un resumen de 4-8 líneas para el archivo SUMMARIES.md.

REGLAS:
- Una línea por tema/acción concreto. Bullets con "- ".
- Mencioná: qué pidió el usuario, qué tools se usaron, decisiones tomadas, fallos importantes.
- Omití trivia (saludos, "ok", confirmaciones cortas).
- Español. Conciso. Sin markdown headers.
- Si la sesión fue trivial (< 3 eventos significativos), devolvé `(sin actividad relevante)`.

Eventos:
"""


def _summarize_with_gemini(events: list[dict]) -> str:
    """Llama a Gemini para resumir la lista de eventos."""
    try:
        from google import genai
        from google.genai import types
        import json
        from pathlib import Path
        from memory.config_manager import cfg
        api_key = cfg("gemini_api_key", "")
        if not api_key:
            return "(sin API key)"
    except Exception as e:
        return f"(error setup: {e})"

    # Resumir eventos en formato compacto
    lines = []
    for e in events:
        t = e.get("type")
        if t == "user_turn":
            lines.append(f"U: {e.get('text','')[:120]}")
        elif t == "assistant_turn":
            lines.append(f"A: {e.get('text','')[:120]}")
        elif t == "tool_call":
            ok = "✓" if e.get("success") else "✗"
            lines.append(f"T: {ok} {e.get('name')}({list((e.get('args') or {}).keys())}) → {e.get('result','')[:60]}")
    body = "\n".join(lines[:200])  # cap por seguridad

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[types.Content(parts=[
                types.Part(text=_PROMPT),
                types.Part(text=body),
            ])],
            config=types.GenerateContentConfig(max_output_tokens=400),
        )
        return (resp.text or "").strip() or "(sin contenido)"
    except Exception as e:
        return f"(error Gemini: {str(e)[:80]})"


def _append_summary(session_id: str, started: str, summary: str) -> None:
    SUMMARIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    header = f"\n## Session {session_id} — {started}\n"
    SUMMARIES_PATH.touch(exist_ok=True)
    with open(SUMMARIES_PATH, "a", encoding="utf-8") as f:
        f.write(header)
        f.write(summary.strip() + "\n")


@tool(
    name='compact_sessions',
    description='Resume sesiones JSONL viejas con Gemini y las archiva. action=run|stats|list. Por defecto resume sesiones de >7 días.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING', 'description': 'run (default) | stats | list'},
                    'older_than_days': {'type': 'INTEGER',
                                        'description': 'Resumir sesiones más antiguas que N días '
                                                       '(default 7)'},
                    'dry_run': {'type': 'BOOLEAN',
                                'description': 'Si true, no escribe nada (preview)'}},
     'required': []},
)
def run(parameters: dict, player=None, speak=None) -> str:
    """
    Acciones:
      action=run (default): resume sesiones >= older_than_days (default 7)
      action=stats: cuenta sesiones, summaries y archivo
      action=list: lista sesiones sin archivar
    """
    action = (parameters.get("action") or "run").lower()
    older_than_days = int(parameters.get("older_than_days", 7))
    dry_run = bool(parameters.get("dry_run", False))

    if action == "stats":
        sessions = list(iter_sessions(reverse=False))
        summaries_exists = SUMMARIES_PATH.exists()
        archived = len(list(ARCHIVE_DIR.glob("*.jsonl"))) if ARCHIVE_DIR.exists() else 0
        sum_size = SUMMARIES_PATH.stat().st_size if summaries_exists else 0
        return (
            f"Sessions activas: {len(sessions)}\n"
            f"Summaries: {'SI' if summaries_exists else 'NO'} ({sum_size} bytes)\n"
            f"Archivadas: {archived}"
        )

    if action == "list":
        sessions = list(iter_sessions(reverse=True))
        if not sessions:
            return "Sin sesiones activas."
        lines = [f"  {s.name}  ({s.stat().st_size} bytes)" for s in sessions[:20]]
        return f"Sesiones activas ({len(sessions)}):\n" + "\n".join(lines)

    # action == "run"
    cutoff = datetime.now() - timedelta(days=older_than_days)
    processed, summarized, errors = 0, 0, []

    for sess_path in iter_sessions(reverse=False):
        try:
            ts_str = "".join(sess_path.stem.split("_")[:2])
            session_dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
        except Exception:
            continue
        if session_dt > cutoff:
            continue

        processed += 1
        events = list(read_events(sess_path))
        if len(events) < 3:
            # demasiado vacía — solo archivar
            if not dry_run:
                ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
                shutil.move(str(sess_path), str(ARCHIVE_DIR / sess_path.name))
            continue

        sid = session_id_from_path(sess_path)
        started = session_dt.strftime("%Y-%m-%d %H:%M")
        if player:
            player.write_log(f"📚 Resumiendo {sid}...")
        summary = _summarize_with_gemini(events)
        if summary == "(sin actividad relevante)" or summary.startswith("(error"):
            errors.append(f"{sid}: {summary}")
            if not dry_run:
                ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
                shutil.move(str(sess_path), str(ARCHIVE_DIR / sess_path.name))
            continue

        if not dry_run:
            _append_summary(sid, started, summary)
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            shutil.move(str(sess_path), str(ARCHIVE_DIR / sess_path.name))
        summarized += 1

    msg = f"Compactado: {summarized} sesión(es) resumida(s), {processed} procesada(s) totales."
    if errors:
        msg += f"\nErrores en {len(errors)}: " + "; ".join(errors[:3])
    if dry_run:
        msg += " (DRY RUN: nada se escribió)"
    return msg
