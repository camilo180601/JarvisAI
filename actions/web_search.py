"""
web_search.py — Búsqueda web vía DuckDuckGo (gratis, sin API key).
"""
import re
from core.registry import tool

# Motor: ddgs (nombre nuevo de la lib) con fallback al nombre viejo deprecado.
try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _html_unescape(s: str) -> str:
    import html
    return html.unescape(re.sub(r"<[^>]+>", "", s or ""))


def _ddg_html_search(query: str, max_results: int = 4) -> list[tuple[str, str, str]]:
    """Fallback sin librería: scrapea html.duckduckgo.com (HTML estático, sin JS).
    Se usa cuando duckduckgo_search falla (ratelimit/lib rota/no instalada)."""
    import urllib.request
    import urllib.parse
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (JARVIS)"})
    with urllib.request.urlopen(req, timeout=10) as r:
        page = r.read().decode("utf-8", errors="ignore")
    results = []
    # bloques de resultado: <a class="result__a" href="...">título</a> ... <a class="result__snippet">cuerpo</a>
    blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'class="result__snippet"[^>]*>(.*?)</a>',
        page, re.DOTALL)
    for href, title, body in blocks[:max_results]:
        # los hrefs vienen como //duckduckgo.com/l/?uddg=<url-real>
        m = re.search(r"uddg=([^&]+)", href)
        real = urllib.parse.unquote(m.group(1)) if m else href
        results.append((_clean(_html_unescape(title)), _clean(_html_unescape(body)), real))
    return results


@tool(
    name='web_search',
    description='Búsqueda web (DuckDuckGo). mode=compare para comparar items por aspect (price/specs/reviews).',
    parameters={'type': 'OBJECT',
     'properties': {'query': {'type': 'STRING', 'description': 'Search query'},
                    'mode': {'type': 'STRING', 'description': 'search (default) or compare'},
                    'items': {'type': 'ARRAY',
                              'items': {'type': 'STRING'},
                              'description': 'Items to compare'},
                    'aspect': {'type': 'STRING', 'description': 'price | specs | reviews'}},
     'required': ['query']},
)
def web_search(parameters: dict, player=None) -> str:
    """Busca en la web. Motor primario: duckduckgo_search; fallback: HTML scraping."""
    query = (parameters.get("query") or "").strip()
    if not query:
        return "Error: no se proporcionó 'query'."

    mode = (parameters.get("mode") or "search").lower()
    max_results = 5 if mode == "compare" else 4

    if player:
        player.write_log(f"🔎 Buscando: '{query}'...")

    try:
        results = []
        if DDGS is not None:
            try:
                with DDGS() as ddgs:
                    for r in ddgs.text(query, max_results=max_results, region="wt-wt"):
                        title = _clean(r.get("title", ""))
                        body = _clean(r.get("body", ""))
                        url = r.get("href") or r.get("url") or ""
                        if title or body:
                            results.append((title, body, url))
            except Exception:
                results = []   # la lib falla seguido (ratelimit) → probar el fallback
        if not results:
            results = _ddg_html_search(query, max_results)

        if not results:
            return f"No se encontraron resultados para '{query}'."

        if mode == "compare":
            aspect = parameters.get("aspect", "")
            header = f"Comparación '{query}'" + (f" — {aspect}" if aspect else "") + ":\n"
        else:
            header = f"Resultados para '{query}':\n"

        body_lines = []
        for i, (title, body, url) in enumerate(results, 1):
            snippet = body[:200] + ("..." if len(body) > 200 else "")
            body_lines.append(f"{i}. {title}\n   {snippet}\n   {url}")
        return header + "\n".join(body_lines)

    except Exception as e:
        return f"Error en búsqueda web: {e}"
