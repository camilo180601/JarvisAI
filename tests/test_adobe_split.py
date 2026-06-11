# -*- coding: utf-8 -*-
"""
test_adobe_split.py — La fachada adobe_ops reexporta TODAS las operaciones.

adobe_ops.py se partió en core/adobe/{common,illustrator,photoshop,indesign}.py (Fase 5).
adobe_baseline.json congela las 128 funciones públicas que existían antes del split:
ninguna debe desaparecer ni cambiar de módulo de forma que rompa `ops.<func>`.
"""
import json
from pathlib import Path

BASELINE = set(json.loads((Path(__file__).resolve().parent / "adobe_baseline.json").read_text()))


def test_facade_reexports_all_ops():
    from core import adobe_ops as ops
    current = {n for n in dir(ops) if n.startswith(("ai_", "ps_", "id_", "doc_"))}
    missing = sorted(BASELINE - current)
    assert not missing, f"Operaciones de Adobe que desaparecieron del split: {missing}"


def test_all_ops_are_callable():
    from core import adobe_ops as ops
    not_callable = [n for n in BASELINE if not callable(getattr(ops, n, None))]
    assert not not_callable, f"Ops que dejaron de ser callable: {not_callable}"


def test_split_modules_import():
    # cada módulo por app importa sin error
    import core.adobe.common      # noqa: F401
    import core.adobe.illustrator # noqa: F401
    import core.adobe.photoshop   # noqa: F401
    import core.adobe.indesign    # noqa: F401


def test_ops_live_in_correct_module():
    from core import adobe_ops as ops
    assert getattr(ops, "ai_star").__module__ == "core.adobe.illustrator"
    assert getattr(ops, "ps_levels").__module__ == "core.adobe.photoshop"
    assert getattr(ops, "id_table").__module__ == "core.adobe.indesign"
    assert getattr(ops, "doc_open").__module__ == "core.adobe.common"


def test_dispatch_ops_exist():
    """Cada ops.<fn>( que llama el dispatch de adobe_control debe existir en la
    fachada. Atrapa drift si se renombra/borra una op sin actualizar el dispatch."""
    import re
    from core import adobe_ops as ops
    src = (Path(__file__).resolve().parent.parent / "actions" / "adobe_control.py").read_text()
    called = set(re.findall(r"ops\.([a-z_0-9]+)\(", src))
    available = {n for n in dir(ops) if not n.startswith("_")}
    missing = sorted(called - available)
    assert not missing, f"adobe_control llama ops que no existen: {missing}"
