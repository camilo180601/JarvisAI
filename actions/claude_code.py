"""
claude_code.py — JARVIS usa el Claude Code CLI local (modo headless), sin API key.

Usa tu sesión logueada de Claude (suscripción). JARVIS le pasa la tarea/pregunta,
Claude Code la resuelve (puede editar archivos, correr cosas) y JARVIS te lee el resultado.

Acciones:
  run    Tarea de programación en un proyecto (Claude Code edita archivos). NO commitea.
  plan   Le pide un plan SIN tocar nada (--permission-mode plan).
  ask    Pregunta de conocimiento (sin contexto de proyecto).
  status Verifica que el CLI esté instalado y logueado.
"""
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent


def _claude_bin() -> str | None:
    exe = shutil.which("claude")
    if exe:
        return exe
    cands = [Path.home() / ".claude" / "local" / "claude",
             Path("/opt/homebrew/bin/claude"), Path("/usr/local/bin/claude")]
    import glob
    cands += [Path(p) for p in glob.glob(str(Path.home() / ".nvm/versions/node/*/bin/claude"))]
    for c in cands:
        if Path(c).exists():
            return str(c)
    return None


def _env_with_node(claude_path: str) -> dict:
    """El CLI necesita node en el PATH; lo inyectamos (arranque desde GUI lo pierde)."""
    env = os.environ.copy()
    bindir = str(Path(claude_path).parent)
    if bindir not in env.get("PATH", "").split(os.pathsep):
        env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
    return env


def _run_cli(args: list, cwd: str, env: dict, timeout: int) -> tuple[int, str]:
    try:
        r = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True,
                           timeout=timeout, stdin=subprocess.DEVNULL)
        return r.returncode, ((r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")).strip()
    except subprocess.TimeoutExpired:
        return 1, f"(timeout {timeout}s — la tarea era muy larga)"
    except Exception as e:
        return 1, str(e)


def _needs_login(out: str) -> bool:
    o = out.lower()
    return any(k in o for k in ("log in", "login", "authenticate", "not authenticated",
                                "/login", "invalid api key", "please run", "unauthorized"))


@tool(
    name='claude_code',
    description="Usa el CLI de Claude Code local (headless, con la suscripción del usuario — sin API key) para programar o responder. USAR cuando el usuario diga 'usá Claude Code', 'que lo haga Claude Code', 'preguntale a Claude', o quiera el motor de Claude Code para una tarea de código. action=run (Claude Code edita archivos en el proyecto, NO commitea) | plan (propone sin tocar) | ask (pregunta de conocimiento) | status (verifica instalación/login). Distinto de code_agent (que usa el cerebro configurado vía API).",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING', 'description': 'run | plan | ask | status'},
                    'goal': {'type': 'STRING', 'description': 'Tarea de programación (run/plan)'},
                    'query': {'type': 'STRING', 'description': 'Pregunta (action=ask)'},
                    'project_path': {'type': 'STRING',
                                     'description': 'Proyecto donde trabajar (default: JARVIS)'},
                    'auto': {'type': 'BOOLEAN',
                             'description': 'true = más autónomo (salta permisos). Default false '
                                            '(auto-acepta solo ediciones).'}},
     'required': []},
)
def claude_code(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "run").lower().strip()

    claude = _claude_bin()
    if not claude:
        return ("No encontré el CLI de Claude Code. Instalalo con: "
                "npm install -g @anthropic-ai/claude-code")
    env = _env_with_node(claude)

    def log(m):
        if player:
            try:
                player.write_log(m)
            except Exception:
                pass

    if action == "status":
        code, out = _run_cli([claude, "--version"], str(BASE_DIR), env, 20)
        ver = out.splitlines()[0] if out else "?"
        # probe de login con una pregunta trivial
        code2, out2 = _run_cli([claude, "-p", "responde solo: ok", "--output-format", "text"],
                               str(BASE_DIR), env, 60)
        if _needs_login(out2):
            return f"Claude Code {ver} instalado, pero NO logueado. Abrí una terminal y corré: claude  (logueate con tu cuenta de Claude, sin API key)."
        return f"✓ Claude Code {ver} instalado y logueado. Respuesta de prueba: {out2[:60]}"

    if action in ("ask", "preguntar"):
        q = (parameters.get("query") or parameters.get("question") or parameters.get("goal") or "").strip()
        if not q:
            return "¿Qué le pregunto a Claude?"
        log(f"🤖 Preguntando a Claude Code…")
        code, out = _run_cli([claude, "-p", q, "--output-format", "text"], str(BASE_DIR), env, 180)
        if _needs_login(out):
            return "Claude Code no está logueado. Corré 'claude' en una terminal y logueate una vez."
        return out or "(Claude no devolvió respuesta.)"

    # run / plan → tarea en un proyecto
    goal = (parameters.get("goal") or parameters.get("request") or parameters.get("query") or "").strip()
    if not goal:
        return "Decime qué querés que programe/haga Claude Code (goal)."
    project_path = parameters.get("project_path") or parameters.get("path") or str(BASE_DIR)
    project_path = str(Path(project_path).expanduser().resolve())
    if not Path(project_path).exists():
        return f"El proyecto no existe: {project_path}"

    plan = action in ("plan", "planear", "proponer")
    auto = bool(parameters.get("auto"))   # auto=true → salta permisos (más autónomo, más riesgo)
    perm = "plan" if plan else "acceptEdits"
    args = [claude, "-p", goal, "--output-format", "text", "--add-dir", project_path]
    if auto and not plan:
        args += ["--dangerously-skip-permissions"]
    else:
        args += ["--permission-mode", perm]

    log(f"🤖 Claude Code {'(plan) ' if plan else ''}en {Path(project_path).name}: '{goal[:60]}'…")
    timeout = int(parameters.get("timeout") or 600)
    code, out = _run_cli(args, project_path, env, timeout)
    if _needs_login(out):
        return ("Claude Code no está logueado todavía. Abrí una terminal, corré 'claude', "
                "logueate con tu cuenta (sin API key) y reintentá.")
    if not out:
        return f"Claude Code terminó (exit {code}) sin texto de salida."

    head = "📋 PLAN de Claude Code (no tocó nada):\n" if plan else \
           "🤖 Claude Code terminó (editó archivos en el proyecto, NO desplegué):\n"
    tail = "" if plan else "\n\nRevisá con 'mostrame los cambios' y decime si lo desplegás."
    return head + out[:3000] + tail
