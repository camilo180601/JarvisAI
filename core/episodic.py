"""
episodic.py — Logger append-only de episodios JARVIS estilo OpenClaw.

Cada sesión = un archivo JSONL en ~/.jarvis/sessions/<id>.jsonl.
Cada línea = un evento: {ts, type, ...payload}.

Tipos de evento:
  - session_start: {session_id}
  - user_turn:     {text}
  - assistant_turn:{text}
  - tool_call:     {name, args, result, duration_ms, success}
  - note:          {text}   (eventos manuales)
  - session_end:   {}

Append-only, line-buffered, thread-safe.
"""
from __future__ import annotations
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

SESSIONS_DIR = Path.home() / ".jarvis" / "sessions"
MAX_TEXT_LEN = 1000          # truncar textos largos (audio transcripts pueden ser enormes)
MAX_ARG_VALUE_LEN = 200       # truncar valores de args

_MIME_PREFIXES = ("audio/", "image/", "video/")   # nunca loguear blobs binarios


def _truncate_args(args: dict) -> dict:
    """Limpia args para logging: trunca strings largos, omite blobs binarios."""
    if not isinstance(args, dict):
        return {"_raw": str(args)[:MAX_ARG_VALUE_LEN]}
    out = {}
    for k, v in args.items():
        if isinstance(v, str):
            if any(p in v.lower() for p in _MIME_PREFIXES) or len(v) > 10000:
                out[k] = f"<{len(v)} chars>"
            else:
                out[k] = v[:MAX_ARG_VALUE_LEN]
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, (list, dict)):
            s = json.dumps(v, ensure_ascii=False, default=str)
            out[k] = s[:MAX_ARG_VALUE_LEN] + ("..." if len(s) > MAX_ARG_VALUE_LEN else "")
        else:
            out[k] = str(v)[:MAX_ARG_VALUE_LEN]
    return out


class EpisodicLogger:
    """Append-only JSONL logger. Thread-safe. Line-buffered (durable ante crash)."""

    def __init__(self):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_id = f"{ts}_{uuid.uuid4().hex[:6]}"
        self.path = SESSIONS_DIR / f"{self.session_id}.jsonl"
        self._lock = threading.Lock()
        self._fh = open(self.path, "a", encoding="utf-8", buffering=1)  # line-buffered
        self._closed = False
        self.log_event("session_start", session_id=self.session_id)

    def log_event(self, event_type: str, **payload) -> None:
        if self._closed:
            return
        evt = {"ts": datetime.now().isoformat(timespec="seconds"), "type": event_type, **payload}
        try:
            with self._lock:
                self._fh.write(json.dumps(evt, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            print(f"[Episodic] error escribiendo evento: {e}")

    def log_user_turn(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            self.log_event("user_turn", text=text[:MAX_TEXT_LEN])

    def log_assistant_turn(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            self.log_event("assistant_turn", text=text[:MAX_TEXT_LEN])

    def log_tool_call(self, name: str, args: dict, result: str, duration_ms: int, success: bool) -> None:
        self.log_event(
            "tool_call",
            name=name,
            args=_truncate_args(args or {}),
            result=(result or "")[:300],
            duration_ms=int(duration_ms),
            success=bool(success),
        )

    def log_note(self, text: str) -> None:
        self.log_event("note", text=str(text)[:MAX_TEXT_LEN])

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.log_event("session_end")
            with self._lock:
                self._fh.flush()
                self._fh.close()
        except Exception:
            pass
        self._closed = True


# ── Helpers para tools (recall, compact) ─────────────────────────────────────

def iter_sessions(reverse: bool = True):
    """Genera paths a sesiones .jsonl (más recientes primero por default)."""
    if not SESSIONS_DIR.exists():
        return
    files = sorted(SESSIONS_DIR.glob("*.jsonl"), reverse=reverse)
    for fp in files:
        yield fp


def read_events(jsonl_path: Path):
    """Genera eventos parseados de un archivo .jsonl."""
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return


def session_id_from_path(p: Path) -> str:
    return p.stem
