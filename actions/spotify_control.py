"""
spotify_control.py — Control real de Spotify vía Web API (spotipy).

Busca y reproduce artistas/canciones/playlists, controla la reproducción y elige
dispositivo. Requiere spotify_client_id/secret/redirect_uri en el .env y autorizar
una vez (action=connect abre el navegador).

Acciones: connect, play (query), pause, resume, next, prev, volume (level),
          search (query), devices, current, transfer (device).
"""
from __future__ import annotations
import time
from pathlib import Path
from core.registry import tool

_SCOPES = ("user-read-playback-state user-modify-playback-state "
           "user-read-currently-playing streaming app-remote-control "
           "playlist-read-private")
_CACHE = Path(__file__).resolve().parent.parent / "config" / ".spotify_token"


def _creds():
    from memory.config_manager import cfg
    return (cfg("spotify_client_id"), cfg("spotify_client_secret"),
            cfg("spotify_redirect_uri", "http://127.0.0.1:8888/callback"))


def _oauth(open_browser: bool = False):
    from spotipy.oauth2 import SpotifyOAuth
    cid, secret, uri = _creds()
    if not cid or not secret:
        return None
    return SpotifyOAuth(client_id=cid, client_secret=secret, redirect_uri=uri,
                        scope=_SCOPES, cache_path=str(_CACHE), open_browser=open_browser)


def _client():
    """Devuelve un cliente spotipy autenticado, o None si falta autorizar."""
    import spotipy
    auth = _oauth()
    if auth is None:
        return None
    tok = auth.cache_handler.get_cached_token() if hasattr(auth, "cache_handler") else auth.get_cached_token()
    if not tok:
        return None
    return spotipy.Spotify(auth_manager=auth)


def _pick_device(sp, preferred: str | None = None) -> str | None:
    devs = sp.devices().get("devices", [])
    if not devs:
        return None
    if preferred:
        q = preferred.lower().strip()
        for d in devs:
            if q in d.get("name", "").lower():
                return d["id"]
    for d in devs:
        if d.get("is_active"):
            return d["id"]
    return devs[0]["id"]


def _ensure_device(sp, device_id):
    """Despierta/activa el dispositivo (resuelve el 403 'Restriction violated')."""
    if not device_id:
        return
    try:
        sp.transfer_playback(device_id, force_play=False)
        import time
        time.sleep(0.6)
    except Exception:
        pass


def now_playing_info() -> dict | None:
    """Para la UI: estado de reproducción + dispositivo actual.
    None si hubo error de red; {'auth': False} si falta autorizar."""
    try:
        cid, secret, _ = _creds()
        if not cid or not secret:
            return {"auth": False, "reason": "no_creds"}
        sp = _client()
        if sp is None:
            return {"auth": False, "reason": "no_token"}
        cur = sp.current_playback()
        if not cur or not cur.get("item"):
            dev = (cur or {}).get("device", {}) or {}
            return {"auth": True, "playing": False,
                    "device": dev.get("name", ""), "device_type": dev.get("type", "")}
        it = cur["item"]
        dev = cur.get("device", {}) or {}
        cover = None
        try:
            imgs = it.get("album", {}).get("images", [])
            cover = imgs[-1]["url"] if imgs else None  # la más chica
        except Exception:
            cover = None
        return {
            "auth": True,
            "playing": bool(cur.get("is_playing")),
            "track": it.get("name", ""),
            "artist": ", ".join(a["name"] for a in it.get("artists", [])) or "",
            "device": dev.get("name", ""),
            "device_type": dev.get("type", ""),
            "cover": cover,
        }
    except Exception:
        return None


@tool(
    name='spotify_control',
    description="Control real de Spotify (Web API). 'reproducí/poné a X' (play con query=artista/canción/playlist), pausar, reanudar, siguiente, anterior, volumen, buscar, qué suena, dispositivos. La PRIMERA vez requiere autorizar: action=connect (abre el navegador). Necesita cuenta Premium para reproducir. Si no hay dispositivo activo, hay que abrir Spotify en algún equipo.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'connect | play | pause | resume | next | prev | volume '
                                              '| search | current | devices | transfer'},
                    'query': {'type': 'STRING',
                              'description': 'Para play/search: canción, artista o playlist (ej '
                                             "'Diomedes Díaz')"},
                    'device': {'type': 'STRING',
                               'description': 'play/transfer: nombre del dispositivo donde sonar (ej '
                                              "'Echo Dot', 'MacBook'). Si se omite usa el activo o el "
                                              'primero.'},
                    'level': {'type': 'INTEGER', 'description': 'volume: 0-100'},
                    'value': {'type': 'STRING',
                              'description': "volume: 'up'/'down' si no se da level"}},
     'required': ['action']},
)
def spotify_control(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "").lower().strip()
    if not action:
        return "Falta 'action'."

    # ── Credenciales ──
    cid, secret, _ = _creds()
    if not cid or not secret:
        try:
            from core.credentials import require_key
            ok, msg = require_key("spotify")
            if not ok:
                return msg
        except Exception:
            return "Faltan credenciales de Spotify (spotify_client_id/secret en el .env)."

    # ── Autorización (una vez) ──
    if action in ("connect", "auth", "login"):
        auth = _oauth(open_browser=True)
        try:
            # dispara el flujo OAuth (abre navegador, levanta server local)
            auth.get_access_token(as_dict=False)
            return "✓ Spotify autorizado. Ya podés pedir que reproduzca música."
        except Exception as e:
            url = auth.get_authorize_url()
            return f"Para autorizar Spotify abrí este link y aceptá:\n{url}\n({str(e)[:80]})"

    sp = _client()
    if sp is None:
        return ("Spotify no está autorizado todavía. Decí 'conectá Spotify' "
                "(action=connect) y aceptá en el navegador una vez.")

    try:
        # ── Reproducir algo por nombre ──
        if action in ("play", "reproducir", "poner"):
            query = (parameters.get("query") or parameters.get("name")
                     or parameters.get("track") or parameters.get("artist") or "").strip()
            device = _pick_device(sp, parameters.get("device"))
            _ensure_device(sp, device)

            def _start(**kw):
                # Reintenta despertando el dispositivo si da 403 "Restriction violated".
                try:
                    sp.start_playback(device_id=device, **kw)
                except Exception as e:
                    if "403" in str(e) or "Restriction" in str(e):
                        try:
                            sp.transfer_playback(device, force_play=True)
                            import time; time.sleep(0.8)
                        except Exception:
                            pass
                        sp.start_playback(device_id=device, **kw)
                    else:
                        raise

            if query:
                artists = sp.search(q=query, type="artist", limit=1).get("artists", {}).get("items", [])
                if artists and query.lower() in artists[0]["name"].lower():
                    _start(context_uri=artists[0]["uri"]); return f"▶️ Reproduciendo a {artists[0]['name']}."
                pl = sp.search(q=query, type="playlist", limit=1).get("playlists", {}).get("items", [])
                if pl and ("playlist" in query.lower() or "lista" in query.lower()):
                    _start(context_uri=pl[0]["uri"]); return f"▶️ Reproduciendo la playlist {pl[0]['name']}."
                tr = sp.search(q=query, type="track", limit=1).get("tracks", {}).get("items", [])
                if tr:
                    _start(uris=[tr[0]["uri"]]); return f"▶️ {tr[0]['name']} — {tr[0]['artists'][0]['name']}."
                if artists:
                    _start(context_uri=artists[0]["uri"]); return f"▶️ Reproduciendo a {artists[0]['name']}."
                return f"No encontré '{query}' en Spotify."
            else:
                _start(); return "▶️ Reproduciendo."

        if action in ("transfer", "cambiar_dispositivo", "device_to"):
            target = parameters.get("device") or parameters.get("to")
            dev = _pick_device(sp, target)
            if not dev:
                return "No hay dispositivos. Abrí Spotify en el equipo destino."
            sp.transfer_playback(dev, force_play=True)
            return f"✓ Reproducción movida al dispositivo."

        if action in ("pause", "pausa"):
            sp.pause_playback()
            return "⏸️ Pausado."
        if action in ("resume", "continuar"):
            sp.start_playback(device_id=_pick_device(sp))
            return "▶️ Reanudado."
        if action in ("next", "skip", "siguiente"):
            sp.next_track()
            return "⏭️ Siguiente."
        if action in ("prev", "previous", "back", "anterior"):
            sp.previous_track()
            return "⏮️ Anterior."
        if action in ("volume", "volumen"):
            lvl = parameters.get("level")
            if lvl is None:
                v = str(parameters.get("value", "")).lower()
                cur = (sp.current_playback() or {}).get("device", {}).get("volume_percent", 50)
                lvl = min(100, cur + 15) if "up" in v or "sub" in v else max(0, cur - 15)
            sp.volume(int(lvl))
            return f"🔊 Volumen al {int(lvl)}%."
        if action in ("search", "buscar"):
            q = parameters.get("query", "")
            tr = sp.search(q=q, type="track", limit=5).get("tracks", {}).get("items", [])
            if not tr:
                return f"Sin resultados para '{q}'."
            return "🔎 Resultados:\n" + "\n".join(
                f"  • {t['name']} — {t['artists'][0]['name']}" for t in tr)
        if action in ("current", "now", "actual"):
            cur = sp.current_playback()
            if not cur or not cur.get("item"):
                return "No hay nada reproduciéndose."
            it = cur["item"]
            return f"🎵 {it['name']} — {it['artists'][0]['name']}"
        if action == "devices":
            devs = sp.devices().get("devices", [])
            if not devs:
                return "No hay dispositivos Spotify activos. Abrí Spotify en algún equipo."
            return "📱 Dispositivos:\n" + "\n".join(
                f"  {'▶️' if d.get('is_active') else '  '} {d['name']} ({d['type']})" for d in devs)

        return ("Acciones: connect, play (query), pause, resume, next, prev, "
                "volume, search, current, devices.")
    except Exception as e:
        em = str(e)
        if "NO_ACTIVE_DEVICE" in em or "404" in em:
            return ("No hay un dispositivo activo. Abrí Spotify en tu compu/celu/Echo "
                    "y reintentá (o pedime 'dispositivos de Spotify').")
        if "premium required" in em.lower():
            return "Spotify requiere cuenta Premium para controlar la reproducción por API."
        if "restriction violated" in em.lower() or "403" in em:
            return ("El dispositivo no aceptó el comando (no es por Premium). Probá: abrí Spotify "
                    "en el equipo, reproducí algo manualmente 1 segundo, y reintento — o decime "
                    "en qué dispositivo querés que suene ('dispositivos de Spotify' para verlos).")
        return f"Error de Spotify: {em[:140]}"
