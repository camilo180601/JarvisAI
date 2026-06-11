# -*- coding: utf-8 -*-
"""
test_tool_contract.py — Integridad del registro de tools (el dolor #1 del proyecto).

Hoy una tool vive en 3 lugares (action + handler en main + schema en
tool_declarations). Estos tests garantizan que NO se desincronicen:
  - cada declaración tiene un schema válido (lo que espera Gemini),
  - no hay nombres duplicados,
  - cada tool declarada es EJECUTABLE por alguno de los caminos de dispatch:
        STANDARD_TOOL_HANDLERS  |  dispatch especial (name == "...")  |
        fallback dinámico (actions/<name>.py con función <name>),
  - cada handler registrado está declarado (nada huérfano del otro lado).

Si un refactor rompe el cableado, estos tests lo agarran antes de que Gemini
intente llamar una tool inexistente.
"""
import re
import importlib
from pathlib import Path

import pytest

# Importar main dispara los decoradores @tool de todas las actions (con MCP omitido
# vía conftest), así la UNIÓN base + @tool está completa ya en tiempo de colección.
import main  # noqa: F401
from core import registry as _reg
from core.tool_declarations import TOOL_DECLARATIONS as _BASE_DECLS

ROOT = Path(__file__).resolve().parent.parent
# Fuente de verdad de las tools PROPIAS: archivo base + las migradas a @tool.
BASE_DECLS = _reg.first_party_declarations(_BASE_DECLS)
DECL_NAMES = [d["name"] for d in BASE_DECLS]


# ── Caminos de dispatch ──────────────────────────────────────────────────────

def _special_dispatch_names() -> set[str]:
    """Tools resueltas por ramas `name == "x"` / `name in ("a","b")` en main.py."""
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    names = set(re.findall(r'name\s*==\s*"([a-z_]+)"', src))
    for grp in re.findall(r'name\s+in\s*\(([^)]*)\)', src):
        names |= set(re.findall(r'"([a-z_]+)"', grp))
    return names


def _dynamic_resolvable(name: str) -> bool:
    """Fallback dinámico: actions/<name>.py existe y tiene una función <name>."""
    if not (ROOT / "actions" / f"{name}.py").exists():
        return False
    try:
        mod = importlib.import_module(f"actions.{name}")
        return callable(getattr(mod, name, None))
    except Exception:
        return False


# ── Schema de cada declaración ───────────────────────────────────────────────

@pytest.mark.parametrize("decl", BASE_DECLS, ids=DECL_NAMES)
def test_declaration_schema(decl):
    assert isinstance(decl.get("name"), str) and decl["name"], "name vacío"
    assert isinstance(decl.get("description"), str) and decl["description"].strip(), \
        f"{decl.get('name')}: description vacía"
    params = decl.get("parameters")
    assert isinstance(params, dict), f"{decl['name']}: parameters debe ser dict"
    assert params.get("type") == "OBJECT", f"{decl['name']}: type debe ser OBJECT"
    props = params.get("properties", {})
    assert isinstance(props, dict), f"{decl['name']}: properties debe ser dict"
    for pname, spec in props.items():
        assert isinstance(spec, dict) and "type" in spec, \
            f"{decl['name']}.{pname}: falta 'type'"
    req = params.get("required", [])
    assert isinstance(req, list)
    for r in req:
        assert r in props, f"{decl['name']}: required '{r}' no está en properties"


def test_no_duplicate_tool_names():
    from collections import Counter
    dups = [n for n, c in Counter(DECL_NAMES).items() if c > 1]
    assert not dups, f"Nombres de tool duplicados: {dups}"


def test_every_declared_tool_is_executable(jarvis_main):
    handlers = set(jarvis_main.STANDARD_TOOL_HANDLERS)
    special = _special_dispatch_names()
    orphans = []
    for name in DECL_NAMES:
        if name in handlers or name in special or _dynamic_resolvable(name):
            continue
        orphans.append(name)
    assert not orphans, (
        "Tools declaradas a Gemini SIN forma de ejecutarse "
        f"(ni handler, ni especial, ni actions/<name>.py): {orphans}"
    )


def test_every_handler_is_declared(jarvis_main):
    declared = set(DECL_NAMES)
    extra = sorted(set(jarvis_main.STANDARD_TOOL_HANDLERS) - declared)
    assert not extra, f"Handlers registrados sin declaración (Gemini no los ve): {extra}"


def test_handler_tuple_shape(jarvis_main):
    for name, entry in jarvis_main.STANDARD_TOOL_HANDLERS.items():
        assert isinstance(entry, tuple) and len(entry) == 4, \
            f"{name}: la entrada debe ser (fn, extras, fallback, log_prefix)"
        fn, extras, fallback, log_prefix = entry
        assert fn is None or callable(fn), f"{name}: fn no es callable"
        assert isinstance(extras, list), f"{name}: extras debe ser list"
        assert isinstance(fallback, str), f"{name}: fallback debe ser str"
        assert log_prefix is None or isinstance(log_prefix, str), \
            f"{name}: log_prefix debe ser str o None"
