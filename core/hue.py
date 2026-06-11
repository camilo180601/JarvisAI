"""
hue.py — Soporte Philips Hue (control local por el Bridge). Opcional.

El Bridge se descubre solo (discovery.meethue.com) o por IP en config (hue_bridge_ip).
El primer pareo requiere apretar el botón físico del Bridge (pair()).
El usuario/token se guarda en ~/.python_hue (lo maneja la lib phue).
"""
from __future__ import annotations
import requests


def _bridge_ip() -> str | None:
    # 1) config explícita
    try:
        from memory.config_manager import cfg
        ip = cfg("hue_bridge_ip", "")
        if ip:
            return ip
    except Exception:
        pass
    # 2) descubrimiento en la nube de Hue
    try:
        r = requests.get("https://discovery.meethue.com/", timeout=8)
        data = r.json()
        if data:
            return data[0].get("internalipaddress")
    except Exception:
        pass
    return None


def _connect(do_pair: bool = False):
    from phue import Bridge
    ip = _bridge_ip()
    if not ip:
        raise RuntimeError("no encontré el Bridge de Hue en la red")
    b = Bridge(ip)
    if do_pair:
        b.connect()  # requiere botón apretado
    b.connect()
    return b


def available() -> bool:
    try:
        from memory.config_manager import cfg
        return bool(cfg("hue_bridge_ip", "")) or _bridge_ip() is not None
    except Exception:
        return False


def pair() -> str:
    try:
        b = _connect(do_pair=True)
        n = len(b.get_light_objects())
        return f"✓ Hue vinculado. {n} luces encontradas."
    except Exception as e:
        return ("Para vincular Hue: apretá el botón del Bridge y reintentá en 30s. "
                f"({str(e)[:80]})")


def list_lights() -> list[dict]:
    """Devuelve [{provider:'hue', id, name, on}] o [] si no hay bridge."""
    try:
        b = _connect()
        out = []
        for lid, l in b.get_api().get("lights", {}).items():
            out.append({"provider": "hue", "id": lid, "name": l.get("name", f"Hue {lid}"),
                        "on": l.get("state", {}).get("on", False)})
        return out
    except Exception:
        return []


def _light(b, name_or_id: str):
    objs = b.get_light_objects("name")
    if name_or_id in objs:
        return objs[name_or_id]
    q = name_or_id.lower()
    for nm, obj in objs.items():
        if q in nm.lower():
            return obj
    return None


def control(name: str, action: str, **kw) -> str:
    try:
        b = _connect()
    except Exception as e:
        return f"✗ Hue: {str(e)[:80]}"
    lamp = _light(b, name)
    if lamp is None:
        return f"No encontré la luz Hue '{name}'."
    try:
        if action == "on":
            lamp.on = True
            return f"✓ {lamp.name} encendida."
        if action == "off":
            lamp.on = False
            return f"✓ {lamp.name} apagada."
        if action == "brightness":
            lamp.on = True
            lamp.brightness = max(1, min(254, int(kw.get("level", 50) / 100 * 254)))
            return f"✓ {lamp.name} al {kw.get('level')}%."
        if action == "color":
            r, g, bl = kw.get("rgb", (255, 255, 255))
            lamp.on = True
            # RGB → xy (aprox.)
            import colorsys
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, bl / 255)
            lamp.hue = int(h * 65535)
            lamp.saturation = int(s * 254)
            lamp.brightness = int(v * 254)
            return f"✓ {lamp.name} con color."
    except Exception as e:
        return f"✗ Hue: {str(e)[:80]}"
    return f"Acción '{action}' no soportada en Hue."
