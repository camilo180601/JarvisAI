# -*- coding: utf-8 -*-
"""
test_reminder.py — Parsing de fecha/hora/delay del reminder (Fase A).

El bug original: el schema declaraba date+time pero la implementación trataba
`time` como delay → "mañana a las 9" = timer de 60s. Estos tests fijan el
comportamiento correcto de compute_target (función pura, sin scheduler ni I/O).
"""
from datetime import datetime

import pytest

from actions.reminder import compute_target, _parse_delay

NOW = datetime(2026, 6, 10, 14, 0, 0)   # miércoles 14:00


# ── delays ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("s,secs", [
    ("30s", 30), ("20m", 1200), ("2h", 7200), ("1h30m", 5400),
    ("en 45 minutos", 2700), ("en 2 horas", 7200), ("10 seg", 10),
    ("15", 900),          # número pelado = minutos
    ("", None), ("mañana", None),
])
def test_parse_delay(s, secs):
    assert _parse_delay(s) == secs


def test_delay_param_takes_priority():
    target, desc = compute_target("", "", "20m", NOW)
    assert (target - NOW).total_seconds() == 1200
    assert "20 minutos" in desc


def test_time_that_looks_like_delay():
    # time="5m" (sin formato HH:MM) → delay, retrocompatible con el uso viejo
    target, _ = compute_target("", "5m", "", NOW)
    assert (target - NOW).total_seconds() == 300


# ── hora absoluta ────────────────────────────────────────────────────────────

def test_time_today_future():
    target, desc = compute_target("", "15:30", "", NOW)
    assert target == NOW.replace(hour=15, minute=30)
    assert "hoy a las 15:30" in desc


def test_time_already_passed_rolls_to_tomorrow():
    target, desc = compute_target("", "09:00", "", NOW)   # 9am ya pasó (son las 14)
    assert target.day == NOW.day + 1 and target.hour == 9
    assert "mañana" in desc


def test_explicit_tomorrow():
    target, desc = compute_target("mañana", "09:00", "", NOW)
    assert target.day == NOW.day + 1 and target.hour == 9


def test_explicit_date():
    target, desc = compute_target("2026-06-15", "10:45", "", NOW)
    assert (target.year, target.month, target.day, target.hour, target.minute) == (2026, 6, 15, 10, 45)
    assert "2026-06-15" in desc


def test_past_date_rejected():
    target, err = compute_target("2026-06-01", "10:00", "", NOW)
    assert target is None and "ya pasó" in err


def test_invalid_inputs():
    t1, e1 = compute_target("", "25:99", "", NOW)
    assert t1 is None
    t2, e2 = compute_target("", "", "", NOW)
    assert t2 is None and "No entendí" in e2
