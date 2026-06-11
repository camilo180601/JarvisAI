# -*- coding: utf-8 -*-
"""
dispatcher.py — Ejecución de tools "normales" (Fase 2): standard / skill / dinámica.

Lógica PURA y SÍNCRONA extraída de JarvisLive._execute_tool, para poder testearla.
Cada función recibe el contexto (player, speak) como parámetros y devuelve el string
resultado — sin async, sin estado de sesión, sin Qt. El wrapping async (run_in_executor),
las tools especiales (shutdown/restart/save_memory/…) y los side-effects de UI siguen
viviendo en _execute_tool.

Las 3 funciones replican EXACTAMENTE el comportamiento previo (mismos kwargs, mismos
strings de fallback), para no cambiar nada observable.
"""
from __future__ import annotations

import inspect
import importlib
from typing import Callable, Optional


def standard_kwargs(extras: list, args: dict, player, speak: Callable) -> dict:
    """Arma los kwargs para un handler de STANDARD_TOOL_HANDLERS según sus 'extras'."""
    kwargs = {"parameters": args, "player": player}
    if "response" in extras:
        kwargs["response"] = None
    if "speak" in extras:
        kwargs["speak"] = speak
    return kwargs


def sig_kwargs(fn: Callable, args: dict, player, speak: Callable) -> dict:
    """Arma kwargs para skills/dinámicas: 'speak' solo si la firma lo acepta."""
    kwargs = {"parameters": args, "player": player}
    try:
        if "speak" in inspect.signature(fn).parameters:
            kwargs["speak"] = speak
    except (TypeError, ValueError):
        pass
    return kwargs


def wants_context(fn: Callable) -> bool:
    """True si la tool usa la firma nueva (recibe `ctx`/`context` — Fase 4)."""
    try:
        params = inspect.signature(fn).parameters
        return "ctx" in params or "context" in params
    except (TypeError, ValueError):
        return False


def _invoke(fn: Callable, args: dict, player, speak: Callable, legacy_kwargs: dict):
    """Llama a la tool con ToolContext si lo pide, o con los kwargs legacy."""
    if wants_context(fn):
        from core.runtime.context import ToolContext
        return fn(ToolContext(params=args, player=player, speak=speak))
    return fn(**legacy_kwargs)


def call_standard(name: str, args: dict, handlers: dict, player, speak: Callable) -> str:
    """Ejecuta una tool de STANDARD_TOOL_HANDLERS. Devuelve el resultado (o el fallback)."""
    fn, extras, fallback, _log_prefix = handlers[name]
    if fn is None:
        return f"Módulo '{name}' no disponible (no instalado/no importado)."
    r = _invoke(fn, args, player, speak, standard_kwargs(extras, args, player, speak))
    return r or fallback


def call_skill(name: str, args: dict, skill_dispatch: dict, player, speak: Callable) -> str:
    """Ejecuta una skill cargada desde skills/<name>/skill.py."""
    fn = skill_dispatch[name]
    r = _invoke(fn, args, player, speak, sig_kwargs(fn, args, player, speak))
    return r or f"Skill '{name}' ejecutada."


def call_dynamic(name: str, args: dict, player, speak: Callable) -> str:
    """Fallback: importa actions/<name>.py y ejecuta su función <name>."""
    try:
        module = importlib.import_module(f"actions.{name}")
        func = getattr(module, name)
        r = _invoke(func, args, player, speak, sig_kwargs(func, args, player, speak))
        return r or f"Herramienta {name} ejecutada."
    except Exception as dyn_e:
        return f"Unknown tool: {name}. (Dynamic load failed: {dyn_e})"


def is_error_result(result) -> bool:
    """True si el resultado de una tool indica error (para el log episódico/métricas).
    Replica la heurística previa de _execute_tool."""
    return isinstance(result, str) and ("failed:" in result or result.startswith("Error"))
