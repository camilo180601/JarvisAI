# -*- coding: utf-8 -*-
"""
registry.py — Registro unificado de tools (Fase 0 de la arquitectura escalable).

Objetivo a futuro: que una tool sea autodescriptiva (schema + handler + metadata
juntos) y se autodescubra, eliminando el registro triple (action + handler en main
+ schema en tool_declarations). En la FASE 0 esto CONVIVE con el sistema actual:

  • `Tool` + `ToolRegistry`  → modelo y contenedor.
  • `@tool(...)`             → decorador para tools autodescriptivas (lo usará la Fase 1).
  • `build_from_legacy(...)` → arma un registry que REFLEJA el sistema actual
                               (STANDARD_TOOL_HANDLERS + TOOL_DECLARATIONS), sin cambiarlo.

Nada acá altera el dispatch de `main.py`; es una vista unificada + los cimientos.
Este módulo es PURO: no importa `main` (evita imports circulares).
"""
from __future__ import annotations

import re
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Tool:
    """Una tool unificada: schema (lo que ve Gemini) + handler + metadata."""
    name: str
    description: str
    parameters: dict                       # {"type":"OBJECT","properties":{...},"required":[...]}
    handler: Optional[Callable] = None
    source: str = "legacy"                 # handler | special | dynamic | decorator | external
    category: str = ""
    requires: list = field(default_factory=list)
    # Campos heredados del tuple de STANDARD_TOOL_HANDLERS (compatibilidad):
    extras: list = field(default_factory=list)
    fallback: str = "Done."
    log_prefix: Optional[str] = None

    def declaration(self) -> dict:
        """Formato de declaración que consume el modelo de voz (Gemini)."""
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool, *, override: bool = False) -> Tool:
        if tool.name in self._tools and not override:
            raise ValueError(f"Tool duplicada en el registry: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def declarations(self) -> list[dict]:
        return [t.declaration() for t in self._tools.values()]

    def resolve_handler(self, name: str) -> Optional[Callable]:
        """Callable ejecutable para la tool (handler directo o import dinámico).
        Devuelve None para tools 'special'/'external' (las maneja otro dispatch)."""
        t = self._tools.get(name)
        if not t:
            return None
        if t.handler is not None:
            return t.handler
        if t.source == "dynamic":
            try:
                mod = importlib.import_module(f"actions.{name}")
                return getattr(mod, name, None)
            except Exception:
                return None
        return None

    def by_source(self, source: str) -> list[Tool]:
        return [t for t in self._tools.values() if t.source == source]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# ── Decorador para tools autodescriptivas (Fase 1 en adelante) ───────────────

_GLOBAL = ToolRegistry()


def tool(name: str, description: str, parameters: dict, *,
         category: str = "", requires: list | None = None):
    """Marca una función como tool autodescriptiva y la registra globalmente.

    @tool(name="x", description="...", parameters={...})
    def x(parameters, player=None) -> str: ...
    """
    def deco(fn: Callable) -> Callable:
        _GLOBAL.register(Tool(
            name=name, description=description, parameters=parameters,
            handler=fn, source="decorator", category=category,
            requires=requires or [],
        ))
        return fn
    return deco


def global_registry() -> ToolRegistry:
    """Registry de las tools declaradas con @tool (vacío hasta migrar en Fase 1)."""
    return _GLOBAL


def discover_action_tools(actions_dir: Path | None = None) -> int:
    """Importa todos los módulos actions/*.py para que sus @tool se registren.
    Necesario para las tools lazy-load (dynamic) que main no importa al arrancar.
    Devuelve cuántas tools quedaron registradas vía @tool."""
    import importlib
    d = actions_dir or (ROOT / "actions")
    for f in sorted(d.glob("*.py")):
        if f.stem.startswith("__"):
            continue
        try:
            importlib.import_module(f"actions.{f.stem}")
        except Exception as e:
            print(f"[Registry] no pude importar actions.{f.stem}: {e}")
    return len(_GLOBAL)


def first_party_declarations(base_declarations: list[dict]) -> list[dict]:
    """Une las declaraciones del archivo base (`tool_declarations.py`) con las de
    las tools migradas a `@tool`, sin duplicar (la migrada gana si hay colisión).

    A medida que una tool se migra, su schema desaparece de `base_declarations` y
    aparece acá vía el decorador — la UNIÓN se mantiene constante. Es el único punto
    que `main.py` y los tests deben usar como fuente de verdad de las tools propias.
    """
    out: dict[str, dict] = {d["name"]: d for d in base_declarations}
    for d in _GLOBAL.declarations():
        out[d["name"]] = d
    return list(out.values())


# ── Construcción desde el sistema actual (legacy) ────────────────────────────

def special_dispatch_names(main_path: Path | None = None) -> set[str]:
    """Tools resueltas por ramas `name == "x"` / `name in ("a","b")` en main.py."""
    p = main_path or (ROOT / "main.py")
    try:
        src = p.read_text(encoding="utf-8")
    except Exception:
        return set()
    names = set(re.findall(r'name\s*==\s*"([a-z_]+)"', src))
    for grp in re.findall(r'name\s+in\s*\(([^)]*)\)', src):
        names |= set(re.findall(r'"([a-z_]+)"', grp))
    return names


def _classify(name: str, handlers: dict, special: set[str]):
    """Determina (source, handler, extras, fallback, log_prefix) para una tool."""
    if name in handlers:
        fn, extras, fallback, log_prefix = handlers[name]
        return "handler", fn, list(extras or []), fallback, log_prefix
    if name in special:
        return "special", None, [], "Done.", None
    if (ROOT / "actions" / f"{name}.py").exists():
        return "dynamic", None, [], "Done.", None
    return "external", None, [], "Done.", None   # MCP / skill / desconocida


def build_from_legacy(handlers: dict, declarations: list[dict],
                      special: set[str] | None = None) -> ToolRegistry:
    """Arma un ToolRegistry que refleja el sistema actual, sin modificarlo."""
    reg = ToolRegistry()
    special = special if special is not None else special_dispatch_names()
    for d in declarations:
        name = d.get("name")
        if not name:
            continue
        source, fn, extras, fallback, log_prefix = _classify(name, handlers, special)
        reg.register(Tool(
            name=name,
            description=d.get("description", ""),
            parameters=d.get("parameters", {}),
            handler=fn, source=source, extras=extras,
            fallback=fallback, log_prefix=log_prefix,
        ), override=True)
    return reg


# ── Registry "activo" del proceso (lo setea main al arrancar) ────────────────

_ACTIVE: ToolRegistry | None = None


def set_active_registry(reg: ToolRegistry) -> None:
    global _ACTIVE
    _ACTIVE = reg


def active_registry() -> ToolRegistry | None:
    return _ACTIVE
