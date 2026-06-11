# -*- coding: utf-8 -*-
"""
test_imports.py — Toda la base importa sin errores.

Es la red de seguridad más amplia: detecta errores de sintaxis, imports rotos y
side-effects de import en CUALQUIER módulo de actions/ y core/. Si un refactor
rompe un import, esto lo agarra de inmediato.
"""
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Módulos que NO deben importarse en tests (arrancan procesos/UI pesados o son
# puntos de entrada). El resto sí debe importar limpio.
_SKIP = {"main"}  # main se cubre aparte vía la fixture (con guard MCP)


def _modules(pkg: str) -> list[str]:
    out = []
    for f in sorted((ROOT / pkg).glob("*.py")):
        if f.stem.startswith("__"):
            continue
        out.append(f"{pkg}.{f.stem}")
    return out


@pytest.mark.parametrize("mod", _modules("actions"))
def test_action_imports(mod):
    importlib.import_module(mod)


@pytest.mark.parametrize("mod", _modules("core"))
def test_core_imports(mod):
    importlib.import_module(mod)


@pytest.mark.parametrize("mod", _modules("memory"))
def test_memory_imports(mod):
    importlib.import_module(mod)


def test_main_imports(jarvis_main):
    assert jarvis_main is not None
    assert hasattr(jarvis_main, "STANDARD_TOOL_HANDLERS")
    assert hasattr(jarvis_main, "TOOL_DECLARATIONS")
