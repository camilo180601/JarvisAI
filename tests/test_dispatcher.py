# -*- coding: utf-8 -*-
"""
test_dispatcher.py — Lógica de ejecución de tools (standard/skill/dinámica).

Caracteriza el comportamiento EXACTO extraído de _execute_tool: cómo arma los kwargs
(extras response/speak, speak por firma), y los strings de fallback de cada camino.
Sin async, sin Qt: funciones puras.
"""
import sys
import types

import pytest

from core.runtime import dispatcher as dp

SPEAK = lambda *a, **k: None   # noqa: E731
PLAYER = object()


# ── standard_kwargs ──────────────────────────────────────────────────────────

def test_standard_kwargs_minimal():
    assert dp.standard_kwargs([], {"a": 1}, PLAYER, SPEAK) == {"parameters": {"a": 1}, "player": PLAYER}


def test_standard_kwargs_response_extra():
    k = dp.standard_kwargs(["response"], {}, PLAYER, SPEAK)
    assert k["response"] is None


def test_standard_kwargs_speak_extra():
    k = dp.standard_kwargs(["speak"], {}, PLAYER, SPEAK)
    assert k["speak"] is SPEAK


# ── call_standard ────────────────────────────────────────────────────────────

def test_call_standard_returns_handler_result():
    captured = {}
    def handler(parameters, player=None):
        captured.update(parameters=parameters, player=player)
        return "RESULTADO"
    handlers = {"x": (handler, [], "Done.", None)}
    assert dp.call_standard("x", {"k": "v"}, handlers, PLAYER, SPEAK) == "RESULTADO"
    assert captured == {"parameters": {"k": "v"}, "player": PLAYER}


def test_call_standard_empty_result_uses_fallback():
    handlers = {"x": (lambda parameters, player=None: "", [], "FALLBACK", None)}
    assert dp.call_standard("x", {}, handlers, PLAYER, SPEAK) == "FALLBACK"


def test_call_standard_none_handler():
    handlers = {"x": (None, [], "Done.", None)}
    out = dp.call_standard("x", {}, handlers, PLAYER, SPEAK)
    assert "no disponible" in out


def test_call_standard_passes_speak_when_extra():
    got = {}
    def handler(parameters, player=None, speak=None):
        got["speak"] = speak
        return "ok"
    handlers = {"x": (handler, ["speak"], "Done.", None)}
    dp.call_standard("x", {}, handlers, PLAYER, SPEAK)
    assert got["speak"] is SPEAK


# ── call_skill ───────────────────────────────────────────────────────────────

def test_call_skill_with_speak_in_sig():
    got = {}
    def skill(parameters, player=None, speak=None):
        got["speak"] = speak
        return "skill-ok"
    assert dp.call_skill("s", {}, {"s": skill}, PLAYER, SPEAK) == "skill-ok"
    assert got["speak"] is SPEAK


def test_call_skill_without_speak_in_sig():
    def skill(parameters, player=None):
        return "no-speak"
    assert dp.call_skill("s", {}, {"s": skill}, PLAYER, SPEAK) == "no-speak"


def test_call_skill_empty_uses_fallback():
    assert dp.call_skill("s", {}, {"s": lambda parameters, player=None: ""}, PLAYER, SPEAK) \
        == "Skill 's' ejecutada."


# ── call_dynamic ─────────────────────────────────────────────────────────────

def test_call_dynamic_success(monkeypatch):
    mod = types.ModuleType("actions.__fake_tool__")
    def __fake_tool__(parameters, player=None):
        return "dyn-ok"
    mod.__fake_tool__ = __fake_tool__
    monkeypatch.setitem(sys.modules, "actions.__fake_tool__", mod)
    assert dp.call_dynamic("__fake_tool__", {}, PLAYER, SPEAK) == "dyn-ok"


def test_call_dynamic_import_failure():
    out = dp.call_dynamic("__no_existe_xyz__", {}, PLAYER, SPEAK)
    assert out.startswith("Unknown tool: __no_existe_xyz__")


def test_call_dynamic_empty_uses_fallback(monkeypatch):
    mod = types.ModuleType("actions.__fake_empty__")
    mod.__fake_empty__ = lambda parameters, player=None: ""
    monkeypatch.setitem(sys.modules, "actions.__fake_empty__", mod)
    assert dp.call_dynamic("__fake_empty__", {}, PLAYER, SPEAK) == "Herramienta __fake_empty__ ejecutada."


# ── is_error_result ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("result,expected", [
    ("Tool 'x' failed: boom", True),
    ("Error: algo", True),
    ("todo ok", False),
    ("", False),
    (None, False),
    (123, False),
    ("✓ Mensaje enviado", False),
])
def test_is_error_result(result, expected):
    assert dp.is_error_result(result) is expected
