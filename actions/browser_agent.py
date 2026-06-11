"""
browser_agent.py — Automatización de navegador con Playwright (Chromium ya instalado).

Cada llamada abre el navegador, hace la operación y lo cierra (stateless, simple y robusto).

Acciones (action=...):
  scrape     navega a url y devuelve el texto visible (limpio) — default
  extract    navega y devuelve textos que matchean un selector CSS
  links      navega y lista los links de la página
  screenshot navega y guarda una captura (full page opcional)
  fill       navega, completa campos {selector: valor} y opcionalmente hace submit/click
"""
from __future__ import annotations
import re
from pathlib import Path
from core.registry import tool

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _norm_url(u: str) -> str:
    u = (u or "").strip()
    if u and not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


@tool(
    name='browser_agent',
    description="Automatiza un navegador real (Playwright/Chromium). USAR para leer/scrapear sitios, extraer datos, capturar páginas o llenar formularios. Acciones: scrape (texto visible), extract (por selector CSS), links (lista links), screenshot, fill (completa campos y envía). Ej: 'leéme esta página', 'sacá los precios de este sitio', 'capturá esta web', 'llená este formulario'.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'scrape (texto crudo) | article (lectura LIMPIA del '
                                              "artículo, sin navbar/ads — para 'leéme este "
                                              "artículo/nota') | extract | links | screenshot | fill"},
                    'url': {'type': 'STRING', 'description': 'URL a abrir'},
                    'selector': {'type': 'STRING', 'description': 'extract: selector CSS'},
                    'fields': {'type': 'OBJECT', 'description': 'fill: {selector: valor}'},
                    'submit': {'type': 'STRING',
                               'description': 'fill: selector del botón a clickear tras llenar'},
                    'path': {'type': 'STRING', 'description': 'screenshot: ruta de salida'},
                    'full_page': {'type': 'BOOLEAN',
                                  'description': 'screenshot: capturar la página completa'},
                    'limit': {'type': 'INTEGER', 'description': 'scrape: máximo de caracteres'}},
     'required': ['url']},
)
def browser_agent(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "scrape").lower().strip()
    url = _norm_url(parameters.get("url") or "")
    if not url:
        return "Error: falta 'url'."

    # ── Lectura limpia de artículo (inspirado en web-readability de openclaw) ──
    if action in ("article", "read", "readable", "leer"):
        try:
            import trafilatura
        except ImportError:
            return "Falta trafilatura (pip install trafilatura)."
        if player:
            player.write_log(f"📰 Leyendo artículo → {url}")
        try:
            downloaded = trafilatura.fetch_url(url)
            text = trafilatura.extract(downloaded, include_comments=False,
                                       include_tables=True) if downloaded else None
            if not text:
                action = "scrape"  # fallback: scrape con playwright si trafilatura no pudo
            else:
                limit = int(parameters.get("limit") or 6000)
                return text[:limit] + ("…" if len(text) > limit else "")
        except Exception as e:
            return f"No pude extraer el artículo: {str(e)[:120]}"

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Falta Playwright (pip install playwright && playwright install chromium)."

    headless = parameters.get("headless")
    headless = True if headless is None else bool(headless)
    timeout = int(parameters.get("timeout") or 30) * 1000

    if player:
        player.write_log(f"🌐 {action} → {url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            page = browser.new_context(user_agent=_UA).new_page()
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass

            if action == "scrape":
                txt = page.evaluate("() => document.body ? document.body.innerText : ''")
                txt = re.sub(r"\n{3,}", "\n\n", (txt or "").strip())
                limit = int(parameters.get("limit") or 4000)
                browser.close()
                return txt[:limit] + ("…" if len(txt) > limit else "") if txt else "(página sin texto)"

            if action == "extract":
                sel = parameters.get("selector")
                if not sel:
                    browser.close()
                    return "Error: falta 'selector' (CSS)."
                vals = page.eval_on_selector_all(
                    sel, "els => els.map(e => (e.innerText||e.textContent||'').trim()).filter(Boolean)")
                browser.close()
                if not vals:
                    return f"Sin resultados para selector '{sel}'."
                return "\n".join(f"{i}. {v}" for i, v in enumerate(vals[:40], 1))

            if action == "links":
                links = page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => ({t:(e.innerText||'').trim(), h:e.href}))")
                browser.close()
                seen, out = set(), []
                for l in links:
                    h = l.get("h")
                    if h and h.startswith("http") and h not in seen:
                        seen.add(h)
                        out.append(f"- {l.get('t') or '(sin texto)'} → {h}")
                    if len(out) >= 40:
                        break
                return "\n".join(out) if out else "(sin links)"

            if action == "screenshot":
                dest = parameters.get("path") or str(Path.home() / "Desktop" / "jarvis_page.png")
                page.screenshot(path=dest, full_page=bool(parameters.get("full_page")))
                browser.close()
                return f"✓ Captura → {dest}"

            if action == "fill":
                fields = parameters.get("fields") or {}
                if not isinstance(fields, dict) or not fields:
                    browser.close()
                    return "Error: 'fields' debe ser {selector: valor}."
                for sel, val in fields.items():
                    page.fill(sel, str(val), timeout=timeout)
                submit = parameters.get("submit") or parameters.get("click")
                if submit:
                    page.click(submit, timeout=timeout)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                result = page.evaluate("() => document.body ? document.body.innerText.slice(0,2000) : ''")
                browser.close()
                return f"✓ Formulario completado.\n{result}"

            browser.close()
            return f"Acción '{action}' no reconocida. Usá: scrape, extract, links, screenshot, fill."
    except Exception as e:
        return f"Error de navegador: {str(e)[:200]}"
