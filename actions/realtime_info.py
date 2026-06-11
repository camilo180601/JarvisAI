"""
realtime_info.py — Información en tiempo real, gratis y sin API keys.

  crypto    precio de criptomonedas (CoinGecko)
  currency  conversión de divisas / valor del dólar (open.er-api.com)
  stock     cotización de acciones (Stooq)
  news      últimas noticias sobre un tema (DuckDuckGo)
"""
from __future__ import annotations
import requests
from core.registry import tool

_UA = {"User-Agent": "JARVIS/1.0"}

_CRYPTO_IDS = {
    "btc": "bitcoin", "bitcoin": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "sol": "solana", "solana": "solana",
    "ada": "cardano", "doge": "dogecoin",
    "xrp": "ripple", "bnb": "binancecoin",
    "usdt": "tether", "matic": "matic-network",
}


def _crypto(query: str, vs: str = "usd") -> str:
    coins = [c.strip().lower() for c in query.replace(",", " ").split() if c.strip()]
    if not coins:
        coins = ["bitcoin", "ethereum"]
    ids = []
    for c in coins:
        if c in _CRYPTO_IDS:
            ids.append(_CRYPTO_IDS[c])
        else:
            try:
                s = requests.get("https://api.coingecko.com/api/v3/search",
                                 params={"query": c}, headers=_UA, timeout=15).json()
                if s.get("coins"):
                    ids.append(s["coins"][0]["id"])
            except Exception:
                pass
    if not ids:
        return f"No reconocí esas criptos: {query}"
    vs = vs.lower()
    r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                     params={"ids": ",".join(ids), "vs_currencies": vs,
                             "include_24hr_change": "true"}, headers=_UA, timeout=15)
    data = r.json()
    out = []
    for cid in ids:
        d = data.get(cid, {})
        price = d.get(vs)
        chg = d.get(f"{vs}_24h_change")
        if price is not None:
            arrow = "▲" if (chg or 0) >= 0 else "▼"
            out.append(f"  {cid.capitalize()}: {price:,.2f} {vs.upper()} {arrow}{abs(chg or 0):.1f}% (24h)")
    return "💰 Cripto:\n" + "\n".join(out) if out else "Sin datos."


def _currency(amount: float, base: str, target: str) -> str:
    base, target = base.upper(), target.upper()
    r = requests.get(f"https://open.er-api.com/v6/latest/{base}", headers=_UA, timeout=15).json()
    if r.get("result") != "success":
        return f"No pude obtener cotizaciones de {base}."
    rate = r.get("rates", {}).get(target)
    if rate is None:
        return f"No encontré la moneda {target}."
    return f"💱 {amount:,.2f} {base} = {amount*rate:,.2f} {target}  (1 {base} = {rate:,.4f} {target})"


def _stock(symbol: str) -> str:
    sym = symbol.strip().lower()
    s = sym if "." in sym else f"{sym}.us"
    try:
        txt = requests.get("https://stooq.com/q/l/",
                           params={"s": s, "f": "sd2t2ohlcv", "h": "", "e": "csv"},
                           headers=_UA, timeout=15).text.strip().splitlines()
        if len(txt) < 2:
            return f"Sin datos para {symbol}."
        cols = txt[0].split(","); vals = txt[1].split(",")
        row = dict(zip(cols, vals))
        close = row.get("Close")
        if not close or close == "N/D":
            return f"No encontré la acción '{symbol}'."
        return (f"📈 {symbol.upper()}: {close} "
                f"(apertura {row.get('Open','?')}, máx {row.get('High','?')}, mín {row.get('Low','?')}) "
                f"— {row.get('Date','')}")
    except Exception as e:
        return f"Error con la acción {symbol}: {str(e)[:80]}"


def _news(query: str, n: int = 5) -> str:
    try:
        from ddgs import DDGS
        items = list(DDGS().news(query, max_results=n))
    except Exception as e:
        return f"No pude traer noticias: {str(e)[:80]}"
    if not items:
        return f"Sin noticias recientes sobre '{query}'."
    out = [f"📰 Noticias — {query}:"]
    for it in items[:n]:
        out.append(f"  • {it.get('title','')} ({it.get('source','')})\n    {it.get('url','')}")
    return "\n".join(out)


@tool(
    name='realtime_info',
    description="Datos en tiempo real, gratis. USAR para: 'cuánto está el bitcoin/ethereum' (crypto), 'a cuánto está el dólar', 'convertí 100 USD a pesos' (currency), 'cómo está la acción de Apple/Tesla' (stock), 'últimas noticias de X' (news).",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING', 'description': 'crypto | currency | stock | news'},
                    'query': {'type': 'STRING',
                              'description': "crypto: monedas (ej 'btc eth'); news: tema"},
                    'symbol': {'type': 'STRING', 'description': 'stock: símbolo (AAPL, TSLA, MSFT)'},
                    'vs': {'type': 'STRING',
                           'description': 'crypto: moneda de referencia (usd default)'},
                    'amount': {'type': 'NUMBER', 'description': 'currency: monto a convertir'},
                    'base': {'type': 'STRING', 'description': 'currency: moneda origen (ej USD)'},
                    'target': {'type': 'STRING',
                               'description': 'currency: moneda destino (ej COP, EUR)'}},
     'required': ['action']},
)
def realtime_info(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "").lower().strip()

    if action in ("crypto", "cripto"):
        return _crypto(parameters.get("query") or parameters.get("symbol") or "bitcoin ethereum",
                       parameters.get("vs", "usd"))
    if action in ("currency", "divisa", "exchange", "dolar", "dólar"):
        amt = float(parameters.get("amount") or 1)
        base = parameters.get("base") or "USD"
        target = parameters.get("target") or parameters.get("to") or "COP"
        return _currency(amt, base, target)
    if action in ("stock", "stocks", "accion", "acción"):
        sym = parameters.get("symbol") or parameters.get("query")
        if not sym:
            return "Decime el símbolo (ej AAPL, TSLA)."
        return _stock(sym)
    if action in ("news", "noticias"):
        q = parameters.get("query") or parameters.get("topic") or ""
        if not q:
            return "¿Sobre qué tema querés noticias?"
        return _news(q, int(parameters.get("n", 5)))

    return "Acciones: crypto, currency, stock, news."
