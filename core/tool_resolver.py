"""
tool_resolver.py — Invoca cualquier tool por nombre, fuera de la sesión Gemini Live.

Útil para procesos que necesitan llamar tools de forma síncrona sin la maquinaria
de WebSocket/asyncio (planner, skill_workshop nocturno, scripts CLI).

Resolución por orden:
  1. Skills dinámicas en skills/<name>/ (precedencia más alta)
  2. actions/<name>.py con función `<name>(...)` o `run(...)`
  3. actions/<name>.py con función `<name>_run(...)` o similar
"""
from __future__ import annotations
import importlib
import inspect
from typing import Callable

# Tools especiales que solo tienen sentido dentro de la sesión Live (UI-coupled)
# y no deberían ser invocadas por planners/agents externos.
_LIVE_ONLY_TOOLS = {
    "shutdown_jarvis", "restart_jarvis", "sleep_mode", "jarvis_ui_control",
    "save_memory",  # requiere update_memory en proceso principal
    "agent_task",   # usa la queue del proceso principal
    "skill_teach",  # reentrante problemático
}

# Mapeo manual de tools con entry function != name del módulo
_ENTRY_OVERRIDES = {
    "web_search":        ("actions.web_search",        "web_search"),
    "weather_report":    ("actions.weather_report",    "weather_action"),
    "openrouter_agent":  ("actions.openrouter_agent",  "openrouter_agent"),
    "recall":            ("actions.recall",            "run"),
    "compact_sessions":  ("actions.compact_sessions",  "run"),
    "skill_teach":       ("actions.skill_teach",       "skill_teach"),
}


def _resolve_action(name: str) -> Callable | None:
    """Importa actions/<name>.py y devuelve la función entry."""
    if name in _ENTRY_OVERRIDES:
        mod_name, fn_name = _ENTRY_OVERRIDES[name]
        try:
            module = importlib.import_module(mod_name)
            return getattr(module, fn_name, None)
        except ImportError:
            return None

    try:
        module = importlib.import_module(f"actions.{name}")
    except ImportError:
        return None

    for candidate in (name, "run"):
        fn = getattr(module, candidate, None)
        if callable(fn):
            return fn
    return None


def _resolve_skill(name: str) -> Callable | None:
    """Busca en skills/<name>/skill.py."""
    try:
        from core.skill_loader import discover_skills, load_skill_function
        for m in discover_skills():
            if m["name"] == name and m["available"]:
                return load_skill_function(m)
    except Exception:
        pass
    return None


def invoke_tool(name: str, args: dict | None = None, allow_live_only: bool = False) -> str:
    """
    Invoca una tool por nombre con args. Devuelve resultado como string.

    Si la tool no existe o falla, devuelve un mensaje de error (no raise).
    Si la tool es Live-only y allow_live_only=False, rechaza.
    """
    args = args or {}

    if not allow_live_only and name in _LIVE_ONLY_TOOLS:
        return f"Tool '{name}' solo funciona dentro de la sesión Live."

    fn = _resolve_skill(name) or _resolve_action(name)
    if fn is None:
        return f"Tool '{name}' no encontrada."

    try:
        sig = inspect.signature(fn)
        kwargs = {"parameters": args}
        if "player" in sig.parameters:
            kwargs["player"] = None
        if "speak" in sig.parameters:
            kwargs["speak"] = None
        if "response" in sig.parameters:
            kwargs["response"] = None
        result = fn(**kwargs)
        if result is None:
            return f"Tool '{name}' devolvió None."
        return str(result)
    except Exception as e:
        return f"Error invocando '{name}': {e}"


def list_available_tools() -> list[str]:
    """Lista nombres de tools invocables (skills disponibles + actions detectables)."""
    names: set[str] = set()
    # Skills
    try:
        from core.skill_loader import discover_skills
        for m in discover_skills():
            if m["available"]:
                names.add(m["name"])
    except Exception:
        pass
    # actions/*.py
    from pathlib import Path
    actions_dir = Path(__file__).resolve().parent.parent / "actions"
    if actions_dir.exists():
        for p in actions_dir.glob("*.py"):
            if p.stem.startswith("_") or p.stem == "__init__":
                continue
            names.add(p.stem)
    # Quitar live-only
    return sorted(names - _LIVE_ONLY_TOOLS)
