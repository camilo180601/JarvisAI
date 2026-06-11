"""
mcp_explorer.py — Agente de investigación continuo de MCPs.

Corre en background apenas arranca JARVIS. Cada N horas:
  1. Combina lista curada de MCPs populares + búsqueda web fresca
  2. Lee USER.md / MEMORY.md para entender contexto del usuario
  3. Pide a Gemini que evalúe cada candidato: relevancia, pros/cons, plan de integración
  4. Guarda resultados en ~/.jarvis/mcp_research.json
  5. Cuando el usuario pregunta "¿qué integraciones nuevas hay?", lee del cache

Acciones:
  status      — última investigación, cuántos candidatos
  list        — top candidatos rankeados por relevancia
  details     — plan de integración detallado para un MCP
  research    — forzar investigación ahora
  installed   — qué MCPs ya están en mcp_servers.json
  dismiss     — marcar candidato como no interesado (no aparece más)
"""
from __future__ import annotations
import json
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import threading
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent
API_FILE = BASE_DIR / "config" / "api_keys.json"
MEMORY_DIR = BASE_DIR / "memory"
MCP_CONFIG = BASE_DIR / "config" / "mcp_servers.json"

CACHE_FILE = Path.home() / ".jarvis" / "mcp_research.json"
RESEARCH_INTERVAL_HOURS = 24
BACKGROUND_FIRST_RUN_DELAY = 60  # segundos después de boot

# Lista curada — MCPs populares + estables a Mayo 2026.
# El explorador la complementa con búsqueda web fresca.
CURATED_MCPS = [
    # ── Messaging ──
    {"name": "whatsapp",        "category": "messaging",   "repo": "lharries/whatsapp-mcp",                  "install": "Go bridge + Python server, escaneo QR"},
    {"name": "whatsapp-vgp",    "category": "messaging",   "repo": "verygoodplugins/whatsapp-mcp",           "install": "Alternativa de WhatsApp MCP, WhatsApp Business API friendly"},
    {"name": "whatsapp-simple", "category": "messaging",   "repo": "Charlesagui/mcp-whats-app",              "install": "Versión simplificada de WhatsApp MCP"},
    {"name": "slack",           "category": "messaging",   "repo": "modelcontextprotocol/server-slack",      "install": "npx + Slack bot token"},
    {"name": "imessage",        "category": "messaging",   "repo": "community/imessage-mcp",                 "install": "Solo Mac, lee chat.db directo, requiere Full Disk Access"},
    {"name": "telegram",        "category": "messaging",   "repo": "chigwell/telegram-mcp",                  "install": "Telegram Bot API token"},
    # ── Music ──
    {"name": "spotify",         "category": "music",       "repo": "marcelmarais/spotify-mcp-server",        "install": "npx + Spotify Developer App + OAuth"},
    # ── Productivity ──
    {"name": "google-workspace","category": "productivity","repo": "taylorwilsdon/google_workspace_mcp",     "install": "OAuth Google (Gmail+Calendar+Drive+Docs+Sheets+Tasks)"},
    {"name": "notion",          "category": "productivity","repo": "makenotion/notion-mcp-server",           "install": "OAuth Notion + integration"},
    {"name": "obsidian",        "category": "productivity","repo": "smithery-ai/mcp-obsidian",               "install": "Path al vault + Obsidian Local REST API plugin"},
    {"name": "calendar-apple",  "category": "productivity","repo": "community/apple-calendar-mcp",           "install": "AppleScript bridge"},
    # ── Dev ──
    {"name": "github",          "category": "dev",         "repo": "modelcontextprotocol/server-github",     "install": "npx + GitHub Personal Access Token"},
    {"name": "jira",            "category": "dev",         "repo": "sooperset/mcp-atlassian",                "install": "Atlassian email + API token (Jira + Confluence)"},
    {"name": "linear",          "category": "dev",         "repo": "modelcontextprotocol/server-linear",     "install": "Linear API key"},
    {"name": "docker",          "category": "dev",         "repo": "modelcontextprotocol/server-docker",     "install": "npx + Docker daemon corriendo"},
    {"name": "gitlab",          "category": "dev",         "repo": "modelcontextprotocol/server-gitlab",     "install": "npx + GitLab token"},
    # ── Browser ──
    {"name": "playwright",      "category": "browser",     "repo": "microsoft/playwright-mcp",               "install": "npx, oficial Microsoft, automatización real"},
    {"name": "puppeteer",       "category": "browser",     "repo": "modelcontextprotocol/server-puppeteer",  "install": "npx, alternativa más liviana"},
    # ── System ──
    {"name": "filesystem",      "category": "system",      "repo": "modelcontextprotocol/server-filesystem", "install": "npx, expone directorio autorizado"},
    {"name": "shell",           "category": "system",      "repo": "modelcontextprotocol/server-shell",      "install": "npx, requiere allowlist de comandos"},
    {"name": "sqlite",          "category": "system",      "repo": "modelcontextprotocol/server-sqlite",     "install": "npx + path a archivo .db"},
    # ── AI / Memory ──
    {"name": "memory",          "category": "ai",          "repo": "modelcontextprotocol/server-memory",     "install": "npx, embeddings locales"},
    # ── Media ──
    {"name": "youtube",         "category": "media",       "repo": "icraft2170/youtube-data-mcp-server",     "install": "YouTube Data API key opcional"},
    # ── Info ──
    {"name": "weather",         "category": "info",        "repo": "modelcontextprotocol/server-weather",    "install": "npx"},
    {"name": "brave-search",    "category": "info",        "repo": "modelcontextprotocol/server-brave-search","install": "npx + Brave API key"},
    # ── Fintech ──
    {"name": "stripe",          "category": "fintech",     "repo": "stripe/agent-toolkit",                   "install": "Stripe API key"},
    # ── Mega-agregador ──
    {"name": "composio",        "category": "mega",        "repo": "composiohq/composio",                    "install": "Composio API key — 250+ apps en un solo MCP"},
]


def _get_api_key() -> str:
    try:
        from memory.config_manager import cfg
        return cfg("gemini_api_key", "")
    except Exception:
        return ""

def _load_user_context() -> str:
    """Lee USER.md + MEMORY.md para enriquecer el prompt de evaluación."""
    parts = []
    for fname in ("USER.md", "MEMORY.md"):
        fp = MEMORY_DIR / fname
        if fp.exists():
            try:
                parts.append(f"=== {fname} ===\n{fp.read_text(encoding='utf-8')[:1500]}")
            except Exception:
                pass
    return "\n\n".join(parts) or "(sin contexto de usuario disponible)"


def _load_installed_servers() -> list[str]:
    """Nombres de servers MCP ya configurados en mcp_servers.json."""
    if not MCP_CONFIG.exists():
        return []
    try:
        cfg = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
        return [name for name, sc in (cfg.get("servers") or {}).items() if not sc.get("disabled")]
    except Exception:
        return []


def _load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {"last_scan": None, "candidates": [], "dismissed": []}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"last_scan": None, "candidates": [], "dismissed": []}


def _save_cache(data: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _web_search_recent_mcps() -> list[dict]:
    """Búsqueda web para MCPs recientes/menos conocidos (best-effort, fallback silencioso)."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return []
    found = []
    queries = [
        "best MCP servers 2026 github",
        "new model context protocol server release",
        "useful MCP servers personal productivity",
    ]
    seen_repos = set()
    try:
        with DDGS() as ddgs:
            for q in queries:
                for r in ddgs.text(q, max_results=4, region="wt-wt"):
                    url = r.get("href") or r.get("url") or ""
                    title = r.get("title", "")
                    body = r.get("body", "")
                    # Solo capturar URLs github.com/<owner>/<repo>
                    m = re.search(r"github\.com/([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)", url + " " + title + " " + body)
                    if m:
                        repo = f"{m.group(1)}/{m.group(2)}"
                        if repo in seen_repos:
                            continue
                        seen_repos.add(repo)
                        found.append({
                            "name": m.group(2),
                            "category": "web-discovered",
                            "repo": repo,
                            "install": "(ver README del repo)",
                            "source_url": url,
                            "blurb": (title + " — " + body)[:200],
                        })
                        if len(found) >= 8:
                            return found
    except Exception:
        pass
    return found


_SYSTEM_EVAL = """Eres un investigador de MCPs (Model Context Protocol) para JARVIS.

Te paso:
1. Contexto del usuario (USER.md, MEMORY.md)
2. Lista de MCPs ya instalados
3. Lista de MCPs candidatos con su info básica

Para cada candidato NO instalado evalúa:
  - relevance: 1-10 según el contexto del usuario
  - reason_for: por qué le serviría a ESTE usuario específico (≤80 chars)
  - reason_against: motivos para NO instalarlo (costo, fricción, riesgo) (≤80 chars)
  - effort: low | medium | high (cuánto cuesta setup)
  - integration_plan: lista de 3-6 pasos concretos para instalarlo

DEVOLVER SOLO JSON, sin markdown:

{
  "evaluations": [
    {
      "name": "...",
      "repo": "...",
      "category": "...",
      "relevance": 8,
      "reason_for": "...",
      "reason_against": "...",
      "effort": "low",
      "integration_plan": ["Paso 1...", "Paso 2..."]
    }
  ]
}

REGLAS:
- Máximo 12 evaluaciones (las más relevantes).
- Si un MCP no aplica al perfil del usuario, no lo incluyas.
- Sé honesto: si algo no vale la pena, ponelo en reason_against y bajá relevance.
- Plan de integración en español, accionable.
"""


def _evaluate_with_gemini(candidates: list[dict], user_context: str, installed: list[str]) -> tuple[list[dict], str]:
    """Devuelve (evaluations, error_msg). evaluations vacío si error_msg presente."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return [], "google-genai no instalado"

    api_key = _get_api_key()
    if not api_key:
        return [], "falta gemini_api_key"

    pending = [c for c in candidates if c.get("name") not in installed]
    if not pending:
        return [], ""

    # Batch en chunks de 8 para que la respuesta JSON no exceda max_output_tokens
    BATCH = 8
    all_evaluations: list[dict] = []
    last_err = ""
    client = genai.Client(api_key=api_key)

    for batch_start in range(0, len(pending), BATCH):
        batch = pending[batch_start:batch_start + BATCH]
        body = json.dumps({
            "user_context_preview": user_context[:1500],
            "installed_servers": installed,
            "candidates": batch,
        }, ensure_ascii=False, indent=2)[:8000]

        batch_ok = False
        for model in ("gemini-2.5-flash", "gemini-2.5-flash-lite"):
            for delay in (0, 2, 5):
                if delay:
                    time.sleep(delay)
                try:
                    resp = client.models.generate_content(
                        model=model,
                        contents=[types.Content(parts=[
                            types.Part(text=_SYSTEM_EVAL),
                            types.Part(text=body),
                        ])],
                        config=types.GenerateContentConfig(
                            max_output_tokens=4000,
                            response_mime_type="application/json",
                        ),
                    )
                    raw = (resp.text or "").strip()
                    if raw.startswith("```"):
                        raw = re.sub(r"^```(?:json)?\s*", "", raw)
                        raw = re.sub(r"\s*```\s*$", "", raw)
                    parsed = json.loads(raw)
                    all_evaluations.extend(parsed.get("evaluations", []))
                    batch_ok = True
                    break
                except Exception as e:
                    last_err = str(e)[:200]
                    if not any(c in str(e) for c in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED")):
                        last_err = f"{model}: {last_err}"
                        break
            if batch_ok:
                break
        if not batch_ok:
            # batch falla, seguimos con los siguientes
            continue

    return all_evaluations, ("" if all_evaluations else last_err)


# ── Acciones ─────────────────────────────────────────────────────────────────

def _do_research(player=None) -> str:
    cache = _load_cache()
    user_ctx = _load_user_context()
    installed = _load_installed_servers()
    dismissed = set(cache.get("dismissed") or [])

    if player:
        player.write_log("🔬 Investigando MCPs...")

    # Combinar curados + web (filtrando dismissed)
    web_found = _web_search_recent_mcps()
    pool = []
    seen_repos = set()
    for src in (CURATED_MCPS + web_found):
        repo = src.get("repo", "")
        if repo in seen_repos:
            continue
        seen_repos.add(repo)
        if src.get("name") in dismissed:
            continue
        pool.append(src)

    if player:
        player.write_log(f"  📚 {len(pool)} candidatos (curados + web). Evaluando con Gemini...")

    evaluations, err = _evaluate_with_gemini(pool, user_ctx, installed)
    if not evaluations:
        return f"Investigación falló: {err or 'sin evaluaciones'}"

    # Asignar ID estable por nombre para que dismiss/details funcionen
    for e in evaluations:
        existing = next((c for c in cache.get("candidates", []) if c.get("name") == e.get("name")), None)
        e["id"] = (existing or {}).get("id") or uuid.uuid4().hex[:8]
        e["discovered"] = (existing or {}).get("discovered") or datetime.now().isoformat(timespec="seconds")
        e["last_seen"] = datetime.now().isoformat(timespec="seconds")
        e["status"] = "candidate"

    cache["candidates"] = evaluations
    cache["last_scan"] = datetime.now().isoformat(timespec="seconds")
    _save_cache(cache)

    top = sorted(evaluations, key=lambda x: -x.get("relevance", 0))[:5]
    return (
        f"✓ Investigación lista. {len(evaluations)} candidatos evaluados.\n"
        f"Top 5 por relevancia:\n" +
        "\n".join(f"  · [{c.get('relevance')}/10] {c.get('name')} — {c.get('reason_for', '')[:60]}" for c in top)
    )


def _do_status() -> str:
    cache = _load_cache()
    last = cache.get("last_scan") or "(nunca)"
    n = len(cache.get("candidates") or [])
    dismissed = len(cache.get("dismissed") or [])
    installed = _load_installed_servers()
    return (
        f"📊 MCP Explorer\n"
        f"  Última investigación: {last}\n"
        f"  Candidatos en cache: {n}\n"
        f"  Descartados por usuario: {dismissed}\n"
        f"  Ya instalados: {len(installed)} ({', '.join(installed) or '(ninguno)'})"
    )


def _do_list(min_relevance: int = 5) -> str:
    cache = _load_cache()
    candidates = cache.get("candidates") or []
    if not candidates:
        return "No hay investigación previa. Pedí 'investigá MCPs nuevos' para iniciar."
    sorted_c = sorted([c for c in candidates if c.get("relevance", 0) >= min_relevance],
                      key=lambda x: -x.get("relevance", 0))
    if not sorted_c:
        return f"Sin candidatos con relevancia >= {min_relevance}. Bajá el umbral o pedí research nuevo."
    lines = [f"🔍 {len(sorted_c)} candidatos relevantes:"]
    for c in sorted_c[:12]:
        rel = c.get("relevance", 0)
        name = c.get("name", "?")
        cat = c.get("category", "")
        eff = c.get("effort", "?")
        why = c.get("reason_for", "")[:70]
        lines.append(f"  [{c.get('id','?')[:6]}] {rel}/10 {name} ({cat}, {eff}) — {why}")
    return "\n".join(lines)


def _do_details(target: str) -> str:
    if not target:
        return "Error: indicame 'id' o 'name' del MCP."
    cache = _load_cache()
    candidates = cache.get("candidates") or []
    match = None
    for c in candidates:
        if c.get("id", "").startswith(target) or c.get("name", "").lower() == target.lower():
            match = c
            break
    if not match:
        return f"No encontré candidato '{target}'. Usá action=list para ver opciones."

    plan = match.get("integration_plan") or []
    plan_str = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(plan))
    return (
        f"📦 {match.get('name')} ({match.get('category')})\n"
        f"Repo: {match.get('repo')}\n"
        f"Relevancia: {match.get('relevance')}/10  ·  Esfuerzo: {match.get('effort')}\n"
        f"\nA favor: {match.get('reason_for')}\n"
        f"En contra: {match.get('reason_against')}\n"
        f"\nPlan de integración:\n{plan_str}"
    )


def _do_installed() -> str:
    installed = _load_installed_servers()
    if not installed:
        return "Sin MCPs configurados todavía. Ver config/mcp_servers.example.json para empezar."
    return "MCPs instalados:\n" + "\n".join(f"  ✓ {s}" for s in installed)


def _do_dismiss(target: str) -> str:
    if not target:
        return "Error: especificá 'name' del MCP a descartar."
    cache = _load_cache()
    dismissed = set(cache.get("dismissed") or [])
    # Buscar por id o nombre
    name = target
    for c in cache.get("candidates") or []:
        if c.get("id", "").startswith(target) or c.get("name", "").lower() == target.lower():
            name = c.get("name")
            break
    dismissed.add(name)
    cache["dismissed"] = sorted(dismissed)
    cache["candidates"] = [c for c in cache.get("candidates") or [] if c.get("name") != name]
    _save_cache(cache)
    return f"✓ '{name}' marcado como no interesante. No aparecerá en próximas investigaciones."


# ── Entry point ──────────────────────────────────────────────────────────────

@tool(
    name='mcp_explorer',
    description="Investigador de MCPs (Model Context Protocol). Corre en background investigando integraciones nuevas con plan de instalación. USAR cuando el usuario pregunte '¿qué integraciones nuevas hay?', '¿qué MCPs me sirven?', 'investigá nuevos MCPs', '¿cómo instalo X MCP?'. Acciones: list (top candidatos), details (plan de un MCP), status, research (forzar scan), installed, dismiss.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'list (default) | status | details | research | '
                                              'installed | dismiss'},
                    'id': {'type': 'STRING',
                           'description': 'ID o nombre del MCP (para details/dismiss)'},
                    'name': {'type': 'STRING', 'description': 'Alias de id'},
                    'min_relevance': {'type': 'INTEGER',
                                      'description': 'Umbral mínimo de relevancia para list (default '
                                                     '5)'}},
     'required': []},
)
def run(parameters: dict, player=None, speak=None) -> str:
    action = (parameters.get("action") or "list").lower()

    if action == "research":
        return _do_research(player=player)
    if action == "status":
        return _do_status()
    if action == "list":
        return _do_list(min_relevance=int(parameters.get("min_relevance", 5)))
    if action == "details":
        return _do_details((parameters.get("id") or parameters.get("name") or "").strip())
    if action == "installed":
        return _do_installed()
    if action == "dismiss":
        return _do_dismiss((parameters.get("name") or parameters.get("id") or "").strip())
    return f"Acción '{action}' no soportada. Usá: research | status | list | details | installed | dismiss"


# ── Background runner — investiga cada N horas sin bloquear ─────────────────

_runner_thread: threading.Thread | None = None
_runner_stop = threading.Event()


def _runner_loop(player=None):
    """Loop: primer scan tras BACKGROUND_FIRST_RUN_DELAY, después cada RESEARCH_INTERVAL_HOURS."""
    # Esperar boot
    if _runner_stop.wait(BACKGROUND_FIRST_RUN_DELAY):
        return

    while not _runner_stop.is_set():
        try:
            cache = _load_cache()
            last_scan = cache.get("last_scan")
            should_scan = True
            if last_scan:
                try:
                    last_dt = datetime.fromisoformat(last_scan)
                    if datetime.now() - last_dt < timedelta(hours=RESEARCH_INTERVAL_HOURS):
                        should_scan = False
                except Exception:
                    pass

            if should_scan:
                print("[MCP-Explorer] 🔬 Investigación en background iniciada...")
                result = _do_research(player=player)
                print(f"[MCP-Explorer] {result.splitlines()[0] if result else 'done'}")
        except Exception as e:
            print(f"[MCP-Explorer] error en loop: {e}")

        # Dormir hasta próximo scan
        _runner_stop.wait(RESEARCH_INTERVAL_HOURS * 3600)


def start_background_runner(player=None) -> None:
    """Arranca el thread daemon. Idempotente."""
    global _runner_thread
    if _runner_thread and _runner_thread.is_alive():
        return
    _runner_stop.clear()
    _runner_thread = threading.Thread(
        target=_runner_loop, args=(player,), daemon=True, name="mcp-explorer"
    )
    _runner_thread.start()
    print("[MCP-Explorer] 🔭 Background runner iniciado (primer scan en 60s, después cada 24h).")


def stop_background_runner() -> None:
    _runner_stop.set()
