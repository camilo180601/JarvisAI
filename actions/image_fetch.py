"""
image_fetch.py — Busca una imagen en la web y la descarga a disco (gratis, sin API key).

Fuentes en cascada:
  1. ddgs (DuckDuckGo, sucesor mantenido) — mejor para queries arbitrarias.
  2. Openverse API — respaldo confiable (imágenes con licencia CC).

Devuelve la ruta del archivo guardado. Reusable por adobe_control para el flujo
"buscá una imagen y trazala en Illustrator".
"""
from __future__ import annotations
import io
import re
import time
from pathlib import Path

import requests

from core.registry import tool

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
SAVE_DIR = Path.home() / "Pictures" / "JARVIS"


def _slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_-]+", "-", s)[:40] or "image"


def _candidates(query: str, limit: int = 8) -> list[str]:
    """Lista de URLs de imágenes candidatas, mejor primero."""
    urls: list[str] = []
    # 1. ddgs
    try:
        from ddgs import DDGS
        for r in DDGS().images(query, max_results=limit):
            u = r.get("image")
            if u:
                urls.append(u)
    except Exception:
        pass
    # 2. Openverse (respaldo)
    if not urls:
        try:
            resp = requests.get(
                "https://api.openverse.org/v1/images/",
                params={"q": query, "page_size": limit},
                headers={"User-Agent": "JARVIS/1.0"}, timeout=20,
            )
            if resp.ok:
                for x in resp.json().get("results", []):
                    u = x.get("url")
                    if u:
                        urls.append(u)
        except Exception:
            pass
    return urls


def fetch_image(query: str, dest: str | Path | None = None,
                min_side: int = 200) -> tuple[str, str]:
    """
    Descarga la primera imagen válida para `query`.
    Devuelve (ruta_absoluta, descripción). Lanza RuntimeError si no consigue ninguna.
    """
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("Falta Pillow (pip install pillow).")

    urls = _candidates(query)
    if not urls:
        raise RuntimeError(f"No encontré imágenes para '{query}'.")

    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    last_err = ""
    for url in urls:
        try:
            r = requests.get(url, headers={"User-Agent": _UA}, timeout=30)
            if not r.ok or len(r.content) < 1024:
                continue
            im = Image.open(io.BytesIO(r.content))
            im.load()
            if min(im.size) < min_side:
                continue
            # Conservar transparencia si la hay; si no, RGB
            fmt = (im.format or "").upper()
            ext = "png" if (fmt == "PNG" or im.mode in ("RGBA", "LA", "P")) else "jpg"
            if ext == "jpg" and im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            if dest:
                out = Path(dest)
                out.parent.mkdir(parents=True, exist_ok=True)
            else:
                out = SAVE_DIR / f"{_slug(query)}-{int(time.time())}.{ext}"
            im.save(out)
            return str(out.resolve()), f"{im.size[0]}x{im.size[1]} {fmt or ext.upper()}"
        except Exception as e:
            last_err = str(e)
            continue
    raise RuntimeError(f"No pude descargar ninguna imagen válida para '{query}'. {last_err}")


@tool(
    name="image_fetch",
    description="Busca una imagen en la web y la descarga al disco (carpeta ~/Pictures/JARVIS). USAR cuando el usuario dice 'descargame/buscame una imagen de X', 'bajá una foto de Y'. Devuelve la ruta del archivo. Para meterla luego en Illustrator y vectorizarla, mejor usar adobe_control action=place_trace directamente con el query.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Qué imagen buscar (ej: 'galleta caricatura png')"},
            "path": {"type": "STRING", "description": "Ruta de destino opcional; si se omite va a ~/Pictures/JARVIS"}
        },
        "required": ["query"],
    },
    category="content",
)
def image_fetch(parameters: dict, player=None) -> str:
    query = (parameters.get("query") or "").strip()
    if not query:
        return "Error: falta 'query' (qué imagen buscar)."
    dest = parameters.get("path") or parameters.get("dest")
    if player:
        player.write_log(f"🖼️ Buscando imagen: '{query}'...")
    try:
        path, meta = fetch_image(query, dest=dest)
    except Exception as e:
        return f"Error: {e}"
    return f"Imagen guardada en {path} ({meta})."
