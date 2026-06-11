# -*- coding: utf-8 -*-
"""
test_registry.py — El ToolRegistry (Fase 0) refleja FIELMENTE el sistema actual.

Garantiza que la vista unificada no pierde ni inventa tools, que las declaraciones
que genera son idénticas a las actuales, y que toda tool es resoluble. Es la prueba
de que el registry puede convivir con lo legacy sin cambiar comportamiento.
"""
import pytest

from core import registry as reg
from core.tool_declarations import TOOL_DECLARATIONS as BASE_DECLS


@pytest.fixture(scope="module")
def legacy_reg(jarvis_main):
    return reg.build_from_legacy(
        jarvis_main.STANDARD_TOOL_HANDLERS,
        BASE_DECLS,
        reg.special_dispatch_names(),
    )


def test_registry_has_every_declared_tool(legacy_reg):
    declared = {d["name"] for d in BASE_DECLS}
    assert set(legacy_reg.names()) == declared


def test_declarations_roundtrip_identical(legacy_reg):
    # las declaraciones que emite el registry == las declaraciones base (mismo schema)
    by_name = {d["name"]: d for d in legacy_reg.declarations()}
    for d in BASE_DECLS:
        emitted = by_name[d["name"]]
        assert emitted["name"] == d["name"]
        assert emitted["description"] == d["description"]
        assert emitted["parameters"] == d["parameters"]


def test_every_tool_classified(legacy_reg):
    # ninguna tool base debe quedar como 'external' (eso sería MCP/skill/desconocida)
    external = [t.name for t in legacy_reg.by_source("external")]
    assert not external, f"Tools base sin clasificar (handler/special/dynamic): {external}"


def test_handler_tools_resolve(legacy_reg):
    for t in legacy_reg.by_source("handler"):
        # el handler puede ser None si el módulo no se importó, pero el campo existe
        assert t.handler is None or callable(t.handler)


def test_dynamic_tools_resolve_via_import(legacy_reg):
    for t in legacy_reg.by_source("dynamic"):
        fn = legacy_reg.resolve_handler(t.name)
        assert callable(fn), f"{t.name}: el fallback dinámico no resolvió una función"


def test_no_duplicate_registration():
    r = reg.ToolRegistry()
    r.register(reg.Tool(name="x", description="d", parameters={"type": "OBJECT", "properties": {}}))
    with pytest.raises(ValueError):
        r.register(reg.Tool(name="x", description="d2", parameters={"type": "OBJECT", "properties": {}}))


def test_decorator_registers_globally():
    r0 = len(reg.global_registry())

    @reg.tool(name="__test_tmp_tool__", description="tmp",
              parameters={"type": "OBJECT", "properties": {}})
    def _tmp(parameters, player=None):
        return "ok"

    assert "__test_tmp_tool__" in reg.global_registry()
    assert reg.global_registry().resolve_handler("__test_tmp_tool__") is _tmp
    # limpieza para no contaminar otros tests
    reg.global_registry()._tools.pop("__test_tmp_tool__", None)
    assert len(reg.global_registry()) == r0


def test_active_registry_setter(legacy_reg):
    reg.set_active_registry(legacy_reg)
    assert reg.active_registry() is legacy_reg
