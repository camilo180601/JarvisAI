# -*- coding: utf-8 -*-
"""
trading_bot.py — Bot de inversión DCA en modo PAPER (simulación) para JARVIS.

⚠️ NO garantiza ganancias. NINGÚN bot puede. Esto opera con dinero FICTICIO sobre
precios REALES de mercado (Yahoo Finance). Sirve para practicar y validar una
estrategia sin arriesgar un peso. Para pasar a dinero real haría falta conectar un
broker real (ej. Alpaca) — eso es un paso aparte y siempre con riesgo de pérdida.

Estrategia: DCA (Dollar Cost Averaging) = invertir un monto fijo cada cierto tiempo,
sin intentar adivinar el mercado. Por defecto sobre SPY (ETF del S&P 500); podés
sumar empresas individuales (AAPL, MSFT, etc.).

JARVIS lo gestiona entero: setup, comprar periódico (manual o automático vía
scheduler), ver estado/ganancia, vender, historial, reset.

Estado en config/trading/paper_portfolio.json. Acá NO hay dinero real.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent
PORT_PATH = BASE_DIR / "config" / "trading" / "paper_portfolio.json"
_AUTO_NAME = "JARVIS DCA auto"

_DEFAULTS = {
    "mode": "paper",          # paper (simulador local) | real (broker Alpaca)
    "live": False,            # solo importa si mode=real: False=Alpaca Paper, True=Alpaca Live (dinero REAL)
    "cash": 10000.0,
    "start_cash": 10000.0,
    "real_start_equity": None,  # equity al conectar el broker, para medir rendimiento desde ahí
    "ticker": "SPY",
    "dca_amount": 100.0,
    "frequency": "weekly",   # daily | weekly
    "strategy": "dca",        # dca (ciego) | smart (analiza el mercado: SMA + RSI)
    "auto": False,
    "watchlist": [],          # tickers extra que el modo smart vigila además de `ticker`
    "stop_loss_pct": 8.0,     # vende TODO una posición si cae este % bajo el costo promedio
    "positions": {},          # {"SPY": {"shares": 1.23, "cost": 567.8}}  cost = $ invertidos
    "history": [],
    "equity": [],             # [[iso_ts, valor_total]] para la curva del panel
}

# Caché de precios en memoria para no martillar Yahoo dentro de una misma corrida.
_price_cache: dict[str, tuple[float, float]] = {}


# ── Persistencia ──────────────────────────────────────────────────────────────

def _load() -> dict | None:
    if not PORT_PATH.exists():
        return None
    try:
        data = json.loads(PORT_PATH.read_text(encoding="utf-8"))
        for k, v in _DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return None


def _save(port: dict) -> None:
    PORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PORT_PATH.write_text(json.dumps(port, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Precios (Yahoo Finance, sin API key) ────────────────────────────────────────

def _price(ticker: str) -> float | None:
    """Último precio de mercado. Cache 60s. Sin API key."""
    import time as _t
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return None
    hit = _price_cache.get(ticker)
    if hit and (_t.time() - hit[1] < 60):
        return hit[0]

    price = None
    # 1) Endpoint chart de Yahoo (usa requests, ya es dependencia).
    try:
        import requests
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        res = r.json()["chart"]["result"][0]
        price = res["meta"].get("regularMarketPrice")
    except Exception:
        price = None
    # 2) Fallback yfinance si está instalado.
    if price is None:
        try:
            import yfinance as yf
            fi = yf.Ticker(ticker).fast_info
            price = fi.get("last_price") or fi.get("lastPrice")
        except Exception:
            price = None

    if price:
        price = float(price)
        _price_cache[ticker] = (price, _t.time())
        return price
    return None


# ── Análisis de mercado (estrategia "smart": SMA + RSI) ─────────────────────────

def _closes(ticker: str, rng: str = "3mo") -> list[float]:
    """Cierres diarios recientes de Yahoo (sin API key). Lista cronológica."""
    try:
        import requests
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.upper().strip()}"
               f"?interval=1d&range={rng}")
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        res = r.json()["chart"]["result"][0]
        closes = res["indicators"]["quote"][0]["close"]
        return [float(c) for c in closes if c is not None]
    except Exception:
        return []


def _sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def _rsi(values: list[float], n: int = 14) -> float | None:
    if len(values) < n + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-n, 0):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_gain, avg_loss = gains / n, losses / n
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _signal(ticker: str) -> dict:
    """Decide según el mercado. Devuelve dict con decision/reason/indicadores.

    Estrategia conservadora (NO garantiza ganancias):
      • Tendencia: SMA20 vs SMA50.  • Momentum: RSI(14).
      • Compra fuerte si RSI<35 (sobreventa = oportunidad de 'comprar la baja').
      • Compra si tendencia alcista (SMA20>SMA50) y RSI<65 (no sobrecomprado).
      • Toma de ganancia (vende fracción) si RSI>75 (sobrecompra) y hay posición con ganancia.
      • Si no, mantiene (HOLD).
    """
    closes = _closes(ticker)
    last = closes[-1] if closes else _price(ticker)
    sma20, sma50, rsi = _sma(closes, 20), _sma(closes, 50), _rsi(closes, 14)
    ind = {"price": last, "sma20": sma20, "sma50": sma50, "rsi": rsi}
    if rsi is None or sma20 is None:
        return {"decision": "hold", "reason": "Datos insuficientes para analizar.", "ind": ind}

    trend_up = (sma50 is None) or (sma20 >= sma50)
    if rsi < 35:
        return {"decision": "buy_strong",
                "reason": f"RSI {rsi:.0f} (sobreventa) → comprar la baja.", "ind": ind}
    if trend_up and rsi < 65:
        return {"decision": "buy",
                "reason": f"Tendencia alcista (SMA20≥SMA50) y RSI {rsi:.0f} sano → acumular.", "ind": ind}
    if rsi > 75:
        return {"decision": "take_profit",
                "reason": f"RSI {rsi:.0f} (sobrecompra) → tomar ganancia parcial.", "ind": ind}
    return {"decision": "hold",
            "reason": f"Sin señal clara (RSI {rsi:.0f}, "
                      f"{'alcista' if trend_up else 'bajista'}) → esperar.", "ind": ind}


def _snapshot(port: dict, total: float) -> None:
    """Guarda un punto de la curva de equity (cap 600 puntos, mínimo cada ~3 min)."""
    eq = port.setdefault("equity", [])
    now = datetime.now().isoformat(timespec="seconds")
    if eq:
        try:
            if (datetime.fromisoformat(now) - datetime.fromisoformat(eq[-1][0])).total_seconds() < 180:
                eq[-1] = [now, round(total, 2)]
                return
        except Exception:
            pass
    eq.append([now, round(total, 2)])
    if len(eq) > 600:
        del eq[: len(eq) - 600]


# ── Operaciones contra broker real (Alpaca) ─────────────────────────────────────

def _real_order(port: dict, ticker: str, side: str, amount, reason: str = "") -> str:
    ticker = ticker.upper().strip()
    live = bool(port.get("live"))
    try:
        from core import broker_alpaca as br
    except Exception as e:
        return f"No pude cargar el conector de Alpaca: {e}"
    if not br.is_configured():
        return ("Faltan las credenciales de Alpaca. Cargá alpaca_api_key y alpaca_secret_key "
                "en la ventana de API keys y reintentá.")
    if side == "sell" and isinstance(amount, str) and amount.lower() in ("all", "todo", "todas"):
        ok, data = br.close_position(live, ticker)
        if not ok:
            return f"No pude cerrar {ticker} en Alpaca: {data}"
        _log_real(port, side, ticker, None, reason or "cierre total", live)
        return f"🔴 Orden REAL a Alpaca ({'LIVE' if live else 'paper'}): cerrar toda la posición de {ticker}."
    notional = float(amount)
    if notional <= 0:
        return "El monto debe ser mayor a 0."
    ok, data = br.place_order(live, ticker, side, notional=notional)
    if not ok:
        return f"Alpaca rechazó la orden: {data}"
    _log_real(port, side, ticker, notional, reason, live)
    verbo = "comprar" if side == "buy" else "vender"
    extra = "" if br.market_open(live) else " (mercado cerrado: se ejecuta en la próxima apertura)"
    return (f"{'🟢' if side == 'buy' else '🔴'} Orden REAL a Alpaca "
            f"({'LIVE — DINERO REAL' if live else 'paper'}): {verbo} {_money(notional)} de {ticker}{extra}.")


def _log_real(port: dict, side: str, ticker: str, amount, reason: str, live: bool) -> None:
    port.setdefault("history", []).append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "action": side, "ticker": ticker, "amount": round(amount, 2) if amount else 0,
        "price": 0, "reason": (reason or "") + (" [REAL LIVE]" if live else " [REAL paper]"),
    })


def _real_valuate(port: dict) -> dict:
    from core import broker_alpaca as br
    live = bool(port.get("live"))
    rows = []
    ok_p, poss = br.positions(live)
    if ok_p and isinstance(poss, list):
        for p in poss:
            shares = float(p.get("qty", 0))
            mkt = float(p.get("market_value", 0))
            cost = float(p.get("cost_basis", 0)) or (shares * float(p.get("avg_entry_price", 0)))
            pnl = float(p.get("unrealized_pl", 0))
            rows.append({"ticker": p.get("symbol", ""), "shares": shares,
                         "price": float(p.get("current_price", 0)), "market": mkt, "cost": cost,
                         "pnl": pnl, "pnl_pct": (pnl / cost * 100) if cost else 0.0})
    ok_a, acc = br.account(live)
    cash = float(acc.get("cash", 0)) if ok_a and isinstance(acc, dict) else 0.0
    equity = float(acc.get("equity", 0)) if ok_a and isinstance(acc, dict) else (cash + sum(r["market"] for r in rows))
    start = port.get("real_start_equity") or equity or 1.0
    return {"rows": rows, "cash": cash, "market_total": sum(r["market"] for r in rows),
            "invested_total": sum(r["cost"] for r in rows), "total": equity,
            "total_pnl": equity - start, "total_pnl_pct": (equity - start) / start * 100}


# ── Cálculos de cartera ─────────────────────────────────────────────────────────

def _valuate(port: dict) -> dict:
    """Devuelve dict con valor de mercado, costo, P&L por posición y total."""
    if port.get("mode") == "real":
        try:
            return _real_valuate(port)
        except Exception:
            pass
    rows = []
    market_total = 0.0
    invested_total = 0.0
    for tk, pos in port.get("positions", {}).items():
        shares = float(pos.get("shares", 0))
        cost = float(pos.get("cost", 0))
        if shares <= 0:
            continue
        price = _price(tk)
        mkt = (price * shares) if price else cost
        pnl = mkt - cost
        pnl_pct = (pnl / cost * 100) if cost else 0.0
        rows.append({"ticker": tk, "shares": shares, "price": price,
                     "market": mkt, "cost": cost, "pnl": pnl, "pnl_pct": pnl_pct})
        market_total += mkt
        invested_total += cost
    cash = float(port.get("cash", 0))
    total = cash + market_total
    start = float(port.get("start_cash", 0)) or 1.0
    return {
        "rows": rows, "cash": cash, "market_total": market_total,
        "invested_total": invested_total, "total": total,
        "total_pnl": total - start, "total_pnl_pct": (total - start) / start * 100,
    }


def _money(x: float) -> str:
    return f"${x:,.2f}"


# ── Operaciones ─────────────────────────────────────────────────────────────────

def _buy(port: dict, ticker: str, amount: float, reason: str = "") -> str:
    if port.get("mode") == "real":
        return _real_order(port, ticker, "buy", amount, reason)
    ticker = ticker.upper().strip()
    price = _price(ticker)
    if not price:
        return f"No pude obtener el precio de {ticker} (¿símbolo válido? ej: SPY, AAPL). No compré nada."
    if amount <= 0:
        return "El monto a invertir debe ser mayor a 0."
    if amount > port["cash"] + 1e-6:
        return (f"No alcanza el efectivo: querés invertir {_money(amount)} pero hay {_money(port['cash'])} "
                f"disponibles. Bajá el monto o agregá fondos (paper) con 'agregar efectivo'.")
    shares = amount / price
    pos = port["positions"].setdefault(ticker, {"shares": 0.0, "cost": 0.0})
    pos["shares"] = round(float(pos["shares"]) + shares, 8)
    pos["cost"] = round(float(pos["cost"]) + amount, 2)
    port["cash"] = round(port["cash"] - amount, 2)
    port["history"].append({
        "ts": datetime.now().isoformat(timespec="seconds"), "action": "buy",
        "ticker": ticker, "shares": round(shares, 6), "price": round(price, 2),
        "amount": round(amount, 2), "reason": reason,
    })
    avg = pos["cost"] / pos["shares"] if pos["shares"] else price
    return (f"Compré {_money(amount)} de {ticker} a {_money(price)} ({shares:.4f} acciones). "
            f"Posición: {pos['shares']:.4f} {ticker} (promedio {_money(avg)}). "
            f"Efectivo restante: {_money(port['cash'])}.")


def _sell(port: dict, ticker: str, amount, reason: str = "") -> str:
    if port.get("mode") == "real":
        return _real_order(port, ticker, "sell", amount, reason)
    ticker = ticker.upper().strip()
    pos = port["positions"].get(ticker)
    if not pos or float(pos.get("shares", 0)) <= 0:
        return f"No tenés posición en {ticker}."
    price = _price(ticker)
    if not price:
        return f"No pude obtener el precio de {ticker}. No vendí nada."
    shares_held = float(pos["shares"])
    mkt_value = shares_held * price
    if isinstance(amount, str) and amount.lower() in ("all", "todo", "todas"):
        sell_amount = mkt_value
        sell_shares = shares_held
    else:
        sell_amount = min(float(amount), mkt_value)
        sell_shares = sell_amount / price
    # costo proporcional liberado
    frac = sell_shares / shares_held if shares_held else 1.0
    cost_freed = float(pos["cost"]) * frac
    realized = (price * sell_shares) - cost_freed
    pos["shares"] = round(shares_held - sell_shares, 8)
    pos["cost"] = round(float(pos["cost"]) - cost_freed, 2)
    if pos["shares"] <= 1e-6:
        port["positions"].pop(ticker, None)
    port["cash"] = round(port["cash"] + price * sell_shares, 2)
    port["history"].append({
        "ts": datetime.now().isoformat(timespec="seconds"), "action": "sell",
        "ticker": ticker, "shares": round(sell_shares, 6), "price": round(price, 2),
        "amount": round(price * sell_shares, 2), "realized": round(realized, 2), "reason": reason,
    })
    sign = "ganancia" if realized >= 0 else "pérdida"
    return (f"Vendí {_money(price * sell_shares)} de {ticker} a {_money(price)} "
            f"({sell_shares:.4f} acciones). {sign.capitalize()} realizada: {_money(realized)}. "
            f"Efectivo: {_money(port['cash'])}.")


# ── Tick automático (lo llama el scheduler) ──────────────────────────────────────

def check_stop_loss(port: dict) -> list[str]:
    """Protección de riesgo: vende TODA posición que caiga stop_loss_pct% bajo su
    costo promedio. Corre ANTES del análisis en cada tick. Devuelve mensajes."""
    sl = float(port.get("stop_loss_pct") or 0)
    if sl <= 0:
        return []
    out = []
    for tk, pos in list(port.get("positions", {}).items()):
        shares, cost = float(pos.get("shares", 0)), float(pos.get("cost", 0))
        if shares <= 0 or cost <= 0:
            continue
        avg = cost / shares
        price = _price(tk)
        if price and price < avg * (1 - sl / 100):
            drop = (1 - price / avg) * 100
            out.append("🛑 STOP-LOSS: " + _sell(port, tk, "all",
                       reason=f"stop-loss: cayó {drop:.1f}% bajo el promedio ({_money(avg)})"))
    return out


def _watch_tickers(port: dict) -> list[str]:
    """Ticker principal + watchlist, sin duplicados, en orden."""
    seen, out = set(), []
    for tk in [port.get("ticker", "SPY")] + list(port.get("watchlist") or []):
        tk = (tk or "").upper().strip()
        if tk and tk not in seen:
            seen.add(tk)
            out.append(tk)
    return out


def _smart_one(port: dict, ticker: str, amount: float) -> str:
    """Analiza UN ticker y opera según la señal."""
    sig = _signal(ticker)
    dec, reason, ind = sig["decision"], sig["reason"], sig["ind"]

    if dec == "buy_strong":
        spend = amount * 2 if port["cash"] >= amount * 2 else amount
        body = _buy(port, ticker, spend, reason=reason)
    elif dec == "buy":
        body = _buy(port, ticker, amount, reason=reason)
    elif dec == "take_profit":
        pos = port["positions"].get(ticker)
        if pos and float(pos.get("shares", 0)) > 0:
            price = ind.get("price") or _price(ticker)
            sell_val = float(pos["shares"]) * (price or 0) * 0.25
            body = _sell(port, ticker, sell_val, reason=reason)
        else:
            body = f"señal de toma de ganancia pero sin posición; no opero."
    else:  # hold
        port.setdefault("history", []).append({
            "ts": datetime.now().isoformat(timespec="seconds"), "action": "hold",
            "ticker": ticker, "amount": 0, "price": round(ind.get("price") or 0, 2),
            "reason": reason,
        })
        body = f"mantengo ({reason})"

    rsi_txt = f"RSI {ind['rsi']:.0f}" if ind.get("rsi") is not None else "s/RSI"
    return f"{ticker} ({rsi_txt}): {body}"


def _tick(port: dict) -> str:
    """Una corrida automática. smart: stop-loss + análisis de TODA la watchlist;
    dca: compra el monto fijo del ticker principal. NO garantiza ganancias."""
    if port.get("strategy", "dca") != "smart":
        return "⏰ DCA automático: " + _buy(port, port["ticker"], float(port["dca_amount"]), reason="DCA programado")

    lines = check_stop_loss(port)                      # 1º proteger lo que ya tengo
    amount = float(port["dca_amount"])
    for tk in _watch_tickers(port):                    # 2º analizar cada ticker vigilado
        lines.append(_smart_one(port, tk, amount))
    return "🤖 Análisis automático — " + " · ".join(lines)


# ── Auto-DCA vía scheduler ───────────────────────────────────────────────────────

def _set_auto(on: bool, freq: str) -> str:
    try:
        from actions import scheduler as sch
        tasks = [t for t in sch._load_tasks() if t.get("name") != _AUTO_NAME]
        if on:
            tasks.append({
                "id": uuid.uuid4().hex, "name": _AUTO_NAME,
                "frequency": "weekly" if freq == "weekly" else "daily",
                "hour": 10, "minute": 0,
                "weekday": "monday" if freq == "weekly" else "",
                "interval_minutes": 1440, "run_at": "",
                "task_action": "tool_invoke",
                "task_parameters": {"tool": "trading_bot", "args": {"action": "dca_run"}},
                "enabled": True, "next_run": None,
            })
        sch._save_tasks(tasks)
        return "ok"
    except Exception as e:
        return f"err:{e}"


# ── Tool entry point ─────────────────────────────────────────────────────────────

@tool(
    name="trading_bot",
    description="Bot de inversión en modo PAPER (simulación con dinero FICTICIO sobre precios REALES de Yahoo Finance — NO hay dinero real ni ganancias garantizadas). Acciones/ETFs estilo S&P 500 (default SPY) y empresas (AAPL, MSFT...). Dos estrategias: 'dca' (compra monto fijo cada período) o 'smart' (ANALIZA el mercado con medias móviles + RSI y decide solo comprar/tomar ganancia/esperar). USAR cuando el usuario hable de 'bot de trading', 'invertir', 'que opere solo/automático', 'analiza el mercado', 'comprá acciones', 'cómo va mi portafolio', 'cuánto gané', 'abrí el panel/dashboard de trading', 'pasá a dinero real'. IMPORTANTE: si pide 'ganancias seguras/garantizadas', aclarar con honestidad que NINGÚN bot las garantiza; esto es práctica sin riesgo en simulación. action=setup (crea portafolio; pasá strategy=smart para automático inteligente) | status | panel (VENTANA gráfica con posiciones, curva y movimientos por fecha) | analyze (señal de mercado SIN operar) | price | invest (compra manual) | sell | tick (fuerza una corrida automática) | history | performance (reporte de ganancia realizada: period=week/month/all) | watchlist (qué tickers vigila el smart) | config (ticker/monto/frecuencia/estrategia/efectivo/stop_loss_pct/watch_add/watch_remove) | auto (automático on/off) | mode (cambia entre SIMULACIÓN local y DINERO REAL vía broker Alpaca) | reset. El modo smart vigila el ticker principal + la watchlist ('vigilá también Apple'→config watch_add=AAPL) y tiene STOP-LOSS automático (vende todo si una posición cae stop_loss_pct% bajo su promedio; default 8%, 0=off). SOBRE DINERO REAL: por defecto todo es simulación; cambiar a real requiere cuenta y claves de Alpaca, y activar dinero real de verdad (live) exige confirmación EXPLÍCITA del usuario. Si el usuario pide pasar a real, usá action=mode mode=real (eso conecta a Alpaca paper primero); solo pasá live=true + confirm=true cuando el usuario confirme claramente que quiere mover plata real.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "setup | status | panel | analyze | price | invest | sell | tick | history | config | auto | mode | reset"},
            "ticker": {"type": "STRING", "description": "Símbolo bursátil (ej SPY, AAPL, MSFT, QQQ). Default: el configurado (SPY)."},
            "amount": {"type": "NUMBER", "description": "Monto en USD a invertir/vender. 'all' para vender todo. Default: el monto por operación."},
            "dca_amount": {"type": "NUMBER", "description": "setup/config: monto fijo por operación (USD)."},
            "frequency": {"type": "STRING", "description": "daily | weekly (frecuencia del automático). Default weekly."},
            "strategy": {"type": "STRING", "description": "setup/config: 'dca' (compra ciega monto fijo) o 'smart' (analiza el mercado y decide solo). Para 'que opere solo según el mercado' usá smart."},
            "cash": {"type": "NUMBER", "description": "setup: capital inicial ficticio (default 10000)."},
            "add_cash": {"type": "NUMBER", "description": "config: agrega efectivo ficticio al portafolio."},
            "state": {"type": "STRING", "description": "auto: on | off."},
            "stop_loss_pct": {"type": "NUMBER", "description": "config: % de caída bajo el promedio que dispara la venta total de una posición (default 8; 0 = desactivar)."},
            "watch_add": {"type": "STRING", "description": "config: ticker a AGREGAR a la watchlist del modo smart (ej AAPL)."},
            "watch_remove": {"type": "STRING", "description": "config: ticker a QUITAR de la watchlist."},
            "period": {"type": "STRING", "description": "performance: week | month | all (default all)."},
            "mode": {"type": "STRING", "description": "action=mode: 'paper' (simulación local) o 'real' (broker Alpaca). Sin valor = informa el modo actual."},
            "live": {"type": "BOOLEAN", "description": "action=mode: true = Alpaca LIVE (DINERO REAL); false/omitido = Alpaca paper (ficticio). true requiere confirm=true."},
            "confirm": {"type": "BOOLEAN", "description": "action=mode con live=true: confirmación EXPLÍCITA del usuario para mover dinero real. No lo pongas en true salvo que el usuario lo confirme sin ambigüedad."}
        },
        "required": [],
    },
    category="trading",
)
def trading_bot(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "status").lower().strip()

    # — Setup / arranque del portafolio paper —
    if action in ("setup", "init", "start", "crear", "empezar"):
        existing = _load()
        if existing and not parameters.get("force"):
            v = _valuate(existing)
            return (f"Ya tenés un portafolio paper (valor {_money(v['total'])}). "
                    f"Para empezar de cero decí 'reiniciá el bot de trading'.")
        port = dict(_DEFAULTS)
        port["positions"] = {}
        port["history"] = []
        cash = float(parameters.get("cash") or _DEFAULTS["cash"])
        port["cash"] = cash
        port["start_cash"] = cash
        port["ticker"] = (parameters.get("ticker") or _DEFAULTS["ticker"]).upper().strip()
        port["dca_amount"] = float(parameters.get("dca_amount") or _DEFAULTS["dca_amount"])
        port["frequency"] = (parameters.get("frequency") or _DEFAULTS["frequency"]).lower()
        strat = (parameters.get("strategy") or _DEFAULTS["strategy"]).lower()
        port["strategy"] = "smart" if strat in ("smart", "automatico", "automático", "inteligente", "mercado") else "dca"
        port["created"] = datetime.now().isoformat(timespec="seconds")
        _save(port)
        modo = ("analiza el mercado (medias móviles + RSI) y decide comprar/vender solo"
                if port["strategy"] == "smart" else "compra un monto fijo cada período (DCA ciego)")
        return (f"📈 Portafolio PAPER creado (dinero ficticio, precios reales). "
                f"Capital inicial {_money(cash)}, {_money(port['dca_amount'])} por operación, "
                f"frecuencia {'semanal' if port['frequency']=='weekly' else 'diaria'} en {port['ticker']}. "
                f"Estrategia: {port['strategy'].upper()} — {modo}. "
                f"Decí 'activá el modo automático' para que opere solo, o 'abrí el panel de trading' para ver todo. "
                f"⚠️ Recordá: ni en simulación ni en real hay ganancias garantizadas.")

    port = _load()
    if port is None:
        return ("Todavía no hay portafolio de trading. Decí 'creá un bot de trading en paper' "
                "y arranco uno con dinero ficticio (default: $10.000, DCA semanal en SPY).")

    # — Precio puntual —
    if action in ("price", "quote", "precio", "cotizacion", "cotización"):
        tk = (parameters.get("ticker") or port["ticker"]).upper().strip()
        p = _price(tk)
        return f"{tk} cotiza {_money(p)}." if p else f"No pude obtener el precio de {tk}."

    # — Tick automático (lo llama el scheduler, o el usuario fuerza una corrida) —
    if action in ("tick", "dca_run", "smart_run", "analizar", "run_auto"):
        msg = _tick(port)
        _snapshot(port, _valuate(port)["total"])
        _save(port)
        return msg

    # — Análisis de mercado sin operar (solo informa la señal) —
    if action in ("analyze", "signal", "señal", "analisis", "análisis", "recomendacion", "recomendación"):
        tk = (parameters.get("ticker") or port["ticker"]).upper().strip()
        sig = _signal(tk)
        ind = sig["ind"]
        parts = [f"{tk} a {_money(ind['price'])}" if ind.get("price") else tk]
        if ind.get("sma20"): parts.append(f"SMA20 {_money(ind['sma20'])}")
        if ind.get("sma50"): parts.append(f"SMA50 {_money(ind['sma50'])}")
        if ind.get("rsi") is not None: parts.append(f"RSI {ind['rsi']:.0f}")
        dec_txt = {"buy_strong": "COMPRA FUERTE", "buy": "COMPRA", "take_profit": "TOMAR GANANCIA",
                   "hold": "MANTENER"}.get(sig["decision"], sig["decision"].upper())
        return f"📡 {' · '.join(parts)}. Señal: {dec_txt}. {sig['reason']} (Análisis, no garantía.)"

    # — Compra manual ahora —
    if action in ("buy", "invest", "invertir", "comprar", "dca"):
        ticker = (parameters.get("ticker") or port["ticker"]).upper().strip()
        amount = float(parameters.get("amount") or port["dca_amount"])
        msg = _buy(port, ticker, amount, reason="compra manual")
        _snapshot(port, _valuate(port)["total"])
        _save(port)
        return msg

    # — Panel gráfico (se abre solo cuando se pide) —
    if action in ("panel", "dashboard", "open", "show", "abrir", "ventana", "tablero"):
        try:
            from core.trading_panel import request_panel
            if request_panel():
                v = _valuate(port)
                return (f"Abrí el panel de trading. Valor actual {_money(v['total'])} "
                        f"({v['total_pnl_pct']:+.2f}%).")
            return "No pude abrir el panel (¿estás sin interfaz gráfica?). Te paso el estado por voz: " + \
                   trading_bot({"action": "status"}, player)
        except Exception as e:
            return f"No pude abrir el panel ({e}). Pedime 'el estado del portafolio' y te lo leo."

    # — Venta —
    if action in ("sell", "vender"):
        ticker = (parameters.get("ticker") or port["ticker"]).upper().strip()
        amount = parameters.get("amount", "all")
        msg = _sell(port, ticker, amount)
        _save(port)
        return msg

    # — Estado / resumen —
    if action in ("status", "portfolio", "portafolio", "resumen", "estado", "balance"):
        v = _valuate(port)
        _snapshot(port, v["total"]); _save(port)
        estr = port.get("strategy", "dca").upper()
        auto = "ON" if port.get("auto") else "OFF"
        if port.get("mode") == "real":
            lbl = "REAL · Alpaca LIVE (dinero real ⚠️)" if port.get("live") else "REAL · Alpaca paper (ficticio)"
        else:
            lbl = "SIMULACIÓN local (ficticio)"
        if not v["rows"]:
            return (f"Portafolio [{lbl}]: {_money(v['cash'])} en efectivo, sin posiciones todavía. "
                    f"Estrategia {estr}, {_money(port['dca_amount'])} por operación "
                    f"{'semanal' if port['frequency']=='weekly' else 'diario'} en {port['ticker']} "
                    f"(automático {auto}).")
        lines = []
        for r in v["rows"]:
            pcur = _money(r["price"]) if r["price"] else "s/precio"
            lines.append(f"• {r['ticker']}: {r['shares']:.4f} acc · {pcur} · "
                         f"valor {_money(r['market'])} · {r['pnl_pct']:+.2f}% ({_money(r['pnl'])})")
        emoji = "🟢" if v["total_pnl"] >= 0 else "🔴"
        return (f"📊 Portafolio [{lbl}] · estrategia {estr} · automático {auto}:\n" + "\n".join(lines) +
                f"\nEfectivo: {_money(v['cash'])} · Invertido: {_money(v['invested_total'])}\n"
                f"{emoji} Valor total: {_money(v['total'])} · "
                f"Rendimiento: {v['total_pnl_pct']:+.2f}% ({_money(v['total_pnl'])}) "
                f"desde {_money(port['start_cash'])}.")

    # — Historial —
    if action in ("history", "historial", "movimientos"):
        hist = port.get("history", [])[-12:]
        if not hist:
            return "Sin movimientos todavía."
        lines = []
        for h in hist:
            ts = h.get("ts", "")[:16].replace("T", " ")
            verb = "Compra" if h["action"] == "buy" else "Venta"
            extra = f" (realizado {_money(h['realized'])})" if "realized" in h else ""
            lines.append(f"{ts} · {verb} {h['ticker']}: {_money(h['amount'])} @ {_money(h['price'])}{extra}")
        return "🧾 Últimos movimientos:\n" + "\n".join(lines)

    # — Configurar parámetros —
    if action in ("config", "set", "configurar", "ajustar"):
        changed = []
        if parameters.get("ticker"):
            port["ticker"] = parameters["ticker"].upper().strip(); changed.append(f"ticker {port['ticker']}")
        if parameters.get("dca_amount"):
            port["dca_amount"] = float(parameters["dca_amount"]); changed.append(f"DCA {_money(port['dca_amount'])}")
        if parameters.get("frequency"):
            port["frequency"] = parameters["frequency"].lower(); changed.append(f"frecuencia {port['frequency']}")
        if parameters.get("strategy"):
            s = parameters["strategy"].lower()
            port["strategy"] = "smart" if s in ("smart", "automatico", "automático", "inteligente", "mercado") else "dca"
            changed.append(f"estrategia {port['strategy'].upper()}")
        if parameters.get("add_cash"):
            add = float(parameters["add_cash"])
            port["cash"] = round(port["cash"] + add, 2)
            port["start_cash"] = round(port["start_cash"] + add, 2)
            changed.append(f"+{_money(add)} efectivo")
        if parameters.get("stop_loss_pct") is not None:
            port["stop_loss_pct"] = max(0.0, float(parameters["stop_loss_pct"]))
            changed.append(f"stop-loss {port['stop_loss_pct']:.0f}%" if port["stop_loss_pct"] else "stop-loss OFF")
        if parameters.get("watch_add"):
            wl = port.setdefault("watchlist", [])
            tk = parameters["watch_add"].upper().strip()
            if tk and tk not in wl:
                wl.append(tk)
            changed.append(f"vigilando también {tk}")
        if parameters.get("watch_remove"):
            tk = parameters["watch_remove"].upper().strip()
            port["watchlist"] = [t for t in port.get("watchlist", []) if t != tk]
            changed.append(f"dejé de vigilar {tk}")
        if not changed:
            return ("No indicaste qué cambiar (ticker, monto DCA, frecuencia, estrategia, "
                    "efectivo, stop_loss_pct, watch_add/watch_remove).")
        _save(port)
        return "Actualizado: " + ", ".join(changed) + "."

    # — Watchlist (qué vigila el modo smart) —
    if action in ("watchlist", "vigilados"):
        wl = _watch_tickers(port)
        sl = port.get("stop_loss_pct") or 0
        return (f"👀 Vigilando: {', '.join(wl)}. Stop-loss: "
                + (f"{sl:.0f}% bajo el promedio." if sl else "desactivado."))

    # — Reporte de rendimiento (ganancia realizada por período) —
    if action in ("performance", "rendimiento", "report", "reporte", "ganancias"):
        period = (parameters.get("period") or "all").lower()
        days = {"week": 7, "semana": 7, "month": 30, "mes": 30}.get(period)
        cutoff = (datetime.now() - timedelta(days=days)).isoformat() if days else ""
        sells = [h for h in port.get("history", [])
                 if h.get("action") == "sell" and "realized" in h and h.get("ts", "") >= cutoff]
        buys = [h for h in port.get("history", []) if h.get("action") == "buy" and h.get("ts", "") >= cutoff]
        realized = sum(h["realized"] for h in sells)
        v = _valuate(port)
        label = {"week": "esta semana", "semana": "esta semana",
                 "month": "este mes", "mes": "este mes"}.get(period, "desde el inicio")
        emoji = "🟢" if realized >= 0 else "🔴"
        return (f"📈 Rendimiento {label}: {emoji} {_money(realized)} realizados "
                f"({len(buys)} compras, {len(sells)} ventas). "
                f"Sin realizar: {v['total_pnl_pct']:+.2f}% ({_money(v['total_pnl'])}) sobre el total. "
                f"Valor actual: {_money(v['total'])}.")

    # — Auto-DCA on/off —
    if action in ("auto", "automatico", "automático"):
        state = (parameters.get("state") or "on").lower()
        on = state in ("on", "activar", "encender", "si", "sí", "true")
        res = _set_auto(on, port.get("frequency", "weekly"))
        if res != "ok":
            return f"No pude configurar el DCA automático ({res})."
        port["auto"] = on
        _save(port)
        if on:
            f = "todos los lunes 10:00" if port["frequency"] == "weekly" else "cada día a las 10:00"
            if port.get("strategy") == "smart":
                return (f"✅ Modo automático INTELIGENTE activado: {f}, JARVIS analiza {port['ticker']} "
                        f"(medias móviles + RSI) y decide solo si compra, toma ganancia o espera "
                        f"(hasta {_money(port['dca_amount'])} por operación). Vía scheduler, sin que hagas nada. "
                        f"⚠️ No garantiza ganancias.")
            return (f"✅ DCA automático activado: invierto {_money(port['dca_amount'])} en "
                    f"{port['ticker']} {f}. JARVIS lo maneja solo vía scheduler.")
        return "Modo automático DESACTIVADO. Las operaciones quedan manuales ('invertí ahora')."

    # — Cambiar entre SIMULACIÓN local y DINERO REAL (broker Alpaca) —
    if action in ("mode", "modo", "switch_mode", "broker", "go_real", "go_live"):
        target = (parameters.get("mode") or "").lower().strip()
        want_live = bool(parameters.get("live")) or action == "go_live"
        confirm = bool(parameters.get("confirm"))
        if action in ("go_real", "go_live"):
            target = "real"

        # Sin destino claro → informo el estado actual y cómo cambiar.
        if not target:
            cur = port.get("mode", "paper")
            if cur == "real":
                donde = "Alpaca LIVE (dinero REAL)" if port.get("live") else "Alpaca paper (ficticio)"
                return (f"El bot está en modo REAL ({donde}). Para volver a la simulación local: "
                        f"'pasá el bot a paper'.")
            return ("El bot está en SIMULACIÓN local (dinero ficticio). Para conectarlo a un broker real "
                    "decí 'pasá el bot a real' (te conecto a Alpaca paper primero, que es plata ficticia "
                    "sobre infraestructura real para validar). Para dinero real de verdad, después: "
                    "'activá dinero real'. Necesitás cuenta en Alpaca y cargar ALPACA_API_KEY y ALPACA_SECRET_KEY.")

        # → volver a simulación local
        if target in ("paper", "sim", "simulacion", "simulación", "local", "ficticio"):
            port["mode"] = "paper"
            _save(port)
            return "Bot en modo SIMULACIÓN local (dinero ficticio). Tu cuenta real no se toca."

        # → ir a real (Alpaca)
        from core import broker_alpaca as br
        if not br.is_configured():
            try:
                from core.credentials import request_dialog
                request_dialog("alpaca")
            except Exception:
                pass
            return ("Para operar con un broker real necesitás una cuenta GRATIS en Alpaca (alpaca.markets) "
                    "y cargar dos claves: ALPACA_API_KEY y ALPACA_SECRET_KEY. Te abrí la ventana de API keys. "
                    "Consejo: empezá con las keys de PAPER de Alpaca (broker real, dinero ficticio) para validar; "
                    "para dinero real de verdad, después generás las keys LIVE.")
        ok, msg = br.ping(want_live)
        if not ok:
            return f"No pude conectar a Alpaca ({'LIVE' if want_live else 'paper'}): {msg}"
        if want_live and not confirm:
            return ("⚠️ ATENCIÓN: esto activa DINERO REAL en Alpaca Live. Las órdenes mueven plata de verdad "
                    "y podés perderla — ningún bot garantiza ganancias. Si estás seguro, confirmámelo "
                    "claramente ('sí, activá dinero real') y lo dejo activo. Te recomiendo validar primero en paper.")
        port["mode"] = "real"
        port["live"] = want_live
        ok_a, acc = br.account(want_live)
        if ok_a and isinstance(acc, dict):
            try:
                port["real_start_equity"] = float(acc.get("equity", 0)) or None
            except Exception:
                pass
        _save(port)
        return (f"✅ Bot en modo REAL — Alpaca {'LIVE (DINERO REAL ⚠️)' if want_live else 'paper (ficticio)'}. "
                f"{msg} La estrategia {port.get('strategy', 'dca').upper()} y el modo automático siguen igual, "
                f"pero ahora las órdenes van a tu cuenta de Alpaca. Para volver: 'pasá el bot a paper'.")

    # — Reset —
    if action in ("reset", "reiniciar", "borrar"):
        _set_auto(False, port.get("frequency", "weekly"))
        try:
            PORT_PATH.unlink(missing_ok=True)
        except Exception:
            pass
        return "Portafolio paper borrado. Decí 'creá un bot de trading' para empezar de nuevo."

    return (f"Acción '{action}' no reconocida. Disponibles: setup, status, panel, price, analyze, "
            f"invest, sell, tick, history, config, auto, reset.")
