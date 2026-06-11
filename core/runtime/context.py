# -*- coding: utf-8 -*-
"""
context.py — ToolContext: interfaz tipada que recibe una tool (Fase 4).

Reemplaza GRADUALMENTE el `(parameters, player=None, speak=None)` suelto por un
objeto con acceso tipado a los params y helpers de UI/voz. Es OPT-IN: una tool que
declare un parámetro `ctx` recibe el ToolContext; las que mantienen la firma vieja
siguen funcionando igual (el dispatcher detecta cuál usar). Cero churn forzado.

    @tool(name="x", ...)
    def x(ctx: ToolContext) -> str:
        color = ctx.s("color")          # str
        n = ctx.i("amount", 0)          # int (coerce desde "50")
        ctx.log("haciendo algo…")       # write_log si hay UI
        return "ok"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ToolContext:
    params: dict = field(default_factory=dict)
    player: Any = None
    speak: Optional[Callable[[str], None]] = None

    # — Acceso a params con tipado/coerción tolerante —
    def get(self, key: str, default=None):
        return self.params.get(key, default)

    def s(self, key: str, default: str = "") -> str:
        v = self.params.get(key, default)
        return default if v is None else str(v).strip()

    def i(self, key: str, default: int = 0) -> int:
        try:
            return int(str(self.params.get(key, default)).strip())
        except (TypeError, ValueError):
            return default

    def f(self, key: str, default: float = 0.0) -> float:
        try:
            return float(str(self.params.get(key, default)).strip())
        except (TypeError, ValueError):
            return default

    def b(self, key: str, default: bool = False) -> bool:
        v = self.params.get(key, default)
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("true", "1", "yes", "si", "sí", "on")

    # — Helpers de UI / voz (no-op si no están disponibles) —
    def log(self, msg: str) -> None:
        p = self.player
        if p is not None and hasattr(p, "write_log"):
            try:
                p.write_log(msg)
            except Exception:
                pass

    def say(self, msg: str) -> None:
        if self.speak:
            try:
                self.speak(msg)
            except Exception:
                pass
