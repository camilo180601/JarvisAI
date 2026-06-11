"""
smart_home.py — Control de bombillos/enchufes/dispositivos Tuya (Smart Life) por LAN.

Tuya es la plataforma detrás de la mayoría de los dispositivos "Smart Life" genéricos.
JARVIS los controla LOCALMENTE en tu red WiFi (rápido, sin nube) una vez que tiene
la clave local de cada dispositivo — que se obtiene una sola vez desde tu cuenta Tuya.

Setup (una vez):
  1. Creá una cuenta gratis en https://iot.tuya.com (Tuya IoT Platform).
  2. Cloud → Development → Create Cloud Project. Anotá Access ID y Access Secret.
  3. En el proyecto, pestaña "Devices" → "Link App Account" → escaneá el QR con tu
     app Smart Life / Tuya Smart (así Tuya ve tus dispositivos).
  4. Poné en config/api_keys.json:  tuya_api_key, tuya_api_secret, tuya_region (us/eu/cn/in).
  5. Decile a JARVIS "configurá los dispositivos" (action=setup) — baja las claves y escanea la red.

Acciones (action=...):
  setup        Baja dispositivos+claves de la nube Tuya y escanea la LAN. Guarda config.
  scan         Re-escanea la LAN para refrescar IPs.
  list         Lista los dispositivos conocidos.
  on / off     Encender / apagar (por nombre o id).
  toggle       Alternar.
  brightness   Brillo 0-100.
  color        Color (hex '#ff0000' o nombre básico).
  status       Estado actual del dispositivo.
"""
from __future__ import annotations
import json
from pathlib import Path
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent
API_FILE = BASE_DIR / "config" / "api_keys.json"
DEVICES_FILE = BASE_DIR / "config" / "tuya_devices.json"

# categorías Tuya que son luces (soportan brillo/color)
_LIGHT_CATS = {"dj", "dd", "dc", "xdd", "fwd", "tgq", "tgkg"}

_COLORS = {
    "rojo": (255, 0, 0), "red": (255, 0, 0),
    "verde": (0, 255, 0), "green": (0, 255, 0),
    "azul": (0, 0, 255), "blue": (0, 0, 255),
    "amarillo": (255, 255, 0), "yellow": (255, 255, 0),
    "naranja": (255, 120, 0), "orange": (255, 120, 0),
    "morado": (140, 0, 255), "violeta": (140, 0, 255), "purple": (140, 0, 255),
    "rosa": (255, 80, 180), "pink": (255, 80, 180),
    "cian": (0, 255, 255), "cyan": (0, 255, 255),
    "blanco": (255, 255, 255), "white": (255, 255, 255),
}


def _cfg(key: str, default=""):
    try:
        from memory.config_manager import cfg
        return cfg(key, default)
    except Exception:
        return default


def _load_devices() -> list[dict]:
    if DEVICES_FILE.exists():
        try:
            return json.loads(DEVICES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_devices(devs: list[dict]) -> None:
    DEVICES_FILE.write_text(json.dumps(devs, indent=2, ensure_ascii=False), encoding="utf-8")


def _hex_to_rgb(h: str):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _find(devs: list[dict], name_or_id: str) -> dict | None:
    q = (name_or_id or "").lower().strip()
    if not q:
        return None
    for d in devs:                                   # id exacto
        if d.get("id", "").lower() == q:
            return d
    for d in devs:                                   # nombre exacto
        if d.get("name", "").lower() == q:
            return d
    for d in devs:                                   # nombre parcial
        if q in d.get("name", "").lower():
            return d
    return None


def _is_light(dev: dict) -> bool:
    return dev.get("category", "") in _LIGHT_CATS or "luz" in dev.get("name", "").lower() \
        or "bomb" in dev.get("name", "").lower() or "light" in dev.get("name", "").lower()


def _connect(dev: dict):
    """Devuelve un objeto tinytuya conectado, o (None, error)."""
    import tinytuya
    if not dev.get("ip"):
        return None, f"No tengo la IP de '{dev.get('name')}'. Corré action=scan (debe estar encendido y en tu WiFi)."
    if not dev.get("key"):
        return None, f"Falta la clave local de '{dev.get('name')}'. Corré action=setup."
    ver = float(dev.get("version") or 3.3)
    cls = tinytuya.BulbDevice if _is_light(dev) else tinytuya.OutletDevice
    d = cls(dev["id"], dev["ip"], dev["key"])
    d.set_version(ver)
    d.set_socketTimeout(5)
    return d, None


# ───────────────────────── setup / scan ─────────────────────────

def _scan_lan() -> dict:
    """Escanea la LAN. Devuelve {device_id: {ip, version}}."""
    import tinytuya
    found = tinytuya.deviceScan(False, 18)
    out = {}
    for info in (found or {}).values():
        gwid = info.get("gwId") or info.get("id")
        if gwid:
            out[gwid] = {"ip": info.get("ip"), "version": info.get("version", 3.3)}
    return out


def _setup(player=None) -> str:
    try:
        from core.credentials import require_key
        ok, msg = require_key("tuya")
        if not ok:
            return msg + " (Access ID/Secret de https://iot.tuya.com → tu Cloud Project.)"
    except Exception:
        pass
    key, secret = _cfg("tuya_api_key"), _cfg("tuya_api_secret")
    region = _cfg("tuya_region", "us") or "us"
    if not key or not secret:
        return "Faltan credenciales Tuya (tuya_api_key, tuya_api_secret). Cargalas y reintento."
    try:
        import tinytuya
    except ImportError:
        return "Falta tinytuya (pip install tinytuya)."
    if player:
        player.write_log("🏠 Conectando a la nube Tuya...")
    try:
        cloud = tinytuya.Cloud(apiRegion=region, apiKey=key, apiSecret=secret)
        cloud_devs = cloud.getdevices(False)
    except Exception as e:
        return f"Error con la nube Tuya: {str(e)[:160]}"
    if not isinstance(cloud_devs, list) or not cloud_devs:
        return ("La nube no devolvió dispositivos. Verificá que hayas vinculado tu cuenta "
                "Smart Life en el proyecto (Devices → Link App Account) y la región correcta.")
    if player:
        player.write_log(f"  ✓ {len(cloud_devs)} dispositivos en la nube. Escaneando la red...")
    lan = _scan_lan()
    devs = []
    for cd in cloud_devs:
        did = cd.get("id")
        merged = {
            "id": did,
            "name": cd.get("name", did),
            "key": cd.get("key", ""),
            "category": cd.get("category", ""),
            "product_name": cd.get("product_name", ""),
            "ip": lan.get(did, {}).get("ip", ""),
            "version": lan.get(did, {}).get("version", 3.3),
        }
        devs.append(merged)
    _save_devices(devs)
    online = sum(1 for d in devs if d.get("ip"))
    return (f"✓ {len(devs)} dispositivos guardados ({online} encontrados en la red ahora). "
            f"Probá: 'encendé {devs[0]['name']}'." if devs else "Sin dispositivos.")


# ───────────────────────── acción principal ─────────────────────────

@tool(
    name='smart_home',
    description="Controla bombillos, enchufes y dispositivos Tuya/Smart Life (red local) y luces Philips Hue. USAR: 'encendé/apagá la luz', 'poné el bombillo en rojo', 'bajá la luz al 30%', 'qué dispositivos tengo', 'configurá los dispositivos', 'vinculá Hue'. Acciones: setup (Tuya, una vez), scan, list, on, off, toggle, brightness, color, white, status, functions (capacidades de un dispositivo Tuya), set_value (setear un DP crudo: para ventiladores/termostatos/etc.), hue_pair (vincular el Bridge Philips Hue).",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'setup | scan | list | on | off | toggle | brightness | '
                                              'color | white | status | functions | set_value | '
                                              'hue_pair'},
                    'device': {'type': 'STRING',
                               'description': 'Nombre o id del dispositivo (Tuya o Hue). Si hay uno '
                                              'solo, se asume.'},
                    'level': {'type': 'INTEGER', 'description': 'brightness/white: 0-100'},
                    'color': {'type': 'STRING',
                              'description': "color: hex '#ff0000' o nombre (rojo, azul, verde, "
                                             'blanco...)'},
                    'temp': {'type': 'STRING',
                             'description': 'white: temperatura — cálido | neutral | frío | hospital, '
                                            'o 0(cálido)-100(frío).'},
                    'dp': {'type': 'STRING',
                           'description': 'set_value: código/índice del DP a setear (ver con '
                                          'action=functions)'},
                    'value': {'type': 'STRING',
                              'description': 'set_value: valor a escribir (true/false, número o '
                                             'texto)'}},
     'required': ['action']},
)
def smart_home(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "list").lower().strip()

    if action == "setup":
        return _setup(player)

    if action == "scan":
        devs = _load_devices()
        if not devs:
            return "No hay dispositivos. Corré action=setup primero."
        lan = _scan_lan()
        n = 0
        for d in devs:
            info = lan.get(d["id"])
            if info and info.get("ip"):
                d["ip"], d["version"] = info["ip"], info.get("version", d.get("version", 3.3))
                n += 1
        _save_devices(devs)
        return f"✓ Red escaneada: {n}/{len(devs)} dispositivos en línea."

    # ── Philips Hue: vincular el Bridge ──
    if action in ("hue_pair", "pair_hue", "hue_setup"):
        try:
            from core import hue as _hue
            return _hue.pair()
        except Exception as e:
            return f"Hue no disponible: {e}"

    # Dispositivos Tuya (json) + luces Hue (en vivo si hay Bridge)
    devs = _load_devices()
    hue_devs = []
    try:
        from core import hue as _hue
        if _hue.available():
            hue_devs = _hue.list_lights()
    except Exception:
        pass
    all_devs = devs + hue_devs

    if not all_devs:
        return "No tengo dispositivos. Decí 'configurá los dispositivos' (setup) o vinculá Hue (hue_pair)."

    if action == "list":
        lines = ["Dispositivos:"]
        for d in all_devs:
            prov = d.get("provider", "tuya")
            tag = "💡" if (_is_light(d) or prov == "hue") else "🔌"
            net = "Hue" if prov == "hue" else (d.get("ip") or "sin IP (apagado/fuera de red)")
            lines.append(f"  {tag} {d.get('name')} — {net}")
        return "\n".join(lines)

    # acciones que requieren un dispositivo
    target = parameters.get("device") or parameters.get("name") or parameters.get("id") or ""
    if not target and len(all_devs) == 1:
        dev = all_devs[0]
    else:
        dev = _find(all_devs, target)
    if not dev:
        names = ", ".join(d.get("name", "?") for d in all_devs)
        return f"¿Cuál dispositivo? Tengo: {names}."

    # ── Ruteo a Philips Hue ──
    if dev.get("provider") == "hue":
        from core import hue as _hue
        if action in ("on", "off"):
            return _hue.control(dev["name"], action)
        if action == "toggle":
            return _hue.control(dev["name"], "off" if dev.get("on") else "on")
        if action == "brightness":
            return _hue.control(dev["name"], "brightness", level=int(parameters.get("level", 50)))
        if action in ("color", "white"):
            c = (parameters.get("color") or "blanco").lower()
            rgb = _COLORS.get(c, _hex_to_rgb(c) if c.lstrip("#") else (255, 255, 255))
            return _hue.control(dev["name"], "color", rgb=rgb)
        if action == "status":
            return f"{dev['name']}: {'encendida' if dev.get('on') else 'apagada'} (Hue)."
        return f"Acción '{action}' no soportada en Hue."

    d, err = _connect(dev)
    if err:
        return err

    # ── Tuya avanzado: descubrir capacidades / setear DP crudo ──
    if action in ("functions", "capabilities"):
        key, secret = _cfg("tuya_api_key"), _cfg("tuya_api_secret")
        try:
            import tinytuya
            cloud = tinytuya.Cloud(apiRegion=_cfg("tuya_region", "us") or "us",
                                   apiKey=key, apiSecret=secret)
            fns = cloud.getfunctions(dev["id"])
            items = (fns or {}).get("result", {}).get("functions", []) if isinstance(fns, dict) else []
            if not items:
                return f"Sin capacidades reportadas para {dev['name']}."
            return f"Capacidades de {dev['name']}:\n" + "\n".join(
                f"  • {f.get('code')} ({f.get('type')})" for f in items[:25])
        except Exception as e:
            return f"No pude leer capacidades: {str(e)[:100]}"
    if action in ("set_value", "set_dp", "set"):
        dp = parameters.get("dp") or parameters.get("code")
        val = parameters.get("value")
        if dp is None:
            return "Decime 'dp' (código/índice) y 'value'."
        try:
            d.set_value(dp, val)
            return f"✓ {dev['name']}: {dp} = {val}"
        except Exception as e:
            return f"✗ {str(e)[:120]}"

    try:
        if action == "on":
            d.turn_on()
            return f"✓ {dev['name']} encendido."
        if action == "off":
            d.turn_off()
            return f"✓ {dev['name']} apagado."
        if action == "toggle":
            st = d.status().get("dps", {})
            cur = st.get("1") or st.get("20")
            d.turn_off() if cur else d.turn_on()
            return f"✓ {dev['name']} {'apagado' if cur else 'encendido'}."
        if action == "brightness":
            if not _is_light(dev):
                return f"{dev['name']} no es una luz regulable."
            pct = max(1, min(100, int(parameters.get("level", 50))))
            d.turn_on()
            d.set_brightness_percentage(pct)
            return f"✓ {dev['name']} al {pct}%."
        if action == "white":
            if not _is_light(dev):
                return f"{dev['name']} no soporta temperatura de blanco."
            t = str(parameters.get("temp") or parameters.get("color") or "neutral").lower()
            temp_map = {"calido": 0, "cálido": 0, "warm": 0, "amarillo": 10,
                        "neutral": 50, "neutro": 50,
                        "frio": 100, "frío": 100, "cool": 100, "cold": 100, "hospital": 100, "dia": 100, "día": 100}
            ct = temp_map.get(t)
            if ct is None:
                try:
                    ct = max(0, min(100, int(t)))
                except Exception:
                    ct = 50
            lvl = max(1, min(100, int(parameters.get("level", 100))))
            d.turn_on()
            try:
                d.set_white_percentage(lvl, ct)
            except Exception:
                d.set_white(int(lvl * 10), int(ct * 10))
            return f"✓ {dev['name']} en blanco {t} ({lvl}%)."
        if action == "color":
            if not _is_light(dev):
                return f"{dev['name']} no soporta color."
            c = parameters.get("color") or parameters.get("hex") or ""
            if c.startswith("#") or (len(c) in (3, 6) and all(ch in "0123456789abcdefABCDEF" for ch in c)):
                rgb = _hex_to_rgb(c)
            elif c.lower() in _COLORS:
                rgb = _COLORS[c.lower()]
            else:
                return f"No reconozco el color '{c}'. Usá hex (#ff0000) o: {', '.join(list(_COLORS)[:8])}…"
            d.turn_on()
            d.set_colour(*rgb)
            return f"✓ {dev['name']} en {c}."
        if action == "status":
            st = d.status().get("dps", {})
            on = st.get("1") or st.get("20")
            return f"{dev['name']}: {'encendido' if on else 'apagado'}. DPS: {st}"
    except Exception as e:
        return f"✗ Error con {dev['name']}: {str(e)[:140]} (¿está encendido y en la red? probá action=scan)"

    return (f"Acción '{action}' no reconocida. Usá: setup, scan, list, on, off, toggle, "
            "brightness, color, white, status.")
