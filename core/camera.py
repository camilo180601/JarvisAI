"""
camera.py — Acceso a la webcam BAJO DEMANDA + preview en la interfaz.

Privacidad: la cámara solo se abre cuando una acción lo pide (no corre en 2º plano).
El preview flotante visible es la señal clara de que JARVIS está mirando.

  CAMERA           manager de captura (start/stop/get_frame).
  init_camera_ui() crea el puente (en el hilo de la UI, una vez).
  request_show()/request_hide()  muestran/ocultan el preview desde cualquier hilo.
"""
from __future__ import annotations
import threading
import time

try:
    import cv2
except Exception:
    cv2 = None


class CameraManager:
    def __init__(self):
        self._cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._run = False
        self._thread = None
        self.index = 0

    def _open_validated(self, index: int, warm: float = 1.2):
        """Abre un índice y mide el brillo de los primeros cuadros. Algunas 'cámaras'
        (Continuidad del iPhone, virtuales) abren pero entregan SOLO negro. Devuelve
        (cap|None, brillo_max)."""
        cap = cv2.VideoCapture(index)
        if not cap or not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            return None, 0.0
        maxb, t0 = 0.0, time.time()
        while time.time() - t0 < warm:
            ok, fr = cap.read()
            if ok and fr is not None:
                try:
                    b = float(fr.mean())
                except Exception:
                    b = 0.0
                if b > maxb:
                    maxb = b
                if maxb > 12:   # ya hay luz suficiente
                    break
            time.sleep(0.05)
        return cap, maxb

    def start(self, index: int = 0) -> bool:
        if cv2 is None:
            return False
        if self._run:
            return True
        # Probar el índice pedido primero; si da NEGRO, autodetectar uno con luz.
        order = [index] + [i for i in (0, 1, 2) if i != index]
        chosen = None        # (cap, idx) con imagen real
        fallback = None      # (cap, idx) que al menos abre, por si ninguno tiene luz
        for i in order:
            cap, brightness = self._open_validated(i)
            if cap is None:
                continue
            if brightness > 10:
                chosen = (cap, i)
                break
            if fallback is None:
                fallback = (cap, i)
            else:
                cap.release()
        if chosen is None:
            chosen = fallback
        if chosen is None:
            return False
        if fallback and chosen is not fallback:
            fallback[0].release()
        self._cap, self.index = chosen
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[camera] usando índice {self.index}")
        return True

    def _loop(self):
        while self._run and self._cap is not None:
            ok, fr = self._cap.read()
            if ok:
                with self._lock:
                    self._frame = fr
            time.sleep(0.03)

    def get_frame(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def is_on(self) -> bool:
        return self._run

    def stop(self):
        self._run = False
        t = self._thread
        if t:
            t.join(timeout=1.0)
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        with self._lock:
            self._frame = None


CAMERA = CameraManager()


# ───────────────────────── preview flotante (PyQt6) ─────────────────────────

_bridge = None
_preview = None


def _make_preview():
    from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QImage, QPixmap

    class CameraPreview(QWidget):
        def __init__(self):
            super().__init__(None, Qt.WindowType.FramelessWindowHint |
                             Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            self.lbl = QLabel("📷")
            self.lbl.setFixedSize(320, 240)
            self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl.setStyleSheet(
                "border: 2px solid #e0a82e; border-radius: 12px; background: #000; color:#e0a82e;")
            lay.addWidget(self.lbl)
            self.resize(324, 244)
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._tick)

        def _tick(self):
            fr = CAMERA.get_frame()
            if fr is None or cv2 is None:
                return
            rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            self.lbl.setPixmap(QPixmap.fromImage(img).scaled(
                self.lbl.width(), self.lbl.height(),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        def show_cam(self):
            try:
                from PyQt6.QtGui import QGuiApplication
                geo = QGuiApplication.primaryScreen().availableGeometry()
                self.move(geo.right() - self.width() - 30, geo.top() + 60)
            except Exception:
                pass
            self.show()
            self.raise_()
            self.timer.start(33)

        def hide_cam(self):
            self.timer.stop()
            self.hide()

    return CameraPreview()


def init_camera_ui():
    """Crear el puente en el hilo de la UI (después de que exista la QApplication)."""
    global _bridge
    if _bridge is not None:
        return
    try:
        from PyQt6.QtCore import QObject, pyqtSignal, Qt

        class _CamBridge(QObject):
            show_sig = pyqtSignal()
            hide_sig = pyqtSignal()

            def __init__(self):
                super().__init__()
                self.show_sig.connect(self._show, Qt.ConnectionType.QueuedConnection)
                self.hide_sig.connect(self._hide, Qt.ConnectionType.QueuedConnection)

            def _show(self):
                global _preview
                if _preview is None:
                    _preview = _make_preview()
                _preview.show_cam()

            def _hide(self):
                if _preview is not None:
                    _preview.hide_cam()

        _bridge = _CamBridge()
    except Exception as e:
        print(f"[camera] no se pudo iniciar el puente: {e}")


def request_show() -> bool:
    if _bridge is None:
        return False
    _bridge.show_sig.emit()
    return True


def request_hide() -> bool:
    if _bridge is None:
        return False
    _bridge.hide_sig.emit()
    return True
