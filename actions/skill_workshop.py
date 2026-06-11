"""
skill_workshop.py — Observador nocturno que revisa episodios y propone mejoras.

Estrategia OpenClaw Skill-Workshop:
  - Lee últimos N días de sesiones JSONL
  - Analiza: tools más usadas, sequences repetidas, tools con alto fallo
  - Pide a Gemini propuestas: skills nuevas, fixes a skills existentes
  - Guarda propuestas en ~/.jarvis/workshop_pending.json (en cuarentena)
  - El usuario revisa con action=list y aprueba con action=approve

NUNCA modifica nada sin aprobación explícita.

Acciones:
  review (default) — escanea + escribe propuestas pendientes
  list             — muestra propuestas pendientes
  approve          — ejecuta propuesta por id (crea skill / aplica fix)
  reject           — descarta propuesta por id
  clear            — limpia todas las pendientes
  stats            — métricas del último review
"""
from __future__ import annotations
import json
import re
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from core.episodic import SESSIONS_DIR, iter_sessions, read_events
from core.registry import tool

WORKSHOP_FILE = SESSIONS_DIR / "workshop_pending.json"
BASE_DIR = Path(__file__).resolve().parent.parent
API_FILE = BASE_DIR / "config" / "api_keys.json"

MIN_REPETITIONS = 3       # mínimo de veces que aparece un patrón para considerarlo
MIN_TOOL_CALLS = 5        # mínimo de llamadas para evaluar tasa de fallo
HIGH_FAILURE_THRESHOLD = 0.4   # >40% fallo dispara propuesta de fix
DEFAULT_DAYS = 7


_REVIEW_PROMPT = """Eres el archivero de skills de JARVIS. Analizá los datos de uso
y devolvé propuestas concretas para mejorar el sistema.

Tipos de propuesta:
  - new_skill: secuencia repetida de tools → conviene encapsularla en una skill nueva
  - fix_skill: skill o tool con alto fallo → sugerir qué arreglar
  - note: observación útil pero sin acción inmediata

REGLAS:
- Solo propongas si hay evidencia clara (frecuencia, fallos repetidos).
- Si todo va bien, devolvé "proposals": [].
- Máximo 5 propuestas por review (calidad > cantidad).
- "rationale" en español, ≤ 120 chars.
- new_skill.suggested_name en snake_case.
- new_skill.description debe ser una línea ejecutable que skill_teach pueda usar.

FORMATO (devolver SOLO JSON):

{
  "summary": "Resumen breve del período (1-2 líneas)",
  "proposals": [
    {
      "type": "new_skill",
      "suggested_name": "modo_trabajo",
      "description": "Cierra Slack, baja volumen al 30% y abre VSCode",
      "rationale": "El usuario hizo esta secuencia 4 veces esta semana",
      "evidence_count": 4
    },
    {
      "type": "fix_skill",
      "target": "nombre_skill",
      "rationale": "Falló 5 de 8 veces con error 'X'",
      "evidence_count": 5
    }
  ]
}
"""


def _get_api_key() -> str:
    try:
        from memory.config_manager import cfg
        return cfg("gemini_api_key", "")
    except Exception:
        return ""

def _scan_episodes(days: int) -> dict:
    """Lee sessions del último N días y agrega estadísticas."""
    cutoff = datetime.now() - timedelta(days=days)
    tool_counts: Counter = Counter()
    tool_failures: Counter = Counter()
    sequences: list[list] = []      # listas de tool names por sesión, en orden
    user_turns: list[str] = []
    sessions_scanned = 0

    for sess_path in iter_sessions(reverse=True):
        # filtro por fecha del filename
        try:
            ts_str = "".join(sess_path.stem.split("_")[:2])
            if datetime.strptime(ts_str, "%Y%m%d%H%M%S") < cutoff:
                continue
        except Exception:
            pass

        sessions_scanned += 1
        seq = []
        for evt in read_events(sess_path):
            t = evt.get("type")
            if t == "tool_call":
                name = evt.get("name", "?")
                tool_counts[name] += 1
                if not evt.get("success"):
                    tool_failures[name] += 1
                seq.append(name)
            elif t == "user_turn":
                user_turns.append((evt.get("text") or "")[:120])
        if seq:
            sequences.append(seq)

    # Detectar secuencias repetidas (2-3 tools consecutivas que aparecen en >= MIN_REPETITIONS sesiones)
    pair_counter: Counter = Counter()
    triple_counter: Counter = Counter()
    for seq in sequences:
        for i in range(len(seq) - 1):
            pair_counter[(seq[i], seq[i+1])] += 1
        for i in range(len(seq) - 2):
            triple_counter[(seq[i], seq[i+1], seq[i+2])] += 1

    repeated_pairs = [
        {"seq": list(p), "count": c}
        for p, c in pair_counter.most_common(8) if c >= MIN_REPETITIONS
    ]
    repeated_triples = [
        {"seq": list(p), "count": c}
        for p, c in triple_counter.most_common(8) if c >= MIN_REPETITIONS
    ]

    failure_rates = []
    for tool, calls in tool_counts.items():
        if calls < MIN_TOOL_CALLS:
            continue
        rate = tool_failures[tool] / calls
        if rate >= HIGH_FAILURE_THRESHOLD:
            failure_rates.append({"tool": tool, "calls": calls, "fails": tool_failures[tool], "rate": round(rate, 2)})

    return {
        "sessions": sessions_scanned,
        "total_tool_calls": sum(tool_counts.values()),
        "top_tools": [{"tool": t, "calls": c} for t, c in tool_counts.most_common(10)],
        "high_failure": failure_rates,
        "repeated_pairs": repeated_pairs,
        "repeated_triples": repeated_triples,
        "sample_user_turns": user_turns[:20],
    }


# ── Propuestas con Gemini ────────────────────────────────────────────────────

def _ask_gemini_for_proposals(stats: dict) -> dict:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return {"summary": "(google-genai no instalado)", "proposals": []}

    api_key = _get_api_key()
    if not api_key:
        return {"summary": "(falta api key)", "proposals": []}

    body = json.dumps(stats, ensure_ascii=False, indent=2)[:8000]
    client = genai.Client(api_key=api_key)
    for model in ("gemini-2.5-flash", "gemini-2.5-flash-lite"):
        for delay in (0, 2, 5):
            if delay:
                time.sleep(delay)
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[
                        types.Part(text=_REVIEW_PROMPT),
                        types.Part(text=body),
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
                    return {"summary": f"(error Gemini: {msg[:120]})", "proposals": []}
    return {"summary": "(Gemini saturado)", "proposals": []}


# ── Storage de propuestas ────────────────────────────────────────────────────

def _load_pending() -> list:
    if not WORKSHOP_FILE.exists():
        return []
    try:
        return json.loads(WORKSHOP_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_pending(items: list) -> None:
    WORKSHOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    WORKSHOP_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Acciones públicas ────────────────────────────────────────────────────────

def _do_review(days: int) -> str:
    stats = _scan_episodes(days)
    if stats["sessions"] == 0:
        return "Sin sesiones en el período. Nada que revisar."

    result = _ask_gemini_for_proposals(stats)
    summary = result.get("summary", "")
    proposals = result.get("proposals", [])

    # Cargar pendientes previas, agregar nuevas con id
    pending = _load_pending()
    added = 0
    for p in proposals[:5]:  # cap
        if not isinstance(p, dict) or "type" not in p:
            continue
        p["id"] = uuid.uuid4().hex[:8]
        p["created"] = datetime.now().isoformat(timespec="seconds")
        p["status"] = "pending"
        pending.append(p)
        added += 1

    _save_pending(pending)

    lines = [
        f"📊 Review de {stats['sessions']} sesiones, {stats['total_tool_calls']} tool calls.",
        f"   Resumen: {summary}",
    ]
    if added:
        lines.append(f"💡 {added} propuesta(s) nueva(s) en cola. Usá action=list para verlas.")
    else:
        lines.append("✓ Sin propuestas. Todo en orden.")
    return "\n".join(lines)


def _do_list() -> str:
    pending = [p for p in _load_pending() if p.get("status") == "pending"]
    if not pending:
        return "Sin propuestas pendientes."
    lines = [f"Propuestas pendientes ({len(pending)}):"]
    for p in pending:
        pid = p.get("id", "?")[:8]
        ptype = p.get("type", "?")
        if ptype == "new_skill":
            name = p.get("suggested_name", "?")
            desc = p.get("description", "")[:80]
            lines.append(f"  [{pid}] 🆕 skill '{name}' — {desc}")
            lines.append(f"          razón: {p.get('rationale', '')[:100]}")
        elif ptype == "fix_skill":
            target = p.get("target", "?")
            lines.append(f"  [{pid}] 🔧 fix '{target}' — {p.get('rationale', '')[:100]}")
        elif ptype == "note":
            lines.append(f"  [{pid}] 📝 nota — {p.get('rationale', '')[:100]}")
        else:
            lines.append(f"  [{pid}] · {ptype} — {p.get('rationale', '')[:80]}")
    lines.append("\nUsá action=approve y id=<ID> para ejecutar. action=reject para descartar.")
    return "\n".join(lines)


def _do_approve(pid: str, player=None) -> str:
    pending = _load_pending()
    for p in pending:
        if not p.get("id", "").startswith(pid):
            continue

        ptype = p.get("type")
        if ptype == "new_skill":
            try:
                from actions.skill_teach import skill_teach
            except ImportError:
                return "Error: skill_teach no disponible."
            description = p.get("description", "")
            name_hint = p.get("suggested_name", "")
            result = skill_teach(
                {"description": description, "name_hint": name_hint},
                player=player,
            )
            p["status"] = "approved"
            p["executed_at"] = datetime.now().isoformat(timespec="seconds")
            p["execution_result"] = result[:300]
            _save_pending(pending)
            return f"Propuesta {pid} ejecutada vía skill_teach:\n{result}"

        if ptype == "fix_skill":
            target = p.get("target", "")
            rationale = p.get("rationale", "")
            p["status"] = "approved"
            p["executed_at"] = datetime.now().isoformat(timespec="seconds")
            _save_pending(pending)
            return (
                f"Propuesta {pid} marcada como aprobada. Para arreglar '{target}': "
                f"usá self_edit con el rationale: {rationale}"
            )

        if ptype == "note":
            p["status"] = "approved"
            _save_pending(pending)
            return f"Nota {pid} archivada."

        return f"Propuesta {pid} tipo '{ptype}' no es ejecutable automáticamente."

    return f"No se encontró propuesta con id '{pid}'."


def _do_reject(pid: str) -> str:
    pending = _load_pending()
    for p in pending:
        if p.get("id", "").startswith(pid):
            p["status"] = "rejected"
            p["rejected_at"] = datetime.now().isoformat(timespec="seconds")
            _save_pending(pending)
            return f"Propuesta {pid} descartada."
    return f"No se encontró propuesta con id '{pid}'."


def _do_clear() -> str:
    pending = _load_pending()
    n = sum(1 for p in pending if p.get("status") == "pending")
    pending = [p for p in pending if p.get("status") != "pending"]
    _save_pending(pending)
    return f"{n} propuestas pendientes descartadas."


def _do_stats() -> str:
    pending = _load_pending()
    total = len(pending)
    by_status: Counter = Counter()
    by_type: Counter = Counter()
    for p in pending:
        by_status[p.get("status", "?")] += 1
        by_type[p.get("type", "?")] += 1
    lines = [
        f"Total propuestas histórico: {total}",
        f"Por status: {dict(by_status)}",
        f"Por tipo:   {dict(by_type)}",
    ]
    return "\n".join(lines)


@tool(
    name='skill_workshop',
    description="Observador nocturno: revisa episodios, propone skills nuevas o fixes. Acciones: review (escanea), list (muestra pendientes), approve (ejecuta por id), reject (descarta), clear, stats. USAR cuando el usuario pregunte '¿qué encontraste?' o '¿hay sugerencias?' o pida 'revisá la memoria'.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'review (default) | list | approve | reject | clear | '
                                              'stats'},
                    'days': {'type': 'INTEGER', 'description': 'Días a revisar (default 7)'},
                    'id': {'type': 'STRING',
                           'description': 'ID de propuesta para approve/reject (primeros 4-8 chars)'}},
     'required': []},
)
def run(parameters: dict, player=None, speak=None) -> str:
    """Entry point. Acción default: review."""
    action = (parameters.get("action") or "review").lower()

    if action == "review":
        days = int(parameters.get("days", DEFAULT_DAYS))
        return _do_review(days)
    if action == "list":
        return _do_list()
    if action == "approve":
        pid = (parameters.get("id") or "").strip()
        if not pid:
            return "Error: falta 'id' (los primeros 4-8 chars sirven)."
        return _do_approve(pid, player=player)
    if action == "reject":
        pid = (parameters.get("id") or "").strip()
        if not pid:
            return "Error: falta 'id'."
        return _do_reject(pid)
    if action == "clear":
        return _do_clear()
    if action == "stats":
        return _do_stats()

    return f"Acción '{action}' no soportada. Usá: review | list | approve | reject | clear | stats."
