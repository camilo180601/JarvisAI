"""practica_idioma — conversación por niveles MCER (A1–C2) en cualquier idioma.

La conversación la sostiene el modelo de voz (Gemini, multilingüe). Esta skill fija
idioma + nivel + tema y devuelve una DIRECTIVA fuerte que pone a JARVIS en modo tutor.
Recuerda el estado en un archivo para poder subir/bajar de nivel o cambiar idioma.
"""
from __future__ import annotations
import json
from pathlib import Path

_STATE = Path(__file__).resolve().parent / ".state.json"

_LANGS = {
    "espanol": "español", "español": "español", "spanish": "español",
    "ingles": "inglés", "inglés": "inglés", "english": "inglés",
    "aleman": "alemán", "alemán": "alemán", "german": "alemán", "deutsch": "alemán",
    "frances": "francés", "francés": "francés", "french": "francés",
    "portugues": "portugués", "portugués": "portugués", "portuguese": "portugués",
    "italiano": "italiano", "italian": "italiano",
    "japones": "japonés", "japonés": "japonés", "japanese": "japonés",
    "chino": "chino", "mandarin": "chino", "chinese": "chino",
    "ruso": "ruso", "russian": "ruso", "coreano": "coreano", "korean": "coreano",
}

_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
_LEVEL_ALIASES = {
    "principiante": "A1", "basico": "A1", "básico": "A1", "beginner": "A1",
    "elemental": "A2", "intermedio": "B1", "intermediate": "B1",
    "intermedio alto": "B2", "upper": "B2", "avanzado": "C1", "advanced": "C1",
    "experto": "C2", "nativo": "C2", "fluent": "C2",
}

# Cómo debe hablar JARVIS en cada nivel.
_LEVEL_GUIDE = {
    "A1": "frases MUY cortas y simples, solo presente, vocabulario básico, hablá LENTO y claro. Una idea por frase.",
    "A2": "frases cortas, presente y pasado simple, vocabulario cotidiano, ritmo pausado. Preguntas sencillas.",
    "B1": "conversación cotidiana fluida, varios tiempos verbales, vocabulario amplio pero común, ritmo natural moderado.",
    "B2": "conversación fluida sobre temas variados, conectores, algo de vocabulario específico, ritmo natural.",
    "C1": "matices, expresiones idiomáticas, temas abstractos, ritmo casi nativo, vocabulario rico.",
    "C2": "nivel nativo: idiomático, cultural, debate de temas complejos, ritmo y registro totalmente naturales.",
}


def _norm_lang(x: str | None) -> str:
    if not x:
        return ""
    return _LANGS.get(x.strip().lower(), x.strip())


def _norm_level(x: str | None) -> str:
    if not x:
        return ""
    s = x.strip().lower()
    if s.upper() in _LEVELS:
        return s.upper()
    return _LEVEL_ALIASES.get(s, "")


def _load() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(language: str, level: str, topic: str = "") -> None:
    try:
        _STATE.write_text(json.dumps({"language": language, "level": level, "topic": topic}),
                          encoding="utf-8")
    except Exception:
        pass


def _clear() -> None:
    try:
        _STATE.unlink()
    except Exception:
        pass


def _activate(language: str, level: str, topic: str = "") -> str:
    _save(language, level, topic)
    guide = _LEVEL_GUIDE.get(level, "")
    tema = (f" El tema de hoy es: {topic}." if topic else
            " Vos elegí un tema cotidiano y arrancá con una pregunta para romper el hielo.")
    return (
        f"[MODO PRÁCTICA DE IDIOMA — {language} nivel {level}] "
        f"A partir de AHORA y hasta que el usuario diga que salga de la práctica, sos un TUTOR de {language} "
        f"y un compañero de conversación. Hablá SIEMPRE en {language}, adaptado al nivel {level} del MCER: {guide} "
        f"Mantené una conversación de ida y vuelta: respondé lo que diga el usuario y SIEMPRE devolvé una pregunta "
        f"para que siga hablando.{tema} "
        f"Si el usuario comete un error notorio, corregilo con tacto y MUY brevemente (mostrá la forma correcta en "
        f"{language}), y seguí la charla sin cortar el ritmo. Si el usuario se traba o pide ayuda en español, "
        f"podés dar una pista corta, pero volvé enseguida a {language}. No rompas el nivel: no uses vocabulario ni "
        f"gramática por encima de {level}. "
        f"Comandos que el usuario puede dar en cualquier momento: 'subí/bajá el nivel', 'cambiá a <idioma>', "
        f"'salí de práctica'/'modo normal'. "
        f"Ahora SALUDÁ en {language} (nivel {level}) y arrancá la conversación con una primera pregunta."
    )


def run(parameters: dict, player=None, speak=None) -> str:
    action = (parameters.get("action") or "on").strip().lower()

    if action in ("off", "stop", "salir", "desactivar", "normal", "parar"):
        _clear()
        return ("[MODO PRÁCTICA DESACTIVADO] Volvé a ser JARVIS normal. Confirmá en una frase corta "
                "(en español) que terminaste la práctica y, si querés, felicitá brevemente al usuario por practicar.")

    st = _load()

    if action in ("level_up", "subir", "sube", "mas", "más"):
        if not st.get("language"):
            return "No hay práctica activa. Decime idioma y nivel (ej: 'practiquemos inglés B1')."
        cur = st.get("level", "A1")
        i = min(_LEVELS.index(cur) + 1, len(_LEVELS) - 1) if cur in _LEVELS else 0
        return _activate(st["language"], _LEVELS[i], st.get("topic", ""))

    if action in ("level_down", "bajar", "baja", "menos"):
        if not st.get("language"):
            return "No hay práctica activa. Decime idioma y nivel (ej: 'practiquemos inglés B1')."
        cur = st.get("level", "A2")
        i = max(_LEVELS.index(cur) - 1, 0) if cur in _LEVELS else 0
        return _activate(st["language"], _LEVELS[i], st.get("topic", ""))

    # action == on (activar o cambiar idioma/nivel/tema)
    language = _norm_lang(parameters.get("language")) or st.get("language", "")
    level = _norm_level(parameters.get("level")) or st.get("level", "")
    topic = (parameters.get("topic") or "").strip() or st.get("topic", "")

    if not language:
        return "¿Qué idioma querés practicar? (ej: 'practiquemos inglés, soy B1')."
    if not level:
        return (f"¿En qué nivel querés practicar {language}? Decime tu nivel MCER (A1, A2, B1, B2, C1 o C2) "
                "o 'principiante/intermedio/avanzado'.")

    return _activate(language, level, topic)
