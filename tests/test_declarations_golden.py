# -*- coding: utf-8 -*-
"""
test_declarations_golden.py — El schema de cada tool no cambia al migrarla a @tool.

Congela en declarations_golden.json el schema EXACTO de cada tool propia. Cuando una
tool se migra del archivo base al decorador `@tool`, su declaración debe quedar
byte-idéntica. Esto atrapa cualquier typo al copiar el schema (clave para las tools
de schema grande como trading_bot).

Para cambiar un schema A PROPÓSITO: regenerá el golden y revisá el diff.
"""
import json
from pathlib import Path

# Importar main dispara los @tool de las actions (MCP omitido vía conftest).
import main  # noqa: F401
from core import registry as _reg
from core.tool_declarations import TOOL_DECLARATIONS as _BASE

GOLDEN = json.loads((Path(__file__).resolve().parent / "declarations_golden.json").read_text(encoding="utf-8"))


def _effective() -> dict:
    return {d["name"]: d for d in _reg.first_party_declarations(_BASE)}


def test_no_tool_missing_vs_golden():
    eff = _effective()
    missing = sorted(set(GOLDEN) - set(eff))
    assert not missing, f"Tools del golden que desaparecieron: {missing}"


def test_each_declaration_identical_to_golden():
    eff = _effective()
    diffs = []
    for name, decl in GOLDEN.items():
        cur = eff.get(name)
        if cur != decl:
            diffs.append(name)
    assert not diffs, (
        f"Declaraciones que cambiaron vs el golden (¿typo al migrar?): {diffs}. "
        "Si el cambio es intencional, regenerá tests/declarations_golden.json."
    )
