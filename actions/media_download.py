"""
media_download.py — Descarga de video/audio/subtítulos con yt-dlp (YouTube y +1000 sitios).

Acciones (action=...):
  video      descarga el video (mejor calidad disponible) — default
  audio      descarga solo el audio como MP3/M4A
  subs       descarga subtítulos (.srt)
  info       muestra título/duración/formatos sin descargar

Nota: para fusionar video+audio en alta calidad o convertir a MP3 hace falta ffmpeg
(brew install ffmpeg). Sin ffmpeg baja el mejor formato único disponible.
"""
from __future__ import annotations
import shutil
from pathlib import Path
from core.registry import tool

DEFAULT_DIR = Path.home() / "Downloads" / "JARVIS"


def _ffmpeg_dir() -> str | None:
    """Ubica ffmpeg incluso si Homebrew no está en el PATH (arranque desde GUI)."""
    exe = shutil.which("ffmpeg")
    if exe:
        return str(Path(exe).parent)
    for cand in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if Path(cand).exists():
            return str(Path(cand).parent)
    return None


@tool(
    name='media_download',
    description="Descarga video/audio/subtítulos de YouTube y +1000 sitios (yt-dlp). Acciones: video (default), audio (MP3/M4A), subs (subtítulos .srt), info (datos sin descargar). Ej: 'bajá este video', 'descargá esta canción en MP3', 'bajá los subtítulos'. Se guarda en ~/Downloads/JARVIS.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'video (default) | audio | subs | info'},
                    'url': {'type': 'STRING', 'description': 'URL del video/audio'},
                    'dest': {'type': 'STRING',
                             'description': 'Carpeta de salida (default ~/Downloads/JARVIS)'},
                    'lang': {'type': 'STRING', 'description': "subs: idioma, ej 'es'"}},
     'required': ['url']},
)
def media_download(parameters: dict, player=None) -> str:
    try:
        import yt_dlp
    except ImportError:
        return "Falta yt-dlp (pip install yt-dlp)."

    url = (parameters.get("url") or "").strip()
    if not url:
        return "Error: falta 'url'."
    action = (parameters.get("action") or "video").lower().strip()
    out_dir = Path(parameters.get("dest") or DEFAULT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    ff_dir = _ffmpeg_dir()
    has_ff = ff_dir is not None

    if player:
        player.write_log(f"⬇️ {action}: {url}")

    # ── info ──
    if action == "info":
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
                i = ydl.extract_info(url, download=False)
            dur = i.get("duration") or 0
            return (f"{i.get('title','?')} — {i.get('uploader','?')}\n"
                    f"Duración: {dur//60}:{dur%60:02d} · Vistas: {i.get('view_count','?')}")
        except Exception as e:
            return f"Error: {str(e)[:200]}"

    opts = {
        "outtmpl": str(out_dir / "%(title).80s.%(ext)s"),
        "quiet": True,
        "noprogress": True,
        "restrictfilenames": True,
    }
    if ff_dir:
        opts["ffmpeg_location"] = ff_dir

    if action == "audio":
        if has_ff:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio",
                                       "preferredcodec": "mp3", "preferredquality": "192"}]
        else:
            opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
    elif action == "subs":
        lang = parameters.get("lang") or "es"
        opts.update({"skip_download": True, "writesubtitles": True,
                     "writeautomaticsub": True, "subtitleslangs": [lang, "en"],
                     "subtitlesformat": "srt"})
    else:  # video
        opts["format"] = ("bestvideo*+bestaudio/best" if has_ff
                          else "best[ext=mp4]/best")

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        title = info.get("title", "archivo")
        note = "" if has_ff else " (sin ffmpeg: calidad/formato limitado; brew install ffmpeg para máxima calidad)"
        return f"✓ Descargado '{title}' en {out_dir}{note}"
    except Exception as e:
        return f"Error: {str(e)[:200]}"
