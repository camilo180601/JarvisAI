"""
skill_teach.py — Genera skills nuevas a partir de una descripción en lenguaje natural.

Flujo:
  1. Usuario describe la skill por voz
  2. Gemini genera (skill_name, params, requires, código) en JSON
  3. Sandbox: py_compile + ejecución aislada con params mock
  4. Si falla → reintenta hasta 2 veces más pasando el error al LLM
  5. Si pasa → escribe skills/<name>/SKILL.md + skill.py
  6. Caller (main.py) refresca _skill_dispatch + reconecta sesión Gemini

Requiere: gemini_api_key en config/api_keys.json (mismo del Live).
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import py_compile
from pathlib import Path
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = BASE_DIR / "skills"
API_FILE = BASE_DIR / "config" / "api_keys.json"

MAX_ITERATIONS = 3
SANDBOX_TIMEOUT = 10  # segundos

_SYSTEM_PROMPT = """Eres un generador de skills para JARVIS, un asistente Python.

Tu tarea: convertir una descripción en lenguaje natural en una skill ejecutable.

REGLAS DEL CÓDIGO:
- La función entry point DEBE llamarse `run(parameters: dict, player=None, speak=None) -> str`
- DEBE retornar un string descriptivo (no None, no print)
- Cross-platform: usa `core.platform_utils` en lugar de pycaw/winreg/ctypes
- Imports disponibles útiles:
    from core.platform_utils import (
        set_master_volume, change_volume, mute_audio,
        open_application, notify,
        minimize_active_window, maximize_active_window,
    )
- subprocess, pathlib, webbrowser, urllib están permitidos
- NO uses paquetes que no estén en requirements.txt salvo que los declares en requires.packages
- Maneja errores con try/except y retorna mensaje legible
- El código debe ser CORTO (idealmente <40 líneas)

FORMATO DE SALIDA — devuelve SOLO JSON válido, sin markdown, sin explicaciones:

{
  "skill_name": "snake_case_corto",
  "description": "Una línea clara de qué hace (max 80 chars)",
  "parameters": {
    "param_name": {"type": "STRING", "description": "Qué es", "required": false}
  },
  "requires": {
    "packages": [],
    "bins": [],
    "env": []
  },
  "code": "def run(parameters: dict, player=None, speak=None) -> str:\\n    ...\\n    return 'Hecho.'\\n",
  "test_params": {}
}

Si la descripción es ambigua, asume lo más razonable. No pidas aclaración.
"""


def _get_api_key() -> str:
    try:
        from memory.config_manager import cfg
        return cfg("gemini_api_key", "")
    except Exception:
        return ""

def _call_gemini(description: str, previous_error: str = "") -> dict:
    """Llama a Gemini para generar una skill. Devuelve dict parseado o lanza.
    Reintenta con backoff exponencial ante 503/429 (modelos saturados)."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai no instalado.")

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("Falta gemini_api_key en config/api_keys.json.")

    prompt = f"Descripción del usuario:\n{description}\n"
    if previous_error:
        prompt += (
            f"\n⚠️ INTENTO ANTERIOR FALLÓ con este error:\n{previous_error}\n\n"
            "Generá una versión corregida. Mantené el formato JSON exacto."
        )

    client = genai.Client(api_key=api_key)
    # Modelos a probar en orden (si el primero está saturado, cae al segundo)
    models = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    last_err = None
    import time
    for model in models:
        for delay in (0, 2, 6):  # 3 intentos por modelo: inmediato, 2s, 6s
            if delay:
                time.sleep(delay)
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[
                        types.Part(text=_SYSTEM_PROMPT),
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
                last_err = e
                msg = str(e)
                # Solo reintentar en errores transitorios
                if not any(c in msg for c in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "timeout")):
                    raise
    raise RuntimeError(f"Gemini saturado en {len(models)} modelos. Último error: {last_err}")


def _validate_spec(spec: dict) -> tuple[bool, str]:
    """Valida estructura mínima."""
    required_keys = ("skill_name", "description", "parameters", "requires", "code")
    for k in required_keys:
        if k not in spec:
            return False, f"Falta campo '{k}' en la respuesta."
    name = spec["skill_name"]
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        return False, f"skill_name inválido: '{name}' (usar snake_case)"
    if "def run(" not in spec["code"]:
        return False, "El código no define `def run(...)`"
    return True, ""


def _write_skill_files(spec: dict, skill_dir: Path) -> None:
    """Escribe SKILL.md + skill.py en skill_dir."""
    skill_dir.mkdir(parents=True, exist_ok=True)

    # SKILL.md con frontmatter
    fm_lines = [
        "---",
        f"name: {spec['skill_name']}",
        f"description: {spec['description']}",
    ]

    req = spec.get("requires") or {}
    fm_lines.append("requires:")
    fm_lines.append(f"  packages: {req.get('packages', [])}")
    fm_lines.append(f"  bins: {req.get('bins', [])}")
    fm_lines.append(f"  env: {req.get('env', [])}")

    params = spec.get("parameters") or {}
    if params:
        fm_lines.append("parameters:")
        for pname, pdef in params.items():
            fm_lines.append(f"  {pname}:")
            fm_lines.append(f"    type: {pdef.get('type', 'STRING')}")
            fm_lines.append(f"    description: {pdef.get('description', '')}")
            if pdef.get("required"):
                fm_lines.append(f"    required: true")
    else:
        fm_lines.append("parameters: {}")

    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append(f"# {spec['skill_name']}")
    fm_lines.append("")
    fm_lines.append("Skill auto-generada por `skill_teach`.")

    (skill_dir / "SKILL.md").write_text("\n".join(fm_lines), encoding="utf-8")
    (skill_dir / "skill.py").write_text(spec["code"], encoding="utf-8")


def _sandbox_test(skill_dir: Path, test_params: dict) -> tuple[bool, str]:
    """Compila + ejecuta skill.py en subproceso aislado.
    Devuelve (ok, mensaje/error)."""
    skill_py = skill_dir / "skill.py"

    # 1. py_compile
    try:
        py_compile.compile(str(skill_py), doraise=True)
    except py_compile.PyCompileError as e:
        return False, f"Sintaxis inválida:\n{e.msg}"

    # 2. Ejecución aislada
    params_json = json.dumps(test_params)
    code = f"""
import sys
sys.path.insert(0, {str(BASE_DIR)!r})
from importlib.util import spec_from_file_location, module_from_spec
spec = spec_from_file_location("test_skill", {str(skill_py)!r})
mod = module_from_spec(spec)
spec.loader.exec_module(mod)
import json
result = mod.run(json.loads({params_json!r}), player=None, speak=None)
if result is None:
    print("__ERROR__: run() devolvió None")
    sys.exit(1)
if not isinstance(result, str):
    print(f"__ERROR__: run() devolvió {{type(result).__name__}}, esperaba str")
    sys.exit(1)
print("__OK__:" + str(result)[:200])
"""
    try:
        env = os.environ.copy()
        # No usar PYTHONPATH para evitar que sitecustomize.py de BASE_DIR rompa stdlib.
        # En vez de eso, BASE_DIR se agrega a sys.path dentro del código de test.
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
        r = subprocess.run(
            [sys.executable, "-I", "-c", code],  # -I: aislado, sin sitecustomize
            capture_output=True, text=True,
            timeout=SANDBOX_TIMEOUT, env=env,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode == 0 and "__OK__" in out:
            preview = out.split("__OK__:", 1)[1]
            return True, f"Ejecución OK. Output preview: {preview}"
        return False, f"Stderr:\n{err}\nStdout:\n{out}"
    except subprocess.TimeoutExpired:
        return False, f"Timeout ({SANDBOX_TIMEOUT}s) — posible loop infinito o I/O bloqueante."
    except Exception as e:
        return False, f"Sandbox excepción: {e}"


@tool(
    name='skill_teach',
    description="Aprende una skill nueva: genera carpeta skills/<name>/SKILL.md + skill.py vía Gemini, la testea en sandbox, queda activa sin reiniciar. USAR cuando el usuario diga: 'aprendete', 'aprende a hacer X', 'creá una skill para Y', 'cuando diga X hacé Y como rutina'.",
    parameters={'type': 'OBJECT',
     'properties': {'description': {'type': 'STRING',
                                    'description': 'Descripción natural de qué tiene que hacer la '
                                                   'skill (lo que dijo el usuario)'},
                    'name_hint': {'type': 'STRING',
                                  'description': 'Opcional. Nombre sugerido en snake_case (ej: '
                                                 'modo_concentracion)'}},
     'required': ['description']},
)
def skill_teach(parameters: dict, player=None, speak=None) -> str:
    """
    Genera una skill nueva a partir de descripción natural.
    Caller debe refrescar dispatch + reconectar después si retorna éxito.

    Parámetros:
      description: descripción de qué hacer (obligatorio)
      name_hint: nombre sugerido (opcional, snake_case)
    """
    description = (parameters.get("description") or "").strip()
    if not description:
        return "Error: falta 'description' (qué querés que aprenda)."

    name_hint = (parameters.get("name_hint") or "").strip()
    if name_hint:
        description = f"[Sugerencia de nombre: {name_hint}]\n{description}"

    if player:
        player.write_log(f"📚 Aprendiendo skill: '{description[:80]}'...")

    previous_error = ""
    spec = None
    for attempt in range(1, MAX_ITERATIONS + 1):
        if player:
            player.write_log(f"  🤖 Intento {attempt}/{MAX_ITERATIONS}: generando código...")

        try:
            spec = _call_gemini(description, previous_error)
        except Exception as e:
            return f"Error consultando a Gemini: {e}"

        ok, msg = _validate_spec(spec)
        if not ok:
            previous_error = f"Validación falló: {msg}"
            if player:
                player.write_log(f"  ⚠️ {msg}")
            continue

        skill_name = spec["skill_name"]
        skill_dir = SKILLS_DIR / skill_name

        # Backup si ya existe (versionado simple)
        if skill_dir.exists():
            from datetime import datetime
            backup = SKILLS_DIR / f"{skill_name}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            skill_dir.rename(backup)
            if player:
                player.write_log(f"  📦 Skill existente respaldada en {backup.name}")

        _write_skill_files(spec, skill_dir)
        if player:
            player.write_log(f"  ✏️  Escrito skills/{skill_name}/")

        test_params = spec.get("test_params") or {}
        sandbox_ok, sandbox_msg = _sandbox_test(skill_dir, test_params)

        if sandbox_ok:
            if player:
                player.write_log(f"  ✅ Sandbox OK: {sandbox_msg[:120]}")
            return (
                f"Skill '{skill_name}' creada y validada en {attempt} intento(s). "
                f"Descripción: {spec['description']}. "
                f"Sandbox dijo: {sandbox_msg[:100]}"
            )

        # Falló sandbox → preparar reintento
        previous_error = f"Sandbox falló:\n{sandbox_msg[:800]}"
        if player:
            player.write_log(f"  ❌ Sandbox falló: {sandbox_msg[:120]}")

    # Agotó intentos
    final_name = spec.get("skill_name", "(desconocido)") if spec else "(no generado)"
    return (
        f"No pude generar una skill funcional para '{description[:60]}' después de "
        f"{MAX_ITERATIONS} intentos. Último error:\n{previous_error[:300]}\n\n"
        f"Quedó como skills/{final_name}/ pero falla. Podés editarla a mano o pedirme otra forma."
    )
