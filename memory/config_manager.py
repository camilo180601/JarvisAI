"""config_manager.py — Fuente única de configuración.

Orden de prioridad (gana el primero que tenga valor):
  1. Variables del archivo .env (raíz del proyecto)   ← recomendado para secretos
  2. Variables de entorno reales del sistema
  3. config/api_keys.json                              ← ajustes de la app (tema, voz, etc.)

Las claves del .env se nombran en MAYÚSCULAS (GEMINI_API_KEY) y se mapean a la versión
en minúsculas que usa el resto del código (gemini_api_key).
"""
import os
import sys
import json
from pathlib import Path

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "api_keys.json"
ENV_FILE = BASE_DIR / ".env"

# Cargar .env al entorno (no pisa variables ya presentes en el sistema)
try:
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=False)
except Exception:
    pass


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def config_exists() -> bool:
    return CONFIG_FILE.exists() or ENV_FILE.exists()

def _env_overlay() -> dict[str, str]:
    """Valores desde .env + entorno, en minúsculas. Solo los que tengan valor."""
    out: dict[str, str] = {}
    try:
        from dotenv import dotenv_values
        for k, v in dotenv_values(ENV_FILE).items():
            if v not in (None, ""):
                out[k.lower()] = v
    except Exception:
        pass
    # variables reales del entorno (pisan al .env si están seteadas en el sistema)
    for k, v in os.environ.items():
        if v and k.isupper() and ("_" in k):
            out[k.lower()] = v
    return out

def load_api_keys() -> dict:
    """JSON de ajustes + overlay de .env/entorno (estos últimos ganan)."""
    base: dict = {}
    if CONFIG_FILE.exists():
        try:
            base = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            base = {}
    base.update(_env_overlay())
    return base

def cfg(key: str, default=""):
    """Atajo: valor de una sola clave (con prioridad .env > entorno > json)."""
    return load_api_keys().get(key, default)

def save_api_keys(keys: dict) -> None:
    """Guarda ajustes en el JSON (la UI lo usa). Los secretos viven mejor en .env.

    FILTRA antes de escribir (bug histórico: la UI hacía save(load()) y como
    load() mergea TODO el entorno, el JSON terminaba lleno de variables de
    entorno volcadas — vscode_*, xpc_*, etc. — y hasta secretos):
      • claves cuyo valor vino del overlay .env/entorno → no se persisten
      • SECRET_KEYS → van al .env, jamás al JSON
    """
    ensure_config_dir()
    overlay = _env_overlay()
    clean = {k: v for k, v in keys.items()
             if k not in SECRET_KEYS
             and not (k in overlay and overlay[k] == v)}
    CONFIG_FILE.write_text(json.dumps(clean, indent=2), encoding="utf-8")

# Claves que se consideran secretos → se persisten en .env, no en el JSON
SECRET_KEYS = {
    "gemini_api_key", "openrouter_api_key", "tmdb_api_key",
    "spotify_client_id", "spotify_client_secret", "spotify_redirect_uri",
    "tuya_api_key", "tuya_api_secret", "tuya_region",
    "alpaca_api_key", "alpaca_secret_key",
    "figma_token", "figma_api_key",
    "github_personal_access_token", "telegram_bot_api_token",
    "openai_api_key", "anthropic_api_key", "minimax_api_key",
    "notion_token", "brave_api_key", "composio_api_key",
}

def set_env_var(name: str, value: str) -> None:
    """Crea/actualiza una variable en el .env (nombre se normaliza a MAYÚSCULAS)."""
    name = name.upper()
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else \
        ["# JARVIS — secretos y API keys. NO subir a git.", ""]
    found = False
    for i, l in enumerate(lines):
        if l.strip() and not l.strip().startswith("#") and "=" in l:
            if l.split("=", 1)[0].strip() == name:
                lines[i] = f"{name}={value}"
                found = True
                break
    if not found:
        lines.append(f"{name}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[name] = value  # disponible de inmediato sin reiniciar

def set_secret(key: str, value: str) -> None:
    """Guarda un secreto en el .env."""
    set_env_var(key, value)

def set_setting(key: str, value) -> None:
    """Guarda un AJUSTE no-secreto en config/api_keys.json (tema, voz, prioridades, etc.)."""
    keys = {}
    if CONFIG_FILE.exists():
        try:
            keys = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            keys = {}
    keys[key] = value
    save_api_keys(keys)

def is_configured() -> bool:
    try:
        return bool(load_api_keys().get("gemini_api_key"))
    except Exception:
        return False

def get_gemini_key() -> str:
    return load_api_keys().get("gemini_api_key", "")
