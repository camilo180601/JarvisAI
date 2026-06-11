"""
loop.py — Loop agéntico (while-tool-use) + dispatch de tools de código.

Espejo del query() de Claude Code: el cerebro pide tools, se ejecutan con
validación, el resultado vuelve, y se repite hasta que el modelo deja de pedir
tools (respuesta final) o se alcanza max_steps.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from core.code_agent import tools as T
from core.code_agent.brain import make_conversation

# Tools de solo-lectura → se pueden correr en paralelo (como partitionToolCalls de CC)
_READ_ONLY_TOOLS = {"read_file", "grep", "glob", "list_dir"}
_COMPACT_SIZE = 120_000   # chars aprox de historial antes de compactar

# Esquemas (JSON Schema) de las tools que ve el cerebro
TOOL_SPECS = [
    {"name": "read_file", "description": "Lee un archivo (formato 'nº\\ttexto'). OBLIGATORIO leer antes de editar.",
     "parameters": {"type": "object", "properties": {
         "file_path": {"type": "string", "description": "Ruta del archivo"},
         "offset": {"type": "integer", "description": "Línea inicial (opcional)"},
         "limit": {"type": "integer", "description": "Cuántas líneas (opcional)"}},
         "required": ["file_path"]}},
    {"name": "edit_file", "description": "Reemplazo EXACTO de string. Falla si no leíste el archivo o si old_string no es único (usá replace_all). old_string='' crea archivo nuevo.",
     "parameters": {"type": "object", "properties": {
         "file_path": {"type": "string"}, "old_string": {"type": "string"},
         "new_string": {"type": "string"}, "replace_all": {"type": "boolean"}},
         "required": ["file_path", "old_string", "new_string"]}},
    {"name": "write_file", "description": "Crea o sobreescribe un archivo. Si ya existe, hay que leerlo antes. Preferí edit_file para cambios puntuales.",
     "parameters": {"type": "object", "properties": {
         "file_path": {"type": "string"}, "content": {"type": "string"}},
         "required": ["file_path", "content"]}},
    {"name": "bash", "description": "Ejecuta un comando de shell en el proyecto. Comandos destructivos requieren confirmación del usuario.",
     "parameters": {"type": "object", "properties": {
         "command": {"type": "string"}, "timeout": {"type": "integer"},
         "run_in_background": {"type": "boolean"}}, "required": ["command"]}},
    {"name": "grep", "description": "Busca un patrón (regex) en el contenido de los archivos.",
     "parameters": {"type": "object", "properties": {
         "pattern": {"type": "string"}, "path": {"type": "string"},
         "glob": {"type": "string", "description": "Filtro de nombre, ej '*.py'"}}, "required": ["pattern"]}},
    {"name": "glob", "description": "Busca archivos por patrón (ej '**/*.py').",
     "parameters": {"type": "object", "properties": {
         "pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}},
    {"name": "list_dir", "description": "Lista el contenido de un directorio.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": []}},
]

_DISPATCH = {
    "read_file": T.read_file, "edit_file": T.edit_file, "write_file": T.write_file,
    "bash": T.bash, "grep": T.grep, "glob": T.glob_search, "list_dir": T.list_dir,
}


def _dispatch(ctx: T.AgentContext, name: str, args: dict) -> tuple[str, bool]:
    fn = _DISPATCH.get(name)
    if not fn:
        return f"No existe la tool '{name}'.", True
    args = {k: v for k, v in (args or {}).items() if v is not None}
    try:
        return fn(ctx, **args), False
    except T.ToolError as e:
        return f"<tool_use_error>{e}</tool_use_error>", True
    except TypeError as e:
        return f"<tool_use_error>Parámetros inválidos para {name}: {e}</tool_use_error>", True
    except Exception as e:
        return f"<tool_use_error>Error en {name}: {e}</tool_use_error>", True


def _run_calls(ctx: T.AgentContext, calls: list) -> list:
    """Ejecuta las tools: batches consecutivos read-only en paralelo, escrituras en serie."""
    results: list = [None] * len(calls)
    i = 0
    while i < len(calls):
        if calls[i]["name"] in _READ_ONLY_TOOLS:
            j = i
            while j < len(calls) and calls[j]["name"] in _READ_ONLY_TOOLS:
                j += 1
            batch = list(range(i, j))
            with ThreadPoolExecutor(max_workers=min(6, len(batch))) as ex:
                futs = {ex.submit(_dispatch, ctx, calls[k]["name"], calls[k].get("input")): k
                        for k in batch}
                for fut, k in futs.items():
                    content, is_err = fut.result()
                    results[k] = {"id": calls[k]["id"], "name": calls[k]["name"],
                                  "content": content, "is_error": is_err}
            i = j
        else:
            content, is_err = _dispatch(ctx, calls[i]["name"], calls[i].get("input"))
            results[i] = {"id": calls[i]["id"], "name": calls[i]["name"],
                          "content": content, "is_error": is_err}
            i += 1
    return results


def run_agent(goal: str, project_path: Path, provider: str, model: str, system: str,
              log: Callable[[str], None] | None = None,
              confirm: Callable[[str], bool] | None = None,
              plan_mode: bool = False,
              max_steps: int = 40) -> dict:
    """Corre el loop. Devuelve {done, final, steps, error?}."""
    def _log(m):
        if log:
            try:
                log(m)
            except Exception:
                pass

    ctx = T.AgentContext(project_path=Path(project_path), confirm=confirm, log=_log,
                         plan_mode=plan_mode)
    try:
        conv = make_conversation(provider, model, system, TOOL_SPECS)
    except Exception as e:
        return {"done": False, "final": "", "steps": 0, "changed": [],
                "error": f"No pude iniciar el cerebro {provider}:{model} — {e}"}

    conv.add_user(goal)
    for step in range(1, max_steps + 1):
        try:
            r = conv.step()
        except Exception as e:
            return {"done": False, "final": "", "steps": step, "changed": sorted(ctx.changed),
                    "error": f"Error del modelo ({provider}:{model}): {str(e)[:200]}"}
        if r.get("text"):
            _log(f"💭 {r['text'][:200]}")
        calls = r.get("tool_calls") or []
        if not calls:
            return {"done": True, "final": r.get("text") or "(sin resumen)",
                    "steps": step, "changed": sorted(ctx.changed)}
        results = _run_calls(ctx, calls)
        # Compactación: si el historial creció mucho, stubear resultados viejos
        try:
            if hasattr(conv, "size") and conv.size() > _COMPACT_SIZE:
                conv.compact()
                _log("  🗜️ compacté el contexto (tarea larga)")
        except Exception:
            pass
        try:
            conv.add_tool_results(results)
        except Exception as e:
            return {"done": False, "final": "", "steps": step, "changed": sorted(ctx.changed),
                    "error": f"Error pasando resultados al modelo: {str(e)[:160]}"}
    return {"done": False, "final": f"Alcancé el máximo de {max_steps} pasos sin terminar.",
            "steps": max_steps, "changed": sorted(ctx.changed)}
