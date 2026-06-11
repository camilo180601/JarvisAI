# -*- coding: utf-8 -*-
"""
mac_contacts.py — Lee la app Contactos de macOS (la agenda real del usuario) para
resolver nombre ↔ número. Así "mandá un WhatsApp a Mamá" usa el alias de TU agenda
(no el nombre de perfil de WhatsApp), y las notificaciones dicen "Mensaje de Mamá".

El volcado por AppleScript es lento (~30s con cientos de contactos), así que se
CACHEA en config/apple_contacts_cache.json y se refresca como mucho 1 vez/día (o on-demand).
Solo macOS. Normaliza números locales al código de país por defecto (config: default_country_code, def 57).
"""
from __future__ import annotations
import json
import sys
import time
import threading
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_FILE = BASE_DIR / "config" / "apple_contacts_cache.json"
TTL = 24 * 3600
_lock = threading.Lock()


def _is_mac() -> bool:
    return sys.platform == "darwin"


def _norm(s: str) -> str:
    """Minúsculas sin acentos/diacríticos, para comparar 'Mama' con 'Mamá'."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _default_cc() -> str:
    try:
        from memory.config_manager import cfg
        return str(cfg("default_country_code", "") or "57")
    except Exception:
        return "57"


_DUMP_SCRIPT = (
    'tell application "Contacts"\n'
    'set out to ""\n'
    'repeat with p in people\n'
    'set pname to name of p\n'
    'repeat with ph in phones of p\n'
    'set out to out & pname & tab & (value of ph) & linefeed\n'
    'end repeat\n'
    'end repeat\n'
    'return out\n'
    'end tell'
)


def _dump() -> list[tuple[str, str, str]]:
    """Devuelve [(nombre, telefono_crudo, solo_digitos)]."""
    try:
        # Contacts debe estar corriendo o AppleScript da -600 ("isn't running").
        # -g: sin foco, -j: oculto → el usuario no ve nada.
        subprocess.run(["open", "-gja", "Contacts"], capture_output=True, timeout=10)
        time.sleep(2.5)
        r = subprocess.run(["osascript", "-e", _DUMP_SCRIPT],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            print(f"[mac_contacts] osascript error: {(r.stderr or '')[:120]}")
            return []
    except Exception as e:
        print(f"[mac_contacts] osascript falló: {e}")
        return []
    pairs = []
    for line in (r.stdout or "").splitlines():
        if "\t" not in line:
            continue
        nm, raw = line.split("\t", 1)
        nm = nm.strip()
        digits = "".join(c for c in raw if c.isdigit())
        if nm and len(digits) >= 7:   # descartar nombres vacíos / números cortos (911, 123…)
            pairs.append((nm, raw.strip(), digits))
    return pairs


def _natl(digits: str) -> str:
    """Número nacional (últimos 10 dígitos) — estable para comparar sin importar el código país."""
    return digits[-10:] if len(digits) >= 10 else digits


def _intl(raw: str, digits: str, cc: str) -> str:
    """Número internacional sin '+' para enviar por WhatsApp."""
    if raw.strip().startswith("+"):
        return digits
    if len(digits) == 10:        # móvil local (ej Colombia: 3xxxxxxxxx) → anteponer CC
        return cc + digits
    return digits


def build_cache() -> dict:
    """Reconstruye la caché desde la app Contactos (lento). Devuelve el dict."""
    if not _is_mac():
        return {"by_name": [], "by_natl": {}, "built": 0}
    cc = _default_cc()
    pairs = _dump()
    if not pairs:
        # El volcado falló (sin permiso de Contactos en este proceso, p.ej. lanzado
        # por nohup/GUI). NUNCA pisar una caché buena con una vacía.
        old = _load()
        if old and old.get("count"):
            print("[mac_contacts] volcado vacío (¿sin permiso?); conservo la caché previa.")
            return old
    by_name: list = []         # [[nombre, telefono_intl]]
    by_natl: dict = {}         # natl10 → nombre
    for nm, raw, digits in pairs:
        intl = _intl(raw, digits, cc)
        by_name.append([nm, intl])
        natl = _natl(digits)
        if natl and natl not in by_natl:
            by_natl[natl] = nm
    data = {"by_name": by_name, "by_natl": by_natl, "built": time.time(), "count": len(by_name)}
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[mac_contacts] no pude guardar caché: {e}")
    return data


def _load() -> dict | None:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def get_cache() -> dict | None:
    """Caché actual (aunque esté vieja). None si no hay nada todavía."""
    return _load()


def warm_async(force: bool = False) -> None:
    """Reconstruye la caché en background si falta o está vieja (no bloquea)."""
    if not _is_mac():
        return
    data = _load()
    if data and not force and (time.time() - data.get("built", 0) < TTL):
        return
    def run():
        with _lock:
            d = _load()
            if d and not force and (time.time() - d.get("built", 0) < TTL):
                return
            n = build_cache().get("count", 0)
            print(f"[mac_contacts] caché de Contactos lista ({n} números).")
    threading.Thread(target=run, daemon=True, name="mac-contacts-warm").start()


def find_by_name(query: str) -> list[tuple[str, str]]:
    """Busca por nombre en la agenda de Apple. Devuelve [(nombre, telefono_intl)]."""
    data = get_cache()
    if not data or not query.strip():
        return []
    q = _norm(query)
    out, seen = [], set()
    # 1) match exacto (sin acentos)
    for nm, ph in data.get("by_name", []):
        if _norm(nm) == q and ph not in seen:
            seen.add(ph); out.append((nm, ph))
    # 2) palabra completa (ej "mama" matchea "Mama Norma" pero después del exacto)
    for nm, ph in data.get("by_name", []):
        if q in _norm(nm).split() and ph not in seen:
            seen.add(ph); out.append((nm, ph))
    # 3) substring
    for nm, ph in data.get("by_name", []):
        if q in _norm(nm) and ph not in seen:
            seen.add(ph); out.append((nm, ph))
    return out


def name_for_phone(phone: str) -> str:
    """Reverse: número (cualquier formato) → nombre de la agenda. '' si no está."""
    data = get_cache()
    if not data:
        return ""
    digits = "".join(c for c in str(phone) if c.isdigit())
    if not digits:
        return ""
    return data.get("by_natl", {}).get(_natl(digits), "")


def available() -> bool:
    return _is_mac()
