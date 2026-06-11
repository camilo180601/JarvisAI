# -*- coding: utf-8 -*-
"""
broker_alpaca.py — Conexión a un broker REAL (Alpaca) para el bot de trading.

Alpaca (alpaca.markets) opera acciones/ETFs de EE.UU. (S&P 500, empresas) por API.
Tiene DOS entornos con las MISMAS keys:
  • PAPER  → https://paper-api.alpaca.markets   (broker real, dinero FICTICIO)
  • LIVE   → https://api.alpaca.markets          (dinero REAL)

JARVIS usa esto solo cuando el usuario cambia el bot a modo "real". El default
siempre es el simulador local (core/trading_panel + actions/trading_bot). Esta capa
usa REST con `requests` (ya es dependencia) — no hace falta instalar SDK.

Credenciales (en .env, vía la ventana de API keys):
  ALPACA_API_KEY     (API Key ID)
  ALPACA_SECRET_KEY  (Secret Key)
Se obtienen gratis creando una cuenta en alpaca.markets → sección API Keys.
Para PAPER alcanza con generar las keys de "Paper Trading". Para LIVE hay que
completar el alta real (KYC) y usar las keys de Live.
"""
from __future__ import annotations
import requests

_PAPER_BASE = "https://paper-api.alpaca.markets"
_LIVE_BASE = "https://api.alpaca.markets"
_TIMEOUT = 15


def _creds() -> tuple[str, str]:
    try:
        from memory.config_manager import cfg
        return (cfg("alpaca_api_key", "") or "").strip(), (cfg("alpaca_secret_key", "") or "").strip()
    except Exception:
        return "", ""


def is_configured() -> bool:
    k, s = _creds()
    return bool(k and s)


def _base(live: bool) -> str:
    return _LIVE_BASE if live else _PAPER_BASE


def _headers() -> dict:
    k, s = _creds()
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s, "Content-Type": "application/json"}


def _req(method: str, path: str, live: bool, **kw) -> tuple[bool, object]:
    """Devuelve (ok, json|mensaje_error)."""
    if not is_configured():
        return False, "Faltan las credenciales de Alpaca (alpaca_api_key / alpaca_secret_key)."
    try:
        r = requests.request(method, _base(live) + path, headers=_headers(), timeout=_TIMEOUT, **kw)
        if r.status_code >= 400:
            try:
                msg = r.json().get("message", r.text)
            except Exception:
                msg = r.text
            return False, f"Alpaca {r.status_code}: {msg}"
        if r.text.strip():
            return True, r.json()
        return True, {}
    except Exception as e:
        return False, f"Error de red con Alpaca: {e}"


def ping(live: bool) -> tuple[bool, str]:
    """Verifica credenciales y entorno. Devuelve (ok, mensaje)."""
    ok, data = _req("GET", "/v2/account", live)
    if not ok:
        return False, str(data)
    env = "LIVE (dinero real)" if live else "Paper (ficticio)"
    status = data.get("status", "?")
    equity = data.get("equity", "?")
    return True, f"Conectado a Alpaca {env}. Cuenta {status}, equity ${equity}."


def account(live: bool) -> tuple[bool, object]:
    return _req("GET", "/v2/account", live)


def positions(live: bool) -> tuple[bool, object]:
    return _req("GET", "/v2/positions", live)


def list_orders(live: bool, limit: int = 50) -> tuple[bool, object]:
    return _req("GET", f"/v2/orders?status=all&limit={limit}&direction=desc", live)


def market_open(live: bool) -> bool:
    ok, data = _req("GET", "/v2/clock", live)
    return bool(ok and isinstance(data, dict) and data.get("is_open"))


def place_order(live: bool, symbol: str, side: str, notional: float | None = None,
                qty: float | None = None) -> tuple[bool, object]:
    """Orden de mercado. notional = monto en USD (permite fracciones); qty = nº de acciones."""
    body = {"symbol": symbol.upper().strip(), "side": side,
            "type": "market", "time_in_force": "day"}
    if notional is not None:
        body["notional"] = round(float(notional), 2)
    elif qty is not None:
        body["qty"] = str(qty)
    else:
        return False, "Hay que indicar notional (USD) o qty (acciones)."
    return _req("POST", "/v2/orders", live, json=body)


def close_position(live: bool, symbol: str) -> tuple[bool, object]:
    return _req("DELETE", f"/v2/positions/{symbol.upper().strip()}", live)
