#!/usr/bin/env python3
"""
smoke_test.py — Valida todos los subsistemas de JARVIS sin arrancar la UI.

Corre chequeos automáticos de: config, imports, tools core, skills, memoria,
episodic, planner, MCP, notification engine. NO testea voz (eso es manual).

Uso:
    python3 smoke_test.py
    python3 smoke_test.py --verbose

Exit code 0 = todo OK. !=0 = alguna falla crítica.
"""
import sys
import os
import warnings
import json
from pathlib import Path

warnings.filterwarnings("ignore")
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

# ── Mini framework ───────────────────────────────────────────────────────────
_results = []

def check(name: str):
    def deco(fn):
        def wrapper():
            try:
                detail = fn()
                _results.append((name, True, detail or ""))
                print(f"  ✓ {name}" + (f" — {detail}" if detail and VERBOSE else ""))
            except SkipTest as e:
                _results.append((name, None, str(e)))
                print(f"  ⏭️  {name} — {e}")
            except Exception as e:
                _results.append((name, False, str(e)))
                print(f"  ✗ {name} — {e}")
        return wrapper
    return deco

class SkipTest(Exception):
    pass


# ── 1. Config ────────────────────────────────────────────────────────────────
@check("config: gemini_api_key (vía config_manager / .env)")
def t_config():
    from memory.config_manager import cfg as _cfg
    key = _cfg("gemini_api_key", "")
    assert key.startswith("AIza"), "key inválida o ausente"
    return f"key {key[:8]}..."

@check("config: prompt.txt + SOUL/USER/MEMORY.md presentes")
def t_memory_files():
    for f in ["core/prompt.txt", "memory/SOUL.md", "memory/USER.md", "memory/MEMORY.md"]:
        assert (BASE / f).exists(), f"falta {f}"
    return "4 archivos"


# ── 2. Tool declarations ─────────────────────────────────────────────────────
@check("tool_declarations: carga + nombres únicos")
def t_decls():
    from core.tool_declarations import TOOL_DECLARATIONS
    names = [t["name"] for t in TOOL_DECLARATIONS]
    assert len(names) == len(set(names)), "nombres duplicados: " + str([n for n in names if names.count(n) > 1])
    return f"{len(names)} tools"

@check("tool_declarations: todas tienen description + parameters")
def t_decls_shape():
    from core.tool_declarations import TOOL_DECLARATIONS
    bad = [t["name"] for t in TOOL_DECLARATIONS if not t.get("description") or "parameters" not in t]
    assert not bad, f"mal formadas: {bad}"
    return "schema OK"


# ── 3. Skills system ─────────────────────────────────────────────────────────
@check("skills: discovery + availability signals")
def t_skills():
    from core.skill_loader import discover_skills
    skills = discover_skills()
    assert len(skills) >= 1, "no se descubrió ninguna skill"
    avail = [s["name"] for s in skills if s["available"]]
    return f"{len(skills)} skills, {len(avail)} disponibles"

@check("skills: git_control ejecuta")
def t_skill_exec():
    from core.skill_loader import build_skill_dispatch
    d = build_skill_dispatch()
    if "git_control" not in d:
        raise SkipTest("git_control no disponible")
    r = d["git_control"]({"action": "status"})
    assert "git" in r.lower() or "rama" in r.lower() or "status" in r.lower()
    return "git status OK"


# ── 4. Tool resolver ─────────────────────────────────────────────────────────
@check("tool_resolver: lista tools + invoca knowledge_base")
def t_resolver():
    from core.tool_resolver import invoke_tool, list_available_tools
    tools = list_available_tools()
    assert len(tools) > 20, f"muy pocas tools: {len(tools)}"
    r = invoke_tool("knowledge_base", {"action": "list"})
    assert "Error" not in r or "vac" in r.lower()
    return f"{len(tools)} tools invocables"


# ── 5. Episodic memory ───────────────────────────────────────────────────────
@check("episodic: logger escribe + recall lee")
def t_episodic():
    from core.episodic import EpisodicLogger
    from actions.recall import run as recall
    log = EpisodicLogger()
    log.log_user_turn("smoke test mensaje de prueba xyzzy")
    log.log_tool_call("test_tool", {"a": 1}, "ok", 5, True)
    log.close()
    r = recall({"query": "xyzzy"})
    assert "xyzzy" in r, "recall no encontró el evento recién escrito"
    return "round-trip OK"


# ── 6. Planner (sin llamar a Gemini — solo carga) ────────────────────────────
@check("planner: módulo carga + tool_resolver accesible")
def t_planner():
    from actions.planner import planner, _looks_like_failure
    assert _looks_like_failure("Error: algo") is True
    assert _looks_like_failure("Listo, hecho") is False
    return "heurística OK"


# ── 7. Notification engine ───────────────────────────────────────────────────
@check("notifications: engine + sources")
def t_notif():
    from core.notification_engine import get_engine
    eng = get_engine()
    eng.register_default_sources()
    sources = [s.name for s in eng.sources]
    return f"sources: {sources or '(ninguna)'}"

@check("notifications: rule matcher + DND")
def t_notif_logic():
    from core.notification_engine import Rule, DNDState, Event
    r = Rule(id="x", name="t", contact="juan")
    assert r.matches(Event("imessage", "Juan Perez", "hola", 0))
    assert not r.matches(Event("imessage", "Maria", "hola", 0))
    d = DNDState(scope="whatsapp", expires_at="2099-01-01T00:00:00")
    assert d.silences(Event("whatsapp", "x", "hola", 0))
    assert not d.silences(Event("imessage", "x", "hola", 0))
    return "matcher + DND OK"


# ── 8. MCP client ────────────────────────────────────────────────────────────
@check("mcp: command resolver encuentra npx")
def t_mcp_resolver():
    from core.mcp_client import _resolve_command
    npx = _resolve_command("npx")
    if not os.path.exists(npx):
        raise SkipTest("npx no instalado en este sistema")
    return Path(npx).name

@check("mcp: servers activos en config arrancan")
def t_mcp_servers():
    from core.mcp_client import get_manager
    mgr = get_manager()
    n = mgr.load_from_config()
    if n == 0:
        raise SkipTest("0 servers activos (config vacío o disabled)")
    tools = mgr.get_tool_declarations()
    mgr.shutdown()
    return f"{n} servers, {len(tools)} MCP tools"


# ── 9. Platform utils ────────────────────────────────────────────────────────
@check("platform_utils: OS detection + chrome path")
def t_platform():
    from core.platform_utils import OS_NAME, get_chrome_path
    chrome = get_chrome_path()
    return f"OS={OS_NAME}, chrome={'OK' if chrome else 'no encontrado'}"


# ── Runner ───────────────────────────────────────────────────────────────────
def main():
    print("\n🧪 JARVIS Smoke Test\n" + "=" * 50)

    print("\n[1] Config")
    t_config(); t_memory_files()
    print("\n[2] Tool declarations")
    t_decls(); t_decls_shape()
    print("\n[3] Skills")
    t_skills(); t_skill_exec()
    print("\n[4] Tool resolver")
    t_resolver()
    print("\n[5] Episodic memory")
    t_episodic()
    print("\n[6] Planner")
    t_planner()
    print("\n[7] Notification engine")
    t_notif(); t_notif_logic()
    print("\n[8] MCP")
    t_mcp_resolver(); t_mcp_servers()
    print("\n[9] Platform")
    t_platform()

    # Resumen
    passed = sum(1 for _, ok, _ in _results if ok is True)
    failed = sum(1 for _, ok, _ in _results if ok is False)
    skipped = sum(1 for _, ok, _ in _results if ok is None)
    print("\n" + "=" * 50)
    print(f"Resultado: {passed} ✓   {failed} ✗   {skipped} ⏭️")
    if failed:
        print("\nFALLAS:")
        for name, ok, detail in _results:
            if ok is False:
                print(f"  ✗ {name}: {detail}")
        sys.exit(1)
    print("\n✅ Todos los chequeos críticos pasaron.")
    sys.exit(0)


if __name__ == "__main__":
    main()
