# -*- coding: utf-8 -*-
"""
test_trading_bot.py — Indicadores y operaciones del bot (sin red ni archivos reales).

Caracteriza SMA/RSI, la lógica de señal de la estrategia 'smart' y la mecánica de
compra/venta sobre un portafolio en memoria (precio mockeado).
"""
import pytest

from actions import trading_bot as tb


# ── Indicadores ──────────────────────────────────────────────────────────────

def test_sma_basic():
    assert tb._sma([1, 2, 3, 4], 2) == 3.5
    assert tb._sma([10, 20, 30], 3) == 20.0
    assert tb._sma([1, 2], 5) is None   # menos datos que la ventana


def test_rsi_all_gains_is_100():
    rising = list(range(1, 30))          # serie estrictamente creciente
    assert tb._rsi(rising, 14) == 100.0


def test_rsi_insufficient_data():
    assert tb._rsi([1, 2, 3], 14) is None


# ── Señal de la estrategia smart ─────────────────────────────────────────────

@pytest.fixture
def patched_indicators(monkeypatch):
    monkeypatch.setattr(tb, "_closes", lambda t, rng="3mo": [1, 2, 3])
    monkeypatch.setattr(tb, "_price", lambda t: 100.0)
    return monkeypatch


def _set(monkeypatch, sma20, sma50, rsi):
    monkeypatch.setattr(tb, "_sma", lambda vals, n: sma20 if n == 20 else sma50)
    monkeypatch.setattr(tb, "_rsi", lambda vals, n=14: rsi)


def test_signal_buy_strong_on_oversold(patched_indicators):
    _set(patched_indicators, 10, 5, 30)      # RSI < 35
    assert tb._signal("SPY")["decision"] == "buy_strong"


def test_signal_buy_on_uptrend(patched_indicators):
    _set(patched_indicators, 10, 5, 50)      # tendencia alcista, RSI sano
    assert tb._signal("SPY")["decision"] == "buy"


def test_signal_take_profit_on_overbought(patched_indicators):
    _set(patched_indicators, 5, 10, 80)      # RSI > 75
    assert tb._signal("SPY")["decision"] == "take_profit"


def test_signal_hold_on_downtrend(patched_indicators):
    _set(patched_indicators, 5, 10, 50)      # bajista, sin señal clara
    assert tb._signal("SPY")["decision"] == "hold"


# ── Compra / venta (portafolio en memoria) ───────────────────────────────────

def _fresh_port():
    p = dict(tb._DEFAULTS)
    p["positions"] = {}
    p["history"] = []
    p["cash"] = 10000.0
    p["start_cash"] = 10000.0
    p["mode"] = "paper"
    return p


def test_buy_adds_position_and_deducts_cash(monkeypatch):
    monkeypatch.setattr(tb, "_price", lambda t: 100.0)
    port = _fresh_port()
    tb._buy(port, "SPY", 300, reason="test")
    assert round(port["positions"]["SPY"]["shares"], 6) == 3.0
    assert round(port["cash"], 2) == 9700.0
    assert port["history"][-1]["action"] == "buy"


def test_buy_rejects_over_cash(monkeypatch):
    monkeypatch.setattr(tb, "_price", lambda t: 100.0)
    port = _fresh_port()
    msg = tb._buy(port, "SPY", 999999)
    assert "No alcanza" in msg
    assert "SPY" not in port["positions"]


def test_sell_all_closes_position(monkeypatch):
    monkeypatch.setattr(tb, "_price", lambda t: 100.0)
    port = _fresh_port()
    tb._buy(port, "SPY", 300)
    tb._sell(port, "SPY", "all")
    assert "SPY" not in port["positions"]
    assert round(port["cash"], 2) == 10000.0   # precio sin cambios → vuelve al inicio


# ── Fase E: stop-loss + watchlist ────────────────────────────────────────────

def test_stop_loss_sells_position(monkeypatch):
    port = _fresh_port()
    port["stop_loss_pct"] = 8.0
    monkeypatch.setattr(tb, "_price", lambda t: 100.0)
    tb._buy(port, "SPY", 1000)                     # avg = 100
    monkeypatch.setattr(tb, "_price", lambda t: 90.0)   # cayó 10% > 8%
    msgs = tb.check_stop_loss(port)
    assert len(msgs) == 1 and "STOP-LOSS" in msgs[0]
    assert "SPY" not in port["positions"]          # vendió todo


def test_stop_loss_respects_threshold(monkeypatch):
    port = _fresh_port()
    port["stop_loss_pct"] = 8.0
    monkeypatch.setattr(tb, "_price", lambda t: 100.0)
    tb._buy(port, "SPY", 1000)
    monkeypatch.setattr(tb, "_price", lambda t: 95.0)   # cayó 5% < 8%
    assert tb.check_stop_loss(port) == []
    assert "SPY" in port["positions"]              # no tocó la posición


def test_stop_loss_disabled(monkeypatch):
    port = _fresh_port()
    port["stop_loss_pct"] = 0
    monkeypatch.setattr(tb, "_price", lambda t: 50.0)
    port["positions"]["SPY"] = {"shares": 10, "cost": 1000}   # avg 100, cayó 50%
    assert tb.check_stop_loss(port) == []


def test_watch_tickers_dedup():
    port = _fresh_port()
    port["ticker"] = "SPY"
    port["watchlist"] = ["AAPL", "spy", "MSFT", "AAPL"]
    assert tb._watch_tickers(port) == ["SPY", "AAPL", "MSFT"]


def test_tick_smart_covers_watchlist(monkeypatch):
    port = _fresh_port()
    port["strategy"] = "smart"
    port["watchlist"] = ["AAPL"]
    monkeypatch.setattr(tb, "_price", lambda t: 100.0)
    monkeypatch.setattr(tb, "_signal", lambda t: {"decision": "hold", "reason": "test", "ind": {"price": 100.0, "rsi": 50}})
    out = tb._tick(port)
    assert "SPY" in out and "AAPL" in out          # analizó ambos
