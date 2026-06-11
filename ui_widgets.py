# -*- coding: utf-8 -*-
"""
ui_widgets.py — Widgets del dashboard de JARVIS (Fase 3).

Extraídos de ui.py: orbe, reloj, clima, Spotify, sistema, todos, notas, archivos.
Módulo HERMANO de ui.py (mismo nivel) para que Path(__file__).parent siga siendo la
raíz del repo (assets/sphere.html). Dependen de core.theme + ui_helpers + PyQt.
"""
from __future__ import annotations
import json
import random
import psutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QLineEdit, QTextEdit,
    QListWidget, QListWidgetItem, QProgressBar, QDialog, QMessageBox,
    QComboBox, QCheckBox, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, pyqtSlot, QObject, QTimer, QSize, QRectF
from PyQt6.QtGui import QFont, QColor, QIcon, QMouseEvent, QPainter, QPen, QBrush, QLinearGradient
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

from core import theme
from ui_helpers import (HAS_QTA, _best_dpr, _crisp_pixmap, _crisp_icon, RoundIconButton,
                        make_themed_icon_label, refresh_themed_icons)

# Zona horaria del reloj (UTC-5).
_BA_TZ = timezone(timedelta(hours=-5))


class WebBridge(QObject):
    def __init__(self, orb):
        super().__init__()
        self.orb = orb
    @pyqtSlot()
    def toggle_mute(self):
        if self.orb.ui:
            self.orb.ui._win._toggle_mute()
    @pyqtSlot()
    def request_theme(self):
        QTimer.singleShot(0, self.orb.sync_theme)
class CustomParticleOrb(QWidget):
    audio_signal = pyqtSignal(float)
    state_signal = pyqtSignal(str)
    theme_signal = pyqtSignal()
    def __init__(self, ui, parent=None):
        super().__init__(parent)
        self.ui = ui
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.web_view = QWebEngineView(self)
        self.web_view.setStyleSheet("background: transparent;")
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)
        
        try:
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            settings = self.web_view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
        except Exception:
            pass
            
        self.channel = QWebChannel()
        self.bridge = WebBridge(self)
        self.channel.registerObject("pyBridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        
        sphere_path = Path(__file__).parent / "assets" / "sphere.html"
        self.web_view.setUrl(QUrl.fromLocalFile(str(sphere_path.absolute())))
        
        layout.addWidget(self.web_view)
        self.setLayout(layout)
        
        self.audio_signal.connect(self._safe_set_audio)
        self.state_signal.connect(self._safe_set_state)
        self.theme_signal.connect(self._safe_sync_theme)
        self.web_view.loadFinished.connect(self._on_load_finished)
        
    def _on_load_finished(self, ok):
        if ok:
            self.sync_theme()
            self.set_state("MUTED" if self.ui.muted else "LISTENING")
    def sync_theme(self):
        self.theme_signal.emit()
    def set_audio(self, level: float):
        self.audio_signal.emit(level)
        
    def set_state(self, state: str):
        self.state_signal.emit(state)
    def _safe_sync_theme(self):
        colors = {
            'PRI': theme.C_PRI,
            'PRI_DIM': theme.C_PRI_DIM,
            'TEXT': theme.C_TEXT,
            'BG': theme.C_BG
        }
        js_code = f"if (window.setThemeColors) window.setThemeColors({json.dumps(colors)});"
        self.web_view.page().runJavaScript(js_code)
    def _safe_set_audio(self, level: float):
        js_code = f"if (window.updateVolume) window.updateVolume({level});"
        self.web_view.page().runJavaScript(js_code)
    def _safe_set_state(self, state: str):
        js_code = f"if (window.updateState) window.updateState('{state}');"
        self.web_view.page().runJavaScript(js_code)
class ClockWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ClockWidget")
        self.update_style()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        self.lbl_time = QLabel("12:00:00")
        font_t = QFont("Century Gothic", 24, QFont.Weight.Bold)
        font_t.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        self.lbl_time.setFont(font_t)
        self.lbl_time.setStyleSheet("color: white; border: none; background: transparent;")
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.lbl_time)
        
        self.lbl_date = QLabel("Monday, 24 May 2026")
        self.lbl_date.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.lbl_date)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()
        
    def tick(self):
        now = datetime.now(_BA_TZ)
        self.lbl_time.setText(now.strftime("%I:%M:%S %p"))
        self.lbl_date.setText(now.strftime("%A, %d %B %Y").upper())
        
    def update_style(self):
        self.setStyleSheet("QWidget#ClockWidget { background: transparent; border: none; }")
        if hasattr(self, "lbl_date"):
            self.lbl_date.setStyleSheet(f"font-family: 'JetBrains Mono'; font-size: 10px; letter-spacing: 1px; color: {theme.C_PRI}; border: none; background: transparent; font-weight: bold;")
class WeatherWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WeatherWidget")
        self.update_style()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(4)
        
        header = QHBoxLayout()
        header.addWidget(make_themed_icon_label('fa5s.cloud-sun', "☀️"))
        
        self.lbl_title = QLabel("WEATHER CORE")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        info = QHBoxLayout()
        self.lbl_temp = QLabel("18°C")
        self.lbl_temp.setStyleSheet("font-family: 'Century Gothic'; font-size: 26px; font-weight: bold; border: none; background: transparent; color: white;")
        info.addWidget(self.lbl_temp)
        
        self.lbl_desc = QLabel("Partly Cloudy")
        info.addWidget(self.lbl_desc)
        info.addStretch()
        layout.addLayout(info)
        
        details = QHBoxLayout()
        self.lbl_humidity = QLabel("HUMIDITY: 82%")
        self.lbl_wind = QLabel("WIND: 12 km/h")
        
        details.addWidget(self.lbl_humidity)
        details.addWidget(self.lbl_wind)
        details.addStretch()
        layout.addLayout(details)
        
    def update_style(self):
        self.setStyleSheet(f"""
            QWidget#WeatherWidget {{
                background: {theme.C_PANEL};
                border: 1px solid {theme.C_BORDER};
                border-radius: 16px;
            }}
            QWidget#WeatherWidget:hover {{
                background: rgba(245,158,11,0.06);
                border: 1.2px solid {theme.C_PRI};
            }}
        """)
        if hasattr(self, "lbl_title"):
            self.lbl_title.setStyleSheet(f"font-family: 'JetBrains Mono'; font-weight: bold; font-size: 10px; letter-spacing: 2px; color: {theme.C_PRI}; border: none; background: transparent;")
            self.lbl_desc.setStyleSheet(f"font-size: 11px; color: {theme.C_TEXT}; border: none; background: transparent;")
            self.lbl_humidity.setStyleSheet(f"font-family: 'JetBrains Mono'; font-size: 9px; color: {theme.C_PRI_DIM}; border: none; background: transparent;")
            self.lbl_wind.setStyleSheet(f"font-family: 'JetBrains Mono'; font-size: 9px; color: {theme.C_PRI_DIM}; border: none; background: transparent;")
class SoundWaveBars(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(24)
        self.setMaximumHeight(24)
        self.bars = [4, 6, 8, 12, 10, 6, 4, 8]
        self._active = True

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_heights)
        self.timer.start(100)

    def set_active(self, active: bool):
        self._active = bool(active)
        if not self._active:
            self.bars = [3] * 8
            self.update()

    def update_heights(self):
        # Organic pulsing behavior simulating spectrum heights
        if not self._active:
            return
        self.bars = [random.randint(4, 20) for _ in range(8)]
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        bar_w = 4
        spacing = 3
        total_w = 8 * bar_w + 7 * spacing
        start_x = (w - total_w) / 2
        
        color = QColor(theme.C_PRI)
        for i, bar_h in enumerate(self.bars):
            x = start_x + i * (bar_w + spacing)
            y = h - bar_h
            painter.fillRect(int(x), int(y), bar_w, bar_h, QBrush(color))
class SpotifyWidget(QWidget):
    now_playing_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SpotifyWidget")
        self._is_playing = False
        self.update_style()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(6)
        
        header = QHBoxLayout()
        self.lbl_logo = QLabel()
        if HAS_QTA:
            self.lbl_logo.setPixmap(_crisp_pixmap('fa5b.spotify', '#1DB954'))
        else:
            self.lbl_logo.setText("🎵")
            self.lbl_logo.setStyleSheet("font-size: 14px; border: none;")
        header.addWidget(self.lbl_logo)
        
        self.lbl_title = QLabel("SPOTIFY CORE")
        header.addWidget(self.lbl_title)
        
        # Adding animated soundwaves in header space
        self.waves = SoundWaveBars(self)
        header.addWidget(self.waves)
        header.addStretch()
        layout.addLayout(header)
        
        info_layout = QHBoxLayout()
        
        # Track cover art placeholder
        self.cover_art = QWidget()
        self.cover_art.setFixedSize(50, 50)
        self.cover_art.setObjectName("CoverArt")
        self.cover_art.setStyleSheet(f"""
            QWidget#CoverArt {{
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 rgba(245,158,11,0.25), stop:1 rgba(0,0,0,0.5));
                border: 1px dashed {theme.C_BORDER};
                border-radius: 25px;
            }}
        """)
        info_layout.addWidget(self.cover_art)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self.lbl_track = QLabel("SYSTEM STANDBY")
        self.lbl_track.setStyleSheet("font-family: 'Century Gothic'; font-size: 13px; font-weight: bold; border: none; background: transparent; color: white;")
        self.lbl_track.setWordWrap(False)
        self.lbl_artist = QLabel("Waiting for transmission...")
        self.lbl_device = QLabel("")
        self.lbl_device.setStyleSheet("font-family: 'JetBrains Mono'; font-size: 9px; color: #1DB954; border: none; background: transparent;")
        text_layout.addWidget(self.lbl_track)
        text_layout.addWidget(self.lbl_artist)
        text_layout.addWidget(self.lbl_device)
        info_layout.addLayout(text_layout)
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.btn_shuffle = RoundIconButton()
        self.btn_prev = RoundIconButton()
        self.btn_play = RoundIconButton()
        self.btn_next = RoundIconButton()
        self.btn_heart = RoundIconButton()
        
        self.buttons_list = [
            (self.btn_shuffle, 'fa5s.random', theme.C_PRI_DIM),
            (self.btn_prev, 'fa5s.step-backward', '#ffffff'),
            (self.btn_play, 'fa5s.play', '#ffffff'),
            (self.btn_next, 'fa5s.step-forward', '#ffffff'),
            (self.btn_heart, 'fa5s.heart', theme.RED)
        ]
        
        for btn, icon, clr in self.buttons_list:
            if HAS_QTA:
                btn.setIcon(_crisp_icon(icon, clr, 15))
                btn.setIconSize(QSize(15, 15))
            btn.setFixedSize(28, 28)
            controls.addWidget(btn)
            
        layout.addLayout(controls)
        
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_prev.clicked.connect(lambda: self._api("prev"))
        self.btn_next.clicked.connect(lambda: self._api("next"))

        # Polling de "qué suena" + dispositivo (en background para no trabar la UI).
        self.now_playing_changed.connect(self._apply_now_playing)
        self._np_timer = QTimer(self)
        self._np_timer.timeout.connect(self._poll_now_playing)
        self._np_timer.start(4000)
        QTimer.singleShot(800, self._poll_now_playing)

    def _poll_now_playing(self):
        import threading
        def run():
            try:
                from actions.spotify_control import now_playing_info
                info = now_playing_info()
            except Exception:
                info = None
            self.now_playing_changed.emit(info or {})
        threading.Thread(target=run, daemon=True).start()

    @pyqtSlot(dict)
    def _apply_now_playing(self, info: dict):
        if not info or info.get("auth") is False:
            self.lbl_track.setText("SYSTEM STANDBY")
            self.lbl_artist.setText("Conectá Spotify en ajustes" if info.get("reason") in ("no_creds", "no_token")
                                    else "Waiting for transmission...")
            self.lbl_device.setText("")
            self._set_playing(False)
            return
        if not info.get("playing") and not info.get("track"):
            self.lbl_track.setText("SYSTEM STANDBY")
            dev = info.get("device") or ""
            self.lbl_artist.setText("En pausa" if dev else "Nada reproduciéndose")
            self.lbl_device.setText(f"◆ {dev}" if dev else "")
            self._set_playing(False)
            return
        track = info.get("track", "")
        artist = info.get("artist", "")
        dev = info.get("device", "")
        dtype = info.get("device_type", "")
        self.lbl_track.setText((track[:32] + "…") if len(track) > 33 else track)
        self.lbl_artist.setText(artist)
        icon = {"Computer": "🖥️", "Smartphone": "📱", "Speaker": "🔊",
                "TV": "📺", "CastVideo": "📺"}.get(dtype, "◆")
        self.lbl_device.setText(f"{icon} {dev}" if dev else "")
        self._set_playing(bool(info.get("playing")))

    def _set_playing(self, playing: bool):
        self._is_playing = playing
        if HAS_QTA:
            self.btn_play.setIcon(_crisp_icon('fa5s.pause' if playing else 'fa5s.play', '#ffffff', 15))
        try:
            if hasattr(self, "waves"):
                self.waves.set_active(playing)
        except Exception:
            pass

    def _toggle_play(self):
        self._api("pause" if self._is_playing else "resume")

    def _api(self, action, **kw):
        import threading
        def run():
            try:
                from actions.spotify_control import spotify_control
                spotify_control({"action": action, **kw})
            except Exception:
                pass
            self._poll_now_playing()
        threading.Thread(target=run, daemon=True).start()
    def update_style(self):
        self.setStyleSheet(f"""
            QWidget#SpotifyWidget {{
                background: {theme.C_PANEL};
                border: 1px solid {theme.C_BORDER};
                border-radius: 16px;
            }}
            QWidget#SpotifyWidget:hover {{
                background: rgba(245,158,11,0.06);
                border: 1.2px solid {theme.C_PRI};
            }}
        """)
        if hasattr(self, "lbl_title"):
            self.lbl_title.setStyleSheet(f"font-family: 'JetBrains Mono'; font-weight: bold; font-size: 10px; letter-spacing: 2px; color: {theme.C_PRI}; border: none; background: transparent;")
            self.lbl_artist.setStyleSheet(f"font-family: 'JetBrains Mono'; font-size: 10px; color: {theme.C_PRI_DIM}; border: none; background: transparent;")
            for btn, icon, clr in self.buttons_list:
                btn.update()  # RoundIconButton se pinta solo (borde liso, sin stylesheet)
class CircularGauge(QWidget):
    def __init__(self, title, unit="%", parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.value = 0
        self.setMinimumSize(95, 95)
        
    def setValue(self, val):
        self.value = int(max(0, min(100, val)))
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        size = min(w, h) - 18
        
        # Bounding box of circular ring (leaves space for subtitle at bottom)
        rect = QRectF((w - size)/2, (h - size)/2 - 8, size, size)
        
        # 1. Background arc track
        pen_bg = QPen(QColor(theme.C_PRI_DIM), 6)
        pen_bg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(rect, 0 * 16, 360 * 16)
        
        # 2. Glowing active progress arc
        pen_fg = QPen(QColor(theme.C_PRI), 6)
        pen_fg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_fg)
        
        start_angle = 90 * 16 # top center
        span_angle = -int(self.value * 3.6) * 16 # clockwise progress
        painter.drawArc(rect, start_angle, span_angle)
        
        # 3. Text label inside core
        font_val = QFont("Century Gothic", 12, QFont.Weight.Bold)
        painter.setFont(font_val)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.value}{self.unit}")
        
        # 4. Text title underneath
        font_lbl = QFont("JetBrains Mono", 8, QFont.Weight.Bold)
        painter.setFont(font_lbl)
        painter.setPen(QColor(theme.C_TEXT))
        lbl_rect = QRectF(0, h - 16, w, 16)
        painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter, self.title.upper())
class SystemWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SystemWidget")
        self.update_style()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(4)
        
        header = QHBoxLayout()
        header.addWidget(make_themed_icon_label('fa5s.bolt', "⚡"))
        
        self.lbl_title = QLabel("SYSTEM GAUGES")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        gauges_layout = QHBoxLayout()
        self.cpu_gauge = CircularGauge("CPU")
        self.ram_gauge = CircularGauge("RAM")
        
        gauges_layout.addWidget(self.cpu_gauge)
        gauges_layout.addWidget(self.ram_gauge)
        layout.addLayout(gauges_layout)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(1000)
        self.update_stats()
        
    def update_stats(self):
        try:
            self.cpu_gauge.setValue(psutil.cpu_percent())
            self.ram_gauge.setValue(psutil.virtual_memory().percent)
        except Exception:
            pass
    def update_style(self):
        self.setStyleSheet(f"""
            QWidget#SystemWidget {{
                background: {theme.C_PANEL};
                border: 1px solid {theme.C_BORDER};
                border-radius: 16px;
            }}
            QWidget#SystemWidget:hover {{
                background: rgba(245,158,11,0.06);
                border: 1.2px solid {theme.C_PRI};
            }}
        """)
        if hasattr(self, "lbl_title"):
            self.lbl_title.setStyleSheet(f"font-family: 'JetBrains Mono'; font-weight: bold; font-size: 10px; letter-spacing: 2px; color: {theme.C_PRI}; border: none; background: transparent;")
class TodoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TodoWidget")
        self.update_style()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(6)
        
        header = QHBoxLayout()
        header.addWidget(make_themed_icon_label('fa5s.check-circle', "✅"))
        
        self.lbl_title = QLabel("TODOS")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        inp_layout = QHBoxLayout()
        self.txt_task = QLineEdit()
        self.txt_task.setPlaceholderText("Assign task...")
        inp_layout.addWidget(self.txt_task)
        
        self.btn_add = QPushButton("+")
        inp_layout.addWidget(self.btn_add)
        layout.addLayout(inp_layout)
        
        self.lst_todo = QListWidget()
        layout.addWidget(self.lst_todo)
        
        self.btn_add.clicked.connect(self.add_task)
        self.txt_task.returnPressed.connect(self.add_task)
        
    def add_task(self):
        text = self.txt_task.text().strip()
        if text:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.lst_todo.addItem(item)
            self.txt_task.clear()
    def update_style(self):
        self.setStyleSheet(f"""
            QWidget#TodoWidget {{
                background: {theme.C_PANEL};
                border: 1px solid {theme.C_BORDER};
                border-radius: 16px;
            }}
            QWidget#TodoWidget:hover {{
                background: rgba(245,158,11,0.06);
                border: 1.2px solid {theme.C_PRI};
            }}
            QLineEdit {{
                background: rgba(0,0,0,0.3);
                border: 1px solid {theme.C_BORDER};
                border-radius: 8px;
                padding: 6px;
                color: white;
            }}
            QLineEdit:focus {{
                border-color: {theme.C_PRI};
            }}
            QPushButton {{
                background: {theme.C_PRI};
                color: black;
                font-weight: bold;
                border-radius: 8px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background: #ffffff;
            }}
            QListWidget {{
                border: none;
                background: transparent;
            }}
            QListWidget::item {{
                padding: 5px;
                color: white;
                border-bottom: 1px solid rgba(245,158,11,0.08);
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme.C_PRI_DIM};
                min-height: 20px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {theme.C_PRI};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
            }}
        """)
        if hasattr(self, "lbl_title"):
            self.lbl_title.setStyleSheet(f"font-family: 'JetBrains Mono'; font-weight: bold; font-size: 10px; letter-spacing: 2px; color: {theme.C_PRI}; border: none; background: transparent;")
class NotesWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NotesWidget")
        self.update_style()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(6)
        
        header = QHBoxLayout()
        header.addWidget(make_themed_icon_label('fa5s.sticky-note', "📝"))
        
        self.lbl_title = QLabel("PAD NOTES")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("Write neural records here...")
        layout.addWidget(self.txt_notes)
    def update_style(self):
        self.setStyleSheet(f"""
            QWidget#NotesWidget {{
                background: {theme.C_PANEL};
                border: 1px solid {theme.C_BORDER};
                border-radius: 16px;
            }}
            QWidget#NotesWidget:hover {{
                background: rgba(245,158,11,0.06);
                border: 1.2px solid {theme.C_PRI};
            }}
            QTextEdit {{
                border: none;
                background: rgba(0,0,0,0.2);
                border-radius: 8px;
                padding: 8px;
                color: white;
                line-height: 1.4;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme.C_PRI_DIM};
                min-height: 20px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {theme.C_PRI};
            }}
        """)
        if hasattr(self, "lbl_title"):
            self.lbl_title.setStyleSheet(f"font-family: 'JetBrains Mono'; font-weight: bold; font-size: 10px; letter-spacing: 2px; color: {theme.C_PRI}; border: none; background: transparent;")
class FileDropZone(QWidget):
    fileDropped = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.update_style()
        layout = QVBoxLayout(self)
        self.lbl = QLabel("Drop File Trigger")
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl.setStyleSheet("border: none; background: transparent; font-weight: bold; color: white; font-size: 11px;")
        layout.addWidget(self.lbl)
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(f"QWidget {{ background: rgba(245,158,11,0.12); border: 2px dashed {theme.C_PRI}; border-radius: 12px; }}")
    def dragLeaveEvent(self, event):
        self.update_style()
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.exists(path):
                self.fileDropped.emit(path)
                break
        self.dragLeaveEvent(None)
    def update_style(self):
        self.setStyleSheet(f"""
            QWidget {{
                background: rgba(0,0,0,0.2);
                border: 1px dashed {theme.C_BORDER};
                border-radius: 12px;
            }}
        """)
class FilesPanel(QWidget):
    def __init__(self, ui, parent=None):
        super().__init__(parent)
        self.ui = ui
        self.setObjectName("FilesPanel")
        self.update_style()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(6)
        
        header = QHBoxLayout()
        header.addWidget(make_themed_icon_label('fa5s.folder-open', "📁"))
        
        self.lbl_title = QLabel("FILES DROP")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        self.drop_zone = FileDropZone()
        self.drop_zone.fileDropped.connect(self.on_file_dropped)
        layout.addWidget(self.drop_zone)
        
        self.lbl_current = QLabel("System idle: await drop.")
        layout.addWidget(self.lbl_current)
        
    def on_file_dropped(self, path):
        self.ui.current_file = path
        name = os.path.basename(path)
        self.lbl_current.setText(f"ACTIVE: {name.upper()}")
        self.ui.write_log(f"📁 Drops linked: {name}")
    def update_style(self):
        self.setStyleSheet(f"""
            QWidget#FilesPanel {{
                background: {theme.C_PANEL};
                border: 1px solid {theme.C_BORDER};
                border-radius: 16px;
            }}
            QWidget#FilesPanel:hover {{
                background: rgba(245,158,11,0.06);
                border: 1.2px solid {theme.C_PRI};
            }}
        """)
        if hasattr(self, "lbl_title"):
            self.lbl_title.setStyleSheet(f"font-family: 'JetBrains Mono'; font-weight: bold; font-size: 10px; letter-spacing: 2px; color: {theme.C_PRI}; border: none; background: transparent;")
            self.lbl_current.setStyleSheet(f"font-family: 'JetBrains Mono'; font-size: 9px; color: {theme.C_PRI_DIM}; border: none; background: transparent; text-align: center;")
            self.drop_zone.update_style()
