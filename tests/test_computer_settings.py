# -*- coding: utf-8 -*-
"""
test_computer_settings.py — Caracteriza el parsing de volumen/ventana del action.

Esta lógica estaba DUPLICADA inline en main._execute_tool. La caracterizamos acá
(mockeando platform_utils) antes de borrar la duplicación de main, para garantizar
que el comportamiento queda igual al despacharse como tool normal.
"""
import pytest

from actions import computer_settings as cs


@pytest.fixture
def mocked(monkeypatch):
    calls = {}
    def mk(label):
        def f(*a, **k):
            calls[label] = a or True
            return (True, f"{label}:{a[0] if a else ''}")
        return f
    monkeypatch.setattr(cs, "set_master_volume", mk("set"))
    monkeypatch.setattr(cs, "change_volume", mk("change"))
    monkeypatch.setattr(cs, "mute_audio", mk("mute"))
    monkeypatch.setattr(cs, "minimize_active_window", mk("min"))
    monkeypatch.setattr(cs, "maximize_active_window", mk("max"))
    return calls


def test_volume_numeric_sets_level(mocked):
    out = cs.computer_settings({"action": "volume", "value": "50"})
    assert out == "set:50"
    assert mocked["set"] == (50,)


def test_volume_up(mocked):
    cs.computer_settings({"action": "volume", "value": "subir"})
    assert mocked["change"] == (10,)


def test_volume_down(mocked):
    cs.computer_settings({"action": "volume", "value": "down"})
    assert mocked["change"] == (-10,)


def test_volume_mute(mocked):
    cs.computer_settings({"action": "volume", "value": "silenciar"})
    assert mocked["mute"] == (True,)


def test_volume_unknown(mocked):
    out = cs.computer_settings({"action": "volume", "value": "xyz"})
    assert "no reconocida" in out


def test_minimize(mocked):
    cs.computer_settings({"action": "window_minimize"})
    assert "min" in mocked


def test_maximize(mocked):
    cs.computer_settings({"action": "maximize"})
    assert "max" in mocked


def test_unsupported_action():
    out = cs.computer_settings({"action": "nope"})
    assert "not supported" in out
