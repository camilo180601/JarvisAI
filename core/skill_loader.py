"""
skill_loader.py — Descubre y carga skills tipo OpenClaw (carpeta + SKILL.md).

Cada skill vive en `skills/<name>/` con:
  - SKILL.md  → metadata (YAML frontmatter) + docs
  - skill.py  → implementación con `def run(parameters, player=None, speak=None) -> str`

SKILL.md frontmatter ejemplo:
    ---
    name: web_search
    description: Búsqueda web vía DuckDuckGo
    requires:
      packages: [duckduckgo-search]
      bins: []
      auth: []
    parameters:
      query:
        type: STRING
        description: Search query
        required: true
    ---
    # Markdown docs aquí (opcional)

El loader convierte cada SKILL.md en un tool declaration compatible con Gemini
y expone un dispatcher unificado.
"""
from __future__ import annotations
import importlib.util
import shutil
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = BASE_DIR / "skills"


# ── Parser YAML minimal (subset: key: value, listas, dicts anidados 2 niveles) ────

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Separa frontmatter YAML del body markdown.
    Devuelve (metadata_dict, body_str). Si no hay frontmatter, ({}, text)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip("\n")
    body = text[end + 4:].lstrip("\n")
    return _parse_yaml_block(fm_block), body


def _parse_yaml_block(block: str) -> dict:
    """Parser YAML minimal: key:value (string/number/bool), `[a, b]` listas inline,
    bloques anidados por indentación de 2 espacios."""
    result: dict = {}
    lines = block.split("\n")
    i = 0

    def parse_value(raw: str) -> Any:
        raw = raw.strip()
        if not raw:
            return ""
        if raw == "{}":
            return {}
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if not inner:
                return []
            return [parse_value(x) for x in _split_top(inner, ",")]
        if raw.lower() in ("true", "yes"):
            return True
        if raw.lower() in ("false", "no"):
            return False
        if raw.lower() == "null":
            return None
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            return raw[1:-1]
        try:
            if "." in raw:
                return float(raw)
            return int(raw)
        except ValueError:
            return raw

    def _split_top(s: str, sep: str) -> list[str]:
        out, depth, buf = [], 0, []
        for ch in s:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            if ch == sep and depth == 0:
                out.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)
        if buf:
            out.append("".join(buf).strip())
        return out

    def indent_of(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def parse_block(start: int, base_indent: int) -> tuple[dict, int]:
        node: dict = {}
        k = start
        while k < len(lines):
            line = lines[k]
            if not line.strip() or line.lstrip().startswith("#"):
                k += 1
                continue
            ind = indent_of(line)
            if ind < base_indent:
                break
            if ind > base_indent:
                k += 1
                continue
            stripped = line.strip()
            if ":" not in stripped:
                k += 1
                continue
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "":
                # Posible bloque anidado
                child, next_k = parse_block(k + 1, base_indent + 2)
                node[key] = child if child else {}
                k = next_k
            else:
                node[key] = parse_value(val)
                k += 1
        return node, k

    parsed, _ = parse_block(0, 0)
    return parsed


# ── Discovery & validation ───────────────────────────────────────────────────

def _check_requires(requires: dict) -> tuple[bool, list[str]]:
    """Valida requires.{packages,bins,env}. Devuelve (ok, missing_list)."""
    missing: list[str] = []
    for pkg in (requires or {}).get("packages") or []:
        try:
            importlib.util.find_spec(pkg.replace("-", "_"))
        except (ImportError, ValueError):
            missing.append(f"package:{pkg}")
            continue
        if importlib.util.find_spec(pkg.replace("-", "_")) is None:
            missing.append(f"package:{pkg}")
    for binary in (requires or {}).get("bins") or []:
        if not shutil.which(binary):
            missing.append(f"bin:{binary}")
    import os
    for env_var in (requires or {}).get("env") or []:
        if not os.environ.get(env_var):
            missing.append(f"env:{env_var}")
    return (len(missing) == 0, missing)


def _to_tool_declaration(meta: dict) -> dict:
    """Convierte metadata de SKILL.md a tool declaration formato Gemini."""
    params_in = meta.get("parameters") or {}
    if not isinstance(params_in, dict):
        params_in = {}   # frontmatter malformado (ej: 'parameters: {}' mal parseado)
    properties: dict = {}
    required: list[str] = []
    for pname, pdef in params_in.items():
        if not isinstance(pdef, dict):
            continue
        properties[pname] = {
            "type": pdef.get("type", "STRING"),
            "description": pdef.get("description", ""),
        }
        if pdef.get("required"):
            required.append(pname)
    return {
        "name": meta["name"],
        "description": meta.get("description", ""),
        "parameters": {
            "type": "OBJECT",
            "properties": properties,
            "required": required,
        },
    }


def discover_skills() -> list[dict]:
    """Escanea skills/ y devuelve lista de skill manifests.
    Cada manifest = {name, meta, path, available, missing}."""
    if not SKILLS_DIR.exists():
        return []
    manifests = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
            continue
        md = skill_dir / "SKILL.md"
        py = skill_dir / "skill.py"
        if not md.exists() or not py.exists():
            continue
        try:
            text = md.read_text(encoding="utf-8")
            meta, _body = _parse_frontmatter(text)
            if "name" not in meta:
                meta["name"] = skill_dir.name
            ok, missing = _check_requires(meta.get("requires") or {})
            manifests.append({
                "name": meta["name"],
                "meta": meta,
                "path": skill_dir,
                "py_path": py,
                "available": ok,
                "missing": missing,
            })
        except Exception as e:
            print(f"[SkillLoader] Error parseando {md}: {e}")
    return manifests


def load_skill_function(manifest: dict):
    """Importa skill.py y devuelve la función `run`."""
    py = manifest["py_path"]
    spec = importlib.util.spec_from_file_location(f"skills.{manifest['name']}", py)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar {py}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "run"):
        raise AttributeError(f"{py} debe definir `def run(parameters, player=None, speak=None) -> str`")
    return module.run


# ── API pública para integrar con TOOL_DECLARATIONS ──────────────────────────

def get_skill_tool_declarations() -> list[dict]:
    """Lista de tool declarations de todas las skills DISPONIBLES (requires OK)."""
    return [
        _to_tool_declaration(m["meta"])
        for m in discover_skills()
        if m["available"]
    ]


def build_skill_dispatch() -> dict:
    """Mapa name → función `run` lista para invocar.
    Solo incluye skills disponibles. Las que tienen requires faltantes se omiten."""
    out: dict = {}
    for m in discover_skills():
        if not m["available"]:
            print(f"[SkillLoader] ⏭️  '{m['name']}' omitido (falta: {', '.join(m['missing'])})")
            continue
        try:
            out[m["name"]] = load_skill_function(m)
        except Exception as e:
            print(f"[SkillLoader] ❌ Error cargando '{m['name']}': {e}")
    return out


def list_skills_human() -> str:
    """Resumen humano de skills (útil para debug y para `/skills` voz)."""
    manifests = discover_skills()
    if not manifests:
        return "Sin skills en skills/."
    lines = []
    for m in manifests:
        flag = "✓" if m["available"] else "✗"
        desc = m["meta"].get("description", "")[:60]
        miss = f"  [falta: {', '.join(m['missing'])}]" if not m["available"] else ""
        lines.append(f"  {flag} {m['name']:25} — {desc}{miss}")
    return f"Skills ({len(manifests)}):\n" + "\n".join(lines)
