# -*- coding: utf-8 -*-
"""
ui_helpers.py — Helpers e widgets-base reutilizables de la UI (Fase 3).

Extraído de ui.py: render nítido de iconos en Retina y el botón circular pintado a
mano. Capa hoja: depende solo de core.theme + PyQt + qtawesome. Módulo HERMANO de
ui.py (mismo nivel) para que rutas con __file__ sigan apuntando a la raíz del repo.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QPushButton
from PyQt6.QtCore import Qt, QSize, QRectF
from PyQt6.QtGui import QIcon, QPainter, QColor, QPen

from core import theme

try:
    import qtawesome as qta
    HAS_QTA = True
except ImportError:
    HAS_QTA = False


def _best_dpr() -> float:
    """DPR de render más alto entre las pantallas (robusto si se llama antes de show())."""
    app = QApplication.instance()
    if not app:
        return 2.0
    try:
        ratios = [s.devicePixelRatio() for s in app.screens()]
        return max(ratios) if ratios else float(app.devicePixelRatio())
    except Exception:
        try:
            return float(app.devicePixelRatio())
        except Exception:
            return 2.0


def _crisp_pixmap(name, color, size=16):
    """Pixmap de icono nítido en Retina/HiDPI: renderiza a resolución física
    (x devicePixelRatio) y la marca, así el QLabel lo muestra sin pixelar."""
    dpr = max(1.0, _best_dpr())
    pm = qta.icon(name, color=color).pixmap(QSize(round(size * dpr), round(size * dpr)))
    pm.setDevicePixelRatio(dpr)
    return pm


def _crisp_icon(name, color, size=16):
    """QIcon nítido en Retina para botones (envuelve un pixmap HiDPI)."""
    return QIcon(_crisp_pixmap(name, color, size))


# ── Iconos que siguen el color del tema (se regeneran al cambiarlo en vivo) ──
_THEMED_ICONS: list = []   # (QLabel, icon_name, size)


def make_themed_icon_label(name, emoji="●", size=16):
    """QLabel con un icono que sigue el color del tema. Se re-colorea en vivo
    al cambiar de tema (vía refresh_themed_icons)."""
    from PyQt6.QtWidgets import QLabel
    lbl = QLabel()
    if HAS_QTA:
        lbl.setPixmap(_crisp_pixmap(name, theme.C_PRI, size))
        _THEMED_ICONS.append((lbl, name, size))
    else:
        lbl.setText(emoji)
        lbl.setStyleSheet(f"color: {theme.C_PRI}; font-size: 14px; border: none;")
    return lbl


def refresh_themed_icons():
    """Regenera todos los iconos temáticos con el color de tema vigente."""
    if not HAS_QTA:
        return
    for lbl, name, size in list(_THEMED_ICONS):
        try:
            lbl.setPixmap(_crisp_pixmap(name, theme.C_PRI, size))
        except RuntimeError:
            pass  # el widget fue destruido


class RoundIconButton(QPushButton):
    """Botón circular pintado a mano con ANTIALIASING — el borde es una curva lisa,
    no el trazo punteado/escalonado que produce 'border-radius' del stylesheet en
    ventanas translúcidas con render por software."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        self._border_w = 1.4

    def enterEvent(self, e):
        self._hover = True; self.update(); super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False; self.update(); super().leaveEvent(e)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        m = self._border_w + 0.5
        rect = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        bg = QColor(theme.C_PRI); bg.setAlphaF(0.18 if self._hover else 0.06)
        p.setBrush(bg)
        bc = QColor(theme.C_PRI)
        if not self._hover:
            bc.setAlphaF(0.45)
        pen = QPen(bc); pen.setWidthF(self._border_w)
        p.setPen(pen)
        p.drawEllipse(rect)
        ic = self.icon()
        if not ic.isNull():
            sz = self.iconSize()
            pm = ic.pixmap(sz)
            x = (self.width() - sz.width()) / 2
            y = (self.height() - sz.height()) / 2
            p.drawPixmap(int(x), int(y), pm)
        p.end()
