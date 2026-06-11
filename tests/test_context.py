# -*- coding: utf-8 -*-
"""
test_context.py — ToolContext (Fase 4): acceso tipado a params + helpers UI/voz,
y el ruteo opt-in del dispatcher (tools con `ctx` reciben el contexto; las viejas no).
"""
import pytest

from core.runtime.context import ToolContext
from core.runtime import dispatcher as dp


# ── ToolContext: getters tipados ─────────────────────────────────────────────

def test_typed_getters():
    ctx = ToolContext(params={"color": "rojo", "amount": "50", "ratio": "1.5", "on": "sí"})
    assert ctx.s("color") == "rojo"
    assert ctx.i("amount") == 50           # coerce desde string
    assert ctx.f("ratio") == 1.5
    assert ctx.b("on") is True
    assert ctx.i("missing", 7) == 7        # default
    assert ctx.b("missing") is False


def test_get_and_none_handling():
    ctx = ToolContext(params={"x": None})
    assert ctx.s("x", "def") == "def"      # None → default
    assert ctx.get("nope", "d") == "d"


def test_log_and_say_are_noop_without_player():
    ctx = ToolContext(params={})
    ctx.log("hola")   # no debe explotar sin player
    ctx.say("chau")   # no debe explotar sin speak


def test_log_uses_player_write_log():
    logged = []
    class FakePlayer:
        def write_log(self, m): logged.append(m)
    spoken = []
    ctx = ToolContext(params={}, player=FakePlayer(), speak=lambda m: spoken.append(m))
    ctx.log("L"); ctx.say("S")
    assert logged == ["L"] and spoken == ["S"]


# ── Ruteo del dispatcher: ctx vs legacy ──────────────────────────────────────

def test_wants_context_detection():
    def new_tool(ctx): return "x"
    def legacy_tool(parameters, player=None): return "y"
    assert dp.wants_context(new_tool) is True
    assert dp.wants_context(legacy_tool) is False


def test_call_standard_routes_ctx_tool():
    captured = {}
    def ctx_tool(ctx):
        captured["color"] = ctx.s("color")
        captured["is_ctx"] = isinstance(ctx, ToolContext)
        return "CTX-OK"
    handlers = {"t": (ctx_tool, [], "Done.", None)}
    out = dp.call_standard("t", {"color": "azul"}, handlers, player=None, speak=None)
    assert out == "CTX-OK"
    assert captured == {"color": "azul", "is_ctx": True}


def test_call_standard_still_routes_legacy():
    def legacy(parameters, player=None):
        return f"legacy:{parameters.get('k')}"
    handlers = {"t": (legacy, [], "Done.", None)}
    assert dp.call_standard("t", {"k": "v"}, handlers, None, None) == "legacy:v"
