"""nivel_idioma — examen adaptativo de nivel MCER (A1–C2) por voz.

JARVIS entrevista al usuario en el idioma, ajusta la dificultad según las respuestas
y al final estima el nivel. La conduce el modelo de voz (Gemini); esta skill activa
el modo y devuelve la directiva. La regla de SOUL.md lo mantiene turno a turno.
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


def _norm_lang(x: str | None) -> str:
    if not x:
        return ""
    return _LANGS.get(x.strip().lower(), x.strip())


def _save(language: str) -> None:
    try:
        _STATE.write_text(json.dumps({"language": language}), encoding="utf-8")
    except Exception:
        pass


def _load() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _clear() -> None:
    try:
        _STATE.unlink()
    except Exception:
        pass


def run(parameters: dict, player=None, speak=None) -> str:
    action = (parameters.get("action") or "on").strip().lower()

    if action in ("off", "stop", "salir", "terminar", "normal", "parar", "fin"):
        st = _load()
        _clear()
        lang = st.get("language", "el idioma")
        return (
            f"[EXAMEN DE NIVEL FINALIZADO — {lang}] Terminá el examen ahora: en español, dale al usuario su "
            f"NIVEL MCER estimado en {lang} (A1, A2, B1, B2, C1 o C2), con una justificación BREVE (2-3 puntos: "
            f"comprensión, vocabulario, gramática/fluidez) y un consejo corto. Después ofrecele practicar en ese "
            f"nivel con el modo práctica si quiere. Volvé a ser JARVIS normal."
        )

    language = _norm_lang(parameters.get("language")) or _load().get("language", "")
    if not language:
        return "¿De qué idioma querés que evalúe tu nivel? (ej: 'evaluá mi nivel de inglés')."

    _save(language)
    return (
        f"[MODO EXAMEN DE NIVEL — {language}] "
        f"A partir de AHORA sos un EXAMINADOR de {language} que estima el nivel MCER (A1–C2) del usuario mediante "
        f"una entrevista adaptativa por voz. Reglas: "
        f"1) Hacé las preguntas EN {language}, de a UNA por turno, y esperá la respuesta. "
        f"2) Empezá FÁCIL (nivel A1/A2: saludo, datos personales, presente) y, según cómo responde el usuario "
        f"(comprensión, vocabulario, gramática, fluidez), SUBÍ o BAJÁ la dificultad de la siguiente pregunta para "
        f"encontrar su techo: si responde bien y fluido, hacé la próxima más difícil (tiempos compuestos, temas "
        f"abstractos, opinión, hipótesis); si le cuesta o no entiende, bajá. "
        f"3) Evaluá también si ENTENDIÓ: podés preguntar cosas tipo '¿entendiste?' o pedir que reformule o resuma. "
        f"4) NO le digas el nivel en cada turno; tomá nota mentalmente y seguí. Mantené un tono amable y alentador. "
        f"5) Hacé entre 6 y 10 preguntas en total; cuando tengas una estimación clara (o el usuario diga "
        f"'terminá el examen'/'ya está'), CERRÁ vos: dale su nivel MCER estimado con una justificación breve y un consejo. "
        f"6) Si el usuario responde en español o pide ayuda, dale una pista corta y volvé a {language}. "
        f"Ahora SALUDÁ en {language}, explicá en una frase que le vas a hacer preguntas para medir su nivel, y hacé "
        f"la PRIMERA pregunta (fácil)."
    )
