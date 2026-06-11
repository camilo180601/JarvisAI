"""
google_maps.py — Abre Google Maps + calcula distancia/tiempo por voz (OSRM, sin key).
"""
import json
import urllib.parse
import urllib.request
import webbrowser

from core.registry import tool


def _get_json(url: str, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (JARVIS)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _geocode(place: str):
    """Lugar → (lat, lon) vía Open-Meteo geocoding (gratis). None si no está."""
    data = _get_json("https://geocoding-api.open-meteo.com/v1/search?count=1&language=es&name="
                     + urllib.parse.quote(place))
    res = data.get("results") or []
    return (res[0]["latitude"], res[0]["longitude"]) if res else None


def route_summary(origin: str, destination: str, mode: str = "driving") -> str:
    """Distancia y duración por OSRM (público, sin key). '' si no se pudo."""
    try:
        o, d = _geocode(origin), _geocode(destination)
        if not o or not d:
            return ""
        profile = {"driving": "driving", "walking": "foot", "bicycling": "bike"}.get(mode, "driving")
        data = _get_json(f"https://router.project-osrm.org/route/v1/{profile}/"
                         f"{o[1]},{o[0]};{d[1]},{d[0]}?overview=false")
        routes = data.get("routes") or []
        if not routes:
            return ""
        km = routes[0]["distance"] / 1000
        mins = routes[0]["duration"] / 60
        dur = f"{mins / 60:.1f} horas" if mins >= 90 else f"{mins:.0f} minutos"
        return f"Son {km:.0f} km, unas {dur} en {'auto' if profile == 'driving' else profile}"
    except Exception:
        return ""


@tool(
    name='google_maps',
    description='Maps: directions (origin+destination, mode car/walk/bike) o search.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING', 'description': 'directions | search'},
                    'origin': {'type': 'STRING',
                               'description': 'Punto de partida (dirección, ciudad, lugar)'},
                    'destination': {'type': 'STRING',
                                    'description': 'Destino (dirección, ciudad, lugar)'},
                    'mode': {'type': 'STRING',
                             'description': 'car (auto) | walk (caminando) | bike (bicicleta). '
                                            'Default: car'},
                    'query': {'type': 'STRING',
                              'description': 'Lugar a buscar en el mapa (para action=search)'}},
     'required': ['action']},
)
def google_maps(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "search").lower()
    query = parameters.get("query", "")
    origin = parameters.get("origin", "")
    destination = parameters.get("destination", "")
    mode = (parameters.get("mode") or "driving").lower()  # driving, walking, bicycling, transit

    if action == "search":
        if not query:
            return "Error: falta 'query' para search."
        url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}"
        webbrowser.open(url)
        return f"Abriendo Maps con búsqueda: '{query}'."

    if action == "directions" or action == "route":
        if not destination:
            return "Error: falta 'destination' para directions."
        params = {"api": "1", "destination": destination, "travelmode": mode}
        if origin:
            params["origin"] = origin
        url = "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params)
        webbrowser.open(url)
        msg = f"Abriendo ruta {mode} a '{destination}'" + (f" desde '{origin}'" if origin else "")
        # Decir distancia/tiempo por voz (OSRM), no solo abrir el mapa
        if origin:
            summary = route_summary(origin, destination, mode)
            if summary:
                msg += f". {summary}."
        return msg

    if action == "place":
        if not query:
            return "Error: falta 'query' (nombre del lugar)."
        url = f"https://www.google.com/maps/place/{urllib.parse.quote(query)}"
        webbrowser.open(url)
        return f"Abriendo lugar: '{query}'."

    return f"Acción '{action}' no soportada. Usa: search, directions, place."
