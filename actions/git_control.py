"""
git_control.py — Operaciones git via subprocess (cross-platform).
"""
from __future__ import annotations
import subprocess
from pathlib import Path
from core.registry import tool


def _run_git(cmd: list, cwd: str | None = None, timeout: int = 30):
    try:
        r = subprocess.run(
            ["git"] + cmd,
            capture_output=True, text=True, cwd=cwd, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except FileNotFoundError:
        return -1, "", "git no está instalado o no está en PATH."
    except subprocess.TimeoutExpired:
        return -2, "", f"Timeout de {timeout}s."
    except Exception as e:
        return -3, "", str(e)


@tool(
    name='git_control',
    description='Git: status, log, diff, add, commit, push, pull, branch, clone.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'status | log | diff | commit | add | branches | '
                                              'branch_create | checkout | pull | push | stash | '
                                              'analyze'},
                    'repo_path': {'type': 'STRING', 'description': 'Ruta al repositorio Git'},
                    'message': {'type': 'STRING', 'description': 'Mensaje del commit'},
                    'branch_name': {'type': 'STRING', 'description': 'Nombre de la rama'},
                    'remote': {'type': 'STRING', 'description': 'Remote (default: origin)'},
                    'n': {'type': 'INTEGER', 'description': 'Número de commits para log'},
                    'file': {'type': 'STRING', 'description': 'Archivo específico para diff'},
                    'staged': {'type': 'BOOLEAN', 'description': 'Mostrar diff staged'},
                    'add_all': {'type': 'BOOLEAN',
                                'description': 'Agregar todos los archivos antes del commit (default: '
                                               'true)'},
                    'files': {'type': 'ARRAY',
                              'items': {'type': 'STRING'},
                              'description': 'Archivos para add'},
                    'sub': {'type': 'STRING', 'description': 'Subcomando para stash: push|pop|list'}},
     'required': ['action', 'repo_path']},
)
def git_control(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "status").lower()
    path = parameters.get("path") or "."
    repo = str(Path(path).expanduser().resolve())

    if action == "status":
        rc, out, err = _run_git(["status", "--short", "--branch"], cwd=repo)
        if rc != 0:
            return err or out
        return f"Git status en {repo}:\n{out or '(working tree limpio)'}"

    if action == "log":
        n = int(parameters.get("count", 10))
        rc, out, err = _run_git(["log", f"-{n}", "--oneline", "--no-decorate"], cwd=repo)
        return out if rc == 0 else (err or "Error en log.")

    if action == "diff":
        rc, out, err = _run_git(["diff", "--stat"], cwd=repo)
        return out if rc == 0 else (err or "Error en diff.")

    if action == "add":
        files = parameters.get("files", ".")
        rc, out, err = _run_git(["add", files], cwd=repo)
        return "Archivos staged." if rc == 0 else (err or "Error.")

    if action == "commit":
        msg = parameters.get("message", "")
        if not msg:
            return "Error: falta 'message' para commit."
        rc, out, err = _run_git(["commit", "-m", msg], cwd=repo)
        return out if rc == 0 else (err or out)

    if action == "push":
        rc, out, err = _run_git(["push"], cwd=repo, timeout=60)
        return (out + "\n" + err).strip() or "Push ejecutado."

    if action == "pull":
        rc, out, err = _run_git(["pull"], cwd=repo, timeout=60)
        return (out + "\n" + err).strip() or "Pull ejecutado."

    if action == "branch":
        rc, out, err = _run_git(["branch", "--show-current"], cwd=repo)
        return f"Rama actual: {out}" if rc == 0 else (err or "Error.")

    if action == "clone":
        url = parameters.get("url", "")
        if not url:
            return "Error: falta 'url' para clone."
        dest = parameters.get("destination", "")
        cmd = ["clone", url] + ([dest] if dest else [])
        rc, out, err = _run_git(cmd, timeout=120)
        return (out + "\n" + err).strip() or "Clone completado."

    return f"Acción git '{action}' no soportada. Usa: status, log, diff, add, commit, push, pull, branch, clone."
