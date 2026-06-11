"""
code_agent.py — JARVIS escribe/edita código de forma autónoma (estilo Claude Code).

Flujo (decisiones del usuario):
  • SIEMPRE se pide qué cerebro usar; si falta la API key, se abre la ventana de keys.
  • NUNCA mergea a main ni pushea: solo deja los cambios hechos. El usuario despliega
    después con action=deploy (commit) o descarta con action=discard.
  • Funciona sobre CUALQUIER proyecto (project_path).
"""
from __future__ import annotations
from pathlib import Path
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent

# Estado de la última corrida (para deploy/discard/diff)
_SESSION = {"project_path": None, "changed": [], "brain": None, "goal": None}

_PROVIDER_ALIASES = {"gpt": "openai", "chatgpt": "openai", "anthropic": "claude",
                     "claude": "claude", "openai": "openai", "gemini": "gemini", "minimax": "minimax"}


def _resolve_brain(brain: str):
    p = _PROVIDER_ALIASES.get((brain or "").lower().strip())
    if not p:
        return None, None
    from core.llm_router import MODELS
    return p, MODELS[p][0][0]   # modelo default del proveedor


@tool(
    name='code_agent',
    description="Agente que ESCRIBE/EDITA código de forma autónoma (estilo Claude Code) en JARVIS o en cualquier proyecto. USAR cuando el usuario pide programar, agregar una feature, arreglar un bug, refactorizar, 'agregate X', 'mejorá tu código', etc. IMPORTANTE: SIEMPRE preguntá primero con qué cerebro programar (Claude, GPT, Gemini o MiniMax) y pasalo en 'brain' — si no se especifica, la tool te lo recuerda. NUNCA despliega solo: deja los cambios hechos en una rama y el usuario decide. action=run programa; deploy commitea los cambios (cuando el usuario diga 'desplegá'); discard los descarta; diff los muestra.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'run (default, programa) | plan (propone sin tocar nada) '
                                              '| deploy | discard | diff'},
                    'goal': {'type': 'STRING',
                             'description': 'Qué programar/cambiar, en lenguaje natural y con detalle'},
                    'brain': {'type': 'STRING',
                              'description': 'Cerebro a usar: claude | gpt | gemini | minimax '
                                             '(PREGUNTAR al usuario primero)'},
                    'project_path': {'type': 'STRING',
                                     'description': 'Ruta del proyecto (default: el propio JARVIS)'},
                    'model': {'type': 'STRING',
                              'description': 'Modelo específico opcional (si no, el default del '
                                             'cerebro)'},
                    'message': {'type': 'STRING',
                                'description': 'deploy: mensaje de commit (opcional)'}},
     'required': []},
)
def code_agent(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "run").lower().strip()

    def log(m):
        if player:
            try:
                player.write_log(m)
            except Exception:
                pass

    # ── Desplegar / descartar / ver diff de la última corrida ──
    if action in ("deploy", "desplegar", "commit"):
        from core.code_agent import safety
        if not _SESSION["changed"]:
            return "No hay cambios pendientes de la última corrida."
        msg = parameters.get("message") or f"JARVIS code_agent: {(_SESSION.get('goal') or 'cambios')[:60]}"
        return safety.commit(Path(_SESSION["project_path"]), _SESSION["changed"], msg)
    if action in ("discard", "descartar", "revert"):
        from core.code_agent import safety
        if not _SESSION["changed"]:
            return "No hay cambios para descartar."
        r = safety.revert(Path(_SESSION["project_path"]), _SESSION["changed"])
        _SESSION["changed"] = []
        return r
    if action in ("diff", "status"):
        from core.code_agent import safety
        if not _SESSION["changed"]:
            return "No hay una corrida reciente con cambios."
        return f"Última corrida ({_SESSION['brain']}): {len(_SESSION['changed'])} archivo(s).\n" + \
               safety.diff_for(Path(_SESSION["project_path"]), _SESSION["changed"])

    plan_mode = action in ("plan", "planear", "proponer")

    # ── Correr el agente ──
    goal = (parameters.get("goal") or parameters.get("request") or "").strip()
    if not goal:
        return "Decime qué querés que programe (goal)."

    brain = (parameters.get("brain") or parameters.get("provider") or "").strip()
    if not brain:
        return ("¿Con qué cerebro querés que programe? Opciones: Claude, GPT (OpenAI), Gemini o MiniMax. "
                "Volvé a pedirlo indicando el cerebro (ej: brain='claude').")

    provider, default_model = _resolve_brain(brain)
    if not provider:
        return f"No reconozco el cerebro '{brain}'. Usá: claude, gpt, gemini o minimax."
    model = parameters.get("model") or default_model

    # Chequeo de API key → abre la ventana si falta
    try:
        from core.credentials import require_key
        ok, msg = require_key(provider)
        if not ok:
            return msg + " Cuando la cargues, repetí el pedido indicando el cerebro."
    except Exception:
        pass

    # Proyecto destino
    project_path = parameters.get("project_path") or parameters.get("path") or str(BASE_DIR)
    project_path = Path(project_path).expanduser().resolve()
    if not project_path.exists():
        return f"El proyecto no existe: {project_path}"

    from core.code_agent.loop import run_agent
    from core.code_agent.prompt import build_system_prompt
    from core.code_agent import safety

    log(f"🛠️ code_agent ({provider}:{model}{', PLAN' if plan_mode else ''}) en {project_path.name} — '{goal[:60]}'")
    branch = safety.current_branch(project_path) if safety.is_git_repo(project_path) else "(sin git)"

    # confirm para comandos peligrosos: bloqueado por defecto (el agente no los necesita)
    res = run_agent(goal=goal, project_path=project_path, provider=provider, model=model,
                    system=build_system_prompt(project_path), log=log, plan_mode=plan_mode,
                    confirm=lambda cmd: False, max_steps=int(parameters.get("max_steps") or 40))

    if plan_mode:
        if res.get("error"):
            return f"✗ {res['error']}"
        return f"📋 PLAN (no toqué nada) — {provider}:{model}:\n{res.get('final','')}"

    # Capturar archivos cambiados desde el contexto del loop
    changed = sorted(res.get("changed") or [])
    _SESSION.update({"project_path": str(project_path), "changed": changed,
                     "brain": f"{provider}:{model}", "goal": goal})

    if res.get("error"):
        return f"✗ El agente se detuvo: {res['error']}" + (
            f"\n(Alcanzó a tocar {len(changed)} archivo(s) — mirá con action=diff)" if changed else "")

    # Verificación: sintaxis instantánea primero; si está rota, NO perder minutos en tests
    syntax = safety.syntax_check(project_path, changed) if changed else ""
    if syntax.startswith("❌"):
        tests = "(salteé los tests: hay sintaxis rota — arreglala o descartá los cambios)"
    else:
        tests = safety.run_tests(project_path) if changed else "(sin cambios, no corrí tests)"
    summary = res.get("final", "")
    out = [f"✓ Terminé ({res.get('steps')} pasos, cerebro {provider}:{model}).",
           f"📝 {summary}",
           f"📂 Archivos tocados ({len(changed)}): " + (", ".join(Path(f).name for f in changed) or "ninguno"),
           *([syntax] if syntax else []),
           f"🧪 {tests}",
           f"🌿 Rama actual: {branch} — NO desplegué nada.",
           "Decime 'desplegá esos cambios' para commitearlos, 'mostrame el diff', o 'descartá'."]
    return "\n".join(out)
