# -*- coding: utf-8 -*-
"""test_prompt.py — Armado del system instruction (Fase: refactor de main)."""
from datetime import datetime, timezone, timedelta
from core.runtime import prompt as p


def test_build_system_instruction(monkeypatch):
    monkeypatch.setattr(p, "load_markdown_memory", lambda: "MD-MEM")
    monkeypatch.setattr(p, "load_system_prompt", lambda: "SYS-PROMPT")
    now = datetime(2026, 6, 4, 15, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
    out = p.build_system_instruction(now, "America/Bogota", "-0500", memory_str="STRUCT-MEM")
    assert "[CURRENT DATE & TIME]" in out
    assert "America/Bogota (UTC-0500)" in out
    assert "MD-MEM" in out and "STRUCT-MEM" in out and "SYS-PROMPT" in out
    # orden: tiempo → md → struct → prompt
    assert out.index("[CURRENT") < out.index("MD-MEM") < out.index("STRUCT-MEM") < out.index("SYS-PROMPT")


def test_build_system_instruction_skips_empty(monkeypatch):
    monkeypatch.setattr(p, "load_markdown_memory", lambda: "")
    monkeypatch.setattr(p, "load_system_prompt", lambda: "SYS")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = p.build_system_instruction(now, "UTC", "+0000", memory_str="")
    assert "SYS" in out and "[CURRENT" in out
