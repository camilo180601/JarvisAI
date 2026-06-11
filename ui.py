"""ui.py — 100% Custom Gold-Themed Dynamic Bento PyQt6 User Interface for JARVIS.
Fully optimized HUD layouts:
- Background WebGL reactive Particle Orb covering the screen.
- Floating transparent digital clock at the top-right corner.
- Organized Bento grid dashboard aligned perfectly at the bottom half.
- Centered speech captions at the bottom.
"""
from __future__ import annotations
import sys
import os
import json
import psutil
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGridLayout, QLabel, QPushButton, QLineEdit, QTextEdit, 
    QListWidget, QListWidgetItem, QProgressBar, QDialog, QMessageBox,
    QComboBox, QCheckBox, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import (Qt, QUrl, pyqtSignal, pyqtSlot, QObject, QTimer, QSize, QRectF,
                          QMetaObject, QPropertyAnimation, Q_ARG)
from PyQt6.QtGui import QFont, QColor, QIcon, QMouseEvent, QPainter, QPen, QBrush, QLinearGradient
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from core import theme  # motor de tema (Fase 3)
try:
    import qtawesome as qta
    HAS_QTA = True
except ImportError:
    HAS_QTA = False


from ui_helpers import (_best_dpr, _crisp_pixmap, _crisp_icon, RoundIconButton,
                        make_themed_icon_label, refresh_themed_icons)  # Fase 3
# Active Timezone Peru (UTC-5)
_BA_TZ = timezone(timedelta(hours=-5))
# System configuration safe fallbacks for standalone execution
try:
    from memory.config_manager import load_api_keys, save_api_keys, set_secret, BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).parent
    def load_api_keys() -> dict:
        cfg_file = BASE_DIR / "config.json"
        if cfg_file.exists():
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def save_api_keys(cfg: dict):
        cfg_file = BASE_DIR / "config.json"
        try:
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
        except Exception:
            pass
            
    def set_secret(key: str, val: str):
        cfg = load_api_keys()
        cfg[key] = val
        save_api_keys(cfg)
# Tema (paletas, tokens C_*, theme.apply_theme_tokens) → core/theme.py (Fase 3)
from ui_widgets import (WebBridge, CustomParticleOrb, ClockWidget, WeatherWidget,
                        SoundWaveBars, SpotifyWidget, CircularGauge, SystemWidget,
                        TodoWidget, NotesWidget, FileDropZone, FilesPanel)  # Fase 3


class MainWindow(QMainWindow):
    _shutdown_sig = pyqtSignal()
    _restart_sig = pyqtSignal()
    def __init__(self, ui, face_path):
        super().__init__()
        self.ui = ui
        self.ui._win = self
        
        self.resize(1080, 780)
        self.setMinimumSize(1000, 750)
        
        # Frameless + flotante: que clickear otra app NO entierre el orbe detrás
        # (la ventana no tiene marco ni barra, así que si va atrás "desaparece").
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("centralWidget")
        self.setCentralWidget(self.central_widget)
        
        icon_path = Path(__file__).parent / "assets" / "jarvis_icono.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
            
        self.header_container = QWidget(self.central_widget)
        header_bar = QHBoxLayout(self.header_container)
        header_bar.setContentsMargins(20, 10, 20, 10)
        
        self.lbl_brand = QLabel("J A R V I S")
        font = QFont("Century Gothic", 16, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 8.0)
        self.lbl_brand.setFont(font)
        header_bar.addWidget(self.lbl_brand)
        header_bar.addStretch()

        # Indicador de estado de WhatsApp (verde=conectado, rojo=desconectado)
        self.lbl_wa_status = QLabel("● WhatsApp")
        self.lbl_wa_status.setStyleSheet(
            "color:#666; font-family:'JetBrains Mono'; font-size:10px; background:transparent;")
        header_bar.addWidget(self.lbl_wa_status)
        self._wa_timer = QTimer(self)
        self._wa_timer.timeout.connect(self._refresh_wa_status)
        self._wa_timer.start(8000)
        QTimer.singleShot(3000, self._refresh_wa_status)
        
        self.btn_settings = RoundIconButton()
        self.btn_play = RoundIconButton()
        self.btn_folder = RoundIconButton()
        self.btn_min = RoundIconButton()
        self.btn_close = RoundIconButton()
        
        self.head_buttons = [
            (self.btn_settings, 'fa5s.cog', self._open_settings),
            (self.btn_play, 'fa5s.play', self._toggle_mute),
            (self.btn_folder, 'fa5s.folder', self._open_folder),
            (self.btn_min, 'fa5s.window-minimize', self.showMinimized),
            (self.btn_close, 'fa5s.times', self.close)
        ]
        
        for btn, icon, cb in self.head_buttons:
            btn.setFixedSize(30, 30)
            btn.clicked.connect(cb)
            header_bar.addWidget(btn)
            
        self.orb = CustomParticleOrb(self.ui, self.central_widget)
        self.orb.lower()
        
        # Symmetrical Bento overlay dashboard container at bottom half
        self.bento_container = QWidget(self.central_widget)
        bento_layout = QGridLayout(self.bento_container)
        bento_layout.setContentsMargins(0, 0, 0, 0)
        bento_layout.setSpacing(15)
        
        # Aligned stretches
        bento_layout.setColumnStretch(0, 1)
        bento_layout.setColumnStretch(1, 1)
        bento_layout.setColumnStretch(2, 1)
        bento_layout.setColumnStretch(3, 1)
        
        self.spotify_w = SpotifyWidget()
        self.system_w = SystemWidget()
        self.todo_w = TodoWidget()
        self.notes_w = NotesWidget()
        self.files_panel = FilesPanel(self.ui)
        self.weather_w = WeatherWidget()
        
        # Highly Organized Symmetrical 2-row, 4-column layout at bottom half
        # Row 0
        bento_layout.addWidget(self.spotify_w, 0, 0, 1, 2)
        bento_layout.addWidget(self.weather_w, 0, 2, 1, 1)
        bento_layout.addWidget(self.system_w, 0, 3, 1, 1)
        
        # Row 1
        bento_layout.addWidget(self.todo_w, 1, 0, 1, 1)
        bento_layout.addWidget(self.notes_w, 1, 1, 1, 2)
        bento_layout.addWidget(self.files_panel, 1, 3, 1, 1)
        
        # Clean floating digital Clock Widget at top-right corner
        self.clock_w = ClockWidget(self.central_widget)
        
        # Dedicated Holographic Closed Captions Speech Area (Single centered line)
        self.txt_console = QLabel(self.central_widget)
        self.txt_console.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_console.setWordWrap(True)
        # Fade-in/out de los subtítulos (en vez de aparecer/desaparecer de golpe)
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        self._console_fx = QGraphicsOpacityEffect(self.txt_console)
        self.txt_console.setGraphicsEffect(self._console_fx)
        self._console_fx.setOpacity(1.0)
        self._console_anim = QPropertyAnimation(self._console_fx, b"opacity", self)
        self._console_anim.setDuration(260)
        
        # Force Close flag and System Tray initialization
        self._force_close = False
        self.tray_icon = None
        self._setup_tray_icon()
        
        self.update_theme_styles()
        self._drag_pos = None
        self._shutdown_sig.connect(self._handle_shutdown)
        self._restart_sig.connect(self._handle_restart)
    def _refresh_wa_status(self):
        """Actualiza el chip 'WhatsApp conectado/desconectado' (chequeo de puerto, rápido)."""
        try:
            from core.whatsapp_bridge import status
            st = status()
        except Exception:
            st = "down"
        if st == "connected":
            self.lbl_wa_status.setText("● WhatsApp conectado")
            self.lbl_wa_status.setStyleSheet(
                "color:#25D366; font-family:'JetBrains Mono'; font-size:10px; background:transparent;")
        elif st in ("qr", "starting"):
            self.lbl_wa_status.setText("● WhatsApp conectando…")
            self.lbl_wa_status.setStyleSheet(
                "color:#e0a82e; font-family:'JetBrains Mono'; font-size:10px; background:transparent;")
        else:
            self.lbl_wa_status.setText("● WhatsApp desconectado")
            self.lbl_wa_status.setStyleSheet(
                "color:#ff3b30; font-family:'JetBrains Mono'; font-size:10px; background:transparent;")

    @pyqtSlot(str)
    def show_console_text(self, text: str):
        """Setea el subtítulo con fade-in si estaba vacío (hilo de la UI)."""
        was_empty = not self.txt_console.text()
        self.txt_console.setText(text)
        if was_empty and text:
            self._console_anim.stop()
            self._console_anim.setStartValue(0.0)
            self._console_anim.setEndValue(1.0)
            self._console_anim.start()

    @pyqtSlot()
    def fade_clear_console(self):
        """Borra el subtítulo con fade-out (hilo de la UI)."""
        if not self.txt_console.text():
            return
        self._console_anim.stop()
        self._console_anim.setStartValue(self._console_fx.opacity())
        self._console_anim.setEndValue(0.0)

        def _done():
            self.txt_console.setText("")
            self._console_fx.setOpacity(1.0)
            try:
                self._console_anim.finished.disconnect(_done)
            except Exception:
                pass
        self._console_anim.finished.connect(_done)
        self._console_anim.start()

    @pyqtSlot(str)
    def apply_theme_color(self, color: str):
        """Cambia el color/tema en vivo (llamado por voz vía QMetaObject)."""
        try:
            theme.apply_theme_tokens(color)
            self.update_theme_styles()
        except Exception as e:
            print(f"[theme] error aplicando '{color}': {e}")
    def update_theme_styles(self):
        self.central_widget.setStyleSheet(f"""
            QWidget#centralWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {theme.C_BG}, stop:1 #020202);
                border: 2px solid {theme.C_PRI};
                border-radius: 20px;
            }}
        """)
        self.lbl_brand.setStyleSheet(f"color: {theme.C_PRI}; font-weight: bold; background: transparent;")
        
        for btn, icon, cb in self.head_buttons:
            if HAS_QTA:
                btn.setIcon(_crisp_icon(icon, theme.C_PRI, 15))
                btn.setIconSize(QSize(15, 15))
            btn.update()  # RoundIconButton se pinta solo (borde liso, sin stylesheet)

        self.txt_console.setStyleSheet(f"QLabel {{ color: {theme.C_PRI}; font-family: 'Century Gothic'; font-weight: bold; font-size: 15px; background: transparent; text-shadow: 0 0 10px {theme.C_BORDER}; }}")
        
        self.spotify_w.update_style()
        self.system_w.update_style()
        self.todo_w.update_style()
        self.notes_w.update_style()
        self.files_panel.update_style()
        self.clock_w.update_style()
        self.weather_w.update_style()
        refresh_themed_icons()  # re-colorea los iconos de header al cambiar de tema

        if hasattr(self, "orb"):
            self.orb.sync_theme()
    def resizeEvent(self, event):
        super().resizeEvent(event)
        W = self.central_widget.width()
        H = self.central_widget.height()
        
        self.header_container.setGeometry(0, 0, W, 50)
        
        # Position digital Clock floating at top-right
        self.clock_w.setGeometry(W - 270, 55, 250, 75)
        
        # Position background Particle Orb Web capsule
        self.orb.setGeometry(0, 50, W, H - 50)
        
        # Position centered continuous speech line at bottom of HUD
        self.txt_console.setGeometry(30, H - 65, W - 60, 45)
        
        # Bento overlay container layout math
        bh = H // 3 + 45
        by = H - bh - 65
        self.bento_container.setGeometry(15, by, W - 30, bh)
        
        self.orb.lower()
        self.bento_container.raise_()
        self.txt_console.raise_()
        self.clock_w.raise_()
    def _open_settings(self):
        # Abre el MISMO diálogo unificado de API keys que la voz ("abrí la config de API keys").
        try:
            from core.credentials import open_dialog
            saved = open_dialog()
            if saved and self.ui.on_config_saved:
                self.ui.on_config_saved(load_api_keys())
        except Exception as e:
            print(f"[settings] no pude abrir el diálogo de API keys: {e}")

    def _open_folder(self):
        try:
            os.startfile(BASE_DIR)
        except Exception:
            import subprocess
            if sys.platform == "darwin":
                subprocess.run(["open", str(BASE_DIR)])
            elif sys.platform == "win32":
                subprocess.run(["explorer", str(BASE_DIR)])
    def _toggle_mute(self):
        self.ui.muted = not self.ui.muted
        self.orb.set_state("MUTED" if self.ui.muted else "LISTENING")
        if self.ui.muted:
            if self.ui.on_stop_command:
                self.ui.on_stop_command()
    def _setup_tray_icon(self):
        from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = Path(__file__).parent / "assets" / "jarvis_icono.ico"
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            from PyQt6.QtWidgets import QStyle
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
            
        tray_menu = QMenu(self)
        
        show_action = tray_menu.addAction("Show JARVIS")
        show_action.triggered.connect(self.show_and_activate)
        
        mute_action = tray_menu.addAction("Mute/Unmute")
        mute_action.triggered.connect(self._toggle_mute)
        
        tray_menu.addSeparator()
        
        exit_action = tray_menu.addAction("Exit")
        exit_action.triggered.connect(self._exit_application)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()
    def show_and_activate(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()
    def _exit_application(self):
        self._force_close = True
        self.close()
    def _handle_shutdown(self):
        self._force_close = True
        self.close()
    def _relaunch_process(self):
        """Lanza una instancia NUEVA de JARVIS, desacoplada, que espera a que esta
        termine (libera mic/cámara/audio) antes de arrancar. Cross-platform: SIN
        shell (en Windows no existen `sleep`/`&&`) — un bootstrap de Python duerme
        2s y exec'ea main.py."""
        import subprocess
        try:
            from memory.config_manager import BASE_DIR as _BD
            base = str(_BD)
        except Exception:
            base = os.path.dirname(os.path.abspath(__file__))
        py = sys.executable or "python3"
        boot = ("import time, os, subprocess, sys; time.sleep(2); "
                f"os.chdir({base!r}); subprocess.Popen([{py!r}, 'main.py'])")
        kwargs = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                      stdin=subprocess.DEVNULL)
        if sys.platform == "win32":
            # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP (start_new_session es POSIX)
            kwargs["creationflags"] = 0x00000008 | 0x00000200
        else:
            kwargs["start_new_session"] = True
        try:
            subprocess.Popen([py, "-c", boot], **kwargs)
            return True
        except Exception as e:
            print(f"[restart] no pude lanzar la nueva instancia: {e}")
            return False
    def _handle_restart(self):
        self._relaunch_process()
        self._force_close = True
        self.close()
    def _on_tray_activated(self, reason):
        from PyQt6.QtWidgets import QSystemTrayIcon
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick, QSystemTrayIcon.ActivationReason.Trigger):
            if self.isVisible():
                self.hide()
            else:
                self.show_and_activate()
    def closeEvent(self, event):
        if getattr(self, "_force_close", False):
            event.accept()
        else:
            event.ignore()
            self.hide()
            if hasattr(self, "tray_icon") and self.tray_icon.isVisible():
                from PyQt6.QtWidgets import QSystemTrayIcon
                self.tray_icon.showMessage(
                    "JARVIS AI",
                    "JARVIS is running background services. Double-click tray to restore console.",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000
                )
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
class MockRoot:
    def __init__(self, qapp: QApplication):
        self.qapp = qapp
        
    def mainloop(self):
        sys.exit(self.qapp.exec())
        
    def after(self, ms: int, func):
        QTimer.singleShot(ms, func)
class JarvisUI:
    def __init__(self, face_path=""):
        self.app = QApplication.instance() or QApplication(sys.argv)
        # Que cerrar un diálogo (ej. ventana de API keys) NO apague todo JARVIS:
        # la app solo termina con shutdown_jarvis o cerrando la ventana principal.
        self.app.setQuitOnLastWindowClosed(False)
        self.root = MockRoot(self.app)

        self.muted = False
        self.current_file = ""
        
        self.on_text_command = None
        self.on_stop_command = None
        self.on_config_saved = None
        
        self.jarvis_response_buffer = ""
        
        self._win = MainWindow(self, face_path)
        self._win.show()
        
        QTimer.singleShot(2000, self.ensure_startup_shortcut)
        
    def wait_for_api_key(self):
        pass
    def write_log(self, text: str):
        pass
        
    def set_state(self, state: str):
        self._win.orb.set_state(state)
        if state == "MUTED":
            self.muted = True
        elif state in ("LISTENING", "SPEAKING", "THINKING"):
            if self.muted:
                self.muted = False
                
    def set_audio_level(self, level: float):
        self._win.orb.set_audio(level)
        
    def clear_jarvis_response(self):
        self.jarvis_response_buffer = ""
        # invokeMethod → corre en el hilo de la UI con fade-out (se llama desde el hilo de voz)
        QMetaObject.invokeMethod(self._win, "fade_clear_console", Qt.ConnectionType.QueuedConnection)
        
    def stream_jarvis_chunk(self, chunk: str):
        text = chunk.replace("JARVIS:", "").strip()
        if text:
            if self.jarvis_response_buffer:
                self.jarvis_response_buffer += " " + text
            else:
                self.jarvis_response_buffer = text
            QMetaObject.invokeMethod(self._win, "show_console_text",
                                     Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, self.jarvis_response_buffer))
    def ensure_startup_shortcut(self):
        try:
            import os
            import subprocess
            appdata = os.getenv('APPDATA')
            if not appdata:
                return
            startup_dir = os.path.join(appdata, 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
            shortcut_path = os.path.join(startup_dir, 'JARVIS AI.lnk')
            
            current_dir = os.path.abspath(os.path.dirname(__file__))
            target_vbs = os.path.join(current_dir, "Iniciar JARVIS Beta.vbs")
            icon_path = os.path.join(current_dir, "assets", "jarvis_icono.ico")
            
            if not os.path.exists(shortcut_path) and os.path.exists(target_vbs):
                cmd = (
                    f'$WshShell = New-Object -ComObject WScript.Shell; '
                    f'$Shortcut = $WshShell.CreateShortcut("{shortcut_path}"); '
                    f'$Shortcut.TargetPath = "{target_vbs}"; '
                    f'$Shortcut.WorkingDirectory = "{current_dir}"; '
                    f'$Shortcut.IconLocation = "{icon_path}"; '
                    f'$Shortcut.Save()'
                )
                subprocess.run(["powershell", "-Command", cmd], capture_output=True)
        except Exception:
            pass
if __name__ == "__main__":
    ui = JarvisUI()
    ui.root.mainloop()
