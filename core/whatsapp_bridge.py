# -*- coding: utf-8 -*-
"""
whatsapp_bridge.py — Manager del bridge de WhatsApp + UI de conexión (QR en ventana).

Antes el QR salía como ASCII en una Terminal. Ahora:
  • el manager lanza el bridge Go (vendoreado en integrations/) como subproceso
    y lee su stdout: `JARVIS_QR:<código>` → muestra una VENTANA con el QR
    (renderizado con la lib qrcode + QPainter); `JARVIS_WA_CONNECTED` → la cierra.
  • estado consultable para el indicador de la UI: connected | qr | starting | down.
  • si ya hay sesión guardada, conecta directo sin QR (la ventana ni aparece).

El diálogo usa el mismo puente cross-thread que credentials/camera/trading_panel.
"""
from __future__ import annotations

import socket
import subprocess
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BRIDGE_DIR = BASE_DIR / "integrations" / "whatsapp-mcp" / "whatsapp-bridge"
PORT = 8080

_state = {"status": "down", "qr": "", "proc": None}
_lock = threading.Lock()


def port_open(timeout: float = 0.15) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=timeout):
            return True
    except Exception:
        return False


def status() -> str:
    """connected | qr | starting | down (para el indicador de la UI)."""
    if port_open():
        return "connected"
    with _lock:
        return _state["status"] if _state["status"] in ("qr", "starting") else "down"


def is_running() -> bool:
    with _lock:
        p = _state["proc"]
    return p is not None and p.poll() is None


def start(on_qr=None, on_connected=None) -> str:
    """Lanza el bridge (si no está ya andando). Callbacks desde el hilo lector."""
    if port_open():
        with _lock:
            _state["status"] = "connected"
        return "ya estaba conectado"
    if is_running():
        return "ya estaba arrancando"
    if not (BRIDGE_DIR / "main.go").exists():
        return f"no encuentro el bridge en {BRIDGE_DIR}"

    import os
    import sys
    env = os.environ.copy()
    if sys.platform != "win32":
        # Lanzado desde GUI, el PATH no trae homebrew → agregar (os.pathsep, no ':')
        extra = ["/opt/homebrew/bin", "/usr/local/bin"]
        cur = env.get("PATH", "").split(os.pathsep)
        env["PATH"] = os.pathsep.join([d for d in extra if d not in cur] + cur)
    try:
        proc = subprocess.Popen(
            ["go", "run", "main.go"], cwd=str(BRIDGE_DIR), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, stdin=subprocess.DEVNULL,
        )
    except Exception as e:
        return f"no pude lanzar el bridge: {e}"
    with _lock:
        _state.update(proc=proc, status="starting", qr="")

    def reader():
        try:
            for line in proc.stdout:
                line = line.strip()
                if line.startswith("JARVIS_QR:"):
                    code = line[len("JARVIS_QR:"):]
                    with _lock:
                        _state.update(status="qr", qr=code)
                    if on_qr:
                        try:
                            on_qr(code)
                        except Exception:
                            pass
                elif line == "JARVIS_WA_CONNECTED":
                    with _lock:
                        _state.update(status="connected", qr="")
                    if on_connected:
                        try:
                            on_connected()
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            with _lock:
                if _state["status"] != "connected" or not port_open():
                    _state["status"] = "down"

    threading.Thread(target=reader, daemon=True, name="wa-bridge-reader").start()
    return "arrancando"


# ───────────────────── UI: diálogo con el QR (hilo de la UI) ─────────────────────

_BRIDGE_QT = None
_DIALOG = None


def _qr_pixmap(code: str, size: int = 320):
    """Renderiza el QR como QPixmap (qrcode → matriz → QPainter, sin PIL)."""
    import qrcode
    from PyQt6.QtGui import QPixmap, QPainter, QColor
    from PyQt6.QtCore import Qt
    q = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_L)
    q.add_data(code)
    q.make(fit=True)
    matrix = q.get_matrix()
    n = len(matrix)
    cell = max(2, size // n)
    px = QPixmap(n * cell, n * cell)
    px.fill(QColor("#ffffff"))
    p = QPainter(px)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#000000"))
    for y, row in enumerate(matrix):
        for x, v in enumerate(row):
            if v:
                p.drawRect(x * cell, y * cell, cell, cell)
    p.end()
    return px


def _open_dialog():
    from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel
    from PyQt6.QtCore import Qt
    global _DIALOG
    QApplication.instance()
    if _DIALOG is not None:
        return
    dlg = QDialog()
    dlg.setWindowTitle("JARVIS — Conectar WhatsApp")
    dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    dlg.setStyleSheet("QDialog{background:#0b0e14;} QLabel{color:#e6e6e6;}")
    lay = QVBoxLayout(dlg)
    title = QLabel("Escaneá el QR con tu teléfono")
    title.setStyleSheet("font-size:15px; font-weight:bold; color:#25D366;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(title)
    sub = QLabel("WhatsApp → Ajustes → Dispositivos vinculados → Vincular dispositivo")
    sub.setStyleSheet("font-size:11px; color:#9aa4b2;")
    sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(sub)
    qr_label = QLabel("Generando QR…")
    qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    qr_label.setMinimumSize(340, 340)
    lay.addWidget(qr_label)
    dlg._qr_label = qr_label
    _DIALOG = dlg
    dlg.finished.connect(_on_dialog_closed)
    dlg.show()
    dlg.raise_()


def _on_dialog_closed(*_):
    global _DIALOG
    _DIALOG = None


def init_whatsapp_ui():
    """Crear el puente Qt en el hilo de la UI (una vez, tras existir QApplication)."""
    global _BRIDGE_QT
    if _BRIDGE_QT is not None:
        return
    try:
        from PyQt6.QtCore import QObject, pyqtSignal, Qt

        class _WB(QObject):
            qr_sig = pyqtSignal(str)
            ok_sig = pyqtSignal()

            def __init__(self):
                super().__init__()
                self.qr_sig.connect(self._show_qr, Qt.ConnectionType.QueuedConnection)
                self.ok_sig.connect(self._connected, Qt.ConnectionType.QueuedConnection)

            def _show_qr(self, code):
                try:
                    _open_dialog()
                    if _DIALOG is not None:
                        _DIALOG._qr_label.setPixmap(_qr_pixmap(code))
                except Exception as e:
                    print(f"[whatsapp_ui] error mostrando QR: {e}")

            def _connected(self):
                global _DIALOG
                if _DIALOG is not None:
                    try:
                        _DIALOG._qr_label.setText("✅ ¡Conectado!")
                        from PyQt6.QtCore import QTimer
                        QTimer.singleShot(1200, _DIALOG.accept)
                    except Exception:
                        pass

        _BRIDGE_QT = _WB()
    except Exception as e:
        print(f"[whatsapp_ui] no se pudo iniciar el puente: {e}")


def connect_with_ui() -> str:
    """Arranca el bridge; si hace falta QR lo muestra en ventana (no Terminal)."""
    def on_qr(code):
        if _BRIDGE_QT:
            _BRIDGE_QT.qr_sig.emit(code)

    def on_connected():
        if _BRIDGE_QT:
            _BRIDGE_QT.ok_sig.emit()

    return start(on_qr=on_qr, on_connected=on_connected)


def ensure_started_quietly() -> None:
    """Al arrancar JARVIS: levanta el bridge en background. Si hay sesión guardada
    conecta solo (sin QR); si pide QR, la ventana aparece sola."""
    if port_open() or is_running():
        return
    if (BRIDGE_DIR / "store" / "whatsapp.db").exists() or True:
        connect_with_ui()
