"""
safety.py — Capa de seguridad para el code_agent.

Conservador a propósito (decisión del usuario): NO cambia de rama, NO mergea a main,
NO pushea por su cuenta. Solo:
  • muestra el diff de los archivos que tocó el agente
  • corre los tests/smoke si existen y reporta honestamente
  • commit (= "desplegar", explícito) o revert de SOLO esos archivos
"""
from __future__ import annotations
import subprocess
from pathlib import Path


def _git(project_path: Path, *args, timeout: int = 30) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=str(project_path),
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


def is_git_repo(project_path: Path) -> bool:
    code, out = _git(project_path, "rev-parse", "--is-inside-work-tree")
    return code == 0 and "true" in out


def current_branch(project_path: Path) -> str:
    _, out = _git(project_path, "rev-parse", "--abbrev-ref", "HEAD")
    return out.strip()


def diff_for(project_path: Path, files: list[str]) -> str:
    """Diff de los archivos cambiados por el agente (tracked + nuevos)."""
    if not files:
        return "(el agente no modificó archivos)"
    if not is_git_repo(project_path):
        return f"{len(files)} archivo(s) modificado(s) (no es repo git, no hay diff):\n" + \
               "\n".join(f"  • {f}" for f in files)
    rel = [str(Path(f)) for f in files]
    # intent-to-add para que los archivos nuevos aparezcan en el diff
    _git(project_path, "add", "-N", *rel)
    code, out = _git(project_path, "diff", "--stat", "--", *rel)
    code2, full = _git(project_path, "diff", "--", *rel)
    diff = (out.strip() + "\n\n" + full.strip()).strip()
    if len(diff) > 6000:
        diff = diff[:6000] + "\n… (diff truncado)"
    return diff or "(sin diferencias detectables)"


def syntax_check(project_path: Path, files: list[str]) -> str:
    """Chequeo INSTANTÁNEO de sintaxis (ast.parse) de los .py cambiados.
    Corre antes de los tests (que tardan minutos): atrapa código roto al toque."""
    import ast
    pyfiles = [f for f in files if str(f).endswith(".py")]
    if not pyfiles:
        return ""
    broken = []
    for f in pyfiles:
        p = Path(f)
        if not p.is_absolute():
            p = project_path / p
        try:
            ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:
            broken.append(f"{p.name}:{e.lineno}: {e.msg}")
        except Exception:
            pass
    if broken:
        return "❌ SINTAXIS ROTA en " + "; ".join(broken)
    return f"✅ Sintaxis OK ({len(pyfiles)} archivo(s) .py)"


def run_tests(project_path: Path) -> str:
    """Corre smoke_test.py o pytest si existen. Reporta honesto (pasan/fallan)."""
    smoke = project_path / "smoke_test.py"
    py = _python_bin(project_path)
    if smoke.exists():
        code, out = _git_safe_run([py, "smoke_test.py"], project_path, timeout=180)
        tail = "\n".join(out.strip().splitlines()[-15:])
        return f"smoke_test.py → {'✅ PASARON' if code == 0 else '❌ FALLARON'} (exit {code})\n{tail}"
    if (project_path / "pytest.ini").exists() or (project_path / "tests").exists():
        code, out = _git_safe_run([py, "-m", "pytest", "-q"], project_path, timeout=300)
        tail = "\n".join(out.strip().splitlines()[-15:])
        return f"pytest → {'✅ PASARON' if code == 0 else '❌ FALLARON'} (exit {code})\n{tail}"
    return "(no encontré tests/smoke para correr — no pude verificar automáticamente)"


def _python_bin(project_path: Path) -> str:
    for c in (project_path / ".venv" / "bin" / "python", project_path / "venv" / "bin" / "python"):
        if c.exists():
            return str(c)
    return "python3"


def _git_safe_run(cmd, project_path, timeout):
    try:
        r = subprocess.run(cmd, cwd=str(project_path), capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 1, f"(timeout {timeout}s)"
    except Exception as e:
        return 1, str(e)


def commit(project_path: Path, files: list[str], message: str) -> str:
    """'Desplegar' explícito: commitea SOLO los archivos del agente en la rama actual."""
    if not is_git_repo(project_path):
        return "No es un repo git — los cambios ya están en disco, no hay nada que commitear."
    if not files:
        return "El agente no cambió archivos."
    rel = [str(Path(f)) for f in files]
    code, out = _git(project_path, "add", *rel)
    if code != 0:
        return f"✗ git add falló: {out[:160]}"
    code, out = _git(project_path, "commit", "-m", message)
    if code != 0:
        return f"✗ git commit falló: {out[:200]}"
    branch = current_branch(project_path)
    return f"✓ Commit creado en la rama '{branch}' ({len(files)} archivo(s)). Para subirlo: 'git push' cuando quieras."


def revert(project_path: Path, files: list[str]) -> str:
    """Descarta los cambios del agente: revierte tracked, borra los nuevos."""
    if not files:
        return "Nada que descartar."
    reverted, deleted = 0, 0
    for f in files:
        p = Path(f)
        # ¿está trackeado en git?
        code, _ = _git(project_path, "ls-files", "--error-unmatch", str(p))
        if code == 0:
            c, _ = _git(project_path, "checkout", "HEAD", "--", str(p))
            if c == 0:
                reverted += 1
        else:
            try:
                p.unlink(missing_ok=True)
                deleted += 1
            except Exception:
                pass
    return f"✓ Descartado: {reverted} revertido(s), {deleted} archivo(s) nuevo(s) borrado(s)."
