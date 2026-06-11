# -*- coding: utf-8 -*-
"""
facetime.py — Llamadas por FaceTime (solo macOS).

"llamá a Mamá" → resuelve el contacto en la agenda de Apple (core/mac_contacts,
insensible a acentos, match exacto primero) y abre FaceTime con el número.
FaceTime muestra su propio botón de confirmación antes de llamar (a propósito:
nadie quiere llamadas disparadas por error de transcripción).

  audio (default) → facetime-audio://  (llamada tipo teléfono)
  video           → facetime://        (videollamada)
"""
from __future__ import annotations

import sys
import subprocess
import unicodedata

from core.registry import tool


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _resolve(query: str):
    """Nombre/número → (etiqueta, numero_intl_sin_+) | lista de matches | None."""
    q = (query or "").strip()
    digits = "".join(c for c in q if c.isdigit())
    if len(digits) >= 7 and sum(c.isdigit() for c in q) > len(q) / 2:
        return (q, digits)                      # ya es un número
    try:
        from core import mac_contacts as mc
        matches = mc.find_by_name(q)
    except Exception:
        matches = []
    if not matches:
        return None
    exact = [m for m in matches if _norm(m[0]) == _norm(q)]
    if len(exact) == 1:
        return exact[0]
    if len(matches) == 1:
        return matches[0]
    return matches[:5]                          # ambiguo → que elija


@tool(
    name="facetime",
    description="Llama por FaceTime (SOLO Mac). USAR cuando el usuario diga 'llamá a X', 'llamalo/llamala', 'hacele una llamada a X', 'videollamada con X'. Resuelve el nombre contra la agenda de Apple (ej 'Mamá'). mode=audio (default, llamada normal) | video (videollamada). FaceTime pide confirmación con un click antes de llamar.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "contact": {"type": "STRING", "description": "Nombre del contacto (como en la agenda, ej 'Mamá') o número con código de país."},
            "mode": {"type": "STRING", "description": "audio (default) | video"},
        },
        "required": ["contact"],
    },
    category="communications",
)
def facetime(parameters: dict, player=None) -> str:
    if sys.platform != "darwin":
        return "FaceTime solo está disponible en Mac."
    who = (parameters.get("contact") or parameters.get("receiver") or "").strip()
    if not who:
        return "¿A quién llamo?"
    mode = (parameters.get("mode") or "audio").lower().strip()
    video = mode in ("video", "videollamada", "facetime")

    hit = _resolve(who)
    if hit is None:
        return (f"No encontré a '{who}' en tu agenda. Decime el nombre como figura "
                "en Contactos o pasame el número con código de país.")
    if isinstance(hit, list):
        opts = "; ".join(f"{n} (+{p})" for n, p in hit)
        return f"Hay varios contactos parecidos a '{who}': {opts}. ¿Cuál?"

    name, phone = hit
    scheme = "facetime" if video else "facetime-audio"
    url = f"{scheme}://+{phone}"
    try:
        subprocess.run(["open", url], check=True, timeout=10,
                       capture_output=True)
    except Exception as e:
        return f"No pude abrir FaceTime: {str(e)[:80]}"
    kind = "videollamada" if video else "llamada"
    if player:
        try:
            player.write_log(f"📞 FaceTime ({kind}) → {name}")
        except Exception:
            pass
    return f"📞 Iniciando {kind} de FaceTime a {name}. Confirmá con un click en la ventana de FaceTime."
