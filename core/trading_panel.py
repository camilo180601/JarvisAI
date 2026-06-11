# -*- coding: utf-8 -*-
"""
trading_panel.py — Ventana gráfica del bot de trading (paper) de JARVIS.

Se abre SOLO cuando se lo pide a JARVIS ('abrí el panel de trading'). Muestra:
resumen (valor, rendimiento, efectivo), posiciones, curva de equity y TODOS los
movimientos por fecha (compras/ventas/análisis). Lee el portafolio paper de
actions.trading_bot. Dinero FICTICIO — no hay ganancias garantizadas.

Patrón cross-thread idéntico a core/credentials.py: la tool (otro hilo) pide abrir
vía una señal Qt con QueuedConnection, y la ventana se construye en el hilo de la UI.
"""
from __future__ import annotations

# ───────────────────────── puente entre hilos ─────────────────────────

_BRIDGE = None


def init_panel_bridge():
    """Crear en el hilo de la UI (después de que exista la QApplication)."""
    global _BRIDGE
    if _BRIDGE is not None:
        return
    try:
        from PyQt6.QtCore import QObject, pyqtSignal, Qt

        class _Bridge(QObject):
            req = pyqtSignal()

            def __init__(self):
                super().__init__()
                self.req.connect(self._open, Qt.ConnectionType.QueuedConnection)

            def _open(self):
                try:
                    open_panel()
                except Exception as e:
                    print(f"[trading_panel] error abriendo panel: {e}")

        _BRIDGE = _Bridge()
    except Exception as e:
        print(f"[trading_panel] no se pudo iniciar el puente: {e}")


def request_panel() -> bool:
    """Pedir abrir el panel desde cualquier hilo. False si no hay GUI."""
    if _BRIDGE is None:
        # Sin bridge (p.ej. corriendo headless): intento abrir directo si hay QApplication.
        try:
            from PyQt6.QtWidgets import QApplication
            if QApplication.instance() is None:
                return False
            open_panel()
            return True
        except Exception:
            return False
    _BRIDGE.req.emit()
    return True


# ───────────────────────── curva de equity (sin dependencias) ─────────────────────────

def _make_equity_widget():
    from PyQt6.QtWidgets import QWidget
    from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath
    from PyQt6.QtCore import Qt

    class EquityCurve(QWidget):
        def __init__(self):
            super().__init__()
            self.points: list[float] = []
            self.baseline: float | None = None
            self.setMinimumHeight(140)

        def set_data(self, points, baseline=None):
            self.points = [float(p) for p in points if p is not None]
            self.baseline = baseline
            self.update()

        def paintEvent(self, _evt):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()
            p.fillRect(0, 0, w, h, QColor("#10131a"))
            pts = self.points
            if len(pts) < 2:
                p.setPen(QColor("#6b7280"))
                p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                           "Sin datos suficientes todavía\n(se llena al operar / consultar)")
                p.end()
                return
            lo, hi = min(pts), max(pts)
            if self.baseline is not None:
                lo, hi = min(lo, self.baseline), max(hi, self.baseline)
            rng = (hi - lo) or 1.0
            pad = 10
            iw, ih = w - 2 * pad, h - 2 * pad

            def xy(i, v):
                x = pad + (iw * i / (len(pts) - 1))
                y = pad + ih - (ih * (v - lo) / rng)
                return x, y

            # línea base (capital inicial)
            if self.baseline is not None:
                _, by = xy(0, self.baseline)
                pen = QPen(QColor("#3a3f4b")); pen.setStyle(Qt.PenStyle.DashLine); pen.setWidth(1)
                p.setPen(pen)
                p.drawLine(pad, int(by), w - pad, int(by))

            up = pts[-1] >= pts[0]
            color = QColor("#22c55e") if up else QColor("#ef4444")
            path = QPainterPath()
            x0, y0 = xy(0, pts[0]); path.moveTo(x0, y0)
            for i, v in enumerate(pts[1:], start=1):
                x, y = xy(i, v); path.lineTo(x, y)
            pen = QPen(color); pen.setWidth(2)
            p.setPen(pen)
            p.drawPath(path)
            # relleno tenue
            fill = QPainterPath(path)
            fill.lineTo(w - pad, h - pad); fill.lineTo(pad, h - pad); fill.closeSubpath()
            c = QColor(color); c.setAlpha(30)
            p.fillPath(fill, c)
            p.end()

    return EquityCurve()


# ───────────────────────── ventana ─────────────────────────

_PANEL = None  # referencia global para que no la recoja el GC
_GOLD = "#e0a82e"


def _fmt_money(x):
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return str(x)


def open_panel() -> bool:
    from PyQt6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QAbstractItemView)
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor

    QApplication.instance() or QApplication([])
    global _PANEL
    if _PANEL is not None:
        try:
            _refresh(_PANEL)
            _PANEL.show(); _PANEL.raise_(); _PANEL.activateWindow()
            return True
        except Exception:
            _PANEL = None

    dlg = QDialog()
    dlg.setWindowTitle("JARVIS — Bot de Trading (paper)")
    dlg.resize(760, 720)
    dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    dlg.setStyleSheet(
        "QDialog{background:#0b0e14;} QLabel{color:#e6e6e6;} "
        "QTableWidget{background:#10131a;color:#e6e6e6;gridline-color:#222733;"
        "border:1px solid #222733;border-radius:6px;} "
        "QHeaderView::section{background:#161a23;color:#9aa4b2;border:0;padding:6px;font-weight:bold;} "
        f"QPushButton{{background:#161a23;color:{_GOLD};border:1px solid #2a2f3a;"
        "border-radius:6px;padding:7px 12px;font-weight:bold;} "
        "QPushButton:hover{background:#1d222d;}")
    root = QVBoxLayout(dlg)

    title = QLabel("📈 Bot de Trading — modo PAPER (dinero ficticio · precios reales)")
    title.setStyleSheet(f"font-size:16px;font-weight:bold;color:{_GOLD};")
    root.addWidget(title)
    disc = QLabel("Simulación sin riesgo. NINGÚN bot garantiza ganancias.")
    disc.setStyleSheet("color:#8b93a1;font-size:11px;")
    root.addWidget(disc)

    summary = QLabel("…")
    summary.setStyleSheet("font-size:13px;padding:8px;background:#10131a;border-radius:6px;")
    summary.setWordWrap(True)
    root.addWidget(summary)

    equity = _make_equity_widget()
    root.addWidget(equity)

    root.addWidget(_section_label("Posiciones"))
    pos_tbl = QTableWidget(0, 6)
    pos_tbl.setHorizontalHeaderLabels(["Ticker", "Acciones", "Precio", "Valor", "Costo", "P&L %"])
    _setup_table(pos_tbl)
    root.addWidget(pos_tbl)

    root.addWidget(_section_label("Movimientos (por fecha, más recientes arriba)"))
    mov_tbl = QTableWidget(0, 6)
    mov_tbl.setHorizontalHeaderLabels(["Fecha", "Tipo", "Ticker", "Monto", "Precio", "Motivo"])
    _setup_table(mov_tbl)
    root.addWidget(mov_tbl, stretch=1)

    btns = QHBoxLayout()
    b_refresh = QPushButton("↻ Actualizar")
    b_invest = QPushButton("Invertir ahora")
    b_signal = QPushButton("Analizar mercado")
    b_tick = QPushButton("Correr análisis auto")
    b_close = QPushButton("Cerrar")
    for b in (b_refresh, b_invest, b_signal, b_tick):
        btns.addWidget(b)
    btns.addStretch(1)
    btns.addWidget(b_close)
    root.addLayout(btns)

    note = QLabel("")
    note.setStyleSheet("color:#9aa4b2;font-size:12px;")
    root.addWidget(note)

    # refs para refrescar
    dlg._w = {"summary": summary, "equity": equity, "pos": pos_tbl, "mov": mov_tbl, "note": note}

    def _do(action, **extra):
        try:
            from actions.trading_bot import trading_bot
            note.setText(trading_bot({"action": action, **extra}))
        except Exception as e:
            note.setText(f"Error: {e}")
        _refresh(dlg)

    b_refresh.clicked.connect(lambda: _refresh(dlg))
    b_invest.clicked.connect(lambda: _do("invest"))
    b_signal.clicked.connect(lambda: _do("analyze"))
    b_tick.clicked.connect(lambda: _do("tick"))
    b_close.clicked.connect(dlg.hide)

    timer = QTimer(dlg)
    timer.timeout.connect(lambda: _refresh(dlg))
    timer.start(30000)
    dlg._timer = timer

    _refresh(dlg)
    _PANEL = dlg
    dlg.show(); dlg.raise_(); dlg.activateWindow()
    return True


def _section_label(text):
    from PyQt6.QtWidgets import QLabel
    lab = QLabel(text)
    lab.setStyleSheet("color:#9aa4b2;font-weight:bold;margin-top:6px;")
    return lab


def _setup_table(tbl):
    from PyQt6.QtWidgets import QHeaderView, QAbstractItemView
    tbl.verticalHeader().setVisible(False)
    tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    tbl.setAlternatingRowColors(False)


def _refresh(dlg):
    from PyQt6.QtWidgets import QTableWidgetItem
    from PyQt6.QtGui import QColor
    from PyQt6.QtCore import Qt
    try:
        from actions.trading_bot import _load, _valuate
    except Exception as e:
        dlg._w["summary"].setText(f"No pude leer el portafolio: {e}")
        return
    port = _load()
    w = dlg._w
    if port is None:
        w["summary"].setText("Todavía no hay portafolio. Pedile a JARVIS: 'creá un bot de trading'.")
        w["pos"].setRowCount(0); w["mov"].setRowCount(0)
        w["equity"].set_data([], None)
        return

    v = _valuate(port)
    emoji = "🟢" if v["total_pnl"] >= 0 else "🔴"
    estr = port.get("strategy", "dca").upper()
    auto = "ON" if port.get("auto") else "OFF"
    w["summary"].setText(
        f"{emoji}  Valor total: <b>{_fmt_money(v['total'])}</b>   ·   "
        f"Rendimiento: <b>{v['total_pnl_pct']:+.2f}%</b> ({_fmt_money(v['total_pnl'])})<br>"
        f"Efectivo: {_fmt_money(v['cash'])}   ·   Invertido: {_fmt_money(v['invested_total'])}   ·   "
        f"Estrategia: <b>{estr}</b>   ·   Automático: <b>{auto}</b>   ·   "
        f"Cada operación: {_fmt_money(port.get('dca_amount', 0))} "
        f"({'semanal' if port.get('frequency')=='weekly' else 'diario'} en {port.get('ticker')})")

    # equity
    eq = port.get("equity", [])
    w["equity"].set_data([p[1] for p in eq], port.get("start_cash"))

    # posiciones
    rows = v["rows"]
    pt = w["pos"]; pt.setRowCount(len(rows))
    for i, r in enumerate(rows):
        vals = [r["ticker"], f"{r['shares']:.4f}",
                _fmt_money(r["price"]) if r["price"] else "—",
                _fmt_money(r["market"]), _fmt_money(r["cost"]),
                f"{r['pnl_pct']:+.2f}%"]
        for j, val in enumerate(vals):
            it = QTableWidgetItem(val)
            if j == 5:
                it.setForeground(QColor("#22c55e") if r["pnl"] >= 0 else QColor("#ef4444"))
            if j >= 1:
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            pt.setItem(i, j, it)

    # movimientos (recientes arriba)
    hist = list(reversed(port.get("history", [])))[:200]
    mt = w["mov"]; mt.setRowCount(len(hist))
    tipo_map = {"buy": ("Compra", "#22c55e"), "sell": ("Venta", "#ef4444"),
                "hold": ("Análisis", "#9aa4b2")}
    for i, h in enumerate(hist):
        ts = (h.get("ts", "")[:16]).replace("T", " ")
        tipo, color = tipo_map.get(h.get("action", ""), (h.get("action", ""), "#e6e6e6"))
        motivo = h.get("reason", "") or ""
        if "realized" in h:
            motivo = (motivo + f"  (realizado {_fmt_money(h['realized'])})").strip()
        amount = _fmt_money(h.get("amount", 0)) if h.get("amount") else "—"
        price = _fmt_money(h.get("price", 0)) if h.get("price") else "—"
        vals = [ts, tipo, h.get("ticker", ""), amount, price, motivo]
        for j, val in enumerate(vals):
            it = QTableWidgetItem(val)
            if j == 1:
                it.setForeground(QColor(color))
            if j in (3, 4):
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            mt.setItem(i, j, it)
