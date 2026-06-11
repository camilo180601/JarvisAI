# -*- coding: utf-8 -*-
"""
prompt.py — Carga del system prompt, la memoria markdown y limpieza de transcript.

Extraído de main.py (Fase 2). Lee core/prompt.txt y memory/{SOUL,USER,MEMORY}.md,
y limpia los marcadores de control que mete el modelo de voz en los transcripts.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_PROMPT_PATH = _ROOT / "core" / "prompt.txt"
_MEMORY_DIR = _ROOT / "memory"

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)


def load_system_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )


def load_markdown_memory() -> str:
    """Lee SOUL.md, USER.md, MEMORY.md y los concatena como contexto persistente.
    Patrón inspirado en OpenClaw: memoria como archivos editables a mano."""
    parts = []
    for fname in ("SOUL.md", "USER.md", "MEMORY.md"):
        fp = _MEMORY_DIR / fname
        if not fp.exists():
            continue
        try:
            content = fp.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"# === {fname} ===\n\n{content}")
        except Exception as e:
            print(f"[Memory] Error leyendo {fname}: {e}")
    return "\n\n".join(parts)


def clean_transcript(text: str) -> str:
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


def build_system_instruction(now, tz_name: str, utc_off: str, memory_str: str = "") -> str:
    """System instruction de la sesión Live: contexto de fecha/hora + memoria markdown
    (SOUL/USER/MEMORY) + memoria estructurada + el system prompt, todo unido.
    Lo rearma _build_config en cada reconexión (la hora se refresca)."""
    time_ctx = (
        "[CURRENT DATE & TIME]\n"
        f"Right now it is: {now.strftime('%A, %d %B %Y — %I:%M:%S %p')}\n"
        f"Timezone: {tz_name} (UTC{utc_off})\n"
        f"The current Unix timestamp is: {int(now.timestamp())}\n"
        "Use this information to calculate exact times for reminders, scheduling, "
        "and answering time-related questions.\n\n"
    )
    parts = [time_ctx]
    md = load_markdown_memory()
    if md:
        parts.append(md)
    if memory_str:
        parts.append(memory_str)
    parts.append(load_system_prompt())
    return "\n".join(parts)
