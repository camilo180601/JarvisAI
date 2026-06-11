# -*- coding: utf-8 -*-
"""
youtube_video.py — Reproducción directa de YouTube.

Antes: abría la PÁGINA DE RESULTADOS (el usuario tenía que clickear el video).
Ahora: resuelve el primer video de la búsqueda (sin API key, leyendo el JSON
inicial de la página) y abre watch?v=… directo. Fallback: página de resultados.
"""
import re
import json
import webbrowser
import urllib.parse
import urllib.request

from core.registry import tool


def _first_video(query: str):
    """(video_id, título) del primer resultado de búsqueda. None si no se pudo."""
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept-Language": "es-419,es;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        page = r.read().decode("utf-8", errors="ignore")
    # primer videoRenderer del JSON inicial: videoId + título
    m = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}', page)
    if not m:
        m2 = re.search(r'"videoId":"([\w-]{11})"', page)
        return (m2.group(1), "") if m2 else None
    title = m.group(2).encode("utf-8").decode("unicode_escape", errors="ignore")
    try:  # des-escapar unicode del JSON (ej é) sin romper acentos
        title = json.loads(f'"{m.group(2)}"')
    except Exception:
        pass
    return m.group(1), title


@tool(
    name='youtube_video',
    description='YouTube: reproduce DIRECTO el primer video de la búsqueda (play, default). También search_page para abrir los resultados.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'play (default, reproduce el primer video) | search_page (abre los resultados)'},
                    'query': {'type': 'STRING', 'description': 'Qué buscar/reproducir'},
                    'url': {'type': 'STRING', 'description': 'URL directa de un video (opcional, la abre tal cual)'}},
     'required': []},
)
def youtube_video(parameters: dict, response=None, player=None) -> str:
    action = (parameters.get("action") or "play").lower().strip()
    query = (parameters.get("query") or "").strip()
    direct = (parameters.get("url") or "").strip()

    if direct:
        webbrowser.open(direct)
        return "Abriendo el video."
    if not query:
        return "¿Qué querés ver en YouTube?"

    if action in ("search_page", "search", "resultados"):
        webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(query))
        return f"Abrí los resultados de '{query}' en YouTube."

    # play (default): resolver el primer video y reproducirlo directo
    try:
        hit = _first_video(query)
        if hit:
            vid, title = hit
            webbrowser.open(f"https://www.youtube.com/watch?v={vid}")
            msg = f"▶️ Reproduciendo: {title or query}"
            if player:
                player.write_log(f"📺 {msg[:90]}")
            return msg
    except Exception:
        pass
    # fallback: página de resultados
    webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(query))
    return f"No pude resolver el video directo; abrí los resultados de '{query}'."
