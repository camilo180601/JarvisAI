import os
import json
import sys
from pathlib import Path

# Cargar .env al entorno lo antes posible (antes de MCP y de cualquier integración)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    # El MCP de Figma (figma-developer-mcp) espera FIGMA_API_KEY; reusamos FIGMA_TOKEN.
    if os.environ.get("FIGMA_TOKEN") and not os.environ.get("FIGMA_API_KEY"):
        os.environ["FIGMA_API_KEY"] = os.environ["FIGMA_TOKEN"]
except Exception:
    pass

# Load config early to determine GPU acceleration settings
_gpu_enabled = False
try:
    if getattr(sys, "frozen", False):
        _base_dir = Path(sys.executable).parent
    else:
        _base_dir = Path(__file__).resolve().parent
    _cfg_path = _base_dir / "config" / "api_keys.json"
    if _cfg_path.exists():
        _cfg = json.loads(_cfg_path.read_text(encoding="utf-8"))
        _gpu_enabled = _cfg.get("gpu_acceleration", False)
except Exception:
    pass

if _gpu_enabled:
    # GPU / High Performance Mode: sustain rendering workload on GPU VRAM, maximize space size
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--ignore-gpu-blocklist "
        "--enable-gpu-rasterization "
        "--enable-zero-copy "
        "--num-raster-threads=4 "
        "--js-flags=--max-old-space-size=1024"
    )
    # Enable hardware acceleration backends for Qt
    os.environ["QSG_RHI_BACKEND"] = "d3d11" # Force Direct3D 11 for hardware rendering on Windows
    os.environ["QSG_INFO"] = "1"
    print("[JARVIS] GPU Acceleration is ENABLED. Offloading RAM rendering workload to GPU.")
else:
    # Balanced low-RAM mode. En macOS el compositor de GPU de QtWebEngine falla
    # (SharedImage RGBA_4444) y deja el orb en blanco → forzamos render por software,
    # que es confiable en cualquier sistema (el orb es Canvas 2D, no necesita GPU).
    _mac_soft = "--disable-gpu --disable-gpu-compositing " if sys.platform == "darwin" else ""
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        _mac_soft +
        "--enable-low-end-device-mode "
        "--renderer-process-limit=1 "
        "--js-flags=--max-old-space-size=64 "
        "--disable-gpu-shader-disk-cache "
        "--disable-dev-shm-usage "
        "--disable-extensions "
        "--disable-sync "
        "--mute-audio"
    )
    print(f"[JARVIS] Render mode: {'software (macOS-safe)' if sys.platform=='darwin' else 'GPU-composited'}.")

import asyncio
from concurrent.futures import ThreadPoolExecutor
from beta_config import is_pro_tool, check_daily_limit, increment_calls, pro_tool_message, daily_limit_message
import re
import threading
import json
import sys
try:
    import pygetwindow as gw
except ImportError:
    gw = None
from PyQt6.QtCore import QMetaObject, Qt

import traceback
from pathlib import Path

# ── Dedicated thread pool for tool execution — prevents starvation ────────────
_TOOL_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="jarvis-tool")

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _BA_TZ = _ZoneInfo("America/Lima")
except Exception:
    from datetime import timezone as _tz, timedelta as _td
    _BA_TZ = _tz(_td(hours=-5))


def _load_tz():
    """Load timezone from api_keys.json config."""
    global _BA_TZ
    try:
        from memory.config_manager import load_api_keys
        cfg = load_api_keys()
        tz_name = cfg.get("timezone", "")
        if tz_name:
            try:
                _BA_TZ = _ZoneInfo(tz_name)
                print(f"[TZ] Timezone loaded: {tz_name}")
            except Exception as e:
                print(f"[TZ] Failed to load '{tz_name}': {e}")
                # Fallback: try to find a common alias or partial match
                import zoneinfo as _zi
                available = _zi.available_timezones()
                # Try case-insensitive match
                tz_lower = tz_name.lower()
                for known in available:
                    if known.lower() == tz_lower:
                        _BA_TZ = _ZoneInfo(known)
                        print(f"[TZ] Matched '{tz_name}' → '{known}'")
                        break
                else:
                    # Try partial match (e.g., "Buenos_Aires" → "America/Argentina/Buenos_Aires")
                    parts = tz_name.replace("\\", "/").split("/")
                    short = parts[-1].lower() if parts else ""
                    for known in available:
                        if known.lower().endswith("/" + short):
                            _BA_TZ = _ZoneInfo(known)
                            print(f"[TZ] Partial match '{tz_name}' → '{known}'")
                            break
                    else:
                        from datetime import datetime as _dt
                        _BA_TZ = _dt.now().astimezone().tzinfo
                        print(f"[TZ] Falling back to system timezone: {_BA_TZ}")
    except Exception as e:
        print(f"[TZ] Error reading config: {e}")

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI

def _patch_settings_ui():
    pass

_patch_settings_ui()

from core.runtime.tool_imports import *  # noqa: F401,F403  (Fase 5)



def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LOG_PATH        = BASE_DIR / "jarvis.log"

# ── Redirect output to log file (pythonw.exe has no console) ─
try:
    import io as _io
    _log_fh = open(LOG_PATH, "w", encoding="utf-8", buffering=1)

    class _TeeStream:
        def __init__(self, *streams):
            self._streams = [s for s in streams if s is not None]
        def write(self, data):
            for s in self._streams:
                try: s.write(data)
                except Exception: pass
        def flush(self):
            for s in self._streams:
                try: s.flush()
                except Exception: pass
        @property
        def encoding(self): return "utf-8"
        def fileno(self): raise _io.UnsupportedOperation("fileno")

    sys.stdout = _TeeStream(sys.stdout, _log_fh)
    sys.stderr = _TeeStream(sys.stderr, _log_fh)
except Exception:
    pass

# ── Suppress console windows from all child subprocesses ─────────────────────
if sys.platform == "win32":
    try:
        import ctypes as _ctypes
        if _ctypes.windll.kernel32.GetConsoleWindow() == 0:
            import subprocess as _sp
            _CREATE_NO_WINDOW = 0x08000000
            _orig_Popen = _sp.Popen
            class _NoCmdPopen(_orig_Popen):
                def __init__(self, *args, **kwargs):
                    kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_NO_WINDOW
                    super().__init__(*args, **kwargs)
            _sp.Popen = _NoCmdPopen
            print("[JARVIS] subprocess.Popen patched: CREATE_NO_WINDOW active")
    except Exception as _e:
        print(f"[JARVIS] Could not patch subprocess: {_e}")

# Config de voz y audio extraída a core/runtime/ (Fase 2). Se reimporta con los
# mismos nombres internos para no tocar los call-sites de JarvisLive.
from core.runtime.voice import (
    LIVE_MODEL, JARVIS_VOICES,
    voice_model as _voice_model, jarvis_voice as _get_jarvis_voice,
)
from core.runtime.audio import (
    CHANNELS, SEND_SAMPLE_RATE, RECEIVE_SAMPLE_RATE, CHUNK_SIZE, PLAY_CHUNK_SIZE,
    audio_device as _audio_device,
)
from core.runtime import dispatcher as _dispatch  # ejecución de tools (Fase 2)


_cached_api_key: str | None = None

def _get_api_key() -> str:
    global _cached_api_key
    if _cached_api_key:
        return _cached_api_key
    from memory.config_manager import cfg
    _cached_api_key = cfg("gemini_api_key", "")
    return _cached_api_key


# Prompt / memoria / transcript extraídos a core/runtime/prompt.py (Fase 2).
from core.runtime.prompt import (
    load_system_prompt as _load_system_prompt,
    load_markdown_memory as _load_markdown_memory,
    clean_transcript as _clean_transcript,
    build_system_instruction as _build_sys_instruction,
)

from core.tool_declarations import TOOL_DECLARATIONS
# Fase 1: fusiona las tools migradas a @tool (autodescriptivas) con el archivo base.
# discover_action_tools importa TODAS las actions (incluidas las lazy-load) para que
# sus decoradores @tool se registren antes de fusionar.
try:
    from core.registry import discover_action_tools as _discover, first_party_declarations as _first_party
    _discover()
    TOOL_DECLARATIONS = _first_party(TOOL_DECLARATIONS)
except Exception as _fpe:
    print(f"[Registry] no pude fusionar tools @tool: {_fpe}")
from core.skill_loader import (
    get_skill_tool_declarations,
    build_skill_dispatch,
    list_skills_human,
)

# ── MCP client: carga servers externos y mergea sus tools ────────────────
# JARVIS_SKIP_MCP=1 evita arrancar los servers MCP al importar (tests/CI).
_mcp_manager = None
if os.getenv("JARVIS_SKIP_MCP") == "1":
    print("[MCP] omitido (JARVIS_SKIP_MCP=1)")
else:
    try:
        from core.mcp_client import get_manager as _mcp_get_manager
        _mcp_manager = _mcp_get_manager()
        _mcp_loaded = _mcp_manager.load_from_config()
        if _mcp_loaded > 0:
            print(f"[MCP] {_mcp_loaded} server(s) iniciado(s)")
            print(_mcp_manager.list_servers())
        _mcp_decls = _mcp_manager.get_tool_declarations()
        if _mcp_decls:
            TOOL_DECLARATIONS = TOOL_DECLARATIONS + _mcp_decls
            print(f"[MCP] +{len(_mcp_decls)} tools agregadas al registry de Gemini")
        # Cierre limpio al salir
        import atexit
        atexit.register(_mcp_manager.shutdown)
        # SIGTERM (kill, reinicios) NO corre atexit por defecto → cada reinicio
        # filtraba un server MCP huérfano. Convertirlo en sys.exit lo arregla.
        import signal as _signal

        def _graceful_term(_signum, _frame):
            raise SystemExit(0)
        try:
            _signal.signal(_signal.SIGTERM, _graceful_term)
        except Exception:
            pass
    except Exception as _mcpe:
        print(f"[MCP] no disponible: {_mcpe}")
        _mcp_manager = None

# Cargar skills dinámicas (carpetas con SKILL.md) y mergear con las core
_skill_decls = get_skill_tool_declarations()
_skill_dispatch = build_skill_dispatch()
if _skill_decls:
    print(f"[Skills] {len(_skill_decls)} skills cargadas desde skills/")
    print(list_skills_human())
    # Skills tienen precedencia sobre core (mismo nombre → gana skill)
    _core_names = {td["name"] for td in TOOL_DECLARATIONS}
    _skill_names = {td["name"] for td in _skill_decls}
    _overrides = _core_names & _skill_names
    if _overrides:
        # Quitar duplicados core, queda la versión skill
        TOOL_DECLARATIONS = [td for td in TOOL_DECLARATIONS if td["name"] not in _overrides]
        print(f"[Skills] Override de core por skill: {_overrides}")
    TOOL_DECLARATIONS = TOOL_DECLARATIONS + _skill_decls


# ── Registry de tools "estándar" (call_in_executor → action_fn → result o fallback) ──
# Formato: name → (function_ref, extra_kwargs_to_pass, fallback_msg, ui_log_prefix)
# - extra_kwargs: lista con cualquier combo de "response", "speak"
# - fallback_msg: usado solo si la función devuelve None/""
# - ui_log_prefix: si != None, se loguea antes de ejecutar
STANDARD_TOOL_HANDLERS = {
    "open_app":         (open_app,           ["response"], "Done.", None),
    "weather_report":   (weather_action,     [],           "Weather delivered.", None),
    "browser_control":  (browser_control,    [],           "Done.", None),
    "visual_click":     (visual_click,       [],           "Done.", None),
    "file_controller":  (file_controller,    [],           "Done.", None),
    "reminder":         (reminder,           ["response"], "Reminder set.", None),
    "youtube_video":    (youtube_video,      ["response"], "Done.", None),
    "screen_vision":    (screen_vision,      [],           "No pude analizar la imagen/pantalla.", None),
    "screen_process":   (screen_vision,      [],           "No pude analizar la imagen/pantalla.", None),
    "desktop_control":  (desktop_control,    [],           "Done.", None),
    "web_search":       (web_search_action,  [],           "Done.", None),
    "image_fetch":      (image_fetch,        [],           "Listo.", "🖼️ Buscando imagen..."),
    "mac_control":      (mac_control,        [],           "Listo.", "🖥️ Controlando macOS..."),
    "media_edit":       (media_edit,         [],           "Listo.", "🎞️ Editando..."),
    "browser_agent":    (browser_agent,      [],           "Listo.", "🌐 Navegando..."),
    "media_download":   (media_download,     [],           "Listo.", "⬇️ Descargando..."),
    "smart_home":       (smart_home,         [],           "Listo.", "🏠 Controlando dispositivos..."),
    "consult_model":    (consult_model,      [],           "Listo.", "🧠 Pensando..."),
    "model_config":     (model_config,       [],           "Listo.", "⚙️ Configurando modelo..."),
    "manage_keys":      (manage_keys,        [],           "Listo.", "🔑 Abriendo API keys..."),
    "system_control":   (system_control,     [],           "Listo.", "🖥️ Sistema..."),
    "realtime_info":    (realtime_info,      [],           "Listo.", "📊 Consultando..."),
    "figma_control":    (figma_control,      [],           "Listo.", "📐 Figma..."),
    "camera_vision":    (camera_vision,      [],           "Listo.", "📷 Mirando..."),
    "set_theme":        (set_theme,          [],           "Listo.", "🎨 Cambiando color..."),
    "code_agent":       (code_agent,         [],           "Listo.", "🛠️ Programando..."),
    "claude_code":      (claude_code,        [],           "Listo.", "🤖 Usando Claude Code..."),
    "antigravity":      (antigravity,        [],           "Listo.", "🛰️ Usando Antigravity..."),
    "trading_bot":      (trading_bot,        [],           "Listo.", "📈 Trading (paper)..."),
    "computer_control": (computer_control,   [],           "Done.", None),
    "google_calendar":  (google_calendar,    [],           "Done.", None),
    "spotify_control":  (spotify_control,    [],           "Done.", None),
    "scheduler":        (scheduler,          ["speak"],    "Done.", None),
    "google_drive":     (google_drive,       [],           "Done.", None),
    "google_maps":      (google_maps,        [],           "Done.", None),
    "gmail_control":    (gmail_control,      [],           "Done.", None),
    "rules_engine":     (rules_engine,       [],           "Done.", None),
    "user_profile":     (user_profile,       [],           "Done.", None),
    "goals":            (goals,              [],           "Done.", None),
    "git_control":      (git_control,        [],           "Done.", None),
    "knowledge_base":   (knowledge_base,     [],           "Done.", None),
    "whatsapp":         (whatsapp,           [],           "Done.", None),
    "document_creator": (document_creator,   [],           "Done.", None),
    "system_monitor":   (system_monitor,     [],           "Done.", None),
    "morning_brief":    (morning_brief,      [],           "Aquí está tu informe del día.", None),
    "recall":           (recall_run,         [],           "Sin coincidencias.", "🧠 Buscando en memoria..."),
    "compact_sessions": (compact_sessions_run,[],          "Compactación ejecutada.", "📚 Compactando sesiones..."),
    "planner":          (planner,            ["speak"],    "Plan ejecutado.", "📋 Planificando..."),
    "skill_workshop":   (skill_workshop_run, ["speak"],    "Workshop ejecutado.", "🔬 Revisando memoria..."),
    "mcp_explorer":     (mcp_explorer_run,   ["speak"],    "MCP Explorer OK.", "🔭 Consultando research de MCPs..."),
    "notifications":    (notifications_run,  ["speak"],    "Notificaciones OK.", "📬 Configurando notificaciones..."),
    "adobe_control":    (adobe_control,      ["speak"],    "Adobe OK.", "🎨 Controlando Adobe..."),
    "terminal_agent":   (terminal_agent,     [],           "Comando ejecutado.", "⚠️ Ejecutando en Terminal..."),
    "native_ui":        (native_ui,          [],           "Acción de UI completada.", "💻 UI Nativa en acción..."),
}


# ── Registry unificado (Fase 0): vista única sobre el sistema actual ─────────
# NO cambia el dispatch; refleja STANDARD_TOOL_HANDLERS + TOOL_DECLARATIONS y queda
# disponible como `main.REGISTRY` / core.registry.active_registry() para lo que viene.
REGISTRY = None
try:
    from core.registry import build_from_legacy as _build_reg, set_active_registry as _set_reg
    REGISTRY = _build_reg(STANDARD_TOOL_HANDLERS, TOOL_DECLARATIONS)
    _set_reg(REGISTRY)
    _by_src = {}
    for _t in REGISTRY.all():
        _by_src[_t.source] = _by_src.get(_t.source, 0) + 1
    print(f"[Registry] {len(REGISTRY)} tools unificadas — "
          + ", ".join(f"{k}:{v}" for k, v in sorted(_by_src.items())))
except Exception as _rege:
    print(f"[Registry] no se pudo construir: {_rege}")
    REGISTRY = None


class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.is_sleeping    = False
        self.vosk_recognizer = None
        try:
            import vosk
            if os.path.exists("config/vosk_model"):
                model = vosk.Model("config/vosk_model")
                self.vosk_recognizer = vosk.KaldiRecognizer(model, 16000)
                print("[JARVIS] Modelo Vosk cargado para Modo Suspensión.")
        except Exception as e:
            print(f"[JARVIS] No se pudo cargar Vosk: {e}")
        self.audio_in_queue = None
        # Iniciar scheduler y motor de reglas en background al arrancar JARVIS
        start_runner(player=ui, speak=None)
        start_rules_runner(player=ui, speak=None)
        # Investigador continuo de MCPs en background
        if start_mcp_explorer:
            try:
                start_mcp_explorer(player=ui)
            except Exception as _mce:
                print(f"[JARVIS] mcp_explorer no arrancó: {_mce}")
        # Auto-programar skill_workshop nocturno (3:00 AM, una vez por install)
        try:
            from actions.scheduler import _load_tasks as _sched_load, scheduler as _sched
            _existing = _sched_load()
            if not any(t.get("name") == "workshop_nightly" for t in _existing):
                _sched({
                    "action": "create",
                    "name": "workshop_nightly",
                    "frequency": "daily",
                    "hour": 3, "minute": 0,
                    "task_action": "tool_invoke",
                    "task_parameters": {"tool": "skill_workshop", "args": {"action": "review", "days": 7}},
                }, player=None)
                print("[JARVIS] 🔬 skill_workshop nocturno programado (3:00 AM diario).")
        except Exception as _wse:
            print(f"[JARVIS] No pude auto-programar workshop: {_wse}")
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self.ui.on_text_command = self._on_text_command
        self.ui.on_stop_command = self._on_stop_pressed
        self.ui.on_config_saved = self._apply_config
        self._turn_done_event: asyncio.Event | None = None
        self._api_1011_tool: str | None = None   # tracks tool name when 1011 hits
        self._reconnect_event: asyncio.Event | None = None
        self._first_connect = True  # flag for auto morning brief + guardian start
        self._resume_handle: str | None = None  # session resumption handle (saves tokens on reconnect)
        # Episodic logger — append-only JSONL en ~/.jarvis/sessions/
        self.episodic = EpisodicLogger() if EpisodicLogger else None
        if self.episodic:
            print(f"[JARVIS] 📔 Episodic logger: {self.episodic.path}")
        # Cierre limpio al salir
        import atexit
        if self.episodic:
            atexit.register(self.episodic.close)

        # Notification Engine: arranca después de que la sesión Live esté lista
        # (se inicia desde run() para tener acceso a inject_text)
        self.notif_engine = get_notif_engine() if get_notif_engine else None

    def _inject_text(self, text: str):
        """Thread-safe injection of a text message into the current live session."""
        if self._loop and self.session and not self._is_speaking:
            asyncio.run_coroutine_threadsafe(
                self.session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True
                ),
                self._loop
            )

    def _apply_config(self, cfg: dict):
        """Called from UI thread when user saves settings. Triggers session reconnect."""
        global _cached_api_key
        _cached_api_key = None  # Invalidate cached key so new one is loaded on reconnect
        print("[JARVIS] ⚙️ Config actualizada — reconectando sesión...")
        self.ui.write_log("SYS: Aplicando nueva configuración...")
        if self._reconnect_event and self._loop:
            self._loop.call_soon_threadsafe(self._reconnect_event.set)

    async def _watch_reconnect(self):
        """Task that triggers a graceful reconnect when config changes."""
        if self._reconnect_event:
            await self._reconnect_event.wait()
            raise RuntimeError("Config changed — reconnect requested")

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return

        # Audio file: process with Gemini Vision (not the realtime audio session)
        if text.startswith("[AUDIO_FILE]"):
            m = re.search(r'path=([^\s|]+)', text)
            if m:
                asyncio.run_coroutine_threadsafe(
                    self._process_audio_file(m.group(1)), self._loop
                )
            return

        # Episodic log: registrar entrada del usuario (texto)
        if self.episodic:
            self.episodic.log_user_turn(text)

        # Check phrase triggers — if one fires, don't also send to Gemini
        if self._fire_phrase_triggers(text):
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    async def _process_audio_file(self, path: str):
        """Transcribe and analyze an audio file via Gemini (separate from realtime session)."""
        try:
            p = Path(path)
            if not p.exists():
                self.ui.write_log(f"❌ Archivo no encontrado: {path}")
                return

            self.ui.set_state("THINKING")
            self.ui.write_log(f"🎵 Procesando audio: {p.name}…")

            data = p.read_bytes()
            ext  = p.suffix.lower().lstrip(".")
            mime_map = {
                "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4",
                "ogg": "audio/ogg",  "flac": "audio/flac", "aac": "audio/aac",
                "wma": "audio/x-ms-wma", "opus": "audio/opus", "webm": "audio/webm",
            }
            mime = mime_map.get(ext, "audio/mpeg")

            loop = asyncio.get_event_loop()

            def _analyze():
                client = genai.Client(api_key=_get_api_key())
                resp = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        types.Content(parts=[
                            types.Part(text=(
                                f"El usuario adjuntó un archivo de audio: '{p.name}'.\n"
                                "1. Transcribí el contenido del audio.\n"
                                "2. Si es música, identificá la canción/artista si podés.\n"
                                "3. Describí brevemente qué contiene.\n"
                                "Respondé en español."
                            )),
                            types.Part(
                                inline_data=types.Blob(data=data, mime_type=mime)
                            ),
                        ])
                    ],
                )
                return resp.text.strip()

            result = await loop.run_in_executor(_TOOL_EXECUTOR, _analyze)
            self.ui.write_log(f"JARVIS: {result}")

            # Feed result back into the realtime session so JARVIS can speak it
            if self.session:
                await self.session.send_client_content(
                    turns={"parts": [{"text": f"[RESULTADO AUDIO '{p.name}']\n{result}"}]},
                    turn_complete=True
                )

        except Exception as e:
            traceback.print_exc()
            self.ui.write_log(f"❌ Error procesando audio: {e}")
        finally:
            if not self.ui.muted:
                self.ui.set_state("LISTENING")

    def _fire_phrase_triggers(self, user_text: str) -> bool:
        """
        Check phrase-based automations. Returns True if any trigger fired
        (caller should skip sending the text to Gemini in that case).
        """
        text_lower = user_text.lower()

        # ── Accessibility quick triggers ──────────────────────────────────────
        if any(p in text_lower for p in ["activar seguimiento ocular", "iniciar eye tracking",
                                          "activar control ocular", "encender seguimiento de ojos"]):
            if eye_tracking:
                result = eye_tracking({"action": "start"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["detener seguimiento ocular", "apagar eye tracking",
                                          "desactivar control ocular"]):
            if eye_tracking:
                result = eye_tracking({"action": "stop"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["activar detector de movimientos", "iniciar movimiento",
                                          "activar micromovimientos", "encender control por cabeza"]):
            if micro_movement:
                result = micro_movement({"action": "start"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["detener detector de movimientos", "apagar micromovimientos"]):
            if micro_movement:
                result = micro_movement({"action": "stop"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["simplifica", "simplificar", "dividir en pasos"]):
            for phrase in ["simplifica ", "simplificar ", "dividir en pasos "]:
                if phrase in text_lower:
                    task_text = user_text[len(phrase):].strip()
                    if task_text:
                        if task_simplify:
                            result = task_simplify(task_text)
                        else:
                            self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
                        self.ui.write_log("⚡ [Simplificado]\n" + result[:300])
                        return True

        if "agregar rutina" in text_lower or "nueva rutina" in text_lower:
            for phrase in ["agregar rutina ", "nueva rutina "]:
                if phrase in text_lower:
                    routine_name = user_text[len(phrase):].strip()
                    if routine_name:
                        if routine_gamify:
                            result = routine_gamify({"action": "add", "name": routine_name})
                        else:
                            self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
                        self.ui.write_log("⚡ " + result)
                        return True

        if "completar rutina" in text_lower or "terminar rutina" in text_lower:
            for phrase in ["completar rutina ", "terminar rutina "]:
                if phrase in text_lower:
                    routine_name = user_text[len(phrase):].strip()
                    if routine_name:
                        if routine_gamify:
                            result = routine_gamify({"action": "complete", "name": routine_name})
                        else:
                            self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
                        self.ui.write_log("⚡ " + result)
                        return True

        if "mis rutinas" in text_lower or "ver rutinas" in text_lower or "listar rutinas" in text_lower:
            if routine_gamify:
                result = routine_gamify({"action": "list"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ [Rutinas]\n" + result)
            return True

        # ── User-defined phrase automations ───────────────────────────────────
        try:
            triggered = check_phrase_triggers(user_text)
            if triggered:
                for rule in triggered:
                    action = rule.get("action", {})
                    name   = rule.get("name", "?")
                    self.ui.write_log(f"⚡ Automatización: {name}")
                    threading.Thread(
                        target=_rules_run_action, args=(action,), daemon=True
                    ).start()
                return True  # phrase fired → don't also send to Gemini
        except Exception as e:
            print(f"[JARVIS] phrase trigger error: {e}")

        return False

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"I'm afraid {tool_name} ran into a problem, sir. {short}")

    def _on_stop_pressed(self):
        """Llamado desde el hilo de la UI al presionar DETENER o ESC."""
        self._stop_requested.set()
        self.set_speaking(False)
        self.ui.write_log("SYS: ⛔ Respuesta detenida.")
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._drain_audio_queue(), self._loop)

    async def _drain_audio_queue(self):
        """Vacía la cola de audio para cortar la reproducción de inmediato."""
        if self.audio_in_queue:
            while not self.audio_in_queue.empty():
                try:
                    self.audio_in_queue.get_nowait()
                except Exception:
                    break
        self.set_speaking(False)
        if not self.ui.muted:
            self.ui.set_state("LISTENING")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        mem_str = format_memory_for_prompt(load_memory())
        # Refresh timezone from config each reconnect
        _load_tz()
        now = datetime.now(_BA_TZ)
        sys_instruction = _build_sys_instruction(now, str(_BA_TZ), now.strftime("%z"), mem_str)

        # Build SpeechConfig — try to set speaking rate for faster delivery
        _voice_name = _get_jarvis_voice()
        _speech_cfg = None
        try:
            _speech_cfg = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=_voice_name
                    )
                )
            )
        except Exception:
            _speech_cfg = None

        cfg_kwargs: dict = dict(
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=sys_instruction,
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
        )
        if _speech_cfg:
            cfg_kwargs["speech_config"] = _speech_cfg

        # Speaking rate: try output_audio_config (newer SDK versions)
        try:
            cfg_kwargs["output_audio_config"] = types.OutputAudioConfig(
                audio_encoding="LINEAR16",
                speaking_rate=1.15,   # 15% faster — crisp, natural pace
            )
        except Exception:
            pass

        # Temperature directly on LiveConnectConfig (not via deprecated generation_config)
        # Low value = consistent voice tone across reconnects
        try:
            cfg_kwargs["temperature"] = 0.2
        except Exception:
            pass

        # ── VAD: faster end-of-speech detection → lower perceived latency ────
        # Try typed objects first; fall back to raw dict (SDK version resilience)
        _vad_applied = False
        try:
            cfg_kwargs["realtime_input_config"] = types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity="START_SENSITIVITY_HIGH",
                    end_of_speech_sensitivity="END_SENSITIVITY_HIGH",
                    prefix_padding_ms=60,
                    silence_duration_ms=350,
                )
            )
            _vad_applied = True
            print("[JARVIS] VAD config aplicado (typed)")
        except Exception:
            pass

        if not _vad_applied:
            try:
                cfg_kwargs["realtime_input_config"] = {
                    "automatic_activity_detection": {
                        "start_of_speech_sensitivity": "START_SENSITIVITY_HIGH",
                        "end_of_speech_sensitivity": "END_SENSITIVITY_HIGH",
                        "prefix_padding_ms": 100,
                        "silence_duration_ms": 500,
                    }
                }
                print("[JARVIS] VAD config aplicado (dict)")
            except Exception:
                print("[JARVIS] VAD config no aplicado")

        # ── Context compression: prevent session degradation over time ────────
        try:
            cfg_kwargs["context_window_compression"] = types.ContextWindowCompressionConfig(
                trigger_tokens=12000,
                sliding_window=types.SlidingWindow(target_tokens=6000),
            )
        except Exception:
            pass

        # ── Session resumption: server retains context across reconnects ──────
        # Equivalente real de "context caching" para Live API: al reconectar
        # mandamos un handle en vez de re-enviar prompt+memoria+tools (~1000 tokens).
        try:
            handle = getattr(self, "_resume_handle", None)
            cfg_kwargs["session_resumption"] = types.SessionResumptionConfig(handle=handle)
            if handle:
                print(f"[JARVIS] 🔁 Reanudando sesión previa (handle={handle[:12]}...)")
            else:
                print("[JARVIS] 🆕 Habilitando session resumption (nueva sesión)")
        except Exception as _sre:
            print(f"[JARVIS] session_resumption no soportado: {_sre}")

        # ── Thinking budget: disable model reasoning for lowest latency ─────────
        # Set directly on LiveConnectConfig (generation_config field is deprecated)
        try:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            pass

        return types.LiveConnectConfig(**cfg_kwargs)

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")
        _exec_start = __import__("time").perf_counter()



        if name == "shutdown_jarvis":
            self.ui.write_log("SYS: Apagando JARVIS...")
            # Must quit from Qt main thread — signals are thread-safe
            self.ui._win._shutdown_sig.emit()
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Apagando JARVIS. ¡Hasta luego, señor!"}
            )

        if name == "restart_jarvis":
            self.ui.write_log("SYS: Reiniciando JARVIS...")
            # Lanza una instancia nueva (detached) y cierra la actual; señal en el hilo Qt.
            self.ui._win._restart_sig.emit()
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Reiniciando JARVIS. Vuelvo en unos segundos, señor."}
            )

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Memory saved."}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            # ── Path rápido: tool en el registry estándar ────────────────
            if name in STANDARD_TOOL_HANDLERS:
                fn, _extras, _fallback, log_prefix = STANDARD_TOOL_HANDLERS[name]
                if fn is not None and log_prefix:
                    self.ui.write_log(log_prefix)
                result = await loop.run_in_executor(
                    _TOOL_EXECUTOR,
                    lambda: _dispatch.call_standard(name, args, STANDARD_TOOL_HANDLERS, self.ui, self.speak),
                )

            elif name == "sleep_mode":
                self.is_sleeping = True
                self.ui.write_log("SYS: 💤 Entrando en suspensión local.")
                self.ui.set_state("MUTED")
                result = "Entrando en suspensión absoluta. Cortando transmisión a la nube hasta escuchar 'JARVIS'."

            # computer_settings: ya no es un caso especial — su action hace TODO
            # (volumen/ventanas). Cae al fallback dinámico como una tool normal.

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "openrouter_agent":
                if openrouter_agent:
                    self.ui.write_log("🤖 Delegando tarea a agente especialista (Gemini)...")
                    r = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: openrouter_agent(
                            query=args.get("query", ""),
                            model=args.get("model", "gemini-2.5-flash")
                        )
                    )
                    result = r or "Error al procesar con el agente especialista."
                else:
                    result = "Módulo openrouter_agent no encontrado."

            elif name == "jarvis_ui_control":
                action_ui = args.get("action", "").lower()
                widget_name = args.get("widget", "").lower()
                if action_ui == "minimize":
                    try:
                        if hasattr(self.ui, "_win") and hasattr(self.ui._win, "showMinimized"):
                            QMetaObject.invokeMethod(self.ui._win, "showMinimized", Qt.ConnectionType.QueuedConnection)
                        elif hasattr(self.ui, "root") and hasattr(self.ui.root, "iconify"):
                            self.ui.root.after(0, self.ui.root.iconify)
                        result = "Interfaz de usuario minimizada."
                    except Exception as ui_e:
                        result = f"Error al minimizar: {ui_e}"
                elif action_ui == "restore":
                    try:
                        if hasattr(self.ui, "_win") and hasattr(self.ui._win, "showNormal"):
                            QMetaObject.invokeMethod(self.ui._win, "showNormal", Qt.ConnectionType.QueuedConnection)
                            QMetaObject.invokeMethod(self.ui._win, "activateWindow", Qt.ConnectionType.QueuedConnection)
                        elif hasattr(self.ui, "root") and hasattr(self.ui.root, "deiconify"):
                            def _restore():
                                self.ui.root.deiconify()
                                self.ui.root.attributes("-topmost", True)
                                self.ui.root.attributes("-topmost", False)
                            self.ui.root.after(0, _restore)
                        result = "Interfaz de usuario restaurada."
                    except Exception as ui_e:
                        result = f"Error al restaurar: {ui_e}"
                elif action_ui == "hide_all":
                    self.ui.write_log("__hide__")
                    result = "Todos los widgets ocultados."
                elif action_ui in ("show", "hide", "toggle"):
                    if widget_name == "main_window" or not widget_name:
                        if action_ui == "show":
                            try:
                                if hasattr(self.ui, "_win") and hasattr(self.ui._win, "showNormal"):
                                    QMetaObject.invokeMethod(self.ui._win, "showNormal", Qt.ConnectionType.QueuedConnection)
                                    QMetaObject.invokeMethod(self.ui._win, "activateWindow", Qt.ConnectionType.QueuedConnection)
                                elif hasattr(self.ui, "root") and hasattr(self.ui.root, "deiconify"):
                                    def _restore():
                                        self.ui.root.deiconify()
                                        self.ui.root.attributes("-topmost", True)
                                        self.ui.root.attributes("-topmost", False)
                                    self.ui.root.after(0, _restore)
                                result = "Interfaz de usuario restaurada."
                            except Exception as ui_e:
                                result = f"Error al restaurar: {ui_e}"
                        else:
                            self.ui.write_log("__hide__")
                            result = "Todos los widgets ocultados."
                    else:
                        cmd = "__widget_show__" if action_ui in ("show", "toggle") else "__widget_close__"
                        self.ui.write_log(f"{cmd}:{widget_name}")
                        result = f"Widget '{widget_name}' {'mostrado' if 'show' in cmd else 'ocultado'}."
                else:
                    result = f"Acción de UI desconocida: {action_ui}"

            elif name.startswith("mcp__") and _mcp_manager:
                # Tool externa via MCP server. Ruteo por el manager.
                r = await loop.run_in_executor(
                    _TOOL_EXECUTOR,
                    lambda: _mcp_manager.call(name, args)
                )
                result = r or f"MCP tool '{name}' sin output."

            elif name == "whatsapp_connect":
                if whatsapp_connect is None:
                    result = "Módulo whatsapp_connect no disponible."
                else:
                    r = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: whatsapp_connect(parameters=args, player=self.ui, speak=self.speak)
                    )
                    result = r or "WhatsApp."
                    # Si el bridge está corriendo, arrancar el MCP server en vivo + reconectar
                    if _mcp_manager and ("ya está conectado" in (r or "").lower() or "recargar" in (r or "").lower()):
                        try:
                            ok, wa_decls = _mcp_manager.start_one("whatsapp")
                            if ok and wa_decls:
                                globals()["TOOL_DECLARATIONS"] = TOOL_DECLARATIONS + wa_decls
                                self.ui.write_log(f"🟢 WhatsApp MCP activo (+{len(wa_decls)} tools). Reconectando...")
                                if self._reconnect_event and self._loop:
                                    self._loop.call_soon_threadsafe(self._reconnect_event.set)
                                result += f" Activé {len(wa_decls)} herramientas de WhatsApp."
                        except Exception as _wae:
                            self.ui.write_log(f"⚠️ WhatsApp MCP no activó: {_wae}")

            elif name == "skill_teach":
                # Especial: tras generar la skill, refrescar dispatch + reconectar para que aparezca sin reiniciar
                if skill_teach is None:
                    result = "Módulo skill_teach no disponible."
                else:
                    self.ui.write_log("🧠 Aprendiendo skill nueva...")
                    r = await loop.run_in_executor(
                        _TOOL_EXECUTOR,
                        lambda: skill_teach(parameters=args, player=self.ui, speak=self.speak)
                    )
                    result = r or "Skill creada."
                    # Si la creación fue exitosa, hot-reload del dispatch + reconectar
                    if r and "creada" in r.lower() and "no pude" not in r.lower():
                        try:
                            global _skill_dispatch, _skill_decls
                            from core.skill_loader import build_skill_dispatch, get_skill_tool_declarations
                            _skill_dispatch = build_skill_dispatch()
                            _skill_decls = get_skill_tool_declarations()
                            # Reconstruir TOOL_DECLARATIONS para que la sesión nueva la incluya
                            from core import tool_declarations as _td_mod
                            _core_names = {td["name"] for td in _td_mod.TOOL_DECLARATIONS}
                            _skill_names = {td["name"] for td in _skill_decls}
                            _overrides = _core_names & _skill_names
                            _base = [td for td in _td_mod.TOOL_DECLARATIONS if td["name"] not in _overrides]
                            globals()["TOOL_DECLARATIONS"] = _base + _skill_decls
                            self.ui.write_log("🔁 Dispatch refrescado. Reconectando sesión para activar...")
                            # Trigger reconnect — config nuevo incluirá la skill
                            if self._reconnect_event and self._loop:
                                self._loop.call_soon_threadsafe(self._reconnect_event.set)
                        except Exception as reload_err:
                            self.ui.write_log(f"⚠️ Hot-reload falló (reiniciá manual): {reload_err}")

            elif name in _skill_dispatch:
                # Skill cargada desde skills/<name>/skill.py vía SKILL.md
                result = await loop.run_in_executor(
                    _TOOL_EXECUTOR,
                    lambda: _dispatch.call_skill(name, args, _skill_dispatch, self.ui, self.speak),
                )

            else:
                # Fallback: tools dinámicas creadas por tool_creator/auto_programmer
                result = await loop.run_in_executor(
                    _TOOL_EXECUTOR,
                    lambda: _dispatch.call_dynamic(name, args, self.ui, self.speak),
                )

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        # Record action for habit learning (fire-and-forget, non-blocking)
        if record_action:
            threading.Thread(target=lambda: record_action(name, args), daemon=True).start()

        # Episodic log: registrar la tool call con duración + éxito
        if self.episodic:
            _exec_ms = int((__import__("time").perf_counter() - _exec_start) * 1000)
            _success = not _dispatch.is_error_result(result)
            try:
                self.episodic.log_tool_call(name, args, str(result), _exec_ms, _success)
            except Exception:
                pass

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic iniciado")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            if getattr(self, "is_sleeping", False):
                if getattr(self, "vosk_recognizer", None):
                    audio_data = indata.tobytes()
                    if self.vosk_recognizer.AcceptWaveform(audio_data):
                        res = json.loads(self.vosk_recognizer.Result())
                        text = res.get("text", "")
                        if "jarvis" in text.lower():
                            self.is_sleeping = False
                            self.ui.set_state("LISTENING")
                            self.ui.write_log("SYS: 🟢 ¡Despierto!")
                            try:
                                import winsound
                                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
                            except: pass
                return

            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted:
                # Calculate RMS audio level for sphere visualization
                try:
                    rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
                    self.ui.set_audio_level(min(1.0, rms * 18))
                except Exception:
                    pass
                data = indata.tobytes()
                # Silently drop if queue is full (during long tool calls)
                def _safe_put(q, item):
                    try:
                        q.put_nowait(item)
                    except Exception:
                        pass  # Queue full — discard; prevents QueueFull crash
                loop.call_soon_threadsafe(
                    _safe_put, self.out_queue, {"data": data, "mime_type": "audio/pcm"}
                )
            # Mientras JARVIS habla, el nivel lo provee _play_audio con el audio de salida real
            # (no usamos el micrófono acá: sería el eco del parlante).

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
                device=_audio_device("mic_device"),
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.01)  # 10ms — máxima responsividad del mic
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv iniciado")
        out_buf, in_buf = [], []
        _first_chunk   = True
        _last_tool     = None   # track which tool was executing when error hit

        try:
            while True:
                async for response in self.session.receive():

                    # Capturar handle de resumption — permite reconectar sin re-enviar prompt
                    sru = getattr(response, "session_resumption_update", None)
                    if sru and getattr(sru, "resumable", False) and getattr(sru, "new_handle", None):
                        self._resume_handle = sru.new_handle

                    if response.data:
                        if not self._stop_requested.is_set():
                            self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)
                                if _first_chunk:
                                    self.ui.clear_jarvis_response()
                                    _first_chunk = False
                                self.ui.stream_jarvis_chunk(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            self._stop_requested.clear()
                            if self._turn_done_event:
                                self._turn_done_event.set()
                            full_in = " ".join(in_buf).strip()
                            full_out = " ".join(out_buf).strip()
                            if full_in:
                                self.ui.write_log(f"Tú: {full_in}")
                                self._fire_phrase_triggers(full_in)
                                if self.episodic:
                                    self.episodic.log_user_turn(full_in)
                            if full_out and self.episodic:
                                self.episodic.log_assistant_turn(full_out)
                            in_buf = []
                            out_buf = []
                            _first_chunk = True

                    if response.tool_call:
                        self.ui.clear_jarvis_response()
                        _first_chunk = True
                        fcs = response.tool_call.function_calls
                        for fc in fcs:
                            print(f"[JARVIS] 📞 {fc.name}")
                            _last_tool = fc.name
                        # Execute all tool calls in parallel when there are multiple
                        if len(fcs) > 1:
                            tasks = [asyncio.create_task(self._execute_tool(fc)) for fc in fcs]
                            fn_responses = list(await asyncio.gather(*tasks))
                        else:
                            fn_responses = [await self._execute_tool(fcs[0])]
                        try:
                            await self.session.send_tool_response(
                                function_responses=fn_responses
                            )
                            _last_tool = None  # only clear AFTER successful send
                        except Exception as tool_err:
                            print(f"[JARVIS] ❌ send_tool_response failed: {tool_err}")
                            raise
        except Exception as e:
            msg  = str(e)
            code = getattr(e, "status_code", 0) or getattr(e, "code", 0) or 0
            # Detect 1011 (internal server error) regardless of exception type
            if code == 1011 or "1011" in msg or "Internal error" in msg:
                tool_info = f" durante '{_last_tool}'" if _last_tool else ""
                print(f"[JARVIS] ⚡ API 1011{tool_info} — reconectando...")
                self._api_1011_tool = _last_tool
            else:
                print(f"[JARVIS] ❌ Recv: {e}")
                traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play iniciado")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=PLAY_CHUNK_SIZE,
            device=_audio_device("speaker_device"),
        )
        stream.start()

        # Jitter buffer: accumulate a few chunks before playback to prevent underruns
        _jitter_buf: list[bytes] = []
        _JITTER_TARGET = 1  # ~20ms — start playback ASAP for low latency

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.05   # 50ms — faster turn-complete detection
                    )
                except asyncio.TimeoutError:
                    # Must check turn_done + empty BEFORE jitter guard,
                    # otherwise 1-2 stuck chunks in jitter_buf prevent
                    # ever reaching the turn_done check → infinite SPEAKING loop.
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        # Drain remaining jitter buffer before stopping
                        for buffered in _jitter_buf:
                            await asyncio.to_thread(stream.write, buffered)
                        _jitter_buf.clear()
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue

                self.set_speaking(True)
                # Nivel real de lo que JARVIS está diciendo → el orb reacciona a la voz
                try:
                    _s = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
                    if _s.size:
                        _rms = float(np.sqrt(np.mean(_s ** 2))) / 32768.0
                        self.ui.set_audio_level(min(1.0, _rms * 9))
                except Exception:
                    pass
                _jitter_buf.append(chunk)

                # Once we have enough chunks buffered, drain them to the output stream
                if len(_jitter_buf) >= _JITTER_TARGET:
                    for buffered in _jitter_buf:
                        await asyncio.to_thread(stream.write, buffered)
                    _jitter_buf.clear()
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        reconnect_delay   = 1.0
        consecutive_fails = 0

        while True:
            try:
                print("[JARVIS] 🔌 Conectando...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=_voice_model(), config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self._loop            = asyncio.get_event_loop()
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=5)  # buffer moderado — evita drops durante ráfagas de mic
                    self._turn_done_event = asyncio.Event()
                    self._reconnect_event = asyncio.Event()

                    print("[JARVIS] ✅ Conectado.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS en línea.")
                    reconnect_delay   = 1.0   # reset backoff on successful connection
                    consecutive_fails = 0
                    self._api_1011_tool = None   # clear 1011 tool tracker

                    # ── First-connect extras ──────────────────────────────────
                    if self._first_connect:
                        self._first_connect = False
                        # Notification Engine: arrancar watcher con callback inject_text
                        if self.notif_engine:
                            try:
                                self.notif_engine.start(inject_fn=self._inject_text)
                            except Exception as _ne:
                                print(f"[JARVIS] notif_engine no arrancó: {_ne}")
                        # Auto morning brief (6am–12pm, once per day)
                        _hour = __import__("datetime").datetime.now().hour
                        if (
                            morning_brief
                            and already_briefed_today
                            and 6 <= _hour < 12
                            and not already_briefed_today()
                        ):
                            async def _auto_brief():
                                await asyncio.sleep(1)
                                await self.session.send_client_content(
                                    turns={"parts": [{"text": "[AUTO] Dame el informe matutino del día."}]},
                                    turn_complete=True
                                )
                            tg.create_task(_auto_brief())

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._watch_reconnect())

            except Exception as e:
                exceptions = e.exceptions if isinstance(e, ExceptionGroup) else [e]

                is_handshake_timeout = False
                is_config_reconnect  = False
                for exc in exceptions:
                    msg = str(exc)
                    if "Config changed" in msg:
                        # Intentional reconnect triggered by config change — fast, no backoff
                        is_config_reconnect = True
                        consecutive_fails = 0
                    elif "timed out during opening handshake" in msg or (
                        isinstance(exc, TimeoutError) and "handshake" in msg
                    ):
                        # Timeout de WebSocket al conectar — error de red transitorio.
                        # NO incrementar consecutive_fails: sólo reintento rápido.
                        is_handshake_timeout = True
                        print(f"[JARVIS] ⏱️ Timeout al conectar — reintentando en 1s...")
                    elif "1011" in msg or "Internal error" in msg:
                        tool_hint = self._api_1011_tool or ""
                        print(f"[JARVIS] ⚡ API 1011{tool_hint and ' durante '+tool_hint} — reconectando...")
                        consecutive_fails += 1
                        if consecutive_fails >= 4:
                            self.ui.write_log(
                                "SYS: ⚠️ Error 1011 repetido. Esperando para no saturar la API...\n"
                                "SYS: Si persiste más de 2 min, reiniciá JARVIS."
                            )
                        elif tool_hint:
                            self.ui.write_log(f"SYS: Error de servidor al ejecutar '{tool_hint}'. Reconectando...")
                        else:
                            self.ui.write_log("SYS: Error de servidor 1011. Reconectando...")
                    elif "1008" in msg or "policy violation" in msg.lower() or "not found for API version" in msg:
                        # Model not available / wrong API version — log clearly, retry with same model
                        print(f"[JARVIS] ⚠️ Modelo no disponible en esta versión de API: {msg[:120]}")
                        self.ui.write_log("SYS: ⚠️ Modelo no disponible. Reintentando...")
                        consecutive_fails += 1
                    elif "1000" in msg or "going away" in msg.lower():
                        # Cierre normal de la sesión (expiró ~15 min) — silencioso
                        print(f"[JARVIS] 🔄 Sesión expirada — reconectando...")
                        consecutive_fails = 0   # reset: no es un fallo
                    else:
                        print(f"[JARVIS] ⚠️ {exc}")
                        traceback.print_exc()
                        consecutive_fails += 1

                if is_config_reconnect:
                    self.set_speaking(False)
                    self.ui.set_state("THINKING")
                    await asyncio.sleep(0.5)
                    continue

                if is_handshake_timeout:
                    # Timeout en handshake → reintento fijo de 1s, sin backoff
                    self.set_speaking(False)
                    self.ui.set_state("THINKING")
                    await asyncio.sleep(1.0)
                    continue

            self.set_speaking(False)
            self.ui.set_state("THINKING")

            # Exponential backoff con jitter para evitar thundering herd
            # After 5+ fails: wait up to 90s to let API rate limits recover
            if consecutive_fails > 1:
                max_delay = 90.0 if consecutive_fails >= 5 else 12.0
                reconnect_delay = min(reconnect_delay * 2, max_delay)
            elif consecutive_fails == 0:
                reconnect_delay = 1.0

            import random as _rnd
            jitter = _rnd.uniform(0, reconnect_delay * 0.25)
            total  = reconnect_delay + jitter
            print(f"[JARVIS] 🔄 Reconectando en {total:.1f}s...")
            await asyncio.sleep(total)

def main():
    # ── Single Instance Lock (cross-platform) ─────────────────────────────────
    from core.platform_utils import acquire_single_instance_lock
    global _single_instance_lock
    _single_instance_lock = acquire_single_instance_lock("jarvis_ai")
    if _single_instance_lock is None:
        print("[JARVIS] Ya hay una instancia en ejecución. Cerrando.")
        sys.exit(0)

    # ── License check ─────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────────

    # Load timezone from config
    _load_tz()

    def _ensure_api_key():
        # Diálogo unificado de TODAS las API keys (Gemini obligatoria).
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        # Iconos/pixmaps nítidos en pantallas Retina (debe ir ANTES de crear la QApplication).
        try:
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
        except Exception:
            pass
        QApplication.instance() or QApplication(sys.argv)
        from core.credentials import startup_check, init_bridge
        startup_check()      # abre el diálogo si falta Gemini; sale si se cancela
        init_bridge()        # puente para reabrir la ventana on-demand desde las tools
        try:
            from core.camera import init_camera_ui
            init_camera_ui()  # puente para mostrar el preview de cámara desde las tools
        except Exception:
            pass
        try:
            from core.trading_panel import init_panel_bridge
            init_panel_bridge()  # puente para abrir el panel de trading desde la voz
        except Exception:
            pass
        try:
            from core import mac_contacts
            mac_contacts.warm_async()  # cachea la agenda de Apple (nombre↔número WhatsApp)
        except Exception:
            pass
        try:
            from core import whatsapp_bridge
            whatsapp_bridge.init_whatsapp_ui()        # diálogo de QR (hilo de la UI)
            whatsapp_bridge.ensure_started_quietly()  # bridge en background (sin Terminal)
        except Exception as _wbe:
            print(f"[whatsapp] bridge no arrancó: {_wbe}")

    _ensure_api_key()

    ui = JarvisUI("face.png")

    # --- UI COSMETICS PATCH ---
    try:
        if hasattr(ui, "_win"):
            # Aumentar transparencia (Glassmorphism)
            ui._win.setWindowOpacity(0.85)
            # Reemplazar textos "Beta" y "Gratuito"
            from PyQt6.QtWidgets import QLabel
            for label in ui._win.findChildren(QLabel):
                text_lower = label.text().lower()
                if "beta" in text_lower or "gratuita" in text_lower or "gratuito" in text_lower or "premium" in text_lower:
                    try:
                        # Ocultar el contenedor completo del banner (incluye el botón PRO)
                        label.parentWidget().hide()
                    except:
                        label.hide()

            # 2. Add keyboard shortcut & Global Hotkey (INS / Insert key) to wake up JARVIS
            from PyQt6.QtGui import QKeySequence, QShortcut
            from PyQt6.QtCore import Qt, QTimer

            def on_shortcut_triggered():
                # Wake up / unmute JARVIS
                if hasattr(ui, "_win"):
                    # Si está muteado, desmutearlo para que escuche
                    if getattr(ui, "muted", False):
                        if hasattr(ui._win, "_toggle_mute"):
                            ui._win._toggle_mute()
                            ui.write_log("SYS: 🎤 Micrófono ACTIVADO vía atajo INS.")
                    else:
                        # Si ya está activo, mostrar/restaurar la ventana principal y enfocarla
                        if hasattr(ui._win, "showNormal"):
                            ui._win.showNormal()
                            ui._win.activateWindow()
                            ui.write_log("SYS: 🔔 JARVIS en foco vía atajo INS.")
                        
                        # Cambiar estado visual a escuchando
                        try:
                            ui.set_state("LISTENING")
                        except:
                            pass

            # A. PyQt Window Shortcut (for local window events)
            local_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Insert), ui._win)
            local_shortcut.activated.connect(on_shortcut_triggered)

            # B. Win32 Native Global Hotkey Hook (for background capture)
            def setup_global_hotkey():
                if sys.platform != "win32":
                    print("[HOTKEY] Global hotkey Win32 deshabilitado: solo soportado en Windows.")
                    return
                import threading
                import ctypes
                import ctypes.wintypes

                def hotkey_thread():
                    user32 = ctypes.windll.user32
                    # MOD_NOREPEAT = 0x4000
                    # VK_INSERT = 0x2D
                    try:
                        if not user32.RegisterHotKey(None, 99, 0x0000, 0x2D):
                            print("[HOTKEY] Error registering global Insert hotkey.")
                            return
                    except Exception as e:
                        print(f"[HOTKEY] Exception registering global hotkey: {e}")
                        return

                    try:
                        msg = ctypes.wintypes.MSG()
                        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                            if msg.message == 0x0312: # WM_HOTKEY
                                if msg.wParam == 99:
                                    # Thread-safely trigger UI callback inside PyQt event loop
                                    QTimer.singleShot(0, on_shortcut_triggered)
                            user32.TranslateMessage(ctypes.byref(msg))
                            user32.DispatchMessageW(ctypes.byref(msg))
                    finally:
                        user32.UnregisterHotKey(None, 99)

                threading.Thread(target=hotkey_thread, daemon=True).start()

            setup_global_hotkey()
            print("[PATCH] Avengers: Age of Ultron golden aesthetics & Insert global hotkey loaded successfully!")

    except Exception as e:
        print(f"[PATCH] Cosmetics & Shortcut patch failed: {e}")

    def runner():
        ui.wait_for_api_key()
        # Onboarding de permisos de macOS — solo en el primer arranque
        try:
            from core.permissions import onboard_if_first_run
            report = onboard_if_first_run(player=ui)
            if report:
                for line in report.splitlines():
                    try:
                        ui.write_log(line)
                    except Exception:
                        pass
        except Exception as _pe:
            print(f"[permissions] onboarding falló: {_pe}")
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Apagando...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()