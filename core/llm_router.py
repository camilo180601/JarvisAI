"""
llm_router.py — Cerebro de pensamiento/consulta multi-proveedor para JARVIS.

La VOZ (hablar) siempre es Gemini 2.5 Flash (audio nativo, en main.py).
Esto es solo el modelo que PIENSA/CONSULTA cuando JARVIS delega razonamiento pesado.
Por defecto Gemini 2.5 Flash, pero se puede cambiar a OpenAI (GPT) o Claude y elegir modelo.

Config (config/api_keys.json):  reasoning_provider, reasoning_model
Claves (.env):                  GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY
"""
from __future__ import annotations
import concurrent.futures

# Catálogo de modelos conocidos (mayo 2026). El primero de cada lista es el default sugerido.
# Modelos vigentes (confirmado mayo 2026). El primero de cada lista es el default.
MODELS = {
    "gemini": [
        ("gemini-2.5-flash",       "Rápido y barato (default de fallback)"),
        ("gemini-3.5-flash",       "Gen 3.5 GA — el más inteligente para agentes/código"),
        ("gemini-3.1-pro",         "Gen 3.1 Pro — el mejor en razonamiento puro (feb-2026)"),
        ("gemini-3-flash",         "Gen 3, multimodal complejo"),
        ("gemini-3.1-flash-lite",  "Gen 3.1 lite — velocidad/costo"),
        ("gemini-2.5-pro",         "Razonamiento profundo (gen 2.5)"),
    ],
    "openai": [
        ("gpt-5.5",       "Flagship, razonamiento+código"),
        ("gpt-5.5-pro",   "Máxima precisión (más caro/lento)"),
        ("gpt-5.4-mini",  "Rápido y económico"),
        ("gpt-5.4-nano",  "Ultraligero"),
        ("gpt-5.3-codex", "Especialista en código/agentes"),
    ],
    "claude": [
        ("claude-opus-4-8",   "Default premium — 1M contexto, lo mejor calidad/precio"),
        ("claude-fable-5",    "FABLE 5 — el MÁS potente de Anthropic (tier nuevo sobre Opus; ~2x el precio)"),
        ("claude-sonnet-4-6", "Mejor balance velocidad/inteligencia"),
        ("claude-opus-4-7",   "Opus anterior"),
        ("claude-haiku-4-5",  "El más rápido y barato"),
    ],
    "minimax": [
        ("MiniMax-M3",              "M3 — lo último (jun-2026): 1M contexto, multimodal, agentes"),
        ("MiniMax-M2.7",            "Flagship 2.7 (229B)"),
        ("MiniMax-M2.7-highspeed",  "2.7 alta velocidad"),
        ("MiniMax-M2.5",            "2.5"),
        ("MiniMax-M2",              "M2"),
    ],
    "claude_cli": [
        ("claude-cli", "Claude Code CLI — tu suscripción, SIN API key"),
    ],
    "antigravity": [
        ("antigravity", "Antigravity CLI de Google (Gemini 3.5 Flash) — tu suscripción, SIN API key"),
    ],
}

MINIMAX_BASE_URL = "https://api.minimax.io/v1"

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-2.5-flash"


def _cfg(key, default=""):
    try:
        from memory.config_manager import cfg
        return cfg(key, default)
    except Exception:
        return default


def get_reasoning_config() -> tuple[str, str]:
    """(provider, model) del cerebro de pensamiento, con fallback inteligente:
    - lo configurado por el usuario (claude_cli / gemini / openai / claude / minimax);
    - si ese proveedor NO está disponible (sin CLI o sin API key) → Gemini Flash por defecto."""
    provider = (_cfg("reasoning_provider", DEFAULT_PROVIDER) or DEFAULT_PROVIDER).lower()
    if provider not in MODELS:
        provider = DEFAULT_PROVIDER
    model = _cfg("reasoning_model", "") or MODELS[provider][0][0]
    # Fallback: si el cerebro elegido no está disponible, caer a Gemini Flash
    if not _has_key(provider) and _has_key("gemini"):
        return DEFAULT_PROVIDER, DEFAULT_MODEL
    return provider, model


def _has_key(provider: str) -> bool:
    if provider == "claude_cli":
        try:
            from actions.claude_code import _claude_bin
            return _claude_bin() is not None   # no necesita API key, solo el CLI instalado+logueado
        except Exception:
            return False
    if provider == "antigravity":
        try:
            from actions.antigravity import _agy_bin
            return _agy_bin() is not None      # idem: solo la CLI instalada+logueada
        except Exception:
            return False
    return bool(_cfg({"gemini": "gemini_api_key", "openai": "openai_api_key",
                      "claude": "anthropic_api_key", "minimax": "minimax_api_key"}.get(provider, ""), ""))


# ───────────────────────── llamadas por proveedor ─────────────────────────

def _call_gemini(prompt, system, model, max_tokens) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=_cfg("gemini_api_key"))
    parts = []
    if system:
        parts.append(types.Part(text=system))
    parts.append(types.Part(text=prompt))
    cfg = types.GenerateContentConfig(max_output_tokens=max_tokens)
    resp = client.models.generate_content(
        model=model, contents=[types.Content(parts=parts)], config=cfg)
    return (resp.text or "").strip()


def _call_openai(prompt, system, model, max_tokens) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=_cfg("openai_api_key"))
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    try:
        r = client.chat.completions.create(model=model, messages=msgs, max_completion_tokens=max_tokens)
    except TypeError:
        r = client.chat.completions.create(model=model, messages=msgs, max_tokens=max_tokens)
    return (r.choices[0].message.content or "").strip()


def _call_claude(prompt, system, model, max_tokens) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=_cfg("anthropic_api_key"))
    kw = {"model": model, "max_tokens": max_tokens,
          "messages": [{"role": "user", "content": prompt}]}
    if system:
        kw["system"] = system
    r = client.messages.create(**kw)
    return "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()


def _call_minimax(prompt, system, model, max_tokens) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=_cfg("minimax_api_key"), base_url=MINIMAX_BASE_URL)
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    r = client.chat.completions.create(model=model, messages=msgs, max_tokens=max_tokens)
    return (r.choices[0].message.content or "").strip()


def _call_claude_cli(prompt, system, model, max_tokens, timeout: int = 55) -> str:
    """Piensa con el Claude Code CLI headless — usa la suscripción, sin API key.
    Timeout corto: si tarda, LANZA excepción para que consult() caiga a Gemini (rápido)
    y la voz NO se congele/desconecte."""
    from actions.claude_code import _claude_bin, _env_with_node, _run_cli, _needs_login, BASE_DIR
    claude = _claude_bin()
    if not claude:
        raise RuntimeError("Claude CLI no instalado (npm i -g @anthropic-ai/claude-code)")
    full = (system + "\n\n" + prompt) if system else prompt
    code, out = _run_cli([claude, "-p", full, "--output-format", "text"],
                         str(BASE_DIR), _env_with_node(claude), timeout=timeout)
    if _needs_login(out):
        raise RuntimeError("Claude CLI sin login — corré 'claude' una vez en una terminal")
    if not out or out.startswith("(timeout"):
        raise RuntimeError("Claude CLI tardó demasiado (fallback a Gemini)")
    return out.strip()


def _call_antigravity(prompt, system, model, max_tokens, timeout: int = 55) -> str:
    """Piensa con la Antigravity CLI de Google headless — usa la suscripción, sin API key.
    Timeout corto: si tarda, LANZA excepción para que consult() caiga a Gemini (rápido)
    y la voz NO se congele/desconecte."""
    from actions.antigravity import _agy_bin, _env_with_node, _run_cli, _needs_login, _print_args, BASE_DIR
    agy = _agy_bin()
    if not agy:
        raise RuntimeError("Antigravity CLI no instalada (npm i -g @google/antigravity-cli)")
    full = (system + "\n\n" + prompt) if system else prompt
    code, out = _run_cli(_print_args(agy, full), str(BASE_DIR), _env_with_node(agy), timeout=timeout)
    if _needs_login(out):
        raise RuntimeError("Antigravity sin login — corré 'agy' una vez en una terminal")
    if not out or out.startswith("(timeout"):
        raise RuntimeError("Antigravity tardó demasiado o no devolvió texto (fallback a Gemini)")
    return out.strip()


_CALLERS = {"gemini": _call_gemini, "openai": _call_openai,
            "claude": _call_claude, "minimax": _call_minimax,
            "claude_cli": _call_claude_cli, "antigravity": _call_antigravity}


# Tope de tiempo por proveedor para que la VOZ nunca se congele/desconecte.
# Vale para TODOS los cerebros (no solo claude_cli): si una API se cuelga o tarda,
# se aborta y cae a Gemini Flash (rápido).
_TIMEOUTS = {"gemini": 40, "openai": 45, "claude": 50, "minimax": 45, "claude_cli": 55, "antigravity": 55}


def _call_with_timeout(prov, mdl, prompt, system, max_tokens):
    secs = _TIMEOUTS.get(prov, 45)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_CALLERS[prov], prompt, system, mdl, max_tokens)
        return fut.result(timeout=secs)   # TimeoutError si se pasa


def consult(prompt: str, system: str | None = None, provider: str | None = None,
            model: str | None = None, max_tokens: int = 2000) -> tuple[str, str]:
    """
    Consulta al cerebro configurado (o al override provider/model), con TOPE DE TIEMPO.
    Devuelve (texto, etiqueta_modelo). Si el proveedor no tiene clave, falla, o TARDA
    demasiado → cae a Gemini Flash (para que la voz no se trabe). Vale para todos los cerebros.
    """
    if provider:
        provider = provider.lower()
        if provider not in MODELS:
            provider = DEFAULT_PROVIDER
        model = model or MODELS[provider][0][0]
    else:
        provider, model = get_reasoning_config()

    def _try(prov, mdl):
        if not _has_key(prov):
            raise RuntimeError(f"falta la API key de {prov}")
        return _call_with_timeout(prov, mdl, prompt, system, max_tokens)

    try:
        return _try(provider, model), f"{provider}:{model}"
    except Exception as e:
        reason = "tardó demasiado" if isinstance(e, concurrent.futures.TimeoutError) else str(e)[:80]
        if provider != DEFAULT_PROVIDER and _has_key(DEFAULT_PROVIDER):
            try:
                txt = _try(DEFAULT_PROVIDER, DEFAULT_MODEL)
                return f"[{provider} {reason} — usé Gemini] {txt}", f"{DEFAULT_PROVIDER}:{DEFAULT_MODEL}"
            except Exception as e2:
                return f"Error consultando ({provider} y fallback Gemini): {str(e2)[:120]}", ""
        return f"Error consultando {provider}:{model} — {reason}", ""


def list_models_human() -> str:
    cur_p, cur_m = get_reasoning_config()
    lines = [f"Cerebro actual: {cur_p} / {cur_m}", ""]
    for prov, items in MODELS.items():
        key = "✓ clave" if _has_key(prov) else "✗ sin clave"
        lines.append(f"{prov.upper()} ({key}):")
        for mid, desc in items:
            mark = " ←actual" if (prov == cur_p and mid == cur_m) else ""
            lines.append(f"  • {mid} — {desc}{mark}")
    return "\n".join(lines)
