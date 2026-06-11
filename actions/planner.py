"""
planner.py — Planner multi-step. Recibe goal complejo, descompone en pasos,
ejecuta cada uno con tool_resolver, replanifica si algo falla.

Flujo:
  1. Recibe `goal` en lenguaje natural
  2. Opcional: consulta recall para planes pasados similares
  3. Llama a Gemini → plan JSON con steps {tool, args, why}
  4. Ejecuta cada step vía tool_resolver.invoke_tool
  5. Si un step falla: re-llama a Gemini con el error → plan revisado para los pasos restantes
  6. Devuelve resumen ejecutivo del plan + resultados

Usar para tareas como:
  - "buscame el precio del RTX 4070, encontrá el mejor y guardalo en mis notas"
  - "compactá las sesiones viejas, después decime cuántas notas tengo"
  - "leé mi último correo de mi jefe y resumímelo"
"""
from __future__ import annotations
import json
import re
import time
from pathlib import Path

from core.tool_resolver import invoke_tool, list_available_tools
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent
API_FILE = BASE_DIR / "config" / "api_keys.json"

MAX_STEPS = 8                # cap de pasos por plan
MAX_REPLANS = 2              # cuántas veces puede replanificar tras fallo
STEP_TIMEOUT_SOFT = 30       # warning si paso tarda más

_SYSTEM = """Eres el planificador de JARVIS. Recibís un objetivo complejo y
devolvés un plan JSON ejecutable.

REGLAS:
- Cada step usa una tool de la lista que te paso
- No inventes tools. Si no hay tool que sirva, dejá la lista vacía y explicá en `cannot_do`.
- Los args de cada step deben ser válidos para esa tool (los conocés por su nombre).
- Step "why" en español, ≤ 80 chars, explica para qué sirve ese paso.
- Plan secuencial: cada step ve los anteriores en su contexto.
- Máximo 8 steps. Si el goal requiere más, simplificá.

FORMATO (devolver SOLO JSON, sin markdown):

{
  "title": "Resumen de 1 línea de qué vas a hacer",
  "steps": [
    {"tool": "web_search", "args": {"query": "..."}, "why": "..."},
    {"tool": "knowledge_base", "args": {"action": "add", "topic": "...", "content": "..."}, "why": "..."}
  ],
  "cannot_do": ""
}

Si no es posible: {"title":"...", "steps":[], "cannot_do":"razón corta"}.
"""


def _get_api_key() -> str:
    try:
        from memory.config_manager import cfg
        return cfg("gemini_api_key", "")
    except Exception:
        return ""

def _call_gemini_plan(goal: str, available_tools: list, prior_failure: str = "", prior_results: list | None = None) -> dict:
    """Pide a Gemini un plan JSON. Reintenta con backoff ante 503."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai no instalado.")

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("Falta gemini_api_key.")

    tools_str = ", ".join(available_tools)
    prompt_parts = [f"Goal del usuario: {goal}\n\nTools disponibles: {tools_str}"]
    if prior_results:
        prompt_parts.append("\nPasos ya ejecutados:")
        for i, r in enumerate(prior_results, 1):
            prompt_parts.append(f"  {i}. {r.get('tool')} → {r.get('result_preview', '')[:120]}")
    if prior_failure:
        prompt_parts.append(f"\n⚠️ Último intento falló: {prior_failure}\nGenerá plan corregido para LO QUE FALTA, no repitas lo hecho.")

    prompt = "\n".join(prompt_parts)
    client = genai.Client(api_key=api_key)

    for model in ("gemini-2.5-flash", "gemini-2.5-flash-lite"):
        for delay in (0, 2, 5):
            if delay:
                time.sleep(delay)
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[
                        types.Part(text=_SYSTEM),
                        types.Part(text=prompt),
                    ])],
                    config=types.GenerateContentConfig(
                        max_output_tokens=2000,
                        response_mime_type="application/json",
                    ),
                )
                raw = (resp.text or "").strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```\s*$", "", raw)
                return json.loads(raw)
            except Exception as e:
                msg = str(e)
                if not any(c in msg for c in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED")):
                    raise

    raise RuntimeError("Gemini saturado, no se pudo generar plan.")


def _looks_like_failure(result: str) -> bool:
    """Heurística: ¿el string parece un mensaje de error?"""
    if not result:
        return True
    low = result.lower()
    indicators = ("error", "failed", "no se encontró", "no encontrado", "no pude",
                  "no soportad", "missing", "no instalado", "timeout", "excepción")
    return any(ind in low for ind in indicators)


def _format_summary(plan: dict, results: list, total_ms: int, replans: int) -> str:
    title = plan.get("title", "(sin título)")
    lines = [f"📋 Plan: {title}",
             f"   Steps: {len(results)}/{len(plan.get('steps', []))}  ·  {total_ms}ms  ·  {replans} replans"]
    for i, r in enumerate(results, 1):
        flag = "✓" if r["success"] else "✗"
        lines.append(f"  {i}. {flag} {r['tool']} → {r['result_preview']}")
    return "\n".join(lines)


@tool(
    name='planner',
    description="Resuelve tareas multi-step descomponiendo el goal en pasos y ejecutándolos. USAR cuando la petición requiere varias tools encadenadas (ej: 'buscame X, encontrá lo mejor, guardalo'). Si es 1 sola tool obvia, NO usar planner — llamar directo.",
    parameters={'type': 'OBJECT',
     'properties': {'goal': {'type': 'STRING',
                             'description': 'Descripción completa de la tarea compleja'},
                    'max_steps': {'type': 'INTEGER', 'description': 'Máx pasos (default 8)'},
                    'stop_on_failure': {'type': 'BOOLEAN',
                                        'description': 'Detener si un paso falla (default true)'},
                    'dry_run': {'type': 'BOOLEAN', 'description': 'Solo mostrar plan sin ejecutar'}},
     'required': ['goal']},
)
def planner(parameters: dict, player=None, speak=None) -> str:
    """
    Planifica + ejecuta una tarea multi-step.

    parameters:
      goal (str): descripción de la tarea
      max_steps (int): override de MAX_STEPS (default 8)
      stop_on_failure (bool): default True. False = continúa aunque un paso falle.
      dry_run (bool): si true, solo genera plan sin ejecutar (preview)
    """
    goal = (parameters.get("goal") or "").strip()
    if not goal:
        return "Error: falta 'goal'."

    max_steps = min(int(parameters.get("max_steps", MAX_STEPS)), MAX_STEPS)
    stop_on_failure = parameters.get("stop_on_failure", True)
    dry_run = parameters.get("dry_run", False)

    available = list_available_tools()
    if player:
        player.write_log(f"📋 Planificando: '{goal[:80]}'")

    # 1. Generar plan inicial
    try:
        plan = _call_gemini_plan(goal, available)
    except Exception as e:
        return f"Error planificando: {e}"

    if plan.get("cannot_do"):
        return f"No es posible: {plan['cannot_do']}"

    steps = (plan.get("steps") or [])[:max_steps]
    if not steps:
        return f"Plan vacío. Razón: {plan.get('cannot_do', '(sin razón)')}"

    if dry_run:
        lines = [f"📋 (DRY RUN) Plan: {plan.get('title', '?')}"]
        for i, s in enumerate(steps, 1):
            lines.append(f"  {i}. {s.get('tool')}({', '.join(s.get('args', {}).keys())}) — {s.get('why', '')}")
        return "\n".join(lines)

    # 2. Ejecutar pasos
    results = []
    replans = 0
    t0 = time.perf_counter()
    i = 0

    while i < len(steps):
        step = steps[i]
        tool_name = step.get("tool", "")
        args = step.get("args") or {}
        why = step.get("why", "")

        if player:
            player.write_log(f"  ▶️ [{i+1}/{len(steps)}] {tool_name}: {why}")

        step_start = time.perf_counter()
        result = invoke_tool(tool_name, args)
        step_ms = int((time.perf_counter() - step_start) * 1000)
        success = not _looks_like_failure(result)

        results.append({
            "step_idx": i,
            "tool": tool_name,
            "args": args,
            "why": why,
            "result": result,
            "result_preview": result[:150],
            "success": success,
            "ms": step_ms,
        })

        if success:
            i += 1
            continue

        # Falló — replan?
        if replans >= MAX_REPLANS:
            if player:
                player.write_log(f"  ❌ Sin más replans. Aborto.")
            if stop_on_failure:
                break
            i += 1
            continue

        if player:
            player.write_log(f"  🔄 Replanificando (intento {replans+1}/{MAX_REPLANS})...")
        replans += 1
        try:
            failure_msg = f"Step {i+1} ({tool_name}) devolvió: {result[:200]}"
            new_plan = _call_gemini_plan(goal, available, prior_failure=failure_msg, prior_results=results)
        except Exception as e:
            if player:
                player.write_log(f"  ⚠️ Replan falló: {e}")
            if stop_on_failure:
                break
            i += 1
            continue

        if new_plan.get("cannot_do"):
            if player:
                player.write_log(f"  ⚠️ Replan dice imposible: {new_plan['cannot_do']}")
            break

        new_steps = new_plan.get("steps") or []
        # Insertar new_steps en lugar del fallido, manteniendo cap
        steps = steps[:i] + new_steps[:max_steps - i]

    total_ms = int((time.perf_counter() - t0) * 1000)
    return _format_summary(plan, results, total_ms, replans)
