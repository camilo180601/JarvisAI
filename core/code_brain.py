"""
code_brain.py — Resolución del cerebro para PROGRAMAR, según disponibilidad + prioridad del usuario.

Idea: solo hay que ELEGIR cuando hay varias opciones disponibles a la vez.
- 0 opciones premium configuradas  → Gemini Flash 2.5 (default, siempre disponible).
- 1 sola opción premium             → esa, sin preguntar.
- 2+ opciones premium               → según la PRIORIDAD del usuario (modo 'auto'),
                                       o preguntar (modo 'ask').

La config se guarda en config/api_keys.json (no es secreto):
  code_brain_mode      "ask" | "auto"        (default "ask")
  code_brain_priority  lista de ids ordenada (default DEFAULT_PRIORITY)
"""
from __future__ import annotations

# (id, etiqueta humana). El orden es la PRIORIDAD por defecto (Gemini último = fallback).
BRAINS: list[tuple[str, str]] = [
    ("claude_cli",        "Claude Code CLI (suscripción, sin API key)"),
    ("code_agent:claude", "Agente integrado · Claude (API key)"),
    ("code_agent:gpt",    "Agente integrado · GPT (API key)"),
    ("code_agent:minimax", "Agente integrado · MiniMax (API key)"),
    ("antigravity",       "Antigravity CLI (Google · Gemini 3.5 Flash, suscripción)"),
    ("code_agent:gemini", "Agente integrado · Gemini Flash 2.5 (default)"),
]
DEFAULT_PRIORITY = [bid for bid, _ in BRAINS]
GEMINI_DEFAULT = "code_agent:gemini"   # siempre disponible (Gemini es obligatoria)
LABELS = {bid: lbl for bid, lbl in BRAINS}


def _cfg(key, default=""):
    try:
        from memory.config_manager import cfg
        return cfg(key, default)
    except Exception:
        return default


def availability() -> dict[str, bool]:
    """Qué cerebros de código están realmente disponibles ahora."""
    out: dict[str, bool] = {}
    # CLIs: basta con que el binario esté (el login se valida al usarlo)
    try:
        from actions.claude_code import _claude_bin
        out["claude_cli"] = _claude_bin() is not None
    except Exception:
        out["claude_cli"] = False
    try:
        from actions.antigravity import _agy_bin
        out["antigravity"] = _agy_bin() is not None
    except Exception:
        out["antigravity"] = False
    # code_agent por API: depende de la key del proveedor
    out["code_agent:gemini"] = bool(_cfg("gemini_api_key"))   # obligatoria → casi siempre True
    out["code_agent:claude"] = bool(_cfg("anthropic_api_key"))
    out["code_agent:gpt"] = bool(_cfg("openai_api_key"))
    out["code_agent:minimax"] = bool(_cfg("minimax_api_key"))
    return out


def get_mode() -> str:
    m = (_cfg("code_brain_mode", "ask") or "ask").lower()
    return m if m in ("ask", "auto") else "ask"


def get_priority() -> list[str]:
    """Prioridad guardada, normalizada: ids válidos + completá los que falten en orden default."""
    saved = _cfg("code_brain_priority", None)
    if not isinstance(saved, list):
        saved = []
    prio = [b for b in saved if b in LABELS]
    for b in DEFAULT_PRIORITY:
        if b not in prio:
            prio.append(b)
    return prio


def set_mode(mode: str) -> None:
    from memory.config_manager import set_setting
    set_setting("code_brain_mode", "auto" if (mode or "").lower() == "auto" else "ask")


def set_priority(order: list[str]) -> None:
    from memory.config_manager import set_setting
    clean = [b for b in (order or []) if b in LABELS]
    for b in DEFAULT_PRIORITY:
        if b not in clean:
            clean.append(b)
    set_setting("code_brain_priority", clean)


def invocation(brain_id: str) -> dict:
    """Cómo invocar ese cerebro: tool + parámetros sugeridos (para la voz / el dispatcher)."""
    if brain_id == "claude_cli":
        return {"tool": "claude_code", "params": {"action": "run"}}
    if brain_id == "antigravity":
        return {"tool": "antigravity", "params": {"action": "run"}}
    if brain_id.startswith("code_agent:"):
        return {"tool": "code_agent", "params": {"action": "run", "brain": brain_id.split(":", 1)[1]}}
    return {"tool": "code_agent", "params": {"action": "run", "brain": "gemini"}}


def resolve() -> dict:
    """
    Decide qué hacer al pedir programar. Devuelve:
      {"decision": "use", "brain": <id>, "label":..., "invoke":..., "reason":...}
      {"decision": "ask", "options": [(id,label),...], "reason":...}
    """
    avail = availability()
    prio = get_priority()
    avail_ids = [b for b in prio if avail.get(b)]
    # Gemini default es el piso garantizado
    if GEMINI_DEFAULT not in avail_ids:
        avail_ids.append(GEMINI_DEFAULT)
    premium = [b for b in avail_ids if b != GEMINI_DEFAULT]

    if not premium:
        return {"decision": "use", "brain": GEMINI_DEFAULT, "label": LABELS[GEMINI_DEFAULT],
                "invoke": invocation(GEMINI_DEFAULT),
                "reason": "no hay otros cerebros configurados → Gemini Flash 2.5 por defecto"}
    if len(premium) == 1:
        b = premium[0]
        return {"decision": "use", "brain": b, "label": LABELS[b], "invoke": invocation(b),
                "reason": "es el único cerebro de código disponible"}
    # 2+ premium disponibles
    if get_mode() == "auto":
        b = premium[0]
        return {"decision": "use", "brain": b, "label": LABELS[b], "invoke": invocation(b),
                "reason": "varios disponibles → el primero de tu prioridad (modo automático)"}
    opts = [(b, LABELS[b]) for b in premium] + [(GEMINI_DEFAULT, LABELS[GEMINI_DEFAULT])]
    return {"decision": "ask", "options": opts,
            "reason": "tenés varios cerebros de código → preguntá cuál priorizar"}


def status_human() -> str:
    avail = availability()
    mode = get_mode()
    prio = get_priority()
    lines = [f"Cerebro de código — modo: {'preguntar' if mode == 'ask' else 'automático (por prioridad)'}",
             "Prioridad (de mayor a menor) y disponibilidad:"]
    for i, b in enumerate(prio, 1):
        mark = "✓ disponible" if avail.get(b) else "✗ no configurado"
        lines.append(f"  {i}. {LABELS[b]} — {mark}")
    r = resolve()
    if r["decision"] == "use":
        lines.append(f"\nAhora mismo usaría: {r['label']} ({r['reason']}).")
    else:
        lines.append("\nAhora mismo preguntaría entre: " + ", ".join(lbl for _, lbl in r["options"]) + ".")
    return "\n".join(lines)
