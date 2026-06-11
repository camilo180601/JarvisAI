"""
antigravity.py — JARVIS usa la Antigravity CLI de Google (modo headless), sin API key.

Antigravity es la plataforma de desarrollo agéntica de Google (corre con Gemini 3.5
Flash, sucesora de Gemini CLI). Usa tu sesión logueada (suscripción de Google).
El binario suele llamarse `agy`. JARVIS le pasa la tarea/pregunta, Antigravity la
resuelve (puede editar archivos) y JARVIS te lee el resultado.

Acciones:
  run               Tarea de programación en un proyecto (edita archivos). NO commitea.
  plan              Le pide un plan / propuesta SIN tocar nada.
  ask               Pregunta de conocimiento (sin contexto de proyecto).
  status            Verifica que el CLI esté instalado y logueado.
  improve_frontend  Mejora el frontend de JARVIS (ui.py, assets/sphere.html) en una
                    RAMA git nueva, con preview del diff. NUNCA toca main solo.

⚠️ Bug conocido (agy 1.0.x): el flag -p/--print a veces NO escribe la respuesta a
stdout en contextos sin TTY. Si pasa, devolvemos un aviso en vez de un fallo mudo.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import glob
import time
from pathlib import Path
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent

# Archivos que componen el frontend del asistente.
_FRONTEND_FILES = ["ui.py", "assets/sphere.html"]


def _agy_bin() -> str | None:
    """Ubica el binario de la Antigravity CLI (agy / antigravity)."""
    for name in ("agy", "antigravity"):
        exe = shutil.which(name)
        if exe:
            return exe
    cands = [Path("/opt/homebrew/bin/agy"), Path("/usr/local/bin/agy"),
             Path("/opt/homebrew/bin/antigravity"), Path("/usr/local/bin/antigravity"),
             Path.home() / ".antigravity" / "bin" / "agy"]
    cands += [Path(p) for p in glob.glob(str(Path.home() / ".nvm/versions/node/*/bin/agy"))]
    for c in cands:
        if Path(c).exists():
            return str(c)
    return None


def _env_with_node(bin_path: str) -> dict:
    """El CLI necesita node en el PATH; lo inyectamos (arranque desde GUI lo pierde)."""
    env = os.environ.copy()
    bindir = str(Path(bin_path).parent)
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
                                "/login", "sign in", "please run", "unauthorized", "no credentials"))


def _print_args(agy: str, prompt: str) -> list:
    """Argumentos para una corrida no-interactiva (print)."""
    return [agy, "-p", prompt]


def _git(args: list, cwd: str) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:
        return 1, str(e)


@tool(
    name='antigravity',
    description="Usa la Antigravity CLI de Google (headless, con la suscripción del usuario — sin API key, corre con Gemini 3.5 Flash) para programar o responder. USAR cuando el usuario diga 'usá Antigravity', 'que lo haga Antigravity', 'conectate a Antigravity', o pida que JARVIS 'mejore su frontend/interfaz'. action=run (edita archivos en el proyecto, NO commitea) | plan (propone sin tocar) | ask (pregunta de conocimiento) | status (verifica instalación/login) | improve_frontend (mejora ui.py y assets/sphere.html en una RAMA git nueva con preview del diff — NUNCA toca main solo; pasá 'goal' para enfocar la mejora). Nota: agy 1.0.x tiene un bug donde -p headless a veces no devuelve texto; si pasa, la tool avisa.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'run | plan | ask | status | improve_frontend'},
                    'goal': {'type': 'STRING',
                             'description': 'Tarea/objetivo (run/plan/improve_frontend). Para '
                                            'improve_frontend, enfoca qué mejorar del frontend.'},
                    'query': {'type': 'STRING', 'description': 'Pregunta (action=ask)'},
                    'project_path': {'type': 'STRING',
                                     'description': 'Proyecto donde trabajar (default: JARVIS)'},
                    'branch': {'type': 'STRING',
                               'description': 'improve_frontend: nombre de rama (default: '
                                              'antigravity/frontend-<fecha>)'},
                    'auto': {'type': 'BOOLEAN',
                             'description': 'true = más autónomo (salta permisos). Default false.'}},
     'required': []},
)
def antigravity(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "run").lower().strip()

    agy = _agy_bin()
    if not agy:
        return ("No encontré la Antigravity CLI. Instalala con: npm install -g @google/antigravity-cli "
                "(o seguí las instrucciones de antigravity.google) y logueate corriendo 'agy' una vez.")
    env = _env_with_node(agy)

    def log(m):
        if player:
            try:
                player.write_log(m)
            except Exception:
                pass

    if action == "status":
        code, out = _run_cli([agy, "--version"], str(BASE_DIR), env, 20)
        ver = out.splitlines()[0] if out else "?"
        code2, out2 = _run_cli(_print_args(agy, "responde solo: ok"), str(BASE_DIR), env, 60)
        if _needs_login(out2):
            return f"Antigravity CLI {ver} instalada, pero NO logueada. Abrí una terminal y corré: agy (logueate con tu cuenta de Google, sin API key)."
        if not out2:
            return (f"Antigravity CLI {ver} instalada y logueada, pero la prueba headless no devolvió texto "
                    "(bug conocido de agy 1.0.x con -p en modo no-interactivo). El cerebro queda disponible; "
                    "si no responde, actualizá la CLI.")
        return f"✓ Antigravity CLI {ver} instalada y logueada. Respuesta de prueba: {out2[:60]}"

    if action in ("ask", "preguntar"):
        q = (parameters.get("query") or parameters.get("question") or parameters.get("goal") or "").strip()
        if not q:
            return "¿Qué le pregunto a Antigravity?"
        log("🛰️ Preguntando a Antigravity…")
        code, out = _run_cli(_print_args(agy, q), str(BASE_DIR), env, 180)
        if _needs_login(out):
            return "Antigravity no está logueada. Corré 'agy' en una terminal y logueate una vez."
        return out or "(Antigravity no devolvió texto — posible bug de -p headless en agy 1.0.x.)"

    if action in ("improve_frontend", "mejorar_frontend", "frontend"):
        return _improve_frontend(parameters, agy, env, log)

    # run / plan → tarea en un proyecto
    goal = (parameters.get("goal") or parameters.get("request") or parameters.get("query") or "").strip()
    if not goal:
        return "Decime qué querés que programe/haga Antigravity (goal)."
    project_path = parameters.get("project_path") or parameters.get("path") or str(BASE_DIR)
    project_path = str(Path(project_path).expanduser().resolve())
    if not Path(project_path).exists():
        return f"El proyecto no existe: {project_path}"

    plan = action in ("plan", "planear", "proponer")
    auto = bool(parameters.get("auto"))
    args = _print_args(agy, goal)
    if plan:
        args += ["--plan"] if False else []  # plan mode: pedimos propuesta en el prompt, sin editar
        goal = "Propón un plan detallado SIN editar ni ejecutar nada:\n" + goal
        args = _print_args(agy, goal)
    elif auto:
        args += ["--dangerously-skip-permissions"]

    log(f"🛰️ Antigravity {'(plan) ' if plan else ''}en {Path(project_path).name}: '{goal[:60]}'…")
    timeout = int(parameters.get("timeout") or 600)
    code, out = _run_cli(args, project_path, env, timeout)
    if _needs_login(out):
        return ("Antigravity no está logueada todavía. Abrí una terminal, corré 'agy', "
                "logueate con tu cuenta de Google (sin API key) y reintentá.")
    if not out:
        return (f"Antigravity terminó (exit {code}) sin texto de salida — posible bug de -p headless en "
                "agy 1.0.x. Si editó archivos igual, revisalos con git.")

    head = "📋 PLAN de Antigravity (no tocó nada):\n" if plan else \
           "🛰️ Antigravity terminó (pudo editar archivos, NO desplegué):\n"
    tail = "" if plan else "\n\nRevisá con 'mostrame los cambios' y decime si lo desplegás."
    return head + out[:3000] + tail


def _improve_frontend(parameters: dict, agy: str, env: dict, log) -> str:
    """Antigravity mejora el frontend de JARVIS en una RAMA git nueva (preview, sin merge)."""
    repo = str(BASE_DIR)
    # 1) debe ser repo git
    code, _ = _git(["rev-parse", "--is-inside-work-tree"], repo)
    if code != 0:
        return "Esto no es un repo git; no puedo aislar los cambios en una rama. Iniciá git primero."
    # 2) árbol limpio (para que el diff de Antigravity sea revisable y no se mezcle con tu trabajo)
    code, dirty = _git(["status", "--porcelain"], repo)
    if dirty.strip():
        return ("Tenés cambios sin commitear. Para que pueda aislar lo que cambie Antigravity en una rama "
                "limpia y mostrarte un diff claro, hacé commit o stash de lo actual primero.")

    # 3) crear y cambiar a una rama nueva
    branch = parameters.get("branch") or f"antigravity/frontend-{time.strftime('%Y%m%d-%H%M%S')}"
    code, out = _git(["checkout", "-b", branch], repo)
    if code != 0:
        return f"No pude crear la rama '{branch}': {out[:200]}"

    focus = (parameters.get("goal") or parameters.get("request") or "").strip()
    files = ", ".join(_FRONTEND_FILES)
    goal = (
        "Sos un agente de desarrollo frontend. Mejorá la interfaz del asistente JARVIS, "
        f"centrándote SOLO en estos archivos: {files}. "
        + (f"Objetivo concreto del usuario: {focus}. " if focus else
           "Mejorá la estética/UX del orbe y la ventana: pulido visual, responsividad, micro-animaciones suaves, "
           "accesibilidad y limpieza del código, sin romper la funcionalidad existente. ")
        + "NO toques la lógica de voz, tools ni el backend. NO borres funcionalidad. "
        "Hacé cambios incrementales y seguros. Explicá brevemente qué cambiaste."
    )
    args = [agy, "-p", goal, "--dangerously-skip-permissions"]

    log(f"🛰️ Antigravity mejorando el frontend en rama '{branch}'…")
    timeout = int(parameters.get("timeout") or 900)
    code, out = _run_cli(args, repo, env, timeout)

    if _needs_login(out):
        _git(["checkout", "-"], repo)
        _git(["branch", "-D", branch], repo)
        return "Antigravity no está logueada. Corré 'agy' en una terminal, logueate y reintentá."

    # 4) ver qué cambió
    code_d, stat = _git(["diff", "--stat"], repo)
    if not stat.strip():
        # nada cambió → volver a la rama anterior y borrar la rama vacía
        _git(["checkout", "-"], repo)
        _git(["branch", "-D", branch], repo)
        extra = "" if out else " (y -p no devolvió texto: posible bug de agy 1.0.x headless)"
        return f"Antigravity no hizo cambios en el frontend{extra}. Quedaste en tu rama original."

    msg = out[:1500] if out else "(sin resumen de texto — bug de -p headless en agy 1.0.x)"
    return (
        f"🛰️ Antigravity propuso mejoras al frontend en la rama '{branch}' (NO toqué main):\n\n"
        f"{msg}\n\n"
        f"📊 Archivos cambiados:\n{stat[:800]}\n\n"
        f"Revisá con 'mostrame el diff'. Si te gusta: mergealo a main. Si no: "
        f"`git checkout main && git branch -D {branch}` lo descarta. Estás en la rama, tu trabajo en main intacto."
    )
