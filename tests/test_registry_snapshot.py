# -*- coding: utf-8 -*-
"""
test_registry_snapshot.py — Baseline del registro de tools.

Congela el set de tools (declaraciones + handlers) que existe HOY. Durante el
refactor de arquitectura, esto detecta si una tool desaparece sin querer: el set
nuevo debe ser SUPERSET del baseline (se puede agregar, no quitar silenciosamente).

Para re-basar a propósito (cuando quites/renombres una tool de forma intencional),
regenerá tests/registry_baseline.json y revisá el diff.
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent / "registry_baseline.json"
_SNAP = json.loads(BASE.read_text(encoding="utf-8"))


def test_no_declaration_disappeared(jarvis_main):
    # Lista EFECTIVA que JARVIS expone: base + tools migradas a @tool + skills.
    # (Una tool puede mudarse del archivo base al decorador; sigue estando acá.)
    current = {d["name"] for d in jarvis_main.TOOL_DECLARATIONS}
    missing = sorted(set(_SNAP["declarations"]) - current)
    assert not missing, f"Declaraciones del baseline que ya no existen: {missing}"


def test_no_handler_disappeared(jarvis_main):
    current = set(jarvis_main.STANDARD_TOOL_HANDLERS)
    missing = sorted(set(_SNAP["handlers"]) - current)
    assert not missing, f"Handlers del baseline que ya no existen: {missing}"
