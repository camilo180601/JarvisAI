"""
tools.py — Tools de código para el agente (espejo de Claude Code).

Reglas portadas de Claude Code (FileRead/FileEdit/FileWrite/Bash):
  • Read devuelve formato `cat -n` (nº de línea + tab) y MARCA el archivo como leído.
  • Edit es reemplazo EXACTO de string: falla si no leíste el archivo, falla si
    old_string no es único (salvo replace_all), old_string="" crea archivo.
  • Write exige haber leído el archivo si ya existe.
  • Bash pide confirmación para comandos peligrosos; nunca destructivo solo.
  • Todo path queda dentro del project_path (allowlist) — no toca afuera.
"""
from __future__ import annotations
import os
import re
import sys
import shutil
import subprocess
import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MAX_LINES = 2000


class ToolError(Exception):
    """Error de validación → vuelve al modelo como tool_result is_error."""


@dataclass
class AgentContext:
    project_path: Path
    read_files: dict = field(default_factory=dict)   # path_resuelto -> contenido leído
    changed: set = field(default_factory=set)         # archivos creados/editados por el agente
    confirm: Callable[[str], bool] | None = None      # confirmación de comandos peligrosos
    log: Callable[[str], None] | None = None
    plan_mode: bool = False                           # True = solo lectura, no escribe nada

    def _say(self, m: str):
        if self.log:
            try:
                self.log(m)
            except Exception:
                pass


# ───────────────────────── helpers ─────────────────────────

def _resolve(ctx: AgentContext, file_path: str) -> Path:
    """Resuelve un path y verifica que quede dentro del proyecto (allowlist)."""
    p = Path(file_path)
    if not p.is_absolute():
        p = ctx.project_path / p
    p = p.resolve()
    root = ctx.project_path.resolve()
    if root != p and root not in p.parents:
        raise ToolError(f"Por seguridad solo puedo tocar archivos dentro de {root}. "
                        f"'{file_path}' queda afuera.")
    return p


def _cat_n(text: str, start: int = 1) -> str:
    out = []
    for i, line in enumerate(text.splitlines(), start):
        out.append(f"{i}\t{line}")
    return "\n".join(out)


# ── Tolerancia de Edit (portado de Claude Code FileEditTool/utils.ts) ──
_CURLY = {"‘": "'", "’": "'", "“": '"', "”": '"'}
_LINE_PREFIX = re.compile(r"^\s*\d+\t")  # "123\t" del output de read_file


def _norm_quotes(s: str) -> str:
    for k, v in _CURLY.items():
        s = s.replace(k, v)
    return s


def _diagnostics(p: Path) -> str:
    """Chequeo post-edición (equivalente liviano al LSP de opencode). Devuelve el
    error para que el agente lo corrija, o '' si está OK."""
    try:
        if p.suffix == ".py":
            py = sys.executable or "python3"
            r = subprocess.run([py, "-m", "py_compile", str(p)],
                               capture_output=True, text=True, timeout=20)
            if r.returncode != 0:
                err = (r.stderr or r.stdout).strip().splitlines()
                return "\n⚠️ Error de sintaxis introducido — corregilo:\n" + "\n".join(err[-4:])
        elif p.suffix == ".json":
            import json as _json
            _json.loads(p.read_text(encoding="utf-8"))
    except subprocess.TimeoutExpired:
        return ""
    except Exception as e:
        if p.suffix == ".json":
            return f"\n⚠️ JSON inválido — corregilo: {str(e)[:120]}"
    return ""


def _strip_prefixes(s: str) -> str:
    return "\n".join(_LINE_PREFIX.sub("", ln) for ln in s.split("\n"))


def _levenshtein(a: str, b: str) -> int:
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _line_trimmed_matches(content: str, find: str) -> list[str]:
    """Portado de opencode LineTrimmedReplacer: matchea por línea ignorando indentación/espacios."""
    olines = content.split("\n")
    slines = find.split("\n")
    if slines and slines[-1] == "":
        slines.pop()
    if not slines:
        return []
    out = []
    for i in range(len(olines) - len(slines) + 1):
        if all(olines[i + j].strip() == slines[j].strip() for j in range(len(slines))):
            start = sum(len(olines[k]) + 1 for k in range(i))
            end = start
            for k in range(len(slines)):
                end += len(olines[i + k]) + (1 if k < len(slines) - 1 else 0)
            out.append(content[start:end])
    return out


def _block_anchor_match(content: str, find: str) -> str | None:
    """Portado de opencode BlockAnchorReplacer: para bloques 3+ líneas, ancla 1ª y última
    línea y elige el mejor candidato por similitud (Levenshtein) de las del medio."""
    olines = content.split("\n")
    slines = find.split("\n")
    if slines and slines[-1] == "":
        slines.pop()
    if len(slines) < 3:
        return None
    first, last = slines[0].strip(), slines[-1].strip()
    cands = []
    for i in range(len(olines)):
        if olines[i].strip() != first:
            continue
        for j in range(i + 2, len(olines)):
            if olines[j].strip() == last:
                cands.append((i, j))
                break
    if not cands:
        return None

    def _sub(i, j):
        start = sum(len(olines[k]) + 1 for k in range(i))
        end = start
        for k in range(i, j + 1):
            end += len(olines[k]) + (1 if k < j else 0)
        return content[start:end]

    if len(cands) == 1:
        return _sub(*cands[0])
    best, best_sim = None, -1.0
    for (i, j) in cands:
        n = min(len(slines) - 2, (j - i + 1) - 2)
        sim = 1.0
        if n > 0:
            acc = 0.0
            for k in range(1, n + 1):
                o, s = olines[i + k].strip(), slines[k].strip()
                m = max(len(o), len(s))
                if m:
                    acc += 1 - _levenshtein(o, s) / m
            sim = acc / n
        if sim > best_sim:
            best_sim, best = sim, (i, j)
    return _sub(*best) if best and best_sim >= 0.3 else None


def _resolve_match(content: str, old: str) -> str | None:
    """Substring REAL presente en content que corresponde a old, o None.
    Estrategias (portadas de Claude Code + opencode), de más estricta a más tolerante:
    exacto → comillas normalizadas → sin prefijo de línea → líneas trim → anclas de bloque."""
    if old in content:
        return old
    nc, no = _norm_quotes(content), _norm_quotes(old)
    idx = nc.find(no)
    if idx != -1:
        return content[idx: idx + len(old)]
    stripped = _strip_prefixes(old)
    if stripped != old and stripped:
        if stripped in content:
            return stripped
        idx = nc.find(_norm_quotes(stripped))
        if idx != -1:
            return content[idx: idx + len(stripped)]
    # opencode: líneas con trim (tolera indentación/espacios)
    lt = _line_trimmed_matches(content, old)
    if len(set(lt)) == 1:
        return lt[0]
    # opencode: anclas de bloque (bloques grandes con líneas del medio algo distintas)
    ba = _block_anchor_match(content, old)
    if ba:
        return ba
    return None


# ───────────────────────── READ ─────────────────────────

def read_file(ctx: AgentContext, file_path: str, offset: int | None = None,
              limit: int | None = None) -> str:
    p = _resolve(ctx, file_path)
    if not p.exists():
        raise ToolError(f"El archivo no existe: {p}")
    if p.is_dir():
        raise ToolError(f"Es un directorio, no un archivo: {p}. Usá list_dir o glob.")
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise ToolError(f"No pude leer {p}: {e}")
    # Registrar como leído (read-before-edit + detección de cambios)
    ctx.read_files[str(p)] = content
    if content == "":
        return "(El archivo existe pero está vacío.)"
    lines = content.splitlines()
    start = (offset or 1)
    if offset or limit:
        s = max(0, (offset or 1) - 1)
        e = s + (limit or MAX_LINES)
        chunk = lines[s:e]
        return _cat_n("\n".join(chunk), start=s + 1)
    if len(lines) > MAX_LINES:
        chunk = lines[:MAX_LINES]
        return _cat_n("\n".join(chunk)) + f"\n\n… (mostrando {MAX_LINES} de {len(lines)} líneas; usá offset/limit para el resto)"
    return _cat_n(content)


# ───────────────────────── EDIT ─────────────────────────

def edit_file(ctx: AgentContext, file_path: str, old_string: str,
              new_string: str, replace_all: bool = False) -> str:
    if ctx.plan_mode:
        raise ToolError("MODO PLAN: no puedo escribir. Proponé el cambio en tu resumen final; "
                        "el usuario lo ejecutará sin plan.")
    if old_string == new_string:
        raise ToolError("No hay cambios: old_string y new_string son idénticos.")
    p = _resolve(ctx, file_path)

    # Crear archivo nuevo: old_string vacío
    if old_string == "":
        if p.exists() and p.read_text(encoding="utf-8", errors="replace").strip():
            raise ToolError(f"{p} ya existe y no está vacío. Para crear usá un archivo nuevo; "
                            "para reescribir usá write_file (tras leerlo).")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new_string, encoding="utf-8")
        ctx.read_files[str(p)] = new_string
        ctx.changed.add(str(p))
        ctx._say(f"  ✎ creado {p.name}")
        return f"OK: archivo creado {p}" + _diagnostics(p)

    if not p.exists():
        raise ToolError(f"El archivo no existe: {p}")
    # read-before-edit
    if str(p) not in ctx.read_files:
        raise ToolError("El archivo no fue leído todavía. Leelo con read_file antes de editarlo.")
    content = p.read_text(encoding="utf-8", errors="replace")
    # detección de cambio externo
    if ctx.read_files.get(str(p)) != content:
        ctx.read_files[str(p)] = content  # re-sincronizar
    actual = _resolve_match(content, old_string)
    if actual is None:
        raise ToolError(f"No encontré el texto a reemplazar en el archivo.\nString: {old_string[:200]}")
    matches = content.count(actual)
    if matches > 1 and not replace_all:
        raise ToolError(f"Encontré {matches} coincidencias de old_string pero replace_all es false. "
                        "Dale más contexto para que sea único, o usá replace_all=true.\n"
                        f"String: {old_string[:200]}")
    new_content = content.replace(actual, new_string) if replace_all \
        else content.replace(actual, new_string, 1)
    p.write_text(new_content, encoding="utf-8")
    ctx.read_files[str(p)] = new_content
    ctx.changed.add(str(p))
    n = matches if replace_all else 1
    ctx._say(f"  ✎ editado {p.name} ({n} reemplazo{'s' if n > 1 else ''})")
    return f"OK: {p} editado ({n} reemplazo{'s' if n > 1 else ''})." + _diagnostics(p)


# ───────────────────────── WRITE ─────────────────────────

def write_file(ctx: AgentContext, file_path: str, content: str) -> str:
    if ctx.plan_mode:
        raise ToolError("MODO PLAN: no puedo escribir. Proponé el archivo en tu resumen final.")
    p = _resolve(ctx, file_path)
    if p.exists() and str(p) not in ctx.read_files:
        raise ToolError("El archivo ya existe y no lo leíste. Leelo con read_file antes de sobreescribir "
                        "(o usá edit_file para cambios puntuales).")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    ctx.read_files[str(p)] = content
    ctx.changed.add(str(p))
    ctx._say(f"  ✎ escrito {p.name}")
    return f"OK: {p} escrito ({len(content.splitlines())} líneas)." + _diagnostics(p)


# ───────────────────────── BASH ─────────────────────────

_DANGEROUS = [
    r"\brm\s+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)\b", r"\brm\s+-rf\b", r"\bsudo\b",
    r"\bgit\s+push\b.*--force", r"\bgit\s+push\s+-f\b", r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-[a-z]*f", r"\bgit\s+checkout\s+\.", r"\bgit\s+restore\s+\.",
    r"\bdd\b", r"\bmkfs", r">\s*/dev/", r":\(\)\s*\{", r"\bshutdown\b", r"\breboot\b",
    r"\bkillall\b", r"\bchmod\s+-R\b", r"\bgit\s+branch\s+-D\b", r"--no-verify",
]


def _is_dangerous(cmd: str) -> bool:
    return any(re.search(p, cmd) for p in _DANGEROUS)


# Allowlist de comandos de SOLO LECTURA (portado de Claude Code readOnlyValidation.ts)
_READ_ONLY = {"ls", "cat", "head", "tail", "wc", "grep", "rg", "find", "pwd", "echo",
              "which", "type", "file", "stat", "du", "df", "tree", "diff", "sort", "uniq",
              "cut", "awk", "sed", "env", "printenv", "date", "whoami", "hostname", "uname",
              "ps", "top", "cat", "less", "more", "realpath", "dirname", "basename"}
_GIT_READ_ONLY = {"status", "log", "diff", "show", "branch", "remote", "config", "ls-files",
                  "rev-parse", "describe", "blame", "shortlog", "tag"}


def _is_read_only_cmd(cmd: str) -> bool:
    parts = cmd.strip().split()
    if not parts:
        return False
    head = parts[0]
    if head == "git":
        return len(parts) > 1 and parts[1] in _GIT_READ_ONLY
    return head in _READ_ONLY


def bash(ctx: AgentContext, command: str, timeout: int = 120,
         run_in_background: bool = False) -> str:
    if ctx.plan_mode and not _is_read_only_cmd(command):
        raise ToolError("MODO PLAN: solo permito comandos de lectura (ls, cat, git status, etc).")
    if _is_dangerous(command):
        allowed = ctx.confirm(command) if ctx.confirm else False
        if not allowed:
            raise ToolError(f"Comando potencialmente destructivo bloqueado (requiere confirmación del usuario): {command}")
    ctx._say(f"  $ {command[:80]}")
    try:
        if run_in_background:
            subprocess.Popen(command, shell=True, cwd=str(ctx.project_path),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "OK: comando lanzado en background."
        r = subprocess.run(command, shell=True, cwd=str(ctx.project_path),
                           capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
        out = out.strip()
        if len(out) > 8000:
            out = out[:8000] + "\n… (salida truncada)"
        return f"(exit {r.returncode})\n{out}" if out else f"(exit {r.returncode}, sin salida)"
    except subprocess.TimeoutExpired:
        raise ToolError(f"Timeout {timeout}s ejecutando: {command}")
    except Exception as e:
        raise ToolError(f"Error ejecutando: {e}")


# ───────────────────────── GREP / GLOB / LIST ─────────────────────────

def grep(ctx: AgentContext, pattern: str, path: str | None = None,
         glob: str | None = None) -> str:
    base = _resolve(ctx, path) if path else ctx.project_path
    # ripgrep si está (rapidísimo en repos grandes)
    rg = shutil.which("rg")
    if rg:
        args = [rg, "-n", "--no-heading", "-m", "100"]
        if glob:
            args += ["-g", glob]
        args += [pattern, str(base)]
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=30)
            out = (r.stdout or "").strip()
            if out:
                return "\n".join(out.splitlines()[:100])
            if r.returncode in (0, 1):
                return f"Sin coincidencias para '{pattern}'."
        except Exception:
            pass  # fallback a Python
    try:
        rx = re.compile(pattern)
    except re.error as e:
        raise ToolError(f"Regex inválida: {e}")
    hits = []
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in skip]
        for fn in files:
            if glob and not fnmatch.fnmatch(fn, glob):
                continue
            fp = Path(root) / fn
            try:
                for i, line in enumerate(fp.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{fp}:{i}: {line.strip()[:160]}")
                        if len(hits) >= 100:
                            return "\n".join(hits) + "\n… (100+ resultados, refiná)"
            except Exception:
                continue
    return "\n".join(hits) if hits else f"Sin coincidencias para '{pattern}'."


def glob_search(ctx: AgentContext, pattern: str, path: str | None = None) -> str:
    base = _resolve(ctx, path) if path else ctx.project_path
    matches = [str(p) for p in base.rglob(pattern)
               if not any(s in p.parts for s in (".git", "node_modules", "__pycache__", ".venv"))]
    matches = matches[:200]
    return "\n".join(matches) if matches else f"Sin archivos para '{pattern}'."


def list_dir(ctx: AgentContext, path: str | None = None) -> str:
    base = _resolve(ctx, path) if path else ctx.project_path
    if not base.exists():
        raise ToolError(f"No existe: {base}")
    if base.is_file():
        return str(base)
    items = []
    for p in sorted(base.iterdir()):
        if p.name.startswith(".") and p.name not in (".env.example",):
            continue
        items.append(f"{'📁 ' if p.is_dir() else '   '}{p.name}")
    return "\n".join(items) if items else "(vacío)"
