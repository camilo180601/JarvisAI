"""traductor — activa/desactiva/ajusta el modo intérprete de voz.

La traducción la hace el modelo de voz (Gemini, multilingüe). Esta skill devuelve
una DIRECTIVA fuerte que reconfigura el comportamiento dentro de la sesión de voz:
mientras está activo, JARVIS solo repite en el idioma destino lo que el usuario diga.

Recuerda el par de idiomas activo en un archivo de estado para poder INVERTIRLO
("invertí los idiomas") sin que el usuario los repita.
"""
from __future__ import annotations
import json
from pathlib import Path

_STATE = Path(__file__).resolve().parent / ".state.json"

# normalización ligera de nombres de idioma (acepta variantes y sin acento)
_LANGS = {
    "espanol": "español", "español": "español", "castellano": "español", "spanish": "español",
    "ingles": "inglés", "inglés": "inglés", "english": "inglés",
    "aleman": "alemán", "alemán": "alemán", "german": "alemán", "deutsch": "alemán",
    "frances": "francés", "francés": "francés", "french": "francés",
    "portugues": "portugués", "portugués": "portugués", "portuguese": "portugués",
    "italiano": "italiano", "italian": "italiano",
    "japones": "japonés", "japonés": "japonés", "japanese": "japonés",
    "chino": "chino", "mandarin": "chino", "chinese": "chino",
    "ruso": "ruso", "russian": "ruso", "coreano": "coreano", "korean": "coreano",
    "arabe": "árabe", "árabe": "árabe", "arabic": "árabe",
}


def _norm(lang: str | None) -> str:
    if not lang:
        return ""
    return _LANGS.get(lang.strip().lower(), lang.strip())


def _load_state() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(source: str, target: str) -> None:
    try:
        _STATE.write_text(json.dumps({"source": source, "target": target}), encoding="utf-8")
    except Exception:
        pass


def _clear_state() -> None:
    try:
        _STATE.unlink()
    except Exception:
        pass


def _activate(source: str, target: str) -> str:
    _save_state(source, target)
    return (
        f"[MODO TRADUCTOR ACTIVO — {source} → {target}] "
        f"A partir de AHORA y hasta que el usuario diga que salga del traductor, NO sos un asistente y "
        f"NO conversás. Sos un intérprete de voz. Regla estricta para CADA turno siguiente: "
        f"el usuario habla en {source}; vos decís EN VOZ ALTA ÚNICAMENTE la traducción a {target} de lo que dijo. "
        f"Nada más: sin saludar, sin responder preguntas, sin comentarios, sin explicar, sin nombrar el idioma. "
        f"Si el usuario hace una pregunta, NO la respondas — traducí la pregunta a {target}. "
        f"Solo salí de este modo si el usuario dice explícitamente 'pará el modo traductor', 'salí del traductor', "
        f"'modo normal' o 'dejá de traducir'; y si pide 'invertí los idiomas' o 'cambiá a X e Y', reconfigurás el par. "
        f"Ahora confirmá el modo en UNA frase corta en {source} (ej: 'Listo, traduzco de {source} a {target}. Hablá.') "
        f"y a partir del próximo turno solo traducí."
    )


def run(parameters: dict, player=None, speak=None) -> str:
    action = (parameters.get("action") or "on").strip().lower()

    if action in ("off", "stop", "salir", "desactivar", "normal", "parar"):
        _clear_state()
        return (
            "[MODO TRADUCTOR DESACTIVADO] Volvé a ser JARVIS, el asistente normal. "
            "Confirmá en una frase corta que saliste del modo traductor y respondé normal de nuevo. "
            "Decí algo como: 'Listo, salí del modo traductor.'"
        )

    if action in ("invert", "invertir", "swap", "al_reves"):
        st = _load_state()
        s, t = st.get("source"), st.get("target")
        if not s or not t:
            return ("No tengo un par de idiomas activo para invertir. "
                    "Primero activá el traductor (ej: 'traductor de español a inglés').")
        return _activate(t, s)  # invertido

    # action == on (activar o cambiar el par)
    source = _norm(parameters.get("source"))
    target = _norm(parameters.get("target"))

    if not target:
        return ("Para activar el traductor decime al menos el idioma DESTINO "
                "(ej: 'convertite en traductor de español a inglés').")
    if not source:
        source = "el idioma que hable el usuario"

    return _activate(source, target)
