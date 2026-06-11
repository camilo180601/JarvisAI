# -*- coding: utf-8 -*-
"""
conftest.py — setup compartido de la suite.

CLAVE: fija JARVIS_SKIP_MCP=1 ANTES de que cualquier test importe `main`, así no
arranca los servers MCP (tests rápidos, deterministas, sin red). Agrega la raíz del
repo al path y silencia warnings ruidosos.
"""
import os
import sys
import warnings
from pathlib import Path

# Debe ir antes de cualquier `import main`.
os.environ.setdefault("JARVIS_SKIP_MCP", "1")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore")

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def jarvis_main():
    """Importa el módulo `main` una sola vez (con MCP omitido)."""
    import main
    return main
