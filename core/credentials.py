"""
credentials.py — Gestión central de API keys + diálogo unificado (PyQt6).

- Ventana con TODAS las keys agrupadas por categoría. Gemini es obligatoria.
- Se puede abrir al arranque (modal, exige Gemini) o on-demand desde cualquier hilo
  (las tools corren en un hilo distinto al de la UI → usamos un puente con señal Qt).
- Al guardar, los secretos van al .env (config_manager.set_secret) y se invalida el cache.

Helpers para las integraciones:
  require_key("openai")  -> (ok, mensaje). Si falta, abre el diálogo y explica.
"""
from __future__ import annotations

# (clave_en_config, etiqueta, categoría, es_secreto, es_obligatoria, default)
KEY_SPECS = [
    ("gemini_api_key",     "Gemini API Key (obligatoria)", "Cerebros de IA", True, True, ""),
    ("openai_api_key",     "OpenAI (GPT)",                 "Cerebros de IA", True, False, ""),
    ("anthropic_api_key",  "Anthropic (Claude)",           "Cerebros de IA", True, False, ""),
    ("openrouter_api_key", "OpenRouter",                   "Cerebros de IA", True, False, ""),
    ("minimax_api_key",    "MiniMax",                      "Cerebros de IA", True, False, ""),
    ("tmdb_api_key",       "TMDB (pelis/series)",          "Contenido",      True, False, ""),
    ("alpaca_api_key",     "Alpaca API Key ID",            "Trading (broker real)", True, False, ""),
    ("alpaca_secret_key",  "Alpaca Secret Key",            "Trading (broker real)", True, False, ""),
    ("figma_token",        "Figma (token personal)",       "Diseño",         True, False, ""),
    ("spotify_client_id",     "Spotify Client ID",         "Spotify",        True, False, ""),
    ("spotify_client_secret", "Spotify Client Secret",     "Spotify",        True, False, ""),
    ("spotify_redirect_uri",  "Spotify Redirect URI",      "Spotify",        False, False, "http://127.0.0.1:8888/callback"),
    ("tuya_api_key",    "Tuya Access ID",                  "Casa (Tuya)",    True, False, ""),
    ("tuya_api_secret", "Tuya Access Secret",              "Casa (Tuya)",    True, False, ""),
    ("tuya_region",     "Tuya Región (us/eu/cn/in)",       "Casa (Tuya)",    False, False, "us"),
    ("github_personal_access_token", "GitHub Token",       "Integraciones MCP", True, False, ""),
    ("telegram_bot_api_token",       "Telegram Bot Token", "Integraciones MCP", True, False, ""),
    ("brave_api_key",                "Brave Search",       "Integraciones MCP", True, False, ""),
    ("notion_token",                 "Notion (token de integración)", "Integraciones MCP", True, False, ""),
    ("composio_api_key",             "Composio",           "Integraciones MCP", True, False, ""),
]

# integración → claves que necesita
INTEGRATION_KEYS = {
    "gemini": ["gemini_api_key"],
    "openai": ["openai_api_key"], "gpt": ["openai_api_key"],
    "claude": ["anthropic_api_key"], "anthropic": ["anthropic_api_key"],
    "openrouter": ["openrouter_api_key"],
    "minimax": ["minimax_api_key"],
    "tmdb": ["tmdb_api_key"],
    "alpaca": ["alpaca_api_key", "alpaca_secret_key"], "trading": ["alpaca_api_key", "alpaca_secret_key"],
    "figma": ["figma_token"],
    "spotify": ["spotify_client_id", "spotify_client_secret"],
    "tuya": ["tuya_api_key", "tuya_api_secret"], "smart_home": ["tuya_api_key", "tuya_api_secret"],
    "github": ["github_personal_access_token"],
    "telegram": ["telegram_bot_api_token"],
    "brave": ["brave_api_key"],
    "notion": ["notion_token"],
    "composio": ["composio_api_key"],
}

_LABELS = {k: lbl for k, lbl, *_ in KEY_SPECS}


def _cfg(key, default=""):
    try:
        from memory.config_manager import cfg
        return cfg(key, default)
    except Exception:
        return default


def missing_keys(integration: str) -> list[str]:
    needed = INTEGRATION_KEYS.get((integration or "").lower(), [])
    return [k for k in needed if not _cfg(k)]


def integration_status() -> str:
    lines = ["Estado de integraciones:"]
    for name, keys in INTEGRATION_KEYS.items():
        if name in ("gpt", "anthropic", "smart_home"):
            continue  # alias
        ok = all(_cfg(k) for k in keys)
        lines.append(f"  {'✓' if ok else '✗'} {name}")
    return "\n".join(lines)


# ───────────────────────── puente entre hilos ─────────────────────────

_BRIDGE = None


def init_bridge():
    """Crear en el hilo de la UI (después de que exista la QApplication)."""
    global _BRIDGE
    if _BRIDGE is not None:
        return
    try:
        from PyQt6.QtCore import QObject, pyqtSignal, Qt

        class _Bridge(QObject):
            req = pyqtSignal(str)

            def __init__(self):
                super().__init__()
                self.req.connect(self._open, Qt.ConnectionType.QueuedConnection)

            def _open(self, highlight):
                try:
                    open_dialog(highlight or None)
                except Exception as e:
                    print(f"[credentials] error abriendo diálogo: {e}")

        _BRIDGE = _Bridge()
    except Exception as e:
        print(f"[credentials] no se pudo iniciar el puente: {e}")


def request_dialog(highlight: str = "") -> bool:
    """Pedir abrir el diálogo desde cualquier hilo. False si no hay GUI."""
    if _BRIDGE is None:
        return False
    _BRIDGE.req.emit(highlight or "")
    return True


def require_key(integration: str, open_window: bool = True) -> tuple[bool, str]:
    """
    Para que una integración chequee su key antes de actuar.
    Devuelve (ok, mensaje). Si falta, (opcionalmente) abre la ventana y explica.
    """
    miss = missing_keys(integration)
    if not miss:
        return True, ""
    labels = ", ".join(_LABELS.get(k, k) for k in miss)
    opened = request_dialog(integration) if open_window else False
    extra = " Te abrí la ventana para que la cargues." if opened else \
            " Cargala en el .env (o pedime 'abrí el menú de API keys')."
    return False, f"No está disponible: falta la API key de {integration} ({labels}).{extra}"


# ───────────────────────── diálogo PyQt6 ─────────────────────────

def open_dialog(highlight: str | None = None, startup: bool = False) -> bool:
    """Abre el diálogo de credenciales (en el hilo de la UI). Devuelve True si guardó."""
    try:
        from PyQt6.QtWidgets import (
            QApplication, QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
            QPushButton, QGroupBox, QScrollArea, QWidget, QMessageBox, QHBoxLayout)
        from PyQt6.QtCore import Qt
    except Exception:
        return False

    app = QApplication.instance() or QApplication([])

    # claves a resaltar (de una integración puntual)
    hl_keys = set(INTEGRATION_KEYS.get((highlight or "").lower(), []))

    dialog = QDialog()
    dialog.setWindowTitle("JARVIS — Configuración de API Keys")
    dialog.resize(560, 640)
    dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    root = QVBoxLayout(dialog)

    info = QLabel("Configurá tus claves. Solo <b>Gemini</b> es obligatoria; el resto "
                  "habilita integraciones opcionales. Se guardan localmente en el .env.")
    info.setWordWrap(True)
    info.setStyleSheet("font-size: 13px; margin-bottom: 6px;")
    root.addWidget(info)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    container = QWidget()
    cl = QVBoxLayout(container)

    inputs: dict[str, QLineEdit] = {}
    cats: dict[str, QFormLayout] = {}
    for key, label, cat, secret, mandatory, default in KEY_SPECS:
        if cat not in cats:
            box = QGroupBox(cat)
            form = QFormLayout(box)
            cats[cat] = form
            cl.addWidget(box)
        edit = QLineEdit()
        edit.setText(_cfg(key, default))
        if secret:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        if key in hl_keys:
            edit.setStyleSheet("border: 2px solid #e0a82e; border-radius: 4px;")
            edit.setPlaceholderText("← necesaria para lo que pediste")
        inputs[key] = edit
        cats[cat].addRow(QLabel(label + ":"), edit)

    # ── Prioridad del cerebro de código (solo importa si hay varias opciones) ──
    brain_widgets = None
    try:
        brain_widgets = _add_code_brain_section(cl)
    except Exception as e:
        print(f"[credentials] no pude armar la sección de prioridad: {e}")

    # ── Zona horaria (saludo + recordatorios + scheduler) ──
    tz_widget = None
    try:
        tz_widget = _add_timezone_section(cl)
    except Exception as e:
        print(f"[credentials] no pude armar la sección de zona horaria: {e}")

    # ── Dispositivos de audio (micrófono / altavoz) ──
    audio_widgets = None
    try:
        audio_widgets = _add_audio_devices_section(cl)
    except Exception as e:
        print(f"[credentials] no pude armar la sección de audio: {e}")

    # ── Spotify: enlazar cuenta (OAuth, un click) ──
    try:
        _add_spotify_link_section(cl, inputs)
    except Exception as e:
        print(f"[credentials] no pude armar la sección de Spotify: {e}")

    # ── Google (Calendar/Gmail/Drive): credencial por ARCHIVO, no texto ──
    try:
        _add_google_section(cl)
    except Exception as e:
        print(f"[credentials] no pude armar la sección de Google: {e}")

    scroll.setWidget(container)
    root.addWidget(scroll)

    status = QLabel("")
    status.setStyleSheet("color: #c0392b;")
    root.addWidget(status)

    btns = QHBoxLayout()
    btn_save = QPushButton("Guardar y conectar")
    btn_save.setStyleSheet("background:#0078D7; color:white; font-weight:bold; padding:8px; border-radius:4px;")
    btn_cancel = QPushButton("Cancelar")
    btns.addWidget(btn_cancel)
    btns.addWidget(btn_save)
    root.addLayout(btns)

    saved = {"ok": False}

    def on_save():
        from memory.config_manager import set_secret
        gem = inputs["gemini_api_key"].text().strip()
        if not gem:
            status.setText("La clave de Gemini es obligatoria.")
            return
        for key, *_ in [(k,) for k, *_ in KEY_SPECS]:
            val = inputs[key].text().strip()
            if val:
                set_secret(key, val)
        # guardar prioridad del cerebro de código (ajuste, no secreto)
        if brain_widgets:
            try:
                _save_code_brain_section(brain_widgets)
            except Exception as e:
                print(f"[credentials] no pude guardar la prioridad: {e}")
        # guardar zona horaria elegida (ajuste, no secreto)
        if tz_widget is not None:
            try:
                _save_timezone_section(tz_widget)
            except Exception as e:
                print(f"[credentials] no pude guardar zona horaria: {e}")
        # guardar dispositivos de audio elegidos (ajuste, no secreto)
        if audio_widgets:
            try:
                _save_audio_devices_section(audio_widgets)
            except Exception as e:
                print(f"[credentials] no pude guardar audio: {e}")
        # invalidar cache del Live
        try:
            import main as _m
            _m._cached_api_key = None
        except Exception:
            pass
        saved["ok"] = True
        dialog.accept()

    def on_cancel():
        if startup and not _cfg("gemini_api_key"):
            import sys
            sys.exit(0)   # al arranque sin Gemini no se puede continuar
        dialog.reject()

    btn_save.clicked.connect(on_save)
    btn_cancel.clicked.connect(on_cancel)

    dialog.exec()
    return saved["ok"]


def _add_code_brain_section(parent_layout):
    """Sección 'Prioridad para programar' dentro del diálogo. Devuelve los widgets para guardar.

    Lista reordenable (subir/bajar) de los cerebros de código + interruptor 'preguntarme siempre'.
    Solo afecta cuando hay VARIAS opciones disponibles; con una sola, JARVIS la usa sin preguntar.
    """
    from PyQt6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
                                 QListWidgetItem, QPushButton, QCheckBox)
    from PyQt6.QtCore import Qt
    from core import code_brain as cb

    box = QGroupBox("Prioridad para programar (cerebro de código)")
    v = QVBoxLayout(box)
    info = QLabel("Cuando pidas programar y haya <b>varias</b> opciones disponibles, JARVIS usará "
                  "la primera de esta lista. Si solo hay una, la usa directo (no pregunta). "
                  "Gemini Flash 2.5 es el respaldo final.")
    info.setWordWrap(True)
    info.setStyleSheet("font-size: 12px;")
    v.addWidget(info)

    ask = QCheckBox("Preguntarme siempre cuál usar (ignora el orden de abajo)")
    ask.setChecked(cb.get_mode() == "ask")
    v.addWidget(ask)

    avail = cb.availability()
    lst = QListWidget()
    lst.setMaximumHeight(150)
    for bid in cb.get_priority():
        mark = "✓" if avail.get(bid) else "✗ (no configurado)"
        it = QListWidgetItem(f"{cb.LABELS[bid]}   {mark}")
        it.setData(Qt.ItemDataRole.UserRole, bid)
        lst.addItem(it)
    v.addWidget(lst)

    row = QHBoxLayout()
    up = QPushButton("▲ Subir")
    down = QPushButton("▼ Bajar")
    row.addWidget(up)
    row.addWidget(down)
    row.addStretch()
    v.addLayout(row)

    def move(delta):
        i = lst.currentRow()
        if i < 0:
            return
        j = i + delta
        if 0 <= j < lst.count():
            it = lst.takeItem(i)
            lst.insertItem(j, it)
            lst.setCurrentRow(j)

    up.clicked.connect(lambda: move(-1))
    down.clicked.connect(lambda: move(1))

    parent_layout.addWidget(box)
    return {"ask": ask, "list": lst}


def _save_code_brain_section(widgets) -> None:
    from PyQt6.QtCore import Qt
    from core import code_brain as cb
    cb.set_mode("ask" if widgets["ask"].isChecked() else "auto")
    lst = widgets["list"]
    order = [lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())]
    cb.set_priority(order)


# Zonas horarias comunes (LatAm + principales). value = nombre IANA, label = amistoso.
_COMMON_TZS = [
    ("America/Bogota", "Colombia — Bogotá"),
    ("America/Mexico_City", "México — CDMX"),
    ("America/Lima", "Perú — Lima"),
    ("America/Argentina/Buenos_Aires", "Argentina — Buenos Aires"),
    ("America/Santiago", "Chile — Santiago"),
    ("America/Caracas", "Venezuela — Caracas"),
    ("America/Sao_Paulo", "Brasil — São Paulo"),
    ("America/Guayaquil", "Ecuador — Quito/Guayaquil"),
    ("America/La_Paz", "Bolivia — La Paz"),
    ("America/Montevideo", "Uruguay — Montevideo"),
    ("America/Asuncion", "Paraguay — Asunción"),
    ("America/Panama", "Panamá"),
    ("America/Costa_Rica", "Costa Rica"),
    ("America/Guatemala", "Guatemala / El Salvador / Honduras"),
    ("America/Santo_Domingo", "Rep. Dominicana"),
    ("America/New_York", "EE.UU. Este — Nueva York"),
    ("America/Chicago", "EE.UU. Centro — Chicago"),
    ("America/Denver", "EE.UU. Montaña — Denver"),
    ("America/Los_Angeles", "EE.UU. Oeste — Los Ángeles"),
    ("Europe/Madrid", "España — Madrid"),
    ("Europe/London", "Reino Unido — Londres"),
    ("Europe/Paris", "Europa Central — París/Berlín"),
    ("UTC", "UTC"),
]


def _add_timezone_section(parent_layout):
    """Selector de zona horaria (saludo según hora, recordatorios, scheduler). Devuelve el QComboBox."""
    from PyQt6.QtWidgets import QGroupBox, QFormLayout, QComboBox, QLabel
    box = QGroupBox("Zona horaria")
    form = QFormLayout(box)
    cmb = QComboBox()
    current = (_cfg("timezone", "") or "").strip()
    items = list(_COMMON_TZS)
    if current and current not in [tz for tz, _ in items]:
        items.insert(0, (current, current))   # respetar una tz custom guardada
    for tz, label in items:
        cmb.addItem(f"{label}  ({tz})", tz)
    idx = cmb.findData(current or "America/Bogota")
    if idx >= 0:
        cmb.setCurrentIndex(idx)
    form.addRow(QLabel("Tu zona:"), cmb)
    parent_layout.addWidget(box)
    return cmb


def _save_timezone_section(cmb):
    from memory.config_manager import set_setting
    tz = cmb.currentData()
    if tz:
        set_setting("timezone", tz)


def _add_audio_devices_section(parent_layout):
    """Sección de dispositivos de audio (micrófono / altavoz). Devuelve (cmb_mic, cmb_speaker)."""
    from PyQt6.QtWidgets import QGroupBox, QFormLayout, QComboBox, QLabel
    box = QGroupBox("Audio (entrada / salida)")
    form = QFormLayout(box)
    cmb_mic = QComboBox()
    cmb_speaker = QComboBox()
    cmb_mic.addItem("Micrófono por defecto", "")
    cmb_speaker.addItem("Altavoz por defecto", "")
    try:
        import sounddevice as sd
        for i, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                cmb_mic.addItem(dev["name"], i)
            if dev.get("max_output_channels", 0) > 0:
                cmb_speaker.addItem(dev["name"], i)
    except Exception as e:
        form.addRow(QLabel(f"(no pude listar dispositivos: {str(e)[:50]})"))
    mic, spk = _cfg("mic_device", ""), _cfg("speaker_device", "")
    im = cmb_mic.findData(mic)
    if im >= 0:
        cmb_mic.setCurrentIndex(im)
    isp = cmb_speaker.findData(spk)
    if isp >= 0:
        cmb_speaker.setCurrentIndex(isp)
    form.addRow(QLabel("Micrófono:"), cmb_mic)
    form.addRow(QLabel("Altavoz:"), cmb_speaker)
    parent_layout.addWidget(box)
    return (cmb_mic, cmb_speaker)


def _save_audio_devices_section(widgets):
    from memory.config_manager import set_setting
    cmb_mic, cmb_speaker = widgets
    md = cmb_mic.currentData()
    sd_ = cmb_speaker.currentData()
    set_setting("mic_device", md if md is not None else "")
    set_setting("speaker_device", sd_ if sd_ is not None else "")


_SPOTIFY_SCOPE = "user-modify-playback-state user-read-playback-state user-read-currently-playing"


def _google_status() -> str:
    from pathlib import Path
    base = Path(__file__).resolve().parent.parent / "config"
    has_cred = (base / "google_credentials.json").exists()
    has_tok = (base / "google_token.json").exists()
    if has_cred and has_tok:
        return "🟢 Conectado (credencial + autorización OK)"
    if has_cred:
        return "🟡 Credencial cargada — falta autorizar (se abre el navegador al primer uso)"
    return "🔴 Sin configurar"


def _add_google_section(parent_layout):
    """Google usa un ARCHIVO OAuth (google_credentials.json), no un campo de texto:
    botón que lo elige y lo copia a config/ (gitignorado)."""
    from PyQt6.QtWidgets import QGroupBox, QVBoxLayout, QLabel, QPushButton, QFileDialog
    from pathlib import Path
    import shutil

    box = QGroupBox("Google (Calendar / Gmail / Drive)")
    lay = QVBoxLayout(box)
    status = QLabel(_google_status())
    status.setStyleSheet("font-size: 12px;")
    lay.addWidget(status)
    hint = QLabel("Descargá el JSON del cliente OAuth (Desktop) desde Google Cloud Console "
                  "→ APIs → Credentials, y elegilo acá:")
    hint.setWordWrap(True)
    hint.setStyleSheet("font-size: 11px; color: #888;")
    lay.addWidget(hint)
    btn = QPushButton("Elegir google_credentials.json…")

    def pick():
        path, _ = QFileDialog.getOpenFileName(box, "Elegí el JSON de credenciales de Google",
                                              str(Path.home() / "Downloads"), "JSON (*.json)")
        if not path:
            return
        try:
            import json as _json
            data = _json.loads(Path(path).read_text(encoding="utf-8"))
            if "installed" not in data and "web" not in data:
                status.setText("⚠️ Ese JSON no parece un cliente OAuth de Google (falta 'installed').")
                return
            dest = Path(__file__).resolve().parent.parent / "config" / "google_credentials.json"
            shutil.copyfile(path, dest)
            status.setText(_google_status())
        except Exception as e:
            status.setText(f"⚠️ No pude copiarlo: {str(e)[:60]}")

    btn.clicked.connect(pick)
    lay.addWidget(btn)
    parent_layout.addWidget(box)


def _add_spotify_link_section(parent_layout, inputs):
    """Botón para enlazar Spotify (OAuth) + estado, usando los campos del propio diálogo."""
    from PyQt6.QtWidgets import QGroupBox, QHBoxLayout, QVBoxLayout, QPushButton, QLabel
    from PyQt6.QtCore import QTimer
    import threading
    box = QGroupBox("Spotify — enlazar cuenta")
    lay = QVBoxLayout(box)
    info = QLabel("Cargá Client ID/Secret arriba y pulsá 'Enlazar' para autorizar (abre el navegador una vez).")
    info.setWordWrap(True)
    info.setStyleSheet("font-size:11px; color:#888;")
    lay.addWidget(info)
    row = QHBoxLayout()
    btn = QPushButton("🔗 Enlazar Spotify")
    btn.setStyleSheet("background:#1DB954; color:white; font-weight:bold; padding:6px 12px; border-radius:4px;")
    status = QLabel("")
    status.setStyleSheet("font-size:11px;")
    row.addWidget(btn)
    row.addWidget(status)
    row.addStretch()
    lay.addLayout(row)
    parent_layout.addWidget(box)

    def _fields():
        return (inputs["spotify_client_id"].text().strip(),
                inputs["spotify_client_secret"].text().strip(),
                inputs["spotify_redirect_uri"].text().strip() or "http://127.0.0.1:8888/callback")

    def refresh_status():
        cid, sec, uri = _fields()
        if not cid or not sec:
            status.setText("sin configurar")
            return
        try:
            from spotipy.oauth2 import SpotifyOAuth
            tok = SpotifyOAuth(client_id=cid, client_secret=sec, redirect_uri=uri,
                               scope=_SPOTIFY_SCOPE, open_browser=False).get_cached_token()
            status.setText("✅ conectado" if tok else "⚠️ sin autorizar")
        except Exception:
            status.setText("⚠️ sin autorizar")

    def do_link():
        cid, sec, uri = _fields()
        if not cid or not sec:
            status.setText("Cargá Client ID y Secret primero.")
            return
        from memory.config_manager import set_secret
        for k, v in (("spotify_client_id", cid), ("spotify_client_secret", sec), ("spotify_redirect_uri", uri)):
            if v:
                set_secret(k, v)
        status.setText("⏳ abriendo navegador…")
        btn.setEnabled(False)

        def worker():
            try:
                from spotipy.oauth2 import SpotifyOAuth
                SpotifyOAuth(client_id=cid, client_secret=sec, redirect_uri=uri,
                             scope=_SPOTIFY_SCOPE, open_browser=True).get_access_token(as_dict=False)
                QTimer.singleShot(0, lambda: (status.setText("✅ conectado"), btn.setEnabled(True)))
            except Exception as e:
                QTimer.singleShot(0, lambda: (status.setText(f"❌ {str(e)[:40]}"), btn.setEnabled(True)))

        threading.Thread(target=worker, daemon=True).start()

    btn.clicked.connect(do_link)
    refresh_status()
    return (btn, status)


def startup_check() -> None:
    """Al arrancar: si falta Gemini, abrir el diálogo modal exigiéndola."""
    if _cfg("gemini_api_key"):
        return
    open_dialog(highlight="gemini", startup=True)
