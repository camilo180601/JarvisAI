# -*- coding: utf-8 -*-
"""
weather_report.py — Clima vía Open-Meteo (API JSON gratis, sin key).

Antes: wttr.in en texto plano (frágil, se cae seguido, sin pronóstico).
Ahora: geocoding + clima actual + sensación térmica + pronóstico de hoy/mañana,
con descripción en español. Fallback a wttr.in si Open-Meteo no responde.
"""
import urllib.request
import urllib.parse
import json

from core.registry import tool

# Códigos WMO → descripción en español
_WMO = {
    0: "despejado", 1: "mayormente despejado", 2: "parcialmente nublado", 3: "nublado",
    45: "con niebla", 48: "con niebla escarchada",
    51: "llovizna leve", 53: "llovizna", 55: "llovizna intensa",
    61: "lluvia leve", 63: "lluvia", 65: "lluvia fuerte",
    66: "lluvia helada", 67: "lluvia helada fuerte",
    71: "nevada leve", 73: "nevada", 75: "nevada fuerte", 77: "granos de nieve",
    80: "chubascos leves", 81: "chubascos", 82: "chubascos fuertes",
    85: "chubascos de nieve", 86: "chubascos de nieve fuertes",
    95: "tormenta", 96: "tormenta con granizo", 99: "tormenta con granizo fuerte",
}


def _get_json(url: str, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (JARVIS)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _geocode(city: str):
    """Ciudad → (lat, lon, nombre_resuelto). None si no se encontró."""
    url = ("https://geocoding-api.open-meteo.com/v1/search?count=1&language=es&name="
           + urllib.parse.quote(city))
    data = _get_json(url)
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    label = r.get("name", city)
    if r.get("country"):
        label += f" ({r['country']})"
    return r["latitude"], r["longitude"], label


def _fetch_weather(lat: float, lon: float) -> dict:
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
           "weather_code,wind_speed_10m"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
           "&forecast_days=2&timezone=auto")
    return _get_json(url)


def format_report(label: str, data: dict) -> str:
    """Arma el reporte hablado a partir del JSON de Open-Meteo (puro, testeable)."""
    cur = data.get("current", {})
    daily = data.get("daily", {})
    t = cur.get("temperature_2m")
    feels = cur.get("apparent_temperature")
    hum = cur.get("relative_humidity_2m")
    wind = cur.get("wind_speed_10m")
    desc = _WMO.get(cur.get("weather_code"), "")

    parts = [f"En {label}: {desc}, {t}°C" if desc else f"En {label}: {t}°C"]
    if feels is not None and t is not None and abs(feels - t) >= 2:
        parts.append(f"sensación de {feels}°C")
    if hum is not None:
        parts.append(f"humedad {hum}%")
    if wind is not None:
        parts.append(f"viento {wind} km/h")
    report = ", ".join(parts) + "."

    try:
        tmax, tmin = daily["temperature_2m_max"], daily["temperature_2m_min"]
        rain = daily.get("precipitation_probability_max") or [None, None]
        hoy = f" Hoy: máx {tmax[0]}°, mín {tmin[0]}°"
        if rain[0] is not None and rain[0] >= 20:
            hoy += f", {rain[0]}% de lluvia"
        man_desc = _WMO.get((daily.get("weather_code") or [None, None])[1], "")
        man = f". Mañana: {man_desc + ', ' if man_desc else ''}máx {tmax[1]}°, mín {tmin[1]}°"
        if rain[1] is not None and rain[1] >= 20:
            man += f", {rain[1]}% de lluvia"
        report += hoy + man + "."
    except Exception:
        pass
    return report


@tool(
    name='weather_report',
    description='Clima actual + pronóstico de hoy y mañana por ciudad (temperatura, sensación térmica, humedad, viento, probabilidad de lluvia).',
    parameters={'type': 'OBJECT',
     'properties': {'city': {'type': 'STRING', 'description': 'Ciudad (ej: Bogotá, Madrid)'}},
     'required': ['city']},
)
def weather_action(parameters: dict, player=None) -> str:
    city = (parameters.get("city") or "Bogotá").strip() or "Bogotá"
    try:
        geo = _geocode(city)
        if not geo:
            return f"No encontré la ciudad '{city}'. ¿Está bien escrita?"
        lat, lon, label = geo
        report = format_report(label, _fetch_weather(lat, lon))
        if player:
            player.write_log(f"🌤️ {report[:90]}")
        return report
    except Exception:
        # Fallback: wttr.in (lo viejo, por si Open-Meteo está caído)
        try:
            url = f"https://wttr.in/{urllib.parse.quote(city)}?format=%C+%t+%h+%w"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = r.read().decode("utf-8").strip()
            return f"Clima en {city}: {data}"
        except Exception:
            return f"No pude consultar el clima de {city} ahora. Probá de nuevo en un rato."
